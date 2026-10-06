"""The beginner sequence teaches each tested form and retains authored audio."""
import json
from pathlib import Path
import re
import unittest

import pymorphy3

from services.first_steps import DEFAULT_VERSION, HELLO, LESSON_IDS, chapter_content


def russian_words(text):
    return set(re.findall(r'[а-яё]+', text.casefold().replace('\u0301', '')))


class FirstStepsV2ContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = chapter_content()
        cls.morph = pymorphy3.MorphAnalyzer()

    def test_five_step_sequence_reuses_existing_hello_and_has_complete_bounded_contracts(self):
        old = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'first_steps.json').read_text())
        self.assertEqual(self.content['version'], DEFAULT_VERSION)
        self.assertEqual(self.content['first_lesson'], old['first_lesson'])
        self.assertEqual(self.content['first_lesson']['vocabulary'], HELLO['vocabulary'])
        self.assertEqual(tuple(item['id'] for item in self.content['lessons']), LESSON_IDS[1:])
        seen = set()
        for position, lesson in enumerate(self.content['lessons'], 2):
            self.assertEqual(lesson['position'], position)
            self.assertTrue(all(lesson.get(key) for key in ('title', 'description', 'resolution')))
            self.assertGreaterEqual(len(lesson['teaching']), 3)
            self.assertLessEqual(len(lesson['teaching']), 4)
            for item in [*lesson['teaching'], *lesson['questions']]:
                self.assertNotIn(item['id'], seen)
                seen.add(item['id'])
            for teaching in lesson['teaching']:
                self.assertTrue(all(isinstance(teaching.get(key), str) and teaching[key].strip() for key in ('id', 'title', 'word', 'meaning', 'explanation', 'audio_text', 'audio_url')))
                self.assertEqual(teaching['word_display'].replace('\u0301', ''), teaching['word'])
                if 'name_slot' in teaching:
                    self.assertIs(teaching['name_slot'], True)
                    self.assertEqual(lesson['id'], 'introductions')
                for example in teaching.get('examples', []):
                    self.assertTrue(example['ru'] and example['en'])
            for question in lesson['questions']:
                self.assertIn(question.get('choices_language'), ('en', 'ru'))
                self.assertTrue(question['prompt'] and question['hint'] and question['feedback'])
                self.assertTrue(2 <= len(question['choices']) <= 3)
                ids = [choice['id'] for choice in question['choices']]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertIn(question['answer'], ids)
                if question['choices_language'] == 'en':
                    self.assertEqual(lesson['id'], 'gender')
                    self.assertEqual({choice['text'] for choice in question['choices']}, {'Masculine', 'Feminine', 'Neuter'})

    def test_russian_choices_passages_and_recordings_use_language_already_taught(self):
        taught = set().union(*(russian_words(word['sentence']) for word in HELLO['vocabulary']))
        for lesson in self.content['lessons']:
            for card in lesson['teaching']:
                taught |= russian_words(card['word'])
                for example in card.get('examples', []):
                    taught |= russian_words(example['ru'])
            for question in lesson['questions']:
                with self.subTest(lesson=lesson['id'], question=question['id']):
                    texts = [question.get('passage', ''), question.get('audio_text', '')]
                    if question['choices_language'] == 'ru':
                        texts += [choice['text'] for choice in question['choices']]
                    for text in texts:
                        self.assertLessEqual(russian_words(text), taught)

    def test_teaching_and_listening_assets_have_distinct_stable_paths(self):
        recordings = []
        listening = []
        for lesson in self.content['lessons']:
            for item in [*lesson['teaching'], *lesson['questions']]:
                if item.get('audio_url'):
                    self.assertEqual(item['audio_url'], '/static/audio/first-steps-v2/' + item['id'] + '.mp3')
                    self.assertTrue(item['audio_text'])
                    recordings.append(item['audio_url'])
            for question in lesson['questions']:
                if question.get('audio_url'):
                    self.assertEqual(question['audio_text'], question['transcript'])
                    self.assertNotIn('passage', question)
                    listening.append(question['id'])
        self.assertEqual(len(recordings), len(set(recordings)))
        self.assertEqual(len(recordings), 18)
        self.assertEqual(listening, ['bag-listen-object', 'introductions-listen-name', 'ownership-listen-exchange'])

    def test_bag_listening_matches_the_recorded_sentence_with_parallel_choices(self):
        lesson = next(item for item in self.content['lessons'] if item['id'] == 'bag')
        question = next(item for item in lesson['questions'] if item['id'] == 'bag-listen-object')
        self.assertEqual(question['prompt'], 'Listen. Which sentence did you hear?')
        self.assertEqual([choice['text'] for choice in question['choices']],
                         ['Это карта.', 'Это сумка.', 'Это письмо.'])
        correct = next(choice['text'] for choice in question['choices'] if choice['id'] == question['answer'])
        self.assertEqual(correct, question['audio_text'])
        self.assertEqual(correct, question['transcript'])

    def test_authored_card_vocabulary_has_one_target_and_matching_morphology(self):
        for lesson in self.content['lessons']:
            for item in lesson['vocabulary']:
                with self.subTest(lesson=lesson['id'], form=item['form']):
                    self.assertTrue(all(item.get(key) for key in ('lemma', 'form', 'pos', 'sentence', 'translation', 'target_meaning')))
                    self.assertEqual(len(re.findall(r'(?<!\w)' + re.escape(item['form']) + r'(?!\w)', item['sentence'], flags=re.IGNORECASE)), 1)
                    parses = [parse for parse in self.morph.parse(item['form'])
                              if parse.normal_form == item['lemma'] and parse.tag.POS == item['pos']
                              and all(getattr(parse.tag, key, None) == value for key, value in item['grammar'].items())]
                    self.assertTrue(parses, item)


if __name__ == '__main__':
    unittest.main()
