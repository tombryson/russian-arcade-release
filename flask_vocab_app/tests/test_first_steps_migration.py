"""Migration029 adds owned chapter attempts without rewriting learning history."""
import shutil
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import migrations


class FirstStepsMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='first-steps-migration-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.migration_dir = root / 'migrations'
        self.migration_dir.mkdir()
        for file in migrations.MIGRATION_DIR.glob('*.sql'):
            if int(file.name.split('_')[0]) <= 28:
                shutil.copy(file, self.migration_dir / file.name)
        self.db = str(root / 'vocab.db')
        with patch.object(migrations, 'MIGRATION_DIR', self.migration_dir):
            self.assertEqual(migrations.upgrade_database(self.db, backup=False), (28, None))
        migrations.seed_demo(self.db)

    def upgrade(self):
        filename = '029_first_steps.sql'
        shutil.copy(migrations.MIGRATION_DIR / filename, self.migration_dir / filename)
        with patch.object(migrations, 'MIGRATION_DIR', self.migration_dir):
            self.assertEqual(migrations.upgrade_database(self.db, backup=False), (29, None))

    def test_additive_upgrade_keeps_all_old_schema_rows_and_does_not_invent_chapter_progress(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO first_delivery_attempts(id,profile_id,version,answers_json,hints_json,acknowledged_json,completed_at,created_at,updated_at) VALUES ('old-first','personal-learning','first-delivery-v1','{}','[]','[]',123,100,123)")
            conn.execute("INSERT INTO first_delivery_attempts(id,guest_token,version,learned_json,answers_json,hints_json,acknowledged_json,created_at,updated_at) VALUES ('guest-first','old-guest-owner','first-delivery-v2','[\"word-hello\"]','{}','[]','[]',101,124)")
            conn.execute("UPDATE users SET lingocoins=87,elo_rating=1400 WHERE user_id=1")
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
            rows = {table: sorted(conn.execute('SELECT * FROM "' + table + '"').fetchall(), key=repr) for table in tables}
            schema = {table: conn.execute('PRAGMA table_info("' + table + '")').fetchall() for table in tables}
        self.upgrade()
        self.upgrade()
        with sqlite3.connect(self.db) as conn:
            for table in tables:
                with self.subTest(table=table):
                    self.assertEqual(sorted(conn.execute('SELECT * FROM "' + table + '"').fetchall(), key=repr), rows[table])
                    self.assertEqual(conn.execute('PRAGMA table_info("' + table + '")').fetchall(), schema[table])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_steps_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone(), ('ok',))
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_attempts_require_unique_owned_lesson_and_valid_frozen_json(self):
        self.upgrade()
        with sqlite3.connect(self.db) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            insert = 'INSERT INTO first_steps_attempts(id,profile_id,guest_token,chapter_id,lesson_id,version,content_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,1,1)'
            conn.execute(insert, ('profile-bag', 'personal-learning', None, 'first-steps', 'bag', 'v1', '{}'))
            conn.execute(insert, ('guest-bag', None, 'guest-owner', 'first-steps', 'bag', 'v1', '{}'))
            conn.execute(insert, ('profile-help', 'personal-learning', None, 'first-steps', 'help', 'v1', '{}'))
            for attempt, profile, guest, content in (
                    ('unowned', None, None, '{}'),
                    ('double-owned', 'personal-learning', 'another-guest', '{}'),
                    ('duplicate-profile', 'personal-learning', None, '{}'),
                    ('duplicate-guest', None, 'guest-owner', '{}'),
                    ('foreign-profile', 'missing-profile', None, '{}'),
                    ('bad-json', None, 'bad-json-owner', 'not json')):
                with self.subTest(attempt=attempt), self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(insert, (attempt, profile, guest, 'first-steps', 'bag', 'v1', content))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE first_steps_attempts SET reward_amount=-1 WHERE id='profile-bag'")
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_steps_attempts').fetchone()[0], 3)


if __name__ == '__main__':
    unittest.main()
