"""Owned generated practice uses normal saved sessions, support and rewards."""
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from pydub.generators import Sine

from repositories.learning_repository import transaction
from services.curriculum_situation_content import validate_output
from tests.support import isolated_app
from tests.test_curriculum_situation_content import legacy_build_request, situation_response


class CurriculumSituationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with io.BytesIO() as stream:
            Sine(330).to_audio_segment(duration=1500).export(stream, format='mp3')
            cls.recording = stream.getvalue()

    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.service = self.app.extensions['learning']['curriculum_situations']
        self.service.speech = SimpleNamespace(voice_ids=('configured-one', 'configured-two'),
            model='configured_model', api_key='test-not-a-real-key', config={})
        self.identity = self.client.get('/api/v1/user-session').json
        self.token = self.identity['csrf_token']
        self.profile_id = self.identity['profile']['id']
        with self.client.session_transaction() as state:
            self.access = state['personal_access_id']
        # These provider-free lifecycle tests retain their original authored
        # source-v2/v5 passages. New v6 language quality is tested separately;
        # do not weaken its validator to admit this old synthetic passage.
        self.request_factory = patch('services.curriculum_situation_content.build_request',
                                     side_effect=legacy_build_request).start()
        self.generation = patch('services.curriculum_situation_content.generate', side_effect=self.generate).start()
        self.addCleanup(patch.stopall)
        self.audio_factory = patch('services.curriculum_generated_audio.ElevenLabsService', side_effect=self.speech).start()
        self.speech_texts = []

    def generate(self, request, provider):
        # A second writer fails instantly if the provider is accidentally called
        # under BEGIN IMMEDIATE. Paid latency cannot hold the learner's DB lock.
        with sqlite3.connect(self.db, timeout=0) as conn:
            conn.execute('BEGIN IMMEDIATE')
        return validate_output(request, situation_response(request))

    def speech(self, key, directory, **kwargs):
        service = Mock()
        def make(text, filename):
            with sqlite3.connect(self.db, timeout=0) as conn:
                conn.execute('BEGIN IMMEDIATE')
            self.speech_texts.append(text)
            (Path(directory) / filename).write_bytes(self.recording)
            return filename
        service.generate_audio.side_effect = make
        return service

    def post(self, path, body, *, status=200):
        response = self.client.post(path, json=body, headers={'X-CSRF-Token': self.token})
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        return response.json

    def start(self, mode='reading', request_id=None, unit='present-actions-v1', *, status=303):
        response = self.client.post('/curriculum/units/' + unit + '/situations',
            data={'mode': mode, 'request_id': request_id or uuid4().hex, 'profile_id': self.profile_id},
            headers={'X-CSRF-Token': self.token})
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        if status != 303:
            return response
        if '#practice/' in response.location:
            return {'url': response.location, 'state': 'ready'}
        sid = response.location.rsplit('/', 1)[-1]
        return self.client.get('/api/v1/curriculum/situations/' + sid).json

    def prepare(self, state, retry=False, *, status=200):
        return self.post('/api/v1/curriculum/situations/' + state['id'] + '/prepare', {'retry': retry}, status=status)

    def row(self, state):
        with transaction(self.db) as conn:
            return dict(conn.execute('SELECT * FROM curriculum_situations WHERE id=?', (state['id'],)).fetchone())

    def player(self, state):
        self.assertEqual(state['state'], 'ready', state)
        session_id = state['url'].rsplit('/', 1)[-1]
        response = self.client.get('/api/v1/learning-sessions/' + session_id)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json

    def pack(self, session):
        with transaction(self.db) as conn:
            return json.loads(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?',
                                           (session['version_id'],)).fetchone()[0])

    def command(self, state, operation, **body):
        return self.post('/api/v1/learning-sessions/' + state['id'] + '/' + operation,
            {'submission_id': uuid4().hex, 'expected_revision': state['revision'],
             'item_id': state['item']['id'], **body})

    def complete(self, state, pack):
        for item in pack['items']:
            if item['type'] == 'listening_choice':
                state = self.command(state, 'listened')
            state = self.command(state, 'attempts', answer={'choice_id': item['answer']})
        self.assertEqual(state['status'], 'completed')
        return state

    def test_start_is_idempotent_and_gets_never_call_providers(self):
        state = self.start(request_id='one-start')
        self.assertEqual(state['state'], 'pending')
        self.assertEqual(self.start(request_id='one-start'), state)
        self.assertEqual(self.start(request_id='other-tab'), state)
        page = self.client.get('/curriculum/situations/' + state['id'])
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'data-situation-preparation', page.data)
        self.assertIn(b'curriculum_situation.js', page.data)
        self.assertNotIn(b'configured_model', page.data)
        self.assertNotIn(b'goal_en', page.data)
        self.assertEqual(self.service.read(self.access, state['id']), state)
        self.generation.assert_not_called()
        self.audio_factory.assert_not_called()
        row = self.row(state)
        self.assertEqual((row['text_attempts'], row['audio_attempts']), (0, 0))
        self.start(mode='listening', request_id='one-start', status=409)

    def test_post_requires_csrf_and_exact_retry_shape(self):
        state = self.start()
        endpoint = '/api/v1/curriculum/situations/' + state['id'] + '/prepare'
        self.assertEqual(self.client.post(endpoint, json={'retry': False}).status_code, 403)
        for body in ({}, {'retry': 'false'}, {'retry': False, 'model': 'another-model'}):
            with self.subTest(body=body):
                self.post(endpoint, body, status=400)
        self.generation.assert_not_called()

    def test_published_reading_uses_saved_answers_evidence_and_daily_reward_identity(self):
        state = self.prepare(self.start())
        saved = self.player(state)
        self.assertNotIn('answer', saved['item'])
        self.assertNotIn('evidence', saved['item'])
        self.assertNotIn('plan', saved['item'])
        pack = self.pack(saved)
        self.assertEqual(len(pack['items']), 3)
        self.assertEqual(saved['item']['passage'], pack['items'][0]['passage'])
        self.assertEqual(saved['item']['prompt'], 'Where is Anna now?')
        self.assertNotIn(saved['item']['passage'], saved['item']['prompt'])
        self.complete(saved, pack)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts WHERE session_id=?', (saved['id'],)).fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports WHERE profile_id=?', (self.profile_id,)).fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_continuation_entitlements').fetchone()[0], 0)
            contracts = [json.loads(row[0]) for row in conn.execute('SELECT contract_json FROM activity_task_contracts')]
            self.assertEqual(len(contracts), 3)
            self.assertTrue(all(c['purpose'] == 'practice' for c in contracts))
            self.assertTrue(all(c['criteria'][0]['requirement_id'].startswith('a1.reading.') for c in contracts))
        self.generation.assert_called_once()
        self.audio_factory.assert_not_called()
        self.assertEqual(self.prepare(state), state)
        # A subsequent reading/listening variant belongs to the same lesson's
        # reward identity; generated seeds cannot farm another daily reward.
        from services.curriculum_fresh_practice import reward_family
        self.assertEqual(reward_family(pack['id']), 'curriculum-unit:present-actions-v1')

    def test_other_profile_cannot_read_prepare_or_generic_start_a_private_generation(self):
        pending = self.start()
        state = self.prepare(pending)
        saved = self.player(state)
        other = self.post('/api/v1/user-session/profiles', {'display_name': 'Another learner'}, status=201)
        profile = other['profile']['id']
        self.token = other['csrf_token']
        for endpoint in ('/api/v1/curriculum/situations/' + pending['id'],
                         '/api/v1/learning-sessions/' + saved['id']):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.prepare(pending, status=404)
        self.post('/api/v1/learning-sessions', {'profile_id': profile, 'version_id': saved['version_id'],
                  'submission_id': uuid4().hex}, status=404)
        self.assertEqual(self.generation.call_count, 1)

    def test_owner_returns_to_lesson_instead_of_replaying_an_answer_key_as_new_evidence(self):
        saved = self.player(self.prepare(self.start()))
        result = self.post('/api/v1/learning-sessions', {'profile_id': self.profile_id,
            'version_id': saved['version_id'], 'submission_id': uuid4().hex}, status=409)
        self.assertEqual(result['error']['code'], 'use_lesson')
        self.assertEqual(self.client.get('/api/v1/learning-sessions/' + saved['id']).status_code, 200)
        self.generation.assert_called_once()

    def test_failure_is_sanitized_and_requires_explicit_retry_with_a_cap(self):
        state = self.start()
        self.generation.side_effect = RuntimeError('secret-provider-detail-not-for-client')
        first = self.prepare(state)
        self.assertEqual(first['state'], 'failed')
        self.assertTrue(first['retryable'])
        self.assertEqual(first['error'], 'preparation_failed')
        self.assertNotIn('secret-provider', json.dumps(first))
        self.prepare(state)
        self.client.get('/api/v1/curriculum/situations/' + state['id'])
        self.assertEqual(self.generation.call_count, 1)
        for _ in range(2):
            last = self.prepare(state, retry=True)
        self.assertFalse(last['retryable'])
        self.assertEqual(self.generation.call_count, 3)
        self.prepare(state, retry=True, status=429)
        self.assertEqual(self.generation.call_count, 3)
        self.assertIsNone(self.row(state)['document_json'])

    def test_audio_retry_retains_text_and_selected_voice_and_complete_playback(self):
        pending = self.start(mode='listening')
        waiting = self.prepare(pending)
        self.assertEqual((waiting['state'], waiting['stage']), ('pending', 'audio'))
        original_document = self.row(waiting)['document_json']
        self.audio_factory.side_effect = RuntimeError('speech failed')
        failed = self.prepare(waiting)
        self.assertEqual((failed['state'], failed['stage']), ('failed', 'audio'))
        selected_voice = self.row(failed)['voice_json']
        self.assertIsNotNone(selected_voice)
        self.prepare(failed)
        self.assertEqual(self.audio_factory.call_count, 1)
        self.service.speech.voice_ids = ('different-voice-now',)
        self.audio_factory.side_effect = self.speech
        ready = self.prepare(failed, retry=True)
        row = self.row(ready)
        self.assertEqual(row['document_json'], original_document)
        self.assertEqual(row['voice_json'], selected_voice)
        self.assertEqual((row['text_attempts'], row['audio_attempts']), (1, 2))
        self.generation.assert_called_once()
        saved = self.player(ready)
        pack = self.pack(saved)
        self.assertIsNone(saved['item'].get('transcript'))
        self.assertNotIn('storage_key', json.dumps(saved))
        with self.client.get(saved['item']['audio']['url']) as clip:
            self.assertEqual(clip.status_code, 200)
            self.assertEqual(clip.data, self.recording)
        first = self.command(saved, 'listened')
        answered = self.command(first, 'attempts', answer={'choice_id': pack['items'][0]['answer']})
        self.assertNotIn(pack['items'][0]['transcript'], json.dumps(answered, ensure_ascii=False))
        with transaction(self.db) as conn:
            first_receipt = tuple(conn.execute('SELECT * FROM learning_item_support WHERE session_id=? AND item_id=?',
                (saved['id'], pack['items'][0]['id'])).fetchone())
        for item in pack['items'][1:]:
            self.assertTrue(answered['item']['listened'])
            self.assertIsNone(answered['item']['transcript'])
            restored = self.client.get('/api/v1/learning-sessions/' + saved['id']).json
            self.assertTrue(restored['item']['listened'])
            answered = self.command(restored, 'attempts', answer={'choice_id': item['answer']})
        self.assertEqual(answered['status'], 'completed')
        self.assertTrue(all(not attempt['feedback']['assisted'] for attempt in answered['attempts']))
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute('SELECT * FROM learning_item_support WHERE session_id=? AND item_id=?',
                (saved['id'], pack['items'][0]['id'])).fetchone()), first_receipt)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM learning_commands WHERE session_id=? AND payload_hash IS NOT NULL",
                (saved['id'],)).fetchone()[0], 4)  # One listened receipt and three answers.
            from services.learning_listening import validate_saved_support
            validate_saved_support(conn)

    def test_audio_failure_can_resume_when_text_used_its_last_attempt(self):
        state = self.start(mode='listening')
        self.generation.side_effect = RuntimeError('text unavailable')
        self.prepare(state)
        self.prepare(state, retry=True)
        self.generation.side_effect = self.generate
        waiting = self.prepare(state, retry=True)
        self.assertEqual(self.row(waiting)['text_attempts'], 3)
        self.audio_factory.side_effect = RuntimeError('speech unavailable')
        failed = self.prepare(waiting)
        self.assertTrue(failed['retryable'])
        resumed = self.start(mode='listening')
        self.assertEqual(resumed['id'], state['id'])
        self.assertEqual(self.row(resumed)['document_json'], self.row(waiting)['document_json'])
        self.assertEqual(self.generation.call_count, 3)

    def test_pending_and_failed_audio_text_is_not_semantic_exposure(self):
        from services.curriculum_situation_content import build_request, resolve_source_references
        from services.curriculum_units import get_unit
        from tests.test_curriculum_situation_content import meaning_provider_response
        self.generation.side_effect = lambda request, provider: validate_output(
            request, resolve_source_references(request, meaning_provider_response(request)))
        waiting = self.prepare(self.start(mode='listening', unit='location-destination-v1'))
        self.assertEqual((waiting['state'], waiting['stage']), ('pending', 'audio'))
        self.assertIsNotNone(self.row(waiting)['document_json'])
        for expected in ('pending', 'failed'):
            with self.subTest(state=expected):
                if expected == 'failed':
                    self.audio_factory.side_effect = RuntimeError('synthetic audio failure')
                    waiting = self.prepare(waiting)
                    self.assertEqual(waiting['state'], 'failed')
                started = self.start(unit='location-destination-v1')
                request = json.loads(self.row(started)['request_json'])
                self.assertEqual(request['recent'], [])
                unexposed = build_request(get_unit('location-destination-v1'), request['seed'], mode='reading')
                self.assertEqual(request['language_plan']['family_id'], unexposed['language_plan']['family_id'])
                # Permit another explicit reading start without issuing this
                # synthetic pending task or consuming another text call.
                with transaction(self.db, write=True) as conn:
                    conn.execute("UPDATE curriculum_situations SET state='failed',text_attempts=3 WHERE id=?", (started['id'],))

    def test_other_units_do_not_crowd_out_issued_semantic_exposure(self):
        from services.curriculum_situation_content import resolve_source_references
        from tests.test_curriculum_situation_content import meaning_provider_response
        self.generation.side_effect = lambda request, provider: validate_output(
            request, resolve_source_references(request, meaning_provider_response(request)))
        ready = self.prepare(self.start(unit='location-destination-v1'))
        issued = self.row(ready)
        saved = self.player(ready)
        self.complete(saved, self.pack(saved))
        prior_family = json.loads(issued['document_json'])['request']['language_plan']['family_id']
        self.generation.side_effect = self.generate
        other = self.prepare(self.start(unit='present-actions-v1'))
        self.assertEqual(other['state'], 'ready')
        # Seed a busy profile's other issued history beyond the global limit.
        # Only chronology matters here; retain a real accepted document and
        # owned session rather than pretending a failed preparation was seen.
        with transaction(self.db, write=True) as conn:
            conn.execute('UPDATE curriculum_situations SET created_at=created_at-7200 WHERE id IN (?,?)', (ready['id'], other['id']))
            for index in range(13):
                now = issued['created_at'] - 7200 + index + 1
                conn.execute(
                    'INSERT INTO curriculum_situations(id,profile_id,unit_id,mode,request_json,document_json,state,stage,session_id,created_at,updated_at) '
                    'SELECT ?,profile_id,unit_id,mode,request_json,document_json,state,stage,session_id,?,? FROM curriculum_situations WHERE id=?',
                    ('other-history-' + str(index), now, now, other['id']))
        next_state = self.start(mode='listening', unit='location-destination-v1')
        request = json.loads(self.row(next_state)['request_json'])
        self.assertEqual(len(request['recent']), 1)
        self.assertEqual(request['recent'][0]['family_id'], prior_family)
        self.assertNotEqual(request['language_plan']['family_id'], prior_family)

    def test_post_budget_denial_keeps_saved_status_and_never_retries_on_poll(self):
        from services.ai_trial_budget import TrialDenied
        state = self.start()
        self.generation.side_effect = TrialDenied('test_limit', 'Provider quota detail', 429)
        failed = self.prepare(state)
        self.assertEqual(failed['error'], 'allowance_unavailable')
        self.client.get('/api/v1/curriculum/situations/' + state['id'])
        self.prepare(state)
        self.generation.assert_called_once()

    def test_live_claim_prevents_a_second_provider_call(self):
        state = self.start()
        seen = []
        def concurrent(request, provider):
            seen.append(self.service.advance(self.access, state['id'], retry=True))
            return self.generate(request, provider)
        self.generation.side_effect = concurrent
        ready = self.prepare(state)
        self.assertEqual(ready['state'], 'ready')
        self.assertEqual(seen[0]['state'], 'running')
        self.generation.assert_called_once()

    def test_expired_claim_needs_an_explicit_retry_and_old_worker_cannot_publish(self):
        state = self.start()
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE curriculum_situations SET state='running',claim_id='old-worker',lease_until=0,text_attempts=1 WHERE id=?", (state['id'],))
        current = self.client.get('/api/v1/curriculum/situations/' + state['id']).json
        self.assertEqual(current['state'], 'failed')
        self.assertEqual(current['error'], 'preparation_interrupted')
        self.prepare(state)
        self.generation.assert_not_called()
        def lost_claim(request, provider):
            with transaction(self.db, write=True) as conn:
                conn.execute("UPDATE curriculum_situations SET claim_id='replacement-worker' WHERE id=?", (state['id'],))
            return self.generate(request, provider)
        self.generation.side_effect = lost_claim
        self.prepare(state, retry=True, status=409)
        self.assertIsNone(self.row(state)['session_id'])
        self.assertIsNone(self.row(state)['document_json'])

    def test_six_new_jobs_per_hour_limit_and_input_immutability(self):
        for _ in range(6):
            state = self.start()
            with transaction(self.db, write=True) as conn:
                conn.execute("UPDATE curriculum_situations SET state='failed',text_attempts=3 WHERE id=?", (state['id'],))
        self.start(status=429)
        self.generation.assert_not_called()
        with transaction(self.db, write=True) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE curriculum_situations SET request_json='{}' WHERE id=?", (state['id'],))

    def test_unit_exposes_explicit_generation_without_generating_on_navigation(self):
        response = self.client.get('/curriculum/units/present-actions-v1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'/curriculum/units/present-actions-v1/situations', response.data)
        self.assertIn(b'name="mode" value="reading"', response.data)
        self.assertIn(b'name="mode" value="listening"', response.data)
        self.generation.assert_not_called()
        self.audio_factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
