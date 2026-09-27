"""Reading course coverage keeps the original server task across feedback saves."""
import json
import sqlite3
import unittest

from services.course_progression import course_snapshot
from tests import test_story_titles
from repositories.learning_repository import timestamp
from services.progression import award

encoded = test_story_titles.encoded


class ReadingCourseContextTests(unittest.TestCase):
    setUp = test_story_titles.StoryTitlePersistenceTests.setUp
    save = test_story_titles.StoryTitlePersistenceTests.save

    def course_count(self):
        with sqlite3.connect(self.service.db_path) as conn:
            return next(topic for chapter in course_snapshot(conn, 'personal-learning')['chapters']
                        for topic in chapter['topics'] if topic['id'] == 'family')['successful_tasks']

    def evidence(self):
        with sqlite3.connect(self.service.db_path) as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT evidence_json FROM progression_events WHERE activity='reading' ORDER BY created_at,rowid")]

    def test_corrected_and_cached_answers_to_original_questions_count_once(self):
        self.save()
        self.service.evaluate_answers.return_value = (['Try again'] * 5, [4] * 5, 4.0, False)
        self.assertEqual(self.client.post('/comprehension/answer', data=self.payload).status_code, 200)
        self.assertEqual(self.course_count(), 0)
        # Corrections may use saved feedback: independence is not the coverage gate.
        self.service.evaluate_answers.return_value = (['Good'] * 5, None, 8.0, False)
        corrected = {**self.payload, 'answers[]': ['Исправленный ответ.'] * 5}
        self.assertEqual(self.client.post('/comprehension/save', data=corrected).status_code, 200)
        self.assertEqual(self.course_count(), 1)
        self.assertEqual(self.client.post('/comprehension/answer', data=corrected).status_code, 200)
        self.assertEqual(self.course_count(), 1)
        self.assertTrue(all(item['course_task_context_matches'] for item in self.evidence()))
        self.assertFalse(self.evidence()[-1]['first_fresh_assessment'])

    def test_edited_questions_cannot_become_trusted_by_saving_and_repeating(self):
        story_id = self.save()
        edited_questions = ['Другой лёгкий вопрос?'] * 5
        edited = {**self.payload, 'story_id': str(story_id),
                  'questions_b64': encoded(json.dumps(edited_questions)),
                  'course_task_context_matches': 'true', 'course_task_questions_hash': 'forged'}
        for route, answer in [('/comprehension/answer', 'Первый ответ.'), ('/comprehension/save', 'Новый ответ.')]:
            with self.subTest(route=route):
                response = self.client.post(route, data={**edited, 'answers[]': [answer] * 5})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.course_count(), 0)
        # Ordinary feedback still saves the edited questions, but they never
        # replace the original question hash in the course evidence receipts.
        self.assertEqual(self.repository.load(story_id)['questions'], edited_questions)
        receipts = self.evidence()
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(item['course_task_context_matches'] is False for item in receipts))
        self.assertEqual(receipts[0]['course_task_questions_hash'], receipts[1]['course_task_questions_hash'])
        self.assertNotEqual(receipts[0]['course_task_questions_hash'], 'forged')
        # Returning to the real original task can still earn preparation.
        response = self.client.post('/comprehension/answer', data={**self.payload, 'story_id': str(story_id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.course_count(), 1)

    def test_pinned_context_is_scoped_to_owner_and_story(self):
        story_id = self.save()
        with sqlite3.connect(self.service.db_path) as conn:
            now = timestamp()
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)", (now,))
            # Neither another profile's receipt for this ID nor this profile's
            # receipt for another ID may supply this task's original hash.
            for owner, content, source in [('other', f'story:{story_id}', 'other-owner'),
                                            ('personal-learning', 'story:9999', 'other-story')]:
                award(conn, owner, activity='reading', content_key=content, source_key=source,
                      title='Scoped receipt', now=now, evidence={'course_task_context_matches': False,
                      'course_task_questions_hash': 'not-this-task'})
        response = self.client.post('/comprehension/answer', data={**self.payload, 'story_id': str(story_id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.course_count(), 1)

    def test_missing_original_context_cannot_be_laundered_into_course_evidence(self):
        # No generated-session context or saved task establishes these questions.
        response = self.client.post('/comprehension/answer', data=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.course_count(), 0)
        response = self.client.post('/comprehension/save', data={**self.payload, 'answers[]': ['Ещё ответ.'] * 5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.course_count(), 0)
        self.assertTrue(all(item['course_task_questions_hash'] is None for item in self.evidence()))


if __name__ == '__main__':
    unittest.main()
