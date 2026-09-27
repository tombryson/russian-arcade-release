"""Contextual vocabulary uses the import policy without replacing saved data."""
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from services.sync_service import SyncService


class LexicalBackfillTests(unittest.TestCase):
    def setUp(self):
        self.service = SyncService(':memory:', drive_service=object(), api_key='', config={})
        self.conn = self.database()
        self.addCleanup(self.conn.close)

    @staticmethod
    def database():
        conn = sqlite3.connect(':memory:')
        conn.execute('PRAGMA foreign_keys=ON')
        baseline = Path(__file__).resolve().parents[1] / 'migrations' / '001_baseline.sql'
        conn.executescript(baseline.read_text())
        return conn

    def reading(self, lemma, pos):
        return next(p for p in self.service.morph.parse(lemma) if p.normal_form == lemma and p.tag.POS == pos)

    def test_contextual_interjection_is_not_reranked_as_a_noun(self):
        parsed = self.reading('привет', 'INTJ')
        with patch.object(self.service.morph, 'parse', side_effect=AssertionError('Do not rerank a verified reading')):
            self.assertTrue(self.service.process_word('привет', self.conn, self.conn.cursor(), parsed=parsed))
        self.assertEqual(self.conn.execute('SELECT lemma,pos FROM words').fetchall(), [('привет', 'INTJ')])
        self.assertEqual(self.conn.execute('SELECT form FROM forms').fetchall(), [('привет',)])

    def test_explicit_homograph_keeps_the_other_part_of_speech(self):
        self.conn.execute("INSERT INTO words(id,lemma,pos,count,lemma_difficulty,topic,mnemonic) VALUES (17,'печь','NOUN',9,3,'[\"home\"]','A stove')")
        original = self.conn.execute('SELECT * FROM words WHERE id=17').fetchone()
        self.assertTrue(self.service.process_word('печь', self.conn, self.conn.cursor(), parsed=self.reading('печь', 'INFN')))
        self.assertEqual(self.conn.execute('SELECT * FROM words WHERE id=17').fetchone(), original)
        self.assertEqual(self.conn.execute('SELECT pos FROM words WHERE lemma=? ORDER BY id', ('печь',)).fetchall(), [('NOUN',), ('VERB',)])

    def test_backfill_preserves_ids_history_enrichment_and_semantically_equal_forms(self):
        expected = self.database()
        self.addCleanup(expected.close)
        self.assertTrue(self.service.process_word('машина', expected, expected.cursor()))
        expected_difficulty = expected.execute('SELECT lemma_difficulty FROM words').fetchone()[0]
        generated = expected.execute('SELECT form,tags,form_difficulty FROM forms ORDER BY form,tags').fetchall()
        surface, tags, difficulty = generated[0]
        other_surface, other_tags, other_difficulty = generated[1]
        # The JSON bytes differ from the importer's output, while grammar is equal.
        reordered_tags = json.dumps(dict(reversed(list(json.loads(tags).items()))), separators=(',', ':'))
        self.conn.execute("INSERT INTO words(id,lemma,pos,count,lemma_difficulty,topic,mnemonic,date_added) VALUES (42,'машина','noun',12,0,'[\"travel\"]','My car clue','2020-01-01')")
        self.conn.execute('INSERT INTO forms(id,word_id,form,count,tags,form_difficulty) VALUES (71,42,?,8,?,7)', (surface, reordered_tags))
        self.conn.execute('INSERT INTO forms(id,word_id,form,count,tags,form_difficulty) VALUES (72,42,?,4,?,NULL)', (other_surface, other_tags))
        self.conn.execute("INSERT INTO forms(id,word_id,form,count,tags,form_difficulty) VALUES (73,42,'машиною',6,'{\"case\":\"ablt\",\"number\":\"sing\"}',8)")
        self.conn.execute('INSERT INTO anki_cards(card_id,form_id,word_id,reps) VALUES (99,71,42,25)')
        saved_form = self.conn.execute('SELECT * FROM forms WHERE id=71').fetchone()
        contextual_form = self.conn.execute('SELECT * FROM forms WHERE id=73').fetchone()
        history = self.conn.execute('SELECT * FROM anki_cards').fetchall()
        parsed = self.reading('машина', 'NOUN')
        self.assertTrue(self.service.process_word('машина', self.conn, self.conn.cursor(), parsed=parsed, word_id=42))
        self.assertEqual(self.conn.execute('SELECT * FROM forms WHERE id=71').fetchone(), saved_form)
        self.assertEqual(self.conn.execute('SELECT * FROM forms WHERE id=73').fetchone(), contextual_form)
        self.assertEqual(self.conn.execute('SELECT count,form_difficulty FROM forms WHERE id=72').fetchone(), (4, other_difficulty))
        self.assertEqual(self.conn.execute('SELECT * FROM anki_cards').fetchall(), history)
        self.assertEqual(self.conn.execute('SELECT id,lemma,pos,count,lemma_difficulty,topic,mnemonic,date_added FROM words').fetchone(),
                         (42, 'машина', 'noun', 12, expected_difficulty, '["travel"]', 'My car clue', '2020-01-01'))
        forms = self.conn.execute('SELECT form,tags FROM forms').fetchall()
        for form, encoded_tags, _ in generated:
            self.assertEqual(sum(1 for saved, saved_tags in forms if saved == form and json.loads(saved_tags) == json.loads(encoded_tags)), 1)
        snapshot = list(self.conn.iterdump())
        self.assertTrue(self.service.process_word('машина', self.conn, self.conn.cursor(), parsed=parsed, word_id=42))
        self.assertEqual(list(self.conn.iterdump()), snapshot)
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_existing_difficulty_is_retained_and_used_for_missing_forms(self):
        self.conn.execute("INSERT INTO words(id,lemma,pos,lemma_difficulty) VALUES (42,'машина','NOUN',4)")
        self.assertTrue(self.service.process_word('машина', self.conn, self.conn.cursor(), word_id=42))
        self.assertEqual(self.conn.execute('SELECT lemma_difficulty FROM words').fetchone()[0], 4)
        self.assertGreater(self.conn.execute('SELECT COUNT(*) FROM forms').fetchone()[0], 1)
        for tags, difficulty in self.conn.execute('SELECT tags,form_difficulty FROM forms'):
            self.assertEqual(difficulty, 4 + (json.loads(tags).get('number') == 'plur'))

    def test_mismatched_ids_lemmas_and_readings_make_no_changes(self):
        self.conn.execute("INSERT INTO words(id,lemma,pos,lemma_difficulty) VALUES (42,'печь','NOUN',0)")
        snapshot = list(self.conn.iterdump())
        for lemma, parsed, word_id in (
            ('печь', self.reading('печь', 'NOUN'), 999),
            ('машина', self.reading('машина', 'NOUN'), 42),
            ('машина', self.reading('печь', 'NOUN'), None),
            ('печь', self.reading('печь', 'INFN'), 42),
        ):
            with self.subTest(lemma=lemma, word_id=word_id, pos=parsed.tag.POS):
                self.assertFalse(self.service.process_word(lemma, self.conn, self.conn.cursor(), parsed=parsed, word_id=word_id))
                self.assertEqual(list(self.conn.iterdump()), snapshot)

    def test_contextual_backfill_uses_the_same_frequency_and_participle_filters(self):
        expected = self.database()
        self.addCleanup(expected.close)
        parsed = self.reading('читать', 'INFN')
        frequencies = {'читать': 1e-4, 'читаю': 1e-5, 'читающий': 3e-6, 'читающая': 1e-6}
        self.conn.execute("INSERT INTO words(id,lemma,pos,lemma_difficulty) VALUES (42,'читать','VERB',0)")
        with patch('services.sync_service.word_frequency', side_effect=lambda word, language: frequencies.get(word, 0)):
            self.assertTrue(self.service.process_word('читать', expected, expected.cursor()))
            self.assertTrue(self.service.process_word('читать', self.conn, self.conn.cursor(), parsed=parsed, word_id=42))
        query = 'SELECT form,tags,form_difficulty FROM forms ORDER BY form,tags'
        self.assertEqual(self.conn.execute(query).fetchall(), expected.execute(query).fetchall())
        surfaces = {row[0] for row in self.conn.execute('SELECT form FROM forms')}
        self.assertIn('читающий', surfaces)
        self.assertNotIn('читающая', surfaces)
        self.assertNotIn('читаешь', surfaces)

