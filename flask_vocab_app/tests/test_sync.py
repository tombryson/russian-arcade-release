import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from models.database import connect_db
from services.google_drive_service import GoogleDriveService
from services.sync_service import SyncService
from tests.support import isolated_app


class MemoryDrive:
    def __init__(self, content):
        self.content = content
        self.reads = []
        self.fail_export = False

    def download_vocab_list(self, **kwargs):
        self.reads.append(kwargs)
        return self.content

    def append_words(self, words):
        if self.fail_export:
            raise RuntimeError('Drive unavailable')
        self.content += '\n' + '\n'.join(words)
        return True


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.db = self.app.config['DB_PATH']
        self.drive = MemoryDrive('МАШИНА\nмашины\n')
        self.service = SyncService(self.db, drive_service=self.drive, api_key='')

    def test_preview_is_fresh_and_read_only(self):
        before = Path(self.db).read_bytes()
        db_only, cloud_only, error = self.service.compare_vocab()
        self.assertIsNone(error)
        self.assertIn('машина', cloud_only)
        self.assertIn('кофе', db_only)
        self.assertEqual(self.drive.reads, [{'force_refresh':True, 'allow_stale':False}])
        self.assertEqual(Path(self.db).read_bytes(), before)
        self.assertFalse(list(Path(self.db).parent.glob('*.bak')))

    def test_import_normalizes_inflections_and_retains_data_on_retry(self):
        result = self.service.sync_vocab(['МАШИНА', 'машины'])
        self.assertEqual(result['imported'], ['машина'])
        self.assertEqual(result['enrichment_pending'], ['машина'])
        self.assertEqual(result['status'], 'partial')
        with connect_db(self.db) as conn:
            word = conn.execute("SELECT id FROM words WHERE lemma='машина'").fetchone()[0]
            conn.execute("UPDATE words SET mnemonic='custom', topic='[\"travel\"]', count=5 WHERE id=?", (word,))
            forms = conn.execute('SELECT * FROM forms WHERE word_id=?', (word,)).fetchall()
        repeated = self.service.sync_vocab(['МАШИНА', 'машины'])
        self.assertEqual(repeated['imported'], [])
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute("SELECT mnemonic,topic,count FROM words WHERE id=?", (word,)).fetchone(), ('custom','["travel"]',5))
            self.assertEqual(conn.execute('SELECT * FROM forms WHERE word_id=?', (word,)).fetchall(), forms)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM sync_runs').fetchone()[0], 2)
        self.assertIn('кофе', self.drive.content)

    def test_mobile_removal_never_deletes_sqlite_history(self):
        self.drive.content = ''
        result = self.service.sync_vocab([])
        self.assertEqual(result['imported'], [])
        self.assertIn('кофе', result['exported'])
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], 3)

    def test_changed_capture_fails_before_writing(self):
        before = Path(self.db).read_bytes()
        with self.assertRaisesRegex(ValueError, 'Drive changed'):
            self.service.sync_vocab(['кошка'])
        self.assertEqual(Path(self.db).read_bytes(), before)

    def test_failed_word_import_rolls_back_partial_rows(self):
        def fail(lemma, conn, cursor):
            cursor.execute("INSERT INTO words(lemma,pos,lemma_difficulty) VALUES (?,'NOUN',1)", (lemma,))
            return False
        with patch.object(self.service, 'process_word', side_effect=fail):
            result = self.service.sync_vocab(['машина'])
        self.assertEqual(result['failed'], ['машина'])
        with connect_db(self.db) as conn:
            self.assertIsNone(conn.execute("SELECT id FROM words WHERE lemma='машина'").fetchone())

    def test_unexpected_import_failure_does_not_claim_rolled_back_words(self):
        def fail(lemma, conn, cursor):
            cursor.execute("INSERT INTO words(lemma,pos,lemma_difficulty) VALUES (?,'NOUN',1)", (lemma,))
            raise RuntimeError('unexpected failure')
        with patch.object(self.service, 'process_word', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'unexpected failure'):
                self.service.sync_vocab(['машина'])
        with connect_db(self.db) as conn:
            self.assertIsNone(conn.execute("SELECT id FROM words WHERE lemma='машина'").fetchone())
            summary = json.loads(conn.execute('SELECT summary FROM sync_runs').fetchone()[0])
            self.assertEqual(summary['status'], 'failed')
            self.assertEqual(summary['imported'], [])

    def test_export_failure_is_visible_and_import_survives(self):
        self.drive.fail_export = True
        result = self.service.sync_vocab(['машина'])
        self.assertEqual(result['imported'], ['машина'])
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['warnings'])
        with connect_db(self.db) as conn:
            summary = json.loads(conn.execute('SELECT summary FROM sync_runs').fetchone()[0])
            self.assertEqual(summary['status'], 'partial')
            self.assertIsNotNone(conn.execute("SELECT id FROM words WHERE lemma='машина'").fetchone())

    def test_route_revalidates_selected_capture_and_exposes_history(self):
        app = isolated_app(self, {'SyncService': self.service})
        client = app.test_client()
        headers = {'X-CSRF-Token': client.get('/api/v1/user-session').json['csrf_token']}
        self.assertEqual(client.post('/sync',headers=headers,json={'to_add':[{'word':17}]}).status_code,400)
        self.assertEqual(client.post('/sync',headers=headers,json={'to_add':[{'word':'removed'}]}).status_code,400)
        response = client.post('/sync',headers=headers,json={'to_add':[{'word':'машина','lemma':'arbitrary-client-value'}]})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['imported'], ['машина'])
        self.assertEqual(client.get('/sync/history').status_code,200)

    def test_enrichment_happens_outside_database_write_transaction(self):
        self.service.api_key = 'test-only'
        def topics(words):
            with connect_db(self.db, timeout=0) as conn:
                conn.execute("UPDATE users SET elo_rating=elo_rating WHERE user_id=1")
            return {'машина':['travel']}
        with patch.object(self.service,'assign_topics',side_effect=topics), patch.object(self.service,'assign_mnemonics',return_value={'машина':'A memorable car'}):
            result = self.service.sync_vocab(['машина'])
        self.assertEqual(result['status'], 'completed')


class DriveCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.service = GoogleDriveService(cache_file=Path(self.temporary.name)/'cache.txt')
        self.service.CACHE_FILE.write_text('кофе\n')

    def test_adding_word_reads_fresh_mobile_content_before_rewriting(self):
        class Downloader:
            def __init__(self, output, request):
                self.output = output
            def next_chunk(self):
                self.output.write('кофе\nмашина\n'.encode())
                return SimpleNamespace(progress=lambda:1), True
        self.service.service = Mock()
        with patch('services.google_drive_service.MediaIoBaseDownload', Downloader), patch.object(self.service,'_upload_words') as upload:
            self.assertTrue(self.service.add_word('семья'))
        upload.assert_called_once_with(['кофе','машина','семья'])

    def test_failed_fresh_read_never_uploads_a_stale_list(self):
        with patch.object(self.service,'_ensure_service',side_effect=RuntimeError('offline')), patch('services.google_drive_service.time.sleep'), patch.object(self.service,'_upload_words') as upload:
            with self.assertRaisesRegex(Exception, 'offline'):
                self.service.add_word('семья')
            upload.assert_not_called()
            self.assertEqual(self.service.CACHE_FILE.read_text(), 'кофе\n')

    def test_read_only_browsing_can_use_cache(self):
        with patch.object(self.service,'_ensure_service',side_effect=AssertionError('Unnecessary network call')):
            self.assertEqual(self.service.download_vocab_list(), 'кофе\n')
