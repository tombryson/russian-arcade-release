"""Saved reading checks continue ordinary practice progress, never level passes."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch

from migrations import upgrade_database
from repositories.comprehension_repository import ComprehensionRepository
from repositories.learning_repository import payload_hash, timestamp
from services.comprehension_evidence import build_contracts, reissue_contracts
from services.course_evidence import comprehension_assessment, freeze_course_evidence
from services.progression import award, personal_profile
from services.skill_progress import freeze_evidence, snapshot
from tests.test_comprehension_evidence_content import ANSWERS, assessment, prepared_story


class ComprehensionProgressionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.db = str(Path(temporary.name) / 'reading.db')
        upgrade_database(self.db, backup=False)
        self.conn = sqlite3.connect(self.db); self.addCleanup(self.conn.close)
        self.pid = personal_profile(self.conn); self.conn.commit()
        self.repo = ComprehensionRepository(self.db)

    def create(self, topic='family', requested=None):
        prepared = prepared_story(topic=topic)
        requested = requested or topic
        return self.repo.create(prepared, requested, 'A1', build_contracts(prepared, requested, 'A1'), expected_owner=self.pid)

    def check(self, task_id, score=8, answers=None):
        task = self.repo.load(task_id); answers = deepcopy(answers or ANSWERS)
        revision, submission = task['revision'], uuid4().hex
        lease, _ = self.repo.begin_check(task_id, revision, submission, answers)
        result = assessment(task['payload'], answers)
        result.update(scores=[score] * len(answers), total_score=score)
        if task['payload'].get('practice_mode') == 'listening' and task['payload'].get('audio') is None:
            for report in result['criterion_reports'].values():
                for judgement in report['judgements']:
                    judgement.update(outcome='insufficient_evidence', score=None, evidence=[])
        return self.repo.finish_check(task_id, revision, submission, answers, result, expected_owner=self.pid, lease_token=lease['check_token'])

    def receipt(self, attempt_id):
        row = self.conn.execute('SELECT evidence_json FROM progression_events WHERE source_key=?',
                                ('comprehension-check:' + attempt_id,)).fetchone()
        return json.loads(row[0])

    def skill(self, key='reading'):
        return next(item for item in snapshot(self.conn, self.pid)['skills'] if item['id'] == key)

    def test_new_checked_story_records_existing_preparation_and_reading_elo_inside_save(self):
        task_id, story_id = self.create()
        result = self.check(task_id)
        saved = self.receipt(result['id'])
        self.assertEqual(saved['_course']['topic_id'], 'family')
        self.assertEqual(saved['_course']['score'], .8)
        self.assertFalse(saved['_course']['assisted'])
        self.assertEqual(saved['_skill']['scores'], {'reading': .8})
        self.assertEqual(saved['course_task_questions_hash'], payload_hash(self.repo.load(task_id)['payload']['questions']))
        self.assertEqual(saved['answered_questions'], 5)
        self.assertTrue(saved['first_fresh_assessment'])
        self.assertEqual(self.skill()['observations'], 1)
        self.assertEqual(self.conn.execute('SELECT content_key FROM course_evidence').fetchone()[0], f'story:{story_id}')
        for table in ('course_target_observations', 'course_chapter_passes', 'course_continuation_entitlements'):
            self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)

    def test_event_claims_do_not_override_saved_score_support_or_question_identity(self):
        task_id, story_id = self.create(); result = self.check(task_id, score=0)
        claims = {'score': 10, 'score_max': 10, 'answered_questions': 100, 'assisted': True,
                  'first_fresh_assessment': False, 'course_task_context_matches': False,
                  'course_task_questions_hash': 'forged', '_course_targets': ['forged']}
        source = 'comprehension-check:' + result['id']; key = f'story:{story_id}'
        course = freeze_course_evidence(self.conn, self.pid, 'reading', key, source, claims)
        skill = freeze_evidence(self.conn, 'reading', key, source, None, claims, profile_id=self.pid)
        self.assertEqual(course['_course']['score'], 0)
        self.assertFalse(course['_course']['assisted'])
        self.assertTrue(skill['first_fresh_assessment'])
        self.assertEqual(skill['_skill']['scores'], {'reading': 0})
        self.assertEqual(skill['answered_questions'], 5)
        self.assertNotEqual(skill['course_task_questions_hash'], 'forged')
        self.assertNotIn('_course_targets', course)

    def test_wrong_owner_story_and_unpersisted_attempt_cannot_count(self):
        task_id, story_id = self.create(); result = self.check(task_id)
        _, other_story = self.create(); source = 'comprehension-check:' + result['id']
        cases = [('other', f'story:{story_id}', source), (self.pid, f'story:{other_story}', source),
                 (self.pid, f'story:{story_id}', 'comprehension-check:' + uuid4().hex),
                 (self.pid, f'story:0{story_id}', source)]
        for owner, key, candidate in cases:
            with self.subTest(owner=owner, key=key, candidate=candidate):
                self.assertIsNone(comprehension_assessment(self.conn, owner, key, candidate))
                self.assertNotIn('_course', freeze_course_evidence(self.conn, owner, 'reading', key, candidate, {'score': 10}))
                self.assertNotIn('_skill', freeze_evidence(self.conn, 'reading', key, candidate, None,
                                                         {'score': 10, 'score_max': 10, 'first_fresh_assessment': True,
                                                          'answered_questions': 5}, profile_id=owner))

    def test_tampered_saved_score_task_support_and_answer_digest_are_rejected(self):
        task_id, story_id = self.create(); result = self.check(task_id)
        source = 'comprehension-check:' + result['id']; key = f'story:{story_id}'
        task = self.repo.load(task_id); payload = deepcopy(task['payload'])
        changed_score = deepcopy(result['assessment']); changed_score['total_score'] = 10
        changed_text = deepcopy(payload); changed_text['text'] = 'Changed passage.'
        changed_questions = deepcopy(payload); changed_questions['questions'][0] = 'Changed question?'
        changes = [
            ('UPDATE comprehension_attempts SET assessment_json=? WHERE id=?', json.dumps(changed_score), result['id']),
            ('UPDATE comprehension_attempts SET support_json=? WHERE id=?', '["model_answer"]', result['id']),
            ('UPDATE comprehension_attempts SET request_sha256=? WHERE id=?', 'a' * 64, result['id']),
            ('UPDATE comprehension_tasks SET payload_json=? WHERE id=?', json.dumps(changed_text), task_id),
            ('UPDATE comprehension_tasks SET payload_json=? WHERE id=?', json.dumps(changed_questions), task_id),
        ]
        for statement, value, identity in changes:
            with self.subTest(statement=statement):
                self.conn.execute('SAVEPOINT tamper')
                self.conn.execute(statement, (value, identity))
                self.assertIsNone(comprehension_assessment(self.conn, self.pid, key, source))
                self.conn.execute('ROLLBACK TO tamper'); self.conn.execute('RELEASE tamper')

    def test_correction_counts_preparation_but_cannot_repeat_elo_and_other_activities_still_count(self):
        task_id, story_id = self.create(); self.check(task_id, score=0)
        corrected_answers = deepcopy(ANSWERS); corrected_answers[0] = 'Она сейчас на почте.'
        corrected = self.check(task_id, score=9, answers=corrected_answers)
        saved = self.receipt(corrected['id'])
        self.assertEqual(saved['_course']['score'], .9)
        self.assertTrue(saved['_course']['assisted'])
        self.assertNotIn('_skill', saved)
        self.assertFalse(saved['first_fresh_assessment'])
        self.assertEqual(self.skill()['observations'], 1)
        second, _ = self.create(); self.check(second, score=9)
        self.assertEqual(self.skill()['observations'], 2)
        now = timestamp()
        sentence = self.conn.execute("INSERT INTO sentences(sentence,english,topic,difficulty,owner_profile_id) VALUES ('Мама дома.','Mum is home.','family',1,?)", (self.pid,)).lastrowid
        attempt = self.conn.execute('''INSERT INTO translation_attempts
            (sentence_id,response,score,strength,next_step,example,ui_language,created_at,coins_earned,elo_change,already_rewarded)
            VALUES (?,'Мама дома.',4,'Clear.','Continue.','Мама дома.','en',?,0,0,0)''', (sentence, str(now))).lastrowid
        award(self.conn, self.pid, activity='translation', content_key=f'translation:{sentence}',
              source_key=f'translation-attempt:{attempt}', title='Translation', now=now, evidence={'score': 4, 'score_max': 4})
        self.assertEqual(self.skill('translation')['observations'], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(DISTINCT content_key) FROM course_evidence').fetchone()[0], 3)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)

    def test_added_questions_after_feedback_keep_preparation_but_no_new_independent_rating(self):
        task_id, story_id = self.create(); self.check(task_id)
        task = self.repo.load(task_id); questions = task['payload']['questions'] + ['Как зовут девушку?']
        prepared = prepared_story(topic='family'); prepared['questions'] = questions
        lease = self.repo.begin_questions(task_id, task['revision'])
        new_id, _ = self.repo.create(prepared, 'family', 'A1', reissue_contracts(task['payload'], questions),
                                     expected_owner=self.pid, story_id=story_id, parent_id=task_id, lease_token=lease['check_token'])
        saved = self.receipt(self.check(new_id, answers=ANSWERS + ['Нина.'])['id'])
        self.assertTrue(saved['_course']['assisted'])
        self.assertNotIn('_skill', saved)
        self.assertEqual(self.skill()['observations'], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(DISTINCT content_key) FROM course_evidence').fetchone()[0], 1)

    def test_any_uses_the_actual_frozen_topic_and_coin_limits_do_not_stop_preparation(self):
        for _ in range(6):
            task_id, _ = self.create(topic='family', requested='any')
            saved = self.receipt(self.check(task_id)['id'])
            self.assertEqual(saved['_course']['topic_id'], 'family')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_evidence').fetchone()[0], 6)
        self.assertEqual(self.conn.execute('SELECT SUM(amount) FROM progression_entries WHERE category="activity"').fetchone()[0], 12)
        self.assertEqual(self.skill()['observations'], 6)

    def create_listening(self, *, audio=True):
        prepared = prepared_story(topic='family')
        prepared['listening_focus'] = prepared.pop('reading_focus')
        for focus in prepared['listening_focus']:
            focus['requirement_id'] = 'a1.listening.short-message'
        recording = {'url': '/static/media/projection-fixture.mp3', 'sha256': 'a' * 64, 'size_bytes': 10} if audio else None
        prepared['audio_url'] = recording['url'] if recording else ''
        contracts = build_contracts(prepared, 'family', 'A1', practice_mode='listening', audio=recording, track_support=True)
        return self.repo.create(prepared, 'family', 'A1', contracts, expected_owner=self.pid,
                                practice_mode='listening', audio=recording, track_support=True)

    def test_audio_first_check_rates_listening_only_and_replays_without_reading_credit(self):
        task_id, _ = self.create_listening()
        # Byte validation has its own route/storage tests. This test examines
        # the receipt's scoring projection without a provider or media writes.
        with patch('repositories.comprehension_repository.verify_audio', return_value=Path('/fixture.mp3')):
            self.repo.record_support(task_id, 0, uuid4().hex, 'listened')
            result = self.check(task_id)
        saved = self.receipt(result['id'])
        self.assertEqual(saved['_skill']['scores'], {'listening': .8})
        self.assertEqual(saved['_skill']['comprehension_mode'], 'listening')
        self.assertEqual(saved['comprehension_mode'], 'listening')
        self.assertTrue(saved['listened'])
        self.assertFalse(saved['_course']['assisted'])
        self.assertEqual(self.skill('listening')['observations'], 1)
        self.assertEqual(self.skill('reading')['observations'], 0)
        self.assertEqual(self.skill('listening')['observations'], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)

    def test_listening_transcript_and_missing_audio_keep_participation_without_rating(self):
        for audio in (True, False):
            with self.subTest(audio=audio):
                task_id, _ = self.create_listening(audio=audio)
                self.repo.record_support(task_id, 0, uuid4().hex, 'transcript')
                result = self.check(task_id)
                saved = self.receipt(result['id'])
                self.assertTrue(saved['_course']['assisted'])
                self.assertNotIn('_skill', saved)
                self.assertFalse(saved['first_fresh_assessment'])
        self.assertEqual(self.skill('listening')['observations'], 0)
        self.assertEqual(self.skill('reading')['observations'], 0)
        self.assertEqual(self.conn.execute('SELECT SUM(amount) FROM progression_entries').fetchone()[0], 6)

    def test_missing_or_forged_playback_receipt_cannot_become_reading_or_listening_rating(self):
        task_id, story_id = self.create_listening()
        with patch('repositories.comprehension_repository.verify_audio', return_value=Path('/fixture.mp3')):
            self.repo.record_support(task_id, 0, uuid4().hex, 'listened')
            result = self.check(task_id)
        source, key = 'comprehension-check:' + result['id'], f'story:{story_id}'
        self.conn.execute('SAVEPOINT no_receipt')
        self.conn.execute("UPDATE comprehension_attempts SET support_receipts_json='[]' WHERE id=?", (result['id'],))
        self.assertIsNone(comprehension_assessment(self.conn, self.pid, key, source))
        self.assertNotIn('_skill', freeze_evidence(self.conn, 'reading', key, source, None,
            {'listened': True, 'comprehension_mode': 'reading', 'score': 10, 'first_fresh_assessment': True}, profile_id=self.pid))
        self.conn.execute('ROLLBACK TO no_receipt'); self.conn.execute('RELEASE no_receipt')
        self.conn.execute('SAVEPOINT wrong_audio')
        self.conn.execute('UPDATE comprehension_support_receipts SET detail_json=? WHERE task_id=?',
                          (json.dumps({'audio_sha256': 'b' * 64}), task_id))
        self.assertIsNone(comprehension_assessment(self.conn, self.pid, key, source))
        self.conn.execute('ROLLBACK TO wrong_audio'); self.conn.execute('RELEASE wrong_audio')

    def test_reading_word_support_counts_preparation_without_independent_reading_rating(self):
        prepared = prepared_story(topic='family')
        task_id, _ = self.repo.create(prepared, 'family', 'A1',
            build_contracts(prepared, 'family', 'A1', track_support=True), expected_owner=self.pid,
            practice_mode='reading', track_support=True)
        self.repo.record_support(task_id, 0, uuid4().hex, 'translation', word='Нина')
        result = self.check(task_id)
        saved = self.receipt(result['id'])
        self.assertTrue(saved['_course']['assisted'])
        self.assertNotIn('_skill', saved)
        self.assertEqual(self.skill('reading')['observations'], 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_evidence').fetchone()[0], 1)
