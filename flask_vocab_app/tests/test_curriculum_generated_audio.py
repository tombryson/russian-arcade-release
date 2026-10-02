"""Runtime lesson speech keeps the exact message and the owning workspace."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from pydub.generators import Sine

from contracts.learning import validate_pack
from repositories.learning_repository import LearningError
from services.curriculum_generated_audio import (
    DIRECTORY, generate_audio, plan_audio, validate_descriptor,
    validate_saved_generated_audio, verify_generated_audio,
)
from services.learning_backup import backup_learning_store
from services.learning_listening import verify_audio
from tests.support import isolated_app


class CurriculumGeneratedAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with io.BytesIO() as stream:
            Sine(330).to_audio_segment(duration=1400).export(stream, format='mp3')
            cls.recording = stream.getvalue()

    def setUp(self):
        self.app = isolated_app(self)
        self.db = self.app.config['DB_PATH']
        self.root = Path(self.app.config['APP_MEDIA_DIR'])
        self.provider = Mock(voice_ids=('one', 'two'), model='configured_model', api_key='private-test-key',
                             config={'ELEVENLABS_API_KEY': 'private-test-key'})
        self.text = 'Нина идёт в библиотеку. Потом она встретит Диму.'
        self.spec = plan_audio(self.text, self.provider)
        self.factory = patch('services.curriculum_generated_audio.ElevenLabsService').start()
        self.addCleanup(patch.stopall)
        self.factory.side_effect = self.speech
        self.client = self.app.test_client()
        self.identity = self.client.get('/api/v1/user-session').json
        self.token = self.identity['csrf_token']
        self.services = self.app.extensions['learning']
        self.services['sessions'].media_root = self.root

    def speech(self, key, directory, **kwargs):
        service = Mock()
        def generate(text, filename):
            self.assertEqual(text, self.text)
            self.assertEqual(key, 'private-test-key')
            self.assertEqual(kwargs['voice_ids'], (self.spec['voice_id'],))
            self.assertEqual(kwargs['model'], self.spec['model'])
            (Path(directory) / filename).write_bytes(self.recording)
            return filename
        service.generate_audio.side_effect = generate
        return service

    def audio(self):
        return generate_audio(self.spec, self.provider, self.root)

    def pack(self, audio):
        return {'schema_version': 1, 'id': 'generated-fixture', 'kind': 'activity', 'title': 'A message',
                'source': 'Synthetic integration fixture.', 'items': [
                    {'id': 'first', 'type': 'listening_choice', 'prompt': 'Куда идёт Нина?',
                     'transcript': self.text, 'audio': audio,
                     'choices': [{'id': 'a', 'text': 'В библиотеку.'}, {'id': 'b', 'text': 'В аптеку.'}], 'answer': 'a'}]}

    def start(self):
        audio = self.audio()
        version = self.services['content'].import_draft(self.pack(audio))
        with self.client.session_transaction() as state:
            credential = state['personal_access_id']
        self.services['content'].publish(credential, version, 'Fixture')
        response = self.client.post('/api/v1/learning-sessions', json={
            'profile_id': self.identity['profile']['id'], 'version_id': version,
            'submission_id': uuid4().hex}, headers={'X-CSRF-Token': self.token})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.json, audio

    def test_voice_plan_is_random_then_frozen_across_config_change(self):
        with patch('services.curriculum_generated_audio.random.choice', return_value='two') as choose:
            self.spec = plan_audio(self.text, self.provider)
        choose.assert_called_once_with(('one', 'two'))
        self.provider.voice_ids, self.provider.model = ('changed',), 'changed_model'
        audio = self.audio()
        self.assertEqual(audio['transcript_sha256'], hashlib.sha256(self.text.encode()).hexdigest())
        self.assertEqual(self.factory.call_count, 1)
        self.assertTrue(1000 <= audio['duration_ms'] <= 180000)
        self.assertNotIn('url', audio)
        path = verify_generated_audio(audio, self.text, self.root)
        metadata = path.with_suffix('.json').read_text()
        self.assertNotIn('private-test-key', metadata)
        self.assertIn('configured_model', metadata)
        self.assertEqual(path.read_bytes(), self.recording)
        self.assertFalse(list(self.root.glob('.curriculum-speech-*')))

    def test_provider_failure_does_not_retry_publish_or_leave_partial_files(self):
        service = Mock()
        service.generate_audio.side_effect = RuntimeError('failed')
        self.factory.side_effect, self.factory.return_value = None, service
        with self.assertRaises(RuntimeError):
            self.audio()
        service.generate_audio.assert_called_once()
        self.assertFalse((self.root / DIRECTORY).exists())
        self.assertFalse(list(self.root.glob('.curriculum-speech-*')))

    def test_bad_audio_is_rejected_before_publication(self):
        self.recording = b'ID3not-a-recording'
        with self.assertRaises(ValueError):
            self.audio()
        self.assertFalse((self.root / DIRECTORY).exists())
        self.assertEqual(self.factory.call_count, 1)

    def test_changed_transcript_wrong_workspace_and_changed_metadata_are_rejected(self):
        audio = self.audio()
        pack = self.pack(audio)
        validate_pack(pack)
        self.assertEqual(verify_audio(pack['items'][0], media_root=self.root).read_bytes(), self.recording)
        with self.assertRaises(ValueError):
            validate_descriptor(audio, self.text + ' Другой текст.')
        with self.assertRaises(LearningError):
            verify_generated_audio(audio, self.text, self.root / 'another-tenant')
        path = verify_generated_audio(audio, self.text, self.root)
        path.with_suffix('.json').write_text('{}')
        with self.assertRaises(LearningError):
            verify_generated_audio(audio, self.text, self.root)

    def test_runtime_descriptors_cannot_use_urls_or_traverse_paths(self):
        audio = self.audio()
        for field, value in (('storage_key', '../outside'), ('sha256', 'nope'), ('url', '/static/media/secret.mp3')):
            with self.subTest(field=field), self.assertRaises(LearningError):
                validate_pack(self.pack({**audio, field: value}))
        with tempfile.TemporaryDirectory() as other:
            path = verify_generated_audio(audio, self.text, self.root)
            saved = path.read_bytes()
            path.unlink()
            external = Path(other) / 'outside.mp3'
            external.write_bytes(saved)
            path.symlink_to(external)
            with self.assertRaises(LearningError):
                verify_generated_audio(audio, self.text, self.root)

    def test_directory_symlink_fails_before_provider_call(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as other:
            (self.root / DIRECTORY).symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.audio()
        self.factory.assert_not_called()

    def test_owned_playback_and_listened_receipt_do_not_expose_transcript_or_private_key(self):
        state, audio = self.start()
        private_path = verify_generated_audio(audio, self.text, self.root).relative_to(self.root.resolve()).as_posix()
        self.assertEqual(self.client.get('/static/media/' + private_path).status_code, 404)
        self.assertEqual(self.client.get('/static/media/' + private_path.replace('curriculum-audio', 'CURRICULUM-AUDIO')).status_code, 404)
        self.assertEqual(self.client.get('/static/media/' + private_path.removesuffix('.mp3') + '.json').status_code, 404)
        self.assertEqual(set(state['item']['audio']), {'url', 'sha256', 'duration_ms'})
        self.assertIsNone(state['item']['transcript'])
        url = state['item']['audio']['url']
        with self.client.get(url, headers={'Range': 'bytes=0-31'}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, self.recording[:32])
        response = self.client.post('/api/v1/learning-sessions/' + state['id'] + '/listened', json={
            'submission_id': uuid4().hex, 'item_id': state['item']['id'], 'expected_revision': state['revision']},
            headers={'X-CSRF-Token': self.token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['item']['listened'])
        self.assertIsNone(response.json['item']['transcript'])
        self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Other learner'},
                         headers={'X-CSRF-Token': self.token})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_backup_copies_and_validates_runtime_audio_for_restore(self):
        _, audio = self.start()
        target = Path(self.db).parent / 'runtime-backup'
        manifest = backup_learning_store(self.db, self.services['assets'], target, media_root=self.root)
        self.assertEqual(len(manifest['generated_curriculum_audio']), 2)
        copied = verify_generated_audio(audio, self.text, target / 'media')
        self.assertEqual(copied.read_bytes(), self.recording)
        with sqlite3.connect(target / 'vocab.db') as conn:
            self.assertEqual(len(validate_saved_generated_audio(conn, target / 'media')), 2)
        original = verify_generated_audio(audio, self.text, self.root)
        original.write_bytes(b'changed')
        with self.assertRaises(LearningError):
            backup_learning_store(self.db, self.services['assets'], target.with_name('corrupt-backup'), media_root=self.root)
        self.assertTrue((target.with_name('corrupt-backup') / 'INCOMPLETE').exists())

    def test_account_import_requires_and_rechecks_runtime_media(self):
        from migrations import upgrade_database
        from services.account_import import build_account_import, ImportConflict
        _, audio = self.start()
        hosted = Path(self.db).parent / 'hosted.db'
        output = hosted.with_name('merged.db')
        upgrade_database(hosted, backup=False)
        with self.assertRaisesRegex(ImportConflict, 'local-media-root'):
            build_account_import(self.db, hosted, output)
        self.assertFalse(output.exists())
        report = build_account_import(self.db, hosted, output, local_media_root=self.root)
        self.assertEqual(report['verified_generated_curriculum_recordings'], 1)
        self.assertFalse(report['media_copied'])
        with sqlite3.connect(output) as conn:
            self.assertEqual(len(validate_saved_generated_audio(conn, self.root)), 2)


    def test_staged_audio_survives_without_a_published_content_row(self):
        audio = self.audio()
        with sqlite3.connect(':memory:') as conn:
            conn.execute('CREATE TABLE curriculum_situations(audio_json TEXT,document_json TEXT,voice_json TEXT)')
            conn.execute('INSERT INTO curriculum_situations VALUES (?,?,?)',
                (json.dumps(audio), json.dumps({'response': {'text': self.text}}), json.dumps(self.spec)))
            self.assertEqual(len(validate_saved_generated_audio(conn, self.root)), 2)
            changed = {**self.spec, 'voice_id': 'another-voice'}
            conn.execute('UPDATE curriculum_situations SET voice_json=?', (json.dumps(changed),))
            with self.assertRaises(ValueError):
                validate_saved_generated_audio(conn, self.root)

    def test_import_verification_checks_actual_duration_not_only_manifest(self):
        audio = self.audio()
        path = verify_generated_audio(audio, self.text, self.root)
        metadata = json.loads(path.with_suffix('.json').read_text())
        audio['duration_ms'] += 1000
        metadata['audio'] = audio
        path.with_suffix('.json').write_text(json.dumps(metadata))
        with self.assertRaises(LearningError):
            verify_generated_audio(audio, self.text, self.root, check_duration=True)



if __name__ == '__main__':
    unittest.main()
