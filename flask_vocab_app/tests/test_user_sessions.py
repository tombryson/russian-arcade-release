import unittest

from repositories.learning_repository import transaction
from services.personal_learning import PERSONAL_PROFILE, PersonalSessions, personal_access
from tests.support import isolated_app


class UserSessionTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, signed_in=False)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']

    def state(self, client=None):
        response = (client or self.client).get('/api/v1/user-session')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json

    def command(self, path, data, *, client=None, method='POST'):
        client = client or self.client
        return client.open('/api/v1/user-session' + path, method=method, json=data,
                           headers={'X-CSRF-Token': self.state(client)['csrf_token']})

    def select(self, profile_id=PERSONAL_PROFILE, client=None):
        response = self.command('/select', {'profile_id': profile_id}, client=client)
        self.assertEqual(response.status_code, 200)
        return response.json

    def credential(self, client=None):
        with (client or self.client).session_transaction() as saved:
            return saved.get('personal_access_id')

    def test_new_visitor_can_browse_home_but_must_choose_before_studying(self):
        state = self.state()
        self.assertIsNone(state['profile'])
        self.assertIn(PERSONAL_PROFILE, [p['id'] for p in state['profiles']])
        self.assertIsNone(self.client.get('/api/v1/household').json['profile'])
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/progression').status_code, 401)
        self.assertEqual(self.client.get('/api/v1/flashcards').status_code, 401)
        self.assertEqual(self.client.get('/writing').headers['Location'], '/post/profiles')
        self.assertIsNone(self.credential())

    def test_existing_personal_cookie_and_progress_survive(self):
        credential = personal_access(self.db)
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO progression_preferences(profile_id,preferred_level) VALUES (?,?) '
                         'ON CONFLICT(profile_id) DO UPDATE SET preferred_level=excluded.preferred_level',
                         (PERSONAL_PROFILE, 'B1'))
        with self.client.session_transaction() as saved:
            saved['personal_access_id'] = credential
        self.assertEqual(self.state()['profile']['id'], PERSONAL_PROFILE)
        self.assertEqual(self.credential(), credential)
        self.assertEqual(self.client.get('/api/v1/progression').json['preferred_level'], 'B1')

    def test_create_and_switch_rotate_session_clear_transient_state_and_keep_each_balance(self):
        original = self.select()
        old_credential = self.credential()
        old_cookie = self.client.get_cookie('session').value
        old_progress = self.client.get('/api/v1/progression').json
        with self.client.session_transaction() as saved:
            saved.update(ui_lang='ru', current_story_data={'text': 'old'}, reading_rating_context={'text': 'old'})
        created = self.command('/profiles', {'display_name': 'River', 'study_timezone': 'Australia/Melbourne', 'avatar': 'moon'})
        self.assertEqual(created.status_code, 201)
        profile = created.json['profile']
        self.assertEqual((profile['display_name'], profile['avatar'], profile['study_timezone']),
                         ('River', 'moon', 'Australia/Melbourne'))
        self.assertNotEqual(profile['id'], PERSONAL_PROFILE)
        self.assertNotEqual(self.client.get_cookie('session').value, old_cookie)
        self.assertNotEqual(created.json['csrf_token'], original['csrf_token'])
        with self.client.session_transaction() as saved:
            self.assertEqual(saved['ui_lang'], 'ru')
            self.assertNotIn('current_story_data', saved)
            self.assertNotIn('reading_rating_context', saved)
        with transaction(self.db) as conn:
            self.assertIsNone(conn.execute('SELECT id FROM household_access WHERE id=?', (old_credential,)).fetchone())
        stale = self.app.test_client()
        stale.set_cookie('session', old_cookie)
        self.assertIsNone(self.state(stale)['profile'])
        self.assertEqual(stale.get('/api/v1/progression').status_code, 401)
        new_progress = self.client.get('/api/v1/progression').json
        self.assertEqual(new_progress['balance'], 0)
        self.assertEqual(new_progress['profile_id'], profile['id'])
        self.select()
        restored = self.client.get('/api/v1/progression').json
        self.assertEqual(restored['balance'], old_progress['balance'])

    def test_logout_revokes_access_and_does_not_sign_back_in(self):
        selected = self.select()
        credential = self.credential()
        response = self.command('/logout', {})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json['profile'])
        self.assertNotEqual(response.json['csrf_token'], selected['csrf_token'])
        for _ in range(2):
            self.assertIsNone(self.state()['profile'])
            self.assertIsNone(self.client.get('/api/v1/household').json['profile'])
            self.assertEqual(self.client.get('/api/v1/progression').status_code, 401)
        with transaction(self.db) as conn:
            self.assertIsNone(conn.execute('SELECT id FROM household_access WHERE id=?', (credential,)).fetchone())
            self.assertIsNotNone(conn.execute('SELECT id FROM learning_profiles WHERE id=?', (PERSONAL_PROFILE,)).fetchone())

    def test_clients_keep_independent_selections_and_logout_only_revokes_one_browser(self):
        self.select()
        other = self.app.test_client()
        created = self.command('/profiles', {'display_name': 'Alex'}, client=other).json
        self.assertEqual(self.state()['profile']['id'], PERSONAL_PROFILE)
        self.assertEqual(self.state(other)['profile']['id'], created['profile']['id'])
        self.command('/logout', {})
        self.assertEqual(self.state(other)['profile']['id'], created['profile']['id'])

    def test_csrf_checks_selection_and_stale_tab_writes(self):
        token = self.state()['csrf_token']
        self.assertEqual(self.client.post('/api/v1/user-session/select', json={'profile_id': PERSONAL_PROFILE}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/user-session/select', json={'profile_id': PERSONAL_PROFILE},
                         headers={'X-CSRF-Token': token, 'Origin': 'https://other.invalid'}).status_code, 403)
        self.select()
        response = self.client.post('/api/v1/progression/preferences', json={'level': 'B2'},
                                    headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/v1/progression').json['preferred_level'], 'A1')

    def test_expired_session_requires_selection_and_lifetime_matches_cookie_configuration(self):
        self.app.config['PERMANENT_SESSION_LIFETIME'] = 120
        self.select()
        credential = self.credential()
        with transaction(self.db, write=True) as conn:
            row = conn.execute('SELECT expires_at,adult_until FROM household_access WHERE id=?', (credential,)).fetchone()
            from repositories.learning_repository import timestamp
            self.assertLessEqual(abs(row['expires_at'] - timestamp() - 120), 1)
            self.assertEqual(row['adult_until'], row['expires_at'])
            conn.execute('UPDATE household_access SET expires_at=0 WHERE id=?', (credential,))
        self.assertIsNone(self.state()['profile'])
        self.assertIsNone(self.credential())
        self.assertEqual(self.client.get('/api/v1/progression').status_code, 401)

    def test_stale_page_identity_rejects_reads_and_writes_even_with_a_fresh_csrf_token(self):
        self.select()
        created = self.command('/profiles', {'display_name': 'River'}).json
        old_page = {'X-Profile-ID': PERSONAL_PROFILE, 'X-CSRF-Token': created['csrf_token']}
        self.assertEqual(self.client.get('/api/v1/progression', headers=old_page).status_code, 409)
        response = self.client.post('/api/v1/progression/preferences', json={'level': 'B2'}, headers=old_page)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['error']['code'], 'profile_changed')
        self.assertEqual(self.client.get('/sentence/generate', headers=old_page).status_code, 409)
        current_page = {'X-Profile-ID': created['profile']['id']}
        self.assertEqual(self.client.get('/api/v1/progression', headers=current_page).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/progression').json['preferred_level'], 'A1')

    def test_invalid_create_select_and_rename_preserve_current_profile(self):
        self.select()
        for body in ({'display_name': ' '}, {'display_name': 'Alex', 'study_timezone': 'invalid'},
                     {'display_name': 'Alex', 'avatar': 'invalid'}, {'display_name': 'Alex', 'unknown': True}):
            self.assertEqual(self.command('/profiles', body).status_code, 400)
        self.assertEqual(self.command('/select', {'profile_id': 'missing'}).status_code, 404)
        self.assertEqual(self.state()['profile']['id'], PERSONAL_PROFILE)
        renamed = self.command('/profile', {'display_name': 'Tom'}, method='PATCH')
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json['profile']['id'], PERSONAL_PROFILE)
        self.assertEqual(renamed.json['profile']['display_name'], 'Tom')
        self.command('/logout', {})
        self.assertEqual(self.command('/profile', {'display_name': 'Other'}, method='PATCH').status_code, 401)

    def test_archived_profiles_are_not_listed_or_selectable_and_household_mode_is_separate(self):
        service = PersonalSessions(self.db)
        credential = service.create('Hidden')
        profile_id = service.state(credential)['profile']['id']
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE learning_profiles SET archived=1 WHERE id=?', (profile_id,))
        self.assertNotIn(profile_id, [p['id'] for p in self.state()['profiles']])
        self.assertEqual(self.command('/select', {'profile_id': profile_id}).status_code, 404)
        self.app.config['WORD_POST_HOUSEHOLD_ENABLED'] = True
        self.assertEqual(self.client.get('/api/v1/user-session').status_code, 404)

    def test_html_profile_actions_use_csrf_and_safe_redirects(self):
        token = self.state()['csrf_token']
        response = self.client.post('/post/profiles/actions', data={
            'action': 'create', 'display_name': 'Jo', 'csrf_token': token,
            'next': 'https://other.invalid',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/#home')
        self.assertEqual(self.state()['profile']['display_name'], 'Jo')
        response = self.client.post('/post/profiles/actions', data={
            'action': 'logout', 'csrf_token': self.state()['csrf_token'],
        })
        self.assertEqual(response.headers['Location'], '/post/profiles')
        self.assertIsNone(self.state()['profile'])

    def test_profile_pages_escape_names_and_keep_invalid_form_input(self):
        self.command('/profiles', {'display_name': '<img src=x onerror=alert(1)>'})
        page = self.client.get('/post/profiles')
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers['Cache-Control'], 'no-store')
        self.assertIn('&lt;img', page.text)
        self.assertNotIn('<img src=x onerror=', page.text)
        response = self.client.post('/post/profiles/actions', data={
            'action': 'create', 'display_name': 'River', 'study_timezone': 'invalid',
            'csrf_token': self.state()['csrf_token'],
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('valid IANA study timezone', response.text)
        self.assertIn('value="River"', response.text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.state()['profile']['display_name'], '<img src=x onerror=alert(1)>')


if __name__ == '__main__':
    unittest.main()
