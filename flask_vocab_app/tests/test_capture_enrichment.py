"""Captured words finish the importer pipeline before their cards are frozen."""
import json
import unittest

from repositories.learning_repository import encoded, transaction
from services.ai_trial_budget import TrialDenied
from tests import test_lesson_cards as lessons
from tests import test_first_steps_practice as first_steps
from tests import test_game_vocabulary_discovery as games


class LessonEnrichmentTests(unittest.TestCase):
    setUp = lessons.LessonCardTests.setUp
    prepare = lessons.LessonCardTests.prepare
    finish = lessons.LessonCardTests.finish

    def test_committed_word_metadata_and_mnemonic_reach_the_generated_card(self):
        result = self.prepare()
        pipeline = self.app.extensions['services']['SyncService']
        with transaction(self.db) as conn:
            word = conn.execute("SELECT * FROM words WHERE lemma='город'").fetchone()
            selection = json.loads(conn.execute('SELECT selection FROM native_card_generation_items').fetchone()[0])
            self.assertEqual(pipeline.calls, [[word['id']]])
            self.assertTrue(word['mnemonic'])
            self.assertEqual(selection['mnemonic'], word['mnemonic'])
            self.assertEqual(selection['metadata']['topics'], ['places'])
        self.finish(result['batch_id'])
        with transaction(self.db) as conn:
            payload = json.loads(conn.execute('SELECT payload FROM learning_content_versions').fetchone()[0])
            self.assertEqual(payload['items'][0]['hint'], word['mnemonic'])

    def test_failed_enrichment_keeps_source_words_and_retries_without_new_cards(self):
        pipeline = self.app.extensions['services']['SyncService']._get()
        pipeline.pending = True
        request_id = self.cards.create(self.access, self.lid, self.rid, 1, 1, 1)
        failed = self.cards.advance(self.access, request_id, self.lid)
        self.assertEqual(failed['state'], 'failed')
        self.assertIn('words are saved', failed['error'])
        with transaction(self.db) as conn:
            word_id = conn.execute("SELECT id FROM words WHERE lemma='город'").fetchone()[0]
            item_id = conn.execute('SELECT id FROM native_card_generation_items').fetchone()[0]
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_content_versions').fetchone()[0], 0)
        pipeline.pending = False
        recovered = self.cards.advance(self.access, request_id, self.lid)
        self.assertEqual(recovered['state'], 'ready')
        self.assertEqual(self.ai.card_calls, 1)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT id FROM words WHERE lemma='город'").fetchone()[0], word_id)
            self.assertEqual([row[0] for row in conn.execute('SELECT id FROM native_card_generation_items')], [item_id])
            self.assertTrue(json.loads(conn.execute('SELECT selection FROM native_card_generation_items').fetchone()[0])['mnemonic'])

    def test_trial_denial_is_propagated_after_saving_retryable_request(self):
        pipeline = self.app.extensions['services']['SyncService']._get()
        pipeline.error = TrialDenied('Daily trial limit reached.')
        request_id = self.cards.create(self.access, self.lid, self.rid, 1, 1, 1)
        with self.assertRaises(TrialDenied):
            self.cards.advance(self.access, request_id, self.lid)
        state = self.cards.read(self.access, request_id, self.lid)
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(state['error'], 'Daily trial limit reached.')

    def test_existing_annotations_are_used_without_overwriting_them(self):
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO words(lemma,pos,topic,mnemonic,count,lemma_difficulty) VALUES (?,?,?,?,?,?)',
                         ('город', 'NOUN', '["city"]', 'My own city memory.', 7, 3))
        batch = self.prepare()
        with transaction(self.db) as conn:
            word = conn.execute("SELECT * FROM words WHERE lemma='город'").fetchone()
            selection = json.loads(conn.execute('SELECT selection FROM native_card_generation_items').fetchone()[0])
            self.assertEqual((word['count'], word['mnemonic'], json.loads(word['topic'])), (7, 'My own city memory.', ['city']))
            self.assertEqual(selection['mnemonic'], word['mnemonic'])
        self.finish(batch['batch_id'])


class FirstStepsEnrichmentTests(unittest.TestCase):
    setUp = first_steps.FirstStepsPracticeTests.setUp
    post = first_steps.FirstStepsPracticeTests.post
    hello = first_steps.FirstStepsPracticeTests.hello

    def test_chapter_card_capture_uses_the_same_completed_annotations(self):
        self.hello()
        self.post('/api/v1/first-steps/hello/flashcards', status=201)
        with transaction(self.db) as conn:
            for row in conn.execute('SELECT selection FROM native_card_generation_items'):
                selection = json.loads(row[0])
                word = conn.execute('SELECT mnemonic,topic FROM words WHERE id=?', (selection['word_id'],)).fetchone()
                self.assertTrue(word['mnemonic'])
                self.assertEqual(selection['mnemonic'], word['mnemonic'])
                self.assertNotIn('First steps', json.loads(word['topic']))


class GameEnrichmentTests(unittest.TestCase):
    def setUp(self):
        games.GameWordTests.setUp(self)
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/v1/household').json['csrf_token']
        self.path = '/api/v1/games/sessions/capture/words'
        with transaction(self.db, write=True) as conn:
            conn.execute('INSERT INTO journey_game_sessions '
                         '(id,profile_id,game_id,seed,request_ids_json,content_json,completed_at,created_at,updated_at) '
                         "VALUES ('capture','personal-learning','missing-stamp','test','[]',?,2,1,1)", (encoded(self.content),))

    def add(self):
        return self.client.post(self.path, json={'word': 'посылкой', 'lemma': 'посылка'}, headers={'X-CSRF-Token': self.csrf})

    def test_explicit_add_completes_enrichment_after_word_commit(self):
        response = self.add()
        self.assertEqual(response.status_code, 200, response.text)
        with transaction(self.db) as conn:
            word = conn.execute('SELECT * FROM words WHERE id=?', (response.json['word_id'],)).fetchone()
            self.assertTrue(word['mnemonic'])
            self.assertTrue(json.loads(word['topic']))
        again = self.add()
        self.assertFalse(again.json['added'])
        self.assertEqual(again.json['word_id'], response.json['word_id'])

    def test_provider_failure_keeps_word_and_tells_user_to_retry_enrichment(self):
        pipeline = self.app.extensions['services']['SyncService']._get()
        pipeline.pending = True
        failed = self.add()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertIn('The word is saved', failed.json['error']['message'])
        with transaction(self.db) as conn:
            word_id = conn.execute("SELECT id FROM words WHERE lemma='посылка'").fetchone()[0]
        pipeline.pending = False
        completed = self.add()
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json['word_id'], word_id)
        self.assertFalse(completed.json['added'])

    def test_trial_budget_denial_remains_a_429(self):
        self.app.extensions['services']['SyncService']._get().error = TrialDenied('Daily trial limit reached.')
        failed = self.add()
        self.assertEqual(failed.status_code, 429, failed.text)
        self.assertEqual(failed.json['error']['code'], 'trial_limit')
        with transaction(self.db) as conn:
            self.assertIsNotNone(conn.execute("SELECT id FROM words WHERE lemma='посылка'").fetchone())
