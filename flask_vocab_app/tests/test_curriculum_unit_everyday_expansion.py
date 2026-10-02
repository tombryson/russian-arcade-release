"""Everyday A1 practice tests distinct skills without implying spoken fluency."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from contracts.learning import assess_activity_answer, validate_pack
from repositories.writing_repository import WritingRepository
from services.activity_evidence import validate_saved_evidence
from services.curriculum_requirement_map import requirement_index
from services.curriculum_units import (get_unit, _pack, _questions,
                                       _practice_contract, writing_task)
from tests.support import isolated_app


UNITS = ('numbers-quantities-v1', 'social-exchanges-v1', 'needs-company-v1')
DATA = Path(__file__).resolve().parents[1] / 'data/curriculum_units'


class EverydayUnitContentTests(unittest.TestCase):
    def test_teaching_and_tasks_have_valid_scoped_reference_contracts(self):
        references = requirement_index()
        for unit_id in UNITS:
            unit = get_unit(unit_id)
            self.assertEqual(unit['level'], 'A1')
            self.assertEqual(len(unit['questions']), 8)
            self.assertEqual(len(unit['forms']['questions']), 5)
            self.assertGreaterEqual(len(unit['groups']), 3)
            self.assertIn('qualified language review pending', unit['review_status'])
            for group in unit['groups']:
                self.assertTrue(all(group[k] for k in ('title', 'title_ru', 'note', 'note_ru')))
                self.assertGreaterEqual(len(group['examples']), 2)
                self.assertTrue(all(example['ru'] and example['en'] for example in group['examples']))
            for stage in ('practice', 'forms'):
                pack = validate_pack(_pack(unit, stage))
                for item, question in zip(pack['items'], _questions(unit, stage)):
                    with self.subTest(unit=unit_id, question=item['id']):
                        contract = _practice_contract(unit, item, question, 'validation')
                        criterion = contract['criteria'][0]
                        reference = references[question['requirement_id']]
                        self.assertEqual(contract['purpose'], 'practice')
                        self.assertEqual(criterion['source_refs'], reference['source_refs'])
                        self.assertNotIn('speaking', criterion['requirement_id'])
                        if stage == 'forms':
                            self.assertEqual(criterion['response_mode'], 'controlled_text')
                            self.assertEqual(criterion['evidence_scope'], 'controlled_production')
                            self.assertEqual(reference['domain'], 'language_use')
                        else:
                            self.assertEqual(criterion['response_mode'], reference['response_mode'])
                            for choice in item['choices']:
                                self.assertEqual(assess_activity_answer(item, {'choice_id': choice['id']})[1],
                                                 choice['id'] == item['answer'])
            task = writing_task(unit)
            WritingRepository.validate_task(task)
            WritingRepository.validate_curriculum_contract(task['curriculum_contract'], task['task'],
                                                           task['required_words'], 'A1')
            criterion = task['curriculum_contract']['criteria'][0]
            self.assertEqual(criterion['response_mode'], 'independent_writing')
            self.assertEqual(criterion['expectation'], unit['writing_focus']['expectation'])

    def test_typed_forms_reject_case_number_and_address_errors(self):
        incorrect = {
            'numbers-quantities-v1': ['один', 'тетрадей', 'рубля', 'года', 'два'],
            'social-exchanges-v1': ['Я', 'тебе', 'Повтори', 'Скажите', 'вам'],
            'needs-company-v1': ['я', 'Он', 'Она', 'друга', 'сыра'],
        }
        for unit_id, wrong in incorrect.items():
            for item, error in zip(_pack(get_unit(unit_id), 'forms')['items'], wrong):
                with self.subTest(unit=unit_id, question=item['id']):
                    for accepted in item['accepted_answers']:
                        self.assertTrue(assess_activity_answer(item, {'text': '  '+accepted.upper()+'!  '})[1])
                    self.assertFalse(assess_activity_answer(item, {'text': error})[1])

    def test_pragmatic_recognition_is_not_misreported_as_independent_speech(self):
        unit = get_unit('social-exchanges-v1')
        by_id = {q['id']: q for q in unit['questions']}
        for identity in ('polite-arrival', 'repair-intention'):
            self.assertEqual(by_id[identity]['requirement_id'], 'a1.reading.narrative-meaning')
        self.assertIn('на ты', by_id['familiar-repeat']['prompt'])
        self.assertIn('на вы', by_id['polite-information']['prompt'])
        self.assertIn('повторите', by_id['repair-intention']['prompt'])
        self.assertEqual(by_id['repair-intention']['answer'], 'repeat')

    def test_counted_forms_and_company_match_the_declared_functions(self):
        numbers = get_unit('numbers-quantities-v1')
        targets = {q['id']: q['requirement_id'] for q in numbers['questions']}
        self.assertEqual(targets['price-label'], 'a1.reading.practical-information')
        self.assertEqual(targets['child-age'], 'a1.language.genitive-quantity')
        self.assertEqual(targets['three-tickets'], 'a1.language.genitive-quantity')
        self.assertIn('11–14', numbers['groups'][2]['note'])
        company = {q['id']: q for q in get_unit('needs-company-v1')['questions']}
        self.assertEqual(company['walk-with-sister']['requirement_id'], 'a1.language.instrumental-company')
        self.assertIn('вместе', company['walk-with-sister']['prompt'])
        self.assertEqual(company['tea-with-milk']['requirement_id'], 'a1.language.instrumental-ingredient')
        self.assertIn('добавить молоко', company['tea-with-milk']['prompt'])

    def test_prepared_listening_sources_keep_their_authored_contracts(self):
        scripts = set()
        for unit_id in UNITS:
            unit = get_unit(unit_id)
            content_id = unit_id.removesuffix('-v1') + '-listening-v1'
            source = json.loads((DATA / (content_id+'.json')).read_text())
            self.assertEqual(source['unit_id'], unit_id)
            self.assertEqual(source['id'], content_id)
            self.assertEqual(len(source['items']), 3)
            self.assertLess(sum(len(q['transcript']) for q in source['items']), 750)
            self.assertTrue(unit['listening_available'])
            prepared = deepcopy(source)
            for item in prepared['items']:
                self.assertNotIn(item['transcript'], scripts)
                scripts.add(item['transcript'])
                self.assertTrue(item['requirement_id'].startswith('a1.listening.'))
                expected = '/static/audio/course/curriculum/'+content_id+'/'+item['id']+'.mp3'
                self.assertEqual(item['audio_url'], expected)
                # Synthetic metadata exercises only the task validator;
                # the published-media tests check the actual recording hashes.
                item['audio'] = {'url': expected, 'sha256': '0'*64, 'duration_ms': 1000}
            with patch('services.curriculum_units.listening_content', return_value=prepared):
                pack = validate_pack(_pack(unit, 'listening'))
                for item, question in zip(pack['items'], prepared['items']):
                    contract = _practice_contract(unit, item, question, 'validation')
                    self.assertEqual(contract['criteria'][0]['response_mode'], 'listening_selection')
                    self.assertIn('transcript', contract['support']['independence_breakers'])


class EverydayUnitIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.state = self.client.get('/api/v1/user-session').json
        self.headers = {'X-CSRF-Token': self.state['csrf_token']}
        provider = patch('utils.lazy.LazyService._get', side_effect=AssertionError('Authored practice must not call AI'))
        provider.start()
        self.addCleanup(provider.stop)

    def test_all_39_responses_use_owned_frozen_evidence_without_awarding_level_passes(self):
        for unit_id in UNITS:
            unit = get_unit(unit_id)
            entry = self.client.get('/curriculum/units/' + unit_id)
            self.assertEqual(entry.status_code, 200)
            self.assertIn(unit['title'], entry.text)
            self.assertIn('/' + unit_id + '/listening', entry.text)
            for stage in ('practice', 'forms'):
                pack = _pack(unit, stage)
                response = self.client.post('/curriculum/units/'+unit_id+'/'+stage,
                    data={'profile_id': self.state['profile']['id'], 'request_id': unit_id+'-'+stage}, headers=self.headers)
                self.assertEqual(response.status_code, 303, response.text)
                path = '/api/v1/learning-sessions/' + response.location.rsplit('/', 1)[1]
                saved = self.client.get(path).json
                for index, item in enumerate(pack['items']):
                    self.assertNotIn('answer', saved['item'])
                    self.assertNotIn('accepted_answers', saved['item'])
                    answer = {'text': item['answer']} if stage == 'forms' else {'choice_id': item['answer']}
                    body = {'submission_id': 'answer-'+str(index), 'expected_revision': saved['revision'],
                            'item_id': item['id'], 'answer': answer}
                    result = self.client.post(path+'/attempts', json=body, headers=self.headers)
                    self.assertEqual(result.status_code, 200, result.text)
                    saved = result.json
                    self.assertEqual(saved['attempts'][-1]['outcome'], 'correct')
                self.assertEqual(saved['status'], 'completed')
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 39)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            validate_saved_evidence(conn)

    def test_three_writing_briefs_resume_their_own_drafts_with_their_own_criteria(self):
        locations = set()
        for unit_id in UNITS:
            path = '/curriculum/units/'+unit_id+'/writing'
            data = {'profile_id': self.state['profile']['id']}
            response = self.client.post(path, data=data, headers=self.headers)
            self.assertEqual(response.status_code, 303, response.text)
            self.assertEqual(self.client.post(path, data=data, headers=self.headers).location, response.location)
            self.assertEqual(self.client.get(response.location).status_code, 200)
            locations.add(response.location)
        self.assertEqual(len(locations), 3)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            contracts = [json.loads(row[0]) for row in conn.execute(
                "SELECT contract_json FROM activity_task_contracts WHERE activity='writing'")]
        self.assertEqual({contract['content_version'] for contract in contracts}, set(UNITS))
        self.assertTrue(all(contract['criteria'][0]['response_mode'] == 'independent_writing' for contract in contracts))


if __name__ == '__main__':
    unittest.main()
