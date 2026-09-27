"""Structural audio evidence tests; synthetic PCM is not an acoustic evaluation."""
from copy import deepcopy
import json
import os
import sqlite3
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from repositories.learning_repository import transaction
from services.activity_evidence import load_contract, save_contract, save_report, validate_saved_evidence
from services.live_conversation import _ReceivedAudio
from services.speaking_assessment import SpeakingAssessment
from services.speaking_evidence import recorded_audio_source, speaking_task_contract, verify_audio_source
from services.speech_provider import SpeechError
from tests.support import isolated_app


def feedback(contract, *, outcome='satisfied', status='insufficient'):
    return {
        'transcript': 'Где парк?', 'speech_status': status, 'uncertain_phrases': [],
        'grammar': {'score': None, 'reason': 'There is too little speech for a broad score.', 'evidence': []},
        'fluency': {'score': None, 'reason': 'There is too little speech for a broad score.', 'evidence': []},
        'goals': [{'id': 'objective-1', 'status': 'completed', 'evidence': ['Где парк?']},
                  {'id': 'objective-2', 'status': 'not_yet', 'evidence': []},
                  {'id': 'objective-3', 'status': 'not_yet', 'evidence': []}],
        'summary': 'Your location question was understandable.', 'next_step': 'Try checking the direction next.',
        'corrections': [], 'uncertainty': '',
        'criterion_report': {'contract_sha256': contract['contract_sha256'], 'judgements': [{
            'criterion_id': 'ask-location', 'outcome': outcome,
            'score': None if outcome == 'insufficient_evidence' else 2,
            'feedback': 'Your short question asks where the park is.' if outcome == 'satisfied' else 'I could not locate clear speech for this question.',
            'evidence': [] if outcome == 'insufficient_evidence' else [{'start_ms': 100, 'end_ms': 600}]}]},
    }


class SpeakingCurriculumEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assessor = Mock()
        self.app = isolated_app(self, {'SpeakingAssessment': self.assessor})
        self.db = self.app.config['DB_PATH']
        self.live = self.app.extensions['learning']['live_conversation']
        self.reviews = self.live.reviews
        self.client = self.app.test_client()
        state = self.client.get('/api/v1/user-session').json
        self.profile = state['profile']['id']
        self.headers = {'X-CSRF-Token': state['csrf_token']}
        self.addCleanup(self.live.executor.shutdown, wait=True)
        self.addCleanup(self.reviews.executor.shutdown, wait=True)
        self.addCleanup(patch.stopall)
        patch.object(self.reviews, 'dispatch').start()
        patch.object(self.live, 'dispatch').start()
        self.body = {'submission_id': 'directions', 'scenario_id': 'directions',
                     'scenario_seed': 'directions-a1-park-v2', 'target_level': 'A1'}
        saved = self.post('', self.body)
        self.assertEqual(saved.status_code, 201, saved.json)
        self.sid, self.scenario = saved.json['id'], saved.json['scenario']
        with transaction(self.db) as conn:
            self.contract = load_contract(conn, self.profile, 'speaking', self.sid)
        self.set_feedback(feedback(self.contract))

    def post(self, path='', body=None):
        return self.client.post('/api/v1/live-conversations' + path, json=body or {}, headers=self.headers)

    def set_feedback(self, value):
        self.assessor.assess.return_value = {**deepcopy(value), 'basis': 'audio_review',
                                           'rubric_version': 'speaking-audio-v1', 'model': 'test-audio', 'rewards_applied': False}

    def record(self):
        capture = _ReceivedAudio(self.live, self.sid)
        capture.append(b'\0\0' * 2400 + struct.pack('<h', 900) * 16800 + b'\0\0' * 4800)
        capture.finish()

    def run_review(self):
        self.post('/' + self.sid + '/finish')
        self.reviews._work(self.sid)
        with transaction(self.db) as conn:
            return self.reviews.read(conn, self.sid)

    def recordings(self):
        with transaction(self.db) as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM live_conversation_recordings WHERE session_id=? ORDER BY ordinal', (self.sid,))]

    def counts(self):
        with transaction(self.db) as conn:
            return {table: conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in
                    ('activity_criterion_reports', 'progression_events', 'progression_entries',
                     'course_target_observations', 'course_chapter_passes')}

    def test_new_session_freezes_one_authored_goal_and_idempotent_start_keeps_it(self):
        self.assertEqual(self.contract['content']['scenario'], self.scenario)
        self.assertEqual(self.contract['content']['goal_ids'], ['objective-1'])
        self.assertEqual(len(self.contract['criteria']), 1)
        self.assertEqual(self.contract['criteria'][0]['requirement_id'], 'a1.speaking.ask-and-answer')
        again = self.post('', {**self.body, 'curriculum_contract': {'forged': True}})
        self.assertEqual(again.json['id'], self.sid)
        with transaction(self.db) as conn:
            self.assertEqual(load_contract(conn, self.profile, 'speaking', self.sid), self.contract)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM activity_task_contracts WHERE activity='speaking'").fetchone()[0], 1)
        altered = deepcopy(self.scenario)
        altered['goals'][0] = 'Give an unrelated speech.'
        with self.assertRaises(ValueError):
            speaking_task_contract(altered)
        self.assertIsNone(speaking_task_contract({'seed': 'old-unmapped-scenario'}))

    def test_short_question_keeps_null_general_scores_and_binds_exact_original_audio(self):
        self.record()
        self.live._event(self.sid, {'type': 'session.input_transcript.delta', 'event_id': 'asr',
                                  'delta': 'REPAIRED LEARNER WORDS', 'start_ms': 0, 'end_ms': 100})
        expected = recorded_audio_source(self.recordings(), self.live.root)
        before = self.counts()
        review = self.run_review()
        self.assertEqual(review['state'], 'ready', review)
        self.assertIsNone(review['report']['grammar']['score'])
        self.assertEqual(review['report']['criterion_report']['judgements'][0]['score'], 2)
        self.assertEqual(review['report']['audio_source'], expected)
        self.assertEqual((expected['duration_ms'], expected['independence']), (1000, 'unverified'))
        self.assertEqual(self.assessor.assess.call_args.kwargs['curriculum_contract'], self.contract)
        self.assertNotIn('REPAIRED', json.dumps(self.assessor.assess.call_args.args[2]))
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT response_sha256 FROM activity_criterion_reports').fetchone()[0], expected['sha256'])
            self.assertEqual(save_report(conn, self.profile, 'speaking', self.sid, self.sid,
                                         review['report']['criterion_report'], audio_source=expected),
                             conn.execute('SELECT id FROM activity_criterion_reports').fetchone()[0])
        # The existing goal adapter may record supported practice. The new
        # criterion cannot establish independent mastery or a milestone.
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations WHERE demonstrated=1').fetchone()[0], 0)
        self.assertEqual(self.counts()['course_chapter_passes'], before['course_chapter_passes'])
        loaded = self.client.get('/api/v1/live-conversations/' + self.sid).json
        detail = loaded['review']['report']['criterion_details'][0]
        self.assertEqual(detail['label'], 'Ask where the park is')
        self.assertNotIn('requirement_id', detail)
        self.reviews._work(self.sid)
        self.assessor.assess.assert_called_once()

    def test_invalid_audio_judgements_save_no_report_scores_or_rewards(self):
        self.record()
        baseline = self.counts()
        bad = []
        for span in ({'start_ms': -1, 'end_ms': 600}, {'start_ms': 100, 'end_ms': 1001},
                     {'start_ms': 100.0, 'end_ms': 600}, {'quote': 'Где парк?', 'start': 0, 'end': 9}):
            item = feedback(self.contract)
            item['criterion_report']['judgements'][0]['evidence'] = [span]
            bad.append(item)
        missing = feedback(self.contract); missing.pop('criterion_report'); bad.append(missing)
        wrong_hash = feedback(self.contract); wrong_hash['criterion_report']['contract_sha256'] = '0' * 64; bad.append(wrong_hash)
        null_score = feedback(self.contract); null_score['criterion_report']['judgements'][0]['score'] = None; bad.append(null_score)
        unclear = feedback(self.contract, status='unclear'); bad.append(unclear)
        uncertain = feedback(self.contract); uncertain['uncertain_phrases'] = ['Где']; bad.append(uncertain)
        for item in bad:
            with self.subTest(item=item):
                self.set_feedback(item)
                review = self.run_review()
                self.assertEqual(review['state'], 'failed')
                self.assertIsNone(review['report'])
                self.assertEqual(self.counts(), baseline)
        self.assertTrue(all((self.live.root / row['filename']).is_file() for row in self.recordings()))

    def test_uncertain_criterion_remains_unscored(self):
        self.record()
        value = feedback(self.contract, outcome='insufficient_evidence', status='unclear')
        value['uncertain_phrases'], value['uncertainty'] = ['парк'], 'The destination is hard to hear.'
        self.set_feedback(value)
        review = self.run_review()
        self.assertEqual(review['state'], 'ready', review)
        self.assertIsNone(review['report']['criterion_report']['judgements'][0]['score'])

    def test_original_bytes_changed_during_provider_work_fail_atomically(self):
        self.record()
        row = self.recordings()[0]
        path = self.live.root / row['filename']
        before = self.counts()
        def tamper(*args, **kwargs):
            data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
            return self.assessor.assess.return_value
        self.assessor.assess.side_effect = tamper
        review = self.run_review()
        self.assertEqual(review['state'], 'failed')
        self.assertIsNone(review['report'])
        self.assertEqual(self.counts(), before)

    def test_report_insert_failure_rolls_back_normal_review_and_rewards(self):
        self.record()
        before = self.counts()
        with transaction(self.db, write=True) as conn:
            conn.execute("CREATE TRIGGER fail_audio_evidence BEFORE INSERT ON activity_criterion_reports BEGIN SELECT RAISE(ABORT,'test failure'); END")
        review = self.run_review()
        self.assertEqual(review['state'], 'failed')
        self.assertIsNone(review['report'])
        self.assertEqual(self.counts(), before)

    def test_uncontracted_existing_scenario_keeps_ordinary_review_and_no_backfill(self):
        with transaction(self.db, write=True) as conn:
            conn.execute("DELETE FROM activity_task_contracts WHERE activity='speaking' AND task_key=?", (self.sid,))
        self.record()
        value = feedback(self.contract); value.pop('criterion_report'); self.set_feedback(value)
        self.assertEqual(self.run_review()['state'], 'ready')
        self.assertEqual(self.assessor.assess.call_args.kwargs, {})
        with transaction(self.db) as conn:
            self.assertIsNone(load_contract(conn, self.profile, 'speaking', self.sid))
            with self.assertRaises(ValueError):
                save_contract(conn, self.profile, 'speaking', self.sid, self.contract)
        self.assertEqual(self.counts()['activity_criterion_reports'], 0)

    def test_audio_manifest_ownership_offline_audit_and_delete(self):
        self.record(); self.assertEqual(self.run_review()['state'], 'ready')
        with sqlite3.connect(self.db) as conn:
            validate_saved_evidence(conn)
            validate_saved_evidence(conn, audio_root=self.live.root)
            source = json.loads(conn.execute('SELECT report_json FROM speaking_reviews WHERE session_id=?', (self.sid,)).fetchone()[0])['audio_source']
            with self.assertRaises(LookupError):
                verify_audio_source(conn, 'other-profile', self.sid, source)
            with self.assertRaises(ValueError):
                save_report(conn, self.profile, 'speaking', self.sid, 'other-session',
                            feedback(self.contract)['criterion_report'], audio_source=source)
            wrong = deepcopy(source); wrong['recordings'][0]['sample_count'] -= 1
            with self.assertRaises(ValueError):
                verify_audio_source(conn, self.profile, self.sid, wrong)
        self.assertTrue(self.post('/' + self.sid + '/delete').json['deleted'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM activity_task_contracts WHERE activity='speaking'").fetchone()[0], 0)
        self.assertFalse(list(self.live.root.glob('*.wav')))

    def test_symlinks_and_special_files_are_rejected_without_provider_work(self):
        self.record()
        rows = self.recordings(); path = self.live.root / rows[0]['filename']
        original = path.with_suffix('.original'); path.rename(original)
        path.symlink_to(original)
        self.assertEqual(self.run_review()['state'], 'failed')
        path.unlink(); os.mkfifo(path)
        try:
            with self.assertRaises(ValueError):
                recorded_audio_source(rows, self.live.root)
        finally:
            path.unlink(); original.rename(path)
        self.assessor.assess.assert_not_called()

    def test_actual_provider_receives_original_audio_contract_and_bounded_report(self):
        self.record()
        path = self.live.root / self.recordings()[0]['filename']
        service = SpeakingAssessment({'OPENAI_API_KEY': 'test-only'})
        response = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
            content=json.dumps(feedback(self.contract)), refusal=None))])
        with patch('services.speaking_assessment.openai_client') as factory:
            create = factory.return_value.chat.completions.create
            create.return_value = response
            result = service.assess(path, self.scenario, [{'role': 'user', 'content': 'Invented corrected captions'}],
                                    curriculum_contract=self.contract)
            sent = create.call_args.kwargs
            context = json.loads(sent['messages'][1]['content'][0]['text'])
            self.assertEqual(context['curriculum_contract'], self.contract)
            self.assertEqual(context['original_audio_duration_ms'], 1000)
            self.assertEqual(context['other_speaker_context'], [])
            self.assertEqual(sent['max_completion_tokens'], 6000)
            self.assertEqual(sent['model'], 'gpt-audio-1.5')
            self.assertNotIn('response_format', sent)
            self.assertIsNone(result['grammar']['score'])
            self.assertEqual(result['criterion_report']['judgements'][0]['score'], 2)
            broken = feedback(self.contract)
            broken['criterion_report']['judgements'][0]['evidence'][0]['end_ms'] = 2000
            response.choices[0].message.content = json.dumps(broken)
            with self.assertRaises(SpeechError):
                service.assess(path, self.scenario, [], curriculum_contract=self.contract)
            wrong = deepcopy(self.scenario); wrong['goals'][0] = 'A different demand'
            create.reset_mock()
            with self.assertRaises(SpeechError):
                service.assess(path, wrong, [], curriculum_contract=self.contract)
            create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
