"""A shared recording must not disclose later answers or rewrite earlier support."""
from copy import deepcopy
import json
import unittest
from uuid import uuid4

from repositories.learning_repository import timestamp, transaction
from repositories.curriculum_sequence_repository import validate_saved_sequences
from services.activity_evidence import validate_saved_evidence
from services.learning_listening import validate_saved_support
from tests.support import isolated_app


class SharedListeningFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        session = self.client.get('/api/v1/user-session').json
        self.profile = session['profile']['id']
        self.headers = {'X-CSRF-Token': session['csrf_token']}

    def post(self, url, body, status=200):
        response = self.client.post(url, json=body, headers=self.headers)
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        return response.json

    def start(self):
        run = self.post('/api/v1/curriculum/units/location-destination-v2/runs', {
            'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1'})
        return self.open_step(run)

    def open_step(self, run, operation='start'):
        opened = self.post(f"/api/v1/curriculum/runs/{run['id']}/steps/listening/{operation}", {
            'submission_id': uuid4().hex, 'expected_revision': run['revision']})
        return opened['run'], self.read(opened['url'].rsplit('/', 1)[1])

    def read(self, sid):
        response = self.client.get('/api/v1/learning-sessions/' + sid)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json

    def pack(self, state):
        with transaction(self.db) as conn:
            row = conn.execute('SELECT payload FROM learning_content_versions WHERE id=?',
                               (state['version_id'],)).fetchone()
        return json.loads(row[0])

    def command(self, state, action, answer=None):
        body = {'submission_id': uuid4().hex, 'expected_revision': state['revision'],
                'item_id': state['item']['id']}
        if answer is not None:
            body['answer'] = answer
        return self.post('/api/v1/learning-sessions/' + state['id'] + '/' + action, body)

    def answer(self, state, correct=True):
        item = next(i for i in self.pack(state)['items'] if i['id'] == state['item']['id'])
        if not state['item']['listened'] and not state['item'].get('transcript'):
            state = self.command(state, 'listened')
        choice = item['answer'] if correct else next(c['id'] for c in item['choices'] if c['id'] != item['answer'])
        return self.command(state, 'attempts', {'choice_id': choice})

    def finish(self, state):
        while state['status'] == 'active':
            state = self.answer(state)
        return state

    def validate(self):
        with transaction(self.db) as conn:
            validate_saved_sequences(conn)
            validate_saved_support(conn)
            validate_saved_evidence(conn)

    def test_shared_message_hides_key_and_marks_until_last_question_then_restores_feedback(self):
        _, state = self.start()
        pack = self.pack(state)
        state = self.answer(state, correct=False)
        for count in (1, 2):
            self.assertEqual(state['completed_items'], count)
            self.assertNotIn(pack['items'][0]['transcript'], json.dumps(state, ensure_ascii=False))
            for attempt in state['attempts']:
                feedback = attempt['feedback']
                self.assertTrue(feedback['deferred'])
                self.assertEqual(feedback['outcome'], 'deferred')
                for secret in ('outcome',):
                    self.assertNotIn(secret, attempt)
                for secret in ('answer', 'explanation', 'transcript'):
                    self.assertNotIn(secret, feedback)
                item = next(i for i in pack['items'] if i['id'] == attempt['item_id'])
                submitted = next(c['text'] for c in item['choices'] if c['id'] == attempt['answer']['choice_id'])
                self.assertEqual(feedback['response_text'], submitted)
                self.assertFalse(feedback['assisted'])
            reloaded = self.read(state['id'])
            self.assertEqual(reloaded['attempts'], state['attempts'])
            state = self.answer(state)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual([a['outcome'] for a in state['attempts']], ['incorrect', 'correct', 'correct'])
        for attempt in state['attempts']:
            self.assertNotIn('deferred', attempt['feedback'])
            self.assertIn('answer', attempt['feedback'])
            self.assertIn('explanation', attempt['feedback'])
            self.assertEqual(attempt['feedback']['transcript'], pack['items'][0]['transcript'])
            self.assertEqual(attempt['feedback']['support'], [])
        self.validate()

    def test_explicit_transcript_applies_to_remaining_questions_only_when_they_become_current(self):
        _, state = self.start()
        items = self.pack(state)['items']
        state = self.command(state, 'transcript')
        for index in range(3):
            self.assertEqual(state['item']['transcript'], items[0]['transcript'])
            self.assertFalse(state['item']['listened'])
            with transaction(self.db) as conn:
                receipts = conn.execute('SELECT item_id FROM learning_item_support WHERE session_id=? '
                                        'AND transcript_at IS NOT NULL', (state['id'],)).fetchall()
                self.assertEqual({r[0] for r in receipts}, {i['id'] for i in items[:index + 1]})
                before = conn.execute('SELECT * FROM learning_item_support WHERE session_id=?', (state['id'],)).fetchall()
            self.assertEqual(self.read(state['id'])['item']['transcript'], items[0]['transcript'])
            with transaction(self.db) as conn:
                self.assertEqual(conn.execute('SELECT * FROM learning_item_support WHERE session_id=?',
                                              (state['id'],)).fetchall(), before)
            state = self.answer(state)
            self.assertTrue(state['feedback']['assisted'])
            self.assertEqual(state['feedback']['support'], ['transcript'])
        self.validate()

    def test_later_transcript_does_not_change_earlier_unaided_answer_or_report(self):
        _, state = self.start()
        state = self.answer(state)
        first = state['attempts'][0]
        with transaction(self.db) as conn:
            report = tuple(conn.execute('SELECT * FROM activity_criterion_reports WHERE source_key=?',
                                        (first['id'],)).fetchone())
        state = self.command(state, 'transcript')
        state = self.finish(state)
        self.assertEqual([a['feedback']['assisted'] for a in state['attempts']], [False, True, True])
        self.assertEqual(state['attempts'][0]['feedback']['support'], [])
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute('SELECT * FROM activity_criterion_reports WHERE source_key=?',
                                               (first['id'],)).fetchone()), report)
            self.assertIsNone(conn.execute('SELECT transcript_at FROM learning_item_support WHERE session_id=? AND item_id=?',
                                          (state['id'], first['item_id'])).fetchone()[0])
        self.validate()

    def test_unfinished_feedback_is_hidden_from_profile_and_not_counted_as_retry_assistance(self):
        run, original = self.start()
        original = self.answer(original)
        run, retry = self.open_step(run, 'retry')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_prior_feedback WHERE session_id=?',
                                          (retry['id'],)).fetchone()[0], 0)
        retry = self.answer(retry)
        self.assertFalse(retry['feedback']['assisted'])
        response = self.client.get('/api/v1/curriculum/summary')
        self.assertEqual(response.status_code, 200)
        listening = next(d for d in response.json['domains'] if d['id'] == 'listening')
        self.assertIsNone(listening['latest'])
        self.assertEqual(listening['scopes'], [])
        self.assertEqual(listening['next_action']['kind'], 'resume')
        self.assertEqual(listening['next_action']['url'], '/#practice/' + retry['id'])
        first_id = retry['attempts'][0]['id']
        with transaction(self.db) as conn:
            first_report = tuple(conn.execute('SELECT * FROM activity_criterion_reports WHERE source_key=?',
                                             (first_id,)).fetchone())
        # Another tab now completes the old set: only later answers can use its feedback.
        original = self.finish(original)
        retry = self.answer(retry)
        self.assertTrue(retry['feedback']['assisted'])
        self.assertIn('model_answer', retry['feedback']['support'])
        self.assertFalse(retry['attempts'][0]['feedback']['assisted'])
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute('SELECT * FROM activity_criterion_reports WHERE source_key=?',
                                               (first_id,)).fetchone()), first_report)
        retry = self.finish(retry)
        self.validate()

    def test_explicit_transcript_in_other_tab_is_disclosed_even_when_feedback_is_deferred(self):
        run, original = self.start()
        original = self.answer(original)
        original = self.command(original, 'transcript')
        _, retry = self.open_step(run, 'retry')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_prior_feedback WHERE session_id=?',
                                          (retry['id'],)).fetchone()[0], 1)
        retry = self.answer(retry)
        self.assertTrue(retry['feedback']['assisted'])
        self.assertIn('model_answer', retry['feedback']['support'])
        self.validate()

    def test_other_tab_transcript_before_any_answer_is_carried_forward_without_exposing_other_profiles(self):
        run, original = self.start()
        original = self.command(original, 'transcript')
        _, retry = self.open_step(run, 'retry')
        self.assertEqual(retry['item']['transcript'], original['item']['transcript'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_prior_feedback').fetchone()[0], 0)
        retry = self.answer(retry)
        self.assertEqual(retry['feedback']['support'], ['transcript'])
        self.assertTrue(retry['feedback']['assisted'])
        with transaction(self.db) as conn:
            # Only answered Q1 and now-current Q2 receive immutable support.
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_item_support WHERE session_id=? '
                                          'AND transcript_at IS NOT NULL', (retry['id'],)).fetchone()[0], 2)
        other = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Other listener'},
                                 headers=self.headers)
        self.assertEqual(other.status_code, 201, other.get_data(as_text=True))
        self.headers = {'X-CSRF-Token': other.json['csrf_token']}
        _, private = self.start()
        self.assertFalse(private['item'].get('transcript'))
        private = self.answer(private)
        self.assertFalse(private['feedback']['assisted'])
        self.validate()

    def test_shared_support_requires_same_frozen_version_not_only_same_audio(self):
        run, original = self.start()
        original = self.command(original, 'transcript')
        pack = self.pack(original)
        pack['id'] = 'a-different-frozen-task'
        pack['items'][0]['prompt'] = 'Послушайте новую задачу.'
        version = self.app.extensions['learning']['content'].import_draft(pack)
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE learning_content_versions SET status='published',approved_by='Test fixture',"
                         'approved_at=? WHERE id=?', (timestamp(), version))
        state = self.post('/api/v1/learning-sessions', {'profile_id': self.profile,
            'version_id': version, 'submission_id': uuid4().hex}, status=201)
        self.assertFalse(state['item'].get('transcript'))
        state = self.answer(state)
        self.assertFalse(state['feedback']['assisted'])
        self.validate()

    def test_legacy_shared_audio_defers_but_single_question_reveals_completion_transcript(self):
        _, source = self.start()
        source_pack = self.pack(source)
        for size in (2, 1):
            with self.subTest(items=size):
                pack = deepcopy(source_pack)
                pack['id'] = 'shared-listening-fixture-' + str(size)
                pack['items'] = pack['items'][:size]
                version = self.app.extensions['learning']['content'].import_draft(pack)
                # Only this isolated fixture is approved; no production content is published here.
                with transaction(self.db, write=True) as conn:
                    conn.execute("UPDATE learning_content_versions SET status='published',approved_by='Test fixture',"
                                 'approved_at=? WHERE id=?', (timestamp(), version))
                state = self.post('/api/v1/learning-sessions', {'profile_id': self.profile,
                    'version_id': version, 'submission_id': uuid4().hex}, status=201)
                state = self.answer(state)
                if size == 2:
                    self.assertTrue(state['feedback']['deferred'])
                    self.assertNotIn('transcript', state['feedback'])
                    state = self.answer(state)
                self.assertEqual(state['status'], 'completed')
                self.assertEqual(state['feedback']['transcript'], pack['items'][0]['transcript'])
                self.assertNotIn('deferred', state['feedback'])
        self.validate()


if __name__ == '__main__':
    unittest.main()
