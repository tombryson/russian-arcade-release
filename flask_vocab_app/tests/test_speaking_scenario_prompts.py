"""Shared Speaking behaviour must follow the chosen role, not default to a café."""
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from services.conversation_ai import SCENARIO
from services.conversation_policy import cafe_instructions, scenario_instructions
from services.live_voice_provider import session_config
from services.speaking_assessment import SpeakingAssessment
from services.speaking_lifecycle import FINISH_TOOL, NaturalEnding, ending_instructions


def directions():
    return {
        'scenario_id': 'directions', 'role': 'A passer-by', 'role_ru': 'прохожий',
        'title': 'Find the museum', 'title_ru': 'Дорога к музею',
        'worker_brief': 'Помоги собеседнику дойти до музея. Он рядом с парком.',
        'reference': {'route': 'Идите прямо до парка, затем поверните направо.'},
        'menu': {}, 'goals': ['Ask the way', 'Check the turning'],
        'goals_ru': ['Спросите дорогу', 'Уточните поворот'],
        'goal_ids': ['route', 'turning'],
        'completion_criteria': ['The learner asks for the museum.', 'The learner confirms the turning.'],
        'closing_instruction': 'Когда маршрут понятен и собеседник прощается, пожелай хорошей прогулки.',
    }


def introduction():
    return {
        'scenario_id': 'meet-someone', 'role': 'A new acquaintance', 'role_ru': 'новый знакомый',
        'worker_brief': 'Ты Алексей. Вы знакомитесь на прогулке. Тебе нравится рисовать.',
        'reference': {'name': 'Алексей', 'hobby': 'рисование'}, 'menu': {},
        'goals': ['Introduce yourself', 'Ask about a hobby'],
        'goals_ru': ['Представьтесь', 'Спросите об увлечении'],
        'completion_criteria': ['The learner gives a name.', 'The learner asks about a hobby.'],
    }


