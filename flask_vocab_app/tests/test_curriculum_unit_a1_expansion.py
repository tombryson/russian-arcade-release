"""Authored A1 expansion is usable practice, not a proficiency assessment."""
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from contracts.learning import assess_activity_answer, validate_pack
from services.curriculum_units import (get_unit, UNIT_IDS, LISTENING_IDS, _pack,
                                       _questions, _practice_contract, writing_task)
from services.curriculum_requirement_map import requirement_index
from tests.support import isolated_app

NEW_UNITS = ('noun-adjective-agreement-v1', 'personal-reference-v1', 'basic-motion-v1')
DATA = Path(__file__).resolve().parents[1] / 'data/curriculum_units'
OLD_CONTRACTS = {
    'possession-absence-v1': '49239e70f35427552b95f313ce2352daf35d2ae6eb11cf3b82202db26669cb05',
    'objects-recipients-v1': '0c735683398fb0e7feb302f3ff76389c02bb9f0b839878ae9608ca45ab8259b5',
    'time-routine-v1': '3b6ad27a19a640be850a43e407483ae4ab7fad0583d33ee33897895538609197',
}


class A1ExpansionContentTests(unittest.TestCase):
    def test_existing_practice_forms_and_writing_contracts_remain_unchanged(self):
        for unit_id, expected in OLD_CONTRACTS.items():
            unit = get_unit(unit_id)
            snapshot = {'packs': [_pack(unit, stage) for stage in ('practice', 'forms')],
                'writing': writing_task(unit),
                'contracts': [_practice_contract(unit, item, question, 'validation')
                    for stage in ('practice', 'forms')
                    for item, question in zip(_pack(unit, stage)['items'], _questions(unit, stage))]}
            with self.subTest(unit=unit_id):
                self.assertEqual(hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), expected)

    def test_classified_examples_and_contextual_items_have_valid_narrow_contracts(self):
        for unit_id in NEW_UNITS:
            unit = get_unit(unit_id)
            self.assertEqual(len(unit['groups']), 3)
            self.assertTrue(all(group['note'] and len(group['examples']) >= 2 for group in unit['groups']))
            self.assertGreaterEqual(len(unit['questions']), 6)
            self.assertGreaterEqual(sum(q['requirement_id'].startswith('a1.reading.') for q in unit['questions']), 2)
            self.assertGreaterEqual(len(unit['forms']['questions']), 4)
            self.assertIn('qualified language review pending', unit['review_status'])
            for stage in ('practice', 'forms'):
                pack = validate_pack(_pack(unit, stage))
                for item, question in zip(pack['items'], _questions(unit, stage)):
                    frozen = _practice_contract(unit, item, question, 'validation')
                    self.assertEqual(frozen['purpose'], 'practice')
                    self.assertEqual(len(frozen['criteria']), 1)
                    if stage == 'forms':
                        self.assertEqual(frozen['criteria'][0]['evidence_scope'], 'controlled_production')
            writing = writing_task(unit)['curriculum_contract']
            self.assertEqual(writing['criteria'][0]['response_mode'], 'independent_writing')
            self.assertEqual(writing['criteria'][0]['expectation'], unit['writing_focus']['expectation'])

    def test_controlled_forms_accept_authored_alternatives_not_case_or_conjugation_errors(self):
        wrong = {
            'noun-adjective-agreement-v1': ['новая', 'новый', 'синяя', 'красный'],
            'personal-reference-v1': ['он', 'её', 'его', 'неё'],
            'basic-motion-v1': ['идёт', 'едут', 'ходю', 'автобус'],
        }
        for unit_id, errors in wrong.items():
            for item, error in zip(_pack(get_unit(unit_id), 'forms')['items'], errors):
                with self.subTest(unit=unit_id, item=item['id']):
                    for answer in item['accepted_answers']:
                        self.assertTrue(assess_activity_answer(item, {'text': '  '+answer.upper()+'!  '})[1])
                    self.assertFalse(assess_activity_answer(item, {'text': error})[1])
        pronoun = _pack(get_unit('personal-reference-v1'), 'forms')['items'][-1]
        self.assertTrue(assess_activity_answer(pronoun, {'text': 'ее сумка'})[1])

    def test_motion_prompts_do_not_define_a_frequency_word_as_a_universal_verb_rule(self):
        unit = get_unit('basic-motion-v1')
        self.assertIn('Context matters', unit['groups'][1]['note'])
        item = next(q for q in unit['questions'] if q['id'] == 'regular-travel')
        self.assertIn('сейчас', item['choices'][1]['text'])
        self.assertIn('frequency phrase alone', item['expectation'])

    def test_listening_drafts_have_unique_complete_source_without_fake_availability(self):
        transcripts = set()
        for unit_id in UNIT_IDS:
            if unit_id not in LISTENING_IDS:
                self.assertFalse(get_unit(unit_id)['listening_available'])
                continue
            content_id = unit_id.removesuffix('-v1') + '-listening-v1'
            source = json.loads((DATA / (content_id + '.json')).read_text())
            self.assertEqual(source['unit_id'], unit_id)
            self.assertEqual(len(source['items']), 3)
            self.assertLessEqual(sum(len(item['transcript']) for item in source['items']), 750)
            for item in source['items']:
                self.assertNotIn(item['transcript'], transcripts)
                transcripts.add(item['transcript'])
                self.assertTrue(item['requirement_id'].startswith('a1.listening.'))
                self.assertIn(item['requirement_id'], requirement_index())
                self.assertIn(item['answer'], {c['id'] for c in item['choices']})
            unit = get_unit(unit_id)
            self.assertEqual(unit['listening_available'], unit_id in LISTENING_IDS)
            if unit['listening_available']:
                self.assertEqual(unit['listening_title'], source['title'])


