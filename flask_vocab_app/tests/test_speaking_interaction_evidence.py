"""Original-audio boundaries for the six additional authored A1 situations.

Synthetic PCM and stub reports check storage and routing, not acoustic accuracy.
"""
from copy import deepcopy
import json
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from repositories.learning_repository import transaction
from repositories.speaking_repository import choose_variant
from services.activity_evidence import load_contract, save_report, validate_saved_evidence
from services.live_conversation import _ReceivedAudio
from services.speaking_assessment import SpeakingAssessment
from services.speaking_evidence import recorded_audio_source, speaking_task_contract, verify_audio_source
from tests.support import isolated_app


SEEDS = {
    'cafe-a1-takeaway-v2': ('cafe', 'request-order', ['objective-1']),
    'cafe-a1-warm-lunch-v2': ('cafe', 'request-order', ['objective-1']),
    'cafe-a1-two-drinks-v2': ('cafe', 'request-order', ['objective-1']),
    'meet-someone-a1-classmate-v2': ('meet-someone', 'exchange-names', ['objective-1', 'objective-2']),
    'meet-someone-a1-neighbour-v2': ('meet-someone', 'exchange-names', ['objective-1', 'objective-2']),
    'meet-someone-a1-club-v2': ('meet-someone', 'exchange-names', ['objective-1', 'objective-2']),
}


def feedback(scenario, contract):
    return {
        'transcript': 'Можно воду и булочку?' if scenario['scenario_id'] == 'cafe' else 'Меня зовут Ира. А вас?',
        'speech_status': 'insufficient', 'uncertain_phrases': [],
        'grammar': {'score': None, 'reason': 'There is too little speech for a broad score.', 'evidence': []},
        'fluency': {'score': None, 'reason': 'There is too little speech for a broad score.', 'evidence': []},
        'goals': [{'id': identity, 'status': 'not_yet', 'evidence': []} for identity in scenario['goal_ids']],
        'summary': 'This brief response supplies useful task evidence.', 'next_step': 'Try another short exchange.',
        'corrections': [], 'uncertainty': '',
        'criterion_report': {'contract_sha256': contract['contract_sha256'], 'judgements': [{
            'criterion_id': criterion['id'], 'outcome': 'satisfied', 'score': 2,
            'feedback': 'The requested communicative action is audible.',
            'evidence': [{'start_ms': 100, 'end_ms': 800}]} for criterion in contract['criteria']]},
    }


