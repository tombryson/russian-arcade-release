"""Rehearse schema045 on populated schema044 and compare all saved columns."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import migrations
from repositories.learning_repository import LearningError, encoded, payload_hash
from services import course_progression as course


class CourseReleaseMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='course-release-migration-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.migration_dir = root / 'migrations'
        self.migration_dir.mkdir()
        for file in migrations.MIGRATION_DIR.glob('*.sql'):
            if int(file.name.split('_')[0]) <= 44:
                shutil.copy(file, self.migration_dir / file.name)
        self.db = str(root / 'fixture.db')
        with patch.object(migrations, 'MIGRATION_DIR', self.migration_dir):
            self.assertEqual(migrations.upgrade_database(self.db, backup=False), (44, None))
        migrations.seed_demo(self.db)
        # Use the shipped IDs, questions and media, never synthetic chapter IDs.
        self.catalogue = json.loads(course.DATA_FILE.read_text())
        with sqlite3.connect(self.db) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            for profile in ('active', 'retry', 'partial', 'complete', 'finishing'):
                conn.execute('INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES (?,?,\'cat\',\'UTC\',1)', (profile, profile))
            self.old_attempt(conn, 'active', 1, 'active')
            self.old_attempt(conn, 'retry', 1, 'retry', support=['transcript'])
            self.old_attempt(conn, 'partial', 1, 'passed')
            for chapter in range(1, 5):
                self.old_attempt(conn, 'complete', chapter, 'passed')
                self.old_attempt(conn, 'finishing', chapter, 'active' if chapter == 4 else 'passed')
            metadata = encoded({'_course': {'topic_id': 'greetings', 'level': 'A1', 'score': 1, 'assisted': False}})
            conn.execute("INSERT INTO progression_events VALUES ('practice','active','reading','practice-request','saved-story','Practice','activity','A1',?,120,NULL)", (metadata,))
            conn.execute("INSERT INTO course_evidence VALUES ('practice','active','greetings','reading','saved-story','A1',1,'a1-course-practice-v1',120)")
            conn.execute('UPDATE users SET lingocoins=87,elo_rating=1400 WHERE user_id=1')
            self.tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
            self.columns = {table: [row[1] for row in conn.execute('PRAGMA table_info("' + table + '")')] for table in self.tables}
            self.before = {table: sorted(conn.execute('SELECT * FROM "' + table + '"').fetchall(), key=repr) for table in self.tables}

    def old_attempt(self, conn, profile, number, status, support=None):
        chapter = self.catalogue['chapters'][number - 1]
        attempt_id = f'{profile}-{number}'
        variant = chapter['variants'][0]
        frozen = {'chapter_id': chapter['id'], 'chapter_number': number, 'title': chapter['title'],
                  'title_ru': chapter['title_ru'], 'variant': variant, 'rubric': deepcopy(course.RUBRIC)}
        answers = {question['id']: question['answer'] for question in variant['questions']}
        result = {'score': len(answers), 'total': len(answers), 'passed': status == 'passed', 'essential_passed': True,
                  'feedback': [{'question_id': question['id'], 'correct': True, 'answer': question['answer'],
                                'explanation': question['explanation'], 'explanation_ru': question['explanation_ru']}
                               for question in variant['questions']]}
        # Deliberate whitespace proves migration never reserializes saved JSON.
        conn.execute('INSERT INTO course_checkpoint_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (attempt_id, profile, chapter['id'], number, variant['id'], 1, 'a1-checkpoint-v1',
                      json.dumps(frozen, ensure_ascii=False, indent=1), status, json.dumps(support or []),
                      None if status == 'active' else 100 + number,
                      None if status == 'active' else json.dumps(answers),
                      None if status == 'active' else json.dumps(result), 100 + number,
                      None if status == 'active' else 200 + number))
        response = {'id': attempt_id, 'chapter_id': chapter['id'], 'letter': variant['letter'],
                    'status': status, 'course': {'band': 'A1', 'unlocked_levels': ['A1']}}
        if status != 'active':
            response['result'] = result
            conn.execute('INSERT INTO course_checkpoint_submissions VALUES (?,?,?,?,?)',
                         (profile, 'submission-' + str(number), payload_hash({'attempt_id': attempt_id, 'answers': answers}),
                          attempt_id, json.dumps(response, ensure_ascii=False, indent=2)))
        conn.execute('INSERT INTO course_checkpoint_requests VALUES (?,?,?,?,?)',
                     (profile, 'start-' + str(number), payload_hash({'chapter_id': chapter['id'], 'challenge': True}),
                      attempt_id, json.dumps(response, ensure_ascii=False, indent=2)))
        if status == 'passed':
            conn.execute('INSERT INTO course_chapter_passes VALUES (?,?,?,?)', (profile, chapter['id'], attempt_id, 200 + number))

    def upgrade(self):
        filename = '045_course_releases.sql'
        shutil.copy(migrations.MIGRATION_DIR / filename, self.migration_dir / filename)
        with patch.object(migrations, 'MIGRATION_DIR', self.migration_dir):
            self.assertEqual(migrations.upgrade_database(self.db, backup=False), (45, None))

    def test_upgrade_preserves_every_existing_column_and_pins_all_profiles(self):
        self.upgrade()
        self.upgrade()
        with sqlite3.connect(self.db) as conn:
            for table in self.tables:
                selection = ','.join('"' + column + '"' for column in self.columns[table])
                with self.subTest(table=table):
                    self.assertEqual(sorted(conn.execute('SELECT ' + selection + ' FROM "' + table + '"').fetchall(), key=repr), self.before[table])
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone(), ('ok',))
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(conn.execute('SELECT DISTINCT release_id,band FROM course_checkpoint_attempts').fetchall(), [('a1-v1', 'A1')])
            self.assertEqual(conn.execute('SELECT DISTINCT release_id,requirement_version FROM course_chapter_passes').fetchall(), [('a1-v1', 'a1-checkpoint-v1')])
            self.assertEqual(conn.execute('SELECT DISTINCT release_id,band,migration_source FROM course_enrolments').fetchall(), [('a1-v1', 'A1', 'schema-044')])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_enrolments').fetchone(), conn.execute('SELECT COUNT(*) FROM learning_profiles').fetchone())
            self.assertEqual(conn.execute('SELECT profile_id,target_level,source_release_id,source,earned_at FROM course_continuation_entitlements').fetchall(),
                             [('complete', 'A2', 'a1-v1', 'legacy-course-completion', 204)])
            for profile, passed in [('personal-learning', 0), ('active', 0), ('retry', 0), ('partial', 1), ('complete', 4), ('finishing', 3)]:
                state = course.course_snapshot(conn, profile)
                self.assertEqual(state['completed_milestones'], passed)
                self.assertEqual(state['unlocked_levels'], ['A1', 'A2'] if profile == 'complete' else ['A1'])

    def test_legacy_receipts_replay_exactly_and_changed_or_foreign_commands_fail(self):
        self.upgrade()
        with sqlite3.connect(self.db) as conn:
            for profile, request_id, fingerprint, attempt_id, response in self.before['course_checkpoint_requests']:
                self.assertEqual(course.checkpoint_start(conn, profile, json.loads(response)['chapter_id'], request_id, True), json.loads(response))
            for profile, submission_id, fingerprint, attempt_id, response in self.before['course_checkpoint_submissions']:
                frozen = json.loads(conn.execute('SELECT frozen_json FROM course_checkpoint_attempts WHERE id=?', (attempt_id,)).fetchone()[0])
                answers = {item['id']: item['answer'] for item in frozen['variant']['questions']}
                self.assertEqual(course.checkpoint_answer(conn, profile, attempt_id, answers, submission_id), json.loads(response))
                with self.assertRaises(LearningError) as caught:
                    course.checkpoint_answer(conn, profile, attempt_id, answers | {'r1': 'b'}, submission_id)
                self.assertEqual(caught.exception.status, 409)
            for operation in (
                lambda: course.checkpoint_start(conn, 'active', 'a1-post-office', 'start-1', False),
                lambda: course.checkpoint_start(conn, 'active', 'a1-post-office', 'start-1', True, release_id='a1-v1'),
                lambda: course.checkpoint_read(conn, 'partial', 'active-1'),
                lambda: course.checkpoint_support(conn, 'partial', 'active-1', 'transcript'),
                lambda: course.checkpoint_listened(conn, 'partial', 'active-1'),
                lambda: course.checkpoint_answer(conn, 'partial', 'active-1', {'q1': 'a'}, 'foreign'),
            ):
                with self.subTest(operation=operation), self.assertRaises(LearningError) as caught:
                    operation()
                self.assertIn(caught.exception.status, (404, 409))
            new = course.checkpoint_start(conn, 'partial', 'a1-home', 'resume-shared', True)
            other = course.checkpoint_start(conn, 'active', 'a1-post-office', 'resume-shared', True)
            self.assertEqual(new['release_id'], 'a1-v1')
            self.assertNotEqual(new['id'], other['id'])

    def test_saved_active_letter_finishes_under_frozen_rubric_and_earns_a2(self):
        self.upgrade()
        with sqlite3.connect(self.db) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            original = conn.execute("SELECT frozen_json FROM course_checkpoint_attempts WHERE id='finishing-4'").fetchone()[0]
            resumed = course.checkpoint_start(conn, 'finishing', 'a1-delivery', 'resume', True)
            self.assertEqual(resumed['id'], 'finishing-4')
            self.assertEqual(resumed['release_id'], 'a1-v1')
            self.assertEqual(resumed['listening']['audio_url'], '/static/audio/course/a1-delivery-v1.mp3')
            course.checkpoint_listened(conn, 'finishing', 'finishing-4')
            frozen = json.loads(original)
            answers = {item['id']: item['answer'] for item in frozen['variant']['questions']}
            answers['r2'] = 'a'
            with patch.dict(course.RUBRIC, {'minimum_score': 1}):
                passed = course.checkpoint_answer(conn, 'finishing', 'finishing-4', answers, 'after-migration')
            self.assertTrue(passed['result']['passed'])
            self.assertEqual(passed['course']['completed_milestones'], 4)
            self.assertEqual(passed['course']['unlocked_levels'], ['A1', 'A2'])
            self.assertEqual(conn.execute("SELECT frozen_json FROM course_checkpoint_attempts WHERE id='finishing-4'").fetchone()[0], original)
            self.assertEqual(course.checkpoint_answer(conn, 'finishing', 'finishing-4', answers, 'after-migration'), passed)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM course_continuation_entitlements WHERE profile_id='finishing'").fetchone()[0], 1)
            self.assertTrue(course.checkpoint_read(conn, 'retry', 'retry-1')['support_used'])

    def test_release_uniqueness_and_pass_foreign_keys_are_enforced(self):
        self.upgrade()
        with sqlite3.connect(self.db) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            old = conn.execute("SELECT * FROM course_checkpoint_attempts WHERE id='active-1'").fetchone()
            duplicate = list(old)
            duplicate[0] = 'same-edition'
            placeholders = ','.join('?' for _ in duplicate)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('INSERT INTO course_checkpoint_attempts VALUES (' + placeholders + ')', duplicate)
            # Same chapter ID in another future release is a different gate.
            duplicate[0], duplicate[-2] = 'next-edition', 'a1-next'
            conn.execute('INSERT INTO course_checkpoint_attempts VALUES (' + placeholders + ')', duplicate)
            conn.execute("INSERT INTO course_chapter_passes VALUES ('active','a1-post-office','next-edition',300,'a1-next','next-rubric')")
            for profile, release_id, chapter in [('partial', 'a1-v1', 'a1-home'), ('active', 'a1-v1', 'a1-post-office'), ('active', 'a1-next', 'a1-home')]:
                with self.subTest(profile=profile, release_id=release_id, chapter=chapter), self.assertRaises(sqlite3.IntegrityError):
                    conn.execute('INSERT INTO course_chapter_passes VALUES (?,?,?,?,?,?)', (profile, chapter, 'next-edition', 300, release_id, 'rubric'))
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_four_unrelated_passes_do_not_create_legacy_a2_access(self):
        with sqlite3.connect(self.db) as conn:
            # A1 continuation requires the actual four shipped identities.
            for number in (2, 3, 4):
                self.old_attempt(conn, 'partial', number, 'passed')
                invented = 'unrelated-' + str(number)
                conn.execute('UPDATE course_checkpoint_attempts SET chapter_id=? WHERE id=?', (invented, f'partial-{number}'))
                conn.execute('UPDATE course_chapter_passes SET chapter_id=? WHERE attempt_id=?', (invented, f'partial-{number}'))
        self.upgrade()
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM course_chapter_passes WHERE profile_id='partial'").fetchone()[0], 4)
            self.assertIsNone(conn.execute("SELECT 1 FROM course_continuation_entitlements WHERE profile_id='partial'").fetchone())
            self.assertEqual(course.course_snapshot(conn, 'partial')['completed_milestones'], 1)

    def test_orphaned_legacy_pass_aborts_migration_without_losing_rows(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE course_chapter_passes SET attempt_id='missing' WHERE profile_id='partial'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.upgrade()
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(migrations.schema_version(conn), 44)
            self.assertEqual(conn.execute("SELECT attempt_id FROM course_chapter_passes WHERE profile_id='partial'").fetchone()[0], 'missing')
            self.assertNotIn('release_id', [row[1] for row in conn.execute('PRAGMA table_info(course_checkpoint_attempts)')])
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='course_enrolments'").fetchone())

    def test_mismatched_legacy_ownership_aborts_at_final_foreign_key_check(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE course_chapter_passes SET attempt_id='complete-1' WHERE profile_id='partial'")
        with self.assertRaisesRegex(ValueError, 'orphaned references'):
            self.upgrade()
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(migrations.schema_version(conn), 44)
            self.assertEqual(conn.execute("SELECT attempt_id FROM course_chapter_passes WHERE profile_id='partial'").fetchone()[0], 'complete-1')


if __name__ == '__main__':
    unittest.main()
