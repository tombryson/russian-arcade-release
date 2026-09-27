"""Explicit, reusable Russian audio for server-owned lesson game clues.

The public key identifies exact text, never permission to synthesize client text.
Every read and write first resolves that key against this learner's frozen
lessons or games. Native-card audio is reused only from the selected owner's
current cards. Generated instruction audio is cached separately and may be
shared between learners entitled to the same authored clue.
"""
import hashlib
import json
import logging
import re

from repositories.card_repository import load_card
from repositories.learning_repository import LearningError, encoded, identifier, timestamp, transaction
from services.learning_assets import import_asset

logger = logging.getLogger(__name__)
POLICY_VERSION = 'journey-game-audio-v1'
LEASE_SECONDS = 300
FAILURE_MESSAGE = 'The audio could not be prepared. You can try again.'


class JourneyGameMediaService:
    def __init__(self, db_path, store, provider, authorize, *, clock=timestamp):
        self.db_path, self.store, self.provider = db_path, store, provider
        self.authorize, self.clock = authorize, clock

    def _context(self, conn, key):
        if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
            raise LearningError('not_found', 'This lesson audio is not available.', 404)
        context = self.authorize(conn, key)
        if (not isinstance(context, dict) or not isinstance(context.get('text'), str)
                or not context['text'] or hashlib.sha256(context['text'].encode('utf-8')).hexdigest() != key):
            raise LearningError('not_found', 'This lesson audio is not available.', 404)
        return context

    def _policy(self):
        # The choice is still random for each new recording. Store the chosen
        # voice in spec_json so retries and repeat listens preserve it exactly.
        speech = getattr(self.provider, 'speech', None)
        policy = {'version': POLICY_VERSION, 'provider': type(self.provider).__name__,
                  'model': getattr(speech, 'model', None),
                  'voices': list(getattr(speech, 'voice_ids', ()))}
        return hashlib.sha256(encoded(policy).encode('utf-8')).hexdigest()

    def _configured(self):
        if self.provider is None:
            return False
        # Injected providers use the same spec/generate boundary without keys.
        speech = getattr(self.provider, 'speech', None)
        if hasattr(self.provider, 'speech'):
            return bool(speech and getattr(speech, 'api_key', None) and getattr(speech, 'voice_ids', ()))
        return callable(getattr(self.provider, 'spec', None)) and callable(getattr(self.provider, 'generate', None))

    def _asset_row(self, conn, asset_id):
        if not asset_id:
            return None
        row = conn.execute('SELECT * FROM learning_assets WHERE id=?', (asset_id,)).fetchone()
        if row and row['media_type'].startswith('audio/') and self.store.path(row['storage_key']).is_file():
            return row
        return None

    def _owned_audio(self, conn, context):
        game_audio = self._game_audio(conn, context)
        if game_audio:
            return game_audio
        profile_id = context.get('profile_id')
        if not profile_id:
            return None
        rows = conn.execute(
            "SELECT DISTINCT j.asset_id,cv.id FROM native_card_media_jobs j "
            "JOIN card_versions original ON original.card_id=j.card_id "
            "JOIN native_card_generation_items g ON g.version_id=original.content_version_id "
            "JOIN native_card_batches b ON b.id=g.batch_id "
            "JOIN card_versions cv ON cv.card_id=j.card_id "
            "JOIN learning_content_versions v ON v.id=cv.content_version_id "
            "JOIN card_definitions d ON d.id=j.card_id "
            "WHERE b.owner_id=? AND j.kind='sentence_audio' AND j.status='saved' "
            "AND json_extract(j.spec,'$.text')=? AND d.retired=0 AND v.status='published' "
            "AND v.version=(SELECT MAX(v2.version) FROM learning_content_versions v2 WHERE v2.content_id=v.content_id) "
            "ORDER BY cv.id", (profile_id, context['text']),
        )
        for row in rows:
            _, item = load_card(conn, row['id'])
            if item.get('context') != context['text']:
                continue
            if not any(asset.get('id') == row['asset_id'] and asset.get('kind') == 'sentence_audio'
                       for asset in item.get('assets', [])):
                continue
            asset = self._asset_row(conn, row['asset_id'])
            if asset:
                return asset
        return None

    def _game_audio(self, conn, context):
        """A ready vocabulary game's recordings also serve its Listen button.

        Use the exact frozen example belonging to this profile or guest. The
        shared text hash alone never grants access to another learner's media.
        """
        profile_id, guest_token = context.get('profile_id'), context.get('guest_token')
        if profile_id:
            where, params = 'profile_id=?', (profile_id,)
        elif guest_token:
            where, params = 'profile_id IS NULL AND guest_token=?', (guest_token,)
        else:
            return None
        for row in conn.execute('SELECT content_json FROM journey_game_sessions WHERE ' + where + ' ORDER BY created_at DESC,rowid DESC', params):
            content = json.loads(row['content_json'])
            broadcast = content.get('broadcast', {})
            if broadcast.get('script') == context['text']:
                asset = self._asset_row(conn, broadcast.get('asset_id'))
                if asset:
                    return asset
            for example in content.get('vocabulary_refs', []):
                if example.get('sentence') != context['text']:
                    continue
                for reference in example.get('assets', []):
                    if reference.get('kind') != 'sentence_audio':
                        continue
                    asset = self._asset_row(conn, reference.get('id'))
                    if asset:
                        return asset
        return None

    def _cached(self, conn, key):
        return conn.execute('SELECT * FROM journey_game_media WHERE text_hash=? AND policy_hash=?',
                            (key, self._policy())).fetchone()

    def reusable_audio(self, conn, text):
        """Internal native-card bridge for already generated authored audio.

        Never reads private card recordings or creates media. The saved voice
        and provider policy travel with the asset instead of being relabelled.
        """
        key = hashlib.sha256(text.encode('utf-8')).hexdigest()
        cached = self._cached(conn, key)
        if cached and cached['status'] == 'ready' and self._asset_row(conn, cached['asset_id']):
            return {'asset_id': cached['asset_id'], 'spec': json.loads(cached['spec_json'])}
        return None

    @staticmethod
    def _ready(key):
        return {'status': 'ready', 'url': '/api/v1/games/media/' + key}

    def _state(self, conn, key, context):
        if self._owned_audio(conn, context):
            return self._ready(key)
        cached = self._cached(conn, key)
        if cached and self._asset_row(conn, cached['asset_id']):
            return self._ready(key)
        if not self._configured():
            return {'status': 'unavailable', 'message': 'Audio is not connected yet. You can still read the Russian clue.'}
        if cached and (cached['status'] in ('ready', 'failed')):
            return {'status': 'failed', 'message': FAILURE_MESSAGE}
        return {'status': 'pending', 'message': 'Listen to prepare the Russian audio.'}

    def status(self, key):
        """Read-only: opening a game or polling never contacts a provider."""
        with transaction(self.db_path) as conn:
            return self._state(conn, key, self._context(conn, key))

    def prepare(self, key):
        with transaction(self.db_path, write=True) as conn:
            context = self._context(conn, key)
            state = self._state(conn, key, context)
            if state['status'] in ('ready', 'unavailable'):
                return state
            row = self._cached(conn, key)
            now = self.clock()
            if row and row['status'] == 'running' and row['lease_until'] > now:
                return {'status': 'pending', 'message': 'The audio is being prepared.'}
            if row:
                job_id, spec = row['id'], json.loads(row['spec_json'])
            else:
                job_id = identifier()
                spec = self.provider.spec('sentence_audio', {'context': context['text']}, '')
                # Providers cannot silently replace the frozen lesson wording.
                if spec.get('text') != context['text']:
                    raise LearningError('invalid_media', 'The audio does not match this lesson.', 409)
                conn.execute('INSERT INTO journey_game_media(id,text_hash,text,policy_hash,spec_json,created_at,updated_at) '
                             'VALUES (?,?,?,?,?,?,?)',
                             (job_id, key, context['text'], self._policy(), encoded(spec), now, now))
            claim = identifier()
            conn.execute("UPDATE journey_game_media SET status='running',claim_id=?,lease_until=?,error=NULL,updated_at=? WHERE id=?",
                         (claim, now + LEASE_SECONDS, now, job_id))
        # Do not hold a database transaction across the paid network request.
        try:
            data = self.provider.generate('sentence_audio', spec)
            asset_id = import_asset(self.db_path, self.store, data, 'Russian audio for a frozen First steps game clue')
            with transaction(self.db_path, write=True) as conn:
                if not self._asset_row(conn, asset_id):
                    raise ValueError('The provider did not return valid audio')
                conn.execute("UPDATE journey_game_media SET status='ready',asset_id=?,lease_until=0,error=NULL,updated_at=? "
                             'WHERE id=? AND claim_id=?', (asset_id, self.clock(), job_id, claim))
        except Exception as error:
            # Provider messages can contain request details; keep them out of
            # both the browser response and the application log.
            logger.warning('Journey game audio failed (%s)', type(error).__name__)
            with transaction(self.db_path, write=True) as conn:
                conn.execute("UPDATE journey_game_media SET status='failed',lease_until=0,error=?,updated_at=? WHERE id=? AND claim_id=?",
                             (FAILURE_MESSAGE, self.clock(), job_id, claim))
        return self.status(key)

    def asset(self, key):
        with transaction(self.db_path) as conn:
            context = self._context(conn, key)
            row = self._owned_audio(conn, context)
            cached = self._cached(conn, key)
            row = row or (self._asset_row(conn, cached['asset_id']) if cached else None)
            if not row:
                raise LearningError('not_found', 'Listen first to prepare this lesson audio.', 404)
            return self.store.path(row['storage_key']), row['media_type']
