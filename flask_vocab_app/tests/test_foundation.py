import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import create_app
from migrations import upgrade_database, seed_demo, schema_version
from models.database import connect_db
from services.user_service import UserService
from tests.support import isolated_app, latest_schema_version, strip_progression_and_levels
from tests.test_stabilization import FakeSentenceService


class FoundationTests(unittest.TestCase):
    def test_empty_database_supports_all_pages_without_providers(self):
        app = isolated_app(self, demo=False)
        with patch('openai.OpenAI', side_effect=AssertionError('Read-only page initialized OpenAI')):
            for path in ['/', '/vocab', '/metrics', '/comprehension', '/writing', '/lessons', '/word_jumble', '/sentences', '/sentences/saved', '/user/stats']:
                with self.subTest(path=path):
                    response = app.test_client().get(path)
                    # Coin totals stay hidden until the learner reaches their introduction.
                    self.assertEqual(response.status_code, 204 if path == '/user/stats' else 200)

    def test_factories_isolate_data_and_sessions(self):
        first = isolated_app(self)
        second = isolated_app(self, demo=False)
        self.assertEqual(first.test_client().get('/metrics').json['total_words'], 3)
        self.assertEqual(second.test_client().get('/metrics').json['total_words'], 0)
        self.assertNotEqual(first.config['SESSION_FILE_DIR'], second.config['SESSION_FILE_DIR'])
        self.assertIsNot(first.extensions['services']['WritingService'], second.extensions['services']['WritingService'])

    def test_invalid_query_and_redirect_inputs(self):
        client = isolated_app(self).test_client()
        client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get('/api/v1/user-session').json['csrf_token']
        for path in ['/vocab?page=abc', '/vocab?page=0', '/sentence/generate?topic=food&difficulty=abc']:
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 400)
        for target in ['//example.invalid', '/\\example.invalid', 'https://example.invalid']:
            self.assertEqual(client.post('/ui-language', data={'lang':'ru', 'next':target}).headers['Location'], '/')
        self.assertEqual(client.post('/ui-language', data={'next':'/vocab?page=2'}).headers['Location'], '/vocab?page=2')

    def test_configured_media_is_served_without_path_traversal(self):
        app = isolated_app(self)
        media = Path(app.config['APP_MEDIA_DIR'])
        media.mkdir()
        (media / 'example.txt').write_text('generated test asset')
        response = app.test_client().get('/static/media/example.txt')
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_data(as_text=True), 'generated test asset')
        finally:
            response.close()
        self.assertEqual(app.test_client().get('/static/media/../vocab.db').status_code, 404)

    def test_connection_enforces_references_and_closes(self):
        app = isolated_app(self)
        with self.assertRaises(sqlite3.IntegrityError):
            with connect_db(app.config['DB_PATH']) as conn:
                conn.execute("INSERT INTO forms(word_id,form,tags) VALUES (999999, 'missing', '{}')")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute('SELECT 1')

    def test_cli_bootstrap_is_repeatable_and_does_not_seed_personal_data(self):
        app = isolated_app(self, demo=False)
        runner = app.test_cli_runner()
        self.assertEqual(runner.invoke(args=['db-upgrade']).exit_code, 0)
        self.assertEqual(runner.invoke(args=['db-upgrade']).exit_code, 0)
        self.assertEqual(runner.invoke(args=['seed-demo']).exit_code, 0)
        self.assertNotEqual(runner.invoke(args=['seed-demo']).exit_code, 0)
        self.assertEqual(app.test_client().get('/metrics').json['total_words'], 3)

    def test_migration_adopts_existing_schema_and_preserves_rows(self):
        app = isolated_app(self)
        db = app.config['DB_PATH']
        with connect_db(db) as conn:
            before = list(conn.execute('SELECT * FROM words'))
            # Remove the later region extension when constructing an older schema.
            conn.execute('DROP INDEX lesson_pick_region')
            conn.execute('ALTER TABLE lesson_word_picks DROP COLUMN reading_confirmed')
            conn.execute('ALTER TABLE lesson_word_picks DROP COLUMN region_id')
            conn.execute('DROP TABLE lesson_word_regions')
            conn.execute('ALTER TABLE word_jumble_attempts DROP COLUMN tutor_feedback')
            strip_progression_and_levels(conn)
            conn.execute('DROP INDEX live_sessions_scenario')
            conn.execute('ALTER TABLE live_conversation_sessions DROP COLUMN variant_id')
            conn.execute('ALTER TABLE live_conversation_sessions DROP COLUMN scenario_id')
            conn.execute('ALTER TABLE live_conversation_sessions DROP COLUMN end_reason')
            conn.execute('DROP TABLE speaking_reviews')
            conn.execute('DROP TABLE schema_migrations')
            conn.execute('DROP TABLE sync_runs')
            conn.execute('DROP TABLE reward_events')
        version, backup = upgrade_database(db)
        self.assertEqual(version, latest_schema_version())
        self.assertTrue(Path(backup).exists())
        with connect_db(db) as conn:
            self.assertEqual(list(conn.execute('SELECT * FROM words')), before)
        self.assertEqual(upgrade_database(db), (latest_schema_version(), None))

    def test_migration_rejects_incompatible_schema_without_partial_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = str(Path(temporary) / 'legacy.db')
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE words(id INTEGER PRIMARY KEY, lemma TEXT)')
                conn.execute("INSERT INTO words VALUES (1,'кофе')")
            with self.assertRaisesRegex(ValueError, 'Unsupported legacy schema'):
                upgrade_database(db)
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute('SELECT * FROM words').fetchall(), [(1,'кофе')])
                self.assertEqual(schema_version(conn), 0)
                self.assertEqual(conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [('words',)])
            self.assertEqual(len(list(Path(temporary).glob('*.bak'))), 1)

    def test_legacy_score_wrapper_never_mints_rewards_even_under_concurrent_retries(self):
        app = isolated_app(self)
        service = UserService(app.config['DB_PATH'])
        def reward(_):
            return service.update_user_stats(1, 3, 4, 1, 'sentences', reward_key='sentence:42')
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(reward, range(4)))
        self.assertEqual(sum(r['lingocoins_earned'] for r in outcomes), 0)
        with connect_db(app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM reward_events').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_entries').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT lingocoins FROM users WHERE user_id=1').fetchone()[0], 0)

    def test_repeated_sentence_assessment_uses_reward_ledger(self):
        app = isolated_app(self, {'SentenceService': FakeSentenceService()})
        client = app.test_client()
        client.environ_base['HTTP_X_CSRF_TOKEN'] = client.get('/api/v1/user-session').json['csrf_token']
        with connect_db(app.config['DB_PATH']) as conn:
            id = conn.execute("INSERT INTO sentences(sentence,english,topic,difficulty,score) VALUES ('Привет!','Hi!','greetings',1,0)").lastrowid
        payload = {'sentence_id': id, 'user_response': 'Привет!', 'revision': 0}
        self.assertEqual(client.post('/sentence/assess',data=payload).status_code, 303)
        payload['revision'] = 1
        self.assertEqual(client.post('/sentence/assess',data=payload).status_code, 303)
        with connect_db(app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT lingocoins FROM users WHERE user_id=1').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT SUM(amount) FROM progression_entries').fetchone()[0], 3)
