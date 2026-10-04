"""Packaged alphabet playback stays public; learner recordings stay private."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hosted_demo_mount import packaged_asset
from services.alphabet_audio import is_public_alphabet_recording, public_recordings
from tests.support import isolated_app, select_test_profile


class AlphabetAccessTests(unittest.TestCase):
    def test_only_the_66_published_recordings_are_public(self):
        paths = public_recordings()
        self.assertEqual(len(paths), 66)
        for path in paths:
            self.assertTrue(is_public_alphabet_recording(path.removeprefix('/static/')))
        for filename in ('audio/alphabet-v1/unknown-name.mp3', 'audio/alphabet-v1/manifest.json',
                         'audio/alphabet-v1/a-name.wav', 'audio/alphabet-v1/../private.mp3',
                         'audio/alphabet-v1/../../media/recording.mp3',
                         'media/alphabet-v1/a-name.mp3', 'uploads/recording.mp3'):
            self.assertFalse(is_public_alphabet_recording(filename), filename)

    def test_household_guard_allows_packaged_audio_but_not_unlisted_files(self):
        app = isolated_app(self, signed_in=False)
        app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='test-alphabet-household-secret-' * 2)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        app.static_folder = directory.name
        audio = Path(directory.name) / 'audio' / 'alphabet-v1'
        audio.mkdir(parents=True)
        content = b'ID3' + b'synthetic-test-recording' * 50
        (audio / 'a-name.mp3').write_bytes(content)
        (audio / 'private-note.mp3').write_bytes(b'private recording')
        client = app.test_client()
        with client.get('/static/audio/alphabet-v1/a-name.mp3', headers={'Range': 'bytes=0-31'}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, content[:32])
            self.assertEqual(response.mimetype, 'audio/mpeg')
        with client.get('/static/audio/alphabet-v1/private-note.mp3') as response:
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, '/post/household')
            self.assertNotIn(b'private recording', response.data)
        with sqlite3.connect(app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM household_access').fetchone()[0], 0)
        app.config['WORD_POST_HOUSEHOLD_ENABLED'] = False
        select_test_profile(client)
        with client.get('/static/audio/alphabet-v1/a-name.mp3') as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, content)


class HostedAlphabetPlaybackTests(unittest.TestCase):
    def setUp(self):
        from tests import test_hosted_guest_demo
        test_hosted_guest_demo.HostedGuestCompositionTests.setUp(self)

    def test_all_recordings_support_public_and_demo_playback_without_provisioning(self):
        from hosted import create_hosted_app
        app = create_hosted_app()
        client = app.test_client()
        for path in sorted(public_recordings()):
            self.assertTrue(packaged_asset(path), path)
            for prefix in ('', '/demo'):
                with self.subTest(path=prefix + path):
                    with client.get(prefix + path, base_url=self.base, headers={'Range': 'bytes=0-127'}) as response:
                        self.assertEqual(response.status_code, 206)
                        self.assertEqual(response.mimetype, 'audio/mpeg')
                        self.assertEqual(len(response.data), 128)
                        self.assertTrue(response.headers['Content-Range'].startswith('bytes 0-127/'))
        dispatch = app.extensions['hosted_trial']
        self.assertFalse(dispatch.cache)
        with sqlite3.connect(dispatch.registry) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM guest_sessions').fetchone()[0], 0)
        for path in ('/static/media/alphabet-recording.mp3', '/static/uploads/alphabet-recording.mp3',
                     '/static/audio/alphabet-v1/../../media/alphabet-recording.mp3'):
            self.assertFalse(packaged_asset(path), path)
