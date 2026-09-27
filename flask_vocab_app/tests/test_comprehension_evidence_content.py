"""Provider fixtures check reading contracts, not human marking accuracy."""
import asyncio
from copy import deepcopy
import json
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.comprehension_evidence import build_contracts, reading_candidates, reissue_contracts, validate_contracts
from services.comprehension_service import ComprehensionService
from contracts.curriculum import freeze_task_contract
from utils.story_content import story_schema, validate_story_content
from services.ai_trial_budget import TrialDenied

TEXT = ('Нина сейчас на почте. Сначала она отправит письмо. Потом она пойдёт в парк. '
        'У неё сегодня выходной, поэтому она не спешит.')
QUESTIONS = ['Где сейчас Нина?', 'Куда она пойдёт после почты?', 'Почему Нина не спешит?',
             'Что она сделает перед прогулкой?', 'Как вы проводите свободный день?']
ANSWERS = ['  На почта. 🙂\n', 'Она пойдёт в парк.', 'Потому что у неё выходной.', 'Сначала отправит письмо.',
           'Я гуляю с друзьями.']


def prepared_story(level='A1', topic='places'):
    references = {
        'A1': ['a1.reading.practical-information', 'a1.reading.reference-and-sequence',
               'a1.reading.narrative-meaning', 'a1.reading.reference-and-sequence'],
        'A2': ['a2.reading.gist-and-detail', 'a2.reading.event-relations',
               'a2.reading.event-relations', 'a2.reading.event-relations'],
        'B1': ['b1.reading.details-sequence', 'b1.reading.details-sequence',
               'b1.reading.attitude-reasons', 'b1.reading.details-sequence'],
        'B2': ['b2.reading.find-relevant-information'] * 4,
    }
    excerpts = ['Нина сейчас на почте.', 'Потом она пойдёт в парк.',
                'У неё сегодня выходной, поэтому она не спешит.', 'Сначала она отправит письмо.']
    meanings = ['Identify Nina’s current location.', 'Identify where she will go after visiting the post office.',
                'Explain why she is not in a hurry.', 'Identify the action before her walk.']
    return {'title': 'Письмо перед прогулкой', 'title_en': 'A Letter Before the Walk', 'text': TEXT,
            'questions': deepcopy(QUESTIONS), 'topic_id': topic,
            'reading_focus': [{'question_index': i, 'requirement_id': rid, 'passage_excerpt': excerpts[i],
                               'expectation': meanings[i]} for i, rid in enumerate(references[level])]}


def saved_task(level='A1', topic='places'):
    prepared = prepared_story(level, 'places' if topic == 'any' else topic)
    return {'text': prepared['text'], 'questions': prepared['questions'], 'topic': topic,
            'difficulty': level, 'contracts': build_contracts(prepared, topic, level)}


def assessment(task, answers=None):
    answers = answers or ANSWERS
    return {'feedback': ['Your meaning is clear.'] * len(answers), 'scores': [9] * len(answers),
            'criterion_reports': {key: {'contract_sha256': contract['contract_sha256'], 'judgements': [{
                'criterion_id': contract['criteria'][0]['id'], 'outcome': 'satisfied', 'score': 2,
                'feedback': 'You found the requested detail.',
                'evidence': [{'quote': answers[int(key)], 'start': 0, 'end': len(answers[int(key)])}]}]}
                for key, contract in task['contracts'].items()}}


