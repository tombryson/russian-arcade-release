from tests.support import latest_schema_version
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from PIL import Image

from app import create_app
from contracts.learning import validate_pack
from migrations import upgrade_database
from models.database import connect_db
from repositories.learning_repository import LearningError, transaction
from services.learning_assets import import_asset
from services.learning_backup import backup_learning_store
from tests.support import isolated_app


def choice_pack(content_id='coffee-letter', count=1):
    return {'schema_version': 1, 'id': content_id, 'kind': 'activity', 'title': 'A coffee letter',
            'source': 'Synthetic test fixture, explicitly approved only in isolated tests.',
            'items': [{'id': f'coffee-{i}', 'type': 'choice', 'prompt': 'Find coffee.', 'word_id': 1,
                       'choices': [{'id': 'coffee', 'text': 'кофе'}, {'id': 'school', 'text': 'школа'}],
                       'answer': 'coffee', 'hint': 'The answer is кофе.'} for i in range(count)]}


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='test-only-' * 4)
        self.db = self.app.config['DB_PATH']
        self.services = self.app.extensions['learning']
        self.household = self.services['household']
        self.content = self.services['content']
        self.learning = self.services['sessions']
        self.store = self.services['assets']
        self.household.configure('Test household', '246810')
        self.adult = self.app.test_client()
        self.unlock(self.adult)

    def post(self, client, url, data):
        token = client.get('/api/v1/household').json['csrf_token']
        return client.post(url, json=data, headers={'X-CSRF-Token': token})

    def unlock(self, client):
        result = self.post(client, '/api/v1/household/unlock', {'pin': '246810'})
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))

    @staticmethod
    def credential(client):
        with client.session_transaction() as saved:
            return saved['household_access_id']

    def learner(self, name='Explorer'):
        response = self.post(self.adult, '/api/v1/grownups/profiles', {'display_name': name, 'study_timezone': 'Australia/Melbourne'})
        self.assertEqual(response.status_code, 201)
        profile_id = response.json['id']
        child = self.app.test_client()
        self.unlock(child)
        response = self.post(child, f'/api/v1/grownups/profiles/{profile_id}/select', {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['adult'])
        return child, profile_id

    def publish(self, pack=None):
        version = self.content.import_draft(pack or choice_pack())
        response = self.post(self.adult, f'/api/v1/grownups/content/{version}/publish', {'reviewer': 'Fixture reviewer', 'approved': True})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return version

    def start(self, child, profile, version, key='start-1'):
        response = self.post(child, '/api/v1/learning-sessions', {'profile_id': profile, 'version_id': version, 'submission_id': key})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.json

    @staticmethod
    def answer(saved, submission='answer-1', choice='coffee'):
        return {'submission_id': submission, 'expected_revision': saved['revision'], 'item_id': saved['item']['id'], 'answer': {'choice_id': choice}}

    def test_default_mode_keeps_legacy_and_personal_study_without_household_controls(self):
        self.app.config['WORD_POST_HOUSEHOLD_ENABLED'] = False
        client = self.app.test_client()
        self.assertEqual(client.get('/tools/anki/').status_code, 200)
        self.assertEqual(client.get('/api/v1/household').json['mode'], 'personal')
        self.assertEqual(client.post('/api/v1/household/unlock', json={'pin': '246810'}).status_code, 404)
        former_household = client.get('/post/household')
        self.assertEqual(former_household.status_code, 302)
        self.assertEqual(former_household.location, '/post/profiles')

    def test_household_mode_requires_a_private_session_key(self):
        self.assertEqual(self.app.test_client().get('/post/household', headers={'Host': 'untrusted.invalid'}).status_code, 400)
        self.app.config['SECRET_KEY'] = 'dev-secret-key-change-me'
        self.assertEqual(self.app.test_client().get('/post/household').status_code, 503)

    def test_uninitialized_reads_do_not_create_a_database(self):
        missing = Path(self.db).parent / 'not-created.db'
        config = {**dict(self.app.config), 'DB_PATH': str(missing)}
        client = create_app(config).test_client()
        self.assertEqual(client.get('/api/v1/household').status_code, 503)
        self.assertFalse(missing.exists())

    def test_legacy_routes_private_uploads_and_catalogue_have_no_child_bypass(self):
        child, _ = self.learner()
        for client in (child, self.app.test_client()):
            for url in ('/tools/anki/', '/vocab', '/metrics', '/user/stats', '/comprehension/load/1', '/writing', '/lessons/load/1',
                        '/word_jumble', '/static/uploads/private.pdf', '/static/media/private.png', '/post/catalogue'):
                with self.subTest(url=url):
                    response = client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.headers['Location'], '/post/household')
            for url in ('/generate', '/delete_word', '/sync', '/writing/save'):
                response = self.post(client, url, {})
                self.assertIn(response.status_code, (401,403))
            self.assertEqual(client.get('/static/js/household_security.js').status_code, 200)
            self.assertEqual(client.get('/static/images/barsik-running-v1.webp').status_code, 200)
            self.assertEqual(client.get('/static/images/barsik-progress-run-v1.webp').status_code, 200)
        self.assertEqual(self.adult.get('/vocab').status_code, 200)
        self.assertIn('csrf-token', self.adult.get('/tools/anki/').get_data(as_text=True))
        self.assertEqual(self.adult.get('/tools/anki/').headers['Cache-Control'], 'no-store')

    def test_csrf_protects_login_json_forms_and_legacy_get_writes(self):
        client = self.app.test_client()
        self.assertEqual(client.post('/api/v1/household/unlock', json={'pin': '246810'}).status_code, 403)
        token = client.get('/api/v1/household').json['csrf_token']
        for headers in ({'Origin': 'https://elsewhere.invalid'}, {'Sec-Fetch-Site': 'cross-site'}):
            response = client.post('/api/v1/household/unlock', json={'pin': '246810'}, headers={'X-CSRF-Token': token, **headers})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.adult.post('/ui-language', data={'lang': 'ru'}).status_code, 403)
        self.assertEqual(self.adult.get('/sentence/generate').status_code, 403)
        self.assertEqual(self.adult.get('/sync_vocab').status_code, 403)
        for malformed in (None, [], {'pin': '246810', 'adult': True}):
            response = self.post(client, '/api/v1/household/unlock', malformed)
            self.assertIn(response.status_code, (400,415))

    def test_pin_throttle_survives_new_browser_and_success_rotates_session(self):
        client = self.app.test_client()
        token = client.get('/api/v1/household').json['csrf_token']
        old_cookie = client.get_cookie('session').value
        for _ in range(5):
            self.assertEqual(self.post(client, '/api/v1/household/unlock', {'pin': '000000'}).status_code, 403)
        self.assertEqual(self.post(self.app.test_client(), '/api/v1/household/unlock', {'pin': '246810'}).status_code, 429)
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE household_settings SET locked_until=1')
        self.unlock(client)
        self.assertNotEqual(client.get_cookie('session').value, old_cookie)
        self.assertNotEqual(client.get('/api/v1/household').json['csrf_token'], token)
        with transaction(self.db) as conn:
            row = conn.execute('SELECT pin_hash,failed_unlocks FROM household_settings').fetchone()
            self.assertNotIn('246810', row['pin_hash'])
            self.assertEqual(row['failed_unlocks'], 0)

    def test_pin_recovery_and_adult_expiry_revoke_access_without_losing_records(self):
        child, profile = self.learner()
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE household_access SET adult_until=0 WHERE id=?', (self.credential(self.adult),))
        self.assertEqual(self.post(self.adult, '/api/v1/grownups/profiles', {'display_name': 'No', 'study_timezone': 'UTC'}).status_code, 403)
        self.household.configure('Test household', '135790', reset=True)
        self.assertEqual(child.get('/api/v1/post').status_code, 401)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT display_name FROM learning_profiles WHERE id=?', (profile,)).fetchone()[0], 'Explorer')

    def test_new_profiles_have_no_legacy_balance_or_word_evidence(self):
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE users SET lingocoins=987,elo_rating=1234 WHERE user_id=1')
        child, profile = self.learner()
        state = child.get('/api/v1/word-pocket').json
        self.assertEqual((state['balance'], state['evidence'], state['rewards']), (0, [], []))
        self.assertEqual(child.get('/api/v1/household').json['profile']['id'], profile)
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone()), (987,1234))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_profiles WHERE legacy_user_id=1 AND archived=1').fetchone()[0], 1)

    def test_publication_is_explicit_and_draft_answers_cannot_leak(self):
        version = self.content.import_draft(choice_pack())
        self.assertEqual(self.content.import_draft(choice_pack()), version)
        child, profile = self.learner()
        self.assertEqual(child.get('/api/v1/post').json['content'], [])
        self.assertEqual(child.get(f'/api/v1/grownups/content/{version}').status_code, 403)
        self.assertEqual(self.post(child, '/api/v1/learning-sessions', {'profile_id': profile, 'version_id': version, 'submission_id': 'draft'}).status_code, 409)
        self.assertEqual(self.post(self.adult, f'/api/v1/grownups/content/{version}/publish', {'approved': False, 'reviewer': 'Test'}).status_code, 400)
        self.assertEqual(self.post(child, f'/api/v1/grownups/content/{version}/publish', {'approved': True, 'reviewer': 'Forged'}).status_code, 403)
        self.assertEqual(self.post(self.adult, f'/api/v1/grownups/content/{version}/publish', {'approved': True, 'reviewer': 'Test'}).status_code, 200)
        saved = self.start(child, profile, version)
        self.assertNotIn('answer', saved['item'])
        self.assertNotIn('hint', saved['item'])
        self.assertNotIn('source', saved)

    def test_strict_content_validation_and_native_deck_preparation(self):
        invalid = []
        for field, value in [('schema_version', True), ('items', []), ('kind', 'html')]:
            pack = choice_pack()
            pack[field] = value
            invalid.append(pack)
        for field, value in [('word_id', 99999), ('answer', 'unknown'), ('asset_ids', ['unknown']), ('type', 'javascript')]:
            pack = choice_pack()
            pack['items'][0][field] = value
            invalid.append(pack)
        pack = choice_pack()
        pack['items'].append(copy.deepcopy(pack['items'][0]))
        invalid.append(pack)
        for pack in invalid:
            with self.subTest(pack=pack), self.assertRaises(LearningError):
                self.content.import_draft(pack)
        starter = Path(__file__).parents[1] / 'content/starter-postcards.json'
        deck = json.loads(starter.read_text())
        validate_pack(deck)
        version = self.publish(deck)
        child, profile = self.learner()
        response = self.post(child, '/api/v1/learning-sessions', {'profile_id': profile, 'version_id': version, 'submission_id': 'not-yet'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['error']['code'], 'use_native_review')

    def test_content_edits_pin_old_sessions_and_withdrawal_stops_further_use(self):
        version = self.publish()
        child, profile = self.learner()
        saved = self.start(child, profile, version)
        pack = choice_pack()
        pack['items'][0]['prompt'] = 'A changed prompt'
        second = self.publish(pack)
        self.assertNotEqual(second, version)
        self.assertEqual(child.get('/api/v1/post').json['content'][0]['version_id'], second)
        self.assertEqual(child.get(f'/api/v1/learning-sessions/{saved["id"]}').json['item']['prompt'], 'Find coffee.')
        with self.assertRaises(sqlite3.IntegrityError), transaction(self.db, write=True) as conn:
            conn.execute("UPDATE learning_content_versions SET payload='{}' WHERE id=?", (version,))
        with self.assertRaises(sqlite3.IntegrityError), transaction(self.db, write=True) as conn:
            conn.execute('DELETE FROM forms WHERE word_id=1')
            conn.execute('DELETE FROM words WHERE id=1')
        self.assertEqual(self.post(self.adult, f'/api/v1/grownups/content/{version}/withdraw', {}).status_code, 200)
        self.assertEqual(child.get(f'/api/v1/learning-sessions/{saved["id"]}').status_code, 409)
        self.assertEqual(self.post(child, f'/api/v1/learning-sessions/{saved["id"]}/attempts', self.answer(saved)).status_code, 409)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_sessions').fetchone()[0], 1)

    def test_help_answer_and_history_survive_a_fresh_app_and_same_start_is_idempotent(self):
        version = self.publish(choice_pack(count=2))
        child, profile = self.learner()
        saved = self.start(child, profile, version)
        self.assertEqual(self.start(child, profile, version), saved)
        help_data = {k: v for k, v in self.answer(saved, 'help-1').items() if k != 'answer'}
        response = self.post(child, f'/api/v1/learning-sessions/{saved["id"]}/help', help_data)
        self.assertEqual(response.status_code, 200)
        helped = response.json
        self.assertIn('hint', helped['item'])
        response = self.post(child, f'/api/v1/learning-sessions/{saved["id"]}/attempts', self.answer(helped))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['attempts'][0]['assisted'])
        fresh = create_app(dict(self.app.config))
        reopened = fresh.test_client()
        reopened.set_cookie('session', child.get_cookie('session').value)
        resumed = reopened.get(f'/api/v1/learning-sessions/{saved["id"]}').json
        self.assertEqual(resumed['completed_items'], 1)
        self.assertEqual(resumed['revision'], 2)
        self.assertEqual(resumed['attempts'], response.json['attempts'])
        self.assertEqual(resumed['attempts'][0]['feedback']['answer'], 'кофе')
        self.assertEqual(resumed['attempts'][0]['prompt'], 'Find coffee.')
        evidence = reopened.get('/api/v1/word-pocket').json['evidence']
        self.assertEqual(evidence[0]['evidence_type'], 'supported_recognition')

    def test_concurrent_retry_creates_one_attempt_one_evidence_and_one_reward(self):
        version = self.publish()
        child, profile = self.learner()
        saved = self.start(child, profile, version)
        credential, answer = self.credential(child), self.answer(saved)
        def submit(_):
            return self.learning.command(credential, saved['id'], 'answer', answer)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit, range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(results[0]['balance'], 3)
        with transaction(self.db) as conn:
            for table in ('activity_attempts','learner_word_evidence','progression_entries','learning_commands'):
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 1)
        changed = {**answer, 'answer': {'choice_id': 'school'}}
        self.assertEqual(self.post(child, f'/api/v1/learning-sessions/{saved["id"]}/attempts', changed).status_code, 409)
        stale = self.post(child, f'/api/v1/learning-sessions/{saved["id"]}/attempts', {**answer, 'submission_id': 'new-stale'})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json['error']['current_session']['revision'], 1)

    def test_cross_profile_cached_results_stale_tab_and_archived_profile_are_rejected(self):
        version = self.publish()
        first, p1 = self.learner('First')
        second, p2 = self.learner('Second')
        saved = self.start(first, p1, version)
        self.assertEqual(self.post(first, f'/api/v1/learning-sessions/{saved["id"]}/attempts', self.answer(saved)).status_code, 200)
        self.assertEqual(second.get(f'/api/v1/learning-sessions/{saved["id"]}').status_code, 404)
        self.assertEqual(self.post(second, f'/api/v1/learning-sessions/{saved["id"]}/attempts', self.answer(saved)).status_code, 404)
        self.unlock(first)
        self.post(first, f'/api/v1/grownups/profiles/{p2}/select', {})
        self.assertEqual(self.post(first, '/api/v1/learning-sessions', {'profile_id': p1, 'version_id': version, 'submission_id': 'stale-tab'}).status_code, 409)
        self.assertEqual(self.post(self.adult, f'/api/v1/grownups/profiles/{p2}/archive', {}).status_code, 200)
        self.assertEqual(second.get('/api/v1/word-pocket').status_code, 409)

    def test_a_failed_reward_write_rolls_back_the_entire_answer(self):
        version = self.publish()
        child, profile = self.learner()
        saved = self.start(child, profile, version)
        with transaction(self.db, write=True) as conn:
            conn.execute("CREATE TRIGGER fail_reward BEFORE INSERT ON progression_entries BEGIN SELECT RAISE(ABORT,'simulated storage failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.learning.command(self.credential(child), saved['id'], 'answer', self.answer(saved))
        self.assertEqual(child.get(f'/api/v1/learning-sessions/{saved["id"]}').json['revision'], 0)
        with transaction(self.db) as conn:
            for table in ('activity_attempts','learner_word_evidence','progression_entries','learning_commands'):
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)

    def test_busy_database_returns_retryable_failure_without_saving_an_answer(self):
        version = self.publish()
        child, profile = self.learner()
        saved = self.start(child, profile, version)
        with transaction(self.db, write=True), patch('repositories.learning_repository.connect_db', side_effect=lambda path: connect_db(path, timeout=0.01)):
            response = self.post(child, f'/api/v1/learning-sessions/{saved["id"]}/attempts', self.answer(saved))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json['error']['code'], 'storage_busy')
        self.assertEqual(child.get(f'/api/v1/learning-sessions/{saved["id"]}').json['revision'], 0)

    def test_reward_cap_is_shared_across_concurrent_games_and_republication(self):
        child, profile = self.learner()
        sessions = [self.start(child, profile, self.publish(choice_pack(f'activity-{i}')), f'start-{i}') for i in range(5)]
        credential = self.credential(child)
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda saved: self.learning.command(credential, saved['id'], 'answer', self.answer(saved, choice='school')), sessions))
        self.assertEqual(sum(result['coins_earned'] for result in results), 12)
        self.assertEqual(child.get('/api/v1/word-pocket').json['balance'], 12)
        self.assertTrue(all(result['feedback']['outcome'] == 'incorrect' for result in results))
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 5)
        repeat = self.start(child, profile, sessions[0]['version_id'], 'repeat')
        self.assertEqual(self.learning.command(credential, repeat['id'], 'answer', self.answer(repeat))['coins_earned'], 0)

    def test_untrusted_scores_and_answers_cannot_force_completion(self):
        child, profile = self.learner()
        saved = self.start(child, profile, self.publish())
        for data in (self.answer(saved, choice='outside-options'), {**self.answer(saved), 'score': 100},
                     {**self.answer(saved), 'expected_revision': True}, {**self.answer(saved), 'item_id': 'future-item'}):
            response = self.post(child, f'/api/v1/learning-sessions/{saved["id"]}/attempts', data)
            self.assertIn(response.status_code, (400,409))
        self.assertEqual(child.get(f'/api/v1/learning-sessions/{saved["id"]}').json['revision'], 0)
        self.assertEqual(child.get('/api/v1/word-pocket').json['balance'], 0)

    def test_private_asset_publication_withdrawal_missing_media_and_traversal(self):
        image = io.BytesIO()
        Image.new('RGB', (2,2), 'green').save(image, format='PNG')
        asset_id = import_asset(self.db, self.store, image.getvalue(), 'Synthetic test image')
        self.assertEqual(import_asset(self.db, self.store, image.getvalue(), 'Same bytes'), asset_id)
        child, profile = self.learner()
        url = f'/api/v1/assets/{asset_id}'
        self.assertEqual(child.get(url).status_code, 404)
        response = self.adult.get(url)
        self.assertEqual(response.mimetype, 'image/png')
        response.close()
        pack = choice_pack()
        pack['items'][0]['asset_ids'] = [asset_id]
        version = self.publish(pack)
        response = child.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        response.close()
        self.post(self.adult, f'/api/v1/grownups/content/{version}/withdraw', {})
        self.assertEqual(child.get(url).status_code, 404)
        for value in ('../vocab.db', '/etc/passwd', 'a' * 64 + '/x'):
            with self.assertRaises(LearningError):
                self.store.path(value)
        for data in (b'<svg onload="alert(1)"></svg>', b'ID3not-valid-audio', b''):
            with self.assertRaises(LearningError):
                import_asset(self.db, self.store, data, 'Invalid fixture')
        with transaction(self.db) as conn:
            storage_key = conn.execute('SELECT storage_key FROM learning_assets WHERE id=?', (asset_id,)).fetchone()[0]
        self.store.path(storage_key).unlink()
        self.assertEqual(self.adult.get(url).status_code, 404)
        with self.assertRaises(LearningError):
            self.content.import_draft(pack)

    def test_household_forms_render_escaped_review_content_and_submit(self):
        pack = choice_pack()
        pack['items'][0]['prompt'] = '<script>untrusted()</script>'
        version = self.content.import_draft(pack)
        html = self.adult.get('/post/household?version=' + version).get_data(as_text=True)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>untrusted()', html)
        token = self.adult.get('/api/v1/household').json['csrf_token']
        response = self.adult.post('/post/household/actions', data={'action': 'publish', 'version_id': version, 'reviewer': 'Adult', 'approved': 'yes', 'csrf_token': token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.content.inspect(self.credential(self.adult), version)['status'], 'published')

    def test_cli_import_is_a_draft_and_setup_never_overwrites_existing_pin(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=['word-post', 'setup'], input='111111\n111111\n')
        self.assertNotEqual(result.exit_code, 0)
        source = Path(__file__).parents[1] / 'content/starter-postcards.json'
        result = runner.invoke(args=['word-post', 'import-pack', str(source)])
        self.assertEqual(result.exit_code, 0, result.output)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT status FROM learning_content_versions').fetchone()[0], 'draft')

    def test_reward_day_uses_profile_timezone_and_new_version_does_not_reaward(self):
        child, profile = self.learner()
        version = self.publish()
        credential = self.credential(child)
        # Melbourne is UTC+10 here: these are one minute either side of midnight.
        before = int(datetime(2026, 9, 8, 13, 59, tzinfo=timezone.utc).timestamp())
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE household_access SET expires_at=? WHERE id=?', (before + 3600, credential))
        self.learning.clock = lambda: before
        start_data = {'profile_id': profile, 'version_id': version, 'submission_id': 'day-one'}
        saved = self.learning.start(credential, start_data)
        self.assertEqual(self.learning.command(credential, saved['id'], 'answer', self.answer(saved))['coins_earned'], 3)
        pack = choice_pack()
        pack['title'] = 'A fresh coat of paint'
        second = self.publish(pack)
        same_day = self.learning.start(credential, {**start_data, 'version_id': second, 'submission_id': 'same-day'})
        self.assertEqual(self.learning.command(credential, same_day['id'], 'answer', self.answer(same_day))['coins_earned'], 0)
        self.learning.clock = lambda: before + 120
        next_day = self.learning.start(credential, {**start_data, 'submission_id': 'next-day'})
        self.assertEqual(self.learning.command(credential, next_day['id'], 'answer', self.answer(next_day))['coins_earned'], 3)
        with transaction(self.db) as conn:
            self.assertEqual([row[0] for row in conn.execute('SELECT study_day FROM progression_entries ORDER BY created_at')], ['2026-09-08','2026-09-09'])

    def test_migration_from_real_v3_shape_and_backup_restore_preserve_every_old_row(self):
        root = Path(self.db).parent
        legacy = root / 'baseline-v3.db'
        migration_dir = Path(__file__).parents[1] / 'migrations'
        with sqlite3.connect(legacy) as conn:
            for script in sorted(migration_dir.glob('00[123]_*.sql')):
                conn.executescript(script.read_text())
            conn.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            conn.executemany('INSERT INTO schema_migrations(version) VALUES (?)', [(1,),(2,),(3,)])
            conn.execute("INSERT INTO words(id,lemma,pos,lemma_difficulty) VALUES (42,'кофе','NOUN',1)")
            conn.execute("INSERT INTO forms(id,word_id,form,tags) VALUES (99,42,'кофе','{}')")
            conn.execute('INSERT INTO anki_cards(card_id,form_id,word_id,reps) VALUES (123,99,42,7)')
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('schema_migrations','sqlite_sequence')")]
            before = {name: list(conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')) for name in tables}
        version, backup = upgrade_database(str(legacy))
        self.assertEqual(version, latest_schema_version())
        self.assertTrue(Path(backup).exists())
        with sqlite3.connect(legacy) as conn:
            self.assertEqual({name: list(conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')) for name in tables}, before)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        restored = root / 'restored-v3.db'
        with sqlite3.connect(backup) as source, sqlite3.connect(restored) as destination:
            source.backup(destination)
        self.assertEqual(upgrade_database(str(restored))[0], latest_schema_version())
        with sqlite3.connect(restored) as conn:
            self.assertEqual({name: list(conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')) for name in tables}, before)

    def test_database_and_asset_backup_restore_a_completed_session_and_its_balance(self):
        image = io.BytesIO()
        Image.new('RGB', (2,2), 'blue').save(image, format='PNG')
        asset_id = import_asset(self.db, self.store, image.getvalue(), 'Backup fixture')
        pack = choice_pack()
        pack['items'][0]['asset_ids'] = [asset_id]
        version = self.publish(pack)
        child, profile = self.learner()
        saved = self.start(child, profile, version)
        result = self.post(child, f'/api/v1/learning-sessions/{saved["id"]}/attempts', self.answer(saved)).json
        backup = Path(self.db).parent / 'learning-backup'
        manifest = backup_learning_store(self.db, self.store, backup)
        self.assertEqual(len(manifest['assets']), 1)
        self.assertFalse((backup / 'INCOMPLETE').exists())
        with self.assertRaises(FileExistsError):
            backup_learning_store(self.db, self.store, backup)
        config = dict(self.app.config)
        config.update(DB_PATH=str(backup / 'vocab.db'), WORD_POST_ASSET_DIR=str(backup / 'assets'), SESSION_FILE_DIR=str(backup / 'fresh-sessions'))
        restored = create_app(config).test_client()
        self.unlock(restored)
        self.assertEqual(self.post(restored, f'/api/v1/grownups/profiles/{profile}/select', {}).status_code, 200)
        recovered = restored.get(f'/api/v1/learning-sessions/{saved["id"]}').json
        self.assertEqual(recovered['attempts'], result['attempts'])
        self.assertEqual((recovered['balance'], recovered['status']), (3, 'completed'))
        response = restored.get(f'/api/v1/assets/{asset_id}')
        self.assertEqual(response.get_data(), image.getvalue())
        response.close()
        self.store.path(manifest['assets'][0]['storage_key']).unlink()
        incomplete = backup.parent / 'incomplete-backup'
        with self.assertRaises(FileNotFoundError):
            backup_learning_store(self.db, self.store, incomplete)
        self.assertTrue((incomplete / 'INCOMPLETE').exists())
        self.assertFalse((incomplete / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
