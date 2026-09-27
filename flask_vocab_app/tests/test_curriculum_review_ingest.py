"""Review ingestion separates declared human decisions from internal checks."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_curriculum_review_packet import command as exporter

SPEC = importlib.util.spec_from_file_location('review_curriculum_packet', Path(__file__).resolve().parents[2] / 'scripts/review_curriculum_packet.py')
command = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(command)


class CurriculumReviewIngestTests(unittest.TestCase):
    def setUp(self):
        self.packet = exporter.build_packet(exporter.read_fixture())

    def completed(self, name='Fixture reviewer one', kind='human'):
        review = deepcopy(self.packet['reviewer.json'])
        review['reviewer'] = {'name_or_id': name, 'qualification': 'Synthetic test identity; no actual assessor',
                              'date': '2026-09-24', 'kind': kind}
        author = {'case:' + row['id']: row for row in self.packet['author-key.json']['cases']}
        for key, rating in command.targets(review).items():
            for field, value in rating.items():
                if field == 'outcome':
                    rating[field] = author[key]['outcome']
                elif value is None:
                    rating[field] = True
        return review

    def test_empty_packet_stays_pending_and_internal_model_review_does_not_count(self):
        result = command.report(self.packet, [])
        self.assertEqual(result['status'], 'awaiting human review')
        self.assertEqual(result['human_submissions'], 0)
        self.assertTrue(result['unresolved'])
        result = command.report(self.packet, [self.completed(kind='internal_model')])
        self.assertEqual(result['status'], 'awaiting human review')
        self.assertEqual(result['internal_model_submissions'], 1)
        self.assertEqual(result['agreements'], {})

    def test_review_cannot_change_raw_response_prompt_unit_hash_or_add_target(self):
        for mutate in (lambda r: r['cases'][0].update(response='Corrected after submission'),
                       lambda r: r['units'][0]['questions'][0]['item'].update(prompt='A different question'),
                       lambda r: r['unit_sha256'].update({'location-destination-v1': '0' * 64}),
                       lambda r: r['cases'].append(deepcopy(r['cases'][0]))):
            with self.subTest(mutate=mutate):
                review = self.completed(); mutate(review)
                with self.assertRaisesRegex(ValueError, 'content differs'):
                    command.report(self.packet, [review])

    def test_wrong_field_types_and_missing_declared_identity_fail(self):
        for mutate in (lambda r: r['reviewer'].pop('kind'),
                       lambda r: r['reviewer'].update(qualification=''),
                       lambda r: r['cases'][0]['review'].update(outcome='correct'),
                       lambda r: r['units'][0]['questions'][0]['review'].update(natural_russian='yes'),
                       lambda r: r['cases'][0]['review'].update(corrections='a correction')):
            with self.subTest(mutate=mutate):
                review = self.completed(); mutate(review)
                with self.assertRaises(ValueError):
                    command.report(self.packet, [review])

    def test_duplicate_review_identity_does_not_create_independent_agreement(self):
        first = self.completed(); second = deepcopy(first)
        second['reviewer']['name_or_id'] = '  FIXTURE REVIEWER ONE  '
        with self.assertRaisesRegex(ValueError, 'one review per reviewer'):
            command.report(self.packet, [first, second])

    def test_two_declared_human_reviews_record_decisions_without_claiming_release(self):
        result = command.report(self.packet, [self.completed(), self.completed('Fixture reviewer two')])
        self.assertEqual(result['status'], 'review decisions recorded')
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(result['human_submissions'], 2)
        self.assertIn('not independently verified', ' '.join(result['limitations']))
        self.assertNotIn('passed', result)

    def test_one_completed_language_review_is_recorded_without_requiring_a_second_for_every_item(self):
        result = command.report(self.packet, [self.completed()])
        self.assertEqual(result['status'], 'review decisions recorded')
        self.assertEqual(result['unresolved'], [])
        self.assertTrue(result['recorded_ratings'])
        self.assertEqual(result['agreements'], {})
        self.assertEqual(result['marking_comparison'], 'not performed')

    def test_disagreements_and_content_concerns_remain_visible_for_adjudication(self):
        first = self.completed(); second = self.completed('Fixture reviewer two')
        second['cases'][0]['review'].update(outcome='not_satisfied', reason='The requested form is absent.')
        second['units'][0]['questions'][0]['review']['unambiguous'] = False
        result = command.report(self.packet, [first, second])
        self.assertEqual(result['status'], 'review decisions pending')
        case = next(row for row in result['unresolved'] if row['target'] == 'case:case-001')
        self.assertIn('reviewer_disagreement:outcome', case['reasons'])
        self.assertIn('author_key_disagreement', case['reasons'])
        self.assertTrue(any('content_concern:unambiguous' in row['reasons'] for row in result['unresolved']))

    def test_adjudication_binds_exact_reviews_and_preserves_revision_work(self):
        first = self.completed(); second = self.completed('Fixture reviewer two')
        second['cases'][0]['review']['disputed'] = True
        report = command.report(self.packet, [first, second])
        adjudication = deepcopy(report['adjudication_template'])
        adjudication['adjudicator'] = {**first['reviewer'], 'name_or_id': 'Fixture third assessor'}
        adjudication['decisions'] = [{'target': 'case:case-001', 'decision': 'revise',
                                     'reason': 'The prompt needs a clear contrast.', 'rating': first['cases'][0]['review']}]
        result = command.report(self.packet, [first, second], adjudication)
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(result['release_actions'][0]['decision'], 'revise')
        changed = deepcopy(second); changed['cases'][0]['review']['reason'] = 'Further observations.'
        with self.assertRaisesRegex(ValueError, 'different content or review'):
            command.report(self.packet, [first, changed], adjudication)
        adjudication['adjudicator'] = first['reviewer']
        with self.assertRaisesRegex(ValueError, 'separate assessor'):
            command.report(self.packet, [first, second], adjudication)

    def test_adjudication_cannot_supply_missing_second_review(self):
        first = self.completed()
        first['cases'][0]['review']['disputed'] = True
        report = command.report(self.packet, [first])
        adjudication = deepcopy(report['adjudication_template'])
        adjudication['adjudicator'] = {**first['reviewer'], 'name_or_id': 'Fixture third assessor'}
        adjudication['decisions'] = [{'target': 'case:case-001', 'decision': 'accept', 'reason': 'Looks correct.',
                                     'rating': first['cases'][0]['review']}]
        with self.assertRaisesRegex(ValueError, 'second independent rating'):
            command.report(self.packet, [first], adjudication)

    def test_duplicate_json_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.json'
            path.write_text('{"outcome":"satisfied","outcome":"not_satisfied"}')
            with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
                command.read_json(path)


if __name__ == '__main__':
    unittest.main()
