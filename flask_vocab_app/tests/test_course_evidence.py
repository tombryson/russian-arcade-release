"""Course coverage uses saved assessments, independently of daily coin caps."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from migrations import upgrade_database
from repositories.learning_repository import payload_hash, timestamp
from services.course_evidence import freeze_course_evidence
from services.course_progression import checkpoint_start, course_snapshot
from services.progression import award, personal_profile, reverse


class CourseEvidenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = str(Path(directory.name) / 'course.db')
        upgrade_database(path, backup=False)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.pid = personal_profile(self.conn)
        self.now = timestamp()

    def translation(self, topic='greetings', score=4, difficulty=1, task=None, owner=None):
        if task is None:
            task = self.conn.execute('''INSERT INTO sentences(sentence,english,topic,difficulty,owner_profile_id)
                VALUES ('Привет!','Hello!',?,?,?)''', (topic, difficulty, owner or self.pid)).lastrowid
        aid = self.conn.execute('''INSERT INTO translation_attempts
            (sentence_id,response,score,strength,next_step,example,ui_language,created_at,coins_earned,elo_change,already_rewarded)
            VALUES (?,'Привет!',?,'Clear','Continue','Привет!','en',?,0,0,0)''', (task, score, str(self.now))).lastrowid
        return task, aid

    def credit(self, task, attempt, **evidence):
        return award(self.conn, self.pid, activity='translation', content_key=f'translation:{task}',
                     source_key=f'translation-attempt:{attempt}', title='Translation', now=self.now,
                     evidence={'score': 4, 'score_max': 4, **evidence})

    def topic(self, topic='greetings'):
        return next(t for c in course_snapshot(self.conn, self.pid)['chapters'] for t in c['topics'] if t['id'] == topic)

    def test_saved_score_and_topic_override_forged_metadata(self):
        task, attempt = self.translation(score=0)
        self.credit(task, attempt, _course={'topic_id': 'family', 'level': 'A1', 'score': 1, 'assisted': False})
        saved = json.loads(self.conn.execute('SELECT evidence_json FROM progression_events').fetchone()[0])
        self.assertEqual(saved['_course']['topic_id'], 'greetings')
        self.assertEqual(saved['_course']['score'], 0)
        self.assertEqual(self.topic()['successful_tasks'], 0)

    def test_later_correction_counts_once_and_independent_task_is_needed(self):
        task, attempt = self.translation(score=0)
        self.credit(task, attempt)
        _, improved = self.translation(task=task)
        self.credit(task, improved, assisted=True)
        _, repeat = self.translation(task=task)
        self.credit(task, repeat)
        self.assertEqual(self.topic()['successful_tasks'], 1)
        self.assertFalse(self.topic()['completed'])
        self.credit(*self.translation())
        self.assertTrue(self.topic()['completed'])
        self.assertEqual(course_snapshot(self.conn, self.pid)['chapters'][0]['activity_count'], 1)
        self.assertEqual(course_snapshot(self.conn, self.pid)['chapters'][0]['status'], 'practice')

    def test_course_keeps_recording_after_coin_allowance(self):
        amounts = [self.credit(*self.translation(topic=topic)) for topic in
                   ('greetings', 'greetings', 'numbers', 'numbers', 'family', 'family')]
        self.assertEqual(amounts, [3, 3, 3, 3, 0, 0])
        self.assertEqual(self.topic('family')['successful_tasks'], 2)

    def test_standalone_activity_work_prepares_without_creating_target_evidence(self):
        self.credit(*self.translation())
        chapter = course_snapshot(self.conn, self.pid)['chapters'][0]
        self.assertAlmostEqual(chapter['progress'], 1 / 6)
        self.assertEqual(chapter['preparation_basis'], 'activity_practice')
        self.assertEqual(chapter['target_preparation_progress'], 0)
        self.assertEqual(chapter['target_coverage']['prepared_count'], 0)
        self.credit(*self.translation())
        for topic in ('family', 'home'):
            self.credit(*self.translation(topic=topic))
            self.credit(*self.translation(topic=topic))
        self.assertEqual(course_snapshot(self.conn, self.pid)['chapters'][0]['progress'], .5)
        questions, answers = ['Как зовут девочку?'], ['Анна.']
        sid = self.conn.execute('''INSERT INTO saved_stories(title,topic,difficulty,text,questions,answers,score,owner_profile_id)
            VALUES ('Анна','family','A1','Это Анна.',?,?,8,?)''', (json.dumps(questions), json.dumps(answers), self.pid)).lastrowid
        digest = payload_hash({'story_id': sid, 'questions': questions, 'answers': answers})
        source = f'story-check:{digest}:activity-route'
        award(self.conn, self.pid, activity='reading', content_key=f'story:{sid}', source_key=source,
              title='Reading', target_level='A1', evidence={'course_task_context_matches': True}, now=self.now)
        course = course_snapshot(self.conn, self.pid)
        chapter = course['chapters'][0]
        self.assertEqual((chapter['status'], chapter['activity_preparation_progress'], chapter['progress']), ('ready', 1, 1))
        self.assertEqual(chapter['target_preparation_progress'], 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
        self.assertFalse(course['awards_proficiency_level'])
        attempt = checkpoint_start(self.conn, self.pid, 'home', 'normal-after-activities')
        self.assertEqual(attempt['status'], 'active')
        reverse(self.conn, self.pid, 'reading', source)
        self.assertEqual(course_snapshot(self.conn, self.pid)['chapters'][0]['progress'], .5)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)

    def test_other_owners_wrong_task_ids_and_unmapped_topics_do_not_credit(self):
        self.conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)", (self.now,))
        task, attempt = self.translation(owner='other')
        self.credit(task, attempt)
        task, attempt = self.translation(topic='any')
        self.credit(task, attempt)
        another, _ = self.translation()
        self.credit(another, attempt)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_evidence').fetchone()[0], 0)

    def test_task_level_does_not_come_from_word_difficulty_or_caller(self):
        self.credit(*self.translation(difficulty=2), _course={'topic_id':'greetings','level':'A1','score':1,'assisted':False})
        self.assertEqual(self.topic()['successful_tasks'], 0)

    def test_reversal_does_not_discard_another_successful_receipt(self):
        task, a = self.translation()
        self.credit(task, a)
        _, b = self.translation(task=task)
        self.credit(task, b)
        reverse(self.conn, self.pid, 'translation', f'translation-attempt:{a}')
        self.assertEqual(self.topic()['successful_tasks'], 1)
        reverse(self.conn, self.pid, 'translation', f'translation-attempt:{b}')
        self.assertEqual(self.topic()['successful_tasks'], 0)

    def test_reading_binds_saved_questions_answers_and_owner(self):
        questions, answers = ['Как зовут девочку?'], ['Анна.']
        sid = self.conn.execute('''INSERT INTO saved_stories(title,topic,difficulty,text,questions,answers,score,owner_profile_id)
            VALUES ('Анна','family','A1','Это Анна.',?,?,8,?)''', (json.dumps(questions), json.dumps(answers), self.pid)).lastrowid
        digest = payload_hash({'story_id':sid,'questions':questions,'answers':answers})
        meta = freeze_course_evidence(self.conn,self.pid,'reading',f'story:{sid}',f'story-check:{digest}:today',
                                     {'course_task_context_matches':True})
        self.assertEqual(meta['_course']['score'], .8)
        self.assertNotIn('_course', freeze_course_evidence(self.conn,self.pid,'reading',f'story:{sid}','story-check:forged:today',meta))
        self.assertNotIn('_course', freeze_course_evidence(self.conn,self.pid,'reading',f'story:{sid}',
            f'story-check:{digest}:today', {'course_task_context_matches':False}))

    def test_self_reported_flashcard_ratings_cannot_claim_chapter_coverage(self):
        self.assertNotIn('_course', freeze_course_evidence(self.conn,self.pid,'flashcards','card','review',
            {'rating':'easy','_course':{'topic_id':'greetings','level':'A1','score':1,'assisted':False}}))


if __name__ == '__main__':
    unittest.main()
