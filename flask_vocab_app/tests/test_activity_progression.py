"""Legacy activities join the shared ledger without rewriting old points."""
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

from repositories.learning_repository import transaction, timestamp
from repositories.translation_repository import TranslationRepository
from repositories.writing_repository import WritingRepository
from services.comprehension_service import ComprehensionService
from services.progression import snapshot
from services.user_service import UserService
from services.word_jumble_service import WordJumbleService
from tests.support import isolated_app
from tests.test_lessons import FakeAI as LessonAI, picture


ASSESSMENT = {'score': 0, 'strength': 'You attempted the sentence.',
              'next_step': 'Try the suggested ending.', 'example': 'Кот спит дома.'}


class ActivityProgressionTests(unittest.TestCase):
    def setUp(self):
        self.lesson_ai = LessonAI()
        self.app = isolated_app(self, {'LessonAI': self.lesson_ai})
        self.app.config['LESSON_BACKGROUND_ENABLED'] = False
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        state = self.client.get('/api/v1/household').json
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = state['csrf_token']
        self.translations = TranslationRepository(self.db)
        self.writing = WritingRepository(self.db)
        self.jumble = WordJumbleService.__new__(WordJumbleService)
        self.jumble.db_path = self.db
        self.jumble._assess = Mock(return_value={
            'score': 0, 'commentary': 'You tried expressing an idea.', 'corrections': [],
            'polished_sentence': 'Кот спит.', 'phrasing_note': '', 'extension': ''})
        self.comp = self.app.extensions['learning']['lessons']
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for key in ('conversation', 'live_conversation'):
            service = self.app.extensions['learning'][key]
            service.executor.shutdown(wait=True)
            if getattr(service, 'reviews', None):
                service.reviews.executor.shutdown(wait=True)

    def counts(self, *tables):
        with transaction(self.db) as conn:
            return tuple(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in tables)

    def progress(self):
        with transaction(self.db) as conn:
            return snapshot(conn, 'personal-learning')

    def sentence(self, suffix=''):
        return self.translations.save_content('Кот спит дома.' + suffix, 'The cat sleeps at home.' + suffix, 'home', 5)[0]

    def writing_task(self):
        return self.writing.create({'title': 'Дома', 'title_en': 'At home', 'task': 'Опишите дом.',
            'task_en': 'Describe your home.', 'required_words': ['дом', 'кот', 'стол']}, 'home', 'advanced', 30)

    def story(self, *, assessed=True, answers=None, story_id=None, progression_result=None):
        service = ComprehensionService.__new__(ComprehensionService)
        service.db_path = self.db
        return service.save_story(title='Дома', title_en='At home', topic='home', difficulty='advanced',
            text='Кот спит дома.', audio_url='', image_url='', questions=['Где кот?'],
            answers=['Кот спать улица.'] if answers is None else answers,
            feedback=['You attempted the question. Try the location again.'], score=0,
            assessed=assessed, story_id=story_id, progression_result=progression_result)

    def lesson(self):
        material = self.comp.files.receive(picture(), 'lesson.png')
        lid, rid, _ = self.comp.create('My lesson', 'Practise endings', [material])
        self.comp.process(rid)
        return lid, rid, self.comp.snapshot(lid, 'personal-learning')['tasks']

    def test_creation_and_drafts_award_nothing(self):
        sid = self.sentence()
        self.translations.save_draft(sid, 'Мой ответ.', 0)
        wid = self.writing_task()
        self.writing.save(wid, 'Мой черновик.', 0)
        game = self.jumble.create_game('any', 'easy')
        self.jumble.save_draft(game['id'], 'Мой черновик.', 0)
        self.story(assessed=False)
        self.lesson()
        self.assertEqual(self.counts('progression_events', 'progression_entries'), (0, 0))

    def test_three_activities_award_equal_participation_for_incorrect_answers(self):
        sid = self.sentence()
        self.translations.save_check(sid, 'Я спать дом.', 0, ASSESSMENT, 'en')
        wid = self.writing_task()
        self.writing.save(wid, 'Я спать дом.', 0, ASSESSMENT)
        game = self.jumble.create_game('any', 'easy')
        self.jumble.mark_response(game['id'], 'Я спать дом.', 0)
        self.assertEqual(self.progress()['earned_total'], 9)
        with transaction(self.db) as conn:
            self.assertEqual([row[0] for row in conn.execute('SELECT amount FROM progression_entries')], [3, 3, 3])
            self.assertEqual(tuple(conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone()), (0, 1000))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM reward_events').fetchone()[0], 0)
            self.assertTrue(all(row[0] is None for row in conn.execute('SELECT target_level FROM progression_events')))

    def test_saved_a1_assessments_contribute_to_course_topic_practice(self):
        sentence = self.translations.save_content('Привет, Анна!', 'Hello, Anna!', 'greetings', 1)[0]
        self.translations.save_check(sentence, 'Привет, Анна!', 0, ASSESSMENT | {'score':4}, 'en')
        writing = self.writing.create({'title':'Моя семья','title_en':'My family',
            'task':'Напишите о семье.','task_en':'Write about your family.',
            'required_words':['мама','папа','семья']}, 'family', 'A1', 30)
        self.writing.save(writing, 'Это моя мама. Это мой папа.', 0, ASSESSMENT | {'score':8})
        with patch.object(self.jumble, 'get_words', return_value=['один','два','час','день','утро','вечер']):
            game = self.jumble.create_game('numbers', 'A1')
        self.jumble._assess.return_value['score'] = 3
        self.jumble.mark_response(game['id'], 'Сейчас два часа.', 0)
        course = self.progress()['course']
        self.assertEqual(course['release_id'], 'a1-journey-v2')
        chapter = course['chapters'][0]
        self.assertEqual({t['id']:t['successful_tasks'] for t in chapter['topics']},
                         {'greetings':1,'family':1,'home':0})
        self.assertEqual(chapter['activity_count'], 2)
        post_office = course['chapters'][1]
        self.assertEqual(post_office['status'], 'locked')
        self.assertEqual(post_office['topics'], [])
        self.assertEqual(post_office['title'], '')
        # Two of six topic tasks prepare the checkpoint without inventing
        # detailed target evidence or requiring entry through Journey.
        self.assertAlmostEqual(chapter['progress'], 1 / 3)
        self.assertEqual(chapter['preparation_basis'], 'activity_practice')
        self.assertEqual(chapter['target_coverage']['prepared_count'], 0)
        # Later-topic work is hidden, not discarded. Complete the preceding
        # authored checkpoint and verify the saved task becomes visible.
        from services.course_progression import checkpoint_start, checkpoint_listened, checkpoint_answer
        with transaction(self.db, write=True) as conn:
            recorded = conn.execute('''SELECT c.activity,c.content_key,c.score,c.target_level
                FROM course_evidence c JOIN progression_events e ON e.id=c.event_id
                WHERE c.profile_id=? AND e.profile_id=c.profile_id AND c.topic_id='numbers'
                AND e.reversed_at IS NULL''', ('personal-learning',)).fetchall()
            self.assertEqual([tuple(row) for row in recorded],
                             [('word_jumble', 'word-jumble:' + game['id'], .75, 'A1')])
            attempt = checkpoint_start(conn, 'personal-learning', 'home', 'unlock-saved-topic', True)
            frozen = json.loads(conn.execute('SELECT frozen_json FROM course_checkpoint_attempts WHERE id=?',
                                             (attempt['id'],)).fetchone()[0])
            checkpoint_listened(conn, 'personal-learning', attempt['id'])
            passed = checkpoint_answer(conn, 'personal-learning', attempt['id'],
                {question['id']: question['answer'] for question in frozen['variant']['questions']}, 'pass-saved-topic')
        self.assertTrue(passed['result']['passed'])
        post_office = self.progress()['course']['chapters'][1]
        self.assertEqual(post_office['status'], 'practice')
        self.assertEqual({topic['id']: topic['successful_tasks'] for topic in post_office['topics']},
                         {'numbers': 1, 'daily_activities': 0})
        self.assertEqual(post_office['activity_count'], 1)

    def test_repeat_check_is_capped_per_content_and_a_new_day_can_earn_again(self):
        sid = self.sentence()
        current = timestamp()
        with patch('services.progression.timestamp', return_value=current):
            self.translations.save_check(sid, 'Первый ответ.', 0, ASSESSMENT, 'en')
            self.translations.save_check(sid, 'Второй ответ.', 1, ASSESSMENT, 'en')
        self.assertEqual(self.progress()['earned_total'], 3)
        with patch('services.progression.timestamp', return_value=current + 86400):
            self.translations.save_check(sid, 'Третий ответ.', 2, ASSESSMENT, 'en')
        self.assertEqual(self.progress()['earned_total'], 6)

    def test_activity_daily_cap_is_shared_across_legacy_activity_types(self):
        for number in range(3):
            sid = self.sentence(str(number))
            self.translations.save_check(sid, 'Ответ.', 0, ASSESSMENT, 'en')
        wid = self.writing_task()
        self.writing.save(wid, 'Ответ.', 0, ASSESSMENT)
        game = self.jumble.create_game('any', 'easy')
        self.jumble.mark_response(game['id'], 'Ответ.', 0)
        self.assertEqual(self.progress()['earned_total'], 12)
        self.assertEqual(self.counts('progression_events', 'progression_entries'), (5, 4))

    def test_reward_storage_failure_rolls_back_translation_and_writing_attempts(self):
        sid, wid = self.sentence(), self.writing_task()
        with transaction(self.db, write=True) as conn:
            conn.execute("CREATE TRIGGER fail_progress BEFORE INSERT ON progression_entries BEGIN SELECT RAISE(ABORT,'test failure'); END")
        for action in (lambda: self.translations.save_check(sid, 'Ответ.', 0, ASSESSMENT, 'en'),
                       lambda: self.writing.save(wid, 'Ответ.', 0, ASSESSMENT)):
            with self.assertRaises(sqlite3.IntegrityError):
                action()
        self.assertEqual(self.counts('translation_attempts', 'translation_drafts', 'writing_attempts',
                                    'writing_drafts', 'progression_events', 'progression_entries'), (0, 0, 0, 0, 0, 0))

    def test_reading_save_and_reward_are_atomic_and_duplicate_checks_are_free(self):
        details = {}
        sid = self.story(progression_result=details)
        self.assertEqual(details['coins_earned'], 3)
        self.assertEqual(self.progress()['earned_total'], 3)
        self.story(story_id=sid, progression_result=details)
        self.assertEqual(details['coins_earned'], 0)
        self.assertEqual(self.counts('progression_events', 'progression_entries'), (1, 1))
        with patch('services.progression.timestamp', return_value=timestamp() + 86400):
            self.story(story_id=sid, progression_result=details)
        self.assertEqual(details['coins_earned'], 3)
        self.assertEqual(self.progress()['earned_total'], 6)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM user_stories').fetchone()[0], 0)

    def test_reading_failed_award_rolls_back_the_saved_answers(self):
        sid = self.story(assessed=False, answers=[])
        with transaction(self.db, write=True) as conn:
            before = dict(conn.execute('SELECT * FROM saved_stories WHERE id=?', (sid,)).fetchone())
            conn.execute("CREATE TRIGGER fail_progress BEFORE INSERT ON progression_entries BEGIN SELECT RAISE(ABORT,'test failure'); END")
        self.assertIsNone(self.story(story_id=sid))
        with transaction(self.db) as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM saved_stories WHERE id=?', (sid,)).fetchone()), before)
        self.assertEqual(self.counts('progression_events', 'progression_entries'), (0, 0))

    def test_blank_or_partial_reading_is_not_completion(self):
        for answers in ([], [' '], ['Ответ', 'Лишний ответ']):
            with self.assertRaises(ValueError):
                self.story(answers=answers)
        self.assertEqual(self.counts('saved_stories', 'progression_entries'), (0, 0))

    def test_reading_provider_failure_is_not_a_zero_grade_or_completion(self):
        service = ComprehensionService.__new__(ComprehensionService)
        service.db_path = self.db
        service._evaluate_answers = Mock(side_effect=RuntimeError('provider unavailable'))
        with self.assertRaisesRegex(ValueError, 'could not be checked'):
            service.evaluate_answers('Кот спит дома.', ['Где кот?'], ['Дома.'], 1)
        self.assertEqual(self.counts('saved_stories', 'progression_entries'), (0, 0))

    def test_household_legacy_workspace_does_not_award_to_personal_or_selected_learner(self):
        self.app.config['WORD_POST_HOUSEHOLD_ENABLED'] = True
        with self.app.test_request_context('/sentence/assess'):
            sid = self.sentence()
            self.translations.save_check(sid, 'Ответ.', 0, ASSESSMENT, 'en')
            wid = self.writing_task()
            self.writing.save(wid, 'Ответ.', 0, ASSESSMENT)
            game = self.jumble.create_game('any', 'easy')
            self.jumble.mark_response(game['id'], 'Ответ.', 0)
            self.story()
        self.assertEqual(self.counts('progression_events', 'progression_entries'), (0, 0))

    def test_lesson_awards_on_final_checked_task_and_not_repeat_checks(self):
        lid, rid, tasks = self.lesson()
        self.lesson_ai.assess = Mock(return_value={'outcome': 'try_again', 'feedback': {'en': 'Try an ending.', 'ru': 'Попробуйте окончание.'},
                                                 'corrections': [], 'model_answer': 'В новых городах.'})
        for index, task in enumerate(tasks):
            key = f'lesson-answer-{index:08d}'
            self.comp.assess('personal-learning', lid, task['id'], 'В новый городах.', 0, key)
            self.assertEqual(self.progress()['earned_total'], 3 if index == len(tasks) - 1 else 0)
        last = tasks[-1]
        self.comp.assess('personal-learning', lid, last['id'], 'В новый городах.', 0, f'lesson-answer-{len(tasks)-1:08d}')
        with patch('services.progression.timestamp', return_value=timestamp() + 86400):
            self.comp.assess('personal-learning', lid, last['id'], 'В новых городах.', 1, 'lesson-recheck-00000001')
        self.assertEqual(self.progress()['earned_total'], 3)
        self.assertEqual(self.counts('progression_events'), (1,))

    def test_lesson_final_check_and_reward_commit_together(self):
        lid, _, tasks = self.lesson()
        for index, task in enumerate(tasks[:-1]):
            self.comp.assess('personal-learning', lid, task['id'], 'Ответ.', 0, f'lesson-answer-{index:08d}')
        with transaction(self.db, write=True) as conn:
            conn.execute("CREATE TRIGGER fail_progress BEFORE INSERT ON progression_entries BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.comp.assess('personal-learning', lid, tasks[-1]['id'], 'Ответ.', 0, 'lesson-final-00000001')
        with transaction(self.db) as conn:
            state = conn.execute("SELECT state FROM lesson_attempts WHERE submission_key='lesson-final-00000001'").fetchone()[0]
            self.assertEqual(state, 'checking')
        self.assertEqual(self.counts('progression_events', 'progression_entries'), (0, 0))

    def test_deprecated_score_and_anki_calls_preserve_old_totals_and_anki_records(self):
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE users SET lingocoins=75,elo_rating=1250 WHERE user_id=1')
            form = conn.execute('SELECT id,word_id FROM forms LIMIT 1').fetchone()
            conn.execute('INSERT INTO anki_cards(card_id,form_id,word_id,interval,lapses,reps) VALUES (111,?,?,10,0,5)', tuple(form))
            before = dict(conn.execute('SELECT * FROM anki_cards WHERE card_id=111').fetchone())
        service = UserService(self.db)
        self.assertEqual(service.update_user_stats(1, 10, 10, 5, 'add_word')['lingocoins_earned'], 0)
        result = service.check_anki_cards(1)
        self.assertEqual((result['lingocoins_earned'], result['cards_processed'], result['cards_eligible']), (0, 0, 1))
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute('SELECT lingocoins,elo_rating FROM users WHERE user_id=1').fetchone()), (75, 1250))
            self.assertEqual(dict(conn.execute('SELECT * FROM anki_cards WHERE card_id=111').fetchone()), before)
        self.assertEqual(self.counts('progression_events', 'progression_entries'), (0, 0))

    def test_stats_display_shared_balance_without_elo(self):
        sid = self.sentence()
        self.translations.save_check(sid, 'Ответ.', 0, ASSESSMENT, 'en')
        self.assertEqual(self.client.get('/user/stats').status_code, 204)
        introduced = self.client.post('/api/v1/onboarding', json={'milestone': 'coins'})
        self.assertEqual(introduced.status_code, 200)
        response = self.client.get('/user/stats')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Lingocoins:</strong> 3', html)
        self.assertNotIn('ELO', html)

    def test_anki_accessory_describes_stats_instead_of_promising_coins(self):
        response = self.client.post('/review_cards')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Anki progress stays in Anki', html)
        self.assertNotIn('Coins earned:', html)
        self.assertNotIn('Processed 0 Anki cards', html)
        self.assertIn('Check Anki stats', self.client.get('/tools/anki/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
