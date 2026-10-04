"""Retired public demos do not reopen guest data or weaken account isolation."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from hosted import create_hosted_app, main
from hosted_trial import COOKIE, GUEST_COOKIE
from migrations import upgrade_database
from services.ai_trial_budget import AITrialBudget
from tests.test_hosted_trial import IdentityProvider


class DemoRetirementTests(unittest.TestCase):
    base = 'https://arcade.example'

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.database = self.root / 'public.db'
        upgrade_database(str(self.database), backup=False)
        with sqlite3.connect(self.database) as conn:
            # Migration 025 adds the local compatibility profile. Requests
            # must not add visitor profiles or access credentials to it.
            self.initial_profiles = conn.execute('SELECT * FROM learning_profiles ORDER BY id').fetchall()
        env = patch.dict(os.environ, {
            'PUBLIC_DEMO': 'true', 'HOSTED_PUBLIC_DEMO_ENABLED': 'false',
            # A stale deployment flag must not override the explicit retirement.
            'HOSTED_GUEST_DEMO_ENABLED': 'true', 'HOSTED_ACCOUNTS_ENABLED': 'true',
            'HOSTED_HOSTNAME': 'arcade.example', 'HOSTED_TRIAL_ROOT': str(self.root / 'accounts'),
            'FLASK_SECRET_KEY': 'retirement-synthetic-secret-' * 3,
            'VOCAB_DB_PATH': str(self.database), 'VOCAB_SESSION_DIR': str(self.root / 'sessions'),
            'VOCAB_UPLOAD_DIR': str(self.root / 'uploads'), 'APP_MEDIA_DIR': str(self.root / 'media'),
            'WORD_POST_ASSET_DIR': str(self.root / 'assets'), 'ANKI_MEDIA_DIR': str(self.root / 'anki'),
            'GOOGLE_OAUTH_CLIENT_ID': '', 'GOOGLE_OAUTH_CLIENT_SECRET': '',
            'GITHUB_OAUTH_CLIENT_ID': 'synthetic-client', 'GITHUB_OAUTH_CLIENT_SECRET': 'synthetic-secret',
            'AI_TRIAL_ENABLED': 'true', 'DEMO_OPENAI_API_KEY': 'synthetic-openai',
            'DEMO_ELEVENLABS_API_KEY': 'synthetic-eleven', 'DEMO_OPENROUTER_API_KEY': 'synthetic-router',
        })
        env.start()
        self.addCleanup(env.stop)
        self.budget = AITrialBudget(self.root / 'accounts' / 'ai-budget.sqlite3', enabled=True)
        self.budget.initialize()
        network = patch('socket.socket.connect', side_effect=AssertionError('No live providers in retirement tests'))
        network.start()
        self.addCleanup(network.stop)
        disk = patch('hosted_trial.shutil.disk_usage')
        disk.start().return_value.free = 1024 ** 3
        self.addCleanup(disk.stop)
        self.app = create_hosted_app()
        self.dispatch = self.app.extensions['hosted_trial']
        self.dispatch.provider = IdentityProvider()
        self.client = self.app.test_client()
        self.addCleanup(self.close_executors)

    def close_executors(self):
        for app in self.dispatch.cache.values():
            for executor in app.extensions.get('trial_executors', []):
                executor.shutdown(wait=True)

    def get(self, path, **kwargs):
        return self.client.get(path, base_url=self.base, **kwargs)

    def assert_no_anonymous_workspace(self):
        self.assertFalse(self.dispatch.cache)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM guest_sessions').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identities').fetchone()[0], 0)
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute('SELECT * FROM learning_profiles ORDER BY id').fetchall(), self.initial_profiles)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM household_access').fetchone()[0], 0)

    def login(self):
        start = self.get('/trial/sign-in/github')
        state = parse_qs(urlsplit(start.location).query)['state'][0]
        self.assertEqual(self.get('/trial/callback?code=valid&state=' + state).status_code, 302)

    def test_demo_flag_defaults_off_and_stale_guest_flag_cannot_enable_it(self):
        with patch.dict(os.environ):
            os.environ.pop('HOSTED_PUBLIC_DEMO_ENABLED')
            app = create_hosted_app()
        self.assertFalse(app.extensions['hosted_trial'].guest_demo_enabled)
        self.assertFalse(app.extensions['hosted_trial'].public_preview_enabled)
        state = self.get('/trial/status').json
        self.assertFalse(state['demo_enabled'])
        self.assertEqual(state['demo_url'], '')
        self.assertTrue(state['enabled'])
        self.assertTrue(state['ai_enabled'])
        self.assert_no_anonymous_workspace()

    def test_old_demo_navigation_resets_to_home_without_provisioning(self):
        for path in ('/demo', '/demo/', '/demo?next=https://evil.example',
                     '/demo/vocab', '/demo/trial/account'):
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, '/#home')
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.head('/demo/', base_url=self.base).location, '/#home')
        self.assertEqual(self.client.get('/demo/', base_url='https://evil.example').status_code, 400)
        self.assert_no_anonymous_workspace()

    def test_old_demo_mutations_are_not_replayed_in_personal_accounts(self):
        for path in ('/demo/api/v1/user-session', '/demo/api', '/demo/trial/status'):
            response = self.get(path)
            self.assertEqual(response.status_code, 410)
            self.assertEqual(response.json['error']['code'], 'demo_retired')
            self.assertNotIn('Location', response.headers)
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            response = self.client.open('/demo/api/v1/card-generation/batches', method=method,
                                        json={}, base_url=self.base)
            self.assertEqual(response.status_code, 410)
            self.assertEqual(response.json['error']['code'], 'demo_retired')
            self.assertNotIn('Location', response.headers)
        self.assert_no_anonymous_workspace()

    def test_anonymous_root_assets_and_health_never_create_profiles(self):
        for path in ('/', '/vocab', '/post/profiles'):
            response = self.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('/trial/sign-in/github', response.text)
            self.assertNotIn('Try demo', response.text)
        for path in ('/static/css/account.css', '/static/images/favicon.svg', '/healthz'):
            with self.get(path) as response:
                self.assertEqual(response.status_code, 200, path)
        for path in ('/api/v1/user-session', '/api/v1/flashcards', '/api/v1/games'):
            self.assertEqual(self.get(path).status_code, 401)
        response = self.client.post('/api/v1/card-generation/batches', json={}, base_url=self.base)
        self.assertEqual(response.status_code, 401)
        self.assert_no_anonymous_workspace()

    def test_retirement_preserves_old_guest_records_and_files(self):
        old_data = self.root / 'accounts' / 'tenants' / 'old-guest'
        old_data.mkdir(parents=True)
        saved = old_data / 'keep.txt'
        saved.write_text('existing guest data')
        with sqlite3.connect(self.dispatch.registry) as conn:
            conn.execute('INSERT INTO guest_sessions VALUES (?,?,?,?)',
                         ('old-token-hash', 'demo:' + 'a' * 32, 1, 2))
        self.client.set_cookie(GUEST_COOKIE, 'stale-guest', domain='arcade.example')
        with patch.object(self.dispatch, '_cleanup_guests', side_effect=AssertionError('Retirement must not delete guest data')):
            self.assertEqual(self.get('/').status_code, 200)
            self.assertEqual(self.get('/demo/').location, '/#home')
        self.assertIsNone(self.client.get_cookie(GUEST_COOKIE, domain='arcade.example'))
        self.assertEqual(saved.read_text(), 'existing guest data')
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM guest_sessions').fetchone()[0], 1)

    def test_authenticated_workspace_and_budget_survive_old_demo_link(self):
        self.login()
        before = self.get('/api/v1/user-session').json
        personal_cookie = self.client.get_cookie(COOKIE, domain='arcade.example').value
        tenant = self.dispatch.cache['github:11']
        database = tenant.config['DB_PATH']
        with sqlite3.connect(database) as conn:
            conn.execute('CREATE TABLE retirement_sentinel(value TEXT)')
            conn.execute("INSERT INTO retirement_sentinel VALUES ('saved personal data')")
        self.assertEqual(self.get('/demo/vocab').location, '/#home')
        self.assertEqual(self.get('/api/v1/user-session').json['profile']['id'], before['profile']['id'])
        self.assertEqual(self.client.get_cookie(COOKIE, domain='arcade.example').value, personal_cookie)
        with sqlite3.connect(database) as conn:
            self.assertEqual(conn.execute('SELECT value FROM retirement_sentinel').fetchone()[0], 'saved personal data')
        self.assertTrue(tenant.config['AI_TRIAL_ENABLED'])
        self.assertEqual(tenant.config['AI_TRIAL_LEDGER_PATH'], str(self.budget.path))
        self.assertFalse(tenant.config['PUBLIC_DEMO'])
        self.assertTrue(self.app.config['PUBLIC_DEMO'])
        self.assertFalse(self.dispatch.guest_demo_enabled)
        self.assertEqual(self.get('/post/profiles').status_code, 200)
        self.assertNotIn('AI demo allowance', self.get('/trial/account').text)

    def test_startup_does_not_prepare_an_ephemeral_sample_database(self):
        with patch('public_demo.prepare_demo', side_effect=AssertionError('Demo creation retired')), \
             patch('migrations.upgrade_database') as migrate, \
             patch('hosted.recover_trial_voice_sessions'), patch('hosted.os.execvp') as launch:
            main()
        migrate.assert_called_once_with(str(self.database))
        launch.assert_called_once()
        self.assertEqual(os.environ['VOCAB_DB_PATH'], str(self.database))

    def test_public_account_mode_fails_closed_without_persistent_root(self):
        with patch.dict(os.environ, {'HOSTED_TRIAL_ROOT': '', 'HOSTED_ACCOUNTS_ENABLED': 'false', 'AI_TRIAL_ENABLED': 'false'}):
            with self.assertRaisesRegex(RuntimeError, 'HOSTED_TRIAL_ROOT'):
                create_hosted_app()
