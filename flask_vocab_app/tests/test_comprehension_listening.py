"""Generated audio-first tasks hide source text and freeze support per check."""
import asyncio
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from services.comprehension_evidence import build_contracts, listening_candidates, SUPPORT_VERSION, validate_contracts
from services.comprehension_service import ComprehensionService
from services.story_vocabulary import story_key
from tests.support import isolated_app, select_test_profile
from tests.test_comprehension_evidence_routes import HiddenFields, prepared_story, PASSAGE, QUESTIONS, ANSWERS


def listening_story():
    result = prepared_story()
    result['listening_focus'] = result.pop('reading_focus')
    for focus in result['listening_focus']:
        focus['requirement_id'] = 'a1.listening.short-message'
    return result


def assessment(payload, answers):
    reports = {}
    for index, contract in payload['contracts'].items():
        unavailable = payload.get('practice_mode') == 'listening' and payload.get('audio') is None
        reports[index] = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
            'criterion_id': contract['criteria'][0]['id'],
            'outcome': 'insufficient_evidence' if unavailable else 'satisfied',
            'score': None if unavailable else 2,
            'feedback': 'The recording was unavailable.' if unavailable else 'The answer conveys the meaning.',
            'evidence': [] if unavailable else [{'quote': answers[int(index)], 'start': 0, 'end': len(answers[int(index)])}]}]}
    return {'feedback': ['Your meaning is clear.'] * len(answers), 'scores': [8] * len(answers),
            'total_score': 8, 'criterion_reports': reports}


