"""Exact lesson review routes retain originals behind real hosted guest limits."""
import io
import sqlite3
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from hosted import create_hosted_app
from repositories.learning_repository import transaction
from services.ai_trial_budget import AITrialBudget
from tests import test_hosted_guest_demo as guest_fixtures
from tests.test_unit_exchange import recording


class HostedSequenceReviewTests(unittest.TestCase):
    def setUp(self):
        guest_fixtures.HostedGuestCompositionTests.setUp(self)
        self.app = create_hosted_app()
        self.dispatch = self.app.extensions['hosted_trial']
        self.client = self.app.test_client()
        self.assertEqual(self.client.get('/demo', base_url=self.base).status_code, 302)
        state = self.client.get('/demo/api/v1/user-session', base_url=self.base).json
        self.token = state['csrf_token']
        self.workspace = next(iter(self.dispatch.cache.values()))
        self.db = self.workspace.config['DB_PATH']
        self.workspace.config['OPENAI_MODEL_FAST'] = 'gpt-5-mini'
        self.addCleanup(self.close_executors)

    def close_executors(self):
        for tenant in self.dispatch.cache.values():
            for executor in tenant.extensions.get('trial_executors', []):
                executor.shutdown(wait=True)

    def post(self, path, body=None, **options):
        return self.client.post('/demo' + path, base_url=self.base,
            headers={'X-CSRF-Token': self.token}, **({'json': body or {}} if not options else options))

    def originals(self):
        run = self.post('/api/v1/curriculum/units/location-destination-v2/runs',
            {'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1'}).json
        tasks = {}
        for step in ('writing', 'reading', 'speaking'):
            opened = self.post('/api/v1/curriculum/runs/' + run['id'] + '/steps/' + step + '/start',
                {'submission_id': uuid4().hex, 'expected_revision': run['revision']})
            self.assertEqual(opened.status_code, 200, opened.text)
            run = opened.json['run']
            tasks[step] = opened.json['url'].rsplit('/', 1)[1]
        responses = {
            'writing': {'text': 'Я сейчас в школе. Потом иду в парк. Встретимся в парке.'},
            'comprehension': {'answers': ['В школе.', 'В парк.', 'В парке.']},
        }
        submissions = {}
        for activity, task in (('writing', tasks['writing']), ('comprehension', tasks['reading'])):
            saved = self.post(f'/api/v1/{activity}/tasks/{task}/submissions',
                {'submission_id': uuid4().hex, 'expected_revision': 0, 'response': responses[activity]})
            self.assertEqual(saved.status_code, 200, saved.text)
            submissions[activity] = saved.json['id']
        exchange = '/api/v1/unit-exchanges/' + tasks['speaking']
        state = self.client.get('/demo' + exchange, base_url=self.base).json
        for _ in range(2):
            turn = state['current_turn']['id']
            heard = self.post(exchange + '/turns/' + turn + '/listened',
                {'submission_id': uuid4().hex, 'expected_revision': state['revision']})
            self.assertEqual(heard.status_code, 200, heard.text)
            saved = self.post(exchange + '/turns/' + turn + '/recording', data={
                'audio': (io.BytesIO(recording()), 'reply.wav'), 'submission_id': uuid4().hex,
                'expected_revision': str(heard.json['revision'])}, content_type='multipart/form-data')
            self.assertEqual(saved.status_code, 200, saved.text)
            state = saved.json
        self.assertEqual(state['work_state'], 'submitted')
        return [
            ('writing.review_original', '/api/v1/writing/submissions/' + submissions['writing'] + '/review', 200),
            ('writing.retry_saved_review', '/writing/review/' + submissions['writing'], 303),
            ('comprehension.review_original', '/api/v1/comprehension/submissions/' + submissions['comprehension'] + '/review', 200),
            ('comprehension.retry_saved_review', '/comprehension/review/' + submissions['comprehension'], 303),
            ('unit_exchange.review', exchange + '/review', 200),
        ]

    def test_exact_review_routes_apply_guest_spend_and_request_caps_before_paid_work(self):
        sdk = Mock()
        with patch('openai.OpenAI', return_value=sdk):
            routes = self.originals()
            with transaction(self.db) as conn:
                before = {row['id']: row['original_json'] for row in conn.execute('SELECT id,original_json FROM activity_review_submissions')}
            identity = self.workspace.config['AI_TRIAL_IDENTITY']
            self.assertTrue(identity.startswith('demo:'))
            self.assertTrue(self.workspace.config['HOSTED_GUEST_DEMO'])
            self.assertTrue(self.workspace.config['HOSTED_AI_TRIAL'])
            self.assertFalse(self.workspace.config['PUBLIC_DEMO'])
            reserve = AITrialBudget.reserve
            with patch('services.ai_trial_budget.ACCOUNT_DAILY_LIMIT', 0), \
                    patch.object(AITrialBudget, 'reserve', autospec=True, side_effect=reserve) as guarded:
                for endpoint, path, status in routes:
                    with self.subTest(endpoint=endpoint):
                        self.assertEqual(self.workspace.url_map.bind('arcade.example').match(path, method='POST')[0], endpoint)
                        response = self.post(path)
                        self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(guarded.call_count, len(routes))
                for call in guarded.call_args_list:
                    self.assertEqual(call.args[1], identity)
            with transaction(self.db) as conn:
                rows = list(conn.execute('SELECT id,original_json,review_status,review_error FROM activity_review_submissions'))
                self.assertEqual({row['id']: row['original_json'] for row in rows}, before)
                self.assertTrue(all(row['review_status'] == 'review_unavailable' and row['review_error'] == 'budget_exhausted' for row in rows))
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_attempts').fetchone()[0], 0)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM comprehension_attempts').fetchone()[0], 0)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)
            sdk.responses.create.assert_not_called()
            sdk.chat.completions.create.assert_not_called()
            with sqlite3.connect(self.ledger_path) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM trial_requests').fetchone()[0], 0)
            # An unknown route stays a404; no fallback sends it to a provider.
            self.assertEqual(self.post('/api/v1/unit-exchanges/unknown/review-unknown').status_code, 404)
            with sqlite3.connect(self.dispatch.registry) as conn:
                conn.execute('INSERT OR REPLACE INTO request_limits VALUES (?,?,?,?)',
                    (identity, 'writes', int(self.dispatch.clock()) // 60, 30))
            with patch.object(AITrialBudget, 'reserve', autospec=True, side_effect=reserve) as guarded:
                for endpoint, path, _ in routes:
                    with self.subTest(rate_limited=endpoint):
                        response = self.post(path)
                        self.assertEqual(response.status_code, 429, response.text)
                        self.assertEqual(response.json['error']['code'], 'rate_limited')
                guarded.assert_not_called()
            with transaction(self.db) as conn:
                self.assertEqual({row['id']: row['original_json'] for row in conn.execute('SELECT id,original_json FROM activity_review_submissions')}, before)
            for _, path, _ in routes:
                if path.startswith('/api/'):
                    reopened = self.client.get('/demo' + path.removesuffix('/review'), base_url=self.base)
                    self.assertEqual(reopened.status_code, 200, reopened.text)
                    self.assertEqual(reopened.json['work_state'], 'review_unavailable')
            sdk.responses.create.assert_not_called()
            sdk.chat.completions.create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
