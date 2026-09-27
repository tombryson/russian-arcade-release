"""First steps feeds contextual cards, media and saved sentence practice."""
import json
import unittest
from repositories.learning_repository import transaction
from services.first_delivery import QUESTIONS
from services.first_steps import chapter_content
from tests.support import isolated_app
from tests.test_card_media import MediaProvider
from tests.test_personal_flashcards import Provider

class FirstStepsPracticeTests(unittest.TestCase):
    def setUp(self):
        self.text=Provider()
        self.app=isolated_app(self, {'OpenAIService':self.text,'CardMediaProvider':MediaProvider()})
        self.client=self.app.test_client()
        self.csrf=self.client.get('/api/v1/onboarding').json['csrf_token']
        with self.client.session_transaction() as saved:self.access=saved['personal_access_id']
        self.db=self.app.config['DB_PATH'];self.gen=self.app.extensions['learning']['generator']

    def post(self,path,data=None,status=200):
        result=self.client.post(path,json=data or {},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(result.status_code,status,result.text)
        return result.json

    def hello(self):
        for milestone in ('coins','progress'):self.post('/api/v1/onboarding',{'milestone':milestone})
        base='/api/v1/onboarding/practice/'
        self.post(base+'start')
        for q in QUESTIONS:self.post(base+'learn',{'question_id':q['id']})
        for q in QUESTIONS:
            self.post(base+'answer',{'question_id':q['id'],'answer':q['answer']})
            self.post(base+'continue',{'question_id':q['id']})
        self.post(base+'complete')

    def chapter(self):
        self.hello()
        for lesson in chapter_content()['lessons']:
            base='/api/v1/first-steps/'+lesson['id']+'/'
            self.post(base+'start')
            for t in lesson['teaching']:self.post(base+'learn',{'teaching_id':t['id']})
            for q in lesson['questions']:
                self.post(base+'answer',{'question_id':q['id'],'answer':q['answer']})
                self.post(base+'continue',{'question_id':q['id']})
            self.post(base+'complete')

    def finish_batch(self,batch):
        for _ in range(100):
            batch=self.gen.next(self.access,batch['id'])
            if batch['complete']:break
        self.assertTrue(batch['complete'],batch)
        self.assertEqual({i['status'] for i in batch['items']},{'saved'})
        self.assertEqual({j['kind'] for i in batch['items'] for j in i['media_jobs']},{'image','word_audio','sentence_audio'})
        self.assertEqual({j['status'] for i in batch['items'] for j in i['media_jobs']},{'saved'})
        return batch

    def test_contextual_native_clozes_use_authored_text_all_media_and_real_schedule(self):
        self.post('/api/v1/first-steps/hello/flashcards',status=409)
        self.hello()
        batch=self.post('/api/v1/first-steps/hello/flashcards',status=201)
        self.assertEqual(batch['total'],3)
        self.assertEqual(self.post('/api/v1/first-steps/hello/flashcards',status=201)['id'],batch['id'])
        self.gen.next(self.access,batch['id'])
        pending=self.client.get('/api/v1/flashcards?topic=First%20steps').json
        self.assertEqual(pending['counts']['ready'],0)
        self.assertFalse(pending['cards'][0]['media_ready'])
        self.finish_batch(batch)
        self.assertEqual(self.text.calls,[])
        library=self.client.get('/api/v1/flashcards?topic=First%20steps').json
        self.assertEqual(library['counts']['cards'],3);self.assertEqual(library['counts']['ready'],3)
        self.assertTrue(all(c['direction']=='ru-cloze' and c['media_ready'] for c in library['cards']))
        self.app.extensions['learning']['review'].start(self.access,{'profile_id':library['profile_id'],'scope':{},'size':3,'submission_id':'unfiltered-test'})
        scoped=self.client.get('/api/v1/flashcards?topic=First%20steps').json
        self.assertIsNone(scoped['active_session_id'])
        review=self.app.extensions['learning']['review'].start(self.access,{'profile_id':library['profile_id'],'scope':{'topic':'First steps'},'size':3,'submission_id':'chapter-native-test'})
        self.assertIn('[[blank]]',review['item']['prompt'])
        self.assertNotIn('answer',review['item']);self.assertNotIn('dictionary_url',review['item']);self.assertTrue(review['item']['cue_en'])
        with transaction(self.db) as c:
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
            w=c.execute("SELECT id FROM words WHERE lemma='письмо'").fetchone()
            self.assertEqual(c.execute('SELECT COUNT(*) FROM card_definitions WHERE word_id=?',(w['id'],)).fetchone()[0],1)

    def test_chapter_deduplicates_earlier_contexts_and_jumble_reuses_familiar_words(self):
        self.chapter()
        hello=self.post('/api/v1/first-steps/hello/flashcards',status=201);self.finish_batch(hello)
        batch=self.post('/api/v1/first-steps/chapter/flashcards',status=201)
        self.assertGreaterEqual(batch['first_steps']['reused'],3)
        self.assertEqual(self.post('/api/v1/first-steps/chapter/flashcards',status=201)['id'],batch['id'])
        with transaction(self.db) as c:
            selections=[json.loads(r[0]) for r in c.execute('SELECT selection FROM native_card_generation_items')]
            identities=[s['first_steps_source']['identity'] for s in selections]
            self.assertEqual(len(identities),len(set(identities)))
            polite=next(s for s in selections if s['lemma']=='показать')
            self.assertEqual(polite['form'],'Покажите');self.assertEqual(polite['tags']['mood'],'impr');self.assertEqual(polite['tags']['number'],'plur')
        result=self.post('/api/v1/first-steps/practice/word-jumble',status=201)
        self.assertEqual(result,self.post('/api/v1/first-steps/practice/word-jumble',status=201))
        self.assertEqual(self.client.get(result['url']).status_code,200)
        with transaction(self.db) as c:
            game=c.execute('SELECT * FROM word_jumble_games WHERE id=?',(result['url'].rsplit('/',1)[1],)).fetchone()
            self.assertEqual(json.loads(game['words']),['это','письмо','сумка']);self.assertEqual(game['owner_profile_id'],'personal-learning')

    def test_no_client_words_or_owners_and_no_practice_before_completion(self):
        self.post('/api/v1/first-steps/chapter/flashcards',status=409)
        self.post('/api/v1/first-steps/practice/word-jumble',status=409)
        self.post('/api/v1/first-steps/hello/flashcards',{'profile_id':'another'},status=400)
        self.post('/api/v1/first-steps/practice/word-jumble',{'words':['anything']},status=400)
        with transaction(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM native_card_batches').fetchone()[0],0)
