"""Hosted spending and burst limits reach every metered provider boundary.

Providers are mocks. Historical ledger rows model prior spending without
making paid calls or depending on the system clock crossing a budget period.
"""
import base64
import io
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import wave

from services.ai_trial_budget import (
    ACCOUNT_DAILY_LIMIT, ACCOUNT_OPERATIONS_PER_MINUTE, ACCOUNT_TOTAL_LIMIT,
    TOTAL_LIMIT, AITrialBudget, TrialDenied,
)
from services.trial_live_budget import LiveTrialBudget, TRIAL_SECONDS, VOICE_RESERVATION
from services.trial_provider import TrialOpenAI, elevenlabs_call, provider_call


class DemoAbuseControlsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'budget.db'
        self.ledger = AITrialBudget(self.path, enabled=True)
        self.ledger.initialize()
        self.identity = 'github:verified-demo-user'
        self.ledger.authorize_identity(self.identity)
        self.config = {
            'HOSTED_AI_TRIAL': True, 'AI_TRIAL_ENABLED': True,
            'AI_TRIAL_IDENTITY': self.identity,
            'AI_TRIAL_LEDGER_PATH': str(self.path),
        }
        self.raw = Mock()
        self.raw.responses.create.return_value = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=100, output_tokens=20))
        self.client = TrialOpenAI(self.raw, self.config)

    def seed_spending(self, cost, *, identity=None, age_seconds=0, count=1):
        identity = identity or self.identity
        self.ledger.authorize_identity(identity)
        when = int(time.time()) - age_seconds
        with sqlite3.connect(self.path) as conn:
            offset = conn.execute('SELECT COUNT(*) FROM trial_requests').fetchone()[0]
            conn.executemany('''
                INSERT INTO trial_requests
                    (identity, request_id, payload_hash, reserved, actual,
                     created_at, settled_at, state, lane)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'settled', 'operation')
            ''', [(identity, f'history-{offset + index}', 'a' * 64,
                   max(1, cost), cost, when, when) for index in range(count)])

    def rows(self):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute('SELECT * FROM trial_requests')]

    def text(self, client=None):
        return (client or self.client).responses.create(
            model='gpt-5.6-luna', input='Чай, пожалуйста.', max_output_tokens=1024)

    def test_daily_account_limit_stops_text_and_audio_before_provider_calls(self):
        self.seed_spending(ACCOUNT_DAILY_LIMIT)
        before = self.rows()
        with self.assertRaises(TrialDenied):
            self.text()
        audio = Mock()
        with self.assertRaises(TrialDenied):
            elevenlabs_call(self.config, 'Здравствуйте!', 'eleven_multilingual_v2',
                           'test-voice', audio)
        self.raw.responses.create.assert_not_called()
        audio.assert_not_called()
        self.assertEqual(self.rows(), before)

    def test_lifetime_account_limit_still_applies_after_daily_reset(self):
        self.seed_spending(ACCOUNT_TOTAL_LIMIT, age_seconds=40 * 86400)
        invoke = Mock()
        with self.assertRaises(TrialDenied):
            provider_call(self.config, 'test-generation', {'prompt': 'Hello'}, 100, invoke)
        invoke.assert_not_called()
        self.assertEqual(len(self.rows()), 1)

    def test_burst_allowance_is_shared_across_text_audio_and_live_connections(self):
        # Zero-cost settled work still consumed provider operations. Switching
        # activity or provider must not reset a user's rolling minute.
        self.seed_spending(0, count=ACCOUNT_OPERATIONS_PER_MINUTE)
        before = self.rows()
        audio = Mock()
        with self.assertRaises(TrialDenied):
            self.text()
        with self.assertRaises(TrialDenied):
            elevenlabs_call(self.config, 'Привет!', 'eleven_multilingual_v2',
                           'test-voice', audio)
        with self.assertRaises(TrialDenied):
            LiveTrialBudget(self.config).reserve(
                {'id': 'blocked-live', 'model': 'gpt-live-1'}, {'scenario_id': 'cafe'})
        self.raw.responses.create.assert_not_called()
        audio.assert_not_called()
        self.assertEqual(self.rows(), before)

    def test_burst_cooldown_allows_new_work_without_resetting_history(self):
        self.seed_spending(0, age_seconds=61, count=ACCOUNT_OPERATIONS_PER_MINUTE)
        self.text()
        self.raw.responses.create.assert_called_once()
        self.assertEqual(len(self.rows()), ACCOUNT_OPERATIONS_PER_MINUTE + 1)
        self.assertTrue(all(row['state'] == 'settled' for row in self.rows()))

    def test_new_identity_cannot_bypass_the_shared_total_allowance(self):
        self.seed_spending(TOTAL_LIMIT, identity='github:prior-user', age_seconds=40 * 86400)
        before = self.rows()
        fresh_client = TrialOpenAI(self.raw, self.config)
        with self.assertRaises(TrialDenied):
            self.text(fresh_client)
        with self.assertRaises(TrialDenied):
            LiveTrialBudget(self.config).reserve(
                {'id': 'new-user-live', 'model': 'gpt-live-1'}, {'scenario_id': 'cafe'})
        self.raw.responses.create.assert_not_called()
        self.assertEqual(self.rows(), before)

    def test_live_connection_reserves_its_full_bound_against_account_spend(self):
        self.seed_spending(ACCOUNT_DAILY_LIMIT - VOICE_RESERVATION + 1)
        with self.assertRaises(TrialDenied):
            LiveTrialBudget(self.config).reserve(
                {'id': 'over-allowance', 'model': 'gpt-live-1'}, {'scenario_id': 'cafe'})
        self.assertEqual(len(self.rows()), 1)

    def test_one_minute_conversation_with_text_and_audio_feedback_still_fits(self):
        live = LiveTrialBudget(self.config)
        session = {'id': 'normal-live', 'model': 'gpt-live-1'}
        live.reserve(session, {'scenario_id': 'cafe'})
        self.assertEqual(self.rows()[0]['reserved'], VOICE_RESERVATION)

        # The separate operation lane must remain usable while voice is held.
        self.text()
        self.text()
        self.assertEqual(self.raw.responses.create.call_count, 2)
        self.assertEqual(self.rows()[0]['state'], 'reserved')

        recording = io.BytesIO()
        with wave.open(recording, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\0' * (16000 * 2 * TRIAL_SECONDS))
        self.raw.chat.completions.create.return_value = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=6100, completion_tokens=100,
                                  prompt_tokens_details=SimpleNamespace(audio_tokens=6000)))
        self.client.chat.completions.create(
            model='gpt-audio-1.5', max_completion_tokens=4096,
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': 'Assess the Russian grammar and fluency.'},
                {'type': 'input_audio', 'input_audio': {
                    'format': 'wav', 'data': base64.b64encode(recording.getvalue()).decode()}},
            ]}])
        self.raw.chat.completions.create.assert_called_once()
        live.finish(session['id'], {'seconds': TRIAL_SECONDS})
        rows = self.rows()
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row['state'] == 'settled' for row in rows))
        self.assertEqual(rows[0]['actual'], 50_000)
        self.assertLess(sum(row['actual'] for row in rows), ACCOUNT_DAILY_LIMIT)

    def test_local_provider_calls_do_not_consult_demo_limits(self):
        self.seed_spending(TOTAL_LIMIT)
        before = self.rows()
        invoke = Mock(return_value='local response')
        self.assertEqual(provider_call({}, 'local', {}, TOTAL_LIMIT * 2, invoke),
                         'local response')
        invoke.assert_called_once_with()
        local_voice = LiveTrialBudget({})
        local_voice.reserve({'id': 'local', 'model': 'local-model'}, {})
        local_voice.finish('local', {'seconds': 300})
        self.assertEqual(self.rows(), before)

    def test_public_demo_cannot_spend_without_a_verified_account(self):
        invoke = Mock()
        with self.assertRaises(TrialDenied):
            provider_call({'PUBLIC_DEMO': True, 'AI_TRIAL_ENABLED': True,
                           'AI_TRIAL_LEDGER_PATH': str(self.path)},
                          'test-generation', {}, 100, invoke)
        invoke.assert_not_called()
        self.assertEqual(self.rows(), [])


if __name__ == '__main__':
    unittest.main()
