import base64
import json
import struct
import unittest

from services.conversation_ai import SCENARIO
from services.live_voice_provider import session_config
from services.speaking_lifecycle import NaturalEnding


def response(kind, *, delegation='d1', **data):
    return {'type': 'response.event', 'delegation_id': delegation, 'event': {'type': kind, **data}}


class NaturalEndingTests(unittest.TestCase):
    def setUp(self):
        self.ending = NaturalEnding(SCENARIO)

    def input(self, text, end=1000, now=1):
        return self.ending.receive({'type': 'session.input_transcript.delta', 'delta': text, 'end_ms': end}, now)

    def finish(self, arguments=None, *, call_id='call1', delegation='d1', now=3):
        arguments = arguments or {'reason': 'learner_finished', 'learner_quote': 'До свидания!', 'goal_evidence': []}
        self.ending.receive(response('response.created', delegation=delegation, response={'id': delegation}), now)
        self.ending.receive(response('response.output_item.done', delegation=delegation, item={
            'type': 'function_call', 'name': 'finish_speaking', 'call_id': call_id,
            'arguments': json.dumps(arguments, ensure_ascii=False),
        }), now)
        return self.ending.receive(response('response.completed', delegation=delegation, response={'id': delegation, 'output': []}), now)

    def goodbye(self, text='Всего доброго. До свидания!', now=5, amplitude=1000):
        self.ending.receive(response('response.created', delegation='d1', response={'id': 'r2'}), now)
        self.ending.receive(response('response.completed', delegation='d1', response={'id': 'r2', 'output': []}), now)
        self.ending.receive({'type': 'session.output_transcript.delta', 'delta': text}, now)
        self.ending.receive({'type': 'session.output_audio.delta',
            'delta': base64.b64encode(struct.pack('<h', amplitude) * 24000).decode()}, now)

    def test_tool_waits_for_completed_items_and_returns_supported_protocol(self):
        self.input('До свидания!')
        commands = self.finish()
        self.assertEqual([c['type'] for c in commands], ['response.item.create', 'response.create'])
        result = commands[0]['item']
        self.assertEqual(result['type'], 'function_call_output')
        self.assertTrue(json.loads(result['output'])['accepted'])
        self.assertEqual(set(commands[1]), {'type', 'event_id'})
        self.assertIsNone(self.ending.tick(4))

    def test_natural_finish_requires_audio_and_drain_and_is_once(self):
        self.input('До свидания!')
        self.finish()
        self.goodbye()
        self.assertIsNone(self.ending.tick(7.9))
        self.assertEqual(self.ending.tick(8), 'learner_finished')
        self.assertIsNone(self.ending.tick(9))
        self.assertEqual(self.ending.completion['basis'], 'agent_assessment')
        self.assertFalse(self.ending.completion['rewards_applied'])

    def test_farewell_word_alone_never_ends_conversation(self):
        self.input('Что значит до свидания?')
        self.goodbye()
        self.assertIsNone(self.ending.tick(50))

    def test_task_success_requires_actual_evidence_for_every_goal(self):
        self.input('Мне чай и булочку. Сколько стоит?')
        evidence = [{'goal_index': 0, 'learner_quote': 'Мне чай'},
                    {'goal_index': 1, 'learner_quote': 'булочку'},
                    {'goal_index': 2, 'learner_quote': 'Сколько стоит?'}]
        result = self.finish({'reason': 'task_complete', 'learner_quote': 'Сколько стоит?', 'goal_evidence': evidence})
        self.assertTrue(json.loads(result[0]['item']['output'])['accepted'])
        self.goodbye()
        self.assertEqual(self.ending.tick(8), 'task_complete')

    def test_missing_goal_or_invented_corrected_quote_rejected(self):
        self.input('Я хотеть чай без сахар')
        for index, evidence in enumerate(([], [{'goal_index': 0, 'learner_quote': 'Я хочу чай без сахара'}])):
            result = self.finish({'reason': 'task_complete', 'learner_quote': 'Я хотеть чай', 'goal_evidence': evidence},
                                 call_id=f'call{index}', delegation=f'd{index}')
            self.assertFalse(json.loads(result[0]['item']['output'])['accepted'])
        self.assertFalse(self.ending.pending)

    def test_english_cannot_complete_even_with_previous_russian_quote(self):
        self.input('До свидания!')
        self.input(' How do I say goodbye?', end=2000)
        result = self.finish()
        self.assertFalse(json.loads(result[0]['item']['output'])['accepted'])

    def test_new_learner_speech_cancels_pending_farewell(self):
        self.input('До свидания!')
        self.finish()
        self.goodbye()
        self.input('А можно ещё воды?', end=2000, now=6)
        self.assertIsNone(self.ending.tick(8))
        self.assertEqual(self.ending.abandoned_reason, 'learner_continued')
        self.assertIsNone(self.ending.completion)

    def test_silent_or_missing_farewell_times_out_without_success(self):
        self.input('До свидания!')
        self.finish()
        self.goodbye(amplitude=0)
        self.assertIsNone(self.ending.tick(8))
        self.assertIsNone(self.ending.tick(33))
        self.assertEqual(self.ending.abandoned_reason, 'farewell_not_confirmed')
        self.assertIsNone(self.ending.completion)

    def test_another_question_after_goodbye_does_not_close(self):
        self.input('До свидания!')
        self.finish()
        self.goodbye('До свидания! Вам ещё что-нибудь?')
        self.assertIsNone(self.ending.tick(8))

    def test_duplicate_function_call_does_not_execute_or_continue_again(self):
        self.input('До свидания!')
        self.finish()
        self.assertEqual(self.finish(delegation='d2'), [])

    def test_unwrapped_events_and_arguments_done_are_not_tools(self):
        self.input('До свидания!')
        self.assertEqual(self.ending.receive({'type': 'response.output_item.done', 'item': {'type': 'function_call'}}), [])
        self.assertEqual(self.ending.receive(response('response.function_call_arguments.done', arguments='{}')), [])
        self.assertFalse(self.ending.pending)

    def test_unrelated_backend_completion_cannot_confirm_farewell(self):
        self.input('До свидания!')
        self.finish()
        self.ending.receive(response('response.created', delegation='other', response={'id': 'other-response'}), 4)
        self.ending.receive(response('response.completed', delegation='other', response={'id': 'other-response'}), 4)
        self.ending.receive({'type': 'session.output_transcript.delta', 'delta': 'До свидания!'}, 5)
        self.ending.receive({'type': 'session.output_audio.delta',
            'delta': base64.b64encode(struct.pack('<h', 1000) * 24000).decode()}, 5)
        self.assertIsNone(self.ending.tick(8))

    def test_seed_instructions_and_selected_voice_models_are_preserved(self):
        scenario = {**SCENARIO, 'worker_brief': 'Сегодня булочки закончились.',
                    'goals_ru': ['Закажите напиток', 'Выберите замену', 'Узнайте цену']}
        config = session_config({'model': 'chosen-live', 'voice': 'cedar', 'backend_model': 'chosen-backend'}, scenario)
        self.assertEqual(config['model'], 'chosen-live')
        self.assertEqual(config['audio']['output']['voice'], 'cedar')
        backend = config['delegation']['responses']
        self.assertEqual(backend['model'], 'chosen-backend')
        self.assertEqual([tool['name'] for tool in backend['tools']], ['finish_speaking'])
        self.assertFalse(backend['parallel_tool_calls'])
        for prompt in (config['instructions'], backend['instructions']):
            self.assertIn('Сегодня булочки закончились.', prompt)
            self.assertIn('Выберите замену', prompt)


if __name__ == '__main__':
    unittest.main()
