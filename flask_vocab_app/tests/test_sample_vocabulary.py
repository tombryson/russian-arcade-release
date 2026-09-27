"""Sample data follows lexical rules without paid providers or personal data."""
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from services.sample_vocabulary import prepared_vocabulary, seed_sample_items, sample_needs_repair
from services.vocabulary_topics import TOPICS


class SampleVocabularyTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript((Path(__file__).resolve().parents[1] / 'migrations/001_baseline.sql').read_text())
        self.addCleanup(self.conn.close)
        network = patch('socket.socket.connect', side_effect=AssertionError('Seeding must be offline'))
        network.start()
        self.addCleanup(network.stop)

    def test_sample_words_have_real_topics_filtered_forms_and_contextual_card_links(self):
        items = seed_sample_items(self.conn, 'demo')
        words = self.conn.execute('SELECT * FROM words').fetchall()
        self.assertEqual(len(words), len(prepared_vocabulary()))
        for word in words:
            self.assertTrue(set(json.loads(word['topic'])) <= set(TOPICS))
            self.assertNotIn('First steps', word['topic'])
            self.assertGreaterEqual(word['lemma_difficulty'], 1)
            self.assertTrue(word['mnemonic'].strip())
            self.assertFalse(word['mnemonic'].startswith('Recall '))
        for lemma in ('письмо', 'сумка', 'рынок'):
            count = self.conn.execute('SELECT count(*) FROM forms f JOIN words w ON w.id=f.word_id WHERE w.lemma=?', (lemma,)).fetchone()[0]
            self.assertGreater(count, 3, lemma)
        for item in items:
            form = self.conn.execute('SELECT * FROM forms WHERE id=?', (item['form_id'],)).fetchone()
            self.assertEqual(form['word_id'], item['word_id'])
            self.assertEqual(form['form'].casefold(), item['answer'].casefold())
            self.assertNotIn('topic', item)
            self.assertIn('[[blank]]', item['prompt'])
            self.assertTrue(item['hint'])
        self.assertFalse(sample_needs_repair(self.conn))

    def test_repair_fills_missing_mnemonics_even_after_topics_were_fixed(self):
        seed_sample_items(self.conn, 'demo')
        self.conn.execute("UPDATE words SET mnemonic=NULL WHERE lemma='письмо'")
        self.assertTrue(sample_needs_repair(self.conn))
        seed_sample_items(self.conn, 'demo')
        mnemonic = self.conn.execute("SELECT mnemonic FROM words WHERE lemma='письмо'").fetchone()[0]
        self.assertEqual(mnemonic, prepared_vocabulary()[('письмо', 'NOUN')]['mnemonic'])
        self.assertFalse(sample_needs_repair(self.conn))

    def test_old_seed_repair_preserves_ids_counts_custom_topics_mnemonics_and_existing_forms(self):
        self.conn.execute("INSERT INTO words(id,lemma,pos,count,lemma_difficulty,topic,mnemonic) VALUES (42,'письмо','NOUN',9,1,?,?)",
                          (json.dumps(['First steps', 'work']), 'My own memory aid'))
        self.conn.execute("INSERT INTO forms(id,word_id,form,count,tags,form_difficulty) VALUES (81,42,'письмо',7,?,4)",
                          (json.dumps({'case':'nomn','number':'sing','gender':'neut','animacy':'inan'}),))
        first = seed_sample_items(self.conn, 'trial-sample')
        word = self.conn.execute('SELECT * FROM words WHERE id=42').fetchone()
        self.assertEqual(word['count'], 9)
        self.assertEqual(json.loads(word['topic']), ['work'])
        self.assertEqual(word['mnemonic'], 'My own memory aid')
        self.assertGreater(word['lemma_difficulty'], 1)
        form = self.conn.execute('SELECT * FROM forms WHERE id=81').fetchone()
        self.assertEqual((form['word_id'],form['count'],form['form_difficulty']), (42,7,4))
        self.assertTrue(any(item['form_id']==81 for item in first))
        counts = tuple(self.conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('words','forms'))
        second = seed_sample_items(self.conn, 'trial-sample')
        self.assertEqual(first, second)
        self.assertEqual(counts, tuple(self.conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('words','forms')))
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
