"""Preserve dictionary readings and select the form a saved task actually needs."""
from collections import Counter
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from services.form_selection import bucket, canonical_tags, choose_form
from services.sync_service import SyncService


class MorphologyImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = SyncService(':memory:', drive_service=object(), api_key='', config={})

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.executescript((Path(__file__).resolve().parents[1] / 'migrations/001_baseline.sql').read_text())
        self.addCleanup(self.conn.close)

    def import_word(self, lemma, **kwargs):
        # Isolate grammar from corpus-frequency drift. Separate tests exercise
        # the threshold, and contextual-capture tests use real rare occurrences.
        with patch('services.sync_service.word_frequency', return_value=1e-4):
            self.assertTrue(self.service.process_word(lemma, self.conn, self.conn.cursor(), **kwargs))
        return self.conn.execute('SELECT * FROM forms ORDER BY id').fetchall()

    @staticmethod
    def readings(forms, surface):
        return [json.loads(row['tags']) for row in forms if row['form'] == surface]

    def test_adjective_syncretism_retains_case_and_accusative_animacy(self):
        forms = self.import_word('новый')
        readings = self.readings(forms, 'нового')
        self.assertTrue(any(t.get('case') == 'gent' and t.get('gender') == 'masc' for t in readings))
        self.assertTrue(any(t.get('case') == 'accs' and t.get('animacy') == 'anim' for t in readings))
        chosen = choose_form(forms, 'новый', Counter(), Counter(), constraints={
            'pos': 'ADJF', 'case': 'accs', 'animacy': 'anim', 'number': 'sing', 'gender': 'masc'})
        self.assertEqual(chosen['form'], 'нового')
        self.assertEqual(json.loads(chosen['tags'])['case'], 'accs')

    def test_short_adjectives_survive_full_adjective_limit_without_invented_case(self):
        forms = self.import_word('готовый')
        short = {row['form']: json.loads(row['tags']) for row in forms if json.loads(row['tags'])['pos'] == 'ADJS'}
        self.assertEqual(set(short), {'готов', 'готова', 'готово', 'готовы'})
        self.assertEqual(short['готова']['gender'], 'femn')
        self.assertEqual(short['готовы']['number'], 'plur')
        self.assertTrue(all('case' not in tags for tags in short.values()))

    def test_full_and_short_participles_keep_distinct_readings(self):
        forms = self.import_word('написать')
        readings = self.readings(forms, 'написанного')
        self.assertTrue(any(t['pos'] == 'PRTF' and t.get('case') == 'gent' for t in readings))
        self.assertTrue(any(t.get('case') == 'accs' and t.get('animacy') == 'anim' for t in readings))
        for tags in readings:
            self.assertEqual((tags['tense'], tags['aspect'], tags['voice']), ('past', 'perf', 'pssv'))
        short = self.readings(forms, 'написана')[0]
        self.assertEqual((short['pos'], short['gender'], short['voice']), ('PRTS', 'femn', 'pssv'))
        self.assertNotIn('case', short)

    def test_past_gender_infinitive_and_verbal_adverb_are_not_lost(self):
        forms = self.import_word('читать')
        feminine = self.readings(forms, 'читала')[0]
        self.assertEqual((feminine['pos'], feminine['tense'], feminine['gender']), ('VERB', 'past', 'femn'))
        self.assertEqual(self.readings(forms, 'читать')[0]['pos'], 'INFN')
        gerund = next(row for row in forms if row['form'] == 'читая')
        self.assertEqual(json.loads(gerund['tags'])['pos'], 'GRND')
        base = self.conn.execute('SELECT lemma_difficulty FROM words').fetchone()[0]
        self.assertEqual(gerund['form_difficulty'], base + 2)
        lemma, pos, _ = self.service.get_lemma('ведя', self.conn, self.conn.cursor())
        self.assertEqual((lemma, pos), ('вести', 'VERB'))

    def test_same_noun_spelling_preserves_three_grammatical_readings(self):
        forms = self.import_word('книга')
        readings = self.readings(forms, 'книги')
        self.assertEqual({(t['case'], t['number']) for t in readings},
                         {('gent', 'sing'), ('nomn', 'plur'), ('accs', 'plur')})

    def test_comparative_keeps_its_own_pos(self):
        forms = self.import_word('быстрый')
        comparative = self.readings(forms, 'быстрее')[0]
        self.assertEqual((comparative['pos'], comparative['degree']), ('COMP', 'comp'))
        self.assertNotIn('case', comparative)

    def test_dictionary_yo_is_preserved_without_rewriting_saved_e_spelling(self):
        lemma, pos, _ = self.service.get_lemma('веселый', self.conn, self.conn.cursor())
        self.assertEqual((lemma, pos), ('весёлый', 'ADJ'))
        self.conn.execute("INSERT INTO words(id,lemma,pos,lemma_difficulty) VALUES (17,'весёлый','ADJ',3)")
        self.conn.execute("INSERT INTO forms(id,word_id,form,tags,count,form_difficulty) VALUES (41,17,'веселый','{}',5,3)")
        old = tuple(self.conn.execute('SELECT * FROM forms WHERE id=41').fetchone())
        forms = self.import_word(lemma, word_id=17)
        self.assertIn('весёлый', {row['form'] for row in forms})
        self.assertEqual(tuple(self.conn.execute('SELECT * FROM forms WHERE id=41').fetchone()), old)

    def test_bulk_frequency_rules_keep_rare_participles_out(self):
        frequencies = {'читать': 1e-4, 'читающий': 3e-6, 'читающая': 1e-6}
        with patch('services.sync_service.word_frequency', side_effect=lambda word, language: frequencies.get(word, 0)):
            self.assertTrue(self.service.process_word('читать', self.conn, self.conn.cursor()))
        forms = {row[0] for row in self.conn.execute('SELECT form FROM forms')}
        self.assertIn('читающий', forms)
        self.assertNotIn('читающая', forms)
        self.assertNotIn('читаю', forms)

    def test_incomplete_historical_analysis_is_retained_not_relabelled(self):
        self.conn.execute("INSERT INTO words(id,lemma,pos,count,lemma_difficulty) VALUES (17,'новый','ADJ',9,3)")
        self.conn.execute("INSERT INTO forms(id,word_id,form,tags,count,form_difficulty) VALUES (41,17,'нового','{\"gender\":\"masc\",\"number\":\"sing\"}',5,6)")
        self.conn.execute('INSERT INTO anki_cards(card_id,form_id,word_id,reps) VALUES (99,41,17,25)')
        old_form = tuple(self.conn.execute('SELECT * FROM forms WHERE id=41').fetchone())
        old_history = tuple(self.conn.execute('SELECT * FROM anki_cards').fetchone())
        forms = self.import_word('новый', word_id=17)
        self.assertEqual(tuple(self.conn.execute('SELECT * FROM forms WHERE id=41').fetchone()), old_form)
        self.assertEqual(tuple(self.conn.execute('SELECT * FROM anki_cards').fetchone()), old_history)
        self.assertTrue(any(t.get('case') == 'gent' for t in self.readings(forms, 'нового')))
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        snapshot = list(self.conn.iterdump())
        self.import_word('новый', word_id=17)
        self.assertEqual(list(self.conn.iterdump()), snapshot)

    def test_generated_tag_encoding_is_canonical_and_readings_are_unique(self):
        forms = self.import_word('написать')
        signatures = set()
        for form in forms:
            tags = json.loads(form['tags'])
            self.assertEqual(form['tags'], canonical_tags(dict(reversed(list(tags.items())))))
            signature = (form['form'], form['tags'])
            self.assertNotIn(signature, signatures)
            signatures.add(signature)


