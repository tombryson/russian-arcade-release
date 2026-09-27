"""The teaching revision adds state without rewriting v1 work or receipts."""
import shutil
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import migrations


class FirstDeliveryTeachingMigrationTests(unittest.TestCase):
    def test_migration_preserves_old_attempts_answers_and_reward_receipts(self):
        with tempfile.TemporaryDirectory(prefix='first-delivery-teaching-migration-') as temporary:
            root = Path(temporary)
            migration_dir = root / 'migrations'
            migration_dir.mkdir()
            for file in migrations.MIGRATION_DIR.glob('*.sql'):
                if int(file.name.split('_')[0]) <= 27:
                    shutil.copy(file, migration_dir / file.name)
            database = str(root / 'vocab.db')
            with patch.object(migrations, 'MIGRATION_DIR', migration_dir):
                self.assertEqual(migrations.upgrade_database(database, backup=False), (27, None))
            with sqlite3.connect(database) as conn:
                partial = '{ "greeting": { "answer": "greeting", "correct": true, "hint_used": false, "answered_at": 102 } }'
                completed = '{ "greeting": { "answer": "greeting", "correct": true, "hint_used": false, "answered_at": 102 }, "letter": { "answer": "letter", "correct": true, "hint_used": true, "answered_at": 104 }, "thanks": { "answer": "hello", "correct": false, "hint_used": false, "answered_at": 106 } }'
                insert = 'INSERT INTO first_delivery_attempts VALUES (?,?,?,?,?,?,?,?,?,?)'
                conn.execute(insert, ('old-profile', 'personal-learning', None, 'first-delivery-v1', completed, '["letter"]', '["greeting","letter","thanks"]', 110, 100, 110))
                conn.execute(insert, ('old-guest', None, 'server-guest-token', 'first-delivery-v1', partial, '[]', '[]', None, 100, 102))
                conn.execute("INSERT INTO progression_events VALUES ('old-welcome','personal-learning','first_delivery','first-delivery-welcome','first-delivery-v1','Your first delivery','activity','A1',?,110,NULL)",
                             ('{"_skill":{"policy_version":"practice-elo-v1","task_rating":1000,"scores":{"reading":0.5}}}',))
                conn.execute("INSERT INTO progression_entries VALUES ('old-bonus','personal-learning','old-welcome','first-delivery-welcome:personal-learning',3,1,'activity','2026-09-15','Your first delivery','first-delivery-welcome-v1',110)")
                tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
                columns = {table: [row[1] for row in conn.execute('PRAGMA table_info("' + table + '")')] for table in tables}
                before = {table: sorted(conn.execute('SELECT * FROM "' + table + '"').fetchall(), key=repr) for table in tables}
            filename = '028_first_delivery_teaching.sql'
            shutil.copy(migrations.MIGRATION_DIR / filename, migration_dir / filename)
            with patch.object(migrations, 'MIGRATION_DIR', migration_dir):
                self.assertEqual(migrations.upgrade_database(database, backup=False), (28, None))
                self.assertEqual(migrations.upgrade_database(database, backup=False), (28, None))
            with sqlite3.connect(database) as conn:
                for table in tables:
                    selection = ','.join('"' + column + '"' for column in columns[table])
                    with self.subTest(table=table):
                        self.assertEqual(sorted(conn.execute('SELECT ' + selection + ' FROM "' + table + '"').fetchall(), key=repr), before[table])
                self.assertEqual(conn.execute('SELECT version,learned_json,previous_attempt_json FROM first_delivery_attempts ORDER BY id').fetchall(),
                                 [('first-delivery-v1', '[]', None), ('first-delivery-v1', '[]', None)])
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone(), ('ok',))
                self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
                for column in ('learned_json', 'previous_attempt_json'):
                    with self.subTest(column=column), self.assertRaises(sqlite3.IntegrityError):
                        conn.execute('UPDATE first_delivery_attempts SET ' + column + "='invalid json' WHERE id='old-profile'")


if __name__ == '__main__':
    unittest.main()
