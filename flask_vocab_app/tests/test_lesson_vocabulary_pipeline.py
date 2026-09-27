"""Contextual lesson/game vocabulary uses the established lexical pipeline."""
import json
import sqlite3
import unittest
from unittest.mock import patch

from migrations import MIGRATION_DIR
from services.card_metadata import GRAMMAR
from services.lesson_cards import LessonCards, _local_vocabulary_pipeline


def noun(lemma='город', surface='городах', **grammar):
    return {'lemma': lemma, 'surface': surface, 'pos': 'NOUN',
            'grammar': {**{key: '' for key in GRAMMAR}, 'case': 'loct',
                        'number': 'plur', 'gender': 'masc', 'animacy': 'inan',
                        **grammar}}


class LessonVocabularyPipelineTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript((MIGRATION_DIR / '001_baseline.sql').read_text())
        self.addCleanup(self.conn.close)

    def test_new_contextual_noun_has_declensions_and_difficulties(self):
        result = LessonCards.resolve(self.conn, noun())
        forms = self.conn.execute('SELECT * FROM forms WHERE word_id=?', (result['word_id'],)).fetchall()
        self.assertTrue({'город', 'города', 'городу', 'городом', 'городе',
                         'городов', 'городами', 'городах'} <= {row['form'] for row in forms})
        cases = {(json.loads(row['tags']).get('case'), json.loads(row['tags']).get('number')) for row in forms}
        self.assertEqual(cases, {(case, number) for case in ('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct')
                                for number in ('sing', 'plur')})
        self.assertTrue(all(row['form_difficulty'] > 0 for row in forms))
        self.assertGreater(result['metadata']['lemma_difficulty'], 0)
        self.assertEqual(result['metadata']['form_difficulty'], result['metadata']['lemma_difficulty'] + 1)
        repeated = LessonCards.resolve(self.conn, noun())
        self.assertEqual((repeated['word_id'], repeated['form_id']), (result['word_id'], result['form_id']))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM forms').fetchone()[0], len(forms))

    def test_rare_context_keeps_exact_form_filtered_out_of_bulk_declensions(self):
        common = LessonCards.resolve(self.conn, noun())
        rare = LessonCards.resolve(self.conn, noun('архипелаг', 'архипелагами', case='ablt'))
        self.assertGreater(rare['metadata']['lemma_difficulty'], common['metadata']['lemma_difficulty'])
        self.assertGreater(rare['metadata']['form_difficulty'], rare['metadata']['lemma_difficulty'])
        form = self.conn.execute('SELECT * FROM forms WHERE id=?', (rare['form_id'],)).fetchone()
        self.assertEqual(form['form'], 'архипелагами')
        self.assertEqual(json.loads(form['tags'])['case'], 'ablt')
        self.assertGreater(self.conn.execute('SELECT COUNT(*) FROM forms WHERE word_id=?', (rare['word_id'],)).fetchone()[0], 1)

    def test_contextual_special_case_survives_normal_case_filter(self):
        result = LessonCards.resolve(self.conn, noun('лес', 'лесу', case='loc2', number='sing'))
        form = self.conn.execute('SELECT * FROM forms WHERE id=?', (result['form_id'],)).fetchone()
        self.assertEqual(json.loads(form['tags'])['case'], 'loc2')
        self.assertGreater(form['form_difficulty'], 0)
        cases = {json.loads(row[0]).get('case') for row in self.conn.execute('SELECT tags FROM forms WHERE word_id=?', (result['word_id'],))}
        self.assertTrue({'loc2', 'nomn', 'gent', 'datv', 'accs', 'ablt', 'loct'} <= cases)

    def test_existing_word_and_context_keep_all_metadata_counts_and_ids(self):
        self.conn.execute("INSERT INTO words VALUES (73,'город','NOUN',23,4,?,?,'2020-02-03')",
                          ('["city","my-custom-topic"]', 'A saved mnemonic'))
        tags = {'case': 'loct', 'number': 'plur', 'gender': 'masc', 'animacy': 'inan'}
        self.conn.execute('INSERT INTO forms VALUES (301,73,?,19,?,7)', ('городах', json.dumps(tags)))
        before_word = tuple(self.conn.execute('SELECT * FROM words').fetchone())
        before_form = tuple(self.conn.execute('SELECT * FROM forms').fetchone())
        with patch('services.lesson_cards._local_vocabulary_pipeline', side_effect=AssertionError('Existing vocabulary must not be reprocessed')):
            result = LessonCards.resolve(self.conn, noun())
        self.assertEqual((result['word_id'], result['form_id']), (73, 301))
        self.assertEqual(tuple(self.conn.execute('SELECT * FROM words').fetchone()), before_word)
        self.assertEqual(tuple(self.conn.execute('SELECT * FROM forms').fetchone()), before_form)
        self.assertEqual(result['metadata']['topics'], ['city', 'my-custom-topic'])
        self.assertEqual(result['mnemonic'], 'A saved mnemonic')

    def test_validated_context_is_not_reselected_from_ambiguous_surface(self):
        pipeline = _local_vocabulary_pipeline()
        with patch.object(pipeline.morph, 'parse', side_effect=AssertionError('Use the already validated contextual parse')):
            result = LessonCards.resolve(self.conn, noun('сталь', 'стали', case='gent', number='sing', gender='femn'))
        self.assertEqual((result['lemma'], result['pos']), ('сталь', 'NOUN'))
        self.assertEqual(result['tags']['case'], 'gent')
        forms = self.conn.execute('SELECT tags FROM forms WHERE word_id=?', (result['word_id'],)).fetchall()
        self.assertGreater(len(forms), 1)
        self.assertTrue(all('tense' not in json.loads(row[0]) for row in forms))

    def test_local_pipeline_does_not_initialize_provider_or_drive_auth(self):
        _local_vocabulary_pipeline.cache_clear()
        self.addCleanup(_local_vocabulary_pipeline.cache_clear)
        with patch('socket.socket.connect', side_effect=AssertionError('No network')), \
             patch('services.sync_service.GoogleDriveService', side_effect=AssertionError('No Drive authentication')), \
             patch('services.sync_service.OpenAI', side_effect=AssertionError('No provider client')), \
             patch('services.sync_service.openai_client', side_effect=AssertionError('No provider gateway')):
            result = LessonCards.resolve(self.conn, noun())
        self.assertGreater(result['metadata']['lemma_difficulty'], 0)


if __name__ == '__main__':
    unittest.main()
