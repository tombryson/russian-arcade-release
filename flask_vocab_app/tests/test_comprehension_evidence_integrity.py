"""Open reading responses retain frozen tasks, original answers and support."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

from contracts.curriculum import freeze_task_contract, validate_judgements
from migrations import upgrade_database
from repositories.comprehension_repository import ComprehensionRepository, ComprehensionConflict
from repositories.learning_repository import encoded
from services import activity_evidence as evidence
from services.account_import import build_account_import, digest, ImportConflict, inspect, transform
from services.comprehension_evidence import build_contracts
from services.curriculum_requirement_map import requirement_index
from tests.test_curriculum_task_contracts import spec_for


OWNER = 'personal-learning'
QUESTIONS = ['Где живёт Барсик?', 'Кто у него дома?', 'Что делает мама?',
             'Когда он читает?', 'А где живёте вы?']
TEXT = 'Барсик живёт дома. Дома его мама. Мама читает. Барсик читает вечером.'


def prepared(questions=None):
    return {'title': 'Барсик дома', 'title_en': 'Barsik at home', 'text': TEXT,
            'questions': list(questions or QUESTIONS), 'topic_id': 'home',
            'audio_url': '/static/audio/story.mp3', 'image_url': '/static/images/story.png',
            'reading_focus': [
                {'question_index': index, 'requirement_id': 'a1.reading.practical-information',
                 'passage_excerpt': excerpt, 'expectation': meaning}
                for index, (excerpt, meaning) in enumerate([
                    ('Барсик живёт дома.', 'Identify that Barsik lives at home.'),
                    ('Дома его мама.', 'Identify his mother as the person at home.'),
                    ('Мама читает.', 'Identify reading as the mother’s activity.'),
                    ('Барсик читает вечером.', 'Identify the evening as the time he reads.')])]}


def assessment_for(payload, answers):
    reports = {}
    for index, contract in payload['contracts'].items():
        answer = answers[int(index)]
        reports[index] = {'contract_sha256': contract['contract_sha256'], 'judgements': [
            {'criterion_id': 'reading-focus', 'outcome': 'satisfied', 'score': 2,
             'feedback': 'The answer conveys the relevant meaning.',
             'evidence': [{'quote': answer, 'start': 0, 'end': len(answer)}]}]}
    return {'feedback': ['Relevant answer.'] * len(answers), 'scores': [8] * len(answers),
            'total_score': 8, 'criterion_reports': reports}


class ComprehensionEvidenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'local.db'; upgrade_database(self.path, backup=False)
        self.repository = ComprehensionRepository(str(self.path))
        # These tests isolate diagnostic evidence; participation policy is tested
        # by the activity integration suite.
        reward = patch('repositories.comprehension_repository.legacy_profile', return_value=None)
        reward.start(); self.addCleanup(reward.stop)
        with self.connection() as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','O','UTC',1)")

    def connection(self, path=None):
        conn = sqlite3.connect(path or self.path)
        conn.execute('PRAGMA foreign_keys=ON')
        self.addCleanup(conn.close)
        return conn

    def issue(self, parent=None, questions=None):
        data = prepared(questions)
        options = {}
        if parent:
            task = self.repository.load(parent)
            issued = self.repository.begin_questions(parent, task['revision'])
            options = {'story_id': task['story_id'], 'parent_id': parent, 'lease_token': issued['check_token']}
        task_id, _ = self.repository.create(data, 'home', 'A1', build_contracts(data, 'home', 'A1'),
                                           expected_owner=OWNER, **options)
        return task_id

    def check(self, task_id, answers=None):
        task = self.repository.load(task_id)
        answers = answers or ['  Дома.  ', 'Его мама.', 'Она читает.', 'Вечером.', 'Я живу в городе.']
        submission = uuid.uuid4().hex
        issued, cached = self.repository.begin_check(task_id, task['revision'], submission, answers)
        self.assertIsNone(cached)
        return self.repository.finish_check(task_id, task['revision'], submission, answers,
                    assessment_for(issued['payload'], answers), expected_owner=OWNER, lease_token=issued['check_token'])

    def audit(self):
        with self.connection() as conn:
            before = conn.total_changes
            evidence.validate_saved_evidence(conn)
            self.assertEqual(conn.total_changes, before)

    def test_open_response_scope_keeps_source_selection_contract_unchanged(self):
        reference = deepcopy(requirement_index()['a1.reading.practical-information'])
        old = freeze_task_contract(spec_for('a1.reading.practical-information'))
        new = build_contracts(prepared(), 'home', 'A1')['0']
        self.assertEqual(new['criteria'][0]['response_mode'], 'reading_response')
        self.assertEqual(new['criteria'][0]['evidence_scope'], 'reading_comprehension')
        self.assertEqual(requirement_index()['a1.reading.practical-information'], reference)
        self.assertEqual(reference['response_mode'], 'reading_selection')
        self.assertEqual(old, freeze_task_contract(spec_for('a1.reading.practical-information')))
        for requirement, mode, scope in [
                ('a1.reading.practical-information', 'reading_response', 'reference'),
                ('a1.writing.personal-message', 'reading_response', 'reading_comprehension'),
                ('a1.reading.practical-information', 'independent_writing', 'reading_comprehension')]:
            with self.subTest(requirement=requirement, mode=mode, scope=scope), self.assertRaises(ValueError):
                freeze_task_contract(spec_for(requirement, mode, scope))
        spec = spec_for('a1.reading.practical-information', 'reading_response', 'reading_comprehension')
        spec['criteria'][0]['target_id'] = 'a1.reading.practical-information'
        with self.assertRaisesRegex(ValueError, 'distinct application target'):
            freeze_task_contract(spec)

    def test_four_criteria_are_frozen_before_answers_and_reflection_is_unmapped(self):
        task_id = self.issue()
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM comprehension_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_task_contracts').fetchone()[0], 4)
            contract = evidence.load_contract(conn, OWNER, 'comprehension', task_id + ':0')
            self.assertEqual(contract['content']['questions'], QUESTIONS)
            self.assertIsNone(evidence.load_contract(conn, OWNER, 'comprehension', task_id + ':4'))
            for key in (task_id + ':5', task_id + ':00', task_id + ':wrong'):
                with self.assertRaises(ValueError):
                    evidence.load_contract(conn, OWNER, 'comprehension', key)
            with self.assertRaises(LookupError):
                evidence.load_contract(conn, 'other', 'comprehension', task_id + ':0')
        self.audit()

    def test_saved_report_uses_exact_original_answer_and_saved_judgement(self):
        task_id = self.issue(); saved = self.check(task_id)
        report = saved['assessment']['criterion_reports']['0']; answer = saved['answers'][0]
        with self.connection() as conn:
            args = (conn, OWNER, 'comprehension', task_id + ':0', saved['id'], report)
            report_id = evidence.save_report(*args, response_text=answer)
            self.assertEqual(report_id, evidence.save_report(*args, response_text=answer))
            with self.assertRaises(ValueError):
                evidence.save_report(*args, response_text=answer.strip())
            changed = deepcopy(report); changed['judgements'][0]['feedback'] = 'New assessment.'
            with self.assertRaises(ValueError):
                evidence.save_report(*args[:-1], changed, response_text=answer)
            for source, question in [('missing', '0'), (saved['id'], '1'), (saved['id'], '4')]:
                with self.assertRaises(ValueError):
                    evidence.save_report(conn, OWNER, 'comprehension', task_id + ':' + question,
                                         source, report, response_text=answer)
            with self.assertRaises(LookupError):
                evidence.save_report(conn, 'other', 'comprehension', task_id + ':0', saved['id'], report, response_text=answer)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
        self.audit()

    def test_retries_do_not_create_new_attempts_or_change_the_saved_report(self):
        task_id = self.issue(); saved = self.check(task_id)
        task, retry = self.repository.begin_check(task_id, 0, saved['submission_id'], saved['answers'])
        self.assertEqual(retry['id'], saved['id'])
        again = self.repository.finish_check(task_id, 0, saved['submission_id'], saved['answers'],
                                            saved['assessment'], expected_owner=OWNER, lease_token=None)
        self.assertEqual(again['id'], saved['id'])
        _, unchanged = self.repository.begin_check(task_id, 1, uuid.uuid4().hex, saved['answers'])
        self.assertEqual(unchanged['id'], saved['id'])
        with self.assertRaises(ComprehensionConflict):
            self.repository.begin_check(task_id, 0, uuid.uuid4().hex, ['Другой ответ.'] * 5)
        with self.assertRaises(ComprehensionConflict):
            self.repository.begin_check(task_id, 0, saved['submission_id'], ['Другой ответ.'] * 5)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM comprehension_attempts').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 4)
        self.audit()

    def test_expired_worker_cannot_clear_or_commit_a_reclaimed_submission(self):
        task_id = self.issue(); answers = ['Дома.'] * 5; submission = uuid.uuid4().hex
        with patch('repositories.comprehension_repository.timestamp', return_value=2_000_000_000):
            first, _ = self.repository.begin_check(task_id, 0, submission, answers)
        with patch('repositories.comprehension_repository.timestamp', return_value=2_000_000_181):
            replacement, _ = self.repository.begin_check(task_id, 0, submission, answers)
            self.assertNotEqual(first['check_token'], replacement['check_token'])
            self.repository.abandon_check(task_id, submission, first['check_token'])
            with self.connection() as conn:
                self.assertEqual(conn.execute('SELECT checking_token FROM comprehension_tasks WHERE id=?',
                                              (task_id,)).fetchone()[0], replacement['check_token'])
            assessment = assessment_for(replacement['payload'], answers)
            with self.assertRaises(ComprehensionConflict):
                self.repository.finish_check(task_id, 0, submission, answers, assessment,
                                             expected_owner=OWNER, lease_token=first['check_token'])
            self.repository.finish_check(task_id, 0, submission, answers, assessment,
                                         expected_owner=OWNER, lease_token=replacement['check_token'])
        self.audit()

    def test_later_attempt_and_reissued_question_set_retain_feedback_exposure(self):
        task_id = self.issue(); first = self.check(task_id)
        later = self.check(task_id, ['Он дома.', 'Мама.', 'Читает.', 'Вечером.', 'В Москве.'])
        self.assertEqual(first['support'], [])
        self.assertEqual(later['support'], ['model_answer'])
        questions = QUESTIONS + ['Кто читает вечером?']
        next_id = self.issue(parent=task_id, questions=questions)
        inherited = self.check(next_id, ['Дома.', 'Мама.', 'Читает.', 'Вечером.', 'В Москве.', 'Барсик.'])
        self.assertEqual(inherited['support'], ['model_answer'])
        with self.connection() as conn:
            report = later['assessment']['criterion_reports']['0']
            with self.assertRaises(ValueError):
                evidence.save_report(conn, OWNER, 'comprehension', task_id + ':0', later['id'],
                                     report, response_text=later['answers'][0], support=[])
            # The library projects the new questions; the earlier contract keeps
            # its original question set and original exact evidence.
            old = evidence.load_contract(conn, OWNER, 'comprehension', task_id + ':0')
            self.assertEqual(old['content']['questions'], QUESTIONS)
        self.audit()

    def test_criteria_cannot_be_added_after_an_assessed_response(self):
        task_id = self.issue(); saved = self.check(task_id)
        with self.connection() as conn:
            contract = evidence.load_contract(conn, OWNER, 'comprehension', task_id + ':0')
            conn.execute("DELETE FROM activity_criterion_reports WHERE contract_id IN (SELECT id FROM activity_task_contracts WHERE task_key=?)", (task_id + ':0',))
            conn.execute('DELETE FROM activity_task_contracts WHERE task_key=?', (task_id + ':0',))
            with self.assertRaisesRegex(ValueError, 'before the first'):
                evidence.save_contract(conn, OWNER, 'comprehension', task_id + ':0', contract)

    def test_unanswered_task_still_requires_owned_frozen_criteria(self):
        task_id = self.issue()
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM comprehension_attempts').fetchone()[0], 0)
            conn.execute('DELETE FROM activity_task_contracts WHERE task_key=?', (task_id + ':0',))
            with self.assertRaisesRegex(ValueError, 'missing its original frozen contract'):
                evidence.validate_saved_evidence(conn)

    def test_readonly_migration_audit_detects_corrupt_response_digest(self):
        task_id = self.issue(); self.check(task_id)
        script = Path(__file__).resolve().parents[2] / 'scripts' / 'audit_course_migration.py'
        spec = importlib.util.spec_from_file_location('comprehension_migration_audit', script)
        audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
        with self.connection() as conn:
            before = conn.total_changes
            self.assertEqual(audit.inventory(conn)['invalid_comprehension_evidence'], 0)
            self.assertEqual(conn.total_changes, before)
            conn.execute("UPDATE activity_criterion_reports SET response_sha256=?", ('0' * 64,))
            self.assertEqual(audit.inventory(conn)['invalid_comprehension_evidence'], 1)

    def test_original_answer_spans_are_required_without_deterministic_scoring(self):
        task_id = self.issue(); task = self.repository.load(task_id)
        answers = ['Дома.'] * 5
        assessment = assessment_for(task['payload'], answers)
        report = assessment['criterion_reports']['0']
        report['judgements'][0].update(outcome='partial', score=1)
        # Reading judgements can be partial even when aggregate practice scores
        # differ; the adapter binds the saved assessor result, not an answer key.
        validate_judgements(task['payload']['contracts']['0'], report, response_text=answers[0])
        bad = deepcopy(report); bad['judgements'][0]['evidence'][0]['quote'] = 'На улице.'
        with self.assertRaises(ValueError):
            validate_judgements(task['payload']['contracts']['0'], bad, response_text=answers[0])
        sid = uuid.uuid4().hex
        issued, _ = self.repository.begin_check(task_id, 0, sid, answers)
        self.repository.finish_check(task_id, 0, sid, answers, assessment,
                                     expected_owner=OWNER, lease_token=issued['check_token'])
        self.audit()

    def test_import_preserves_frozen_bytes_and_ids_and_clears_only_provider_lease(self):
        task_id = self.issue(); self.check(task_id)
        task = self.repository.load(task_id)
        self.repository.begin_check(task_id, 1, uuid.uuid4().hex, ['Новый ответ.'] * 5)
        hosted = self.directory / 'hosted.db'; upgrade_database(hosted, backup=False)
        output = self.directory / 'imported.db'
        before = (digest(self.path), digest(hosted))
        with self.connection() as conn:
            original_tasks = conn.execute('SELECT id,story_id,profile_id,payload_json,revision,created_at FROM comprehension_tasks').fetchall()
            frozen = {name: conn.execute('SELECT * FROM ' + name).fetchall()
                      for name in ('comprehension_attempts', 'activity_task_contracts', 'activity_criterion_reports')}
        build_account_import(self.path, hosted, output)
        self.assertEqual(before, (digest(self.path), digest(hosted)))
        with self.connection(output) as conn:
            self.assertEqual(conn.execute('SELECT id,story_id,profile_id,payload_json,revision,created_at FROM comprehension_tasks').fetchall(), original_tasks)
            self.assertEqual(conn.execute('SELECT checking_submission_id,checking_sha256,checking_started_at,checking_token FROM comprehension_tasks').fetchone(), (None, None, None, None))
            for name, rows in frozen.items():
                self.assertEqual(conn.execute('SELECT * FROM ' + name).fetchall(), rows)
            evidence.validate_saved_evidence(conn)
        with self.connection() as conn:
            self.assertIsNotNone(conn.execute('SELECT checking_submission_id FROM comprehension_tasks').fetchone()[0])

    def test_import_remaps_only_story_foreign_key_and_preserves_frozen_json(self):
        self.issue()
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            schemas = inspect(conn)
        table = schemas['comprehension_tasks']; row = table['rows'][0]
        maps = {'saved_stories': {row['story_id']: 99}}
        mapped = transform('comprehension_tasks', table, row, maps, schemas)
        self.assertEqual(mapped['story_id'], 99)
        self.assertEqual(mapped['id'], row['id'])
        self.assertEqual(mapped['payload_json'], row['payload_json'])
        broken = dict(row); payload = json.loads(row['payload_json']); payload['story_id'] = row['story_id']
        broken['payload_json'] = encoded(payload)
        with self.assertRaisesRegex(ImportConflict, 'Frozen activity evidence'):
            transform('comprehension_tasks', table, broken, maps, schemas)

    def test_import_rejects_tampering_even_when_no_criterion_row_references_it(self):
        task_id = self.issue(); self.check(task_id)
        hosted = self.directory / 'hosted.db'; upgrade_database(hosted, backup=False)
        mutations = {
            'wrong-story-owner': "UPDATE saved_stories SET owner_profile_id='other'",
            'changed-passage': "UPDATE saved_stories SET text='Другой текст.'",
            'changed-question': "UPDATE comprehension_tasks SET payload_json=json_set(payload_json,'$.questions[0]','Другой вопрос?')",
            'removed-contracts': "UPDATE comprehension_tasks SET payload_json=json_set(payload_json,'$.contracts',json('{}'))",
            'revision': 'UPDATE comprehension_tasks SET revision=2',
            'invented-exposure': "UPDATE comprehension_tasks SET payload_json=json_set(payload_json,'$.prior_feedback',json('true'))",
            'reflection-answer': "UPDATE comprehension_attempts SET answers_json=json_set(answers_json,'$[4]','Changed reflection')",
            'aggregate-score': "UPDATE comprehension_attempts SET assessment_json=json_set(assessment_json,'$.total_score',10)",
            'support': "UPDATE comprehension_attempts SET support_json='[\"model_answer\"]'",
            'request-digest': "UPDATE comprehension_attempts SET request_sha256='" + '0' * 64 + "'",
            'submission-id': "UPDATE comprehension_attempts SET submission_id='unbound'",
            'pre-task-answer': 'UPDATE comprehension_attempts SET created_at=0',
            'missing-report': 'DELETE FROM activity_criterion_reports WHERE rowid=(SELECT MIN(rowid) FROM activity_criterion_reports)',
            'late-contract': 'UPDATE activity_task_contracts SET created_at=created_at+1000',
        }
        baseline = (digest(self.path), digest(hosted))
        for label, sql in mutations.items():
            with self.subTest(tamper=label):
                corrupt = self.directory / (label + '.db'); output = self.directory / (label + '-output.db')
                with self.connection() as source, self.connection(corrupt) as target:
                    source.backup(target)
                    target.execute(sql)
                with self.assertRaises(ImportConflict):
                    build_account_import(corrupt, hosted, output)
                self.assertFalse(output.exists())
        self.assertEqual(baseline, (digest(self.path), digest(hosted)))

    def test_legacy_stories_do_not_acquire_contracts_or_attempts_during_import(self):
        with self.connection() as conn:
            conn.execute("INSERT INTO saved_stories(title,topic,difficulty,text,questions,answers,feedback,score,owner_profile_id) VALUES ('Старый рассказ','home','A1','Старый текст.','[\"Вопрос?\"]','[\"Ответ.\"]','[\"Хорошо.\"]',8,?)", (OWNER,))
            old = conn.execute('SELECT * FROM saved_stories').fetchall()
        hosted = self.directory / 'hosted.db'; upgrade_database(hosted, backup=False)
        output = self.directory / 'legacy-import.db'
        build_account_import(self.path, hosted, output)
        with self.connection(output) as conn:
            self.assertEqual(conn.execute('SELECT * FROM saved_stories').fetchall(), old)
            for table in ('comprehension_tasks', 'comprehension_attempts', 'activity_task_contracts', 'activity_criterion_reports'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
