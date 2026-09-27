from tests.support import latest_schema_version
import base64
import io
import json
from pathlib import Path
import queue
import struct
import threading
import time
import unittest
from unittest.mock import Mock, patch
import wave

from repositories.learning_repository import transaction, timestamp
from services.live_conversation import _ReceivedAudio
from services.live_voice_provider import LiveVoiceProvider, session_config
from services.speech_provider import SpeechError
from tests.support import isolated_app
from tests.test_conversation import FakeAI, FakeSpeech


class FakeSocket:
    def __init__(self):
        self.incoming=queue.Queue();self.sent=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def send(self,data):
        event=json.loads(data);self.sent.append(event)
        if event['type']=='session.close': self.incoming.put({'type':'session.closed','event_id':'closed','usage':{'duration_seconds':1}})
    def recv(self,timeout=1):
        try: return json.dumps(self.incoming.get(timeout=min(timeout,.05)))
        except queue.Empty: raise TimeoutError()


class FakeLive:
    def __init__(self): self.ws=FakeSocket();self.creates=[]
    def create(self,session,scenario,sdp): self.creates.append((session,scenario,sdp));return 'live_opaque_id','v=0\r\nanswer'
    def attach(self,provider_id): return self.ws


class LiveConversationTests(unittest.TestCase):
    def setUp(self):
        self.provider,self.speech,self.ai=FakeLive(),FakeSpeech(),FakeAI()
        self.app=isolated_app(self,{'LiveVoiceProvider':self.provider,'SpeechProvider':self.speech,'ConversationAI':self.ai})
        self.service=self.app.extensions['learning']['live_conversation'];self.db=self.app.config['DB_PATH']
        self.client=self.app.test_client();self.token=self.client.get('/api/v1/household').json['csrf_token']
        self.dispatch=patch.object(self.service,'dispatch').start()
        self.review_dispatch=patch.object(self.service.reviews,'dispatch').start()
        self.review_request=patch.object(self.service.reviews,'request').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for runtime in list(self.service.connections.values()):
            runtime['stop'].set();runtime['closed'].wait(3)
        self.service.executor.shutdown(wait=True)
        self.service.reviews.executor.shutdown(wait=True)

    def post(self,path='',body=None):
        return self.client.post('/api/v1/live-conversations'+path,json=body or {},headers={'X-CSRF-Token':self.token})
    def start(self,key='first'):
        r=self.post('',{'submission_id':key});self.assertEqual(r.status_code,201,r.json);return r.json['id']
    def read(self,sid): return self.client.get('/api/v1/live-conversations/'+sid).json
    def connect(self,sid): return self.post('/'+sid+'/connect',{'sdp':'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'})
    def record(self,sid):
        capture=_ReceivedAudio(self.service,sid)
        data=struct.pack('<h',1000)*24000
        capture.append(data);capture.finish()
        return self.read(sid)['recordings'][0],data
    def run_job(self,rid): self.service.slots.acquire();self.service._analyse(rid)

    def test_separate_activity_start_idempotent_without_calling_provider(self):
        sid=self.start();self.assertEqual(self.start(),sid)
        self.assertEqual(self.provider.creates,[])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM conversation_sessions').fetchone()[0],0)
        self.assertEqual(self.post('',{'submission_id':'first','language':'ru'}).status_code,409)

    def test_orphan_call_cleanup_uses_tracked_executor(self):
        sid = self.start()
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE live_conversation_sessions SET state='connecting',provider_id='orphan-call' WHERE id=?", (sid,))
        with patch.object(self.service.executor, 'submit') as submit:
            result = self.post('/' + sid + '/finish')
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['state'], 'interrupted')
        submit.assert_called_once_with(self.service._close_orphan, sid, 'orphan-call')

    def test_signalling_retries_keep_one_paid_connection_and_hide_credentials(self):
        sid=self.start();first=self.connect(sid)
        self.assertEqual(first.status_code,200,first.json)
        self.assertEqual(self.connect(sid).json,first.json)
        self.assertEqual(len(self.provider.creates),1)
        self.assertNotIn('provider_id',self.read(sid));self.assertNotIn('sdp',self.read(sid))
        self.assertEqual(self.post('/'+sid+'/connect',{'sdp':'v=0\r\nm=audio different'}).status_code,409)
        runtime=self.service.connections[sid]
        self.post('/'+sid+'/finish');self.assertTrue(runtime['closed'].wait(3))
        self.assertEqual(self.read(sid)['state'],'completed');self.assertTrue(self.read(sid)['finalized'])
        self.assertEqual(self.connect(sid).status_code,409)

    def test_sideband_records_pcm_before_asr_and_captions_are_not_assessment_input(self):
        sid=self.start();self.connect(sid);runtime=self.service.connections[sid]
        data=struct.pack('<h',1000)*24000
        self.provider.ws.incoming.put({'type':'session.started'})
        self.provider.ws.incoming.put({'type':'session.input_transcript.delta','event_id':'caption1','delta':'Она читает.','start_ms':0,'end_ms':1000})
        self.provider.ws.incoming.put({'type':'session.input_audio.append','audio':base64.b64encode(data).decode()})
        self.post('/'+sid+'/finish');self.assertTrue(runtime['closed'].wait(3))
        saved=self.read(sid);recording=saved['recordings'][0]
        original=self.client.get(recording['audio_url'])
        self.assertEqual(original.status_code,200);self.assertEqual(original.headers['Cache-Control'],'no-store')
        with wave.open(io.BytesIO(original.data)) as wav: self.assertEqual(wav.readframes(24000),data)
        self.run_job(recording['id'])
        self.assertEqual(self.ai.assessments,[])  # New sessions use one final audio review.
        self.assertEqual(self.read(sid)['captions'][0]['delta'],'Она читает.')
        self.assertIn('читаю',self.read(sid)['recordings'][0]['transcript']['text'])

    def test_audio_chunks_are_contiguous_and_never_trimmed(self):
        sid=self.start();capture=_ReceivedAudio(self.service,sid)
        first=struct.pack('<h',800)*24000*8; silence=b'\0\0'*24000; second=struct.pack('<h',-900)*24000
        capture.append(first);capture.append(silence);capture.append(second);capture.finish()
        saved=self.read(sid);self.assertEqual(len(saved['recordings']),2)
        self.assertEqual(saved['recordings'][1]['start_sample'],9*24000)
        joined=b''
        for recording in saved['recordings']:
            with wave.open(io.BytesIO(self.client.get(recording['audio_url']).data)) as wav: joined+=wav.readframes(wav.getnframes())
        self.assertEqual(joined,first+silence+second)

    def test_notes_retry_reuses_original_transcription(self):
        sid=self.start();recording,_=self.record(sid);rid=recording['id']
        from services.conversation_ai import SCENARIO
        self.service._session(sid,scenario_json=json.dumps(SCENARIO))
        assess=self.ai.assess;self.ai.assess=Mock(side_effect=SpeechError('Could not finish'))
        self.run_job(rid);self.assertEqual(self.read(sid)['recordings'][0]['state'],'failed')
        self.ai.assess=assess;self.run_job(rid)
        self.assertEqual(self.speech.calls,[('mai','verbatim')]);self.assertEqual(self.read(sid)['recordings'][0]['state'],'ready')
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_reward_entries').fetchone()[0],0)

    def test_no_providers_run_on_options_or_saved_reads(self):
        sid=self.start();self.record(sid)
        for _ in range(3): self.read(sid);self.client.get('/api/v1/live-conversations/options')
        self.assertEqual(self.provider.creates,[]);self.assertEqual(self.speech.calls,[])

    def test_restart_recovery_seals_partial_wav_without_inventing_a_completed_call(self):
        sid=self.start();capture=_ReceivedAudio(self.service,sid)
        capture.append(struct.pack('<h',1000)*24000)
        # writeframes has patched the WAV header, but the DB still says capturing.
        capture.writer.close();capture.writer=None
        self.service._session(sid,state='live')
        self.assertTrue(self.read(sid)['needs_recovery'])
        recovered=self.post('/'+sid+'/finish').json
        self.assertEqual(recovered['state'],'interrupted');self.assertFalse(recovered['finalized'])
        self.assertEqual(recovered['recordings'][0]['state'],'queued')
        self.assertEqual(recovered['recordings'][0]['sample_count'],24000)

    def test_close_watchdog_when_browser_heartbeat_is_lost(self):
        sid=self.start();self.connect(sid);runtime=self.service.connections[sid]
        with transaction(self.db,write=True) as conn:
            conn.execute('UPDATE live_conversation_sessions SET heartbeat_at=? WHERE id=?',(timestamp()-60,sid))
        self.assertTrue(runtime['closed'].wait(3));self.assertEqual(self.read(sid)['state'],'completed')

    def test_events_deduplicate_without_rewriting_original_fragments(self):
        sid=self.start();event={'type':'session.input_transcript.delta','event_id':'one','delta':' без...','start_ms':1,'end_ms':2}
        self.service._event(sid,event);self.service._event(sid,event)
        self.assertEqual(len(self.read(sid)['captions']),1);self.assertEqual(self.read(sid)['captions'][0]['delta'],' без...')

    def test_csrf_ownership_and_audio_isolation(self):
        sid=self.start();recording,_=self.record(sid)
        self.assertEqual(self.client.post('/api/v1/live-conversations/'+sid+'/finish',json={}).status_code,403)
        self.assertEqual(self.client.post('/api/v1/live-conversations/'+sid+'/finish',json={},headers={'X-CSRF-Token':self.token,'Origin':'https://wrong.invalid'}).status_code,403)
        other=self.start('other')
        self.assertEqual(self.client.get(f'/api/v1/live-conversations/{other}/recordings/{recording["id"]}').status_code,404)
        with transaction(self.db,write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)",(timestamp(),))
            conn.execute("UPDATE live_conversation_sessions SET profile_id='other' WHERE id=?",(sid,))
        self.assertEqual(self.client.get(recording['audio_url']).status_code,404)
        self.assertEqual(self.post('/'+sid+'/finish').status_code,404)

    def test_backup_and_delete_include_live_recordings(self):
        from services.learning_backup import backup_learning_store
        sid=self.start();recording,data=self.record(sid)
        self.run_job(recording['id']);self.post('/'+sid+'/finish')
        target=Path(self.db).parent/'snapshot'
        manifest=backup_learning_store(self.db,self.app.extensions['learning']['assets'],target)
        self.assertEqual(len(manifest['live_conversation_audio']),1)
        self.assertTrue((target/manifest['live_conversation_audio'][0]['file']).is_file())
        self.assertEqual(self.post('/'+sid+'/delete').json,{'deleted':True});self.assertFalse(list(self.service.root.iterdir()))

    def test_migration_preserves_existing_record_and_send_sessions(self):
        from migrations import upgrade_database
        with transaction(self.db,write=True) as conn:
            conn.execute("INSERT INTO conversation_sessions(id,profile_id,mode,scenario_json,voice_id,ui_language,start_key,created_at) VALUES ('existing','personal-learning','conversation','{}','voice','en','original',1)")
        self.assertEqual(upgrade_database(self.db,backup=False)[0],latest_schema_version())
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute("SELECT start_key FROM conversation_sessions WHERE id='existing'").fetchone()[0],'original')


