"""Beginner speech must be published, playable and public without exposing uploads."""
import hashlib
import json
from pathlib import Path
import unittest

from services.first_steps_audio import authored_clips, intro_speech, is_public_recording
from services.speech_provider import audio_info
from tests.support import isolated_app

APP = Path(__file__).resolve().parents[1]


class FirstStepsAudioTests(unittest.TestCase):
    def test_authored_audio_has_verified_bytes_and_decodes(self):
        manifest = json.loads((APP / 'static/audio/first-steps-v2/manifest.json').read_text())
        for url, text in authored_clips().items():
            with self.subTest(url=url):
                clip = manifest['clips'][url]
                path = APP / 'static' / url.removeprefix('/static/')
                self.assertEqual(clip['text_sha256'], hashlib.sha256(text.encode()).hexdigest())
                self.assertEqual(clip['audio_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertAlmostEqual(audio_info(path), clip['duration'], places=2)
                self.assertNotIn('\u0301', text, 'TTS receives ordinary Russian, not visual stress markup.')

    def test_all_recordings_are_public_and_support_seeking(self):
        app = isolated_app(self, signed_in=False)
        client = app.test_client()
        for path in authored_clips():
            with self.subTest(path=path), client.get(path, headers={'Range': 'bytes=0-511'}) as response:
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response.mimetype, 'audio/mpeg')
                self.assertEqual(len(response.data), 512)
                self.assertTrue(response.headers['Content-Range'].startswith('bytes 0-511/'))
        self.assertFalse(is_public_recording('audio/first-steps-v2/manifest.json'))
        self.assertFalse(is_public_recording('audio/first-steps-v2/learner-recording.mp3'))
        self.assertFalse(is_public_recording('uploads/private.mp3'))

    def test_first_words_have_stress_reading_help_and_pronunciation(self):
        for question in ('word-hello', 'word-letter', 'word-thanks'):
            speech = intro_speech(question)
            self.assertIn('\u0301', speech['word_display'])
            self.assertTrue(speech['reading_help'])
            self.assertIn(speech['audio_url'], authored_clips())
        self.assertEqual(intro_speech('unpublished'), {})


if __name__ == '__main__':
    unittest.main()
