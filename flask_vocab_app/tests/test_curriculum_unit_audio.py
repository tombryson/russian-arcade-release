"""Authored listening media is immutable, bounded and available without AI calls."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from services.speech_provider import audio_info


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'prepare_curriculum_unit_audio_command', ROOT / 'scripts/prepare_curriculum_unit_audio.py')
command = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command)
SOURCE = ROOT / 'flask_vocab_app/data/curriculum_units/location-destination-listening-v1.json'


class CurriculumUnitAudioCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / command.UNIT_ID
        self.source = json.loads(SOURCE.read_text())
        self.config = {'ELEVENLABS_API_KEY': 'test-key', 'ELEVENLABS_MODEL': 'existing-model',
                       'ELEVENLABS_VOICE_IDS': ['voice-one', 'voice-two']}
        self.provider = Mock()
        self.provider.speak.side_effect = lambda text, voice: text.encode()
        self.factory = Mock(return_value=self.provider)
        self.probe = Mock(return_value=8.25)
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def prepare(self, **kwargs):
        command.prepare_recordings(self.source, self.directory, self.config,
                                   self.factory, self.probe, **kwargs)

    def test_dry_run_does_not_create_files_or_construct_provider(self):
        self.prepare(dry_run=True)
        self.assertIn('3 new recordings;', self.output.getvalue())
        self.factory.assert_not_called()
        self.assertFalse(self.directory.exists())

    def test_explicit_budget_is_checked_before_provider_or_writes(self):
        with self.assertRaisesRegex(ValueError, 'limit exceeded'):
            self.prepare(max_new=2)
        self.factory.assert_not_called()
        self.assertFalse(self.directory.exists())

    def test_total_character_limit_is_checked_even_during_dry_run(self):
        self.source['items'][0]['transcript'] = 'А' * 751
        with self.assertRaisesRegex(ValueError, '750-character'):
            self.prepare(dry_run=True)
        self.factory.assert_not_called()

    def test_rerun_skips_identical_published_recordings_without_credentials(self):
        self.prepare()
        original = {path.name: path.read_bytes() for path in self.directory.iterdir()}
        self.assertEqual(self.provider.speak.call_count, 3)
        for call in self.provider.speak.call_args_list:
            self.assertIn(call.args[1], self.config['ELEVENLABS_VOICE_IDS'])
        self.config.clear()
        self.factory.reset_mock()
        self.prepare()
        self.factory.assert_not_called()
        self.assertEqual(original, {path.name: path.read_bytes() for path in self.directory.iterdir()})

    def test_changed_transcript_cannot_replace_published_recording(self):
        self.prepare()
        self.factory.reset_mock()
        self.source['items'][0]['transcript'] += ' Новый текст.'
        with self.assertRaisesRegex(ValueError, 'new content version'):
            self.prepare()
        self.factory.assert_not_called()

    def test_missing_or_tampered_recording_is_not_regenerated(self):
        self.prepare()
        path = self.directory / 'shop-now.mp3'
        path.write_bytes(b'changed')
        self.factory.reset_mock()
        with self.assertRaisesRegex(ValueError, 'differs from'):
            self.prepare()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'missing its published'):
            self.prepare()
        self.factory.assert_not_called()

    def test_untracked_file_is_not_overwritten(self):
        self.directory.mkdir()
        (self.directory / 'shop-now.mp3').write_bytes(b'orphan')
        with self.assertRaisesRegex(ValueError, 'untracked'):
            self.prepare()
        self.factory.assert_not_called()

    def test_failure_stops_paid_work_preserves_success_and_hides_provider_error(self):
        self.provider.speak.side_effect = [b'first', RuntimeError('Sensitive provider response')]
        with self.assertRaisesRegex(ValueError, 'Recording stopped') as error:
            self.prepare()
        self.assertNotIn('Sensitive', str(error.exception))
        self.assertEqual(self.provider.speak.call_count, 2)
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        self.assertEqual(set(manifest['clips']), {'shop-now'})
        self.assertEqual((self.directory / 'shop-now.mp3').read_bytes(), b'first')

    def test_duration_and_identity_metadata_cannot_change(self):
        self.prepare()
        path = self.directory / 'manifest.json'
        original = json.loads(path.read_text())
        for field, value in [('duration', 10), ('voice_id', ''), ('model', '')]:
            altered = copy.deepcopy(original)
            altered['clips']['shop-now'][field] = value
            path.write_text(json.dumps(altered))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'invalid recording metadata'):
                self.prepare()

    def test_new_pack_preserves_identity_and_cannot_reuse_another_packs_url(self):
        content_id = 'objects-recipients-listening-v1'
        self.source = json.loads((ROOT / 'flask_vocab_app/data/curriculum_units' / (content_id + '.json')).read_text())
        self.prepare()
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        self.assertEqual(manifest['content_id'], content_id)
        self.factory.reset_mock()
        self.source['items'][0]['audio_url'] = '/static/audio/course/curriculum/other/hand-over-envelope.mp3'
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.prepare()
        self.factory.assert_not_called()

    def test_pilot_has_its_own_explicit_two_clip_limit_and_media_paths(self):
        self.source = json.loads((ROOT / 'flask_vocab_app/data/assessment_pilot/a1-pilot-listening-v1.json').read_text())
        self.prepare()
        self.assertEqual(self.provider.speak.call_count, 2)
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        self.assertEqual(manifest['content_id'], command.PILOT_CONTENT_ID)
        self.assertEqual(set(manifest['clips']), {'a1-pilot-a-v1', 'a1-pilot-b-v1'})
        self.factory.reset_mock()
        self.source['items'].append(copy.deepcopy(self.source['items'][0]))
        with self.assertRaisesRegex(ValueError, 'exactly 2'):
            self.prepare()
        self.factory.assert_not_called()

    def test_unknown_source_and_path_like_ids_are_rejected_before_provider(self):
        for content_id in ('../outside', 'unapproved-listening-v1', None):
            self.source['id'] = content_id
            with self.subTest(content=content_id), self.assertRaisesRegex(ValueError, 'Unsupported'):
                self.prepare()
        self.factory.assert_not_called()


class CurriculumUnitPublishedAudioTests(unittest.TestCase):
    def test_three_authored_listening_messages_have_matching_playable_recordings(self):
        source = json.loads(SOURCE.read_text())
        directory = ROOT / 'flask_vocab_app/static/audio/course/curriculum' / command.UNIT_ID
        manifest, todo = command.plan_recordings(source, directory, audio_info)
        self.assertEqual(todo, [])
        self.assertEqual(len(manifest['clips']), 3)
        self.assertLessEqual(sum(len(item['transcript']) for item in source['items']), 750)
        for item in source['items']:
            with self.subTest(item=item['id']):
                self.assertEqual(item['requirement_id'], 'a1.listening.short-message')
                self.assertEqual(len(item['choices']), 3)
                self.assertIn(item['answer'], {choice['id'] for choice in item['choices']})
                self.assertGreater(manifest['clips'][item['id']]['duration'], 3)
                self.assertLess(manifest['clips'][item['id']]['duration'], 30)

    def test_every_exposed_unit_has_complete_immutable_playable_media(self):
        from services.curriculum_units import LISTENING_IDS
        for content_id in LISTENING_IDS.values():
            source_path, directory, count = command.content_layout(content_id)
            source = json.loads((ROOT / 'flask_vocab_app/data' / source_path).read_text())
            with self.subTest(content=content_id):
                manifest, todo = command.plan_recordings(
                    source, ROOT / 'flask_vocab_app/static/audio/course' / directory, audio_info)
                self.assertEqual(todo, [])
                self.assertEqual(len(manifest['clips']), count)


if __name__ == '__main__':
    unittest.main()
