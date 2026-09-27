"""A complete shared syllabus without changing the lexical database."""
from copy import deepcopy
import sqlite3
import unittest
from unittest.mock import patch

from services.curriculum import (
    ACTIVITIES, BANDS, LEVELS, band_summaries, curriculum, generation_context,
    get_topic, level_options, normalize_level, topic_options, validate_curriculum,
)
from services.vocabulary_topics import TOPICS
from tests.support import isolated_app


class CurriculumTests(unittest.TestCase):
    def test_complete_course_and_substantive_band_vocabulary(self):
        data = curriculum()
        self.assertEqual([topic['id'] for topic in data['topics']], list(TOPICS[:-1]))
        self.assertEqual([band['id'] for band in band_summaries()], list(BANDS))
        for band in band_summaries():
            self.assertEqual(len(band['topics']), 10)
            self.assertGreaterEqual(band['lemma_count'], band['lemma_target']['min'])
            for topic in band['topics']:
                self.assertGreaterEqual(len(topic['lemmas']), 12)
                self.assertGreaterEqual(len(topic['objectives']), 2)
                self.assertGreaterEqual(len(topic['grammar_focus']), 2)
                self.assertEqual(set(topic['practice']), set(ACTIVITIES))

    def test_catalogue_copies_and_independent_numeric_difficulty(self):
        topic = get_topic('greetings')
        topic['lemmas'].clear()
        self.assertTrue(get_topic('greetings')['lemmas'])
        data = curriculum()
        data['topics'].clear()
        self.assertEqual(len(curriculum()['topics']), 50)
        self.assertIsNone(get_topic('unlisted'))
        self.assertNotIn('lemma_difficulty', generation_context('food', 'B2', 'reading'))
        self.assertNotIn('form_difficulty', generation_context('food', 'B2', 'reading'))

    def test_no_incomplete_curriculum_can_be_served(self):
        data = curriculum()
        for field in ('topics', 'bands', 'levels'):
            broken = deepcopy(data)
            broken[field] = [] if field != 'levels' else {}
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_curriculum(broken)
        broken = deepcopy(data)
        broken['topics'][0]['lemmas'].append('до свидания')
        with self.assertRaises(ValueError):
            validate_curriculum(broken)

    def test_generation_uses_same_topic_objectives_and_separate_task_levels(self):
        for topic in curriculum()['topics']:
            level = 'C1' if topic['band'] == 'C1-C2' else topic['band']
            for activity in ACTIVITIES:
                with self.subTest(topic=topic['id'], activity=activity):
                    context = generation_context(topic['id'], level, activity)
                    self.assertEqual(context['topic_band'], topic['band'])
                    self.assertEqual(context['target_level'], level)
                    self.assertEqual(context['activity_brief'], topic['practice'][activity])
                    self.assertEqual(context['target_vocabulary'], topic['lemmas'])
        revision = generation_context('food', 'C2', 'writing')
        self.assertEqual((revision['topic_band'], revision['target_level']), ('A1', 'C2'))
        self.assertNotEqual(generation_context('law', 'C1', 'writing')['level_guidance'],
                            generation_context('law', 'C2', 'writing')['level_guidance'])

    def test_historical_level_aliases_keep_activity_specific_meanings(self):
        self.assertEqual(normalize_level('intermediate', 'reading'), 'A2')
        self.assertEqual(normalize_level('intermediate', 'word_jumble'), 'B1')
        self.assertEqual(normalize_level(6, 'translation'), 'C2')
        for value in (True, None, 'C3', 8, '<script>'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_level(value)

    def test_localized_selectors_and_cross_topic_grammar(self):
        for language in ('en', 'ru'):
            options = topic_options(language)
            self.assertEqual([item['value'] for item in options], list(TOPICS))
            self.assertEqual([item['value'] for item in level_options(language)], list(LEVELS))
            self.assertEqual(options[-1]['band'], '')
            self.assertEqual(options[-1]['level'], '')
        self.assertNotEqual(topic_options()[0]['label'], topic_options('ru')[0]['label'])


class CurriculumPageTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self, demo=False, signed_in=False)
        self.client = self.app.test_client()

    def test_full_public_catalogue_links_to_existing_generators_without_writing_words(self):
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            before = conn.execute('SELECT COUNT(*) FROM words').fetchone()[0]
        with patch('openai.OpenAI', side_effect=AssertionError('Catalogue initialized provider')):
            response = self.client.get('/curriculum')
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertEqual(html.count('class="curriculum-topic"'), 50)
        for topic in curriculum()['topics']:
            self.assertIn(f'id="topic-{topic["id"]}"', html)
            self.assertIn(f'href="/curriculum/topics/{topic["id"]}"', html)
            page = self.client.get(f'/curriculum/topics/{topic["id"]}')
            self.assertEqual(page.status_code, 200)
            self.assertIn(f'/comprehension?topic={topic["id"]}&amp;level=', page.text)
            self.assertNotIn('<details class="curriculum-', page.text)
        advanced = self.client.get('/curriculum/topics/law').text
        for level in ('C1', 'C2'):
            self.assertIn(f'/writing?topic=law&amp;level={level}', advanced)
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM words').fetchone()[0], before)

    def test_shell_navigation_and_russian_titles(self):
        with self.client.session_transaction() as session:
            session['ui_lang'] = 'ru'
        response = self.client.get('/curriculum', headers={'HX-Target': 'mainContent'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<!DOCTYPE', response.text)
        self.assertIn(get_topic('greetings')['title_ru'], response.text)

    def test_speaking_links_open_implemented_topics_at_the_curriculum_level(self):
        expected = {
            'greetings': ('meet-someone', 'A1'),
            'food': ('cafe', 'A1'),
            'clothing': ('shop', 'A1'),
            'places': ('directions', 'A1'),
            'shopping': ('shop', 'A2'),
            'travel': ('station', 'A2'),
            'restaurant': ('cafe', 'A2'),
            'hobbies': ('meet-someone', 'A2'),
        }
        for topic in curriculum()['topics']:
            section = self.client.get(f'/curriculum/topics/{topic["id"]}').text
            with self.subTest(topic=topic['id']):
                if topic['id'] in expected:
                    scenario, level = expected[topic['id']]
                    self.assertIn(f'/#speaking/scenario/{scenario}?level={level}', section)
                else:
                    self.assertNotIn('/#speaking/scenario/', section)

    def test_unknown_topic_does_not_fall_back_to_another_topic(self):
        self.assertEqual(self.client.get('/curriculum/topics/unlisted').status_code, 404)

    def test_reading_pages_are_available_in_public_demo(self):
        self.app.config['PUBLIC_DEMO'] = True
        for path in ('/curriculum', '/curriculum/topics/places', '/curriculum/levels/A1'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)


if __name__ == '__main__':
    unittest.main()