class LiveVoiceProviderTests(unittest.TestCase):
    def test_voice_and_delegation_share_russian_scenario_boundaries(self):
        from services.conversation_ai import SCENARIO
        from services.conversation_policy import cafe_instructions
        session={'model':'gpt-live-1','backend_model':'gpt-5.6-luna','voice':'cedar','language':'en'}
        config=session_config(session,SCENARIO)
        for prompt in (config['instructions'],config['delegation']['responses']['instructions']):
            self.assertIn(cafe_instructions(SCENARIO),prompt)
            self.assertNotIn('Briefly explain in English',prompt)
        self.assertEqual(config['audio']['output']['voice'],'cedar')
        self.assertNotIn('language',config['audio'])

    def test_provider_errors_do_not_expose_body_or_retry_with_another_model(self):
        from services.conversation_ai import SCENARIO
        response=Mock(ok=False,status_code=403,text='sensitive provider detail')
        with patch('services.live_voice_provider.requests.post',return_value=response) as post:
            with self.assertRaises(SpeechError) as error:
                LiveVoiceProvider({'OPENAI_API_KEY':'secret'}).create({'model':'gpt-live-1','backend_model':'gpt-5.6-luna','voice':'marin'},SCENARIO,'v=0')
        self.assertNotIn('sensitive',str(error.exception));self.assertEqual(post.call_count,1)
        config=post.call_args.kwargs['json']['session']
        self.assertEqual(config['model'],'gpt-live-1');self.assertNotIn('format',config['audio'])
        self.assertFalse(config['store'])
        self.assertEqual([tool['name'] for tool in config['delegation']['responses']['tools']], ['finish_speaking'])
