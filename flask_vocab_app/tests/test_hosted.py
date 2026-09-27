import base64
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.test import Client
from werkzeug.wrappers import Response

from hosted import PrivateSite, settings


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / 'vocab.db'
        with sqlite3.connect(self.database) as conn:
            conn.execute('CREATE TABLE schema_migrations (version INTEGER)')
        self.forwarded = []

        def application(environ, start_response):
            self.forwarded.append(environ.get('HTTP_AUTHORIZATION'))
            return Response('private')(environ, start_response)

        self.client = Client(PrivateSite(application, 'arcade', 'test-password',
                                        self.database, 'russian-arcade.fly.dev'), Response)
        self.base = 'https://russian-arcade.fly.dev'

    def test_every_content_route_requires_credentials(self):
        for path in ('/', '/post', '/post/', '/tools/anki/', '/api/v1/user-session', '/static/uploads/lesson.pdf',
                     '/static/media/audio.mp3', '/post/assets/app.js'):
            for method in ('GET', 'POST'):
                response = self.client.open(path, method=method, base_url=self.base)
                self.assertEqual(response.status_code, 401)
                self.assertIn('Basic', response.headers['WWW-Authenticate'])
        self.assertEqual(self.forwarded, [])

    def test_valid_credentials_are_removed_before_application(self):
        token = base64.b64encode(b'arcade:test-password').decode()
        response = self.client.get('/post/', base_url=self.base,
                                   headers={'Authorization': 'Basic ' + token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.forwarded, [None])

    def test_bad_credentials_and_unknown_hosts_are_denied(self):
        for authorization in ('Basic invalid', 'Bearer token', 'Basic ' + base64.b64encode(b'arcade:wrong').decode()):
            self.assertEqual(self.client.get('/post/', base_url=self.base,
                headers={'Authorization': authorization}).status_code, 401)
        self.assertEqual(self.client.get('/healthz', base_url='https://attacker.example').status_code, 400)

    def test_health_checks_database_without_opening_access(self):
        response = self.client.get('/healthz', base_url=self.base)
        self.assertEqual(response.status_code, 200)
        self.database.unlink()
        self.assertEqual(self.client.get('/healthz', base_url=self.base).status_code, 503)
        self.assertFalse(self.database.exists())
        self.assertEqual(self.client.post('/healthz', base_url=self.base).status_code, 401)

    def test_hsts_covers_https_pages_errors_and_health_only(self):
        for path in ('/post/', '/healthz'):
            response = self.client.get(path, base_url=self.base)
            self.assertEqual(response.headers['Strict-Transport-Security'], 'max-age=31536000')
        token = base64.b64encode(b'arcade:test-password').decode()
        response = self.client.get('/post/', base_url=self.base, headers={'Authorization': 'Basic ' + token})
        self.assertEqual(response.headers['Strict-Transport-Security'], 'max-age=31536000')
        self.assertNotIn('Strict-Transport-Security', self.client.get('/healthz', base_url='http://russian-arcade.fly.dev').headers)

    def test_startup_refuses_missing_secrets_and_missing_database(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                settings()
        values = {'FLASK_SECRET_KEY': 's' * 32, 'HOSTED_ACCESS_USERNAME': 'arcade',
                  'HOSTED_ACCESS_PASSWORD': 'p' * 32, 'HOSTED_HOSTNAME': 'russian-arcade.fly.dev',
                  'VOCAB_DB_PATH': str(self.database)}
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(settings()['VOCAB_DB_PATH'], str(self.database))
            self.database.unlink()
            with self.assertRaises(RuntimeError):
                settings()


if __name__ == '__main__':
    unittest.main()
