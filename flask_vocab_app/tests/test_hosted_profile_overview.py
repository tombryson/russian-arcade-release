"""Hosted profile progress stays inside the authenticated learner workspace."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from werkzeug.test import Client
from werkzeug.wrappers import Response

from app import create_app
from hosted_trial import HostedTrialDispatcher
from repositories.learning_repository import timestamp, transaction
from services.skill_progress import POLICY, SKILLS
from tests.support import isolated_app, select_test_profile
from tests.test_hosted_trial import IdentityProvider


class NamedIdentityProvider(IdentityProvider):
    def verify(self, code, verifier):
        identity, _ = super().verify(code, verifier)
        return identity, {'github:11': 'Alice', 'github:22': 'Boris'}[identity]


class HostedProfileOverviewTests(unittest.TestCase):
    base = 'https://arcade.example'

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        disk = patch('hosted_trial.shutil.disk_usage')
        disk.start().return_value.free = 1024 ** 3
        self.addCleanup(disk.stop)
        network = patch('socket.socket.connect', side_effect=AssertionError('Profile tests must not call providers'))
        network.start()
        self.addCleanup(network.stop)
        self.provider = NamedIdentityProvider()
        self.dispatch = HostedTrialDispatcher(
            lambda environ, respond: Response('Public samples')(environ, respond),
            lambda settings: create_app(settings | {
                'TESTING': True, 'OPENAI_API_KEY': '', 'OPENROUTER_API_KEY': '',
                'ELEVENLABS_API_KEY': '', 'YANDEX_API_KEY': '',
            }),
            root=self.root, ledger_path=self.root / 'budget.sqlite3',
            secret='synthetic-profile-secret-' * 3, hostname='arcade.example',
            enabled=True, ai_enabled=False, guest_demo_enabled=True,
            identity_provider=self.provider, max_cached_apps=3,
        )
        self.alice, self.boris = Client(self.dispatch, Response), Client(self.dispatch, Response)

    def get(self, client, path):
        return client.get(path, base_url=self.base, buffered=True)

    def login(self, client, identity='github:11'):
        self.provider.identity = identity
        response = self.get(client, '/trial/sign-in/github')
        self.assertEqual(response.status_code, 302, response.text)
        state = parse_qs(urlsplit(response.location).query)['state'][0]
        response = self.get(client, '/trial/callback?code=valid&state=' + state)
        self.assertEqual(response.status_code, 302, response.text)
        return self.dispatch.cache[identity]

    def add_rating(self, app, *, score, profile_id='personal-learning'):
        event_id = profile_id + '-reading'
        receipt = {'_skill': {'policy_version': POLICY, 'task_rating': 1000, 'scores': {'reading': score}}}
        with transaction(app.config['DB_PATH'], write=True) as conn:
            conn.execute(
                'INSERT INTO progression_events(id,profile_id,activity,source_key,content_key,title,category,evidence_json,created_at) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                (event_id, profile_id, 'reading', event_id, event_id, 'Saved assessment',
                 'activity', json.dumps(receipt), timestamp()),
            )

    def skill_card(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('id="skill-progress"', response.text)
        return response.text.split('<section id="skill-progress"', 1)[1].split('</section>', 1)[0]

    def test_personal_overview_has_progress_preferences_and_account_settings_without_local_controls(self):
        self.login(self.alice)
        state = self.get(self.alice, '/api/v1/user-session').json
        response = self.get(self.alice, '/post/profiles')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('Alice', response.text)
        self.assertIn('data-course-profile="personal-learning"', response.text)
        self.assertIn('Course milestones', response.text)
        self.assertIn('aria-label="Appearance"', response.text)
        self.assertIn('action="/ui-navigation"', response.text)
        self.assertIn('href="/trial/account"', response.text)
        self.assertIn('Account settings', response.text)
        self.assertIn('data-profile-id="personal-learning"', response.text)
        self.assertIn(f'data-session-scope="{state["session_scope"]}"', response.text)
        self.assertNotIn('action="/post/profiles/actions"', response.text)
        self.assertNotIn('Who’s learning?', response.text)
        self.assertNotIn('Add a profile', response.text)
        self.assertNotIn('End session', response.text)

    def test_hosted_skills_show_empty_and_measured_progress_without_completing_onboarding(self):
        app = self.login(self.alice)
        before = self.get(self.alice, '/api/v1/onboarding').json
        self.assertFalse(before['progress_introduced'])
        card = self.skill_card(self.get(self.alice, '/post/profiles'))
        self.assertEqual(card.count('Not started'), len(SKILLS))
        self.assertEqual(card.count('class="profile-skill-rating">—'), len(SKILLS))
        self.assertNotIn('1,000', card)
        self.add_rating(app, score=1)
        self.assertIn('1,012', self.skill_card(self.get(self.alice, '/post/profiles')))
        self.assertEqual(self.get(self.alice, '/api/v1/onboarding').json, before)

    def test_same_profile_id_in_two_accounts_never_shares_names_or_ratings_and_query_ids_are_ignored(self):
        alice_app = self.login(self.alice)
        boris_app = self.login(self.boris, 'github:22')
        self.add_rating(alice_app, score=1)
        self.add_rating(boris_app, score=0)
        with transaction(alice_app.config['DB_PATH'], write=True) as conn:
            conn.execute(
                'INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES (?,?,?,?,?)',
                ('unselected-profile', 'Unselected learner', 'cat', 'UTC', timestamp()),
            )
        alice_state = self.get(self.alice, '/api/v1/user-session').json
        boris_state = self.get(self.boris, '/api/v1/user-session').json
        self.assertEqual(alice_state['profile']['id'], boris_state['profile']['id'])
        self.assertNotEqual(alice_state['session_scope'], boris_state['session_scope'])
        for client, own_name, own_rating, foreign_name, foreign_rating in (
            (self.alice, 'Alice', '1,012', 'Boris', '988'),
            (self.boris, 'Boris', '988', 'Alice', '1,012'),
        ):
            with self.subTest(learner=own_name):
                response = self.get(client, '/post/profiles?profile_id=unselected-profile')
                card = self.skill_card(response)
                self.assertIn('data-profile-id="personal-learning"', card)
                self.assertIn(own_name, card)
                self.assertIn(own_rating, card)
                self.assertNotIn(foreign_name, card)
                self.assertNotIn(foreign_rating, card)
                self.assertNotIn('Unselected learner', response.text)

    def test_account_management_and_demo_routes_keep_their_separate_controls(self):
        self.login(self.alice)
        household = self.get(self.alice, '/post/household')
        self.assertEqual(household.status_code, 302)
        self.assertEqual(household.location, '/post/profiles')
        settings = self.get(self.alice, '/trial/account')
        self.assertEqual(settings.status_code, 200)
        self.assertIn('<h1>Account settings</h1>', settings.text)
        self.assertIn('href="/post/profiles"', settings.text)
        self.assertIn('action="/trial/sign-out"', settings.text)
        self.assertIn('Sign-in methods', settings.text)
        self.assertEqual(self.get(self.alice, '/trial/sign-in').location, '/post/profiles')
        self.assertEqual(self.get(self.boris, '/demo').status_code, 302)
        for path in ('/demo/post/profiles', '/demo/post/household'):
            response = self.get(self.boris, path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.location, '/demo/trial/account', path)

    def test_opening_hosted_overview_does_not_enable_local_profile_mutations(self):
        self.login(self.alice)
        self.assertEqual(self.get(self.alice, '/post/profiles').status_code, 200)
        token = self.get(self.alice, '/api/v1/user-session').json['csrf_token']
        for path, body in (
            ('/api/v1/user-session/profiles', {'display_name': 'Other learner'}),
            ('/api/v1/user-session/select', {'profile_id': 'personal-learning'}),
            ('/api/v1/user-session/logout', {}),
            ('/post/profiles/actions', {'action': 'logout'}),
        ):
            with self.subTest(path=path):
                response = self.alice.post(path, base_url=self.base, json=body,
                                           headers={'X-CSRF-Token': token}, buffered=True)
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.get(self.alice, '/api/v1/user-session').json['profile']['display_name'], 'Alice')

    def test_local_profile_picker_still_waits_for_progress_introduction(self):
        app = isolated_app(self, signed_in=False)
        client = app.test_client()
        select_test_profile(client)
        page = client.get('/post/profiles')
        self.assertIn('Who’s learning?', page.text)
        self.assertIn('action="/post/profiles/actions"', page.text)
        self.assertNotIn('id="skill-progress"', page.text)
        token = client.get('/api/v1/onboarding').json['csrf_token']
        for milestone in ('coins', 'progress'):
            response = client.post('/api/v1/onboarding', json={'milestone': milestone},
                                   headers={'X-CSRF-Token': token})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('id="skill-progress"', client.get('/post/profiles').text)


if __name__ == '__main__':
    unittest.main()
