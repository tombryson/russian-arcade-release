"""Evaluation preserves inputs, limits calls and never invents validation results."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import evaluate_curriculum_writing as command
import prepare_curriculum_review as packets


class WritingEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.fixture = packets.read_fixture(packets.CURRENT_FIXTURE)
        self.case = next(case for case in self.fixture['cases'] if case['id'] == 'possession-absence-v1-writing-clear')

    def assessment(self, unit, task, response):
        contract = task['curriculum_contract']
        return {'score': 10, 'strength': 'The request and missing item are clear.',
                'next_step': 'Your message meets the task.', 'example': 'Возьми воду, пожалуйста.',
                'criterion_report': {'contract_sha256': contract['contract_sha256'], 'judgements': [
                    {'criterion_id': contract['criteria'][0]['id'], 'outcome': 'satisfied', 'score': 2,
                     'feedback': 'The friend knows what to bring.',
                     'evidence': [{'quote': response, 'start': 0, 'end': len(response)}]}]}}

    def test_offline_matches_forms_without_calling_ai_and_keeps_writing_unmeasured(self):
        result = command.evaluate(self.fixture, self.output)
        measured = [row for row in result['results'] if row['status'] == 'measured']
        self.assertTrue(measured)
        self.assertTrue(all(row['stage'] == 'forms' for row in measured))
        self.assertTrue(all(row['actual'] == row['expected'] for row in measured))
        self.assertTrue(all(row['status'] == 'not_run' for row in result['results'] if row['stage'] == 'writing'))
        self.assertNotIn('accuracy', result['summary'])

    def test_resume_preserves_original_text_and_does_not_repeat_provider_calls(self):
        assess = Mock(side_effect=self.assessment)
        args = dict(assess=assess, model='fixture-model', case_ids=[self.case['id']])
        first = command.evaluate(self.fixture, self.output, **args)
        second = command.evaluate(self.fixture, self.output, **args)
        self.assertEqual(first, second)
        assess.assert_called_once()
        self.assertEqual(first['results'][0]['original_response'], self.case['response'])
        changed = deepcopy(self.fixture)
        changed['cases'][0]['response'] += ' changed'
        with self.assertRaisesRegex(ValueError, 'different content'):
            command.evaluate(changed, self.output, **args)
        assess.assert_called_once()

    def test_concurrent_run_cannot_buy_the_same_case_or_overwrite_results(self):
        duplicate = Mock(side_effect=self.assessment)
        def assess(unit, task, response):
            with self.assertRaisesRegex(ValueError, 'Another evaluation'):
                command.evaluate(self.fixture, self.output, assess=duplicate, model='fixture-model', case_ids=[self.case['id']])
            duplicate.assert_not_called()
            return self.assessment(unit, task, response)
        result = command.evaluate(self.fixture, self.output, assess=assess, model='fixture-model', case_ids=[self.case['id']])
        self.assertEqual(result['summary']['measured'], 1)
        resumed = command.evaluate(self.fixture, self.output, assess=duplicate, model='fixture-model', case_ids=[self.case['id']])
        self.assertEqual(result, resumed)
        duplicate.assert_not_called()

    def test_failure_stops_before_next_call_and_cannot_auto_retry_on_resume(self):
        cases = [self.case['id'], 'possession-absence-v1-writing-grammar']
        assess = Mock(side_effect=RuntimeError('sensitive-provider-details'))
        result = command.evaluate(self.fixture, self.output, assess=assess, model='fixture-model', case_ids=cases)
        assess.assert_called_once()
        self.assertEqual(result['results'][0]['status'], 'failed')
        self.assertNotIn('sensitive-provider-details', json.dumps(result))
        command.evaluate(self.fixture, self.output, assess=assess, model='fixture-model', case_ids=[cases[0]])
        assess.assert_called_once()

    def test_interrupted_request_remains_visible_without_retry(self):
        assess = Mock(side_effect=KeyboardInterrupt)
        with self.assertRaises(KeyboardInterrupt):
            command.evaluate(self.fixture, self.output, assess=assess, model='fixture-model', case_ids=[self.case['id']])
        result = command.evaluate(self.fixture, self.output, assess=assess, model='fixture-model', case_ids=[self.case['id']])
        assess.assert_called_once()
        self.assertEqual(result['summary']['status_counts'], {'interrupted': 1})

    def test_empty_response_is_input_validation_not_a_model_judgement(self):
        assess = Mock(side_effect=self.assessment)
        result = command.evaluate(self.fixture, self.output, assess=assess, model='fixture-model',
                                  case_ids=['possession-absence-v1-writing-empty'])
        assess.assert_not_called()
        self.assertEqual(result['results'][0]['status'], 'input_rejected')
        self.assertEqual(result['summary']['measured'], 0)

    def test_paid_selection_is_explicit_bounded_and_supported_work_stays_supported(self):
        assess = Mock(side_effect=self.assessment)
        for cases in ([], ['unknown'], [case['id'] for case in self.fixture['cases'] if case['stage'] == 'writing']):
            with self.assertRaises(ValueError):
                command.evaluate(self.fixture, self.output, assess=assess, model='fixture-model', case_ids=cases)
        assess.assert_not_called()
        result = command.evaluate(self.fixture, self.output, assess=assess, model='fixture-model',
                                  case_ids=['possession-absence-v1-writing-supported'])
        self.assertFalse(result['results'][0]['independent'])

    def test_fabricated_response_quote_is_rejected(self):
        def wrong_quote(unit, task, response):
            result = self.assessment(unit, task, response)
            result['criterion_report']['judgements'][0]['evidence'][0]['quote'] = 'a repaired answer'
            return result
        result = command.evaluate(self.fixture, self.output, assess=wrong_quote, model='fixture-model',
                                  case_ids=[self.case['id']])
        self.assertEqual(result['results'][0]['status'], 'failed')

    def test_summary_separates_disagreement_abstention_and_invalid_reports(self):
        rows = [dict(case_id='over', status='measured', expected='partial', actual='satisfied'),
                dict(case_id='miss', status='measured', expected='satisfied', actual='partial'),
                dict(case_id='abstain', status='measured', expected='satisfied', actual='insufficient_evidence'),
                dict(case_id='broken', status='failed', expected='satisfied', actual=None)]
        summary = command.summarise(rows)
        self.assertEqual(summary['overstated_success'], ['over'])
        self.assertEqual(summary['missed_success'], ['miss', 'abstain'])
        self.assertEqual(summary['abstentions'], ['abstain'])
        self.assertEqual(summary['measured'], 3)


if __name__ == '__main__':
    unittest.main()
