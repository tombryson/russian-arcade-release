"""Curriculum flows through generators without replacing lexical difficulty."""
import asyncio
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

from services.comprehension_service import ComprehensionService
from services.curriculum import LEVELS, topic_options
from services.writing_service import WritingService
from repositories.writing_repository import WritingRepository
from tests.support import isolated_app
from tests.test_story_titles import STORY
from tests.test_writing_cleanup import TASK, ADVICE
from tests.test_writing_generated_evidence import generated_task
from utils.story_display import present_story


class Selects(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.selects = {}
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'select':
            self.current = attrs.get('id')
            self.selects[self.current] = []
        elif tag == 'option' and self.current:
            self.selects[self.current].append(attrs)

    def handle_endtag(self, tag):
        if tag == 'select':
            self.current = None

    def selected(self, name):
        return [item['value'] for item in self.selects[name] if 'selected' in item]


class CurriculumProviderContractTests(unittest.TestCase):
    def test_reading_passes_c2_objectives_and_keeps_saved_vocabulary(self):
        service = ComprehensionService.__new__(ComprehensionService)
        service.get_vocab_for_topic = Mock(return_value=['суд', 'право'])
        service._request_story = Mock(return_value=deepcopy(STORY))
        service.generate_image = Mock(return_value='/static/media/test.png')
        asyncio.run(service.generate_story('law', 'C2'))
        payload = json.loads(service._request_story.call_args.args[0])
        self.assertEqual(payload['level'], 'C2')
        self.assertEqual(payload['curriculum']['topic_id'], 'law')
        self.assertEqual(payload['curriculum']['topic_band'], 'C1-C2')
        self.assertEqual(payload['curriculum']['target_level'], 'C2')
        self.assertTrue(payload['curriculum']['grammar_focus'])
        self.assertTrue(payload['curriculum']['activity_brief'])
        self.assertEqual(payload['use_when_relevant'], ['суд', 'право'])
        self.assertGreaterEqual(payload['target_words'][0], 300)
        asyncio.run(service.generate_story('family', 'intermediate'))
        self.assertEqual(json.loads(service._request_story.call_args.args[0])['level'], 'A2')

    def test_pasted_passage_is_preserved_with_advanced_question_brief(self):
        service = ComprehensionService.__new__(ComprehensionService)
        service._request_story = Mock(return_value={key: value for key, value in STORY.items() if key != 'text'})
        passage = '  Сложный текст.\n\nВторой абзац. '
        result = asyncio.run(service.prepare_story_from_text(passage, 'literature', 'C1'))
        payload = json.loads(service._request_story.call_args.args[0])
        self.assertEqual(result['text'], passage)
        self.assertEqual(payload['passage'], passage)
        self.assertEqual(payload['curriculum']['target_level'], 'C1')
        self.assertFalse(service._request_story.call_args.args[1])

    def test_reading_feedback_uses_the_saved_questions_as_the_assessment_scope(self):
        service = ComprehensionService.__new__(ComprehensionService)
        service.client = Mock()
        service.client.chat.completions.create.return_value = Mock(choices=[Mock(message=Mock(
            content=json.dumps({'feedback': ['You found the stated reason.'], 'scores': [9]})))])
        feedback, scores, total = service._evaluate_answers('Это важный закон.', ['Что важно?'], ['Закон.'], 'law', 'C2')
        instruction = service.client.chat.completions.create.call_args.kwargs['messages'][0]['content']
        self.assertIn('saved passage and its questions define what is being assessed', instruction)
        self.assertIn('Curriculum objectives are guidance, not extra requirements', instruction)
        self.assertIn('"target_level": "C2"', instruction)
        self.assertEqual((scores, total), ([9], 9))

    def test_writing_generation_and_feedback_use_same_topic_level(self):
        service = WritingService.__new__(WritingService)
        task = {**TASK, 'required_words': ['суд', 'закон', 'право', 'адвокат', 'доказательство']}
        service.structured = Mock(return_value=task)
        self.assertEqual(service.generate_writing_task('law', 'C2', 300), task)
        payload = service.structured.call_args.args[3]
        self.assertEqual((payload['level'], payload['target_words']), ('C2', 300))
        self.assertEqual(payload['curriculum']['topic_band'], 'C1-C2')
        self.assertTrue(payload['curriculum']['objectives'])
        self.assertEqual(payload['vocabulary_count'], 5)
        service.structured.return_value = ADVICE
        service.assess_writing(task['task'], task['required_words'], 300, 'Это важный закон.', 'C2', topic='law')
        assessment = service.structured.call_args.args[3]
        self.assertEqual(assessment['curriculum'], payload['curriculum'])
        self.assertEqual(assessment['russian_answer'], 'Это важный закон.')
        instruction = service.structured.call_args.args[2]
        self.assertIn('The saved task defines what is being assessed.', instruction)
        self.assertIn('not extra requirements', instruction)

    def test_writing_legacy_levels_remain_accepted_and_invalid_levels_fail_before_provider(self):
        service = WritingService.__new__(WritingService)
        service.structured = Mock(return_value=generated_task('B1'))
        service.generate_writing_task('family', 'advanced')
        self.assertEqual(service.structured.call_args.args[3]['level'], 'B1')
        service.structured.reset_mock()
        with self.assertRaises(ValueError):
            service.generate_writing_task('family', 'invented')
        service.structured.assert_not_called()

    def test_familiar_reading_words_use_canonical_lemmas_without_level_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'vocab.db'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE words(lemma TEXT, count INTEGER, topic TEXT, lemma_difficulty INTEGER)')
                conn.executemany('INSERT INTO words VALUES (?,?,?,?)', [
                    ('семья', 2, '["family"]', 5), ('мама', 1, '["family"]', 1),
                    ('суд', 3, '["law"]', 1), ('чужой', 4, 'broken JSON', 1)])
            service = ComprehensionService.__new__(ComprehensionService)
            service.db_path = str(db)
            self.assertEqual(service.get_vocab_for_topic('family', 'A1'), ['семья', 'мама'])
            self.assertEqual(service.get_vocab_for_topic('family', 'C2'), ['семья', 'мама'])
            self.assertEqual(service.get_vocab_for_topic('law', 'C2'), ['суд'])


class CurriculumReadingWritingRoutesTests(unittest.TestCase):
    def setUp(self):
        self.writing = Mock(spec=WritingService)
        self.writing.generate_writing_task.return_value = deepcopy(TASK)
        self.writing.assess_writing.return_value = deepcopy(ADVICE)
        self.app = isolated_app(self, {'WritingService': self.writing})
        self.client = self.app.test_client()
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']
        self.repo = WritingRepository(self.app.config['DB_PATH'])

    def test_empty_vocabulary_does_not_remove_curriculum_topics_or_levels(self):
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            conn.execute('DELETE FROM forms')
            conn.execute('DELETE FROM words')
        for url, topic_id, level_id in [('/comprehension', 'topic', 'difficulty'), ('/writing', 'writing-topic', 'writing-level')]:
            with self.subTest(url=url):
                response = self.client.get(url + '?topic=law&level=C2')
                self.assertEqual(response.status_code, 200)
                document = Selects(response.get_data(as_text=True))
                self.assertTrue({item['value'] for item in topic_options()}.issubset({item['value'] for item in document.selects[topic_id]}))
                self.assertEqual([item['value'] for item in document.selects[level_id]], list(LEVELS))
                self.assertEqual(document.selected(topic_id), ['law'])
                self.assertEqual(document.selected(level_id), ['C2'])
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM words').fetchone()[0], 0)

    def test_topic_primary_band_defaults_without_overriding_explicit_revision_level(self):
        for url, level_id in [('/comprehension', 'difficulty'), ('/writing', 'writing-level')]:
            for query, expected in [('?topic=work', 'B2'), ('?topic=work&level=A1', 'A1'), ('?topic=unknown&level=invalid', 'A1')]:
                document = Selects(self.client.get(url + query).get_data(as_text=True))
                self.assertEqual(document.selected(level_id), [expected])

    def test_c2_writing_persists_then_checks_saved_level_and_topic(self):
        result = self.client.post('/writing/generate', data={'topic': 'law', 'difficulty': 'C2', 'target_words': 300}, headers={'Accept': 'application/json'})
        self.assertEqual(result.status_code, 200)
        saved = self.repo.list_saved()[0]
        self.assertEqual((saved['topic'], saved['difficulty'], saved['min_words']), ('law', 'C2', 300))
        self.assertIn('C2', self.client.get(result.json['url']).get_data(as_text=True))
        checked = self.client.post('/writing/assess', data={'exercise_id': saved['id'], 'revision': 0, 'user_response': 'Это важный закон.', 'difficulty': 'A1', 'topic': 'family'}, headers={'Accept': 'application/json'})
        self.assertEqual(checked.status_code, 200)
        self.assertEqual(self.writing.assess_writing.call_args.kwargs['difficulty'], 'C2')
        self.assertEqual(self.writing.assess_writing.call_args.kwargs['topic'], 'law')

    def test_legacy_writing_record_remains_unchanged(self):
        item_id = self.repo.create(TASK, 'family', 'advanced', 30)
        self.assertEqual(self.client.get(f'/writing/load/{item_id}').status_code, 200)
        self.assertEqual(self.repo.load(item_id)['difficulty'], 'advanced')
        story = {'title': 'История', 'topic': 'family', 'difficulty': 'C2'}
        shown = present_story(story, 'en')
        self.assertTrue(shown['level_label'].startswith('C2'))
        self.assertEqual(story['difficulty'], 'C2')
