"""Published listening assets must match the authored checkpoint variants."""
import hashlib
import json
from pathlib import Path
import unittest

from services.course_progression import course_catalogue
from services.course_releases import RELEASES
from services.speech_provider import audio_info


class CourseAudioTests(unittest.TestCase):
    def test_every_checkpoint_has_its_published_decodable_recording(self):
        static = Path(__file__).resolve().parents[1] / 'static'
        manifest = json.loads((static / 'audio/course/manifest.json').read_text())
        new_manifest = json.loads((static / 'audio/course/milestones-manifest.json').read_text())
        for release_id in RELEASES:
          for chapter in course_catalogue(release_id)['chapters']:
            for variant in chapter['variants']:
                with self.subTest(variant=variant['id']):
                    clip = variant['listening']
                    record = manifest['clips'][variant['id']] if release_id == 'a1-v1' else new_manifest['clips'][clip['audio_url']]
                    path = static / clip['audio_url'].removeprefix('/static/')
                    self.assertEqual(record['text_sha256'], hashlib.sha256(clip['transcript'].encode()).hexdigest())
                    self.assertEqual(record['audio_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                    duration = audio_info(path)
                    self.assertGreater(duration, 3)
                    self.assertLess(duration, 30)
                    self.assertAlmostEqual(duration, record['duration'], places=1)

    def test_preparation_listening_assets_are_bundled_and_match_their_text(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'static/audio/course/milestones-manifest.json').read_text())
        items = json.loads((root / 'data/course_target_practice.json').read_text())['items']
        for item in items:
            question = item['question']
            if not question.get('audio_url'):
                continue
            with self.subTest(item=item['id']):
                record = manifest['clips'][question['audio_url']]
                path = root / 'static' / question['audio_url'].removeprefix('/static/')
                self.assertEqual(record['text_sha256'], hashlib.sha256(question['transcript'].encode()).hexdigest())
                self.assertEqual(record['audio_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertAlmostEqual(audio_info(path), record['duration'], places=1)
