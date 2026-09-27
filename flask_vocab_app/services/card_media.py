"""Native media stages reuse saved text and keep review identities stable."""
import base64
import copy
import json
import logging
import random
import tempfile
from pathlib import Path

import requests
from services.elevenlabs_service import ElevenLabsService
from services.learning_assets import import_asset
from services.card_metadata import enrich_item
from services.ai_trial_budget import TrialDenied
from repositories.card_repository import load_card
from repositories.learning_repository import LearningError, encoded, identifier, require_access, timestamp, transaction

logger = logging.getLogger(__name__)
KINDS = ('image', 'word_audio', 'sentence_audio')


class NativeMediaProvider:
    def __init__(self, images, speech):
        self.images, self.speech = images, speech

    def spec(self, kind, item, form):
        if kind == 'image':
            return {'model': self.images.image_model, 'text': item['context'], 'word': form, 'no_text': True}
        return {'model': self.speech.model, 'voice_id': random.choice(self.speech.voice_ids),
                'text': form if kind == 'word_audio' else item['context']}

    def generate(self, kind, spec):
        if kind == 'image':
            result = self.images.generate_image_url(spec['text'], spec['word'], model=spec['model'], no_text=spec.get('no_text',True))
            if not result:
                raise ValueError('No image returned')
            if result.startswith('data:image/'):
                return base64.b64decode(result.split(',',1)[1], validate=True)
            response = requests.get(result, timeout=30)
            response.raise_for_status()
            return response.content
        with tempfile.TemporaryDirectory(prefix='native-audio-') as directory:
            speech = ElevenLabsService(self.speech.api_key, directory, voice_ids=(spec['voice_id'],), model=spec['model'], config=self.speech.config)
            result = speech.generate_audio(spec['text'], 'audio.mp3')
            if not result:
                raise ValueError('No audio returned')
            return (Path(directory)/result).read_bytes()


