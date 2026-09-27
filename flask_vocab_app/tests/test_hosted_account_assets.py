"""Account recovery must not depend on opening the learner's database."""
from hashlib import sha256
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from werkzeug.test import Client
from werkzeug.wrappers import Response

from hosted_account_page import ACCOUNT_PUBLIC_ASSETS, render_account_page
from hosted_trial import HostedTrialDispatcher


class AccountAssetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.public = Mock(side_effect=lambda env, respond: Response('public asset')(env, respond))
        self.dispatch = HostedTrialDispatcher(self.public, Mock(), root=root,
            ledger_path=root / 'budget.sqlite3', secret='synthetic-account-asset-test-' * 2,
            hostname='arcade.example', enabled=False, ai_enabled=False)
        account = {'identity': 'github:11', 'display_name': 'Sample', 'token_hash': 'synthetic-session'}
        session = patch.object(self.dispatch, '_session', return_value=account)
        session.start()
        self.addCleanup(session.stop)
        maintenance = root / 'operator' / 'maintenance'
        maintenance.mkdir(parents=True)
        (maintenance / sha256(account['identity'].encode()).hexdigest()).touch()
        self.client = Client(self.dispatch, Response)

    def test_public_account_assets_remain_readable_during_maintenance(self):
        with patch.object(self.dispatch, '_application') as application:
            for path in ACCOUNT_PUBLIC_ASSETS:
                for method in ('GET', 'HEAD'):
                    with self.subTest(path=path, method=method):
                        response = self.client.open(path, method=method, base_url='https://arcade.example')
                        self.assertEqual(response.status_code, 200)
            application.assert_not_called()

    def test_other_paths_methods_and_hosts_cannot_use_asset_bypass(self):
        paths = ('/static/media/private.mp3', '/static/uploads/lesson.png',
                 '/static/fonts/../media/private.mp3', '/static/css/account.css/private')
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, base_url='https://arcade.example').status_code, 503)
        self.assertEqual(self.client.post('/static/css/account.css', base_url='https://arcade.example').status_code, 503)
        self.assertEqual(self.client.get('/static/css/account.css', base_url='https://wrong.example').status_code, 400)
        self.public.assert_not_called()

    def test_allowlist_covers_rendered_images_stylesheet_and_its_fonts(self):
        root = Path(__file__).resolve().parents[1]
        html = render_account_page('Sign in', providers=[{'id': 'google'}, {'id': 'github'}])
        referenced = set(re.findall(r'(?:href|src)="(/static/[^"?]+)', html))
        referenced.update(re.findall(r'url\("([^\"]+)"\)', (root / 'static/css/account.css').read_text()))
        self.assertEqual(referenced, ACCOUNT_PUBLIC_ASSETS)
        for path in ACCOUNT_PUBLIC_ASSETS:
            self.assertTrue((root / path.lstrip('/')).is_file(), path)
