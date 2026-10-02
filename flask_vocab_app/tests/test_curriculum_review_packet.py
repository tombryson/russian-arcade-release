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
        from services.curriculum_units import UNIT_IDS, LISTENING_IDS, get_unit
        current = command.read_fixture(command.CURRENT_FIXTURE)
        directory = ROOT / 'flask_vocab_app/data/curriculum_evaluation'
        retained = {
            1: 'c73bead57aca1c6f9f2082f96b4cee7195fcddf9dd864365407c812673f0425c',
            2: '83b66c8480a3691db9cc77790c8efdac02cc6052543edfdaa76e847f1bded92e',
            3: '9f8e8d0bd08d6eae3ebb39b1d37054f30b5ab04f417bfc51d2122167940e7525',
            4: 'f68b7c29a597bc6b20b6fdb56ae3e2da9733efff525e8b84c7bbbf9c74a9b268',
            5: 'ad354c4fe852c74347fd252b0dbe615ccbb4cd66fc42d162f9c260f6cda6ce61',
        }
        for version, digest in retained.items():
            path = directory / f'a1-units-review-v{version}.json'
            self.assertEqual(command.digest(path.read_bytes()), digest)
            previous = command.read_fixture(path)
            self.assertEqual(current['cases'][:len(previous['cases'])], previous['cases'])
            for field in ('unit_sha256', 'listening_sha256'):
                for identity, expected in previous.get(field, {}).items():
                    self.assertEqual(current[field][identity], expected)
        self.assertEqual(current['id'], 'a1-units-review-v6')
        self.assertEqual(set(current['unit_sha256']), set(UNIT_IDS))
        self.assertEqual(set(current['listening_sha256']), set(LISTENING_IDS.values()))
        self.assertEqual(current['review'], {'kind': 'internal_model', 'independently_validated': False})
        fourth = command.read_fixture(directory / 'a1-units-review-v4.json')
        added = previous['cases'][len(fourth['cases']):]
        self.assertEqual({case['unit_id'] for case in added}, {'instrumental-activities-professions-v1'})
        forms = get_unit('instrumental-activities-professions-v1')['forms']['questions']
        self.assertEqual(sum(case['stage'] == 'forms' for case in added), 3 * len(forms) + 1)
        self.assertIn('музыкою', {case['response'] for case in added})
        self.assertEqual(sum(case['stage'] == 'writing' for case in added), 7)

        added = current['cases'][len(previous['cases']):]
        new_units = {'calendar-and-duration-v1', 'talking-about-topics-v1'}
        self.assertEqual({case['unit_id'] for case in added}, new_units)
        self.assertEqual(len(current['cases']), 365)
        self.assertEqual(sum(case['stage'] == 'forms' for case in added), 54)
        self.assertEqual(sum(case['stage'] == 'writing' for case in added), 14)
        for unit_id in new_units:
            cases = [case for case in added if case['unit_id'] == unit_id]
            for item in get_unit(unit_id)['forms']['questions']:
                forms = [case for case in cases if case.get('item_id') == item['id']]
                self.assertEqual({case['author_expectation']['outcome'] for case in forms},
                                 {'satisfied', 'not_satisfied'})
                self.assertTrue(any(case['response'] == item['answer'] and not case['support'] for case in forms))
                self.assertTrue(any(case['support'] == ['hint'] for case in forms))
                for answer in item['accepted_answers']:
                    self.assertIn(answer, {case['response'] for case in forms})
            writing = [case for case in cases if case['stage'] == 'writing']
            self.assertEqual({case['author_expectation']['outcome'] for case in writing}, command.OUTCOMES)
            self.assertTrue(any(case['support'] == ['model_answer'] for case in writing))
            self.assertTrue(any(case['id'].endswith('grammar-errors') and
                                case['author_expectation']['outcome'] == 'satisfied' for case in writing))
        time_cases = [case for case in added if case['unit_id'] == 'calendar-and-duration-v1']
        for confusion in ('в десять', 'через неделю', 'первого марта'):
            self.assertTrue(any(case['response'] == confusion and
                                case['author_expectation']['outcome'] == 'not_satisfied' for case in time_cases))

    def test_supported_form_cases_keep_help_visible_and_reject_unavailable_help(self):
        fixture = command.read_fixture(command.CURRENT_FIXTURE)
        packet = command.build_packet(fixture)
        hinted = [(source, row) for source, row in zip(fixture['cases'], packet['reviewer.json']['cases'])
                  if source['stage'] == 'forms' and source['support'] == ['hint']]
        self.assertEqual(len(hinted), 12)
        for source, row in hinted:
            self.assertEqual(row['support'], ['hint'])
            self.assertEqual(row['response'], source['response'])
            self.assertIsNone(row['review']['independent_evidence'])
            self.assertNotIn('author_expectation', row)
        next(case for case in fixture['cases'] if case['stage'] == 'forms' and
             case['support'] == ['hint'])['support'] = ['transcript']
        path = self.directory / 'unsupported-form.json'
        path.write_text(json.dumps(fixture, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, 'Unsupported controlled-form help'):
            command.read_fixture(path)

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