class ComprehensionListeningRoutes(unittest.TestCase):
    def setUp(self):
        self.service = ComprehensionService.__new__(ComprehensionService)
        self.service.generate_story = AsyncMock(side_effect=lambda *args, **kwargs:
            deepcopy(listening_story() if kwargs.get('practice_mode') == 'listening' else prepared_story()))
        self.service.prepare_story_from_text = AsyncMock(return_value=listening_story())
        self.service.generate_image = Mock(return_value='/static/media/story_picture.png')
        self.service.generate_audio = Mock(return_value='/static/media/story_listening_fixture.mp3')
        self.service.assess_task = Mock(side_effect=assessment)
        self.service.generate_additional_questions = Mock(return_value=['Как зовут девушку?'])
        drive = Mock(); drive.download_vocab_list.return_value = ''
        self.app = isolated_app(self, {'ComprehensionService': self.service, 'GoogleDriveService': drive})
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.audio_path = Path(self.app.config['APP_MEDIA_DIR']) / 'story_listening_fixture.mp3'
        self.audio_path.parent.mkdir(parents=True, exist_ok=True)
        # Provider-free synthetic bytes exercise identity, ownership and serving;
        # these tests make no claim about a model's human listening accuracy.
        self.audio_bytes = b'ID3\x04\x00\x00synthetic generated recording fixture'
        self.audio_path.write_bytes(self.audio_bytes)
        self.csrf()

    def csrf(self):
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']

    def rows(self, table):
        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]

    def generate(self, **extra):
        response = self.client.post('/comprehension', data={'topic': 'places', 'difficulty': 'A1',
                                    'practice_mode': 'listening', **extra}, headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        fields = HiddenFields(response.get_data(as_text=True)).fields
        self.assertTrue(fields.get('task_id'), response.get_data(as_text=True))
        return fields, response.get_data(as_text=True)

    def support(self, fields, operation, **extra):
        return self.client.post('/comprehension/tasks/' + fields['task_id'] + '/support', json={
            'task_revision': int(fields['task_revision']), 'request_key': uuid4().hex, 'operation': operation, **extra})

    def check(self, fields, answers=None):
        return self.client.post('/comprehension/answer', data={**fields, 'answers[]': answers or ANSWERS},
                                headers={'HX-Request': 'true'})

    def test_generation_and_reload_never_send_unrevealed_transcript_or_word_payload(self):
        fields, html = self.generate()
        payload = json.loads(self.rows('comprehension_tasks')[0]['payload_json'])
        self.assertEqual(payload['practice_mode'], 'listening')
        self.assertEqual(payload['audio']['sha256'], hashlib.sha256(self.audio_bytes).hexdigest())
        self.assertEqual(payload['audio']['size_bytes'], len(self.audio_bytes))
        for contract in payload['contracts'].values():
            self.assertEqual(contract['criteria'][0]['response_mode'], 'listening_response')
            self.assertEqual(contract['criteria'][0]['evidence_scope'], 'listening_comprehension')
        reloaded = self.client.get('/comprehension/load/' + fields['story_id'])
        self.assertEqual(reloaded.status_code, 200)
        for page in (html, reloaded.get_data(as_text=True)):
            self.assertNotIn(PASSAGE, page)
            self.assertNotIn(base64.b64encode(PASSAGE.encode()).decode(), page)
            self.assertNotIn('Meeting after the pharmacy', page)
            self.assertNotIn('/static/media/test-story.png', page)
            self.assertNotIn(hashlib.sha256(PASSAGE.encode()).hexdigest(), page)
        self.assertEqual(self.rows('comprehension_support_receipts'), [])
        self.assertEqual(self.rows('comprehension_attempts'), [])

    def test_unopened_audio_cannot_be_checked_and_playback_is_bound_to_original_bytes(self):
        fields, _ = self.generate()
        self.assertEqual(self.check(fields).status_code, 409)
        self.service.assess_task.assert_not_called()
        audio = self.client.get('/comprehension/tasks/' + fields['task_id'] + '/audio')
        self.assertEqual(audio.status_code, 200)
        self.assertEqual(audio.data, self.audio_bytes)
        self.assertIn('no-store', audio.headers['Cache-Control'])
        self.assertEqual(self.support(fields, 'listened').status_code, 200)
        checked = self.check(fields)
        self.assertEqual(checked.status_code, 200, checked.get_data(as_text=True))
        saved = self.rows('comprehension_attempts')[0]
        self.assertEqual(json.loads(saved['answers_json']), ANSWERS)
        self.assertEqual(json.loads(saved['support_json']), [])
        self.assertEqual(json.loads(saved['support_receipts_json']), [self.rows('comprehension_support_receipts')[0]['id']])
        self.assertEqual(len(self.rows('activity_criterion_reports')), 4)
        self.assertEqual(self.rows('course_chapter_passes'), [])

    def test_replaced_or_missing_audio_blocks_playback_but_transcript_fallback_remains_explicit(self):
        fields, _ = self.generate()
        self.audio_path.write_bytes(b'replaced recording')
        self.assertEqual(self.client.get('/comprehension/tasks/' + fields['task_id'] + '/audio').status_code, 409)
        self.assertEqual(self.support(fields, 'listened').status_code, 409)
        self.assertEqual(self.rows('comprehension_support_receipts'), [])
        revealed = self.support(fields, 'transcript')
        self.assertEqual(revealed.status_code, 200)
        self.assertEqual(revealed.json['text'], PASSAGE)
        self.assertTrue(revealed.json['words'])
        self.assertTrue(revealed.json['audio_unavailable'])
        self.assertEqual(revealed.json['support'], ['transcript'])
        self.assertEqual(self.check(fields).status_code, 200)
        self.assertEqual(json.loads(self.rows('comprehension_attempts')[0]['support_json']), ['transcript'])

    def test_initial_audio_failure_keeps_saved_task_and_only_unscored_listening_fallback(self):
        self.service.generate_audio.return_value = ''
        fields, html = self.generate()
        payload = json.loads(self.rows('comprehension_tasks')[0]['payload_json'])
        self.assertIsNone(payload['audio'])
        self.assertNotIn(PASSAGE, html)
        self.assertEqual(self.support(fields, 'listened').status_code, 409)
        self.assertEqual(self.check(fields).status_code, 409)
        self.assertEqual(self.support(fields, 'transcript').status_code, 200)
        self.assertEqual(self.check(fields).status_code, 200)
        saved = json.loads(self.rows('comprehension_attempts')[0]['assessment_json'])
        self.assertEqual(saved['total_score'], 8)
        for report in saved['criterion_reports'].values():
            self.assertIsNone(report['judgements'][0]['score'])
            self.assertEqual(report['judgements'][0]['outcome'], 'insufficient_evidence')

    def test_pasted_passage_starts_with_known_transcript_exposure(self):
        fields, html = self.generate(custom_story=PASSAGE)
        self.assertIn(PASSAGE, html)
        receipt = self.rows('comprehension_support_receipts')[0]
        self.assertEqual((receipt['kind'], receipt['revision']), ('transcript', 0))
        self.assertEqual(self.check(fields).status_code, 200)
        self.assertEqual(json.loads(self.rows('comprehension_attempts')[0]['support_json']), ['transcript'])

    def test_support_retry_is_idempotent_and_cannot_change_operation(self):
        fields, _ = self.generate(); key = uuid4().hex
        first = self.support(fields, 'listened', request_key=key)
        retry = self.support(fields, 'listened', request_key=key)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json, retry.json)
        self.assertEqual(len(self.rows('comprehension_support_receipts')), 1)
        self.assertEqual(self.support(fields, 'transcript', request_key=key).status_code, 409)
        self.assertEqual(self.support(fields, 'listened', task_revision=1).status_code, 409)

    def test_later_transcript_and_word_help_cannot_relabel_first_attempt(self):
        fields, _ = self.generate()
        self.assertEqual(self.support(fields, 'listened').status_code, 200)
        checked = self.check(fields)
        self.assertEqual(checked.status_code, 200)
        first = deepcopy(self.rows('comprehension_attempts')[0])
        fields.update(HiddenFields(checked.get_data(as_text=True)).fields)
        self.assertEqual(self.support(fields, 'transcript').status_code, 200)
        self.assertEqual(self.support(fields, 'hint', word='аптеке').status_code, 200)
        self.assertEqual(self.support(fields, 'translation', word='почту').status_code, 200)
        self.assertEqual(self.support(fields, 'hint', word='слон').status_code, 400)
        changed = ANSWERS.copy(); changed[0] = 'Она находится в аптеке.'
        self.assertEqual(self.check(fields, changed).status_code, 200)
        saved = self.rows('comprehension_attempts')
        self.assertEqual(saved[0], first)
        self.assertEqual(json.loads(saved[1]['support_json']), ['hint', 'model_answer', 'transcript', 'translation'])
        self.assertEqual(len(json.loads(saved[1]['support_receipts_json'])), 4)

    def test_word_help_requires_disclosure_and_support_cannot_race_pending_check(self):
        fields, _ = self.generate()
        self.assertEqual(self.support(fields, 'hint', word='аптеке').status_code, 409)
        self.assertEqual(self.support(fields, 'listened').status_code, 200)
        from repositories.comprehension_repository import ComprehensionRepository
        with self.app.test_request_context():
            # No selected browser session: use the owned personal workspace.
            from unittest.mock import patch
            with patch('repositories.comprehension_repository.activity_profile_id', return_value='personal-learning'):
                issued, _ = ComprehensionRepository(self.db).begin_check(fields['task_id'], 0, fields['submission_id'], ANSWERS)
        self.assertEqual(self.support(fields, 'transcript').status_code, 409)
        self.assertEqual([row['kind'] for row in self.rows('comprehension_support_receipts')], ['listened'])

    def test_more_questions_inherit_receipts_without_replacing_original_evidence(self):
        fields, _ = self.generate()
        self.assertEqual(self.support(fields, 'listened').status_code, 200)
        original = self.rows('comprehension_support_receipts')[0]
        more = self.client.post('/comprehension/generate_more_questions', data=fields, headers={'HX-Request': 'true'})
        self.assertEqual(more.status_code, 200, more.get_data(as_text=True))
        child = HiddenFields(more.get_data(as_text=True)).fields
        self.assertNotEqual(child['task_id'], fields['task_id'])
        receipts = self.rows('comprehension_support_receipts')
        self.assertEqual(receipts[0], original)
        self.assertEqual(receipts[1]['inherited_from'], original['id'])
        self.assertEqual(receipts[1]['task_id'], child['task_id'])
        payload = json.loads(self.rows('comprehension_tasks')[-1]['payload_json'])
        self.assertEqual(payload['parent_task_id'], fields['task_id'])
        self.assertEqual(payload['practice_mode'], 'listening')
        self.assertNotIn(PASSAGE, more.get_data(as_text=True))
        self.assertEqual(self.check(child, ANSWERS + ['Её зовут Анна.']).status_code, 200)

    def test_new_reading_tasks_track_actual_word_help_without_changing_mode(self):
        fields, _ = self.generate(practice_mode='reading')
        payload = json.loads(self.rows('comprehension_tasks')[0]['payload_json'])
        self.assertEqual(payload['support_version'], SUPPORT_VERSION)
        self.assertEqual(payload['practice_mode'], 'reading')
        self.assertEqual(self.support(fields, 'hint', word='аптеке').status_code, 200)
        self.assertEqual(self.support(fields, 'transcript').status_code, 400)
        self.assertEqual(self.check(fields).status_code, 200)
        self.assertEqual(json.loads(self.rows('comprehension_attempts')[0]['support_json']), ['hint'])
        self.assertEqual(payload['contracts']['0']['criteria'][0]['response_mode'], 'reading_response')

    def test_another_profile_cannot_play_disclose_or_check(self):
        fields, _ = self.generate()
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
        select_test_profile(self.client, 'other'); self.csrf()
        self.assertEqual(self.client.get('/comprehension/tasks/' + fields['task_id'] + '/audio').status_code, 404)
        self.assertEqual(self.support(fields, 'transcript').status_code, 404)
        self.assertEqual(self.check(fields).status_code, 404)
        self.assertEqual(self.rows('comprehension_support_receipts'), [])
        self.service.assess_task.assert_not_called()

    def word_source(self, fields):
        return {'story_id': fields['story_id'], 'task_id': fields['task_id'], 'story_key': story_key(PASSAGE)}

    def popup(self, source, method='POST'):
        if method == 'GET':
            return self.client.get('/word-details/аптеке', query_string=source)
        return self.client.post('/word-details/аптеке', json=source)

    def capture(self, source):
        return self.client.post('/add-vocab/аптека', json={**source, 'word': 'аптеке', 'pos': 'NOUN'})

    def test_actual_popup_and_capture_require_explicit_transcript_before_disclosure(self):
        fields, _ = self.generate()
        original_words = self.rows('words')
        source = self.word_source(fields)
        self.assertEqual(self.popup(source).status_code, 409)
        self.assertEqual(self.capture(source).status_code, 409)
        self.assertEqual(self.popup(source, 'GET').status_code, 405)
        # Neither omitting the task nor both identities can turn this into a
        # legacy session lookup and reveal words from the hidden transcript.
        for removed in (('task_id',), ('story_id',), ('task_id', 'story_id')):
            reduced = {key: value for key, value in source.items() if key not in removed}
            self.assertEqual(self.popup(reduced).status_code, 409)
            self.assertEqual(self.capture(reduced).status_code, 409)
        self.assertEqual(self.rows('comprehension_support_receipts'), [])
        self.assertEqual(self.rows('words'), original_words)
        self.assertEqual(self.support(fields, 'transcript').status_code, 200)
        shown = self.popup(source)
        self.assertEqual(shown.status_code, 200, shown.get_data(as_text=True))
        self.assertEqual(shown.json['lemma'], 'аптека')
        self.assertEqual([row['kind'] for row in self.rows('comprehension_support_receipts')], ['transcript', 'hint'])
        self.assertEqual(self.check(fields).status_code, 200)
        self.assertEqual(json.loads(self.rows('comprehension_attempts')[0]['support_json']), ['hint', 'transcript'])

    def test_reading_popup_records_assistance_and_capture_uses_shared_vocabulary_pipeline(self):
        fields, _ = self.generate(practice_mode='reading')
        source = self.word_source(fields)
        self.assertEqual(self.popup(source, 'GET').status_code, 405)
        self.assertEqual(self.popup(source).status_code, 200)
        added = self.capture(source)
        self.assertEqual(added.status_code, 200, added.get_data(as_text=True))
        self.assertTrue(added.json['mnemonic'])
        sync = self.app.extensions['services']['SyncService']._get()
        self.assertEqual(sync.calls, [[added.json['word_id']]])
        word = next(row for row in self.rows('words') if row['id'] == added.json['word_id'])
        self.assertEqual(word['lemma'], 'аптека')
        self.assertNotEqual(word['topic'], '[]')
        self.assertGreater(len(self.rows('forms')), 1)
        self.assertIn('аптеке', [row['form'] for row in self.rows('forms')])
        receipts = self.rows('comprehension_support_receipts')
        self.assertEqual([row['kind'] for row in receipts], ['hint', 'hint'])
        self.assertTrue(all(row['task_id'] == fields['task_id'] for row in receipts))
        self.assertEqual(self.check(fields).status_code, 200)
        self.assertEqual(json.loads(self.rows('comprehension_attempts')[0]['support_json']), ['hint'])

    def test_word_help_rejects_parent_task_after_more_questions(self):
        fields, _ = self.generate(practice_mode='reading')
        source = self.word_source(fields)
        more = self.client.post('/comprehension/generate_more_questions', data=fields, headers={'HX-Request': 'true'})
        self.assertEqual(more.status_code, 200)
        child = HiddenFields(more.get_data(as_text=True)).fields
        self.assertEqual(self.popup(source).status_code, 409)
        self.assertEqual(self.capture(source).status_code, 409)
        self.assertEqual(self.popup({'story_key': source['story_key']}).status_code, 409)
        self.assertEqual(self.rows('comprehension_support_receipts'), [])
        self.assertEqual(self.popup({**source, 'task_id': child['task_id']}).status_code, 200)
        self.assertEqual(self.rows('comprehension_support_receipts')[0]['task_id'], child['task_id'])

    def test_dropped_story_identity_cannot_reuse_another_profiles_cached_page(self):
        fields, _ = self.generate(practice_mode='reading')
        original_words = self.rows('words')
        source = self.word_source(fields)
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',1)")
        select_test_profile(self.client, 'other'); self.csrf()
        for cached in ({'id': fields['story_id'], 'task_id': fields['task_id'], 'text': PASSAGE},
                       {'task_id': fields['task_id'], 'text': PASSAGE}):
            with self.client.session_transaction() as session:
                session['current_story_data'] = cached
            for lookup_source in (source, {'task_id': fields['task_id'], 'story_key': source['story_key']},
                                  {'story_key': source['story_key']}):
                self.assertEqual(self.popup(lookup_source).status_code, 404)
                self.assertEqual(self.popup(lookup_source, 'GET').status_code, 404)
                self.assertEqual(self.capture(lookup_source).status_code, 404)
        self.assertEqual(self.rows('comprehension_support_receipts'), [])
        self.assertEqual(self.rows('words'), original_words)

    def test_real_popup_cannot_disclose_support_during_pending_answer_check(self):
        fields, _ = self.generate(practice_mode='reading')
        original_words = self.rows('words')
        from repositories.comprehension_repository import ComprehensionRepository
        from unittest.mock import patch
        with self.app.test_request_context(), patch('repositories.comprehension_repository.activity_profile_id', return_value='personal-learning'):
            ComprehensionRepository(self.db).begin_check(fields['task_id'], 0, fields['submission_id'], ANSWERS)
        self.assertEqual(self.popup(self.word_source(fields)).status_code, 409)
        self.assertEqual(self.capture(self.word_source(fields)).status_code, 409)
        self.assertEqual(self.rows('comprehension_support_receipts'), [])
        self.assertEqual(self.rows('words'), original_words)

    def test_malformed_popup_identity_is_rejected_before_morphology_or_disclosure(self):
        fields, _ = self.generate(practice_mode='reading')
        original_words = self.rows('words')
        source = self.word_source(fields)
        for task_id in ([], {}, 42, True, 'x' * 101):
            self.assertEqual(self.popup({**source, 'task_id': task_id}).status_code, 422)
            self.assertEqual(self.capture({**source, 'task_id': task_id}).status_code, 422)
        self.assertEqual(self.popup({**source, 'sentence': PASSAGE}).status_code, 400)
        self.assertEqual(self.rows('comprehension_support_receipts'), [])
        self.assertEqual(self.rows('words'), original_words)


