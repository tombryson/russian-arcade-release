"""Listening media follows the owned task and never changes answer evidence."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from repositories.learning_repository import transaction
from services.learning_listening import STATIC_ROOT
from tests.support import isolated_app


class CurriculumListeningAudioAccessTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        self.run = self.post('/api/v1/curriculum/units/location-destination-v2/runs', {
            'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1',
            'completion_path': 'guided'})

    def post(self, url, body):
        response = self.client.post(url, json=body, headers={'X-CSRF-Token': self.token})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json

    def start(self, step='listening'):
        opened = self.post('/api/v1/curriculum/runs/' + self.run['id'] + '/steps/' + step + '/start', {
            'submission_id': uuid4().hex, 'expected_revision': self.run['revision']})
        self.run = opened['run']
        identity = opened['url'].rsplit('/', 1)[1]
        response = self.client.get('/api/v1/learning-sessions/' + identity)
        self.assertEqual(response.status_code, 200)
        state = response.json
        with transaction(self.db) as conn:
            pack = json.loads(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?',
                                          (state['version_id'],)).fetchone()[0])
        return state, pack['items']

    @staticmethod
    def audio_url(state, item_id):
        return '/api/v1/learning-sessions/' + state['id'] + '/items/' + item_id + '/audio'

    def command(self, state, operation, **fields):
        return self.post('/api/v1/learning-sessions/' + state['id'] + '/' + operation, {
            'submission_id': uuid4().hex, 'expected_revision': state['revision'],
            'item_id': state['item']['id'], **fields})

    def assert_unchanged(self, state):
        current = self.client.get('/api/v1/learning-sessions/' + state['id'])
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json, state)

    def test_current_clip_uses_owned_url_and_supports_seeking_without_marking_listened(self):
        state, items = self.start()
        item = items[0]
        url = self.audio_url(state, item['id'])
        self.assertEqual(state['item']['audio']['url'], url)
        original = (STATIC_ROOT / item['audio']['url'].removeprefix('/static/')).read_bytes()
        with self.client.get(url) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'audio/mpeg')
            self.assertEqual(response.data, original)
            self.assertEqual(hashlib.sha256(response.data).hexdigest(), item['audio']['sha256'])
            self.assertNotIn('public', response.headers.get('Cache-Control', ''))
        with self.client.get(url, headers={'Range': 'bytes=0-511'}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, original[:512])
            self.assertEqual(response.headers['Content-Range'], f'bytes 0-511/{len(original)}')
        self.assert_unchanged(state)
        with transaction(self.db) as conn:
            for table in ('learning_item_support', 'learning_commands', 'activity_attempts',
                          'activity_criterion_reports', 'progression_events'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0, table)
        denied = self.client.post('/api/v1/learning-sessions/' + state['id'] + '/attempts', json={
            'submission_id': uuid4().hex, 'expected_revision': state['revision'],
            'item_id': item['id'], 'answer': {'choice_id': item['answer']}},
            headers={'X-CSRF-Token': self.token})
        self.assertEqual(denied.status_code, 409)

    def test_current_and_previous_clips_remain_available_after_advancing_and_completion(self):
        state, items = self.start()
        for item in items:
            self.assertEqual(state['item']['id'], item['id'])
            self.assertEqual(state['item']['audio']['url'], self.audio_url(state, item['id']))
            state = self.command(state, 'listened')
            state = self.command(state, 'attempts', answer={'choice_id': item['answer']})
            with self.client.get(self.audio_url(state, item['id'])) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(hashlib.sha256(response.data).hexdigest(), item['audio']['sha256'])
        self.assertIsNone(state['item'])
        # Completed-task projection omits the transient POST feedback/coin fields.
        state = self.client.get('/api/v1/learning-sessions/' + state['id']).json
        for item in items:
            with self.client.get(self.audio_url(state, item['id'])) as response:
                self.assertEqual(response.status_code, 200)
        self.assert_unchanged(state)

    def test_future_unknown_and_non_listening_items_cannot_be_fetched(self):
        state, items = self.start()
        for item_id in (items[1]['id'], 'unknown-item'):
            with self.subTest(item=item_id), self.client.get(self.audio_url(state, item_id)) as response:
                self.assertIn(response.status_code, (404, 409))
                self.assertNotEqual(response.mimetype, 'audio/mpeg')
        self.assert_unchanged(state)
        choices, _ = self.start('choices')
        with self.client.get(self.audio_url(choices, choices['item']['id'])) as response:
            self.assertIn(response.status_code, (404, 409))
        self.assert_unchanged(choices)

    def test_other_profile_and_unknown_session_cannot_read_a_clip(self):
        state, items = self.start()
        changed = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Other listener'},
                                   headers={'X-CSRF-Token': self.token})
        self.assertEqual(changed.status_code, 201)
        for url in (self.audio_url(state, items[0]['id']),
                    self.audio_url({'id': 'missing-session'}, items[0]['id'])):
            with self.subTest(url=url), self.client.get(url) as response:
                self.assertEqual(response.status_code, 404)
                self.assertNotEqual(response.mimetype, 'audio/mpeg')

    def test_missing_and_changed_clip_are_denied_without_mutating_saved_task(self):
        state, items = self.start()
        target = (STATIC_ROOT / items[0]['audio']['url'].removeprefix('/static/')).resolve()
        original = target.read_bytes()
        read_bytes, is_file = Path.read_bytes, Path.is_file

        def changed(path):
            if path.resolve() == target:
                return bytes([original[0] ^ 1]) + original[1:]
            return read_bytes(path)

        def missing(path):
            return False if path.resolve() == target else is_file(path)

        for attribute, replacement in (('read_bytes', changed), ('is_file', missing)):
            with self.subTest(failure=attribute), patch.object(Path, attribute, replacement):
                with self.client.get(self.audio_url(state, items[0]['id'])) as response:
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json['error']['code'], 'audio_unavailable')
            self.assert_unchanged(state)
        self.assertEqual(target.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