class TaskFormSelectionTests(unittest.TestCase):
    @staticmethod
    def form(identity, surface, **tags):
        return {'id': identity, 'form': surface, 'tags': json.dumps(tags)}

    def test_constraints_filter_before_commonness_or_rotation(self):
        forms = [self.form(1, 'книга', case='nomn', number='sing'),
                 self.form(2, 'книгами', case='ablt', number='plur')]
        with patch('services.form_selection.frequency', side_effect=lambda word: 1e-4 if word == 'книга' else 1e-9):
            self.assertEqual(choose_form(forms, 'книга', Counter(), Counter())['id'], 1)
            self.assertEqual(choose_form(forms, 'книга', Counter({2: 50}), Counter(),
                                         constraints={'case': 'ablt', 'number': 'plur'})['id'], 2)

    def test_constraints_do_not_guess_missing_historical_tags_or_fallback(self):
        forms = [self.form(1, 'готов', gender='masc', number='sing'),
                 self.form(2, 'готовый', pos='ADJF', gender='masc', case='nomn')]
        self.assertIsNone(choose_form(forms, 'готовый', Counter(), Counter(), constraints={'pos': 'ADJS'}))
        self.assertIsNone(choose_form(forms, 'готовый', Counter(), Counter(), constraints={'case': 'datv'}))

    def test_allowed_alternatives_and_distinct_readings(self):
        forms = [self.form(1, 'книги', case='gent', number='sing'),
                 self.form(2, 'книги', case='nomn', number='plur')]
        selected = choose_form(forms, 'книга', Counter(), Counter(), constraints={
            'case': ['nomn', 'accs'], 'number': 'plur'})
        self.assertEqual(selected['id'], 2)
        self.assertNotEqual(bucket(json.loads(forms[0]['tags'])), bucket(json.loads(forms[1]['tags'])))
        self.assertNotEqual(bucket({'pos': 'VERB', 'gender': 'masc', 'tense': 'past'}),
                            bucket({'pos': 'VERB', 'gender': 'femn', 'tense': 'past'}))

    def test_unsupported_or_malformed_constraints_fail_before_selection(self):
        for constraints in ({'case': 'genitive'}, {'function': 'possession'}, {'case': []},
                            {'case': ['gent', None]}, {'gender': True}, ['case']):
            with self.subTest(constraints=constraints), self.assertRaises(ValueError):
                choose_form([], 'книга', Counter(), Counter(), constraints=constraints)

    def test_invalid_stored_tags_cannot_win_selection(self):
        forms = [{'id': 1, 'form': 'книге', 'tags': '{'},
                 {'id': 2, 'form': 'книге', 'tags': '[]'},
                 {'id': 3, 'form': 'книге', 'tags': '{"case":["datv"]}'},
                 self.form(4, 'книге', case='datv', number='sing')]
        self.assertEqual(choose_form(forms, 'книга', Counter(), Counter(), constraints={'case': 'datv'})['id'], 4)

    def test_default_ranking_still_penalises_legacy_and_canonical_participles(self):
        for pos in ('participle', 'PRTF', 'PRTS'):
            forms = [self.form(1, 'читаем', pos=pos), self.form(2, 'читаю', pos='VERB')]
            with self.subTest(pos=pos), patch('services.form_selection.frequency', return_value=1e-6):
                self.assertEqual(choose_form(forms, 'читать', Counter(), Counter())['id'], 2)


if __name__ == '__main__':
    unittest.main()
