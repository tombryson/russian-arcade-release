"""Generate native cards from the same vocabulary and filters as the Anki tool."""
import json
import hashlib
import logging
import re

from contracts.learning import fields, key, reject
from contracts.flashcards import objective
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, require_access, timestamp, transaction
from utils.pos_case import POS_MAP
from services.card_metadata import metadata_for
from services.lesson_cards import batch_source
from repositories.card_repository import load_card

logger = logging.getLogger(__name__)
CASES = {'instr':'ablt', 'prep':'loct'}


class CardGenerationService:
    def __init__(self, db_path, content, provider, *, household=False, media=None, clock=timestamp, vocabulary=None, config=None):
        self.db_path, self.content, self.provider = db_path, content, provider
        self.household, self.clock = household, clock
        self.media = media
        self.vocabulary = vocabulary
        self.config = config if config is not None else {}

    @property
    def max_quantity(self):
        return 5 if self.config.get('HOSTED_AI_TRIAL') else 20

    def _owner(self, conn, credential):
        access = require_access(conn, credential, self.clock(), adult=True)
        return 'household' if self.household else access['profile_id']

    def options(self, data):
        fields(data, {'kind','quantity'}, {'difficulty','pos','case','topic','word_id','max_cards','audio','image'})
        result = dict(data)
        for name in ("audio", "image"):
            if name in data and type(data[name]) is not bool:
                reject("Choose whether to include audio and pictures.")
        if data['kind'] not in ('ru-en','en-ru','ru-cloze'):
            reject('Choose a flashcard type.')
        for name, maximum, default in (('quantity',self.max_quantity,5),('max_cards',20,1)):
            value = data.get(name,default)
            if type(value) is not int or not 1 <= value <= maximum:
                if name == 'quantity' and self.config.get('HOSTED_AI_TRIAL'):
                    reject('Choose between 1 and 5 cards per demo batch.')
                reject(f'{name.replace("_"," ").capitalize()} must be between 1 and {maximum}.')
            result[name] = value
        for name in ('difficulty','word_id'):
            if data.get(name) is not None and (type(data[name]) is not int or data[name] < 1 or (name=='difficulty' and data[name]>8)):
                reject('Choose a valid word and difficulty.')
        for name in ('pos','case','topic'):
            if name in data and (not isinstance(data[name],str) or len(data[name])>120):
                reject('Choose valid filters.')
        if data.get('case','') not in ('','nomn','gent','datv','accs','ablt','loct','instr','prep'):
            reject('Choose a supported grammatical case.')
        result['case'] = CASES.get(data.get('case'),data.get('case',''))
        return result

    def select(self, conn, options, owner=None):
        conditions, parameters = ['1=1'], []
        if options.get('word_id'):
            conditions.append('w.id=?'); parameters.append(options['word_id'])
        if options.get('pos'):
            tags = sorted({options['pos']} | {k for k,v in POS_MAP.items() if v==options['pos']})
            conditions.append('w.pos IN ('+','.join('?' for _ in tags)+')'); parameters.extend(tags)
        if options.get('topic'):
            conditions.append("EXISTS(SELECT 1 FROM json_each(CASE WHEN json_valid(w.topic) THEN w.topic ELSE '[]' END) WHERE value=?)")
            parameters.append(options['topic'])
        # Counts here are native active cards, never the old Anki export counter.
        conditions.append("(SELECT COUNT(DISTINCT d.id) FROM card_definitions d JOIN card_versions cv ON cv.card_id=d.id JOIN learning_content_versions v ON v.id=cv.content_version_id WHERE d.word_id=w.id AND d.retired=0 AND v.status='published' AND v.version=(SELECT MAX(v2.version) FROM learning_content_versions v2 WHERE v2.content_id=v.content_id AND v2.status='published')) < ?")
        parameters.append(options['max_cards'])
        rows = conn.execute('SELECT w.* FROM words w WHERE '+' AND '.join(conditions)+' ORDER BY w.id',parameters).fetchall()
        from services.form_selection import coverage, choose_form
        word_use, form_use, grammar_use = coverage(conn, owner)
        rows = sorted(rows, key=lambda row: (word_use[row['id']], row['id']))
        selected = []
        for row in rows:
            form_sql = 'SELECT id,form,tags,form_difficulty FROM forms WHERE word_id=?'
            args = [row['id']]
            if options.get('case'):
                form_sql += " AND json_extract(CASE WHEN json_valid(tags) THEN tags ELSE '{}' END,'$.case')=?"
                args.append(options['case'])
            if options.get('difficulty'):
                form_sql += ' AND COALESCE(form_difficulty,?)=?'
                args.extend([row['lemma_difficulty'], options['difficulty']])
            form = choose_form(conn.execute(form_sql, args).fetchall(), row['lemma'], form_use, grammar_use)
            if options.get('difficulty') and not form and (row['lemma_difficulty'] != options['difficulty'] or conn.execute('SELECT 1 FROM forms WHERE word_id=?', (row['id'],)).fetchone()):
                continue
            if options.get('case') and not form:
                continue
            selected.append({'word_id':row['id'],'lemma':row['lemma'],'pos':row['pos'],
                             'form_id':form['id'] if form else None,'form':form['form'] if form else row['lemma'],
                             'tags':json.loads(form['tags'] or '{}') if form else {},
                             'metadata':metadata_for(row,form), 'mnemonic':row['mnemonic'] or ''})
            if len(selected)==options['quantity']:
                break
        return selected

    def preview(self, credential, options):
        options = self.options(options)
        with transaction(self.db_path) as conn:
            owner = self._owner(conn,credential)
            return self.select(conn,options,owner)

    def create(self, credential, data):
        fields(data, {'submission_id','options'}); key(data['submission_id'])
        options = self.options(data['options']); digest = payload_hash(options)
        with transaction(self.db_path,write=True) as conn:
            owner = self._owner(conn,credential)
            old = conn.execute('SELECT * FROM native_card_batches WHERE owner_id=? AND request_key=?',(owner,data['submission_id'])).fetchone()
            if old:
                if old['request_hash']!=digest:
                    raise LearningError('idempotency_conflict','This generation request has different settings.',409)
                batch = old['id']
            else:
                selected = self.select(conn,options,owner)
                if not selected:
                    raise LearningError('no_matching_words','No words match. Change the filters or allow more cards per word.',409)
                batch = identifier()
                conn.execute('INSERT INTO native_card_batches VALUES (?,?,?,?,?,?)',(batch,owner,data['submission_id'],digest,encoded(options),self.clock()))
                for position,word in enumerate(selected):
                    conn.execute('INSERT INTO native_card_generation_items(id,batch_id,position,selection) VALUES (?,?,?,?)',(identifier(),batch,position,encoded(word)))
        return self.read(credential,batch)

    def _batch(self, conn, credential, batch_id):
        owner = self._owner(conn,credential)
        batch = conn.execute('SELECT * FROM native_card_batches WHERE id=? AND owner_id=?',(batch_id,owner)).fetchone()
        if not batch:
            raise LearningError('not_found','Generation batch not found.',404)
        return batch

    def _batch_items(self, conn, credential, batch_id):
        """Own items plus explicitly selected older native items, never batches.

        References are server-authored and point straight to original items.
        Reading them does not traverse another batch's references or generate
        unrelated cards. Ownership and creation order also reject cycles.
        """
        batch = self._batch(conn, credential, batch_id)
        options = json.loads(batch['options'])
        items = [dict(row) | {'batch_options': options, 'reused': False}
                 for row in conn.execute('SELECT * FROM native_card_generation_items WHERE batch_id=? ORDER BY position', (batch_id,))]
        source = options.get('first_steps')
        if source is not None and not isinstance(source, dict):
            raise LearningError('invalid_generation_references', 'This card request has invalid saved references.', 409)
        references = source.get('reused_items', []) if isinstance(source, dict) else []
        if not isinstance(references, list) or len(references) > 500:
            raise LearningError('invalid_generation_references', 'This card request has invalid saved references.', 409)
        order = conn.execute('SELECT rowid FROM native_card_batches WHERE id=?', (batch_id,)).fetchone()[0]
        seen = {item['id'] for item in items}
        for reference in references:
            legacy = {'batch_id', 'item_id', 'identity'}
            native = legacy | {'card_id', 'content_version_id'}
            if (not isinstance(reference, dict) or set(reference) not in (legacy, native)
                    or any(not isinstance(value, str) or not value for value in reference.values())):
                raise LearningError('invalid_generation_references', 'This card request has invalid saved references.', 409)
            row = conn.execute(
                'SELECT i.*,b.options AS batch_options FROM native_card_generation_items i '
                'JOIN native_card_batches b ON b.id=i.batch_id '
                'WHERE i.id=? AND i.batch_id=? AND b.owner_id=? AND b.rowid<?',
                (reference['item_id'], reference['batch_id'], batch['owner_id'], order),
            ).fetchone()
            selection = json.loads(row['selection']) if row else None
            original = selection.get('first_steps_source') if isinstance(selection, dict) else None
            valid = bool(row and isinstance(original, dict) and original.get('identity') == reference['identity'])
            if row and set(reference) == native:
                valid = (reference['identity'] == payload_hash({name: reference[name] for name in ('card_id', 'content_version_id')})
                         and bool(conn.execute('SELECT 1 FROM learning_content_versions original JOIN learning_content_versions frozen '
                                               'ON frozen.content_id=original.content_id WHERE original.id=? AND frozen.id=?',
                                               (row['version_id'], reference['content_version_id'])).fetchone())
                         and bool(conn.execute('SELECT 1 FROM card_versions WHERE content_version_id=? AND card_id=?',
                                               (reference['content_version_id'], reference['card_id'])).fetchone()))
            if not valid:
                raise LearningError('invalid_generation_references', 'An earlier card request is not available to this batch.', 409)
            if row['id'] not in seen:
                items.append(dict(row) | {'batch_options': json.loads(row['batch_options']), 'reused': True,
                                          'reference_card_id': reference.get('card_id')})
                seen.add(row['id'])
        return batch, items

    def read(self, credential, batch_id):
        with transaction(self.db_path) as conn:
            batch, selected = self._batch_items(conn,credential,batch_id)
            options = json.loads(batch['options'])
            items = []
            for row in selected:
                item_options = row['batch_options']
                required = (['image'] if item_options.get('image') else []) + (['word_audio','sentence_audio'] if item_options.get('audio') else [])
                word = json.loads(row['selection'])
                item = {'id':row['id'],'batch_id':row['batch_id'],'reused':row['reused'],'word':word['form'],'status':row['status'],'error':row['error'],'version_id':row['version_id'],'origin':word.get('lesson_source',{}).get('origin')}
                if row['version_id']:
                    card = (conn.execute('SELECT id,card_id FROM card_versions WHERE card_id=? ORDER BY rowid DESC LIMIT 1',
                                         (row['reference_card_id'],)).fetchone() if row.get('reference_card_id') else
                            conn.execute('SELECT id,card_id FROM card_versions WHERE content_version_id=?',(row['version_id'],)).fetchone())
                    latest = conn.execute("SELECT cv.id FROM card_versions cv JOIN learning_content_versions v ON v.id=cv.content_version_id JOIN card_definitions d ON d.id=cv.card_id WHERE cv.card_id=? AND d.retired=0 AND v.status IN ('draft','published') AND v.version=(SELECT MAX(version) FROM learning_content_versions WHERE content_id=v.content_id) ORDER BY v.version DESC,v.rowid DESC LIMIT 1",(card['card_id'],)).fetchone() if card else None
                    if not latest:
                        item.update(status='removed',version_id=None)
                        items.append(item)
                        continue
                    item['card_version_id'] = latest['id']
                    item['card_id'] = card['card_id']
                    _, current = load_card(conn, latest['id'], published=False)
                    item['word'] = current['prompt'] if current['direction'] == 'ru-en' else current['answer']
                    if self.media:
                        jobs = [dict(j) for j in conn.execute('SELECT kind,status,error FROM native_card_media_jobs WHERE card_id=?',(card['card_id'],))]
                        attached = self._reusable_assets(conn, current.get('assets', []))
                        jobs.extend({'kind': asset['kind'], 'status': 'saved', 'error': None} for asset in attached
                                    if asset['kind'] not in {job['kind'] for job in jobs})
                        item['media_jobs'] = jobs
                        item['media_expected'] = len(set(required) | {j['kind'] for j in jobs})
                    item.update(english=current.get('cue_en') or (current['answer'] if current['direction'] == 'ru-en' else current['prompt'] if current['direction'] == 'en-ru' else ''),
                                sentence=current['context'], notes=current.get('explanation', ''))
                items.append(item)
            return {'id':batch_id,'items':items,'household':self.household,'source':batch_source(conn,batch_id), 'first_steps':options.get('first_steps'),
                    'complete':all(i['status'] in ('saved','failed','removed') and len(i.get('media_jobs',[])) >= i.get('media_expected',0) and all(j['status'] in ('saved','failed') for j in i.get('media_jobs',[])) for i in items),
                    'saved':sum(i['status']=='saved' for i in items), 'total':len(items)}

    def enrich_batch(self, credential, batch_id):
        """Complete captured vocabulary before freezing its card hints.

        Existing published cards stay immutable. Only queued lesson/game items
        participate; ordinary vocabulary reviews never trigger enrichment.
        """
        if self.vocabulary is None:
            return
        with transaction(self.db_path) as conn:
            _, items = self._batch_items(conn, credential, batch_id)
            selected = []
            for item in items:
                word = json.loads(item['selection'])
                if (item['status'] not in ('saved', 'removed') and not item['version_id']
                        and (word.get('lesson_source') or word.get('first_steps_source'))):
                    selected.append((item['id'], word['word_id']))
        if not selected:
            return
        result = self.vocabulary.enrich_words(list(dict.fromkeys(word_id for _, word_id in selected)))
        if result['pending']:
            raise LearningError('vocabulary_enrichment_pending',
                                'Your selected words are saved. Their topics and memory hints could not be prepared yet. Try again to finish these cards.', 503)
        with transaction(self.db_path, write=True) as conn:
            self._batch(conn, credential, batch_id)
            for item_id, word_id in selected:
                item = conn.execute('SELECT selection,status,version_id FROM native_card_generation_items WHERE id=?', (item_id,)).fetchone()
                if not item or item['status'] in ('saved', 'removed') or item['version_id']:
                    continue
                word = json.loads(item['selection'])
                row = conn.execute('SELECT * FROM words WHERE id=?', (word_id,)).fetchone()
                form = conn.execute('SELECT * FROM forms WHERE id=? AND word_id=?', (word.get('form_id'), word_id)).fetchone()
                word.update(mnemonic=row['mnemonic'] or '', metadata=metadata_for(row, form))
                conn.execute('UPDATE native_card_generation_items SET selection=? WHERE id=?', (encoded(word), item_id))

    def next(self, credential, batch_id):
        self.enrich_batch(credential, batch_id)
        with transaction(self.db_path,write=True) as conn:
            batch, selected = self._batch_items(conn,credential,batch_id)
            options = json.loads(batch['options'])
            item_options = {row['id']: row['batch_options'] for row in selected}
            row = next((row for row in selected if row['status'] == 'pending' or
                        row['status'] in ('running','generated') and row['lease_until'] <= self.clock()), None)
            if not row:
                item = None
            else:
                item = dict(row); claim = identifier()
                options = item['batch_options']
                conn.execute("UPDATE native_card_generation_items SET status='running',claim_id=?,lease_until=? WHERE id=?",(claim,self.clock()+120,item['id']))
        if not item:
            saved = self.read(credential,batch_id)
            for card in saved['items']:
                if self.media and card.get('card_id') and len(card.get('media_jobs',[])) < card.get('media_expected',0):
                    media_options = item_options[card['id']]
                    kinds = (['image'] if media_options.get('image') else []) + (['word_audio','sentence_audio'] if media_options.get('audio') else [])
                    self.media.queue(credential,card['card_id'],kinds)
                    self.media.advance(credential,card['card_id'])
                    break
                if self.media and any(j['status'] in ('pending','running') for j in card.get('media_jobs',[])):
                    self.media.advance(credential,card['card_id'])
                    break
            return self.read(credential,batch_id)
        try:
            word = json.loads(item['selection'])
            response = json.loads(item['response']) if item['response'] else self.provider.generate_native_card(word,options['kind'])
            pack = self.pack(item['id'],word,options,response)
            with transaction(self.db_path,write=True) as conn:
                self._batch(conn,credential,batch_id)
                assets = self._reusable_assets(conn, word.get('reused_assets', []))
                if assets:
                    pack['items'][0]['assets'] = [{**asset, 'role': 'prompt' if asset['kind'] == 'image' or options['kind'] == 'ru-en' else 'answer'} for asset in assets]
                updated = conn.execute("UPDATE native_card_generation_items SET response=?,status='generated' WHERE id=? AND claim_id=?",(encoded(response),item['id'],claim)).rowcount
                if not updated:
                    raise LearningError('generation_changed','This card is already being handled by another request.',409)
            # Persist the provider result first. A restart reuses that exact result.
            source = word.get('lesson_source')
            if source:
                label = 'New example based on lesson' if source.get('origin')=='example' else 'From lesson'
                pack['source'] = f"{label} {source['lesson_id']}, revision {source['revision_id']}, page {source['page']}. Context and translation: {source['model']}."
            elif word.get('first_steps_source'):
                origin = word['first_steps_source']
                label = {'game': 'Saved Journey game practice: ', 'course': 'Authored course letter: '}.get(origin.get('kind'), 'Authored First steps lesson: ')
                pack['source'] = label + origin['title'] + '. ' + origin['url']
                if word.get('practice_source', {}).get('kind') == 'lesson':
                    pack['source'] += ' Lesson: ' + word['practice_source']['title'] + '. ' + word['practice_source']['url']
            else:
                pack['source'] += ' Model: '+str(getattr(self.provider,'flashcard_model','configured'))+'.'
            version = self.content.import_draft(pack,access_id=credential)
            if not self.household and self.content.inspect(credential,version)['status']=='draft':
                self.content.publish(credential,version,'Me')
            with transaction(self.db_path,write=True) as conn:
                self._batch(conn,credential,batch_id)
                conn.execute("UPDATE native_card_generation_items SET status='saved',version_id=?,lease_until=0 WHERE id=? AND claim_id=?",(version,item['id'],claim))
            if self.media:
                kinds = (['image'] if options.get('image') else []) + (['word_audio','sentence_audio'] if options.get('audio') else [])
                if kinds:
                    self.media.queue(credential,pack['items'][0]['card_id'],kinds)
        except Exception as error:
            logger.warning('Native card generation failed (%s)',type(error).__name__)
            from services.ai_trial_budget import TrialDenied
            message = str(error) if isinstance(error,(LearningError, TrialDenied)) else 'This card could not be generated. The other cards are kept.'
            with transaction(self.db_path,write=True) as conn:
                conn.execute("UPDATE native_card_generation_items SET status='failed',error=?,lease_until=0 WHERE id=? AND claim_id=? AND status<>'saved'",(message,item['id'],claim))
            if isinstance(error, TrialDenied):
                raise
        return self.read(credential,batch_id)

    def _reusable_assets(self, conn, assets):
        """Only intact server-saved media may bypass a generation job."""
        ready = {}
        for asset in assets if isinstance(assets, list) else []:
            if not isinstance(asset, dict) or asset.get('kind') not in ('image', 'word_audio', 'sentence_audio'):
                continue
            row = conn.execute('SELECT * FROM learning_assets WHERE id=?', (asset.get('id'),)).fetchone()
            if not row or not row['media_type'].startswith('image/' if asset['kind'] == 'image' else 'audio/'):
                continue
            path = self.content.store.path(row['storage_key'])
            if not path.is_file() or path.stat().st_size != row['byte_size'] or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                continue
            ready[asset['kind']] = {'id': row['id'], 'kind': asset['kind']}
        return list(ready.values())

    @staticmethod
    def pack(item_id, word, options, response):
        fields(response, {'english','sentence','sentence_english','notes'})
        if any(not isinstance(value,str) or len(value)>2000 for value in response.values()) or not all(response[k].strip() for k in ('english','sentence','sentence_english')):
            reject('The generated card was incomplete. Try generating another.')
        sentence = response['sentence'].strip()
        matches = list(re.finditer(r'(?<!\w)'+re.escape(word['form'])+r'(?!\w)',sentence,re.I))
        if len(matches)!=1:
            reject('The generated example did not use the selected word exactly once. Try generating another.')
        match = matches[0]; answer = match.group()
        direction = options['kind']
        prompt = sentence[:match.start()]+'[[blank]]'+sentence[match.end():] if direction=='ru-cloze' else response['english'] if direction=='en-ru' else answer
        item = {'id':'card','word_id':word['word_id'],'type':'cloze' if direction=='ru-cloze' else 'basic','direction':direction,
                'sense_key':item_id,'sense_label':word['lemma'],'sense_label_ru':word['lemma'],
                'context':sentence,'context_meaning':response['sentence_english'], 'cue_en':response['english'].strip(), 'prompt':prompt,
                'answer':response['english'] if direction=='ru-en' else answer}
        if response['notes'].strip(): item['explanation']=response['notes'].strip()
        if word.get('form_id'): item['form_id']=word['form_id']
        if options.get('topic'): item['topic']=options['topic']
        if word.get('metadata'): item['metadata']=word['metadata']
        if word.get('mnemonic'): item['hint']=word['mnemonic']
        item['card_id']='generated-'+item_id+'-'+objective(item)[:12]
        return {'schema_version':2,'id':'generated-'+item_id,'kind':'deck','title':word['lemma'],
                'source':'Automatically generated from the vocabulary library. Editable by the user.','items':[item]}
