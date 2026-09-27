"""Regressions for saved activities and the reading workspace. No provider calls."""
import base64
from collections import Counter
from html.parser import HTMLParser
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from tests.support import isolated_app
from services.writing_service import WritingService
from repositories.writing_repository import WritingRepository
from utils.story_display import present_story
from utils.story_processing import process_story_words


def encoded(value):
    return base64.b64encode(value.encode()).decode()


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.answers = {}
        self.current_answer = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == 'textarea':
            self.current_answer = attrs['id']
            self.answers[self.current_answer] = ''

    def handle_endtag(self, tag):
        if tag == 'textarea':
            self.current_answer = None

    def handle_data(self, data):
        if self.current_answer:
            self.answers[self.current_answer] += data

    def element(self, id):
        return next(attrs for _, attrs in self.elements if attrs.get('id') == id)


class ActivityCleanupTests(unittest.TestCase):
    def setUp(self):
        self.writing = WritingService.__new__(WritingService)
        self.game = dict(id=7, topic='family', difficulty='easy', words=['мама', 'дом'],
                         user_response='Мама дома.', score=3, feedback='Try using both words.')
        self.jumble = SimpleNamespace(get_game=lambda id: self.game, get_saved_games=lambda: [self.game],
                                      get_topics=lambda: ['family'])
        self.lesson = dict(id=9, title='Family lesson', description='', images=[], pdf_path='',
                           prompts=[dict(id=21, prompt='Кто дома?')], responses=[], created_at='2026-09-09')
        self.lessons = SimpleNamespace(get_lesson=lambda id: self.lesson, get_saved_lessons=lambda: [self.lesson])
        self.comprehension = SimpleNamespace(get_topics=lambda: ['family'],
                                            generate_additional_questions=Mock(return_value=['Куда идёт Анна?']))
        self.drive = SimpleNamespace(download_vocab_list=lambda: '')
        self.app = isolated_app(self, {'WritingService': self.writing, 'WordJumbleService': self.jumble,
                                     'LessonService': self.lessons, 'ComprehensionService': self.comprehension,
                                     'GoogleDriveService': self.drive})
        self.writing.db_path = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        state = self.client.get('/api/v1/user-session').json
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = state['csrf_token']
        self.title = 'Девочка по имени Анна живет ... (any, beginner)'
        self.story_text = 'Анна живёт дома.\n\nОна говорит: «Привет, мир!»'
        self.answer = 'Она сказала: «Привет!» </textarea><script>bad()</script>'
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            cursor = conn.execute('''INSERT INTO saved_stories
                (title, text, topic, difficulty, questions, answers, audio_url, image_url)
                VALUES (?, ?, 'any', 'beginner', ?, ?, '', '')''',
                (self.title, self.story_text, json.dumps(['Кто живёт дома?', 'Что она говорит?']), json.dumps([self.answer])))
            self.story_id = cursor.lastrowid

    def assert_unique_ids(self, document):
        ids = Counter(attrs['id'] for _, attrs in document.elements if 'id' in attrs)
        self.assertEqual({id: count for id, count in ids.items() if count > 1}, {})

    def test_library_formats_historical_title_without_changing_storage(self):
        html = self.client.get('/comprehension').get_data(as_text=True)
        document = Document(html)
        self.assertIn('open', document.element('saved-stories'))
        self.assertNotIn('open', document.element('new-story'))
        self.assertIn('Девочка по имени Анна живет ...', html)
        self.assertNotIn('(any, beginner)', html)
        self.assertIn('Questions: 2', html)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT title FROM saved_stories WHERE id=?', (self.story_id,)).fetchone()[0], self.title)

    def test_saved_story_full_shell_and_fragment_render_same_answers_once(self):
        for headers in [{}, {'HX-Request': 'true', 'HX-Target': 'mainContent'},
                        {'HX-Request': 'true', 'HX-Target': 'comprehension-content'}]:
            with self.subTest(headers=headers):
                response = self.client.get(f'/comprehension/load/{self.story_id}', headers=headers)
                html = response.get_data(as_text=True)
                document = Document(html)
                self.assertEqual(response.status_code, 200)
                self.assert_unique_ids(document)
                self.assertEqual(document.answers['story-answer-0'], self.answer)
                self.assertEqual(document.answers['story-answer-1'], '')
                self.assertNotIn('<script>bad()', html)
                self.assertIn(self.story_text, html)
                self.assertNotIn('hx-preserve', html)
                if headers.get('HX-Target') != 'comprehension-content':
                    self.assertNotIn('open', document.element('saved-stories'))
                    self.assertEqual(html.count('id="comprehension-content"'), 1)
                self.assertEqual('<!DOCTYPE html>' in html, not headers)

    def test_more_questions_keep_answers_and_return_only_question_region(self):
        response = self.client.post('/comprehension/generate_more_questions', data={
            'story_text': encoded(self.story_text), 'questions_b64': encoded(json.dumps(['Кто дома?', 'Что дальше?'])),
            'answers[]': [self.answer, 'Ещё один ответ.'], 'topic': 'any', 'difficulty': 'beginner',
        }, headers={'HX-Request': 'true', 'HX-Target': 'questions-section'})
        html = response.get_data(as_text=True)
        document = Document(html)
        self.assertEqual(response.status_code, 200)
        self.assert_unique_ids(document)
        self.assertEqual(list(document.answers.values()), [self.answer, 'Ещё один ответ.', ''])
        self.assertIn('hx-preserve', document.element('story-answer-0'))
        self.assertNotIn('id="story-container"', html)
        self.assertNotIn('id="questions-section"', html)
        self.assertNotIn('id="comprehension-content"', html)
        self.assertEqual(self.comprehension.generate_additional_questions.call_count, 1)

    def test_reading_tokens_preserve_spaces_paragraphs_and_punctuation(self):
        with self.app.app_context():
            tokens = process_story_words(self.story_text, self.app.config['DB_PATH'], self.drive)
        self.assertEqual(''.join(token['word'] for token in tokens), self.story_text)
        self.assertTrue(any(token['lemma'] for token in tokens))

    def test_more_questions_failure_returns_retry_message_without_replacing_questions(self):
        self.comprehension.generate_additional_questions.side_effect = RuntimeError('private provider diagnostics')
        response = self.client.post('/comprehension/generate_more_questions', data={
            'story_text': encoded(self.story_text), 'questions_b64': encoded(json.dumps(['Кто дома?'])),
            'answers[]': [self.answer],
        })
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn('Your answers are still here', html)
        self.assertNotIn('private provider diagnostics', html)
        self.assertNotIn('id="question-form"', html)

    def test_writing_save_then_resume_restores_complete_escaped_response(self):
        response = self.answer + '\n' + ('Моя семья живёт здесь. ' * 60)
        repository = WritingRepository(self.app.config['DB_PATH'])
        exercise_id = repository.create(dict(title='Моя семья', title_en='My family', task='Расскажите о семье.',
            task_en='Write about your family.', required_words=['мама','семья','дом']), 'family', 'beginner', 30)
        result = self.client.post('/writing/save', data={
            'exercise_id': exercise_id, 'revision': 0, 'user_response': response,
        })
        self.assertEqual(result.status_code, 303)
        for headers in [{}, {'HX-Request': 'true', 'HX-Target': 'mainContent'},
                        {'HX-Request': 'true', 'HX-Target': 'writing-content'}]:
            with self.subTest(headers=headers):
                html = self.client.get(f'/writing/load/{exercise_id}', headers=headers).get_data(as_text=True)
                document = Document(html)
                self.assert_unique_ids(document)
                self.assertEqual(document.answers['user-response'], response)
                self.assertNotIn('<script>bad()', html)
                self.assertEqual('<!DOCTYPE html>' in html, not headers)

    def test_jumble_full_page_and_fragment_use_four_point_scale_and_saved_answer(self):
        for headers in [{}, {'HX-Request': 'true', 'HX-Target': 'jumble-content'}]:
            html = self.client.get('/word_jumble/load/7', headers=headers).get_data(as_text=True)
            document = Document(html)
            self.assert_unique_ids(document)
            self.assertIn('3/4', html)
            self.assertNotIn('3/100', html)
            self.assertEqual(document.answers['response-7'], self.game['user_response'])
            self.assertEqual('<!DOCTYPE html>' in html, not headers)

    def test_legacy_lesson_history_is_readable_in_full_page_and_fragment(self):
        for headers in [{}, {'HX-Request': 'true', 'HX-Target': 'lesson-content'}]:
            html = self.client.get('/lessons/load/9', headers=headers).get_data(as_text=True)
            document = Document(html)
            self.assert_unique_ids(document)
            self.assertIn('Кто дома?', html)
            self.assertIn('Earlier exercises', html)
            self.assertNotIn('answer-', html)
            self.assertEqual('<!DOCTYPE html>' in html, not headers)

    def test_phrasebook_bookmarks_reach_saved_sentences(self):
        response = self.client.get('/phrasebook')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/sentences/saved')
        self.assertEqual(self.client.get(response.location).status_code, 200)


