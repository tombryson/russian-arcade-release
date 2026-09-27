"""Separate saved practice and grades for named local users, with no providers."""
import base64
from contextlib import contextmanager
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from flask import session

from migrations import MIGRATION_DIR, upgrade_database
from repositories.learning_repository import timestamp, transaction
from repositories.sentence_repository import SentenceRepository
from repositories.story_repository import StoryRepository
from repositories.translation_repository import TranslationRepository
from repositories.writing_repository import WritingRepository
from services.comprehension_service import ComprehensionService
from services.lesson_service import LessonService
from services.progression import snapshot
from services.user_service import UserService
from services.word_jumble_service import WordJumbleService
from tests.support import isolated_app, select_test_profile


TASK = dict(title='Мой дом', title_en='My home', task='Опишите дом.',
            task_en='Describe your home.', required_words=['дом', 'кот', 'стол'])
ADVICE = dict(score=3, strength='Clear meaning.', next_step='Try a longer answer.', example='Кот дома.')
STORY = dict(title='Кот дома', title_en='The cat at home', topic='home', difficulty='beginner',
             text='Кот дома.', audio_url='/static/media/story.mp3', image_url='',
             questions=['Где кот?'], answers=[], feedback=[], score=0)


class ActivityOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.reading = ComprehensionService.__new__(ComprehensionService)
        self.reading._evaluate_answers = Mock(return_value=(['Good'], [8], 8))
        self.writing_ai = Mock()
        self.sentence_ai = Mock()
        self.jumble = WordJumbleService.__new__(WordJumbleService)
        self.jumble._assess = Mock(return_value={
            'score': 3, 'commentary': 'Clear meaning.', 'corrections': [],
            'polished_sentence': 'Кот дома.', 'phrasing_note': '', 'extension': ''})
        self.app = isolated_app(self, {
            'ComprehensionService': self.reading, 'WritingService': self.writing_ai,
            'SentenceService': self.sentence_ai, 'WordJumbleService': self.jumble,
        }, signed_in=False)
        self.db = self.app.config['DB_PATH']
        self.reading.db_path = self.jumble.db_path = self.db
        self.translations = TranslationRepository(self.db)
        self.writing = WritingRepository(self.db)
        self.stories = StoryRepository(self.db)
        self.sentences = SentenceRepository(self.db)
        now = timestamp()
        self.credentials = {'personal-learning': 'access-me', 'other': 'access-other'}
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)", (now,))
            for profile, credential in self.credentials.items():
                conn.execute('INSERT INTO household_access VALUES (?,?,?,?)', (credential, profile, now + 86400, now + 86400))
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for name in ('conversation', 'live_conversation'):
            service = self.app.extensions['learning'][name]
            service.executor.shutdown(wait=True)
            if getattr(service, 'reviews', None):
                service.reviews.executor.shutdown(wait=True)

    @contextmanager
    def as_user(self, profile):
        with self.app.test_request_context('/'):
            session['personal_access_id'] = self.credentials[profile]
            yield

    def create_all(self):
        return {
            'translation': self.translations.save_content('Кот дома.', 'The cat is at home.', 'home', 1)[0],
            'writing': self.writing.create(TASK, 'home', 'beginner', 30),
            'jumble': self.jumble.create_game('any', 'easy')['id'],
            'reading': self.reading.save_story(**STORY),
        }

    def grade_all(self, ids, answer):
        self.translations.save_draft(ids['translation'], answer, 0)
        self.translations.save_check(ids['translation'], answer, 1, ADVICE, 'en')
        self.writing.save(ids['writing'], answer, 0)
        self.writing.save(ids['writing'], answer, 1, ADVICE)
        self.jumble.save_draft(ids['jumble'], answer, 0)
        self.jumble.mark_response(ids['jumble'], answer, 1)
        self.reading.save_story(**(STORY | {'answers': [answer], 'feedback': ['Good'], 'score': 8}),
                               story_id=ids['reading'], assessed=True, fresh_assessment=True)

    def test_two_users_keep_separate_drafts_grades_coins_and_identical_content(self):
        saved = {}
        for profile, answer in [('personal-learning', 'Мой первый ответ.'), ('other', 'Совсем другой ответ.')]:
            with self.as_user(profile):
                saved[profile] = self.create_all()
                self.grade_all(saved[profile], answer)
                ids = saved[profile]
                self.assertEqual([item['id'] for item in self.translations.list_saved()], [ids['translation']])
                self.assertEqual([item['id'] for item in self.sentences.list_saved()], [ids['translation']])
                self.assertEqual([item['id'] for item in self.writing.list_saved()], [ids['writing']])
                self.assertEqual([item['id'] for item in self.jumble.get_saved_games()], [ids['jumble']])
                self.assertEqual([item['id'] for item in self.stories.list_saved()], [ids['reading']])
                self.assertEqual([item['id'] for item in self.reading.get_saved_stories()], [ids['reading']])
                self.assertEqual(self.translations.load(ids['translation'])['draft'], answer)
                self.assertEqual(self.writing.load(ids['writing'])['draft'], answer)
                self.assertEqual(self.jumble.get_game(ids['jumble'])['draft'], answer)
                self.assertEqual(self.stories.load(ids['reading'])['answers'], [answer])
                self.assertEqual(self.reading.find_existing_story(STORY['text'], 'home', 'beginner'), ids['reading'])
                self.assertEqual(self.stories.find_existing(STORY['text'], 'home', 'beginner'), ids['reading'])
                self.assertEqual(self.translations.save_content('Кот дома.', 'The cat is at home.', 'home', 1), (ids['translation'], False))
                with transaction(self.db) as conn:
                    state = snapshot(conn, profile)
                    self.assertEqual(state['balance'], 12)
                    self.assertTrue(all(event['profile_id'] == profile for event in conn.execute('SELECT profile_id FROM progression_events WHERE profile_id=?', (profile,))))
                    stats = UserService.stats_in_transaction(conn)
                    self.assertEqual(stats['lingocoins'], 12)
                    self.assertEqual(stats['elo_rating'], 1000 if profile == 'personal-learning' else None)
        for activity in saved['other']:
            self.assertNotEqual(saved['other'][activity], saved['personal-learning'][activity])
        with self.as_user('personal-learning'):
            self.assertEqual(self.writing.load(saved['personal-learning']['writing'])['draft'], 'Мой первый ответ.')

    def test_foreign_ids_are_hidden_and_cannot_change_drafts_grades_or_audio(self):
        with self.as_user('personal-learning'):
            ids = self.create_all()
            self.grade_all(ids, 'Мой ответ.')
        with transaction(self.db) as conn:
            tables = ('sentences', 'translation_drafts', 'translation_attempts', 'writing_exercises',
                      'writing_drafts', 'writing_attempts', 'word_jumble_games', 'word_jumble_drafts',
                      'word_jumble_attempts', 'saved_stories', 'progression_events', 'progression_entries')
            before = {table: [tuple(row) for row in conn.execute('SELECT * FROM ' + table)] for table in tables}
        with self.as_user('other'):
            for load, key in ((self.translations.load, 'translation'), (self.sentences.load, 'translation'),
                              (self.writing.load, 'writing'), (self.jumble.get_game, 'jumble'),
                              (self.stories.load, 'reading'), (self.reading.load_story, 'reading')):
                self.assertIsNone(load(ids[key]))
            self.assertEqual(self.reading.get_existing_feedback(ids['reading']), (None, None, None))
            actions = (
                lambda: self.translations.save_draft(ids['translation'], 'Intruder', 2),
                lambda: self.translations.save_check(ids['translation'], 'Intruder', 2, ADVICE, 'en'),
                lambda: self.translations.save_audio(ids['translation'], '/static/media/other.mp3'),
                lambda: self.writing.save(ids['writing'], 'Intruder', 2),
                lambda: self.writing.save(ids['writing'], 'Intruder', 2, ADVICE),
                lambda: self.jumble.save_draft(ids['jumble'], 'Intruder', 2),
                lambda: self.jumble.mark_response(ids['jumble'], 'Intruder', 2),
                lambda: self.reading.save_story(**STORY, story_id=ids['reading']),
                lambda: self.reading.evaluate_answers(STORY['text'], STORY['questions'], ['Intruder'], None, ids['reading']),
            )
            for action in actions:
                with self.assertRaises(LookupError):
                    action()
        with transaction(self.db) as conn:
            self.assertEqual({table: [tuple(row) for row in conn.execute('SELECT * FROM ' + table)] for table in tables}, before)
        self.reading._evaluate_answers.assert_not_called()
        self.assertEqual(self.jumble._assess.call_count, 1)

    def test_foreign_activity_routes_return_404_before_provider_calls(self):
        with self.as_user('personal-learning'):
            ids = self.create_all()
        client = self.app.test_client()
        state = select_test_profile(client, 'other')
        headers = {'X-CSRF-Token': state['csrf_token'], 'Accept': 'application/json'}
        for url in (f"/sentences/practice/{ids['translation']}", f"/sentences/saved/{ids['translation']}",
                    f"/writing/load/{ids['writing']}", f"/word_jumble/load/{ids['jumble']}",
                    f"/comprehension/load/{ids['reading']}"):
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 404)
        for url, data in (
            ('/sentence/assess', {'sentence_id': ids['translation'], 'user_response': 'Other', 'revision': 0}),
            ('/sentence/save', {'sentence_id': ids['translation'], 'user_response': 'Other', 'revision': 0}),
            (f"/sentence/audio/{ids['translation']}", {}),
            ('/writing/assess', {'exercise_id': ids['writing'], 'user_response': 'Other', 'revision': 0}),
            ('/writing/save', {'exercise_id': ids['writing'], 'user_response': 'Other', 'revision': 0}),
            (f"/word_jumble/mark/{ids['jumble']}", {'user_response': 'Other', 'revision': 0}),
            (f"/word_jumble/save/{ids['jumble']}", {'user_response': 'Other', 'revision': 0}),
            ('/comprehension/save', {'story_id': ids['reading'], 'story_text': base64.b64encode(STORY['text'].encode()).decode(),
                                    'questions_b64': base64.b64encode(json.dumps(STORY['questions']).encode()).decode(),
                                    'answers[]': ['Other'], 'topic': 'home', 'difficulty': 'beginner'}),
        ):
            with self.subTest(url=url):
                self.assertEqual(client.post(url, data=data, headers=headers).status_code, 404)
        self.reading._evaluate_answers.assert_not_called()
        self.writing_ai.assess_writing.assert_not_called()
        self.sentence_ai.assess_translation.assert_not_called()
        self.sentence_ai.generate_audio.assert_not_called()
        self.jumble._assess.assert_not_called()

    def test_household_adult_workspace_keeps_me_content_without_reward_attribution(self):
        with self.as_user('personal-learning'):
            ids = self.create_all()
        self.app.config['WORD_POST_HOUSEHOLD_ENABLED'] = True
        with self.as_user('other'):
            self.assertIsNotNone(self.translations.load(ids['translation']))
            self.grade_all(ids, 'Adult workspace answer.')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)

    def test_shared_legacy_lesson_only_shows_original_users_answers(self):
        prompts = json.dumps([{'id': 'old-prompt', 'question': 'Shared lesson question', 'answer': 'Reference answer'}])
        responses = json.dumps([{'prompt_id': 'old-prompt', 'response': 'Original private answer', 'feedback': 'Original private feedback'}])
        with transaction(self.db, write=True) as conn:
            conn.execute("INSERT INTO lessons(id,title,description,prompts,responses,created_at) VALUES ('legacy-lesson','Shared lesson','Shared material',?,?,?)",
                         (prompts, responses, '2000-01-01'))
        legacy = LessonService(self.db)
        client = self.app.test_client()
        for profile, visible in [('personal-learning', True), ('other', False), ('personal-learning', True)]:
            with self.as_user(profile):
                lesson = legacy.get_lesson('legacy-lesson')
                self.assertEqual(lesson['prompts'][0]['prompt'], 'Shared lesson question')
                self.assertEqual(lesson['prompts'][0]['reference_answer'], 'Reference answer')
                self.assertEqual(bool(lesson['responses']), visible)
            select_test_profile(client, profile)
            for headers in ({}, {'HX-Request': 'true', 'HX-Target': 'lesson-content'}):
                response = client.get('/lessons/load/legacy-lesson', headers=headers)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn('Shared lesson question', html)
                self.assertIn('Shared material', html)
                self.assertEqual('Original private answer' in html, visible)
                self.assertEqual('Original private feedback' in html, visible)
        # Historical tools and the household adult workspace retain the original
        # record, and displaying another profile never rewrites that source JSON.
        self.assertEqual(legacy.get_lesson('legacy-lesson')['responses'], json.loads(responses))
        self.app.config['WORD_POST_HOUSEHOLD_ENABLED'] = True
        with self.as_user('other'):
            self.assertEqual(legacy.get_lesson('legacy-lesson')['responses'], json.loads(responses))
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute("SELECT prompts,responses FROM lessons WHERE id='legacy-lesson'").fetchone()), (prompts, responses))


