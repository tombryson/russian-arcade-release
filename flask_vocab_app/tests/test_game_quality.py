"""Learning-quality regressions: chance, correction history and Russian forms."""
from itertools import combinations, permutations, product
import json
import random
import unittest
from tests.game_fixtures import grant_earned_game_access

from repositories.learning_repository import encoded, identifier, transaction
from services.cloze_choices import choices_for
from services.game_assessment import chance_score, evidence_keys, expected_score
from services.journey_games import assess_answer
from services.skill_progress import snapshot, freeze_evidence
from tests import test_journey_games as journey_tests
from tests.support import select_test_profile


class ChanceTests(unittest.TestCase):
    def assert_baseline(self, item, answers):
        baseline = chance_score(item, item['mechanic'])
        observed = sum(assess_answer(item, answer)['score'] for answer in answers) / len(answers)
        self.assertAlmostEqual(baseline, observed)
        for rating in (600, 1000, 1400, 1800):
            for difficulty in (1000, 1200, 1400, 1600, 1800):
                self.assertLessEqual(observed - expected_score(rating, difficulty, baseline), 0)

    def test_actual_scoring_rules_match_chance_baselines(self):
        for mechanic in ('missing-stamp', 'radio', 'detective'):
            item = {'mechanic': mechanic, 'expected_answer': ['a'],
                    'destinations' if mechanic == 'detective' else 'choices': [{'id': x} for x in 'abcd']}
            self.assert_baseline(item, [[x] for x in 'abcd'])
        for mechanic in ('pairs', 'mailbox-sort'):
            item = {'mechanic': mechanic, 'expected_answer': ['a:x', 'b:y', 'c:z'],
                    'right' if mechanic == 'pairs' else 'bins': [{'id': x} for x in 'xyz']}
            choices = permutations('xyz') if mechanic == 'pairs' else product('xyz', repeat=3)
            self.assert_baseline(item, [[f'{a}:{b}' for a,b in zip('abc', values)] for values in choices])
        self.assert_baseline({'mechanic': 'pack-bag', 'expected_answer': ['a','c'],
                             'objects': [{'id': x} for x in 'abcd']}, [list(x) for x in combinations('abcd',2)])
        self.assert_baseline({'mechanic': 'directions', 'expected_answer': ['left','right','straight']},
                             [list(x) for x in product(('left','right','straight'), repeat=3)])
        self.assert_baseline({'mechanic': 'letter-back', 'expected_answer': ['a','b','c'],
                             'tiles': [{'id': 'a','text':'да'}, {'id': 'b','text':'да'}, {'id': 'c','text':'нет'}]},
                            [list(x) for x in permutations('abc')])

    def test_content_identity_survives_shuffle_and_game_type(self):
        first = {'evidence_texts': ['Я говорю с учителем.']}
        second = {'clues': [{'text': 'Я говорю с учителем.'}]}
        self.assertEqual(evidence_keys(first), evidence_keys(second))


