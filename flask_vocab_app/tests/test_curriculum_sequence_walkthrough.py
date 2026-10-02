"""Complete both lesson paths through public routes with bounded provider stubs."""
from collections import Counter
import io
import json
import unittest
from unittest.mock import Mock
from uuid import uuid4
import wave

from repositories.learning_repository import transaction
from services.activity_evidence import validate_saved_evidence
from services.activity_review_submissions import validate_saved_reviews
from repositories.curriculum_sequence_repository import validate_saved_sequences
from tests.support import isolated_app
from tests.test_activity_review_submissions import criterion_report
from tests.test_unit_exchange import recording


class CurriculumSequenceWalkthroughTests(unittest.TestCase):
    def setUp(self):
        self.writing, self.reading, self.speaking = Mock(), Mock(), Mock()
        self.app = isolated_app(self, {'WritingService': self.writing,
            'ComprehensionService': self.reading, 'SpeakingAssessment': self.speaking})
        self.app.config['OPENAI_API_KEY'] = 'test-configured-not-used'
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        self.token = self.client.get('/api/v1/user-session').json['csrf_token']
        self.configure_review_stubs()

    def configure_review_stubs(self):
        self.writing.assess_writing.side_effect = lambda **kw: {
            'score': 8, 'strength': 'A clear reply.', 'next_step': 'Keep practising.',
            'example': kw['response'], 'criterion_report': criterion_report(kw['curriculum_contract'], kw['response'])}
        self.reading.assess_task.side_effect = lambda payload, raw, **kw: {
            'scores': [8] * len(raw), 'total_score': 8, 'feedback': ['Understood.'] * len(raw),
            'criterion_reports': {i: criterion_report(c, raw[int(i)]) for i, c in payload['contracts'].items()}}
        self.speaking.assess.side_effect = self.speaking_report

    def post(self, url, body=None):
        response = self.client.post(url, json=body or {}, headers={'X-CSRF-Token': self.token})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json

    def start(self, path='challenge'):
        return self.post('/api/v1/curriculum/units/location-destination-v2/runs', {
            'submission_id': uuid4().hex, 'sequence_id': 'location-destination-sequence-v1',
            'completion_path': path})

    def read_run(self, run):
        response = self.client.get('/api/v1/curriculum/runs/' + run['id'])
        self.assertEqual(response.status_code, 200)
        return response.json

    def open_transfer(self, run):
        return self.open_step(run, 'transfer')

    def open_step(self, run, step):
        return self.post('/api/v1/curriculum/runs/' + run['id'] + '/steps/' + step + '/start', {
            'submission_id': uuid4().hex, 'expected_revision': run['revision']})

    def practice(self, identity, *, allow_rewards=False, save_drafts=False):
        path = '/api/v1/learning-sessions/' + identity
        state = self.client.get(path).json
        with transaction(self.db) as conn:
            pack = json.loads(conn.execute('SELECT v.payload FROM learning_sessions s '
                'JOIN learning_content_versions v ON v.id=s.version_id WHERE s.id=?', (identity,)).fetchone()[0])
        items = {item['id']: item for item in pack['items']}
        while state['item']:
            item = items[state['item']['id']]
            if item['type'] == 'listening_choice':
                audio = self.client.get(state['item']['audio']['url'])
                self.assertEqual(audio.status_code, 200)
                self.assertTrue(audio.data)
                audio.close()
                state = self.post(path + '/listened', {'submission_id': uuid4().hex,
                    'expected_revision': state['revision'], 'item_id': item['id']})
            if save_drafts:
                self.assertEqual(item['type'], 'controlled_text')
                saved = self.post(path + '/draft', {'submission_id': uuid4().hex,
                    'expected_revision': state['revision'], 'expected_draft_revision': state['draft']['revision'],
                    'item_id': item['id'], 'response': {'text': item['answer']}})
                restored = self.client.get(path).json
                self.assertEqual(restored['draft'], saved['draft'])
                self.assertEqual(restored['draft']['response']['text'], item['answer'])
                self.assertEqual(restored['revision'], state['revision'])
                self.assertEqual(restored['attempts'], state['attempts'])
                state = restored
            state = self.post(path + '/attempts', {'submission_id': uuid4().hex,
                'expected_revision': state['revision'], 'item_id': item['id'],
                'answer': {'text': item['answer']} if item['type'] == 'controlled_text' else {'choice_id': item['answer']}})
            if allow_rewards:
                self.assertGreaterEqual(state['coins_earned'], 0)
            else:
                self.assertEqual(state['coins_earned'], 0)
        return state

    def production(self, activity, identity, *, run=None):
        response = ({'text': 'Привет, Нина! Я сейчас в парке. Я иду в библиотеку. Встретимся в библиотеке.'}
                    if activity == 'writing' else {'answers': ['В школе.', 'В библиотеку.', 'В библиотеке.']})
        original = self.post(f'/api/v1/{activity}/tasks/{identity}/submissions', {
            'submission_id': uuid4().hex, 'expected_revision': 0, 'response': response})
        self.assertEqual(original['work_state'], 'submitted')
        self.assertEqual(original['original'], response)
        if run:
            self.assertFalse(self.read_run(run)['completed'])
        result = self.post(f"/api/v1/{activity}/submissions/{original['id']}/review")
        self.assertEqual(result['work_state'], 'reviewed', result)
        reopened = self.client.get(f"/api/v1/{activity}/submissions/{original['id']}").json
        self.assertEqual(reopened['original'], response)
        return reopened

    def speaking_report(self, path, scenario, dialogue, language, curriculum_contract, include_provenance=False, recording_turns=None):
        self.assertEqual(len(dialogue), 2)
        with wave.open(str(path), 'rb') as audio:
            duration = audio.getnframes() * 1000 // audio.getframerate()
        return {'basis': 'audio_review', 'rubric_version': 'speaking-audio-v1', 'model': 'test',
            'speech_status': 'russian', 'uncertain_phrases': [], 'transcript': 'Я сейчас в парке. Я иду в библиотеку.',
            'grammar': {'score': 4, 'reason': 'Clear forms.', 'evidence': ['в парке']},
            'fluency': {'score': None, 'reason': 'Short sample.', 'evidence': []},
            'goals': [{'id': row['id'], 'status': 'completed', 'evidence': ['в парке']} for row in scenario['goals']],
            'summary': 'Both replies are clear.', 'next_step': 'Keep practising.', 'corrections': [], 'uncertainty': '',
            'criterion_report': {'contract_sha256': curriculum_contract['contract_sha256'], 'judgements': [
                {'criterion_id': c['id'], 'outcome': 'satisfied', 'score': c['max_score'], 'reason_code': None,
                 'feedback': 'The detail is audible.', 'evidence': [
                     {'start_ms': turn['start_ms'], 'end_ms': turn['end_ms']} for turn in recording_turns
                     if turn['turn_id'] in curriculum_contract['content']['criterion_turns'][c['id']]]}
                for c in curriculum_contract['criteria']]}}

    def exchange(self, identity, *, run=None):
        path = '/api/v1/unit-exchanges/' + identity
        state = self.client.get(path).json
        while state['current_turn']:
            turn_path = path + '/turns/' + state['current_turn']['id']
            audio = self.client.get(state['current_turn']['audio_url'])
            self.assertEqual(audio.status_code, 200)
            self.assertTrue(audio.data)
            audio.close()
            state = self.post(turn_path + '/listened', {'submission_id': uuid4().hex, 'expected_revision': state['revision']})
            sent = self.client.post(turn_path + '/recording', data={
                'audio': (io.BytesIO(recording()), 'reply.wav'), 'submission_id': uuid4().hex,
                'expected_revision': str(state['revision'])}, headers={'X-CSRF-Token': self.token})
            self.assertEqual(sent.status_code, 200, sent.get_data(as_text=True))
            state = self.client.get(path).json
            self.assertEqual(state, sent.json)
            if run:
                self.assertFalse(self.read_run(run)['completed'])
        self.assertEqual(state['work_state'], 'submitted')
        self.assertEqual(sum(turn['saved'] for turn in state['turns']), 2)
        self.assertEqual(self.post(path + '/review')['work_state'], 'reviewed')

    def test_complete_guided_path_preserves_ordinary_rewards_and_transfer_has_no_effects(self):
        run = self.start('guided')
        self.assertFalse(run['completed'])
        self.assertEqual(run['next_action']['step_id'], 'learn')
        opened = self.open_step(run, 'learn')
        run = opened['run']
        self.assertTrue(opened['url'].endswith('#learn'))
        self.assertEqual(self.client.get(opened['url']).status_code, 200)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_bindings').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0], 0)
        ordinary = ('choices', 'forms', 'reading', 'listening', 'writing', 'speaking')
        for step in ordinary:
            self.assertFalse(self.read_run(run)['completed'])
            opened = self.open_step(run, step)
            run = opened['run']
            identity = opened['url'].rsplit('/', 1)[1]
            if step in ('choices', 'forms', 'listening'):
                self.practice(identity, allow_rewards=True, save_drafts=step == 'forms')
            elif step == 'speaking':
                self.exchange(identity, run=run)
            else:
                self.production('comprehension' if step == 'reading' else 'writing', identity, run=run)
            current = self.read_run(run)
            self.assertEqual(next(s['work_state'] for s in current['steps'] if s['id'] == step), 'reviewed')
            self.assertFalse(current['completed'], 'The guided route still requires transfer.')
        with transaction(self.db) as conn:
            events = [dict(row) for row in conn.execute('SELECT activity,evidence_json FROM progression_events')]
            self.assertEqual(Counter(e['activity'] for e in events), {'activity': 3, 'reading': 1, 'writing': 1, 'speaking': 1})
            evidence = {e['activity']: json.loads(e['evidence_json']) for e in events}
            self.assertIn('writing', evidence['writing']['_skill']['scores'])
            self.assertIn('speaking_grammar', evidence['speaking']['_skill']['scores'])
            # Existing daily limits still apply even when a guided lesson has
            # more ordinary activities than the coin allowance.
            from services.progression import RULES
            earned = conn.execute('SELECT COALESCE(SUM(amount),0) FROM progression_entries').fetchone()[0]
            self.assertGreater(earned, 0)
            self.assertLessEqual(earned, RULES['activity_daily_cap'])
            effect_tables = ('progression_events', 'progression_entries', 'progression_claims', 'course_evidence',
                             'course_target_observations', 'course_chapter_passes', 'course_continuation_entitlements')
            effects = {table: [tuple(row) for row in conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                       for table in effect_tables}
        opened = self.open_transfer(run)
        with transaction(self.db) as conn:
            tasks = [dict(row) for row in conn.execute("SELECT * FROM curriculum_unit_bindings WHERE run_id=? AND step_id LIKE 'transfer/%' ORDER BY step_id", (run['id'],))]
        self.assertEqual(len(tasks), 5)
        for index, task in enumerate(tasks):
            self.assertFalse(self.read_run(run)['completed'])
            opened = self.open_transfer(opened['run'])
            self.assertTrue(opened['url'].endswith('/' + task['task_key']))
            if task['activity'] == 'curriculum_unit':
                self.practice(task['task_key'])  # Transfer keeps strict zero-coin assertions.
            elif task['activity'] == 'unit_exchange':
                self.exchange(task['task_key'], run=run)
            else:
                self.production(task['activity'], task['task_key'], run=run)
            self.assertEqual(self.read_run(run)['completed'], index == len(tasks) - 1)
        finished = self.read_run(run)
        self.assertTrue(all(s['work_state'] == 'reviewed' for s in finished['steps'] if s['id'] != 'learn'))
        self.assertIsNone(finished['next_action'])
        self.assertEqual(self.client.get(finished['lesson_url']).status_code, 200)
        with transaction(self.db) as conn:
            for table, rows in effects.items():
                self.assertEqual([tuple(row) for row in conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid')], rows, table)
            for table in ('course_chapter_passes', 'course_checkpoint_attempts', 'course_continuation_entitlements', 'assessment_pilot_sessions'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0, table)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM activity_review_submissions WHERE review_status='reviewed'").fetchone()[0], 6)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM curriculum_unit_exchange_turns').fetchone()[0], 4)
            validate_saved_sequences(conn)
            from services.unit_exchange import audio_root
            validate_saved_reviews(conn, unit_exchange_audio_root=audio_root(self.db), require_audio=True)
            validate_saved_evidence(conn)
        domains = self.client.get('/api/v1/curriculum/summary').json['domains']
        self.assertEqual({d['id'] for d in domains}, {'language_use', 'reading', 'listening', 'writing', 'speaking'})
        self.assertTrue(all(d['latest'] is not None and d['pending'] is None for d in domains))
        self.assertEqual(next(d for d in domains if d['id'] == 'speaking')['latest']['condition'], 'unverified')
        self.assertEqual((self.writing.assess_writing.call_count, self.reading.assess_task.call_count, self.speaking.assess.call_count), (2, 2, 2))

    def test_complete_challenge_preserves_skipped_practice_and_new_run_uses_other_family(self):
        run = self.start()
        opened = self.open_transfer(run)
        with transaction(self.db) as conn:
            tasks = [dict(row) for row in conn.execute('SELECT * FROM curriculum_unit_bindings WHERE run_id=? ORDER BY step_id', (run['id'],))]
        self.assertEqual(len(tasks), 5)
        for task in tasks:
            self.assertFalse(self.read_run(run)['completed'])
            resumed = self.open_transfer(opened['run'])
            self.assertTrue(resumed['url'].endswith('/' + task['task_key']), resumed)
            opened = resumed
            if task['activity'] == 'curriculum_unit':
                self.practice(task['task_key'])
            elif task['activity'] == 'unit_exchange':
                self.exchange(task['task_key'])
            else:
                self.production(task['activity'], task['task_key'])
        finished = self.read_run(run)
        self.assertTrue(finished['completed'])
        self.assertIsNone(finished['next_action'])
        self.assertTrue(all(s['work_state'] == 'not_started' for s in finished['steps'] if s['id'] != 'transfer'))
        with transaction(self.db) as conn:
            for table in ('progression_events', 'progression_entries', 'course_chapter_passes'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0, table)
            validate_saved_sequences(conn)
            from services.unit_exchange import audio_root
            validate_saved_reviews(conn, unit_exchange_audio_root=audio_root(self.db), require_audio=True)
            validate_saved_evidence(conn)
        domains = self.client.get('/api/v1/curriculum/summary').json['domains']
        self.assertTrue(all(domain['latest'] is not None for domain in domains))
        self.assertEqual(next(d for d in domains if d['id'] == 'speaking')['latest']['condition'], 'unverified')
        following = self.start()
        self.assertNotEqual(following['id'], run['id'])
        self.open_transfer(following)
        with transaction(self.db) as conn:
            families = {row[0] for row in conn.execute('SELECT family_id FROM curriculum_transfer_exposure')}
        self.assertEqual(families, {'location-meeting-people-v1', 'location-meeting-update-v1'})
        self.assertTrue(self.read_run(run)['completed'])


class HostedCurriculumSequenceWalkthroughTests(CurriculumSequenceWalkthroughTests):
    """Repeat the same five-domain workflow through the actual /demo mount."""
    def setUp(self):
        from app import create_app
        from hosted import create_hosted_app
        from tests import test_hosted_guest_demo
        test_hosted_guest_demo.HostedGuestCompositionTests.setUp(self)
        self.writing, self.reading, self.speaking = Mock(), Mock(), Mock()
        self.app = create_hosted_app()
        dispatch = self.app.extensions['hosted_trial']
        dispatch.app_factory = lambda config: create_app(config, {'WritingService': self.writing,
            'ComprehensionService': self.reading, 'SpeakingAssessment': self.speaking})
        raw = self.app.test_client()
        self.assertEqual(raw.get('/demo', base_url=self.base).status_code, 302)
        state = raw.get('/demo/api/v1/user-session', base_url=self.base)
        self.assertEqual(state.status_code, 200)
        self.token = state.json['csrf_token']
        workspace = next(iter(dispatch.cache.values()))
        self.db = workspace.config['DB_PATH']
        self.assertTrue(workspace.config['HOSTED_GUEST_DEMO'])
        base = self.base
        # Simulate elapsed learner time while preserving the real write limit.
        # A whole lesson intentionally cannot be submitted in one second.
        clock = [dispatch.clock()]
        dispatch.clock = lambda: clock[0]

        def finished(response):
            # The WSGI server closes every completed response. Test clients
            # must do so explicitly to release hosted storage reservations.
            response.get_data()
            response.close()
            return response

        class DemoClient:
            def get(_, path, **kwargs):
                clock[0] += 3
                # Response links already carry the demo mount; packaged audio
                # remains public at /static, as in the browser.
                url = path if path.startswith(('/demo/', '/static/', '/post/assets/')) else '/demo' + path
                return finished(raw.get(url, base_url=base, **kwargs))

            def post(_, path, **kwargs):
                clock[0] += 3
                return finished(raw.post(path if path.startswith('/demo/') else '/demo' + path, base_url=base, **kwargs))

        self.client = DemoClient()
        self.configure_review_stubs()

        def close_executors():
            for tenant in dispatch.cache.values():
                for executor in tenant.extensions.get('trial_executors', []):
                    executor.shutdown(wait=True)
        self.addCleanup(close_executors)
