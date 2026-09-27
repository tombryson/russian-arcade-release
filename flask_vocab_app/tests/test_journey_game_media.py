"""Lesson audio is explicit, frozen, reusable, and scoped before every access."""
import hashlib
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from repositories.learning_repository import LearningError, transaction
from services.card_media import NativeMediaProvider
from services.journey_game_media import JourneyGameMediaService
from services.learning_assets import import_asset
from services.first_delivery import QUESTIONS
from services.first_steps import chapter_content
from tests.support import isolated_app, select_test_profile
from tests.test_card_media import MediaProvider
from tests.test_personal_flashcards import Provider


class JourneyGameMediaTests(unittest.TestCase):
    def setUp(self):
        self.provider = MediaProvider()
        self.app = isolated_app(self, {'OpenAIService': Provider(), 'CardMediaProvider': self.provider})
        self.db = self.app.config['DB_PATH']
        self.store = self.app.extensions['learning']['assets']
        self.key = hashlib.sha256('Это письмо.'.encode('utf-8')).hexdigest()
        self.allowed = {self.key: {'text': 'Это письмо.', 'profile_id': 'personal-learning'}}
        self.media = JourneyGameMediaService(self.db, self.store, self.provider, self.authorize)

    def authorize(self, conn, key):
        if key not in self.allowed:
            raise LearningError('not_found', 'This lesson audio is not available.', 404)
        return dict(self.allowed[key])

    def test_reads_never_generate_and_prepare_then_listen_reuses_one_asset(self):
        self.assertEqual(self.media.status(self.key)['status'], 'pending')
        self.assertEqual(self.provider.calls, [])
        with self.assertRaises(LearningError):
            self.media.asset(self.key)
        result = self.media.prepare(self.key)
        self.assertEqual(result, {'status': 'ready', 'url': '/api/v1/games/media/' + self.key})
        for _ in range(3):
            self.assertEqual(self.media.prepare(self.key), result)
            path, mimetype = self.media.asset(self.key)
            self.assertEqual(path.read_bytes(), self.provider.mp3)
            self.assertEqual(mimetype, 'audio/mpeg')
        self.assertEqual(self.provider.calls, [('sentence_audio', {
            'voice_id': 'saved-random-voice', 'text': 'Это письмо.', 'model': 'test'})])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_media').fetchone()[0], 1)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_failed_recording_retries_frozen_spec_without_changing_the_clue_or_voice(self):
        self.provider.fail = {'sentence_audio'}
        first = self.media.prepare(self.key)
        self.assertEqual(first['status'], 'failed')
        self.assertNotIn('url', first)
        self.provider.fail.clear()
        self.assertEqual(self.media.prepare(self.key)['status'], 'ready')
        self.assertEqual(self.provider.calls[0], self.provider.calls[1])
        with transaction(self.db) as conn:
            row = conn.execute('SELECT * FROM journey_game_media').fetchone()
            self.assertEqual(row['text'], 'Это письмо.')
            self.assertEqual(json.loads(row['spec_json']), self.provider.calls[0][1])
            self.assertIsNone(row['error'])

    def test_unknown_key_invalid_key_and_changed_authorization_cannot_read_or_generate(self):
        for bad in ('../secret', 'f' * 64):
            for operation in (self.media.status, self.media.prepare, self.media.asset):
                with self.assertRaises(LearningError) as error:
                    operation(bad)
                self.assertEqual(error.exception.status, 404)
        self.media.prepare(self.key)
        self.allowed.clear()
        for operation in (self.media.status, self.media.prepare, self.media.asset):
            with self.assertRaises(LearningError) as error:
                operation(self.key)
            self.assertEqual(error.exception.status, 404)
        self.allowed[self.key] = {'text': 'A changed sentence.', 'profile_id': 'personal-learning'}
        with self.assertRaises(LearningError):
            self.media.prepare(self.key)
        self.assertEqual(len(self.provider.calls), 1)

    def test_no_key_reports_unavailable_before_any_provider_work(self):
        speech = SimpleNamespace(api_key='', voice_ids=('one', 'two'), model='test')
        provider = NativeMediaProvider(None, speech)
        provider.spec = lambda *_: self.fail('An unavailable provider must not choose a voice.')
        provider.generate = lambda *_: self.fail('An unavailable provider must not generate.')
        media = JourneyGameMediaService(self.db, self.store, provider, self.authorize)
        self.assertEqual(media.status(self.key)['status'], 'unavailable')
        self.assertEqual(media.prepare(self.key)['status'], 'unavailable')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_media').fetchone()[0], 0)

    def test_concurrent_requests_claim_one_recording_without_holding_database_lock(self):
        entered, release = threading.Event(), threading.Event()
        original = self.provider.generate

        def blocked(kind, spec):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test timed out waiting for the competing request.')
            return original(kind, spec)

        self.provider.generate = blocked
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.media.prepare, self.key)
            self.assertTrue(entered.wait(5))
            try:
                self.assertEqual(self.media.prepare(self.key)['status'], 'pending')
                self.assertEqual(self.media.status(self.key)['status'], 'pending')
            finally:
                release.set()
            self.assertEqual(first.result()['status'], 'ready')
        self.assertEqual(len(self.provider.calls), 1)

    def test_missing_cached_file_rebuilds_the_recording_from_its_saved_spec(self):
        self.media.prepare(self.key)
        path, _ = self.media.asset(self.key)
        path.unlink()
        self.assertEqual(self.media.status(self.key)['status'], 'failed')
        self.assertEqual(self.media.prepare(self.key)['status'], 'ready')
        self.assertEqual(self.provider.calls[0], self.provider.calls[1])

    def test_native_sentence_audio_reuse_requires_the_same_owner_and_exact_context(self):
        client = self.app.test_client()
        with client.session_transaction() as saved:
            access = saved['personal_access_id']
        generator = self.app.extensions['learning']['generator']
        batch = generator.create(access, {'submission_id': 'shared-media-test', 'options': {
            'kind': 'ru-cloze', 'quantity': 1, 'word_id': 1, 'audio': True, 'image': True}})
        for _ in range(5):
            batch = generator.next(access, batch['id'])
            if batch['complete']:
                break
        self.assertTrue(batch['complete'])
        text = 'Это кофе.'
        key = hashlib.sha256(text.encode('utf-8')).hexdigest()
        self.allowed[key] = {'text': text, 'profile_id': 'personal-learning'}
        before = len(self.provider.calls)
        self.assertEqual(self.media.status(key)['status'], 'ready')
        self.media.prepare(key)
        self.media.asset(key)
        self.assertEqual(len(self.provider.calls), before)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_media').fetchone()[0], 0)
        # Having the same frozen clue grants no access to somebody else's card.
        self.allowed[key]['profile_id'] = None
        self.assertEqual(self.media.status(key)['status'], 'pending')
        with self.assertRaises(LearningError):
            self.media.asset(key)
        self.assertEqual(self.media.prepare(key)['status'], 'ready')
        self.assertEqual(len(self.provider.calls), before + 1)
        self.allowed[key]['profile_id'] = 'a-second-eligible-profile'
        self.assertEqual(self.media.prepare(key)['status'], 'ready')
        self.assertEqual(len(self.provider.calls), before + 1)

    def test_model_or_voice_policy_changes_create_a_new_cache_entry(self):
        provider = NativeMediaProvider(None, SimpleNamespace(api_key='test-only', model='model-one', voice_ids=('one',)))
        provider.generate = self.provider.generate
        media = JourneyGameMediaService(self.db, self.store, provider, self.authorize)
        self.assertEqual(media.prepare(self.key)['status'], 'ready')
        self.assertEqual(media.prepare(self.key)['status'], 'ready')
        provider.speech.model = 'model-two'
        self.assertEqual(media.status(self.key)['status'], 'pending')
        self.assertEqual(media.prepare(self.key)['status'], 'ready')
        self.assertEqual(len(self.provider.calls), 2)
        self.assertNotEqual(self.provider.calls[0][1]['model'], self.provider.calls[1][1]['model'])

    def test_image_bytes_cannot_be_returned_as_game_audio(self):
        self.provider.generate = lambda *_: self.provider.image
        self.assertEqual(self.media.prepare(self.key)['status'], 'failed')
        with self.assertRaises(LearningError):
            self.media.asset(self.key)

    def test_prepared_game_audio_is_reused_for_its_guest_without_another_paid_call(self):
        audio_id = import_asset(self.db, self.store, self.provider.mp3, 'Prepared game recording')
        content = {'vocabulary_refs': [{'sentence': 'Это письмо.', 'assets': [{'id': audio_id, 'kind': 'sentence_audio'}]}]}
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,NULL,?,?,?,?,?,?,?)',
                         ('prepared-guest-game', 'its-guest', 'pairs', 'seed', '[]', json.dumps(content), 1, 1))
        self.allowed[self.key] = {'text': 'Это письмо.', 'profile_id': None, 'guest_token': 'its-guest'}
        self.assertEqual(self.media.status(self.key)['status'], 'ready')
        self.assertEqual(self.media.prepare(self.key)['status'], 'ready')
        path, mime = self.media.asset(self.key)
        self.assertEqual(path.read_bytes(), self.provider.mp3)
        self.assertEqual(mime, 'audio/mpeg')
        self.assertEqual(self.provider.calls, [])
        self.allowed[self.key]['guest_token'] = 'another-guest'
        self.assertEqual(self.media.status(self.key)['status'], 'pending')
        with self.assertRaises(LearningError):
            self.media.asset(self.key)
        self.allowed[self.key] = {'text': 'Это письмо.', 'profile_id': 'personal-learning'}
        self.assertEqual(self.media.status(self.key)['status'], 'pending')

    def test_prepared_profile_game_recording_requires_exact_frozen_sentence(self):
        client = self.app.test_client()
        audio_id = import_asset(self.db, self.store, self.provider.mp3, 'Prepared profile recording')
        content = {'vocabulary_refs': [{'sentence': 'Это письмо.', 'assets': [{'id': audio_id, 'kind': 'sentence_audio'}]}]}
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,?,NULL,?,?,?,?,?,?)',
                         ('prepared-profile-game', 'personal-learning', 'pairs', 'seed', '[]', json.dumps(content), 1, 1))
        self.assertEqual(self.media.prepare(self.key)['status'], 'ready')
        self.assertEqual(self.provider.calls, [])
        other_key = hashlib.sha256('Это карта.'.encode('utf-8')).hexdigest()
        self.allowed[other_key] = {'text': 'Это карта.', 'profile_id': 'personal-learning'}
        self.assertEqual(self.media.status(other_key)['status'], 'pending')
        with self.assertRaises(LearningError):
            self.media.asset(other_key)


