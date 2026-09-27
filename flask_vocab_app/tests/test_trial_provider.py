"""Admission tests use fake providers only; no API credentials or paid calls."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import io
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock
import wave

from flask import Flask
from services.ai_trial_budget import AITrialBudget, TrialDenied
from services.trial_provider import (TrialOpenAI, config_snapshot, openai_client,
    elevenlabs_call, mai_call, yandex_call)


class TrialProviderTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        self.path = self.root / 'budget.db'
        self.ledger = AITrialBudget(self.path, enabled=True)
        self.ledger.initialize()
        self.ledger.authorize_identity('verified-user')
        self.config = {'HOSTED_AI_TRIAL': True, 'AI_TRIAL_ENABLED': True,
                       'AI_TRIAL_IDENTITY': 'verified-user', 'AI_TRIAL_LEDGER_PATH': str(self.path)}
        self.raw = Mock()
        self.raw.with_options.return_value = self.raw
        self.raw.chat.completions.create.return_value = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))
        self.raw.responses.create.return_value = SimpleNamespace(usage=SimpleNamespace(input_tokens=100, output_tokens=20))
        self.client = TrialOpenAI(self.raw, self.config)

    def rows(self):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute('SELECT * FROM trial_requests')]

    def chat(self, **extra):
        return self.client.chat.completions.create(model='gpt-5.6-luna',
            messages=[{'role': 'user', 'content': 'Привет'}], **extra)

    def test_reservation_before_provider_and_usage_releases_headroom(self):
        def response(**kwargs):
            rows = self.rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['state'], 'reserved')
            self.assertGreater(rows[0]['reserved'], 44)
            self.assertEqual(kwargs['max_completion_tokens'], 4096)
            self.assertFalse(kwargs['store'])
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))
        self.raw.chat.completions.create.side_effect = response
        self.chat()
        self.assertEqual(self.rows()[0]['actual'], 49)
        self.assertEqual(self.rows()[0]['state'], 'settled')

    def test_factory_and_options_never_restore_hidden_retries(self):
        factory = Mock(return_value=self.raw)
        client = openai_client(config=self.config, factory=factory, api_key='test-only', max_retries=5)
        self.assertEqual(factory.call_args.kwargs['max_retries'], 0)
        self.assertEqual(factory.call_args.kwargs['base_url'], 'https://api.openai.com/v1')
        client.with_options(timeout=10, max_retries=3)
        self.assertEqual(self.raw.with_options.call_args.kwargs['max_retries'], 0)
        with self.assertRaises(TrialDenied):
            client.with_options(base_url='https://elsewhere.invalid')

    def test_local_client_keeps_existing_behavior(self):
        factory = Mock(return_value=self.raw)
        self.assertIs(openai_client(config={}, factory=factory, api_key='test-only', max_retries=1), self.raw)
        self.assertEqual(factory.call_args.kwargs['max_retries'], 1)
        call = Mock(return_value='local')
        self.assertEqual(elevenlabs_call({}, 'x' * 5000, 'local-model', 'voice', call), 'local')
        call.assert_called_once()
        self.assertEqual(self.rows(), [])

    def test_toggle_off_and_missing_identity_do_not_become_unmetered(self):
        for config in ({**self.config, 'AI_TRIAL_ENABLED': False},
                       {**self.config, 'AI_TRIAL_IDENTITY': ''},
                       {**self.config, 'AI_TRIAL_LEDGER_PATH': ''},
                       {**self.config, 'AI_TRIAL_IDENTITY': 'unregistered'}):
            client = TrialOpenAI(self.raw, config)
            with self.assertRaises(TrialDenied):
                client.responses.create(model='gpt-5.6-luna', input='Hello')
        self.raw.responses.create.assert_not_called()

    def test_server_identity_is_immutable_and_survives_background_thread(self):
        app = Flask(__name__)
        app.config.update(self.config)
        with app.app_context():
            client = TrialOpenAI(self.raw, config_snapshot())
        app.config['AI_TRIAL_IDENTITY'] = 'different-browser-profile'
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(client.responses.create, model='gpt-5.6-luna', input='Hello').result()
        self.assertEqual(self.rows()[0]['identity'], 'verified-user')

    def test_budget_and_unknown_models_block_before_network(self):
        self.ledger.reserve('verified-user', 'spent', 'a' * 64, 1_000_000)
        self.ledger.settle('verified-user', 'spent', 1_000_000)
        with self.assertRaises(TrialDenied):
            self.chat()
        with self.assertRaises(TrialDenied):
            self.client.responses.create(model='unpriced-premium', input='Hello')
        self.raw.chat.completions.create.assert_not_called()
        self.raw.responses.create.assert_not_called()

    def test_unbounded_operations_and_hidden_state_are_rejected(self):
        for extra in ({'stream': True}, {'n': 2}, {'tools': [{'type': 'web_search'}]},
                      {'max_completion_tokens': 999999}, {'max_tokens': -1},
                      {'extra_body': {'model': 'expensive'}}, {'service_tier': 'fast'},
                      {'modalities': ['audio']}, {'previous_response_id': 'response'},
                      {'conversation': 'hidden-history'}):
            with self.subTest(extra=extra), self.assertRaises(TrialDenied):
                self.chat(**extra)
        with self.assertRaises(AttributeError):
            self.client.files.create()
        with self.assertRaises(TrialDenied):
            self.client.responses.create(model='gpt-5.6-luna', input='x' * 100000)
        self.raw.chat.completions.create.assert_not_called()
        self.assertEqual(self.rows(), [])

    def test_timeout_and_missing_usage_charge_bound_without_retry(self):
        self.raw.chat.completions.create.side_effect = TimeoutError('lost response')
        with self.assertRaises(TimeoutError):
            self.chat()
        row = self.rows()[0]
        self.assertEqual(row['actual'], row['reserved'])
        self.assertEqual(self.raw.chat.completions.create.call_count, 1)
        self.raw.chat.completions.create.side_effect = None
        self.raw.chat.completions.create.return_value = SimpleNamespace()
        self.chat()
        self.assertEqual(self.rows()[1]['actual'], self.rows()[1]['reserved'])

    def test_underestimated_usage_is_recorded_and_halts_new_requests(self):
        self.raw.chat.completions.create.return_value = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000))
        self.chat()
        self.assertEqual(self.rows()[0]['actual'], 1_450_000)
        with self.assertRaises(TrialDenied):
            self.chat()

    def test_concurrency_cannot_bypass_per_account_admission(self):
        started, finish = threading.Event(), threading.Event()
        def block(**kwargs):
            started.set()
            finish.wait(5)
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10))
        self.raw.chat.completions.create.side_effect = block
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.chat)
            self.assertTrue(started.wait(5))
            try:
                with self.assertRaises(TrialDenied):
                    self.chat()
            finally:
                finish.set()
            first.result()
        self.assertEqual(self.raw.chat.completions.create.call_count, 1)

    def test_image_shape_and_usage_are_bounded(self):
        self.raw.images.generate.return_value = SimpleNamespace(usage=SimpleNamespace(input_tokens=40, output_tokens=3500))
        self.client.images.generate(model='gpt-image-2', prompt='A cat')
        sent = self.raw.images.generate.call_args.kwargs
        self.assertEqual((sent['n'], sent['size'], sent['quality']), (1, '1024x1024', 'medium'))
        self.assertEqual(self.rows()[0]['actual'], 52600)
        for extra in ({'n': 8}, {'quality': 'high'}, {'size': '4096x4096'}, {'extra_body': {'n': 4}}):
            with self.assertRaises(TrialDenied):
                self.client.images.generate(model='gpt-image-2', prompt='A cat', **extra)
        self.assertEqual(self.raw.images.generate.call_count, 1)

    def test_vision_rejects_remote_urls_and_limits_pages(self):
        import base64
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (100, 100)).save(buffer, format='PNG')
        url = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
        content = [{'type': 'input_image', 'image_url': url}]
        self.client.responses.create(model='gpt-5.6-luna', input=[{'role': 'user', 'content': content}])
        self.assertGreater(self.rows()[0]['reserved'], 5000)
        for invalid in ([{'type': 'input_image', 'image_url': 'https://example.test/a.png'}], content * 5):
            with self.assertRaises(TrialDenied):
                self.client.responses.create(model='gpt-5.6-luna', input=[{'role': 'user', 'content': invalid}])
        self.assertEqual(self.raw.responses.create.call_count, 1)

    def audio(self):
        path = self.root / 'sample.wav'
        with wave.open(str(path), 'wb') as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(16000)
            file.writeframes(b'\0' * 32000)
        return path

    def test_stt_and_mai_charge_before_network(self):
        path = self.audio()
        with path.open('rb') as file:
            self.client.audio.transcriptions.create(model='gpt-transcribe', file=file)
            self.assertEqual(file.tell(), 0)
        call = Mock(return_value={'text': 'Привет'})
        mai_call(self.config, path, 'microsoft/mai-transcribe-2', {}, call)
        self.assertEqual(len(self.rows()), 2)
        self.assertTrue(all(row['actual'] == row['reserved'] for row in self.rows()))
        call.assert_called_once()

    def test_tts_and_yandex_are_covered_and_bound_inputs(self):
        call = Mock(return_value='audio')
        elevenlabs_call(self.config, 'Привет', 'eleven_multilingual_v2', 'voice', call)
        yandex_call(self.config, 'Привет', 'en', call)
        self.assertEqual([row['actual'] for row in self.rows()], [1200, 600])
        for operation in (
            lambda: elevenlabs_call(self.config, 'x' * 3001, 'eleven_multilingual_v2', 'voice', call),
            lambda: elevenlabs_call(self.config, 'x', 'unknown-model', 'voice', call),
            lambda: yandex_call(self.config, 'x' * 3001, 'en', call)):
            with self.assertRaises(TrialDenied):
                operation()
        self.assertEqual(call.call_count, 2)

    def test_missing_ledger_cannot_reset_spending(self):
        self.path.unlink()
        with self.assertRaises(TrialDenied):
            self.chat()
        self.raw.chat.completions.create.assert_not_called()
        self.assertFalse(self.path.exists())
