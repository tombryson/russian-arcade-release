"""All capture paths use the importer's post-commit vocabulary enrichment."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from models.database import connect_db
from services.ai_trial_budget import TrialDenied
from services.sync_service import SyncService


class VocabularyEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = str(Path(self.temporary.name) / 'vocab.db')
        with connect_db(self.db) as conn:
            baseline = Path(__file__).resolve().parents[1] / 'migrations' / '001_baseline.sql'
            conn.executescript(baseline.read_text())
            conn.execute('CREATE TABLE sync_runs (id INTEGER PRIMARY KEY, status TEXT, summary TEXT, finished_at TEXT)')
        self.drive = Mock()
        self.drive.download_vocab_list.return_value = 'машина'
        self.drive.append_words.return_value = True
        self.service = SyncService(self.db, drive_service=self.drive, api_key='test-only', config={})

    def add(self, lemma='машина', pos='NOUN', topic=None, mnemonic=None):
        with connect_db(self.db) as conn:
            return conn.execute('''INSERT INTO words(lemma,pos,topic,mnemonic,count,lemma_difficulty)
                                   VALUES (?,?,?,?,9,4)''', (lemma, pos, topic, mnemonic)).lastrowid

    def word(self, word_id):
        with connect_db(self.db) as conn:
            return conn.execute('SELECT * FROM words WHERE id=?', (word_id,)).fetchone()

    def test_missing_fields_use_existing_assigners_without_a_write_lock(self):
        word_id = self.add(topic='[]', mnemonic='  ')
        def topics(words):
            self.assertEqual([(w['id'], w['lemma'], w['pos']) for w in words], [(word_id, 'машина', 'NOUN')])
            with connect_db(self.db, timeout=0) as conn:
                conn.execute('UPDATE words SET count=count WHERE id=?', (word_id,))
            return {'машина': ['travel']}
        def mnemonics(words):
            with connect_db(self.db, timeout=0) as conn:
                conn.execute('UPDATE words SET count=count WHERE id=?', (word_id,))
            return {'машина': 'Machine-a car zooms away.'}
        with patch.object(self.service, 'assign_topics', side_effect=topics), patch.object(self.service, 'assign_mnemonics', side_effect=mnemonics):
            result = self.service.enrich_words([word_id])
        self.assertEqual(result['completed'], [word_id])
        self.assertEqual(result['pending'], [])
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT topic,mnemonic,count,lemma_difficulty FROM words').fetchone(),
                             ('["travel"]', 'Machine-a car zooms away.', 9, 4))

    def test_existing_enrichment_is_preserved_and_not_sent_to_provider(self):
        finished = self.add(topic='["travel"]', mnemonic='My own clue')
        missing_mnemonic = self.add('дом', topic='["home"]')
        missing_topic = self.add('кошка', mnemonic='My cat clue')
        snapshot = self.word(finished)
        with patch.object(self.service, 'assign_topics', return_value={'кошка': ['animals']}) as topics, patch.object(self.service, 'assign_mnemonics', return_value={'дом': 'Domed home.'}) as mnemonics:
            result = self.service.enrich_words([finished, missing_mnemonic, missing_topic])
        self.assertEqual(self.word(finished), snapshot)
        self.assertEqual([w['id'] for w in topics.call_args.args[0]], [missing_topic])
        self.assertEqual([w['id'] for w in mnemonics.call_args.args[0]], [missing_mnemonic])
        self.assertCountEqual(result['completed'], [finished, missing_mnemonic, missing_topic])

    def test_legacy_fallbacks_are_retryable_and_invalid_results_are_not_saved(self):
        word_id = self.add(topic='["generic"]', mnemonic='Recall машина phonetically.')
        snapshot = self.word(word_id)
        with patch.object(self.service, 'assign_topics', return_value={'машина': ['First steps']}), patch.object(self.service, 'assign_mnemonics', return_value={'машина': 'Recall машина phonetically.'}):
            self.assertEqual(self.service.enrich_words([word_id])['pending'], [word_id])
        self.assertEqual(self.word(word_id), snapshot)
        with patch.object(self.service, 'assign_topics', return_value={'машина': ['travel']}), patch.object(self.service, 'assign_mnemonics', return_value={'машина': 'Machine-a car zooms away.'}):
            self.assertEqual(self.service.enrich_words([word_id])['completed'], [word_id])

    def test_provider_failure_keeps_valid_partial_enrichment_for_retry(self):
        word_id = self.add()
        with patch.object(self.service, 'assign_topics', side_effect=RuntimeError('offline')), patch.object(self.service, 'assign_mnemonics', return_value={'машина': 'Machine-a car zooms away.'}):
            result = self.service.enrich_words([word_id])
        self.assertEqual(result['pending'], [word_id])
        self.assertTrue(result['warnings'])
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT topic,mnemonic FROM words').fetchone(), (None, 'Machine-a car zooms away.'))
        with patch.object(self.service, 'assign_topics', return_value={'машина': ['travel']}), patch.object(self.service, 'assign_mnemonics') as mnemonics:
            self.assertEqual(self.service.enrich_words([word_id])['completed'], [word_id])
            mnemonics.assert_not_called()

    def test_concurrent_user_edits_win_over_generated_values(self):
        word_id = self.add()
        def mnemonic(words):
            with connect_db(self.db) as conn:
                conn.execute('UPDATE words SET mnemonic=?,topic=? WHERE id=?', ('My new clue', '["technology"]', word_id))
            return {'машина': 'Machine-a car zooms away.'}
        with patch.object(self.service, 'assign_topics', return_value={'машина': ['travel']}), patch.object(self.service, 'assign_mnemonics', side_effect=mnemonic):
            result = self.service.enrich_words([word_id])
        self.assertEqual(result['updated'], [])
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT topic,mnemonic FROM words').fetchone(), ('["technology"]', 'My new clue'))

    def test_homographs_are_enriched_in_separate_calls_with_their_parts_of_speech(self):
        noun = self.add('печь', 'NOUN')
        verb = self.add('печь', 'VERB')
        def topics(words):
            self.assertEqual(len(words), 1)
            return {'печь': ['home' if words[0]['pos'] == 'NOUN' else 'cuisine']}
        def mnemonic(words):
            return {'печь': 'Pech stove.' if words[0]['pos'] == 'NOUN' else 'Pech bakes pies.'}
        with patch.object(self.service, 'assign_topics', side_effect=topics), patch.object(self.service, 'assign_mnemonics', side_effect=mnemonic):
            result = self.service.enrich_words([noun, verb])
        self.assertEqual(result['completed'], [noun, verb])
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT topic,mnemonic FROM words ORDER BY id').fetchall(),
                             [('["home"]', 'Pech stove.'), ('["cuisine"]', 'Pech bakes pies.')])

    def test_no_key_keeps_fields_empty_and_budget_denials_propagate(self):
        word_id = self.add()
        self.service.api_key = ''
        with patch.object(self.service, 'assign_topics') as topics, patch.object(self.service, 'assign_mnemonics') as mnemonics:
            self.assertEqual(self.service.enrich_words([word_id])['pending'], [word_id])
            topics.assert_not_called()
            mnemonics.assert_not_called()
        self.service.api_key = 'test-only'
        with patch.object(self.service, 'assign_topics', side_effect=TrialDenied('Budget reached')):
            with self.assertRaises(TrialDenied):
                self.service.enrich_words([word_id])

    def test_reselecting_an_imported_capture_retries_missing_enrichment(self):
        word_id = self.add(topic='[]')
        with patch.object(self.service, 'assign_topics', return_value={'машина': ['travel']}), patch.object(self.service, 'assign_mnemonics', return_value={'машина': 'Machine-a car zooms away.'}):
            result = self.service.sync_vocab(['машина'])
        self.assertEqual(result['imported'], [])
        self.assertEqual(result['enrichment_pending'], [])
        self.assertEqual(result['status'], 'completed')
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT id,topic,mnemonic FROM words').fetchone(),
                             (word_id, '["travel"]', 'Machine-a car zooms away.'))

    def test_assigners_return_no_fake_values_when_generation_fails(self):
        self.service.openai_client = Mock()
        self.service.openai_client.chat.completions.create.side_effect = RuntimeError('offline')
        with patch('services.sync_service.time.sleep'):
            self.assertEqual(self.service.assign_topics([{'lemma': 'машина', 'pos': 'NOUN'}]), {})
            self.assertEqual(self.service.assign_mnemonics([{'lemma': 'машина', 'pos': 'NOUN'}]), {})
        self.service.openai_client.chat.completions.create.side_effect = TrialDenied('Budget reached')
        with self.assertRaises(TrialDenied):
            self.service.assign_mnemonics([{'lemma': 'машина', 'pos': 'NOUN'}])

    def test_exhausted_credit_stops_calls_and_keeps_vocabulary_retryable(self):
        first = self.add()
        second = self.add('дом')
        class ExhaustedCredit(RuntimeError):
            status_code = 429
            body = {'error': {'code': 'credit_balance_exhausted', 'type': 'insufficient_quota'}}
        self.service.openai_client = Mock()
        self.service.openai_client.chat.completions.create.side_effect = ExhaustedCredit('Credit exhausted')
        with patch('services.sync_service.time.sleep') as sleep:
            result = self.service.enrich_words([first, second], batch_size=1)
        self.service.openai_client.chat.completions.create.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(result['pending'], [first, second])
        self.assertIn('no available credit', result['warnings'][0])
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT topic,mnemonic FROM words').fetchall(), [(None, None), (None, None)])

    def test_successful_topics_survive_mnemonic_account_failure(self):
        from services.sync_service import VocabularyEnrichmentUnavailable
        word_id = self.add()
        with patch.object(self.service, 'assign_topics', return_value={'машина': ['travel']}), patch.object(self.service, 'assign_mnemonics', side_effect=VocabularyEnrichmentUnavailable('No credit')):
            result = self.service.enrich_words([word_id])
        self.assertEqual(result['pending'], [word_id])
        with connect_db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT topic,mnemonic FROM words').fetchone(), ('["travel"]', None))
