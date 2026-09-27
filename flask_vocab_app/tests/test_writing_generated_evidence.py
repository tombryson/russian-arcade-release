"""New Writing tasks freeze an explicit, bounded focus before any response."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from contracts.curriculum import validate_task_contract
from services.torfl_requirements import reference_for_level
from services.vocabulary_topics import TOPICS
from services.writing_service import WritingService, WritingUnavailable


TASK = {'title': 'Письмо другу', 'title_en': 'A message to a friend',
        'task': 'Напишите другу о вашей семье. Расскажите, кто живёт с вами.',
        'task_en': 'Write a message to a friend about your family. Say who lives with you.',
        'required_words': ['семья', 'жить', 'вместе']}
WRITING_IDS = {'A1': 'a1.writing.personal-message', 'A2': 'a2.writing.personal-correspondence',
               'B1': 'b1.writing.purposeful-message', 'B2': 'b2.writing.correspondence-register'}


def generated_task(level='A1', topic='family'):
    return {**deepcopy(TASK), 'topic_id': topic, 'writing_focus': [{
        'requirement_id': WRITING_IDS[level], 'instruction_ru': TASK['task'], 'instruction_en': TASK['task_en']}]}


class GeneratedWritingEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.service = WritingService.__new__(WritingService)
        self.service.client = Mock()

    def output(self, value):
        self.service.client.responses.create.return_value = SimpleNamespace(
            status='completed', output_text=json.dumps(value))

    def test_each_referenced_level_uses_only_its_writing_candidates_and_exact_task(self):
        for level in WRITING_IDS:
            with self.subTest(level=level):
                self.output(generated_task(level))
                result = self.service.generate_writing_task('family', level, 30)
                frozen = validate_task_contract(result['curriculum_contract'])
                self.assertEqual(frozen['level'], level)
                self.assertEqual(frozen['topic_ids'], ['family'])
                self.assertEqual(frozen['content']['requested_topic'], 'family')
                for key in TASK:
                    self.assertEqual(frozen['content'][key], result[key])
                criterion = frozen['criteria'][0]
                self.assertEqual((criterion['response_mode'], criterion['evidence_scope']), ('independent_writing', 'reference'))
                self.assertEqual(criterion['expectation'], TASK['task_en'])
                expected = {item['id']: item for item in reference_for_level(level)['requirements'] if item['domain'] == 'writing'}
                self.assertEqual(criterion['source_refs'], expected[WRITING_IDS[level]]['source_refs'])
                sent = self.service.client.responses.create.call_args.kwargs
                payload = json.loads(sent['input'][1]['content'])
                self.assertEqual({item['id'] for item in payload['writing_focus_candidates']}, set(expected))
                schema = sent['text']['format']['schema']['properties']
                self.assertEqual(schema['topic_id']['enum'], ['family'])
                focus = schema['writing_focus']
                self.assertEqual((focus['minItems'], focus['maxItems']), (1, 2))
                self.assertFalse(focus['items']['additionalProperties'])
                self.assertEqual(set(focus['items']['properties']['requirement_id']['enum']), set(expected))
                self.assertEqual(sent['max_output_tokens'], 4096)
                self.assertEqual(sent['reasoning'], {'effort': 'low'})
                self.assertFalse(sent['store'])

    def test_any_records_selected_canonical_topic_without_changing_the_request(self):
        self.output(generated_task())
        result = self.service.generate_writing_task('any', 'beginner', 30)
        frozen = result['curriculum_contract']
        self.assertEqual(frozen['content']['requested_topic'], 'any')
        self.assertEqual(frozen['content']['topic_id'], 'family')
        sent = self.service.client.responses.create.call_args.kwargs
        self.assertEqual(sent['text']['format']['schema']['properties']['topic_id']['enum'], list(TOPICS))
        self.assertEqual(json.loads(sent['input'][1]['content'])['topic'], 'any')

    def test_two_distinct_visible_focuses_are_allowed(self):
        task = generated_task()
        task['writing_focus'].append({'requirement_id': 'a1.writing.connected-description',
                                     'instruction_ru': 'Расскажите, кто живёт с вами.',
                                     'instruction_en': 'Say who lives with you.'})
        self.output(task)
        result = self.service.generate_writing_task('family', 'A1', 30)
        self.assertEqual(len(result['curriculum_contract']['criteria']), 2)

    def test_invalid_focus_never_silently_becomes_an_uncontracted_task(self):
        invalid = []
        for rid in ('invented', 'a1.language.prepositional-location', 'b2.writing.formal-document', {}, None):
            task = generated_task()
            task['writing_focus'][0]['requirement_id'] = rid
            invalid.append(task)
        for focus in ([], {}, [generated_task()['writing_focus'][0]] * 2, [generated_task()['writing_focus'][0]] * 3):
            invalid.append({**generated_task(), 'writing_focus': focus})
        for field, value in (('instruction_en', 'Hidden requirement.'), ('instruction_ru', ''), ('instruction_en', [])):
            task = generated_task()
            task['writing_focus'][0][field] = value
            invalid.append(task)
        for topic in ('any', 'invented', 'law', []):
            invalid.append({**generated_task(), 'topic_id': topic})
        invalid.extend([deepcopy(TASK), {**generated_task(), 'curriculum_contract': {}},
                        {**generated_task(), 'extra': 'not allowed'}])
        extra_focus = generated_task()
        extra_focus['writing_focus'][0]['score'] = 2
        invalid.append(extra_focus)
        for task in invalid:
            with self.subTest(task=task):
                self.output(task)
                with self.assertRaises(WritingUnavailable):
                    self.service.generate_writing_task('family', 'A1', 30)

    def test_c1_c2_keep_the_existing_contractless_task_shape(self):
        for level in ('C1', 'C2'):
            with self.subTest(level=level):
                self.output(TASK)
                self.assertEqual(self.service.generate_writing_task('law', level, 30), TASK)
                sent = self.service.client.responses.create.call_args.kwargs
                self.assertEqual(set(sent['text']['format']['schema']['properties']), set(TASK))
                self.assertNotIn('writing_focus_candidates', json.loads(sent['input'][1]['content']))


if __name__ == '__main__':
    unittest.main()
