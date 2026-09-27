from concurrent.futures import ThreadPoolExecutor
import json
import unittest
from unittest.mock import patch

from repositories.learning_repository import encoded, transaction
from services.first_delivery import GUEST_ATTEMPT_KEY, QUESTIONS, V1_QUESTIONS, VERSION, claim_guest_practice
from services.progression import WELCOME_POLICY, award, award_first_delivery, reverse, snapshot
from tests.support import isolated_app, select_test_profile


class FirstDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, signed_in=False)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']

    def token(self, client=None):
        return (client or self.client).get('/api/v1/onboarding').json['csrf_token']

    def post(self, operation, data=None, client=None, status=200):
        client = client or self.client
        response = client.post('/api/v1/onboarding/practice/' + operation, json=data or {},
                               headers={'X-CSRF-Token': self.token(client)})
        self.assertEqual(response.status_code, status, response.text)
        return response.json

    def read(self, client=None):
        response = (client or self.client).get('/api/v1/onboarding/practice')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def introduce(self, client=None):
        client = client or self.client
        for milestone in ('coins', 'progress'):
            response = client.post('/api/v1/onboarding', json={'milestone': milestone},
                                   headers={'X-CSRF-Token': self.token(client)})
            self.assertEqual(response.status_code, 200, response.text)

    def prepare(self, *, profile=True):
        if profile:
            select_test_profile(self.client)
        self.introduce()
        self.post('start')
        return self.learn_all()

    def learn_all(self, client=None):
        state = self.read(client)
        while state['attempt']['phase'] == 'learn':
            state = self.post('learn', {'question_id': state['attempt']['question']['id']}, client)
        return state

    def answer_all(self, *, hints=(), wrong=(), client=None):
        self.learn_all(client)
        for question in QUESTIONS:
            qid = question['id']
            if qid in hints:
                self.post('hint', {'question_id': qid}, client)
            answer = next(choice['id'] for choice in question['choices'] if choice['id'] != question['answer']) if qid in wrong else question['answer']
            self.post('answer', {'question_id': qid, 'answer': answer}, client)
            self.post('continue', {'question_id': qid}, client)

    def profile_create(self, name='River', client=None):
        client = client or self.client
        response = client.post('/api/v1/user-session/profiles', json={'display_name': name},
                               headers={'X-CSRF-Token': self.token(client)})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json['profile']['id']

    def balances(self, profile='personal-learning'):
        with transaction(self.db) as conn:
            return snapshot(conn, profile)

    def counts(self):
        with transaction(self.db) as conn:
            return tuple(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                         for table in ('first_delivery_attempts', 'progression_events', 'progression_entries'))

    def test_reads_and_intro_alone_never_create_an_attempt_or_reward(self):
        original = self.counts()
        state = self.read()
        self.assertIsNone(state['attempt'])
        self.assertIsNone(state['profile_id'])
        self.assertEqual(state['pending_reward'], 0)
        self.assertEqual(state['teaching_cards'], [])
        self.post('start', status=409)
        self.introduce()
        self.assertIsNone(self.read()['attempt'])
        self.assertEqual(self.counts(), original)
        with self.client.session_transaction() as saved:
            self.assertNotIn(GUEST_ATTEMPT_KEY, saved)

    def test_teaches_all_three_words_before_russian_only_recall_and_persists_each_phase(self):
        select_test_profile(self.client)
        self.introduce()
        before = self.counts()
        state = self.post('start')
        self.assertEqual(state['attempt']['version'], VERSION)
        self.post('learn', {'question_id': 'word-letter'}, status=409)
        for index, question in enumerate(QUESTIONS):
            self.assertEqual(state['attempt']['phase'], 'learn')
            self.assertEqual(state['attempt']['question_index'], index)
            self.assertEqual(state['attempt']['learned_count'], index)
            self.assertEqual(state['attempt']['question']['lesson'], question['lesson'])
            self.assertEqual(state['attempt']['question']['title'], question['title'])
            self.assertEqual(state['attempt']['question']['choices'], [])
            self.assertEqual(self.read()['attempt'], state['attempt'])
            self.post('answer', {'question_id': 'word-hello', 'answer': 'hello'}, status=409)
            self.post('hint', {'question_id': 'word-hello'}, status=409)
            state = self.post('learn', {'question_id': question['id']})
            self.assertEqual(self.post('learn', {'question_id': question['id']})['attempt'], state['attempt'])
        self.assertEqual(state['attempt']['phase'], 'question')
        self.assertEqual(state['attempt']['question_index'], 0)
        self.assertEqual(state['attempt']['learned_count'], 3)
        self.assertEqual(state['teaching_cards'], [])
        self.assertEqual(self.counts()[1:], before[1:])
        for question, expected_position in zip(QUESTIONS, (1, 0, 2)):
            current = state['attempt']['question']
            self.assertEqual(current['id'], question['id'])
            self.assertNotIn('lesson', current)
            self.assertEqual({choice['text'] for choice in current['choices']}, {'Привет!', 'письмо', 'Спасибо!'})
            self.assertEqual(current['choices'][expected_position]['id'], question['answer'])
            state = self.post('answer', {'question_id': question['id'], 'answer': question['answer']})
            self.assertEqual(state['attempt']['phase'], 'feedback')
            self.assertNotIn('lesson', state['attempt']['question'])
            state = self.post('continue', {'question_id': question['id']})
        self.assertEqual(state['attempt']['phase'], 'ready')
        self.assertEqual(self.counts()[1:], before[1:])

    def legacy_attempt(self, *, profile=True, completed=False, wrong=False):
        if profile:
            select_test_profile(self.client)
        self.introduce()
        started = self.post('start')
        questions = V1_QUESTIONS if completed else V1_QUESTIONS[:1]
        answers = {question['id']: {'answer': next(choice['id'] for choice in question['choices'] if choice['id'] != question['answer']) if wrong else question['answer'],
                                    'correct': not wrong, 'hint_used': False, 'answered_at': 100 + index}
                   for index, question in enumerate(questions)}
        acknowledged = [question['id'] for question in questions] if completed else []
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE first_delivery_attempts SET version=?,answers_json=?,hints_json=?,learned_json=?,acknowledged_json=?,completed_at=?,created_at=?,updated_at=? WHERE id=?',
                         ('first-delivery-v1', encoded(answers), '[]', '[]', encoded(acknowledged), 110 if completed else None, 90, 110,
                          started['attempt']['id']))
            if profile and completed:
                award_first_delivery(conn, 'personal-learning', started['attempt']['id'], answers, now=110)
            return dict(conn.execute('SELECT * FROM first_delivery_attempts WHERE id=?', (started['attempt']['id'],)).fetchone())

    def test_legacy_reads_keep_exact_original_english_answers_until_explicit_restart(self):
        original = self.legacy_attempt()
        before = self.counts()
        legacy = self.read()
        self.assertEqual(legacy['attempt']['version'], 'first-delivery-v1')
        self.assertEqual(legacy['attempt']['answers'][0]['answer_text'], 'Saying hello')
        self.assertEqual(legacy['attempt']['answers'][0]['correct_answer'], 'Saying hello')
        self.assertEqual(self.post('start')['attempt'], legacy['attempt'])
        with transaction(self.db) as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM first_delivery_attempts').fetchone()), original)
        updated = self.post('start', {'restart': True})
        self.assertEqual(updated['attempt']['phase'], 'learn')
        self.assertEqual(updated['attempt']['version'], VERSION)
        self.assertEqual(updated['attempt']['answers'], [])
        self.assertEqual(updated['previous_attempt'], legacy['attempt'])
        self.assertNotIn('profile_id', updated['previous_attempt'])
        self.assertNotIn('guest_token', updated['previous_attempt'])
        with transaction(self.db) as conn:
            row = conn.execute('SELECT * FROM first_delivery_attempts').fetchone()
            self.assertEqual(json.loads(row['previous_attempt_json']), original)
            self.assertEqual(row['answers_json'], '{}')
        self.assertEqual(self.counts(), before)
        # An old tab cannot submit its English answer into the new vocabulary.
        self.post('answer', {'question_id': 'greeting', 'answer': 'greeting'}, status=400)

    def test_restarted_credited_legacy_completion_preserves_its_original_reward_and_rating(self):
        self.legacy_attempt(completed=True, wrong=True)
        before = self.balances()
        counts = self.counts()
        self.assertEqual(before['skill']['skills'][0]['rating'], 988)
        self.post('start', {'restart': True})
        self.answer_all()
        finished = self.post('complete')
        self.assertFalse(finished['reward']['awarded_now'])
        self.assertEqual(finished['progression'], before)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(finished['previous_attempt']['version'], 'first-delivery-v1')

    def test_completed_legacy_guest_keeps_pending_reward_and_original_evidence_through_restart_and_claim(self):
        original = self.legacy_attempt(profile=False, completed=True, wrong=True)
        restarted = self.post('start', {'restart': True})
        self.assertEqual(restarted['pending_reward'], 3)
        self.assertEqual(restarted['reward']['status'], 'pending')
        self.assertNotIn(original['guest_token'], encoded(restarted))
        profile = self.profile_create()
        claimed = self.read()
        self.assertEqual(claimed['attempt']['phase'], 'learn')
        self.assertEqual(claimed['progression']['balance'], 3)
        self.assertEqual(claimed['progression']['skill']['skills'][0]['rating'], 988)
        self.answer_all()
        finished = self.post('complete')
        self.assertFalse(finished['reward']['awarded_now'])
        self.assertEqual(finished['progression']['balance'], 3)
        self.assertEqual(finished['progression']['skill']['skills'][0]['rating'], 988)
        with transaction(self.db) as conn:
            events = conn.execute('SELECT content_key FROM progression_events WHERE profile_id=?', (profile,)).fetchall()
            self.assertEqual([row[0] for row in events], ['first-delivery-v1'])

    def test_unfinished_legacy_guest_can_finish_new_lesson_and_claim_its_new_evidence(self):
        self.legacy_attempt(profile=False)
        self.post('start', {'restart': True})
        self.answer_all()
        self.post('complete')
        profile = self.profile_create()
        result = self.read()
        self.assertEqual(result['progression']['balance'], 3)
        self.assertEqual(result['progression']['skill']['skills'][0]['rating'], 1012)
        with transaction(self.db) as conn:
            events = conn.execute('SELECT content_key FROM progression_events WHERE profile_id=?', (profile,)).fetchall()
            self.assertEqual([row[0] for row in events], [VERSION])

    def test_restart_only_upgrades_old_version_and_cannot_reset_new_answers_or_teaching(self):
        self.prepare()
        saved = self.post('answer', {'question_id': 'word-hello', 'answer': 'hello'})
        self.assertEqual(self.post('start', {'restart': True})['attempt'], saved['attempt'])
        self.assertIsNone(self.read()['previous_attempt'])
        for value in (None, 1, 'true', {}, []):
            self.post('start', {'restart': value}, status=400)

    def test_questions_are_server_authored_and_feedback_is_frozen_until_acknowledged(self):
        initial = self.prepare()
        question = initial['attempt']['question']
        self.assertEqual(question['id'], 'word-hello')
        self.assertNotIn('answer', question)
        self.assertNotIn('feedback', question)
        self.assertNotIn('hint', question)
        self.post('answer', {'question_id': 'word-letter', 'answer': 'letter'}, status=409)
        self.post('continue', {'question_id': 'word-hello'}, status=409)
        feedback = self.post('answer', {'question_id': 'word-hello', 'answer': 'thanks'})
        self.assertEqual(feedback['attempt']['phase'], 'feedback')
        self.assertEqual(feedback['attempt']['question']['id'], 'word-hello')
        self.assertFalse(feedback['attempt']['answers'][0]['correct'])
        self.assertEqual(feedback['attempt']['answers'][0]['correct_answer'], 'Привет!')
        self.assertFalse(feedback['attempt']['answers'][0]['hint_used'])
        self.assertEqual(self.read()['attempt'], feedback['attempt'])
        self.assertEqual(self.post('answer', {'question_id': 'word-hello', 'answer': 'thanks'})['attempt'], feedback['attempt'])
        self.post('answer', {'question_id': 'word-hello', 'answer': 'hello'}, status=409)
        self.post('hint', {'question_id': 'word-hello'}, status=409)
        next_question = self.post('continue', {'question_id': 'word-hello'})
        self.assertEqual(next_question['attempt']['question']['id'], 'word-letter')
        self.assertTrue(next_question['attempt']['answers'][0]['acknowledged'])
        self.assertEqual(self.post('continue', {'question_id': 'word-hello'})['attempt'], next_question['attempt'])
        self.assertEqual(self.post('start')['attempt'], next_question['attempt'])

    def test_completion_requires_every_answer_and_its_feedback_acknowledgement(self):
        self.prepare()
        before = self.counts()
        self.post('complete', status=409)
        for question in QUESTIONS:
            self.post('answer', {'question_id': question['id'], 'answer': question['answer']})
            self.post('complete', status=409)
            self.post('continue', {'question_id': question['id']})
        self.assertEqual(self.read()['attempt']['phase'], 'ready')
        self.assertEqual(self.counts(), before)
        completed = self.post('complete')
        self.assertEqual(completed['attempt']['phase'], 'completed')
        self.assertEqual(completed['reward'], {'amount': 3, 'status': 'credited', 'awarded_now': True})
        self.assertEqual(completed['pending_reward'], 0)
        self.assertEqual(completed['teaching_cards'], [{'id': question['id'], 'title': question['title'], **question['lesson']} for question in QUESTIONS])
        reading = completed['progression']['skill']['skills'][0]
        self.assertEqual((reading['rating'], reading['observations']), (1012, 1))
        self.assertEqual(reading['progress'], .06)
        self.assertTrue(all(skill['rating'] is None for skill in completed['progression']['skill']['skills'][1:]))
        after = self.counts()
        for result in (self.read(), self.post('start'), self.post('complete'), self.post('complete')):
            self.assertFalse(result['reward']['awarded_now'])
            self.assertEqual(result['progression'], completed['progression'])
        self.assertEqual(self.counts(), after)

    def test_completion_and_guest_claim_roll_back_if_the_reward_cannot_be_saved(self):
        self.prepare()
        self.answer_all()
        before = self.counts()
        with patch('services.first_delivery.award_first_delivery', side_effect=RuntimeError('storage test')):
            with self.assertRaises(RuntimeError):
                self.post('complete')
        self.assertEqual(self.read()['attempt']['phase'], 'ready')
        self.assertEqual(self.counts(), before)
        self.post('complete')
        guest = self.app.test_client()
        self.introduce(guest)
        self.post('start', client=guest)
        self.answer_all(client=guest)
        self.post('complete', client=guest)
        with transaction(self.db) as conn:
            profiles_before = conn.execute('SELECT COUNT(*) FROM learning_profiles').fetchone()[0]
        with patch('services.first_delivery.award_first_delivery', side_effect=RuntimeError('storage test')):
            with self.assertRaises(RuntimeError):
                self.profile_create(client=guest)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_profiles').fetchone()[0], profiles_before)
        self.assertEqual(self.read(guest)['pending_reward'], 3)
        self.profile_create(client=guest)
        self.assertEqual(self.read(guest)['progression']['balance'], 3)

    def test_hints_are_persistent_and_only_unassisted_first_answers_count(self):
        self.prepare()
        hinted = self.post('hint', {'question_id': 'word-hello'})
        self.assertIn('hint', hinted['attempt']['question'])
        self.assertEqual(self.read()['attempt'], hinted['attempt'])
        self.assertEqual(self.post('hint', {'question_id': 'word-hello'})['attempt'], hinted['attempt'])
        self.answer_all(wrong=('word-letter',))
        result = self.post('complete')
        reading = result['progression']['skill']['skills'][0]
        # One unhinted wrong + one unhinted correct gives a single 0.5 observation.
        self.assertEqual((reading['rating'], reading['observations']), (1000, 1))
        self.assertTrue(result['attempt']['answers'][0]['hint_used'])
        with transaction(self.db) as conn:
            evidence = json.loads(conn.execute("SELECT evidence_json FROM progression_events WHERE activity='first_delivery'").fetchone()[0])
        self.assertEqual(evidence['unassisted_count'], 2)
        self.assertEqual(evidence['_skill']['scores'], {'reading': .5})

    def test_all_hinted_still_earns_coins_without_inventing_a_skill_rating(self):
        self.prepare()
        before = self.balances()
        self.answer_all(hints=tuple(q['id'] for q in QUESTIONS))
        result = self.post('complete')
        self.assertEqual(result['progression']['balance'], before['balance'] + 3)
        self.assertEqual(result['progression']['earned_total'], before['earned_total'] + 3)
        self.assertTrue(all(skill['rating'] is None and skill['observations'] == 0
                            for skill in result['progression']['skill']['skills']))

    def test_incorrect_unassisted_answers_do_not_force_progress_up(self):
        self.prepare()
        self.answer_all(wrong=tuple(q['id'] for q in QUESTIONS))
        result = self.post('complete')
        self.assertEqual(result['reward']['amount'], 3)
        self.assertEqual(result['progression']['skill']['skills'][0]['rating'], 988)
        self.assertEqual(result['progression']['skill']['skills'][0]['progress'], 0)

    def test_welcome_reward_is_guaranteed_after_daily_cap_and_does_not_consume_it(self):
        self.prepare()
        with transaction(self.db, write=True) as conn:
            for index in range(4):
                self.assertEqual(award(conn, 'personal-learning', activity='journey', content_key=f'cap-{index}',
                                       source_key=f'cap-{index}', title='Practice'), 3)
        before = self.balances()
        self.answer_all()
        result = self.post('complete')
        self.assertEqual(result['progression']['balance'], before['balance'] + 3)
        self.assertEqual(result['progression']['earned_total'], before['earned_total'] + 3)
        with transaction(self.db, write=True) as conn:
            self.assertEqual(award(conn, 'personal-learning', activity='journey', content_key='extra', source_key='extra', title='Practice'), 0)
            entry = conn.execute('SELECT amount,eligible,policy_version FROM progression_entries WHERE policy_version=?', (WELCOME_POLICY,)).fetchone()
            self.assertEqual(tuple(entry), (3, 1, WELCOME_POLICY))
        second = self.profile_create()
        self.introduce()
        self.post('start')
        self.answer_all(hints=tuple(q['id'] for q in QUESTIONS))
        self.post('complete')
        with transaction(self.db, write=True) as conn:
            amounts = [award(conn, second, activity='journey', content_key=f'second-{index}', source_key=f'second-{index}', title='Practice')
                       for index in range(5)]
        self.assertEqual(amounts, [3, 3, 3, 3, 0])

    def test_guest_completion_is_pending_until_claimed_only_by_a_new_profile(self):
        self.prepare(profile=False)
        before = self.counts()
        self.answer_all()
        guest = self.post('complete')
        self.assertIsNone(guest['profile_id'])
        self.assertNotIn('progression', guest)
        self.assertEqual(guest['pending_reward'], 3)
        self.assertEqual(guest['reward'], {'amount': 3, 'status': 'pending', 'awarded_now': False})
        self.assertEqual(self.counts(), before)
        with self.client.session_transaction() as saved:
            guest_token = saved[GUEST_ATTEMPT_KEY]
        profile = self.profile_create()
        claimed = self.read()
        self.assertEqual(claimed['profile_id'], profile)
        self.assertEqual(claimed['attempt']['id'], guest['attempt']['id'])
        self.assertEqual(claimed['reward'], {'amount': 3, 'status': 'credited', 'awarded_now': False})
        self.assertEqual(claimed['progression']['balance'], 3)
        self.assertEqual(claimed['progression']['skill']['skills'][0]['rating'], 1012)
        with self.client.session_transaction() as saved:
            self.assertNotIn(GUEST_ATTEMPT_KEY, saved)
        with transaction(self.db, write=True) as conn:
            claim_guest_practice(conn, profile, guest_token)
        self.assertEqual(self.balances(profile)['balance'], 3)
        another = self.profile_create('Another')
        self.assertIsNone(self.read()['attempt'])
        self.assertEqual(self.balances(another)['balance'], 0)

    def test_guest_incomplete_attempt_transfers_and_resumes_without_early_award(self):
        self.prepare(profile=False)
        feedback = self.post('answer', {'question_id': 'word-hello', 'answer': 'hello'})
        profile = self.profile_create()
        resumed = self.read()
        self.assertEqual(resumed['attempt'], feedback['attempt'])
        self.assertIsNone(resumed['reward'])
        self.assertEqual(self.balances(profile)['balance'], 0)
        self.answer_all()
        self.assertEqual(self.post('complete')['progression']['balance'], 3)

    def test_select_existing_profile_and_logout_never_claim_guest_activity(self):
        self.prepare(profile=False)
        self.answer_all()
        self.post('complete')
        before = self.balances()
        select_test_profile(self.client)
        self.assertIsNone(self.read()['attempt'])
        self.assertEqual(self.balances(), before)
        response = self.client.post('/api/v1/user-session/logout', json={}, headers={'X-CSRF-Token': self.token()})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.read()['attempt'])
        self.assertEqual(self.read()['pending_reward'], 0)

    def test_profiles_guests_and_stale_tabs_cannot_read_or_write_each_others_attempts(self):
        original = self.prepare()
        self.post('answer', {'question_id': 'word-hello', 'answer': 'hello'})
        other = self.app.test_client()
        self.assertIsNone(self.read(other)['attempt'])
        old_token = self.token()
        other_id = self.profile_create('Other')
        self.assertIsNone(self.read()['attempt'])
        self.assertEqual(self.client.get('/api/v1/onboarding/practice', headers={'X-Profile-ID': 'personal-learning'}).status_code, 409)
        self.assertEqual(self.client.get('/api/v1/onboarding/practice', headers={'X-Profile-ID': ''}).status_code, 409)
        self.assertEqual(self.client.post('/api/v1/onboarding/practice/start', json={}, headers={'X-CSRF-Token': old_token}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/onboarding/practice/start', json={},
                                         headers={'X-CSRF-Token': self.token(), 'X-Profile-ID': 'personal-learning'}).status_code, 409)
        self.assertEqual(self.read()['profile_id'], other_id)
        select_test_profile(self.client)
        self.assertEqual(self.read()['attempt']['id'], original['attempt']['id'])
        self.assertEqual(self.read()['attempt']['phase'], 'feedback')

    def test_payloads_cannot_supply_ownership_awards_scores_or_invalid_answers(self):
        self.prepare()
        for body in ({'profile_id': 'personal-learning'}, {'guest_token': 'fake'}, {'amount': 30}, {'score': 1}):
            self.post('start', body, status=400)
        self.assertEqual(self.client.post('/api/v1/onboarding/practice/answer', json={'question_id': 'word-hello', 'answer': 'hello'}).status_code, 403)
        for value in ('unknown', None, [], 1):
            self.post('answer', {'question_id': 'word-hello', 'answer': value}, status=400)
        self.post('answer', {'question_id': [], 'answer': 'hello'}, status=400)
        self.post('complete', {'amount': 3}, status=400)
        self.post('unknown', status=404)

    def test_concurrent_completion_credits_exactly_once(self):
        self.prepare()
        self.answer_all()
        clients = [self.app.test_client(), self.app.test_client()]
        tokens = [select_test_profile(client)['csrf_token'] for client in clients]
        def complete(pair):
            client, token = pair
            return client.post('/api/v1/onboarding/practice/complete', json={}, headers={'X-CSRF-Token': token})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(complete, zip(clients, tokens)))
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(sum(response.json['reward']['awarded_now'] for response in responses), 1)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='first_delivery'").fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT SUM(amount) FROM progression_entries WHERE policy_version=?', (WELCOME_POLICY,)).fetchone()[0], 3)

    def test_welcome_reversal_preserves_policy_and_cannot_reopen_normal_daily_cap(self):
        self.prepare()
        self.answer_all()
        self.post('complete')
        with transaction(self.db, write=True) as conn:
            for index in range(4):
                self.assertEqual(award(conn, 'personal-learning', activity='journey', content_key=f'cap-{index}',
                                       source_key=f'cap-{index}', title='Practice'), 3)
            self.assertEqual(reverse(conn, 'personal-learning', 'first_delivery', 'first-delivery-welcome'), -3)
            self.assertEqual(award(conn, 'personal-learning', activity='journey', content_key='extra', source_key='extra', title='Practice'), 0)
            entries = conn.execute('SELECT amount,policy_version FROM progression_entries WHERE policy_version=?', (WELCOME_POLICY,)).fetchall()
            self.assertEqual(sorted(tuple(row) for row in entries), [(-3, WELCOME_POLICY), (3, WELCOME_POLICY)])

    def test_simultaneous_guest_first_starts_share_one_durable_attempt(self):
        self.introduce()
        token = self.token()
        cookie_name = self.app.config['SESSION_COOKIE_NAME']
        cookie = self.client.get_cookie(cookie_name)
        clients = [self.app.test_client(), self.app.test_client()]
        for client in clients:
            client.set_cookie(cookie_name, cookie.value)
        def start(client):
            return client.post('/api/v1/onboarding/practice/start', json={}, headers={'X-CSRF-Token': token})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(start, clients))
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].json['attempt']['id'], responses[1].json['attempt']['id'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_delivery_attempts').fetchone()[0], 1)

    def test_household_selected_profile_has_its_own_activity(self):
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='test-household-secret-at-least-32-characters')
        self.app.extensions['learning']['household'].configure('Home', '246810')
        def action(path, data):
            response = self.client.post(path, json=data, headers={'X-CSRF-Token': self.token()})
            self.assertLess(response.status_code, 300, response.text)
            return response.json
        action('/api/v1/household/unlock', {'pin': '246810'})
        profile = action('/api/v1/grownups/profiles', {'display_name': 'River', 'study_timezone': 'UTC'})['id']
        action(f'/api/v1/grownups/profiles/{profile}/select', {})
        self.introduce()
        self.post('start')
        self.answer_all()
        completed = self.post('complete')
        self.assertEqual(completed['profile_id'], profile)
        self.assertEqual(completed['progression']['balance'], 3)
        action('/api/v1/household/lock', {})
        self.assertIsNone(self.read()['attempt'])


if __name__ == '__main__':
    unittest.main()
