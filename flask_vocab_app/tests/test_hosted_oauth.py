"""Provider validation and explicit account connection, without network access."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from flask import Flask
from werkzeug.test import Client
from werkzeug.wrappers import Response
from hosted_trial import COOKIE, FLOW_COOKIE, GoogleIdentity, HostedTrialDispatcher, TrialIdentityError
from services.ai_trial_budget import AITrialBudget
from tests.test_hosted_trial import IdentityProvider


class GoogleProvider:
    configured = True
    def __init__(self):
        self.identity, self.calls, self.verify_hook = 'google:google-user-1', [], None
    def authorization_url(self, state, verifier, nonce):
        self.calls.append((state, verifier, nonce))
        return 'https://accounts.google.com/o/oauth2/v2/auth?state=' + state
    def verify(self, code, verifier, nonce):
        if self.verify_hook:
            self.verify_hook()
        if code != 'valid' or not nonce:
            raise TrialIdentityError('Invalid sign-in')
        return self.identity, 'sample-user'


class HostedOAuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.github, self.google = IdentityProvider(), GoogleProvider()
        self.ledger = AITrialBudget(self.root / 'budget.sqlite3', enabled=True)
        self.ledger.initialize()
        self.configs = []
        # Full learner/profile middleware is covered in hosted_trial_integration.
        session = patch('hosted_trial.install_trial_session')
        session.start()
        self.addCleanup(session.stop)
        self.dispatch = self.make_dispatcher()
        self.a, self.b = Client(self.dispatch, Response), Client(self.dispatch, Response)
        self.base = 'https://arcade.example'
    def make_dispatcher(self):
        return HostedTrialDispatcher(lambda e, s: Response('sample')(e, s), self.factory,
            root=self.root, ledger_path=self.ledger.path, secret='synthetic-secret-' * 3,
            hostname='arcade.example', enabled=True, identity_provider=self.github,
            identity_providers={'google': self.google}, budget=self.ledger, seed=lambda config, name: None)
    def factory(self, config):
        self.configs.append(config)
        app = Flask(__name__)
        app.config.update(config)
        return app
    def get(self, client, path):
        return client.get(path, base_url=self.base, buffered=True)
    def start(self, client, provider, path=None):
        result = self.get(client, path or '/trial/sign-in/' + provider)
        self.assertEqual(result.status_code, 302, result.text)
        return parse_qs(urlsplit(result.location).query)['state'][0]
    def callback(self, client, provider, state, code='valid'):
        path = '/trial/callback' + ('/google' if provider == 'google' else '')
        return self.get(client, path + '?code=' + code + '&state=' + state)
    def login(self, client, provider):
        response = self.callback(client, provider, self.start(client, provider))
        self.assertEqual(response.status_code, 302, response.text)
        return response
    def session_hash(self, client):
        cookie = client.get_cookie(COOKIE, domain='arcade.example').value
        return sha256(self.dispatch.signer.loads(cookie).encode()).hexdigest()
    def connect(self, client, provider, **kwargs):
        return client.post('/trial/connect/' + provider, base_url=self.base,
            data={'csrf_token': self.dispatch.link_signer.dumps(self.session_hash(client))}, **kwargs)
    def connection_state(self, client, provider='google'):
        response = self.connect(client, provider)
        self.assertEqual(response.status_code, 302, response.text)
        return parse_qs(urlsplit(response.location).query)['state'][0]

    def test_chooser_configured_only_and_safe_next(self):
        page = self.get(self.a, '/trial/sign-in?next=/%23flashcards')
        self.assertEqual(page.status_code, 200)
        self.assertIn('/trial/sign-in/google?next=%2F%23flashcards', page.text)
        self.assertIn('/trial/sign-in/github?next=%2F%23flashcards', page.text)
        self.assertEqual(self.google.calls, [])
        self.google.configured = False
        self.assertNotIn('/trial/sign-in/google', self.get(self.a, '/trial/sign-in').text)
        self.assertEqual(self.get(self.a, '/trial/sign-in/google').status_code, 503)
        self.assertEqual(self.get(self.a, '/trial/sign-in/not-a-provider').status_code, 404)
        status = self.get(self.a, '/trial/status').json
        self.assertEqual([provider['id'] for provider in status['providers']], ['github'])
        self.login(self.a, 'github')
        self.assertEqual(self.get(self.a, '/trial/sign-in').location, '/post/profiles')

    def test_provider_state_browser_binding_replay_and_redirect(self):
        state = self.start(self.a, 'google', '/trial/sign-in/google?next=/%23flashcards')
        self.assertEqual(self.callback(self.a, 'github', state).status_code, 400)
        self.assertEqual(self.callback(self.b, 'google', state).status_code, 400)
        self.assertEqual(self.callback(self.a, 'google', state).location, '/#flashcards')
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 400)
        self.assertFalse(self.get(self.b, '/trial/status').json['authenticated'])
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM oauth_flows').fetchone()[0], 0)

    def test_verification_failure_and_denial_create_no_account(self):
        state = self.start(self.a, 'google')
        self.assertEqual(self.callback(self.a, 'google', state, 'bad').status_code, 503)
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 400)
        state = self.start(self.a, 'google')
        result = self.get(self.a, '/trial/callback/google?error=access_denied&state=' + state)
        self.assertEqual(result.status_code, 400)
        self.assertIsNone(self.a.get_cookie(FLOW_COOKIE, domain='arcade.example'))
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identities').fetchone()[0], 0)
        self.assertEqual(self.configs, [])

    def test_matching_names_never_merge_google_subject_is_stable(self):
        self.login(self.a, 'github')
        self.login(self.b, 'google')
        self.assertNotEqual(self.configs[0]['DB_PATH'], self.configs[1]['DB_PATH'])
        expected = 'google:' + sha256(self.google.identity.encode()).hexdigest()
        self.assertEqual(self.configs[1]['AI_TRIAL_IDENTITY'], expected)
        self.dispatch.cache.clear()
        self.login(self.b, 'google')
        self.assertEqual(self.configs[-1]['AI_TRIAL_IDENTITY'], expected)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identities').fetchone()[0], 2)
        with sqlite3.connect(self.ledger.path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM trial_accounts').fetchone()[0], 2)

    def test_long_google_subject_fits_existing_budget_and_storage_identity_limit(self):
        self.google.identity = 'google:' + 'CaseSensitive.' * 18 + 'xyz'
        self.assertEqual(len(self.google.identity.removeprefix('google:')), 255)
        self.login(self.a, 'google')
        self.assertLess(len(self.configs[-1]['AI_TRIAL_IDENTITY']), 200)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT provider_identity FROM identity_aliases').fetchone()[0], self.google.identity)

    def test_connect_preserves_workspace_files_cookie_scope_budget_and_denial(self):
        self.login(self.a, 'github')
        config = dict(self.configs[0])
        path = Path(config['DB_PATH'])
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as conn:
            conn.execute('CREATE TABLE personal(note TEXT)')
            conn.execute("INSERT INTO personal VALUES ('saved progress')")
        Path(config['APP_MEDIA_DIR']).mkdir()
        recording = Path(config['APP_MEDIA_DIR']) / 'recording.mp3'
        recording.write_bytes(b'personal recording')
        self.ledger.reserve('github:11', 'previous-spend', 'a' * 64, 100)
        self.ledger.settle('github:11', 'previous-spend', 90)
        with sqlite3.connect(self.ledger.path) as conn:
            conn.execute("UPDATE trial_accounts SET enabled=0 WHERE identity='github:11'")
            spend = conn.execute('SELECT * FROM trial_requests').fetchall()
        cookie = self.a.get_cookie(COOKIE, domain='arcade.example').value
        state = self.connection_state(self.a)
        self.assertEqual(self.callback(self.a, 'google', state).location, '/trial/account')
        self.assertEqual(self.a.get_cookie(COOKIE, domain='arcade.example').value, cookie)
        self.dispatch = self.make_dispatcher()
        self.b = Client(self.dispatch, Response)
        self.login(self.b, 'google')
        for key in ('AI_TRIAL_IDENTITY', 'DB_PATH', 'APP_MEDIA_DIR', 'SECRET_KEY', 'SESSION_COOKIE_NAME'):
            self.assertEqual(self.configs[-1][key], config[key], key)
        self.assertEqual(recording.read_bytes(), b'personal recording')
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute('SELECT note FROM personal').fetchone()[0], 'saved progress')
        with sqlite3.connect(self.ledger.path) as conn:
            self.assertEqual(conn.execute('SELECT identity,enabled FROM trial_accounts').fetchall(), [('github:11', 0)])
            self.assertEqual(conn.execute('SELECT * FROM trial_requests').fetchall(), spend)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identities').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identity_aliases').fetchone()[0], 2)

    def test_connect_requires_post_session_csrf_origin_and_purpose(self):
        self.assertEqual(self.get(self.a, '/trial/connect/google').status_code, 404)
        self.assertEqual(self.a.post('/trial/connect/google', base_url=self.base).status_code, 403)
        self.login(self.a, 'github')
        self.assertEqual(self.a.post('/trial/connect/google', base_url=self.base, data={'csrf_token': 'wrong'}).status_code, 403)
        signout_token = self.dispatch.csrf_signer.dumps(self.session_hash(self.a))
        self.assertEqual(self.a.post('/trial/connect/google', base_url=self.base, data={'csrf_token': signout_token}).status_code, 403)
        for headers in ({'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.connect(self.a, 'google', headers=headers).status_code, 403)
        self.assertEqual(self.google.calls, [])

    def test_connect_rejects_other_account_identity_and_provider_replacement(self):
        self.login(self.a, 'github')
        self.login(self.b, 'google')
        state = self.connection_state(self.a)
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 409)
        self.google.identity = 'google:new-user'
        state = self.connection_state(self.a)
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 302)
        self.google.identity = 'google:replacement'
        state = self.connection_state(self.a)
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 409)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identities').fetchone()[0], 2)
            self.assertIsNone(conn.execute('SELECT 1 FROM identity_aliases WHERE provider_identity=?', (self.google.identity,)).fetchone())

    def test_concurrent_connections_cannot_claim_one_provider_for_two_workspaces(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        self.login(self.a, 'github')
        self.github.identity = 'github:22'
        self.login(self.b, 'github')
        states = (self.connection_state(self.a), self.connection_state(self.b))
        barrier = Barrier(2)
        self.google.verify_hook = lambda: barrier.wait(timeout=5)
        with ThreadPoolExecutor(max_workers=2) as workers:
            callbacks = [workers.submit(self.callback, client, 'google', state)
                         for client, state in zip((self.a, self.b), states)]
            statuses = sorted(future.result(timeout=10).status_code for future in callbacks)
        self.assertEqual(statuses, [302, 409])
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM identity_aliases WHERE provider='google'").fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identities').fetchone()[0], 2)

    def test_signout_or_different_session_midflow_rejects_callback(self):
        self.login(self.a, 'github')
        state = self.connection_state(self.a)
        token = self.dispatch.csrf_signer.dumps(self.session_hash(self.a))
        self.a.post('/trial/sign-out', base_url=self.base, data={'csrf_token': token})
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 400)
        self.login(self.a, 'github')
        state = self.connection_state(self.a)
        original_cookie = self.a.get_cookie(COOKIE, domain='arcade.example').value
        self.github.identity = 'github:22'
        self.login(self.b, 'github')
        self.a.set_cookie(COOKIE, self.b.get_cookie(COOKIE, domain='arcade.example').value, domain='arcade.example')
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 403)
        self.a.set_cookie(COOKIE, original_cookie, domain='arcade.example')
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 400)

    def test_revocation_during_provider_request_cannot_link(self):
        self.login(self.a, 'github')
        state = self.connection_state(self.a)
        token_hash = self.session_hash(self.a)
        def revoke():
            with self.dispatch._db() as conn:
                conn.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash,))
        self.google.verify_hook = revoke
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 403)
        with sqlite3.connect(self.dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM identity_aliases').fetchone()[0], 1)

    def test_account_switch_rotates_previous_browser_session(self):
        self.login(self.a, 'github')
        original_cookie = self.a.get_cookie(COOKIE, domain='arcade.example').value
        state = self.connection_state(self.a)
        self.login(self.a, 'google')
        self.a.set_cookie(COOKIE, original_cookie, domain='arcade.example')
        self.assertFalse(self.get(self.a, '/trial/status').json['authenticated'])
        self.assertEqual(self.callback(self.a, 'google', state).status_code, 400)

    def test_old_registry_and_pending_github_flow_migrate_additively(self):
        self.login(self.a, 'github')
        cookie = self.a.get_cookie(COOKIE, domain='arcade.example').value
        state = self.start(self.b, 'github')
        original_path = self.configs[0]['DB_PATH']
        with sqlite3.connect(self.dispatch.registry) as conn:
            conn.execute('DROP TABLE identity_aliases')
            conn.execute('CREATE TABLE old_flows AS SELECT state_hash,browser_hash,verifier,next_url,expires_at FROM oauth_flows')
            conn.execute('DROP TABLE oauth_flows')
            conn.execute('ALTER TABLE old_flows RENAME TO oauth_flows')
        restarted = self.make_dispatcher()
        returning = Client(restarted, Response)
        returning.set_cookie(COOKIE, cookie, domain='arcade.example')
        self.assertTrue(self.get(returning, '/trial/status').json['authenticated'])
        returning.set_cookie(FLOW_COOKIE, self.b.get_cookie(FLOW_COOKIE, domain='arcade.example').value, domain='arcade.example')
        self.assertEqual(self.callback(returning, 'github', state).status_code, 302)
        with sqlite3.connect(restarted.registry) as conn:
            self.assertEqual(conn.execute('SELECT provider_identity,identity FROM identity_aliases').fetchall(), [('github:11', 'github:11')])
        self.assertEqual(self.configs[-1]['DB_PATH'], original_path)


class GoogleIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from google.auth.crypt import RSASigner
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.signer = RSASigner.from_string(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), key_id='test-key')
        cls.public_key = key.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    def setUp(self):
        self.http = Mock()
        self.provider = GoogleIdentity('our-client', 'synthetic-secret', 'https://arcade.example/trial/callback/google', http=self.http)
        self.claims = {'iss': 'https://accounts.google.com', 'aud': 'our-client', 'sub': 'case-Sensitive_123',
                       'iat': int(time.time()) - 10, 'exp': int(time.time()) + 300, 'nonce': 'expected-nonce', 'name': 'Learner'}
        transport = patch('google.auth.transport.requests.Request')
        self.transport = transport.start().return_value
        self.addCleanup(transport.stop)
        self.transport.return_value.status = 200
        self.transport.return_value.data = json.dumps({'test-key': self.public_key}).encode()
    def verify(self, changes=None, **kwargs):
        from google.auth import jwt
        claims = dict(self.claims, **(changes or {}))
        for key in kwargs.get('remove', ()):
            claims.pop(key, None)
        token = jwt.encode(self.signer, claims).decode()
        self.http.post.return_value.json.return_value = {'id_token': token, 'access_token': 'discarded'}
        return self.provider.verify('code', 'verifier', 'expected-nonce')

    def test_code_exchange_signature_validation_and_pkce(self):
        options = parse_qs(urlsplit(self.provider.authorization_url('state', 'verifier', 'expected-nonce')).query)
        self.assertEqual(options['scope'], ['openid profile'])
        self.assertEqual(options['code_challenge_method'], ['S256'])
        self.assertEqual(options['nonce'], ['expected-nonce'])
        self.assertEqual(options['response_type'], ['code'])
        self.assertNotIn('access_type', options)
        self.assertEqual(self.verify(), ('google:case-Sensitive_123', 'Learner'))
        payload = self.http.post.call_args.kwargs['data']
        self.assertEqual(payload['code_verifier'], 'verifier')
        self.assertEqual(payload['redirect_uri'], 'https://arcade.example/trial/callback/google')
        self.assertEqual(self.transport.call_args.kwargs['timeout'], 15)

    def test_invalid_claims_fail(self):
        for changes in ({'iss': 'https://evil.example'}, {'aud': 'different-client'},
                        {'exp': int(time.time()) - 10}, {'iat': int(time.time()) + 600},
                        {'nonce': 'wrong'}, {'sub': ''}, {'sub': 'x' * 256}, {'azp': 'different-client'}):
            with self.subTest(changes=changes), self.assertRaises(TrialIdentityError):
                self.verify(changes)
        for key in ('exp', 'iat', 'aud', 'iss', 'sub', 'nonce'):
            with self.subTest(missing=key), self.assertRaises(TrialIdentityError):
                self.verify(remove=(key,))

    def test_invalid_signature_fails(self):
        self.transport.return_value.data = json.dumps({'different-key': self.public_key}).encode()
        with self.assertRaises(TrialIdentityError):
            self.verify()

    def test_tampered_signature_fails_with_matching_certificate_key_id(self):
        from google.auth import jwt
        token = jwt.encode(self.signer, self.claims).decode()
        header, payload, signature = token.split('.')
        signature = ('A' if signature[0] != 'A' else 'B') + signature[1:]
        self.http.post.return_value.json.return_value = {'id_token': '.'.join((header, payload, signature))}
        with self.assertRaises(TrialIdentityError):
            self.provider.verify('code', 'verifier', 'expected-nonce')

    def test_missing_token_or_malformed_response_fails(self):
        for value in ({}, {'id_token': ''}, {'id_token': 'invalid'}, [], None):
            with self.subTest(value=value), self.assertRaises(TrialIdentityError):
                self.http.post.return_value.json.return_value = value
                self.provider.verify('code', 'verifier', 'expected-nonce')


if __name__ == '__main__':
    unittest.main()
