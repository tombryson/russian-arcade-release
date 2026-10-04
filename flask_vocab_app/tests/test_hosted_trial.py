import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from flask import Flask, jsonify, request, session
from werkzeug.test import Client
from werkzeug.wrappers import Response

from hosted_trial import (COOKIE, FLOW_COOKIE, GitHubIdentity, HostedTrialDispatcher,
                          TrialIdentityError, safe_return_url, seed_trial_workspace, tenant_settings)


class IdentityProvider:
    configured = True

    def __init__(self):
        self.calls = []
        self.identity = 'github:11'

    def authorization_url(self, state, verifier):
        self.calls.append((state, verifier))
        return 'https://github.com/login/oauth/authorize?state=' + state

    def verify(self, code, verifier):
        if code != 'valid':
            raise TrialIdentityError('invalid')
        return self.identity, 'sample-user'


class HostedTrialTests(unittest.TestCase):
    def setUp(self):
        # Host free space is not the condition under test; the admission test
        # below supplies its own low-space reading explicitly.
        disk = patch('hosted_trial.shutil.disk_usage')
        disk.start().return_value.free = 1024 * 1024 * 1024
        self.addCleanup(disk.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.provider = IdentityProvider()
        self.budget = Mock()
        self.apps = []
        self.base = 'https://arcade.example'
        self.dispatch = HostedTrialDispatcher(lambda e, s: Response('public samples')(e, s), self.factory,
            root=self.root, ledger_path=self.root / 'budget.sqlite3', secret='test-secret-' * 4,
            hostname='arcade.example', enabled=True, identity_provider=self.provider, budget=self.budget,
            max_cached_apps=1, max_tenants=2, public_preview_enabled=True)
        self.a, self.b = Client(self.dispatch, Response), Client(self.dispatch, Response)

    def factory(self, settings):
        app = Flask(__name__)
        app.config.update(settings)
        self.apps.append(app)
        @app.get('/who')
        def who():
            return jsonify(identity=app.config['AI_TRIAL_IDENTITY'], database=app.config['DB_PATH'],
                           credential=session.get('personal_access_id'))
        @app.post('/write')
        def write():
            with sqlite3.connect(app.config['DB_PATH']) as conn:
                conn.execute('CREATE TABLE IF NOT EXISTS test_notes(note TEXT)')
                conn.execute('INSERT INTO test_notes VALUES (?)', (request.json['note'],))
            target = Path(app.config['APP_MEDIA_DIR'])
            target.mkdir(exist_ok=True)
            (target / 'example.txt').write_text(request.json['note'])
            return 'saved'
        @app.get('/notes')
        def notes():
            with sqlite3.connect(app.config['DB_PATH']) as conn:
                conn.execute('CREATE TABLE IF NOT EXISTS test_notes(note TEXT)')
                return jsonify([row[0] for row in conn.execute('SELECT note FROM test_notes')])
        @app.get('/media')
        def media():
            path = Path(app.config['APP_MEDIA_DIR']) / 'example.txt'
            return path.read_text() if path.exists() else ('missing', 404)
        return app

    def get(self, client, path):
        return client.get(path, base_url=self.base, buffered=True)

    def login(self, client, identity='github:11', next_url='/'):
        self.provider.identity = identity
        result = self.get(client, '/trial/sign-in/github?next=' + next_url)
        self.assertEqual(result.status_code, 302)
        state = parse_qs(urlsplit(result.location).query)['state'][0]
        result = self.get(client, '/trial/callback?code=valid&state=' + state)
        self.assertEqual(result.status_code, 302, result.text)
        return result, state

    def test_anonymous_and_forged_cookies_never_create_tenant(self):
        self.assertEqual(self.get(self.a, '/who').text, 'public samples')
        self.a.set_cookie(COOKIE, 'forged', domain='arcade.example')
        self.assertEqual(self.get(self.a, '/who').text, 'public samples')
        self.a.set_cookie(COOKIE, self.dispatch.signer.dumps('github:11'), domain='arcade.example')
        self.assertEqual(self.get(self.a, '/who').text, 'public samples')
        self.assertEqual(self.apps, [])

    def test_ai_flag_supports_legacy_callers_and_explicit_accounts_only(self):
        for config, explicit, expected in (({}, None, True),
                                           ({'AI_TRIAL_ENABLED': False}, None, False),
                                           ({'AI_TRIAL_ENABLED': True}, False, False),
                                           ({'AI_TRIAL_ENABLED': False}, True, True)):
            with self.subTest(config=config, explicit=explicit):
                dispatcher = HostedTrialDispatcher(self.dispatch.public_application, self.factory,
                    root=self.root, ledger_path=self.root / 'budget.sqlite3', secret='test-secret-' * 4,
                    hostname='arcade.example', enabled=True, app_config=config, ai_enabled=explicit,
                    identity_provider=self.provider)
                self.assertEqual(dispatcher.ai_enabled, expected)
                self.assertEqual(dispatcher.config['AI_TRIAL_ENABLED'], expected)
                self.assertEqual(dispatcher.budget.enabled, expected)
                self.assertTrue(dispatcher.enabled)

    def test_accounts_only_never_authorizes_spending(self):
        self.dispatch.ai_enabled = False
        self.dispatch.config['AI_TRIAL_ENABLED'] = False
        self.login(self.a)
        self.budget.authorize_identity.assert_not_called()
        self.assertFalse((self.root / 'budget.sqlite3').exists())
        status = self.get(self.a, '/trial/status').json
        self.assertTrue(status['authenticated'])
        self.assertTrue(status['enabled'])
        self.assertFalse(status['ai_enabled'])
        self.assertTrue(self.apps[0].config['HOSTED_AI_TRIAL'])
        page = self.get(self.a, '/trial/account')
        self.assertIn('<h1>Account settings</h1>', page.text)
        self.assertIn('AI generation is currently turned off.', page.text)
        self.assertNotIn('US$1', page.text)

    def test_callback_requires_same_browser_state_and_single_use(self):
        self.get(self.a, '/trial/sign-in/github')
        state = self.provider.calls[-1][0]
        self.assertEqual(self.get(self.b, '/trial/callback?code=valid&state=' + state).status_code, 400)
        self.assertEqual(self.get(self.a, '/trial/callback?code=valid&state=forged').status_code, 400)
        self.assertEqual(self.get(self.a, '/trial/callback?code=valid&state=' + state).status_code, 302)
        self.assertEqual(self.get(self.a, '/trial/callback?code=valid&state=' + state).status_code, 400)
        self.budget.authorize_identity.assert_called_once_with('github:11')

    def test_separate_databases_media_cookies_and_cache_reload(self):
        self.login(self.a)
        a = self.get(self.a, '/who').json
        self.a.post('/write', base_url=self.base, json={'note': 'only-a'}, buffered=True)
        self.login(self.b, 'github:22')
        b = self.get(self.b, '/who').json
        self.assertNotEqual(a['database'], b['database'])
        self.assertNotEqual(self.apps[0].config['SESSION_COOKIE_NAME'], self.apps[-1].config['SESSION_COOKIE_NAME'])
        self.assertEqual(self.get(self.b, '/notes').json, [])
        self.assertEqual(self.get(self.b, '/media').status_code, 404)
        self.assertEqual(self.get(self.a, '/notes').json, ['only-a'])
        self.assertEqual(self.get(self.a, '/media').text, 'only-a')
        self.assertEqual(len(self.dispatch.cache), 1)
        self.assertEqual(self.get(self.a, '/who').json['identity'], 'github:11')

    def test_synthetic_seed_and_repeated_open_preserve_user_data(self):
        self.login(self.a)
        path = self.get(self.a, '/who').json['database']
        with sqlite3.connect(path) as conn:
            before = conn.execute('SELECT COUNT(*) FROM words').fetchone()[0]
            self.assertGreater(before, 6)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_content_versions').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM saved_stories').fetchone()[0], 0)
        seed_trial_workspace(self.apps[-1].config, 'different')
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], before)
            self.assertEqual(conn.execute('SELECT display_name FROM learning_profiles').fetchone()[0], 'sample-user')

    def test_existing_sample_topics_are_repaired_with_backup_without_republishing_cards(self):
        self.login(self.a)
        path = self.get(self.a, '/who').json['database']
        with sqlite3.connect(path) as conn:
            word_id = conn.execute("SELECT id FROM words WHERE lemma='письмо'").fetchone()[0]
            conn.execute("UPDATE words SET topic=?,count=11,mnemonic='Keep this hint' WHERE id=?", (json.dumps(['First steps']), word_id))
            versions = conn.execute('SELECT id,payload FROM learning_content_versions').fetchall()
        seed_trial_workspace(self.apps[-1].config, 'different')
        with sqlite3.connect(path) as conn:
            word = conn.execute('SELECT topic,count,mnemonic FROM words WHERE id=?', (word_id,)).fetchone()
            from services.sample_vocabulary import prepared_vocabulary
            self.assertEqual(json.loads(word[0]), prepared_vocabulary()[('письмо', 'NOUN')]['topics'])
            self.assertEqual(word[1:], (11, 'Keep this hint'))
            self.assertEqual(conn.execute('SELECT id,payload FROM learning_content_versions').fetchall(), versions)
        backups = list(Path(path).parent.glob('vocab.db.before-vocabulary-repair-*.bak'))
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as conn:
            self.assertEqual(json.loads(conn.execute('SELECT topic FROM words WHERE id=?', (word_id,)).fetchone()[0]), ['First steps'])

    def test_signout_csrf_and_revocation(self):
        self.login(self.a)
        cookie = self.a.get_cookie(COOKIE, domain='arcade.example').value
        page = self.get(self.a, '/trial/account')
        self.assertEqual(page.status_code, 200)
        self.assertIn('<h1>Account settings</h1>', page.text)
        self.assertIn('Signed in as <strong>sample-user</strong>.', page.text)
        self.assertIn('AI use has account and shared spending limits.', page.text)
        self.assertIn('Saved practice remains available when an allowance is used.', page.text)
        self.assertNotIn('AI demo allowance', page.text)
        self.assertIn('action="/trial/sign-out"', page.text)
        self.assertNotIn('href="/trial/sign-in/github"', page.text)
        token = re.search('name="csrf_token" value="([^"]+)"', page.text)[1]
        self.assertEqual(self.a.post('/trial/sign-out', base_url=self.base, data={'csrf_token': 'bad'}).status_code, 403)
        self.assertEqual(self.a.post('/trial/sign-out', base_url=self.base, data={'csrf_token': token},
                                   headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.a.post('/trial/sign-out', base_url=self.base, data={'csrf_token': token}).status_code, 302)
        self.a.set_cookie(COOKIE, cookie, domain='arcade.example')
        self.assertEqual(self.get(self.a, '/who').text, 'public samples')

    def test_anonymous_account_offers_signin_only_when_available(self):
        for enabled, configured in ((True, True), (False, True), (True, False), (False, False)):
            with self.subTest(enabled=enabled, configured=configured):
                self.dispatch.enabled = enabled
                self.provider.configured = configured
                page = self.get(self.a, '/trial/account')
                self.assertEqual(page.status_code, 200)
                self.assertNotIn('action="/trial/sign-out"', page.text)
                if enabled and configured:
                    self.assertIn('<h1>Sign in</h1>', page.text)
                    self.assertIn('href="/trial/sign-in/github"', page.text)
                    self.assertIn('Sign in with GitHub', page.text)
                else:
                    self.assertIn('<h1>Public preview</h1>', page.text)
                    self.assertIn('sign-in', page.text.lower())
                    self.assertIn('not enabled', page.text.lower())
                    self.assertNotIn('href="/trial/sign-in/github"', page.text)
                self.assertIn('href="/"', page.text)

    def test_tenant_cap_and_auth_status(self):
        self.login(self.a)
        self.login(self.b, 'github:22')
        self.provider.identity = 'github:33'
        self.get(self.b, '/trial/sign-in/github')
        state = self.provider.calls[-1][0]
        self.assertEqual(self.get(self.b, '/trial/callback?code=valid&state=' + state).status_code, 503)
        status = self.get(self.a, '/trial/status').json
        self.assertTrue(status['authenticated'])
        self.assertNotIn('identity', status)
        self.assertNotIn('secret', json.dumps(status))

    def test_unconfigured_auth_and_host_are_closed(self):
        self.provider.configured = False
        self.assertEqual(self.get(self.a, '/trial/sign-in/github').status_code, 503)
        self.assertEqual(self.a.get('/trial/status', base_url='https://evil.example').status_code, 400)
        self.assertEqual(self.get(self.a, '/who').text, 'public samples')

    def test_return_urls_and_cookie_flags(self):
        for bad in ('//evil.example/path', 'https://evil.example', '/\\evil.example', '/x\nLocation:evil', '/trial/sign-out'):
            self.assertEqual(safe_return_url(bad), '/')
        self.assertEqual(safe_return_url('/#activities'), '/#activities')
        self.assertEqual(safe_return_url('/post/?level=A2#speaking'), '/?level=A2#speaking')
        self.assertEqual(safe_return_url('/post#flashcards'), '/#flashcards')
        self.assertEqual(safe_return_url('/post/profiles'), '/post/profiles')
        response, _ = self.login(self.a, next_url='//evil.example')
        self.assertEqual(response.location, '/')
        cookies = '\n'.join(response.headers.getlist('Set-Cookie'))
        for setting in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/'):
            self.assertIn(setting, cookies)
        self.assertNotIn('Domain=', cookies)

    def test_rate_limit_and_expired_flow(self):
        with patch.object(self.dispatch, 'clock', return_value=100):
            self.get(self.a, '/trial/sign-in/github')
            state = self.provider.calls[-1][0]
            for _ in range(29):
                self.get(self.a, '/trial/sign-in/github')
            self.assertEqual(self.get(self.a, '/trial/sign-in/github').status_code, 429)
        with patch.object(self.dispatch, 'clock', return_value=800):
            self.assertEqual(self.get(self.a, '/trial/callback?code=valid&state=' + state).status_code, 400)

    def test_active_app_is_not_evicted(self):
        self.login(self.a)
        app = self.dispatch.cache['github:11']
        self.dispatch.inflight['github:11'] = 1
        self.provider.identity = 'github:22'
        self.get(self.b, '/trial/sign-in/github')
        state = self.provider.calls[-1][0]
        self.assertEqual(self.get(self.b, '/trial/callback?code=valid&state=' + state).status_code, 503)
        self.assertIs(self.dispatch.cache['github:11'], app)
        self.dispatch.inflight['github:11'] = 0
        self.login(self.b, 'github:22')
        self.assertIn('github:22', self.dispatch.cache)

    def test_pending_worker_pins_application_until_complete(self):
        from concurrent.futures import Future
        from types import SimpleNamespace
        self.login(self.a)
        app = self.dispatch.cache['github:11']
        future = Future()
        executor = Mock()
        executor.submit.return_value = future
        live = SimpleNamespace(executor=executor, reviews=None, connections={})
        app.extensions['learning'] = {'live_conversation': live}
        self.dispatch._track_executors(app)
        live.executor.submit(lambda: None)
        self.assertTrue(self.dispatch._busy('github:11', app))
        future.set_result(None)
        self.assertFalse(self.dispatch._busy('github:11', app))

    def test_storage_admission_upload_limit_and_request_limit(self):
        self.login(self.a)
        with patch('hosted_trial.shutil.disk_usage') as disk:
            disk.return_value.free = 10
            self.assertEqual(self.a.post('/write', base_url=self.base, json={'note': 'denied'}).status_code, 507)
        self.assertEqual(self.get(self.a, '/notes').json, [])
        response = self.a.post('/write', base_url=self.base, data=b'x' * (12 * 1024 * 1024 + 1))
        self.assertEqual(response.status_code, 413)
        now = int(self.dispatch.clock())
        with self.dispatch._db() as conn:
            conn.execute('INSERT INTO request_limits VALUES (?,?,?,?) ON CONFLICT(identity,kind,bucket) DO UPDATE SET attempts=excluded.attempts',
                         ('github:11', 'requests', now // 60, 1200))
        self.assertEqual(self.get(self.a, '/notes').status_code, 429)

    def test_real_factory_blocks_local_profiles_and_drive_tools(self):
        from app import create_app
        self.dispatch.app_factory = lambda config: create_app(config | {
            'TESTING': True, 'OPENAI_API_KEY': '', 'OPENROUTER_API_KEY': '',
            'ELEVENLABS_API_KEY': '', 'YANDEX_API_KEY': ''})
        with patch('socket.socket.connect', side_effect=AssertionError('No network calls in identity tests')):
            self.login(self.a)
            state = self.get(self.a, '/api/v1/user-session').json
            self.assertEqual(state['profile']['id'], 'personal-learning')
            for path in ('/api/v1/user-session/select', '/api/v1/user-session/profiles',
                         '/post/profiles/actions', '/generate', '/sync', '/add_word', '/edit_word', '/sanitize_vocab'):
                result = self.a.post(path, base_url=self.base, json={}, buffered=True)
                self.assertEqual(result.status_code, 403, path)
            self.assertEqual(self.get(self.a, '/vocab?source=cloud').status_code, 403)
            profile = self.get(self.a, '/post/profiles')
            self.assertEqual(profile.status_code, 200)
            self.assertIn('Your profile', profile.text)
            self.assertEqual(self.get(self.a, '/vocab').status_code, 200)

    def test_settings_override_paths_identity_and_credentials(self):
        config = tenant_settings(self.root, 'github:11', secret='secret', ledger_path=self.root/'ledger.db', hostname='arcade.example')
        self.assertEqual(config['AI_TRIAL_IDENTITY'], 'github:11')
        self.assertFalse(config['PUBLIC_DEMO'])
        self.assertFalse(config['GOOGLE_DRIVE_AUTO_AUTH'])
        for name in ('DB_PATH', 'APP_MEDIA_DIR', 'UPLOAD_FOLDER', 'SESSION_FILE_DIR', 'WORD_POST_ASSET_DIR', 'ANKI_MEDIA_DIR'):
            self.assertTrue(Path(config[name]).is_relative_to(self.root/'tenants'))


class HostedLessonLimitTests(unittest.TestCase):
    def test_hosted_page_cap_keeps_local_limit(self):
        from services.lesson_files import LessonFiles
        from repositories.learning_repository import LearningError
        with patch('services.lesson_files.pdfplumber.open') as reader:
            reader.return_value.__enter__.return_value.pages = [None] * 13
            self.assertEqual(LessonFiles.inspect(b'%PDF-test'), ('application/pdf', 13))
            with self.assertRaisesRegex(LearningError, '12 pages'):
                LessonFiles.inspect(b'%PDF-test', max_pages=12)

    def test_whole_upload_is_validated_before_any_files_are_saved(self):
        import io
        from werkzeug.datastructures import FileStorage
        from services.lesson_companion import LessonCompanion
        from repositories.learning_repository import LearningError
        companion = LessonCompanion('/unused/vocab.db', None, None, {'LESSON_MAX_PAGES': 12})
        companion.files.inspect = Mock(return_value=('application/pdf', 7))
        companion.files.put = Mock()
        uploads = [FileStorage(stream=io.BytesIO(b'fake'), filename=f'{n}.pdf') for n in range(2)]
        with self.assertRaisesRegex(LearningError, '12 pages'):
            companion.receive(uploads)
        companion.files.put.assert_not_called()


class GitHubIdentityTests(unittest.TestCase):
    def test_pkce_and_stable_identity_without_repository_scope(self):
        http = Mock()
        http.post.return_value.json.return_value = {'access_token': 'synthetic-token'}
        http.get.return_value.json.return_value = {'id': 123, 'login': 'example', 'type': 'User'}
        provider = GitHubIdentity('client', 'secret', 'https://arcade.example/trial/callback', http=http)
        values = parse_qs(urlsplit(provider.authorization_url('state', 'verifier')).query)
        self.assertEqual(values['code_challenge_method'], ['S256'])
        self.assertNotIn('repo', values.get('scope', []))
        self.assertEqual(provider.verify('code', 'verifier'), ('github:123', 'example'))
        self.assertEqual(http.post.call_args.kwargs['data']['code_verifier'], 'verifier')
        self.assertEqual(http.get.call_args.kwargs['headers']['Authorization'], 'Bearer synthetic-token')

    def test_provider_rejects_non_personal_or_missing_identity(self):
        http = Mock()
        http.post.return_value.json.return_value = {'access_token': 'synthetic-token'}
        provider = GitHubIdentity('client', 'secret', 'https://arcade.example/trial/callback', http=http)
        for value in ({'id': 5, 'type': 'Organization'}, {'id': '5', 'type': 'User'}, {}):
            http.get.return_value.json.return_value = value
            with self.assertRaises(TrialIdentityError):
                provider.verify('code', 'verifier')


if __name__ == '__main__':
    unittest.main()
