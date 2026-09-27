"""Release-scoped preparation preserves old work and refuses unknown identity."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import migrations
from repositories.learning_repository import LearningError, encoded, payload_hash, timestamp
from services import course_releases, course_targets
from services.progression import personal_profile


class PracticeIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = str(Path(temporary.name) / 'saved.db')
        migrations.upgrade_database(self.path, backup=False)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.pid = personal_profile(self.conn)

    def test_release_scopes_active_attempts_and_explicit_requests(self):
        release = dict(course_releases.RELEASES['a1-journey-v2'], release_id='a1-test-edition')
        with patch.dict(course_releases.RELEASES, {'a1-test-edition': release}):
            first = course_targets.practice_start(self.conn, self.pid, 'home', 'first', release_id='a1-journey-v2')
            other = course_targets.practice_start(self.conn, self.pid, 'home', 'other', release_id='a1-test-edition')
            self.assertNotEqual(first['id'], other['id'])
            self.assertEqual(other['release_id'], 'a1-test-edition')
            self.assertEqual(other['coverage']['practice_href'], '/#journey/release/a1-test-edition/practice/start/home')
            self.assertEqual(first['id'], course_targets.practice_start(self.conn, self.pid, 'home', 'resume', release_id='a1-journey-v2')['id'])
            with self.assertRaises(LearningError) as error:
                course_targets.practice_start(self.conn, self.pid, 'home', 'first', release_id='a1-test-edition')
            self.assertEqual(error.exception.code, 'request_conflict')
            with self.assertRaises(LearningError):
                course_targets.practice_start(self.conn, self.pid, 'home', 'first')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_practice_attempts').fetchone()[0], 2)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)

    def test_new_attempt_uses_frozen_target_versions_and_titles(self):
        state = course_targets.practice_start(self.conn, self.pid, 'home', 'start')
        snapshot = json.loads(self.conn.execute('SELECT target_snapshot_json FROM course_target_practice_attempts').fetchone()[0])
        altered = deepcopy(snapshot)
        for target in altered['targets']:
            target.update(version=999, title_en='Changed later')
        with patch.object(course_targets, '_target_snapshot', return_value=altered):
            current = course_targets.practice_get(self.conn, self.pid, state['id'])
            self.assertEqual(current['coverage']['targets'][0]['title'], snapshot['targets'][0]['title_en'])
            course_targets.practice_action(self.conn, self.pid, state['id'], 'learn', {'item_id': state['current_item']['id']}, 'learn')
        observed = self.conn.execute('SELECT target_version,catalogue_version FROM course_target_observations').fetchone()
        self.assertEqual(tuple(observed), (1, 'a1-targets-v1'))

    def test_unknown_saved_versions_or_target_refs_cannot_write_evidence(self):
        state = course_targets.practice_start(self.conn, self.pid, 'home', 'start')
        row = dict(self.conn.execute('SELECT * FROM course_target_practice_attempts').fetchone())
        mutations = [('target_catalogue_version', 'unknown'), ('content_version', 'unknown')]
        items = json.loads(row['content_json']); items[0]['target_id'] = 'a1.invented.read'
        mutations.append(('content_json', encoded(items)))
        for field, value in mutations:
            with self.subTest(field=field):
                self.conn.execute(f'UPDATE course_target_practice_attempts SET {field}=?', (value,))
                with self.assertRaises(LearningError) as error:
                    course_targets.practice_action(self.conn, self.pid, state['id'], 'learn', {'item_id': state['current_item']['id']}, 'learn')
                self.assertEqual(error.exception.code, 'practice_content_unavailable')
                self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
                self.conn.execute(f'UPDATE course_target_practice_attempts SET {field}=?', (row[field],))


class PracticeIdentityMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scripts = self.root / 'migrations'; self.scripts.mkdir()
        self.path = self.root / 'saved.db'
        for path in migrations.MIGRATION_DIR.glob('*.sql'):
            if int(path.name.split('_')[0]) <= 47:
                shutil.copy(path, self.scripts / path.name)
        with patch.object(migrations, 'MIGRATION_DIR', self.scripts):
            self.assertEqual(migrations.upgrade_database(str(self.path), backup=False), (47, None))
        targets = {t['id'] for t in course_targets.targets_for_section('home', required_only=True)}
        items = [item for item in course_targets.practice_catalogue()['items'] if item['target_id'] in targets]
        self.item_id = items[0]['id']
        self.receipt = {'id': 'old-attempt', 'original': 'saved response', 'coverage': {'prepared_count': 1}}
        with sqlite3.connect(self.path) as conn:
            self.pid = personal_profile(conn)
            conn.execute('''INSERT INTO course_target_practice_attempts
                (id,profile_id,section_id,content_version,content_json,state_json,created_at)
                VALUES ('old-attempt',?,'home','a1-target-practice-v1',?,?,1)''',
                (self.pid, json.dumps(items, ensure_ascii=False, indent=2), json.dumps({self.item_id: {'learned': True}}, indent=1)))
            conn.execute('INSERT INTO course_target_practice_requests VALUES (?,?,?,?)',
                (self.pid, 'old-start', payload_hash({'section_id': 'home'}), 'old-attempt'))
            conn.execute('INSERT INTO course_target_practice_receipts VALUES (?,?,?,?,?,?)',
                (self.pid, 'old-learn', 'old-attempt', payload_hash({'attempt_id': 'old-attempt', 'action': 'learn', 'item_id': self.item_id, 'choice_id': None}), json.dumps(self.receipt, indent=3), 2))
        self.before = self.snapshot()

    def snapshot(self):
        with sqlite3.connect(self.path) as conn:
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
            return {table: ([row[1] for row in conn.execute('PRAGMA table_info("' + table + '")')],
                            sorted(conn.execute('SELECT * FROM "' + table + '"').fetchall(), key=repr)) for table in tables}

    def upgrade(self):
        filename = '048_course_practice_identity.sql'
        shutil.copy(migrations.MIGRATION_DIR / filename, self.scripts / filename)
        with patch.object(migrations, 'MIGRATION_DIR', self.scripts):
            return migrations.upgrade_database(str(self.path), backup=False)

    def assert_unchanged(self, snapshot):
        with sqlite3.connect(self.path) as conn:
            for table, (columns, values) in snapshot.items():
                with self.subTest(table=table):
                    selection = ','.join('"' + name + '"' for name in columns)
                    self.assertEqual(sorted(conn.execute('SELECT ' + selection + ' FROM "' + table + '"').fetchall(), key=repr), values)

    def test_populated_047_upgrade_keeps_all_old_columns_and_receipts(self):
        self.assertEqual(self.upgrade(), (48, None))
        self.assertEqual(self.upgrade(), (48, None))
        self.assert_unchanged(self.before)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM course_target_practice_attempts').fetchone()
            self.assertEqual((row['release_id'], row['target_catalogue_version'], row['target_snapshot_json']), ('a1-journey-v2', 'a1-targets-v1', None))
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            # An old explicit release request had the section-only fingerprint.
            state = course_targets.practice_start(conn, self.pid, 'home', 'old-start', release_id='a1-journey-v2', enrol=True)
            self.assertEqual(state['id'], 'old-attempt')
            self.assertEqual(state['current_item']['stage'], 'question')
            self.assertEqual(course_targets.practice_action(conn, self.pid, 'old-attempt', 'learn', {'item_id': self.item_id}, 'old-learn'), self.receipt)
        self.assert_unchanged(self.before)

    def test_unknown_history_aborts_without_schema_or_row_changes(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE course_target_practice_attempts SET content_version='unknown-edition'")
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.upgrade()
        self.assert_unchanged(before)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(migrations.schema_version(conn), 47)
            self.assertNotIn('release_id', [row[1] for row in conn.execute('PRAGMA table_info(course_target_practice_attempts)')])

    def test_orphan_owned_receipt_aborts_atomically(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE course_target_practice_receipts SET profile_id='missing-profile'")
        before = self.snapshot()
        with self.assertRaises((sqlite3.IntegrityError, ValueError)):
            self.upgrade()
        self.assert_unchanged(before)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(migrations.schema_version(conn), 47)

    def test_unknown_saved_item_target_cannot_inherit_a_catalogue_identity(self):
        with sqlite3.connect(self.path) as conn:
            items = json.loads(conn.execute('SELECT content_json FROM course_target_practice_attempts').fetchone()[0])
            items[0]['target_id'] = 'a1.home.unrecognised.read'
            conn.execute('UPDATE course_target_practice_attempts SET content_json=?', (encoded(items),))
        before = self.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.upgrade()
        self.assert_unchanged(before)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(migrations.schema_version(conn), 47)

    def test_audit_covers_preparation_receipts_and_refuses_unknown_content(self):
        script = Path(__file__).resolve().parents[2] / 'scripts' / 'audit_course_migration.py'
        spec = importlib.util.spec_from_file_location('course_identity_audit', script)
        audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
        with sqlite3.connect(self.path) as conn:
            report = audit.inventory(conn)
            self.assertEqual(report['counts']['course_target_practice_receipts'], 1)
            self.assertEqual(report['unknown_preparations'], 0)
            conn.execute("UPDATE course_target_practice_attempts SET content_version='unrecognised'")
            self.assertEqual(audit.inventory(conn)['unknown_preparations'], 1)


if __name__ == '__main__':
    unittest.main()
