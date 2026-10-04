"""Pronunciation examples preserve whole syllables and require audible speech."""
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
            self.assertEqual(filename, spec['letter_id'] + '-sound.mp3')
        self.assertEqual(sum(spec['kind'] == 'syllable' for spec in clips.values()), 12)
        self.assertEqual(sum(spec['kind'] == 'sound' for spec in clips.values()), 19)
        self.assertEqual(clips['be-sound.mp3']['display_text'], 'ба')
        self.assertEqual(clips['be-sound.mp3']['ipa'], 'ba')
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

    def test_female_en_preserves_the_entire_syllable_without_changing_male_en(self):
        clips = command.load_clips()
        recipes = command.load_recipes(clips=clips)
        female = command.for_voice(clips['en-sound.mp3'], 'female')
        male = command.for_voice(clips['en-sound.mp3'], 'male')
        self.assertEqual((female['kind'], female['display_text'], female['ipa']), ('syllable', 'на', 'na'))
        self.assertEqual((male['kind'], male['display_text'], male['ipa']), ('sound', 'н', 'n'))
        recipe = recipes['female-en']
        self.assertEqual(recipe['mode'], 'copy')
        self.assertIsNone(recipe['start_ms'])
        self.assertIsNone(recipe['end_ms'])
        source = command.ROOT / recipe['source']
        packaged = command.DIRECTORY / 'female/en-sound.mp3'
        self.assertEqual(packaged.read_bytes(), source.read_bytes())
        self.assertEqual(len(AudioSegment.from_file(packaged)), 720)
        self.assertEqual(recipes['male-en']['mode'], 'crop')
        self.assertEqual(recipes['male-en']['end_ms'] - recipes['male-en']['start_ms'], 150)

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


class AlphabetSpeechDurationTests(unittest.TestCase):
    def test_per_letter_duration_exceptions_do_not_count_external_silence(self):
        targets = {**dict.fromkeys(('ve', 'en', 'tse', 'short-i', 'zhe'), 150),
                   **dict.fromkeys(('o', 'shcha', 'ef', 'che', 'pe'), 130), 'sha': 110}
        silence = AudioSegment.silent(duration=500, frame_rate=48000)
        for letter_id, duration in targets.items():
            tone = Sine(330, sample_rate=48000).to_audio_segment(duration=duration).apply_gain(-15)
            with self.subTest(letter_id=letter_id):
                self.assertEqual(command.require_speech(tone, letter_id=letter_id), duration)
                with self.assertRaisesRegex(ValueError, f'{duration} ms'):
                    command.require_speech(silence + tone[:duration - 1] + silence, letter_id=letter_id)
        tone = Sine(330).to_audio_segment(duration=130).apply_gain(-15)
        for letter_id in set(item['letter_id'] for item in command.load_clips().values()) - set(targets):
            with self.subTest(letter_id=letter_id), self.assertRaisesRegex(ValueError, '160 ms'):
                command.require_speech(tone, letter_id=letter_id)

    def test_exactly_160_ms_of_signal_passes_but_159_does_not(self):
        tone = Sine(330).to_audio_segment(duration=160).apply_gain(-15)
        self.assertEqual(command.require_speech(tone), 160)
        with self.assertRaisesRegex(ValueError, '160 ms'):
            command.require_speech(tone[:159])

    def test_selected_consonants_preserve_internal_quiet_without_counting_padding(self):
        for letter_id, duration, quiet_ms in (('che', 130, 5), ('en', 150, 3), ('tse', 150, 12)):
            tone = Sine(330, sample_rate=48000).to_audio_segment(duration=duration).apply_gain(-15)
            silence = AudioSegment.silent(duration=quiet_ms, frame_rate=48000)
            release = tone[:5] + silence + tone[5 + quiet_ms:]
            with self.subTest(letter_id=letter_id):
                self.assertEqual(command.require_speech(release, letter_id=letter_id), duration - quiet_ms)
                with self.assertRaisesRegex(ValueError, f'{duration} ms'):
                    command.require_speech(release, letter_id='ef' if duration == 130 else 've')
                for padded in (silence + tone[:duration - quiet_ms], tone[:duration - quiet_ms] + silence):
                    with self.assertRaisesRegex(ValueError, f'{duration} ms'):
                        command.require_speech(padded, letter_id=letter_id)

    def test_external_padding_cannot_round_159_ms_up_to_the_minimum(self):
        for leading_ms in (500, 503):
            for speech_ms in (159, 160):
                recording = (AudioSegment.silent(duration=leading_ms, frame_rate=44100)
                             + Sine(330).to_audio_segment(duration=speech_ms).apply_gain(-15)
                             + AudioSegment.silent(duration=500, frame_rate=44100))
                with self.subTest(leading_ms=leading_ms, speech_ms=speech_ms):
                    if speech_ms == 159:
                        with self.assertRaisesRegex(ValueError, '160 ms'):
                            command.require_speech(recording)
                    else:
                        self.assertEqual(command.require_speech(recording), 160)

    def test_silence_quiet_signal_and_a_long_file_with_a_tiny_burst_do_not_count(self):
        silence = AudioSegment.silent(duration=1000, frame_rate=44100)
        burst = Sine(330).to_audio_segment(duration=20).apply_gain(-15)
        quiet = Sine(330).to_audio_segment(duration=1000).apply_gain(-50)
        for recording in (silence, quiet, silence + burst + silence):
            with self.subTest(duration=len(recording), level=recording.dBFS), self.assertRaisesRegex(ValueError, 'silence does not count'):
                command.require_speech(recording)


class AlphabetSoundPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recordings = {}
        for name, frequency in (('name', 330), ('syllable', 550)):
            stream = io.BytesIO()
            Sine(frequency).to_audio_segment(duration=350).apply_gain(-15).export(stream, format='mp3')
            cls.recordings[name] = stream.getvalue()
        cls.recording = cls.recordings['name']
        cls.syllable_recording = cls.recordings['syllable']

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / 'output'
        self.clips = {name: spec for name, spec in command.load_clips().items()
                      if name in ('a-sound.mp3', 'ef-sound.mp3')}
        # Keep a complete syllable fixture to exercise unchanged-copy safeguards.
        self.clips['ef-sound.mp3'].update(kind='syllable', ipa='fa', display_text='фа')
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
                    'audio_sha256': command.audio.digest(self.recording), 'duration_ms': 350}
                self.recipes[voice + '-' + letter] = {'source': source.relative_to(self.root).as_posix(),
                    'source_sha256': command.audio.digest(self.recording), 'mode': 'copy',
                    'start_ms': None, 'end_ms': None, 'repetitions': 1, 'fade_in_ms': 0, 'fade_out_ms': 0}
            command.audio.save_manifest(source_dir, {'version': command.audio.VERSION, 'provider': 'elevenlabs',
                'model': 'eleven_v4', 'voice': voice, 'voice_id': command.VOICE_IDS[voice],
                'voice_settings': command.audio.SETTINGS, 'clips': records})
            self.write_syllable(voice, self.syllable_recording, 350)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def write_syllable(self, voice, recording, duration):
        source = self.root / command.RECORDED_PREFIX / (voice + '-ef.mp3')
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(recording)
        provenance = {'payload': {'text': 'фа.', 'model_id': 'eleven_v4', 'language_code': 'ru',
                                  'voice_settings': command.audio.SETTINGS},
                      'voice_id': command.VOICE_IDS[voice], 'sha256': command.audio.digest(recording),
                      'duration_ms': duration}
        source.with_suffix('.json').write_text(json.dumps(provenance))
        self.recipes[voice + '-ef'].update(source=source.relative_to(self.root).as_posix(),
                                         source_sha256=command.audio.digest(recording))
        return source

    def specs(self, voice='female'):
        return command.source_specs(self.clips, self.recipes, voice, self.root)

    def prepare(self, voice='female', **kwargs):
        return command.prepare(self.directory / voice, self.specs(voice), voice=voice, source_dir=self.root, **kwargs)

    def isolated_recipe(self, **changes):
        recipe = {**self.recipes['female-ef'], 'source': command.SOURCE_PREFIX + 'ef-name.mp3',
                  'source_sha256': command.audio.digest(self.recording), 'mode': 'crop',
                  'start_ms': 100, 'end_ms': 280, 'fade_in_ms': 2, 'fade_out_ms': 3}
        return {**recipe, **changes}

    def load_recipes(self, recipes=None, clips=None):
        path = self.root / 'recipes.json'
        path.write_text(json.dumps({'version': command.RECIPE_VERSION, 'processing': command.PROCESSING,
                                    'clips': self.recipes if recipes is None else recipes}))
        return command.load_recipes(path, self.clips if clips is None else clips)

    def test_vowels_and_whole_syllables_copy_exact_bytes_with_correct_provenance(self):
        before = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.load_recipes()
        saved = self.prepare()
        self.assertEqual((self.directory / 'female/a-sound.mp3').read_bytes(), self.recording)
        self.assertEqual((self.directory / 'female/ef-sound.mp3').read_bytes(), self.syllable_recording)
        self.assertNotEqual((self.directory / 'female/ef-sound.mp3').read_bytes(), self.recording)
        record = saved['clips']['ef-sound.mp3']
        self.assertEqual(record['source_generation']['text'], 'фа.')
        self.assertEqual(record['kind'], 'syllable')
        self.assertEqual(record['ipa'], 'fa')
        self.assertEqual(record['duration_ms'], 350)
        self.assertEqual(record['source_active_ms'], 350)
        self.assertEqual(record['gain_db'], 0)
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
        self.assertTrue(male['clips']['ef-sound.mp3']['recipe']['source'].endswith('/male-ef.mp3'))
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
        self.recipes['female-ef']['end_ms'] = None
        (self.directory / 'female/a-sound.mp3').write_bytes(b'broken')
        with self.assertRaises(Exception):
            self.prepare()

    def test_an_isolated_160_ms_clip_plays_once_with_only_edge_padding(self):
        recipe = self.isolated_recipe(end_ms=260)
        clips = {**self.clips, 'ef-sound.mp3': {**self.clips['ef-sound.mp3'], 'kind': 'sound', 'ipa': 'f', 'display_text': 'ф'}}
        self.load_recipes({**self.recipes, 'female-ef': recipe,
                           'male-ef': self.isolated_recipe(source=command.SOURCE_PREFIX + 'male/ef-name.mp3')}, clips)
        destination = self.root / 'isolated-output.mp3'
        result = command.render(self.root / recipe['source'], destination, recipe)
        recording = AudioSegment.from_file(destination)
        self.assertEqual(len(recording), 160 + 60 + 100)
        self.assertEqual(result['source_active_ms'], 160)
        self.assertGreater(recording[60:220].dBFS, -40)
        self.assertLess(recording[245:].dBFS, -50)

    def test_under_160_ms_crops_are_rejected_by_loading_and_direct_render(self):
        destination = self.root / 'untouched-output.mp3'
        destination.write_bytes(b'keep existing recording')
        for duration in (14, 159):
            recipe = self.isolated_recipe(source=command.SOURCE_PREFIX + 'a-name.mp3', end_ms=100 + duration)
            with self.subTest(duration=duration):
                with self.assertRaisesRegex(ValueError, '160 ms'):
                    self.load_recipes({**self.recipes, 'female-a': recipe})
                with self.assertRaisesRegex(ValueError, '160 ms'):
                    command.render(self.root / recipe['source'], destination, recipe)
                self.assertEqual(destination.read_bytes(), b'keep existing recording')

    def test_ef_130_ms_crop_passes_loading_and_render_but_129_ms_is_rejected(self):
        clips = {**self.clips, 'ef-sound.mp3': {**self.clips['ef-sound.mp3'], 'kind': 'sound', 'ipa': 'f', 'display_text': 'ф'}}
        recipe = self.isolated_recipe(end_ms=230)
        male = self.isolated_recipe(source=command.SOURCE_PREFIX + 'male/ef-name.mp3', end_ms=230)
        self.load_recipes({**self.recipes, 'female-ef': recipe, 'male-ef': male}, clips)
        destination = self.root / 'isolated-output.mp3'
        result = command.render(self.root / recipe['source'], destination, recipe, letter_id='ef')
        self.assertEqual(result['source_active_ms'], 130)
        self.assertEqual(len(AudioSegment.from_file(destination)), 130 + 60 + 100)
        before = destination.read_bytes()
        shorter = {**recipe, 'end_ms': 229}
        with self.assertRaisesRegex(ValueError, '130 ms'):
            self.load_recipes({**self.recipes, 'female-ef': shorter, 'male-ef': male}, clips)
        with self.assertRaisesRegex(ValueError, '130 ms'):
            command.render(self.root / recipe['source'], destination, shorter, letter_id='ef')
        self.assertEqual(destination.read_bytes(), before)

    def test_a_long_file_with_a_tiny_burst_cannot_pass_copy_or_crop_guards(self):
        segment = (AudioSegment.silent(duration=500, frame_rate=44100)
                   + Sine(330).to_audio_segment(duration=20).apply_gain(-15)
                   + AudioSegment.silent(duration=500, frame_rate=44100))
        stream = io.BytesIO()
        segment.export(stream, format='mp3')
        source = self.write_syllable('female', stream.getvalue(), len(segment))
        with self.assertRaisesRegex(ValueError, 'audible source speech'):
            self.specs()
        destination = self.root / 'output-must-not-exist.mp3'
        for mode in ('copy', 'crop'):
            recipe = {**self.recipes['female-ef'], 'mode': mode}
            if mode == 'crop':
                recipe.update(start_ms=0, end_ms=len(segment))
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'audible source speech'):
                command.render(source, destination, recipe)
            self.assertFalse(destination.exists())
        self.assertFalse(self.directory.exists())

    def test_renderer_rejects_repetitions_even_when_recipe_validation_is_bypassed(self):
        destination = self.root / 'existing-output.mp3'
        destination.write_bytes(b'preserve this output')
        for recipe in (self.recipes['female-ef'], self.isolated_recipe()):
            recipe = {**recipe, 'repetitions': 3}
            with self.subTest(mode=recipe['mode']), self.assertRaisesRegex(ValueError, 'without repeats'):
                command.render(self.root / recipe['source'], destination, recipe)
            self.assertEqual(destination.read_bytes(), b'preserve this output')

    def test_quiet_but_audible_clips_receive_at_most_three_decibels_of_gain(self):
        source = self.root / 'quiet-source.mp3'
        destination = self.root / 'quiet-output.mp3'
        with Sine(330).to_audio_segment(duration=350).apply_gain(-35).export(source, format='mp3'):
            pass
        original = AudioSegment.from_file(source)[100:280]
        result = command.render(source, destination, self.isolated_recipe())
        rendered = AudioSegment.from_file(destination)
        # MP3 decoding can round the container duration by one millisecond;
        # the source activity threshold above remains exact.
        self.assertAlmostEqual(len(rendered), 180 + 60 + 100, delta=1)
        self.assertEqual(result['source_active_ms'], 180)
        self.assertEqual(result['gain_db'], 3)
        observed_gain = rendered[60:240].dBFS - original.dBFS
        self.assertGreater(observed_gain, 1.5)
        self.assertLessEqual(observed_gain, 3.25)
        self.assertLess(rendered[60:240].dBFS, -30)

    def test_authored_recipe_rejects_traversal_wrong_voice_repeats_and_syllable_edits(self):
        for field, value in [('source', '../outside.mp3'), ('source', command.RECORDED_PREFIX + 'male-ef.mp3'),
                             ('end_ms', 300), ('start_ms', 0), ('repetitions', 2), ('repetitions', 3), ('fade_out_ms', 1)]:
            recipes = {**self.recipes, 'female-ef': {**self.recipes['female-ef'], field: value}}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.load_recipes(recipes)
        with self.assertRaisesRegex(ValueError, 'syllables must remain whole'):
            self.load_recipes({**self.recipes, 'female-ef': self.isolated_recipe()})

    def test_syllable_source_requires_matching_text_voice_model_and_hash(self):
        source = self.root / self.recipes['female-ef']['source']
        path = source.with_suffix('.json')
        original = json.loads(path.read_text())
        self.assertEqual(self.specs()['ef-sound.mp3']['source_generation']['request']['text'], 'фа.')
        cases = [('voice_id', command.VOICE_IDS['male']), ('sha256', '0' * 64),
                 ('text', 'эф.'), ('model_id', 'eleven_multilingual_v2'), ('language_code', 'en')]
        for field, value in cases:
            provenance = json.loads(json.dumps(original))
            target = provenance if field in ('voice_id', 'sha256') else provenance['payload']
            target[field] = value
            path.write_text(json.dumps(provenance))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.specs()
        path.write_text(json.dumps(original))

    def test_a_glide_crop_retains_its_complete_source_request_provenance(self):
        source = self.root / command.RECORDED_PREFIX / 'female-short-i.mp3'
        source.write_bytes(self.syllable_recording)
        original_source = self.root / self.recipes['female-ef']['source']
        provenance = json.loads(original_source.with_suffix('.json').read_text())
        provenance['payload']['text'] = 'йо.'
        source.with_suffix('.json').write_text(json.dumps(provenance))
        recipe = {**self.recipes['female-ef'], 'source': source.relative_to(self.root).as_posix(),
                  'mode': 'crop', 'start_ms': 30, 'end_ms': 180}
        clips = {'short-i-sound.mp3': {'letter_id': 'short-i', 'kind': 'sound', 'ipa': 'j', 'display_text': 'й'}}
        specs = command.source_specs(clips, {'female-short-i': recipe}, 'female', self.root)
        self.assertEqual(specs['short-i-sound.mp3']['source_generation']['request']['text'], 'йо.')
        self.assertEqual(specs['short-i-sound.mp3']['ipa'], 'j')
        provenance['payload']['text'] = 'и.'
        source.with_suffix('.json').write_text(json.dumps(provenance))
        with self.assertRaisesRegex(ValueError, 'request provenance'):
            command.source_specs(clips, {'female-short-i': recipe}, 'female', self.root)

    def test_shortened_pe_retains_syllable_label_and_can_only_use_its_syllable_source(self):
        clips = {'pe-sound.mp3': command.load_clips()['pe-sound.mp3']}
        recipes = {voice + '-pe': {'source': command.RECORDED_PREFIX + voice + '-pe.mp3',
                    'source_sha256': 'a' * 64, 'mode': 'crop', 'start_ms': 90, 'end_ms': 220,
                    'repetitions': 1, 'fade_in_ms': 2, 'fade_out_ms': 3}
                   for voice in command.VOICE_IDS}
        self.assertEqual(clips['pe-sound.mp3']['display_text'], 'па')
        self.assertEqual(clips['pe-sound.mp3']['kind'], 'syllable')
        self.load_recipes(recipes, clips)
        recipes['female-pe']['source'] = command.SOURCE_PREFIX + 'pe-name.mp3'
        with self.assertRaises(ValueError):
            self.load_recipes(recipes, clips)

    def test_copying_a_consonant_name_cannot_masquerade_as_a_practice_syllable(self):
        recipe = {**self.recipes['female-ef'], 'source': command.SOURCE_PREFIX + 'ef-name.mp3'}
        with self.assertRaisesRegex(ValueError, 'explicitly labelled practice syllable'):
            self.load_recipes({**self.recipes, 'female-ef': recipe})


if __name__ == '__main__':
    unittest.main()
