"""Provider character-count errors never rewrite or invent learner evidence."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from contracts.curriculum import validate_judgements
from services.writing_service import WritingService, WritingUnavailable, _ground_criterion_spans


RESPONSE = 'Привет, Оля! 👋\nВ нашем городе есть парк. Иди прямо, потом поверни налево.\nЯ жду тебя в парк.'
TASK = {'title': 'Дорога в парк', 'title_en': 'The way to the park',
        'task': 'Напишите другу, как пройти в парк.',
        'task_en': 'Write a message telling a friend how to get to the park.',
        'required_words': ['город', 'парк', 'налево'], 'topic_id': 'places',
        'writing_focus': [{'requirement_id': 'a1.writing.personal-message',
                           'instruction_ru': 'Напишите другу, как пройти в парк.',
                           'instruction_en': 'Write a message telling a friend how to get to the park.'}]}


class WritingProviderSpanTests(unittest.TestCase):
    def setUp(self):
        self.service = WritingService.__new__(WritingService)
        self.service.client = Mock()
        self.output(TASK)
        self.task = self.service.generate_writing_task('places', 'A1', 30)
        self.contract = self.task['curriculum_contract']
        # These two wrong ranges came from the bounded live gpt-5-mini smoke
        # test. The quoted text is synthetic; no learner response is stored.
        self.report = {'contract_sha256': self.contract['contract_sha256'], 'judgements': [{
            'criterion_id': 'writing-focus-1', 'outcome': 'partial', 'score': 1,
            'feedback': 'The message gives directions; check the last location phrase.',
            'evidence': [{'quote': 'Иди прямо, потом поверни налево.', 'start': 41, 'end': 72},
                         {'quote': 'Я жду тебя в парк.', 'start': 73, 'end': 91}]}]}
        self.assessment = {'score': 6, 'strength': 'Your directions are understandable.',
                           'next_step': 'Use в парке for the place where you are waiting.',
                           'example': 'Я жду тебя в парке.', 'criterion_report': self.report}

    def output(self, value):
        self.service.client.responses.create.return_value = SimpleNamespace(
            status='completed', output_text=json.dumps(value))

    def assess(self, response=RESPONSE):
        return self.service.assess_writing(self.task['task'], self.task['required_words'], 30, response,
            difficulty='A1', language='en', topic='places', curriculum_contract=self.contract)

    def test_live_unicode_offset_failure_replays_through_provider_adapter_without_mutation(self):
        before = deepcopy(self.assessment)
        with self.assertRaisesRegex(ValueError, 'match the original response'):
            validate_judgements(self.contract, self.report, response_text=RESPONSE)
        self.output(self.assessment)
        checked = self.assess()
        self.assertEqual(self.assessment, before)
        self.assertEqual(checked['score'], 6)
        self.assertEqual(checked['criterion_report']['judgements'][0]['score'], 1)
        spans = checked['criterion_report']['judgements'][0]['evidence']
        for span in spans:
            self.assertEqual(RESPONSE[span['start']:span['end']], span['quote'])
            self.assertEqual(span['start'], RESPONSE.index(span['quote']))
        validate_judgements(self.contract, checked['criterion_report'], response_text=RESPONSE)
        sent = json.loads(self.service.client.responses.create.call_args.kwargs['input'][1]['content'])
        self.assertEqual(sent['russian_answer'], RESPONSE)

    def test_absent_or_ambiguous_quotation_does_not_become_accepted_evidence(self):
        for response, quote in ((RESPONSE, 'Я жду тебя в парке.'),
                                ('Я в парке. Я в парке.', 'Я в парке.'),
                                ('ааа', 'аа'), ('Я всё знаю.', 'Я все знаю.')):
            with self.subTest(response=response):
                report = deepcopy(self.report)
                report['judgements'][0]['evidence'] = [{'quote': quote, 'start': 1, 'end': 2}]
                self.output({**self.assessment, 'criterion_report': report})
                with self.assertRaises(WritingUnavailable):
                    self.assess(response)

    def test_already_valid_repeated_quote_keeps_its_original_occurrence(self):
        response = 'Я в парке. Я в парке.'
        quote = 'Я в парке.'
        start = response.rindex(quote)
        report = deepcopy(self.report)
        report['judgements'][0]['evidence'] = [{'quote': quote, 'start': start, 'end': start + len(quote)}]
        before = deepcopy(report)
        grounded = _ground_criterion_spans(report, response)
        self.assertEqual(grounded, before)
        self.assertEqual(report, before)
        self.assertIsNot(grounded, report)
        validate_judgements(self.contract, grounded, response_text=response)

    def test_grounding_does_not_hide_malformed_fields_or_relax_the_shared_validator(self):
        for change in ({'start': True}, {'start': '41'}, {'extra': 'unsupported'}):
            report = deepcopy(self.report)
            report['judgements'][0]['evidence'][0].update(change)
            self.output({**self.assessment, 'criterion_report': report})
            with self.subTest(change=change), self.assertRaises(WritingUnavailable):
                self.assess()


if __name__ == '__main__':
    unittest.main()
