"""Lessons share native cards, lexical forms, media and review history."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from repositories.learning_repository import LearningError, transaction
from services.card_metadata import GRAMMAR
from services.lesson_ai import LessonClozes
from services.ai_trial_budget import TrialDenied
from tests.support import isolated_app
from tests.test_lessons import FakeAI, picture
from tests.test_card_media import MediaProvider
from tests.test_personal_flashcards import Provider


def candidate(**changes):
    item = {'page':1, 'lemma':'город', 'surface':'городах', 'pos':'NOUN',
            'grammar':{k:'' for k in GRAMMAR}, 'sentence':'Анна живёт в новых городах.',
            'english':'cities', 'sentence_english':'Anna lives in new cities.',
            'notes':'Use the prepositional plural after в to say where someone lives.'}
    item['grammar'].update(case='loct', number='plur', gender='masc', animacy='inan')
    item.update(changes)
    return item


class CardsAI(FakeAI):
    def __init__(self):
        super().__init__(); self.cards=[candidate()]; self.card_calls=0

    def flashcards(self, pages, quantity):
        self.card_calls += 1
        return LessonClozes.model_validate({'cards':deepcopy(self.cards)}).model_dump()


class LessonCardTests(unittest.TestCase):
    def setUp(self):
        self.ai=CardsAI(); self.media=MediaProvider(); self.text=Provider()
        self.app=isolated_app(self, {'LessonAI':self.ai,'CardMediaProvider':self.media,'OpenAIService':self.text})
        self.app.config['LESSON_BACKGROUND_ENABLED']=False
        self.client=self.app.test_client()
        self.csrf=self.client.get('/api/v1/household').json['csrf_token']
        with self.client.session_transaction() as s:self.access=s['personal_access_id']
        self.services=self.app.extensions['learning']; self.comp=self.services['lessons']; self.cards=self.services['lesson_cards']; self.gen=self.services['generator']
        self.db=self.app.config['DB_PATH']
        material=self.comp.files.receive(picture(), 'notes.png')
        self.lid,self.rid,_=self.comp.create('Places', '', [material])
        self.comp.process(self.rid)

    def prepare(self, quantity=5, rid=None):
        request_id=self.cards.create(self.access,self.lid,rid or self.rid,1,1,quantity)
        result=self.cards.advance(self.access,request_id,self.lid)
        self.assertEqual(result['state'],'ready',result)
        return result

    def finish(self, batch_id):
        for _ in range(15):
            batch=self.gen.next(self.access,batch_id)
            if batch['complete']:break
        self.assertTrue(batch['complete'],batch)
        self.assertEqual({j['status'] for i in batch['items'] for j in i.get('media_jobs',[])},{'saved'})
        return batch

    def library(self):
        result=self.client.get('/api/v1/flashcards?lesson_id='+self.lid)
        self.assertEqual(result.status_code,200,result.json)
        return result.json

    def test_source_form_media_counts_and_cloze_front(self):
        result=self.prepare(); bid=result['batch_id']
        batch=self.gen.next(self.access,bid)
        self.assertEqual(batch['saved'],1,batch)
        self.assertEqual(self.library()['counts']['ready'],0)
        self.assertFalse(self.library()['cards'][0]['media_ready'])
        self.finish(bid)
        library=self.library(); card=library['cards'][0]
        self.assertEqual((library['counts']['cards'],library['counts']['ready']),(1,1))
        self.assertEqual(card['answer'],'городах')
        self.assertEqual(card['metadata']['grammar']['case'],'loct')
        self.assertEqual(card['sources'][0]['page'],1)
        self.assertEqual(len(self.text.calls),0)  # No unrelated sentence regeneration.
        with transaction(self.db) as conn:
            word=conn.execute("SELECT * FROM words WHERE lemma='город'").fetchone()
            form=conn.execute('SELECT * FROM forms WHERE word_id=? AND form=?',(word['id'],'городах')).fetchone()
            self.assertEqual(form['form'],'городах')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_definitions WHERE word_id=?',(word['id'],)).fetchone()[0],1)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        review=self.services['review'].start(self.access, {'profile_id':library['profile_id'],'scope':{'lesson_id':self.lid},'size':5,'submission_id':'lesson-study'})
        self.assertEqual(review['item']['prompt'],'Анна живёт в новых [[blank]].')
        for key in ('answer','dictionary_url','context','sources'):
            self.assertNotIn(key,review['item'])
        self.assertEqual(review['item']['cue_en'],'cities')
        self.assertEqual({a['kind'] for a in review['item']['assets']},{'image'})
        self.assertEqual(review['lesson']['lesson_id'],self.lid)

    def test_lesson_media_allowance_denial_returns_429_without_losing_source_work(self):
        prepared = self.prepare()
        bid = prepared['batch_id']
        self.gen.next(self.access, bid)
        self.gen.next(self.access, bid)
        card = self.library()['cards'][0]
        message = 'Your daily AI allowance is used. Saved practice is still available.'
        with patch.object(self.media, 'generate', side_effect=TrialDenied(message)):
            response = self.client.post('/api/v1/card-generation/batches/'+bid+'/next', json={},
                                        headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(response.status_code, 429, response.json)
        self.assertEqual(response.json['error']['message'], message)
        self.assertEqual(self.cards.read(self.access, prepared['id'], self.lid)['state'], 'ready')
        saved = self.library()['cards'][0]
        self.assertEqual(saved['id'], card['id'])
        self.assertEqual(saved['assets'], card['assets'])
        self.assertEqual(saved['sources'], card['sources'])
        self.assertEqual(self.ai.card_calls, 1)
        self.assertEqual(self.text.calls, [])

    def test_repeated_selection_and_revision_reuse_card_and_schedule(self):
        first=self.prepare(); self.finish(first['batch_id'])
        again=self.prepare(); self.assertEqual(first['id'],again['id']);self.assertEqual(self.ai.card_calls,1)
        library=self.library()
        review=self.services['review'].start(self.access, {'profile_id':library['profile_id'],'scope':{'lesson_id':self.lid},'size':5,'submission_id':'first'})
        with transaction(self.db) as conn:
            schedules=[tuple(r) for r in conn.execute('SELECT * FROM learner_card_state')]
        material=self.comp.files.receive(picture('red'),'new-notes.png')
        rid=self.comp.revise(self.lid,[material]);self.comp.process(rid)
        second=self.prepare(rid=rid)
        reused=self.gen.read(self.access,second['batch_id'])
        self.assertEqual(reused['total'],0)
        self.assertEqual(reused['source']['report'][0]['reused'],1)
        self.assertEqual(self.library()['cards'][0]['id'],library['cards'][0]['id'])
        self.assertEqual(self.library()['active_session_id'],review['id'])
        with transaction(self.db) as conn:
            self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM learner_card_state')],schedules)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM lesson_card_sources').fetchone()[0],2)

    def test_bad_quote_or_morphology_does_not_add_vocabulary(self):
        self.ai.cards=[candidate(sentence='Анна живёт на Луне.'),candidate(lemma='город',grammar={**candidate()['grammar'],'case':'gent'})]
        request_id=self.cards.create(self.access,self.lid,self.rid,1,1,5)
        result=self.cards.advance(self.access,request_id,self.lid)
        self.assertEqual(result['state'],'failed')
        with transaction(self.db) as conn:
            self.assertIsNone(conn.execute("SELECT id FROM words WHERE lemma='город'").fetchone())
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0],0)

    def test_partial_batch_reports_rejected_candidates(self):
        self.ai.cards=[candidate(),candidate(lemma='несуществующее',surface='несуществующее')]
        batch=self.gen.read(self.access,self.prepare()['batch_id'])
        self.assertEqual(batch['total'],1)
        self.assertEqual(len(batch['source']['report']),2)

    def test_finite_verb_voice_is_not_a_false_morphology_rejection(self):
        verb=candidate(lemma='думать',surface='думает',pos='VERB',sentence='Анна думает о своей семье.',
                       grammar={**{k:'' for k in GRAMMAR},'number':'sing','person':'3per','tense':'pres','mood':'indc','aspect':'impf','voice':'actv'})
        with transaction(self.db,write=True) as conn:
            word=self.cards.resolve(conn,verb)
            self.assertEqual(word['tags']['person'],'3per')
            self.assertNotIn('voice',word['tags'])

    def test_recheck_and_duplicate_candidates_do_not_duplicate_saved_cards(self):
        self.ai.cards=[candidate(),candidate()]
        first=self.prepare(); self.finish(first['batch_id'])
        self.cards.recheck(self.access,first['batch_id'])
        batch=self.gen.read(self.access,first['batch_id'])
        self.assertEqual(batch['total'],1)
        self.assertEqual(batch['source']['report'][0]['added'],1)
        self.assertEqual(self.ai.card_calls,1)
        self.assertEqual(len(self.media.calls),3)

    def test_ambiguous_ending_does_not_pick_the_first_parse(self):
        ambiguous=candidate(surface='дома',grammar={k:'' for k in GRAMMAR})
        with transaction(self.db,write=True) as conn:
            with self.assertRaises(ValueError):self.cards.resolve(conn,ambiguous)

    def test_source_recheck_can_append_a_recovered_card(self):
        good=candidate(); self.ai.cards=[good,candidate(lemma='новый',surface='новых',pos='ADJF',grammar={**{k:'' for k in GRAMMAR},'case':'loct','number':'plur'},english='new')]
        original=self.cards.resolve
        def temporary(conn, word):
            if word['lemma']=='новый':raise ValueError('Temporary dictionary mismatch')
            return original(conn,word)
        with patch.object(self.cards,'resolve',side_effect=temporary):first=self.prepare()
        first_card=self.finish(first['batch_id'])['items'][0]['card_id']
        self.cards.recheck(self.access,first['batch_id'])
        batch=self.finish(first['batch_id'])
        self.assertEqual(batch['total'],2)
        self.assertEqual(batch['items'][0]['card_id'],first_card)
        self.assertEqual(self.ai.card_calls,1)

    def test_saved_response_resumes_without_another_model_call(self):
        with patch.object(self.cards,'_materialize',side_effect=RuntimeError('interrupted')):
            rid=self.cards.create(self.access,self.lid,self.rid,1,1,5)
            self.assertEqual(self.cards.advance(self.access,rid,self.lid)['state'],'failed')
        self.assertEqual(self.cards.advance(self.access,rid,self.lid)['state'],'ready')
        self.assertEqual(self.ai.card_calls,1)

    def test_route_csrf_validation_and_page_selection(self):
        data={'revision_id':self.rid,'first_page':1,'last_page':1,'quantity':5}
        url=f'/lessons/{self.lid}/flashcards'
        self.assertEqual(self.client.post(url,data=data).status_code,403)
        response=self.client.post(url,data={**data,'csrf_token':self.csrf})
        self.assertEqual(response.status_code,303)
        html=self.client.get(response.location).get_data(as_text=True)
        self.assertIn('data-auto-prepare',html)
        self.assertIn('Your lesson cards',html)
        with self.assertRaises(LearningError):self.cards.create(self.access,self.lid,self.rid,1,12,5)
        with self.assertRaises(LearningError):self.cards.create(self.access,self.lid,self.rid,1,2,5)

    def test_failed_media_not_available_until_retry(self):
        result=self.prepare(); self.media.fail={'word_audio'}
        for _ in range(5):self.gen.next(self.access,result['batch_id'])
        self.assertEqual(self.library()['counts']['ready'],0)
        card=self.library()['cards'][0]
        self.media.fail.clear();self.services['card_media'].retry(self.access,card['id'])
        self.finish(result['batch_id'])
        self.assertEqual(self.library()['counts']['ready'],1)

    def test_unrelated_active_session_is_not_resumed_for_lesson(self):
        # An ordinary vocabulary session must not steal the lesson's Start action.
        ordinary=self.gen.create(self.access,{'submission_id':'ordinary','options':{'kind':'ru-cloze','quantity':1,'word_id':1}})
        self.gen.next(self.access,ordinary['id'])
        review=self.services['review']
        old=review.start(self.access,{'profile_id':'personal-learning','scope':{},'size':1,'submission_id':'ordinary-study'})
        result=self.prepare(); self.finish(result['batch_id'])
        self.assertIsNone(self.library()['active_session_id'])
        new=review.start(self.access,{'profile_id':'personal-learning','scope':{'lesson_id':self.lid},'size':1,'submission_id':'lesson-study'})
        self.assertNotEqual(new['id'],old['id'])
        self.assertNotEqual(new['item']['card_id'],old['item']['card_id'])