class ListeningProviderContracts(unittest.TestCase):
    def service(self, result):
        service = ComprehensionService.__new__(ComprehensionService)
        service.story_model = 'fixture'; service.story_reasoning_effort = 'low'
        service.client = Mock()
        service.client.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(result, ensure_ascii=False))
        return service

    def test_provider_gets_listening_references_and_audio_first_focus_schema(self):
        data = listening_story(); data.pop('image_url')
        service = self.service(data)
        prepared = service._request_story('fixture', reading_level='A1', topic='places', practice_mode='listening')
        self.assertIn('listening_focus', prepared)
        self.assertNotIn('reading_focus', prepared)
        call = service.client.responses.create.call_args.kwargs
        schema = call['text']['format']['schema']
        self.assertIn('listening_focus', schema['properties'])
        allowed = schema['properties']['listening_focus']['items']['properties']['requirement_id']['enum']
        self.assertEqual(set(allowed), set(listening_candidates('A1')))
        self.assertTrue(all('.listening.' in key for key in allowed))
        self.assertIn('text is hidden', call['input'][0]['content'])

    def test_initial_missing_audio_cannot_become_a_scored_listening_claim(self):
        prepared = listening_story()
        contracts = build_contracts(prepared, 'places', 'A1', practice_mode='listening', audio=None, track_support=True)
        task = {'text': PASSAGE, 'questions': QUESTIONS, 'topic': 'places', 'difficulty': 'A1',
                'practice_mode': 'listening', 'support_version': SUPPORT_VERSION, 'audio': None, 'contracts': contracts}
        provider = assessment(task, ANSWERS)
        provider.pop('total_score')
        for index, report in provider['criterion_reports'].items():
            report['judgements'][0].update(outcome='satisfied', score=2, evidence=[{'quote': ANSWERS[int(index)], 'start': 0, 'end': len(ANSWERS[int(index)])}])
        service = self.service(provider)
        result = service.assess_task(task, ANSWERS)
        self.assertEqual(result['scores'], [8] * 5)
        for report in result['criterion_reports'].values():
            self.assertEqual(report['judgements'][0]['outcome'], 'insufficient_evidence')
            self.assertIsNone(report['judgements'][0]['score'])
        instruction = service.client.responses.create.call_args.kwargs['input'][0]['content']
        self.assertIn('do not grade Russian writing', instruction)
        self.assertIn('never infer independence or attention', instruction)


if __name__ == '__main__':
    unittest.main()
