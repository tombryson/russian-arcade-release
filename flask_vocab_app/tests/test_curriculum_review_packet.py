"""Reviewer fixtures are reproducible hypotheses, with human results left blank."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('curriculum_review_command', ROOT / 'scripts/prepare_curriculum_review.py')
command = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command)


class CurriculumReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.fixture = command.read_fixture()

    def changed_fixture(self, mutate):
        changed = deepcopy(self.fixture)
        mutate(changed)
        path = self.directory / 'fixture.json'
        path.write_text(json.dumps(changed, ensure_ascii=False))
        return path

    def test_authored_fixture_hashes_and_controlled_expectations_match_existing_units(self):
        self.assertEqual(len(self.fixture['unit_sha256']), 4)
        self.assertEqual(len(self.fixture['cases']), 66)
        self.assertEqual(sum(c['stage'] == 'forms' for c in self.fixture['cases']), 48)
        self.assertEqual(sum(c['stage'] == 'writing' for c in self.fixture['cases']), 18)
        self.assertTrue(any(c['response'].startswith('  ') for c in self.fixture['cases']))

    def test_changed_unit_hash_or_incorrect_deterministic_expectation_is_rejected(self):
        path = self.changed_fixture(lambda f: f['unit_sha256'].update({'time-routine-v1': '0' * 64}))
        with self.assertRaisesRegex(ValueError, 'Unit content changed'):
            command.read_fixture(path)
        path = self.changed_fixture(lambda f: f['cases'][0]['author_expectation'].update(outcome='not_satisfied'))
        with self.assertRaisesRegex(ValueError, 'disagrees with the published matcher'):
            command.read_fixture(path)

    def test_current_fixture_extends_retained_versions_without_rewriting_them(self):
        current = command.read_fixture(command.CURRENT_FIXTURE)
        previous = command.read_fixture(ROOT / 'flask_vocab_app/data/curriculum_evaluation/a1-units-review-v2.json')
        self.assertEqual(len(current['unit_sha256']), 13)
        self.assertEqual(len(current['listening_sha256']), 13)
        self.assertEqual(len(current['cases']), 246)
        by_id = {case['id']: case for case in current['cases']}
        for case in previous['cases']:
            self.assertEqual(by_id[case['id']], case)
        for identity, digest in previous['unit_sha256'].items():
            self.assertEqual(current['unit_sha256'][identity], digest)

    def test_duplicate_cases_or_unavailable_support_are_rejected(self):
        path = self.changed_fixture(lambda f: f['cases'].append(deepcopy(f['cases'][0])))
        with self.assertRaisesRegex(ValueError, 'distinct IDs'):
            command.read_fixture(path)
        path = self.changed_fixture(lambda f: f['cases'][-1].update(support=['transcript']))
        with self.assertRaisesRegex(ValueError, 'Unsupported Writing help'):
            command.read_fixture(path)

    def test_reviewer_packet_omits_author_answers_and_keeps_human_judgements_blank(self):
        packet = command.build_packet(self.fixture)
        reviewer = packet['reviewer.json']
        self.assertEqual(reviewer['reviewer']['qualification'], '')
        for source, row in zip(self.fixture['cases'], reviewer['cases']):
            self.assertNotIn('author_expectation', row)
            self.assertRegex(row['id'], r'^case-\d{3}$')
            self.assertEqual(row['response'], source['response'])
            self.assertIsNone(row['review']['outcome'])
            self.assertIsNone(row['review']['independent_evidence'])
            if row['stage'] == 'forms':
                self.assertNotIn('expectation', row['task'])
        for unit in reviewer['units']:
            for question in unit['questions']:
                self.assertNotIn('answer', question['item'])
                self.assertNotIn('accepted_answers', question['item'])
        self.assertEqual({r['id'] for r in reviewer['cases']}, {r['id'] for r in packet['author-key.json']['cases']})
        self.assertEqual(packet['manifest.json']['review_status'], 'not completed')
        self.assertEqual(packet['manifest.json']['provider_calls'], 0)

    def test_export_is_repeatable_and_never_overwrites_filled_review(self):
        first = command.build_packet(self.fixture)
        self.assertEqual(first, command.build_packet(self.fixture))
        command.write_packet(first, self.directory)
        command.write_packet(first, self.directory)
        path = self.directory / 'reviewer.json'
        reviewed = json.loads(path.read_text())
        reviewed['reviewer']['name_or_id'] = 'A real reviewer'
        path.write_text(json.dumps(reviewed, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            command.write_packet(first, self.directory)
        self.assertEqual(json.loads(path.read_text())['reviewer']['name_or_id'], 'A real reviewer')


if __name__ == '__main__':
    unittest.main()
