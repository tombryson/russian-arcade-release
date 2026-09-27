from tests.support import latest_schema_version
import asyncio
import base64
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock

import httpx
import openai

from tests.support import isolated_app
from services.comprehension_service import ComprehensionService
from repositories import StoryRepository
from story_cli import retitle_stories, story_text_hash
from utils.story_display import present_story
from migrations import upgrade_database


def encoded(value):
    return base64.b64encode(value.encode()).decode()


STORY = {'title': 'Новая игрушка для Макса', 'title_en': 'A New Toy for Max', 'text': 'Анна и Макс гуляют в парке. Макс нашёл мяч.',
         'questions': ['Где гуляют Анна и Макс?', 'Что нашёл Макс?', 'Почему Анна рада?',
                       'Как они могут играть с мячом?', 'Во что ты любишь играть?']}


def with_reading_focus(story, passage=None):
    return {**story, 'topic_id': 'family', 'reading_focus': [
        {'question_index': index, 'requirement_id': 'a1.reading.narrative-meaning',
         'passage_excerpt': passage or story['text'], 'expectation': 'Identify the requested detail in the account.'}
        for index in range(4)]}


class StoryGenerationContractTests(unittest.TestCase):
    def setUp(self):
        self.service = ComprehensionService.__new__(ComprehensionService)
        self.service.story_model = 'gpt-6-astra'
        self.service.story_reasoning_effort = 'low'
        self.service.get_vocab_for_topic = Mock(return_value=['мяч'])
        self.service.generate_image = Mock(return_value='/static/media/test.png')
        self.requests = []

    def client_for(self, payload, status='completed', refusal=False):
        def respond(request):
            self.requests.append(json.loads(request.content))
            self.assertEqual(request.url.path, '/v1/responses')
            content = [{'type': 'refusal', 'refusal': 'Cannot prepare this passage.'}] if refusal else [
                {'type': 'output_text', 'text': json.dumps(payload, ensure_ascii=False), 'annotations': []}]
            return httpx.Response(200, json={'id': 'resp_test', 'object': 'response', 'created_at': 0,
                'status': status, 'model': 'gpt-6-astra',
                'output': [{'id': 'msg_test', 'type': 'message', 'role': 'assistant', 'status': 'completed', 'content': content}]})
        client = openai.OpenAI(api_key='test-only', http_client=httpx.Client(transport=httpx.MockTransport(respond)))
        self.addCleanup(client.close)
        self.service.client = client

    def test_real_sdk_sends_astra_low_and_required_title_schema(self):
        self.client_for(with_reading_focus(STORY))
        result = asyncio.run(self.service.generate_story('family', 'beginner'))
        self.assertEqual(result['title'], STORY['title'])
        self.assertEqual(result['title_en'], STORY['title_en'])
        self.assertEqual(result['text'], STORY['text'])
        request = self.requests[0]
        self.assertEqual(request['model'], 'gpt-6-astra')
        self.assertEqual(request['reasoning'], {'effort': 'low'})
        self.assertEqual(request['text']['format']['type'], 'json_schema')
        self.assertTrue(request['text']['format']['strict'])
        self.assertEqual(set(request['text']['format']['schema']['required']), {'title', 'title_en', 'text', 'questions', 'topic_id', 'reading_focus'})
        self.assertFalse(request['store'])
        self.assertNotIn('max_tokens', request)
        self.assertNotIn('temperature', request)
        self.service.generate_image.assert_called_once_with(STORY['text'])

    def test_missing_title_is_rejected_instead_of_becoming_an_excerpt(self):
        self.client_for({key: value for key, value in STORY.items() if key != 'title'})
        with self.assertRaisesRegex(ValueError, 'invalid title'):
            asyncio.run(self.service.generate_story('family', 'beginner'))
        self.assertEqual(len(self.requests), 2)
        self.service.generate_image.assert_not_called()
        self.assertEqual(present_story({'text': STORY['text']})['display_title'], '')

    def test_pasted_passage_keeps_exact_text_and_receives_a_title(self):
        passage = 'Анна говорит: «Привет!»\n\n  Макс рядом.\n'
        self.client_for(with_reading_focus({'title': STORY['title'], 'title_en': STORY['title_en'], 'questions': STORY['questions']}, passage))
        result = asyncio.run(self.service.prepare_story_from_text(passage, 'family', 'beginner'))
        self.assertEqual(result['text'], passage)
        self.assertEqual(result['title'], STORY['title'])
        self.assertEqual(set(self.requests[0]['text']['format']['schema']['required']), {'title', 'title_en', 'questions', 'topic_id', 'reading_focus'})
        self.assertEqual(json.loads(self.requests[0]['input'][1]['content'])['passage'], passage)
        self.service.generate_image.assert_not_called()

    def test_missing_english_title_is_rejected_before_creating_media(self):
        self.client_for({key: value for key, value in STORY.items() if key != 'title_en'})
        with self.assertRaisesRegex(ValueError, 'invalid title'):
            asyncio.run(self.service.generate_story('family', 'beginner'))
        self.service.generate_image.assert_not_called()

    def test_refused_or_incomplete_responses_do_not_create_content(self):
        for status, refusal in [('completed', True), ('incomplete', False)]:
            with self.subTest(status=status):
                self.client_for(STORY, status, refusal)
                with self.assertRaises(ValueError):
                    asyncio.run(self.service.generate_story('family', 'beginner'))
                self.service.generate_image.assert_not_called()


class StoryTitlePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.service = ComprehensionService.__new__(ComprehensionService)
        self.service.get_topics = Mock(return_value=['family'])
        self.service.generate_image = Mock(return_value='')
        self.service.generate_audio = Mock(return_value='')
        self.service.evaluate_answers = Mock(return_value=(['Good'] * 5, [8] * 5, 8.0, False))
        self.service.generate_additional_questions = Mock(return_value=['Какого цвета мяч?'])
        self.drive = Mock()
        self.drive.download_vocab_list.return_value = ''
        self.app = isolated_app(self, {'ComprehensionService': self.service, 'GoogleDriveService': self.drive})
        self.service.db_path = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        state = self.client.get('/api/v1/user-session').json
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = state['csrf_token']
        self.repository = StoryRepository(self.service.db_path)
        self.payload = {'story_title': STORY['title'], 'story_title_en': STORY['title_en'], 'story_text': encoded(STORY['text']),
                        'questions_b64': encoded(json.dumps(STORY['questions'])),
                        'answers[]': ['Ответ.'] * 5, 'topic': 'family', 'difficulty': 'beginner'}

    def save(self, **overrides):
        return self.service.save_story(title=STORY['title'], title_en=STORY['title_en'], text=STORY['text'], topic='family', difficulty='beginner',
            audio_url='', image_url='', questions=STORY['questions'], answers=[], feedback=[], score=0, **overrides)

    def test_new_story_generation_check_and_reload_keep_the_generated_title(self):
        async def generate(topic, difficulty):
            return {**STORY, 'image_url': ''}
        self.service.generate_story = generate
        generated = self.client.post('/comprehension', data={'topic': 'family'}, headers={'HX-Request': 'true'})
        self.assertIn(STORY['title'], generated.get_data(as_text=True))
        self.assertIn('name="story_title"', generated.get_data(as_text=True))
        # Checking a new unsaved activity must create its record with the same title.
        checked = self.client.post('/comprehension/answer', data=self.payload)
        self.assertEqual(checked.status_code, 200)
        story_id = self.repository.find_existing(STORY['text'], 'family', 'beginner')
        self.assertIsNotNone(story_id)
        self.assertEqual(self.repository.load(story_id)['title'], STORY['title'])
        self.assertEqual(self.repository.load(story_id)['title_en'], STORY['title_en'])
        loaded = self.client.get(f'/comprehension/load/{story_id}').get_data(as_text=True)
        self.assertIn(f'lang="en">{STORY["title_en"]}</h2>', loaded)

    def test_interface_language_selects_title_in_library_and_reader(self):
        story_id = self.save()
        for language, title in [('en', STORY['title_en']), ('ru', STORY['title']), ('en', STORY['title_en'])]:
            self.client.post('/ui-language', data={'lang': language, 'next': '/comprehension'})
            library = self.client.get('/comprehension').get_data(as_text=True)
            self.assertIn(f'class="reading-story-title" lang="{language}">{title}</span>', library)
            for headers in [{}, {'HX-Request': 'true', 'HX-Target': 'mainContent'}]:
                reader = self.client.get(f'/comprehension/load/{story_id}', headers=headers).get_data(as_text=True)
                self.assertIn(f'lang="{language}">{title}</h2>', reader)
                self.assertIn('Анна', reader)
        saved = self.repository.load(story_id)
        self.assertEqual(saved['text'], STORY['text'])
        self.assertEqual(saved['title'], STORY['title'])
        self.assertEqual(saved['title_en'], STORY['title_en'])

    def test_save_and_more_questions_preserve_title_after_a_migration(self):
        story_id = self.save()
        new_title = 'Мяч для Макса'
        with sqlite3.connect(self.service.db_path) as conn:
            conn.execute('UPDATE saved_stories SET title=? WHERE id=?', (new_title, story_id))
            conn.execute("UPDATE story_title_translations SET title='A Ball for Max' WHERE story_id=? AND language='en'", (story_id,))
        # Simulate an older open form still carrying the old title.
        payload = {**self.payload, 'story_id': str(story_id)}
        more = self.client.post('/comprehension/generate_more_questions', data=payload)
        self.assertIn(f'name="story_title" value="{new_title}"', more.get_data(as_text=True))
        self.assertIn('name="story_title_en" value="A Ball for Max"', more.get_data(as_text=True))
        saved = self.client.post('/comprehension/save', data=payload)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.repository.load(story_id)['title'], new_title)
        self.assertEqual(self.repository.load(story_id)['title_en'], 'A Ball for Max')
        self.assertEqual(self.repository.load(story_id)['answers'], ['Ответ.'] * 5)

    def test_resaving_a_specific_copy_does_not_overwrite_another_copy(self):
        first_id = self.save()
        with sqlite3.connect(self.service.db_path) as conn:
            cursor = conn.execute('''INSERT INTO saved_stories (title,text,topic,difficulty,questions,answers)
                SELECT 'Другой заголовок',text,topic,difficulty,questions,answers FROM saved_stories WHERE id=?''', (first_id,))
            second_id = cursor.lastrowid
        result = self.client.post('/comprehension/save', data={**self.payload, 'story_id': str(second_id)})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.repository.load(first_id)['answers'], [])
        self.assertEqual(self.repository.load(second_id)['answers'], ['Ответ.'] * 5)
        self.assertEqual(self.repository.load(second_id)['title'], 'Другой заголовок')

    def test_wrong_story_identity_fails_before_assessment(self):
        story_id = self.save()
        result = self.client.post('/comprehension/save', data={**self.payload, 'story_id': str(story_id),
                                                             'story_text': encoded('Другой текст')})
        self.assertGreaterEqual(result.status_code, 400)
        self.service.evaluate_answers.assert_not_called()
        self.assertEqual(self.repository.load(story_id)['answers'], [])

    def test_title_plan_changes_only_titles_and_is_repeatable(self):
        story_id = self.save()
        row_before = self.repository.load(story_id)
        plan = {'version': 1, 'stories': [{'id': story_id, 'expected_title': STORY['title'],
                'text_sha256': story_text_hash(STORY['text']), 'title': 'Мяч для Макса'}]}
        changes, backup = retitle_stories(self.service.db_path, plan)
        self.assertEqual(len(changes), 1)
        self.assertIsNone(backup)
        self.assertEqual(self.repository.load(story_id), row_before)
        changes, backup = retitle_stories(self.service.db_path, plan, apply=True)
        row_after = self.repository.load(story_id)
        self.assertEqual(row_after.pop('title'), 'Мяч для Макса')
        row_before.pop('title')
        self.assertEqual(row_after, row_before)
        self.assertEqual(StoryRepository(backup).load(story_id)['title'], STORY['title'])
        backup_conn = sqlite3.connect(backup)
        try:
            self.assertEqual(backup_conn.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
        finally:
            backup_conn.close()
        self.assertEqual(retitle_stories(self.service.db_path, plan, apply=True), ([], None))

    def test_title_plan_refuses_wrong_content_without_any_partial_updates(self):
        story_id = self.save()
        plan = {'version': 1, 'stories': [{'id': story_id, 'expected_title': STORY['title'],
                'text_sha256': story_text_hash(STORY['text']), 'title': 'Мяч для Макса'},
                {'id': 9999, 'expected_title': 'Missing', 'text_sha256': 'wrong', 'title': 'Нет истории'}]}
        with self.assertRaises(ValueError):
            retitle_stories(self.service.db_path, plan, apply=True)
        self.assertEqual(self.repository.load(story_id)['title'], STORY['title'])
        self.assertFalse(list(Path(self.service.db_path).parent.glob('*.bak')))
        wrong_text = deepcopy(plan)
        wrong_text['stories'] = wrong_text['stories'][:1]
        wrong_text['stories'][0]['text_sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'different text'):
            retitle_stories(self.service.db_path, wrong_text, apply=True)

    def test_english_backfill_preserves_legacy_rows_and_supports_later_upgrade(self):
        story_id = self.save()
        # A pre-household installation can add translations without upgrading
        # unrelated tables. The regular migration can still run afterwards.
        with sqlite3.connect(self.service.db_path) as conn:
            conn.execute('DROP TABLE story_title_translations')
            conn.execute('DELETE FROM schema_migrations WHERE version=5')
            before = conn.execute('SELECT * FROM saved_stories').fetchall()
        plan = {'version': 1, 'stories': [{'id': story_id, 'expected_title': '',
            'text_sha256': story_text_hash(STORY['text']), 'title': STORY['title_en']}]}
        changes, backup = retitle_stories(self.service.db_path, plan, language='en')
        self.assertEqual(len(changes), 1)
        self.assertIsNone(backup)
        self.assertEqual(self.repository.load(story_id)['title_en'], '')
        changes, backup = retitle_stories(self.service.db_path, plan, apply=True, language='en')
        self.assertEqual(self.repository.load(story_id)['title_en'], STORY['title_en'])
        self.assertEqual(StoryRepository(backup).load(story_id)['title_en'], '')
        with sqlite3.connect(self.service.db_path) as conn:
            self.assertEqual(conn.execute('SELECT * FROM saved_stories').fetchall(), before)
        self.assertEqual(retitle_stories(self.service.db_path, plan, apply=True, language='en'), ([], None))
        self.assertEqual(upgrade_database(self.service.db_path, backup=False), (latest_schema_version(), None))
        self.assertEqual(self.repository.load(story_id)['title_en'], STORY['title_en'])
