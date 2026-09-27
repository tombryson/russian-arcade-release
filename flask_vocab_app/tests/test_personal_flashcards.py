import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from repositories.learning_repository import transaction
from services.card_generation import CardGenerationService
from services.openai_service import OpenAIService
from tests.support import isolated_app, select_test_profile


class Provider:
    def __init__(self):
        self.calls = []

    def generate_native_card(self, word, kind):
        self.calls.append((word,kind))
        return {'english':'coffee' if word['lemma']=='кофе' else 'a word',
                'sentence':f'Это {word["form"]}.','sentence_english':'This is coffee.', 'notes':''}


class PersonalFlashcardTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.app = isolated_app(self,{'OpenAIService':self.provider})
        self.app.config['OPENAI_API_KEY']='synthetic-test-key'
        self.client = self.app.test_client()
        self.db = self.app.config['DB_PATH']
        self.services = self.app.extensions['learning']
        self.generator = self.services['generator']

    def post(self,url,data):
        token = self.client.get('/api/v1/household').json['csrf_token']
        return self.client.post(url,json=data,headers={'X-CSRF-Token':token})

    def batch(self,**options):
        response = self.post('/api/v1/card-generation/batches',{
            'submission_id':'one-batch','options':{'kind':'ru-cloze','quantity':1,'word_id':1,**options}})
        self.assertEqual(response.status_code,201,response.get_data(as_text=True))
        return response.json

    def generate(self,**options):
        batch = self.batch(**options)
        response = self.post(f'/api/v1/card-generation/batches/{batch["id"]}/next',{})
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        return response.json

    def credential(self):
        with self.client.session_transaction() as session:
            return session['personal_access_id']

    def test_native_selection_covers_inflections_and_keeps_explicit_case(self):
        with transaction(self.db,write=True) as conn:
            word_id = conn.execute("INSERT INTO words(lemma,pos,count,lemma_difficulty) VALUES ('книга','NOUN',0,1)").lastrowid
            for form, case in [('книга','nomn'), ('книгу','accs'), ('книгой','ablt')]:
                conn.execute('INSERT INTO forms(word_id,form,count,tags,form_difficulty) VALUES (?,?,0,?,1)',
                             (word_id,form,'{"case":"'+case+'","number":"sing"}'))
        options = {'kind':'ru-cloze','quantity':1,'word_id':word_id,'max_cards':5}
        first = self.generator.preview(self.credential(),options)[0]
        self.assertNotEqual(first['form'],'книга')
        self.generator.create(self.credential(),{'submission_id':'form-coverage-one','options':options})
        second = self.generator.preview(self.credential(),options)[0]
        self.assertNotEqual(second['form_id'], first['form_id'])
        filtered = self.generator.preview(self.credential(),dict(options,case='instr'))[0]
        self.assertEqual(filtered['form'],'книгой')
        self.assertEqual(filtered['tags']['case'],'ablt')

    def test_native_difficulty_filters_the_form_and_reduces_rare_participles(self):
        with transaction(self.db,write=True) as conn:
            word_id = conn.execute("INSERT INTO words(lemma,pos,count,lemma_difficulty) VALUES ('читать','VERB',0,1)").lastrowid
            conn.execute("INSERT INTO forms(word_id,form,count,tags,form_difficulty) VALUES (?,'читаю',0,'{\"person\":\"1per\",\"tense\":\"pres\"}',3)", (word_id,))
            conn.execute("INSERT INTO forms(word_id,form,count,tags,form_difficulty) VALUES (?,'читавшимися',0,'{\"pos\":\"participle\"}',3)", (word_id,))
        selected = self.generator.preview(self.credential(),{'kind':'ru-cloze','quantity':1,'word_id':word_id,'difficulty':3})
        self.assertEqual(selected[0]['form'],'читаю')
        self.assertEqual(selected[0]['metadata']['form_difficulty'],3)

    def test_personal_mode_opens_without_pin_or_household_and_keeps_one_profile(self):
        state = self.client.get('/api/v1/household').json
        self.assertEqual(state['mode'],'personal')
        self.assertEqual(state['profile']['display_name'],'Me')
        self.assertEqual(self.client.get('/api/v1/flashcards').status_code,200)
        other = self.app.test_client().get('/api/v1/household').json
        self.assertEqual(other['profile']['id'],state['profile']['id'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM household_settings').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM learning_profiles').fetchone()[0],1)
        redirect = self.client.get('/post/flashcards/manage?word_id=1')
        self.assertEqual(redirect.headers['Location'],'/#generate?word_id=1')

    def test_personal_generation_and_edit_writes_still_require_same_origin_token(self):
        response = self.client.post('/api/v1/card-generation/batches',json={})
        self.assertEqual(response.status_code,403)
        token = self.client.get('/api/v1/household').json['csrf_token']
        response = self.client.post('/api/v1/card-generation/batches',json={},headers={'X-CSRF-Token':token,'Origin':'https://elsewhere.invalid'})
        self.assertEqual(response.status_code,403)

    def test_hosted_batch_limit_is_advertised_and_enforced_before_saving_work(self):
        self.app.config.update(HOSTED_AI_TRIAL=True, AI_TRIAL_IDENTITY='github:synthetic')
        self.assertEqual(self.client.get('/api/v1/card-generation/options').json['max_quantity'], 5)
        options = {'kind':'ru-cloze','quantity':6}
        for url, body in (
            ('/api/v1/card-generation/preview', options),
            ('/api/v1/card-generation/batches', {'submission_id':'over-limit','options':options}),
        ):
            response = self.post(url, body)
            self.assertEqual(response.status_code, 400, response.json)
            self.assertIn('1 and 5 cards', response.json['error']['message'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0], 0)
        self.assertEqual(self.provider.calls, [])
        self.batch(quantity=5, word_id=None)

    def test_local_generator_keeps_twenty_card_batches(self):
        self.assertEqual(self.client.get('/api/v1/card-generation/options').json['max_quantity'], 20)
        self.batch(quantity=20, word_id=None)

    def test_generate_saves_ready_cards_and_can_study_immediately_without_approval(self):
        result = self.generate()
        self.assertEqual((result['saved'],result['total'],result['complete']),(1,1,True))
        overview = self.client.get('/api/v1/flashcards').json
        self.assertEqual(overview['counts']['new'],1)
        self.assertEqual(overview['cards'][0]['answer'],'кофе')
        session = self.post('/api/v1/review-sessions',{'profile_id':overview['profile_id'],'scope':{},'size':5,'submission_id':'start'}).json
        self.assertNotIn('answer',session['item'])
        self.assertEqual(session['item']['prompt'],'Это [[blank]].')
        self.assertNotIn('кофе',str(session['item']))
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT count FROM words WHERE id=1').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM anki_cards').fetchone()[0],0)

    def test_duplicate_generation_request_and_finished_batch_do_not_call_provider_again(self):
        result = self.generate()
        same = self.batch()
        self.assertEqual(same['id'],result['id'])
        self.post(f'/api/v1/card-generation/batches/{result["id"]}/next',{})
        self.assertEqual(len(self.provider.calls),1)
        conflict = self.post('/api/v1/card-generation/batches',{'submission_id':'one-batch','options':{'kind':'ru-en','quantity':2}})
        self.assertEqual(conflict.status_code,409)

    def test_selector_reads_json_case_values_and_filters_without_duplicate_words(self):
        with transaction(self.db,write=True) as conn:
            conn.execute('INSERT INTO forms(word_id,form,tags,form_difficulty) VALUES (1,?,?,1)',('кофе','{"case": "ablt", "number": "sing"}'))
            conn.execute('INSERT INTO forms(word_id,form,tags,form_difficulty) VALUES (1,?,?,1)',('кофе','{"case":"ablt"}'))
        response = self.post('/api/v1/card-generation/preview',{'kind':'ru-cloze','quantity':10,'case':'instr','pos':'NOUN'})
        self.assertEqual([w['word_id'] for w in response.json['words']],[1])
        self.assertEqual(self.provider.calls,[])

    def test_one_failure_does_not_lose_other_generated_cards(self):
        original = self.provider.generate_native_card
        def generate(word,kind):
            if word['word_id']==1: raise ValueError('Provider failed')
            return original(word,kind)
        self.provider.generate_native_card=generate
        batch = self.batch(word_id=None,quantity=2)
        for _ in range(2): result=self.post(f'/api/v1/card-generation/batches/{batch["id"]}/next',{}).json
        self.assertEqual(result['saved'],1);self.assertTrue(result['complete'])
        self.assertEqual(result['items'][0]['status'],'failed')
        self.assertEqual(self.client.get('/api/v1/flashcards').json['counts']['cards'],1)

    def test_invalid_generated_form_is_rejected_without_substituting_another_word(self):
        self.provider.generate_native_card=lambda *_:{'english':'tea','sentence':'Это чай.','sentence_english':'This is tea.','notes':''}
        result = self.generate()
        self.assertEqual(result['saved'],0)
        self.assertIn('selected word',result['items'][0]['error'])

    def test_edit_and_delete_belong_to_the_individual(self):
        result = self.generate(kind='ru-en')
        version = result['items'][0]['card_version_id']
        page = self.client.get('/post/flashcards/manage?edit='+version)
        self.assertEqual(page.status_code,200)
        self.assertNotIn('For grown-ups',page.get_data(as_text=True))
        token = self.client.get('/api/v1/household').json['csrf_token']
        response = self.client.post('/post/flashcards/drafts',data={
            'csrf_token':token,'draft_key':'corrected','edit':version,'word_id':'1','direction':'ru-en',
            'sense_label':'кофе','context':'Это кофе.','prompt':'кофе','answer':'coffee, the drink'})
        self.assertEqual(response.status_code,302,response.get_data(as_text=True))
        cards = self.client.get('/api/v1/flashcards').json['cards']
        self.assertEqual(len(cards),1);self.assertEqual(cards[0]['answer'],'coffee, the drink')
        self.assertEqual(self.post(f'/api/v1/cards/{cards[0]["id"]}/delete',{}).status_code,200)
        self.assertEqual(self.client.get('/api/v1/flashcards').json['counts']['cards'],0)

    def test_household_mode_remains_opt_in_and_personal_session_cannot_unlock_it(self):
        self.client.get('/api/v1/household')
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True,SECRET_KEY='long-test-key-for-optional-household-mode')
        self.services['household'].configure('Optional household','246810')
        self.assertEqual(self.client.get('/post/flashcards/manage').status_code,302)
        self.assertEqual(self.client.get('/api/v1/flashcards').status_code,401)
        self.app.config['WORD_POST_HOUSEHOLD_ENABLED']=False
        # Household configuration revoked every credential. Personal mode must
        # not silently recreate access after that revocation.
        self.assertEqual(self.client.get('/api/v1/flashcards').status_code,401)
        select_test_profile(self.client)
        self.assertEqual(self.client.get('/api/v1/flashcards').status_code,200)

    def test_optional_household_generation_saves_drafts_until_explicit_approval(self):
        self.app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='long-test-key-for-optional-household-mode')
        self.generator.household = True
        self.services['household'].configure('Optional household', '246810')
        self.assertEqual(self.post('/api/v1/household/unlock', {'pin': '246810'}).status_code, 200)
        result = self.generate()
        self.assertTrue(result['household'])
        with self.client.session_transaction() as saved:
            credential = saved['household_access_id']
        version = result['items'][0]['version_id']
        self.assertEqual(self.services['content'].inspect(credential, version)['status'], 'draft')
        self.assertEqual(self.client.get('/post/flashcards/manage?review=1').status_code, 200)

    def test_topic_options_ignore_invalid_json_and_non_array_metadata(self):
        with transaction(self.db, write=True) as conn:
            conn.execute("UPDATE words SET topic='invalid' WHERE id=1")
            conn.execute('UPDATE words SET topic=? WHERE id=2', ('"scalar"',))
        options = self.client.get('/api/v1/card-generation/options')
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.json['topics'], ['school'])

    def test_concurrent_generation_claim_calls_provider_once(self):
        batch=self.batch(); credential=self.credential()
        started=threading.Event(); release=threading.Event()
        original=self.provider.generate_native_card
        def slow(word,kind):
            started.set();release.wait(3);return original(word,kind)
        self.provider.generate_native_card=slow
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.generator.next,credential,batch['id'])
            self.assertTrue(started.wait(2))
            second=pool.submit(self.generator.next,credential,batch['id']).result()
            self.assertEqual(second['items'][0]['status'],'running')
            release.set();self.assertEqual(first.result()['saved'],1)
        self.assertEqual(len(self.provider.calls),1)

    def test_stored_provider_result_resumes_without_regeneration(self):
        batch=self.batch(); item=batch['items'][0]
        with transaction(self.db,write=True) as conn:
            conn.execute("UPDATE native_card_generation_items SET status='generated',response=? WHERE id=?",('{"english":"coffee","sentence":"Это кофе.","sentence_english":"This is coffee.","notes":""}',item['id']))
        restored=CardGenerationService(self.db,self.services['content'],self.provider)
        self.assertEqual(restored.next(self.credential(),batch['id'])['saved'],1)
        self.assertEqual(self.provider.calls,[])

    def test_openai_generation_requires_structured_complete_output(self):
        service=OpenAIService("synthetic-test-key");service.client=Mock()
        result=Mock();result.finish_reason='stop';result.message.refusal=None
        result.message.content='{"english":"coffee","sentence":"Это кофе.","sentence_english":"This is coffee.","notes":""}'
        service.client.with_options.return_value.chat.completions.create.return_value.choices=[result]
        self.assertEqual(service.generate_native_card({'form':'кофе'},'ru-en')['english'],'coffee')
        settings=service.client.with_options.return_value.chat.completions.create.call_args.kwargs
        self.assertTrue(settings['response_format']['json_schema']['strict'])
        self.assertEqual(settings['model'], service.flashcard_model)
        self.assertEqual(settings['reasoning_effort'], 'low')
        result.finish_reason='length'
        with self.assertRaises(ValueError):service.generate_native_card({'form':'кофе'},'ru-en')

    def test_legacy_generated_cloze_recovers_saved_cue_without_regeneration_or_writes(self):
        from unittest.mock import patch
        original=CardGenerationService.pack
        def legacy(*args):
            pack=original(*args);pack['items'][0].pop('cue_en');return pack
        with patch.object(CardGenerationService,'pack',staticmethod(legacy)):
            self.generate()
        with transaction(self.db) as conn:
            before=[tuple(r) for r in conn.execute('SELECT * FROM learning_content_versions')]
        overview=self.client.get('/api/v1/flashcards').json
        self.assertEqual(overview['cards'][0]['cue_en'],'coffee')
        page=self.client.get('/post/flashcards/manage?edit='+overview['cards'][0]['version_id']).get_data(as_text=True)
        self.assertIn('name="cue_en" value="coffee"',page)
        session=self.post('/api/v1/review-sessions',{'profile_id':overview['profile_id'],'scope':{},'size':5,'submission_id':'legacy-cloze'}).json
        self.assertEqual(session['item']['cue_en'],'coffee')
        self.assertNotIn('dictionary_url',session['item'])
        self.assertNotIn('context_meaning',session['item'])
        self.assertEqual(len(self.provider.calls),1)
        with transaction(self.db) as conn:
            self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM learning_content_versions')],before)

    def test_generated_cloze_keeps_contextual_cue_and_editor_preserves_it(self):
        self.generate()
        card=self.client.get('/api/v1/flashcards').json['cards'][0]
        self.assertEqual(card['cue_en'],'coffee')
        page=self.client.get('/post/flashcards/manage?edit='+card['version_id']).get_data(as_text=True)
        self.assertIn('name="cue_en" value="coffee"',page)
        data={'draft_key':'cue-edit','edit':card['version_id'],'word_id':'1','form_id':'1',
            'direction':'ru-cloze','sense_label':'кофе','context':card['context'],
            'context_meaning':card['context_meaning'],'prompt':card['prompt'],'answer':card['answer'],
            'cue_en':'coffee, the drink'}
        version=self.services['card_authoring'].save(self.credential(),data)
        self.services['content'].publish(self.credential(),version,'Me')
        changed=self.client.get('/api/v1/flashcards').json['cards'][0]
        self.assertEqual(changed['cue_en'],'coffee, the drink')
        self.assertEqual(changed['id'],card['id'])

    def test_database_mnemonic_is_distinct_from_the_english_answer(self):
        mnemonic='Think of the smell outside a café.'
        with transaction(self.db,write=True) as conn:
            conn.execute('UPDATE words SET mnemonic=? WHERE id=1',(mnemonic,))
        self.generate()
        overview=self.client.get('/api/v1/flashcards').json
        s=self.post('/api/v1/review-sessions',{'profile_id':overview['profile_id'],'scope':{},'size':5,'submission_id':'mnemonic-test'}).json
        self.assertTrue(s['item']['has_hint'])
        self.assertEqual(s['item']['cue_en'],'coffee')
        for field in ('dictionary_url','hint','answer','context_meaning'):
            self.assertNotIn(field,s['item'])
        body={'submission_id':'reveal-without-help','expected_revision':s['revision'],'item_id':s['item']['id']}
        shown=self.post('/api/v1/review-sessions/'+s['id']+'/reveal',body).json
        self.assertEqual(shown['item']['hint'],mnemonic)
        self.assertEqual(shown['item']['cue_en'],'coffee')
        self.assertFalse(shown['item']['assisted'])
