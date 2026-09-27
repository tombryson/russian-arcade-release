from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from repositories.learning_repository import encoded, transaction
from services.first_delivery import GUEST_ATTEMPT_KEY, QUESTIONS
from services.first_steps import CHAPTER_ID, LESSON_IDS, chapter_content, completed_lessons
from services.progression import award, snapshot
from tests.support import isolated_app, select_test_profile


class FirstStepsTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, signed_in=False)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.content = chapter_content()

    def token(self, client=None):
        return (client or self.client).get('/api/v1/onboarding').json['csrf_token']

    def request(self, path, data=None, *, client=None, status=200):
        client = client or self.client
        response = client.post(path, json=data or {}, headers={'X-CSRF-Token': self.token(client)})
        self.assertEqual(response.status_code, status, response.text)
        return response.json

    def post(self, lesson, operation, data=None, *, client=None, status=200):
        return self.request(f'/api/v1/first-steps/{lesson}/{operation}', data, client=client, status=status)

    def chapter(self, client=None):
        response = (client or self.client).get('/api/v1/first-steps')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def read(self, lesson, client=None):
        response = (client or self.client).get('/api/v1/first-steps/' + lesson)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def hello(self, *, profile=True, client=None):
        client = client or self.client
        if profile:
            select_test_profile(client)
        for milestone in ('coins', 'progress'):
            self.request('/api/v1/onboarding', {'milestone': milestone}, client=client)
        prefix = '/api/v1/onboarding/practice/'
        self.request(prefix + 'start', client=client)
        for question in QUESTIONS:
            self.request(prefix + 'learn', {'question_id': question['id']}, client=client)
        for question in QUESTIONS:
            self.request(prefix + 'answer', {'question_id': question['id'], 'answer': question['answer']}, client=client)
            self.request(prefix + 'continue', {'question_id': question['id']}, client=client)
        return self.request(prefix + 'complete', client=client)

    def definition(self, lesson_id):
        return next(lesson for lesson in self.content['lessons'] if lesson['id'] == lesson_id)

    def prepare(self, lesson, *, client=None):
        self.post(lesson, 'start', client=client)
        for card in self.definition(lesson)['teaching']:
            self.post(lesson, 'learn', {'teaching_id': card['id']}, client=client)

    def finish(self, lesson, *, client=None, hints=(), wrong=(), complete=True):
        self.prepare(lesson, client=client)
        for question in self.definition(lesson)['questions']:
            qid = question['id']
            if qid in hints:
                self.post(lesson, 'hint', {'question_id': qid}, client=client)
            answer = next(choice['id'] for choice in question['choices'] if choice['id'] != question['answer']) if qid in wrong else question['answer']
            self.post(lesson, 'answer', {'question_id': qid, 'answer': answer}, client=client)
            self.post(lesson, 'continue', {'question_id': qid}, client=client)
        return self.post(lesson, 'complete', client=client) if complete else self.read(lesson, client)

    def balance(self, profile_id='personal-learning'):
        with transaction(self.db) as conn:
            return snapshot(conn, profile_id)

    def counts(self):
        with transaction(self.db) as conn:
            return tuple(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                         for table in ('first_steps_attempts', 'progression_events', 'progression_entries', 'journey_answers'))

    def create_profile(self, name='New learner', *, client=None):
        return self.request('/api/v1/user-session/profiles', {'display_name': name}, client=client, status=201)['profile']['id']

    def test_chapter_is_optional_read_only_and_requires_real_v2_first_lesson_completion(self):
        before = self.counts()
        chapter = self.chapter()
        self.assertEqual(chapter['chapter_id'], CHAPTER_ID)
        self.assertEqual([lesson['id'] for lesson in chapter['lessons']], list(LESSON_IDS))
        self.assertEqual([lesson['status'] for lesson in chapter['lessons']], ['available', 'locked', 'locked', 'locked', 'locked'])
        self.assertEqual(chapter['next_lesson']['href'], '#first-delivery')
        self.assertEqual(chapter['completed_count'], 0)
        self.assertFalse(chapter['complete'])
        self.post('bag', 'start', status=409)
        self.assertEqual(self.client.get('/api/v1/first-steps/bag').status_code, 409)
        self.assertEqual(self.counts(), before)
        self.hello()
        chapter = self.chapter()
        self.assertEqual(chapter['completed_count'], 1)
        self.assertEqual(chapter['next_lesson']['id'], 'bag')
        self.assertIsNone(self.read('bag')['attempt'])
        self.assertEqual(self.client.get('/api/v1/progression').status_code, 200)
        # A saved old dialogue is preserved, but is not a completion of the
        # revised three-word lesson used as this chapter's first step.
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE first_delivery_attempts SET version='first-delivery-v1' WHERE profile_id='personal-learning'")
        self.assertEqual(self.chapter()['completed_count'], 0)
        self.post('bag', 'start', status=409)

    def test_teaching_first_and_feedback_acknowledgement_are_saved_before_reward(self):
        self.hello()
        baseline = self.balance()
        started = self.post('bag', 'start')
        self.assertEqual(started['attempt']['phase'], 'learn')
        self.assertIsNone(started['attempt']['question'])
        self.assertEqual(started['teaching_cards'], [])
        self.assertEqual(started['lesson']['position'], 2)
        self.assertEqual(self.chapter()['lessons'][1]['status'], 'active')
        self.post('bag', 'answer', {'question_id': 'bag-name-letter', 'answer': 'letter'}, status=409)
        self.post('bag', 'learn', {'teaching_id': 'bag-map'}, status=409)
        for index, card in enumerate(self.definition('bag')['teaching']):
            current = self.read('bag')
            self.assertEqual(current['attempt']['teaching_index'], index)
            self.assertEqual(current['attempt']['teaching'], card)
            state = self.post('bag', 'learn', {'teaching_id': card['id']})
            self.assertEqual(self.post('bag', 'learn', {'teaching_id': card['id']})['attempt'], state['attempt'])
        self.assertEqual(state['attempt']['phase'], 'question')
        self.assertIsNone(state['attempt']['teaching'])
        self.assertNotIn('answer', state['attempt']['question'])
        self.assertNotIn('hint', state['attempt']['question'])
        for question in self.definition('bag')['questions']:
            feedback = self.post('bag', 'answer', {'question_id': question['id'], 'answer': question['answer']})
            self.assertEqual(feedback['attempt']['phase'], 'feedback')
            self.assertEqual(self.read('bag')['attempt'], feedback['attempt'])
            self.post('bag', 'complete', status=409)
            self.post('bag', 'continue', {'question_id': question['id']})
        self.assertEqual(self.balance(), baseline)
        complete = self.post('bag', 'complete')
        self.assertEqual(complete['attempt']['phase'], 'completed')
        self.assertEqual(complete['reward'], {'amount': 3, 'status': 'credited', 'awarded_now': True})
        self.assertEqual(complete['teaching_cards'], self.definition('bag')['teaching'])
        self.assertEqual(complete['resolution'], self.definition('bag')['resolution'])
        self.assertEqual(complete['next_lesson']['id'], 'directions')
        self.assertEqual(complete['progression']['balance'], baseline['balance'] + 3)
        self.assertEqual(complete['progression']['skill']['skills'][0]['observations'], 2)

    def test_frozen_content_survives_author_edits_without_changing_first_answers(self):
        self.hello()
        first = self.post('bag', 'start')
        changed = deepcopy(self.content)
        changed['version'] = 'future-version'
        changed['lessons'][0]['title'] = 'Changed title'
        changed['lessons'][0]['teaching'][0]['word'] = 'Changed word'
        changed['lessons'][0]['questions'][0]['answer'] = 'map'
        changed['lessons'][0]['questions'][0]['feedback'] = 'Changed feedback'
        with patch('services.first_steps.chapter_content', return_value=changed):
            self.assertEqual(self.read('bag')['attempt'], first['attempt'])
            self.assertEqual(self.post('bag', 'start')['lesson']['title'], self.definition('bag')['title'])
            completed = self.finish('bag')
            self.assertTrue(completed['attempt']['answers'][0]['correct'])
            self.assertEqual(completed['attempt']['answers'][0]['feedback'], self.definition('bag')['questions'][0]['feedback'])
            with transaction(self.db) as conn:
                owned = completed_lessons(conn, 'personal-learning')
                self.assertEqual(owned[1]['title'], self.definition('bag')['title'])
                self.assertEqual(owned[1]['version'], self.content['version'])

    def test_first_answers_are_immutable_and_hints_exclude_only_assisted_questions(self):
        self.hello()
        self.prepare('bag')
        self.post('bag', 'hint', {'question_id': 'bag-name-letter'})
        self.assertIn('hint', self.read('bag')['attempt']['question'])
        self.post('bag', 'answer', {'question_id': 'bag-name-letter', 'answer': 'letter'})
        self.post('bag', 'answer', {'question_id': 'bag-name-letter', 'answer': 'map'}, status=409)
        self.post('bag', 'hint', {'question_id': 'bag-name-letter'})
        self.post('bag', 'continue', {'question_id': 'bag-name-letter'})
        self.post('bag', 'answer', {'question_id': 'bag-name-bag', 'answer': 'map'})
        self.post('bag', 'continue', {'question_id': 'bag-name-bag'})
        self.post('bag', 'answer', {'question_id': 'bag-name-map', 'answer': 'map'})
        self.post('bag', 'continue', {'question_id': 'bag-name-map'})
        finished = self.post('bag', 'complete')
        with transaction(self.db) as conn:
            receipt = json.loads(conn.execute("SELECT evidence_json FROM progression_events WHERE activity='first_steps'").fetchone()[0])
        self.assertEqual(receipt['_skill']['scores'], {'reading': .5})
        self.assertEqual(receipt['unassisted_count'], 2)
        self.assertEqual(finished['progression']['skill']['skills'][0]['observations'], 2)
        self.assertTrue(all(item['rating'] is None for item in finished['progression']['skill']['skills'][1:]))
        before = self.balance()
        hinted_questions = [question['id'] for question in self.definition('directions')['questions']]
        all_hinted = self.finish('directions', hints=hinted_questions)
        self.assertEqual(all_hinted['progression']['balance'], before['balance'] + 3)
        self.assertEqual(all_hinted['progression']['skill'], before['skill'])

    def test_completed_replay_is_read_only_and_cannot_earn_again_on_a_new_day(self):
        self.hello()
        finished = self.finish('bag')
        before, counts = self.balance(), self.counts()
        with patch('services.first_steps.timestamp', return_value=2_000_000_000):
            for operation, body in (('start', {}), ('complete', {}), ('answer', {'question_id': 'bag-name-letter', 'answer': 'map'}), ('learn', {'teaching_id': 'bag-letter'})):
                result = self.post('bag', operation, body)
                self.assertEqual(result['attempt'], finished['attempt'])
                self.assertFalse(result['reward']['awarded_now'])
        self.assertEqual(self.balance(), before)
        self.assertEqual(self.counts(), counts)

    def test_normal_daily_cap_can_award_zero_without_erasing_reading_evidence(self):
        self.hello()
        with transaction(self.db, write=True) as conn:
            for index in range(4):
                award(conn, 'personal-learning', activity='journey', content_key=f'cap-{index}', source_key=f'cap-{index}', title='Earlier practice')
        baseline = self.balance()
        result = self.finish('bag')
        self.assertEqual(result['reward'], {'amount': 0, 'status': 'credited', 'awarded_now': False})
        self.assertEqual(result['progression']['balance'], baseline['balance'])
        self.assertEqual(result['progression']['skill']['skills'][0]['observations'], 2)
        self.assertEqual(self.post('bag', 'complete')['reward']['amount'], 0)

    def test_final_lesson_establishes_post_office_checkpoint_and_unlocks_market_without_fabricated_answers(self):
        self.hello()
        with transaction(self.db) as conn:
            before_answers = [tuple(row) for row in conn.execute('SELECT * FROM journey_answers')]
        for lesson in LESSON_IDS[1:]:
            result = self.finish(lesson)
        chapter = self.chapter()
        self.assertTrue(chapter['complete'])
        self.assertEqual(chapter['completed_count'], 5)
        self.assertIsNone(chapter['next_lesson'])
        self.assertTrue(result['chapter_complete'])
        worlds = {world['id']: world for world in result['progression']['journey']['worlds']}
        self.assertTrue(worlds['post-office']['completed'])
        self.assertTrue(worlds['market-town']['unlocked'])
        self.assertFalse(worlds['market-town']['completed'])
        with transaction(self.db) as conn:
            self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM journey_answers')], before_answers)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='first_steps'").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='first_delivery'").fetchone()[0], 1)

    def test_final_lesson_preserves_existing_checkpoint_history(self):
        self.hello()
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE journey_progress SET unlocked_at=10,visited_at=20,completed_at=30 WHERE profile_id='personal-learning' AND world_id='post-office'")
        for lesson in LESSON_IDS[1:]:
            self.finish(lesson)
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute("SELECT unlocked_at,visited_at,completed_at FROM journey_progress WHERE profile_id='personal-learning' AND world_id='post-office'").fetchone()), (10, 20, 30))

    def test_guest_chapter_progress_claims_only_into_new_profile_and_transfers_partial_teaching(self):
        self.hello(profile=False)
        self.finish('bag')
        self.finish('directions')
        self.post('help', 'start')
        partial = self.post('help', 'learn', {'teaching_id': self.definition('help')['teaching'][0]['id']})
        self.assertEqual(self.chapter()['pending_reward'], 9)
        self.assertNotIn('progression', self.read('bag'))
        self.assertEqual(self.read('bag')['reward']['status'], 'pending')
        before = self.counts()
        with self.client.session_transaction() as saved:
            token = saved[GUEST_ATTEMPT_KEY]
        profile = self.create_profile()
        self.assertEqual(self.chapter()['pending_reward'], 0)
        self.assertEqual(self.balance(profile)['balance'], 9)
        self.assertEqual(self.read('help')['attempt'], partial['attempt'])
        self.assertEqual(self.read('bag')['reward'], {'amount': 3, 'status': 'credited', 'awarded_now': False})
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_steps_attempts WHERE guest_token=?', (token,)).fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_steps_attempts WHERE profile_id=?', (profile,)).fetchone()[0], 3)
        self.assertEqual(self.counts()[0], before[0])
        self.finish('help')
        final = self.finish('set-off')
        self.assertEqual(final['progression']['balance'], 15)
        self.assertEqual(final['progression']['skill']['skills'][0]['observations'], 5)

    def test_guest_full_chapter_claim_is_atomic_with_checkpoint_and_never_claims_on_select(self):
        self.hello(profile=False)
        for lesson in LESSON_IDS[1:]:
            self.finish(lesson)
        self.assertEqual(self.chapter()['pending_reward'], 15)
        before = self.counts()
        with patch('services.first_steps._credit', side_effect=RuntimeError('save failure')):
            with self.assertRaises(RuntimeError):
                self.create_profile()
        self.assertEqual(self.chapter()['pending_reward'], 15)
        self.assertEqual(self.counts(), before)
        profile = self.create_profile()
        self.assertEqual(self.balance(profile)['balance'], 15)
        self.assertTrue(self.chapter()['complete'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journey_progress WHERE profile_id=? AND world_id='post-office' AND completed_at IS NOT NULL", (profile,)).fetchone()[0], 1)
        other = self.app.test_client()
        self.hello(profile=False, client=other)
        self.finish('bag', client=other)
        before_select = self.balance()
        select_test_profile(other)
        self.assertEqual(self.chapter(other)['completed_count'], 0)
        self.assertEqual(self.balance(), before_select)

    def test_owner_isolation_csrf_and_stale_profile_binding_cover_public_reads_and_writes(self):
        self.hello()
        self.post('bag', 'start')
        self.post('bag', 'learn', {'teaching_id': 'bag-letter'})
        old_token = self.token()
        self.create_profile('Another')
        self.assertEqual(self.chapter()['completed_count'], 0)
        self.assertEqual(self.client.get('/api/v1/first-steps', headers={'X-Profile-ID': 'personal-learning'}).status_code, 409)
        self.assertEqual(self.client.get('/api/v1/first-steps/bag', headers={'X-Profile-ID': 'personal-learning'}).status_code, 409)
        self.assertEqual(self.client.post('/api/v1/first-steps/bag/start', json={}, headers={'X-CSRF-Token': old_token}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/first-steps/bag/start', json={}, headers={'X-CSRF-Token': self.token(), 'X-Profile-ID': 'personal-learning'}).status_code, 409)
        guest = self.app.test_client()
        self.assertEqual(self.chapter(guest)['completed_count'], 0)
        select_test_profile(self.client)
        self.assertEqual(self.read('bag')['attempt']['teaching_index'], 1)
        self.request('/api/v1/user-session/logout')
        self.assertEqual(self.chapter()['completed_count'], 0)

    def test_payload_cannot_invent_ownership_content_scores_rewards_or_skip_lessons(self):
        self.hello()
        for extra in ({'profile_id': 'other'}, {'guest_token': 'fake'}, {'content': {}}, {'score': 1}, {'amount': 99}):
            self.post('bag', 'start', extra, status=400)
        self.post('directions', 'start', status=409)
        self.post('unknown', 'start', status=404)
        self.post('bag', 'unknown', status=404)
        self.post('bag', 'start')
        self.post('bag', 'learn', {'teaching_id': []}, status=400)
        self.assertEqual(self.client.post('/api/v1/first-steps/bag/complete', json={}).status_code, 403)
        self.prepare('bag')
        for answer in ('unknown', None, 1, [], {}):
            self.post('bag', 'answer', {'question_id': 'bag-name-letter', 'answer': answer}, status=400)

    def test_concurrent_start_and_completion_keep_one_attempt_and_one_award(self):
        self.hello()
        clients = [self.app.test_client(), self.app.test_client()]
        tokens = [select_test_profile(client)['csrf_token'] for client in clients]
        def command(operation):
            def send(pair):
                client, token = pair
                return client.post(f'/api/v1/first-steps/bag/{operation}', json={}, headers={'X-CSRF-Token': token})
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(send, zip(clients, tokens)))
            self.assertEqual([response.status_code for response in responses], [200, 200])
            return responses
        starts = command('start')
        self.assertEqual(starts[0].json['attempt']['id'], starts[1].json['attempt']['id'])
        self.finish('bag', complete=False)
        completions = command('complete')
        self.assertEqual(sum(response.json['reward']['awarded_now'] for response in completions), 1)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_steps_attempts').fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='first_steps'").fetchone()[0], 1)

    def test_completion_rolls_back_answers_phase_and_rewards_when_award_fails(self):
        self.hello()
        self.finish('bag', complete=False)
        before = self.counts()
        with patch('services.first_steps.award', side_effect=RuntimeError('save failure')):
            with self.assertRaises(RuntimeError):
                self.post('bag', 'complete')
        self.assertEqual(self.read('bag')['attempt']['phase'], 'ready')
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.post('bag', 'complete')['reward']['amount'], 3)

    def test_selected_household_profile_can_follow_chapter_without_claiming_guest_history(self):
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='test-household-secret-at-least-32-characters')
        self.app.extensions['learning']['household'].configure('Home', '246810')
        self.request('/api/v1/household/unlock', {'pin': '246810'})
        profile = self.request('/api/v1/grownups/profiles', {'display_name': 'Learner', 'study_timezone': 'UTC'}, status=201)['id']
        self.request(f'/api/v1/grownups/profiles/{profile}/select')
        self.hello(profile=False)
        completed = self.finish('bag')
        self.assertEqual(completed['profile_id'], profile)
        self.assertEqual(completed['progression']['balance'], 6)
        self.assertEqual(self.chapter()['completed_count'], 2)
        self.request('/api/v1/household/lock')
        self.assertEqual(self.chapter()['completed_count'], 0)
        self.assertEqual(self.chapter()['pending_reward'], 0)

    def test_completed_lesson_bridge_is_read_only_owned_and_returns_frozen_vocabulary(self):
        self.hello()
        self.finish('bag')
        self.post('directions', 'start')
        before = self.counts()
        with transaction(self.db) as conn:
            completed = completed_lessons(conn, 'personal-learning')
            self.assertEqual([lesson['id'] for lesson in completed], ['hello', 'bag'])
            self.assertTrue(all(lesson['vocabulary'] for lesson in completed))
            self.assertEqual(completed_lessons(conn, 'unrelated-profile'), [])
            self.assertEqual(completed_lessons(conn, None, 'unrelated-guest'), [])
        self.assertEqual(self.counts(), before)


if __name__ == '__main__':
    unittest.main()
