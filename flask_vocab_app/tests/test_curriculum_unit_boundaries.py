"""Unit entry points retain normal ownership, saved feedback and spending limits."""
from pathlib import Path
import os
import shutil
import sqlite3
import unittest
from unittest.mock import Mock, patch

from hosted_trial import install_trial_session
from repositories.learning_repository import LearningError
from services.ai_trial_budget import AITrialBudget
from services.curriculum_units import get_unit, start_practice, start_writing
from tests.support import isolated_app


UNIT = 'location-destination-v1'
PATH = '/curriculum/units/' + UNIT


class CurriculumUnitBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.state = self.client.get('/api/v1/user-session').json
        self.headers = {'X-CSRF-Token': self.state['csrf_token']}

    def start(self):
        response = self.client.post(PATH + '/practice', headers=self.headers,
            data={'profile_id': self.state['profile']['id'], 'request_id': 'start-unit'})
        self.assertEqual(response.status_code, 303, response.text)
        return self.client.get('/api/v1/learning-sessions/' + response.location.rsplit('/', 1)[1]).json

    def answer(self, saved):
        return {'submission_id': 'first-answer', 'expected_revision': saved['revision'],
                'item_id': saved['item']['id'], 'answer': {'choice_id': 'school'}}

    def test_retried_answer_has_one_attempt_and_report_and_keeps_frozen_explanation(self):
        saved = self.start()
        path = '/api/v1/learning-sessions/' + saved['id']
        body = self.answer(saved)
        first = self.client.post(path + '/attempts', json=body, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.text)
        repeated = self.client.post(path + '/attempts', json=body, headers=self.headers)
        self.assertEqual(repeated.json, first.json)
        original = first.json['attempts'][0]['feedback']['explanation']
        revised_unit = get_unit(UNIT)
        revised_unit['questions'][0]['explanation'] = 'A later edited explanation.'
        with patch('services.curriculum_units.get_unit', return_value=revised_unit):
            restored = self.client.get(path)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json['attempts'][0]['feedback']['explanation'], original)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 1)

    def test_profile_switch_cannot_read_answer_or_replay_another_profiles_work(self):
        saved = self.start()
        path = '/api/v1/learning-sessions/' + saved['id']
        body = self.answer(saved)
        self.assertEqual(self.client.post(path + '/attempts', json=body, headers=self.headers).status_code, 200)
        created = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Other learner'},
                                   headers=self.headers)
        self.assertEqual(created.status_code, 201, created.text)
        headers = {'X-CSRF-Token': created.json['csrf_token']}
        self.assertEqual(self.client.get(path).status_code, 404)
        for endpoint in ('attempts', 'help'):
            command = body if endpoint == 'attempts' else {k: v for k, v in body.items() if k != 'answer'}
            denied = self.client.post(path + '/' + endpoint, json=command, headers=headers)
            self.assertEqual(denied.status_code, 404, denied.text)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 1)

    def test_evidence_failure_rolls_back_the_answer_and_revision(self):
        saved = self.start()
        path = '/api/v1/learning-sessions/' + saved['id']
        with patch('services.curriculum_units.save_report', side_effect=RuntimeError('test evidence failure')):
            with self.assertRaisesRegex(RuntimeError, 'test evidence failure'):
                self.client.post(path + '/attempts', json=self.answer(saved), headers=self.headers)
        self.assertEqual(self.client.get(path).json['revision'], saved['revision'])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_commands').fetchone()[0], 0)

    def test_services_check_expected_profile_inside_the_write_transaction(self):
        with self.client.session_transaction() as session:
            credential = session['personal_access_id']
        with self.app.app_context():
            for action in ('practice', 'writing'):
                with self.subTest(action=action), self.assertRaises(LearningError) as error:
                    if action == 'practice':
                        start_practice(self.db, credential, UNIT, 'wrong-profile', expected_profile_id='other')
                    else:
                        start_writing(self.db, credential, UNIT, expected_profile_id='other')
                self.assertEqual(error.exception.code, 'profile_changed')
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_sessions').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_exercises').fetchone()[0], 0)


