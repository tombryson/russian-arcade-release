"""Recall grades the visible Russian sequence, not hidden duplicate tile IDs."""
import unittest
import json
import sqlite3

from repositories.learning_repository import LearningError
from services.journey_games import assess_answer, normalise_answer
from services.skill_progress import freeze_evidence


class ReplyTileEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.item = {'mechanic': 'letter-back', 'max_choices': 5,
                     'tiles': [{'id': 'one', 'text': 'Я'}, {'id': 'two', 'text': 'и'},
                               {'id': 'three', 'text': 'ты'}, {'id': 'four', 'text': 'и'},
                               {'id': 'five', 'text': 'он.'}],
                     'expected_answer': ['one', 'two', 'three', 'four', 'five']}

    def test_identical_tiles_can_be_exchanged_and_retried_in_either_identity_order(self):
        swapped = ['one', 'four', 'three', 'two', 'five']
        canonical = normalise_answer(self.item, swapped, 'letter-back')
        self.assertEqual(canonical, self.item['expected_answer'])
        self.assertEqual(assess_answer(self.item, swapped), {'correct': True, 'score': 1, 'matched': 5, 'total': 5})
        self.assertEqual(assess_answer(self.item, canonical), assess_answer(self.item, swapped))

    def test_different_visible_order_is_still_wrong_and_reusing_one_tile_is_rejected(self):
        wrong = ['one', 'three', 'four', 'two', 'five']
        answer = normalise_answer(self.item, wrong, 'letter-back')
        result = assess_answer(self.item, answer)
        self.assertFalse(result['correct'])
        self.assertEqual(result['matched'], 3)
        with self.assertRaises(LearningError):
            normalise_answer(self.item, ['one', 'two', 'three', 'two', 'five'], 'letter-back')

    def test_introductory_reply_still_accepts_valid_but_incorrect_distractor_tiles(self):
        item = {'mechanic': 'letter-back', 'max_choices': 2,
                'tiles': [{'id': 'hello', 'text': 'Здравствуйте!'}, {'id': 'question', 'text': 'Где рынок?'},
                          {'id': 'map', 'text': 'Это карта.'}], 'expected_answer': ['hello', 'question']}
        answer = normalise_answer(item, ['hello', 'map'], 'letter-back')
        self.assertEqual(answer, ['hello', 'map'])
        self.assertEqual(assess_answer(item, answer), {'correct': False, 'score': .5, 'matched': 1, 'total': 2})

    def test_directions_rates_route_language_even_with_advanced_picture_vocabulary(self):
        with sqlite3.connect(':memory:') as conn:
            conn.execute('CREATE TABLE journey_game_sessions(id TEXT,game_id TEXT,content_json TEXT,answers_json TEXT,acknowledged_json TEXT,completed_at INTEGER,profile_id TEXT,created_at INTEGER)')
            content = {'version': 'journey-vocabulary-v1', 'lesson_version': 'test', 'word_difficulty': 8,
                       'rounds': [{'id': 'r1', 'mechanic': 'directions', 'clues': [{'text':'Налево.'}], 'expected_answer': ['left']}]}
            answers = {'r1': {'answer': ['left'], 'hint_used': False, 'transcript_used': False}}
            conn.execute('INSERT INTO journey_game_sessions VALUES (?,?,?,?,?,?,?,?)',
                         ('s1', 'directions', json.dumps(content), json.dumps(answers), '["r1"]', 1, 'p1', 1))
            evidence = freeze_evidence(conn, 'journey_game', 'journey-game:directions:test', 's1', None, {})
        self.assertEqual(evidence['_skill']['task_rating'], 1000)
        self.assertEqual(evidence['_skill']['task_difficulty']['basis'], 'direction-route')
        self.assertEqual(evidence['_skill']['scores'], {'reading': 1})
