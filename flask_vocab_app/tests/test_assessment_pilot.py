"""Provider-free five-domain lifecycle, original media and request boundaries."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
import wave

from repositories.learning_repository import encoded
from services.assessment_pilot import digest, make_report
from services.assessment_pilot_content import blueprint
from services.assessment_pilot_integrity import validate_saved_pilot
from tests.support import isolated_app, select_test_profile

BASE = '/api/v1/assessment-pilot'


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\x12\x00' * 24000)
    return buffer.getvalue()


def criterion_report(contract, text=None):
    evidence = [{'quote': text, 'start': 0, 'end': len(text)}] if text is not None else [{'start_ms': 0, 'end_ms': 800}]
    return {'contract_sha256': contract['contract_sha256'], 'judgements': [
        {'criterion_id': item['id'], 'outcome': 'satisfied', 'score': item['max_score'],
         'feedback': 'This response supplies the requested meaning.', 'evidence': evidence}
        for item in contract['criteria']]}


def speaking_feedback(contract):
    text = 'Меня зовут Анна. Я живу в Москве. Я учусь и люблю читать книги.'
    return {'transcript': text, 'speech_status': 'russian', 'uncertain_phrases': [],
            'grammar': {'score': 4, 'reason': 'Your introduction is clear.', 'evidence': ['Я живу в Москве.']},
            'fluency': {'score': 4, 'reason': 'Your message is easy to follow.', 'evidence': ['Я учусь и люблю читать книги.']},
            'goals': [{'id': 'objective-1', 'status': 'completed', 'evidence': [text]}],
            'summary': 'Your introduction is understandable.', 'next_step': 'Try another introduction.',
            'corrections': [], 'uncertainty': '', 'model': 'offline-speaking-fixture',
            'basis': 'audio_review', 'rubric_version': 'speaking-audio-v1', 'rewards_applied': False,
            'assessment_provenance': {'model': 'offline-speaking-fixture', 'prompt_sha256': '2' * 64, 'rubric_version': 'speaking-audio-v1'},
            'criterion_report': criterion_report(contract)}


class AssessmentPilotTests(unittest.TestCase):
    def setUp(self):
        self.writing = Mock()
        self.writing.assess_writing.side_effect = lambda task, words, target, response, **kwargs: {
            'score': 8, 'strength': 'A clear message.', 'next_step': 'Try another context.', 'example': 'До встречи!',
            'assessment_provenance': {'model': 'offline-writing-fixture', 'prompt_sha256': '1' * 64, 'rubric_version': 'writing-feedback-v1'},
            'criterion_report': criterion_report(kwargs['curriculum_contract'], response)}
        self.speaking = Mock()
        self.speaking.assess.side_effect = lambda path, scenario, dialogue, language, **kwargs: speaking_feedback(kwargs['curriculum_contract'])
        self.app = isolated_app(self, {'WritingService': self.writing, 'SpeakingAssessment': self.speaking})
        self.service = self.app.extensions['learning']['assessment_pilot']
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.service.static = Path(temporary.name)
        audio_root = self.service.static / 'audio/course/assessment-pilot'; audio_root.mkdir(parents=True)
        clips = {}
        for task in blueprint()['forms']['listening']:
            identity = 'a1-pilot-' + task['form_id'] + '-v1'
            data = b'ID3 offline-only source fixture ' + identity.encode()
            (audio_root / (identity + '.mp3')).write_bytes(data)
            clips[identity] = {'audio_sha256': digest(data), 'text_sha256': digest(task['transcript'].encode()), 'duration': 12.0}
        (audio_root / 'manifest.json').write_text(json.dumps({'clips': clips}))
        self.client = self.app.test_client()
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']
        self.db = self.app.config['DB_PATH']

    def connection(self):
        conn = sqlite3.connect(self.db); conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    def start(self, submission_id=None):
        result = self.client.post(BASE + '/sessions', json={'submission_id': submission_id or uuid4().hex})
        self.assertEqual(result.status_code, 200, result.json)
        return result.json

    def component(self, saved, domain):
        return next(item for item in saved['components'] if item['domain'] == domain)

    def request(self, saved, domain, action, **values):
        component = self.component(saved, domain)
        body = {'submission_id': uuid4().hex, 'component_id': component['id'], **values}
        if action != 'review':
            body.setdefault('expected_revision', component['revision'])
        return self.client.post(BASE + '/sessions/' + saved['id'] + '/components/' + domain + '/' + action, json=body)

    def answers(self, saved, domain):
        with self.connection() as conn:
            raw = conn.execute('SELECT task_json FROM assessment_pilot_components WHERE id=?', (self.component(saved, domain)['id'],)).fetchone()[0]
        return {'answers': {item['id']: item['answer'] for item in json.loads(raw)['items']}}

    def upload(self, saved, *, submission_id=None, audio=None, component=None):
        component = component or self.component(saved, 'speaking')
        return self.client.post(BASE + '/sessions/' + saved['id'] + '/components/speaking/attempts', data={
            'submission_id': submission_id or uuid4().hex, 'component_id': component['id'], 'expected_revision': str(component['revision']),
            'audio': (io.BytesIO(wav_bytes() if audio is None else audio), 'original.wav')})

    def test_all_five_components_complete_with_original_evidence_and_no_rewards(self):
        saved = self.start()
        self.assertEqual(len(saved['components']), 5)
        with self.connection() as conn:
            coins = conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0]
        for domain in ('language_use', 'reading'):
            reply = self.request(saved, domain, 'attempts', response=self.answers(saved, domain))
            self.assertEqual(reply.status_code, 200, reply.json); saved = reply.json
        saved = self.request(saved, 'listening', 'support', kind='listened').json
        saved = self.request(saved, 'listening', 'attempts', response=self.answers(saved, 'listening')).json
        raw = '  Привет! Давай встретимся в парке в субботу. Ты можешь прийти?\n'
        saved = self.request(saved, 'writing', 'attempts', response={'text': raw}).json
        reply = self.upload(saved)
        self.assertEqual(reply.status_code, 200, reply.json); saved = reply.json
        self.assertEqual(saved['status'], 'complete')
        self.assertTrue(all(item['attempt']['outcome'] == 'demonstrated_in_task' for item in saved['components']))
        self.assertEqual(self.component(saved, 'writing')['attempt']['response'], {'text': raw})
        audio = self.client.get(self.component(saved, 'speaking')['attempt']['recording_url'])
        self.assertEqual(audio.data, wav_bytes()); self.assertIn('private, no-store', audio.headers['Cache-Control'])
        audio.close()
        self.assertIn('grammar', self.component(saved, 'speaking')['attempt']['production_feedback'])
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], coins)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            before = conn.total_changes
            validate_saved_pilot(conn, audio_root=self.service.root, require_audio=True)
            self.assertEqual(conn.total_changes, before)

    def test_sources_answer_keys_and_transcript_are_hidden_until_explicit_support(self):
        saved = self.start(); component = self.component(saved, 'listening')
        serial = json.dumps(saved, ensure_ascii=False)
        self.assertNotIn(blueprint()['forms']['listening'][0]['transcript'], serial)
        for item in saved['components']:
            self.assertNotIn('contract', item); self.assertNotIn('audio', item)
            for question in item.get('questions', []):
                self.assertEqual(set(question), {'id', 'prompt', 'choices'})
        self.assertEqual(self.request(saved, 'listening', 'attempts', response=self.answers(saved, 'listening')).status_code, 409)
        audio = self.client.get(component['audio_url'])
        self.assertEqual(audio.status_code, 200); self.assertIn('private, no-store', audio.headers['Cache-Control'])
        audio.close()
        transcript = self.request(saved, 'listening', 'support', kind='transcript')
        self.assertEqual(transcript.status_code, 200)
        self.assertEqual(self.component(transcript.json, 'listening')['passage'], blueprint()['forms']['listening'][0]['transcript'])
        checked = self.request(transcript.json, 'listening', 'attempts', response=self.answers(saved, 'listening')).json
        result = self.component(checked, 'listening')['attempt']
        self.assertEqual(result['outcome'], 'more_evidence_needed')
        self.assertEqual(result['support'], ['transcript'])
        self.assertTrue(all(item['score'] is None for item in result['criteria']))

    def test_missing_recordings_do_not_block_other_skills_or_invent_a_listening_result(self):
        path = self.service.static / 'audio/course/assessment-pilot/a1-pilot-a-v1.mp3'
        original = path.read_bytes(); path.unlink()
        saved = self.start()
        overview = self.client.get(BASE).json
        self.assertFalse(overview['recordings_ready']); self.assertTrue(overview['enabled'])
        checked = self.request(saved, 'language_use', 'attempts', response=self.answers(saved, 'language_use'))
        self.assertEqual(checked.status_code, 200, checked.json)
        self.assertEqual(self.component(checked.json, 'language_use')['state'], 'reviewed')
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM assessment_pilot_sessions').fetchone()[0], 1)
        path.write_bytes(original)
        # A later recording cannot silently change this attempt's frozen source.
        self.assertFalse(self.component(self.start(), 'listening')['audio_available'])
        path = self.service.static / 'audio/course/assessment-pilot/a1-pilot-a-v1.mp3'
        path.unlink()
        overview = self.client.get(BASE).json
        self.assertFalse(overview['recordings_ready']); self.assertTrue(overview['enabled'])
        self.assertEqual(self.start()['id'], saved['id'])
        self.assertFalse(self.component(self.client.get(BASE + '/sessions/' + saved['id']).json, 'listening')['audio_available'])
        self.assertEqual(self.request(saved, 'listening', 'support', kind='listened').status_code, 409)
        fallback = self.request(saved, 'listening', 'attempts', response={'unavailable': True})
        self.assertEqual(fallback.status_code, 200)
        self.assertEqual(self.component(fallback.json, 'listening')['attempt']['outcome'], 'more_evidence_needed')

    def test_draft_retry_is_idempotent_and_stale_form_cannot_target_new_variant(self):
        saved = self.start(); old = self.component(saved, 'writing'); request_id = uuid4().hex
        draft = self.request(saved, 'writing', 'draft', submission_id=request_id, response={'text': 'Привет!'})
        same = self.request(saved, 'writing', 'draft', submission_id=request_id, response={'text': 'Привет!'})
        self.assertEqual(draft.json, same.json)
        self.assertEqual(self.request(saved, 'writing', 'draft', response={'text': 'Другой ответ.'}).status_code, 409)
        checked = self.request(draft.json, 'writing', 'attempts', response={'text': 'Привет! Приходи в парк.'}).json
        retried = self.client.post(BASE + '/sessions/' + saved['id'] + '/retry', json={
            'submission_id': uuid4().hex, 'components': [{'domain': 'writing', 'component_id': old['id']}]})
        self.assertEqual(retried.status_code, 200, retried.json)
        self.assertNotEqual(self.component(retried.json, 'writing')['id'], old['id'])
        self.assertEqual(self.component(retried.json, 'writing')['form_id'], 'b')
        for action, payload in [('attempts', {'response': {'text': 'Ответ на старый вопрос.'}}), ('draft', {'response': {'text': 'Старый черновик.'}}), ('support', {'kind': 'hint'}), ('review', {})]:
            reply = self.request(saved, 'writing', action, **payload)
            self.assertEqual(reply.status_code, 409, reply.json)
        self.writing.assess_writing.assert_called_once()

    def test_failed_provider_preserves_raw_answer_and_only_explicit_retry_invokes_again(self):
        saved = self.start(); self.writing.assess_writing.side_effect = RuntimeError('private provider body')
        request_id = uuid4().hex; raw = '  Мой исходный ответ.\n'
        failed = self.request(saved, 'writing', 'attempts', submission_id=request_id, response={'text': raw})
        self.assertEqual(failed.status_code, 200)
        attempt = self.component(failed.json, 'writing')['attempt']
        self.assertEqual(attempt['review_status'], 'review_unavailable'); self.assertEqual(attempt['response'], {'text': raw})
        self.assertNotIn('private provider body', json.dumps(failed.json))
        self.client.get(BASE + '/sessions/' + saved['id'])
        self.request(saved, 'writing', 'attempts', submission_id=request_id, response={'text': raw})
        self.assertEqual(self.writing.assess_writing.call_count, 1)
        retry_key = uuid4().hex
        self.request(failed.json, 'writing', 'review', submission_id=retry_key)
        self.request(failed.json, 'writing', 'review', submission_id=retry_key)
        self.assertEqual(self.writing.assess_writing.call_count, 2)

    def test_pending_submission_cannot_be_replaced_before_review_claim(self):
        saved = self.start(); component = self.component(saved, 'writing')
        with patch.object(self.service, 'review'):
            pending = self.request(saved, 'writing', 'attempts', response={'text': 'Привет, друг!'})
        self.assertEqual(pending.status_code, 200)
        reply = self.client.post(BASE + '/sessions/' + saved['id'] + '/retry', json={
            'submission_id': uuid4().hex, 'components': [{'domain': 'writing', 'component_id': component['id']}]})
        self.assertEqual(reply.status_code, 409)
        reviewed = self.request(pending.json, 'writing', 'review')
        self.assertEqual(self.component(reviewed.json, 'writing')['state'], 'reviewed')

    def test_crashed_pending_review_is_visible_and_can_resume_without_resubmitting(self):
        saved = self.start()
        with patch.object(self.service, 'review'):
            pending = self.request(saved, 'writing', 'attempts', response={'text': 'Привет! Приходи в гости.'}).json
        with self.connection() as conn:
            conn.execute('UPDATE assessment_pilot_reviews SET updated_at=updated_at-241')
        reopened = self.client.get(BASE + '/sessions/' + saved['id']).json
        self.assertEqual(self.component(reopened, 'writing')['state'], 'review_unavailable')
        self.writing.assess_writing.assert_not_called()
        reviewed = self.request(reopened, 'writing', 'review').json
        self.assertEqual(self.component(reviewed, 'writing')['state'], 'reviewed')
        self.assertEqual(self.component(reviewed, 'writing')['attempt']['id'], self.component(pending, 'writing')['attempt']['id'])
        self.writing.assess_writing.assert_called_once()

    def test_expired_pending_review_can_be_retired_without_late_claim_or_lost_original(self):
        saved = self.start(); component = self.component(saved, 'writing')
        raw = '  Привет! Приходи в гости.\n'
        with patch.object(self.service, 'review'):
            pending = self.request(saved, 'writing', 'attempts', response={'text': raw}).json
        submission = self.component(pending, 'writing')['attempt']['id']
        with self.connection() as conn:
            original = dict(conn.execute('SELECT * FROM assessment_pilot_submissions WHERE id=?', (submission,)).fetchone())
            created = conn.execute('SELECT updated_at FROM assessment_pilot_reviews WHERE submission_id=?', (submission,)).fetchone()[0]
        body = {'submission_id': uuid4().hex, 'components': [{'domain': 'writing', 'component_id': component['id']}]}
        url = BASE + '/sessions/' + saved['id'] + '/retry'
        with patch('repositories.assessment_pilot_repository.timestamp', return_value=created + 239):
            self.assertEqual(self.client.post(url, json=body).status_code, 409)
        with patch('repositories.assessment_pilot_repository.timestamp', return_value=created + 240), patch('services.assessment_pilot.timestamp', return_value=created + 240):
            reopened = self.client.get(BASE + '/sessions/' + saved['id']).json
            self.assertEqual(self.component(reopened, 'writing')['state'], 'review_unavailable')
            replacement = self.client.post(url, json=body)
            self.assertEqual(replacement.status_code, 200, replacement.json)
            self.assertEqual(self.component(replacement.json, 'writing')['form_id'], 'b')
            self.assertEqual(self.client.post(url, json=body).json, replacement.json)
            # A process resuming between submit and claim cannot grade the
            # replacement form or buy feedback for the abandoned submission.
            with self.client.session_transaction() as browser:
                access = browser['personal_access_id']
            from repositories.learning_repository import LearningError
            with self.assertRaises(LearningError):
                self.service.review(access, saved['id'], 'writing', submission_id=submission)
        with self.connection() as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM assessment_pilot_submissions WHERE id=?', (submission,)).fetchone()), original)
            retired = conn.execute('SELECT state,claim_token,lease_until,report_json FROM assessment_pilot_reviews WHERE submission_id=?', (submission,)).fetchone()
            self.assertEqual(tuple(retired), ('failed', None, 0, None))
            validate_saved_pilot(conn)
        history = self.component(replacement.json, 'writing')['history'][0]
        self.assertEqual(history['response'], {'text': raw})
        self.writing.assess_writing.assert_not_called()

    def test_speaking_upload_retry_preserves_bytes_and_rejected_uploads_leave_no_files(self):
        saved = self.start(); request_id = uuid4().hex
        first = self.upload(saved, submission_id=request_id)
        self.assertEqual(first.status_code, 200, first.json)
        files = sorted(self.service.root.iterdir()); original = {p.name: p.read_bytes() for p in files}
        duplicate = self.upload(saved, submission_id=request_id)
        self.assertEqual(duplicate.status_code, 200, duplicate.json)
        self.speaking.assess.assert_called_once()
        stale = self.upload(saved)
        self.assertEqual(stale.status_code, 409, stale.json)
        self.assertEqual({p.name: p.read_bytes() for p in self.service.root.iterdir()}, original)
        different = self.upload(saved, submission_id=request_id, audio=wav_bytes().replace(b'\x12\x00', b'\x13\x00'))
        self.assertEqual(different.status_code, 409)
        form_a = self.component(saved, 'speaking')
        next_form = self.client.post(BASE + '/sessions/' + saved['id'] + '/retry', json={
            'submission_id': uuid4().hex, 'components': [{'domain': 'speaking', 'component_id': form_a['id']}]})
        self.assertEqual(next_form.status_code, 200, next_form.json)
        self.assertEqual(self.component(next_form.json, 'speaking')['revision'], 0)
        self.assertEqual(self.upload(saved, component=form_a).status_code, 409)
        self.assertEqual({p.name: p.read_bytes() for p in self.service.root.iterdir()}, original)
        self.speaking.assess.assert_called_once()

    def test_csrf_wrong_profile_and_malformed_audio_do_not_invoke_grader(self):
        saved = self.start()
        no_token = self.client.post(BASE + '/sessions/' + saved['id'] + '/components/writing/attempts', json={}, headers={'X-CSRF-Token': ''})
        self.assertEqual(no_token.status_code, 403)
        malformed = self.upload(saved, audio=b'RIFF\x00\x00\x00\x00WAVEbroken')
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(list(self.service.root.iterdir()), [])
        with self.connection() as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other-pilot','Other','O','UTC',1)")
        select_test_profile(self.client, 'other-pilot')
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']
        self.assertEqual(self.client.get(BASE + '/sessions/' + saved['id']).status_code, 404)
        self.assertEqual(self.upload(saved).status_code, 404)
        self.writing.assess_writing.assert_not_called(); self.speaking.assess.assert_not_called()

    def test_unavailable_requires_real_boolean_and_speaking_is_unmeasured(self):
        saved = self.start()
        self.assertEqual(self.request(saved, 'speaking', 'attempts', response={'unavailable': 1}).status_code, 400)
        result = self.request(saved, 'speaking', 'attempts', response={'unavailable': True})
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.component(result.json, 'speaking')['attempt']['outcome'], 'more_evidence_needed')
        self.speaking.assess.assert_not_called()

    def test_expired_worker_cannot_replace_a_new_review_claim(self):
        saved = self.start(); component = self.component(saved, 'writing')
        with patch.object(self.service, 'review'):
            self.request(saved, 'writing', 'attempts', response={'text': 'Привет, друг!'})
        with self.client.session_transaction() as browser:
            access = browser['personal_access_id']
        first = self.service.repository.claim_review(access, saved['id'], 'writing', body={'submission_id': uuid4().hex, 'component_id': component['id']})
        with self.connection() as conn:
            conn.execute('UPDATE assessment_pilot_reviews SET lease_until=0')
        second = self.service.repository.claim_review(access, saved['id'], 'writing', body={'submission_id': uuid4().hex, 'component_id': component['id']})
        self.assertNotEqual(first[3], second[3])
        self.service.repository.finish_review(first[2]['id'], first[3], error='Old worker')
        with self.connection() as conn:
            row = conn.execute('SELECT state,claim_token,error FROM assessment_pilot_reviews').fetchone()
            self.assertEqual(tuple(row), ('running', second[3], None))
        self.service.repository.finish_review(second[2]['id'], second[3], error='New worker')
        self.writing.assess_writing.assert_not_called()

    def test_retry_retires_expired_worker_before_same_form_can_be_issued_again(self):
        saved = self.start(); original_component = self.component(saved, 'writing')
        raw = '  Привет! Приходи в парк в субботу в три часа. Будем гулять. Ты можешь прийти?\n'
        with patch.object(self.service, 'review'):
            pending = self.request(saved, 'writing', 'attempts', response={'text': raw})
        self.assertEqual(pending.status_code, 200, pending.json)
        with self.client.session_transaction() as browser:
            access = browser['personal_access_id']
        issued = self.service.repository.claim_review(access, saved['id'], 'writing', body={
            'submission_id': uuid4().hex, 'component_id': original_component['id']})
        submission = issued[2]['id']
        task = json.loads(issued[1]['task_json'])
        native = self.writing.assess_writing.side_effect(task['task'], [], 30, raw, curriculum_contract=task['contract'])
        late_report = make_report(task, {'text': raw}, [], criterion_report=native['criterion_report'],
                                  feedback=native['strength'] + '\n' + native['next_step'], model='offline-writing-fixture', production_feedback=native)
        with self.connection() as conn:
            original = dict(conn.execute('SELECT * FROM assessment_pilot_submissions WHERE id=?', (submission,)).fetchone())
            expires = conn.execute('SELECT lease_until FROM assessment_pilot_reviews WHERE submission_id=?', (submission,)).fetchone()[0]
        def retry(component):
            return self.client.post(BASE + '/sessions/' + saved['id'] + '/retry', json={
                'submission_id': uuid4().hex, 'components': [{'domain': 'writing', 'component_id': component['id']}]})
        self.assertEqual(retry(original_component).status_code, 409)
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT claim_token FROM assessment_pilot_reviews WHERE submission_id=?', (submission,)).fetchone()[0], issued[3])
        with patch('repositories.assessment_pilot_repository.timestamp', return_value=expires + 1):
            form_b = retry(original_component)
            self.assertEqual(form_b.status_code, 200, form_b.json)
            checked_b = self.request(form_b.json, 'writing', 'attempts', response={'text': 'Привет! Приходи ко мне в субботу. Будем пить чай.'})
            self.assertEqual(checked_b.status_code, 200, checked_b.json)
            again = retry(self.component(checked_b.json, 'writing'))
            self.assertEqual(again.status_code, 200, again.json)
        current = self.component(again.json, 'writing')
        self.assertEqual(current['form_id'], 'a'); self.assertEqual(current['support'], [])
        with self.connection() as conn:
            retired = dict(conn.execute('SELECT * FROM assessment_pilot_reviews WHERE submission_id=?', (submission,)).fetchone())
            ready_b = dict(conn.execute('SELECT * FROM assessment_pilot_reviews WHERE submission_id=?',
                                       (self.component(checked_b.json, 'writing')['attempt']['id'],)).fetchone())
        self.assertEqual(retired['state'], 'failed'); self.assertIsNone(retired['claim_token'])
        self.assertEqual(retired['lease_until'], 0); self.assertIsNone(retired['report_json'])
        with patch('repositories.assessment_pilot_repository.timestamp', return_value=expires + 2):
            self.service.repository.finish_review(submission, issued[3], report=late_report)
        with self.connection() as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM assessment_pilot_submissions WHERE id=?', (submission,)).fetchone()), original)
            self.assertEqual(dict(conn.execute('SELECT * FROM assessment_pilot_reviews WHERE submission_id=?', (submission,)).fetchone()), retired)
            self.assertEqual(dict(conn.execute('SELECT * FROM assessment_pilot_reviews WHERE submission_id=?', (ready_b['submission_id'],)).fetchone()), ready_b)
            validate_saved_pilot(conn)
        reopened = self.client.get(BASE + '/sessions/' + saved['id']).json
        old_attempt = next(item for item in self.component(reopened, 'writing')['history'] if item['id'] == submission)
        self.assertEqual(old_attempt['response'], {'text': raw})
        self.assertEqual(old_attempt['review_status'], 'review_unavailable')
        self.assertNotIn('production_feedback', old_attempt)

    def test_native_writing_provenance_is_the_actual_model_and_system_prompt(self):
        from services.writing_service import WritingService
        task = blueprint()['forms']['writing'][0]
        service = WritingService.__new__(WritingService); service.client = Mock()
        text = 'Привет! Приходи в парк в субботу. Ты можешь прийти?'
        native = {'score': 8, 'strength': 'A clear invitation.', 'next_step': 'Try another context.', 'example': 'До встречи!',
                  'criterion_report': criterion_report(task['contract'], text)}
        service.client.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(native))
        with self.app.app_context():
            result = service.assess_writing(task['task'], [], 30, text, 'A1', curriculum_contract=task['contract'], include_provenance=True)
        sent = service.client.responses.create.call_args.kwargs
        self.assertEqual(result['assessment_provenance']['model'], sent['model'])
        self.assertEqual(result['assessment_provenance']['prompt_sha256'], digest(sent['input'][0]['content'].encode()))
        self.assertEqual(result['criterion_report'], native['criterion_report'])

    def test_native_speaking_provenance_preserves_new_scope_and_original_audio(self):
        from services.speaking_assessment import SpeakingAssessment
        task = blueprint()['forms']['speaking'][0]
        original = self.service.static / 'native-learner.wav'; original.write_bytes(wav_bytes())
        native = speaking_feedback(task['contract'])
        output = {k: v for k, v in native.items() if k not in ('assessment_provenance', 'model', 'basis', 'rubric_version', 'rewards_applied')}
        with patch('services.speaking_assessment.openai_client') as factory:
            create = factory.return_value.chat.completions.create
            create.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(output), refusal=None))])
            result = SpeakingAssessment({'OPENAI_API_KEY': 'offline-fixture', 'SPEAKING_ASSESSMENT_MODEL': 'gpt-audio-1.5'}).assess(
                original, task['scenario'], [], curriculum_contract=task['contract'], include_provenance=True)
        sent = create.call_args.kwargs
        self.assertEqual(result['assessment_provenance']['model'], sent['model'])
        self.assertEqual(result['assessment_provenance']['prompt_sha256'], digest(sent['messages'][0]['content'].encode()))
        self.assertNotIn('Judge only the elicited location question', sent['messages'][0]['content'])
        self.assertIn('recorded message is not an interactive conversation', sent['messages'][0]['content'])
        self.assertEqual(original.read_bytes(), wav_bytes())


if __name__ == '__main__':
    unittest.main()
