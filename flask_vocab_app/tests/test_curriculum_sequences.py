"""Owned sequence boundaries, frozen work and recoverable practice drafts."""
import json
import sqlite3
import unittest

from tests.support import isolated_app


class CurriculumSequenceTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']

    def post(self, url, body):
        return self.client.post(url, json=body, headers={'X-CSRF-Token': self.token})

    def start(self, key='start', path='guided'):
        response = self.post('/api/v1/curriculum/units/location-destination-v2/runs',
                             {'submission_id': key, 'sequence_id': 'location-destination-sequence-v1', 'completion_path': path})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json

    def step(self, run, step='choices', operation='start', key='open'):
        result = self.post('/api/v1/curriculum/runs/' + run['id'] + '/steps/' + step + '/' + operation,
                           {'submission_id': key, 'expected_revision': run['revision']})
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        return result.json

    def test_read_is_side_effect_free_and_tasks_stay_private(self):
        page = self.client.get('/curriculum/units/location-destination-v2')
        self.assertEqual(page.status_code, 200)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_runs').fetchone()[0], 0)
        run = self.start()
        read = self.client.get('/api/v1/curriculum/runs/' + run['id'])
        self.assertEqual(read.json, run)
        self.assertNotIn('assets', read.json)
        self.assertNotIn('manifest', read.json)
        self.assertNotIn('answer', json.dumps(read.json))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_sessions').fetchone()[0], 0)

    def test_start_and_allocation_replay_and_stale_revision(self):
        run = self.start()
        self.assertEqual(run, self.start())
        self.assertEqual(run['id'], self.start('resume')['id'])
        opened = self.step(run)
        self.assertEqual(opened, self.step(run))
        failed = self.post('/api/v1/curriculum/runs/' + run['id'] + '/steps/forms/start',
                           {'submission_id': 'stale', 'expected_revision': run['revision']})
        self.assertEqual(failed.status_code, 409)
        self.assertEqual(failed.json['error']['code'], 'stale_revision')
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_sessions').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_task_contracts').fetchone()[0], 4)
        conflict = self.post('/api/v1/curriculum/units/location-destination-v2/runs',
                             {'submission_id': 'start', 'sequence_id': 'location-destination-sequence-v1', 'completion_path': 'challenge'})
        self.assertEqual(conflict.status_code, 409)

    def test_drafts_are_owned_revisioned_and_not_answers(self):
        opened = self.step(self.start(), 'forms')
        sid = opened['url'].rsplit('/', 1)[1]
        saved = self.client.get('/api/v1/learning-sessions/' + sid).json
        data = {'submission_id': 'draft', 'item_id': saved['item']['id'], 'expected_revision': saved['revision'],
                'expected_draft_revision': 0, 'response': {'text': 'в школ'}}
        url = '/api/v1/learning-sessions/' + sid + '/draft'
        response = self.post(url, data)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.json, self.post(url, data).json)
        self.assertEqual(self.post(url, {**data, 'submission_id': 'other-tab', 'response': {'text': 'в парке'}}).status_code, 409)
        restored = self.client.get('/api/v1/learning-sessions/' + sid).json
        self.assertEqual(restored['draft']['response']['text'], 'в школ')
        self.assertEqual(restored['revision'], saved['revision'])
        self.assertEqual(restored['attempts'], [])
        self.assertEqual(restored['sequence']['run_id'], opened['run']['id'])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)

    def test_russian_display_keeps_hints_private_and_feedback_durable(self):
        from services.curriculum_sequence_content import load_asset
        asset = load_asset('location-choices-v2')
        first = asset['content']['items'][0]
        with self.client.session_transaction() as session:
            session['ui_lang'] = 'ru'
        opened = self.step(self.start())
        sid = opened['url'].rsplit('/', 1)[1]
        url = '/api/v1/learning-sessions/' + sid
        state = self.client.get(url).json
        self.assertEqual(state['title'], asset['title_ru'])
        self.assertNotIn('hint', state['item'])
        self.assertNotIn('explanation', state['item'])
        shown = self.post(url + '/help', {
            'submission_id': 'show-hint', 'expected_revision': state['revision'],
            'item_id': state['item']['id']})
        self.assertEqual(shown.status_code, 200, shown.get_data(as_text=True))
        state = shown.json
        self.assertEqual(state['item']['hint'], first['hint_ru'])
        answered = self.post(url + '/attempts', {
            'submission_id': 'answer-ru', 'expected_revision': state['revision'],
            'item_id': state['item']['id'], 'answer': {'choice_id': first['answer']}})
        self.assertEqual(answered.status_code, 200, answered.get_data(as_text=True))
        self.assertEqual(answered.json['feedback']['explanation'], first['explanation_ru'])
        self.assertTrue(answered.json['feedback']['assisted'])
        self.assertNotIn('hint', answered.json['item'])
        with sqlite3.connect(self.db) as conn:
            report = json.loads(conn.execute('SELECT report_json FROM activity_criterion_reports').fetchone()[0])
        self.assertEqual(report['judgements'][0]['feedback'], first['explanation_ru'])
        with self.client.session_transaction() as session:
            session['ui_lang'] = 'en'
        restored = self.client.get(url).json
        self.assertEqual(restored['title'], asset['title'])
        self.assertEqual(restored['attempts'][0]['feedback']['explanation'], first['explanation'])

    def test_answer_records_scoped_evidence_and_retries_share_reward_family(self):
        opened = self.step(self.start())
        def complete(url):
            sid = url.rsplit('/', 1)[1]
            state = self.client.get('/api/v1/learning-sessions/' + sid).json
            while state['item']:
                response = self.post('/api/v1/learning-sessions/' + sid + '/attempts',
                    {'submission_id': 'answer-' + str(state['revision']), 'expected_revision': state['revision'],
                     'item_id': state['item']['id'], 'answer': {'choice_id': state['item']['choices'][0]['id']}})
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                state = response.json
            return state
        first = complete(opened['url'])
        self.assertEqual(first['coins_earned'], 3)
        run = self.client.get('/api/v1/curriculum/runs/' + opened['run']['id']).json
        self.assertEqual(next(s for s in run['steps'] if s['id'] == 'choices')['work_state'], 'reviewed')
        again = self.step(run, operation='retry', key='retry')
        repeated = complete(again['url'])
        self.assertEqual(repeated['coins_earned'], 0)
        self.assertTrue(all(a['feedback']['assisted'] for a in repeated['attempts']))
        self.assertTrue(all(a['feedback']['explanation'] for a in repeated['attempts']))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 8)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
        summary = self.client.get('/api/v1/curriculum/summary').json
        language = next(d for d in summary['domains'] if d['id'] == 'language_use')
        self.assertEqual(language['latest']['condition'], 'assisted')
        self.assertIn('model_answer', language['latest']['support'])
        self.assertEqual(language['next_action']['kind'], 'focused_practice')
        self.assertEqual(language['next_action']['step_id'], 'choices')
        draft = self.step(again['run'], 'forms', key='open-forms-draft')
        summary = self.client.get('/api/v1/curriculum/summary').json
        language = next(d for d in summary['domains'] if d['id'] == 'language_use')
        self.assertEqual(language['next_action']['kind'], 'resume')
        self.assertEqual(language['next_action']['url'], draft['url'])

    def test_missing_audio_never_allocates_or_scores(self):
        from unittest.mock import patch
        from repositories.learning_repository import LearningError
        with patch('services.learning_listening.verify_audio', side_effect=LearningError('audio_unavailable', 'Unavailable.', 409)):
            run = self.start()
            result = self.post('/api/v1/curriculum/runs/' + run['id'] + '/steps/listening/start',
                               {'submission_id': 'listen', 'expected_revision': run['revision']})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json['error']['code'], 'audio_unavailable')
        self.assertFalse(self.client.get('/api/v1/curriculum/runs/' + run['id']).json['completed'])

    def test_profile_isolation_and_csrf(self):
        run = self.start()
        other = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Other'}, headers={'X-CSRF-Token': self.token})
        self.assertEqual(other.status_code, 201)
        self.token = other.json['csrf_token']
        self.assertEqual(self.client.get('/api/v1/curriculum/runs/' + run['id']).status_code, 404)
        self.assertEqual(self.post('/api/v1/curriculum/runs/' + run['id'] + '/steps/choices/start',
                                  {'submission_id': 'cross-profile', 'expected_revision': 0}).status_code, 404)
        response = self.client.post('/api/v1/curriculum/units/location-destination-v2/runs', json={'submission_id': 'no-csrf', 'sequence_id': 'location-destination-sequence-v1'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/v1/curriculum/runs/nonexistent').status_code, 404)
