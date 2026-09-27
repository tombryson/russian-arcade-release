"""Focused offline evidence/import checks; providers are deterministic test doubles."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from migrations import upgrade_database
from repositories.assessment_pilot_repository import AssessmentPilotRepository
from repositories.learning_repository import encoded
from services.account_import import ImportConflict, build_account_import, digest
from services.assessment_pilot import AssessmentPilotService
from services.assessment_pilot_content import blueprint, validate_blueprint
from services.assessment_pilot_integrity import PILOT_TABLES, validate_saved_pilot


def judgements(contract, *, text=None, duration=None):
    evidence = ([{'quote': text, 'start': 0, 'end': len(text)}] if text is not None
                else [{'start_ms': 0, 'end_ms': duration}])
    return {'contract_sha256': contract['contract_sha256'], 'judgements': [
        {'criterion_id': criterion['id'], 'outcome': 'satisfied', 'score': criterion['max_score'],
         'feedback': 'Fixture evidence matches this sampled criterion.', 'evidence': evidence}
        for criterion in contract['criteria']]}


class WritingFixture:
    def assess_writing(self, task, words, target_words, response, **kwargs):
        return {'score': 8, 'strength': 'Fixture original text retained.', 'next_step': 'Review the requested details.',
                'example': 'Привет! Приходи в парк в субботу в три часа. Погуляем вместе. Ты можешь прийти?',
                'assessment_provenance': {'model': 'fixture-writing', 'prompt_sha256': hashlib.sha256(b'fixture-writing-v1').hexdigest(), 'rubric_version': 'fixture-writing-v1'},
                'criterion_report': judgements(kwargs['curriculum_contract'], text=response)}


class SpeakingFixture:
    def assess(self, path, scenario, captions, language, **kwargs):
        with wave.open(str(path), 'rb') as source:
            duration = source.getnframes() * 1000 // source.getframerate()
        transcript = 'Меня зовут Анна. Я из Москвы. Я живу с семьёй и люблю читать книги.'
        return {'speech_status': 'russian', 'uncertain_phrases': [], 'model': 'fixture', 'transcript': transcript,
                'grammar': {'score': 5, 'reason': 'Clear fixture language.', 'evidence': ['Меня зовут Анна.']},
                'fluency': {'score': 5, 'reason': 'Connected fixture speech.', 'evidence': ['Я из Москвы.']},
                'goals': [{'id': identity, 'status': 'completed', 'evidence': [transcript]} for identity in scenario['goal_ids']],
                'corrections': [], 'uncertainty': '', 'basis': 'audio_review', 'rubric_version': 'speaking-audio-v1',
                'rewards_applied': False,
                'assessment_provenance': {'model': 'fixture-speaking', 'prompt_sha256': hashlib.sha256(b'fixture-speaking-v1').hexdigest(), 'rubric_version': 'speaking-audio-v1'},
                'summary': 'Fixture original audio retained.', 'next_step': 'Record another original message.',
                'criterion_report': judgements(kwargs['curriculum_contract'], duration=duration)}


class AssessmentPilotIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.local = self.root / 'local.db'; self.hosted = self.root / 'hosted.db'
        for path in (self.local, self.hosted):
            upgrade_database(path, backup=False)
        self.repo = AssessmentPilotRepository(self.local)
        self.service = AssessmentPilotService(self.local, WritingFixture(), SpeakingFixture(), {})
        for target in ('repositories.assessment_pilot_repository.require_access', 'services.assessment_pilot.require_access'):
            mock = patch(target, return_value={'id': 'personal-learning'})
            mock.start(); self.addCleanup(mock.stop)
        self.audit_script = Path(__file__).resolve().parents[2] / 'scripts' / 'audit_course_migration.py'
        spec = importlib.util.spec_from_file_location('pilot_integrity_audit', self.audit_script)
        self.audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.audit)
        self.sid = None

    def connection(self, path=None):
        conn = sqlite3.connect(path or self.local)
        self.addCleanup(conn.close)
        return conn

    def start(self):
        self.sid = self.repo.start('fixture', {'submission_id': 'start'}, blueprint())
        self.assertEqual(self.repo.start('fixture', {'submission_id': 'resume'}, blueprint()), self.sid)

    def current(self, domain):
        with sqlite3.connect(self.local) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM assessment_pilot_components WHERE session_id=? AND domain=? ORDER BY ordinal DESC LIMIT 1',
                               (self.sid, domain)).fetchone()
            return dict(row), json.loads(row['task_json'])

    def body(self, domain, key, **fields):
        row, _ = self.current(domain)
        return {'submission_id': key, 'component_id': row['id'], 'expected_revision': row['revision'], **fields}

    def selection(self, domain, key):
        _, task = self.current(domain)
        response = {'answers': {item['id']: item['answer'] for item in task['items']}}
        return self.service.submit('fixture', self.sid, domain, self.body(domain, key, response=response))

    def retry(self, domain, key):
        row, _ = self.current(domain)
        return self.service.retry('fixture', self.sid, {'submission_id': key, 'components': [{'domain': domain, 'component_id': row['id']}]})

    def fixture(self, *, audio=True):
        self.start()
        self.selection('language_use', 'language-a')
        self.selection('reading', 'reading-a')
        self.service.support('fixture', self.sid, 'listening', self.body('listening', 'transcript-a', kind='transcript'))
        self.selection('listening', 'listening-a')
        raw = '{"sentence_id":1,"message":"Привет! Встретимся в парке в субботу в три часа?"}'
        self.service.draft('fixture', self.sid, 'writing', self.body('writing', 'draft-writing', response={'text': raw}))
        self.service.submit('fixture', self.sid, 'writing', self.body('writing', 'writing-a', response={'text': raw}))
        self.service.submit('fixture', self.sid, 'speaking', self.body('speaking', 'speaking-unavailable', response={'unavailable': True}))
        self.retry('language_use', 'retry-language-b'); self.selection('language_use', 'language-b')
        self.retry('language_use', 'retry-language-a')
        row, _ = self.current('language_use')
        self.assertEqual((row['repeated'], row['prior_feedback']), (1, 1))
        if audio:
            self.retry('speaking', 'retry-speaking-b')
            source = io.BytesIO()
            with wave.open(source, 'wb') as stream:
                stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                stream.writeframes(b'\x01\x00' * 16000)
            # Native PCM fixture avoids external encoders and network providers.
            with patch('services.assessment_pilot.audio_info', return_value={}):
                self.service.submit('fixture', self.sid, 'speaking', self.body('speaking', 'speaking-audio', response={}),
                                    data=source.getvalue(), extension='wav')
        with sqlite3.connect(self.local) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM assessment_pilot_reviews WHERE state!='ready'").fetchone()[0], 0)
        return raw

    @staticmethod
    def snapshots(conn):
        return {table: conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall() for table in PILOT_TABLES}

    def test_frozen_forms_and_full_import_keep_all_original_ids_and_json(self):
        public = blueprint()
        self.assertEqual(validate_blueprint(public), public)
        changed = deepcopy(public); changed['schema_version'] = True
        with self.assertRaises(ValueError): validate_blueprint(changed)
        for task in public['forms']['writing']:
            self.assertNotIn('30', task['prompt']); self.assertNotIn('30', task['prompt_ru'])
        for task in public['forms']['speaking']:
            self.assertEqual({criterion['requirement_id'] for criterion in task['contract']['criteria']},
                             {'a1.speaking.personal-information', 'a1.speaking.intelligibility'})
        raw = self.fixture()
        inputs = {path: digest(path) for path in (self.local, self.hosted)}
        media = {path: digest(path) for path in self.service.root.iterdir()}
        source = self.connection(); before = self.snapshots(source)
        changes = source.total_changes
        self.assertEqual(len(validate_saved_pilot(source, audio_root=self.service.root, require_audio=True)), 2)
        self.assertEqual(self.audit.inventory(source, pilot_audio_root=self.service.root)['invalid_assessment_pilot_evidence'], 0)
        self.assertEqual(source.total_changes, changes)
        result = build_account_import(self.local, self.hosted, self.root / 'import.db', local_pilot_audio_root=self.service.root)
        imported = self.connection(self.root / 'import.db')
        self.assertEqual(self.snapshots(imported), before)
        self.assertEqual(json.loads(imported.execute("SELECT s.response_json FROM assessment_pilot_submissions s JOIN assessment_pilot_components c ON c.id=s.component_id WHERE c.domain='writing'").fetchone()[0]), {'text': raw})
        self.assertEqual(result['verified_pilot_recordings'], 1); self.assertIs(result['media_copied'], False)
        self.assertFalse(imported.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual(inputs, {path: digest(path) for path in inputs})
        self.assertEqual(media, {path: digest(path) for path in media})

    def test_support_report_and_request_tampering_are_rejected_read_only(self):
        self.fixture(audio=False)
        conn = self.connection()
        receipt = conn.execute('SELECT id FROM assessment_pilot_support').fetchone()[0]
        listening = conn.execute("SELECT s.id FROM assessment_pilot_submissions s JOIN assessment_pilot_components c ON c.id=s.component_id WHERE c.domain='listening'").fetchone()[0]
        writing = conn.execute("SELECT s.id FROM assessment_pilot_submissions s JOIN assessment_pilot_components c ON c.id=s.component_id WHERE c.domain='writing'").fetchone()[0]
        language = conn.execute("SELECT s.id FROM assessment_pilot_submissions s JOIN assessment_pilot_components c ON c.id=s.component_id WHERE c.domain='language_use' ORDER BY c.ordinal LIMIT 1").fetchone()[0]
        mutations = [
            ('UPDATE assessment_pilot_support SET created_at=created_at+10000 WHERE id=?', (receipt,)),
            ("UPDATE assessment_pilot_support SET detail_json='{}',kind='listened' WHERE id=?", (receipt,)),
            ("UPDATE assessment_pilot_submissions SET receipt_ids_json='[]' WHERE id=?", (listening,)),
            ("UPDATE assessment_pilot_submissions SET support_json='[]' WHERE id=?", (listening,)),
            ("UPDATE assessment_pilot_submissions SET request_sha256=? WHERE id=?", ('0' * 64, writing)),
            ("UPDATE assessment_pilot_reviews SET report_json=json_set(report_json,'$.source_sha256',?) WHERE submission_id=?", ('0' * 64, writing)),
            ("UPDATE assessment_pilot_reviews SET report_json=json_set(report_json,'$.criterion_report.judgements[0].outcome','not_satisfied','$.criterion_report.judgements[0].score',0,'$.outcome','practise_and_retry') WHERE submission_id=?", (language,)),
            ("UPDATE assessment_pilot_components SET draft_json='{}' WHERE domain='writing'", ()),
            ("UPDATE assessment_pilot_requests SET request_sha256=? WHERE operation='support:listening'", ('0' * 64,)),
        ]
        for sql, values in mutations:
            with self.subTest(sql=sql):
                conn.execute('SAVEPOINT tamper')
                conn.execute(sql, values)
                changes = conn.total_changes
                with self.assertRaises(ValueError): validate_saved_pilot(conn)
                self.assertEqual(self.audit.inventory(conn)['invalid_assessment_pilot_evidence'], 1)
                self.assertEqual(conn.total_changes, changes)
                conn.execute('ROLLBACK TO tamper'); conn.execute('RELEASE tamper')
        conn.execute('UPDATE assessment_pilot_reviews SET report_json=json_set(report_json,\'$.source_sha256\',?) WHERE submission_id=?', ('0' * 64, writing)); conn.commit()
        output = self.root / 'tampered-import.db'
        with self.assertRaises(ImportConflict): build_account_import(self.local, self.hosted, output)
        self.assertFalse(output.exists())

    def test_import_requires_unchanged_original_and_review_audio(self):
        self.fixture()
        original_hash = digest(self.local)
        output = self.root / 'missing-audio.db'
        with self.assertRaises(ImportConflict): build_account_import(self.local, self.hosted, output)
        self.assertFalse(output.exists())
        source = self.connection()
        audio = json.loads(source.execute('SELECT audio_json FROM assessment_pilot_submissions WHERE audio_json IS NOT NULL').fetchone()[0])
        for name in ('filename', 'assessment_filename'):
            path = self.service.root / audio[name]; data = path.read_bytes(); path.write_bytes(data[:-2])
            with self.subTest(name=name):
                with self.assertRaises((OSError, ValueError)):
                    validate_saved_pilot(source, audio_root=self.service.root, require_audio=True)
                with self.assertRaises(ImportConflict):
                    build_account_import(self.local, self.hosted, output, local_pilot_audio_root=self.service.root)
                self.assertFalse(output.exists())
            path.write_bytes(data)
        self.assertEqual(digest(self.local), original_hash)

    def test_import_only_resets_transient_running_claim(self):
        self.fixture(audio=False)
        self.retry('writing', 'retry-writing-b')
        body = self.body('writing', 'writing-running', response={'text': 'Привет! Приходи ко мне домой в субботу в шесть часов. Будем пить чай. Ты можешь прийти?'})
        submission = self.repo.submit('fixture', self.sid, 'writing', body)
        row, _ = self.current('writing')
        self.repo.claim_review('fixture', self.sid, 'writing', body={'submission_id': 'explicit-review', 'component_id': row['id']})
        source = self.connection(); before = self.snapshots(source)
        self.assertEqual(validate_saved_pilot(source), {})
        input_hash = digest(self.local)
        build_account_import(self.local, self.hosted, self.root / 'claim-import.db')
        imported = self.connection(self.root / 'claim-import.db'); after = self.snapshots(imported)
        for table in PILOT_TABLES:
            if table != 'assessment_pilot_reviews': self.assertEqual(before[table], after[table])
        imported.row_factory = sqlite3.Row
        review = imported.execute('SELECT * FROM assessment_pilot_reviews WHERE submission_id=?', (submission,)).fetchone()
        self.assertEqual(review['state'], 'failed'); self.assertIsNone(review['claim_token'])
        self.assertEqual(review['lease_until'], 0); self.assertIsNone(review['report_json'])
        self.assertEqual(validate_saved_pilot(imported), {})
        self.assertEqual(digest(self.local), input_hash)

    def test_schema_53_audit_rehearsal_preserves_existing_evidence(self):
        from repositories.writing_repository import WritingRepository
        from services.curriculum_units import get_unit, writing_task
        conn = self.connection()
        task = writing_task(get_unit('location-destination-v1'))
        WritingRepository.create_in_transaction(conn, task, 'places', 'A1', 30, 'personal-learning')
        for table in reversed(PILOT_TABLES): conn.execute('DROP TABLE ' + table)
        conn.execute('DELETE FROM schema_migrations WHERE version>53'); conn.commit()
        original = digest(self.local)
        result = subprocess.run([sys.executable, str(self.audit_script), '--db', str(self.local), '--rehearse'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['schema'], 53)
        self.assertEqual(report['counts']['activity_task_contracts'], 1)
        self.assertEqual(report['invalid_assessment_pilot_evidence'], 0)
        self.assertTrue(report['rehearsal']['existing_course_rows_unchanged'])
        self.assertGreaterEqual(report['rehearsal']['schema'], 54)
        self.assertEqual(digest(self.local), original)


if __name__ == '__main__':
    unittest.main()
