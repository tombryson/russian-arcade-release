"""A game selects real contextual language without editing the lexical store."""
import json
import unittest

from repositories.learning_repository import encoded, transaction
from services.journey_vocabulary import _vocabulary, cache_source_available, catalogue_sources, select_examples
from tests import test_first_steps_practice as practice


class JourneyVocabularyTests(unittest.TestCase):
    setUp = practice.FirstStepsPracticeTests.setUp
    post = practice.FirstStepsPracticeTests.post
    hello = practice.FirstStepsPracticeTests.hello
    finish_batch = practice.FirstStepsPracticeTests.finish_batch

    def lexicon(self):
        pairs = [('книга', 'книги'), ('школа', 'школы'), ('окно', 'окна'), ('город', 'города'), ('собака', 'собаки'),
                 ('дерево', 'дерева'), ('письмо', 'письма'), ('сумка', 'сумки'), ('карта', 'карты'), ('река', 'реки'),
                 ('море', 'моря'), ('брат', 'брата'), ('сестра', 'сестры'), ('яблоко', 'яблока'), ('дверь', 'двери'),
                 ('чай', 'чая'), ('хлеб', 'хлеба'), ('дождь', 'дождя'), ('музыка', 'музыки'), ('работа', 'работы')]
        with transaction(self.db, write=True) as conn:
            for i, (lemma, genitive) in enumerate(pairs):
                topic = 'travel' if i % 2 else 'home'
                conn.execute("INSERT OR IGNORE INTO words(lemma,pos,lemma_difficulty,topic) VALUES (?,'NOUN',2,?)", (lemma, encoded([topic])))
                word = conn.execute('SELECT id FROM words WHERE lemma=?', (lemma,)).fetchone()[0]
                conn.execute('UPDATE words SET lemma_difficulty=2,topic=? WHERE id=?', (encoded([topic]), word))
                for surface, case in ((lemma, 'nomn'), (genitive, 'gent')):
                    conn.execute('INSERT OR IGNORE INTO forms(word_id,form,tags,form_difficulty) VALUES (?,?,?,?)',
                                 (word, surface, encoded({'case': case, 'number': 'sing'}), 2))

    def choose(self, seed='seed', profile='personal-learning', options=None, limit=6, guest=None):
        with self.app.app_context(), transaction(self.db) as conn:
            return select_examples(conn, profile, guest, options or {'source': 'vocabulary'}, seed, limit)

    def sources(self, profile='personal-learning'):
        with self.app.app_context(), transaction(self.db) as conn:
            return catalogue_sources(conn, profile, None)

    def complete_vocabulary_selection(self):
        # This small fixture fits in one selection. Check every lexical form so
        # recent-form avoidance cannot hide the example whose cache is tested.
        with self.app.app_context(), transaction(self.db) as conn:
            identities = {record['identity'] for record in _vocabulary(conn)}
        self.assertLessEqual(len(identities), 20, 'Expand this helper if the fixture exceeds the selection limit.')
        selected = self.choose(limit=len(identities))
        self.assertCountEqual([record['identity'] for record in selected], identities)
        return selected

    def counts(self):
        with transaction(self.db) as conn:
            return tuple(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                         for table in ('words', 'forms', 'card_definitions', 'native_card_batches', 'progression_events'))

    def test_real_vocabulary_and_form_variation_are_seeded_without_side_effects(self):
        self.lexicon()
        before = self.counts()
        sources = self.sources()
        self.assertGreaterEqual(sources['word_count'], 20)
        self.assertGreaterEqual(sources['form_count'], 40)
        self.assertTrue({'home', 'travel'}.issubset(sources['topics']))
        first = self.choose()
        self.assertEqual(first, self.choose())
        self.assertEqual(len(first), 6)
        self.assertEqual(len({record['word_id'] for record in first}), 6)
        variants = [record for seed in range(12) for record in self.choose(str(seed))]
        self.assertGreater(len({record['lemma'] for record in variants}), 15)
        self.assertTrue(any(record['form'] != record['lemma'] for record in variants))
        self.assertTrue(all('translation' not in record for record in variants))
        self.assertEqual(self.counts(), before)

    def test_recent_unfinished_games_move_selection_to_different_real_words(self):
        self.lexicon()
        first = self.choose('same-seed')
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO journey_game_sessions(id,profile_id,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES ('active','personal-learning','pairs','seed','[]',?,1,1)",
                         (encoded({'vocabulary_refs': first}),))
        second = self.choose('same-seed')
        self.assertFalse({record['lemma'] for record in first} & {record['lemma'] for record in second})

    def test_filters_use_actual_topics_and_form_difficulty(self):
        self.lexicon()
        selected = self.choose(options={'source': 'vocabulary', 'topic': 'travel', 'difficulty': 2}, limit=8)
        self.assertEqual(len(selected), 8)
        self.assertTrue(all('travel' in record['metadata']['topics'] and record['metadata']['form_difficulty'] == 2 for record in selected))
        self.assertEqual(self.choose(options={'source': 'vocabulary', 'topic': 'nonexistent'}), [])

    def test_owned_native_context_and_media_are_reused_without_exposing_other_profiles(self):
        self.hello()
        batch = self.post('/api/v1/first-steps/hello/flashcards', status=201)
        self.finish_batch(batch)
        mine = self.choose(limit=10)
        ready = [record for record in mine if record.get('sentence')]
        self.assertEqual(len(ready), 3)
        self.assertTrue(all({asset['kind'] for asset in record['assets']} == {'image', 'word_audio', 'sentence_audio'} for record in ready))
        self.assertTrue(all(record['source']['kind'] == 'card' for record in ready))
        other = self.choose(profile='another-profile', limit=10)
        guest = self.choose(profile=None, limit=10)
        self.assertTrue(all('sentence' not in record and not record.get('assets') for record in [*other, *guest]))
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE card_definitions SET retired=1')
        self.assertTrue(all('sentence' not in record for record in self.choose(limit=10)))

    def lesson(self):
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO lessons(id,title,created_at) VALUES ('tutor','Tutor lesson','now')")
            conn.execute("INSERT INTO lesson_files VALUES ('fixture-file',1,'image/png',1)")
            conn.execute("INSERT INTO lesson_revisions(id,lesson_id,number,fingerprint,materials,state,model,created_at) VALUES ('revision','tutor',1,'fingerprint','[]','ready','fixture',1)")
            conn.execute("INSERT INTO lesson_pages(revision_id,number,source_digest,source_page,image_digest,base_digest) VALUES ('revision',1,'fixture-file',1,'fixture-file','base')")

    def pick(self, pick_id, surface, context, *, confirmed=True, owner='personal-learning'):
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO lesson_word_picks(id,owner_id,lesson_id,revision_id,page,token_key,surface,context,original,created_at,reading_confirmed) VALUES (?,?,'tutor','revision',1,?,?,?,?,1,?)",
                         (pick_id, owner, pick_id, surface, context, surface, int(confirmed)))

    def test_confirmed_pending_lesson_occurrences_preserve_exact_form_and_context(self):
        self.lexicon()
        self.lesson()
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE words SET pos='noun' WHERE lemma='книга'")
        self.pick('book', 'книгой', 'Я довольна этой книгой.')
        self.pick('doctor', 'врачом', 'Он стал врачом.')
        self.pick('uncertain', 'книге', 'Я думаю о книге.', confirmed=False)
        self.pick('homograph', 'печь', 'Я хочу печь.')
        self.pick('foreign', 'городом', 'Перед городом река.', owner='another-profile')
        before = self.counts()
        selected = self.choose(options={'source': 'lesson', 'lesson_id': 'tutor'}, limit=10)
        self.assertEqual({record['form'] for record in selected}, {'книгой', 'врачом'})
        book = next(record for record in selected if record['form'] == 'книгой')
        self.assertEqual(book['source']['context'], 'Я довольна этой книгой.')
        self.assertEqual(book['tags']['case'], 'ablt')
        self.assertIsNotNone(book['word_id'])
        self.assertNotIn('sentence', book)
        self.assertNotIn('translation', book)
        doctor = next(record for record in selected if record['form'] == 'врачом')
        self.assertIsNone(doctor['word_id'])
        self.assertIsNone(doctor['form_id'])
        self.assertEqual(self.sources()['lessons'], [{'id': 'tutor', 'title': 'Tutor lesson', 'count': 2}])
        self.assertEqual(self.sources(profile=None)['lessons'], [])
        self.assertEqual(self.counts(), before)

    def test_selected_lesson_context_reuses_its_existing_native_media(self):
        self.hello()
        batch = self.post('/api/v1/first-steps/hello/flashcards', status=201)
        self.finish_batch(batch)
        self.lesson()
        with transaction(self.db) as conn:
            item = dict(conn.execute('SELECT * FROM native_card_generation_items WHERE batch_id=? LIMIT 1', (batch['id'],)).fetchone())
        word, response = json.loads(item['selection']), json.loads(item['response'])
        self.pick('saved', word['form'], response['sentence'])
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE lesson_word_picks SET item_id=? WHERE id='saved'", (item['id'],))
        selected = self.choose(options={'source': 'lesson', 'lesson_id': 'tutor'})
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['source']['kind'], 'lesson')
        self.assertEqual(selected[0]['sentence'], response['sentence'])
        self.assertEqual({asset['kind'] for asset in selected[0]['assets']}, {'image', 'word_audio', 'sentence_audio'})

    def test_context_cache_is_owner_scoped_and_ready_unrecent_examples_are_preferred(self):
        self.lexicon()
        target = self.choose(limit=1)[0]
        prepared = {**target, 'sentence': 'Новый пример.', 'translation': 'A new example.', 'target_meaning': 'the contextual meaning'}
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_examples(id,profile_id,identity,word_id,form_id,content_json,created_at) VALUES (?,?,?,?,?,?,1)',
                         ('cached-mine', 'personal-learning', target['identity'], target['word_id'], target['form_id'], encoded(prepared)))
        mine = self.choose('another-seed', limit=1)[0]
        self.assertEqual(mine['identity'], target['identity'])
        self.assertEqual(mine['cached_id'], 'cached-mine')
        self.assertEqual(mine['target_meaning'], prepared['target_meaning'])
        self.assertTrue(all('sentence' not in record for record in self.choose('other', profile='someone-else', limit=20)))
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO journey_game_sessions(id,profile_id,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES ('used','personal-learning','pairs','seed','[]',?,1,1)",
                         (encoded({'vocabulary_refs': [mine]}),))
        fresh = self.choose('another-seed', limit=1)[0]
        self.assertNotEqual(fresh['lemma'], mine['lemma'])

    def native_cache(self):
        self.hello()
        self.finish_batch(self.post('/api/v1/first-steps/hello/flashcards', status=201))
        example = next(record for record in self.choose(limit=10) if record.get('sentence'))
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_examples(id,profile_id,identity,word_id,form_id,content_json,created_at) VALUES (?,?,?,?,?,?,1)',
                         ('saved-native', 'personal-learning', example['identity'], example['word_id'], example['form_id'], encoded(example)))
        return example

    def test_retired_native_example_stays_out_of_new_games_but_history_is_frozen(self):
        example = self.native_cache()
        history = encoded({'vocabulary_refs': [example]})
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO journey_game_sessions(id,profile_id,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES ('history','personal-learning','pairs','seed','[]',?,1,1)", (history,))
        with self.app.app_context(), transaction(self.db) as conn:
            self.assertTrue(cache_source_available(conn, example, 'personal-learning'))
            self.assertFalse(cache_source_available(conn, example, 'another-profile'))
            self.assertFalse(cache_source_available(conn, example, None))
        self.app.extensions['learning']['card_authoring'].retire(self.access, example['source']['id'])
        selected = self.complete_vocabulary_selection()
        self.assertFalse(any(record['source'].get('id') == example['source']['id'] for record in selected))
        fresh = next(record for record in selected if record['identity'] == example['identity'])
        self.assertNotIn('sentence', fresh)
        self.assertNotIn('cached_id', fresh)
        self.assertEqual(fresh['source']['kind'], 'vocabulary')
        with self.app.app_context(), transaction(self.db) as conn:
            self.assertFalse(cache_source_available(conn, example, 'personal-learning'))
            self.assertEqual(conn.execute("SELECT content_json FROM journey_game_sessions WHERE id='history'").fetchone()[0], history)

    def test_withdrawn_latest_native_version_does_not_fall_back_to_older_published_examples(self):
        example = self.native_cache()
        self.gen.content.withdraw(self.access, example['source']['version'])
        selected = self.complete_vocabulary_selection()
        self.assertFalse(any(record['source'].get('id') == example['source']['id'] for record in selected))
        fresh = next(record for record in selected if record['identity'] == example['identity'])
        self.assertNotIn('sentence', fresh)
        self.assertNotIn('cached_id', fresh)
        self.assertEqual(fresh['source']['kind'], 'vocabulary')
        with self.app.app_context(), transaction(self.db) as conn:
            self.assertFalse(cache_source_available(conn, example, 'personal-learning'))
            lesson = {**example, 'source': {'kind': 'lesson', 'id': 'tutor', 'card_id': example['source']['id'],
                                          'card_version': example['source']['version']}}
            self.assertFalse(cache_source_available(conn, lesson, 'personal-learning'))


if __name__ == '__main__':
    unittest.main()
