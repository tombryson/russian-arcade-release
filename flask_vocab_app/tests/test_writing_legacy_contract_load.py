"""Legacy word-list fallback does not weaken frozen Writing evidence checks."""
import sqlite3
import unittest
from unittest.mock import Mock

from repositories.writing_repository import WritingRepository
from services.activity_evidence import load_contract, reports_for_task
from services.writing_service import WritingService
from tests.support import isolated_app
from tests.test_writing_curriculum_evidence import TASK, contract


class LegacyWritingContractLoadTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock(spec=WritingService)
        self.app = isolated_app(self, {'WritingService': self.service})
        self.db = self.app.config['DB_PATH']
        self.repo = WritingRepository(self.db)
        self.client = self.app.test_client()
        self.client.get('/api/v1/user-session')

    def replace_words(self, exercise_id, raw):
        with sqlite3.connect(self.db) as conn:
            conn.execute('UPDATE writing_exercises SET required_words=? WHERE id=?', (raw, exercise_id))

    def test_contractless_legacy_words_list_and_load_with_empty_fallback(self):
        exercise_id = self.repo.create(TASK, 'home', 'A1', 30)
        for raw in ('[broken', '', 'null', '{"word":"парк"}', '"парк"'):
            with self.subTest(raw=raw):
                self.replace_words(exercise_id, raw)
                listed = next(item for item in self.repo.list_saved() if item['id'] == exercise_id)
                self.assertEqual(listed['required_words'], [])
                loaded = self.repo.load(exercise_id)
                self.assertEqual(loaded['required_words'], [])
                self.assertIsNone(loaded['curriculum_contract'])
                self.assertEqual(loaded['attempts'], [])
                self.assertEqual(self.client.get(f'/writing/load/{exercise_id}').status_code, 200)
                with sqlite3.connect(self.db) as conn:
                    self.assertEqual(conn.execute('SELECT required_words FROM writing_exercises WHERE id=?',
                                                  (exercise_id,)).fetchone()[0], raw)
        self.service.assess_writing.assert_not_called()

    def test_contractless_lookup_still_checks_ownership_and_identity(self):
        exercise_id = self.repo.create(TASK, 'home', 'A1', 30)
        self.replace_words(exercise_id, '[broken')
        with sqlite3.connect(self.db) as conn:
            for lookup in (load_contract, reports_for_task):
                with self.subTest(lookup=lookup.__name__):
                    with self.assertRaises(LookupError):
                        lookup(conn, 'another-profile', 'writing', str(exercise_id))
                    with self.assertRaises(LookupError):
                        lookup(conn, 'personal-learning', 'writing', '999999')
                    with self.assertRaises(ValueError):
                        lookup(conn, 'personal-learning', 'writing', f'0{exercise_id}')

    def test_contracted_words_remain_strict_on_load_and_report_lookup(self):
        exercise_id = self.repo.create({**TASK, 'curriculum_contract': contract()}, 'home', 'A1', 30)
        for raw in ('[broken', 'null', '[]', '["Changed"]', '{"word":"парк"}'):
            with self.subTest(raw=raw):
                self.replace_words(exercise_id, raw)
                with self.assertRaises(ValueError):
                    self.repo.load(exercise_id)
                with sqlite3.connect(self.db) as conn:
                    for lookup in (load_contract, reports_for_task):
                        with self.assertRaises(ValueError):
                            lookup(conn, 'personal-learning', 'writing', str(exercise_id))
