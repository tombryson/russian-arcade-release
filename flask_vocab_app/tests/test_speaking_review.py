import json
from pathlib import Path
import struct
import threading
import time
import unittest
from unittest.mock import Mock, patch
import wave

from repositories.learning_repository import timestamp, transaction
from services.conversation_ai import SCENARIO
from services.activity_evidence import load_contract
from services.live_conversation import _ReceivedAudio
from services.speaking_evidence import recorded_audio_source
from services.speech_provider import SpeechError
from tests.support import isolated_app


class SpeakingReviewTests(unittest.TestCase):
    def setUp(self):
        self.assessor = Mock()
        self.assessor.assess.return_value = {'basis':'audio_review','grammar':{'score':3},'fluency':{'score':4}}
        self.app = isolated_app(self, {'SpeakingAssessment':self.assessor})
        self.live = self.app.extensions['learning']['live_conversation']
        self.reviews = self.live.reviews
        self.client = self.app.test_client()
        self.token = self.client.get('/api/v1/household').json['csrf_token']
        self.patch_dispatch = patch.object(self.reviews,'dispatch').start()
        patch.object(self.live,'dispatch').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda:self.live.executor.shutdown(wait=True))
        self.addCleanup(lambda:self.reviews.executor.shutdown(wait=True))

    def post(self, path='', body=None):
        return self.client.post('/api/v1/live-conversations'+path, json=body or {},headers={'X-CSRF-Token':self.token})

    def session(self, key='test', historical=False):
        # Generic lifecycle fixtures intentionally exercise an uncontracted
        # situation; the dedicated A1 evidence tests supply criterion reports.
        value = self.post('',{'submission_id':key,'target_level':'A2',
                             'scenario_seed':'cafe-a2-milk-v2'}).json
        if historical:
            self.live._session(value['id'],scenario_json=json.dumps(SCENARIO))
        return value['id']

    def record(self, sid):
        capture = _ReceivedAudio(self.live,sid)
        voiced = struct.pack('<h',900)*24000*8
        silence = b'\0\0'*24000
        audio = voiced + silence
        capture.append(voiced)
        capture.append(silence)
        capture.append(struct.pack('<h',700)*24000)
        capture.finish()
        return audio + struct.pack('<h',700)*24000

    def read(self, sid):
        return self.client.get('/api/v1/live-conversations/'+sid).json

    def run_review(self, sid):
        self.reviews._work(sid)

    def test_new_calls_keep_their_seed_and_avoid_recent_repeats(self):
        first=self.post('',{'submission_id':'one'}).json
        self.assertEqual(first['scenario'],self.post('',{'submission_id':'one'}).json['scenario'])
        second=self.post('',{'submission_id':'two'}).json
        self.assertNotEqual(first['scenario']['seed'],second['scenario']['seed'])
        self.assertEqual(self.assessor.assess.call_count,0)

    def test_preview_is_read_only_and_saved_call_uses_the_selected_situation(self):
        preview=self.client.get('/api/v1/live-conversations/options').json['scenario']
        another=self.client.get('/api/v1/live-conversations/options?exclude_seed='+preview['seed']).json['scenario']
        self.assertNotEqual(preview['seed'],another['seed'])
        with transaction(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM live_conversation_sessions').fetchone()[0],0)
        created=self.post('',{'submission_id':'preview','scenario_seed':preview['seed']}).json
        self.assertEqual(created['scenario'],preview)
        self.assertEqual(self.post('',{'submission_id':'preview','scenario_seed':another['seed']}).status_code,409)
        self.assertEqual(self.post('',{'submission_id':'bad','scenario_seed':'arbitrary instructions'}).status_code,400)

    def test_full_audio_is_untrimmed_and_learner_asr_is_not_sent_to_reviewer(self):
        sid=self.session();expected=self.record(sid)
        self.live._event(sid,{'type':'session.input_transcript.delta','event_id':'u','delta':'NORMALIZED LEARNER WORDS','start_ms':2,'end_ms':3})
        self.live._event(sid,{'type':'session.output_transcript.delta','event_id':'a','delta':'Что будете пить?','start_ms':0,'end_ms':1})
        def assess(path,scenario,dialogue,language):
            with wave.open(str(path)) as source:
                self.assertEqual(source.readframes(source.getnframes()),expected)
            self.assertEqual(dialogue,[{'role':'assistant','content':'Что будете пить?'}])
            self.assertEqual(language,'en')
            self.assertIn('seed',scenario)
            return {'basis':'audio_review','transcript':'Original words'}
        self.assessor.assess.side_effect=assess
        self.post('/'+sid+'/finish');self.run_review(sid)
        self.assertEqual(self.read(sid)['review']['state'],'ready')
        self.assertEqual(len(list(self.live.root.glob('*.wav'))),2)
        self.assertFalse(list(self.live.root.glob('review-*')))

    def test_finished_read_and_repeated_finish_never_regenerate_a_grade(self):
        sid=self.session();self.record(sid)
        self.post('/'+sid+'/finish');self.run_review(sid)
        for _ in range(3):
            self.read(sid);self.post('/'+sid+'/finish');self.post('/'+sid+'/review')
        self.assertEqual(self.assessor.assess.call_count,1)
        with transaction(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_reward_entries').fetchone()[0],0)

    def test_failed_review_retries_only_on_explicit_post_and_keeps_originals(self):
        sid=self.session();self.record(sid)
        self.assessor.assess.side_effect=SpeechError('Please retry the audio review.')
        self.post('/'+sid+'/finish');self.run_review(sid)
        for _ in range(2): self.post('/'+sid+'/finish');self.read(sid)
        self.assertEqual(self.read(sid)['review']['state'],'failed')
        self.assertEqual(self.assessor.assess.call_count,1)
        self.assessor.assess.side_effect=None
        self.post('/'+sid+'/review');self.run_review(sid)
        self.assertEqual(self.read(sid)['review']['state'],'ready')
        self.assertEqual(self.assessor.assess.call_count,2)

    def test_archiving_during_assessment_keeps_the_paid_report_without_awarding_or_retrying(self):
        value=self.post('',{'submission_id':'archive-during-review','scenario_id':'cafe',
                           'scenario_seed':'cafe-a1-warm-lunch-v2','target_level':'A1'}).json
        sid=value['id'];self.record(sid)
        report={
            'basis':'audio_review','rubric_version':'speaking-audio-v1','model':'test-audio',
            'transcript':'Можно суп и чай, пожалуйста? Я буду есть здесь. Сколько всего? Спасибо, больше ничего.',
            'speech_status':'russian','uncertain_phrases':[],
            'grammar':{'score':5,'reason':'Your requests were clear and accurate.','evidence':['Можно суп и чай, пожалуйста?']},
            'fluency':{'score':4,'reason':'You kept your requests moving.','evidence':['Сколько всего?']},
            'goals':[
                {'id':'objective-1','status':'completed','evidence':['Можно суп и чай, пожалуйста?']},
                {'id':'objective-2','status':'completed','evidence':['Я буду есть здесь.']},
                {'id':'objective-3','status':'completed','evidence':['Сколько всего?']},
            ],
            'summary':'You ordered soup and tea, chose to eat inside and asked the total.',
            'next_step':'Try ordering for a friend next time.','corrections':[],'uncertainty':'',
        }
        with transaction(self.app.config['DB_PATH']) as conn:
            profile=conn.execute('SELECT profile_id FROM live_conversation_sessions WHERE id=?',(sid,)).fetchone()[0]
            contract=load_contract(conn,profile,'speaking',sid)
            recordings=[dict(row) for row in conn.execute('SELECT * FROM live_conversation_recordings WHERE session_id=? ORDER BY ordinal',(sid,))]
        report['criterion_report']={'contract_sha256':contract['contract_sha256'],'judgements':[{
            'criterion_id':'request-order','outcome':'satisfied','score':2,
            'feedback':'Both requested menu items are audible.','evidence':[{'start_ms':100,'end_ms':800}]}]}
        expected={**report,'audio_source':recorded_audio_source(recordings,self.live.root)}
        def finish_after_archive(*args,**kwargs):
            self.assertEqual(kwargs['curriculum_contract'],contract)
            with transaction(self.app.config['DB_PATH'],write=True) as conn:
                conn.execute("UPDATE learning_profiles SET archived=1 WHERE id=(SELECT profile_id FROM live_conversation_sessions WHERE id=?)",(sid,))
            return report
        self.assessor.assess.side_effect=finish_after_archive
        self.post('/'+sid+'/finish');self.run_review(sid)
        with transaction(self.app.config['DB_PATH']) as conn:
            saved=self.reviews.read(conn,sid)
            self.assertEqual(saved['state'],'ready')
            self.assertEqual(saved['report'],expected)
            self.assertFalse(saved['retryable'])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM progression_events WHERE activity='speaking' AND source_key=?",(sid,)).fetchone()[0],0)
        self.assessor.assess.assert_called_once()
        # Restoring the profile and opening/re-requesting feedback reuses the
        # saved report; a reward eligibility change does not buy another review.
        with transaction(self.app.config['DB_PATH'],write=True) as conn:
            conn.execute("UPDATE learning_profiles SET archived=0 WHERE id=(SELECT profile_id FROM live_conversation_sessions WHERE id=?)",(sid,))
        self.patch_dispatch.reset_mock()
        self.assertEqual(self.post('/'+sid+'/review').status_code,202)
        detail={'label':'Order soup and tea','label_ru':'Закажите суп и чай',
                'outcome':'satisfied','feedback':'Both requested menu items are audible.'}
        self.assertEqual(self.read(sid)['review']['report'],{**expected,'criterion_details':[detail]})
        self.patch_dispatch.assert_not_called()
        self.assessor.assess.assert_called_once()

    def test_historical_audio_is_graded_only_when_requested(self):
        sid=self.session(historical=True);self.record(sid)
        self.post('/'+sid+'/finish')
        self.assertIsNone(self.read(sid)['review'])
        self.post('/'+sid+'/review');self.run_review(sid)
        self.assertEqual(self.read(sid)['review']['state'],'ready')

    def test_no_audio_or_missing_segment_never_gets_a_score(self):
        sid=self.session();self.post('/'+sid+'/finish');self.run_review(sid)
        self.assertEqual(self.read(sid)['review']['state'],'failed')
        other=self.session('other');self.record(other)
        self.post('/'+other+'/finish')
        with transaction(self.app.config['DB_PATH'],write=True) as conn:
            conn.execute('UPDATE live_conversation_recordings SET start_sample=start_sample+1 WHERE session_id=? AND ordinal=2',(other,))
        self.run_review(other)
        self.assertIn('gap',self.read(other)['review']['error'])
        self.assessor.assess.assert_not_called()

    def test_lease_prevents_duplicate_calls_and_allows_explicit_restart_recovery(self):
        sid=self.session();self.record(sid);self.post('/'+sid+'/finish')
        with transaction(self.app.config['DB_PATH'],write=True) as conn:
            conn.execute("UPDATE speaking_reviews SET state='analysing',lease_until=? WHERE session_id=?",(timestamp()+120,sid))
        self.post('/'+sid+'/review')
        self.assertFalse(self.read(sid)['review']['retryable'])
        with transaction(self.app.config['DB_PATH'],write=True) as conn:
            conn.execute('UPDATE speaking_reviews SET lease_until=0 WHERE session_id=?',(sid,))
        self.assertTrue(self.read(sid)['review']['retryable'])
        self.post('/'+sid+'/review');self.run_review(sid)
        self.assertEqual(self.read(sid)['review']['state'],'ready')

    def test_grading_rejects_active_call_and_obeys_ownership_and_csrf(self):
        sid=self.session();self.record(sid)
        self.assertEqual(self.post('/'+sid+'/review').status_code,409)
        self.assertEqual(self.client.post('/api/v1/live-conversations/'+sid+'/review',json={}).status_code,403)
        with transaction(self.app.config['DB_PATH'],write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)",(timestamp(),))
            conn.execute("UPDATE live_conversation_sessions SET profile_id='other' WHERE id=?",(sid,))
        self.assertEqual(self.post('/'+sid+'/review').status_code,404)

    def test_delete_waits_for_review_then_cascades_report(self):
        sid=self.session();self.record(sid);self.post('/'+sid+'/finish')
        self.assertEqual(self.post('/'+sid+'/delete').status_code,409)
        self.run_review(sid)
        self.assertTrue(self.post('/'+sid+'/delete').json['deleted'])
        with transaction(self.app.config['DB_PATH']) as conn:
            self.assertIsNone(conn.execute('SELECT * FROM speaking_reviews WHERE session_id=?',(sid,)).fetchone())

    def test_second_queued_review_keeps_polling_and_worker_drains_it(self):
        from services.speaking_review import SpeakingReviewService
        entered, release = threading.Event(), threading.Event()
        def assess(*args):
            entered.set()
            release.wait(5)
            return {'basis':'audio_review'}
        self.assessor.assess.side_effect=assess
        self.reviews.dispatch=SpeakingReviewService.dispatch.__get__(self.reviews)
        first=self.session('first');self.record(first)
        second=self.session('second');self.record(second)
        try:
            self.post('/'+first+'/finish')
            self.assertTrue(entered.wait(2))
            self.post('/'+second+'/finish')
            queued=self.read(second)['review']
            self.assertEqual(queued['state'],'queued')
            self.assertFalse(queued['retryable'])
            release.set()
            deadline=time.monotonic()+4
            while time.monotonic()<deadline and self.read(second)['review']['state']!='ready':
                time.sleep(.02)
            self.assertEqual(self.read(second)['review']['state'],'ready')
            self.assertEqual(self.assessor.assess.call_count,2)
        finally:
            release.set()