class CorrectionTests(unittest.TestCase):
    setUp = journey_tests.JourneyGamesTests.setUp
    token = journey_tests.JourneyGamesTests.token
    request = journey_tests.JourneyGamesTests.request
    post = journey_tests.JourneyGamesTests.post
    start = journey_tests.JourneyGamesTests.start
    seed_lesson = journey_tests.JourneyGamesTests.seed_lesson
    expected = journey_tests.JourneyGamesTests.expected
    read = journey_tests.JourneyGamesTests.read
    finish = journey_tests.JourneyGamesTests.finish
    counts = journey_tests.JourneyGamesTests.counts

    def game(self):
        select_test_profile(self.client)
        self.seed_lesson('bag')
        grant_earned_game_access(self.db)
        return self.start()

    def test_correction_survives_refresh_and_never_changes_first_answer(self):
        state = self.game()
        sid, item = state['id'], self.expected(state['id'])[0]
        self.post(sid, 'answer', {'round_id': item['id'], 'answer': ['apple']})
        before = self.counts()
        practice = self.post(sid, 'retry', {'round_id': item['id']})
        self.assertEqual(practice['phase'], 'practice')
        self.assertIsNone(practice['result'])
        self.assertNotIn('expected_answer', practice['round'])
        self.assertEqual(self.read(sid)['practice']['mode'], 'correction')
        data = {'round_id': item['id'], 'answer': item['expected_answer'], 'request_id': 'correction-1234'}
        result = self.post(sid, 'practice_answer', data)
        self.assertEqual(result['phase'], 'practice_feedback')
        self.assertTrue(result['result']['correct'])
        self.post(sid, 'practice_answer', data)
        self.assertEqual(self.counts(), before)
        with transaction(self.db) as conn:
            answers = json.loads(conn.execute('SELECT answers_json FROM journey_game_sessions WHERE id=?', (sid,)).fetchone()[0])
            self.assertEqual(answers[item['id']]['answer'], ['apple'])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM journey_game_corrections').fetchone()[0], 1)
        next_round = self.post(sid, 'practice_continue', {'round_id': item['id']})
        self.assertEqual(next_round['phase'], 'play')
        self.assertEqual(next_round['round_index'], 1)

    def test_completed_review_keeps_rewards_and_progress_unchanged(self):
        state = self.game()
        first = self.expected(state['id'])[0]
        done = self.finish(state, wrong=(first['id'],))
        before = self.counts()
        before_skill = done['progression']['skill']
        self.assertEqual(done['summary']['missed_rounds'], 1)
        practice = self.post(state['id'], 'review')
        self.assertEqual(practice['practice']['total'], 1)
        self.assertEqual(practice['round']['id'], first['id'])
        self.post(state['id'], 'practice_answer', {'round_id':first['id'], 'answer': first['expected_answer'], 'request_id':'review-answer-1'})
        done_again = self.post(state['id'], 'practice_continue', {'round_id':first['id']})
        self.assertEqual(done_again['phase'], 'completed')
        self.assertEqual(done_again['progression']['skill'], before_skill)
        self.assertEqual(done_again['summary']['missed_rounds'], 1)
        self.assertEqual(self.counts(), before)

    def test_correction_is_optional_and_wrong_or_foreign_rounds_are_rejected(self):
        state = self.game()
        item = self.expected(state['id'])[0]
        self.post(state['id'], 'retry', {'round_id':item['id']}, status=409)
        self.post(state['id'], 'answer', {'round_id':item['id'], 'answer':['apple']})
        self.post(state['id'], 'retry', {'round_id':item['id']})
        self.post(state['id'], 'practice_answer', {'round_id':'other-round','answer':['letter'],'request_id':'wrong-round-123'}, status=409)
        self.post(state['id'], 'practice_hint', {'round_id':item['id']})
        self.assertTrue(self.read(state['id'])['round']['hint'])
        state = self.post(state['id'], 'practice_exit')
        self.assertEqual(state['phase'], 'feedback')
        other = self.app.test_client()
        self.assertEqual(other.get('/api/v1/games/sessions/'+state['id']).status_code,404)

    def test_legacy_receipts_remain_replayable_alongside_new_game_policy(self):
        state = self.game()
        self.finish(state)
        with transaction(self.db, write=True) as conn:
            row = conn.execute("SELECT id,evidence_json FROM progression_events WHERE activity='journey_game'").fetchone()
            evidence = json.loads(row['evidence_json'])
            self.assertEqual(evidence['_skill']['policy_version'], 'game-evidence-v2')
            self.assertEqual(evidence['unassisted_count'], 2)  # Third round repeats both revealed words.
            evidence['_skill'].update(policy_version='practice-elo-v1', scores={'reading':1})
            conn.execute('UPDATE progression_events SET evidence_json=? WHERE id=?', (encoded(evidence),row['id']))
            skill = next(s for s in snapshot(conn,'personal-learning')['skills'] if s['id']=='reading')
            self.assertEqual(skill['rating'],1012)
            self.assertEqual(skill['observations'],1)


    def test_exposure_uses_answer_time_when_sessions_are_opened_out_of_order(self):
        state = self.game()
        self.finish(state)
        with transaction(self.db, write=True) as conn:
            row = conn.execute('SELECT * FROM journey_game_sessions WHERE id=?', (state['id'],)).fetchone()
            content, answers = json.loads(row['content_json']), json.loads(row['answers_json'])
            for answer in answers.values():
                answer['answered_at'] = 100
            conn.execute('UPDATE journey_game_sessions SET answers_json=?,created_at=1 WHERE id=?', (encoded(answers), row['id']))
            first = content['rounds'][0]['id']
            # A newer session can reveal content before an older one is answered.
            conn.execute('INSERT INTO journey_game_sessions(id,profile_id,game_id,seed,request_ids_json,content_json,answers_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                         ('overlapping-session', row['profile_id'], 'pairs', 'seed', '[]', encoded(content),
                          encoded({first: dict(answers[first], answered_at=60)}), 50, 60))
            key = f'journey-game:{row["game_id"]}:{content["lesson_version"]}'
            evidence = freeze_evidence(conn, 'journey_game', key, row['id'], None, {})
            self.assertEqual(evidence['unassisted_count'], 1)
            # Later feedback must not invalidate a genuinely earlier answer.
            conn.execute('UPDATE journey_game_sessions SET answers_json=? WHERE id=?',
                         (encoded({first: dict(answers[first], answered_at=150)}), 'overlapping-session'))
            evidence = freeze_evidence(conn, 'journey_game', key, row['id'], None, {})
            self.assertEqual(evidence['unassisted_count'], 2)


