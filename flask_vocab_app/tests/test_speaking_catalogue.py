"""Isolated catalogue, session relationship and migration regressions."""
from tests.support import latest_schema_version
import json
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch

from migrations import MIGRATION_DIR, schema_version, upgrade_database
from repositories.learning_repository import transaction
from services.conversation_ai import SCENARIO
from tests.support import isolated_app, strip_progression_and_levels
from tests.test_conversation import FakeAI, FakeSpeech
from tests.test_live_conversation import FakeLive


class SpeakingCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.provider, self.speech, self.ai = FakeLive(), FakeSpeech(), FakeAI()
        self.app = isolated_app(self, {'LiveVoiceProvider': self.provider,
                                     'SpeechProvider': self.speech, 'ConversationAI': self.ai})
        self.service = self.app.extensions['learning']['live_conversation']
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        self.token = self.client.get('/api/v1/household').json['csrf_token']
        self.dispatch = self.patch(self.service, 'dispatch')
        self.review_dispatch = self.patch(self.service.reviews, 'dispatch')
        self.review_request = self.patch(self.service.reviews, 'request')
        self.addCleanup(self.cleanup)

    def patch(self, target, name):
        patcher = patch.object(target, name)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def cleanup(self):
        for runtime in list(self.service.connections.values()):
            runtime['stop'].set()
            runtime['closed'].wait(3)
        self.service.executor.shutdown(wait=True)
        self.service.reviews.executor.shutdown(wait=True)
        self.app.extensions['learning']['conversation'].executor.shutdown(wait=True)

    def post(self, path='', body=None):
        return self.client.post('/api/v1/live-conversations' + path, json=body or {},
                                headers={'X-CSRF-Token': self.token})

    def start(self, key, category='cafe', seed=None):
        body = {'submission_id': key, 'scenario_id': category}
        if seed is not None:
            body['scenario_seed'] = seed
        result = self.post(body=body)
        self.assertEqual(result.status_code, 201, result.json)
        return result.json

    def options(self, category, exclude_seed=None, level=None):
        args = {'scenario_id': category}
        if exclude_seed is not None:
            args['exclude_seed'] = exclude_seed
        if level is not None:
            args['level'] = level
        return self.client.get('/api/v1/live-conversations/options', query_string=args)

    def read(self, sid):
        response = self.client.get('/api/v1/live-conversations/' + sid)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def session_count(self):
        with transaction(self.db) as conn:
            return conn.execute('SELECT COUNT(*) FROM live_conversation_sessions').fetchone()[0]

    def test_catalogue_has_five_scenarios_with_variant_counts_and_reads_are_free(self):
        expected = dict.fromkeys(('cafe','shop','directions','station','meet-someone'),6)
        for _ in range(3):
            response = self.client.get('/api/v1/live-conversations/scenarios')
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json['activity'], {
                'id': 'speaking', 'title': 'Speaking', 'title_ru': 'Разговорная практика'})
            self.assertEqual({row['id']: row['variant_count'] for row in response.json['scenarios']}, expected)
            self.assertTrue(all(row['activity_type_id'] == 'speaking' for row in response.json['scenarios']))
            for category in expected:
                preview = self.options(category)
                self.assertEqual(preview.status_code, 200, preview.json)
                self.assertEqual(preview.json['scenario']['scenario_id'], category)
        self.assertEqual(self.session_count(), 0)
        self.assertEqual(self.provider.creates, [])
        self.assertEqual(self.speech.calls, [])
        self.assertEqual(self.ai.replies, [])
        self.assertEqual(self.ai.assessments, [])
        self.dispatch.assert_not_called()
        self.review_dispatch.assert_not_called()
        self.review_request.assert_not_called()

    def test_each_category_starts_the_exact_selected_variant_with_foreign_keys(self):
        seeds = {'cafe': 'cafe-a1-takeaway-v2', 'shop': 'shop-a1-tshirt-v2',
                 'directions': 'directions-a2-library-v2', 'station': 'station-a2-connection-v2',
                 'meet-someone': 'meet-someone-a1-neighbour-v2'}
        for category, seed in seeds.items():
            with self.subTest(category=category):
                saved = self.start('selected-' + category, category, seed)
                self.assertEqual(saved['scenario_id'], category)
                self.assertEqual(saved['variant_id'], seed)
                self.assertEqual(saved['scenario']['seed'], seed)
                self.assertEqual(saved['scenario']['scenario_id'], category)
                with transaction(self.db) as conn:
                    row = conn.execute('''SELECT s.id,v.id FROM live_conversation_sessions c
                        JOIN speaking_scenarios s ON c.scenario_id=s.id
                        JOIN speaking_scenario_variants v ON c.variant_id=v.id AND v.scenario_id=s.id
                        WHERE c.id=?''', (saved['id'],)).fetchone()
                    self.assertEqual(tuple(row), (category, seed))
                self.assertEqual(self.read(saved['id'])['scenario'], saved['scenario'])
        self.assertEqual(self.provider.creates, [])

    def test_fake_connection_receives_the_selected_role_and_snapshot(self):
        saved = self.start('connected-directions', 'directions', 'directions-a2-library-v2')
        response = self.post('/' + saved['id'] + '/connect', {'sdp': 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(self.provider.creates[0][1], saved['scenario'])
        self.assertEqual(self.provider.creates[0][0]['scenario_id'], 'directions')
        runtime = self.service.connections[saved['id']]
        self.post('/' + saved['id'] + '/finish')
        self.assertTrue(runtime['closed'].wait(3))

    def test_cross_category_seed_unknown_category_and_invalid_ids_are_rejected_without_sessions(self):
        for body, status in (
            ({'scenario_id': 'directions', 'scenario_seed': 'cafe-a1-takeaway-v2'}, 400),
            ({'scenario_id': 'missing'}, 404),
            ({'scenario_id': ['cafe']}, 400),
            ({'scenario_id': 'shop', 'scenario_seed': ['shop-a1-tshirt-v2']}, 400),
        ):
            with self.subTest(body=body):
                response = self.post(body={'submission_id': 'invalid', **body})
                self.assertEqual(response.status_code, status, response.json)
        self.assertEqual(self.options('missing').status_code, 404)
        self.assertEqual(self.session_count(), 0)
        self.assertEqual(self.provider.creates, [])

    def test_disabled_scenarios_and_variants_are_unselectable_but_saved_history_is_readable(self):
        saved = self.start('before-disable', 'shop', 'shop-a1-tshirt-v2')
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE speaking_scenario_variants SET enabled=0 WHERE id='shop-a1-tshirt-v2'")
        response = self.post(body={'submission_id': 'disabled-variant', 'scenario_id': 'shop', 'scenario_seed': 'shop-a1-tshirt-v2'})
        self.assertEqual(response.status_code, 400, response.json)
        self.assertNotEqual(self.options('shop').json['scenario']['seed'], 'shop-a1-tshirt-v2')
        counts = {row['id']: row['variant_count'] for row in self.client.get('/api/v1/live-conversations/scenarios').json['scenarios']}
        self.assertEqual(counts['shop'], 5)
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE speaking_scenarios SET enabled=0 WHERE id='shop'")
        self.assertEqual(self.options('shop').status_code, 404)
        response = self.post(body={'submission_id': 'disabled-category', 'scenario_id': 'shop'})
        self.assertEqual(response.status_code, 404, response.json)
        self.assertNotIn('shop', [row['id'] for row in self.client.get('/api/v1/live-conversations/scenarios').json['scenarios']])
        self.assertEqual(self.read(saved['id'])['scenario'], saved['scenario'])
        self.assertEqual(self.session_count(), 1)

    def test_category_without_enabled_variants_is_hidden_and_returns_a_clear_error(self):
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE speaking_scenario_variants SET enabled=0 WHERE scenario_id='station'")
        self.assertNotIn('station', [row['id'] for row in self.client.get('/api/v1/live-conversations/scenarios').json['scenarios']])
        self.assertEqual(self.options('station').status_code, 409)
        self.assertEqual(self.post(body={'submission_id': 'empty', 'scenario_id': 'station'}).status_code, 409)
        self.assertEqual(self.session_count(), 0)

    def test_repeat_avoidance_uses_category_history_beyond_the_recent_list(self):
        first = self.start('directions-first', 'directions', 'directions-a2-library-v2')
        for number in range(13):
            self.start('intervening-cafe-' + str(number))
        preview = self.options('directions').json
        self.assertNotIn(first['id'], [item['id'] for item in preview['sessions']])
        with transaction(self.db) as conn:
            remaining = {row[0] for row in conn.execute("SELECT id FROM speaking_scenario_variants WHERE scenario_id='directions' AND enabled=1")}
        remaining.remove(first['scenario']['seed'])
        for index in range(len(remaining)):
            selected = self.start('directions-other-' + str(index), 'directions')
            self.assertIn(selected['scenario']['seed'], remaining)
            remaining.remove(selected['scenario']['seed'])
        self.assertFalse(remaining)
        self.assertEqual(self.options('directions').json['scenario']['seed'], first['scenario']['seed'])

    def test_another_situation_excludes_the_preview_without_creating_a_session(self):
        self.assertNotEqual(self.options('meet-someone', 'meet-someone-a1-neighbour-v2').json['scenario']['seed'], 'meet-someone-a1-neighbour-v2')
        self.assertNotEqual(self.options('meet-someone', 'meet-someone-a2-cycling-v2').json['scenario']['seed'], 'meet-someone-a2-cycling-v2')
        self.assertEqual(self.session_count(), 0)

    def test_idempotent_retry_preserves_selected_snapshot_and_rejects_conflicting_scenario(self):
        first = self.start('same-key', 'directions', 'directions-a2-library-v2')
        again = self.start('same-key', 'directions', 'directions-a2-library-v2')
        self.assertEqual(again, first)
        for body in (
            {'scenario_id': 'shop', 'scenario_seed': 'shop-a1-trousers-v2'},
            {'scenario_id': 'directions', 'scenario_seed': 'directions-a2-museum-v2'},
            {'scenario_id': 'directions', 'language': 'ru'},
        ):
            response = self.post(body={'submission_id': 'same-key', **body})
            self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(self.post(body={'submission_id': 'same-key'}).json['id'], first['id'])
        self.assertEqual(self.session_count(), 1)
        self.assertEqual(self.provider.creates, [])

    def test_catalogue_edits_change_new_previews_without_rewriting_saved_snapshots(self):
        saved = self.start('before-edit', 'directions', 'directions-a2-library-v2')
        with transaction(self.db, write=True) as conn:
            original = conn.execute('SELECT scenario_json FROM live_conversation_sessions WHERE id=?', (saved['id'],)).fetchone()[0]
            payload = json.loads(conn.execute("SELECT payload_json FROM speaking_scenario_variants WHERE id='directions-a2-library-v2'").fetchone()[0])
            payload.update(title='A new route', worker_brief='Библиотека теперь рядом с театром.')
            conn.execute("UPDATE speaking_scenario_variants SET payload_json=? WHERE id='directions-a2-library-v2'", (json.dumps(payload, ensure_ascii=False),))
            conn.execute("UPDATE speaking_scenario_levels SET title='Around town' WHERE scenario_id='directions' AND target_level='A2'")
            conn.execute("UPDATE speaking_scenario_variants SET enabled=0 WHERE scenario_id='directions' AND id!='directions-a2-library-v2'")
        preview = self.options('directions', 'directions-a2-museum-v2', 'A2').json['scenario']
        self.assertEqual(preview['seed'], 'directions-a2-library-v2')
        self.assertEqual(preview['title'], 'A new route')
        self.assertEqual(preview['worker_brief'], 'Библиотека теперь рядом с театром.')
        self.assertEqual(preview['category_title'], 'Around town')
        self.assertEqual(self.read(saved['id'])['scenario'], saved['scenario'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT scenario_json FROM live_conversation_sessions WHERE id=?', (saved['id'],)).fetchone()[0], original)
        new = self.start('after-edit', 'directions', 'directions-a2-library-v2')
        self.assertEqual(new['scenario'], preview)
        # Up-to-date migrations do not reseed over curriculum edits.
        self.assertEqual(upgrade_database(self.db, backup=False)[0], latest_schema_version())
        self.assertEqual(self.options('directions', 'directions-a2-museum-v2', 'A2').json['scenario']['title'], 'A new route')

    def test_foreign_keys_reject_orphaned_activity_scenario_variant_and_session_references(self):
        saved = self.start('relations', 'directions', 'directions-a2-library-v2')
        for statement, args in (
            ("UPDATE speaking_scenarios SET activity_type_id='missing' WHERE id='directions'", ()),
            ("UPDATE speaking_scenario_variants SET scenario_id='missing' WHERE id='directions-a2-library-v2'", ()),
            ("UPDATE live_conversation_sessions SET scenario_id='missing' WHERE id=?", (saved['id'],)),
            ("UPDATE live_conversation_sessions SET variant_id='missing' WHERE id=?", (saved['id'],)),
        ):
            with self.subTest(statement=statement):
                with self.assertRaises(sqlite3.IntegrityError):
                    with transaction(self.db, write=True) as conn:
                        conn.execute(statement, args)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_migration22_backfills_recognised_cafe_history_and_preserves_original_json(self):
        # Recreate an actual schema-21 shape. Removing only the migration marker
        # would hide an ALTER TABLE regression behind already-present columns.
        with transaction(self.db, write=True) as conn:
            strip_progression_and_levels(conn)
            conn.execute('DROP INDEX live_sessions_scenario')
            conn.execute('ALTER TABLE live_conversation_sessions DROP COLUMN variant_id')
            conn.execute('ALTER TABLE live_conversation_sessions DROP COLUMN scenario_id')
            conn.execute('DROP TABLE speaking_scenario_variants')
            conn.execute('DROP TABLE speaking_scenarios')
            conn.execute('DROP TABLE learning_activity_types')
            conn.execute('DELETE FROM schema_migrations WHERE version=22')
            self.assertEqual(schema_version(conn), 21)
            columns = {row[1] for row in conn.execute('PRAGMA table_info(live_conversation_sessions)')}
            self.assertNotIn('scenario_id', columns)
            self.assertNotIn('variant_id', columns)
            snapshots = {
                'legacy-cafe': json.dumps(SCENARIO, ensure_ascii=False, indent=2),
                'seeded-cafe': '{"seed": "cafe-for-two-v1", "title": "My unchanged café", "menu": {"чай": 77}}',
                'unknown': '{"id": "custom", "seed": "custom-old-seed", "title": "Keep me"}',
                'malformed': 'An old malformed scenario must not prevent migration',
            }
            for sid, snapshot in snapshots.items():
                conn.execute('''INSERT INTO live_conversation_sessions
                    (id,profile_id,start_key,scenario_json,language,model,backend_model,voice,
                     state,created_at,heartbeat_at,end_reason,final_usage_json)
                    VALUES (?,'personal-learning',?,?,'en','original-live','original-backend','cedar',
                            'completed',1,2,'learner_finished','{"duration_seconds":12}')''', (sid, sid, snapshot))
            before = {row['id']: dict(row) for row in conn.execute('SELECT * FROM live_conversation_sessions')}
        through22 = Path(self.db).parent / 'migrations-through-22'
        through22.mkdir()
        for file in MIGRATION_DIR.glob('[0-9][0-9][0-9]_*.sql'):
            if int(file.name.split('_')[0]) <= 22:
                shutil.copyfile(file, through22/file.name)
        with patch('migrations.MIGRATION_DIR', through22):
            self.assertEqual(upgrade_database(self.db, backup=False), (22, None))
        with transaction(self.db) as conn:
            after = {row['id']: dict(row) for row in conn.execute('SELECT * FROM live_conversation_sessions')}
            self.assertEqual((after['legacy-cafe']['scenario_id'], after['legacy-cafe']['variant_id']), ('cafe', None))
            self.assertEqual((after['seeded-cafe']['scenario_id'], after['seeded-cafe']['variant_id']), ('cafe', 'cafe-for-two-v1'))
            for sid in ('unknown', 'malformed'):
                self.assertIsNone(after[sid]['scenario_id'])
                self.assertIsNone(after[sid]['variant_id'])
            for sid, original in before.items():
                self.assertEqual({key: after[sid][key] for key in original}, original)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM speaking_scenarios').fetchone()[0], 5)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM speaking_scenario_variants').fetchone()[0], 16)


if __name__ == '__main__':
    unittest.main()
