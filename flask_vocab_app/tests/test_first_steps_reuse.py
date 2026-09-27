"""Reuse exact native items without losing pending media or recreating cards."""
import json
import unittest

from repositories.learning_repository import LearningError, encoded, transaction
from tests import test_first_steps_practice as practice


class FirstStepsReuseTests(unittest.TestCase):
    setUp = practice.FirstStepsPracticeTests.setUp
    post = practice.FirstStepsPracticeTests.post
    hello = practice.FirstStepsPracticeTests.hello
    chapter = practice.FirstStepsPracticeTests.chapter
    finish_batch = practice.FirstStepsPracticeTests.finish_batch

    def create(self, lesson):
        return self.post('/api/v1/first-steps/' + lesson + '/flashcards', status=201)

    def finish_with_failures(self, batch):
        for _ in range(150):
            batch = self.gen.next(self.access, batch['id'])
            if batch['complete']:
                return batch
        self.fail('The selected native items did not finish.')

    def test_chapter_finishes_pending_earlier_items_and_media_without_duplicates(self):
        self.chapter()
        earlier = self.create('hello')
        self.assertEqual(earlier['first_steps']['url'], '/#first-delivery')
        original_ids = {item['id'] for item in earlier['items']}
        chapter = self.create('chapter')
        self.assertFalse(chapter['complete'])
        self.assertEqual({item['id'] for item in chapter['items'] if item['reused']}, original_ids)
        self.assertEqual(len(chapter['items']), len({item['id'] for item in chapter['items']}))
        done = self.finish_batch(chapter)
        self.assertTrue(self.gen.read(self.access, earlier['id'])['complete'])
        self.assertEqual(self.gen.read(self.access, earlier['id'])['saved'], 3)
        self.assertEqual(self.create('chapter')['id'], chapter['id'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_generation_items').fetchone()[0], done['total'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], done['total'])
        self.assertEqual(self.text.calls, [])

    def test_lesson_reuses_only_its_items_from_an_unfinished_chapter(self):
        self.chapter()
        chapter = self.create('chapter')
        lesson = self.create('hello')
        self.assertEqual(lesson['total'], 3)
        self.assertTrue(all(item['reused'] for item in lesson['items']))
        self.finish_batch(lesson)
        state = self.gen.read(self.access, chapter['id'])
        selected = {item['id'] for item in lesson['items']}
        self.assertFalse(state['complete'])
        self.assertEqual(state['saved'], 3)
        self.assertTrue(all(item['status'] == 'pending' for item in state['items'] if item['id'] not in selected))
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions').fetchone()[0], 3)

    def test_card_and_media_retry_reach_selected_references(self):
        self.chapter()
        earlier = self.create('hello')
        failed = earlier['items'][0]['id']
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE native_card_generation_items SET status='failed',error='Temporary failure' WHERE id=?", (failed,))
        chapter = self.create('chapter')
        self.assertEqual(next(item for item in chapter['items'] if item['id'] == failed)['status'], 'failed')
        retried = self.post('/api/v1/card-generation/batches/' + chapter['id'] + '/retry-cards')
        self.assertEqual(next(item for item in retried['items'] if item['id'] == failed)['status'], 'pending')
        media = self.app.extensions['learning']['card_media'].provider
        media.fail.add('image')
        done = self.finish_with_failures(chapter)
        self.assertTrue(all(any(job['status'] == 'failed' for job in item['media_jobs']) for item in done['items']))
        media.fail.clear()
        self.post('/api/v1/card-generation/batches/' + chapter['id'] + '/retry-media')
        self.finish_batch(chapter)
        previous = self.gen.read(self.access, earlier['id'])
        self.assertTrue(all(job['status'] == 'saved' for item in previous['items'] for job in item['media_jobs']))

    def test_retired_reused_card_stays_removed(self):
        self.chapter()
        earlier = self.finish_batch(self.create('hello'))
        retired = earlier['items'][0]
        self.app.extensions['learning']['card_authoring'].retire(self.access, retired['card_id'])
        chapter = self.create('chapter')
        shown = next(item for item in chapter['items'] if item['id'] == retired['id'])
        self.assertEqual(shown['status'], 'removed')
        done = self.finish_with_failures(chapter)
        self.assertEqual(next(item for item in done['items'] if item['id'] == retired['id'])['status'], 'removed')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT retired FROM card_definitions WHERE id=?', (retired['card_id'],)).fetchone()[0], 1)
            before = conn.execute('SELECT COUNT(*) FROM native_card_generation_items').fetchone()[0]
        self.create('hello')
        self.create('chapter')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_generation_items').fetchone()[0], before)

    def test_old_skip_only_batch_is_repaired_by_the_same_create_request(self):
        self.chapter()
        earlier = self.create('hello')
        chapter = self.create('chapter')
        with transaction(self.db, write=True) as conn:
            options = json.loads(conn.execute('SELECT options FROM native_card_batches WHERE id=?', (chapter['id'],)).fetchone()[0])
            del options['first_steps']['reused_items']
            conn.execute('UPDATE native_card_batches SET options=? WHERE id=?', (encoded(options), chapter['id']))
        repaired = self.create('chapter')
        self.assertEqual(repaired['id'], chapter['id'])
        self.assertEqual({item['id'] for item in repaired['items'] if item['reused']}, {item['id'] for item in earlier['items']})

    def test_foreign_forward_and_malformed_references_fail_closed(self):
        self.chapter()
        earlier = self.create('hello')
        chapter = self.create('chapter')
        with transaction(self.db) as conn:
            original = json.loads(conn.execute('SELECT options FROM native_card_batches WHERE id=?', (chapter['id'],)).fetchone()[0])
        valid = original['first_steps']['reused_items'][0]
        for references in ('not a list', [{}], [valid | {'batch_id': chapter['id']}], [valid | {'identity': 'wrong'}]):
            options = json.loads(json.dumps(original))
            options['first_steps']['reused_items'] = references
            with transaction(self.db, write=True) as conn:
                conn.execute('UPDATE native_card_batches SET options=? WHERE id=?', (encoded(options), chapter['id']))
            with self.subTest(references=references), self.assertRaises(LearningError) as error:
                self.gen.next(self.access, chapter['id'])
            self.assertEqual(error.exception.status, 409)
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE native_card_batches SET options=? WHERE id=?', (encoded(original), chapter['id']))
            conn.execute("UPDATE native_card_batches SET owner_id='another-profile' WHERE id=?", (earlier['id'],))
        with self.assertRaises(LearningError):
            self.gen.read(self.access, chapter['id'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM native_card_generation_items WHERE status!='pending'").fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
