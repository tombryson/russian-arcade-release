"""Generation instructions keep criterion metadata out of learner-facing tasks."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from services.writing_service import WritingService
from tests.test_writing_generated_evidence import TASK, generated_task


class WritingPromptConstraintTests(unittest.TestCase):
    def test_reference_focus_is_extracted_from_one_coherent_task_without_repeating_it(self):
        service = WritingService.__new__(WritingService)
        service.client = Mock()
        service.client.responses.create.return_value = SimpleNamespace(
            status='completed', output_text=json.dumps(generated_task()))
        service.generate_writing_task('family', 'A1', 30)
        sent = service.client.responses.create.call_args.kwargs
        instruction = sent['input'][0]['content']
        for policy in ('one situation and one clear communicative purpose',
                       "learner's role and recipient consistent",
                       '1–3 short sentences in each language',
                       'Prefer one focus. Add a second only when',
                       'State each chosen demand once',
                       'Extract those excerpts from the finished instructions',
                       'never append a repeated requirement'):
            self.assertIn(policy, instruction)
        self.assertEqual(sent['max_output_tokens'], 4096)
        self.assertEqual(sent['reasoning'], {'effort': 'low'})
        self.assertTrue(sent['text']['format']['strict'])
        self.assertEqual(set(sent['text']['format']['schema']['properties']),
                         {*TASK, 'topic_id', 'writing_focus'})

    def test_levels_without_reference_contracts_still_request_concise_coherent_instructions(self):
        service = WritingService.__new__(WritingService)
        service.client = Mock()
        service.client.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(TASK))
        service.generate_writing_task('family', 'C1', 30)
        sent = service.client.responses.create.call_args.kwargs
        instruction = sent['input'][0]['content']
        self.assertIn('one situation and one clear communicative purpose', instruction)
        self.assertIn('no repeated directions or assessment labels', instruction)
        self.assertNotIn('writing_focus requirements', instruction)
        self.assertEqual(set(sent['text']['format']['schema']['properties']), set(TASK))


if __name__ == '__main__':
    unittest.main()
