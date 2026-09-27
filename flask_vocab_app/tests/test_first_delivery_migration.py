"""Migration 027 preserves existing learning data and constrains attempt owners."""
import shutil
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import migrations


class FirstDeliveryMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='first-delivery-migration-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.migration_dir = self.root / 'migrations'
        self.migration_dir.mkdir()
        for file in migrations.MIGRATION_DIR.glob('*.sql'):
            if int(file.name.split('_')[0]) <= 26:
                shutil.copy(file, self.migration_dir / file.name)
        self.database = str(self.root / 'vocab.db')
        with patch.object(migrations, 'MIGRATION_DIR', self.migration_dir):
            self.assertEqual(migrations.upgrade_database(self.database, backup=False), (26, None))
        migrations.seed_demo(self.database)

    def upgrade(self):
        filename = '027_first_delivery.sql'
        shutil.copy(migrations.MIGRATION_DIR / filename, self.migration_dir / filename)
        with patch.object(migrations, 'MIGRATION_DIR', self.migration_dir):
            self.assertEqual(migrations.upgrade_database(self.database, backup=False), (27, None))

    def test_upgrade_preserves_all_original_rows_without_inventing_completion(self):
        with sqlite3.connect(self.database) as conn:
            conn.execute('UPDATE users SET lingocoins=87,elo_rating=1400 WHERE user_id=1')
            conn.execute("UPDATE profile_onboarding SET coins_introduced_at=100,progress_introduced_at=101 WHERE profile_id='personal-learning'")
            conn.execute("INSERT INTO progression_events VALUES ('old-reading','personal-learning','reading','old-story','old-content','Saved reading','activity','A1',?,102,NULL)",
                         ('{"score":8,"_skill":{"policy_version":"practice-elo-v1","task_rating":1000,"scores":{"reading":0.8}}}',))
            conn.execute("INSERT INTO progression_entries VALUES ('old-coins','personal-learning','old-reading','old-operation',3,1,'activity','2026-09-15','Saved reading','shared-participation-v2',102)")
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
            before = {table: sorted(conn.execute('SELECT * FROM "' + table + '"').fetchall(), key=repr) for table in tables}
            columns = {table: conn.execute('PRAGMA table_info("' + table + '")').fetchall() for table in tables}
        self.upgrade()
        with sqlite3.connect(self.database) as conn:
            for table in tables:
                with self.subTest(table=table):
                    self.assertEqual(conn.execute('PRAGMA table_info("' + table + '")').fetchall(), columns[table])
                    self.assertEqual(sorted(conn.execute('SELECT * FROM "' + table + '"').fetchall(), key=repr), before[table])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_delivery_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone(), ('ok',))
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        # A second application is a no-op, including its welcome entitlement.
        self.upgrade()
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_delivery_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 1)

    def test_attempt_owner_is_exactly_one_unique_profile_or_guest(self):
        self.upgrade()
        with sqlite3.connect(self.database) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            insert = 'INSERT INTO first_delivery_attempts(id,profile_id,guest_token,version,created_at,updated_at) VALUES (?,?,?,?,1,1)'
            conn.execute(insert, ('profile-attempt', 'personal-learning', None, 'first-delivery-v1'))
            conn.execute(insert, ('guest-attempt', None, 'guest-owner', 'first-delivery-v1'))
            invalid = (
                ('unowned', None, None),
                ('two-owners', 'personal-learning', 'second-guest'),
                ('duplicate-profile', 'personal-learning', None),
                ('duplicate-guest', None, 'guest-owner'),
                ('foreign-profile', 'missing-profile', None),
            )
            for attempt_id, profile, guest in invalid:
                with self.subTest(attempt=attempt_id), self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(insert, (attempt_id, profile, guest, 'first-delivery-v1'))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE first_delivery_attempts SET answers_json='invalid json' WHERE id='profile-attempt'")
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM first_delivery_attempts').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
