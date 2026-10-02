"""Regression checks for lesson retries, evidence provenance and summary ordering."""
import json
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from repositories.learning_repository import transaction
from repositories.curriculum_sequence_repository import validate_saved_sequences
from services.activity_evidence import validate_saved_evidence
from services.activity_review_submissions import validate_saved_reviews
from services import curriculum_sequences
from tests.support import isolated_app


class CurriculumSequenceRegressionTests(unittest.TestCase):
    def setUp(self):
        self.reading = Mock()
        self.app = isolated_app(self, {'ComprehensionService': self.reading})
        self.app.config['OPENAI_API_KEY'] = 'test-configured-not-used'
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']

    def post(self, url, body):
        result = self.client.post(url, json=body, headers={'X-CSRF-Token': self.token})
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        return result.json

    def start(self, path='guided'):
        return self.post('/api/v1/curriculum/units/location-destination-v2/runs', {
            'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1',
            'completion_path': path})

    def read_run(self, run):
        result = self.client.get('/api/v1/curriculum/runs/' + run['id'])
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        return result.json

    def step(self, run, step='choices', operation='start'):
        return self.post(f"/api/v1/curriculum/runs/{run['id']}/steps/{step}/{operation}", {
            'submission_id': uuid4().hex, 'expected_revision': run['revision']})

    def answer(self, opened):
        sid = opened['url'].rsplit('/', 1)[1]
        state = self.client.get('/api/v1/learning-sessions/' + sid).json
        with transaction(self.db) as conn:
            payload = json.loads(conn.execute('SELECT v.payload FROM learning_sessions s '
                'JOIN learning_content_versions v ON v.id=s.version_id WHERE s.id=?', (sid,)).fetchone()[0])
        item = next(i for i in payload['items'] if i['id'] == state['item']['id'])
        answer = {'text': item['answer']} if item['type'] == 'controlled_text' else {'choice_id': item['answer']}
        body = {'submission_id': uuid4().hex, 'expected_revision': state['revision'],
                'item_id': item['id'], 'answer': answer}
        url = '/api/v1/learning-sessions/' + sid + '/attempts'
        result = self.post(url, body)
        return sid, item['id'], result, url, body

    def reading_review(self, task, correct, revision, prefix):
        answers = ['В школе.', 'В библиотеку.', 'В библиотеке.']
        saved = self.post('/api/v1/comprehension/tasks/' + task + '/submissions', {
            'submission_id': uuid4().hex, 'expected_revision': revision, 'response': {'answers': answers}})

        def assess(payload, raw, **kwargs):
            reports = {}
            for index, contract in payload['contracts'].items():
                i = int(index)
                reports[index] = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
                    'criterion_id': c['id'], 'outcome': 'insufficient_evidence' if correct[i] is None else 'satisfied' if correct[i] else 'not_satisfied',
                    'score': None if correct[i] is None else c['max_score'] if correct[i] else 0,
                    'reason_code': 'insufficient_response' if correct[i] is None else None,
                    'feedback': f'Revision {revision}, question {i}: ' + ('understood.' if correct[i] else 'try again.'),
                    'evidence': [] if correct[i] is None else [{'quote': raw[i], 'start': 0, 'end': len(raw[i])}]
                } for c in contract['criteria']]}
            scores = [10 if value else 0 for value in correct]
            return {'scores': scores, 'total_score': sum(scores) / len(scores),
                    'feedback': ['Checked.'] * 3, 'criterion_reports': reports}

        self.reading.assess_task.side_effect = assess
        # Later submissions intentionally get lexically smaller report IDs.
        # Same-second ordering must follow submission identity, not random UUIDs.
        with patch('services.activity_evidence.identifier', side_effect=[prefix + f'{i:031x}' for i in range(3)]):
            reviewed = self.post('/api/v1/comprehension/submissions/' + saved['id'] + '/review', {})
        self.assertEqual(reviewed['work_state'], 'reviewed', reviewed)
        return reviewed

    def summary_domain(self, domain):
        result = self.client.get('/api/v1/curriculum/summary')
        self.assertEqual(result.status_code, 200, result.get_data(as_text=True))
        return next(d for d in result.json['domains'] if d['id'] == domain)

    def test_reading_uses_newest_answer_per_question_and_retains_other_errors(self):
        opened = self.step(self.start(), 'reading')
        task = opened['url'].rsplit('/', 1)[1]
        now = int(time.time())
        with patch('repositories.activity_review_repository.timestamp', return_value=now):
            self.reading_review(task, [False, False, True], 0, 'f')
            second = self.reading_review(task, [True, False, True], 1, 'e')
            latest = self.summary_domain('reading')['latest']
            self.assertEqual(latest['outcome'], 'practise_and_retry')
            self.assertEqual(latest['reference']['source_key'], second['attempt_ref']['id'])
            self.assertEqual(len(latest['feedback']), 3)
            self.assertTrue(all(text.startswith('Revision 1,') for text in latest['feedback']))
            self.assertIn('Revision 1, question 1: try again.', latest['feedback'])
            third = self.reading_review(task, [True, True, True], 2, 'a')
        latest = self.summary_domain('reading')['latest']
        self.assertEqual(latest['outcome'], 'demonstrated_in_task')
        self.assertEqual(latest['reference']['source_key'], third['attempt_ref']['id'])
        self.assertTrue(all(text.startswith('Revision 2,') for text in latest['feedback']))
        self.assertEqual(latest['condition'], 'assisted')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM comprehension_attempts').fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 9)
            validate_saved_evidence(conn)

    def test_unreviewed_reading_draft_is_never_presented_under_previous_grade(self):
        import html
        import re
        opened = self.step(self.start(), 'reading')
        task = opened['url'].rsplit('/', 1)[1]
        self.reading_review(task, [True, True, True], 0, 'f')
        draft = ['Ещё не проверено.', '', '']
        self.post('/api/v1/comprehension/tasks/' + task + '/draft', {
            'submission_id': uuid4().hex, 'expected_revision': 1, 'expected_draft_revision': 0,
            'response': {'answers': draft}})
        page = self.client.get(opened['url'], follow_redirects=True)
        self.assertEqual(page.status_code, 200)
        markup = page.get_data(as_text=True)
        editor = re.search(r'<textarea[^>]*id="story-answer-0"[^>]*>(.*?)</textarea>', markup, re.S)
        self.assertEqual(html.unescape(editor[1]), draft[0])
        checked = re.search(r'<div class="reading-check-result">(.*?)</div>', markup, re.S)[1]
        self.assertIn('10/10', checked)
        self.assertIn('В школе.', checked)
        self.assertNotIn(draft[0], checked)
        self.assertEqual(self.reading.assess_task.call_count, 1)

    def test_summary_recommends_authored_practice_and_pending_review_takes_precedence(self):
        opened = self.step(self.start(), 'reading')
        task = opened['url'].rsplit('/', 1)[1]
        reviewed = self.reading_review(task, [False, True, True], 0, 'f')
        with transaction(self.db) as conn:
            counts = tuple(conn.execute('SELECT (SELECT COUNT(*) FROM curriculum_unit_bindings),'
                '(SELECT COUNT(*) FROM activity_review_submissions),(SELECT COUNT(*) FROM progression_events)').fetchone())
        domain = self.summary_domain('reading')
        action = domain['next_action']
        self.assertEqual(action['kind'], 'focused_practice')
        self.assertEqual(action['step_id'], 'reading')
        self.assertEqual(action['url'], opened['run']['lesson_url'] + '#sequence-step-reading')
        self.assertEqual(domain['latest']['reference']['source_key'], reviewed['attempt_ref']['id'])
        self.assertNotIn('_findings', domain['latest'])
        self.assertEqual(self.client.get(action['url']).status_code, 200)
        with transaction(self.db) as conn:
            self.assertEqual(tuple(conn.execute('SELECT (SELECT COUNT(*) FROM curriculum_unit_bindings),'
                '(SELECT COUNT(*) FROM activity_review_submissions),(SELECT COUNT(*) FROM progression_events)').fetchone()), counts)
        pending = self.post('/api/v1/comprehension/tasks/' + task + '/submissions', {
            'submission_id': uuid4().hex, 'expected_revision': 1,
            'response': {'answers': ['В школе.', 'В библиотеку.', 'В библиотеке.']}})
        self.assertEqual(self.summary_domain('reading')['next_action']['kind'], 'open_saved_reply')
        self.reading.assess_task.side_effect = RuntimeError('Provider unavailable')
        self.post('/api/v1/comprehension/submissions/' + pending['id'] + '/review', {})
        domain = self.summary_domain('reading')
        self.assertEqual(domain['next_action']['kind'], 'retry_review')
        self.assertEqual(domain['latest']['reference']['source_key'], reviewed['attempt_ref']['id'])

    def test_summary_insufficient_evidence_offers_new_situation_without_allocating(self):
        opened = self.step(self.start(), 'reading')
        task = opened['url'].rsplit('/', 1)[1]
        self.reading_review(task, [None, True, True], 0, 'f')
        action = self.summary_domain('reading')['next_action']
        self.assertEqual(action['kind'], 'new_example')
        self.assertEqual(action['step_id'], 'transfer')
        self.assertEqual(action['url'], opened['run']['lesson_url'] + '#sequence-step-transfer')
        self.assertEqual(self.client.get(action['url']).status_code, 200)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_bindings').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_transfer_exposure').fetchone()[0], 0)
        self.reading.assess_task.assert_called_once()

    def test_transfer_chooses_a_playable_family_when_other_family_audio_is_missing(self):
        capability = curriculum_sequences._capability
        def available(asset):
            return 'audio_unavailable' if asset['id'] == 'location-transfer-people-listening-v1' else capability(asset)
        with patch.object(curriculum_sequences, '_capability', side_effect=available):
            from flask import template_rendered
            contexts = []
            def capture(sender, template, context, **extra):
                contexts.append(context)
            with template_rendered.connected_to(capture, self.app):
                page = self.client.get('/curriculum/units/location-destination-v2')
            self.assertEqual(page.status_code, 200)
            transfer_preview = next(s for s in contexts[-1]['curriculum_sequence']['steps'] if s['id'] == 'transfer')
            self.assertEqual(transfer_preview['availability'], 'available')
            run = self.start('challenge')
            self.assertEqual(next(s for s in run['steps'] if s['id'] == 'transfer')['availability'], 'available')
            self.assertEqual(run['next_action']['step_id'], 'transfer')
            with transaction(self.db) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_bindings').fetchone()[0], 0)
            opened = self.step(run, 'transfer')
            resumed = self.step(opened['run'], 'transfer')
        self.assertEqual(opened['url'], resumed['url'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT family_id FROM curriculum_transfer_exposure').fetchone()[0],
                             'location-meeting-update-v1')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_bindings').fetchone()[0], 5)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)
            speaking_id = conn.execute("SELECT task_key FROM curriculum_unit_bindings WHERE activity='unit_exchange'").fetchone()[0]
            validate_saved_sequences(conn)
        speaking = self.client.get('/api/v1/unit-exchanges/' + speaking_id)
        self.assertEqual(speaking.status_code, 200, speaking.get_data(as_text=True))
        from services.curriculum_sequence_content import load_asset
        scene = load_asset('location-transfer-update-speaking-v1')['content']['scene']
        self.assertEqual(speaking.json['scene']['instruction'], scene['instruction'])
        self.assertEqual(speaking.json['scene']['instruction_ru'], scene['instruction_ru'])
        self.assertNotIn('criteria', speaking.json)
        self.assertNotIn('model_answer', speaking.json['scene'])

    def test_current_transfer_family_does_not_depend_on_unused_family_media(self):
        opened = self.step(self.start('challenge'), 'transfer')
        capability = curriculum_sequences._capability
        def available(asset):
            return 'audio_unavailable' if asset['id'] == 'location-transfer-update-listening-v1' else capability(asset)
        with patch.object(curriculum_sequences, '_capability', side_effect=available):
            run = self.read_run(opened['run'])
            transfer = next(s for s in run['steps'] if s['id'] == 'transfer')
            self.assertEqual(transfer['availability'], 'available')
            self.assertEqual(transfer['url'], opened['url'])
            self.assertEqual(self.step(run, 'transfer')['url'], opened['url'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT family_id FROM curriculum_transfer_exposure').fetchone()[0],
                             'location-meeting-people-v1')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_bindings').fetchone()[0], 5)

    def test_feedback_disclosed_between_allocation_and_answer_is_assistance(self):
        first = self.step(self.start())
        retry = self.step(first['run'], operation='retry')
        retry_sid = retry['url'].rsplit('/', 1)[1]
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_prior_feedback WHERE session_id=?',
                                          (retry_sid,)).fetchone()[0], 0)
        first_sid, item_id, _, _, _ = self.answer(first)
        _, _, repeated, url, body = self.answer(retry)
        self.assertTrue(repeated['feedback']['assisted'])
        self.assertEqual(self.post(url, body), repeated)
        with transaction(self.db) as conn:
            receipt = conn.execute('SELECT a.session_id,a.item_id FROM learning_prior_feedback p '
                'JOIN activity_attempts a ON a.id=p.source_attempt_id WHERE p.session_id=? AND p.item_id=?',
                (retry_sid, item_id)).fetchone()
            self.assertEqual(tuple(receipt), (first_sid, item_id))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts WHERE session_id=?', (retry_sid,)).fetchone()[0], 1)
            validate_saved_sequences(conn)
            validate_saved_evidence(conn)

    def test_later_feedback_does_not_retroactively_taint_an_earlier_answer(self):
        first = self.step(self.start())
        retry = self.step(first['run'], operation='retry')
        sid, item_id, original, url, body = self.answer(retry)
        self.assertFalse(original['feedback']['assisted'])
        with transaction(self.db) as conn:
            reports = [tuple(row) for row in conn.execute('SELECT * FROM activity_criterion_reports')]
        _, _, later, _, _ = self.answer(first)
        self.assertTrue(later['feedback']['assisted'])
        self.assertEqual(self.post(url, body), original)
        reloaded = self.client.get('/api/v1/learning-sessions/' + sid).json
        self.assertFalse(reloaded['attempts'][0]['feedback']['assisted'])
        with transaction(self.db) as conn:
            self.assertIsNone(conn.execute('SELECT 1 FROM learning_prior_feedback WHERE session_id=? AND item_id=?',
                                           (sid, item_id)).fetchone())
            self.assertEqual(tuple(conn.execute('SELECT * FROM activity_criterion_reports WHERE id=?', (reports[0][0],)).fetchone()), reports[0])
            validate_saved_sequences(conn)
            validate_saved_evidence(conn)

    def test_import_rejects_effects_policy_tampering_in_both_directions(self):
        ordinary = self.step(self.start())
        self.step(ordinary['run'], 'transfer')
        with transaction(self.db, write=True) as conn:
            validate_saved_reviews(conn)
            for step, policy in [('choices', 'unit-transfer-no-effects-v1'),
                                 ('transfer/0', 'existing-activity-effects-v1')]:
                with self.subTest(step=step):
                    conn.execute('SAVEPOINT tamper')
                    conn.execute('UPDATE curriculum_unit_bindings SET effects_policy=? WHERE step_id=?', (policy, step))
                    with self.assertRaisesRegex(ValueError, 'effects.*frozen lesson policy'):
                        validate_saved_reviews(conn)
                    conn.execute('ROLLBACK TO tamper')
                    conn.execute('RELEASE tamper')
            validate_saved_reviews(conn)

    def test_import_rejects_feedback_from_wrong_item_version_or_profile(self):
        first = self.step(self.start())
        source_sid, _, _, _, _ = self.answer(first)
        retry = self.step(first['run'], operation='retry')
        self.answer(retry)
        forms = self.step(retry['run'], 'forms')
        form_sid = forms['url'].rsplit('/', 1)[1]
        other = self.client.post('/api/v1/user-session/profiles', json={'display_name': 'Other learner'},
                                 headers={'X-CSRF-Token': self.token})
        self.assertEqual(other.status_code, 201, other.get_data(as_text=True))
        with transaction(self.db, write=True) as conn:
            version = conn.execute('SELECT version_id FROM learning_sessions WHERE id=?', (form_sid,)).fetchone()[0]
            profile = conn.execute("SELECT id FROM learning_profiles WHERE display_name='Other learner'").fetchone()[0]
            validate_saved_sequences(conn)
            mutations = [
                ('item', 'UPDATE activity_attempts SET item_id=? WHERE session_id=?', ('not-the-same-question', source_sid)),
                ('version', 'UPDATE learning_sessions SET version_id=? WHERE id=?', (version, source_sid)),
                ('profile', 'UPDATE learning_sessions SET profile_id=? WHERE id=?', (profile, source_sid)),
            ]
            for label, sql, params in mutations:
                with self.subTest(mismatch=label):
                    conn.execute('SAVEPOINT tamper')
                    conn.execute(sql, params)
                    with self.assertRaisesRegex(ValueError, 'same owned, frozen question'):
                        validate_saved_sequences(conn)
                    conn.execute('ROLLBACK TO tamper')
                    conn.execute('RELEASE tamper')
            validate_saved_sequences(conn)
            validate_saved_evidence(conn)

    def test_malformed_navigation_values_return_400_without_mutating_the_run(self):
        run = self.start()
        headers = {'X-CSRF-Token': self.token}
        for value in ([], {}):
            with self.subTest(operation='start', value=value):
                result = self.client.post('/api/v1/curriculum/units/location-destination-v2/runs',
                    json={'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1',
                          'completion_path': value}, headers=headers)
                self.assertEqual(result.status_code, 400, result.get_data(as_text=True))
            for field in ('completion_path', 'step_id'):
                with self.subTest(operation='navigation', field=field, value=value):
                    result = self.client.post(f"/api/v1/curriculum/runs/{run['id']}/navigation",
                        json={'submission_id': uuid4().hex, 'expected_revision': run['revision'], field: value},
                        headers=headers)
                    self.assertEqual(result.status_code, 400, result.get_data(as_text=True))
        self.assertEqual(self.read_run(run), run)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_runs').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_bindings').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_requests').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
