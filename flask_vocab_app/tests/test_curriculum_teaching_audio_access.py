"""Public teaching examples must play without opening private learner media."""
import unittest

from services.curriculum_sequence_content import is_public_teaching_recording, load_asset
from tests.support import isolated_app


class CurriculumTeachingAudioAccessTests(unittest.TestCase):
    def test_only_authored_teaching_clips_are_public_and_seekable(self):
        app = isolated_app(self, signed_in=False)
        client = app.test_client()
        examples = [example for group in load_asset('location-teaching-v2')['content']['groups'] for example in group['examples']]
        self.assertEqual(len(examples), 13)
        for example in examples:
            url = example['audio']['url']
            with self.subTest(text=example['ru']), client.get(url, headers={'Range': 'bytes=0-511'}) as response:
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response.mimetype, 'audio/mpeg')
                self.assertEqual(len(response.data), 512)
        listening = load_asset('location-listening-v2')['content']['items'][0]['audio']['url']
        for filename in (listening.removeprefix('/static/'), 'uploads/private.mp3',
                         'audio/course/curriculum/location-destination-sequence-v1/manifest.json',
                         'audio/course/curriculum/location-destination-sequence-v1/' + '0' * 64 + '.mp3'):
            with self.subTest(filename=filename):
                self.assertFalse(is_public_teaching_recording(filename))
                self.assertNotIn(client.get('/static/' + filename).status_code, (200, 206))
