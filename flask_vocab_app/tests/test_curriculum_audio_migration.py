"""The v4 migration changes only an unrecorded job's model and settings."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from migrations import schema_version, upgrade_database
from repositories.learning_repository import encoded


class CurriculumAudioMigrationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        migrations = Path(__file__).resolve().parents[1] / 'migrations'
        self.conn.executescript((migrations / '064_curriculum_situations.sql').read_text())
        self.spec = {'version': 'curriculum-generated-audio-v1', 'provider': 'elevenlabs',
                     'model': 'eleven_multilingual_v2', 'voice_id': 'chosen-voice',
                     'text': 'Это письмо.', 'transcript_sha256': 'frozen-hash',
                     'voice_settings': {'stability': 0.8, 'similarity_boost': 0.85, 'style': 0.0}}
        self.original = encoded(self.spec)
        self.upgraded = {**self.spec, 'model': 'eleven_v4', 'voice_settings': {'stability': 0.8, 'similarity_boost': 0.85}}
        self.conn.execute("INSERT INTO curriculum_situations(id,profile_id,unit_id,mode,request_json,voice_json,state,stage,created_at,updated_at) "
                          "VALUES ('pending','owner','unit','listening','{}',?,'running','audio',1,1)", (self.original,))
        self.conn.execute("INSERT INTO curriculum_situations(id,profile_id,unit_id,mode,request_json,voice_json,audio_json,state,stage,created_at,updated_at) "
                          "VALUES ('saved','owner','unit','listening','{}',?,'{\"spec_sha256\":\"original-hash\"}','ready','ready',1,1)", (self.original,))
        self.conn.commit()
        self.conn.executescript((migrations / '065_curriculum_audio_v4.sql').read_text())

    def test_migration_keeps_existing_specs_and_audio_hashes_unchanged(self):
        for voice, audio in self.conn.execute('SELECT voice_json,audio_json FROM curriculum_situations'):
            self.assertEqual(voice, self.original)
            if audio:
                self.assertEqual(json.loads(audio), {'spec_sha256': 'original-hash'})

    def test_pending_claim_can_upgrade_only_model_and_supported_settings(self):
        self.conn.execute("UPDATE curriculum_situations SET voice_json=? WHERE id='pending'", (encoded(self.upgraded),))
        self.assertEqual(json.loads(self.conn.execute("SELECT voice_json FROM curriculum_situations WHERE id='pending'").fetchone()[0]), self.upgraded)

    def test_upgrade_cannot_change_voice_transcript_provider_or_other_fields(self):
        changes = [('voice_id', 'other'), ('text', 'Другой текст.'), ('transcript_sha256', 'other'),
                   ('provider', 'other'), ('version', 'other'), ('model', 'eleven_v3'),
                   ('voice_settings', {'stability': 0.8, 'similarity_boost': 0.85, 'style': 0.0}),
                   ('voice_settings', {'stability': 0.5, 'similarity_boost': 0.85})]
        for field, value in changes:
            with self.subTest(field=field, value=value), self.assertRaisesRegex(sqlite3.IntegrityError, 'Selected voice is immutable'):
                self.conn.execute("UPDATE curriculum_situations SET voice_json=? WHERE id='pending'", (encoded({**self.upgraded, field: value}),))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE curriculum_situations SET voice_json=NULL WHERE id='pending'")

    def test_saved_audio_and_publication_stage_cannot_be_upgraded(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE curriculum_situations SET voice_json=? WHERE id='saved'", (encoded(self.upgraded),))
        self.conn.execute("UPDATE curriculum_situations SET stage='publish' WHERE id='pending'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE curriculum_situations SET voice_json=? WHERE id='pending'", (encoded(self.upgraded),))
        self.conn.execute("UPDATE curriculum_situations SET stage='audio',audio_json='{}' WHERE id='pending'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE curriculum_situations SET voice_json=? WHERE id='pending'", (encoded(self.upgraded),))

    def test_upgrade_from_64_backs_up_original_data_and_rolls_back_on_failure(self):
        migrations = Path(__file__).resolve().parents[1] / 'migrations'
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'saved.db'
            with sqlite3.connect(db) as conn:
                conn.executescript("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY); INSERT INTO schema_migrations VALUES(64);"
                                   "CREATE TABLE learning_profiles(id TEXT PRIMARY KEY); INSERT INTO learning_profiles VALUES('owner');"
                                   "CREATE TABLE learning_sessions(id TEXT PRIMARY KEY);")
                conn.executescript((migrations / '064_curriculum_situations.sql').read_text())
                conn.execute("INSERT INTO curriculum_situations(id,profile_id,unit_id,mode,request_json,voice_json,state,stage,created_at,updated_at) "
                             "VALUES ('pending','owner','unit','listening','{}',?,'running','audio',1,1)", (self.original,))
            failing = Path(directory) / 'migrations'
            failing.mkdir()
            (failing / '065_curriculum_audio_v4.sql').write_text((migrations / '065_curriculum_audio_v4.sql').read_text())
            (failing / '066_invalid.sql').write_text('THIS IS INVALID SQL;')
            with patch('migrations.MIGRATION_DIR', failing), self.assertRaises(sqlite3.OperationalError):
                upgrade_database(db, backup=False)
            with sqlite3.connect(db) as conn:
                self.assertEqual(schema_version(conn), 64)
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("UPDATE curriculum_situations SET voice_json=? WHERE id='pending'", (encoded(self.upgraded),))
            version, backup = upgrade_database(db)
            self.assertEqual(version, 65)
            with sqlite3.connect(backup) as conn:
                self.assertEqual(schema_version(conn), 64)
                self.assertEqual(conn.execute('SELECT voice_json FROM curriculum_situations').fetchone()[0], self.original)
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute('SELECT voice_json FROM curriculum_situations').fetchone()[0], self.original)
                conn.execute("UPDATE curriculum_situations SET voice_json=? WHERE id='pending'", (encoded(self.upgraded),))


if __name__ == '__main__':
    unittest.main()
