"""Offline regression checks for bounded, reproducible TTS evaluation."""
from contextlib import redirect_stdout
from datetime import date
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'compare_tts.py'
spec = importlib.util.spec_from_file_location('compare_tts_under_test', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
KEYS = {'ELEVENLABS_API_KEY': 'secret-eleven', 'OPENROUTER_API_KEY': 'secret-router'}


class Response:
    status_code = 200
    headers = {'Content-Type': 'audio/mpeg'}
    def __init__(self, payload=None, chunks=(b'ID3audio',)):
        self.payload, self.chunks = payload, chunks
        self.closed = False
    def json(self): return self.payload
    def iter_content(self, chunk_size): return iter(self.chunks)
    def close(self): self.closed = True


class Client:
    def __init__(self, failure=None):
        self.posts, self.failure, self.closed = [], failure, False
        self.responses = iter([
            Response([{'model_id': 'eleven_multilingual_v2'}, {'model_id': 'eleven_v4'}]),
            Response({'voice_id': 'voiceA', 'category': 'professional', 'fine_tuning': {'state': {'eleven_v4': 'fine_tuned'}}}),
            Response({'data': [{'id': m.MODEL_MAI, 'supported_voices': [m.VOICE_MAI], 'pricing': {'prompt': '0.000015'}}]}),
            Response({'data': {'label': 'private-not-persisted'}})])
    def get(self, *args, **kwargs): return next(self.responses)
    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if self.failure: raise self.failure
        return Response()
    def close(self): self.closed = True


def processed(raw, directory, stem):
    return {'listen_file': stem + '.listen.mp3', 'raw_sha256': m.digest(raw), 'duration_ms': 1000}


class ComparisonTest(unittest.TestCase):
    def setUp(self): self.samples = m.load_samples()

    def test_dry_run_never_reads_credentials_or_calls_providers(self):
        with patch.object(m, 'load_credentials', side_effect=AssertionError), patch.object(m, 'run', side_effect=AssertionError), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main(['--env-file', '/does/not/exist']), 0)
        self.assertEqual(json.loads(output.getvalue())['budget']['maximum_synthesis_calls'], 12)

    def test_model_settings_are_controlled_without_changing_production(self):
        a = m.request_for(m.MODELS[0], 'Ёж', 'voiceA', m.VOICE_MAI, KEYS)
        b = m.request_for(m.MODELS[2], 'Ёж', 'voiceA', m.VOICE_MAI, KEYS)
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[2]['voice_settings'], {'stability': .8, 'similarity_boost': .85, 'style': 0})
        self.assertEqual(b[2]['voice_settings'], {'stability': .8, 'similarity_boost': .85})
        self.assertEqual(m.request_for(m.MODEL_MAI, 'Ёж', 'voiceA', m.VOICE_MAI, KEYS)[2]['input'], 'Ёж')

    def test_cost_units_promotion_and_hard_bounds(self):
        promo = m.estimate(self.samples, date(2026, 10, 4))
        normal = m.estimate(self.samples, date(2026, 10, 12))
        self.assertLess(promo['published_estimate_usd'], promo['conservative_estimate_usd'])
        self.assertEqual(normal['published_estimate_usd'], normal['conservative_estimate_usd'])
        self.assertIsNone(normal['actual_charge_usd'])
        self.assertLess(normal['conservative_estimate_usd'], 1)
        with self.assertRaises(m.ComparisonError): m.estimate(self.samples * 2)
        with self.assertRaises(m.ComparisonError): m.estimate([{'text': 'я' * 2501}])

    def test_success_records_twelve_calls_shared_text_voice_and_blind_players(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, client = Path(tmp) / 'fresh', Client()
            result = m.run(self.samples, KEYS, path, 'voiceA', client=client, audio_processor=processed)
            self.assertEqual((result['state'], result['calls'], len(client.posts)), ('complete', 12, 12))
            self.assertTrue(client.closed)
            for sample in self.samples:
                rows = [r for r in result['results'] if r['sample_id'] == sample['id']]
                self.assertEqual({r['text_sha256'] for r in rows}, {m.digest(sample['text'].encode())})
                self.assertEqual({r['blind_label'] for r in rows}, set('ABC'))
                self.assertEqual({r['voice'] for r in rows if r['model'] != m.MODEL_MAI}, {'voiceA'})
            manifest = (path / 'manifest.json').read_text()
            self.assertNotIn('secret-', manifest)
            self.assertNotIn('private-not-persisted', manifest)
            self.assertEqual((path / 'listen.html').read_text().count('<audio controls'), 12)
            with self.assertRaises(m.ComparisonError): m.run(self.samples, KEYS, path, 'voiceA', client=Client())

    def test_failure_stops_paid_calls_without_retries_or_exception_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, client = Path(tmp) / 'fresh', Client(RuntimeError('secret-router full provider body'))
            result = m.run(self.samples, KEYS, path, 'voiceA', client=client, audio_processor=processed)
            self.assertEqual((result['state'], result['calls'], len(client.posts)), ('stopped', 1, 1))
            self.assertNotIn('secret-router', (path / 'manifest.json').read_text())
            self.assertEqual(result['results'][0]['error_type'], 'RuntimeError')

    def test_unavailable_preflight_does_not_generate_or_substitute_models(self):
        client = Client()
        client.responses = iter([Response([{'model_id': 'eleven_multilingual_v2'}])])
        with tempfile.TemporaryDirectory() as tmp:
            result = m.run(self.samples, KEYS, Path(tmp) / 'fresh', 'voiceA', client=client)
        self.assertEqual((result['state'], result['calls'], len(client.posts)), ('stopped', 0, 0))

    def test_unconfirmed_professional_voice_stops_before_paid_calls(self):
        client = Client()
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, 'preflight', return_value={
                'eleven_voice_category': 'professional', 'eleven_v4_fine_tuning': 'unreported'}):
            result = m.run(self.samples, KEYS, Path(tmp) / 'fresh', 'voiceA', client=client)
        self.assertEqual(result['error_code'], 'ProfessionalVoiceV4NotConfirmed')
        self.assertEqual((result['calls'], len(client.posts)), (0, 0))

    def test_explicit_capability_override_is_recorded_and_shown(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, 'preflight', return_value={
                'eleven_voice_category': 'professional', 'eleven_v4_fine_tuning': 'unreported'}):
            directory = Path(tmp) / 'fresh'
            result = m.run(self.samples, KEYS, directory, 'voiceA', client=Client(),
                           audio_processor=processed, allow_unverified_voice=True)
            self.assertEqual(result['calls'], 12)
            self.assertTrue(result['allow_unverified_voice'])
            self.assertIn('unconfirmed at preflight', (directory / 'listen.html').read_text())

    def test_stream_timings_are_distinct_and_empty_chunks_ignored(self):
        client = Mock()
        response = Response(chunks=(b'', b'ID3', b'audio'))
        client.post.return_value = response
        raw, timings = m.synthesize(client, ('url', {}, {}), clock=Mock(side_effect=[10, 10.2, 10.8]))
        self.assertEqual(raw, b'ID3audio')
        self.assertEqual((timings['first_body_chunk_ms'], timings['complete_response_ms']), (200, 800))
        self.assertEqual(timings['first_chunk_bytes'], 3)
        self.assertTrue(response.closed)

    def test_silence_and_non_audio_do_not_publish(self):
        from pydub import AudioSegment
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with self.assertRaises(m.ComparisonError): m.prepare_audio(b'{"error":"private"}', path, 'bad')
            silent = io.BytesIO()
            AudioSegment.silent(duration=1000).export(silent, format='mp3')
            with self.assertRaises(m.ComparisonError): m.prepare_audio(silent.getvalue(), path, 'silent')
            self.assertEqual([p.name for p in path.iterdir()], ['silent.raw.mp3'])
            self.assertEqual((path / 'silent.raw.mp3').read_bytes(), silent.getvalue())

    def test_decode_failure_preserves_response_without_publishing_listening_copy(self):
        with tempfile.TemporaryDirectory() as tmp, patch('pydub.AudioSegment.from_file', side_effect=RuntimeError):
            path = Path(tmp)
            with self.assertRaises(RuntimeError): m.prepare_audio(b'ID3paid-audio', path, 'response')
            self.assertEqual((path / 'response.raw.mp3').read_bytes(), b'ID3paid-audio')
            self.assertFalse((path / 'response.listen.mp3').exists())

    def test_real_audio_raw_integrity_and_normalized_copy(self):
        from pydub.generators import Sine
        with tempfile.TemporaryDirectory() as tmp:
            raw = io.BytesIO()
            Sine(440).to_audio_segment(duration=500).export(raw, format='mp3')
            result = m.prepare_audio(raw.getvalue(), Path(tmp), 'tone')
            self.assertEqual((Path(tmp) / result['raw_file']).read_bytes(), raw.getvalue())
            self.assertEqual(result['raw_sha256'], m.digest(raw.getvalue()))
            self.assertTrue((Path(tmp) / result['listen_file']).is_file())

    def test_http_failures_never_read_provider_error_bodies(self):
        response = Response(payload={'error': 'secret-eleven'})
        response.status_code = 403
        client = Mock()
        client.post.return_value = response
        with self.assertRaisesRegex(m.ComparisonError, 'ProviderHTTP403'):
            m.synthesize(client, ('url', {}, {}))
        self.assertTrue(response.closed)

    def test_process_keys_override_explicit_file_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'OPENROUTER_API_KEY': 'process-router'}, clear=True):
            path = Path(tmp) / '.env'
            original = 'ELEVENLABS_API_KEY=secret-eleven\nOPENROUTER_API_KEY=file-router\n'
            path.write_text(original)
            self.assertEqual(m.load_credentials(path)['OPENROUTER_API_KEY'], 'process-router')
            self.assertEqual(path.read_text(), original)

    def test_stream_size_limit(self):
        response, client = Response(chunks=(b'ID3' + b'x' * m.MAX_BYTES,)), Mock()
        client.post.return_value = response
        with self.assertRaisesRegex(m.ComparisonError, 'AudioSizeExceeded'):
            m.synthesize(client, ('url', {}, {}))
        self.assertTrue(response.closed)

    def test_hosted_trial_config_is_refused_read_only(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            path = Path(tmp) / '.env'
            original = 'PUBLIC_DEMO=true\nELEVENLABS_API_KEY=secret-eleven\nOPENROUTER_API_KEY=secret-router\n'
            path.write_text(original)
            with self.assertRaises(m.ComparisonError): m.load_credentials(path)
            self.assertEqual(path.read_text(), original)


if __name__ == '__main__': unittest.main()
