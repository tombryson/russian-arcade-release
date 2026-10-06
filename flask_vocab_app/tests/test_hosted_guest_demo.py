"""No-login demo isolation, bounded admission and unchanged shared spending."""
from concurrent.futures import Future
from hashlib import sha256
from pathlib import Path
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from types import SimpleNamespace

from flask import Flask, jsonify, request
from werkzeug.test import Client
from werkzeug.wrappers import Response

from hosted_trial import (COOKIE, GUEST_COOKIE, GUEST_SESSION_SECONDS, GUEST_STORAGE_BYTES,
                          HostedTrialDispatcher)
from services.ai_trial_budget import AITrialBudget, TrialDenied
from services.trial_provider import provider_call
from tests.test_hosted_trial import IdentityProvider


class HostedGuestDemoTests(unittest.TestCase):
    base = 'https://arcade.example'

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.now = 1_790_467_200
        self.ledger = AITrialBudget(self.root / 'ai-budget.sqlite3', enabled=True)
        self.ledger.initialize()
        self.provider = IdentityProvider()
        self.apps = []
        self.dispatch = HostedTrialDispatcher(
            lambda environ, respond: Response('public samples')(environ, respond), self.factory,
            root=self.root, ledger_path=self.ledger.path, secret='synthetic-demo-test-secret-' * 3,
            hostname='arcade.example', enabled=True, ai_enabled=True, guest_demo_enabled=True,
            identity_provider=self.provider, budget=self.ledger, seed=lambda *_: None,
            clock=lambda: self.now, max_cached_apps=3, max_guests=3)
        # Dispatcher tests use tiny workspaces; full application coverage lives
        # in HostedGuestCompositionTests below.
        sessions = patch('hosted_trial.install_trial_session')
        sessions.start()
        self.addCleanup(sessions.stop)
        disk = patch('hosted_trial.shutil.disk_usage')
        disk.start().return_value.free = 1024 ** 3
        self.addCleanup(disk.stop)
        network = patch('socket.socket.connect', side_effect=AssertionError('No live providers in demo tests'))
        network.start()
        self.addCleanup(network.stop)
        self.a, self.b = Client(self.dispatch, Response), Client(self.dispatch, Response)

    def factory(self, config):
        app = Flask(__name__)
        app.config.update(config)
        directory = Path(config['DB_PATH']).parent
        directory.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(config['DB_PATH']) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS notes(note TEXT)')
        @app.get('/who')
        def who():
            return jsonify(identity=config['AI_TRIAL_IDENTITY'], database=config['DB_PATH'])
        @app.route('/notes', methods=['GET', 'POST'])
        def notes():
            with sqlite3.connect(config['DB_PATH']) as conn:
                if request.method == 'POST':
                    conn.execute('INSERT INTO notes VALUES (?)', (request.json['note'],))
                return jsonify([row[0] for row in conn.execute('SELECT note FROM notes')])
        self.apps.append(app)
        return app

    def get(self, client, path, **kwargs):
        return client.get(path, base_url=self.base, buffered=True, **kwargs)

    def start(self, client):
        response = self.get(client, '/demo')
        self.assertEqual(response.status_code, 302, response.text)
        self.assertEqual(response.location, '/demo/')
        return self.get(client, '/demo/who').json

    def login(self, client):
        response = self.get(client, '/trial/sign-in/github')
        state = parse_qs(urlsplit(response.location).query)['state'][0]
        response = self.get(client, '/trial/callback?code=valid&state=' + state)
        self.assertEqual(response.status_code, 302, response.text)

    def test_opt_in_disabled_and_public_pages_do_not_provision_guests(self):
        self.assertIn('Try demo', self.get(self.a, '/').text)
        self.assertEqual(self.get(self.a, '/trial/status').json['demo_url'], '/demo/')
        self.dispatch.guest_demo_enabled = False
        self.assertEqual(self.get(self.a, '/demo').status_code, 404)
        self.assertFalse(self.get(self.a, '/trial/status').json['demo_enabled'])
        self.assertEqual(self.apps, [])

    def test_each_browser_has_an_isolated_stable_workspace(self):
        first, second = self.start(self.a), self.start(self.b)
        self.assertNotEqual(first['identity'], second['identity'])
        self.assertNotEqual(first['database'], second['database'])
        self.a.post('/demo/notes', base_url=self.base, json={'note': 'private to this demo'})
        self.assertEqual(self.get(self.b, '/demo/notes').json, [])
        self.assertEqual(self.start(self.a), first)
        self.assertEqual(self.get(self.a, '/demo/notes').json, ['private to this demo'])
        self.assertTrue(self.apps[0].config['HOSTED_GUEST_DEMO'])
        self.assertTrue(self.apps[0].config['HOSTED_AI_TRIAL'])
        self.assertFalse(self.apps[0].config['PUBLIC_DEMO'])
        status = self.get(self.a, '/demo/trial/status').json
        self.assertTrue(status['demo'])
        self.assertFalse(status['authenticated'])
        self.assertEqual(status['display_name'], 'Demo')
        self.assertNotIn(first['identity'], str(status))
        cookie = self.a.get_cookie(GUEST_COOKIE, domain='arcade.example')
        self.assertTrue(cookie.secure)
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, 'Lax')
        self.assertEqual(cookie.path, '/')

    def test_guest_status_and_account_do_not_offer_identity_linking(self):
        self.start(self.a)
        page = self.get(self.a, '/demo/trial/account')
        self.assertIn('24 hours', page.text)
        self.assertNotIn('/trial/connect/', page.text)
        self.assertNotIn('/trial/sign-out', page.text)
        self.assertIn('/trial/sign-in/github', page.text)
        self.assertIn('href="/demo/">Continue demo', page.text)
        self.assertIn('href="/" data-app-exit', page.text)
        response = self.a.post('/trial/connect/github', base_url=self.base, data={'csrf_token': 'anything'})
        self.assertEqual(response.status_code, 403)

    def test_main_entry_is_not_a_demo_even_with_a_guest_cookie(self):
        self.start(self.a)
        main = self.get(self.a, '/')
        self.assertIn('Try demo', main.text)
        self.assertNotIn('Public demo', main.text)
        self.assertNotIn('24 hours', main.text)
        self.assertNotIn('Continue demo', main.text)
        self.assertFalse(self.get(self.a, '/trial/status').json['demo'])
        self.assertEqual(self.get(self.a, '/api/v1/user-session').status_code, 401)
        self.assertTrue(self.get(self.a, '/demo/trial/status').json['demo'])

    def test_demo_api_never_creates_a_guest_implicitly(self):
        self.assertEqual(self.get(self.a, '/demo/api/v1/user-session').status_code, 401)
        self.assertEqual(self.a.post('/demo/notes', base_url=self.base, json={'note': 'no session'}).status_code, 401)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM guest_sessions').fetchone()[0], 0)

    def test_login_preserves_guest_and_personal_workspaces_without_merging(self):
        guest = self.start(self.a)
        self.a.post('/demo/notes', base_url=self.base, json={'note': 'guest-only'})
        self.login(self.a)
        personal = self.get(self.a, '/who').json
        self.assertEqual(personal['identity'], 'github:11')
        self.assertNotEqual(personal['database'], guest['database'])
        self.assertEqual(self.get(self.a, '/notes').json, [])
        personal_cookie = self.a.get_cookie(COOKIE, domain='arcade.example').value
        self.assertEqual(self.start(self.a), guest)
        self.assertEqual(self.get(self.a, '/who').json, personal)
        self.assertEqual(self.get(self.a, '/demo/notes').json, ['guest-only'])
        self.assertEqual(self.a.get_cookie(COOKIE, domain='arcade.example').value, personal_cookie)
        self.assertTrue(self.get(self.a, '/trial/status').json['authenticated'])
        self.assertFalse(self.get(self.a, '/trial/status').json['demo'])
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identity_aliases WHERE identity=?', (guest['identity'],)).fetchone()[0], 0)

    def test_foreign_or_forged_cookies_cannot_select_a_guest(self):
        known = self.start(self.a)
        for value in ('forged', self.dispatch.guest_signer.dumps(known['identity']),
                      self.dispatch.signer.dumps('anything')):
            self.b.set_cookie(GUEST_COOKIE, value, domain='arcade.example')
            self.assertEqual(self.get(self.b, '/demo/api/v1/user-session').status_code, 401)
        self.assertEqual(self.get(self.b, '/demo/api/v1/user-session?identity=' + known['identity']).status_code, 401)

    def test_return_path_keeps_local_destinations_and_rejects_external_urls(self):
        self.assertEqual(self.get(self.a, '/demo?next=/writing').location, '/demo/writing')
        self.assertEqual(self.get(self.a, '/demo?next=https://evil.example').location, '/demo/')
        self.assertEqual(self.get(self.a, '/demo?next=//evil.example').location, '/demo/')

    def test_prefetch_embeds_head_and_cross_origin_requests_do_not_create_guests(self):
        self.assertEqual(self.a.head('/demo', base_url=self.base).status_code, 302)
        self.assertEqual(self.a.head('/demo/', base_url=self.base).status_code, 200)
        self.assertEqual(self.a.post('/demo', base_url=self.base).status_code, 405)
        for headers in ({'Purpose': 'prefetch'}, {'Sec-Purpose': 'prefetch;prerender'},
                        {'Sec-Fetch-Dest': 'image'}, {'Origin': 'https://evil.example'}):
            self.assertEqual(self.get(self.a, '/demo', headers=headers).status_code, 204)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM guest_sessions').fetchone()[0], 0)
        # A real navigation from GitHub is the intended demo entry.
        self.assertEqual(self.get(self.a, '/demo', headers={'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Dest': 'document', 'Sec-Fetch-Mode': 'navigate'}).status_code, 302)

    def test_guest_capacity_does_not_consume_personal_account_capacity(self):
        self.dispatch.max_guests = 1
        self.dispatch.max_tenants = 1
        self.start(self.a)
        self.assertEqual(self.get(self.b, '/demo').status_code, 503)
        self.login(self.b)
        self.assertEqual(self.get(self.b, '/who').json['identity'], 'github:11')

    def test_cookie_reset_does_not_bypass_global_admission_limit(self):
        self.dispatch.max_guests = 30
        for _ in range(12):
            client = Client(self.dispatch, Response)
            self.assertEqual(self.get(client, '/demo').status_code, 302)
        blocked = self.get(self.a, '/demo')
        self.assertEqual(blocked.status_code, 429)
        self.assertIn('Retry-After', blocked.headers)
        self.now += 61
        self.assertEqual(self.get(self.a, '/demo').status_code, 302)

    def test_global_and_visitor_write_limits_are_separate(self):
        first, second = self.start(self.a), self.start(self.b)
        with sqlite3.connect(self.dispatch.registry) as conn:
            conn.execute('INSERT INTO request_limits VALUES (?,?,?,?)', (first['identity'], 'writes', self.now // 60, 30))
        self.assertEqual(self.a.post('/demo/notes', base_url=self.base, json={'note': 'limited'}).status_code, 429)
        self.assertEqual(self.b.post('/demo/notes', base_url=self.base, json={'note': 'allowed'}).status_code, 200)
        with sqlite3.connect(self.dispatch.registry) as conn:
            conn.execute("UPDATE request_limits SET attempts=180 WHERE identity='guest-global' AND kind='writes'")
        self.assertEqual(self.b.post('/demo/notes', base_url=self.base, json={'note': 'limited'}).status_code, 429)

    def test_storage_limit_cannot_be_overridden_by_guest(self):
        first = self.start(self.a)
        self.assertEqual(self.dispatch._storage_limit(first['identity']), GUEST_STORAGE_BYTES)
        media = Path(first['database']).parent / 'huge.dat'
        with media.open('wb') as output:
            output.truncate(GUEST_STORAGE_BYTES)
        response = self.a.post('/demo/notes', base_url=self.base, json={'note': 'full'}, buffered=True)
        self.assertEqual(response.status_code, 507)
        self.assertEqual(response.json['error']['code'], 'storage_limit')
        self.assertIn('demo has reached its storage limit', response.json['error']['message'])
        self.assertEqual(self.dispatch.storage_reserved.get(first['identity'], 0), 0)
        self.assertEqual(self.get(self.a, '/demo/notes').status_code, 200)

    def test_low_server_storage_blocks_writes_then_recovers_in_same_demo(self):
        first = self.start(self.a)
        identity = first['identity']
        with patch('hosted_trial.shutil.disk_usage') as disk:
            # The workspace has room, but this write would cross the server's
            # minimum free-space reserve by one byte.
            disk.return_value.free = 257 * 1024 * 1024 - 1
            with self.assertLogs('hosted_trial', level='WARNING') as captured:
                response = self.a.post('/demo/notes', base_url=self.base,
                    json={'note': 'saved after retry'}, buffered=True)
            self.assertEqual(response.status_code, 507)
            self.assertEqual(response.json['error']['code'], 'server_storage_low')
            self.assertIn('try again shortly', response.json['error']['message'])
            self.assertEqual(response.headers['Retry-After'], '30')
            self.assertEqual(self.dispatch.storage_reserved.get(identity, 0), 0)
            self.assertEqual(self.dispatch.inflight.get(identity, 0), 0)
            self.assertIn('Server storage admission denied', captured.output[0])
            self.assertNotIn(identity, captured.output[0])
            self.assertNotIn(str(self.root), captured.output[0])
            saved = self.get(self.a, '/demo/notes')
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json, [])

            disk.return_value.free = 1024 ** 3
            response = self.a.post('/demo/notes', base_url=self.base,
                json={'note': 'saved after retry'}, buffered=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, ['saved after retry'])
            self.assertEqual(self.dispatch.storage_reserved[identity], 0)
            self.assertEqual(self.dispatch.inflight[identity], 0)
            self.assertEqual(self.get(self.a, '/demo/who').json, first)

    def test_guests_share_existing_global_dollar_limit(self):
        first, second = self.start(self.a), self.start(self.b)
        invoke = Mock(return_value='generated')
        config = self.dispatch.cache[first['identity']].config
        self.assertEqual(provider_call(config, 'synthetic-test', {}, 600_000, invoke, lambda _: 600_000), 'generated')
        other = self.dispatch.cache[second['identity']].config
        with self.assertRaises(TrialDenied):
            provider_call(other, 'synthetic-test', {}, 500_000, invoke, lambda _: 500_000)
        self.assertEqual(invoke.call_count, 1)
        with sqlite3.connect(self.ledger.path) as conn:
            self.assertEqual(conn.execute('SELECT SUM(actual) FROM trial_requests').fetchone()[0], 600_000)

    def test_expiry_is_fixed_and_cleanup_preserves_budget_and_personal_data(self):
        self.login(self.b)
        personal = self.get(self.b, '/who').json
        guest = self.start(self.a)
        self.ledger.reserve(guest['identity'], 'spent', '0' * 64, 100)
        self.ledger.settle(guest['identity'], 'spent', 100)
        self.ledger.reserve(guest['identity'], 'uncertain-call', '1' * 64, 120)
        with sqlite3.connect(self.dispatch.registry) as conn:
            expires = conn.execute('SELECT expires_at FROM guest_sessions').fetchone()[0]
        self.now += 3600
        self.start(self.a)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT expires_at FROM guest_sessions').fetchone()[0], expires)
        self.now += GUEST_SESSION_SECONDS
        self.assertIn('Try demo', self.get(self.a, '/').text)
        self.assertFalse(Path(guest['database']).parent.exists())
        self.assertTrue(Path(personal['database']).exists())
        with sqlite3.connect(self.ledger.path) as conn:
            self.assertEqual(conn.execute("SELECT actual FROM trial_requests WHERE identity=? AND request_id='spent'", (guest['identity'],)).fetchone()[0], 100)
            self.assertEqual(conn.execute("SELECT reserved,state FROM trial_requests WHERE identity=? AND request_id='uncertain-call'", (guest['identity'],)).fetchone(), (120, 'reserved'))
        fresh = self.start(self.a)
        self.assertNotEqual(fresh['identity'], guest['identity'])

    def test_expired_busy_workspaces_survive_until_jobs_and_requests_finish(self):
        guest = self.start(self.a)
        identity = guest['identity']
        self.dispatch.inflight[identity] = 1
        self.now += GUEST_SESSION_SECONDS + 1
        self.dispatch._cleanup_guests(force=True)
        self.assertTrue(Path(guest['database']).exists())
        self.dispatch.inflight[identity] = 0
        future = Future()
        self.dispatch.cache[identity].extensions['trial_futures'].add(future)
        self.dispatch._cleanup_guests(force=True)
        self.assertTrue(Path(guest['database']).exists())
        self.dispatch.cache[identity].extensions['trial_futures'].clear()
        self.dispatch._cleanup_guests(force=True)
        self.assertFalse(Path(guest['database']).exists())

    def test_cleanup_refuses_non_guest_records_and_symlinked_workspaces(self):
        outside = self.root / 'personal-data'
        outside.mkdir()
        keep = outside / 'keep.txt'
        keep.write_text('preserve')
        identity = 'demo:' + 'a' * 32
        directory = self.root / 'tenants' / sha256(identity.encode()).hexdigest()
        directory.parent.mkdir()
        directory.symlink_to(outside, target_is_directory=True)
        with sqlite3.connect(self.dispatch.registry) as conn:
            conn.execute('INSERT INTO guest_sessions VALUES (?,?,?,?)', ('bad1', identity, 0, 1))
            conn.execute('INSERT INTO guest_sessions VALUES (?,?,?,?)', ('bad2', 'github:11', 0, 1))
        self.dispatch._cleanup_guests(force=True)
        self.assertEqual(keep.read_text(), 'preserve')
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM guest_sessions').fetchone()[0], 2)

    def test_disabled_ai_allows_guest_sample_workspace_without_authorizing_spend(self):
        self.dispatch.ai_enabled = False
        self.dispatch.config['AI_TRIAL_ENABLED'] = False
        with patch.object(self.ledger, 'authorize_identity') as authorize:
            self.start(self.a)
            authorize.assert_not_called()
        self.assertFalse(self.get(self.a, '/trial/status').json['ai_enabled'])


class HostedGuestCompositionTests(unittest.TestCase):
    def setUp(self):
        from tests import test_hosted_trial_integration
        test_hosted_trial_integration.HostedTrialIntegrationTests.setUp(self)
        flags = patch.dict(os.environ, {'HOSTED_GUEST_DEMO_ENABLED': 'true',
            'HOSTED_ACCOUNTS_ENABLED': 'false', 'GITHUB_OAUTH_CLIENT_ID': '',
            'GITHUB_OAUTH_CLIENT_SECRET': '', 'GOOGLE_OAUTH_CLIENT_ID': '',
            'GOOGLE_OAUTH_CLIENT_SECRET': ''})
        flags.start()
        self.addCleanup(flags.stop)

    def test_packaged_journey_and_account_assets_load_without_a_profile(self):
        from hosted import create_hosted_app
        from hosted_account_page import ACCOUNT_PUBLIC_ASSETS
        app = create_hosted_app()
        client = app.test_client()
        journey_images = {
            '/static/images/barsik-leaving-home-v1.webp',
            '/static/images/barsik-post-office-v1.webp',
            '/static/images/barsik-market-v1.webp',
            '/static/images/barsik-leaving-town-v1.webp',
        }
        for path in sorted(journey_images | ACCOUNT_PUBLIC_ASSETS | {'/static/images/phrasebook.svg'}):
            for prefix in ('', '/demo'):
                for method in ('GET', 'HEAD'):
                    with self.subTest(path=prefix + path, method=method):
                        with client.open(prefix + path, method=method, base_url=self.base) as response:
                            self.assertEqual(response.status_code, 200)
                            self.assertNotEqual(response.mimetype, 'text/html')
                            if path in journey_images and method == 'GET':
                                self.assertEqual(response.mimetype, 'image/webp')
                                self.assertEqual(response.data[8:12], b'WEBP')
                            if path == '/static/images/phrasebook.svg':
                                self.assertEqual(response.mimetype, 'image/svg+xml')
                                if method == 'GET':
                                    self.assertTrue(response.data.startswith(b'<svg'))
        self.assertFalse(app.extensions['hosted_trial'].cache)

    def test_practice_recordings_are_public_and_support_partial_playback(self):
        from hosted import create_hosted_app
        from services.course_targets import practice_catalogue
        from services.first_steps_audio import authored_clips
        app = create_hosted_app()
        client = app.test_client()
        paths = {item['question']['audio_url'] for item in practice_catalogue()['items']
                 if item['question'].get('audio_url')}
        self.assertEqual(len(paths), 5)
        paths.update(authored_clips())
        for path in paths:
            for prefix in ('', '/demo'):
                with self.subTest(path=prefix + path):
                    with client.get(prefix + path, base_url=self.base, headers={'Range': 'bytes=0-511'}) as response:
                        self.assertEqual(response.status_code, 206)
                        self.assertEqual(response.mimetype, 'audio/mpeg')
                        self.assertEqual(len(response.data), 512)
                        self.assertTrue(response.headers['Content-Range'].startswith('bytes 0-511/'))
        self.assertFalse(app.extensions['hosted_trial'].cache)

    def test_whole_app_without_oauth_is_isolated_and_provider_calls_remain_metered(self):
        from hosted import create_hosted_app
        app = create_hosted_app()
        dispatch = app.extensions['hosted_trial']
        def close_executors():
            for tenant in dispatch.cache.values():
                for executor in tenant.extensions.get('trial_executors', []):
                    executor.shutdown(wait=True)
        self.addCleanup(close_executors)
        client, other = app.test_client(), app.test_client()
        self.assertEqual(client.get('/demo', base_url=self.base).status_code, 302)
        for path in ('/', '/comprehension', '/writing', '/sentences', '/sentences/saved',
                     '/lessons', '/vocab', '/api/v1/flashcards', '/api/v1/live-conversations/options'):
            result = client.get('/demo' + path, base_url=self.base)
            self.assertEqual(result.status_code, 200, f'{path}: {result.text[:250]}')
        self.assertIn('data-account-mode="demo"', client.get('/demo/', base_url=self.base).text)
        self.assertIn('<summary>Demo</summary>', client.get('/demo/', base_url=self.base).text)
        self.assertEqual(client.get('/demo/tools/anki/', base_url=self.base).status_code, 403)
        status = client.get('/demo/trial/status', base_url=self.base).json
        self.assertTrue(status['demo'])
        self.assertFalse(status['configured'])
        self.assertEqual(status['providers'], [])
        token = client.get('/demo/api/v1/user-session', base_url=self.base).json['csrf_token']
        # Generated media belongs to this workspace, even though its legacy URL
        # starts with /static. Public packaged asset routing must not catch it.
        guest_app = next(iter(dispatch.cache.values()))
        media = Path(guest_app.config['APP_MEDIA_DIR'])
        media.mkdir(parents=True, exist_ok=True)
        (media / 'private-demo-test.mp3').write_bytes(b'only this visitor')
        media_path = '/demo/static/media/private-demo-test.mp3'
        self.assertEqual(client.get(media_path, base_url=self.base).data, b'only this visitor')
        self.assertNotEqual(client.get('/static/media/private-demo-test.mp3', base_url=self.base).data, b'only this visitor')
        sdk = Mock()
        sdk.responses.create.return_value = SimpleNamespace(status='completed',
            output_text=json.dumps({'sentence': 'Я читаю книгу.', 'english': 'I am reading a book.'}),
            usage=SimpleNamespace(input_tokens=10, output_tokens=10))
        with patch('openai.OpenAI', return_value=sdk), patch('services.sentence_service.translation_candidates', return_value={}):
            generated = client.post('/demo/sentence/generate', base_url=self.base,
                data={'difficulty': '1', 'topic': 'any'}, headers={'X-CSRF-Token': token})
        self.assertEqual(generated.status_code, 303, generated.text[:300])
        sdk.responses.create.assert_called_once()
        self.assertIn('I am reading a book.', client.get(generated.location, base_url=self.base).text)
        self.assertIn('Я читаю книгу.', client.get('/demo/sentences/saved', base_url=self.base).text)
        self.assertEqual(other.get('/demo', base_url=self.base).status_code, 302)
        self.assertNotEqual(other.get(media_path, base_url=self.base).data, b'only this visitor')
        self.assertNotIn('Я читаю книгу.', other.get('/demo/sentences/saved', base_url=self.base).text)
        with sqlite3.connect(self.ledger_path) as conn:
            rows = conn.execute('SELECT identity,actual,state FROM trial_requests').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0][0].startswith('demo:'))
        self.assertGreater(rows[0][1], 0)
        self.assertEqual(rows[0][2], 'settled')
        with sqlite3.connect(dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identities').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identity_aliases').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
