"""Sound preparation keeps pilots bounded and never substitutes letter names."""
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
SPEC = importlib.util.spec_from_file_location('prepare_alphabet_sounds', ROOT / 'scripts/prepare_alphabet_sounds.py')
command = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command)


class AlphabetSoundCatalogueTests(unittest.TestCase):
    def test_sound_catalogue_has_representative_ipa_and_excludes_silent_signs(self):
        clips = command.load_clips()
        self.assertEqual(len(clips), 31)
        self.assertFalse({'hard-sign-sound.mp3', 'soft-sign-sound.mp3'} & set(clips))
        for filename, spec in clips.items():
            self.assertEqual(spec['kind'], 'sound')
            self.assertEqual(filename, spec['letter_id'] + '-sound.mp3')
        self.assertEqual(clips['be-sound.mp3']['ipa'], 'b')
        self.assertEqual(clips['ef-sound.mp3']['ipa'], 'f')
        self.assertEqual(clips['short-i-sound.mp3']['ipa'], 'j')
        self.assertEqual(clips['e-sound.mp3']['ipa'], 'ɛ')
        self.assertEqual(clips['shcha-sound.mp3']['ipa'], 'ɕː')
        self.assertEqual(clips['che-sound.mp3']['ipa'], 't͡ɕ')
        self.assertEqual(clips['ye-sound.mp3']['ipa'], 'je')

    def test_catalogue_requires_both_sound_voices_and_no_sound_for_signs(self):
        cases = [('a', 'soundAudio', None), ('a', 'soundAudio', {}),
                 ('a', 'soundAudio', {'female': '/static/audio/alphabet-v1/sounds/female/a-sound.mp3'}),
                 ('a', 'soundAudio', {'female': '/static/audio/alphabet-v1/a-name.mp3',
                                      'male': '/static/audio/alphabet-v1/male/a-name.mp3'}),
                 ('a', 'soundIpa', '/a/'), ('a', 'soundIpa', None),
                 ('hard-sign', 'soundIpa', 'a'), ('soft-sign', 'soundAudio', {})]
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / 'catalogue.json'
            for letter_id, field, value in cases:
                with self.subTest(letter=letter_id, field=field, value=value):
                    data = json.loads(command.DATA.read_text())
                    next(row for row in data if row['id'] == letter_id)[field] = value
                    content.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        command.load_clips(content)

    def test_pilots_accept_only_distinct_sounding_letter_ids(self):
        clips = command.load_clips()
        self.assertEqual(command.selection(clips, ' ef,be '), {'ef-sound.mp3', 'be-sound.mp3'})
        self.assertEqual(command.selection(clips), set(clips))
        for letters in ('', 'ef,ef', 'ef,', 'hard-sign', 'soft-sign', '../ef', 'unknown'):
            with self.subTest(letters=letters), self.assertRaises(ValueError):
                command.selection(clips, letters)

    def test_pilot_dry_run_and_missing_verification_never_read_keys_or_write(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(command, 'DIRECTORY', Path(directory)), \
                patch.object(command.audio, 'load_config', side_effect=AssertionError('No credentials in a dry run')), \
                patch.object(command, 'source_specs', return_value=command.load_clips()), \
                contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(command.main(['--voice', 'male', '--letters', 'ef,be']), 0)
            summary = json.loads(output.getvalue())
            self.assertEqual(summary['provider_calls'], 0)
            self.assertEqual(summary['selected'], 2)
            self.assertEqual(command.main(['--verify', '--letters', 'ef,be']), 1)
            self.assertEqual(list(Path(directory).iterdir()), [])


class AlphabetSoundPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stream = io.BytesIO()
        Sine(330).to_audio_segment(duration=350).apply_gain(-15).export(stream, format='mp3')
        cls.recording = stream.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / 'output'
        self.clips = {name: spec for name, spec in command.load_clips().items()
                      if name in ('a-sound.mp3', 'ef-sound.mp3')}
        self.recipes = {}
        for voice in command.VOICE_IDS:
            source_dir = self.root / command.SOURCE_PREFIX / ('male' if voice == 'male' else '')
            source_dir.mkdir(parents=True)
            records = {}
            for letter in ('a', 'ef'):
                source = source_dir / (letter + '-name.mp3')
                source.write_bytes(self.recording)
                spoken = 'а.' if letter == 'a' else 'эф.'
                records[source.name] = {'model': 'eleven_v4', 'voice_id': command.VOICE_IDS[voice],
                    'text': spoken, 'text_sha256': command.audio.digest(spoken.encode()),
                    **command.audio.audio_metadata(source)}
                self.recipes[voice + '-' + letter] = {'source': source.relative_to(self.root).as_posix(),
                    'source_sha256': command.audio.digest(self.recording), 'mode': 'copy' if letter == 'a' else 'crop',
                    'start_ms': None if letter == 'a' else 100, 'end_ms': None if letter == 'a' else 250,
                    'repetitions': 1, 'fade_in_ms': 0 if letter == 'a' else 2, 'fade_out_ms': 0 if letter == 'a' else 3}
            command.audio.save_manifest(source_dir, {'version': command.audio.VERSION, 'provider': 'elevenlabs',
                'model': 'eleven_v4', 'voice': voice, 'voice_id': command.VOICE_IDS[voice],
                'voice_settings': command.audio.SETTINGS, 'clips': records})
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def specs(self, voice='female'):
        return command.source_specs(self.clips, self.recipes, voice, self.root)

    def prepare(self, voice='female', **kwargs):
        return command.prepare(self.directory / voice, self.specs(voice), voice=voice, source_dir=self.root, **kwargs)

    def test_vowels_copy_exact_bytes_and_consonants_keep_source_provenance(self):
        before = {path: path.read_bytes() for path in (self.root / command.SOURCE_PREFIX).rglob('*') if path.is_file()}
        saved = self.prepare()
        self.assertEqual((self.directory / 'female/a-sound.mp3').read_bytes(), self.recording)
        self.assertNotEqual((self.directory / 'female/ef-sound.mp3').read_bytes(), self.recording)
        self.assertEqual(saved['clips']['ef-sound.mp3']['source_generation']['text'], 'эф.')
        self.assertEqual(saved['clips']['ef-sound.mp3']['ipa'], 'f')
        self.assertEqual(saved['clips']['ef-sound.mp3']['duration_ms'], 310)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(command.plan(self.directory / 'female', self.specs(), 'female')[1], [])

    def test_subset_resume_reuses_verified_outputs_without_touching_the_manifest(self):
        self.prepare(selected={'a-sound.mp3'}, max_new=1)
        original = (self.directory / 'female/a-sound.mp3').read_bytes()
        self.prepare(selected={'ef-sound.mp3'}, max_new=1)
        before = (self.directory / 'female/manifest.json').read_bytes()
        with patch.object(command, 'render', side_effect=AssertionError('Verified clips cannot be rendered again')):
            self.prepare(max_new=0)
        self.assertEqual((self.directory / 'female/a-sound.mp3').read_bytes(), original)
        self.assertEqual((self.directory / 'female/manifest.json').read_bytes(), before)

    def test_voices_have_distinct_pinned_provenance_and_separate_outputs(self):
        female = self.prepare()
        male = self.prepare('male')
        self.assertEqual(female['voice_id'], command.VOICE_IDS['female'])
        self.assertEqual(male['voice_id'], command.VOICE_IDS['male'])
        self.assertTrue(male['clips']['ef-sound.mp3']['recipe']['source'].endswith('/male/ef-name.mp3'))
        with self.assertRaises(ValueError):
            command.plan(self.directory / 'female', self.specs('male'), 'male')

    def test_changed_sources_and_excessive_batches_fail_before_output_writes(self):
        with self.assertRaisesRegex(ValueError, 'recording limit'):
            self.prepare(max_new=1)
        source = self.root / self.recipes['female-ef']['source']
        source.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.prepare()
        self.assertFalse(self.directory.exists())

    def test_recipe_changes_or_output_tampering_cannot_be_silently_rebuilt(self):
        self.prepare()
        self.recipes['female-ef']['end_ms'] = 240
        with self.assertRaisesRegex(ValueError, 'recipe changed'):
            self.prepare()
        self.recipes['female-ef']['end_ms'] = 250
        (self.directory / 'female/a-sound.mp3').write_bytes(b'broken')
        with self.assertRaises(Exception):
            self.prepare()

    def test_short_clip_plays_once_with_only_edge_padding(self):
        recipe = self.recipes['female-ef']
        recipe.update(start_ms=100, end_ms=114, repetitions=1, fade_in_ms=.5, fade_out_ms=.2)
        saved = self.prepare(selected={'ef-sound.mp3'})
        self.assertEqual(saved['clips']['ef-sound.mp3']['duration_ms'], 14 + 60 + 100)
        recording = AudioSegment.from_file(self.directory / 'female/ef-sound.mp3')
        self.assertGreater(recording[60:74].dBFS, -40)
        self.assertLess(recording[100:].dBFS, -50)

    def test_renderer_rejects_repetitions_even_when_recipe_validation_is_bypassed(self):
        destination = self.root / 'existing-output.mp3'
        destination.write_bytes(b'preserve this output')
        for letter in ('a', 'ef'):
            recipe = {**self.recipes['female-' + letter], 'repetitions': 3}
            with self.subTest(mode=recipe['mode']), self.assertRaisesRegex(ValueError, 'without repeats'):
                command.render(self.root / recipe['source'], destination, recipe)
            self.assertEqual(destination.read_bytes(), b'preserve this output')

    def test_quiet_clips_receive_at_most_three_decibels_of_gain(self):
        source = self.root / 'quiet-source.mp3'
        destination = self.root / 'quiet-output.mp3'
        with Sine(330).to_audio_segment(duration=350).apply_gain(-40).export(source, format='mp3'):
            pass
        original = AudioSegment.from_file(source)[100:250]
        result = command.render(source, destination, self.recipes['female-ef'])
        rendered = AudioSegment.from_file(destination)
        self.assertEqual(len(rendered), 150 + 60 + 100)
        self.assertEqual(result['gain_db'], 3)
        # Measure the encoded result too: a quiet source must remain quiet,
        # rather than being amplified to the general -20 dBFS target.
        observed_gain = rendered[60:210].dBFS - original.dBFS
        self.assertGreater(observed_gain, 1.5)
        self.assertLessEqual(observed_gain, 3.25)
        self.assertLess(rendered[60:210].dBFS, -35)

    def test_authored_recipe_rejects_traversal_wrong_voice_and_invalid_intervals(self):
        path = self.root / 'recipes.json'
        pristine = json.loads(json.dumps(self.recipes))
        cases = [('source', '../outside.mp3'), ('source', command.SOURCE_PREFIX + 'male/ef-name.mp3'),
                 ('end_ms', 99), ('start_ms', -1), ('repetitions', 2), ('repetitions', 3), ('fade_out_ms', 200)]
        for field, value in cases:
            recipes = json.loads(json.dumps(pristine))
            recipes['female-ef'][field] = value
            path.write_text(json.dumps({'version': command.RECIPE_VERSION, 'processing': command.PROCESSING, 'clips': recipes}))
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                command.load_recipes(path, self.clips)

    def test_additional_recorded_source_requires_matching_request_and_hash(self):
        source = self.root / command.RECORDED_PREFIX / 'female-ef.mp3'
        source.parent.mkdir(parents=True)
        source.write_bytes(self.recording)
        provenance = {'payload': {'text': 'фффф', 'model_id': 'eleven_v4', 'language_code': 'ru',
                                   'voice_settings': command.audio.SETTINGS},
                      'voice_id': command.VOICE_IDS['female'], 'sha256': command.audio.digest(self.recording), 'duration_ms': 350}
        source.with_suffix('.json').write_text(json.dumps(provenance))
        self.recipes['female-ef']['source'] = source.relative_to(self.root).as_posix()
        self.assertEqual(self.specs()['ef-sound.mp3']['source_generation']['request']['text'], 'фффф')
        provenance['voice_id'] = command.VOICE_IDS['male']
        source.with_suffix('.json').write_text(json.dumps(provenance))
        with self.assertRaisesRegex(ValueError, 'request provenance'):
            self.specs()

    def test_copying_a_consonant_name_cannot_masquerade_as_its_sound(self):
        recipe = self.recipes['female-ef']
        recipe.update(mode='copy', start_ms=None, end_ms=None, repetitions=1, fade_in_ms=0, fade_out_ms=0)
        path = self.root / 'recipes.json'
        path.write_text(json.dumps({'version': command.RECIPE_VERSION, 'processing': command.PROCESSING, 'clips': self.recipes}))
        with self.assertRaisesRegex(ValueError, 'Copied vowel recordings'):
            command.load_recipes(path, self.clips)


if __name__ == '__main__':
    unittest.main()
