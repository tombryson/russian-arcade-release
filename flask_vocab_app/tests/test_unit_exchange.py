"""Two distinct heard prompts require two owned saved microphone replies."""
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from uuid import uuid4
import wave

from repositories.learning_repository import transaction
from services.activity_evidence import validate_saved_evidence
from services.curriculum_sequence_content import load_asset, task_contract
from services.unit_exchange import create_in_transaction
from tests.support import isolated_app


def recording():
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
        audio.writeframes(b'\x01\x00' * 8000)
    return out.getvalue()


class UnitExchangeTests(unittest.TestCase):
    def setUp(self):
        self.assessor = Mock()
        self.app = isolated_app(self, {'SpeakingAssessment': self.assessor})
        self.db = self.app.config['DB_PATH']; self.client = self.app.test_client()
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        self.app.config['OPENAI_API_KEY'] = 'test-configured-not-used'

    def post(self, url, data=None):
        return self.client.post(url, json=data or {}, headers={'X-CSRF-Token': self.token})

    def allocate(self, audio=True, transfer=True):
        run = self.post('/api/v1/curriculum/units/location-destination-v2/runs',
            {'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1'}).json
        asset = load_asset('location-exchange-v1')
        if audio:
            path = Path(__file__).resolve().parents[1] / 'static/audio/course/curriculum/location-destination-listening-v1/shop-now.mp3'
            raw = path.read_bytes()
            for turn in asset['content']['turns']:
                turn['audio'] = {'url': '/static/audio/course/curriculum/location-destination-listening-v1/shop-now.mp3',
                                 'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}
        else:
            for turn in asset['content']['turns']:
                turn['audio'] = None
        with transaction(self.db, write=True) as conn:
            owner = conn.execute('SELECT profile_id FROM curriculum_unit_runs WHERE id=?', (run['id'],)).fetchone()[0]
            task = create_in_transaction(conn, owner, asset, task_contract)
            step = 'transfer/0' if transfer else 'speaking'
            ordinal = conn.execute("SELECT COALESCE(MAX(ordinal),-1)+1 FROM curriculum_unit_bindings WHERE run_id=? AND step_id=?", (run['id'], step)).fetchone()[0]
            conn.execute('INSERT INTO curriculum_unit_bindings VALUES (?,?,?,?,?,?,?,?,?)',
                (uuid4().hex, run['id'], owner, step, ordinal, task['activity'], task['task_key'],
                 'unit-transfer-no-effects-v1' if transfer else 'existing-activity-effects-v1', 1))
        self.identity, self.owner, self.run_id = task['task_key'], owner, run['id']
        self.path = '/api/v1/unit-exchanges/' + self.identity
        return self.client.get(self.path).json

    def send(self, state, key=None, data=None):
        return self.client.post(self.path + '/turns/' + state['current_turn']['id'] + '/recording',
            data={'audio': (io.BytesIO(data or recording()), 'reply.wav'), 'submission_id': key or uuid4().hex,
                  'expected_revision': str(state['revision'])}, headers={'X-CSRF-Token': self.token})

    def turn(self, state):
        listened = self.post(self.path + '/turns/' + state['current_turn']['id'] + '/listened',
            {'submission_id': uuid4().hex, 'expected_revision': state['revision']})
        self.assertEqual(listened.status_code, 200, listened.get_data(as_text=True))
        sent = self.send(listened.json)
        self.assertEqual(sent.status_code, 200, sent.get_data(as_text=True))
        return sent.json

    def ready_report(self):
        def assess(path, scenario, dialogue, language, curriculum_contract, include_provenance=False, recording_turns=None):
            self.assertEqual(len(dialogue), 2)
            self.assertTrue(all(row['role'] == 'assistant' for row in dialogue))
            with wave.open(str(path), 'rb') as audio:
                duration = audio.getnframes() * 1000 // audio.getframerate()
            return {'basis': 'audio_review', 'rubric_version': 'speaking-audio-v1', 'model': 'test',
                'speech_status': 'russian', 'uncertain_phrases': [], 'transcript': 'Я сейчас в школе. Я иду в парк. Встретимся потом в парке.',
                'grammar': {'score': 4, 'reason': 'Clear forms.', 'evidence': ['в школе']},
                'fluency': {'score': None, 'reason': 'This sample is short.', 'evidence': []},
                'goals': [{'id': row['id'], 'status': 'completed', 'evidence': ['в школе']} for row in scenario['goals']],
                'summary': 'Both replies are clear.', 'next_step': 'Keep practising.', 'corrections': [], 'uncertainty': '',
                'criterion_report': {'contract_sha256': curriculum_contract['contract_sha256'], 'judgements': [
                    {'criterion_id': row['id'], 'outcome': 'satisfied', 'score': row['max_score'], 'reason_code': None,
                     'feedback': 'This requested detail is audible.', 'evidence': [
                         {'start_ms': turn['start_ms'], 'end_ms': turn['end_ms']} for turn in recording_turns
                         if turn['turn_id'] in curriculum_contract['content']['criterion_turns'][row['id']]]}
                    for row in curriculum_contract['criteria']]}}
        self.assessor.assess.side_effect = assess

    def test_two_turns_saved_before_review_retry_and_exactly_once_transfer_effects(self):
        state = self.allocate()
        self.assertIn('?run=' + self.run_id, state['origin']['href'])
        self.assertNotIn('prompt', state['current_turn'])
        self.assertEqual(self.send(state).status_code, 409)
        state = self.turn(state)
        self.assertEqual(state['work_state'], 'draft')
        self.assertEqual(self.post(self.path + '/review').status_code, 409)
        state = self.turn(state)
        self.assertIsNone(state['current_turn'])
        self.assertEqual(state['work_state'], 'submitted')
        self.assessor.assess.side_effect = RuntimeError('provider offline')
        self.assertEqual(self.post(self.path + '/review').json['work_state'], 'review_unavailable')
        self.ready_report()
        reviewed = self.post(self.path + '/review')
        self.assertEqual(reviewed.json['work_state'], 'reviewed', reviewed.json)
        self.assertEqual(self.post(self.path + '/review').json, reviewed.json)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_exchange_turns').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)
            validate_saved_evidence(conn)

    def test_unavailable_prompt_never_accepts_a_reply(self):
        state = self.allocate(audio=False)
        self.assertEqual(state['availability'], 'audio_unavailable')
        self.assertEqual(self.post(self.path + '/turns/location/listened',
            {'submission_id': uuid4().hex, 'expected_revision': 0}).status_code, 409)
        self.assertEqual(self.send(state).status_code, 409)
        self.assessor.assess.assert_not_called()

    def test_replay_receipts_obey_authored_limit_and_closing_needs_both_replies(self):
        state = self.allocate()
        self.assertEqual(state['current_turn']['plays_remaining'], 2)
        self.assertEqual(self.client.get(self.path + '/closing-audio').status_code, 409)
        for expected in (1, 0):
            result = self.post(self.path + '/turns/location/listened',
                {'submission_id': uuid4().hex, 'expected_revision': state['revision']})
            self.assertEqual(result.status_code, 200, result.json)
            state = result.json
            self.assertEqual(state['current_turn']['plays_remaining'], expected)
        self.assertEqual(self.post(self.path + '/turns/location/listened',
            {'submission_id': uuid4().hex, 'expected_revision': state['revision']}).status_code, 409)
        state = self.send(state).json
        state = self.turn(state)
        self.assertTrue(state['closing_audio_url'])
        with self.client.get(state['closing_audio_url']) as closing:
            self.assertEqual(closing.status_code, 200)

    def test_ordinary_exchange_preserves_existing_speaking_rewards(self):
        self.turn(self.turn(self.allocate(transfer=False)))
        self.ready_report()
        checked = self.post(self.path + '/review')
        self.assertEqual(checked.json['work_state'], 'reviewed', checked.json)
        self.post(self.path + '/review')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='speaking'").fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            evidence = json.loads(conn.execute("SELECT evidence_json FROM progression_events WHERE activity='speaking'").fetchone()[0])
            self.assertIn('speaking_grammar', evidence['_skill']['scores'])

    def test_uncertain_grammar_is_unscored_and_cannot_award_elo(self):
        self.turn(self.turn(self.allocate(transfer=False)))
        self.ready_report()
        clear = self.assessor.assess.side_effect
        def uncertain(*args, **kwargs):
            result = clear(*args, **kwargs)
            result['uncertain_phrases'] = ['в школе']
            contract = kwargs['curriculum_contract']
            grammar = {c['id'] for c in contract['criteria'] if c['evidence_scope'] == 'spoken_language_use'}
            for row in result['criterion_report']['judgements']:
                if row['criterion_id'] in grammar:
                    row.update(outcome='insufficient_evidence', score=None, reason_code='unclear_audio', evidence=[])
            return result
        self.assessor.assess.side_effect = uncertain
        checked = self.post(self.path + '/review')
        self.assertEqual(checked.json['work_state'], 'reviewed', checked.json)
        self.assertEqual(checked.json['outcome'], 'more_evidence_needed')
        with transaction(self.db) as conn:
            evidence = json.loads(conn.execute("SELECT evidence_json FROM progression_events WHERE activity='speaking'").fetchone()[0])
            self.assertNotIn('_skill', evidence)
            validate_saved_evidence(conn)

    def test_same_spoken_prompts_after_feedback_are_assisted(self):
        self.turn(self.turn(self.allocate()))
        self.ready_report()
        self.assertEqual(self.post(self.path + '/review').json['work_state'], 'reviewed')
        state = self.turn(self.turn(self.allocate(transfer=False)))
        self.assertEqual(state['condition'], 'unverified')
        self.assertEqual(state['support'], ['model_answer'])
        self.assertEqual(self.post(self.path + '/review').json['work_state'], 'reviewed')
        with transaction(self.db) as conn:
            evidence = json.loads(conn.execute("SELECT evidence_json FROM progression_events WHERE activity='speaking'").fetchone()[0])
            self.assertNotIn('_skill', evidence)
            validate_saved_evidence(conn)

    def test_backup_and_import_preserve_private_originals_and_expire_review_lease(self):
        from services.learning_backup import backup_learning_store
        from services.account_import import build_account_import, ImportConflict
        from migrations import upgrade_database
        from repositories import activity_review_repository as reviews
        self.turn(self.turn(self.allocate()))
        with transaction(self.db, write=True) as conn:
            original = dict(conn.execute('SELECT * FROM activity_review_submissions').fetchone())
            reviews.claim(conn, self.owner, original['id'])
        root = Path(self.db).parent
        manifest = backup_learning_store(self.db, self.app.extensions['learning']['assets'], root / 'backup')
        self.assertEqual(len(manifest['unit_exchange_audio']), 4)
        hosted = root / 'hosted.db'; upgrade_database(hosted, backup=False)
        with self.assertRaises(ImportConflict):
            build_account_import(self.db, hosted, root / 'missing-audio.db')
        output = root / 'merged.db'
        report = build_account_import(self.db, hosted, output, local_unit_exchange_audio_root=root / 'unit-exchange-audio')
        self.assertEqual(report['verified_unit_exchange_recordings'], 2)
        with transaction(output) as conn:
            saved = dict(conn.execute('SELECT * FROM activity_review_submissions').fetchone())
            for key in ('original_json', 'task_json', 'contract_json', 'support_receipts_json', 'request_sha256'):
                self.assertEqual(saved[key], original[key])
            self.assertEqual(saved['review_status'], 'review_unavailable')
            self.assertIsNone(saved['review_token'])

    def test_recording_retry_is_idempotent_and_other_profile_cannot_retrieve_audio(self):
        state = self.allocate()
        state = self.post(self.path + '/turns/location/listened', {'submission_id': uuid4().hex, 'expected_revision': state['revision']}).json
        key = uuid4().hex
        first = self.send(state, key=key)
        self.assertEqual(self.send(state, key=key).json, first.json)
        self.assertEqual(self.send(state, key=key, data=recording() + b'changed').status_code, 409)
        url = first.json['turns'][0]['recording_url']
        with self.client.get(url) as response:
            self.assertEqual(response.data, recording())
        changed = self.post('/api/v1/user-session/profiles', {'display_name': 'Other'})
        self.token = changed.json['csrf_token']
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_import_rejects_inconsistent_review_and_keeps_original_audio_evidence(self):
        from copy import deepcopy
        from migrations import upgrade_database
        from services.account_import import build_account_import, ImportConflict
        from services.activity_review_submissions import validate_saved_reviews
        self.turn(self.turn(self.allocate()))
        self.ready_report()
        reviewed = self.post(self.path + '/review')
        self.assertEqual(reviewed.json['work_state'], 'reviewed', reviewed.json)
        root = Path(self.db).parent
        hosted = root / 'hosted.db'; upgrade_database(hosted, backup=False)
        with transaction(self.db) as conn:
            original = dict(conn.execute('SELECT * FROM activity_review_submissions').fetchone())
            canonical = dict(conn.execute('SELECT * FROM activity_criterion_reports').fetchone())
        for change in ('outcome', 'missing_report', 'report', 'support', 'uncertain_grammar', 'audio_source', 'wrong_turn'):
            with self.subTest(change=change):
                altered = deepcopy(json.loads(original['result_json']))
                if change == 'outcome':
                    altered['outcome'] = 'practise_and_retry'
                elif change == 'report':
                    altered['criterion_report']['judgements'][0].update(score=0, outcome='not_satisfied')
                elif change == 'uncertain_grammar':
                    altered['uncertain_phrases'] = ['в школе']
                elif change == 'audio_source':
                    altered['audio_source']['sha256'] = 'a' * 64
                elif change == 'wrong_turn':
                    contract = json.loads(original['contract_json'])
                    first, second = altered['audio_source']['recordings']
                    judgement = next(j for j in altered['criterion_report']['judgements']
                        if contract['content']['criterion_turns'][j['criterion_id']] == [second['turn_id']])
                    judgement['evidence'] = [{'start_ms': first['start_ms'], 'end_ms': first['end_ms']}]
                with transaction(self.db, write=True) as conn:
                    conn.execute('UPDATE activity_review_submissions SET result_json=? WHERE id=?',
                                 (json.dumps(altered), original['id']))
                    if change == 'missing_report':
                        conn.execute('DELETE FROM activity_criterion_reports WHERE id=?', (canonical['id'],))
                    elif change == 'support':
                        conn.execute('UPDATE activity_criterion_reports SET support_json=? WHERE id=?',
                                     (json.dumps(['model_answer']), canonical['id']))
                    elif change == 'wrong_turn':
                        conn.execute('UPDATE activity_criterion_reports SET report_json=? WHERE id=?',
                                     (json.dumps(altered['criterion_report']), canonical['id']))
                with transaction(self.db) as conn:
                    with self.assertRaises(ValueError):
                        validate_saved_reviews(conn, unit_exchange_audio_root=root / 'unit-exchange-audio', require_audio=True)
                output = root / (change + '.db')
                with self.assertRaises(ImportConflict):
                    build_account_import(self.db, hosted, output, local_unit_exchange_audio_root=root / 'unit-exchange-audio')
                self.assertFalse(output.exists())
                with transaction(self.db, write=True) as conn:
                    self.assertEqual(conn.execute('SELECT original_json FROM activity_review_submissions WHERE id=?',
                                                 (original['id'],)).fetchone()[0], original['original_json'])
                    conn.execute('UPDATE activity_review_submissions SET result_json=? WHERE id=?',
                                 (original['result_json'], original['id']))
                    if change == 'missing_report':
                        conn.execute('INSERT INTO activity_criterion_reports VALUES (?,?,?,?,?,?,?,?)', tuple(canonical.values()))
                    elif change == 'support':
                        conn.execute('UPDATE activity_criterion_reports SET support_json=? WHERE id=?',
                                     (canonical['support_json'], canonical['id']))
                    elif change == 'wrong_turn':
                        conn.execute('UPDATE activity_criterion_reports SET report_json=? WHERE id=?',
                                     (canonical['report_json'], canonical['id']))
        output = root / 'valid.db'
        build_account_import(self.db, hosted, output, local_unit_exchange_audio_root=root / 'unit-exchange-audio')
        with transaction(output) as conn:
            saved = dict(conn.execute('SELECT * FROM activity_review_submissions').fetchone())
            for name in ('original_json', 'result_json', 'contract_json', 'task_json', 'support_json', 'support_receipts_json'):
                self.assertEqual(saved[name], original[name])
            self.assertEqual(dict(conn.execute('SELECT * FROM activity_criterion_reports').fetchone()), canonical)

    def test_original_audio_tampering_prevents_review_and_preserves_submission(self):
        state = self.turn(self.turn(self.allocate()))
        with transaction(self.db) as conn:
            manifest = json.loads(conn.execute('SELECT audio_json FROM curriculum_unit_exchange_turns LIMIT 1').fetchone()[0])
        path = Path(self.db).parent / 'unit-exchange-audio' / manifest['filename']
        path.write_bytes(b'changed bytes')
        result = self.post(self.path + '/review').json
        self.assertEqual(result['work_state'], 'review_unavailable')
        self.assessor.assess.assert_not_called()
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_review_submissions').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
