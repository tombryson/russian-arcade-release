"""Live trial reservation, permission boundary and bounded session tests."""
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from services.ai_trial_budget import AITrialBudget, TrialDenied
from services.conversation_ai import SCENARIO
from services.live_conversation import LiveConversationService
from services.live_voice_provider import LiveVoiceProvider
from services.speech_provider import SpeechError
from services.trial_live_budget import LiveTrialBudget, TRIAL_SECONDS, VOICE_RESERVATION
from tests.support import isolated_app
from tests.test_conversation import FakeAI, FakeSpeech
from tests.test_live_conversation import FakeLive, FakeSocket


class LiveTrialBudgetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'budget.db'
        self.ledger = AITrialBudget(self.path, enabled=True)
        self.ledger.initialize()
        self.ledger.authorize_identity('github:11')
        self.config = {'HOSTED_AI_TRIAL': True, 'AI_TRIAL_ENABLED': True,
                       'AI_TRIAL_IDENTITY': 'github:11', 'AI_TRIAL_LEDGER_PATH': str(self.path)}
        self.budget = LiveTrialBudget(self.config)
        self.session = {'id': 'example', 'model': 'gpt-live-1'}

    def row(self):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM trial_requests').fetchone()
            return dict(row) if row else None

    def test_voice_reservation_is_once_and_has_distinct_lane(self):
        self.budget.reserve(self.session, SCENARIO)
        row = self.row()
        self.assertEqual((row['request_id'], row['reserved'], row['lane'], row['state']),
                         ('live:example', VOICE_RESERVATION, 'voice', 'reserved'))
        with self.assertRaises(TrialDenied):
            self.budget.reserve(self.session, SCENARIO)
        self.assertIsNone(self.row()['actual'])

    def test_unknown_model_and_disabled_trial_fail_before_new_admission(self):
        with self.assertRaises(TrialDenied):
            self.budget.reserve(self.session | {'model': 'unknown-live'}, SCENARIO)
        self.assertIsNone(self.row())
        disabled = LiveTrialBudget(self.config | {'AI_TRIAL_ENABLED': False})
        with self.assertRaises(TrialDenied):
            disabled.reserve(self.session, SCENARIO)
        self.assertIsNone(self.row())

    def test_final_provider_seconds_settle_actual_cost(self):
        self.budget.reserve(self.session, SCENARIO)
        self.budget.finish(self.session['id'], {'seconds': 60})
        self.assertEqual((self.row()['state'], self.row()['actual']), ('settled', 50_000))
        self.budget.finish(self.session['id'], {'seconds': 60})
        self.assertEqual(self.row()['actual'], 50_000)

    def test_fractional_seconds_round_up_and_overage_halts_new_spend(self):
        self.budget.reserve(self.session, SCENARIO)
        self.budget.finish(self.session['id'], {'seconds': 120.001})
        self.assertEqual(self.row()['actual'], 100_001)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT halted FROM trial_control').fetchone()[0], 1)
        with self.assertRaises(TrialDenied):
            self.budget.reserve(self.session | {'id': 'another'}, SCENARIO)

    def test_missing_or_invalid_usage_keeps_full_hold(self):
        self.budget.reserve(self.session, SCENARIO)
        for usage in (None, {}, {'seconds': None}, {'seconds': '60'}, {'seconds': True},
                      {'seconds': -1}, {'seconds': float('nan')}, {'seconds': float('inf')}):
            self.budget.finish(self.session['id'], usage)
            self.assertEqual(self.row()['state'], 'uncertain')
            self.assertIsNone(self.row()['actual'])
            self.assertEqual(self.row()['reserved'], VOICE_RESERVATION)
        with self.assertRaises(TrialDenied):
            self.budget.reserve(self.session | {'id': 'another'}, SCENARIO)

    def test_local_calls_need_no_ledger(self):
        local = LiveTrialBudget({})
        local.reserve({'id': 'local', 'model': 'anything'}, {})
        local.finish('local', None)
        self.assertIsNone(self.row())