class ComprehensionContentContractTests(unittest.TestCase):
    def test_exact_level_reading_questions_get_stable_contracts_but_reflection_does_not(self):
        for level in ('A1', 'A2', 'B1', 'B2'):
            with self.subTest(level=level):
                prepared = prepared_story(level)
                before = deepcopy(prepared)
                contracts = build_contracts(prepared, 'places', level)
                self.assertEqual(contracts, build_contracts(deepcopy(prepared), 'places', level))
                self.assertEqual(set(contracts), {'0', '1', '2', '3'})
                self.assertEqual(prepared, before)
                for key, contract in contracts.items():
                    criterion = contract['criteria'][0]
                    self.assertEqual(criterion['response_mode'], 'reading_response')
                    self.assertEqual(criterion['evidence_scope'], 'reading_comprehension')
                    self.assertNotEqual(criterion['target_id'], criterion['requirement_id'])
                    self.assertTrue(criterion['requirement_id'].startswith(level.lower()))
                    self.assertEqual(contract['content']['questions'], QUESTIONS)
                    self.assertEqual(contract['content']['question_index'], int(key))
                    self.assertEqual(contract['activity'], 'comprehension')
                self.assertEqual(validate_contracts(saved_task(level)), contracts)

    def test_any_resolves_a_canonical_topic_without_changing_the_requested_topic(self):
        contract = saved_task(topic='any')['contracts']['0']
        self.assertEqual(contract['topic_ids'], ['places'])
        self.assertEqual(contract['content']['requested_topic'], 'any')
        self.assertEqual(contract['content']['topic_id'], 'places')

    def test_invalid_focus_cannot_become_saved_evidence(self):
        invalid = []
        for key, value in [('question_index', True), ('question_index', 4), ('question_index', 1),
                           ('requirement_id', 'a2.reading.event-relations'),
                           ('requirement_id', 'a1.writing.short-message'),
                           ('passage_excerpt', 'Нина сейчас в школе.'), ('expectation', '')]:
            item = prepared_story(); item['reading_focus'][0][key] = value; invalid.append(item)
        item = prepared_story(); item['topic_id'] = 'First steps'; invalid.append(item)
        item = prepared_story(); item['topic_id'] = 'food'; invalid.append(item)
        item = prepared_story(); del item['reading_focus']; invalid.append(item)
        item = prepared_story(); item['reading_focus'].append(deepcopy(item['reading_focus'][0])); invalid.append(item)
        item = prepared_story(); item['reading_focus'][0]['score'] = 2; invalid.append(item)
        for prepared in invalid:
            with self.subTest(prepared=prepared), self.assertRaises(ValueError):
                build_contracts(prepared, 'places', 'A1')

    def test_custom_passage_is_anchored_without_rewriting_whitespace_or_endings(self):
        prepared = prepared_story()
        passage = '  ' + TEXT + '\n\n🙂'
        payload = {k: v for k, v in prepared.items() if k != 'text'}
        valid = validate_story_content(payload, False, reading_ids=reading_candidates('A1'), topic_ids=('places',), passage=passage)
        contracts = build_contracts({**valid, 'text': passage}, 'places', 'A1')
        self.assertEqual(contracts['0']['content']['text'], passage)
        payload['reading_focus'][0]['passage_excerpt'] = 'Нина сейчас на почта.'
        with self.assertRaises(ValueError):
            validate_story_content(payload, False, reading_ids=reading_candidates('A1'), topic_ids=('places',), passage=passage)

    def test_extra_questions_change_identity_without_claiming_new_reading_criteria(self):
        task = saved_task(); questions = QUESTIONS + ['Какое время года вы представляете?']
        changed = reissue_contracts(task, questions)
        self.assertEqual(set(changed), set(task['contracts']))
        self.assertNotEqual(changed['0']['task_id'], task['contracts']['0']['task_id'])
        self.assertEqual(changed['0']['content']['questions'], questions)
        self.assertEqual(validate_contracts({**task, 'questions': questions, 'contracts': changed}), changed)
        self.assertEqual(task['questions'], QUESTIONS)
        with self.assertRaises(ValueError): reissue_contracts(task, ['Что читает Нина?'] + QUESTIONS[1:])
        with self.assertRaises(ValueError): validate_contracts({**task, 'questions': questions})
        with self.assertRaises(ValueError): reissue_contracts(task, QUESTIONS + [f'Вопрос {n}?' for n in range(16)])

    def test_rehashed_content_or_policy_cannot_change_the_bound_task(self):
        for edit in ('text', 'level', 'policy'):
            task = saved_task(); value = deepcopy(task['contracts']['0'])
            del value['contract_sha256']; del value['content_sha256']
            if edit == 'text': value['content']['text'] += ' Новая строка.'
            elif edit == 'level': value['level'] = 'A2'
            else: value['support'] = {'allowed': [], 'independence_breakers': []}
            task['contracts']['0'] = freeze_task_contract(value)
            with self.assertRaises(ValueError): validate_contracts(task)

    def test_c1_and_c2_and_legacy_schema_stay_without_reading_contracts(self):
        for level in ('C1', 'C2'):
            self.assertEqual(build_contracts({'text': TEXT, 'questions': QUESTIONS}, 'places', level), {})
        plain = {k: v for k, v in prepared_story().items() if k not in ('topic_id', 'reading_focus')}
        self.assertEqual(set(story_schema()['properties']), {'title', 'title_en', 'text', 'questions'})
        self.assertEqual(validate_story_content(plain), plain)


class ComprehensionProviderEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.service = ComprehensionService.__new__(ComprehensionService)
        self.service.client = Mock()
        self.service.story_model = 'existing-story-model'; self.service.story_reasoning_effort = 'low'
        self.service.get_vocab_for_topic = Mock(return_value=['почта'])
        self.service.generate_image = Mock(return_value='image.png')

    def output(self, value, status='completed'):
        self.service.client.responses.create.return_value = SimpleNamespace(status=status, output_text=json.dumps(value, ensure_ascii=False))

    def test_new_generation_requires_exact_level_metadata_before_creating_media(self):
        self.output(prepared_story())
        result = asyncio.run(self.service.generate_story('places', 'A1'))
        self.assertEqual(result['reading_focus'], prepared_story()['reading_focus'])
        sent = self.service.client.responses.create.call_args.kwargs
        self.assertEqual(sent['model'], 'existing-story-model'); self.assertEqual(sent['max_output_tokens'], 4096)
        self.assertEqual(sent['reasoning'], {'effort': 'low'})
        schema = sent['text']['format']['schema']
        self.assertTrue(sent['text']['format']['strict']); self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']), {'title', 'title_en', 'text', 'questions', 'topic_id', 'reading_focus'})
        allowed = schema['properties']['reading_focus']['items']['properties']['requirement_id']['enum']
        self.assertTrue(all(rid.startswith('a1.reading.') for rid in allowed))
        self.assertTrue(all(item['id'] in allowed for item in json.loads(sent['input'][1]['content'])['reading_focus_candidates']))
        self.service.generate_image.assert_called_once_with(TEXT)

    def test_missing_metadata_is_not_silently_accepted_for_a1_to_b2(self):
        for level in ('A1', 'A2', 'B1', 'B2'):
            with self.subTest(level=level):
                plain = {key: value for key, value in prepared_story(level).items() if key not in ('topic_id', 'reading_focus')}
                self.output(plain)
                with self.assertRaises(ValueError): asyncio.run(self.service.generate_story('places', level))
        self.service.generate_image.assert_not_called()

    def test_custom_text_and_c1_generation_preserve_existing_behaviour(self):
        prepared = prepared_story(); self.output({k: v for k, v in prepared.items() if k != 'text'})
        passage = ' ' + TEXT + '\n'
        result = asyncio.run(self.service.prepare_story_from_text(passage, 'places', 'A1'))
        self.assertEqual(result['text'], passage); self.assertEqual(result['image_url'], '')
        self.service.generate_image.assert_not_called()
        plain = {key: value for key, value in prepared.items() if key not in ('topic_id', 'reading_focus')}
        self.output(plain)
        self.assertNotIn('reading_focus', asyncio.run(self.service.generate_story('places', 'C1')))
        self.assertNotIn('reading_focus', self.service.client.responses.create.call_args.kwargs['text']['format']['schema']['properties'])

    def test_one_assessment_call_grounds_raw_quotes_per_question_and_excludes_reflection(self):
        task = saved_task(); expected = assessment(task)
        expected['criterion_reports']['0']['judgements'][0]['evidence'][0]['end'] += 1
        before = deepcopy(expected); self.output(expected)
        result = self.service.assess_task(task, deepcopy(ANSWERS))
        self.service.client.responses.create.assert_called_once()
        self.assertEqual(result['total_score'], 9); self.assertEqual(set(result['criterion_reports']), {'0', '1', '2', '3'})
        self.assertEqual(result['criterion_reports']['0']['judgements'][0]['evidence'][0], {'quote': ANSWERS[0], 'start': 0, 'end': len(ANSWERS[0])})
        self.assertEqual(expected, before)
        sent = self.service.client.responses.create.call_args.kwargs
        self.assertEqual(json.loads(sent['input'][1]['content'])['answers'], ANSWERS)
        self.assertEqual(json.loads(sent['input'][1]['content'])['contracts'], task['contracts'])
        instruction = sent['input'][0]['content']
        self.assertIn('Do not lower a reading score for grammar', instruction)
        self.assertIn('answer in English can demonstrate reading comprehension', instruction)
        self.assertIn('only that question', instruction.lower()); self.assertFalse(sent['store'])

    def test_uncertain_response_is_unscored_and_extra_questions_only_receive_feedback(self):
        task = saved_task(); questions = QUESTIONS + ['Что будет дальше?']
        task['contracts'] = reissue_contracts(task, questions); task['questions'] = questions
        answers = [*ANSWERS, 'Она придёт домой.']; answers[0] = 'Не знаю.'
        value = assessment(task, answers)
        value['criterion_reports']['0']['judgements'][0].update(outcome='insufficient_evidence', score=None, evidence=[])
        self.output(value); result = self.service.assess_task(task, answers)
        self.assertEqual(len(result['feedback']), 6)
        self.assertIsNone(result['criterion_reports']['0']['judgements'][0]['score'])
        self.assertEqual(set(result['criterion_reports']), {'0', '1', '2', '3'})

    def test_invalid_cross_answer_quotes_reports_scores_and_reflection_claims_are_rejected(self):
        task = saved_task(); invalid = []
        value = assessment(task); value['criterion_reports']['0']['judgements'][0]['evidence'][0]['quote'] = ANSWERS[1]; invalid.append(value)
        value = assessment(task); value['criterion_reports']['0']['judgements'][0]['evidence'][0]['quote'] = 'На почте.'; invalid.append(value)
        value = assessment(task); value['criterion_reports']['4'] = deepcopy(value['criterion_reports']['0']); invalid.append(value)
        value = assessment(task); del value['criterion_reports']['0']; invalid.append(value)
        value = assessment(task); value['scores'][0] = True; invalid.append(value)
        value = assessment(task); value['criterion_reports']['0']['judgements'][0]['score'] = 1; invalid.append(value)
        value = assessment(task); value['feedback'] = value['feedback'][:1]; invalid.append(value)
        for output in invalid:
            with self.subTest(output=output):
                self.output(output)
                with self.assertRaises(ValueError): self.service.assess_task(task, ANSWERS)

    def test_changed_task_and_incomplete_answers_fail_before_provider_call(self):
        task = saved_task()
        for value, answers in [({**task, 'text': 'A replacement passage.'}, ANSWERS), (task, ANSWERS[:4]), (task, [''] + ANSWERS[1:])]:
            with self.assertRaises(ValueError): self.service.assess_task(value, answers)
        self.service.client.responses.create.assert_not_called()

    def test_legacy_assessment_keeps_existing_path_and_has_no_reports(self):
        self.service._evaluate_answers = Mock(return_value=(['Good.'] * 5, [8] * 5, 8))
        task = {'text': TEXT, 'questions': QUESTIONS, 'topic': 'places', 'difficulty': 'A1', 'contracts': {}}
        result = self.service.assess_task(task, ANSWERS)
        self.assertEqual(result['criterion_reports'], {})
        self.service._evaluate_answers.assert_called_once_with(TEXT, QUESTIONS, ANSWERS, 'places', 'A1')
        self.service.client.responses.create.assert_not_called()


    def test_incomplete_refused_and_budget_denied_assessments_do_not_retry(self):
        task = saved_task()
        for status, text in [('incomplete', ''), ('completed', ''), ('completed', 'not json')]:
            self.service.client.responses.create.reset_mock()
            self.service.client.responses.create.return_value = SimpleNamespace(status=status, output_text=text)
            with self.assertRaises(ValueError): self.service.assess_task(task, ANSWERS)
            self.service.client.responses.create.assert_called_once()
        self.service.client.responses.create.side_effect = TrialDenied('Daily limit reached')
        with self.assertRaises(TrialDenied): self.service.assess_task(task, ANSWERS)

    def test_ambiguous_wrong_offsets_cannot_be_repaired_to_an_arbitrary_occurrence(self):
        task = saved_task(); answers = deepcopy(ANSWERS); answers[0] = 'на почте, на почте'
        result = assessment(task, answers)
        result['criterion_reports']['0']['judgements'][0]['evidence'] = [{'quote': 'на почте', 'start': 1, 'end': 9}]
        self.output(result)
        with self.assertRaises(ValueError): self.service.assess_task(task, answers)


