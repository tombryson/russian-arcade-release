"""The six starter packs use taught Russian rather than guessed lemma meanings."""
from copy import deepcopy
import hashlib
import json
import unittest

from repositories.learning_repository import LearningError
from services.first_steps import HELLO, chapter_content
from services.journey_game_content import DIRECTION_WORDS, NEW_GAMES, PICTURES, build_content, cloze_sentence


class JourneyGameContentTests(unittest.TestCase):
    def setUp(self):
        content = chapter_content()
        self.lessons = {lesson['id']: deepcopy(lesson) | {'chapter_id': content['id'], 'version': content['version']}
                        for lesson in content['lessons']}
        self.lessons['hello'] = deepcopy(HELLO)
        self.games = {game['id']: game for game in NEW_GAMES}

    def lesson(self, game_id):
        lesson = deepcopy(self.lessons[self.games[game_id]['lesson_id']])
        lesson['related_lessons'] = [deepcopy(item) for item in self.lessons.values() if item['position'] <= lesson['position'] and item['id'] != lesson['id']]
        return lesson

    def build(self, game_id, seed='test-seed'):
        return build_content(self.games[game_id], self.lesson(game_id), seed)

    def test_registry_unlocks_six_distinct_games_at_their_teaching_milestones(self):
        self.assertEqual({game['id']: game['lesson_id'] for game in NEW_GAMES}, {
            'pairs': 'bag', 'missing-stamp': 'bag', 'radio': 'directions',
            'mailbox-sort': 'help', 'letter-back': 'help', 'detective': 'set-off'})
        self.assertEqual(len({game['title'] for game in NEW_GAMES}), 6)

    def test_every_pack_is_seeded_three_rounds_and_does_not_mutate_saved_lessons(self):
        for game_id, game in self.games.items():
            with self.subTest(game=game_id):
                lesson = self.lesson(game_id)
                before = deepcopy(lesson)
                first = build_content(game, lesson, 'first-seed')
                self.assertEqual(first, build_content(game, lesson, 'first-seed'))
                self.assertEqual(lesson, before)
                self.assertEqual(len(first['rounds']), 3)
                self.assertEqual(len({item['id'] for item in first['rounds']}), 3)
                self.assertTrue(all(item['mechanic'] == game_id for item in first['rounds']))
                self.assertEqual(first['source']['lesson_id'], lesson['id'])
                self.assertEqual(first['lesson_version'], lesson['version'])
                variants = {json.dumps(build_content(game, lesson, str(seed)), ensure_ascii=False, sort_keys=True) for seed in range(6)}
                self.assertGreater(len(variants), 1)

    def test_audio_text_and_vocabulary_provenance_come_from_frozen_completed_corpus(self):
        known = set()
        for lesson in self.lessons.values():
            known.update(word['sentence'] for word in lesson.get('vocabulary', []))
            known.update(card['word'] for card in lesson.get('teaching', []))
            known.update(choice['text'] for question in lesson.get('questions', []) for choice in question['choices'])
        for game_id in self.games:
            pack = self.build(game_id)
            self.assertTrue(set(pack['media_texts']) <= known, game_id)
            self.assertTrue(pack['vocabulary_refs'], game_id)
            for ref in pack['vocabulary_refs']:
                source = next(word for word in self.lessons[ref['lesson_id']]['vocabulary']
                              if word['lemma'] == ref['lemma'] and word['sentence'] == ref['sentence'])
                self.assertEqual({key: ref[key] for key in source}, source)
                self.assertIn(ref['sentence'], pack['media_texts'], 'Native cards must come from language actually used in this game.')
            for item in pack['rounds']:
                media = item['clues'] + item.get('answer_audio', []) + item.get('left', []) + item.get('sentences', [])
                for clue in media:
                    self.assertIn(clue['text'], pack['media_texts'])
                    self.assertEqual(clue['audio_key'], hashlib.sha256(clue['text'].encode('utf-8')).hexdigest())

    def test_pairs_match_contexts_to_pictures_with_bijections_and_two_then_three_items(self):
        pack = self.build('pairs')
        self.assertEqual([len(item['left']) for item in pack['rounds']], [2, 3, 3])
        visual_for_text = {word['sentence']: PICTURES[word['lemma']][0] for word in self.lessons['bag']['vocabulary']}
        for item in pack['rounds']:
            left = {card['id']: card for card in item['left']}
            right = {card['id']: card for card in item['right']}
            mappings = [answer.split(':') for answer in item['expected_answer']]
            self.assertEqual({source for source, _ in mappings}, set(left))
            self.assertEqual({target for _, target in mappings}, set(right))
            self.assertEqual(item['max_choices'], len(left))
            for source, target in mappings:
                self.assertEqual(visual_for_text[left[source]['text']], right[target]['visual'])

    def test_clozes_keep_whole_context_translation_and_exact_taught_surface_form(self):
        lesson = self.lesson('missing-stamp')
        word = next(word for word in lesson['vocabulary'] if word['lemma'] == 'карта')
        word.update(form='карту', sentence='Барсик берёт карту.', translation='Barsik takes the map.', grammar={'case': 'accs', 'number': 'sing'})
        pack = build_content(self.games['missing-stamp'], lesson, 'case-test')
        item = next(item for item in pack['rounds'] if item['visual'] == 'map')
        self.assertEqual(item['sentence'], 'Барсик берёт [[blank]].')
        self.assertEqual(item['translation'], 'Barsik takes the map.')
        selected = next(choice['text'] for choice in item['choices'] if choice['id'] == item['expected_answer'][0])
        self.assertEqual(selected, 'карту')
        self.assertEqual(item['clues'], [])
        self.assertEqual(item['answer_audio'][0]['text'], word['sentence'])
        ref = next(word for word in pack['vocabulary_refs'] if word['lemma'] == 'карта')
        self.assertEqual(ref['grammar']['case'], 'accs')

    def test_cloze_rejects_ambiguous_occurrences_partial_words_and_mismatched_stress(self):
        self.assertEqual(cloze_sentence('Покажите, пожалуйста.', 'Покажите'), '[[blank]], пожалуйста.')
        self.assertEqual(cloze_sentence('Это письмо.', 'ПИСЬМО'), 'Это [[blank]].')
        for sentence, word in [('карта и карта', 'карта'), ('карта', 'карт'), ('карта́', 'карта')]:
            with self.assertRaises(LearningError):
                cloze_sentence(sentence, word)

    def test_radio_covers_all_three_recorded_directions_and_no_text_choice_answers(self):
        pack = self.build('radio')
        expected = set()
        for item in pack['rounds']:
            self.assertTrue(item['audio_required'])
            self.assertEqual(len(item['clues']), 1)
            word = next(word for word in self.lessons['directions']['vocabulary'] if word['sentence'] == item['clues'][0]['text'])
            self.assertEqual(item['expected_answer'], [DIRECTION_WORDS[word['lemma']]])
            expected.add(item['expected_answer'][0])
            self.assertTrue(all('visual' in choice and 'text' not in choice for choice in item['choices']))
        self.assertEqual(expected, {'left', 'straight', 'right'})

    def test_mailbox_categories_classify_communicative_function_not_unseen_noun_topics(self):
        expected = {}
        for lesson_id, category in [('bag', 'name'), ('directions', 'direction'), ('help', 'help')]:
            for word in self.lessons[lesson_id]['vocabulary']:
                expected[word['sentence']] = category
        for item in self.build('mailbox-sort')['rounds']:
            sentences = {word['id']: word['text'] for word in item['sentences']}
            self.assertEqual({box['id'] for box in item['bins']}, {'name', 'direction', 'help'})
            self.assertEqual(len(item['expected_answer']), 3)
            for mapping in item['expected_answer']:
                source, category = mapping.split(':')
                self.assertEqual(expected[sentences[source]], category)

    def test_letter_back_orders_whole_utterances_by_communicative_goal(self):
        meanings = {
            'Greet the clerk politely, then ask where the market is.': ['Здравствуйте!', 'Где рынок?'],
            'Ask the clerk to show you the way, then say thank you.': ['Покажите, пожалуйста.', 'Спасибо!'],
            'Greet Barsik by name, then tell him this is a map.': ['Привет, Барсик!', 'Это карта.'],
        }
        for item in self.build('letter-back')['rounds']:
            choices = {tile['id']: tile['text'] for tile in item['tiles']}
            answer = [choices[key] for key in item['expected_answer']]
            self.assertEqual(answer, meanings[item['prompt']])
            self.assertEqual(item['max_choices'], 2)
            self.assertEqual(len(choices), 4)
            self.assertTrue(all(phrase[-1] in '.!?' for phrase in choices.values()))
            self.assertEqual([clue['text'] for clue in item['answer_audio']], answer)
            self.assertEqual(item['clues'], [])

    def test_detective_needs_two_independent_linguistic_clues_not_colour_or_position(self):
        for item in self.build('detective')['rounds']:
            self.assertEqual(len(item['clues']), 2)
            self.assertEqual(len(item['destinations']), 4)
            target = next(card for card in item['destinations'] if card['id'] == item['expected_answer'][0])
            same_object = {card['id'] for card in item['destinations'] if card['visual'] == target['visual']}
            same_route = {card['id'] for card in item['destinations'] if card['route'] == target['route']}
            self.assertEqual(len(same_object), 2)
            self.assertEqual(len(same_route), 2)
            self.assertEqual(same_object & same_route, {target['id']})
            self.assertTrue(all('colour' not in card and 'color' not in card for card in item['destinations']))
        self.assertEqual(len(self.build('detective')['rounds'][2]['destinations'][0]['route']), 2)

    def test_missing_required_frozen_lesson_never_falls_back_to_current_source_file(self):
        lesson = self.lesson('mailbox-sort')
        lesson['related_lessons'] = []
        with self.assertRaises(LearningError) as error:
            build_content(self.games['mailbox-sort'], lesson, 'no-corpus')
        self.assertEqual(error.exception.code, 'game_content_unavailable')


if __name__ == '__main__':
    unittest.main()
