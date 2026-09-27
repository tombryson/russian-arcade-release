"""Additional authored units reuse owned sessions without claiming proficiency."""
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from contracts.learning import assess_activity_answer, validate_pack
from services.activity_evidence import validate_saved_evidence
from services.curriculum_units import (UNIT_IDS, LISTENING_IDS, get_unit, _pack, _questions, _practice_contract,
                                       _unit_for_pack, writing_task)
from tests.support import isolated_app

NEW_UNITS = ('possession-absence-v1', 'objects-recipients-v1', 'time-routine-v1')


class CurriculumUnitExpansionTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        self.provider = patch('utils.lazy.LazyService._get', side_effect=AssertionError('Authored unit operations must not call AI'))
        self.provider.start()
        self.addCleanup(self.provider.stop)

    def post(self, path, *, form=None, body=None):
        return self.client.post(path, data=form, json=body, headers={'X-CSRF-Token': self.token})

    def start(self, unit, stage):
        response = self.post('/curriculum/units/' + unit + '/' + stage,
                            form={'profile_id': 'personal-learning', 'request_id': unit + '-' + stage})
        self.assertEqual(response.status_code, 303, response.text)
        return self.client.get('/api/v1/learning-sessions/' + response.location.rsplit('/', 1)[1]).json

    def test_entries_have_relevant_copy_valid_speaking_links_and_no_unprepared_audio(self):
        scenarios = json.loads((Path(__file__).resolve().parents[1] / 'data/speaking_catalogue.json').read_text())
        scenario_ids = {s['id'] for s in scenarios['scenarios']}
        for unit_id in NEW_UNITS:
            unit = get_unit(unit_id)
            html = self.client.get('/curriculum/units/' + unit_id).text
            self.assertIn(unit['title'], html)
            self.assertNotIn('Four questions about location and destination', html)
            if unit_id in LISTENING_IDS:
                self.assertIn('/' + unit_id + '/listening', html)
                self.assertTrue(unit['listening_available'])
            else:
                self.assertNotIn('/' + unit_id + '/listening', html)
            if unit.get('speaking_href'):
                self.assertIn(unit['speaking_href'], html)
                self.assertIn(unit['speaking_href'].split('/')[-1].split('?')[0], scenario_ids)
            else:
                self.assertNotIn('Open conversation', html)
            if unit_id not in LISTENING_IDS:
                unavailable = self.post('/curriculum/units/' + unit_id + '/listening',
                    form={'profile_id': 'personal-learning', 'request_id': 'unprepared-' + unit_id})
                self.assertEqual(unavailable.status_code, 404, unavailable.text)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_sessions').fetchone()[0], 0)

    def test_each_stage_freezes_before_response_and_preserves_answers_without_gating_or_vocab_writes(self):
        with sqlite3.connect(self.db) as conn:
            word_count = conn.execute('SELECT COUNT(*) FROM words').fetchone()[0]
        expected = 0
        for unit_id in NEW_UNITS:
            for stage in ('practice', 'forms'):
                pack = _pack(get_unit(unit_id), stage)
                saved = self.start(unit_id, stage)
                self.assertEqual(self.start(unit_id, stage)['id'], saved['id'])
                with sqlite3.connect(self.db) as conn:
                    count = conn.execute('SELECT COUNT(*) FROM activity_task_contracts WHERE task_key LIKE ?', (saved['id'] + ':%',)).fetchone()[0]
                self.assertEqual(count, len(pack['items']))
                for index, item in enumerate(pack['items']):
                    self.assertNotIn('answer', saved['item'])
                    self.assertNotIn('accepted_answers', saved['item'])
                    raw = '  ' + item['accepted_answers'][-1].upper() + '!  ' if stage == 'forms' else item['answer']
                    answer = {'text': raw} if stage == 'forms' else {'choice_id': raw}
                    body = {'submission_id': 'answer-' + str(index), 'expected_revision': saved['revision'],
                            'item_id': item['id'], 'answer': answer}
                    path = '/api/v1/learning-sessions/' + saved['id'] + '/attempts'
                    first = self.post(path, body=body)
                    self.assertEqual(first.status_code, 200, first.text)
                    self.assertEqual(self.post(path, body=body).json, first.json)
                    saved = first.json
                    self.assertEqual(saved['attempts'][-1]['outcome'], 'correct')
                    if stage == 'forms':
                        self.assertEqual(saved['attempts'][-1]['answer']['text'], raw)
                expected += len(pack['items'])
                self.assertEqual(saved['status'], 'completed')
                self.assertEqual(self.client.get('/api/v1/learning-sessions/' + saved['id']).json['attempts'], saved['attempts'])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], expected)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], expected)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], word_count)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            before = conn.total_changes
            validate_saved_evidence(conn)
            self.assertEqual(conn.total_changes, before)

    def test_writing_tasks_keep_their_own_communicative_requirement_and_resume_separately(self):
        locations = set()
        for unit_id in NEW_UNITS:
            unit = get_unit(unit_id)
            task = writing_task(unit)
            criterion = task['curriculum_contract']['criteria'][0]
            self.assertEqual(criterion['id'], unit['writing_focus']['id'])
            self.assertEqual(criterion['expectation'], unit['writing_focus']['expectation'])
            self.assertEqual(criterion['response_mode'], 'independent_writing')
            self.assertEqual(len(task['required_words']), 3)
            path = '/curriculum/units/' + unit_id + '/writing'
            response = self.post(path, form={'profile_id': 'personal-learning'})
            self.assertEqual(response.status_code, 303, response.text)
            self.assertEqual(self.post(path, form={'profile_id': 'personal-learning'}).location, response.location)
            locations.add(response.location)
            self.assertEqual(self.client.get(response.location).status_code, 200)
        self.assertEqual(len(locations), 3)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_exercises').fetchone()[0], 3)
            contracts = [json.loads(r[0]) for r in conn.execute("SELECT contract_json FROM activity_task_contracts WHERE activity='writing'")]
            self.assertEqual({c['rubric_version'] for c in contracts}, set(NEW_UNITS))


