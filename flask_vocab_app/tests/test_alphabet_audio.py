"""Alphabet preparation is bounded, immutable, and disconnected from playback."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydub import AudioSegment
from pydub.generators import Sine


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('prepare_alphabet_audio', ROOT / 'scripts/prepare_alphabet_audio.py')
command = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command)


class AlphabetCatalogueTests(unittest.TestCase):
    def test_all_letters_have_their_correct_kind_name_and_distinct_audio(self):
        data = json.loads(command.DATA.read_text())
        self.assertEqual(''.join(row['upper'] for row in data), 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ')
        self.assertEqual([sum(row['kind'] == kind for row in data) for kind in ('vowel', 'consonant', 'sign')], [10, 21, 2])
        rows = {row['upper']: row for row in data}
        self.assertEqual(rows['Й']['name'], 'и кра́ткое')
        self.assertEqual(rows['Й']['kind'], 'consonant')
        self.assertIn('no exact english equivalent', rows['Ы']['note'].lower())
        for letter in 'ЪЬ':
            self.assertIsNone(rows[letter]['soundIpa'])
            self.assertIsNone(rows[letter]['soundAudio'])
        for row in data:
            self.assertIn(row['lower'], row['example'].lower())
            vowels = sum(char in 'аеёиоуыэюя' for char in row['example'])
            self.assertTrue(vowels == 1 or '\u0301' in row['example'] or 'ё' in row['example'])
        clips = command.load_clips()
        self.assertEqual(len(clips), 66)
        self.assertEqual(clips['zhe-name.mp3']['text'], 'жэ.')
        self.assertEqual(clips['tse-name.mp3']['text'], 'цэ.')
        self.assertEqual(clips['be-word.mp3']['display_text'], 'бана́н')
        self.assertEqual(clips['be-word.mp3']['text'], 'банан.')
        self.assertEqual(command.load_clips(voice='male'), clips)
        self.assertEqual(len({url for row in data for field in ('nameAudio', 'exampleAudio') for url in row[field].values()}), 132)

    def test_voice_matrices_reject_missing_unknown_or_misdirected_recordings(self):
        source = json.loads(command.DATA.read_text())
        broken = [
            '/static/audio/alphabet-v1/a-name.mp3',
            {'female': '/static/audio/alphabet-v1/a-name.mp3'},
            {**source[0]['nameAudio'], 'other': '/static/audio/alphabet-v1/a-name.mp3'},
            {**source[0]['nameAudio'], 'male': source[0]['nameAudio']['female']},
            {**source[0]['nameAudio'], 'male': '/static/audio/alphabet-v1/male/../a-name.mp3'},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalogue.json'
            for matrix in broken:
                with self.subTest(matrix=matrix):
                    data = json.loads(command.DATA.read_text())
                    data[0]['nameAudio'] = matrix
                    path.write_text(json.dumps(data))
                    for voice in ('female', 'male'):
                        with self.assertRaises(ValueError):
                            command.load_clips(path, voice=voice)

    def test_dry_run_needs_no_credentials_and_performs_no_writes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(command, 'DIRECTORY', Path(directory)), \
                patch.object(command, 'load_config', side_effect=AssertionError('Dry runs cannot read keys')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(command.main([]), 0)
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(json.loads(output.getvalue())['provider_calls'], 0)


class AlphabetPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stream = io.BytesIO()
        (AudioSegment.silent(duration=350) + Sine(330).to_audio_segment(duration=450).apply_gain(-15)
         + AudioSegment.silent(duration=450)).export(stream, format='mp3')
        cls.recording = stream.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / 'alphabet'
        self.clips = dict(list(command.load_clips().items())[:3])
        self.config = {'ELEVENLABS_API_KEY': 'test-only', 'ELEVENLABS_MODEL': 'eleven_v4',
                       'ELEVENLABS_VOICE_IDS': ('one', 'two')}
        self.calls, self.fail = [], set()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def provider(self, key, directory, *, voice_ids, model, config):
        self.assertEqual(key, 'test-only')
        self.assertEqual(model, 'eleven_v4')
        test = self
        class Provider:
            def generate_audio(self, text, filename):
                saved = json.loads((Path(directory).parent / 'manifest.json').read_text())
                test.assertEqual(saved['voice_id'], voice_ids[0])
                test.assertEqual(saved['clips'][filename]['text'], text)
                test.calls.append((text, voice_ids[0]))
                if filename in test.fail:
                    raise ValueError('Private provider body')
                (Path(directory) / filename).write_bytes(test.recording)
                return filename
        return Provider()

    def prepare(self, **kwargs):
        return command.prepare(self.directory, self.clips, self.config, service_factory=self.provider,
                               **{'voice_id': 'two', **kwargs})

    def test_explicit_voice_is_saved_once_and_completed_clips_are_reused(self):
        saved = self.prepare()
        self.assertEqual({voice for _, voice in self.calls}, {'two'})
        self.assertEqual(len(self.calls), 3)
        before = (self.directory / 'manifest.json').read_bytes()
        self.config['ELEVENLABS_VOICE_IDS'] = ('other',)
        self.assertEqual(self.prepare(), saved)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual((self.directory / 'manifest.json').read_bytes(), before)

    def test_padding_trim_keeps_signal_and_records_verifiable_duration(self):
        saved = self.prepare()
        for filename, record in saved['clips'].items():
            self.assertGreater(record['trimmed_leading_ms'], 200)
            self.assertGreater(record['trimmed_trailing_ms'], 300)
            self.assertLessEqual(record['leading_silence_ms'], 100)
            self.assertLessEqual(record['trailing_silence_ms'], 100)
            self.assertGreater(record['duration_ms'], 550)
        self.assertEqual(command.plan(self.directory, self.clips)[1], [])

    def test_failure_saves_siblings_and_retry_preserves_voice_and_budget(self):
        self.fail = {'a-name.mp3'}
        with self.assertRaisesRegex(ValueError, 'completed clips are preserved'):
            self.prepare(workers=2)
        self.assertEqual(len(self.calls), 2)
        saved = json.loads((self.directory / 'manifest.json').read_text())
        selected = saved['voice_id']
        self.assertTrue((self.directory / 'a-word.mp3').is_file())
        self.assertFalse((self.directory / 'a-name.mp3').exists())
        self.assertNotIn('Private provider body', (self.directory / 'manifest.json').read_text())
        self.fail.clear()
        saved = self.prepare(workers=2, voice_id=None)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual({voice for _, voice in self.calls}, {selected})
        self.assertEqual(saved['clips']['a-name.mp3']['attempts'], 2)

    def test_new_voice_sets_require_a_configured_explicit_voice_before_writes(self):
        for voice in ('female', 'male'):
            for voice_id in (None, 'unconfigured', '../unsafe'):
                with self.subTest(voice=voice, voice_id=voice_id), self.assertRaises(ValueError):
                    self.prepare(voice=voice, voice_id=voice_id)
                self.assertFalse(self.directory.exists())
                self.assertEqual(self.calls, [])

    def test_a_conflicting_voice_override_cannot_relabel_a_saved_set(self):
        self.prepare()
        before = (self.directory / 'manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'saved recording voice cannot change'):
            self.prepare(voice_id='one')
        self.assertEqual(len(self.calls), 3)
        self.assertEqual((self.directory / 'manifest.json').read_bytes(), before)

    def test_male_generation_preserves_legacy_female_bytes_and_uses_a_separate_manifest(self):
        female = self.prepare()
        female.pop('voice')  # The shipped female manifest predates voice labels.
        command.save_manifest(self.directory, female)
        before = {path.name: path.read_bytes() for path in self.directory.iterdir() if path.is_file()}
        male_directory = self.directory / 'male'
        male = command.prepare(male_directory, self.clips, self.config, voice='male', voice_id='one', service_factory=self.provider)
        self.assertEqual({path.name: path.read_bytes() for path in self.directory.iterdir() if path.is_file()}, before)
        self.assertEqual(male['voice_id'], 'one')
        self.assertEqual(male['voice'], 'male')
        self.assertEqual(command.plan(self.directory, self.clips)[1], [])
        self.assertEqual(command.plan(male_directory, self.clips, voice='male')[1], [])
        self.assertEqual(len(self.calls), 6)
        with self.assertRaisesRegex(ValueError, 'manifest does not match'):
            command.plan(self.directory, self.clips, voice='male')

    def test_changed_bytes_or_text_cannot_be_silently_regenerated(self):
        self.prepare()
        original = dict(self.clips['a-name.mp3'])
        self.clips['a-name.mp3']['text'] = 'Другой текст.'
        with self.assertRaisesRegex(ValueError, 'speech changed'):
            self.prepare()
        self.clips['a-name.mp3'] = original
        (self.directory / 'a-name.mp3').write_bytes(b'not-mp3')
        with self.assertRaises(Exception):
            self.prepare()
        self.assertEqual(len(self.calls), 3)

    def test_bounds_reject_calls_before_writes(self):
        with self.assertRaisesRegex(ValueError, 'recording limits'):
            self.prepare(max_new=2)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
