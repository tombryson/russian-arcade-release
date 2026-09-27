"""Selected words retain their identity from page highlight to native card."""
from tests.support import latest_schema_version
from copy import deepcopy
import json
import unittest
from migrations import upgrade_database
from unittest.mock import Mock

from repositories.learning_repository import LearningError, transaction
from services.lesson_ocr import LessonOCR
from services.lesson_ocr import valid_box
from tests import test_lesson_cards as fixtures
from tests.test_lesson_cards import candidate
from tests.support import strip_progression_and_levels


BOXES={'width':160,'height':120,'words':[
    {'key':'0','surface':'городах','ocr':'городах.','x':.1,'y':.2,'width':.3,'height':.1,'confidence':95},
    {'key':'1','surface':'думает','ocr':'думает','x':.2,'y':.4,'width':.3,'height':.1,'confidence':94},
]}


class LessonSelectionTests(unittest.TestCase):
    def setUp(self):
        fixtures.LessonCardTests.setUp(self)
        self.selection=self.services['lesson_selection']
        self.selection.ocr._recognize=Mock(return_value=deepcopy(BOXES))
        def generated(pages,selections):
            return {'cards':[candidate(pick_id=p['id'],origin='source',surface=p['surface']) for p in selections]}
        self.ai.selected_flashcards=Mock(side_effect=generated)

    def choose(self,token='0',selected=True):
        page=self.selection.page(self.access,self.lid,self.rid,1)
        key=page['words'][int(token)]['key'] if token.isdigit() else token
        return self.selection.choose(self.access,self.lid,self.rid,1,key,selected)

    def start(self):
        return self.selection.create(self.access,self.lid,self.rid)

    def test_capture_remove_and_reload_without_generation(self):
        first=self.choose();self.assertEqual(first['pending_count'],1)
        self.assertIn('городах',first['picks'][0]['context'])
        self.assertEqual(self.choose()['picks'][0]['id'],first['picks'][0]['id'])
        self.assertEqual(self.selection.ocr._recognize.call_count,1)
        self.assertEqual(self.ai.card_calls,0);self.ai.selected_flashcards.assert_not_called()
        self.assertEqual(self.choose(selected=False)['pending_count'],0)
        self.assertEqual(self.choose()['picks'][0]['id'],first['picks'][0]['id'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM native_card_batches').fetchone()[0],0)

    def test_explicit_selection_not_confused_with_old_page_request(self):
        old=self.cards.create(self.access,self.lid,self.rid,1,1,1)
        pick=self.choose()['picks'][0];new=self.start()
        self.assertNotEqual(old,new)
        self.assertEqual(self.start(),new)
        saved=self.cards.advance(self.access,new,self.lid)
        self.assertEqual(saved['state'],'ready',saved)
        sent=self.ai.selected_flashcards.call_args.args[1]
        self.assertEqual([p['id'] for p in sent],[pick['id']])
        self.assertEqual(self.ai.card_calls,0)
        with transaction(self.db) as conn:
            self.assertTrue(conn.execute('SELECT item_id FROM lesson_word_picks WHERE id=?',(pick['id'],)).fetchone()[0])
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_unselected_substitution_is_rejected_and_pick_is_kept(self):
        pick=self.choose()['picks'][0];request_id=self.start()
        self.ai.selected_flashcards.return_value=None
        self.ai.selected_flashcards.side_effect=lambda *args:{'cards':[candidate(pick_id=pick['id'],origin='source',surface='новых',lemma='новый')]}
        result=self.cards.advance(self.access,request_id,self.lid)
        self.assertEqual(result['state'],'failed')
        pending=self.selection.pending(self.access,self.lid,self.rid)
        self.assertEqual(pending['pending_count'],1)
        self.assertEqual(pending['picks'][0]['surface'],'городах')

    def test_spelling_correction_makes_new_request_after_failure(self):
        pick=self.choose()['picks'][0];first=self.start()
        with transaction(self.db,write=True) as conn:
            conn.execute("UPDATE lesson_card_requests SET state='failed' WHERE id=?",(first,))
        self.selection.edit(self.access,self.lid,self.rid,pick['id'],'го́родах')
        second=self.start();self.assertNotEqual(first,second)
        with transaction(self.db) as conn:
            original=json.loads(conn.execute('SELECT selection FROM lesson_card_requests WHERE id=?',(first,)).fetchone()[0])
            self.assertEqual(original[0]['surface'],'городах')

    def test_new_example_is_labelled_and_reuses_native_media_pipeline(self):
        pick=self.choose()['picks'][0];request_id=self.start()
        self.ai.selected_flashcards.side_effect=lambda *args:{'cards':[candidate(pick_id=pick['id'],origin='example',sentence='В этих городах много музеев.',sentence_english='There are many museums in these cities.')]}
        result=self.cards.advance(self.access,request_id,self.lid)
        self.assertEqual(result['state'],'ready',result)
        batch=fixtures.LessonCardTests.finish(self,result['batch_id'])
        self.assertEqual(batch['items'][0]['origin'],'example')
        card=fixtures.LessonCardTests.library(self)['cards'][0]
        self.assertEqual(card['sources'][0]['origin'],'example')
        self.assertEqual(card['answer'],'городах');self.assertTrue(card['media_ready'])

    def test_cannot_change_a_selection_while_generation_claims_it(self):
        pick=self.choose()['picks'][0];self.start()
        with self.assertRaises(LearningError):self.choose(selected=False)
        with self.assertRaises(LearningError):self.selection.edit(self.access,self.lid,self.rid,pick['id'],'город')

    def test_routes_enforce_csrf_and_validate_tokens(self):
        base=f'/lessons/{self.lid}/word-selection/{self.rid}'
        self.assertEqual(self.client.get(base+'/1').status_code,200)
        data={'page':1,'token':self.selection.page(self.access,self.lid,self.rid,1)['words'][0]['key'],'selected':True}
        self.assertEqual(self.client.post(base,json=data).status_code,403)
        r=self.client.post(base,json=data,headers={'X-CSRF-Token':self.csrf,'Accept':'application/json'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['pending_count'],1)
        with self.assertRaises(LearningError):self.choose('does-not-exist')
        with self.assertRaises(LearningError):self.selection.choose('invalid',self.lid,self.rid,1,'0',True)

    def test_source_alignment_preserves_accents_and_yo_without_correcting_endings(self):
        words=['Этот','нарбд','живёт','в','новый','городах']
        payload={'words':[{'surface':w,'ocr':w} for w in words]}
        result=LessonOCR.align(payload,'Этот наро́д живёт в новых городах.')['words']
        self.assertEqual(result[1]['surface'],'наро́д')
        self.assertEqual(result[2]['surface'],'живёт')
        self.assertEqual(result[4]['surface'],'новый');self.assertFalse(result[4]['matched'])

    def test_suggestions_do_not_silently_rewrite_an_ending(self):
        payload={'words':[{'surface':w,'ocr':w} for w in ['в','новый','городах']]}
        result=LessonOCR.align(payload,'В новых городах.')['words'][1]
        self.assertEqual(result['surface'],'новый')
        self.assertTrue(result['needs_check'])
        self.assertEqual(result['suggestions'][0]['surface'],'новых')

    def test_confirmed_correction_retains_crop_and_original_after_deselect(self):
        boxes=deepcopy(BOXES);boxes['words'][0].update(surface='тородах',ocr='тородах')
        self.selection.ocr._recognize.return_value=boxes
        word=self.selection.page(self.access,self.lid,self.rid,1)['words'][0]
        self.assertTrue(word['needs_check'])
        self.assertEqual(word['suggestions'][0]['surface'],'городах')
        with self.assertRaises(LearningError):self.selection.choose(self.access,self.lid,self.rid,1,word['key'],True)
        saved=self.selection.choose(self.access,self.lid,self.rid,1,word['key'],True,surface='городах',confirmed=True)
        self.assertEqual(saved['picks'][0]['original'],'тородах')
        self.assertIn('Анна живёт',saved['picks'][0]['context'])
        self.selection.choose(self.access,self.lid,self.rid,1,word['key'],False)
        reloaded=self.selection.page(self.access,self.lid,self.rid,1)['words'][0]
        self.assertEqual(reloaded['surface'],'городах');self.assertFalse(reloaded['needs_check'])
        self.selection.choose(self.access,self.lid,self.rid,1,word['key'],True)
        self.assertEqual(self.cards.advance(self.access,self.start(),self.lid)['state'],'ready')
        crop=self.client.get(f'/lessons/{self.lid}/word-selection/{self.rid}/1/crop/{word["key"]}')
        self.assertEqual(crop.status_code,200);self.assertEqual(crop.mimetype,'image/png')

    def test_reordered_ocr_cannot_move_an_existing_selection(self):
        saved=self.choose()['picks'][0]
        boxes=deepcopy(BOXES);boxes['words'].reverse()
        with transaction(self.db,write=True) as conn:conn.execute('DELETE FROM lesson_ocr_pages')
        self.selection.ocr._recognize.return_value=boxes
        page=self.selection.page(self.access,self.lid,self.rid,1)
        same=next(w for w in page['words'] if w['key']==saved['region_id'])
        self.assertEqual(same['surface'],'городах');self.assertEqual(same['x'],.1)
        self.assertNotEqual(page['words'][0]['key'],saved['region_id'])

    def test_area_capture_is_optional_and_does_not_save_until_confirmed(self):
        box={'x':.1,'y':.2,'width':.3,'height':.1}
        self.selection.ocr._recognize.return_value={'words':[{'surface':'городах','ocr':'городах'}]}
        word=self.selection.ocr.read_area(self.lid,self.rid,1,box)
        self.assertEqual(word['kind'],'area');self.assertTrue(word['needs_check'])
        self.assertEqual(self.selection.pending(self.access,self.lid,self.rid)['pending_count'],0)
        self.selection.choose(self.access,self.lid,self.rid,1,word['key'],True,surface='городах',confirmed=True)
        self.assertEqual(self.selection.pending(self.access,self.lid,self.rid)['pending_count'],1)
        self.assertEqual(self.ai.card_calls,0)

    def test_region_validation_and_owner_access(self):
        for box in (None,{}, {'x':float('nan'),'y':0,'width':.2,'height':.2}, {'x':.9,'y':0,'width':.2,'height':.2}, {'x':0,'y':0,'width':1,'height':1}):
            with self.assertRaises(LearningError):valid_box(box)
        base=f'/lessons/{self.lid}/word-selection/{self.rid}'
        body={'page':1,'box':{'x':.1,'y':.1,'width':.2,'height':.2}}
        self.assertEqual(self.client.post(base+'/area',json=body).status_code,403)
        with self.assertRaises(LearningError):self.selection.page('invalid',self.lid,self.rid,1)
        self.assertEqual(self.client.get(base+'/1/crop/not-a-region').status_code,409)

    def test_area_keeps_source_suggestions_when_crop_loses_letters(self):
        boxes=deepcopy(BOXES);boxes['words'][0].update(surface='тородах',ocr='тородах')
        self.selection.ocr._recognize.return_value=boxes
        self.selection.page(self.access,self.lid,self.rid,1)
        self.selection.ocr._recognize.return_value={'words':[{'surface':'гор','ocr':'гор'}]}
        word=self.selection.ocr.read_area(self.lid,self.rid,1,{'x':.1,'y':.2,'width':.3,'height':.1})
        self.assertEqual(word['surface'],'гор')
        self.assertEqual(word['ocr'],'гор')
        self.assertEqual(word['suggestions'][0]['surface'],'городах')
        self.assertEqual(self.selection.pending(self.access,self.lid,self.rid)['pending_count'],0)

    def test_previous_tap_does_not_confirm_an_uncertain_reading(self):
        pick=self.choose()['picks'][0]
        self.choose(selected=False)
        with transaction(self.db,write=True) as conn:
            conn.execute("UPDATE lesson_word_picks SET surface='тородах',original='тородах' WHERE id=?",(pick['id'],))
            conn.execute('DELETE FROM lesson_ocr_pages')
        boxes=deepcopy(BOXES);boxes['words'][0].update(surface='тородах',ocr='тородах')
        self.selection.ocr._recognize.return_value=boxes
        word=self.selection.page(self.access,self.lid,self.rid,1)['words'][0]
        self.assertTrue(word['needs_check'])
        with self.assertRaises(LearningError):self.selection.choose(self.access,self.lid,self.rid,1,word['key'],True)
        result=self.selection.choose(self.access,self.lid,self.rid,1,word['key'],True,surface='городах',confirmed=True)
        self.assertEqual(result['picks'][0]['surface'],'городах')
        self.assertEqual(result['picks'][0]['original'],'тородах')

    def test_selection_routes_reject_non_object_json(self):
        base=f'/lessons/{self.lid}/word-selection/{self.rid}'
        headers={'X-CSRF-Token':self.csrf,'Accept':'application/json'}
        for path in (base,base+'/area'):
            for body in (['page',1],'word',True):
                response=self.client.post(path,json=body,headers=headers)
                self.assertEqual(response.status_code,422)

    def test_migration_anchors_existing_picks_without_changing_their_readings(self):
        saved=self.choose()['picks'][0]
        with transaction(self.db,write=True) as conn:
            conn.execute("UPDATE lesson_word_picks SET token_key='0',surface='го́родах' WHERE id=?",(saved['id'],))
            conn.execute("UPDATE lesson_ocr_pages SET policy='tesseract-rus-eng-boxes-v1'")
            conn.execute('DROP INDEX lesson_pick_region')
            conn.execute('ALTER TABLE lesson_word_picks DROP COLUMN reading_confirmed')
            conn.execute('ALTER TABLE lesson_word_picks DROP COLUMN region_id')
            conn.execute('DROP TABLE lesson_word_regions')
            conn.execute('ALTER TABLE word_jumble_attempts DROP COLUMN tutor_feedback')
            strip_progression_and_levels(conn)
            conn.execute('DROP INDEX live_sessions_scenario')
            conn.execute('ALTER TABLE live_conversation_sessions DROP COLUMN variant_id')
            conn.execute('ALTER TABLE live_conversation_sessions DROP COLUMN scenario_id')
            conn.execute('ALTER TABLE live_conversation_sessions DROP COLUMN end_reason')
            conn.execute('DROP TABLE speaking_reviews')
            conn.execute('DELETE FROM schema_migrations WHERE version>=18')
            old=dict(conn.execute('SELECT * FROM lesson_word_picks WHERE id=?',(saved['id'],)).fetchone())
        self.assertEqual(upgrade_database(self.db,backup=False)[0],latest_schema_version())
        with transaction(self.db) as conn:
            now=dict(conn.execute('SELECT * FROM lesson_word_picks WHERE id=?',(saved['id'],)).fetchone())
            self.assertEqual({k:now[k] for k in old},old)
            region=json.loads(conn.execute('SELECT payload FROM lesson_word_regions WHERE id=?',(now['region_id'],)).fetchone()[0])
            self.assertEqual(region['x'],.1)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
