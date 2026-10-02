"""Offline reviewer materials preserve tasks and separate authored answer keys."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

def command(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

pilot = command('prepare_assessment_pilot_review')
units = command('prepare_curriculum_review')
review = command('review_curriculum_packet')


class AssessmentPilotReviewPacketTests(unittest.TestCase):
    def test_both_forms_all_domains_have_blank_review_and_separate_keys(self):
        packet = pilot.build_packet(pilot.read_fixture())
        self.assertEqual(len(packet['reviewer.json']['units']), 10)
        self.assertEqual({row['source']['domain'] for row in packet['reviewer.json']['units']},
                         {'language_use', 'reading', 'listening', 'writing', 'speaking'})
        for row in packet['reviewer.json']['units']:
            self.assertIsNone(row['teaching_review']['accuracy'])
            self.assertTrue(row['source']['criteria'])
            self.assertNotIn('contract', row['source'])
            for question in row['questions']:
                self.assertNotIn('answer', question['item'])
                self.assertNotIn('explanation', question['item'])
                self.assertIsNone(question['review']['unambiguous'])
            if row['source']['domain'] == 'listening':
                self.assertIn(row['source']['recording_status'], ['not prepared', 'prepared; editorial audio review not recorded'])
                self.assertTrue(row['source']['transcript'])
        self.assertEqual(sum(len(row['answers']) for row in packet['author-key.json']['units']), 24)
        self.assertEqual(packet['manifest.json']['provider_calls'], 0)
        self.assertIn('not been calibrated', ' '.join(packet['reviewer.json']['limitations']))
        self.assertEqual(review.report(packet, [])['human_submissions'], 0)

    def test_source_pin_and_ingestion_reject_changed_prompt_or_key(self):
        packet = pilot.build_packet(pilot.read_fixture())
        review.validate_packet(packet)
        changed = deepcopy(packet)
        changed['reviewer.json']['units'][0]['source']['prompt'] = 'Changed.'
        with self.assertRaisesRegex(ValueError, 'pinned authored sources'):
            review.validate_packet(changed)
        changed = deepcopy(packet)
        changed['author-key.json']['units'][0]['answers'][0]['answer'] = 'x'
        with self.assertRaisesRegex(ValueError, 'answer keys differ'):
            review.validate_packet(changed)
        with self.assertRaisesRegex(ValueError, 'pinned review fixture'):
            pilot.build_packet({**pilot.read_fixture(), 'blueprint_sha256': '0' * 64})

    def test_current_unit_packet_includes_all_source_and_available_recording_material(self):
        fixture = units.read_fixture(units.CURRENT_FIXTURE)
        self.assertEqual(len(fixture['unit_sha256']), 14)
        self.assertEqual(len(fixture['listening_sha256']), 14)
        self.assertEqual(len(fixture['cases']), 271)
        packet = units.build_packet(fixture)
        items = [row['item'] for unit in packet['reviewer.json']['units'] for row in unit['questions'] if row['stage'] == 'listening']
        self.assertEqual(len(items), 42)
        self.assertEqual(sum(item['audio_file'] is not None for item in items), 42)
        tampered = deepcopy(packet)
        included = next(question['item'] for unit in tampered['reviewer.json']['units'] for question in unit['questions']
                        if question['stage'] == 'listening' and question['item']['audio_file'])
        included['duration_seconds'] = 999
        with self.assertRaisesRegex(ValueError, 'Recording metadata differs'):
            review.validate_packet(tampered)
        with tempfile.TemporaryDirectory() as directory:
            units.write_packet(packet, directory)
            review.validate_packet(packet, directory)
            clip = packet['manifest.json']['audio_files'][0]
            (Path(directory) / clip['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'recording is missing or changed'):
                review.validate_packet(packet, directory)


if __name__ == '__main__':
    unittest.main()