class TrialVoicePermissionsTests(unittest.TestCase):
    def setUp(self):
        self.provider = LiveVoiceProvider({'HOSTED_AI_TRIAL': True, 'OPENAI_API_KEY': 'synthetic-only'})
        self.session = {'model': 'gpt-live-1', 'backend_model': 'gpt-5.6-luna', 'voice': 'marin'}

    def test_trial_uses_metered_client_delegation_and_narrow_browser_permissions(self):
        response = Mock(ok=True)
        response.json.return_value = {'session': {'id': 'live_id'}, 'transport': {'sdp': 'v=0 answer'}}
        with patch('services.live_voice_provider.requests.post', return_value=response) as post:
            self.assertEqual(self.provider.create(self.session, SCENARIO, 'v=0 offer'), ('live_id', 'v=0 answer'))
        configuration = post.call_args.kwargs['json']['session']
        self.assertEqual(configuration['delegation'], {'type': 'client'})
        permissions = configuration['client']['data_channel']
        self.assertEqual(set(permissions['allowed_client_events']),
                         {'session.close', 'session.input_audio.mute', 'session.input_audio.unmute'})
        self.assertFalse({'session.instructions.append', 'session.thinking.append', 'session.update'}
                         & set(permissions['allowed_client_events']))
        events = {row['type'] for row in permissions['allowed_server_events']}
        self.assertNotIn('session.delegation.created', events)
        self.assertNotIn('session.input_audio.append', events)
        self.assertIn('session.output_transcript.delta', events)
        self.assertFalse(configuration['store'])

    def test_hangup_uses_server_key_and_encodes_identifier(self):
        with patch('services.live_voice_provider.requests.post', return_value=Mock(ok=True)) as post:
            self.provider.hangup('session/id?x=1')
        args = post.call_args
        self.assertEqual(args.args[0], 'https://api.openai.com/v1/live/sessions/session%2Fid%3Fx%3D1/hangup')
        self.assertEqual(args.kwargs['headers']['Authorization'], 'Bearer synthetic-only')
        self.assertEqual(args.kwargs['timeout'], (5, 10))
        with patch('services.live_voice_provider.requests.post', return_value=Mock(ok=False)):
            with self.assertRaises(SpeechError):
                self.provider.hangup('session')


class HostedLiveServiceTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeLive()
        self.app = isolated_app(self, {'LiveVoiceProvider': self.provider, 'SpeechProvider': FakeSpeech(), 'ConversationAI': FakeAI()})
        self.service = self.app.extensions['learning']['live_conversation']
        self.ledger_path = Path(self.app.config['DB_PATH']).parent / 'budget.db'
        self.ledger = AITrialBudget(self.ledger_path, enabled=True)
        self.ledger.initialize()
        self.ledger.authorize_identity('github:11')
        self.config = dict(self.app.config) | {'HOSTED_AI_TRIAL': True, 'AI_TRIAL_ENABLED': True,
            'AI_TRIAL_IDENTITY': 'github:11', 'AI_TRIAL_LEDGER_PATH': str(self.ledger_path)}
        self.service.config = self.config
        self.service.trial_budget = LiveTrialBudget(self.config)
        self.service.max_seconds = TRIAL_SECONDS
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/v1/user-session').json['csrf_token']
        self.addCleanup(self.service.executor.shutdown, wait=True)
        self.addCleanup(self.service.reviews.executor.shutdown, wait=True)

    def post(self, path, data):
        return self.client.post('/api/v1/live-conversations' + path, json=data, headers={'X-CSRF-Token': self.csrf})

    def start(self):
        response = self.post('', {'submission_id': 'trial-start'})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json['id']

    def row(self):
        with sqlite3.connect(self.ledger_path) as conn:
            conn.row_factory = sqlite3.Row
            return dict(conn.execute('SELECT * FROM trial_requests').fetchone())

    def test_ledger_reservation_precedes_connection_and_failed_create_keeps_hold(self):
        sid = self.start()
        def create(*_):
            self.assertEqual(self.row()['state'], 'reserved')
            self.assertEqual(self.row()['request_id'], 'live:' + sid)
            raise SpeechError('synthetic connection failure')
        self.provider.create = Mock(side_effect=create)
        data = {'sdp': 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'}
        self.assertEqual(self.post('/' + sid + '/connect', data).status_code, 502)
        self.assertEqual(self.row()['state'], 'uncertain')
        self.assertEqual(self.provider.create.call_count, 1)
        self.assertEqual(self.post('/' + sid + '/connect', data).status_code, 409)
        self.assertEqual(self.provider.create.call_count, 1)

    def test_created_provider_call_is_hung_up_if_local_save_fails(self):
        sid = self.start()
        original = self.service._session
        def save(session_id, **fields):
            if fields.get('provider_id'):
                raise sqlite3.OperationalError('synthetic storage failure')
            return original(session_id, **fields)
        self.provider.hangup = Mock()
        with patch.object(self.service, '_session', side_effect=save):
            response = self.post('/' + sid + '/connect', {'sdp': 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'})
        self.assertEqual(response.status_code, 502)
        self.provider.hangup.assert_called_once_with('live_opaque_id')
        self.assertEqual(self.row()['state'], 'uncertain')

    def test_audio_is_flushed_and_runtime_released_if_settlement_fails(self):
        sid = self.start()
        runtime = {'stop': threading.Event(), 'ready': threading.Event(), 'closed': threading.Event(), 'error': None}
        runtime['stop'].set()
        self.service.connections[sid] = runtime
        with patch('services.live_conversation._ReceivedAudio') as recorder, \
             patch.object(self.service.trial_budget, 'finish', side_effect=TrialDenied('synthetic ledger outage')), \
             patch.object(self.service.reviews, 'request'), \
             patch('services.trial_live_delegation.TrialLiveDelegation') as delegate:
            delegate.return_value.tick.return_value = []
            delegate.return_value.receive.return_value = []
            with self.assertRaises(TrialDenied):
                self.service._listen(sid, 'provider-session', runtime)
            recorder.return_value.finish.assert_called_once()
        self.assertTrue(runtime['closed'].is_set())
        self.assertNotIn(sid, self.service.connections)

    def test_sideband_failure_hangs_up_primary_call_and_retains_hold(self):
        sid = self.start()
        scenario = self.client.get('/api/v1/live-conversations/' + sid).json['scenario']
        self.service.trial_budget.reserve({'id': sid, 'model': 'gpt-live-1'}, scenario)
        runtime = {'stop': threading.Event(), 'ready': threading.Event(), 'closed': threading.Event(), 'error': None}
        self.service.connections[sid] = runtime
        self.provider.attach = Mock(side_effect=SpeechError('synthetic sideband failure'))
        self.provider.hangup = Mock()
        with patch.object(self.service.reviews, 'request'), patch('services.trial_live_delegation.TrialLiveDelegation'):
            self.service._listen(sid, 'provider-session', runtime)
        self.provider.hangup.assert_called_once_with('provider-session')
        self.assertEqual(self.row()['state'], 'uncertain')
        self.assertIsNotNone(runtime['error'])
        self.assertTrue(runtime['closed'].is_set())

    def test_constructor_applies_one_minute_limit_only_to_hosted_trial(self):
        trial = LiveConversationService(self.app.config['DB_PATH'], self.provider, None, None, self.config)
        self.addCleanup(trial.executor.shutdown, wait=True)
        self.assertEqual(trial.max_seconds, 60)
        local = LiveConversationService(self.app.config['DB_PATH'], self.provider, None, None, {})
        self.addCleanup(local.executor.shutdown, wait=True)
        self.assertEqual(local.max_seconds, 300)

    def test_listener_stops_at_limit_and_records_final_usage(self):
        sid = self.start()
        scenario = self.client.get('/api/v1/live-conversations/' + sid).json['scenario']
        self.service.trial_budget.reserve({'id': sid, 'model': 'gpt-live-1'}, scenario)
        class ClosingSocket(FakeSocket):
            def send(self, data):
                event = json.loads(data)
                self.sent.append(event)
                if event['type'] == 'session.close':
                    self.incoming.put({'type': 'session.closed', 'usage': {'seconds': 60}})
        socket = ClosingSocket()
        self.provider.ws = socket
        self.provider.hangup = Mock()
        runtime = {'stop': threading.Event(), 'ready': threading.Event(), 'closed': threading.Event(), 'error': None}
        self.service.connections[sid] = runtime
        moments = iter([0, 61, 61, 61, 61, 61])
        with patch('services.live_conversation.time.monotonic', side_effect=lambda: next(moments, 61)), \
             patch.object(self.service.reviews, 'request'), \
             patch('services.trial_live_delegation.TrialLiveDelegation') as delegate:
            delegate.return_value.tick.return_value = []
            delegate.return_value.receive.return_value = []
            self.service._listen(sid, 'provider-session', runtime)
        self.assertTrue(runtime['closed'].is_set())
        self.assertTrue(any(event['type'] == 'session.close' for event in socket.sent))
        self.assertEqual(self.row()['actual'], 50_000)
        self.assertEqual(self.row()['state'], 'settled')
        state = self.client.get('/api/v1/live-conversations/' + sid).json
        self.assertEqual(state['end_reason'], 'time_limit')
        self.assertEqual(state['state'], 'completed')
        self.provider.hangup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