class RussianChoiceTests(unittest.TestCase):
    def make(self, lemma, form, sentence, tags):
        return choices_for({'lemma':lemma,'form':form,'sentence':sentence,'tags':tags}, [], random.Random(2))

    def test_grammar_rules_match_whole_words_and_the_actual_blank(self):
        noun = self.make('учитель', 'учителя', 'Это кабинет учителя.', {'case':'gent', 'number':'sing'})
        self.assertEqual(noun['objective'], 'vocabulary')
        verb = self.make('идти', 'идёт', 'Маша придёт позже, а он идёт сейчас.', {'tense':'pres', 'person':'3per', 'number':'sing'})
        self.assertEqual(verb['objective'], 'grammar')

    def test_instrumental_question_uses_same_lemma_and_excludes_equivalent_readings(self):
        result = self.make('учитель','учителем','Я говорю с учителем.',{'case':'ablt','number':'sing'})
        self.assertEqual(result['objective'],'grammar')
        self.assertEqual(result['forms'][0],'учителем')
        self.assertGreater(len(result['forms']),1)
        self.assertNotIn('учителями',result['forms'])
        self.assertTrue(result['explanation_ru'])

    def test_finite_verb_uses_other_persons_not_unrelated_nouns(self):
        result = self.make('читать','читаю','Я читаю книгу.',{'tense':'pres','person':'1per','number':'sing'})
        self.assertEqual(result['objective'],'grammar')
        self.assertEqual(set(result['forms']),{'читаю','читаешь','читает'})

    def test_ambiguous_preposition_is_not_claimed_as_a_case_rule(self):
        result = self.make('школа','школы','Я пришёл со школы.',{'case':'gent','number':'sing'})
        self.assertEqual(result['objective'],'vocabulary')
        self.assertNotIn('школу',result['forms'])

    def test_syncretic_case_form_is_not_offered_as_a_wrong_answer(self):
        result = self.make('мама','маме','Я помогаю маме.',{'case':'datv','number':'sing'})
        self.assertEqual(result['objective'],'grammar')
        self.assertEqual(len([s for s in result['forms'] if s=='маме']),1)

class ReadingLanguageTests(unittest.TestCase):
    def test_assessment_requests_the_selected_interface_language(self):
        from flask import Flask, session
        from types import SimpleNamespace
        from unittest.mock import Mock
        from services.comprehension_service import ComprehensionService
        service = ComprehensionService.__new__(ComprehensionService)
        completion = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"feedback":["Clear answer."],"scores":[8]}'))]))
        service.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
        app = Flask(__name__)
        app.secret_key = 'test-only'
        for language, expected in [('en', 'English'), ('ru', 'Russian')]:
            with self.subTest(language=language), app.test_request_context('/'):
                session['ui_lang'] = language
                feedback, scores, total = service._evaluate_answers('Текст.', ['Кто?'], ['Барсик.'])
                self.assertIn('all feedback in ' + expected, completion.call_args.kwargs['messages'][0]['content'])
                self.assertEqual(scores, [8])
