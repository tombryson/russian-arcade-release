"""Original replies survive failed providers; a reviewed identity commits once."""
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from repositories.learning_repository import transaction
from services.activity_evidence import validate_saved_evidence
from services.curriculum_sequence_content import load_asset, task_contract
from services.activity_review_submissions import create_comprehension_in_transaction, create_writing_in_transaction
from tests.support import isolated_app


TEXT = 'Я в школе. Я иду в парк. Встретимся в парке.'


def criterion_report(contract, text):
    return {'contract_sha256': contract['contract_sha256'], 'judgements': [
        {'criterion_id': c['id'], 'outcome': 'satisfied', 'score': c['max_score'], 'reason_code': None,
         'feedback': 'This requested detail is clear.', 'evidence': [{'quote': text, 'start': 0, 'end': len(text)}]}
        for c in contract['criteria']]}


class ActivityReviewSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.writing, self.reading = Mock(), Mock()
        self.app = isolated_app(self, {'WritingService': self.writing, 'ComprehensionService': self.reading})
        self.client = self.app.test_client(); self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']

    def post(self, url, body):
        return self.client.post(url, json=body, headers={'X-CSRF-Token': self.token})

    def allocate(self, kind='writing', transfer=False):
        run = self.post('/api/v1/curriculum/units/location-destination-v2/runs',
            {'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1'}).json
        if not transfer:
            opened = self.post(f"/api/v1/curriculum/runs/{run['id']}/steps/{kind}/start",
                {'submission_id': uuid4().hex, 'expected_revision': run['revision']})
            self.assertEqual(opened.status_code, 200, opened.get_data(as_text=True))
            with transaction(self.db) as conn:
                row = conn.execute('SELECT profile_id,task_key FROM curriculum_unit_bindings WHERE run_id=? AND step_id=?', (run['id'], kind)).fetchone()
            return row['task_key'], row['profile_id']
        with transaction(self.db, write=True) as conn:
            owner = conn.execute('SELECT profile_id FROM curriculum_unit_runs WHERE id=?', (run['id'],)).fetchone()[0]
            asset = load_asset('location-message-v2' if kind == 'writing' else 'location-reading-v1')
            factory = create_writing_in_transaction if kind == 'writing' else create_comprehension_in_transaction
            task = factory(conn, owner, asset, task_contract)
            ordinal = conn.execute("SELECT COALESCE(MAX(ordinal),-1)+1 FROM curriculum_unit_bindings WHERE run_id=? AND step_id='transfer/0'", (run['id'],)).fetchone()[0]
            conn.execute('INSERT INTO curriculum_unit_bindings VALUES (?,?,?,?,?,?,?,?,?)',
                (uuid4().hex, run['id'], owner, 'transfer/0', ordinal, task['activity'], task['task_key'], 'unit-transfer-no-effects-v1', 1))
        return task['task_key'], owner

    def submit(self, task, response, activity='writing', revision=0, key=None):
        result = self.post(f'/api/v1/{activity}/tasks/{task}/submissions',
            {'submission_id': key or uuid4().hex, 'expected_revision': revision, 'response': response})
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        return result.json

    def output_writing(self, task):
        with transaction(self.db) as conn:
            contract = json.loads(conn.execute("SELECT contract_json FROM activity_task_contracts WHERE activity='writing' AND task_key=?", (task,)).fetchone()[0])
        self.writing.assess_writing.return_value = {'score': 8, 'strength': 'The message is clear.', 'next_step': 'Keep practising.',
            'example': TEXT, 'criterion_report': criterion_report(contract, TEXT)}

    def test_original_commits_before_provider_and_retry_uses_saved_text(self):
        task, owner = self.allocate(); key = uuid4().hex
        saved = self.submit(task, {'text': TEXT}, key=key)
        self.assertEqual(saved['work_state'], 'submitted')
        self.assertEqual(self.submit(task, {'text': TEXT}, key=key)['id'], saved['id'])
        conflict = self.post(f'/api/v1/writing/tasks/{task}/submissions',
            {'submission_id': key, 'expected_revision': 0, 'response': {'text': 'different'}})
        self.assertEqual(conflict.status_code, 409)
        def fail_provider(**kwargs):
            # A different writer proves no database transaction spans paid work.
            with sqlite3.connect(self.db, timeout=0) as conn:
                conn.execute('UPDATE writing_drafts SET response=?,revision=revision+1 WHERE exercise_id=?', ('Newer draft.', task))
                original = conn.execute('SELECT original_json FROM activity_review_submissions WHERE id=?', (saved['id'],)).fetchone()
                self.assertEqual(json.loads(original[0]), {'text': TEXT})
            raise RuntimeError('provider unavailable')
        self.writing.assess_writing.side_effect = fail_provider
        url = '/api/v1/writing/submissions/' + saved['id'] + '/review'
        failed = self.post(url, {}).json
        self.assertEqual(failed['work_state'], 'review_unavailable')
        self.writing.assess_writing.side_effect = None; self.output_writing(task)
        checked = self.post(url, {})
        self.assertEqual(checked.status_code, 200, checked.get_data(as_text=True))
        self.assertEqual(checked.json['work_state'], 'reviewed', checked.json)
        self.assertEqual(self.writing.assess_writing.call_args.kwargs['response'], TEXT)
        self.assertEqual(self.post(url, {}).json, checked.json)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_attempts').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT response FROM writing_drafts WHERE exercise_id=?', (task,)).fetchone()[0], 'Newer draft.')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 1)
            validate_saved_evidence(conn)

    def test_unchanged_check_after_provider_failure_cannot_allocate_another_original(self):
        task, _ = self.allocate()
        self.writing.assess_writing.side_effect = RuntimeError('unavailable')
        body = {'exercise_id': task, 'revision': 0, 'user_response': TEXT, 'submission_id': uuid4().hex}
        headers = {'X-CSRF-Token': self.token, 'Accept': 'application/json'}
        first = self.client.post('/writing/assess', data=body, headers=headers)
        self.assertEqual(first.status_code, 503, first.json)
        original = first.json['review_submission']['id']
        repeated = self.client.post('/writing/assess', data={**body, 'revision': first.json['revision'],
            'submission_id': uuid4().hex}, headers=headers)
        self.assertEqual(repeated.status_code, 409, repeated.json)
        self.assertEqual(repeated.json['error']['code'], 'review_pending')
        self.writing.assess_writing.assert_called_once()
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_review_submissions').fetchone()[0], 1)
        replay = self.post('/api/v1/writing/tasks/' + task + '/submissions', {
            'submission_id': body['submission_id'], 'expected_revision': 0, 'response': {'text': TEXT}})
        self.assertEqual(replay.status_code, 200, replay.json)
        self.assertEqual(replay.json['id'], original)
        # Retrying review is an explicit action against that one saved original.
        self.post('/api/v1/writing/submissions/' + original + '/review', {})
        self.assertEqual(self.writing.assess_writing.call_count, 2)

    def test_review_lease_expiry_rejects_previous_worker_and_original_is_immutable(self):
        from repositories import activity_review_repository as store
        task, owner = self.allocate(); saved = self.submit(task, {'text': TEXT})
        with transaction(self.db, write=True) as conn:
            _, first = store.claim(conn, owner, saved['id'])
            conn.execute('UPDATE activity_review_submissions SET review_started_at=0 WHERE id=?', (saved['id'],))
            _, second = store.claim(conn, owner, saved['id'])
            self.assertNotEqual(first, second)
            with self.assertRaisesRegex(ValueError, 'changed'):
                store.assert_lease(conn, owner, saved['id'], first)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE activity_review_submissions SET original_json='{}' WHERE id=?", (saved['id'],))

    def test_model_answer_is_disclosed_only_after_receipt_and_saved_as_support(self):
        task, _ = self.allocate()
        model = load_asset('location-message-v2')['content']['model_answer']
        self.assertNotIn(model, self.client.get('/writing/load/' + task).get_data(as_text=True))
        url = '/api/v1/writing/tasks/' + task + '/model-answer'
        self.assertEqual(self.client.post(url, json={'expected_revision': 0}).status_code, 403)
        shown = self.post(url, {'expected_revision': 0})
        self.assertEqual(shown.status_code, 200, shown.json)
        self.assertEqual(shown.json['model_answer'], model)
        self.assertEqual(self.post(url, {'expected_revision': 0}).json, shown.json)
        saved = self.submit(task, {'text': TEXT})
        self.assertEqual(saved['condition'], 'assisted')
        self.output_writing(task)
        self.assertEqual(self.post('/api/v1/writing/submissions/' + saved['id'] + '/review', {}).json['work_state'], 'reviewed')
        with transaction(self.db) as conn:
            row = conn.execute('SELECT support_json,support_receipts_json FROM activity_review_submissions').fetchone()
            self.assertEqual(json.loads(row[0]), ['model_answer'])
            self.assertEqual(json.loads(row[1]), [shown.json['id']])
            evidence = json.loads(conn.execute('SELECT evidence_json FROM progression_events').fetchone()[0])
            self.assertNotIn('_skill', evidence)
            from services.activity_review_submissions import validate_saved_reviews
            validate_saved_reviews(conn)

    def test_exact_feedback_on_an_earlier_task_marks_new_production_assisted(self):
        task, _ = self.allocate(transfer=True); self.output_writing(task)
        saved = self.submit(task, {'text': TEXT})
        self.assertEqual(self.post('/api/v1/writing/submissions/' + saved['id'] + '/review', {}).json['work_state'], 'reviewed')
        repeat, _ = self.allocate(transfer=True)
        self.assertNotEqual(repeat, task)
        self.assertEqual(self.submit(repeat, {'text': TEXT})['condition'], 'assisted')
        reading, _ = self.allocate('reading', transfer=True)
        self.reading.assess_task.side_effect = lambda payload, raw, **kwargs: {
            'scores': [8] * 3, 'total_score': 8, 'feedback': ['Understood.'] * 3,
            'criterion_reports': {i: criterion_report(c, raw[int(i)]) for i, c in payload['contracts'].items()}}
        answers = ['В школе.', 'В парк.', 'В парке.']
        original = self.submit(reading, {'answers': answers}, 'comprehension')
        self.assertEqual(self.post('/api/v1/comprehension/submissions/' + original['id'] + '/review', {}).json['work_state'], 'reviewed')
        repeat_reading, _ = self.allocate('reading', transfer=True)
        repeated = self.submit(repeat_reading, {'answers': answers}, 'comprehension')
        self.assertEqual(repeated['condition'], 'assisted')
        self.assertEqual(self.post('/api/v1/comprehension/submissions/' + repeated['id'] + '/review', {}).json['work_state'], 'reviewed')
        with transaction(self.db) as conn:
            validate_saved_evidence(conn)

    def test_transfer_writing_has_no_effects_and_legacy_route_uses_original_store(self):
        task, _ = self.allocate(transfer=True); self.output_writing(task)
        response = self.client.post('/writing/assess', data={'exercise_id': task, 'revision': 0, 'user_response': TEXT},
            headers={'X-CSRF-Token': self.token, 'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_review_submissions').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_attempts').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)

    def test_authored_reading_three_questions_original_retry_and_transfer_effects(self):
        task, _ = self.allocate('reading', transfer=True)
        answers = ['В школе.', 'В парк.', 'В парке.']
        saved = self.submit(task, {'answers': answers}, 'comprehension')
        self.reading.assess_task.side_effect = RuntimeError('offline')
        url = '/api/v1/comprehension/submissions/' + saved['id'] + '/review'
        self.assertEqual(self.post(url, {}).json['work_state'], 'review_unavailable')
        self.reading.assess_task.side_effect = lambda payload, raw, **kwargs: {
            'scores': [8] * 3, 'total_score': 8, 'feedback': ['Understood.'] * 3,
            'criterion_reports': {i: criterion_report(c, raw[int(i)]) for i, c in payload['contracts'].items()}}
        reviewed = self.post(url, {})
        self.assertEqual(reviewed.json['work_state'], 'reviewed', reviewed.json)
        self.assertEqual(self.post(url, {}).json, reviewed.json)
        self.assertEqual(self.client.get('/comprehension/tasks/' + task).status_code, 303)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM comprehension_attempts').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)
            validate_saved_evidence(conn)

    def test_submissions_are_owned_and_csrf_protected(self):
        task, _ = self.allocate(); saved = self.submit(task, {'text': TEXT})
        self.assertEqual(self.client.post('/api/v1/writing/submissions/' + saved['id'] + '/review', json={}).status_code, 403)
        other = self.post('/api/v1/user-session/profiles', {'display_name': 'Other'})
        self.token = other.json['csrf_token']
        self.assertEqual(self.client.get('/api/v1/writing/submissions/' + saved['id']).status_code, 404)
        self.assertEqual(self.post('/api/v1/writing/submissions/' + saved['id'] + '/review', {}).status_code, 404)

    def test_import_rejects_bound_task_collision_without_rewriting_frozen_original(self):
        from pathlib import Path
        from migrations import upgrade_database
        from services.account_import import build_account_import, ImportConflict
        task, _ = self.allocate(); saved = self.submit(task, {'text': TEXT})
        root = Path(self.db).parent; hosted = root / 'hosted.db'; upgrade_database(hosted, backup=False)
        with transaction(hosted, write=True) as conn:
            asset = load_asset('location-message-v2')
            create_writing_in_transaction(conn, 'personal-learning', asset, task_contract)
        with self.assertRaises(ImportConflict):
            build_account_import(self.db, hosted, root / 'merged.db')
        self.assertEqual(self.client.get('/api/v1/writing/submissions/' + saved['id']).json['original'], {'text': TEXT})

    def test_import_rejects_review_projection_tampering_and_preserves_originals(self):
        from copy import deepcopy
        from pathlib import Path
        from migrations import upgrade_database
        from services.account_import import build_account_import, ImportConflict
        from services.activity_review_submissions import validate_saved_reviews
        root = Path(self.db).parent; hosted = root / 'hosted.db'; upgrade_database(hosted, backup=False)
        writing, _ = self.allocate(); self.output_writing(writing)
        self.writing.assess_writing.return_value['assessment_provenance'] = {
            'model': 'test', 'prompt_sha256': 'b' * 64, 'rubric_version': 'writing-feedback-v1'}
        first = self.submit(writing, {'text': TEXT})
        self.assertEqual(self.post('/api/v1/writing/submissions/' + first['id'] + '/review', {}).json['work_state'], 'reviewed')
        reading, _ = self.allocate('reading', transfer=True)
        self.reading.assess_task.side_effect = lambda payload, raw, **kwargs: {
            'scores': [8] * 3, 'total_score': 8, 'feedback': ['Understood.'] * 3,
            'criterion_reports': {i: criterion_report(c, raw[int(i)]) for i, c in payload['contracts'].items()},
            'assessment_provenance': {'model': 'test', 'prompt_sha256': 'a' * 64, 'rubric_version': 'comprehension-feedback-v1'}}
        second = self.submit(reading, {'answers': ['В школе.', 'В парк.', 'В парке.']}, 'comprehension')
        self.assertEqual(self.post('/api/v1/comprehension/submissions/' + second['id'] + '/review', {}).json['work_state'], 'reviewed')
        with transaction(self.db) as conn:
            originals = {row['id']: dict(row) for row in conn.execute('SELECT id,original_json,result_json FROM activity_review_submissions')}
        for activity, identity in (('writing', first['id']), ('comprehension', second['id'])):
            for change in ('criterion', 'outcome', 'feedback', 'score_type'):
                with self.subTest(activity=activity, change=change):
                    altered = deepcopy(json.loads(originals[identity]['result_json']))
                    if change in ('criterion', 'score_type'):
                        report = altered['criterion_report'] if activity == 'writing' else altered['criterion_reports']['0']
                        if change == 'criterion':
                            report['judgements'][0].update(score=0, outcome='not_satisfied')
                        else:
                            report['judgements'][0]['score'] = True
                    elif change == 'outcome':
                        altered['outcome'] = 'practise_and_retry'
                    elif activity == 'writing':
                        altered['next_step'] = 'A changed assessment.'
                    else:
                        altered['feedback'][0] = 'A changed assessment.'
                    with transaction(self.db, write=True) as conn:
                        conn.execute('UPDATE activity_review_submissions SET result_json=? WHERE id=?', (json.dumps(altered), identity))
                    with transaction(self.db) as conn:
                        with self.assertRaisesRegex(ValueError, 'canonical assessment'):
                            validate_saved_reviews(conn)
                    output = root / (activity + '-' + change + '.db')
                    with self.assertRaises(ImportConflict):
                        build_account_import(self.db, hosted, output)
                    self.assertFalse(output.exists())
                    with transaction(self.db, write=True) as conn:
                        self.assertEqual(conn.execute('SELECT original_json FROM activity_review_submissions WHERE id=?', (identity,)).fetchone()[0], originals[identity]['original_json'])
                        conn.execute('UPDATE activity_review_submissions SET result_json=? WHERE id=?', (originals[identity]['result_json'], identity))
        # A clean reviewed source, including optional reviewer provenance, is
        # still importable without replacing any frozen assessment or original.
        output = root / 'valid.db'
        build_account_import(self.db, hosted, output)
        with transaction(output) as conn:
            for identity, original in originals.items():
                saved = conn.execute('SELECT original_json,result_json FROM activity_review_submissions WHERE id=?', (identity,)).fetchone()
                self.assertEqual(tuple(saved), (original['original_json'], original['result_json']))

    def test_text_review_clients_make_one_transport_attempt_within_review_lease(self):
        from pathlib import Path
        import httpx
        import openai
        from repositories.activity_review_repository import LEASE_SECONDS
        from services.writing_service import WritingService
        from services.comprehension_service import ComprehensionService
        from services.trial_provider import openai_client as real_client
        for module, factory in (
            ('services.writing_service', lambda config: WritingService(self.db, None, 'test-not-used', config=config)),
            ('services.comprehension_service', lambda config: ComprehensionService(self.db, None, None, str(Path(self.db).parent / 'media'), 'test-not-used', config=config)),
        ):
            with self.subTest(service=module):
                calls = []
                def unavailable(request):
                    calls.append(request)
                    raise httpx.ConnectError('Synthetic transport failure', request=request)
                def local_client(**options):
                    self.assertLess(options['timeout'], LEASE_SECONDS)
                    options.pop('config')
                    return openai.OpenAI(**options, http_client=httpx.Client(transport=httpx.MockTransport(unavailable)))
                with patch(module + '.openai_client', side_effect=local_client):
                    client = factory({}).client._get()
                    try:
                        with self.assertRaises(openai.APIConnectionError):
                            client.responses.create(model='test', input='Synthetic test; no network request.')
                    finally:
                        client.close()
                self.assertEqual(len(calls), 1)
                # The existing trial wrapper still owns its configuration and
                # disables retries when these same constructor options arrive.
                with patch(module + '.openai_client', wraps=real_client):
                    wrapped = factory({'AI_TRIAL_ENABLED': True}).client._get()
                    self.assertEqual(wrapped._client.max_retries, 0)
                    self.assertTrue(wrapped._config['AI_TRIAL_ENABLED'])
                    wrapped._client.close()


if __name__ == '__main__':
    unittest.main()
