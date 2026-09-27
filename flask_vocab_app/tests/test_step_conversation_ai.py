"""Step-through generation uses bounded, validated output and metered providers.

All provider transport is synthetic; these tests never use credentials or make
external requests.
"""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx

from services.ai_trial_budget import AITrialBudget, TrialDenied
from services.conversation_ai import ConversationAI
from services.speech_provider import SpeechError
from services.step_conversation_ai import STEP_SCHEMA, dialogue_schema, validate_dialogue
from services.trial_provider import openai_client


def dialogue(turn_count=4):
    def option(russian, english):
        return {'russian': russian, 'english': english,
                'explanation': {'en': 'Use the form that fits this question.',
                                'ru': 'Выберите форму для этого вопроса.'}}

    return {
        'turns': [
            {'npc': {'russian': f'Вопрос номер {index + 1}: куда вы идёте?',
                     'english': f'Question {index + 1}: where are you going?'},
             'intent': {'en': 'Say you are going to the museum.',
                        'ru': 'Скажите, что вы идёте в музей.'},
             'hint': {'en': 'Use в with the accusative for a destination.',
                      'ru': 'Используйте в с винительным падежом.'},
             'correct': option('Я иду в музей.', 'I am going to the museum.'),
             'distractors': [option('Я иду в музея.', 'I am going to the museum.'),
                             option('Я иду на музеем.', 'I am going to the museum.')]}
            for index in range(turn_count)
        ],
        'ending': {'russian': 'Хорошей прогулки! До свидания!',
                   'english': 'Enjoy your walk! Goodbye!'},
    }


def scenario():
    # No café menu: using the archived café reply prompt would fail here.
    return {'id': 'directions-test-v1', 'seed': 'directions-test-v1',
            'scenario_id': 'directions', 'target_level': 'A1',
            'title': 'Find the museum', 'role_ru': 'прохожий',
            'reference': {'destination': 'музей'},
            'goals': ['Ask the way', 'Confirm the destination'],
            'learning_contract': {'target_level': 'A1',
                                  'grammar_focus': ['Movement with в'],
                                  'vocabulary_focus': ['музей', 'идти']}}


def dialogue_for_scenario(selected):
    """Synthetic protocol/service fixture, not evidence of linguistic correctness."""
    raw = dialogue()
    requirements = selected.get('learning_contract', {}).get('requirements')
    if requirements:
        raw['coverage'] = [{'requirement_id': requirement['id'], 'turn': 1,
                            'role': 'learner', 'quote': raw['turns'][0]['correct']['russian']}
                           for requirement in requirements]
    return raw


def curriculum_scenario():
    selected = scenario()
    selected['curriculum_context'] = {
        'curriculum_version': 1, 'topic_id': 'places', 'target_level': 'A1',
        'activity_brief': 'Ask for a destination and confirm a direction.',
        'level_guidance': {'speaking': 'Use familiar short exchanges.'},
    }
    selected['learning_contract']['requirements'] = [
        {'id': 'state-destination', 'kind': 'communicative',
         'description': 'Tell the resident where you are going.',
         'evidence_hint': 'The learner names the museum as their destination.'},
        {'id': 'destination-case', 'kind': 'grammar',
         'description': 'Use в with an accusative destination.',
         'evidence_hint': 'A learner phrase such as в музей specifies a destination.'},
    ]
    return selected


