"""A reply to one prompt cannot stand in for responding to the other."""
from copy import deepcopy
import unittest

from services.curriculum_sequence_content import load_asset, task_contract
from services.unit_exchange import turn_windows, validate_turn_evidence


class UnitExchangeTurnEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.contract = task_contract(load_asset('location-exchange-v1'), 'turn-timing-check', purpose='diagnostic')
        self.source = {'duration_ms': 5000, 'recordings': [
            {'turn_id': 'location', 'start_ms': 0, 'end_ms': 2100},
            {'turn_id': 'destination', 'start_ms': 2100, 'end_ms': 5000}]}
        spans = {'location': {'start_ms': 100, 'end_ms': 1900},
                 'destination': {'start_ms': 2400, 'end_ms': 4800}}
        self.report = {'criterion_report': {'contract_sha256': self.contract['contract_sha256'], 'judgements': [
            {'criterion_id': c['id'], 'outcome': 'satisfied', 'score': c['max_score'], 'reason_code': None,
             'feedback': 'The reply supplies the requested information.',
             'evidence': [deepcopy(spans[turn]) for turn in self.contract['content']['criterion_turns'][c['id']]]}
            for c in self.contract['criteria']]}}

    def test_distinct_reply_intervals_bind_the_heard_prompts(self):
        windows = turn_windows(self.contract, self.source['recordings'], self.source['duration_ms'])
        self.assertEqual(windows[1]['prompt'], 'Понятно. А куда ты идёшь?')
        self.assertEqual(windows[1]['start_ms'], 2100)
        self.assertEqual(set(windows[1]['criterion_ids']), {'next-place', 'destination-form', 'understandable-places'})
        self.assertIs(validate_turn_evidence(self.contract, self.report, self.source), self.report)

    def test_first_reply_cannot_supply_all_exchange_credit(self):
        for identity in ('next-place', 'destination-form', 'understandable-places'):
            with self.subTest(identity=identity):
                report = deepcopy(self.report)
                next(j for j in report['criterion_report']['judgements'] if j['criterion_id'] == identity)['evidence'] = [
                    {'start_ms': 100, 'end_ms': 1900}]
                with self.assertRaises(ValueError):
                    validate_turn_evidence(self.contract, report, self.source)

    def test_a_span_crossing_the_reply_boundary_is_not_grounded_evidence(self):
        report = deepcopy(self.report)
        report['criterion_report']['judgements'][0]['evidence'] = [{'start_ms': 100, 'end_ms': 4800}]
        with self.assertRaises(ValueError):
            validate_turn_evidence(self.contract, report, self.source)

    def test_silent_second_reply_can_remain_unscored_without_erasing_first(self):
        report = deepcopy(self.report)
        for judgement in report['criterion_report']['judgements']:
            if 'destination' in self.contract['content']['criterion_turns'][judgement['criterion_id']]:
                judgement.update(outcome='insufficient_evidence', score=None, evidence=[], reason_code='insufficient_response')
        validate_turn_evidence(self.contract, report, self.source)
        self.assertEqual(report['criterion_report']['judgements'][0]['score'], 1)

    def test_gaps_reordered_or_truncated_recording_intervals_are_rejected(self):
        for source in (
            {'duration_ms': 5000, 'recordings': list(reversed(self.source['recordings']))},
            {'duration_ms': 5100, 'recordings': self.source['recordings']},
            {'duration_ms': 5000, 'recordings': [self.source['recordings'][0],
                {'turn_id': 'destination', 'start_ms': 2200, 'end_ms': 5000}]},
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                turn_windows(self.contract, source['recordings'], source['duration_ms'])


if __name__ == '__main__':
    unittest.main()
