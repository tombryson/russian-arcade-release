"""A capitalised Russian pronoun is not an additional named person."""
import unittest

from services.curriculum_situation_content import _antecedent_start
from tests.test_curriculum_source_v6 import request_for_family


class ReferenceNameTests(unittest.TestCase):
    def reference_plan(self):
        request = request_for_family('talking-about-topics-v1', 'topics-thought-and-speech')
        plan = request['language_plan']
        fact = next(f for f in plan['meaning_plan']['facts'] if f['role'] == 'location')
        person = next(p for p in plan['meaning_plan']['participants'] if p['name_ru'] == fact['subject_name'])
        return plan, fact, person

    def test_quoted_ya_does_not_become_a_second_same_gender_person(self):
        plan, fact, person = self.reference_plan()
        pronoun = 'она' if person['gender'] == 'feminine' else 'он'
        sentences = [f"{person['name_ru']} говорит: «Я думаю о семье».", f"Сейчас {pronoun} в парке."]
        self.assertEqual(_antecedent_start(plan, fact, sentences, 1, 1), 0)

    def test_real_additional_name_is_still_a_competing_antecedent(self):
        plan, fact, person = self.reference_plan()
        other = 'Юлия' if person['gender'] == 'feminine' else 'Андрей'
        pronoun = 'Она' if person['gender'] == 'feminine' else 'Он'
        sentences = [f"Это {person['name_ru']} и {other}.", f"{pronoun} говорит о семье."]
        with self.assertRaisesRegex(ValueError, 'ambiguous named antecedent'):
            _antecedent_start(plan, fact, sentences, 1, 1)


if __name__ == '__main__':
    unittest.main()