class ActivityContentTests(unittest.TestCase):
    def test_display_formatter_only_removes_matching_legacy_suffixes(self):
        for title, expected in [('История (any, beginner) (any, beginner)', 'История'),
                                ('История (летняя)', 'История (летняя)'),
                                ('История (family, beginner)', 'История (family, beginner)')]:
            self.assertEqual(present_story(dict(title=title, topic='any', difficulty='beginner'))['display_title'], expected)
        self.assertIsNone(present_story(dict(title='Story', questions='broken-json'))['question_count'])

    def test_writing_assessment_receives_entire_task_and_response(self):
        service = WritingService.__new__(WritingService)
        service.client = Mock()
        service.client.responses.create.return_value = SimpleNamespace(status='completed',
            output_text=json.dumps(dict(score=8,strength='Clear writing.',next_step='Add detail.',example='Моя семья дома.')))
        task = 'Расскажите о семье. ' * 50 + 'TASK END'
        response = 'Моя семья живёт здесь. ' * 100 + '\n«Она сказала: привет!» RESPONSE END'
        result = service.assess_writing(task, ['семья'], 150, response)
        payload = json.loads(service.client.responses.create.call_args.kwargs['input'][1]['content'])
        self.assertEqual(payload['task'], task)
        self.assertEqual(payload['russian_answer'], response)
        self.assertEqual(result['score'], 8)
