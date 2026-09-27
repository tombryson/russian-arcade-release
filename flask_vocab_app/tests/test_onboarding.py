import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import migrations
from migrations import upgrade_database
from repositories.learning_repository import transaction
from services.onboarding import GUEST_ONBOARDING_KEY
from tests.support import isolated_app, select_test_profile


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, signed_in=False)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']

    def state(self, client=None):
        response = (client or self.client).get('/api/v1/onboarding')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def post(self, path, body, client=None):
        client = client or self.client
        return client.post(path, json=body, headers={'X-CSRF-Token': self.state(client)['csrf_token']})

    def mark(self, milestone, client=None):
        response = self.post('/api/v1/onboarding', {'milestone': milestone}, client)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json

    def reward_state(self):
        with transaction(self.db) as conn:
            return {
                table: [tuple(row) for row in conn.execute('SELECT * FROM ' + table + ' ORDER BY 1')]
                for table in ('users', 'progression_entries', 'progression_events', 'progression_claims',
                              'learning_reward_entries', 'journey_progress')
            }

    def test_guest_reads_are_initially_false_read_only_and_isolated_by_browser(self):
        rewards = self.reward_state()
        with transaction(self.db) as conn:
            before = [tuple(row) for row in conn.execute('SELECT * FROM profile_onboarding')]
        for _ in range(2):
            value = self.state()
            self.assertIsNone(value['profile_id'])
            self.assertFalse(value['coins_introduced'])
            self.assertFalse(value['progress_introduced'])
        self.mark('coins')
        self.assertTrue(self.state()['coins_introduced'])
        self.assertFalse(self.state(self.app.test_client())['coins_introduced'])
        with transaction(self.db) as conn:
            self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM profile_onboarding')], before)
        self.assertEqual(self.reward_state(), rewards)

    def test_progress_requires_coins_for_guests_and_profiles(self):
        response = self.post('/api/v1/onboarding', {'milestone': 'progress'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['error']['code'], 'coins_not_introduced')
        self.mark('coins')
        self.assertTrue(self.mark('progress')['progress_introduced'])
        select_test_profile(self.client)
        self.assertFalse(self.state()['coins_introduced'])
        self.assertEqual(self.post('/api/v1/onboarding', {'milestone': 'progress'}).status_code, 409)

    def test_profile_milestones_are_persistent_idempotent_and_do_not_change_rewards(self):
        select_test_profile(self.client)
        original = self.reward_state()
        for moment, milestone in ((100, 'coins'), (200, 'coins'), (300, 'progress'), (400, 'progress')):
            with patch('services.onboarding.timestamp', return_value=moment):
                self.mark(milestone)
        with transaction(self.db) as conn:
            row = conn.execute('SELECT coins_introduced_at,progress_introduced_at FROM profile_onboarding WHERE profile_id=?',
                               ('personal-learning',)).fetchone()
            self.assertEqual(tuple(row), (100, 300))
        other = self.app.test_client()
        select_test_profile(other)
        restored = self.state(other)
        self.assertEqual(restored['profile_id'], 'personal-learning')
        self.assertTrue(restored['coins_introduced'])
        self.assertTrue(restored['progress_introduced'])
        self.assertEqual(self.reward_state(), original)

    def test_guest_milestones_transfer_only_when_creating_a_new_profile(self):
        self.mark('coins')
        self.mark('progress')
        created = self.post('/api/v1/user-session/profiles', {'display_name': 'River'}).json['profile']['id']
        transferred = self.state()
        self.assertEqual(transferred['profile_id'], created)
        self.assertTrue(transferred['coins_introduced'])
        self.assertTrue(transferred['progress_introduced'])
        with self.client.session_transaction() as saved:
            self.assertNotIn(GUEST_ONBOARDING_KEY, saved)
        second = self.post('/api/v1/user-session/profiles', {'display_name': 'Jo'}).json['profile']['id']
        self.assertEqual(self.state()['profile_id'], second)
        self.assertFalse(self.state()['coins_introduced'])
        self.assertFalse(self.state()['progress_introduced'])
        select_test_profile(self.client, created)
        self.assertTrue(self.state()['progress_introduced'])

    def test_selecting_an_existing_profile_drops_guest_milestones_without_overwriting_it(self):
        self.mark('coins')
        self.mark('progress')
        select_test_profile(self.client)
        self.assertFalse(self.state()['coins_introduced'])
        self.assertFalse(self.state()['progress_introduced'])
        self.mark('coins')
        self.post('/api/v1/user-session/logout', {})
        signed_out = self.state()
        self.assertIsNone(signed_out['profile_id'])
        self.assertFalse(signed_out['coins_introduced'])
        select_test_profile(self.client)
        self.assertTrue(self.state()['coins_introduced'])
        self.assertFalse(self.state()['progress_introduced'])

    def test_csrf_validation_and_page_identity_prevent_cross_profile_updates(self):
        self.assertEqual(self.client.post('/api/v1/onboarding', json={'milestone': 'coins'}).status_code, 403)
        select_test_profile(self.client)
        old = self.state()
        new_id = self.post('/api/v1/user-session/profiles', {'display_name': 'Jo'}).json['profile']['id']
        self.assertEqual(self.client.post('/api/v1/onboarding', json={'milestone': 'coins'},
                         headers={'X-CSRF-Token': old['csrf_token']}).status_code, 403)
        response = self.client.post('/api/v1/onboarding', json={'milestone': 'coins'},
                                    headers={'X-CSRF-Token': self.state()['csrf_token'], 'X-Profile-ID': old['profile_id']})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.state()['profile_id'], new_id)
        self.assertFalse(self.state()['coins_introduced'])
        self.assertEqual(self.post('/api/v1/onboarding', {'milestone': 'coins', 'profile_id': 'personal-learning'}).status_code, 400)
        for milestone in ('other', None, [], 2):
            self.assertEqual(self.post('/api/v1/onboarding', {'milestone': milestone}).status_code, 400)

    def test_household_guest_new_profile_and_selected_profile_follow_the_same_rules(self):
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='test-household-secret-at-least-32-characters')
        self.app.extensions['learning']['household'].configure('Home', '246810')
        self.post('/api/v1/household/unlock', {'pin': '246810'})
        self.assertIsNone(self.state()['profile_id'])
        self.mark('coins')
        created = self.post('/api/v1/grownups/profiles', {'display_name': 'River', 'study_timezone': 'UTC'})
        self.assertEqual(created.status_code, 201, created.text)
        profile_id = created.json['id']
        self.post(f'/api/v1/grownups/profiles/{profile_id}/select', {})
        self.assertEqual(self.state()['profile_id'], profile_id)
        self.assertTrue(self.state()['coins_introduced'])
        self.assertTrue(self.mark('progress')['progress_introduced'])
        self.post('/api/v1/household/lock', {})
        self.assertIsNone(self.state()['profile_id'])
        self.assertFalse(self.state()['coins_introduced'])
        self.assertFalse(self.state()['progress_introduced'])

    def test_legacy_html_introduces_header_coins_then_progress_without_changing_rewards(self):
        select_test_profile(self.client)
        original = self.reward_state()
        before = self.client.get('/comprehension').text
        self.assertNotIn('data-progression-badge', before)
        self.assertNotIn('data-skill-rail', before)
        stats = self.client.get('/user/stats')
        self.assertEqual(stats.status_code, 204)
        self.assertEqual(stats.text, '')
        self.mark('coins')
        coins = self.client.get('/comprehension').text
        self.assertIn('data-progression-badge', coins)
        self.assertNotIn('data-skill-rail', coins)
        stats = self.client.get('/user/stats')
        self.assertEqual(stats.status_code, 200)
        self.assertIn('Lingocoins:', stats.text)
        self.mark('progress')
        complete = self.client.get('/comprehension').text
        self.assertIn('data-progression-badge', complete)
        self.assertIn('data-skill-rail', complete)
        self.assertEqual(self.reward_state(), original)


