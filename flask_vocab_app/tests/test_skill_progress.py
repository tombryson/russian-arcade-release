"""Practice Elo receipts are scoped, reproducible, and separate from rewards."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from migrations import upgrade_database
from repositories.learning_repository import timestamp
from repositories.translation_repository import TranslationRepository
from services.progression import award, award_speaking, personal_profile, reverse
from services.skill_progress import POLICY, snapshot


class SkillProgressTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = str(Path(temporary.name) / 'practice.db')
        upgrade_database(self.db, backup=False)
        self.conn = sqlite3.connect(self.db)
        self.addCleanup(self.conn.close)
        self.pid = personal_profile(self.conn)
        self.now = timestamp() + 1
        self.sources = {}
        self.conn.commit()

    def state(self, pid=None):
        return snapshot(self.conn, pid or self.pid)

    def skill(self, key='translation', pid=None):
        return next(item for item in self.state(pid)['skills'] if item['id'] == key)

    def sentence(self, key, difficulty=1):
        return self.conn.execute('''INSERT INTO sentences(sentence,english,topic,difficulty)
            VALUES (?,?,'home',?)''', ('Кот ' + key, 'Cat ' + key, difficulty)).lastrowid

    def check(self, source, task=None, score=4, difficulty=1, pid=None):
        task = self.sentence(source, difficulty) if task is None else task
        if source not in self.sources:
            attempt = self.conn.execute('''INSERT INTO translation_attempts
                (sentence_id,response,score,strength,next_step,example,ui_language,created_at,coins_earned,elo_change,already_rewarded)
                VALUES (?,'Кот спит.',?,'Clear.','Try.','Кот спит.','en',?,0,0,0)''',
                (task, score if type(score) is int and 0 <= score <= 4 else 0, str(self.now))).lastrowid
            self.sources[source] = 'translation-attempt:' + str(attempt)
        award(self.conn, pid or self.pid, activity='translation', content_key='translation:' + str(task),
              source_key=self.sources[source], title='Sentence practice', now=self.now,
              evidence={'score': score, 'score_max': 4})
        return task

    def speaking(self, source, *, grammar=5, fluency=4, status='russian', level='A1', words=None, variant=None):
        words = words if words is not None else 'Здравствуйте я хочу чашку чая без сахара и пирог пожалуйста'
        report = {'speech_status': status, 'transcript': words, 'rubric_version': 'speaking-audio-v1',
                  'grammar': {'score': grammar, 'evidence': ['я хочу чашку чая'] if grammar else []},
                  'fluency': {'score': fluency, 'evidence': ['без сахара и пирог'] if fluency else []}}
        session = {'id': source, 'profile_id': self.pid, 'created_at': self.now,
                   'scenario_json': json.dumps({'seed': variant or source, 'target_level': level, 'title': 'Café'})}
        return award_speaking(self.conn, session, report)

    def test_no_evidence_is_not_a_measured_rating_and_reads_do_not_write(self):
        self.conn.execute('UPDATE users SET elo_rating=1718,lingocoins=500 WHERE user_id=1')
        changes = self.conn.total_changes
        first = self.state()
        self.assertEqual(first, self.state())
        self.assertEqual(self.conn.total_changes, changes)
        self.assertEqual(first['status'], 'not_calibrated')
        self.assertEqual(first['policy_version'], POLICY)
        self.assertEqual(first['active_skill'], 'reading')
        for skill in first['skills']:
            self.assertIsNone(skill['rating'])
            self.assertEqual((skill['stage'], skill['progress'], skill['observations']), (1, 0, 0))

    def test_c2_translation_records_the_selected_task_difficulty(self):
        self.check('c2-translation', difficulty=6)
        evidence = json.loads(self.conn.execute("SELECT evidence_json FROM progression_events WHERE activity='translation'").fetchone()[0])
        self.assertEqual(evidence['_skill']['task_difficulty'], 6)
        self.assertEqual(evidence['_skill']['task_rating'], 2000)
        self.assertEqual(self.skill()['observations'], 1)

    def test_explicit_curriculum_reading_preserves_legacy_priors(self):
        for index, (level, prior) in enumerate((('advanced', 1400), ('B2', 1600), ('C1', 1800), ('C2', 2000))):
            self.conn.execute("INSERT INTO saved_stories(id,title,text,topic,difficulty) VALUES (?,'Test','Русский текст.','literature',?)", (index + 100, level))
            award(self.conn, self.pid, activity='reading', content_key='story:' + str(index + 100),
                  source_key='curriculum-check:' + level, title='Read a story', now=self.now,
                  evidence={'score': 8, 'score_max': 10, 'answered_questions': 5, 'first_fresh_assessment': True})
            evidence = json.loads(self.conn.execute('SELECT evidence_json FROM progression_events WHERE source_key=?', ('curriculum-check:' + level,)).fetchone()[0])
            self.assertEqual(evidence['_skill']['task_rating'], prior)

    def game_check(self, source, *, hints=(), answers=(['letter'], ['map']), complete=True,
                   game_id='pack-bag', transcripts=(), listened=True, custom_rounds=None):
        rounds = [{'id': 'one', 'expected_answer': ['letter']}, {'id': 'two', 'expected_answer': ['map']}]
        if custom_rounds is not None:
            rounds = custom_rounds
        for item in rounds:
            item.setdefault('evidence_texts', [item['id'] + ' unique question'])
            item.setdefault('objects', [{'id': value} for value in ('letter','map','apple','cup')])
            item.setdefault('choices', [{'id': value} for value in ('letter','map','apple','cup')])
        if game_id == 'radio':
            rounds = [item | {'mechanic': 'radio', 'clues': [{'audio_key': item['id'] + '-recording'}]} for item in rounds]
        content = {'lesson_version': 'first-steps-v1', 'rounds': rounds}
        saved = {item['id']: {'answer': answers[index], 'correct': True, 'hint_used': item['id'] in hints,
                             'transcript_used': item['id'] in transcripts,
                             'listened_audio_keys': [item['id'] + '-recording'] if listened else []}
                 for index, item in enumerate(rounds)}
        self.conn.execute('INSERT INTO journey_game_sessions '
                          '(id,profile_id,game_id,seed,request_ids_json,content_json,answers_json,acknowledged_json,completed_at,created_at,updated_at) '
                          'VALUES (?,?,?,?,\'[]\',?,?,?,?,?,?)',
                          (source, self.pid, game_id, source, json.dumps(content), json.dumps(saved), json.dumps([item['id'] for item in rounds]),
                           self.now if complete else None, self.now, self.now))
        award(self.conn, self.pid, activity='journey_game', content_key=f'journey-game:{game_id}:first-steps-v1',
              source_key=source, title='Pack the bag', now=self.now, target_level='A1',
              evidence={'score': 100, '_skill': {'scores': {'reading': 1}}})

    def test_journey_game_derives_reading_from_saved_answers_and_replay_cannot_inflate_it(self):
        self.game_check('first-game', answers=(['letter'], ['cup']))
        self.assertEqual((self.skill('reading')['rating'], self.skill('reading')['observations']), (997, 1))
        receipt = json.loads(self.conn.execute("SELECT evidence_json FROM progression_events WHERE activity='journey_game'").fetchone()[0])
        self.assertEqual(receipt['_skill']['scores'], {'reading': .5})
        self.assertEqual(receipt['basis'], 'contextual_reading_with_optional_audio')
        before = self.state()
        self.now += 86400
        self.game_check('later-perfect-game')
        self.assertEqual(before, self.state())

    def test_journey_game_english_hint_excludes_that_round(self):
        self.game_check('hinted-game', hints=('two',), answers=(['letter'], ['cup']))
        self.assertEqual(self.skill('reading')['rating'], 1009)
        receipt = json.loads(self.conn.execute("SELECT evidence_json FROM progression_events WHERE activity='journey_game'").fetchone()[0])
        self.assertEqual(receipt['unassisted_count'], 1)
        self.assertIsNone(self.skill('speaking_fluency')['rating'])

    def test_unfinished_or_entirely_hinted_game_has_no_skill_evidence(self):
        self.game_check('unfinished-game', complete=False)
        self.game_check('all-hinted-game', hints=('one', 'two'))
        self.game_check('later-unhinted-game')
        self.assertIsNone(self.skill('reading')['rating'])

    def test_radio_uses_listening_only_and_excludes_the_transcript_round(self):
        self.game_check('radio-first', game_id='radio', transcripts=('two',), answers=(['letter'], ['wrong']))
        self.assertEqual(self.skill('listening')['rating'], 1009)
        self.assertIsNone(self.skill('reading')['rating'])
        self.assertEqual(self.state()['active_skill'], 'listening')
        receipt = json.loads(self.conn.execute("SELECT evidence_json FROM progression_events WHERE activity='journey_game'").fetchone()[0])
        self.assertEqual(receipt['_skill']['scores'], {'listening': 1})
        self.assertEqual(receipt['unassisted_count'], 1)
        self.assertEqual(receipt['basis'], 'audio_recognition')

    def test_reading_the_radio_text_cannot_later_become_independent_listening(self):
        self.game_check('text-first', game_id='radio', transcripts=('one', 'two'))
        self.game_check('audio-replay', game_id='radio')
        self.assertIsNone(self.skill('listening')['rating'])
        self.assertIsNone(self.skill('reading')['rating'])

    def test_radio_requires_saved_play_receipts_for_a_listening_observation(self):
        self.game_check('unplayed', game_id='radio', listened=False)
        self.assertIsNone(self.skill('listening')['rating'])

    def test_matching_uses_partial_credit_from_actual_pairs_not_the_saved_score(self):
        rounds = [{'id': 'one', 'mechanic': 'pairs', 'right': [{'id': key} for key in ('x','y','z')], 'expected_answer': ['a:x', 'b:y', 'c:z']}]
        self.game_check('pairs-first', game_id='pairs', custom_rounds=rounds, answers=(['a:x', 'b:z', 'c:y'],))
        self.assertEqual(self.skill('reading')['rating'], 992)
        self.assertIsNone(self.skill('writing')['rating'])

    def test_performance_and_task_difficulty_both_change_rating(self):
        self.check('perfect')
        self.assertEqual(self.skill()['rating'], 1012)
        self.assertEqual(self.skill()['progress'], .06)
        self.check('hard-perfect', difficulty=5)
        self.assertGreater(self.skill()['rating'], 1034)
        self.assertEqual(self.skill()['observations'], 2)
        self.check('incorrect', score=0)
        self.assertLess(self.skill()['rating'], 1034)
        self.assertIsNone(self.skill('reading')['rating'])
        self.assertEqual(self.state()['active_skill'], 'translation')

    def test_low_rating_has_truthful_first_stage_gap(self):
        self.check('incorrect', score=0)
        state = self.skill()
        self.assertEqual((state['rating'], state['stage'], state['progress']), (988, 1, 0))
        self.assertEqual(state['points_to_next'], 212)

    def test_retries_same_content_different_days_do_not_inflate_skill(self):
        task = self.check('first', score=0)
        before = self.state()
        self.now += 86400
        self.check('retry', task=task, score=4)
        self.check('first', task=task, score=4)
        self.assertEqual(before, self.state())
        # Reversing does not promote a coached retry into an independent check.
        reverse(self.conn, self.pid, 'translation', self.sources['first'])
        self.assertEqual((self.skill()['rating'], self.skill()['observations']), (None, 0))

    def test_difficulty_is_frozen_and_projection_does_not_join_changed_content(self):
        task = self.check('first', difficulty=1)
        before = self.state()
        self.conn.execute('UPDATE sentences SET difficulty=5 WHERE id=?', (task,))
        self.assertEqual(before, self.state())
        receipt = json.loads(self.conn.execute('SELECT evidence_json FROM progression_events').fetchone()[0])['_skill']
        self.assertEqual(receipt['task_rating'], 1000)
        self.assertEqual(receipt['task_difficulty'], 1)
        self.assertEqual(receipt['scores'], {'translation': 1})

    def test_profiles_are_independent_and_caps_do_not_cap_evidence(self):
        self.conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)", (self.now,))
        self.check('other', pid='other', score=0)
        for index in range(8):
            self.check(str(index))
        self.assertEqual(self.skill()['observations'], 8)
        self.assertEqual(self.skill(pid='other')['rating'], 988)
        coins = self.conn.execute('SELECT SUM(amount) FROM progression_entries WHERE profile_id=?', (self.pid,)).fetchone()[0]
        self.assertEqual(coins, 12)

    def test_ungraded_and_malformed_evidence_does_not_create_ability(self):
        for activity in ('flashcards', 'lessons', 'journey', 'activity'):
            award(self.conn, self.pid, activity=activity, content_key='card', source_key=activity,
                  title='Practice', evidence={'score': 4, 'score_max': 4, 'rating': 'easy',
                    '_skill': {'policy_version': POLICY, 'task_rating': 1000, 'scores': {'translation': 1}}})
        task = self.sentence('bad')
        for index, score in enumerate((None, True, -1, 5, '4')):
            self.check('bad' + str(index), task=task, score=score)
        with self.assertRaises(ValueError):
            self.check('nan', score=float('nan'))
        self.assertEqual(self.state()['status'], 'not_calibrated')
        self.assertIsNone(self.skill()['rating'])

    def test_old_and_unrecognized_receipts_are_not_backfilled(self):
        task = self.check('first')
        self.conn.execute('UPDATE progression_events SET evidence_json=?', (json.dumps({'score': 4, 'score_max': 4}),))
        self.assertIsNone(self.skill()['rating'])
        self.conn.execute('UPDATE progression_events SET evidence_json=?', (json.dumps({'_skill': {'policy_version': 'future-v2', 'task_rating': 1000, 'scores': {'translation': 1}}}),))
        self.assertIsNone(self.skill()['rating'])
        self.check('future-first', task=task)
        self.assertEqual(self.skill()['observations'], 0)

    def test_speaking_requires_audio_evidence_and_keeps_dimensions_separate(self):
        self.speaking('assessed', grammar=5, fluency=None)
        self.assertEqual(self.skill('speaking_grammar')['rating'], 1012)
        self.assertIsNone(self.skill('speaking_fluency')['rating'])
        self.assertEqual(self.state()['active_skill'], 'speaking_grammar')
        self.speaking('both', grammar=3, fluency=1)
        self.assertEqual(self.skill('speaking_fluency')['rating'], 988)
        self.assertEqual(self.state()['active_skill'], 'speaking_fluency')
        before = self.state()
        self.speaking('english', status='no_russian')
        self.speaking('short', words='Мне чай пожалуйста')
        self.speaking('unscored', grammar=None, fluency=None)
        self.assertEqual(before, self.state())

    def test_real_translation_save_creates_one_receipt_and_retry_stays_practice(self):
        self.conn.commit()
        repository = TranslationRepository(self.db)
        task, _ = repository.save_content('Кот спит.', 'The cat sleeps.', 'home', 2)
        assessment = {'score': 4, 'strength': 'Clear meaning.', 'next_step': 'Try another.', 'example': 'Кот спит.'}
        repository.save_check(task, 'Кот спит.', 0, assessment, 'en')
        self.assertEqual(self.skill()['observations'], 1)
        first = self.skill()['rating']
        repository.save_check(task, 'Кот спит.', 1, assessment, 'en')
        self.assertEqual(self.skill()['rating'], first)

    def test_legacy_translation_score_excludes_first_modern_attempt_but_keeps_coins(self):
        old_task = self.sentence('previously checked')
        self.conn.execute('UPDATE sentences SET score=3 WHERE id=?', (old_task,))
        self.check('first-modern-check', task=old_task)
        self.assertIsNone(self.skill()['rating'])
        self.assertEqual(self.conn.execute('SELECT SUM(amount) FROM progression_entries').fetchone()[0], 3)
        self.check('new-task-with-zero-legacy-score')
        self.assertEqual((self.skill()['rating'], self.skill()['observations']), (1012, 1))

    def test_speaking_samples_same_variant_once_per_local_day_per_dimension(self):
        self.speaking('first', grammar=3, fluency=None, variant='table-for-two')
        self.speaking('retry', grammar=5, fluency=4, variant='table-for-two')
        self.assertEqual(self.skill('speaking_grammar')['observations'], 1)
        self.assertEqual(self.skill('speaking_grammar')['rating'], 1000)
        self.assertEqual(self.skill('speaking_fluency')['observations'], 1)
        self.now += 86400
        self.speaking('tomorrow', variant='table-for-two')
        self.assertEqual(self.skill('speaking_grammar')['observations'], 2)
        self.assertEqual(self.skill('speaking_fluency')['observations'], 2)

    def test_stage_rollover_keeps_exact_rating_visible(self):
        for index in range(12):
            self.check(str(index), difficulty=5)
        state = self.skill()
        self.assertEqual(state['stage'], 2)
        self.assertEqual((state['stage_start'], state['stage_end']), (1200, 1400))
        self.assertAlmostEqual(state['progress'], (state['rating'] - 1200) / 200)


class ReadingRatingProvenanceTests(unittest.TestCase):
    # The fixture exercises the actual reading routes using a fake assessor.
    from tests.test_story_titles import StoryTitlePersistenceTests as Fixture
    setUp = Fixture.setUp
    save = Fixture.save

    def rating(self):
        with sqlite3.connect(self.service.db_path) as conn:
            return next(item for item in snapshot(conn, 'personal-learning')['skills'] if item['id'] == 'reading')

    def test_fresh_check_of_saved_questions_counts_once(self):
        self.save()
        response = self.client.post('/comprehension/answer', data=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rating()['observations'], 1)
        self.client.post('/comprehension/answer', data=self.payload)
        self.assertEqual(self.rating()['observations'], 1)

    def test_cached_feedback_never_becomes_a_new_rating(self):
        self.save()
        self.service.evaluate_answers.return_value = (['Good'] * 5, None, 8.0, False)
        response = self.client.post('/comprehension/answer', data=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.rating()['rating'])

    def test_changed_questions_receive_feedback_without_rating_the_original_task(self):
        from tests.test_story_titles import encoded
        self.save()
        response = self.client.post('/comprehension/answer', data={**self.payload,
            'questions_b64': encoded(json.dumps(['Другой вопрос?'] * 5))})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.rating()['rating'])

    def test_existing_feedback_excludes_later_rewrites_even_with_fresh_grade(self):
        story_id = self.save()
        with sqlite3.connect(self.service.db_path) as conn:
            conn.execute('UPDATE saved_stories SET feedback=? WHERE id=?', (json.dumps(['Earlier feedback']), story_id))
        response = self.client.post('/comprehension/answer', data=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.rating()['rating'])


if __name__ == '__main__':
    unittest.main()