class PublicCurriculumUnitBoundaryTests(unittest.TestCase):
    def setUp(self):
        from hosted import create_hosted_app
        from public_demo import prepare_demo
        environment = patch.dict(os.environ, {'PUBLIC_DEMO': 'true',
            'FLASK_SECRET_KEY': 'synthetic-test-secret-' * 3, 'HOSTED_HOSTNAME': 'arcade.example',
            'HOSTED_TRIAL_ROOT': '', 'AI_TRIAL_ENABLED': 'false', 'HOSTED_ACCOUNTS_ENABLED': 'false'})
        environment.start()
        self.addCleanup(environment.stop)
        root = prepare_demo()
        self.addCleanup(shutil.rmtree, root)
        self.app = create_hosted_app()
        self.a, self.b = self.app.test_client(), self.app.test_client()
        self.base = 'https://arcade.example'
        provider = patch('utils.lazy.LazyService._get', side_effect=AssertionError('Authored practice must not resolve a provider'))
        self.provider = provider.start()
        self.addCleanup(provider.stop)

    def test_public_unit_is_playable_owned_and_cannot_create_a_writing_draft(self):
        a = self.a.get('/api/v1/user-session', base_url=self.base).json
        b = self.b.get('/api/v1/user-session', base_url=self.base).json
        headers = {'X-CSRF-Token': a['csrf_token']}
        form = {'profile_id': a['profile']['id'], 'request_id': 'demo-unit'}
        self.assertEqual(self.a.get(PATH, base_url=self.base).status_code, 200)
        self.assertEqual(self.a.post(PATH + '/practice', data=form, base_url=self.base).status_code, 403)
        response = self.a.post(PATH + '/practice', data=form, headers=headers, base_url=self.base)
        self.assertEqual(response.status_code, 303, response.text)
        path = '/api/v1/learning-sessions/' + response.location.rsplit('/', 1)[1]
        saved = self.a.get(path, base_url=self.base).json
        command = {'submission_id': 'answer', 'expected_revision': saved['revision'],
                   'item_id': saved['item']['id'], 'answer': {'choice_id': 'school'}}
        denied = self.b.post(path + '/attempts', json=command,
            headers={'X-CSRF-Token': b['csrf_token']}, base_url=self.base)
        self.assertEqual(denied.status_code, 404, denied.text)
        self.assertEqual(self.b.get(path, base_url=self.base).status_code, 404)
        self.assertEqual(self.a.post(path + '/attempts', json=command, headers=headers, base_url=self.base).status_code, 200)
        self.assertEqual(self.a.post(PATH + '/writing', data=form, headers=headers, base_url=self.base).status_code, 403)
        self.assertEqual(self.a.post('/api/v1/learning-sessions', json={}, headers=headers, base_url=self.base).status_code, 403)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_exercises').fetchone()[0], 0)
        self.provider.assert_not_called()


class HostedCurriculumUnitBudgetTests(unittest.TestCase):
    def test_authored_writing_entry_is_free_and_later_check_reserves_before_provider(self):
        app = isolated_app(self, signed_in=False)
        ledger_path = Path(app.config['DB_PATH']).with_name('budget.sqlite3')
        ledger = AITrialBudget(ledger_path, enabled=True)
        ledger.initialize()
        ledger.authorize_identity('verified-unit-user')
        app.config.update(HOSTED_AI_TRIAL=True, AI_TRIAL_ENABLED=True,
                          AI_TRIAL_IDENTITY='verified-unit-user', AI_TRIAL_LEDGER_PATH=str(ledger_path),
                          OPENAI_API_KEY='synthetic-test-only')
        install_trial_session(app)
        client = app.test_client()
        state = client.get('/api/v1/user-session').json
        headers = {'X-CSRF-Token': state['csrf_token']}
        with patch('utils.lazy.LazyService._get', side_effect=AssertionError('Starting authored writing is free')):
            response = client.post(PATH + '/writing', data={'profile_id': state['profile']['id']}, headers=headers)
        self.assertEqual(response.status_code, 303, response.text)
        with sqlite3.connect(ledger_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM trial_requests').fetchone()[0], 0)
        exercise_id = int(response.location.rsplit('/', 1)[1])
        raw = Mock()

        def checked_call(**kwargs):
            with sqlite3.connect(ledger_path) as conn:
                held = conn.execute('SELECT identity,state,reserved FROM trial_requests').fetchone()
            self.assertEqual(held[:2], ('verified-unit-user', 'reserved'))
            self.assertGreater(held[2], 0)
            self.assertEqual(kwargs['max_output_tokens'], 4096)
            raise TimeoutError('Fake provider interrupted after reservation')

        raw.responses.create.side_effect = checked_call
        with patch('openai.OpenAI', return_value=raw), patch('services.writing_service.model_for', return_value='gpt-5.6-luna'):
            checked = client.post('/writing/assess', data={'exercise_id': exercise_id, 'revision': 0,
                'user_response': 'Я в школе. Потом я иду в парк. Я буду ждать в парке.'}, headers=headers)
        self.assertEqual(checked.status_code, 503, checked.text)
        raw.responses.create.assert_called_once()
        with sqlite3.connect(ledger_path) as conn:
            state, actual, reserved = conn.execute('SELECT state,actual,reserved FROM trial_requests').fetchone()
            self.assertEqual((state, actual), ('settled', reserved))
        with sqlite3.connect(app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_attempts').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