class A1ExpansionRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        provider = patch('utils.lazy.LazyService._get', side_effect=AssertionError('Authored operation must not call AI'))
        provider.start()
        self.addCleanup(provider.stop)

    def post(self, path, form):
        return self.client.post(path, data=form, headers={'X-CSRF-Token': self.token})

    def test_new_units_launch_owned_choice_form_and_distinct_writing_tasks(self):
        writing_locations = set()
        scenario_ids = {s['id'] for s in json.loads((DATA.parent / 'speaking_catalogue.json').read_text())['scenarios']}
        for unit_id in NEW_UNITS:
            unit = get_unit(unit_id)
            response = self.client.get('/curriculum/units/' + unit_id)
            self.assertEqual(response.status_code, 200)
            self.assertIn(unit['title'], response.text)
            self.assertIn(unit['speaking_href'].split('/')[-1].split('?')[0], scenario_ids)
            for stage in ('practice', 'forms'):
                path = '/curriculum/units/' + unit_id + '/' + stage
                form = {'profile_id': 'personal-learning', 'request_id': unit_id + '-' + stage}
                start = self.post(path, form)
                self.assertEqual(start.status_code, 303, start.text)
                self.assertEqual(self.post(path, form).location, start.location)
                state = self.client.get('/api/v1/learning-sessions/' + start.location.rsplit('/', 1)[1]).json
                self.assertNotIn('answer', state['item'])
                self.assertNotIn('accepted_answers', state['item'])
                with sqlite3.connect(self.app.config['DB_PATH']) as conn:
                    count = conn.execute('SELECT COUNT(*) FROM activity_task_contracts WHERE task_key LIKE ?', (state['id']+':%',)).fetchone()[0]
                self.assertEqual(count, len(_pack(unit, stage)['items']))
            writing = self.post('/curriculum/units/' + unit_id + '/writing', {'profile_id': 'personal-learning'})
            self.assertEqual(writing.status_code, 303, writing.text)
            self.assertEqual(self.client.get(writing.location).status_code, 200)
            writing_locations.add(writing.location)
        self.assertEqual(len(writing_locations), 3)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)

    def test_registered_listening_starts_audio_first_with_owned_playback_and_no_transcript_leak(self):
        for unit_id in LISTENING_IDS:
            start = self.post('/curriculum/units/' + unit_id + '/listening',
                              {'profile_id': 'personal-learning', 'request_id': unit_id+'-audio'})
            self.assertEqual(start.status_code, 303, start.text)
            path = '/api/v1/learning-sessions/' + start.location.rsplit('/', 1)[1]
            state = self.client.get(path).json
            authored = _pack(get_unit(unit_id), 'listening')['items'][0]
            self.assertEqual(state['item']['type'], 'listening_choice')
            self.assertFalse(state['item']['listened'])
            self.assertNotIn(authored['transcript'], json.dumps(state, ensure_ascii=False))
            with self.client.get(authored['audio']['url']) as recording:
                self.assertEqual(recording.status_code, 200)
            command = {'submission_id': unit_id+'-heard', 'expected_revision': state['revision'],
                       'item_id': state['item']['id']}
            result = self.client.post(path+'/listened', json=command, headers={'X-CSRF-Token': self.token})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json['item']['listened'])
            self.assertNotIn(authored['transcript'], json.dumps(result.json, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