class ActivityOwnershipMigrationTests(unittest.TestCase):
    def test_upgrade25_preserves_old_fields_ids_and_rewards_and_assigns_me(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / 'migrations'
            old.mkdir()
            for file in MIGRATION_DIR.glob('*.sql'):
                if int(file.name[:3]) <= 24:
                    shutil.copy2(file, old / file.name)
            db = str(root / 'old.db')
            with patch('migrations.MIGRATION_DIR', old):
                upgrade_database(db, backup=False)
            with sqlite3.connect(db) as conn:
                conn.execute("INSERT INTO saved_stories(id,title,text,questions,answers,feedback,score,audio_url) VALUES (51,'Story','Текст','[\"Question\"]','[\"Old answer\"]','[\"Old feedback\"]',8,'/static/media/old.mp3')")
                conn.execute("INSERT INTO writing_exercises(id,topic,difficulty,task,required_words,min_words,user_response,score,feedback,created_at) VALUES (52,'home','beginner','Task','[]',30,'Writing',95,'Old feedback','2000-01-01')")
                conn.execute("INSERT INTO word_jumble_games(id,topic,difficulty,words,user_response,score,feedback,created_at) VALUES ('old-game','home','easy','[]','Jumble',95,'Old feedback','2000-01-01')")
                conn.execute("INSERT INTO sentences(id,sentence,english,score,topic,difficulty,audio_url) VALUES (53,'Кот','Cat',4,'home',1,'/static/media/old.mp3')")
                tables = ('saved_stories', 'writing_exercises', 'word_jumble_games', 'sentences')
                before = {table: conn.execute('SELECT * FROM ' + table).fetchall() for table in tables}
                coins = conn.execute('SELECT * FROM progression_entries').fetchall()
            shutil.copy2(MIGRATION_DIR / '025_activity_ownership.sql', old / '025_activity_ownership.sql')
            with patch('migrations.MIGRATION_DIR', old):
                self.assertEqual(upgrade_database(db, backup=False), (25, None))
            with sqlite3.connect(db) as conn:
                for table in tables:
                    self.assertEqual([row[:-1] for row in conn.execute('SELECT * FROM ' + table)], before[table])
                    self.assertEqual(conn.execute('SELECT DISTINCT owner_profile_id FROM ' + table).fetchall(), [('personal-learning',)])
                self.assertEqual(conn.execute('SELECT * FROM progression_entries').fetchall(), coins)
                self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone(), ('ok',))
            with patch('migrations.MIGRATION_DIR', old):
                self.assertEqual(upgrade_database(db, backup=False), (25, None))
