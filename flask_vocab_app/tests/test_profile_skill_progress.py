import json
import unittest

from flask import session

from blueprints.user_sessions import selected_skill_progress
from repositories.learning_repository import timestamp, transaction
from services.skill_progress import POLICY, SKILLS
from tests.support import isolated_app, select_test_profile


class ProfileSkillProgressTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, signed_in=False)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']

    def post(self, path, body):
        token = self.client.get('/api/v1/onboarding').json['csrf_token']
        response = self.client.post(path, json=body, headers={'X-CSRF-Token': token})
        self.assertLess(response.status_code, 400, response.text)
        return response

    def introduce_progress(self):
        for milestone in ('coins', 'progress'):
            self.post('/api/v1/onboarding', {'milestone': milestone})

    def add_rating(self, profile_id, *, activity='reading', score=1):
        event_id = profile_id + '-' + activity
        receipt = {'_skill': {'policy_version': POLICY, 'task_rating': 1000, 'scores': {activity: score}}}
        with transaction(self.db, write=True) as conn:
            conn.execute(
                'INSERT INTO progression_events(id,profile_id,activity,source_key,content_key,title,category,evidence_json,created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                (event_id, profile_id, activity, event_id, event_id, 'Saved assessment', 'activity', json.dumps(receipt), timestamp()),
            )

    def card(self, path='/post/profiles'):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('id="skill-progress"', response.text)
        return response.text.split('<section id="skill-progress"', 1)[1].split('</section>', 1)[0]

    def test_section_is_hidden_until_progress_is_introduced_for_a_selected_profile(self):
        self.introduce_progress()
        self.assertNotIn('id="skill-progress"', self.client.get('/post/profiles').text)
        select_test_profile(self.client)
        self.add_rating('personal-learning')
        self.assertNotIn('id="skill-progress"', self.client.get('/post/profiles').text)
        self.post('/api/v1/onboarding', {'milestone': 'coins'})
        self.assertNotIn('id="skill-progress"', self.client.get('/post/profiles').text)
        self.post('/api/v1/onboarding', {'milestone': 'progress'})
        self.assertIn('1,012', self.card())

    def test_unmeasured_skills_show_no_fictional_rating_or_getting_started_copy(self):
        select_test_profile(self.client)
        self.introduce_progress()
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE users SET elo_rating=1800 WHERE user_id=1')
        card = self.card()
        self.assertIn('Skill progress', card)
        self.assertIn('<p>Me</p>', card)
        self.assertEqual(card.count('Not started'), len(SKILLS))
        self.assertEqual(card.count('class="profile-skill-rating">—'), len(SKILLS))
        for _, label, _ in SKILLS:
            self.assertIn(label, card)
        for prohibited in ('Getting started', 'Your first checked activity', '1,000', '1000', '1,800', 'Stage 1'):
            self.assertNotIn(prohibited, card)

    def test_each_profile_page_uses_only_its_selected_skills_even_with_a_foreign_query_id(self):
        select_test_profile(self.client)
        self.introduce_progress()
        self.add_rating('personal-learning', activity='translation', score=1)
        other = self.post('/api/v1/user-session/profiles', {'display_name': 'River'}).json['profile']['id']
        self.introduce_progress()
        self.add_rating(other, activity='writing', score=0)
        other_card = self.card('/post/profiles?profile_id=personal-learning')
        self.assertIn(f'data-profile-id="{other}"', other_card)
        self.assertIn('<p>River</p>', other_card)
        self.assertIn('988', other_card)
        self.assertNotIn('1,012', other_card)
        self.assertIn('Stage 1', other_card)
        self.assertIn('1 checked attempt', other_card)
        select_test_profile(self.client)
        original_card = self.card('/post/profiles?profile_id=' + other)
        self.assertIn('data-profile-id="personal-learning"', original_card)
        self.assertIn('<p>Me</p>', original_card)
        self.assertIn('1,012', original_card)
        self.assertNotIn('988', original_card)
        self.assertNotIn('River', original_card)

    def test_skill_projection_does_not_write_authentication_profiles_rewards_or_evidence(self):
        select_test_profile(self.client)
        self.introduce_progress()
        self.add_rating('personal-learning')
        tables = ('household_access', 'learning_profiles', 'profile_onboarding', 'users',
                  'progression_events', 'progression_entries', 'progression_preferences')

        def saved_rows():
            with transaction(self.db) as conn:
                return {table: [tuple(row) for row in conn.execute('SELECT * FROM ' + table + ' ORDER BY 1')]
                        for table in tables}

        with self.client.session_transaction() as current:
            saved_session = dict(current)
        before = saved_rows()
        with self.app.test_request_context('/post/profiles'):
            session.update(saved_session)
            before_session = dict(session)
            first = selected_skill_progress()
            self.assertEqual(first, selected_skill_progress())
            self.assertEqual(first['profile_id'], 'personal-learning')
            self.assertEqual(dict(session), before_session)
        self.assertEqual(saved_rows(), before)

    def test_russian_profile_card_localizes_labels_and_actual_rating(self):
        select_test_profile(self.client)
        self.introduce_progress()
        self.add_rating('personal-learning')
        with self.client.session_transaction() as saved:
            saved['ui_lang'] = 'ru'
        card = self.card()
        self.assertIn('Прогресс навыков', card)
        self.assertIn('Чтение', card)
        self.assertIn('1 012', card)
        self.assertIn('Этап 1', card)
        self.assertIn('Проверено попыток: 1', card)
        self.assertIn('Ещё не начато', card)
        self.assertNotIn('Начало пути', card)

    def test_selected_household_learner_can_open_progress_without_unlocking_adult_controls(self):
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='household-test-key-at-least-32-characters')
        self.app.extensions['learning']['household'].configure('Home', '246810')
        self.post('/api/v1/household/unlock', {'pin': '246810'})
        learner = self.post('/api/v1/grownups/profiles', {'display_name': 'River', 'study_timezone': 'UTC'}).json['id']
        self.post(f'/api/v1/grownups/profiles/{learner}/select', {})
        self.assertNotIn('id="skill-progress"', self.client.get('/post/household').text)
        self.introduce_progress()
        self.add_rating(learner, activity='writing')
        card = self.card('/post/household')
        self.assertIn(f'data-profile-id="{learner}"', card)
        self.assertIn('<p>River</p>', card)
        self.assertIn('1,012', card)
        self.assertFalse(self.client.get('/api/v1/household').json['adult'])
        self.post('/api/v1/household/lock', {})
        self.assertNotIn('id="skill-progress"', self.client.get('/post/household').text)


if __name__ == '__main__':
    unittest.main()
