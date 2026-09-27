"""The curriculum stays an overview; earned milestones belong to learner profiles."""
import json
import sqlite3
import unittest
from unittest.mock import patch
from flask.testing import FlaskClient

from services.curriculum import band_summaries
from tests.support import isolated_app
from utils.shell import extract_main_content


class CurriculumOverviewIsolationTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, demo=False)
        self.client = self.app.test_client()
        self.state = self.client.get('/api/v1/course').json
        self.headers = {'X-CSRF-Token': self.state['csrf_token']}

    def assert_complete_overview(self, response, language='en'):
        self.assertEqual(response.status_code, 200)
        html = extract_main_content(response.text)
        self.assertEqual(html.count('class="curriculum-topic"'), 50)
        for band in band_summaries(language):
            self.assertIn(f'id="level-{band["id"]}"', html)
            for topic in band['topics']:
                self.assertEqual(html.count(f'id="topic-{topic["id"]}"'), 1)
        self.assertNotIn('curriculum-milestone', html)
        self.assertNotIn('/#journey/chapter/', html)
        self.assertNotIn('milestones complete', html)
        self.assertNotIn('data-profile-id=', html)
        for chapter in self.state['chapters']:
            title = chapter['title_ru' if language == 'ru' else 'title']
            if title:
                self.assertNotIn(title, html)
        return html

    def test_overview_does_not_depend_on_journey_catalogue_or_learner_progress(self):
        # A course release or progress failure must not break the public syllabus.
        with patch('services.course_progression.course_catalogue',
                   side_effect=AssertionError('Curriculum loaded the Journey catalogue')), \
             patch('utils.course_context.course_snapshot',
                   side_effect=AssertionError('Curriculum loaded learner course progress')):
            html = self.assert_complete_overview(self.client.get('/curriculum'))
            self.assertIn('/curriculum/topics/food', html)
            topic = self.client.get('/curriculum/topics/food')
            self.assertEqual(topic.status_code, 200)
            self.assertIn('/comprehension?topic=food&amp;level=A1', topic.text)
            visitor = FlaskClient(self.app)
            self.assertEqual(self.assert_complete_overview(visitor.get('/curriculum')), html)
        with visitor.session_transaction() as session:
            self.assertNotIn('personal_access_id', session)

    def test_overview_is_localized_without_journey_content(self):
        with self.client.session_transaction() as session:
            session['ui_lang'] = 'ru'
        html = self.assert_complete_overview(self.client.get('/curriculum'), language='ru')
        self.assertIn('Учебная программа', html)
        self.assertIn('Знакомство и приветствия', html)

    def test_checkpoint_progress_stays_in_profile_and_does_not_change_curriculum(self):
        before = self.assert_complete_overview(self.client.get('/curriculum'))
        first = self.state['chapters'][0]
        response = self.client.post(f'/api/v1/course/chapters/{first["id"]}/checkpoint',
                                    json={'request_id': 'curriculum-start', 'challenge': True,
                                          'release_id': self.state['release_id']}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        attempt = response.json
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            frozen = json.loads(conn.execute('SELECT frozen_json FROM course_checkpoint_attempts WHERE id=?',
                                            (attempt['id'],)).fetchone()[0])
        answers = {item['id']: item['answer'] for item in frozen['variant']['questions']}
        self.client.post(f'/api/v1/course/checkpoints/{attempt["id"]}/listened', json={}, headers=self.headers)
        checked = self.client.post(f'/api/v1/course/checkpoints/{attempt["id"]}/answer',
                                   json={'answers': answers, 'submission_id': 'curriculum-submit'}, headers=self.headers)
        self.assertEqual(checked.status_code, 200)
        self.assertTrue(checked.json['result']['passed'])
        state = self.client.get('/api/v1/course').json
        self.assertEqual(state['completed_milestones'], 1)
        html = self.assert_complete_overview(self.client.get('/curriculum'))
        self.assertEqual(html, before)
        self.assertIn('1 of 4 milestones complete', self.client.get('/post/profiles').text)
        self.assertNotIn(attempt['letter'], html)
        for table in ('progression_events', 'native_reviews'):
            with sqlite3.connect(self.app.config['DB_PATH']) as conn:
                exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if exists:
                    self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        created = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Another learner'},
                                   headers=self.headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.assert_complete_overview(self.client.get('/curriculum')), before)
        self.assertIn('0 of 4 milestones complete', self.client.get('/post/profiles').text)
        stale = self.client.get('/curriculum', headers={'X-Profile-ID': state['profile_id'], 'HX-Target': 'mainContent'})
        self.assertEqual(stale.status_code, 409)
        self.assertNotIn('milestones complete', stale.text)

    def test_null_release_is_not_an_implicit_legacy_start(self):
        response = self.client.post(f'/api/v1/course/chapters/{self.state["chapters"][0]["id"]}/checkpoint',
                                    json={'request_id': 'invalid-release', 'challenge': True, 'release_id': None},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
