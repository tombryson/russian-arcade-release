import io
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock, patch
import wave

from repositories.learning_repository import transaction, timestamp
from services.conversation_ai import ConversationAI
from services.speech_provider import SpeechProvider, SpeechError, audio_info
from tests.support import isolated_app


def recording(seconds=1):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setparams((1,2,16000,0,'NONE','not compressed'))
        out.writeframes(struct.pack('<h', 1000) * int(16000*seconds))
    return buffer.getvalue()


class FakeSpeech:
    def __init__(self):
        self.calls, self.voices = [], []

    def transcribe(self, path, provider='mai', style='verbatim'):
        self.calls.append((provider,style))
        text = 'Она каждый день читаю книгу.'
        return {'text':text,'model':provider,'provider':provider,'style':style,'words':[],
                'latency_ms':1,'raw':{'text':text},'settings':{}}

    def speak(self, text, voice):
        self.voices.append(voice)
        return b'test-only-mp3'


class FakeAI:
    def __init__(self):
        self.replies, self.assessments = [], []

    def reply(self, scenario, history):
        self.replies.append(history)
        return {'russian':'Что будете есть?', 'english':'What would you like to eat?'}

    def assess(self, text, context, language='en'):
        self.assessments.append(text)
        return {'basis':'unverified_transcript','communication':'An understandable reply.',
                'uncertainty':'','corrections':[{'original':'читаю','replacement':'читает','explanation':'Third person singular.'}],
                'grammar_score':None,'fluency_score':None,'rewards_applied':False}


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.speech, self.ai = FakeSpeech(), FakeAI()
        self.app = isolated_app(self, {'SpeechProvider':self.speech,'ConversationAI':self.ai})
        self.service = self.app.extensions['learning']['conversation']
        self.addCleanup(lambda:self.service.executor.shutdown(wait=True))
        self.client = self.app.test_client()
        self.token = self.client.get('/api/v1/household').json['csrf_token']
        self.dispatch = patch.object(self.service,'dispatch').start()
        self.addCleanup(patch.stopall)
        self.db = self.app.config['DB_PATH']

    def post(self, path, body=None):
        return self.client.post('/api/v1/conversations'+path,json=body or {},headers={'X-CSRF-Token':self.token})

    def start(self, mode='conversation'):
        result = self.post('',{'submission_id':'start','mode':mode})
        self.assertEqual(result.status_code,201,result.json)
        return result.json['id']

    def submit(self, sid, key='turn-1', data=None, case=None):
        result = self.client.post(f'/api/v1/conversations/{sid}/turns',data={
            'submission_id':key,'case_id':case or '', 'audio':(io.BytesIO(data if data is not None else recording()),'voice.wav')},
            headers={'X-CSRF-Token':self.token})
        return result

    def run_job(self, tid):
        self.service.slots.acquire()
        self.service._work(tid)

    def read(self, sid):
        result = self.client.get('/api/v1/conversations/'+sid)
        self.assertEqual(result.status_code,200,result.json)
        return result.json

    def test_personal_start_is_idempotent_and_does_not_call_providers(self):
        sid = self.start()
        self.assertEqual(self.start(),sid)
        self.assertEqual(self.post('',{'submission_id':'start','mode':'lab'}).status_code,409)
        self.assertEqual(self.speech.calls,[])
        self.assertEqual(self.ai.replies,[])
        self.assertEqual(self.read(sid)['profile_id'],'personal-learning')

    def test_upload_preserves_original_audio_and_transcript_and_separates_feedback(self):
        sid = self.start(); saved = self.submit(sid).json; tid = saved['turns'][0]['id']
        self.assertEqual(saved['turns'][0]['state'],'queued')
        self.run_job(tid)
        turn = self.read(sid)['turns'][0]
        self.assertEqual(turn['state'],'ready')
        self.assertIn('читаю',turn['transcript']['text'])
        self.assertEqual(turn['assessment']['corrections'][0]['replacement'],'читает')
        self.assertIsNone(turn['assessment']['grammar_score'])
        self.assertEqual(self.ai.assessments,['Она каждый день читаю книгу.'])
        original = self.client.get(turn['recording_url'])
        self.assertEqual(original.data,recording())
        self.assertEqual(original.headers['Cache-Control'],'no-store')
        self.assertNotIn('raw',turn['transcript'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_reward_entries').fetchone()[0],0)

    def test_duplicate_upload_does_not_create_another_turn_or_call_again(self):
        sid=self.start(); first=self.submit(sid).json; tid=first['turns'][0]['id']
        self.run_job(tid)
        duplicate=self.submit(sid)
        self.assertEqual(duplicate.status_code,202)
        self.assertEqual(len(duplicate.json['turns']),1)
        self.assertEqual(self.speech.calls,[('mai','verbatim')])
        self.assertEqual(self.submit(sid,data=recording(2)).status_code,409)

    def test_failed_reply_retries_without_retranscribing_or_losing_audio(self):
        sid=self.start(); tid=self.submit(sid).json['turns'][0]['id']
        original=self.ai.reply
        self.ai.reply=Mock(side_effect=SpeechError('Reply unavailable'))
        self.run_job(tid)
        first=self.read(sid)['turns'][0]
        self.assertEqual(first['state'],'failed');self.assertTrue(first['retryable'])
        self.assertEqual(self.submit(sid,key='new').status_code,409)
        self.ai.reply=original;self.run_job(tid)
        self.assertEqual(self.read(sid)['turns'][0]['state'],'ready')
        self.assertEqual(len(self.speech.calls),1)
        self.assertEqual(len(self.ai.assessments),1)

    def test_completed_steps_remain_saved_when_tts_fails(self):
        sid=self.start();tid=self.submit(sid).json['turns'][0]['id']
        original=self.speech.speak;self.speech.speak=Mock(side_effect=SpeechError('Voice unavailable'))
        self.run_job(tid)
        first=self.read(sid)['turns'][0]
        self.assertEqual(first['state'],'ready');self.assertEqual(first['audio_state'],'failed')
        self.speech.speak=original;self.run_job(tid)
        self.assertEqual(len(self.ai.replies),1);self.assertEqual(len(self.ai.assessments),1)
        self.assertEqual(self.read(sid)['turns'][0]['audio_state'],'ready')

    def test_same_character_voice_and_prior_history_are_kept(self):
        sid=self.start()
        self.post(f'/{sid}/greeting')
        tid=self.submit(sid).json['turns'][0]['id'];self.run_job(tid)
        tid=self.submit(sid,key='two').json['turns'][1]['id'];self.run_job(tid)
        self.assertEqual(len(set(self.speech.voices)),1)
        self.assertEqual(len(self.ai.replies[1]),4)

    def test_lab_uses_the_same_audio_without_passing_the_expected_text(self):
        sid=self.start('lab');tid=self.submit(sid,case='conjugation_singular').json['turns'][0]['id'];self.run_job(tid)
        turn=self.read(sid)['turns'][0]
        self.assertEqual(self.speech.calls,[('mai','verbatim'),('mai','clean'),('openai','verbatim')])
        self.assertEqual(len(turn['comparisons']),2);self.assertEqual(self.ai.replies,[])
        self.assertEqual(turn['assessment_state'],'skipped')

    def test_csrf_origin_and_recording_ownership(self):
        sid=self.start();tid=self.submit(sid).json['turns'][0]['id']
        self.assertEqual(self.client.post(f'/api/v1/conversations/{sid}/finish',json={}).status_code,403)
        self.assertEqual(self.client.post(f'/api/v1/conversations/{sid}/finish',json={},headers={'X-CSRF-Token':self.token,'Origin':'https://evil.invalid'}).status_code,403)
        # A turn from another session must never be playable through this session.
        second=self.post('',{'submission_id':'another'}).json['id']
        self.assertEqual(self.client.get(f'/api/v1/conversations/{second}/turns/{tid}/audio/original').status_code,404)
        with transaction(self.db,write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('someone-else','Other','cat','UTC',?)",(timestamp(),))
            conn.execute("UPDATE conversation_sessions SET profile_id='someone-else' WHERE id=?",(sid,))
        self.assertEqual(self.client.get(f'/api/v1/conversations/{sid}').status_code,404)
        self.assertEqual(self.client.get(f'/api/v1/conversations/{sid}/turns/{tid}/audio/original').status_code,404)

    def test_invalid_audio_and_long_audio_are_rejected_without_turns(self):
        sid=self.start()
        self.assertEqual(self.submit(sid,data=b'not audio').status_code,400)
        self.assertEqual(self.submit(sid,data=recording(91)).status_code,400)
        self.assertEqual(self.read(sid)['turns'],[])

    def test_finish_prevents_further_turns_and_delete_removes_private_files(self):
        sid=self.start();tid=self.submit(sid).json['turns'][0]['id']
        self.assertEqual(self.post(f'/{sid}/finish').status_code,409)
        self.run_job(tid);self.post(f'/{sid}/greeting')
        self.assertEqual(self.post(f'/{sid}/finish').json['state'],'completed')
        self.assertEqual(self.submit(sid,key='two').status_code,409)
        self.assertEqual(self.post(f'/{sid}/delete').json,{'deleted':True})
        self.assertEqual(list(self.service.root.iterdir()),[])
        self.assertEqual(self.client.get(f'/api/v1/conversations/{sid}').status_code,404)

    def test_polling_does_not_start_providers_and_expired_lease_is_retryable(self):
        sid=self.start();tid=self.submit(sid).json['turns'][0]['id']
        with transaction(self.db,write=True) as conn:
            conn.execute("UPDATE conversation_turns SET state='running',lease_until=? WHERE id=?",(timestamp()-1,tid))
        for _ in range(3): self.assertTrue(self.read(sid)['turns'][0]['retryable'])
        self.assertEqual(self.speech.calls,[])
        self.post(f'/{sid}/turns/{tid}/retry')
        self.dispatch.assert_called_with(tid)

    def test_backup_includes_the_original_and_reply_recordings(self):
        from services.learning_backup import backup_learning_store
        sid=self.start();tid=self.submit(sid).json['turns'][0]['id'];self.run_job(tid)
        destination=Path(self.db).parent/'snapshot'
        manifest=backup_learning_store(self.db,self.app.extensions['learning']['assets'],destination)
        self.assertEqual(len(manifest['conversation_audio']),2)
        self.assertEqual((destination/'conversation-audio'/f'{tid}.wav').read_bytes(),recording())


class SpeechAdapterTests(unittest.TestCase):
    def test_recording_preview_csp_allows_blob_audio_only(self):
        from blueprints.word_post import create_word_post_blueprint
        from flask import Flask
        app=Flask(__name__);app.config.update(WORD_POST_ENABLED=True,WORD_POST_DIST_DIR='/tmp/conversation-csp-test-missing')
        app.register_blueprint(create_word_post_blueprint())
        response=app.test_client().get('/post/assets/not-allowed.html')
        self.assertEqual(response.status_code,404)
        policy=response.headers['Content-Security-Policy']
        self.assertIn("media-src 'self' blob:",policy)
        self.assertIn("script-src 'self';",policy)
        self.assertIn("img-src 'self';",policy)

    def test_streaming_browser_webm_without_duration_is_decoded(self):
        import tempfile, subprocess
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input.wav';source.write_bytes(recording())
            output=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(source),'-c:a','libopus','-f','webm','pipe:1'],capture_output=True,check=True,timeout=15)
            webm=Path(tmp)/'browser.webm';webm.write_bytes(output.stdout)
            self.assertAlmostEqual(audio_info(webm),1,delta=0.1)

    def test_mai_uses_supported_verbatim_option_not_ignored_prompt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'audio.wav';path.write_bytes(recording())
            response=Mock(ok=True);response.json.return_value={'text':'Она читаю.','words':[{'word':'читаю','start':1,'end':2}]}
            with patch('services.speech_provider.requests.post',return_value=response) as post:
                result=SpeechProvider({'OPENROUTER_API_KEY':'test'}).transcribe(path)
            body=post.call_args.kwargs['json']
            self.assertEqual(body['model'],'microsoft/mai-transcribe-2')
            self.assertEqual(body['provider']['options']['azure']['enhancedMode']['modelOptions']['transcribeStyle'],'verbatim')
            self.assertNotIn('prompt',body);self.assertEqual(result['text'],'Она читаю.')
            self.assertEqual(result['words'][0]['word'],'читаю')

    def test_provider_failure_does_not_fallback_or_expose_response_body(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'audio.wav';path.write_bytes(recording())
            response=Mock(ok=False,status_code=401,text='SECRET PROVIDER DETAIL')
            with patch('services.speech_provider.requests.post',return_value=response) as post:
                with self.assertRaises(SpeechError) as error: SpeechProvider({'OPENROUTER_API_KEY':'test'}).transcribe(path)
            self.assertNotIn('SECRET',str(error.exception));self.assertEqual(post.call_count,1)

    def test_assessor_rejects_invented_source_quotes_and_never_sets_a_score(self):
        ai=ConversationAI({'CONVERSATION_MODEL':'test'})
        ai._call=Mock(return_value={'communication':'Understood.','uncertainty':'','corrections':[{'original':'читала','replacement':'читает','explanation':'x','category':'verb'}]})
        with self.assertRaises(SpeechError): ai.assess('Она читаю.','Что она делает?')
        ai._call.return_value['corrections'][0]['original']='читаю'
        result=ai.assess('Она читаю.','Что она делает?')
        self.assertIsNone(result['grammar_score']);self.assertIsNone(result['fluency_score'])
        self.assertEqual(result['basis'],'unverified_transcript')

    def test_non_russian_model_output_never_reaches_spoken_reply(self):
        from services.conversation_ai import SCENARIO
        from services.conversation_policy import RECOVERY_REPLY
        ai=ConversationAI({'CONVERSATION_MODEL':'test'})
        for speech in ('Sure, let us speak English.', 'Конечно! Would you like coffee?', '123 ₽'):
            ai._call=Mock(return_value={'russian':speech,'english':'An English translation.'})
            reply=ai.reply(SCENARIO,[{'role':'user','text':'Speak English.'}])
            self.assertEqual(reply['russian'],RECOVERY_REPLY['russian'])
            self.assertTrue(reply['language_recovered'])

    def test_language_check_preserves_learner_errors_and_separate_translation(self):
        from services.conversation_ai import SCENARIO
        ai=ConversationAI({'CONVERSATION_MODEL':'test'})
        ai._call=Mock(return_value={'russian':'Чай без сахара. Что-нибудь к чаю?', 'english':'Tea without sugar. Anything with your tea?'})
        history=[{'role':'user','text':'Я хотеть чай без сахар. My name is Alex.'}]
        reply=ai.reply(SCENARIO,history)
        self.assertEqual(ai._call.call_args.args[2]['history'],history)
        self.assertFalse(reply['language_recovered'])
        self.assertEqual(reply['english'],'Tea without sugar. Anything with your tea?')

    def test_english_help_cannot_acquire_invented_russian_grammar_errors(self):
        ai=ConversationAI({'CONVERSATION_MODEL':'test'})
        ai._call=Mock(return_value={'communication':'You are asking for help with a Russian phrase.',
            'uncertainty':'','corrections':[{'original':'булка','replacement':'булочку',
                'category':'case','explanation':'An invented Russian source.'}]})
        reply=ai.assess('How do I say a bun please in Russian?','At a café.')
        self.assertEqual(reply['corrections'],[])
        self.assertEqual(reply['rubric_version'],'russian-coaching-v4')