class CurriculumUnitContentTests(unittest.TestCase):
    def test_published_location_content_and_contracts_are_unchanged(self):
        unit = get_unit('location-destination-v1')
        snapshot = {'packs': [_pack(unit, stage) for stage in ('practice', 'forms', 'listening')],
            'writing': writing_task(unit),
            'contracts': [_practice_contract(unit, item, question, 'validation')
                for stage in ('practice', 'forms', 'listening')
                for item, question in zip(_pack(unit, stage)['items'], _questions(unit, stage))]}
        self.assertEqual(hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                         '2f7b797febb3ebc2f381f5fb99e9c5296ba92d9ec2c5dd2baa8c2820be6a32eb')

    def test_expansion_includes_contextual_reading_and_does_not_accept_case_or_conjugation_errors(self):
        bad = {'possession-absence-v1': ['Мария', 'книга', 'брат', 'ты'],
               'objects-recipients-v1': ['газета', 'друг', 'сестру', 'маму'],
               'time-routine-v1': ['среде', 'читают', 'писаю', 'работал', 'будут']}
        for unit_id in NEW_UNITS:
            unit = get_unit(unit_id)
            self.assertEqual(len(unit['groups']), 3)
            self.assertGreaterEqual(sum(q['requirement_id'].startswith('a1.reading.') for q in unit['questions']), 2)
            for stage in ('practice', 'forms'):
                pack = validate_pack(_pack(unit, stage))
                self.assertEqual(_unit_for_pack(pack)[1], stage)
            for item, wrong in zip(_pack(unit, 'forms')['items'], bad[unit_id]):
                for accepted in item['accepted_answers']:
                    self.assertTrue(assess_activity_answer(item, {'text': accepted})[1])
                self.assertFalse(assess_activity_answer(item, {'text': wrong})[1])

    def test_unknown_stage_version_is_rejected_instead_of_becoming_listening(self):
        for unit_id in UNIT_IDS:
            pack = _pack(get_unit(unit_id))
            pack['id'] += ':unknown-v9'
            with self.assertRaisesRegex(ValueError, 'Unknown published unit'):
                _unit_for_pack(pack)


if __name__ == '__main__':
    unittest.main()
