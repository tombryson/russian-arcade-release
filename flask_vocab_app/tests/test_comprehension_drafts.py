"""Saving partial reading answers never checks them or changes evidence."""
import json
import unittest
from unittest.mock import Mock
from uuid import uuid4

from repositories.learning_repository import transaction
from repositories.comprehension_repository import ComprehensionRepository
from repositories.curriculum_sequence_repository import validate_saved_sequences
from services.activity_review_submissions import task_work_state
from tests.support import isolated_app


class ComprehensionDraftTests(unittest.TestCase):
    def setUp(self):
        self.provider = Mock()
        self.app = isolated_app(self, {'ComprehensionService': self.provider})
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        run = self.post('/api/v1/curriculum/units/location-destination-v2/runs',
            {'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1'}).json
        self.run = run['id']
        opened = self.post('/api/v1/curriculum/runs/' + self.run + '/steps/reading/start',
            {'submission_id': uuid4().hex, 'expected_revision': run['revision']})
        self.assertEqual(opened.status_code, 200, opened.json)
        with transaction(self.db) as conn:
            row = conn.execute("SELECT task_key,profile_id FROM curriculum_unit_bindings WHERE run_id=? AND step_id='reading'", (self.run,)).fetchone()
            self.task, self.owner = row
        self.url = '/api/v1/comprehension/tasks/' + self.task + '/draft'
        self.body = {'submission_id': uuid4().hex, 'expected_revision': 0, 'expected_draft_revision': 0,
                     'response': {'answers': ['В школе.', '', '']}}

    def post(self, url, body):
        return self.client.post(url, json=body, headers={'X-CSRF-Token': self.token})

    def test_partial_draft_restores_without_review_rewards_or_assistance(self):
        saved = self.post(self.url, self.body)
        self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(saved.json['revision'], 0)
        self.assertEqual(saved.json['draft_revision'], 1)
        self.assertEqual(self.post(self.url, self.body).json, saved.json)
        with self.client:
            self.client.get('/api/v1/user-session')
            display = ComprehensionRepository(self.db).display(self.task)
        self.assertEqual(display['answers'], ['В школе.', '', ''])
        self.assertEqual(display['draft_revision'], 1)
        self.assertEqual(display['support'], [])
        self.assertIsNone(display['assessment'])
        with transaction(self.db) as conn:
            self.assertEqual(task_work_state(conn, self.owner, 'comprehension', self.task), 'draft')
            for table in ('activity_review_submissions', 'comprehension_attempts', 'activity_criterion_reports', 'progression_events'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0, table)
            validate_saved_sequences(conn)
        self.provider.assess_task.assert_not_called()

    def test_conflicting_request_and_stale_tab_never_replace_newer_draft(self):
        self.assertEqual(self.post(self.url, self.body).status_code, 200)
        changed = {**self.body, 'response': {'answers': ['Другая версия.', '', '']}}
        self.assertEqual(self.post(self.url, changed).status_code, 409)
        self.assertEqual(self.post(self.url, {**changed, 'submission_id': uuid4().hex}).status_code, 409)
        accepted = self.post(self.url, {**changed, 'submission_id': uuid4().hex, 'expected_draft_revision': 1})
        self.assertEqual(accepted.status_code, 200, accepted.json)
        with transaction(self.db) as conn:
            self.assertEqual(json.loads(conn.execute('SELECT answers_json FROM comprehension_task_drafts').fetchone()[0]), changed['response']['answers'])

    def test_submitted_original_prevents_late_autosave(self):
        self.assertEqual(self.post(self.url, self.body).status_code, 200)
        saved = self.post('/api/v1/comprehension/tasks/' + self.task + '/submissions', {
            'submission_id': uuid4().hex, 'expected_revision': 0,
            'response': {'answers': ['В школе.', 'В парк.', 'В парке.']}})
        self.assertEqual(saved.status_code, 200, saved.json)
        result = self.post(self.url, {**self.body, 'submission_id': uuid4().hex, 'expected_draft_revision': 1})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json['error']['code'], 'review_pending')
        with transaction(self.db) as conn:
            self.assertEqual(task_work_state(conn, self.owner, 'comprehension', self.task), 'submitted')
            self.assertEqual(json.loads(conn.execute('SELECT original_json FROM activity_review_submissions').fetchone()[0])['answers'], ['В школе.', 'В парк.', 'В парке.'])
        self.provider.assess_task.assert_not_called()

    def test_csrf_profile_ownership_and_invalid_answers(self):
        self.assertEqual(self.client.post(self.url, json=self.body).status_code, 403)
        for answers in (['too few'], [None, '', ''], ['\x00', '', ''], ['a' * 4001, '', '']):
            result = self.post(self.url, {**self.body, 'response': {'answers': answers}})
            self.assertEqual(result.status_code, 400, result.json)
        changed = self.post('/api/v1/user-session/profiles', {'display_name': 'Other'})
        self.assertEqual(changed.status_code, 201, changed.json)
        self.token = changed.json['csrf_token']
        self.assertEqual(self.post(self.url, self.body).status_code, 404)
        self.provider.assess_task.assert_not_called()
