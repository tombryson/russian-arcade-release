"""Hosted sample and funded workspace composition, without provider traffic."""
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from hosted import create_hosted_app
from hosted_trial import COOKIE
from public_demo import prepare_demo
from services.ai_trial_budget import AITrialBudget, TrialDenied
from tests.test_hosted_trial import IdentityProvider


class HostedTrialIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Account-isolation assertions must not depend on the developer's disk.
        disk = patch('hosted_trial.shutil.disk_usage')
        disk.start().return_value.free = 1024 * 1024 * 1024
        self.addCleanup(disk.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.env = patch.dict(os.environ, {
            'PUBLIC_DEMO': 'true', 'HOSTED_HOSTNAME': 'arcade.example',
            'FLASK_SECRET_KEY': 'synthetic-session-secret-' * 3,
            'HOSTED_TRIAL_ROOT': str(self.root), 'AI_TRIAL_ENABLED': 'true',
            'GOOGLE_OAUTH_CLIENT_ID': '', 'GOOGLE_OAUTH_CLIENT_SECRET': '',
            'GITHUB_OAUTH_CLIENT_ID': 'synthetic-client-id',
            'GITHUB_OAUTH_CLIENT_SECRET': 'synthetic-client-secret',
            'DEMO_OPENAI_API_KEY': 'synthetic-demo-openai',
            'DEMO_ELEVENLABS_API_KEY': 'synthetic-demo-elevenlabs',
            'DEMO_OPENROUTER_API_KEY': 'synthetic-demo-openrouter',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.samples = prepare_demo()
        self.addCleanup(shutil.rmtree, self.samples)
        self.ledger_path = self.root / 'ai-budget.sqlite3'
        self.ledger = AITrialBudget(self.ledger_path, enabled=True)
        self.ledger.initialize()
        self.network = patch('socket.socket.connect', side_effect=AssertionError('Hosted smoke must not call providers'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.base = 'https://arcade.example'

    def app(self):
        app = create_hosted_app()
        self.provider = IdentityProvider()
        app.extensions['hosted_trial'].provider = self.provider
        return app

    def login(self, client, identity='github:11'):
        self.provider.identity = identity
        response = client.get('/trial/sign-in/github', base_url=self.base, buffered=True)
        state = parse_qs(urlsplit(response.location).query)['state'][0]
        response = client.get('/trial/callback?code=valid&state=' + state, base_url=self.base, buffered=True)
        self.assertEqual(response.status_code, 302, response.text)

    def test_all_core_activity_pages_work_without_calls_and_samples_remain_public(self):
        app = self.app()
        visitor = app.test_client()
        learner = app.test_client()
        self.assertEqual(visitor.get('/comprehension', base_url=self.base).status_code, 403)
        self.assertEqual(visitor.get('/', base_url=self.base).status_code, 200)
        for path in ('/post', '/post/'):
            response = visitor.get(path + '?v=bookmark', base_url=self.base)
            self.assertEqual(response.status_code, 308)
            self.assertEqual(response.location, '/?v=bookmark')
        self.assertEqual(visitor.get('/tools/anki/', base_url=self.base).status_code, 403)
        self.login(learner)
        self.assertEqual(learner.get('/tools/anki/', base_url=self.base).status_code, 403)
        for path in ('/post', '/post/'):
            response = learner.get(path + '?v=bookmark', base_url=self.base)
            self.assertEqual(response.status_code, 308)
            self.assertEqual(response.location, '/?v=bookmark')
        paths = ('/', '/comprehension', '/writing', '/word_jumble', '/sentences',
                 '/sentences/saved', '/lessons', '/vocab', '/api/v1/user-session',
                 '/api/v1/flashcards', '/api/v1/games', '/api/v1/first-steps',
                 '/api/v1/live-conversations/scenarios', '/api/v1/live-conversations/options',
                 '/api/v1/conversations/options')
        for path in paths:
            response = learner.get(path, base_url=self.base, buffered=True)
            self.assertEqual(response.status_code, 200, f'{path}: {response.text[:250]}')
        home = learner.get('/', base_url=self.base).text
        self.assertIn('/trial/account', home)
        self.assertNotIn('AI generation and uploads need a local installation', home)
        self.assertEqual(visitor.get('/comprehension', base_url=self.base).status_code, 403)
        with sqlite3.connect(self.ledger_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM trial_requests').fetchone()[0], 0)

    def test_dedicated_provider_settings_and_mutated_sample_paths_do_not_leak_between_apps(self):
        app = self.app()
        client = app.test_client()
        self.login(client)
        trial = app.extensions['hosted_trial'].cache['github:11']
        self.assertEqual(trial.config['OPENAI_API_KEY'], 'synthetic-demo-openai')
        self.assertEqual(trial.config['ELEVENLABS_API_KEY'], 'synthetic-demo-elevenlabs')
        self.assertEqual(trial.config['OPENROUTER_API_KEY'], 'synthetic-demo-openrouter')
        self.assertEqual(trial.config['AI_TRIAL_IDENTITY'], 'github:11')
        self.assertTrue(trial.config['AI_TRIAL_ENABLED'])
        self.assertFalse(trial.config['PUBLIC_DEMO'])
        self.assertTrue(app.config['PUBLIC_DEMO'])
        for key in ('OPENAI_API_KEY', 'ELEVENLABS_API_KEY', 'OPENROUTER_API_KEY', 'YANDEX_API_KEY'):
            self.assertEqual(app.config[key], '')
        for key in ('DB_PATH', 'APP_MEDIA_DIR', 'UPLOAD_FOLDER', 'SESSION_FILE_DIR', 'WORD_POST_ASSET_DIR', 'ANKI_MEDIA_DIR'):
            self.assertNotEqual(trial.config[key], app.config[key], key)
            self.assertTrue(Path(trial.config[key]).is_relative_to(self.root / 'tenants'), key)
        self.assertEqual(trial.config['AI_TRIAL_LEDGER_PATH'], str(self.ledger_path))
        self.assertEqual(trial.config['LESSON_MAX_PAGES'], 12)
        self.assertEqual(trial.config['MAX_CONTENT_LENGTH'], 12 * 1024 * 1024)

    def test_profile_control_opens_overview_after_signin_and_keeps_settings_separate(self):
        app = self.app()
        client = app.test_client()
        visitor = client.get('/post/profiles', base_url=self.base)
        self.assertEqual(visitor.status_code, 302)
        self.assertEqual(visitor.location, '/trial/account')
        page = client.get(visitor.location, base_url=self.base)
        self.assertIn('href="/trial/sign-in/github"', page.text)
        self.login(client)
        learner = client.get('/post/profiles', base_url=self.base)
        self.assertEqual(learner.status_code, 200)
        self.assertIn('Your profile', learner.text)
        self.assertIn('Skill progress', learner.text)
        self.assertIn('href="/trial/account"', learner.text)
        self.assertNotIn('action="/trial/sign-out"', learner.text)
        page = client.get('/trial/account', base_url=self.base)
        self.assertIn('<h1>Account settings</h1>', page.text)
        self.assertIn('href="/post/profiles"', page.text)
        self.assertIn('Signed in as <strong>sample-user</strong>.', page.text)
        self.assertIn('action="/trial/sign-out"', page.text)

    def test_disabled_profile_account_explains_unavailable_signin(self):
        with patch.dict(os.environ, {'AI_TRIAL_ENABLED': 'false',
                                    'GITHUB_OAUTH_CLIENT_ID': '', 'GITHUB_OAUTH_CLIENT_SECRET': ''}):
            client = create_hosted_app().test_client()
            response = client.get('/post/profiles', base_url=self.base)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, '/trial/account')
            page = client.get(response.location, base_url=self.base)
            self.assertEqual(page.status_code, 200)
            self.assertIn('<h1>Public preview</h1>', page.text)
            self.assertIn('sign-in', page.text.lower())
            self.assertIn('not enabled', page.text.lower())
            self.assertNotIn('href="/trial/sign-in/github"', page.text)
            self.assertNotIn('action="/trial/sign-out"', page.text)

    def test_accounts_only_signin_persists_without_provider_credentials_or_spend_ledger(self):
        from services.trial_provider import provider_call
        self.ledger_path.unlink()
        with patch.dict(os.environ, {'HOSTED_ACCOUNTS_ENABLED': 'true', 'AI_TRIAL_ENABLED': 'false',
                'DEMO_OPENAI_API_KEY': '', 'DEMO_ELEVENLABS_API_KEY': '', 'DEMO_OPENROUTER_API_KEY': '',
                'OPENAI_API_KEY': 'regular-key-must-not-leak'}):
            app = self.app()
            self.assertTrue(app.config['HOSTED_ACCOUNTS_ENABLED'])
            self.assertFalse(app.config['HOSTED_TRIAL_AVAILABLE'])
            client = app.test_client()
            preview = client.get('/', base_url=self.base).text
            self.assertIn('/trial/sign-in', preview)
            self.assertIn('AI generation is currently turned off.', preview)
            denied = client.post('/api/v1/card-generation/batches', base_url=self.base, json={})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json['error']['sign_in_url'], '/trial/sign-in')
            self.assertIn('AI generation is currently turned off.', denied.json['error']['message'])
            self.login(client)
            trial = app.extensions['hosted_trial'].cache['github:11']
            self.assertTrue(trial.config['HOSTED_AI_TRIAL'])
            self.assertFalse(trial.config['AI_TRIAL_ENABLED'])
            for key in ('OPENAI_API_KEY', 'ELEVENLABS_API_KEY', 'OPENROUTER_API_KEY', 'YANDEX_API_KEY'):
                self.assertEqual(trial.config[key], '')
            status = client.get('/trial/status', base_url=self.base).json
            self.assertEqual(status, {'authenticated': True, 'enabled': True, 'configured': True,
                'demo': False, 'demo_enabled': False, 'demo_url': '',
                'ai_enabled': False, 'display_name': 'sample-user',
                'providers': [{'id': 'github', 'name': 'GitHub', 'sign_in_url': '/trial/sign-in/github'}],
                'sign_in_url': '/trial/sign-in', 'account_url': '/trial/account'})
            account = client.get('/trial/account', base_url=self.base).text
            self.assertIn('<h1>Account settings</h1>', account)
            self.assertIn('AI generation is currently turned off.', account)
            self.assertNotIn('US$1', account)
            self.assertEqual(client.get('/api/v1/user-session', base_url=self.base).json['profile']['id'], 'personal-learning')
            invoke = Mock()
            with self.assertRaises(TrialDenied):
                provider_call(trial.config, 'accounts-only-guard', {}, 1, invoke)
            invoke.assert_not_called()
            self.assertFalse(self.ledger_path.exists())
            with sqlite3.connect(trial.config['DB_PATH']) as conn:
                conn.execute("UPDATE words SET mnemonic='Saved personal hint' WHERE lemma='письмо'")
            cookie = client.get_cookie(COOKIE, domain='arcade.example').value
            restarted = self.app()
            returning = restarted.test_client()
            returning.set_cookie(COOKIE, cookie, domain='arcade.example')
            self.assertEqual(returning.get('/vocab', base_url=self.base).status_code, 200)
            with sqlite3.connect(restarted.extensions['hosted_trial'].cache['github:11'].config['DB_PATH']) as conn:
                self.assertEqual(conn.execute("SELECT mnemonic FROM words WHERE lemma='письмо'").fetchone()[0], 'Saved personal hint')
            self.assertFalse(self.ledger_path.exists())

    def test_existing_sessions_gain_ai_after_activation_without_resetting_spend_or_denials(self):
        from services.trial_provider import provider_call
        with patch.dict(os.environ, {'HOSTED_ACCOUNTS_ENABLED': 'true', 'AI_TRIAL_ENABLED': 'false'}):
            accounts = self.app()
            cookies = {}
            for identity in ('github:11', 'github:22'):
                client = accounts.test_client()
                self.login(client, identity)
                cookies[identity] = client.get_cookie(COOKIE, domain='arcade.example').value
        self.ledger.authorize_identity('github:22')
        self.ledger.reserve('github:22', 'previous-spend', 'a' * 64, 100)
        self.ledger.settle('github:22', 'previous-spend', 100)
        with sqlite3.connect(self.ledger_path) as conn:
            conn.execute("UPDATE trial_accounts SET enabled=0 WHERE identity='github:22'")
            before = conn.execute('SELECT * FROM trial_requests').fetchall()
        activated = self.app()
        for identity, cookie in cookies.items():
            returning = activated.test_client()
            returning.set_cookie(COOKIE, cookie, domain='arcade.example')
            self.assertEqual(returning.get('/vocab', base_url=self.base).status_code, 200)
            self.assertTrue(returning.get('/trial/status', base_url=self.base).json['authenticated'])
            self.assertTrue(returning.get('/trial/status', base_url=self.base).json['ai_enabled'])
        with sqlite3.connect(self.ledger_path) as conn:
            self.assertEqual(dict(conn.execute('SELECT identity,enabled FROM trial_accounts')), {'github:11': 1, 'github:22': 0})
            self.assertEqual(conn.execute('SELECT * FROM trial_requests').fetchall(), before)
        invoke = Mock(return_value='metered result')
        active_config = activated.extensions['hosted_trial'].cache['github:11'].config
        self.assertEqual(provider_call(active_config, 'activated-account', {}, 10, invoke, lambda _: 10), 'metered result')
        invoke.assert_called_once()
        blocked = Mock()
        with self.assertRaises(TrialDenied):
            provider_call(activated.extensions['hosted_trial'].cache['github:22'].config,
                          'blocked-account', {}, 10, blocked)
        blocked.assert_not_called()

    def test_accounts_flag_is_independent_and_oauth_is_required_without_ai(self):
        with patch.dict(os.environ, {'HOSTED_ACCOUNTS_ENABLED': 'false'}):
            app = create_hosted_app()
            self.assertFalse(app.config['HOSTED_ACCOUNTS_ENABLED'])
            self.assertFalse(app.config['HOSTED_TRIAL_AVAILABLE'])
            status = app.test_client().get('/trial/status', base_url=self.base).json
            self.assertFalse(status['enabled'])
            self.assertTrue(status['ai_enabled'])
        for name in ('GITHUB_OAUTH_CLIENT_ID', 'GITHUB_OAUTH_CLIENT_SECRET'):
            with patch.dict(os.environ, {'HOSTED_ACCOUNTS_ENABLED': 'true', 'AI_TRIAL_ENABLED': 'false', name: ''}):
                with self.assertRaisesRegex(RuntimeError, 'Hosted accounts require Google or GitHub OAuth'):
                    create_hosted_app()
        with patch.dict(os.environ, {'HOSTED_ACCOUNTS_ENABLED': 'true', 'AI_TRIAL_ENABLED': 'false', 'HOSTED_TRIAL_ROOT': ''}):
            with self.assertRaisesRegex(RuntimeError, 'HOSTED_TRIAL_ROOT'):
                create_hosted_app()

    def test_dedicated_credentials_required_to_enable_and_no_fallback_to_regular_keys(self):
        required = ('GITHUB_OAUTH_CLIENT_ID', 'GITHUB_OAUTH_CLIENT_SECRET', 'DEMO_OPENAI_API_KEY',
                    'DEMO_ELEVENLABS_API_KEY', 'DEMO_OPENROUTER_API_KEY')
        for name in required:
            with patch.dict(os.environ, {name: '', 'OPENAI_API_KEY': 'synthetic-regular-key'}):
                with self.assertRaisesRegex(RuntimeError, 'dedicated demo provider keys'):
                    create_hosted_app()
        with patch.dict(os.environ, {'AI_TRIAL_ENABLED': 'false', **dict.fromkeys(required, '')}):
            app = create_hosted_app()
            client = app.test_client()
            self.assertEqual(client.get('/', base_url=self.base).status_code, 200)
            self.assertEqual(client.get('/trial/sign-in/github', base_url=self.base).status_code, 503)
            self.assertEqual(client.get('/trial/status', base_url=self.base).json['enabled'], False)

    def test_google_only_accounts_use_dedicated_oauth_credentials_without_github(self):
        from tests.test_hosted_oauth import GoogleProvider
        with patch.dict(os.environ, {
                'HOSTED_ACCOUNTS_ENABLED': 'true',
                'GITHUB_OAUTH_CLIENT_ID': '', 'GITHUB_OAUTH_CLIENT_SECRET': '',
                'GOOGLE_OAUTH_CLIENT_ID': 'synthetic-google-client',
                'GOOGLE_OAUTH_CLIENT_SECRET': 'synthetic-google-secret'}):
            app = create_hosted_app()
            self.assertTrue(app.config['HOSTED_ACCOUNTS_ENABLED'])
            self.assertTrue(app.config['HOSTED_TRIAL_AVAILABLE'])
            dispatcher = app.extensions['hosted_trial']
            self.assertEqual(dispatcher.providers['google'].client_id, 'synthetic-google-client')
            self.assertEqual(dispatcher.providers['google'].callback, self.base + '/trial/callback/google')
            dispatcher.providers['google'] = GoogleProvider()
            client = app.test_client()
            chooser = client.get('/trial/sign-in', base_url=self.base)
            self.assertEqual(chooser.status_code, 200)
            self.assertIn('/trial/sign-in/google', chooser.text)
            self.assertNotIn('/trial/sign-in/github', chooser.text)
            start = client.get('/trial/sign-in/google', base_url=self.base)
            state = parse_qs(urlsplit(start.location).query)['state'][0]
            result = client.get('/trial/callback/google?code=valid&state=' + state, base_url=self.base)
            self.assertEqual(result.status_code, 302, result.text)
            self.assertEqual(client.get('/vocab', base_url=self.base).status_code, 200)
            status = client.get('/trial/status', base_url=self.base).json
            self.assertTrue(status['authenticated'])
            self.assertEqual([row['id'] for row in status['providers']], ['google'])

    def test_drive_configuration_does_not_enable_google_signin(self):
        with patch.dict(os.environ, {
                'HOSTED_ACCOUNTS_ENABLED': 'true', 'AI_TRIAL_ENABLED': 'false',
                'GITHUB_OAUTH_CLIENT_ID': '', 'GITHUB_OAUTH_CLIENT_SECRET': '',
                'GOOGLE_OAUTH_CLIENT_ID': '', 'GOOGLE_OAUTH_CLIENT_SECRET': '',
                'GOOGLE_DRIVE_CREDENTIALS_FILE': '/synthetic/drive-credentials.json'}):
            with self.assertRaisesRegex(RuntimeError, 'Hosted accounts require Google or GitHub OAuth'):
                create_hosted_app()

    def test_missing_spend_ledger_fails_closed_without_reinitializing(self):
        self.ledger_path.unlink()
        with self.assertRaises(TrialDenied):
            create_hosted_app()
        self.assertFalse(self.ledger_path.exists())

    def test_second_identity_has_distinct_sessions_and_samples(self):
        app = self.app()
        a, b = app.test_client(), app.test_client()
        self.login(a, 'github:11')
        self.login(b, 'github:22')
        for client in (a, b):
            self.assertEqual(client.get('/api/v1/user-session', base_url=self.base, buffered=True).status_code, 200)
        apps = app.extensions['hosted_trial'].cache
        self.assertNotEqual(apps['github:11'].config['DB_PATH'], apps['github:22'].config['DB_PATH'])
        self.assertNotEqual(apps['github:11'].config['SESSION_COOKIE_NAME'], apps['github:22'].config['SESSION_COOKIE_NAME'])
        for identity in ('github:11', 'github:22'):
            with sqlite3.connect(apps[identity].config['DB_PATH']) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM saved_stories').fetchone()[0], 0)
        with sqlite3.connect(self.ledger_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM trial_accounts').fetchone()[0], 2)

    def test_account_switch_rejects_stale_scope_even_with_current_csrf_and_same_profile_id(self):
        app = self.app()
        browser = app.test_client()
        self.login(browser, 'github:11')
        previous = browser.get('/api/v1/user-session', base_url=self.base).json
        previous_cookie = browser.get_cookie(COOKIE, domain='arcade.example').value

        # Another tab replaces the shared account cookie. Both workspaces use
        # the same profile ID, and a background response can refresh CSRF.
        self.login(browser, 'github:22')
        current = browser.get('/api/v1/user-session', base_url=self.base).json
        self.assertEqual(previous['profile']['id'], 'personal-learning')
        self.assertEqual(current['profile']['id'], previous['profile']['id'])
        self.assertNotEqual(current['session_scope'], previous['session_scope'])
        self.assertNotEqual(current['csrf_token'], previous['csrf_token'])
        headers = {'X-CSRF-Token': current['csrf_token'], 'X-Profile-ID': previous['profile']['id'],
                   'X-Account-Scope': previous['session_scope']}

        for method, path, payload in (
                ('GET', '/api/v1/progression', None),
                ('POST', '/api/v1/progression/preferences', {'level': 'B2'}),
                ('PATCH', '/api/v1/user-session/profile', {'display_name': 'Stale tab rename'})):
            with self.subTest(method=method, path=path):
                response = browser.open(path, method=method, base_url=self.base, headers=headers, json=payload)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json['error']['code'], 'account_changed')
                self.assertEqual(set(response.json), {'error'})

        current_headers = headers | {'X-Account-Scope': current['session_scope']}
        unchanged = browser.get('/api/v1/progression', base_url=self.base, headers=current_headers)
        self.assertEqual(unchanged.status_code, 200)
        self.assertEqual(unchanged.json['preferred_level'], 'A1')
        profile = browser.get('/api/v1/user-session', base_url=self.base, headers=current_headers).json['profile']
        self.assertEqual(profile['display_name'], 'sample-user')
        updated = browser.post('/api/v1/progression/preferences', base_url=self.base,
                               headers=current_headers, json={'level': 'A2'})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json['preferred_level'], 'A2')
        renamed = browser.patch('/api/v1/user-session/profile', base_url=self.base,
                                headers=current_headers, json={'display_name': 'Current account'})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json['profile']['display_name'], 'Current account')

        browser.set_cookie(COOKIE, previous_cookie, domain='arcade.example')
        self.assertFalse(browser.get('/trial/status', base_url=self.base).json['authenticated'])
        self.login(browser, 'github:11')
        restored = browser.get('/api/v1/user-session', base_url=self.base).json
        self.assertEqual(restored['session_scope'], previous['session_scope'])
        self.assertEqual(restored['profile']['display_name'], 'sample-user')
        self.assertEqual(browser.get('/api/v1/progression', base_url=self.base,
            headers={'X-Account-Scope': previous['session_scope']}).json['preferred_level'], 'A1')

    def test_preview_local_and_hosted_session_scopes_are_distinct(self):
        from tests.support import isolated_app
        local = isolated_app(self, signed_in=False).test_client()
        local_scope = local.get('/api/v1/user-session').json['session_scope']
        self.assertEqual(local_scope, 'local')
        app = self.app()
        browser = app.test_client()
        preview_scope = browser.get('/api/v1/user-session', base_url=self.base).json['session_scope']
        self.assertEqual(preview_scope, 'preview')
        self.login(browser)
        hosted_scope = browser.get('/api/v1/user-session', base_url=self.base).json['session_scope']
        self.assertTrue(hosted_scope.startswith('hosted:'))
        self.assertEqual(len({local_scope, preview_scope, hosted_scope}), 3)
        for stale_scope in (local_scope, preview_scope):
            response = browser.get('/api/v1/flashcards', base_url=self.base,
                                   headers={'X-Account-Scope': stale_scope})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json['error']['code'], 'account_changed')


if __name__ == '__main__':
    unittest.main()
