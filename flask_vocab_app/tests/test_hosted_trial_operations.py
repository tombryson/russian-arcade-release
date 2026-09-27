"""Operator controls must not weaken visitor isolation or paid AI limits."""
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from flask import Flask
from werkzeug.test import Client
from werkzeug.wrappers import Response

from hosted_trial import DEFAULT_TENANT_STORAGE_BYTES, HostedTrialDispatcher


class HostedOperatorTests(unittest.TestCase):
    base = 'https://arcade.example'

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.operator = self.root / 'operator'
        self.operator.mkdir()
        self.limits = self.operator / 'storage-limits.json'
        self.provider = Mock(configured=True)
        self.provider.authorization_url.side_effect = lambda state, verifier: 'https://github.com/login/oauth/authorize?state=' + state
        self.budget, self.seed = Mock(), Mock()
        self.factory = Mock(side_effect=self.app)
        self.dispatch = HostedTrialDispatcher(
            lambda environ, respond: Response('public samples')(environ, respond),
            self.factory, root=self.root, ledger_path=self.root / 'budget.sqlite3',
            secret='test-secret-' * 4, hostname='arcade.example', enabled=True,
            identity_provider=self.provider, budget=self.budget, seed=self.seed)
        # These tests exercise the dispatcher. Existing integration tests cover
        # the profile middleware and full database migrations.
        sessions = patch('hosted_trial.install_trial_session')
        sessions.start()
        self.addCleanup(sessions.stop)
        disk = patch('hosted_trial.shutil.disk_usage')
        disk.start().return_value.free = 1024 ** 3
        self.addCleanup(disk.stop)
        self.a, self.b = Client(self.dispatch, Response), Client(self.dispatch, Response)

    def app(self, settings):
        app = Flask(__name__)
        app.config.update(settings)
        Path(settings['DB_PATH']).parent.mkdir(parents=True, exist_ok=True)
        app.add_url_rule('/content', 'content', lambda: 'saved content', methods=['GET', 'POST'])
        return app

    @staticmethod
    def digest(identity):
        return sha256(identity.encode()).hexdigest()

    def login(self, client, identity='github:11'):
        self.provider.verify.return_value = (identity, 'sample-user')
        start = client.get('/trial/sign-in/github', base_url=self.base)
        self.assertEqual(start.status_code, 302)
        state = parse_qs(urlsplit(start.location).query)['state'][0]
        result = client.get('/trial/callback?code=valid&state=' + state, base_url=self.base)
        self.assertEqual(result.status_code, 302, result.text)

    def marker(self, identity='github:11'):
        directory = self.operator / 'maintenance'
        directory.mkdir(exist_ok=True)
        marker = directory / self.digest(identity)
        marker.touch()
        return marker

    def use_storage(self, identity, size):
        path = self.root / 'tenants' / self.digest(identity) / 'media' / 'large.bin'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('wb') as stream:
            stream.truncate(size)  # Sparse file: no large fixture allocation.

    def post(self, client, **kwargs):
        return client.post('/content', base_url=self.base, buffered=True, **kwargs)

    def test_storage_override_applies_only_to_verified_identity(self):
        self.login(self.a)
        self.login(self.b, 'github:22')
        for identity in ('github:11', 'github:22'):
            self.use_storage(identity, 105 * 1024 * 1024)
        self.assertEqual(self.post(self.a).status_code, 507)
        self.limits.write_text(json.dumps({self.digest('github:11'): 256 * 1024 * 1024}))
        self.assertEqual(self.post(self.a).status_code, 200)
        self.assertEqual(self.post(self.b).status_code, 507)
        self.assertEqual(self.dispatch.storage_reserved['github:11'], 0)
        self.assertEqual(self.a.get('/content', base_url=self.base).status_code, 200)
        # Storage permission does not reset or otherwise alter the AI ledger.
        self.assertEqual(self.budget.mock_calls, [unittest.mock.call.authorize_identity('github:11'),
                                                unittest.mock.call.authorize_identity('github:22')])

    def test_default_and_invalid_settings_remain_bounded(self):
        identity = 'github:11'
        self.assertEqual(self.dispatch._storage_limit(identity), DEFAULT_TENANT_STORAGE_BYTES)
        for data in ('not json', '[]', 'null', '{"x": 123}', ' ' * (64 * 1024 + 1)):
            with self.subTest(data=data[:20]):
                self.limits.write_text(data)
                self.assertEqual(self.dispatch._storage_limit(identity), DEFAULT_TENANT_STORAGE_BYTES)
        for invalid in (None, False, True, -1, 0, 'unlimited', '268435456', 1.5, {}, []):
            with self.subTest(invalid=invalid):
                self.limits.write_text(json.dumps({self.digest(identity): invalid}))
                self.assertEqual(self.dispatch._storage_limit(identity), DEFAULT_TENANT_STORAGE_BYTES)

    def test_request_and_tenant_files_cannot_set_operator_limits(self):
        self.login(self.a)
        self.use_storage('github:11', 105 * 1024 * 1024)
        tenant = self.root / 'tenants' / self.digest('github:11')
        (tenant / 'operator').mkdir()
        (tenant / 'operator' / 'storage-limits.json').write_text(json.dumps({self.digest('github:11'): 1024 ** 3}))
        response = self.a.post('/content?storage_limit=1073741824&identity=github:22',
            base_url=self.base, json={'storage_limit': 1024 ** 3, 'identity': 'github:22'},
            headers={'X-Storage-Limit': str(1024 ** 3), 'X-Tenant-ID': 'github:22'})
        self.assertEqual(response.status_code, 507)
        self.assertEqual(response.json['error']['code'], 'storage_limit')

    def test_override_keeps_upload_and_disk_limits(self):
        self.login(self.a)
        self.limits.write_text(json.dumps({self.digest('github:11'): 256 * 1024 * 1024}))
        with patch('hosted_trial.shutil.disk_usage') as disk:
            disk.return_value.free = 10
            self.assertEqual(self.post(self.a).status_code, 507)
        response = self.post(self.a, environ_overrides={'CONTENT_LENGTH': str(12 * 1024 * 1024 + 1)})
        self.assertEqual(response.status_code, 413)

    def test_maintenance_blocks_only_target_without_entering_cached_app(self):
        self.login(self.a)
        self.login(self.b, 'github:22')
        marker = self.marker()
        with patch.object(self.dispatch, '_application', wraps=self.dispatch._application) as application:
            page = self.a.get('/content', base_url=self.base)
            self.assertEqual(page.status_code, 503)
            self.assertIn('Your workspace is being updated', page.text)
            self.assertEqual(page.headers['Retry-After'], '60')
            self.assertEqual(page.headers['Cache-Control'], 'no-store')
            response = self.post(self.a, json={})
            self.assertEqual(response.json['error']['code'], 'workspace_maintenance')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers['Retry-After'], '60')
            application.assert_not_called()
        self.assertNotIn(str(self.root), page.text)
        self.assertNotIn(self.digest('github:11'), page.text)
        self.assertEqual(self.b.get('/content', base_url=self.base).text, 'saved content')
        anonymous = Client(self.dispatch, Response)
        self.assertEqual(anonymous.get('/content', base_url=self.base).text, 'public samples')
        marker.unlink()
        self.assertEqual(self.post(self.a).status_code, 200)

    def test_maintenance_allows_auth_without_seeding_or_authorizing_ai(self):
        self.marker()
        self.login(self.a)
        self.seed.assert_not_called()
        self.factory.assert_not_called()
        self.budget.authorize_identity.assert_not_called()
        self.assertFalse((self.root / 'tenants').exists())
        status = self.a.get('/trial/status', base_url=self.base)
        self.assertTrue(status.json['authenticated'])
        self.assertNotIn('storage', status.text)
        page = self.a.get('/trial/account', base_url=self.base)
        self.assertEqual(page.status_code, 200)
        csrf = re.search('name="csrf_token" value="([^"]+)"', page.text)[1]
        response = self.a.post('/trial/sign-out', base_url=self.base, data={'csrf_token': csrf})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.a.get('/trial/status', base_url=self.base).json['authenticated'])


if __name__ == '__main__':
    unittest.main()
