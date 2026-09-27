"""Authored coverage and morphology checks without providers or learner data."""
import json
from pathlib import Path
import re
import unittest

import pymorphy3

from services.first_delivery import VERSIONS
from services.first_steps import HELLO


CONTENT = Path(__file__).resolve().parents[1] / 'data' / 'first_steps.json'


def russian_words(text):
    return re.findall(r'[а-яё]+', text.casefold())


class FirstStepsContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = json.loads(CONTENT.read_text())
        cls.morph = pymorphy3.MorphAnalyzer()

    def test_series_has_one_reused_greeting_and_four_complete_lessons(self):
        self.assertEqual(self.content['id'], 'first-steps')
        self.assertEqual(self.content['first_lesson']['source'], 'first-delivery-v2')
        self.assertEqual(self.content['first_lesson']['position'], 1)
        self.assertEqual(self.content['first_lesson']['vocabulary'], HELLO['vocabulary'],
                         'The source must match the immutable bridge descriptor for saved v2 greetings.')
        self.assertEqual([(lesson['id'], lesson['position']) for lesson in self.content['lessons']],
                         [('bag', 2), ('directions', 3), ('help', 4), ('set-off', 5)])
        seen = set()
        for lesson in self.content['lessons']:
            with self.subTest(lesson=lesson['id']):
                self.assertIn(len(lesson['teaching']), (3, 4))
                self.assertIn(len(lesson['questions']), (3, 4))
                self.assertTrue(all(lesson.get(key) for key in ('title', 'description', 'resolution')))
                for teaching in lesson['teaching']:
                    self.assertTrue(all(teaching.get(key) for key in ('id', 'title', 'word', 'meaning', 'explanation')))
                for question in lesson['questions']:
                    self.assertNotIn(question['id'], seen)
                    seen.add(question['id'])
                    self.assertTrue(all(question.get(key) for key in ('prompt', 'hint', 'feedback')))
                    choices = question['choices']
                    ids = [choice['id'] for choice in choices]
                    self.assertEqual(len(ids), len(set(ids)))
                    self.assertIn(question['answer'], ids)
                    self.assertGreaterEqual(len(choices), 2)

    def test_all_answers_and_reading_clues_use_russian_taught_before_the_check(self):
        taught = {word for question in VERSIONS['first-delivery-v2']
                  for word in russian_words(question['lesson']['word'])}
        visuals = {'letter', 'bag', 'map', 'straight', 'left', 'right'}
        for lesson in self.content['lessons']:
            for teaching in lesson['teaching']:
                taught.update(russian_words(teaching['word']))
                taught.update(russian_words(teaching.get('example', '')))
                if 'visual' in teaching:
                    self.assertIn(teaching['visual'], visuals)
            for question in lesson['questions']:
                with self.subTest(lesson=lesson['id'], question=question['id']):
                    for choice in question['choices']:
                        self.assertRegex(choice['text'], r'[А-Яа-яЁё]')
                        self.assertNotRegex(choice['text'], r'[A-Za-z]')
                        self.assertLessEqual(set(russian_words(choice['text'])), taught,
                                             'A distractor or answer requires an untaught Russian word.')
                    self.assertLessEqual(set(russian_words(question.get('passage', ''))), taught,
                                         'The reading clue includes language that was never introduced.')
                    if 'visual' in question:
                        self.assertIn(question['visual'], visuals)

    def test_native_card_candidates_have_one_contextual_target_and_unambiguous_morphology(self):
        grammar_fields = ('case', 'number', 'gender', 'animacy', 'tense', 'person', 'mood', 'aspect', 'voice')
        for lesson in [self.content['first_lesson'], *self.content['lessons']]:
            self.assertIn(len(lesson['vocabulary']), (2, 3))
            for item in lesson['vocabulary']:
                with self.subTest(lesson=lesson['id'], word=item['form']):
                    self.assertTrue(all(item.get(key) for key in ('lemma', 'form', 'pos', 'sentence', 'translation', 'target_meaning')))
                    self.assertEqual(russian_words(item['sentence']).count(item['form'].casefold()), 1)
                    self.assertGreater(len(russian_words(item['sentence'])), 1,
                                       'A native cloze must leave some context after its target is hidden.')
                    self.assertEqual(len(russian_words(item['form'])), 1)
                    self.assertIsInstance(item['grammar'], dict)
                    parses = [parse for parse in self.morph.parse(item['form'].casefold())
                              if parse.is_known and parse.normal_form == item['lemma'] and parse.tag.POS == item['pos']
                              and all(getattr(parse.tag, key, None) == value for key, value in item['grammar'].items())]
                    signatures = {tuple(getattr(parse.tag, key, None) for key in grammar_fields) for parse in parses}
                    self.assertEqual(len(signatures), 1, 'The native card resolver needs a single grammatical reading.')
                    if item['pos'] == 'NOUN':
                        self.assertIn(item['grammar'].get('case'), ('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct'))
                        self.assertIn(item['grammar'].get('number'), ('sing', 'plur'))
                    self.assertNotIn(';', item['target_meaning'], 'Use this sentence’s meaning, not a dictionary list.')

    def test_final_clue_resolves_the_post_office_route_toward_the_market(self):
        final = self.content['lessons'][-1]
        clues = [question for question in final['questions'] if question.get('passage')]
        self.assertGreaterEqual(len(clues), 2)
        self.assertTrue(any('Рынок там. Прямо, потом налево.' in question['passage'] for question in clues))
        self.assertEqual(clues[-1]['answer'], 'market')
        self.assertIn('leaves the post office', final['resolution'])
        self.assertIn('toward the market', final['resolution'])
        self.assertIn('still on its way to you', final['resolution'])


if __name__ == '__main__':
    unittest.main()
