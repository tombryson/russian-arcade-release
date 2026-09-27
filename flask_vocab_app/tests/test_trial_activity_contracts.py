"""Real activity requests pass through trial bounds and SDK serialization.

The HTTP transport is local and returns synthetic output. No credentials or
external providers are used. These tests catch incompatibilities hidden by a
mock of the SDK's create method.
"""
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from services.ai_trial_budget import AITrialBudget
from services.lesson_ai import LessonAI
from services.openai_service import OpenAIService
from services.trial_provider import openai_client
from services.word_jumble_service import WordJumbleService
from services.writing_service import WritingService
from tests.test_writing_generated_evidence import generated_task


class TrialActivityContractTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'budget.sqlite3'
        ledger = AITrialBudget(self.path, enabled=True)
        ledger.initialize()
        ledger.authorize_identity('verified-contract-user')
        self.config = {
            'HOSTED_AI_TRIAL': True, 'AI_TRIAL_ENABLED': True,
            'AI_TRIAL_IDENTITY': 'verified-contract-user',
            'AI_TRIAL_LEDGER_PATH': str(self.path),
            'OPENAI_API_KEY': 'test-only', 'OPENAI_MODEL_LESSONS': 'gpt-6-astra',
        }
        self.sent = []

    def client(self, payload):
        def respond(request):
            body = json.loads(request.content)
            self.sent.append(body)
            with sqlite3.connect(self.path) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM trial_requests WHERE state='reserved'"
                ).fetchone()[0], 1)
            text = json.dumps(payload, ensure_ascii=False)
            if request.url.path.endswith('/chat/completions'):
                data = {
                    'id': 'chat-contract', 'object': 'chat.completion', 'created': 0,
                    'model': body['model'],
                    'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
                        'role': 'assistant', 'content': text, 'refusal': None}}],
                    'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120},
                }
            else:
                data = {
                    'id': 'response-contract', 'object': 'response', 'created_at': 0,
                    'status': 'completed', 'model': body['model'],
                    'output': [{'id': 'message-contract', 'type': 'message', 'role': 'assistant',
                        'status': 'completed', 'content': [{'type': 'output_text',
                            'text': text, 'annotations': []}]}],
                    'usage': {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120},
                }
            return httpx.Response(200, json=data)

        client = openai_client(config=self.config, api_key='test-only',
            http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        self.addCleanup(client.close)
        return client

    def assert_settled(self):
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(self.sent[0]['store'])
        self.assertEqual(self.sent[0]['service_tier'], 'default')
        with sqlite3.connect(self.path) as conn:
            state, reserved, actual = conn.execute(
                'SELECT state,reserved,actual FROM trial_requests').fetchone()
        self.assertEqual(state, 'settled')
        self.assertLessEqual(reserved, 1_000_000)
        self.assertGreater(reserved, actual)

    def test_four_page_lesson_extraction_fits_admission_and_sdk(self):
        payload = {'pages': [{'slot': slot, 'text': 'Кот на столе.',
                             'annotations': '', 'uncertainty': ''} for slot in range(1, 5)]}
        client = self.client(payload)
        buffer = io.BytesIO()
        Image.new('RGB', (200, 300), 'white').save(buffer, 'JPEG')
        with patch('services.lesson_ai.openai_client', return_value=client):
            result = LessonAI(self.config).extract([buffer.getvalue()] * 4)
        self.assertEqual(len(result), 4)
        self.assertEqual(self.sent[0]['max_output_tokens'], 12000)
        images = [part for part in self.sent[0]['input'][0]['content'] if part['type'] == 'input_image']
        self.assertEqual([part['detail'] for part in images], ['high'] * 4)
        self.assert_settled()

    def test_contextual_flashcard_uses_real_chat_schema(self):
        payload = {'english': 'structures', 'sentence': 'Я занимаюсь изучением конструкций.',
                   'sentence_english': 'I am studying structures.', 'notes': ''}
        service = OpenAIService.__new__(OpenAIService)
        service.client = self.client(payload)
        service.flashcard_model = 'gpt-5.6-luna'
        result = service.generate_native_card({
            'lemma': 'конструкция', 'surface': 'конструкций',
            'pos': 'NOUN', 'grammar': {'case': 'gent', 'number': 'plur'}}, 'cloze')
        self.assertEqual(result, payload)
        self.assertEqual(self.sent[0]['max_completion_tokens'], 4096)
        self.assert_settled()

    def test_writing_activity_schema(self):
        payload = generated_task()
        service = WritingService.__new__(WritingService)
        service.client = self.client(payload)
        with patch('services.writing_service.model_for', return_value='gpt-5.6-luna'):
            result = service.generate_writing_task('any', 'beginner', 30)
        self.assertEqual(result['task'], payload['task'])
        self.assertEqual(result['curriculum_contract']['content']['writing_focus'], payload['writing_focus'])
        schema = self.sent[0]['text']['format']['schema']['properties']
        self.assertEqual(schema['writing_focus']['maxItems'], 2)
        self.assert_settled()

    def test_word_jumble_tutor_feedback_schema(self):
        payload = {'score': 4, 'commentary': 'Your sentence is clear and natural.',
            'corrections': [], 'polished_sentence': '', 'phrasing_note': '', 'extension': ''}
        service = WordJumbleService.__new__(WordJumbleService)
        service.client = self.client(payload)
        with patch('services.word_jumble_service.model_for', return_value='gpt-5.6-luna'):
            result = service._request_feedback({'words': ['кот', 'дом'], 'topic': 'any',
                'difficulty': 'easy'}, 'Кот дома.', 'en')
        self.assertEqual(result, payload)
        submitted = json.loads(self.sent[0]['input'][1]['content'])
        self.assertEqual(submitted['target_level'], 'A1')
        self.assertIsNone(submitted['curriculum'])  # Legacy games have no saved curriculum task.
        self.assert_settled()


if __name__ == '__main__':
    unittest.main()
