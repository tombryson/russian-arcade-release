"""Owned guided dialogues: immutable answers, explicit providers and honest rewards."""
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock

from migrations import upgrade_database
from public_demo import install_demo
from repositories.learning_repository import transaction, timestamp
from services.ai_trial_budget import TrialDenied
from services.speech_provider import SpeechError
from services.step_conversation import StepConversationService
from tests.support import isolated_app, latest_schema_version, strip_course_progression
from tests.test_conversation import FakeSpeech
from tests.test_step_conversation_ai import dialogue, dialogue_for_scenario


class StepConversationTests(unittest.TestCase):
    def setUp(self):
        self.ai = Mock()
        self.ai.step_dialogue.side_effect = dialogue_for_scenario
        self.speech = FakeSpeech()
        self.app = isolated_app(self, {'ConversationAI': self.ai, 'SpeechProvider': self.speech})
        self.app.config.update(OPENAI_API_KEY='synthetic', ELEVENLABS_API_KEY='synthetic')
        self.client = self.app.test_client()
        state = self.client.get('/api/v1/user-session').json
        self.headers = {'X-CSRF-Token': state['csrf_token'], 'X-Profile-ID': state['profile']['id'],
                        'X-Account-Scope': state['session_scope']}
        self.service = self.app.extensions['learning']['step_conversation']
        self.db = self.app.config['DB_PATH']
        self.addCleanup(self.app.extensions['learning']['conversation'].executor.shutdown)
        self.addCleanup(self.app.extensions['learning']['live_conversation'].executor.shutdown)
        self.addCleanup(self.app.extensions['learning']['live_conversation'].reviews.executor.shutdown)
        self.base = '/api/v1/step-conversations'

    def post(self, path='', body=None, client=None, headers=None):
        return (client or self.client).post(self.base + path, json=body or {}, headers=headers or self.headers)

    def start(self, key='start', scenario='directions', seed=None):
        body = {'submission_id': key, 'scenario_id': scenario, 'target_level': 'A1', 'language': 'en'}
        if seed:
            body['scenario_seed'] = seed
        result = self.post(body=body)
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json['state'], 'active', result.json)
        return result.json

    def saved(self, sid):
        with transaction(self.db) as conn:
            return dict(conn.execute('SELECT * FROM step_conversation_sessions WHERE id=?', (sid,)).fetchone())

    def choice(self, state, correct=True):
        raw = json.loads(self.saved(state['id'])['dialogue_json'])
        turn = next(item for item in raw['turns'] if item['id'] == state['current_turn']['id'])
        return next(item['id'] for item in turn['options'] if item['correct'] == correct)

    def complete(self, state):
        while state['state'] == 'active':
            sid, tid = state['id'], state['current_turn']['id']
            result = self.post('/' + sid + '/answer', {'submission_id': tid, 'turn_id': tid,
                                                     'option_id': self.choice(state)})
            self.assertEqual(result.status_code, 200, result.text)
            result = self.post('/' + sid + '/next', {'turn_id': tid})
            self.assertEqual(result.status_code, 200, result.text)
            state = result.json
        return state

    def test_options_share_catalogue_levels_and_never_generate(self):
        for category in ('cafe', 'shop', 'directions', 'station', 'meet-someone'):
            response = self.client.get(self.base + '/options', query_string={'scenario_id': category, 'level': 'A1'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['scenario']['scenario_id'], category)
            self.assertEqual(response.json['scenario']['target_level'], 'A1')
            self.assertTrue(response.json['configured'])
            self.assertEqual(response.json['sessions'], [])
        unavailable = self.client.get(self.base + '/options?scenario_id=cafe&level=B2').json
        self.assertIsNone(unavailable['scenario'])
        self.assertEqual(unavailable['available_count'], 0)
        self.assertEqual(self.post(body={'submission_id': 'b2', 'scenario_id': 'cafe', 'target_level': 'B2'}).status_code, 409)
        self.ai.step_dialogue.assert_not_called()

    def test_start_stable_hidden_answers_frozen_scenario_and_idempotency(self):
        state = self.start()
        turn = state['current_turn']
        self.assertEqual(len(turn['options']), 3)
        self.assertTrue(all(set(option) == {'id', 'russian'} for option in turn['options']))
        self.assertIsNone(turn['hint'])
        self.assertIsNone(turn['feedback'])
        self.assertEqual(state['transcript'], [])
        self.assertNotIn('ending', state)
        self.assertNotIn('turns', state)
        self.assertNotIn('"correct":', json.dumps(state))
        duplicate = self.start()
        self.assertEqual(duplicate['id'], state['id'])
        self.assertEqual(duplicate['current_turn'], turn)
        self.ai.step_dialogue.assert_called_once()
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE speaking_scenario_variants SET payload_json=json_set(payload_json,'$.title','Later edit') WHERE id=?",
                         (state['scenario']['seed'],))
        read = self.client.get(self.base + '/' + state['id']).json
        self.assertEqual(read['scenario'], state['scenario'])
        self.assertEqual(self.start()['scenario'], state['scenario'])
        self.assertEqual(self.post(body={'submission_id': 'start', 'scenario_id': 'shop', 'target_level': 'A1'}).status_code, 409)
        history = self.client.get(self.base + '/history').json['sessions']
        self.assertEqual([row['id'] for row in history], [state['id']])
        self.assertNotIn('dialogue_json', history[0])

    def test_wrong_hint_correct_and_next_are_persisted_without_revealing_future_turns(self):
        state = self.start()
        sid, tid = state['id'], state['current_turn']['id']
        self.assertEqual(self.post('/' + sid + '/next', {'turn_id': tid}).status_code, 409)
        raw = json.loads(self.saved(sid)['dialogue_json'])
        future_id = raw['turns'][1]['id']
        wrong = {'submission_id': 'wrong', 'turn_id': tid, 'option_id': self.choice(state, False)}
        denied = self.post('/' + sid + '/answer', wrong).json
        self.assertFalse(denied['current_turn']['feedback']['correct'])
        self.assertFalse(denied['current_turn']['answered'])
        self.assertNotIn(future_id, json.dumps(denied))
        self.assertEqual(denied['transcript'], [])
        self.assertEqual(self.post('/' + sid + '/next', {'turn_id': tid}).status_code, 409)
        hinted = self.post('/' + sid + '/hint', {'turn_id': tid}).json
        self.assertEqual(hinted['current_turn']['hint'], raw['turns'][0]['hint'])
        reloaded = self.client.get(self.base + '/' + sid).json
        self.assertEqual(reloaded['current_turn'], hinted['current_turn'])
        right = {'submission_id': 'right', 'turn_id': tid, 'option_id': self.choice(state)}
        answered = self.post('/' + sid + '/answer', right).json
        self.assertTrue(answered['current_turn']['answered'])
        self.assertEqual(answered['current_turn']['id'], tid)
        self.assertEqual(len(answered['transcript']), 1)
        self.assertEqual(self.post('/' + sid + '/answer', right).json, answered)
        self.assertEqual(self.post('/' + sid + '/answer', right | {'option_id': wrong['option_id']}).status_code, 409)
        next_state = self.post('/' + sid + '/next', {'turn_id': tid}).json
        self.assertEqual(next_state['current_turn']['id'], future_id)
        self.assertEqual(next_state['completed_turns'], 1)
        self.assertEqual(self.post('/' + sid + '/next', {'turn_id': tid}).json, next_state)
        self.assertEqual(self.post('/' + sid + '/answer', right).json, next_state)
        self.assertEqual(self.post('/' + sid + '/answer', right | {'submission_id': 'stale'}).status_code, 409)
        self.assertEqual(self.post('/' + sid + '/hint', {'turn_id': tid}).status_code, 409)
        self.ai.step_dialogue.assert_called_once()

    def test_completion_awards_once_per_variant_day_without_speaking_rating(self):
        state = self.start()
        sid = state['id']
        finished = self.complete(state)
        self.assertEqual(finished['state'], 'completed')
        self.assertEqual(finished['completed_turns'], 4)
        self.assertEqual(finished['reward']['amount'], 3)
        self.assertEqual(finished['ending'], dialogue()['ending'])
        self.assertIsNone(finished['current_turn'])
        final_id = finished['transcript'][-1]['id']
        self.assertEqual(self.post('/' + sid + '/next', {'turn_id': final_id}).json, finished)
        self.assertEqual(self.client.get(self.base + '/' + sid).json, finished)
        again = self.complete(self.start('same-variant', seed=state['scenario']['seed']))
        self.assertEqual(again['reward']['amount'], 0)
        with transaction(self.db) as conn:
            rows = conn.execute("SELECT activity,evidence_json FROM progression_events WHERE activity='speaking_step'").fetchall()
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertNotIn('_skill', json.loads(row['evidence_json']))
                self.assertEqual(json.loads(row['evidence_json'])['basis'], 'guided_step_completion')
                coverage = json.loads(row['evidence_json'])['_course']
                self.assertEqual(coverage['topic_id'], 'places')
                self.assertTrue(coverage['assisted'])
            from services.course_progression import course_snapshot
            course = course_snapshot(conn, self.headers['X-Profile-ID'])
            destination = next(chapter for chapter in course['chapters'] if chapter['id'] == 'leavingtown')
            self.assertEqual(destination['status'], 'locked')
            self.assertEqual(destination['topics'], [])
            self.assertEqual(destination['title'], '')
            # Both completions retain their owned source receipt, but replaying
            # the same variant still provides only one distinct practice task.
            evidence = conn.execute('''SELECT c.profile_id,c.topic_id,c.activity,c.content_key,c.score,c.target_level
                FROM course_evidence c JOIN progression_events e ON e.id=c.event_id
                WHERE c.profile_id=? AND e.profile_id=c.profile_id AND e.activity='speaking_step'
                AND e.reversed_at IS NULL''', (self.headers['X-Profile-ID'],)).fetchall()
            self.assertEqual(len(evidence), 2)
            variant = conn.execute('SELECT variant_id FROM step_conversation_sessions WHERE id=?', (sid,)).fetchone()[0]
            self.assertEqual({tuple(row) for row in evidence},
                             {(self.headers['X-Profile-ID'], 'places', 'speaking', variant, 1, 'A1')})
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='speaking'").fetchone()[0], 0)

    def test_start_prepares_only_opening_audio_and_playback_is_owned_and_cached(self):
        state = self.start()
        sid, tid = state['id'], state['current_turn']['id']
        self.assertEqual(len(self.speech.voices), 1)
        self.assertTrue(state['current_turn']['npc_audio_url'])
        self.assertIsNone(state['current_turn']['npc_audio_error'])
        self.assertEqual(self.post('/' + sid + '/audio', {'turn_id': tid, 'kind': 'reply'}).status_code, 404)
        raw = json.loads(self.saved(sid)['dialogue_json'])
        self.assertEqual(self.post('/' + sid + '/audio', {'turn_id': raw['turns'][1]['id'], 'kind': 'npc'}).status_code, 404)
        result = self.post('/' + sid + '/audio', {'turn_id': tid, 'kind': 'npc'})
        self.assertEqual(result.status_code, 200, result.text)
        url = result.json['current_turn']['npc_audio_url']
        self.assertTrue(url)
        audio = self.client.get(url)
        self.addCleanup(audio.close)
        self.assertEqual(audio.status_code, 200)
        self.post('/' + sid + '/audio', {'turn_id': tid, 'kind': 'npc'})
        self.assertEqual(len(self.speech.voices), 1)
        self.post('/' + sid + '/answer', {'submission_id': 'correct', 'turn_id': tid, 'option_id': self.choice(state)})
        reply = self.post('/' + sid + '/audio', {'turn_id': tid, 'kind': 'reply'})
        self.assertTrue(reply.json['current_turn']['reply_audio_url'])
        self.assertEqual(len(self.speech.voices), 2)

    def test_each_advance_prepares_only_new_speaker_line_and_final_farewell(self):
        self.speech.speak = Mock(wraps=self.speech.speak)
        state = self.start()
        sid = state['id']
        raw = json.loads(self.saved(sid)['dialogue_json'])
        self.assertEqual(self.speech.speak.call_args.args[0], raw['turns'][0]['npc']['russian'])
        self.assertEqual(self.post('/' + sid + '/audio', {'turn_id': 'ending', 'kind': 'ending'}).status_code, 404)
        finished = self.complete(state)
        self.assertEqual([call.args[0] for call in self.speech.speak.call_args_list],
                         [turn['npc']['russian'] for turn in raw['turns']] + [raw['ending']['russian']])
        self.assertTrue(finished['ending_audio_url'])
        self.assertIsNone(finished['ending_audio_error'])
        played = self.client.get(finished['ending_audio_url'])
        self.addCleanup(played.close)
        self.assertEqual(played.status_code, 200)
        self.assertEqual(played.data, b'test-only-mp3')
        for _ in range(2):
            self.client.get(self.base + '/' + sid)
            self.post('/' + sid + '/next', {'turn_id': finished['transcript'][-1]['id']})
            self.post('/' + sid + '/audio', {'turn_id': 'ending', 'kind': 'ending'})
        self.assertEqual(self.speech.speak.call_count, len(raw['turns']) + 1)

    def test_automatic_audio_failure_keeps_dialogue_and_waits_for_explicit_retry(self):
        self.speech.speak = Mock(side_effect=SpeechError('Playback is temporarily unavailable.'))
        state = self.start()
        sid, tid = state['id'], state['current_turn']['id']
        self.assertIsNone(state['current_turn']['npc_audio_url'])
        self.assertEqual(state['current_turn']['npc_audio_error'], 'Playback is temporarily unavailable.')
        for _ in range(2):
            self.client.get(self.base + '/' + sid)
            self.client.get(self.base + '/history')
            self.start()
            self.post('/' + sid + '/retry')
        self.speech.speak.assert_called_once()
        self.speech.speak.side_effect = None
        self.speech.speak.return_value = b'test-only-mp3'
        ready = self.post('/' + sid + '/audio', {'turn_id': tid, 'kind': 'npc'}).json
        self.assertTrue(ready['current_turn']['npc_audio_url'])
        self.assertIsNone(ready['current_turn']['npc_audio_error'])
        self.assertEqual(self.speech.speak.call_count, 2)

    def test_audio_allowance_failure_does_not_lose_advance_or_completion_reward(self):
        state = self.start()
        sid = state['id']
        self.speech.speak = Mock(side_effect=TrialDenied('Allowance used.'))
        finished = self.complete(state)
        self.assertEqual(finished['state'], 'completed')
        self.assertEqual(finished['reward']['amount'], 3)
        self.assertEqual(finished['ending_audio_error'], 'Allowance used.')
        self.assertIsNone(finished['ending_audio_url'])
        # One attempt per new line; completed GETs and request replays never retry.
        self.assertEqual(self.speech.speak.call_count, finished['completed_turns'])
        self.client.get(self.base + '/' + sid)
        self.post('/' + sid + '/next', {'turn_id': finished['transcript'][-1]['id']})
        self.assertEqual(self.speech.speak.call_count, finished['completed_turns'])

    def test_text_dialogue_still_works_without_speech_configuration(self):
        self.app.config['ELEVENLABS_API_KEY'] = ''
        state = self.start()
        self.assertFalse(state['audio_configured'])
        self.assertIsNone(state['current_turn']['npc_audio_url'])
        self.complete(state)
        self.assertEqual(self.speech.voices, [])

    def test_failed_generation_retries_only_explicitly_and_trial_denials_remain_429(self):
        self.ai.step_dialogue.side_effect = SpeechError('The step-through dialogue could not be prepared.')
        failed = self.post(body={'submission_id': 'fail', 'scenario_id': 'shop'}).json
        self.assertEqual(failed['state'], 'failed')
        self.assertTrue(failed['retryable'])
        sid = failed['id']
        for _ in range(2):
            self.client.get(self.base + '/' + sid)
            self.client.get(self.base + '/history')
        self.ai.step_dialogue.assert_called_once()
        self.ai.step_dialogue.side_effect = dialogue_for_scenario
        ready = self.post('/' + sid + '/retry').json
        self.assertEqual(ready['state'], 'active')
        self.assertEqual(self.ai.step_dialogue.call_count, 2)
        self.post('/' + sid + '/retry')
        self.assertEqual(self.ai.step_dialogue.call_count, 2)
        self.ai.step_dialogue.side_effect = TrialDenied('Allowance used.')
        denied = self.post(body={'submission_id': 'denied'})
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(denied.json['error']['code'], 'trial_limit')
        self.assertEqual(self.client.get(self.base + '/history').json['sessions'][0]['state'], 'failed')

    def test_restart_recovers_saved_dialogue_and_expired_preparation_without_auto_calls(self):
        state = self.start()
        sid, tid = state['id'], state['current_turn']['id']
        self.post('/' + sid + '/hint', {'turn_id': tid})
        replacement = StepConversationService(self.db, self.speech, self.ai, self.app.config)
        with self.client.session_transaction() as saved_session:
            access = saved_session['personal_access_id']
        read = replacement.read(access, sid)
        self.assertEqual(read['current_turn']['id'], tid)
        self.assertIsNotNone(read['current_turn']['hint'])
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE step_conversation_sessions SET state='preparing',dialogue_json=NULL,lease_until=? WHERE id=?", (timestamp() - 1, sid))
        waiting = replacement.read(access, sid)
        self.assertTrue(waiting['retryable'])
        self.ai.step_dialogue.assert_called_once()
        self.assertEqual(replacement.retry(access, sid)['state'], 'active')
        self.assertEqual(self.ai.step_dialogue.call_count, 2)

    def test_new_profile_cannot_read_modify_or_play_another_session(self):
        state = self.start()
        sid, tid = state['id'], state['current_turn']['id']
        audio = self.post('/' + sid + '/audio', {'turn_id': tid, 'kind': 'npc'}).json['current_turn']['npc_audio_url']
        other = self.app.test_client()
        token = other.get('/api/v1/user-session').json['csrf_token']
        profile = other.post('/api/v1/user-session/profiles', json={'display_name': 'Other'}, headers={'X-CSRF-Token': token}).json
        headers = {'X-CSRF-Token': profile['csrf_token'], 'X-Profile-ID': profile['profile']['id'], 'X-Account-Scope': 'local'}
        self.assertEqual(other.get(self.base + '/' + sid).status_code, 404)
        self.assertEqual(other.get(audio).status_code, 404)
        for suffix, body in (('/answer', {'submission_id': 'other', 'turn_id': tid, 'option_id': self.choice(state)}),
                             ('/hint', {'turn_id': tid}), ('/next', {'turn_id': tid}), ('/retry', {}),
                             ('/audio', {'turn_id': tid, 'kind': 'npc'})):
            self.assertEqual(self.post('/' + sid + suffix, body, client=other, headers=headers).status_code, 404)
        self.assertEqual(other.get(self.base + '/history').json['sessions'], [])
        self.assertEqual(self.client.post(self.base + '/' + sid + '/hint', json={'turn_id': tid}).status_code, 403)
        self.assertEqual(self.client.get(self.base + '/' + sid, headers={'X-Account-Scope': 'preview'}).status_code, 409)

    def test_hosted_accounts_only_and_public_preview_fail_closed(self):
        self.app.config.update(HOSTED_AI_TRIAL=True, AI_TRIAL_ENABLED=False, AI_TRIAL_IDENTITY='github:11')
        self.assertFalse(self.client.get(self.base + '/options').json['configured'])
        denied = self.post(body={'submission_id': 'hosted-denied'}, headers={'X-CSRF-Token': self.headers['X-CSRF-Token']})
        self.assertEqual(denied.status_code, 429, denied.text)
        self.ai.step_dialogue.assert_not_called()
        self.assertEqual(self.speech.voices, [])

    def test_public_demo_allows_free_options_and_blocks_all_new_mutations(self):
        # Installation belongs before the first request, as in hosted.py.
        preview = isolated_app(self, {'ConversationAI': self.ai, 'SpeechProvider': self.speech}, signed_in=False)
        preview.config.update(PUBLIC_DEMO=True, OPENAI_API_KEY='must-not-enable-preview')
        install_demo(preview)
        visitor = preview.test_client()
        options = visitor.get(self.base + '/options')
        self.assertEqual(options.status_code, 200, options.text)
        self.assertFalse(options.json['configured'])
        self.assertEqual(visitor.get(self.base + '/history').json['sessions'], [])
        token = visitor.get('/api/v1/user-session').json['csrf_token']
        for path in ('', '/forged/answer', '/forged/hint', '/forged/next', '/forged/retry', '/forged/audio'):
            self.assertEqual(visitor.post(self.base + path, json={'submission_id': 'demo'},
                                         headers={'X-CSRF-Token': token}).status_code, 403)
        self.ai.step_dialogue.assert_not_called()

    def test_migration_adds_relations_without_rewriting_existing_records(self):
        self.start()
        with sqlite3.connect(self.db) as conn:
            strip_course_progression(conn)
            before = conn.execute('SELECT * FROM words ORDER BY id').fetchall()
            profiles = conn.execute('SELECT * FROM learning_profiles ORDER BY id').fetchall()
            conn.execute('DROP TABLE step_conversation_answers')
            conn.execute('DROP TABLE step_conversation_sessions')
            conn.execute('DROP TABLE IF EXISTS speaking_scenario_levels')
            conn.execute('DELETE FROM schema_migrations WHERE version>=41')
        version, backup = upgrade_database(self.db)
        self.assertEqual(version, latest_schema_version())
        self.assertTrue(backup)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT * FROM words ORDER BY id').fetchall(), before)
            self.assertEqual(conn.execute('SELECT * FROM learning_profiles ORDER BY id').fetchall(), profiles)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM step_conversation_sessions').fetchone()[0], 0)
            self.assertEqual({row[2] for row in conn.execute('PRAGMA foreign_key_list(step_conversation_sessions)')},
                             {'learning_profiles', 'speaking_scenarios', 'speaking_scenario_variants'})

    def test_backup_includes_prepared_step_audio_with_checksums(self):
        from services.learning_backup import backup_learning_store
        state = self.start()
        sid, tid = state['id'], state['current_turn']['id']
        self.post('/' + sid + '/audio', {'turn_id': tid, 'kind': 'npc'})
        destination = Path(self.db).parent / 'step-snapshot'
        manifest = backup_learning_store(self.db, self.app.extensions['learning']['assets'], destination)
        self.assertEqual(len(manifest['step_conversation_audio']), 1)
        item = manifest['step_conversation_audio'][0]
        self.assertEqual((destination / item['file']).read_bytes(), b'test-only-mp3')
        self.assertEqual(len(item['sha256']), 64)
        with sqlite3.connect(destination / 'vocab.db') as conn:
            self.assertEqual(conn.execute('SELECT dialogue_json FROM step_conversation_sessions WHERE id=?', (sid,)).fetchone()[0],
                             self.saved(sid)['dialogue_json'])

    def test_malformed_input_and_generated_choices_are_not_saved_as_playable(self):
        for body in ({'submission_id': 'bad', 'scenario_id': []}, {'submission_id': 'bad', 'target_level': 'C1'},
                     {'submission_id': 'bad', 'correct_option_id': 'client-choice'}):
            self.assertEqual(self.post(body=body).status_code, 400)
        self.ai.step_dialogue.assert_not_called()
        invalid = dialogue()
        invalid['turns'][0]['distractors'][0] = invalid['turns'][0]['correct']
        self.ai.step_dialogue.side_effect = lambda _: invalid
        result = self.post(body={'submission_id': 'invalid-generated'})
        self.assertEqual(result.json['state'], 'failed')
        self.assertIsNone(result.json['current_turn'])
        self.assertIsNone(self.saved(result.json['id'])['dialogue_json'])

    def test_curriculum_evidence_is_saved_but_never_sent_to_the_player(self):
        state = self.start()
        raw = json.loads(self.saved(state['id'])['dialogue_json'])
        self.assertTrue(raw['coverage'])
        for response in (state, self.client.get(self.base + '/' + state['id']).json,
                         self.client.get(self.base + '/history').json):
            self.assertNotIn('"coverage"', json.dumps(response))
            self.assertNotIn('"requirement_id"', json.dumps(response))
        answer = self.post('/' + state['id'] + '/answer', {
            'submission_id': 'coverage-answer', 'turn_id': state['current_turn']['id'],
            'option_id': self.choice(state)})
        self.assertEqual(answer.status_code, 200)
        self.assertNotIn('"coverage"', json.dumps(answer.json))

    def test_missing_curriculum_evidence_cannot_publish_or_prepare_audio(self):
        self.ai.step_dialogue.side_effect = lambda _: dialogue()
        result = self.post(body={'submission_id': 'missing-coverage', 'scenario_id': 'shop', 'target_level': 'A2'})
        self.assertEqual(result.status_code, 201, result.json)
        self.assertEqual(result.json['state'], 'failed')
        self.assertIsNone(result.json['current_turn'])
        self.assertIsNone(self.saved(result.json['id'])['dialogue_json'])
        self.assertEqual(self.speech.voices, [])
        self.ai.step_dialogue.assert_called_once()


if __name__ == '__main__':
    unittest.main()