class StepDialogueValidationTests(unittest.TestCase):
    def test_curriculum_coverage_requires_every_target_and_preserves_exact_evidence(self):
        selected = curriculum_scenario()
        raw = dialogue_for_scenario(selected)
        raw['coverage'][1]['quote'] = 'в музей'
        original = deepcopy(raw)
        result = validate_dialogue(raw, selected)
        self.assertEqual(result['coverage'], raw['coverage'])
        self.assertEqual(raw, original)

    def test_coverage_rejects_missing_unknown_repeated_and_extra_targets(self):
        selected = curriculum_scenario()
        for change in ('absent', 'missing', 'unknown', 'repeated', 'extra'):
            with self.subTest(change=change):
                raw = dialogue_for_scenario(selected)
                if change == 'absent':
                    del raw['coverage']
                elif change == 'missing':
                    raw['coverage'].pop()
                elif change == 'unknown':
                    raw['coverage'][0]['requirement_id'] = 'invented-target'
                elif change == 'repeated':
                    raw['coverage'][1]['requirement_id'] = raw['coverage'][0]['requirement_id']
                else:
                    raw['coverage'].append(deepcopy(raw['coverage'][0]))
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw, selected)

    def test_coverage_rejects_npc_distractor_hint_and_fabricated_quotes(self):
        selected = curriculum_scenario()
        for quote in ('Вопрос номер', 'Я иду в музея.', 'винительным', 'Я хочу в музей.', 'музе', 'в'):
            with self.subTest(quote=quote):
                raw = dialogue_for_scenario(selected)
                raw['coverage'][0]['quote'] = quote
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw, selected)
        raw = dialogue_for_scenario(selected)
        raw['coverage'][0].update(role='npc', quote=raw['turns'][0]['npc']['russian'])
        with self.assertRaises(SpeechError):
            validate_dialogue(raw, selected)

    def test_evidence_must_match_its_referenced_turn_without_correcting_endings(self):
        selected = curriculum_scenario()
        for turn in (0, 5, True, '1', None):
            with self.subTest(turn=turn):
                raw = dialogue_for_scenario(selected)
                raw['coverage'][0]['turn'] = turn
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw, selected)
        raw = dialogue_for_scenario(selected)
        raw['turns'][1]['correct']['russian'] = 'Я иду в парк.'
        raw['coverage'][0]['turn'] = 2
        with self.assertRaises(SpeechError):
            validate_dialogue(raw, selected)

    def test_schema_carries_only_selected_requirement_ids_without_mutating_legacy_schema(self):
        original = deepcopy(STEP_SCHEMA)
        selected = curriculum_scenario()
        schema = dialogue_schema(selected)
        coverage = schema['properties']['coverage']
        self.assertEqual(coverage['minItems'], 2)
        self.assertEqual(coverage['maxItems'], 2)
        self.assertEqual(coverage['items']['properties']['requirement_id']['enum'],
                         ['state-destination', 'destination-case'])
        self.assertEqual(STEP_SCHEMA, original)
        self.assertEqual(dialogue_schema(scenario()), STEP_SCHEMA)
        self.assertNotIn('coverage', validate_dialogue(dialogue(), scenario()))

    def test_malformed_authored_contract_is_rejected_before_generation(self):
        for requirements in ([], None, {}, [{'id': 'unfinished'}]):
            selected = curriculum_scenario()
            selected['learning_contract']['requirements'] = requirements
            with self.subTest(requirements=requirements), self.assertRaises(SpeechError):
                dialogue_schema(selected)

    def test_npc_cannot_speak_the_learners_exact_question_in_either_word_order(self):
        for npc, reply in (
                ('Хорошо, один билет. Когда поезд отправляется?', 'Когда отправляется поезд?'),
                ('Поезд в десять утра. Сколько стоит билет?', 'Сколько стоит билет?')):
            with self.subTest(npc=npc):
                raw = dialogue()
                raw['turns'][0]['npc']['russian'] = npc
                raw['turns'][0]['correct']['russian'] = reply
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)

    def test_npc_statement_allows_learner_question_and_different_questions_are_valid(self):
        for npc in ('Да, места есть.', 'Вы хотите билет на сегодня?'):
            raw = dialogue()
            raw['turns'][0]['npc']['russian'] = npc
            raw['turns'][0]['correct']['russian'] = 'Когда отправляется поезд?'
            self.assertEqual(validate_dialogue(raw)['turns'][0]['npc']['russian'], npc)

    def test_hint_cannot_be_a_verbatim_copy_of_intent(self):
        for language in ('en', 'ru'):
            raw = dialogue()
            raw['turns'][0]['hint'][language] = raw['turns'][0]['intent'][language]
            with self.assertRaises(SpeechError):
                validate_dialogue(raw)

    def test_four_to_six_turns_are_accepted_without_mutating_provider_data(self):
        for count in (4, 5, 6):
            with self.subTest(count=count):
                raw = dialogue(count)
                original = deepcopy(raw)
                result = validate_dialogue(raw)
                self.assertEqual(len(result['turns']), count)
                self.assertEqual(result['ending'], raw['ending'])
                self.assertEqual(raw, original)

    def test_strict_schema_requires_all_fields_recursively(self):
        def check(value):
            if not isinstance(value, dict):
                return
            if value.get('type') == 'object':
                self.assertIs(value.get('additionalProperties'), False)
                self.assertEqual(set(value.get('required', [])),
                                 set(value.get('properties', {})))
            for child in value.values():
                if isinstance(child, dict):
                    check(child)
                elif isinstance(child, list):
                    for item in child:
                        check(item)
        check(STEP_SCHEMA)
        check(dialogue_schema(curriculum_scenario()))

    def test_bad_top_level_and_turn_counts_fail_closed(self):
        for raw in (None, [], '', {}, {'turns': []}, dialogue(0), dialogue(3), dialogue(7)):
            with self.subTest(raw=raw):
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)

    def test_missing_nested_fields_and_wrong_types_are_rejected(self):
        for path in (('npc', 'russian'), ('npc', 'english'), ('intent', 'en'),
                     ('intent', 'ru'), ('hint', 'en'), ('hint', 'ru'),
                     ('correct', 'russian'), ('correct', 'explanation')):
            with self.subTest(path=path):
                raw = dialogue()
                del raw['turns'][0][path[0]][path[1]]
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)
        for key, value in (('npc', []), ('intent', 'say hello'), ('hint', None),
                           ('correct', False), ('distractors', {})):
            with self.subTest(key=key, value=value):
                raw = dialogue()
                raw['turns'][0][key] = value
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)

    def test_malformed_option_explanations_and_ending_are_rejected(self):
        for field in ('correct', 'distractor'):
            for value in ({'en': 'An explanation'}, {'en': [], 'ru': 'Подсказка'},
                          {'en': 'Use this form.', 'ru': ''}, None):
                with self.subTest(field=field, value=value):
                    raw = dialogue()
                    option = (raw['turns'][0]['correct'] if field == 'correct' else
                              raw['turns'][0]['distractors'][0])
                    option['explanation'] = value
                    with self.assertRaises(SpeechError):
                        validate_dialogue(raw)
        for value in ({'english': 'Goodbye!'}, {'russian': 'Пока!'}, None, []):
            with self.subTest(ending=value):
                raw = dialogue()
                raw['ending'] = value
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)

    def test_empty_overlong_or_non_string_text_is_rejected(self):
        for value in ('', '  \n\t ', 'Я' * 20000, None, 7, ['Привет']):
            with self.subTest(value=repr(value)[:80]):
                raw = dialogue()
                raw['turns'][0]['npc']['russian'] = value
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)

    def test_russian_dialogue_options_and_ending_require_cyrillic(self):
        for target in ('npc', 'correct', 'distractor', 'ending'):
            with self.subTest(target=target):
                raw = dialogue()
                field = (raw['ending'] if target == 'ending' else
                         raw['turns'][0]['distractors'][0] if target == 'distractor' else
                         raw['turns'][0][target])
                field['russian'] = 'Hello, where are you going?'
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)

    def test_exactly_two_distractors_are_required(self):
        for count in (0, 1, 3):
            with self.subTest(count=count):
                raw = dialogue()
                raw['turns'][0]['distractors'] = [deepcopy(raw['turns'][0]['distractors'][0])
                                                for _ in range(count)]
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)

    def test_case_and_punctuation_do_not_make_distinct_answers(self):
        for value in ('Я иду в музей.', 'я иду в музей!', '  Я иду в музей?  '):
            with self.subTest(value=value):
                raw = dialogue()
                raw['turns'][0]['distractors'][0]['russian'] = value
                with self.assertRaises(SpeechError):
                    validate_dialogue(raw)
        raw = dialogue()
        raw['turns'][0]['distractors'][1]['russian'] = 'Я ИДУ В МУЗЕЯ!'
        with self.assertRaises(SpeechError):
            validate_dialogue(raw)

    def test_duplicate_npc_prompts_are_rejected(self):
        raw = dialogue()
        raw['turns'][1]['npc']['russian'] = raw['turns'][0]['npc']['russian'].upper()
        with self.assertRaises(SpeechError):
            validate_dialogue(raw)


class StepDialogueProviderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.ledger_path = Path(directory.name) / 'trial.sqlite3'
        self.ledger = AITrialBudget(self.ledger_path, enabled=True)
        self.ledger.initialize()
        self.ledger.authorize_identity('step-test-account')
        self.config = {'HOSTED_AI_TRIAL': True, 'AI_TRIAL_ENABLED': True,
                       'AI_TRIAL_IDENTITY': 'step-test-account',
                       'AI_TRIAL_LEDGER_PATH': str(self.ledger_path),
                       'OPENAI_API_KEY': 'synthetic-only',
                       'CONVERSATION_MODEL': 'gpt-5.6-luna'}
        self.sent = []

    def client(self, payload, config=None):
        def respond(request):
            body = json.loads(request.content)
            self.sent.append(body)
            with sqlite3.connect(self.ledger_path) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM trial_requests WHERE state='reserved'"
                ).fetchone()[0], 1)
            return httpx.Response(200, json={
                'id': 'step-test', 'object': 'chat.completion', 'created': 0,
                'model': body['model'],
                'choices': [{'index': 0, 'finish_reason': 'stop',
                             'message': {'role': 'assistant', 'refusal': None,
                                         'content': json.dumps(payload, ensure_ascii=False)}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120},
            })
        client = openai_client(config=config or self.config, api_key='synthetic-only',
                               http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        self.addCleanup(client.close)
        return client

    def test_selected_non_cafe_snapshot_and_level_reach_single_schema_call(self):
        ai = ConversationAI(self.config)
        selected = scenario()
        with patch.object(ai, '_call', return_value=dialogue()) as call:
            result = ai.step_dialogue(selected)
        call.assert_called_once()
        name, instructions, data, schema = call.call_args.args
        self.assertEqual(name, 'step_conversation')
        self.assertEqual(data, {'scenario': selected})
        self.assertEqual(schema, STEP_SCHEMA)
        self.assertIn('A1', instructions)
        self.assertEqual(len(result['turns']), 4)

    def test_curriculum_contract_reaches_one_generation_and_coverage_is_enforced(self):
        ai = ConversationAI(self.config)
        selected = curriculum_scenario()
        with patch.object(ai, '_call', return_value=dialogue_for_scenario(selected)) as call:
            result = ai.step_dialogue(selected)
        call.assert_called_once()
        _, instructions, data, schema = call.call_args.args
        self.assertEqual(data['scenario']['curriculum_context'], selected['curriculum_context'])
        self.assertIn('state-destination', instructions)
        self.assertIn('not every objective from the wider topic', instructions)
        self.assertIn('CORRECT LEARNER reply', instructions)
        self.assertEqual(schema, dialogue_schema(selected))
        self.assertEqual(len(result['coverage']), 2)
        # A structurally valid generic dialogue cannot bypass the new contract.
        with patch.object(ai, '_call', return_value=dialogue()) as call:
            with self.assertRaises(SpeechError):
                ai.step_dialogue(selected)
        call.assert_called_once()

    def test_invalid_curriculum_contract_does_not_purchase_a_request(self):
        ai = ConversationAI(self.config)
        selected = curriculum_scenario()
        selected['learning_contract']['requirements'][1]['id'] = 'state-destination'
        with patch.object(ai, '_call') as call:
            with self.assertRaises(SpeechError):
                ai.step_dialogue(selected)
        call.assert_not_called()

    def test_real_call_uses_current_model_and_settles_one_metered_request(self):
        client = self.client(dialogue())
        with patch('services.conversation_ai.openai_client', return_value=client):
            result = ConversationAI(self.config).step_dialogue(scenario())
        self.assertEqual(len(result['turns']), 4)
        self.assertEqual(len(self.sent), 1)
        body = self.sent[0]
        self.assertEqual(body['model'], self.config['CONVERSATION_MODEL'])
        self.assertIn(body['max_completion_tokens'], (4096, 8192))
        self.assertFalse(body['store'])
        self.assertEqual(body['service_tier'], 'default')
        self.assertEqual(body['response_format']['json_schema']['schema'], STEP_SCHEMA)
        self.assertEqual(json.loads(body['messages'][1]['content']), {'scenario': scenario()})
        with sqlite3.connect(self.ledger_path) as conn:
            self.assertEqual(conn.execute('SELECT state FROM trial_requests').fetchall(), [('settled',)])

    def test_paused_missing_or_unrecognized_identity_never_reaches_transport(self):
        for overrides in ({'AI_TRIAL_ENABLED': False}, {'AI_TRIAL_IDENTITY': ''},
                          {'AI_TRIAL_IDENTITY': 'unknown-account'}, {'AI_TRIAL_LEDGER_PATH': ''}):
            with self.subTest(overrides=overrides):
                config = {**self.config, **overrides}
                client = self.client(dialogue(), config)
                with patch('services.conversation_ai.openai_client', return_value=client):
                    with self.assertRaises(TrialDenied):
                        ConversationAI(config).step_dialogue(scenario())
        self.assertEqual(self.sent, [])

    def test_missing_provider_key_fails_without_constructing_a_client(self):
        with patch('services.conversation_ai.openai_client') as factory:
            with self.assertRaises(SpeechError):
                ConversationAI({**self.config, 'OPENAI_API_KEY': ''}).step_dialogue(scenario())
        factory.assert_not_called()

    def test_malformed_output_is_rejected_after_one_call_without_retries(self):
        client = self.client({'turns': [], 'ending': {'russian': 'Пока!', 'english': 'Bye!'}})
        with patch('services.conversation_ai.openai_client', return_value=client):
            with self.assertRaises(SpeechError):
                ConversationAI(self.config).step_dialogue(scenario())
        self.assertEqual(len(self.sent), 1)

    def test_trial_denial_is_not_rewritten_as_a_model_failure(self):
        ai = ConversationAI(self.config)
        denial = TrialDenied('AI generation is paused.')
        with patch.object(ai, '_call', side_effect=denial):
            with self.assertRaises(TrialDenied) as caught:
                ai.step_dialogue(scenario())
        self.assertIs(caught.exception, denial)


if __name__ == '__main__':
    unittest.main()