class OnboardingMigrationTests(unittest.TestCase):
    def test_existing_profiles_start_with_no_introductions_even_with_coins_and_ratings(self):
        with tempfile.TemporaryDirectory(prefix='onboarding-migration-') as temporary:
            root = Path(temporary)
            old_migrations = root / 'migrations'
            old_migrations.mkdir()
            for file in migrations.MIGRATION_DIR.glob('*.sql'):
                if int(file.name.split('_')[0]) <= 25:
                    shutil.copy(file, old_migrations / file.name)
            db = str(root / 'vocab.db')
            with patch.object(migrations, 'MIGRATION_DIR', old_migrations):
                self.assertEqual(upgrade_database(db, backup=False), (25, None))
            with sqlite3.connect(db) as conn:
                conn.execute("UPDATE users SET lingocoins=87,elo_rating=1400 WHERE user_id=1")
                conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
                before = conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone()
            shutil.copy(migrations.MIGRATION_DIR / '026_stepwise_onboarding.sql', old_migrations / '026_stepwise_onboarding.sql')
            with patch.object(migrations, 'MIGRATION_DIR', old_migrations):
                self.assertEqual(upgrade_database(db, backup=False), (26, None))
            with sqlite3.connect(db) as conn:
                profiles = conn.execute('SELECT id FROM learning_profiles ORDER BY id').fetchall()
                rows = conn.execute('SELECT profile_id,coins_introduced_at,progress_introduced_at FROM profile_onboarding ORDER BY profile_id').fetchall()
                self.assertEqual(rows, [(profile[0], None, None) for profile in profiles])
                self.assertEqual(conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone(), before)
            with patch.object(migrations, 'MIGRATION_DIR', old_migrations):
                self.assertEqual(upgrade_database(db, backup=False), (26, None))


if __name__ == '__main__':
    unittest.main()
