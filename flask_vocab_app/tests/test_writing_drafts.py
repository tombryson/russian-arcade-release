"""Lesson autosaves can be retried without losing text or requesting feedback."""
import json
import unittest
from unittest.mock import Mock
from uuid import uuid4

from repositories.learning_repository import transaction
from tests.support import isolated_app


class WritingDraftTests(unittest.TestCase):
    def setUp(self):
        self.provider = Mock()
        self.app = isolated_app(self, {'WritingService': self.provider})
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        run = self.post('/api/v1/curriculum/units/location-destination-v2/runs', {
            'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1'}).json
        opened = self.post('/api/v1/curriculum/runs/' + run['id'] + '/steps/writing/start', {
            'submission_id': uuid4().hex, 'expected_revision': run['revision']})
        self.assertEqual(opened.status_code, 200, opened.json)
        with transaction(self.db) as conn:
            self.task = conn.execute("SELECT task_key FROM curriculum_unit_bindings WHERE run_id=? AND step_id='writing'",
                                     (run['id'],)).fetchone()[0]
        self.body = {'exercise_id': self.task, 'revision': 0, 'user_response': 'Я в школе.',
                     'submission_id': uuid4().hex}

    def post(self, url, body):
        return self.client.post(url, json=body, headers={'X-CSRF-Token': self.token})

    def save(self, body):
        return self.client.post('/writing/save', data=body,
            headers={'X-CSRF-Token': self.token, 'Accept': 'application/json'})

    def test_lost_acknowledgement_replays_without_overwriting_newer_text(self):
        saved = self.save(self.body)
        self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(saved.json['revision'], 1)
        self.assertEqual(self.save(self.body).json, saved.json)
        newer = {**self.body, 'revision': 1, 'submission_id': uuid4().hex, 'user_response': 'Я иду в парк.'}
        self.assertEqual(self.save(newer).json['revision'], 2)
        self.assertEqual(self.save(self.body).json, saved.json)
        with transaction(self.db) as conn:
            row = conn.execute('SELECT response,revision FROM writing_drafts WHERE exercise_id=?', (self.task,)).fetchone()
            self.assertEqual(tuple(row), ('Я иду в парк.', 2))
            for table in ('activity_review_submissions', 'writing_attempts', 'activity_criterion_reports', 'progression_events'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0, table)
        self.provider.assess_writing.assert_not_called()

    def test_conflicting_key_and_stale_tab_leave_saved_text_intact(self):
        self.assertEqual(self.save(self.body).status_code, 200)
        changed = {**self.body, 'user_response': 'Другая версия.'}
        self.assertEqual(self.save(changed).status_code, 409)
        self.assertEqual(self.save({**changed, 'submission_id': uuid4().hex}).status_code, 409)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT response FROM writing_drafts').fetchone()[0], self.body['user_response'])

    def test_pending_original_blocks_late_autosave(self):
        self.assertEqual(self.save(self.body).status_code, 200)
        saved = self.post('/api/v1/writing/tasks/' + self.task + '/submissions', {
            'submission_id': uuid4().hex, 'expected_revision': 1, 'response': {'text': self.body['user_response']}})
        self.assertEqual(saved.status_code, 200, saved.json)
        result = self.save({**self.body, 'revision': 2, 'submission_id': uuid4().hex, 'user_response': 'Позднее изменение.'})
        self.assertEqual(result.status_code, 409, result.json)
        self.assertEqual(result.json['error']['code'], 'review_pending')
        with transaction(self.db) as conn:
            self.assertEqual(json.loads(conn.execute('SELECT original_json FROM activity_review_submissions').fetchone()[0]),
                             {'text': self.body['user_response']})
        self.provider.assess_writing.assert_not_called()

    def test_csrf_and_ownership_are_checked_before_receipt_replay(self):
        self.assertEqual(self.client.post('/writing/save', data=self.body).status_code, 403)
        self.assertEqual(self.save(self.body).status_code, 200)
        profile = self.post('/api/v1/user-session/profiles', {'display_name': 'Other'})
        self.assertEqual(profile.status_code, 201, profile.json)
        self.token = profile.json['csrf_token']
        self.assertEqual(self.save(self.body).status_code, 404)
        self.provider.assess_writing.assert_not_called()

    def test_new_draft_after_review_becomes_resume_action_without_erasing_result(self):
        from services.activity_review_submissions import task_work_state
        from tests.test_activity_review_submissions import criterion_report
        text = self.body['user_response']
        saved = self.post('/api/v1/writing/tasks/' + self.task + '/submissions', {
            'submission_id': uuid4().hex, 'expected_revision': 0, 'response': {'text': text}}).json
        with transaction(self.db) as conn:
            row = conn.execute("SELECT profile_id,contract_json FROM activity_task_contracts WHERE activity='writing' AND task_key=?", (self.task,)).fetchone()
            owner, contract = row['profile_id'], json.loads(row['contract_json'])
        self.provider.assess_writing.return_value = {'score': 8, 'strength': 'Clear message.',
            'next_step': 'Keep practising.', 'example': text, 'criterion_report': criterion_report(contract, text)}
        result = self.post('/api/v1/writing/submissions/' + saved['id'] + '/review', {})
        self.assertEqual(result.json['work_state'], 'reviewed', result.json)
        with transaction(self.db) as conn:
            self.assertEqual(task_work_state(conn, owner, 'writing', self.task), 'reviewed')
        changed = self.save({**self.body, 'revision': 1, 'user_response': 'Я в библиотеке.'})
        self.assertEqual(changed.status_code, 200, changed.json)
        with transaction(self.db) as conn:
            self.assertEqual(task_work_state(conn, owner, 'writing', self.task), 'draft')
            self.assertEqual(conn.execute('SELECT response FROM writing_attempts').fetchone()[0], text)
        domain = next(row for row in self.client.get('/api/v1/curriculum/summary').json['domains'] if row['id'] == 'writing')
        self.assertEqual(domain['next_action']['kind'], 'resume')
        self.assertIsNotNone(domain['latest'])
        self.provider.assess_writing.assert_called_once()
