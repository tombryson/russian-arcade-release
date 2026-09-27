"""Offline imports preserve original evidence while remapping typed routing IDs."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from migrations import upgrade_database
from repositories.comprehension_repository import ComprehensionRepository
from repositories.translation_repository import TranslationRepository
from services.account_import import build_account_import, digest, inspect, transform, ImportConflict, _allocate
from services.activity_evidence import validate_saved_evidence
from services.comprehension_evidence import build_contracts, freeze_audio, reissue_contracts
from services.production_evidence import translation_contract
from tests.test_comprehension_listening import listening_story, assessment
from tests.test_comprehension_evidence_routes import ANSWERS
from tests.test_comprehension_evidence_integrity import prepared, assessment_for
from tests.test_sentence_production_evidence import translation_task, translation_focus, translation_feedback


OWNER = 'personal-learning'


class CurriculumEvidenceImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.local = self.root / 'local.db'; self.hosted = self.root / 'hosted.db'
        for path in (self.local, self.hosted):
            upgrade_database(path, backup=False)
        self.media = self.root / 'media'; self.media.mkdir()
        self.media_file = self.media / 'story_import_fixture.mp3'
        self.media_file.write_bytes(b'ID3 frozen generated recording')
        media = patch('services.comprehension_evidence._media_root', return_value=self.media.resolve())
        media.start(); self.addCleanup(media.stop)
        rewards = patch('repositories.comprehension_repository.legacy_profile', return_value=None)
        rewards.start(); self.addCleanup(rewards.stop)
        self.comprehension = ComprehensionRepository(str(self.local))
        self.translation = TranslationRepository(str(self.local))
        self.audit_script = Path(__file__).resolve().parents[2] / 'scripts' / 'audit_course_migration.py'
        spec = importlib.util.spec_from_file_location('curriculum_import_audit', self.audit_script)
        self.audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.audit)

    def connection(self, path=None):
        conn = sqlite3.connect(path or self.local)
        conn.execute('PRAGMA foreign_keys=ON')
        self.addCleanup(conn.close)
        return conn

    def clock(self, value):
        from contextlib import ExitStack
        scope = ExitStack()
        scope.enter_context(patch('repositories.comprehension_repository.timestamp', return_value=value))
        scope.enter_context(patch('services.activity_evidence.timestamp', return_value=value))
        return scope

    def listen(self):
        data = listening_story(); data['audio_url'] = '/static/media/' + self.media_file.name
        audio = freeze_audio(data['audio_url'], self.media)
        with self.clock(100):
            parent, _ = self.comprehension.create(data, 'places', 'A1',
                build_contracts(data, 'places', 'A1', practice_mode='listening', audio=audio, track_support=True),
                expected_owner=OWNER, practice_mode='listening', audio=audio, track_support=True)
        with self.clock(110):
            self.comprehension.record_support(parent, 0, uuid4().hex, 'listened')
        self.check(parent, ANSWERS, 120)
        with self.clock(130):
            self.comprehension.record_support(parent, 1, uuid4().hex, 'transcript')
        with self.clock(140):
            self.comprehension.record_support(parent, 1, uuid4().hex, 'hint', word='аптеке')
        with self.clock(150):
            task = self.comprehension.begin_questions(parent, 1)
            questions = task['payload']['questions'] + ['Как зовут девушку?']
            child, _ = self.comprehension.create({**task['payload'], 'questions': questions,
                'title': task['title'], 'title_en': task['title_en']}, 'places', 'A1',
                reissue_contracts(task['payload'], questions), expected_owner=OWNER,
                story_id=task['story_id'], parent_id=parent, lease_token=task['check_token'])
        self.check(child, ANSWERS + ['Её зовут Анна.'], 160)
        return parent, child

    def check(self, task_id, answers, now):
        with self.clock(now):
            task = self.comprehension.load(task_id); submission = uuid4().hex
            issued, _ = self.comprehension.begin_check(task_id, task['revision'], submission, answers)
            return self.comprehension.finish_check(task_id, task['revision'], submission, answers,
                assessment(issued['payload'], answers), expected_owner=OWNER, lease_token=issued['check_token'])

    def production(self):
        data = translation_task(); contract = translation_contract(data, translation_focus(), 'home')
        identity, _ = self.translation.save_content(**data, curriculum_contract=contract)
        raw = '{"sentence_id":1,"message":"Я живу в Москве."}'
        self.translation.save_check(identity, raw, 0, translation_feedback(contract, raw), 'en')
        self.translation.record_reference_views([identity])
        self.translation.save_check(identity, '  В Москве я живу.\n', 1,
                                    translation_feedback(contract, '  В Москве я живу.\n'), 'en')
        return identity

    def frozen(self, conn):
        return {table: conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                for table in ('comprehension_tasks', 'comprehension_attempts', 'comprehension_support_receipts',
                              'activity_task_contracts', 'activity_criterion_reports', 'translation_attempts',
                              'translation_reference_views')}

    def clone(self, name):
        target = self.root / (name + '.db')
        with self.connection() as source, self.connection(target) as destination:
            source.backup(destination)
        return target

    def test_full_import_preserves_listening_inheritance_and_production_evidence_bytes(self):
        self.listen(); self.production()
        with self.connection() as conn:
            before = self.frozen(conn)
            validate_saved_evidence(conn)
        hashes = (digest(self.local), digest(self.hosted)); audio = self.media_file.read_bytes()
        output = self.root / 'imported.db'
        report = build_account_import(self.local, self.hosted, output)
        self.assertFalse(report['media_copied'])
        self.assertEqual((digest(self.local), digest(self.hosted)), hashes)
        self.assertEqual(self.media_file.read_bytes(), audio)
        with self.connection(output) as conn:
            self.assertEqual(self.frozen(conn), before)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            changes = conn.total_changes; validate_saved_evidence(conn)
            self.assertEqual(conn.total_changes, changes)

    def test_real_artifact_remaps_sentence_relations_without_editing_raw_json_answer(self):
        self.listen(); sentence_id = self.production()
        output = self.root / 'remapped.db'
        # Hosted Translation history remains unsupported. Force a known, valid
        # allocator result to exercise every real artifact routing edge without
        # relaxing that independent-history merge policy.
        def allocated(existing, incoming, table, **kwargs):
            if table in ('sentences', 'saved_stories'):
                return {row['id']: row['id'] + 100 for row in incoming}
            return _allocate(existing, incoming, table, **kwargs)
        with self.connection() as conn:
            original_attempts = conn.execute('SELECT id,response,criterion_report_json,criterion_support_json FROM translation_attempts ORDER BY id').fetchall()
            frozen_contract = conn.execute("SELECT contract_json FROM activity_task_contracts WHERE activity='translation'").fetchone()[0]
            comprehension_tasks = conn.execute('SELECT id,story_id,payload_json FROM comprehension_tasks ORDER BY rowid').fetchall()
            comprehension_rows = {name: conn.execute('SELECT * FROM ' + name + ' ORDER BY rowid').fetchall()
                                  for name in ('comprehension_attempts', 'comprehension_support_receipts')}
        before = (digest(self.local), digest(self.hosted))
        with patch('services.account_import._allocate', side_effect=allocated):
            report = build_account_import(self.local, self.hosted, output)
        mapped = sentence_id + 100
        self.assertEqual(report['local_id_mappings']['sentences'], {str(sentence_id): mapped})
        self.assertEqual(before, (digest(self.local), digest(self.hosted)))
        with self.connection(output) as conn:
            self.assertEqual(conn.execute('SELECT id FROM sentences').fetchone()[0], mapped)
            self.assertEqual(conn.execute('SELECT sentence_id FROM translation_drafts').fetchone()[0], mapped)
            self.assertEqual(conn.execute('SELECT DISTINCT sentence_id FROM translation_attempts').fetchone()[0], mapped)
            self.assertEqual(conn.execute('SELECT sentence_id,after_attempt_id FROM translation_reference_views').fetchone(), (mapped, original_attempts[0][0]))
            self.assertEqual(conn.execute('SELECT id,response,criterion_report_json,criterion_support_json FROM translation_attempts ORDER BY id').fetchall(), original_attempts)
            self.assertEqual(conn.execute("SELECT task_key,contract_json FROM activity_task_contracts WHERE activity='translation'").fetchone(), (str(mapped), frozen_contract))
            self.assertEqual(conn.execute("SELECT DISTINCT content_key FROM progression_events WHERE activity='translation'").fetchall(), [(f'translation:{mapped}',)])
            self.assertEqual(conn.execute("SELECT content_key FROM progression_claims WHERE content_key LIKE 'translation:%'").fetchone()[0], f'translation:translation:{mapped}')
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(conn.execute('SELECT id,story_id,payload_json FROM comprehension_tasks ORDER BY rowid').fetchall(),
                             [(identity, story_id + 100, payload) for identity, story_id, payload in comprehension_tasks])
            for name, rows in comprehension_rows.items():
                self.assertEqual(conn.execute('SELECT * FROM ' + name + ' ORDER BY rowid').fetchall(), rows)
            validate_saved_evidence(conn)

    def test_typed_attempt_mapping_keeps_reference_views_and_shared_report_source_aligned(self):
        self.production()
        with self.connection() as conn:
            conn.row_factory = sqlite3.Row
            schemas = inspect(conn)
        maps = {'sentences': {1: 101}, 'translation_attempts': {1: 201, 2: 202}}
        draft = {**schemas['translation_drafts']['rows'][0], 'response': '{"sentence_id":1}'}
        mapped_draft = transform('translation_drafts', schemas['translation_drafts'], draft, maps, schemas)
        self.assertEqual(mapped_draft['sentence_id'], 101)
        self.assertEqual(mapped_draft['response'], draft['response'])
        for name in ('translation_attempts', 'translation_reference_views', 'activity_task_contracts', 'activity_criterion_reports', 'progression_events'):
            for row in schemas[name]['rows']:
                mapped = transform(name, schemas[name], row, maps, schemas)
                if name == 'translation_attempts':
                    self.assertEqual((mapped['id'], mapped['sentence_id']), (maps['translation_attempts'][row['id']], 101))
                    for field in ('response', 'criterion_report_json', 'criterion_support_json'):
                        self.assertEqual(mapped[field], row[field])
                elif name == 'translation_reference_views':
                    self.assertEqual((mapped['sentence_id'], mapped['after_attempt_id']), (101, 201))
                elif name == 'activity_task_contracts':
                    self.assertEqual(mapped['task_key'], '101')
                    self.assertEqual(mapped['contract_json'], row['contract_json'])
                elif name == 'activity_criterion_reports':
                    self.assertEqual(mapped['source_key'], str(maps['translation_attempts'][int(row['source_key'])]))
                    self.assertEqual(mapped['report_json'], row['report_json'])
                else:
                    self.assertEqual(mapped['content_key'], 'translation:101')
                    old = int(row['source_key'].split(':')[1])
                    self.assertEqual(mapped['source_key'], 'translation-attempt:' + str(maps['translation_attempts'][old]))

    def test_receipt_chronology_tampering_aborts_artifact_without_mutating_inputs(self):
        parent, child = self.listen()
        changes = {
            'late-inherited-source': ("UPDATE comprehension_support_receipts SET created_at=151 WHERE task_id=? AND kind='hint'", (parent,)),
            'receipt-before-previous-answer': ("UPDATE comprehension_support_receipts SET created_at=119 WHERE task_id=? AND kind='transcript'", (parent,)),
            'missing-inheritance': ("DELETE FROM comprehension_support_receipts WHERE task_id=? AND kind='hint'", (child,)),
            'changed-inheritance': ("UPDATE comprehension_support_receipts SET detail_json='{\"word\":\"Анна\"}' WHERE task_id=? AND kind='hint'", (child,)),
            'dropped-snapshot': ("UPDATE comprehension_attempts SET support_receipts_json='[]' WHERE task_id=?", (child,)),
        }
        originals = (digest(self.local), digest(self.hosted))
        for name, (sql, params) in changes.items():
            with self.subTest(tamper=name):
                corrupt = self.clone(name)
                with self.connection(corrupt) as conn:
                    conn.execute(sql, params)
                before = digest(corrupt); output = self.root / (name + '-output.db')
                with self.assertRaises(ImportConflict):
                    build_account_import(corrupt, self.hosted, output)
                self.assertFalse(output.exists())
                self.assertEqual(digest(corrupt), before)
        self.assertEqual((digest(self.local), digest(self.hosted)), originals)

    def test_reference_receipt_and_production_digest_tampering_fail_import_and_inventory(self):
        self.production()
        changes = {
            'reference-owner': "UPDATE translation_reference_views SET profile_id='wrong-profile'",
            'first-support': "UPDATE translation_attempts SET criterion_support_json='[\"model_answer\"]' WHERE id=1",
            'lost-report': "DELETE FROM activity_criterion_reports WHERE source_key='1'",
            'response-digest': "UPDATE activity_criterion_reports SET response_sha256='" + '0' * 64 + "'",
            'original-response': "UPDATE translation_attempts SET response='Исправленный ответ.' WHERE id=1",
        }
        for name, sql in changes.items():
            with self.subTest(tamper=name):
                corrupt = self.clone(name)
                with self.connection(corrupt) as conn:
                    conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('wrong-profile','Other','O','UTC',1)")
                    conn.execute(sql)
                    before = conn.total_changes
                    self.assertEqual(self.audit.inventory(conn)['invalid_production_evidence'], 1)
                    self.assertEqual(conn.total_changes, before)
                output = self.root / (name + '-output.db')
                with self.assertRaises(ImportConflict):
                    build_account_import(corrupt, self.hosted, output)
                self.assertFalse(output.exists())

    def test_schema_051_readonly_audit_and_rehearsal_preserve_original_rows(self):
        data = prepared()
        with self.clock(100):
            task_id, _ = self.comprehension.create(data, 'home', 'A1', build_contracts(data, 'home', 'A1'), expected_owner=OWNER)
        with self.clock(110):
            answers = ['Дома.'] * 5; submission = uuid4().hex
            task, _ = self.comprehension.begin_check(task_id, 0, submission, answers)
            self.comprehension.finish_check(task_id, 0, submission, answers, assessment_for(task['payload'], answers),
                                            expected_owner=OWNER, lease_token=task['check_token'])
        with self.connection() as conn:
            for table in ('assessment_pilot_requests', 'assessment_pilot_reviews', 'assessment_pilot_submissions',
                          'assessment_pilot_support', 'assessment_pilot_components', 'assessment_pilot_sessions'):
                conn.execute('DROP TABLE ' + table)
            conn.execute('DROP TABLE translation_reference_views')
            for table in ('translation_attempts', 'word_jumble_attempts'):
                conn.execute(f'ALTER TABLE {table} DROP COLUMN criterion_report_json')
                conn.execute(f'ALTER TABLE {table} DROP COLUMN criterion_support_json')
            conn.execute('DROP TABLE comprehension_support_receipts')
            conn.execute('ALTER TABLE comprehension_attempts DROP COLUMN support_receipts_json')
            conn.execute('DELETE FROM schema_migrations WHERE version>51')
        original = digest(self.local)
        result = subprocess.run([sys.executable, str(self.audit_script), '--db', str(self.local), '--rehearse'],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report['schema'], 51)
        self.assertEqual(report['invalid_comprehension_evidence'], 0)
        self.assertEqual(report['invalid_production_evidence'], 0)
        self.assertTrue(report['rehearsal']['existing_course_rows_unchanged'])
        self.assertGreaterEqual(report['rehearsal']['schema'], 53)
        self.assertEqual(digest(self.local), original)


if __name__ == '__main__':
    unittest.main()
