"""One real learning sequence, using existing attempts, drafts and rewards."""
import json
import sqlite3
import unittest
from unittest.mock import patch

from services.curriculum_units import get_unit, writing_task, _pack
from contracts.curriculum import validate_task_contract
from contracts.learning import assess_activity_answer, validate_pack
from repositories.learning_repository import LearningError, encoded
from services.activity_evidence import validate_saved_evidence, save_report, load_contract
from tests.support import isolated_app


UNIT = 'location-destination-v1'
PATH = '/curriculum/units/' + UNIT


class CurriculumUnitTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']

    def post(self, path, *, form=None, body=None):
        return self.client.post(path, data=form, json=body, headers={'X-CSRF-Token': self.token})

    def start(self, request_id='unit-start', stage='practice'):
        response = self.post(PATH + '/' + stage, form={'profile_id': 'personal-learning', 'request_id': request_id})
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        session_id = response.location.rsplit('/', 1)[1]
        return self.client.get('/api/v1/learning-sessions/' + session_id).json

    def command(self, saved, kind='attempts', answer=None):
        body = {'submission_id': f"command-{saved['revision']}", 'expected_revision': saved['revision'], 'item_id': saved['item']['id']}
        if answer is not None:
            body['answer'] = answer if isinstance(answer, dict) else {'choice_id': answer}
        response = self.post('/api/v1/learning-sessions/' + saved['id'] + '/' + kind, body=body)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json

    def test_catalogue_links_to_focused_unit_and_gets_do_not_start_work(self):
        with sqlite3.connect(self.db) as conn:
            before = conn.execute('SELECT COUNT(*) FROM learning_sessions').fetchone()[0]
        self.assertIn('/curriculum/topics/places', self.client.get('/curriculum').get_data(as_text=True))
        self.assertIn(PATH, self.client.get('/curriculum/topics/places').get_data(as_text=True))
        page = self.client.get(PATH)
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('Where and where to', html)
        self.assertIn('Барсик в школе.', html)
        self.assertIn('Барсик идёт в школу.', html)
        self.assertIn('/#speaking/scenario/directions?level=A1', html)
        self.assertIn(PATH + '/forms', html)
        self.assertLess(html.index(PATH + '/practice'), html.index(PATH + '/forms'))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_sessions').fetchone()[0], before)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_task_contracts').fetchone()[0], 0)
        self.assertEqual(self.client.get('/curriculum/units/nonexistent').status_code, 404)

    def test_resume_choice_evidence_and_rewards_share_existing_transaction(self):
        saved = self.start()
        self.assertEqual(saved['origin']['href'], PATH)
        self.assertEqual(self.start('another-request')['id'], saved['id'])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_task_contracts').fetchone()[0], 4)
        saved = self.command(saved, 'help')
        saved = self.command(saved, answer='school')
        self.assertTrue(saved['attempts'][-1]['feedback']['assisted'])
        self.assertIn('next destination', saved['attempts'][-1]['feedback']['explanation'])
        for answer in ('at-library', 'at-post', 'within-park'):
            saved = self.command(saved, answer=answer)
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(saved['coins_earned'], 3)
        with sqlite3.connect(self.db) as conn:
            reports = conn.execute('SELECT source_key,report_json,support_json FROM activity_criterion_reports ORDER BY rowid').fetchall()
            self.assertEqual(len(reports), 4)
            self.assertEqual(json.loads(reports[0][2]), ['hint'])
            self.assertEqual(json.loads(reports[1][1])['judgements'][0]['outcome'], 'not_satisfied')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 4)
        # Reload retains explanation and return route, without another reward.
        restored = self.client.get('/api/v1/learning-sessions/' + saved['id']).json
        self.assertEqual(restored['attempts'], saved['attempts'])
        again = self.command(self.start('fresh-round'), answer='school')
        self.assertEqual(again['total_items'], 4)

    def test_generic_activity_entry_also_freezes_contracts_before_answers(self):
        first = self.start()
        response = self.post('/api/v1/learning-sessions', body={'profile_id': 'personal-learning',
                             'version_id': first['version_id'], 'submission_id': 'generic-start'})
        self.assertEqual(response.status_code, 201)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_task_contracts').fetchone()[0], 8)

    def test_writing_opens_owned_draft_with_frozen_criteria_and_resumes_it(self):
        task = writing_task(get_unit(UNIT))
        validate_task_contract(task['curriculum_contract'])
        form = {'profile_id': 'personal-learning'}
        first = self.post(PATH + '/writing', form=form)
        self.assertEqual(first.status_code, 303, first.get_data(as_text=True))
        self.assertEqual(self.post(PATH + '/writing', form=form).location, first.location)
        page = self.client.get(first.location)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Where shall we meet?', page.get_data(as_text=True))
        self.assertIn(PATH, page.get_data(as_text=True))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_exercises').fetchone()[0], 1)
            contract = json.loads(conn.execute("SELECT contract_json FROM activity_task_contracts WHERE activity='writing'").fetchone()[0])
            self.assertEqual(contract['content']['task'], task['task'])
            self.assertEqual(contract['criteria'][0]['response_mode'], 'independent_writing')

    def test_stale_profile_and_csrf_cannot_start_or_create_work(self):
        for action in ('practice', 'forms', 'writing'):
            response = self.post(PATH + '/' + action, form={'profile_id': 'other', 'request_id': 'bad-start'})
            self.assertEqual(response.status_code, 409)
            response = self.client.post(PATH + '/' + action, data={'profile_id': 'personal-learning', 'request_id': 'bad-start'})
            self.assertEqual(response.status_code, 403)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_sessions').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM writing_exercises').fetchone()[0], 0)

    def test_forms_are_a_separate_stage_and_keep_exact_typed_response_evidence(self):
        choices = self.start()
        with sqlite3.connect(self.db) as conn:
            original = conn.execute('SELECT payload FROM learning_content_versions WHERE id=?', (choices['version_id'],)).fetchone()[0]
        saved = self.start('forms-start', 'forms')
        self.assertNotEqual(saved['version_id'], choices['version_id'])
        self.assertEqual(saved['total_items'], 3)
        self.assertEqual(saved['item']['type'], 'controlled_text')
        for field in ('answer', 'accepted_answers', 'choices'):
            self.assertNotIn(field, saved['item'])
        self.assertEqual(self.start('resume-forms', 'forms')['id'], saved['id'])
        exact = '  В   ШКОЛУ!  '
        before = saved
        saved = self.command(saved, answer={'text': exact})
        self.assertEqual(self.command(before, answer={'text': exact}), saved)
        self.assertEqual(saved['attempts'][-1]['answer'], {'text': exact})
        self.assertEqual(saved['attempts'][-1]['feedback']['response_text'], exact)
        self.assertEqual(saved['attempts'][-1]['outcome'], 'correct')
        saved = self.command(saved, 'help')
        saved = self.command(saved, answer={'text': 'почта'})
        self.assertEqual(saved['attempts'][-1]['outcome'], 'incorrect')
        saved = self.command(saved, answer={'text': 'в парке.'})
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(saved['coins_earned'], 3)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?', (choices['version_id'],)).fetchone()[0], original)
            contracts = [json.loads(row[0]) for row in conn.execute("SELECT contract_json FROM activity_task_contracts WHERE task_key LIKE ?", (saved['id'] + ':%',))]
            self.assertEqual(len(contracts), 3)
            self.assertTrue(all(c['criteria'][0]['response_mode'] == 'controlled_text' and c['criteria'][0]['evidence_scope'] == 'controlled_production' for c in contracts))
            reports = conn.execute('SELECT r.report_json,r.support_json FROM activity_criterion_reports r JOIN activity_task_contracts c ON c.id=r.contract_id WHERE c.task_key LIKE ? ORDER BY r.rowid', (saved['id'] + ':%',)).fetchall()
            evidence = json.loads(reports[0][0])['judgements'][0]['evidence'][0]
            self.assertEqual(evidence, {'quote': exact, 'start': 0, 'end': len(exact)})
            self.assertEqual(json.loads(reports[1][1]), ['hint'])
            self.assertEqual(json.loads(reports[1][0])['judgements'][0]['score'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts WHERE session_id=?', (saved['id'],)).fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)
            changes = conn.total_changes
            validate_saved_evidence(conn)
            self.assertEqual(conn.total_changes, changes)
        restored = self.client.get('/api/v1/learning-sessions/' + saved['id']).json
        self.assertEqual(restored['attempts'], saved['attempts'])
        self.assertEqual(self.client.get('/api/v1/learning-sessions/' + choices['id']).json['total_items'], 4)
        with sqlite3.connect(self.db) as conn:
            key = saved['id'] + ':form-location'
            contract = load_contract(conn, 'personal-learning', 'curriculum_unit', key)
            report = json.loads(reports[1][0])
            report['judgements'][0].update(outcome='satisfied', score=2)
            with self.assertRaisesRegex(ValueError, 'deterministic'):
                save_report(conn, 'personal-learning', 'curriculum_unit', key, saved['attempts'][1]['id'], report,
                            response_text='почта', support=['hint'])
            report['judgements'][0].update(outcome='not_satisfied', score=0)
            with self.assertRaisesRegex(ValueError, 'Support must match'):
                save_report(conn, 'personal-learning', 'curriculum_unit', key, saved['attempts'][1]['id'], report,
                            response_text='почта')
            self.assertEqual(report['contract_sha256'], contract['contract_sha256'])

    def test_forms_reject_wrong_response_mode_and_rollback_failed_evidence(self):
        saved = self.start('forms-start', 'forms')
        url = '/api/v1/learning-sessions/' + saved['id'] + '/attempts'
        base = {'submission_id': 'typed', 'expected_revision': 0, 'item_id': saved['item']['id']}
        for answer in ({'choice_id': 'school'}, {'text': 'школу', 'score': 2}, {'text': '   '}, {'text': 123}, {'text': 'я' * 201}):
            response = self.post(url, body={**base, 'answer': answer})
            self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        from services.learning_service import LearningService
        with self.client.session_transaction() as session:
            credential = session['personal_access_id']
        with patch('services.curriculum_units.observe_answer', side_effect=ValueError('Report unavailable')):
            with self.assertRaisesRegex(ValueError, 'Report unavailable'):
                LearningService(self.db).command(credential, saved['id'], 'answer', {**base, 'answer': {'text': 'школу'}})
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_attempts').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT revision FROM learning_sessions WHERE id=?', (saved['id'],)).fetchone()[0], 0)