class CardMediaService:
    def __init__(self, db_path, content, provider, *, household=False, clock=timestamp):
        self.db_path, self.content, self.provider = db_path, content, provider
        self.household, self.clock = household, clock
        self.shared_audio = None

    def _card(self, conn, credential, card_id):
        require_access(conn, credential, self.clock(), adult=True)
        row = conn.execute('SELECT cv.id FROM card_versions cv JOIN learning_content_versions v ON v.id=cv.content_version_id '
                           'WHERE cv.card_id=? AND v.version=(SELECT MAX(version) FROM learning_content_versions WHERE content_id=v.content_id) ORDER BY v.version DESC,v.rowid DESC LIMIT 1',(card_id,)).fetchone()
        if not row:
            raise LearningError('not_found','This card has been replaced or is no longer available.',404)
        meta,item = load_card(conn,row['id'],published=False)
        if json.loads(meta['payload'])['schema_version'] != 2:
            raise LearningError('unsupported_card','This older card format needs conversion before adding media.',409)
        if meta['retired'] or meta['status']=='withdrawn':
            raise LearningError('content_unavailable','This card was deleted.',409)
        return meta,item

    def queue(self, credential, card_id, kinds=KINDS):
        with transaction(self.db_path,write=True) as conn:
            meta,item = self._card(conn,credential,card_id)
            form = conn.execute('SELECT form FROM forms WHERE id=?',(item.get('form_id'),)).fetchone()
            target = form['form'] if form else meta['lemma']
            attached = {asset.get('kind') for asset in item.get('assets',[])}
            for kind in kinds:
                if kind not in KINDS:
                    raise LearningError('invalid_input','Unknown media type.')
                if kind in attached or conn.execute('SELECT 1 FROM native_card_media_jobs WHERE card_id=? AND kind=?',(card_id,kind)).fetchone():
                    continue
                spec = self.provider.spec(kind,item,target)
                cached = self.shared_audio.reusable_audio(conn, item['context']) if kind == 'sentence_audio' and self.shared_audio else None
                if cached:
                    spec = cached['spec']
                conn.execute('INSERT INTO native_card_media_jobs(id,card_id,kind,spec,asset_id,created_at) VALUES (?,?,?,?,?,?)',
                             (identifier(),card_id,kind,encoded(spec),cached['asset_id'] if cached else None,self.clock()))
        self.attach(credential,card_id)
        return self.status(credential,card_id)

    def status(self, credential, card_id):
        with transaction(self.db_path) as conn:
            self._card(conn,credential,card_id)
            jobs = [dict(r) for r in conn.execute('SELECT kind,status,error FROM native_card_media_jobs WHERE card_id=? ORDER BY kind',(card_id,))]
            return {'card_id':card_id,'jobs':jobs,'complete':all(j['status'] in ('saved','failed') for j in jobs),
                    'saved':sum(j['status']=='saved' for j in jobs),'failed':sum(j['status']=='failed' for j in jobs)}

    def retry(self, credential, card_id):
        with transaction(self.db_path,write=True) as conn:
            self._card(conn,credential,card_id)
            conn.execute("UPDATE native_card_media_jobs SET status='pending',error=NULL WHERE card_id=? AND status='failed'",(card_id,))
        return self.status(credential,card_id)

    def advance(self, credential, card_id):
        with transaction(self.db_path,write=True) as conn:
            self._card(conn,credential,card_id)
            running = conn.execute("SELECT 1 FROM native_card_media_jobs WHERE card_id=? AND status='running' AND lease_until>?",(card_id,self.clock())).fetchone()
            row = None if running else conn.execute("SELECT * FROM native_card_media_jobs WHERE card_id=? AND (status='pending' OR (status='running' AND lease_until<=?)) ORDER BY created_at,rowid LIMIT 1",(card_id,self.clock())).fetchone()
            job = dict(row) if row else None
            if job:
                claim = identifier()
                conn.execute("UPDATE native_card_media_jobs SET status='running',claim_id=?,lease_until=? WHERE id=?",(claim,self.clock()+300,job['id']))
        if running:
            return self.status(credential,card_id)
        if job:
            try:
                asset = job['asset_id']
                if not asset:
                    data = self.provider.generate(job['kind'],json.loads(job['spec']))
                    asset = import_asset(self.db_path,self.content.store,data,'Generated '+job['kind']+' for native card '+card_id)
                with transaction(self.db_path,write=True) as conn:
                    self._card(conn,credential,card_id)
                    updated = conn.execute("UPDATE native_card_media_jobs SET asset_id=? WHERE id=? AND claim_id=?",(asset,job['id'],claim)).rowcount
                    if not updated:
                        raise LearningError('media_changed','Another request is handling this media.',409)
                self.attach(credential,card_id)
                with transaction(self.db_path,write=True) as conn:
                    conn.execute("UPDATE native_card_media_jobs SET status='saved',lease_until=0,error=NULL WHERE id=? AND claim_id=?",(job['id'],claim))
            except Exception as error:
                logger.warning('Native %s failed (%s)',job['kind'],type(error).__name__)
                message = str(error) if isinstance(error, TrialDenied) else 'Could not create this media. Retry when the provider is available.'
                with transaction(self.db_path,write=True) as conn:
                    conn.execute("UPDATE native_card_media_jobs SET status='failed',error=?,lease_until=0 WHERE id=? AND claim_id=?",
                                 (message,job['id'],claim))
                if isinstance(error, TrialDenied):
                    raise
        else:
            self.attach(credential,card_id)
        return self.status(credential,card_id)

    def attach(self, credential, card_id):
        with transaction(self.db_path) as conn:
            meta,item = self._card(conn,credential,card_id)
            pack = json.loads(meta['payload']);updated = copy.deepcopy(item)
            enrich_item(conn,updated)
            assets = {a.get('kind',a['id']):a for a in updated.get('assets',[])}
            for job in conn.execute("SELECT * FROM native_card_media_jobs WHERE card_id=? AND asset_id IS NOT NULL",(card_id,)):
                role = 'prompt' if item['direction']=='ru-en' or job['kind']=='image' else 'answer'
                assets[job['kind']] = {'id':job['asset_id'],'role':role,'kind':job['kind']}
            if assets:
                updated['assets'] = sorted(assets.values(),key=lambda a:(a.get('kind',''),a['id']))
            changed = updated != item
            pack['items'] = [updated if i['id']==item['id'] else i for i in pack['items']]
        version = self.content.import_draft(pack,access_id=credential,expected_base=meta['content_version_id']) if changed else meta['content_version_id']
        if not self.household and self.content.inspect(credential,version)['status']=='draft':
            self.content.publish(credential,version,'Me')
        # Ungraded occurrences may use richer support for the identical objective.
        # Graded occurrences and all historical events remain pinned to their version.
        if not self.household:
            with transaction(self.db_path,write=True) as conn:
                cv = conn.execute('SELECT id FROM card_versions WHERE content_version_id=? AND card_id=?',(version,card_id)).fetchone()[0]
                sessions = [r[0] for r in conn.execute("SELECT DISTINCT i.session_id FROM review_session_items i JOIN learning_sessions s ON s.id=i.session_id WHERE i.card_id=? AND s.status='active' AND i.card_version_id<>? AND NOT EXISTS(SELECT 1 FROM review_events e WHERE e.occurrence_id=i.id)",(card_id,cv))]
                for session_id in sessions:
                    conn.execute('UPDATE review_session_items SET card_version_id=? WHERE session_id=? AND card_id=? AND NOT EXISTS(SELECT 1 FROM review_events e WHERE e.occurrence_id=review_session_items.id)',(cv,session_id,card_id))
                    conn.execute('UPDATE review_session_cards SET card_version_id=? WHERE session_id=? AND card_id=? AND answered=0',(cv,session_id,card_id))
                    conn.execute('UPDATE learning_sessions SET revision=revision+1 WHERE id=?',(session_id,))
