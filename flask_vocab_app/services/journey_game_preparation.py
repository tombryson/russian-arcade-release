"""Prepare reusable contextual game material without creating flashcards.

Selections and their provenance are server owned. Each explicit advance does
at most one paid stage; saved text and media specifications survive retries.
"""
import copy
import json
import logging

from repositories.learning_repository import LearningError, encoded, identifier, timestamp, transaction
from services.card_generation import CardGenerationService
from services.learning_assets import import_asset

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300
REQUIRED_MEDIA = ('image', 'sentence_audio')
MESSAGES = {
    'discovery': 'Finding a new word to learn.',
    'context': 'Preparing Russian examples.',
    'image': 'Preparing the pictures.',
    'sentence_audio': 'Preparing the Russian audio.',
    'ready': 'Your game is ready.',
}
FAILURES = {
    'discovery': 'The new example could not be prepared. Retry to keep your saved progress.',
    'context': 'This example could not be prepared. Retry to keep working on the same words.',
    'image': 'This picture could not be prepared. Retry to keep the example and other media.',
    'sentence_audio': 'This recording could not be prepared. Retry to keep the example and picture.',
}


class JourneyGamePreparationService:
    def __init__(self, db_path, store, provider, media_provider, authorize, *, clock=timestamp, discover=None):
        self.db_path, self.store = db_path, store
        self.provider, self.media_provider = provider, media_provider
        self.authorize, self.clock = authorize, clock
        self.shared_audio = None
        self.discover = discover

    @staticmethod
    def _items(row):
        items = json.loads(row['items_json'])
        if not isinstance(items, list) or not items:
            raise LearningError('invalid_preparation', 'This game has no saved vocabulary selection.', 409)
        return items

    def _preparation(self, conn, session_id):
        owner = self.authorize(conn, session_id)
        row = conn.execute('SELECT * FROM journey_game_preparations WHERE session_id=?', (session_id,)).fetchone()
        if not row:
            raise LearningError('not_found', 'This game preparation is not available.', 404)
        return owner, row

    def _valid_asset(self, conn, asset, kind):
        if not isinstance(asset, dict) or asset.get('kind') != kind:
            return False
        row = conn.execute('SELECT storage_key,media_type FROM learning_assets WHERE id=?', (asset.get('id'),)).fetchone()
        prefix = 'image/' if kind == 'image' else 'audio/'
        return bool(row and row['media_type'].startswith(prefix) and self.store.path(row['storage_key']).is_file())

    def _stage(self, conn, record):
        if record.get('_discovery'):
            return 'discovery'
        state = record.get('_preparation', {})
        if not state.get('context_validated'):
            return 'context'
        for kind in record.get('required_media', REQUIRED_MEDIA):
            if not any(self._valid_asset(conn, asset, kind) for asset in record.get('assets', [])):
                return kind
        return 'ready'

    def status(self, conn, row):
        """Read only; accepts the owned session row or its preparation row."""
        session_id = row['session_id'] if 'session_id' in row.keys() else row['id']
        _, preparation = self._preparation(conn, session_id)
        items = self._items(preparation)
        stages = [self._stage(conn, item) for item in items]
        stage = next((stage for stage in stages if stage != 'ready'), 'ready')
        state = 'ready' if stage == 'ready' else 'failed' if preparation['status'] == 'failed' else 'pending'
        result = {'status': state, 'ready': stages.count('ready'), 'total': len(items),
                  'stage': stage, 'message': MESSAGES[stage]}
        if state == 'failed':
            result.update(error=preparation['error'] or FAILURES[stage], message=preparation['error'] or FAILURES[stage])
        result['items'] = [
            {'word': item['form'] or 'New word', 'status': 'ready' if item_stage == 'ready' else
             'failed' if item.get('_preparation', {}).get('error') else 'pending',
             'stage': item_stage, 'error': item.get('_preparation', {}).get('error')}
            for item, item_stage in zip(items, stages)
        ]
        return result

    @staticmethod
    def _clean(record):
        return {key: copy.deepcopy(value) for key, value in record.items() if key not in ('_preparation', '_discovery')}

    def records(self, conn, session_id):
        _, row = self._preparation(conn, session_id)
        items = self._items(row)
        if any(self._stage(conn, item) != 'ready' for item in items):
            return None
        return [self._clean(item) for item in items]

    @staticmethod
    def _response(record):
        return {'english': record.get('target_meaning', ''), 'sentence': record.get('sentence', ''),
                'sentence_english': record.get('translation', ''), 'notes': record.get('notes', '') or ''}

    @staticmethod
    def _validate(record, response):
        # This builds a pack in memory only. No content import, publishing,
        # review schedule, or native-card count is changed by preparing a game.
        CardGenerationService.pack('journey-example', record, {'kind': 'ru-cloze'}, response)
        if record.get('sentence') and response['sentence'].strip() != record['sentence']:
            raise LearningError('context_changed', 'Keep the selected example exactly as it was saved.', 409)
        if record.get('translation') and response['sentence_english'].strip() != record['translation']:
            raise LearningError('translation_changed', 'Keep the saved translation with its original example.', 409)

    @staticmethod
    def _cache_row(conn, owner, record):
        if owner['profile_id']:
            return conn.execute('SELECT id,content_json FROM journey_game_examples WHERE profile_id=? AND identity=?',
                                (owner['profile_id'], record['identity'])).fetchone()
        return conn.execute('SELECT id,content_json FROM journey_game_examples WHERE profile_id IS NULL AND guest_token=? AND identity=?',
                            (owner['guest_token'], record['identity'])).fetchone()

    def _cached(self, conn, owner, record):
        row = self._cache_row(conn, owner, record)
        if not row:
            return None
        cached = json.loads(row['content_json'])
        from services.journey_vocabulary import cache_source_available
        if not cache_source_available(conn, cached, owner['profile_id']):
            return None
        # Identity is assigned by the selector, but frozen wording and form
        # checks also prevent accidental reuse after a source is edited.
        if any(cached.get(key) != record.get(key) for key in ('word_id', 'form_id', 'lemma', 'form')):
            return None
        if any(key in record and cached.get(key) != record[key]
               for key in ('sentence', 'translation', 'target_meaning', 'notes')):
            return None
        try:
            self._validate(cached, self._response(cached))
        except (LearningError, KeyError, TypeError):
            return None
        # The cache fills missing context; it must not roll back edits to the
        # selected word's metadata/mnemonic or a native card's current media.
        cached.update({key: copy.deepcopy(value) for key, value in record.items()
                       if key not in ('_preparation', 'assets', 'source', 'cached_id')})
        if record.get('sentence'):
            # The selector may already have filled these text fields from this
            # same cache. In that case its vocabulary/selection label is not
            # new provenance; keep the original model and source/example label.
            if record.get('cached_id') != row['id'] or record.get('source', {}).get('kind') == 'card':
                cached['source'] = copy.deepcopy(record.get('source', {}))
            if 'assets' in record:
                cached['assets'] = copy.deepcopy(record['assets'])
        elif record.get('assets'):
            media = {asset['kind']: asset for asset in cached.get('assets', [])}
            media.update({asset['kind']: copy.deepcopy(asset) for asset in record['assets']})
            cached['assets'] = list(media.values())
        cached['_preparation'] = {'context_validated': True}
        # Missing media is prepared again; valid media and wording survive.
        cached['cached_id'] = row['id']
        return cached

    def _cache(self, conn, owner, record):
        clean = self._clean(record)
        # A vocabulary form keeps its selection identity when a learner edits
        # the native example. Replace the cache, never that session's frozen
        # content, and do not collide with the existing owner/identity row.
        existing = self._cache_row(conn, owner, record)
        example_id = existing['id'] if existing else identifier()
        clean['cached_id'] = example_id
        if existing:
            conn.execute('UPDATE journey_game_examples SET content_json=? WHERE id=?', (encoded(clean), example_id))
        else:
            conn.execute('INSERT INTO journey_game_examples(id,profile_id,guest_token,identity,word_id,form_id,content_json,created_at) VALUES (?,?,?,?,?,?,?,?)',
                         (example_id, owner['profile_id'], owner['guest_token'], record['identity'], record.get('word_id'), record.get('form_id'), encoded(clean), self.clock()))
        record['cached_id'] = example_id

    def _save(self, conn, session_id, items, *, claim=None, error=None):
        stages = [self._stage(conn, item) for item in items]
        status = 'failed' if error else 'ready' if all(stage == 'ready' for stage in stages) else 'pending'
        sql = 'UPDATE journey_game_preparations SET items_json=?,status=?,error=?,claim_id=NULL,lease_until=0,updated_at=? WHERE session_id=?'
        args = [encoded(items), status, error, self.clock(), session_id]
        if claim is not None:
            sql += ' AND claim_id=?'; args.append(claim)
        if not conn.execute(sql, args).rowcount:
            raise LearningError('preparation_changed', 'Another request is already preparing this game.', 409)

    def advance(self, session_id, retry=False):
        if type(retry) is not bool:
            raise LearningError('invalid_input', 'Choose whether to retry this preparation.')
        with transaction(self.db_path, write=True) as conn:
            owner, row = self._preparation(conn, session_id)
            if row['lease_until'] > self.clock() or (row['status'] == 'failed' and not retry):
                return self.status(conn, row)
            items = self._items(row)
            # Reuse a ready example without any provider calls. The next paid
            # stage, if one remains, still uses the original frozen selection.
            for position, record in enumerate(items):
                if self._stage(conn, record) == 'context':
                    cached = self._cached(conn, owner, record)
                    if cached:
                        items[position] = cached
            selected = next(((index, self._stage(conn, record)) for index, record in enumerate(items)
                             if self._stage(conn, record) != 'ready'), None)
            if not selected:
                self._save(conn, session_id, items)
                return self.status(conn, row)
            index, stage = selected
            record = items[index]
            state = record.setdefault('_preparation', {})
            state.pop('error', None)
            state.pop('error_reason', None)
            # Existing complete source contexts are validated without an LLM.
            response = self._response(record)
            supplied = stage == 'context' and all(response[key] for key in ('english', 'sentence', 'sentence_english'))
            claim = identifier()
            conn.execute("UPDATE journey_game_preparations SET items_json=?,status='pending',error=NULL,claim_id=?,lease_until=?,updated_at=? WHERE session_id=?",
                         (encoded(items), claim, self.clock() + LEASE_SECONDS, self.clock(), session_id))
        try:
            if stage == 'discovery':
                from services.game_vocabulary_discovery import generate_discovery
                request = copy.deepcopy(record['_discovery'])
                request['known_lemmas'] = list(dict.fromkeys([*request['known_lemmas'], *(e['lemma'] for e in items if e.get('lemma'))]))
                # The original selection may not have had sentences yet. Use
                # the prepared examples so discovery can make distinct choices
                # rather than introducing another word from the same sentence.
                request['familiar_records'] = [self._clean(e) for e in items
                                               if e is not record and e.get('sentence') and e.get('lemma')]
                generated = (self.discover or generate_discovery)(self.provider, **request)
                generated['required_media'] = record['required_media']
                self._validate(generated, self._response(generated))
                if any(generated[field].casefold().strip() == prior.get(field, '').casefold().strip()
                       for prior in request['familiar_records'] for field in ('sentence', 'translation')):
                    raise ValueError('A discovered example must provide a distinct sentence and translation')
                generated['_preparation'] = {'context_validated': True}
                items[index] = record = generated
                state = record['_preparation']
            elif stage == 'context':
                if not supplied:
                    if not self.provider:
                        raise ValueError('Context provider unavailable')
                    word = self._clean(record)
                    # This remains provenance/grounding data in the existing
                    # provider's structured input, never client instructions.
                    response = self.provider.generate_native_card(word, 'ru-cloze')
                self._validate(record, response)
                record.update(sentence=response['sentence'].strip(), translation=response['sentence_english'].strip(),
                              target_meaning=response['english'].strip(), notes=response['notes'].strip())
                source = record.setdefault('source', {})
                if not supplied:
                    source['model'] = str(getattr(self.provider, 'flashcard_model', 'configured'))
                    source['origin'] = 'source' if source.get('context') == record['sentence'] else 'example'
                state['context_validated'] = True
            else:
                # Freeze the randomly chosen voice before crossing the network.
                with transaction(self.db_path, write=True) as conn:
                    self._preparation(conn, session_id)
                    specs = state.setdefault('specs', {})
                    cached = self.shared_audio.reusable_audio(conn, record['sentence']) if stage == 'sentence_audio' and self.shared_audio else None
                    if cached and (stage not in specs or specs[stage] == cached['spec']):
                        specs[stage] = cached['spec']
                        asset_id = cached['asset_id']
                    else:
                        asset_id = None
                        if stage not in specs:
                            if not self.media_provider:
                                raise ValueError('Media provider unavailable')
                            specs[stage] = self.media_provider.spec(stage, {'context': record['sentence']}, record['form'])
                    spec = specs[stage]
                    if spec.get('text') != record['sentence']:
                        raise ValueError('Media specification changed the example')
                    if not conn.execute('UPDATE journey_game_preparations SET items_json=?,updated_at=? WHERE session_id=? AND claim_id=?',
                                        (encoded(items), self.clock(), session_id, claim)).rowcount:
                        raise LearningError('preparation_changed', 'Another request is already preparing this game.', 409)
                if not asset_id:
                    data = self.media_provider.generate(stage, spec)
                    # Recheck ownership after paid work before persisting it.
                    with transaction(self.db_path) as conn:
                        self._preparation(conn, session_id)
                    asset_id = import_asset(self.db_path, self.store, data, 'Generated ' + stage + ' for a saved vocabulary game example')
                with transaction(self.db_path) as conn:
                    self._preparation(conn, session_id)
                    if not self._valid_asset(conn, {'id': asset_id, 'kind': stage}, stage):
                        raise ValueError('Provider returned an incorrect media type')
                record['assets'] = [asset for asset in record.get('assets', []) if asset.get('kind') != stage] + [{'id': asset_id, 'kind': stage}]
        except Exception as error:
            logger.warning('Journey example %s preparation failed (%s)', stage, type(error).__name__)
            with transaction(self.db_path, write=True) as conn:
                self._preparation(conn, session_id)
                reason = error.details.get('reason') if isinstance(error, LearningError) and error.code == 'discovery_unavailable' else None
                message = FAILURES[stage]
                if stage == 'discovery' and reason in {'provider', 'response', 'fields', 'new_word', 'morphology', 'sentence', 'duplicate_context', 'card_context'}:
                    state['error_reason'] = reason
                    message = str(error)
                state['error'] = message
                self._save(conn, session_id, items, claim=claim, error=message)
                return self.status(conn, row)
        with transaction(self.db_path, write=True) as conn:
            owner, row = self._preparation(conn, session_id)
            # A lease expiring does not let an older response overwrite a newer
            # request's text or randomly chosen media specification.
            if row['claim_id'] != claim:
                raise LearningError('preparation_changed', 'Another request is already preparing this game.', 409)
            if self._stage(conn, record) == 'ready':
                self._cache(conn, owner, record)
            self._save(conn, session_id, items, claim=claim)
            return self.status(conn, row)
