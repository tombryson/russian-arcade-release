"""Original speaking recordings remain verifiable during offline imports."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import wave

from migrations import upgrade_database
from repositories.speaking_repository import choose_variant
from services.account_import import (ImportConflict, _assert_audio_filenames,
                                     _verify_speaking_audio, build_account_import, digest, transform)
from services.activity_evidence import save_contract, save_report
from services.speaking_evidence import recorded_audio_source, speaking_task_contract


def wav_bytes(data):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as target:
        target.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        target.writeframes(data)
    return buffer.getvalue()


class SpeakingImportAudioTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.session_id = 'a' * 32
        self.recording_id = 'b' * 32
        self.filename = self.recording_id + '.wav'
        audio = wav_bytes(b'\x08\x01' * 24000)
        (self.root / self.filename).write_bytes(audio)
        self.checksum = hashlib.sha256(audio).hexdigest()
        recording = {'id': self.recording_id, 'ordinal': 1, 'start_sample': 0,
                     'sample_count': 24000, 'sample_rate': 24000, 'sha256': self.checksum}
        self.source = {'version': 'speaking-audio-v1', 'sha256': self.checksum, 'duration_ms': 1000,
                       'recordings': [recording], 'independence': 'unverified'}
        self.contract = {'id': 'contract', 'profile_id': 'personal-learning', 'activity': 'speaking',
                         'task_key': self.session_id, 'contract_json': '{"content":{"scenario":{"title":"Original"}}}'}
        self.report = {'id': 'report', 'contract_id': 'contract', 'profile_id': 'personal-learning',
                       'source_key': self.session_id, 'report_json': '{"judgements":[]}'}
        self.tables = {
            'activity_task_contracts': {'rows': [self.contract]},
            'activity_criterion_reports': {'rows': [self.report]},
            'live_conversation_sessions': {'rows': [{'id': self.session_id, 'state': 'completed'}]},
            'speaking_reviews': {'rows': [{'session_id': self.session_id, 'state': 'ready',
                'report_json': json.dumps({'audio_source': self.source, 'transcript': 'Wrong ASR is not evidence.'})}]},
            'live_conversation_recordings': {'rows': [{k: v for k, v in recording.items() if k != 'sha256'} |
                {'session_id': self.session_id, 'filename': self.filename, 'state': 'ready',
                 'transcript_json': '{"text":"A normalized caption"}' }]},
        }

    def test_source_audio_is_required_and_captions_do_not_define_the_audio_hash(self):
        with self.assertRaisesRegex(ImportConflict, 'local-audio-root'):
            _verify_speaking_audio(self.tables, None)
        self.assertEqual(_verify_speaking_audio(self.tables, self.root),
                         {str(self.root / self.filename): self.checksum})
        self.tables['live_conversation_recordings']['rows'][0]['transcript_json'] = '{"text":"Another caption"}'
        self.assertEqual(_verify_speaking_audio(self.tables, self.root),
                         {str(self.root / self.filename): self.checksum})

    def test_changed_missing_truncated_or_symlinked_original_audio_is_rejected(self):
        path = self.root / self.filename
        original = path.read_bytes()
        for data in (wav_bytes(b'\x04\x01' * 24000), original[:-4]):
            with self.subTest(case='bytes'):
                path.write_bytes(data)
                with self.assertRaises(ImportConflict):
                    _verify_speaking_audio(self.tables, self.root)
        path.unlink()
        with self.assertRaises(ImportConflict):
            _verify_speaking_audio(self.tables, self.root)
        other = self.root / 'other.wav'
        other.write_bytes(original)
        path.symlink_to(other)
        with self.assertRaises(ImportConflict):
            _verify_speaking_audio(self.tables, self.root)

    def test_manifest_cannot_relabel_duration_timing_or_audio_independence(self):
        for key, value in (('duration_ms', 1001), ('independence', 'verified'), ('sha256', 'c' * 64)):
            tables = deepcopy(self.tables)
            source = deepcopy(self.source)
            source[key] = value
            tables['speaking_reviews']['rows'][0]['report_json'] = json.dumps({'audio_source': source})
            with self.subTest(key=key), self.assertRaises(ImportConflict):
                _verify_speaking_audio(tables, self.root)
        for key, value in (('ordinal', 2), ('start_sample', 1), ('sample_rate', 16000), ('sample_count', 23999)):
            tables = deepcopy(self.tables)
            tables['live_conversation_recordings']['rows'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ImportConflict):
                _verify_speaking_audio(tables, self.root)

    def test_frozen_speaking_payloads_and_typed_session_ids_are_not_remapped(self):
        schemas = {'activity_task_contracts': {'rows': [self.contract]}}
        table = {'pk': ['id'], 'foreign': []}
        mapping = {'writing_exercises': {1: 7}, 'live_conversation_events': {1: 11}}
        contract = transform('activity_task_contracts', table, self.contract, mapping, schemas)
        report = transform('activity_criterion_reports', table, self.report, mapping, schemas)
        self.assertEqual(contract, self.contract)
        self.assertEqual(report, self.report)
        changed = dict(self.report, source_key='c' * 32)
        with self.assertRaisesRegex(ImportConflict, 'another recorded conversation'):
            transform('activity_criterion_reports', table, changed, mapping, schemas)
        review = {'session_id': self.session_id,
                  'report_json': json.dumps({'audio_source': self.source, 'exercise_id': 1})}
        with self.assertRaisesRegex(ImportConflict, 'explicit migration policy'):
            transform('speaking_reviews', {'pk': ['session_id'], 'foreign': []}, review, mapping, schemas)

    def test_ambiguous_recording_filenames_require_a_media_merge_policy(self):
        recordings = self.tables['live_conversation_recordings']['rows']
        _assert_audio_filenames(recordings)
        with self.assertRaisesRegex(ImportConflict, 'share a filename'):
            _assert_audio_filenames(recordings + [dict(recordings[0], id='c' * 32)])
        with self.assertRaisesRegex(ImportConflict, 'unsafe filename'):
            _assert_audio_filenames([dict(recordings[0], filename='../recording.wav')])


class SpeakingEvidenceImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.audio = self.root / 'live-conversation-audio'
        self.audio.mkdir()
        self.local, self.hosted, self.output = [self.root / name for name in ('local.db', 'hosted.db', 'import.db')]
        for path in (self.local, self.hosted):
            upgrade_database(path, backup=False)
        self.sid, self.rid = 'a' * 32, 'b' * 32
        self.filename = self.rid + '.wav'
        (self.audio / self.filename).write_bytes(wav_bytes(b'\x08\x01' * 24000))
        with sqlite3.connect(self.local) as conn:
            conn.row_factory = sqlite3.Row
            scenario = choose_variant(conn, 'directions', seed='directions-a1-park-v2', level='A1')
            contract = speaking_task_contract(scenario)
            conn.execute("INSERT INTO live_conversation_sessions(id,profile_id,start_key,scenario_json,language,model,backend_model,voice,state,created_at,heartbeat_at) "
                         "VALUES (?,'personal-learning','start',?,'en','test','test','test','new',1,1)",
                         (self.sid, json.dumps(scenario)))
            save_contract(conn, 'personal-learning', 'speaking', self.sid, contract)
            conn.execute("INSERT INTO live_conversation_recordings(id,session_id,ordinal,filename,start_sample,sample_count,sample_rate,state,created_at) "
                         "VALUES (?,?,1,?,0,24000,24000,'ready',1)", (self.rid, self.sid, self.filename))
            rows = [dict(row) for row in conn.execute('SELECT * FROM live_conversation_recordings')]
            source = recorded_audio_source(rows, self.audio)
            criterion_report = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
                'criterion_id': contract['criteria'][0]['id'], 'outcome': 'satisfied', 'score': 2,
                'feedback': 'The learner asks for the park location.',
                'evidence': [{'start_ms': 0, 'end_ms': 900}]}]}
            review = {'basis': 'audio_review', 'audio_source': source, 'criterion_report': criterion_report,
                      'speech_status': 'russian', 'uncertain_phrases': [], 'transcript': 'Где парк?'}
            conn.execute("UPDATE live_conversation_sessions SET state='completed',ended_at=2 WHERE id=?", (self.sid,))
            conn.execute("INSERT INTO speaking_reviews(session_id,state,report_json,created_at,updated_at) "
                         "VALUES (?,'ready',?,2,2)", (self.sid, json.dumps(review)))
            save_report(conn, 'personal-learning', 'speaking', self.sid, self.sid, criterion_report, audio_source=source)
            self.saved = {table: [tuple(row) for row in conn.execute('SELECT * FROM ' + table)]
                          for table in ('live_conversation_sessions', 'live_conversation_recordings', 'speaking_reviews',
                                        'activity_task_contracts', 'activity_criterion_reports')}

    def test_import_preserves_contract_review_and_original_audio_hashes_exactly(self):
        before = (digest(self.local), digest(self.hosted), digest(self.audio / self.filename))
        report = build_account_import(self.local, self.hosted, self.output, local_audio_root=self.audio)
        self.assertEqual(before, (digest(self.local), digest(self.hosted), digest(self.audio / self.filename)))
        self.assertEqual(report['verified_speaking_recordings'], 1)
        self.assertFalse(report['media_copied'])
        with sqlite3.connect(self.output) as conn:
            for table, rows in self.saved.items():
                self.assertEqual(conn.execute('SELECT * FROM ' + table).fetchall(), rows, table)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_missing_originals_rejects_import_without_changing_inputs(self):
        before = (digest(self.local), digest(self.hosted))
        with self.assertRaisesRegex(ImportConflict, 'local-audio-root'):
            build_account_import(self.local, self.hosted, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, (digest(self.local), digest(self.hosted)))
        (self.audio / self.filename).unlink()
        with self.assertRaisesRegex(ImportConflict, 'audio could not be verified'):
            build_account_import(self.local, self.hosted, self.output, local_audio_root=self.audio)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, (digest(self.local), digest(self.hosted)))

    def test_changed_response_audio_hash_cannot_be_replaced_by_caption_hash(self):
        with sqlite3.connect(self.local) as conn:
            conn.execute('UPDATE activity_criterion_reports SET response_sha256=?',
                         (hashlib.sha256('Где парк?'.encode()).hexdigest(),))
        before = (digest(self.local), digest(self.hosted))
        with self.assertRaisesRegex(ImportConflict, 'evidence does not match'):
            build_account_import(self.local, self.hosted, self.output, local_audio_root=self.audio)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, (digest(self.local), digest(self.hosted)))

    def test_independent_hosted_speaking_evidence_requires_an_explicit_merge_policy(self):
        with self.assertRaisesRegex(ImportConflict, 'additional merge policy: .*activity_criterion_reports'):
            build_account_import(self.hosted, self.local, self.output)
        self.assertFalse(self.output.exists())

    def test_ambiguous_local_and_hosted_media_names_abort_the_merge(self):
        with sqlite3.connect(self.hosted) as conn:
            conn.execute("INSERT INTO live_conversation_sessions(id,profile_id,start_key,scenario_json,language,model,backend_model,voice,state,created_at,heartbeat_at) "
                         "VALUES (?,'personal-learning','hosted','{}','en','test','test','test','completed',1,1)", ('c' * 32,))
            conn.execute("INSERT INTO live_conversation_recordings(id,session_id,ordinal,filename,start_sample,sample_count,sample_rate,state,created_at) "
                         "VALUES (?,?,1,?,0,24000,24000,'ready',1)", ('d' * 32, 'c' * 32, self.filename))
        with self.assertRaisesRegex(ImportConflict, 'explicit media merge policy'):
            build_account_import(self.local, self.hosted, self.output, local_audio_root=self.audio)
        self.assertFalse(self.output.exists())

    def test_recordings_changed_after_initial_verification_prevent_output(self):
        from services import account_import
        repair = account_import._repair_card_projections

        def tamper_after_initial_check(merged):
            repair(merged)
            (self.audio / self.filename).write_bytes(wav_bytes(b'\x04\x01' * 24000))

        with patch.object(account_import, '_repair_card_projections', side_effect=tamper_after_initial_check):
            with self.assertRaisesRegex(ImportConflict, 'audio could not be verified'):
                build_account_import(self.local, self.hosted, self.output, local_audio_root=self.audio)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
