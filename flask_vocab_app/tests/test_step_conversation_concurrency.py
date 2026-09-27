"""Bounded requests and preparation ownership with local, controlled providers."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
from unittest.mock import Mock, patch

from repositories.learning_repository import LearningError, timestamp, transaction
from services.speech_provider import SpeechError
from services.step_conversation import StepConversationService
from tests.support import isolated_app
from tests.test_conversation import FakeSpeech
from tests.test_step_conversation_ai import dialogue_for_scenario


class StepConversationConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.ai = Mock()
        self.ai.step_dialogue.side_effect = dialogue_for_scenario
        self.speech = FakeSpeech()
        self.app = isolated_app(self, {'ConversationAI': self.ai, 'SpeechProvider': self.speech})
        self.app.config.update(OPENAI_API_KEY='synthetic', ELEVENLABS_API_KEY='synthetic')
        self.service = self.app.extensions['learning']['step_conversation']
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        state = self.client.get('/api/v1/user-session').json
        self.headers = {'X-CSRF-Token': state['csrf_token'], 'X-Profile-ID': state['profile']['id'],
                        'X-Account-Scope': state['session_scope']}
        with self.client.session_transaction() as session:
            self.access = session['personal_access_id']
        self.base = '/api/v1/step-conversations'
        for service in (self.app.extensions['learning']['conversation'],
                        self.app.extensions['learning']['live_conversation'],
                        self.app.extensions['learning']['live_conversation'].reviews):
            self.addCleanup(service.executor.shutdown, wait=True)

    def saved(self, sid):
        with transaction(self.db) as conn:
            return dict(conn.execute('SELECT * FROM step_conversation_sessions WHERE id=?', (sid,)).fetchone())

    def start(self, key, prepare=True):
        body = {'submission_id': key, 'scenario_id': 'directions', 'target_level': 'A1'}
        if prepare:
            return self.service.start(self.access, body)
        # Create the real owned durable row while deferring only provider work.
        with patch.object(self.service, '_prepare'):
            return self.service.start(self.access, body)

    def post_audio(self, state):
        return self.client.post(self.base + '/' + state['id'] + '/audio',
                                json={'turn_id': state['current_turn']['id'], 'kind': 'npc'},
                                headers=self.headers)

    def test_expired_lease_does_not_overlap_a_live_request_in_the_same_service(self):
        sid = self.start('expired', prepare=False)['id']
        entered, release = threading.Event(), threading.Event()

        def generate(scenario):
            entered.set()
            if not release.wait(5):
                raise AssertionError('The test did not release its fake provider.')
            return dialogue_for_scenario(scenario)

        self.ai.step_dialogue.side_effect = generate
        with patch('services.step_conversation.timestamp', return_value=timestamp()) as clock:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.service.retry, self.access, sid)
                try:
                    self.assertTrue(entered.wait(2))
                    claimed = self.saved(sid)
                    clock.return_value = claimed['lease_until'] + 1
                    second = pool.submit(self.service.retry, self.access, sid)
                    self.assertEqual(second.result(timeout=2)['state'], 'preparing')
                    self.ai.step_dialogue.assert_called_once()
                    self.assertEqual(self.saved(sid)['preparation_id'], claimed['preparation_id'])
                    self.assertEqual(self.service.read(self.access, sid)['state'], 'preparing')
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=2)['state'], 'active')
        self.assertEqual(self.service.preparing, set())

    def assert_old_attempt_is_fenced(self, fail):
        sid = self.start('fenced', prepare=False)['id']
        old_entered, old_release = threading.Event(), threading.Event()
        new_entered, new_release = threading.Event(), threading.Event()
        current_ai = Mock()

        def older(scenario):
            old_entered.set()
            if not old_release.wait(5):
                raise AssertionError('The test did not release the older provider.')
            if fail:
                raise SpeechError('Older preparation failed.')
            result = dialogue_for_scenario(scenario)
            result['turns'][0]['npc']['russian'] = 'Старая подготовка: куда вы идёте?'
            return result

        def newer(scenario):
            new_entered.set()
            if not new_release.wait(5):
                raise AssertionError('The test did not release the newer provider.')
            result = dialogue_for_scenario(scenario)
            result['turns'][0]['npc']['russian'] = 'Новая подготовка: куда вы идёте?'
            return result

        self.ai.step_dialogue.side_effect = older
        current_ai.step_dialogue.side_effect = newer
        replacement = StepConversationService(self.db, self.speech, current_ai, self.app.config)
        with patch('services.step_conversation.timestamp', return_value=timestamp()) as clock:
            with ThreadPoolExecutor(max_workers=3) as pool:
                old = pool.submit(self.service.retry, self.access, sid)
                try:
                    self.assertTrue(old_entered.wait(2))
                    old_claim = self.saved(sid)
                    clock.return_value = old_claim['lease_until'] + 1
                    new = pool.submit(replacement.retry, self.access, sid)
                    self.assertTrue(new_entered.wait(2))
                    new_claim = self.saved(sid)
                    self.assertNotEqual(new_claim['preparation_id'], old_claim['preparation_id'])
                    old_release.set()
                    self.assertEqual(old.result(timeout=2)['state'], 'preparing')
                    after_old = self.saved(sid)
                    for key in ('state', 'lease_until', 'preparation_id', 'error', 'dialogue_json'):
                        self.assertEqual(after_old[key], new_claim[key], key)
                    retry = pool.submit(replacement.retry, self.access, sid)
                    self.assertEqual(retry.result(timeout=2)['state'], 'preparing')
                    current_ai.step_dialogue.assert_called_once()
                finally:
                    old_release.set()
                    new_release.set()
                self.assertEqual(new.result(timeout=2)['state'], 'active')
        saved = self.saved(sid)
        self.assertIsNone(saved['preparation_id'])
        self.assertEqual(saved['lease_until'], 0)
        self.assertEqual(json.loads(saved['dialogue_json'])['turns'][0]['npc']['russian'],
                         'Новая подготовка: куда вы идёте?')

    def test_stale_success_cannot_publish_over_a_newer_preparation(self):
        self.assert_old_attempt_is_fenced(fail=False)

    def test_stale_failure_cannot_clear_a_newer_preparation_lease(self):
        self.assert_old_attempt_is_fenced(fail=True)

    def test_third_preparation_returns_busy_without_queueing_or_blocking_reads(self):
        sessions = [self.start('slots-' + str(index), prepare=False)['id'] for index in range(3)]
        entered, release, guard = threading.Event(), threading.Event(), threading.Lock()
        calls = []

        def generate(scenario):
            with guard:
                calls.append(True)
                if len(calls) == 2:
                    entered.set()
            if not release.wait(5):
                raise AssertionError('The test did not release its fake providers.')
            return dialogue_for_scenario(scenario)

        self.ai.step_dialogue.side_effect = generate
        with ThreadPoolExecutor(max_workers=3) as pool:
            first = [pool.submit(self.service.retry, self.access, sid) for sid in sessions[:2]]
            try:
                self.assertTrue(entered.wait(2))
                third = pool.submit(self.service.retry, self.access, sessions[2])
                with self.assertRaises(LearningError) as caught:
                    third.result(timeout=2)
                self.assertEqual((caught.exception.code, caught.exception.status), ('busy', 409))
                self.assertEqual(len(calls), 2)
                self.assertEqual(self.service.read(self.access, sessions[2])['state'], 'preparing')
                self.assertEqual(len(self.service.history(self.access)['sessions']), 3)
            finally:
                release.set()
            for future in first:
                self.assertEqual(future.result(timeout=2)['state'], 'active')
        self.ai.step_dialogue.side_effect = dialogue_for_scenario
        self.assertEqual(self.service.retry(self.access, sessions[2])['state'], 'active')

    def test_audio_busy_returns_409_promptly_and_saved_reads_remain_available(self):
        # A conversation saved before automatic speaker preparation has no MP3.
        with patch.object(self.service, '_prepare_current_audio', side_effect=self.service.read):
            state = self.start('audio-busy')
        self.service.audio_lock.acquire()
        with ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(self.post_audio, state)
            try:
                response = request.result(timeout=2)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json['error']['code'], 'busy')
                read = self.client.get(self.base + '/' + state['id'])
                self.assertEqual(read.status_code, 200)
                self.assertEqual(read.json['current_turn']['id'], state['current_turn']['id'])
                self.assertEqual(self.client.get(self.base + '/history').status_code, 200)
                self.assertEqual(self.speech.voices, [])
            finally:
                self.service.audio_lock.release()
        self.assertEqual(self.post_audio(state).status_code, 200)
        self.assertEqual(len(self.speech.voices), 1)

    def test_cached_audio_is_available_even_when_another_audio_request_is_busy(self):
        state = self.start('audio-cache')
        ready = self.post_audio(state)
        self.assertEqual(ready.status_code, 200)
        url = ready.json['current_turn']['npc_audio_url']
        self.service.audio_lock.acquire()
        with ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(self.post_audio, state)
            try:
                response = request.result(timeout=2)
                self.assertEqual(response.status_code, 200, response.text)
                cached = self.client.get(url)
                self.addCleanup(cached.close)
                self.assertEqual(cached.status_code, 200)
                self.assertEqual(cached.data, b'test-only-mp3')
                self.assertEqual(cached.headers['Cache-Control'], 'no-store')
                self.assertEqual(len(self.speech.voices), 1)
            finally:
                self.service.audio_lock.release()

    def test_advancement_commits_before_speech_and_replay_does_not_purchase_again(self):
        state = self.start('advance-audio')
        sid, tid = state['id'], state['current_turn']['id']
        dialogue = json.loads(self.saved(sid)['dialogue_json'])
        correct = next(option['id'] for option in dialogue['turns'][0]['options'] if option['correct'])
        self.service.answer(self.access, sid, {'submission_id': 'correct-current', 'turn_id': tid, 'option_id': correct})
        entered, release = threading.Event(), threading.Event()

        def synthesize(text, voice):
            entered.set()
            if not release.wait(5):
                raise AssertionError('The test did not release speech preparation.')
            return b'test-only-mp3'

        self.speech.speak = Mock(side_effect=synthesize)
        with ThreadPoolExecutor(max_workers=2) as pool:
            original = pool.submit(self.service.next, self.access, sid, {'turn_id': tid})
            try:
                self.assertTrue(entered.wait(2))
                replay = pool.submit(self.service.next, self.access, sid, {'turn_id': tid}).result(timeout=2)
                self.assertEqual(replay['completed_turns'], 1)
                self.assertEqual(replay['current_turn']['id'], dialogue['turns'][1]['id'])
                self.assertIsNone(replay['current_turn']['npc_audio_url'])
                self.assertEqual(self.service.read(self.access, sid)['completed_turns'], 1)
                self.speech.speak.assert_called_once()
            finally:
                release.set()
            prepared = original.result(timeout=2)
        self.assertTrue(prepared['current_turn']['npc_audio_url'])
        self.assertIsNone(prepared['current_turn']['npc_audio_error'])
        self.speech.speak.assert_called_once()


if __name__ == '__main__':
    unittest.main()