class SpeakingInteractionEvidenceTests(unittest.TestCase):
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

    def scenario(self, seed):
        with transaction(self.db) as conn:
            return choose_variant(conn, SEEDS[seed][0], seed=seed, level='A1')

    def start(self, seed):
        body = {'submission_id': seed, 'scenario_id': SEEDS[seed][0], 'scenario_seed': seed, 'target_level': 'A1'}
        reply = self.client.post('/api/v1/live-conversations', json=body, headers=self.headers)
        self.assertEqual(reply.status_code, 201, reply.json)
        with transaction(self.db) as conn:
            contract = load_contract(conn, self.profile, 'speaking', reply.json['id'])
        return reply.json, contract

    def record(self, sid):
        capture = _ReceivedAudio(self.live, sid)
        capture.append(b'\0\0' * 2400 + struct.pack('<h', 900) * 16800 + b'\0\0' * 4800)
        capture.finish()
        with transaction(self.db) as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM live_conversation_recordings WHERE session_id=? ORDER BY ordinal', (sid,))]

    def test_all_six_seeded_situations_freeze_only_the_elicited_action(self):
        for seed, (family, criterion, goals) in SEEDS.items():
            with self.subTest(seed=seed):
                saved, contract = self.start(seed)
                self.assertEqual(contract['content']['scenario'], saved['scenario'])
                self.assertEqual(contract['content']['goal_ids'], goals)
                self.assertEqual(len(contract['criteria']), 1)
                item = contract['criteria'][0]
                self.assertEqual(item['id'], criterion)
                self.assertEqual(item['requirement_id'], 'a1.speaking.request-and-response' if family == 'cafe' else 'a1.speaking.ask-and-answer')
                self.assertEqual(item['response_mode'], 'independent_speaking')
                self.assertNotEqual(item['target_id'], item['requirement_id'])
                self.assertNotIn('grammar', item['target_id'])
                self.assertIn('original learner audio', item['expectation'])
                self.assertEqual(self.start(seed), (saved, contract))
        with transaction(self.db) as conn:
            all_variants = [json.loads(row[0]) for row in conn.execute('SELECT payload_json FROM speaking_scenario_variants')]
        mapped = {s['seed'] for s in all_variants if speaking_task_contract(s) is not None}
        self.assertEqual(mapped, set(SEEDS) | {'directions-a1-park-v2', 'directions-a1-pharmacy-v2', 'directions-a1-post-office-v2'})

    def test_changed_elicitation_cannot_silently_keep_the_mapping(self):
        for seed in SEEDS:
            source = self.scenario(seed)
            for field in ('goals', 'completion_criteria', 'worker_brief', 'opening', 'target_level', 'variation'):
                altered = deepcopy(source)
                if field in ('goals', 'completion_criteria'):
                    altered[field][0] = 'An unrelated communication goal.'
                elif field == 'variation':
                    altered[field]['facts']['unissued_fact'] = 'not the authored bundle'
                else:
                    altered[field] = 'changed'
                with self.subTest(seed=seed, field=field), self.assertRaises(ValueError):
                    speaking_task_contract(altered)

    def test_reviews_bind_originals_not_transcripts_or_general_scores(self):
        for seed in ('cafe-a1-takeaway-v2', 'meet-someone-a1-neighbour-v2'):
            saved, contract = self.start(seed)
            sid, scenario = saved['id'], saved['scenario']
            rows = self.record(sid)
            expected = recorded_audio_source(rows, self.live.root)
            original = {row['filename']: (self.live.root / row['filename']).read_bytes() for row in rows}
            self.live._event(sid, {'type': 'session.input_transcript.delta', 'event_id': seed + '-caption',
                                   'delta': 'REPAIRED CAPTION MUST NOT BECOME SOURCE', 'start_ms': 0, 'end_ms': 100})
            self.assessor.assess.return_value = {**feedback(scenario, contract), 'basis': 'audio_review',
                'rubric_version': 'speaking-audio-v1', 'model': 'offline-audio', 'rewards_applied': False}
            finished = self.client.post('/api/v1/live-conversations/' + sid + '/finish', json={}, headers=self.headers)
            self.assertEqual(finished.status_code, 200, finished.json)
            self.reviews._work(sid)
            loaded = self.client.get('/api/v1/live-conversations/' + sid).json
            self.assertEqual(loaded['review']['state'], 'ready', loaded)
            report = loaded['review']['report']
            self.assertEqual(report['audio_source'], expected)
            self.assertEqual(report['audio_source']['independence'], 'unverified')
            self.assertIsNone(report['grammar']['score']); self.assertIsNone(report['fluency']['score'])
            self.assertEqual(report['criterion_details'][0]['label'], 'Order water and a bread roll' if scenario['scenario_id'] == 'cafe' else 'Exchange names')
            self.assertNotIn('REPAIRED', json.dumps(self.assessor.assess.call_args.args[2]))
            self.assertEqual(original, {row['filename']: (self.live.root / row['filename']).read_bytes() for row in rows})
            with transaction(self.db) as conn:
                validate_saved_evidence(conn, audio_root=self.live.root)
                with self.assertRaises(LookupError):
                    verify_audio_source(conn, 'wrong-profile', sid, expected)
                with self.assertRaises(ValueError):
                    save_report(conn, self.profile, 'speaking', sid, 'wrong-session', report['criterion_report'], audio_source=expected)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations WHERE demonstrated=1').fetchone()[0], 0)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0], 0)

    def test_procedural_a2_original_audio_uses_frozen_fact_dependent_criterion(self):
        response = self.client.post('/api/v1/live-conversations', json={
            'submission_id':'procedural-review', 'scenario_id':'shop', 'target_level':'A2',
            'scenario_seed':'shop-a2-p3-0'}, headers=self.headers)
        self.assertEqual(response.status_code,201,response.json)
        sid=response.json['id']
        self.assertNotIn('diagnostic_mapping',response.json['scenario'])
        with transaction(self.db) as conn:
            contract=load_contract(conn,self.profile,'speaking',sid)
        scenario=contract['content']['scenario']
        self.assertEqual(contract['level'],'A2')
        self.assertIn(scenario['goals'][1],contract['criteria'][0]['expectation'])
        rows=self.record(sid)
        self.assessor.assess.return_value={**feedback(scenario,contract),'basis':'audio_review'}
        self.client.post('/api/v1/live-conversations/'+sid+'/finish',json={},headers=self.headers)
        self.reviews._work(sid)
        loaded=self.client.get('/api/v1/live-conversations/'+sid).json
        self.assertEqual(loaded['review']['state'],'ready',loaded)
        self.assertEqual(self.assessor.assess.call_args.kwargs['curriculum_contract'],contract)
        self.assertEqual(loaded['review']['report']['audio_source'],recorded_audio_source(rows,self.live.root))
        self.assertEqual(loaded['review']['report']['audio_source']['independence'],'unverified')
        with transaction(self.db) as conn:
            validate_saved_evidence(conn,audio_root=self.live.root)

    def test_old_issued_situation_does_not_acquire_new_contract_on_resume(self):
        seed = 'meet-someone-a1-classmate-v2'
        with patch('services.live_conversation.speaking_task_contract', return_value=None):
            saved, contract = self.start(seed)
        self.assertIsNone(contract)
        resumed, contract = self.start(seed)
        self.assertEqual(resumed, saved); self.assertIsNone(contract)

    def test_step_through_selected_responses_do_not_acquire_speaking_evidence(self):
        step = self.app.extensions['learning']['step_conversation']
        with self.client.session_transaction() as browser:
            access = browser['personal_access_id']
        with patch.object(step, '_require_provider'), patch.object(step, '_prepare', return_value=False):
            for seed in SEEDS:
                step.start(access, {'submission_id': seed, 'scenario_id': SEEDS[seed][0], 'scenario_seed': seed, 'target_level': 'A1'})
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_task_contracts WHERE activity=\'speaking\'').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0], 0)

    def test_live_interaction_prompt_preserves_original_audio_and_correct_scope(self):
        saved, contract = self.start('cafe-a1-takeaway-v2')
        rows = self.record(saved['id'])
        path = self.live.root / rows[0]['filename']; original = path.read_bytes()
        response = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
            content=json.dumps(feedback(saved['scenario'], contract)), refusal=None))])
        with patch('services.speaking_assessment.openai_client') as factory:
            create = factory.return_value.chat.completions.create
            create.return_value = response
            result = SpeakingAssessment({'OPENAI_API_KEY': 'offline-only'}).assess(path, saved['scenario'],
                [{'role': 'user', 'content': 'A repaired learner transcript.'}], curriculum_contract=contract, include_provenance=True)
        sent = create.call_args.kwargs
        instruction = sent['messages'][0]['content']
        self.assertNotIn('recorded message is not an interactive conversation', instruction)
        self.assertNotIn('Judge only the elicited location question', instruction)
        context = json.loads(sent['messages'][1]['content'][0]['text'])
        self.assertEqual(context['other_speaker_context'], [])
        self.assertEqual(context['curriculum_contract'], contract)
        self.assertEqual(result['assessment_provenance']['model'], sent['model'])
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