class ComprehensionLegacyWriteGuardTests(unittest.TestCase):
    def test_matching_versioned_story_cannot_be_overwritten_with_or_without_a_browser_story_id(self):
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / 'vocab.db')
            with sqlite3.connect(db) as conn:
                conn.executescript('''
                    CREATE TABLE saved_stories(id INTEGER PRIMARY KEY,title TEXT,topic TEXT,difficulty TEXT,text TEXT,
                      audio_url TEXT,image_url TEXT,questions TEXT,answers TEXT,feedback TEXT,score REAL,owner_profile_id TEXT);
                    CREATE TABLE comprehension_tasks(id TEXT,story_id INTEGER);
                ''')
                conn.execute('INSERT INTO saved_stories VALUES (1,?,?,?,?,?,?,?,?,?,?,?)',
                             ('Saved title', 'places', 'A1', TEXT, 'audio.mp3', 'image.png', json.dumps(QUESTIONS), '[]', '[]', 0, 'personal-learning'))
                conn.execute("INSERT INTO comprehension_tasks VALUES ('task',1)")
                before = conn.execute('SELECT * FROM saved_stories').fetchall()
            service = ComprehensionService.__new__(ComprehensionService); service.db_path = db
            arguments = dict(title='Changed title', topic='places', difficulty='A1', text=TEXT, audio_url='', image_url='',
                             questions=['Changed question'], answers=['Forged answer'], feedback=[], score=0)
            with patch('services.comprehension_service.activity_profile_id', return_value='personal-learning'):
                for story_id in (None, 1):
                    with self.assertRaisesRegex(ValueError, 'saved questions'):
                        service.save_story(**arguments, story_id=story_id)
                with sqlite3.connect(db) as conn:
                    self.assertEqual(conn.execute('SELECT * FROM saved_stories').fetchall(), before)
                    conn.execute('DROP TABLE comprehension_tasks')
                self.assertEqual(service.save_story(**arguments, story_id=1), 1)
