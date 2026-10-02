"""A bounded present-tense lesson observes person and number, not an A1 pass."""
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
from services.curriculum_units import (
    _pack, _practice_contract, _questions, get_unit, writing_task,
)
from tests.support import isolated_app


UNIT = 'present-actions-v1'
DATA = Path(__file__).resolve().parents[1] / 'data/curriculum_units'


def source():
    return json.loads((DATA / (UNIT + '.json')).read_text())


class PresentActionsContentTests(unittest.TestCase):
    def test_each_assessed_present_form_is_taught_with_its_person(self):
        unit = source()
        examples = ' '.join(example['ru'] for group in unit['groups'] for example in group['examples'])
        for pronoun, reading, speaking in (
            ('я', 'читаю', 'говорю'), ('ты', 'читаешь', 'говоришь'),
            ('он', 'читает', 'говорит'), ('мы', 'читаем', 'говорим'),
            ('вы', 'читаете', 'говорите'), ('они', 'читают', 'говорят'),
        ):
            # Он/она share one present form. A feminine example is sufficient
            # for that cell, but it must still be explicitly taught.
            people = '(?:он|она)' if pronoun == 'он' else pronoun
            for verb in (reading, speaking):
                with self.subTest(person=pronoun, verb=verb):
                    self.assertRegex(examples.lower(), rf'\b{people}\s+{verb}\b')
        for question in unit['forms']['questions']:
            self.assertRegex(examples.lower(), rf'\b{question["answer"]}\b')
        notes = ' '.join(group['note'] for group in unit['groups'])
        self.assertIn('dictionary forms', notes)
        self.assertIn('subject', notes)
        self.assertIn('one person addressed politely', notes)
        self.assertIn('Not every verb ending in -ить', notes)

    def test_reference_contracts_keep_recognition_production_and_description_separate(self):
        unit = source()
        references = requirement_index()
        self.assertEqual(len(unit['questions']), 8)
        self.assertEqual(len(unit['forms']['questions']), 6)
        for stage in ('practice', 'forms'):
            pack = validate_pack(_pack(unit, stage))
            for item, question in zip(pack['items'], _questions(unit, stage)):
                contract = _practice_contract(unit, item, question, 'present-action-validation')
                criterion = contract['criteria'][0]
                self.assertEqual(criterion['source_refs'], references[question['requirement_id']]['source_refs'])
                self.assertEqual(contract['purpose'], 'practice')
                if stage == 'forms':
                    self.assertEqual(criterion['requirement_id'], 'a1.language.verb-conjugation')
                    self.assertEqual(criterion['evidence_scope'], 'controlled_production')
                else:
                    self.assertNotEqual(criterion['response_mode'], 'independent_speaking')
        writing = writing_task(unit)
        WritingRepository.validate_task(writing)
        WritingRepository.validate_curriculum_contract(writing['curriculum_contract'], writing['task'], writing['required_words'], 'A1')
        criteria = writing['curriculum_contract']['criteria']
        self.assertEqual([c['requirement_id'] for c in criteria], ['a1.writing.connected-description'])
        self.assertIn('not certify present-tense conjugation control', criteria[0]['expectation'])

    def test_wrong_person_and_plural_forms_are_not_accepted_as_equivalent(self):
        errors = {
            'form-i-read': ['читает', 'читаешь', 'читать'],
            'form-you-speak': ['говорит', 'говорите', 'говорить'],
            'form-we-speak': ['говорят', 'говорю', 'говорить'],
            'form-you-read': ['читаешь', 'читают', 'читать'],
            'form-they-speak': ['говорим', 'говорит', 'говорить'],
            'form-he-speaks': ['говорят', 'говоришь', 'говорить'],
        }
        for item in validate_pack(_pack(source(), 'forms'))['items']:
            for accepted in item['accepted_answers']:
                self.assertTrue(assess_activity_answer(item, {'text': '  ' + accepted.upper() + '! '})[1])
            for error in errors[item['id']]:
                with self.subTest(item=item['id'], error=error):
                    self.assertFalse(assess_activity_answer(item, {'text': error})[1])

    def test_address_and_message_questions_distinguish_people_and_negated_actions(self):
        questions = {q['id']: q for q in source()['questions']}
        polite = questions['one-polite-person']
        self.assertIn('Нина, вы', polite['prompt'])
        self.assertEqual(next(c['text'] for c in polite['choices'] if c['id'] == polite['answer']), 'читаете')
        subject = questions['subject-after-verb']
        self.assertIn('читает Олег', subject['prompt'])
        self.assertEqual(subject['requirement_id'], 'a1.language.nominative-subject')
        self.assertEqual(subject['answer'], 'oleg')
        self.assertEqual(questions['reading-we-reference']['answer'], 'nina-anna')
        self.assertIn('Я Нина.', questions['reading-we-reference']['prompt'])
        self.assertEqual(questions['reading-current-actions']['answer'], 'nina')
        self.assertIn('Нина не читает. Она говорит', questions['reading-current-actions']['prompt'])
        # This lesson teaches present-person agreement, not an unexplained
        # futurate use of the present with потом.
        learner_text = ' '.join(g['note'] + ' ' + ' '.join(e['ru'] for e in g['examples'])
                                for g in source()['groups'])
        learner_text += ' '.join(q['prompt'] for q in source()['questions'])
        self.assertNotIn('потом', learner_text.lower())

    def test_listening_needs_person_and_message_meaning_with_no_claim_of_ready_audio(self):
        listening = json.loads((DATA / 'present-actions-listening-v1.json').read_text())
        self.assertEqual(listening['unit_id'], UNIT)
        self.assertEqual(len(listening['items']), 3)
        self.assertLessEqual(sum(len(q['transcript']) for q in listening['items']), 750)
        self.assertEqual(len({q['transcript'] for q in listening['items']}), 3)
        by_id = {q['id']: q for q in listening['items']}
        self.assertEqual(by_id['two-readers']['answer'], 'oleg-nina')
        self.assertIn('Я Олег.', by_id['two-readers']['transcript'])
        self.assertEqual(by_id['polite-reply']['answer'], 'speaks')
        self.assertIn('Нет, я не читаю.', by_id['polite-reply']['transcript'])
        self.assertEqual(by_id['group-contrast']['answer'], 'all')
        self.assertTrue(by_id['group-contrast']['transcript'].startswith('Сейчас '))
        self.assertIn('Нина тоже говорит', by_id['group-contrast']['transcript'])
        self.assertFalse(any('потом' in item['transcript'].lower() for item in listening['items']))
        prepared = deepcopy(listening)
        for item in prepared['items']:
            self.assertEqual(item['requirement_id'], 'a1.listening.short-message')
            self.assertEqual(item['audio_url'], '/static/audio/course/curriculum/present-actions-listening-v1/' + item['id'] + '.mp3')
            # These bytes are never published. The test checks contracts; the
            # normal media loader alone decides whether real audio is ready.
            item['audio'] = {'url': item['audio_url'], 'sha256': '0' * 64, 'duration_ms': 1000}
        with patch('services.curriculum_units.listening_content', return_value=prepared):
            pack = validate_pack(_pack(source(), 'listening'))
            for item, question in zip(pack['items'], prepared['items']):
                criterion = _practice_contract(source(), item, question, 'listening-validation')['criteria'][0]
                self.assertEqual(criterion['response_mode'], 'listening_selection')
                self.assertTrue(assess_activity_answer(item, {'choice_id': item['answer']})[1])


class PresentActionsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.state = self.client.get('/api/v1/user-session').json
        self.headers = {'X-CSRF-Token': self.state['csrf_token']}
        provider = patch('utils.lazy.LazyService._get', side_effect=AssertionError('Authored unit practice must not call AI'))
        provider.start()
        self.addCleanup(provider.stop)

    def test_existing_players_save_all_responses_without_new_proficiency_effects(self):
        unit = get_unit(UNIT)
        page = self.client.get('/curriculum/units/' + UNIT)
        self.assertEqual(page.status_code, 200)
        self.assertIn(unit['title'], page.text)
        for stage in ('practice', 'forms'):
            data = {'profile_id': self.state['profile']['id'], 'request_id': 'present-' + stage}
            response = self.client.post('/curriculum/units/' + UNIT + '/' + stage, data=data, headers=self.headers)
            self.assertEqual(response.status_code, 303, response.text)
            self.assertEqual(self.client.post('/curriculum/units/' + UNIT + '/' + stage, data=data, headers=self.headers).location, response.location)
            path = '/api/v1/learning-sessions/' + response.location.rsplit('/', 1)[1]
            saved = self.client.get(path).json
            for index, item in enumerate(_pack(unit, stage)['items']):
                self.assertNotIn('answer', saved['item'])
                self.assertNotIn('accepted_answers', saved['item'])
                answer = {'text': item['answer']} if stage == 'forms' else {'choice_id': item['answer']}
                response = self.client.post(path + '/attempts', json={'submission_id': 'answer-' + str(index),
                    'expected_revision': saved['revision'], 'item_id': item['id'], 'answer': answer}, headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
                saved = response.json
            self.assertEqual(saved['status'], 'completed')
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 14)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            validate_saved_evidence(conn)

    def test_writing_reuses_owned_draft_and_only_observes_description(self):
        data = {'profile_id': self.state['profile']['id']}
        route = '/curriculum/units/' + UNIT + '/writing'
        response = self.client.post(route, data=data, headers=self.headers)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.client.post(route, data=data, headers=self.headers).location, response.location)
        self.assertEqual(self.client.get(response.location).status_code, 200)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            rows = conn.execute("SELECT contract_json FROM activity_task_contracts WHERE activity='writing'").fetchall()
        self.assertEqual(len(rows), 1)
        contract = json.loads(rows[0][0])
        self.assertEqual(contract['content_version'], UNIT)
        self.assertEqual(contract['criteria'][0]['requirement_id'], 'a1.writing.connected-description')


if __name__ == '__main__':
    unittest.main()
