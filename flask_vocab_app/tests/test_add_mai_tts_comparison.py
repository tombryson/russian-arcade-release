"""Offline checks that an extra comparison arm preserves paid recordings."""
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
base_spec = importlib.util.spec_from_file_location('compare_tts', SCRIPTS / 'compare_tts.py')
base = importlib.util.module_from_spec(base_spec)
base_spec.loader.exec_module(base)
spec = importlib.util.spec_from_file_location('add_mai_tts_under_test', SCRIPTS / 'add_mai_tts_comparison.py')
m = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'compare_tts': base}):
    spec.loader.exec_module(m)


class Response:
    status_code = 200
    headers = {'Content-Type': 'audio/mpeg'}

    def __init__(self, payload=None, chunks=(b'ID3new-recording',)):
        self.payload, self.chunks, self.closed = payload, chunks, False

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        return iter(self.chunks)

    def close(self):
        self.closed = True


class Client:
    def __init__(self, fail_on=None, rate='0.000022'):
        self.gets, self.posts, self.closed = [], [], False
        self.fail_on = fail_on
        self.responses = iter([
            Response({'data': [{'id': m.MODEL, 'supported_voices': [m.VOICE],
                                'pricing': {'prompt': rate}}]}),
            Response({'data': {'private_account_field': 'not-for-output'}}),
        ])

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return next(self.responses)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if len(self.posts) == self.fail_on:
            raise RuntimeError('secret-key and private provider response')
        return Response()

    def close(self):
        self.closed = True


def processed(raw, directory, stem):
    result = {'duration_ms': 1000}
    for kind in ('raw', 'listen'):
        name = stem + '.' + kind + '.mp3'
        data = raw if kind == 'raw' else raw + b'-normalized'
        (directory / name).write_bytes(data)
        result[kind + '_file'] = name
        result[kind + '_sha256'] = base.digest(data)
    return result


def fixture(directory):
    samples = [dict(s, sha256=base.digest(s['text'].encode())) for s in base.load_samples()]
    result = {'version': 'russian-tts-comparison-v1', 'state': 'complete', 'calls': 12,
              'samples': samples, 'budget': base.estimate(samples), 'results': [],
              'production_changed': False, 'independent_listening_completed': False}
    for sample in samples:
        for index, model in enumerate(base.MODELS):
            label = 'ABC'[index]
            result['results'].append({
                'sample_id': sample['id'], 'text_sha256': sample['sha256'],
                'model': model, 'voice': 'original-voice', 'blind_label': label,
                'state': 'complete', 'original_metadata': {'preserve': index},
                'audio': processed(b'ID3original-' + model.encode(), directory,
                                   sample['id'] + '-' + label),
            })
    base.save(directory / 'manifest.json', result)
    (directory / 'listen.html').write_bytes(b'<!doctype html>Original listening page')
    return result


class AddMAIComparisonTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.original = fixture(self.directory)
        self.before = {p.name: p.read_bytes() for p in self.directory.iterdir()}

    def test_append_adds_exactly_four_standard_calls_and_preserves_previous_recordings(self):
        client = Client()
        receipt = m.run(self.directory, 'secret-key', client=client, audio_processor=processed)
        self.assertEqual((receipt['state'], receipt['calls'], len(client.posts)), ('complete', 4, 4))
        self.assertTrue(client.closed)
        self.assertTrue(all(url.startswith('https://openrouter.ai/') for url, _ in client.gets + client.posts))
        for (url, kwargs), sample in zip(client.posts, self.original['samples']):
            self.assertEqual(url, 'https://openrouter.ai/api/v1/audio/speech')
            self.assertEqual(kwargs['json'], {'model': m.MODEL, 'input': sample['text'],
                                             'voice': m.VOICE, 'response_format': 'mp3'})
        combined = json.loads((self.directory / 'manifest.json').read_text())
        self.assertEqual(combined['results'][:12], self.original['results'])
        self.assertEqual(combined['samples'], self.original['samples'])
        self.assertEqual(combined['calls'], 16)
        self.assertEqual(combined['original_budget'], self.original['budget'])
        self.assertAlmostEqual(receipt['estimated_usd'], 768 * 22 / 1_000_000)
        self.assertIsNone(receipt['actual_charge_usd'])
        for filename, data in self.before.items():
            if filename.endswith('.mp3'):
                self.assertEqual((self.directory / filename).read_bytes(), data)
        self.assertEqual((self.directory / 'manifest.three-model.json').read_bytes(), self.before['manifest.json'])
        self.assertEqual((self.directory / 'listen.three-model.html').read_bytes(), self.before['listen.html'])
        self.assertEqual((self.directory / 'listen.html').read_text().count('<audio controls'), 16)
        for filename in ('manifest.json', 'mai-standard-extension.json'):
            content = (self.directory / filename).read_text()
            self.assertNotIn('secret-key', content)
            self.assertNotIn('private_account_field', content)
        replay = Client()
        with self.assertRaisesRegex(base.ComparisonError, 'ExtensionAlreadyAttempted'):
            m.run(self.directory, 'secret-key', client=replay, audio_processor=processed)
        self.assertEqual(replay.posts, [])

    def test_tampered_original_audio_is_rejected_before_network(self):
        original_audio = self.original['results'][0]['audio']['raw_file']
        (self.directory / original_audio).write_bytes(b'changed')
        client = Client()
        with self.assertRaisesRegex(base.ComparisonError, 'OriginalAudioMismatch'):
            m.run(self.directory, 'secret-key', client=client, audio_processor=processed)
        self.assertEqual((client.gets, client.posts), ([], []))

    def test_changed_passage_or_duplicate_original_row_is_rejected(self):
        for change in ('text', 'duplicate'):
            with self.subTest(change=change):
                altered = copy.deepcopy(self.original)
                if change == 'text':
                    altered['samples'][0]['text'] = 'Другой текст.'
                    altered['samples'][0]['sha256'] = base.digest('Другой текст.'.encode())
                else:
                    altered['results'][1] = copy.deepcopy(altered['results'][0])
                base.save(self.directory / 'manifest.json', altered)
                client = Client()
                with self.assertRaisesRegex(base.ComparisonError, 'OriginalComparisonMismatch'):
                    m.run(self.directory, 'secret-key', client=client, audio_processor=processed)
                self.assertEqual((client.gets, client.posts), ([], []))

    def test_mid_run_failure_keeps_original_manifest_page_and_blocks_replay(self):
        client = Client(fail_on=2)
        receipt = m.run(self.directory, 'secret-key', client=client, audio_processor=processed)
        self.assertEqual((receipt['state'], receipt['calls'], len(client.posts)), ('stopped', 2, 2))
        self.assertTrue(client.closed)
        self.assertEqual([r['state'] for r in receipt['results']], ['complete', 'failed'])
        self.assertEqual((self.directory / 'manifest.json').read_bytes(), self.before['manifest.json'])
        self.assertEqual((self.directory / 'listen.html').read_bytes(), self.before['listen.html'])
        self.assertEqual((self.directory / 'manifest.three-model.json').read_bytes(), self.before['manifest.json'])
        persisted = (self.directory / 'mai-standard-extension.json').read_text()
        self.assertNotIn('secret-key', persisted)
        self.assertNotIn('private provider response', persisted)
        self.assertTrue((self.directory / (self.original['samples'][0]['id'] + '-D.raw.mp3')).is_file())
        replay = Client()
        with self.assertRaisesRegex(base.ComparisonError, 'ExtensionAlreadyAttempted'):
            m.run(self.directory, 'secret-key', client=replay, audio_processor=processed)
        self.assertEqual(replay.posts, [])

    def test_catalogue_price_increase_stops_before_paid_work(self):
        client = Client(rate='0.000023')
        receipt = m.run(self.directory, 'secret-key', client=client, audio_processor=processed)
        self.assertEqual(receipt['error_code'], 'MAIStandardPriceExceedsEstimate')
        self.assertEqual((receipt['calls'], client.posts), (0, []))
        self.assertFalse((self.directory / 'mai-standard-extension.json').exists())
        self.assertEqual((self.directory / 'manifest.json').read_bytes(), self.before['manifest.json'])

    def test_failed_page_publication_restores_original_comparison(self):
        def broken_render(result, directory):
            (directory / 'listen.html').write_text('incomplete page')
            raise RuntimeError('render failure')
        with patch.object(base, 'render_html', side_effect=broken_render):
            receipt = m.run(self.directory, 'secret-key', client=Client(), audio_processor=processed)
        self.assertEqual((receipt['state'], receipt['calls']), ('stopped', 4))
        self.assertEqual((self.directory / 'manifest.json').read_bytes(), self.before['manifest.json'])
        self.assertEqual((self.directory / 'listen.html').read_bytes(), self.before['listen.html'])
        self.assertTrue(all(r['state'] == 'complete' for r in receipt['results']))

    def test_dry_run_does_not_read_credentials_or_run_provider_work(self):
        with patch.object(base, 'load_credentials', side_effect=AssertionError), \
                patch.object(m, 'run', side_effect=AssertionError), redirect_stdout(io.StringIO()) as output:
            status = m.main([str(self.directory), '--env-file', '/unreadable/.env'])
        self.assertEqual(status, 0)
        data = json.loads(output.getvalue())
        self.assertFalse(data['live'])
        self.assertEqual(data['maximum_new_calls'], 4)
        self.assertEqual(data['model'], m.MODEL)
        self.assertFalse((self.directory / 'mai-standard-extension.json').exists())


if __name__ == '__main__':
    unittest.main()
