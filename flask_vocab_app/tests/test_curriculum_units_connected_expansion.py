"""New A1 units retain narrow evidence and original response text."""
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from contracts.learning import assess_activity_answer, validate_pack
from services.curriculum import get_topic
from services.curriculum_units import get_unit, _pack, _questions, _practice_contract, writing_task, LISTENING_IDS
from repositories.writing_repository import WritingRepository
from services.activity_evidence import validate_saved_evidence
from tests.support import isolated_app

ROOT = Path(__file__).resolve().parents[1]
IDS = ('action-aspect-v1', 'origins-and-destinations-v1', 'connected-messages-v1')
ERRORS = {
    'action-aspect-v1': ['написала', 'прочитала', 'напишут', 'будет читать', 'делает'],
    'origins-and-destinations-v1': ['школа', 'работу', 'врача', 'почте', 'её'],
    'connected-messages-v1': ['когда', 'потому что', 'Куда', 'никого', 'ни'],
}


class ConnectedExpansionContentTests(unittest.TestCase):
    def test_published_v2_unit_sources_are_unchanged(self):
        fixture = json.loads((ROOT / 'data/curriculum_evaluation/a1-units-review-v2.json').read_text())
        for unit_id, expected in fixture['unit_sha256'].items():
            raw = (ROOT / 'data/curriculum_units' / (unit_id + '.json')).read_bytes()
            with self.subTest(unit=unit_id):
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)

    def test_all_new_units_register_with_narrow_frozen_requirements_and_specific_writing(self):
        focuses = set()
        for unit_id in IDS:
            unit = get_unit(unit_id)
            with self.subTest(unit=unit_id):
                self.assertEqual(get_topic(unit['topic_id'])['band'], 'A1')
                self.assertGreaterEqual(len(unit['groups']), 3)
                self.assertTrue(all(len(group['examples']) >= 2 and group['note'] and group['note_ru'] for group in unit['groups']))
                self.assertEqual(len(unit['questions']), 8)
                self.assertEqual(len(unit['forms']['questions']), 5)
                self.assertGreaterEqual(sum(q['requirement_id'].startswith('a1.reading.') for q in unit['questions']), 2)
                self.assertIn('qualified language review pending', unit['review_status'])
                for stage in ('practice', 'forms'):
                    pack = validate_pack(_pack(unit, stage))
                    for item, question in zip(pack['items'], _questions(unit, stage)):
                        contract = _practice_contract(unit, item, question, 'content-check')
                        criterion = contract['criteria'][0]
                        self.assertEqual(contract['purpose'], 'practice')
                        self.assertEqual(criterion['requirement_id'], question['requirement_id'])
                        self.assertNotIn(criterion['response_mode'], ('independent_speaking', 'independent_writing'))
                        if stage == 'forms':
                            self.assertEqual(criterion['evidence_scope'], 'controlled_production')
                task = writing_task(unit)
                WritingRepository.validate_task(task)
                WritingRepository.validate_curriculum_contract(task['curriculum_contract'], task['task'], task['required_words'], unit['level'])
                self.assertEqual(task['curriculum_contract']['criteria'][0]['response_mode'], 'independent_writing')
                focuses.add(task['curriculum_contract']['criteria'][0]['expectation'])
        self.assertEqual(len(focuses), len(IDS))
        connected = get_unit('connected-messages-v1')
        self.assertEqual(connected['writing_focus']['requirement_id'], 'a1.writing.source-based-message')
        self.assertIn('с десяти утра до шести вечера', connected['writing']['task'])

    def test_forms_accept_natural_authored_alternatives_but_reject_changed_roles_or_endings(self):
        for unit_id in IDS:
            for item, error in zip(_pack(get_unit(unit_id), 'forms')['items'], ERRORS[unit_id]):
                with self.subTest(unit=unit_id, item=item['id']):
                    for answer in item['accepted_answers']:
                        self.assertTrue(assess_activity_answer(item, {'text': '  '+answer.upper()+'!  '})[1])
                    self.assertFalse(assess_activity_answer(item, {'text': error})[1])
        origin = _pack(get_unit('origins-and-destinations-v1'), 'forms')['items'][-1]
        self.assertTrue(assess_activity_answer(origin, {'text': 'от нее'})[1])
        connected = _pack(get_unit('connected-messages-v1'), 'forms')['items']
        self.assertTrue(assess_activity_answer(connected[1], {'text': 'После того как'})[1])
        self.assertNotIn('(никто)', get_unit('connected-messages-v1')['forms']['questions'][3]['prompt'])

    def test_origin_and_aspect_contracts_do_not_claim_broader_control_than_prompt_elicits(self):
        origins = get_unit('origins-and-destinations-v1')
        self.assertEqual(origins['questions'][-2]['requirement_id'], 'a1.reading.practical-information')
        self.assertEqual(origins['forms']['questions'][-1]['requirement_id'], 'a1.language.personal-pronoun-cases')
        aspects = get_unit('action-aspect-v1')
        self.assertEqual(aspects['forms']['questions'][0]['requirement_id'], 'a1.language.verb-aspect')
        self.assertEqual(aspects['forms']['questions'][1]['requirement_id'], 'a1.language.verb-tense')
        self.assertIn('does not tell us by itself whether I finished', aspects['groups'][0]['note'])

    def test_listening_sources_are_bounded_drafts_with_distinct_information_tasks(self):
        seen = set()
        for unit_id in IDS:
            pack_id = unit_id.removesuffix('-v1')+'-listening-v1'
            source = json.loads((ROOT / 'data/curriculum_units' / (pack_id+'.json')).read_text())
            self.assertEqual(source['id'], pack_id)
            self.assertEqual(source['unit_id'], unit_id)
            self.assertEqual(len(source['items']), 3)
            self.assertLessEqual(sum(len(item['transcript']) for item in source['items']), 750)
            for item in source['items']:
                self.assertEqual(item['requirement_id'], 'a1.listening.short-message')
                self.assertEqual(len(item['choices']), 3)
                self.assertIn(item['answer'], {choice['id'] for choice in item['choices']})
                self.assertNotIn(item['transcript'], seen)
                seen.add(item['transcript'])
                self.assertEqual(item['audio_url'], f'/static/audio/course/curriculum/{pack_id}/{item["id"]}.mp3')
            # A future media preparation can enable this; a source draft alone cannot.
            if unit_id not in LISTENING_IDS:
                self.assertFalse(get_unit(unit_id)['listening_available'])


class ConnectedExpansionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        provider = patch('utils.lazy.LazyService._get', side_effect=AssertionError('Authored unit operations must not call a provider'))
        provider.start(); self.addCleanup(provider.stop)

    def post(self, path, *, form=None, body=None):
        return self.client.post(path, data=form, json=body, headers={'X-CSRF-Token': self.token})

    def test_stages_complete_with_saved_raw_answers_and_no_vocabulary_or_milestone_writes(self):
        db = self.app.config['DB_PATH']
        with sqlite3.connect(db) as conn:
            words_before = conn.execute('SELECT COUNT(*) FROM words').fetchone()[0]
        expected = 0
        for unit_id in IDS:
            self.assertEqual(self.client.get('/curriculum/units/'+unit_id).status_code, 200)
            for stage in ('practice', 'forms'):
                pack = _pack(get_unit(unit_id), stage)
                form = {'profile_id': 'personal-learning', 'request_id': unit_id+'-'+stage}
                start = self.post('/curriculum/units/'+unit_id+'/'+stage, form=form)
                self.assertEqual(start.status_code, 303, start.text)
                self.assertEqual(self.post('/curriculum/units/'+unit_id+'/'+stage, form=form).location, start.location)
                path = '/api/v1/learning-sessions/'+start.location.rsplit('/', 1)[1]
                state = self.client.get(path).json
                for index,item in enumerate(pack['items']):
                    self.assertNotIn('answer', state['item'])
                    self.assertNotIn('accepted_answers', state['item'])
                    raw = '  '+item['accepted_answers'][-1].upper()+'!  ' if stage == 'forms' else item['answer']
                    answer = {'text': raw} if stage == 'forms' else {'choice_id': raw}
                    body = {'submission_id': 'answer-'+str(index), 'expected_revision': state['revision'], 'item_id': item['id'], 'answer': answer}
                    response = self.post(path+'/attempts', body=body)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(self.post(path+'/attempts', body=body).json, response.json)
                    state = response.json
                    self.assertEqual(state['attempts'][-1]['outcome'], 'correct')
                    if stage == 'forms':self.assertEqual(state['attempts'][-1]['answer']['text'], raw)
                self.assertEqual(state['status'], 'completed')
                expected += len(pack['items'])
            writing = self.post('/curriculum/units/'+unit_id+'/writing', form={'profile_id': 'personal-learning'})
            self.assertEqual(writing.status_code, 303, writing.text)
            self.assertEqual(self.client.get(writing.location).status_code, 200)
        with sqlite3.connect(db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], expected)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], words_before)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            validate_saved_evidence(conn)


if __name__ == '__main__':
    unittest.main()