class JourneyGameMediaRouteTests(unittest.TestCase):
    def setUp(self):
        self.provider = MediaProvider()
        self.app = isolated_app(self, {'CardMediaProvider': self.provider}, signed_in=False)
        self.client = self.app.test_client()
        self.key = hashlib.sha256('Это письмо.'.encode('utf-8')).hexdigest()
        self.base = '/api/v1/games/media/' + self.key

    def post(self, url, data=None, *, client=None, status=200):
        client = client or self.client
        token = client.get('/api/v1/onboarding').json['csrf_token']
        result = client.post(url, json=data or {}, headers={'X-CSRF-Token': token})
        self.assertEqual(result.status_code, status, result.text)
        return result.json

    def finish_bag(self):
        for milestone in ('coins', 'progress'):
            self.post('/api/v1/onboarding', {'milestone': milestone})
        base = '/api/v1/onboarding/practice/'
        self.post(base + 'start')
        for question in QUESTIONS:
            self.post(base + 'learn', {'question_id': question['id']})
        for question in QUESTIONS:
            self.post(base + 'answer', {'question_id': question['id'], 'answer': question['answer']})
            self.post(base + 'continue', {'question_id': question['id']})
        self.post(base + 'complete')
        lesson = next(item for item in chapter_content()['lessons'] if item['id'] == 'bag')
        base = '/api/v1/first-steps/bag/'
        self.post(base + 'start')
        for card in lesson['teaching']:
            self.post(base + 'learn', {'teaching_id': card['id']})
        for question in lesson['questions']:
            self.post(base + 'answer', {'question_id': question['id'], 'answer': question['answer']})
            self.post(base + 'continue', {'question_id': question['id']})
        self.post(base + 'complete')

    def test_guest_audio_requires_completed_frozen_lesson_and_explicit_csrf_post(self):
        self.assertEqual(self.client.get(self.base + '/status').status_code, 404)
        self.finish_bag()
        self.assertEqual(self.client.get(self.base + '/status').json['status'], 'pending')
        self.assertEqual(self.provider.calls, [])
        self.post(self.base + '/prepare', {'text': 'Arbitrary input'}, status=400)
        self.assertEqual(self.client.post(self.base + '/prepare', json={}).status_code, 403)
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.post(self.base + '/prepare')['status'], 'ready')
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'audio/mpeg')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response.close()
        other = self.app.test_client()
        self.assertEqual(other.get(self.base).status_code, 404)
        self.post(self.base + '/prepare', client=other, status=404)
        self.assertEqual(self.client.get(self.base + '/status', headers={'X-Profile-ID': 'someone-else'}).status_code, 409)
        self.assertEqual(len(self.provider.calls), 1)

    def test_profile_switch_cannot_read_completed_profile_audio_or_accept_stale_headers(self):
        select_test_profile(self.client)
        self.finish_bag()
        self.assertEqual(self.post(self.base + '/prepare')['status'], 'ready')
        self.post('/api/v1/user-session/profiles', {'display_name': 'Another learner'}, status=201)
        self.assertEqual(self.client.get(self.base).status_code, 404)
        self.assertEqual(self.client.get(self.base + '/status').status_code, 404)
        self.assertEqual(self.client.get(self.base + '/status', headers={'X-Profile-ID': 'personal-learning'}).status_code, 409)
        self.post(self.base + '/prepare', status=404)
        self.assertEqual(len(self.provider.calls), 1)

    def test_guest_listen_route_uses_the_recording_already_prepared_with_the_game(self):
        self.finish_bag()
        db = self.app.config['DB_PATH']
        store = self.app.extensions['learning']['assets']
        text = 'Мы ищем карту.'
        key = hashlib.sha256(text.encode('utf-8')).hexdigest()
        asset_id = import_asset(db, store, self.provider.mp3, 'A prepared vocabulary-game example')
        content = {'rounds': [], 'media_texts': [text],
                   'vocabulary_refs': [{'sentence': text, 'assets': [{'id': asset_id, 'kind': 'sentence_audio'}]}]}
        with transaction(db, write=True) as conn:
            guest = conn.execute('SELECT guest_token FROM first_steps_attempts WHERE guest_token IS NOT NULL LIMIT 1').fetchone()[0]
            conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,NULL,?,?,?,?,?,?,?)',
                         ('ready-vocabulary-game', guest, 'pairs', 'seed', '[]', json.dumps(content), 1, 1))
        base = '/api/v1/games/media/' + key
        self.assertEqual(self.client.get(base + '/status').json['status'], 'ready')
        self.assertEqual(self.post(base + '/prepare')['status'], 'ready')
        response = self.client.get(base)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.provider.mp3)
        response.close()
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.app.test_client().get(base).status_code, 404)
