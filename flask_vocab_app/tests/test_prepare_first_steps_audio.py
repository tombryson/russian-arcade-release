"""Packaged beginner speech must contain audible sound before publication."""
import contextlib
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import wave

from services.first_steps_audio import authored_clips
from services.speech_provider import audio_info


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'prepare_first_steps_audio_command', ROOT / 'scripts/prepare_first_steps_audio.py',
)
command = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command)


def recording(amplitude, audible_seconds=0.5):
    """A duration-valid recording with a controlled amount of audible signal."""
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        samples = [int(amplitude * math.sin(2 * math.pi * 440 * i / 16000))
                   if i < int(audible_seconds * 16000) else 0 for i in range(8000)]
        audio.writeframes(struct.pack('<8000h', *samples))
    return output.getvalue()


class AuthoredSpeechValidationTests(unittest.TestCase):
    def test_duration_valid_silent_and_near_silent_recordings_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'recording.wav'
            for amplitude in (0, 70):
                with self.subTest(amplitude=amplitude):
                    path.write_bytes(recording(amplitude))
                    self.assertEqual(audio_info(path), 0.5)
                    with self.assertRaisesRegex(ValueError, 'silent or too quiet'):
                        command.validate_authored_speech(path)

    def test_an_isolated_click_does_not_pass_as_speech(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'recording.wav'
            path.write_bytes(recording(6000, audible_seconds=0.05))
            with self.assertRaisesRegex(ValueError, 'silent or too quiet'):
                command.validate_authored_speech(path)

    def test_audible_recording_is_accepted_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'recording.wav'
            data = recording(6000)
            path.write_bytes(data)
            self.assertEqual(command.validate_authored_speech(path), 0.5)
            self.assertEqual(path.read_bytes(), data)

    def test_every_published_authored_clip_has_audible_signal(self):
        for url in authored_clips():
            with self.subTest(url=url):
                command.validate_authored_speech(ROOT / 'flask_vocab_app' / url.lstrip('/'))


class FirstStepsAudioPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = Path(self.tmp.name) / 'flask_vocab_app'
        self.directory = self.app / 'static/audio/first-steps-v2'
        self.manifest = self.directory / 'manifest.json'
        self.url = '/static/audio/first-steps-v2/test-word.mp3'
        self.path = self.app / self.url.lstrip('/')
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(command, 'APP', self.app))
        self.stack.enter_context(patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]))
        self.stack.enter_context(patch('services.first_steps_audio.authored_clips', return_value={self.url: 'Слово.'}))
        self.stack.enter_context(patch('config.app_config', return_value={'OPENAI_API_KEY': 'test-key'}))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.create = Mock()
        self.client = types.SimpleNamespace(audio=types.SimpleNamespace(speech=types.SimpleNamespace(create=self.create)))
        self.constructor = Mock(return_value=self.client)
        self.stack.enter_context(patch.dict(sys.modules, {'openai': types.SimpleNamespace(OpenAI=self.constructor)}))

    def save_published(self, data):
        self.directory.mkdir(parents=True)
        self.path.write_bytes(data)
        self.manifest.write_text(json.dumps({'provider': 'openai', 'clips': {self.url: {
            'text_sha256': hashlib.sha256('Слово.'.encode()).hexdigest(),
            'audio_sha256': hashlib.sha256(data).hexdigest(),
            'voice_id': 'cedar', 'model': 'gpt-4o-mini-tts', 'duration': 0.5, 'bytes': len(data),
        }}}))

    def test_silent_response_is_not_published_and_can_be_retried(self):
        self.create.return_value = types.SimpleNamespace(content=recording(70))
        with self.assertRaisesRegex(SystemExit, 'Recording stopped'):
            command.main(['--provider', 'openai', '--max-new', '1'])
        self.assertFalse(self.path.exists())
        pending = json.loads(self.manifest.read_text())['clips'][self.url]
        self.assertNotIn('audio_sha256', pending)
        self.assertEqual({path.name for path in self.directory.iterdir()}, {'manifest.json'})

        data = recording(6000)
        self.create.return_value = types.SimpleNamespace(content=data)
        command.main(['--provider', 'openai', '--max-new', '1'])
        saved = json.loads(self.manifest.read_text())['clips'][self.url]
        self.assertEqual(self.path.read_bytes(), data)
        self.assertEqual(saved['audio_sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(saved['voice_id'], pending['voice_id'])
        self.assertEqual(self.create.call_count, 2)

    def test_reuse_rejects_a_silent_recording_even_when_its_hash_matches(self):
        self.save_published(recording(70))
        with self.assertRaisesRegex(SystemExit, 'silent or too quiet'):
            command.main(['--provider', 'openai', '--dry-run'])
        self.constructor.assert_not_called()

    def test_unfinished_elevenlabs_clip_records_v4_while_retaining_its_selected_voice(self):
        self.directory.mkdir(parents=True)
        self.manifest.write_text(json.dumps({'provider': 'elevenlabs', 'clips': {self.url: {
            'text_sha256': hashlib.sha256('Слово.'.encode()).hexdigest(),
            'voice_id': 'saved-voice', 'model': 'eleven_multilingual_v2',
        }}}))
        config = {'ELEVENLABS_API_KEY': 'test', 'ELEVENLABS_VOICE_IDS': ['different-voice'], 'ELEVENLABS_MODEL': 'eleven_v4'}
        provider = Mock()
        def speak(text, voice):
            saved = json.loads(self.manifest.read_text())['clips'][self.url]
            self.assertEqual(saved['model'], 'eleven_v4')
            self.assertEqual(voice, 'saved-voice')
            return recording(6000)
        provider.speak.side_effect = speak
        with patch('config.app_config', return_value=config), patch('services.speech_provider.SpeechProvider', return_value=provider), \
                patch('requests.get', return_value=Mock(ok=True, json=lambda: {'character_limit': 1000, 'character_count': 0})):
            command.main(['--max-new', '1'])
        provider.speak.assert_called_once_with('Слово.', 'saved-voice')
        self.assertEqual(json.loads(self.manifest.read_text())['clips'][self.url]['model'], 'eleven_v4')

    def test_reuse_accepts_audible_recording_without_provider_calls(self):
        data = recording(6000)
        self.save_published(data)
        command.main(['--provider', 'openai'])
        self.constructor.assert_not_called()
        self.assertEqual(self.path.read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
