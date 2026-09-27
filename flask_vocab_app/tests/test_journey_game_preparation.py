"""Game examples use real forms and durable media without publishing cards."""
import copy
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from repositories.learning_repository import LearningError, encoded, transaction
from services.journey_game_preparation import JourneyGamePreparationService
from services.learning_assets import import_asset
from tests.support import isolated_app
from tests.test_card_media import MediaProvider


class ContextProvider:
    flashcard_model = 'test-context-model'

    def __init__(self):
        self.calls = []
        self.response = {'english': 'coffee', 'sentence': 'Я пью кофе.',
                         'sentence_english': 'I am drinking coffee.', 'notes': ''}

    def generate_native_card(self, word, kind):
        self.calls.append((copy.deepcopy(word), kind))
        return dict(self.response)


class JourneyGamePreparationTests(unittest.TestCase):
    def setUp(self):
        self.provider, self.media = ContextProvider(), MediaProvider()
        self.app = isolated_app(self, {'OpenAIService': self.provider, 'CardMediaProvider': self.media})
        self.db = self.app.config['DB_PATH']
        self.store = self.app.extensions['learning']['assets']
        self.allowed = True
        self.clock = 1000
        self.service = JourneyGamePreparationService(self.db, self.store, self.provider, self.media,
                                                     self.authorize, clock=lambda: self.clock)
        self.record = {'identity': 'vocab-word-1-form-1', 'word_id': 1, 'form_id': 1,
                       'lemma': 'кофе', 'form': 'кофе', 'pos': 'NOUN', 'tags': {},
                       'metadata': {'pos': 'NOUN', 'grammar': {}}, 'mnemonic': '',
                       'assets': [], 'source': {'kind': 'vocabulary', 'id': '1', 'title': 'Vocabulary', 'url': '/vocab'}}
        self.create('first')

    def authorize(self, conn, session_id):
        row = conn.execute('SELECT * FROM journey_game_sessions WHERE id=?', (session_id,)).fetchone()
        if not self.allowed or not row:
            raise LearningError('not_found', 'This game belongs to another learner.', 404)
        return row

    def create(self, session_id, record=None, guest='guest-test', game='pairs'):
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,NULL,?,?,?,?,?,?,?)',
                         (session_id, guest, game, session_id, '[]', '{}', self.clock, self.clock))
            conn.execute('INSERT INTO journey_game_preparations(session_id,items_json,created_at,updated_at) VALUES (?,?,?,?)',
                         (session_id, encoded([record or self.record]), self.clock, self.clock))

    def status(self, session_id='first'):
        with transaction(self.db) as conn:
            return self.service.status(conn, self.authorize(conn, session_id))

    def records(self, session_id='first'):
        with transaction(self.db) as conn:
            return self.service.records(conn, session_id)

    def finish(self, session_id='first'):
        for _ in range(5):
            result = self.service.advance(session_id)
            if result['status'] in ('ready', 'failed'):
                return result
        self.fail('Preparation did not finish within its three stages')

    def supplied(self):
        record = copy.deepcopy(self.record)
        record.update(sentence=self.provider.response['sentence'], translation=self.provider.response['sentence_english'],
                      target_meaning=self.provider.response['english'], notes='')
        return record

    def replace_record(self, record):
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_preparations SET items_json=? WHERE session_id=?', (encoded([record]), 'first'))

    def test_duplicate_discovery_is_retryable_and_uses_prepared_familiar_context(self):
        from services.game_activity_policy import discovery_request
        familiar = self.supplied()
        familiar.update(sentence='Я покупаю кофе и подарки.', translation='I am buying coffee and presents.',
                        required_media=[], _preparation={'context_validated': True})
        placeholder = discovery_request(['кофе'], [self.record], {}, 'fresh', [])
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_preparations SET items_json=? WHERE session_id=?',
                         (encoded([familiar, placeholder]), 'first'))
        calls = []
        def discover(provider, **request):
            calls.append(request)
            return {'identity': 'new-presents', 'word_id': None, 'form_id': None,
                    'lemma': 'подарок', 'form': 'подарки', 'pos': 'NOUN',
                    'tags': {'case': 'accs', 'number': 'plur'}, 'assets': [], 'source': {'kind': 'discovery'},
                    'sentence': familiar['sentence'] if len(calls) == 1 else 'Анна покупает подарки.',
                    'translation': familiar['translation'] if len(calls) == 1 else 'Anna is buying presents.',
                    'target_meaning': 'presents', 'notes': ''}
        self.service.discover = discover
        self.assertEqual(self.service.advance('first')['status'], 'failed')
        self.assertEqual(calls[0]['familiar_records'][0]['sentence'], familiar['sentence'])
        self.assertEqual(self.service.advance('first')['status'], 'failed')
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.service.advance('first', retry=True)['status'], 'ready')
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.records()[0]['sentence'], familiar['sentence'])
        self.assertEqual(self.records()[1]['sentence'], 'Анна покупает подарки.')
        self.assertEqual(self.media.calls, [])

    def test_read_only_status_and_three_bounded_stages_do_not_create_native_cards(self):
        with transaction(self.db) as conn:
            before = conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0]
        self.assertEqual(self.status()['stage'], 'context')
        self.assertIsNone(self.records())
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.media.calls, [])
        self.assertEqual(self.service.advance('first')['stage'], 'image')
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(len(self.media.calls), 0)
        self.assertEqual(self.service.advance('first')['stage'], 'sentence_audio')
        self.assertEqual(len(self.media.calls), 1)
        self.assertEqual(self.service.advance('first')['status'], 'ready')
        result = self.records()[0]
        self.assertEqual(result['sentence'], 'Я пью кофе.')
        self.assertEqual(result['form_id'], 1)
        self.assertEqual({a['kind'] for a in result['assets']}, {'image', 'sentence_audio'})
        self.assertEqual(result['source']['origin'], 'example')
        self.assertNotIn('_preparation', result)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], before)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_examples').fetchone()[0], 1)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_discovery_failure_keeps_safe_reason_and_retries_only_the_missing_example(self):
        from services.game_activity_policy import discovery_request
        familiar = self.supplied() | {'required_media': [], '_preparation': {'context_validated': True}}
        pending = discovery_request(['кофе'], [familiar], {}, 'fresh', [])
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_preparations SET items_json=? WHERE session_id=?',
                         (encoded([familiar, pending]), 'first'))
        message = 'The new example did not pass the Russian language checks. Your prepared examples are saved; retry to replace this example.'
        def fail(provider, **request):
            raise LearningError('discovery_unavailable', message, 503, {'reason': 'morphology'})
        self.service.discover = fail
        status = self.service.advance('first')
        self.assertEqual(status['ready'], 1)
        self.assertEqual(status['error'], message)
        with transaction(self.db) as conn:
            items = json.loads(conn.execute('SELECT items_json FROM journey_game_preparations WHERE session_id=?', ('first',)).fetchone()[0])
            self.assertEqual(items[0], familiar)
            self.assertEqual(items[1]['_preparation']['error_reason'], 'morphology')
        self.service.discover = lambda provider, **request: {
            'identity': 'new-tea', 'word_id': None, 'form_id': None, 'lemma': 'чай', 'form': 'чай',
            'sentence': 'Анна пьёт чай.', 'translation': 'Anna is drinking tea.', 'target_meaning': 'tea', 'notes': '',
        }
        self.assertEqual(self.service.advance('first', retry=True)['status'], 'ready')
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.media.calls, [])
        with transaction(self.db) as conn:
            items = json.loads(conn.execute('SELECT items_json FROM journey_game_preparations WHERE session_id=?', ('first',)).fetchone()[0])
            self.assertEqual(items[0], familiar)
            self.assertNotIn('error_reason', items[1]['_preparation'])

    def test_existing_native_context_and_media_reused_without_any_paid_work(self):
        record = self.supplied()
        record['source'] = {'kind': 'card', 'id': 'existing-card', 'version': 'immutable-version'}
        record['assets'] = [
            {'id': import_asset(self.db, self.store, self.media.image, 'Test native picture'), 'kind': 'image'},
            {'id': import_asset(self.db, self.store, self.media.mp3, 'Test native audio'), 'kind': 'sentence_audio'},
        ]
        self.replace_record(record)
        self.assertEqual(self.service.advance('first')['status'], 'ready')
        result = self.records()[0]
        self.assertEqual(result['sentence'], record['sentence'])
        self.assertEqual(result['translation'], record['translation'])
        self.assertEqual(result['source'], record['source'])
        self.assertEqual(result['assets'], record['assets'])
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.media.calls, [])

    def test_same_owner_cache_reuses_examples_but_another_owner_gets_no_private_content(self):
        self.assertEqual(self.finish()['status'], 'ready')
        original = self.records()[0]
        self.create('second', game='missing-stamp')
        self.assertEqual(self.service.advance('second')['status'], 'ready')
        self.assertEqual(self.records('second')[0], original)
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(len(self.media.calls), 2)
        self.create('other', guest='another-guest')
        self.assertIsNone(self.records('other'))
        self.service.advance('other')
        self.assertEqual(len(self.provider.calls), 2)

    def test_edited_native_context_replaces_cache_without_overwriting_an_earlier_session(self):
        self.assertEqual(self.finish()['status'], 'ready')
        original = self.records()[0]
        record = self.supplied()
        record.update(sentence='Утром я пью кофе.', translation='I drink coffee in the morning.')
        self.create('edited', record=record, game='radio')
        self.assertEqual(self.finish('edited')['status'], 'ready')
        self.assertEqual(self.records('edited')[0]['sentence'], record['sentence'])
        self.assertEqual(self.records()[0], original)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_examples').fetchone()[0], 1)

    def test_current_native_meaning_and_cleared_notes_override_older_cached_answer(self):
        record = self.supplied()
        record['notes'] = 'An older note.'
        self.replace_record(record)
        self.assertEqual(self.finish()['status'], 'ready')
        newer = self.records()[0]
        newer.pop('cached_id')
        newer.update(target_meaning='a coffee', notes='')
        self.create('edited-cue', record=newer, game='radio')
        self.assertEqual(self.service.advance('edited-cue')['status'], 'ready')
        self.assertEqual(self.records('edited-cue')[0]['target_meaning'], 'a coffee')
        self.assertEqual(self.records('edited-cue')[0]['notes'], '')
        self.assertEqual(self.records()[0]['notes'], 'An older note.')
        self.assertEqual(self.provider.calls, [])

    def test_cache_keeps_current_vocabulary_metadata_and_replaced_native_image(self):
        self.finish()
        old = self.records()[0]
        updated = copy.deepcopy(self.record)
        updated.update(mnemonic='My new mnemonic.', metadata={'pos': 'NOUN', 'grammar': {}, 'topics': ['food']})
        self.create('metadata-edit', record=updated, game='radio')
        self.assertEqual(self.service.advance('metadata-edit')['status'], 'ready')
        refreshed = self.records('metadata-edit')[0]
        self.assertEqual(refreshed['mnemonic'], updated['mnemonic'])
        self.assertEqual(refreshed['metadata'], updated['metadata'])
        self.assertEqual(len(self.media.calls), 2)
        from PIL import Image
        import io
        image = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(image, format='PNG')
        changed_id = import_asset(self.db, self.store, image.getvalue(), 'User replaced picture')
        refreshed['assets'] = [a for a in refreshed['assets'] if a['kind'] != 'image'] + [{'id': changed_id, 'kind': 'image'}]
        refreshed['source'] = {'kind': 'card', 'id': 'card', 'version': 'new-version'}
        self.create('image-edit', record=refreshed, game='missing-stamp')
        self.assertEqual(self.service.advance('image-edit')['status'], 'ready')
        current = self.records('image-edit')[0]
        self.assertEqual(current['source']['version'], 'new-version')
        self.assertIn({'id': changed_id, 'kind': 'image'}, current['assets'])
        self.assertEqual(self.records()[0], old)
        self.assertEqual(len(self.media.calls), 2)

    def test_selector_reusing_cached_context_does_not_lose_generation_provenance(self):
        self.finish()
        cached = self.records()[0]
        selected = copy.deepcopy(self.record)
        selected.update({key: cached[key] for key in ('sentence', 'translation', 'target_meaning', 'notes', 'assets', 'cached_id')})
        self.create('selected-cache', record=selected, game='radio')
        self.assertEqual(self.service.advance('selected-cache')['status'], 'ready')
        self.assertEqual(self.records('selected-cache')[0]['source'], cached['source'])

    def test_retired_native_source_is_not_resurrected_by_direct_preparation_cache(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            access = session['personal_access_id']
        generator = self.app.extensions['learning']['generator']
        batch = generator.create(access, {'submission_id': 'native-cache-source', 'options': {
            'kind': 'ru-cloze', 'quantity': 1, 'word_id': 1, 'audio': True, 'image': True}})
        for _ in range(5):
            batch = generator.next(access, batch['id'])
        card = batch['items'][0]
        from repositories.card_repository import load_card
        with transaction(self.db, write=True) as conn:
            meta, item = load_card(conn, card['card_version_id'])
            conn.execute('UPDATE journey_game_sessions SET profile_id=?,guest_token=NULL WHERE id=?', ('personal-learning', 'first'))
        record = self.supplied()
        record['source'] = {'kind': 'card', 'id': meta['card_id'], 'version': meta['content_version_id']}
        record['assets'] = item['assets']
        self.replace_record(record)
        self.assertEqual(self.service.advance('first')['status'], 'ready')
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE card_definitions SET retired=1 WHERE id=?', (meta['card_id'],))
        self.create('after-retirement', game='radio')
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_sessions SET profile_id=?,guest_token=NULL WHERE id=?', ('personal-learning', 'after-retirement'))
        self.provider.response.update(sentence='Я люблю кофе.', sentence_english='I like coffee.')
        self.assertEqual(self.finish('after-retirement')['status'], 'ready')
        self.assertEqual(self.records('after-retirement')[0]['sentence'], 'Я люблю кофе.')
        self.assertEqual(self.records()[0]['sentence'], 'Я пью кофе.')
        self.assertEqual(len(self.provider.calls), 2)

    def test_multiple_records_report_progress_and_return_no_partial_game(self):
        second = self.supplied()
        second['identity'] = 'another-context'
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE journey_game_preparations SET items_json=? WHERE session_id=?',
                         (encoded([self.record, second]), 'first'))
        for _ in range(3):
            self.service.advance('first')
        self.assertEqual(self.status()['ready'], 1)
        self.assertEqual(self.status()['total'], 2)
        self.assertIsNone(self.records())
        self.assertEqual(self.finish()['status'], 'ready')
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(len(self.provider.calls), 1)

    def test_context_rejects_wrong_declension_or_repeated_target_and_requires_explicit_retry(self):
        record = copy.deepcopy(self.record)
        record.update(lemma='карта', form='картой', tags={'case': 'ablt'}, form_id=None)
        self.replace_record(record)
        self.provider.response.update(sentence='Это карта.', english='map', sentence_english='This is a map.')
        self.assertEqual(self.service.advance('first')['status'], 'failed')
        self.service.advance('first')
        self.assertEqual(len(self.provider.calls), 1)
        self.provider.response['sentence'] = 'Я пользуюсь картой, картой города.'
        self.assertEqual(self.service.advance('first', retry=True)['status'], 'failed')
        self.provider.response.update(sentence='Я пользуюсь картой.', sentence_english='I am using a map.')
        self.assertEqual(self.service.advance('first', retry=True)['stage'], 'image')
        self.assertEqual(self.media.calls, [])

    def test_source_context_and_translation_cannot_silently_change(self):
        record = self.supplied()
        record.pop('target_meaning')
        self.replace_record(record)
        self.provider.response['sentence'] = 'Это кофе.'
        self.assertEqual(self.service.advance('first')['status'], 'failed')
        self.provider.response['sentence'] = record['sentence']
        self.provider.response['sentence_english'] = 'This is coffee.'
        self.assertEqual(self.service.advance('first', retry=True)['status'], 'failed')
        self.assertEqual(self.media.calls, [])

    def test_pending_lesson_context_stays_grounding_and_new_example_is_labelled(self):
        record = copy.deepcopy(self.record)
        record['source'] = {'kind': 'lesson', 'id': 'lesson-pick', 'context': 'Утром мы пили кофе.'}
        self.replace_record(record)
        self.finish()
        sent = self.provider.calls[0][0]
        self.assertEqual(sent['source']['context'], 'Утром мы пили кофе.')
        self.assertEqual(self.records()[0]['source']['origin'], 'example')
        self.assertEqual(self.records()[0]['source']['context'], 'Утром мы пили кофе.')

    def test_failed_audio_retries_only_audio_with_the_same_voice_and_saved_text(self):
        self.media.fail.add('sentence_audio')
        self.assertEqual(self.finish()['status'], 'failed')
        before = copy.deepcopy(self.media.calls)
        self.assertEqual(self.service.advance('first')['status'], 'failed')
        self.assertEqual(self.media.calls, before)
        self.media.fail.clear()
        self.assertEqual(self.service.advance('first', retry=True)['status'], 'ready')
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual([kind for kind, _ in self.media.calls], ['image', 'sentence_audio', 'sentence_audio'])
        self.assertEqual(self.media.calls[1], self.media.calls[2])

    def test_overlapping_requests_claim_only_one_stage_without_holding_the_database(self):
        entered, release = threading.Event(), threading.Event()
        original = self.provider.generate_native_card

        def blocked(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test timeout')
            return original(*args)

        self.provider.generate_native_card = blocked
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.service.advance, 'first')
            self.assertTrue(entered.wait(5))
            try:
                self.assertEqual(self.service.advance('first')['status'], 'pending')
                self.assertEqual(self.status()['stage'], 'context')
            finally:
                release.set()
            self.assertEqual(first.result()['stage'], 'image')
        self.assertEqual(len(self.provider.calls), 1)

    def test_profile_change_after_network_cannot_save_or_read_the_other_learners_result(self):
        original = self.provider.generate_native_card

        def switch(*args):
            response = original(*args)
            self.allowed = False
            return response

        self.provider.generate_native_card = switch
        with self.assertRaises(LearningError):
            self.service.advance('first')
        for operation in (self.records, self.status, lambda: self.service.advance('first')):
            with self.assertRaises(LearningError):
                operation()
        with transaction(self.db) as conn:
            row = conn.execute('SELECT items_json FROM journey_game_preparations').fetchone()
            self.assertNotIn('sentence', json.loads(row['items_json'])[0])

    def test_provider_exception_never_exposes_secrets_and_bad_media_never_becomes_ready(self):
        def fail(*_):
            raise RuntimeError('Private API key should never reach the user')

        self.provider.generate_native_card = fail
        result = self.service.advance('first')
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('Private', encoded(result))
        self.provider.generate_native_card = lambda *_: dict(self.provider.response)
        self.service.advance('first', retry=True)
        self.media.generate = lambda *_: self.media.mp3
        self.assertEqual(self.service.advance('first')['status'], 'failed')
        self.assertIsNone(self.records())

    def test_shared_audio_cache_and_missing_image_file_keep_text_and_audio(self):
        audio_id = import_asset(self.db, self.store, self.media.mp3, 'Existing exact text audio')

        class SharedAudio:
            @staticmethod
            def reusable_audio(conn, text):
                return {'asset_id': audio_id, 'spec': {'text': text, 'voice_id': 'original-voice', 'model': 'test'}}

        self.service.shared_audio = SharedAudio()
        self.assertEqual(self.finish()['status'], 'ready')
        self.assertEqual([kind for kind, _ in self.media.calls], ['image'])
        image_id = next(a['id'] for a in self.records()[0]['assets'] if a['kind'] == 'image')
        with transaction(self.db) as conn:
            key = conn.execute('SELECT storage_key FROM learning_assets WHERE id=?', (image_id,)).fetchone()[0]
        self.store.path(key).unlink()
        self.assertIsNone(self.records())
        self.assertEqual(self.service.advance('first')['status'], 'ready')
        self.assertEqual([kind for kind, _ in self.media.calls], ['image', 'image'])
        self.assertEqual(len(self.provider.calls), 1)