class SpeakingScenarioPromptTests(unittest.TestCase):
    def test_live_and_delegated_roles_receive_scoped_curriculum_without_forcing_a_script(self):
        scenario = directions()
        scenario['learning_contract'] = {
            'target_level': 'A2',
            'requirements': [{'id': 'confirm-turn', 'kind': 'communicative',
                              'description': 'Confirm the turning beside the park.',
                              'evidence_hint': 'A learner question checks the turning.'}],
        }
        scenario['curriculum_context'] = {
            'topic_id': 'places', 'target_level': 'A2',
            'activity_brief': 'Ask for directions and clarify a detail.',
            'grammar_focus': ['Movement and destination'],
        }
        config = session_config({'model': 'chosen-live', 'voice': 'cedar', 'backend_model': 'chosen-backend'}, scenario)
        for prompt in (config['instructions'], config['delegation']['responses']['instructions']):
            self.assertIn('Ask for directions and clarify a detail.', prompt)
            self.assertIn('confirm-turn', prompt)
            self.assertIn('Весь учебный раздел не нужно проходить за один разговор', prompt)
            self.assertIn('Короткий понятный ответ и допустимые варианты остаются успешными', prompt)
            self.assertIn('не заставляй повторять заранее выбранную грамматическую конструкцию', prompt)
            self.assertIn('Не проговаривай цели, их идентификаторы', prompt)

    def assert_not_a_cafe(self, prompt):
        for phrase in ('кафе', 'заказ', 'посетител', 'café', 'customer', 'order', 'payment'):
            self.assertNotIn(phrase, prompt.casefold())

    def test_legacy_cafe_policy_is_preserved_verbatim(self):
        self.assertEqual(scenario_instructions(SCENARIO), cafe_instructions(SCENARIO))
        self.assertEqual(scenario_instructions({**SCENARIO, 'scenario_id': 'cafe'}), cafe_instructions(SCENARIO))

    def test_role_facts_and_language_policy_are_specific_to_directions(self):
        prompt = scenario_instructions(directions())
        self.assertIn('Ты — прохожий.', prompt)
        self.assertIn('Идите прямо до парка, затем поверните направо.', prompt)
        self.assertIn('Уточните поворот', prompt)
        self.assertIn('Английскую речь твой персонаж не понимает', prompt)
        self.assertIn('неправильные окончания, если смысл понятен', prompt)
        self.assert_not_a_cafe(prompt)

    def test_fallback_closing_does_not_add_a_purchase_to_meeting_someone(self):
        scenario = introduction()
        for backend in (False, True):
            with self.subTest(backend=backend):
                prompt = scenario_instructions(scenario) + ending_instructions(scenario, backend=backend)
                self.assertIn('Тебе нравится рисовать.', prompt)
                self.assertIn('The learner asks about a hobby.', prompt)
                self.assertIn('finish_speaking', prompt)
                self.assert_not_a_cafe(prompt)

    def test_selected_closing_and_tools_apply_to_live_and_backend_roles(self):
        scenario = directions()
        config = session_config({'model': 'chosen-live', 'voice': 'cedar', 'backend_model': 'chosen-backend'}, scenario)
        backend = config['delegation']['responses']
        self.assertEqual(config['model'], 'chosen-live')
        self.assertEqual(config['audio']['output']['voice'], 'cedar')
        self.assertEqual(backend['model'], 'chosen-backend')
        self.assertEqual(backend['tools'], [FINISH_TOOL])
        self.assertFalse(backend['parallel_tool_calls'])
        self.assert_not_a_cafe(FINISH_TOOL['description'])
        for prompt in (config['instructions'], backend['instructions']):
            self.assertIn('прохожий', prompt)
            self.assertIn(scenario['closing_instruction'], prompt)
            self.assertIn('The learner confirms the turning.', prompt)
            self.assert_not_a_cafe(prompt)

    def test_new_scenario_early_departure_does_not_require_cafe_goals(self):
        ending = NaturalEnding(introduction())
        ending.receive({'type': 'session.input_transcript.delta', 'delta': 'Мне пора. До свидания!', 'end_ms': 1000}, 1)
        result = ending._validate(json.dumps({
            'reason': 'learner_finished', 'learner_quote': 'Мне пора. До свидания!', 'goal_evidence': [],
        }))
        self.assertEqual(result['reason'], 'learner_finished')
        self.assertEqual(result['goal_evidence'], [])
        self.assertFalse(result['rewards_applied'])

    def test_task_completion_requires_only_selected_goals_and_exact_learner_evidence(self):
        ending = NaturalEnding(directions())
        ending.receive({'type': 'session.input_transcript.delta',
                        'delta': 'Как пройти к музею? У парка направо? Спасибо!', 'end_ms': 1000}, 1)
        result = ending._validate(json.dumps({
            'reason': 'task_complete', 'learner_quote': 'Спасибо!',
            'goal_evidence': [{'goal_index': 0, 'learner_quote': 'Как пройти к музею?'},
                              {'goal_index': 1, 'learner_quote': 'У парка направо?'}],
        }))
        self.assertEqual(result['reason'], 'task_complete')
        self.assertEqual(len(result['goal_evidence']), 2)

    def test_audio_review_gets_selected_role_and_goals_without_learner_asr(self):
        scenario = directions()
        transcript = 'Здравствуйте, скажите пожалуйста, как мне пройти отсюда к музею?'
        result = {
            'transcript': transcript, 'speech_status': 'russian', 'uncertain_phrases': [],
            'grammar': {'score': 5, 'reason': 'Your question was correctly formed.', 'evidence': ['к музею']},
            'fluency': {'score': 4, 'reason': 'You kept your question connected.', 'evidence': ['как мне пройти']},
            'goals': [{'id': 'route', 'status': 'completed', 'evidence': ['как мне пройти отсюда к музею']},
                      {'id': 'turning', 'status': 'not_yet', 'evidence': []}],
            'summary': 'You clearly asked for directions.', 'next_step': 'Try confirming the turning as well.',
            'corrections': [], 'uncertainty': '',
        }
        with tempfile.TemporaryDirectory() as temp:
            audio_path = Path(temp) / 'learner.wav'
            with wave.open(str(audio_path), 'wb') as output:
                output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                output.writeframes(struct.pack('<h', 1000) * 24000)
            with patch('openai.OpenAI') as factory:
                create = factory.return_value.chat.completions.create
                create.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
                    message=SimpleNamespace(content=json.dumps(result), refusal=None))])
                reviewed = SpeakingAssessment({'OPENAI_API_KEY': 'test-only-key'}).assess(
                    audio_path, scenario, [{'role': 'assistant', 'content': 'Вам к музею?'},
                                          {'role': 'user', 'content': 'ASR should not anchor the reviewer.'}])
                call = create.call_args.kwargs
        context = json.loads(call['messages'][1]['content'][0]['text'])
        self.assertEqual(context['scenario']['role_ru'], 'прохожий')
        self.assertEqual(context['scenario']['reference'], scenario['reference'])
        self.assertEqual([goal['id'] for goal in context['scenario']['goals']], ['route', 'turning'])
        self.assertEqual(context['other_speaker_context'], [{'role': 'assistant', 'content': 'Вам к музею?'}])
        self.assertNotIn('ASR should not anchor', str(call))
        self.assertNotIn('café worker', call['messages'][0]['content'])
        self.assertIn("selected scenario's goals and completion criteria", call['messages'][0]['content'])
        self.assertEqual(reviewed['grammar']['score'], 5)
        self.assertFalse(reviewed['rewards_applied'])


if __name__ == '__main__':
    unittest.main()
