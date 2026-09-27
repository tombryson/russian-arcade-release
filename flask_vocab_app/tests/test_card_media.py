"""Native media keeps text, card identities and review history independent."""
import io
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from PIL import Image
from pydub import AudioSegment
from repositories.learning_repository import LearningError, transaction
from services.card_media import NativeMediaProvider
from services.ai_trial_budget import TrialDenied
from services.elevenlabs_service import ElevenLabsService
from services.learning_assets import LocalAssetStore
from tests.support import isolated_app
from tests.test_personal_flashcards import Provider


class MediaProvider:
    def __init__(self):
        self.calls=[];self.fail=set()
        buffer=io.BytesIO();Image.new('RGB',(24,24),'#eecb70').save(buffer,format='PNG');self.image=buffer.getvalue()
        with AudioSegment.silent(duration=150,frame_rate=22050).export(format='mp3') as audio:
            self.mp3=audio.read()

    def spec(self,kind,item,form):
        return {'voice_id':'saved-random-voice','text':form if kind=='word_audio' else item['context'],'model':'test'}

    def generate(self,kind,spec):
        self.calls.append((kind,dict(spec)))
        if kind in self.fail:raise ValueError('temporary provider failure')
        return self.image if kind=='image' else self.mp3


class CardMediaTests(unittest.TestCase):
    def setUp(self):
        self.text=Provider();self.provider=MediaProvider()
        self.app=isolated_app(self,{'OpenAIService':self.text,'CardMediaProvider':self.provider})
        self.app.config['OPENAI_API_KEY']='test-only'
        self.client=self.app.test_client();self.services=self.app.extensions['learning'];self.db=self.app.config['DB_PATH']
        self.csrf=self.client.get('/api/v1/household').json['csrf_token']
        with self.client.session_transaction() as s:self.access=s['personal_access_id']
        self.media=self.services['card_media']

    def post(self,url,data):
        result=self.client.post(url,json=data,headers={'X-CSRF-Token':self.csrf})
        self.assertIn(result.status_code,(200,201),result.json)
        return result.json

    def generate(self,kind='ru-en',media=True):
        batch=self.post('/api/v1/card-generation/batches',{'submission_id':'batch','options':{'kind':kind,'quantity':1,'word_id':1,'audio':media,'image':media}})
        return self.post('/api/v1/card-generation/batches/'+batch['id']+'/next',{})

    def finish(self,batch):
        for _ in range(4):
            if batch['complete']:break
            batch=self.post('/api/v1/card-generation/batches/'+batch['id']+'/next',{})
        self.assertTrue(batch['complete']);return batch

    def library(self):return self.client.get('/api/v1/flashcards').json

    def start(self):
        return self.post('/api/v1/review-sessions',{'profile_id':self.library()['profile_id'],'scope':{},'size':5,'submission_id':'study'})

    def command(self,s,action,**extra):
        return self.post('/api/v1/review-sessions/'+s['id']+'/'+action,{'submission_id':action,'expected_revision':s['revision'],'item_id':s['item']['id'],**extra})

    def test_generation_completes_three_media_stages_once_and_reveals_example_translation(self):
        batch=self.generate();card=self.library()['cards'][0];card_id=card['id']
        self.assertEqual(batch['saved'],1);self.assertFalse(batch['complete'])
        self.assertEqual(len(batch['items'][0]['media_jobs']),3)
        batch=self.finish(batch)
        self.post('/api/v1/card-generation/batches/'+batch['id']+'/next',{})
        card=self.library()['cards'][0]
        self.assertEqual(card['id'],card_id);self.assertEqual(len(self.text.calls),1);self.assertEqual(len(self.provider.calls),3)
        self.assertEqual({a['kind'] for a in card['assets']},{'image','word_audio','sentence_audio'})
        self.assertEqual({a['media_type'] for a in card['assets']},{'image/png','audio/mpeg'})
        for asset in card['assets']:
            response=self.client.get('/api/v1/assets/'+asset['id'])
            self.assertEqual(response.status_code,200);self.assertEqual(response.mimetype,asset['media_type']);response.close()
        session=self.start();self.assertNotIn('context_meaning',session['item'])
        shown=self.command(session,'reveal');self.assertEqual(shown['item']['context_meaning'],'This is coffee.')

    def test_failed_media_keeps_text_and_successes_and_retries_original_spec_only(self):
        self.provider.fail={'word_audio'}
        batch=self.finish(self.generate());card=self.library()['cards'][0]
        self.assertEqual(batch['saved'],1);self.assertEqual(len(card['assets']),2)
        failed=[c for c in self.provider.calls if c[0]=='word_audio'][0]
        self.provider.fail.clear()
        retry=self.post('/api/v1/card-generation/batches/'+batch['id']+'/retry-media',{})
        self.assertFalse(retry['complete']);self.finish(retry)
        self.assertEqual(len(self.provider.calls),4);self.assertEqual(self.provider.calls[-1],failed);self.assertEqual(len(self.text.calls),1)
        self.assertEqual(self.library()['cards'][0]['id'],card['id'])

    def test_allowance_denial_pauses_media_with_the_actual_limit_message(self):
        self.generate()
        card = self.library()['cards'][0]
        message = 'Your daily AI allowance is used. Saved practice is still available.'
        with patch.object(self.provider, 'generate', side_effect=TrialDenied(message)):
            with self.assertRaisesRegex(TrialDenied, 'daily AI allowance'):
                self.media.advance(self.access, card['id'])
        jobs = self.media.status(self.access, card['id'])['jobs']
        failed = [job for job in jobs if job['status'] == 'failed']
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['error'], message)

    def test_worker_audio_preserves_trial_configuration_without_flask_context(self):
        speech = ElevenLabsService('synthetic-only', '/unused', voice_ids=('test-voice',),
            config={'HOSTED_AI_TRIAL':True, 'AI_TRIAL_ENABLED':False})
        provider = NativeMediaProvider(None, speech)
        spec = {'voice_id':'test-voice', 'model':'eleven_multilingual_v2', 'text':'кофе'}
        with patch('services.elevenlabs_service.requests.post') as post, ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaisesRegex(TrialDenied, 'paused'):
                pool.submit(provider.generate, 'word_audio', spec).result()
        post.assert_not_called()

    def test_allowance_denial_returns_429_and_keeps_saved_text_and_image(self):
        batch = self.generate()
        card = self.library()['cards'][0]
        self.post('/api/v1/card-generation/batches/'+batch['id']+'/next', {})
        saved_image = self.library()['cards'][0]['assets'][0]['id']
        message = 'Your daily AI allowance is used. Saved practice is still available.'
        with patch.object(self.provider, 'generate', side_effect=TrialDenied(message)):
            for url in ('/api/v1/flashcards/'+card['id']+'/media',
                        '/api/v1/card-generation/batches/'+batch['id']+'/next'):
                response = self.client.post(url, json={}, headers={'X-CSRF-Token':self.csrf})
                self.assertEqual(response.status_code, 429, response.json)
                self.assertEqual(response.json['error'], {'code':'trial_limit', 'message':message})
        saved = self.client.get('/api/v1/card-generation/batches/'+batch['id']).json
        self.assertEqual(saved['saved'], 1)
        self.assertEqual(self.library()['cards'][0]['assets'][0]['id'], saved_image)
        self.assertEqual(len(self.text.calls), 1)
        retry = self.post('/api/v1/card-generation/batches/'+batch['id']+'/retry-media', {})
        self.finish(retry)
        self.assertEqual(len(self.text.calls), 1)
        self.assertEqual(sum(kind=='image' for kind, _ in self.provider.calls), 1)

    def test_existing_ungraded_session_gains_media_and_metadata_without_reset(self):
        self.generate(media=False);session=self.start();card=self.library()['cards'][0]
        with transaction(self.db) as conn:
            before_state=[tuple(r) for r in conn.execute('SELECT * FROM learner_card_state')]
        with transaction(self.db,write=True) as conn:
            conn.execute('UPDATE words SET topic=?,lemma_difficulty=3,mnemonic=? WHERE id=1',(json.dumps(['food','daily_life']),'Remember the cafe.'))
            conn.execute('UPDATE forms SET tags=?,form_difficulty=2 WHERE word_id=1',(json.dumps({'case':'nomn','number':'sing'}),))
        old=self.provider.calls[:]
        status=self.post('/api/v1/flashcards/'+card['id']+'/media',{})
        while not status['complete']:status=self.post('/api/v1/flashcards/'+card['id']+'/media',{})
        current=self.client.get('/api/v1/review-sessions/'+session['id']).json
        self.assertEqual(current['item']['id'],session['item']['id']);self.assertEqual(current['item']['card_id'],card['id'])
        self.assertGreater(current['revision'],session['revision']);self.assertEqual(len(current['item']['assets']),3)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM review_events').fetchone()[0],0)
            self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM learner_card_state')],before_state)
        for query in ('topic=daily_life','pos=NOUN&case=nomn&difficulty=2','sort=difficulty'):
            self.assertEqual(self.client.get('/api/v1/flashcards?'+query).json['counts']['cards'],1)
        self.assertEqual(self.client.get('/api/v1/flashcards?pos=VERB').json['counts']['cards'],0)
        self.assertEqual(len(self.provider.calls)-len(old),3)
        metadata=current['item']['metadata'];self.assertEqual(metadata['topics'],['daily_life','food']);self.assertEqual(metadata['grammar']['number'],'sing')

    def test_enrichment_preserves_graded_events_and_scheduler_state_byte_for_byte(self):
        self.generate(media=False);session=self.command(self.start(),'reveal');self.command(session,'reviews',rating='good')
        with transaction(self.db) as conn:
            before={table:[tuple(r) for r in conn.execute('SELECT * FROM '+table)] for table in ('review_events','learner_card_state','activity_attempts')}
        card=self.library()['cards'][0]
        self.media.queue(self.access,card['id'])
        for _ in range(3):self.media.advance(self.access,card['id'])
        with transaction(self.db) as conn:
            after={table:[tuple(r) for r in conn.execute('SELECT * FROM '+table)] for table in before}
            event=conn.execute('SELECT card_version_id,occurrence_id FROM review_events').fetchone()
            self.assertEqual(conn.execute('SELECT card_version_id FROM review_session_items WHERE id=?',(event['occurrence_id'],)).fetchone()[0],event['card_version_id'])
        self.assertEqual(after,before);self.assertNotEqual(self.library()['cards'][0]['version_id'],card['version_id'])

    def test_cloze_image_supplies_context_and_audio_waits_for_reveal(self):
        self.finish(self.generate(kind='ru-cloze'));session=self.start()
        self.assertEqual([a['kind'] for a in session['item']['assets']],['image']);self.assertNotIn('кофе',str(session['item']))
        shown=self.command(session,'reveal');self.assertEqual(len(shown['item']['assets']),3)

    def test_persisted_result_recovers_after_publish_interruption_without_second_provider_call(self):
        batch=self.generate();card=self.library()['cards'][0]
        original=self.services['content'].publish
        with patch.object(self.services['content'],'publish',side_effect=RuntimeError('process interrupted')):
            result=self.media.advance(self.access,card['id'])
            self.assertEqual(result['failed'],1)
        with patch.object(self.services['content'],'publish',wraps=original):
            self.media.queue(self.access,card['id'])
        self.assertEqual(len(self.library()['cards'][0]['assets']),1)
        self.media.retry(self.access,card['id'])
        self.finish(batch);self.assertEqual(len(self.provider.calls),3)

    def test_concurrent_requests_do_not_start_another_stage_on_the_same_card(self):
        self.generate();card=self.library()['cards'][0];entered=threading.Event();release=threading.Event();original=self.provider.generate
        def blocked(kind,spec):entered.set();release.wait(5);return original(kind,spec)
        self.provider.generate=blocked
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.media.advance,self.access,card['id'])
            self.assertTrue(entered.wait(5))
            other=self.media.advance(self.access,card['id'])
            self.assertEqual(sum(j['status']=='running' for j in other['jobs']),1)
            release.set();first.result()
        self.assertEqual(len(self.provider.calls),1)

    def test_mp3_validation_rejects_truncated_and_overlong_audio(self):
        self.assertEqual(LocalAssetStore._media_type(self.provider.mp3),'audio/mpeg')
        with self.assertRaises(LearningError):LocalAssetStore._media_type(b'ID3truncated')
        with patch('services.learning_assets.AudioSegment.from_file',return_value=AudioSegment.silent(duration=181000)):
            with self.assertRaises(LearningError):LocalAssetStore._media_type(self.provider.mp3)

    def test_voice_is_selected_per_recording_and_saved_in_spec(self):
        class Speech:voice_ids=('one','two');model='eleven_multilingual_v2'
        provider=NativeMediaProvider(None,Speech())
        with patch('services.card_media.random.choice',side_effect=['two','one']) as choice:
            word=provider.spec('word_audio',{'context':'Это кофе.'},'кофе')
            sentence=provider.spec('sentence_audio',{'context':'Это кофе.'},'кофе')
        self.assertEqual((word['voice_id'],sentence['voice_id']),('two','one'));self.assertEqual(choice.call_count,2)
        self.assertEqual(word['text'],'кофе');self.assertEqual(sentence['text'],'Это кофе.')

    def test_restart_after_text_save_queues_missing_media_without_repeating_text(self):
        with patch.object(self.media,'queue',side_effect=RuntimeError('interrupted before queue')):
            batch=self.generate()
        self.assertEqual(batch['saved'],1);self.assertFalse(batch['complete'])
        batch=self.finish(batch)
        self.assertEqual(len(self.text.calls),1);self.assertEqual(len(self.provider.calls),3)
        # Edit links must point at the enriched version, not the text-only version.
        self.assertEqual(batch['items'][0]['card_version_id'],self.library()['cards'][0]['version_id'])

    def test_legacy_deck_stays_studyable_but_cannot_start_unsupported_media_jobs(self):
        pack={'schema_version':1,'id':'legacy','kind':'deck','title':'Legacy words','source':'Synthetic fixture',
              'items':[{'id':'one','word_id':1,'type':'basic','direction':'ru-en','prompt':'кофе','answer':'coffee'}]}
        version=self.services['content'].import_draft(pack,access_id=self.access)
        self.services['content'].publish(self.access,version,'Me')
        card=self.library()['cards'][0];self.assertFalse(card['media_supported'])
        self.assertEqual(self.start()['item']['prompt'],'кофе')
        with self.assertRaises(LearningError) as error:self.media.queue(self.access,card['id'])
        self.assertEqual(error.exception.code,'unsupported_card');self.assertEqual(self.provider.calls,[])

    def test_removed_card_does_not_block_remaining_batch_media(self):
        batch=self.post('/api/v1/card-generation/batches',{'submission_id':'removal-test','options':{'kind':'ru-en','quantity':2,'audio':True,'image':True}})
        url='/api/v1/card-generation/batches/'+batch['id']+'/next'
        first=self.post(url,{})['items'][0]
        self.post('/api/v1/cards/'+first['card_id']+'/delete',{})
        batch=self.post(url,{})
        batch=self.finish(batch)
        self.assertEqual(batch['items'][0]['status'],'removed')
        self.assertEqual(len(self.provider.calls),3)
        self.assertEqual(len(self.library()['cards']),1)

    def test_replacement_stops_old_media_and_old_versions_do_not_count_as_extra_cards(self):
        batch=self.generate();old=batch['items'][0]
        replacement=self.services['card_authoring'].save(self.access,{'draft_key':'replacement','edit':old['card_version_id'],'word_id':'1','direction':'ru-en',
            'sense_label':'Coffee','context':'Это кофе.','context_meaning':'This is coffee.','prompt':'кофе','answer':'coffee, the drink'})
        self.services['content'].publish(self.access,replacement,'Me')
        result=self.post('/api/v1/card-generation/batches/'+batch['id']+'/next',{})
        self.assertTrue(result['complete']);self.assertEqual(result['items'][0]['status'],'removed')
        with self.assertRaises(LearningError):self.media.advance(self.access,old['card_id'])
        self.assertEqual(self.provider.calls,[])
        selected=self.post('/api/v1/card-generation/preview',{'kind':'ru-en','quantity':1,'word_id':1,'max_cards':2})
        self.assertEqual(len(selected['words']),1)