class ControlledFormContractTests(unittest.TestCase):
    def test_authored_variants_only_and_original_choices_unchanged(self):
        unit = get_unit(UNIT)
        original = {'schema_version': 1, 'id': 'curriculum-unit:' + UNIT, 'kind': 'activity',
                    'title': unit['title'], 'source': 'Original application practice: ' + UNIT,
                    'items': [{'id': q['id'], 'type': 'choice', **{k: q[k] for k in ('prompt', 'choices', 'answer', 'hint')}} for q in unit['questions']]}
        self.assertEqual(encoded(_pack(unit)), encoded(original))
        item = _pack(unit, 'forms')['items'][0]
        for value in ('школу', 'В ШКОЛУ.', '  в   школу! '):
            self.assertEqual(assess_activity_answer(item, {'text': value}), (value, True))
        for value in ('школе', 'школа', 'v shkolu', 'школу и парк'):
            self.assertFalse(assess_activity_answer(item, {'text': value})[1])
        with self.assertRaises(LearningError):
            assess_activity_answer(_pack(unit)['items'][0], {'text': 'школу'})
        accented = {**item, 'answer': 'ёлке', 'accepted_answers': ['ёлке']}
        self.assertTrue(assess_activity_answer(accented, {'text': 'ЕЛКЕ.'})[1])
        pack = _pack(unit, 'forms')
        pack['items'][0]['accepted_answers'].append('ШКОЛУ.')
        with self.assertRaises(LearningError):
            validate_pack(pack)


if __name__ == '__main__':
    unittest.main()
