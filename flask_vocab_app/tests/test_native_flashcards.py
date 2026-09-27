"""Real SQLite/FSRS workflows. Providers and personal data are never used."""
from tests.support import latest_schema_version
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
import unittest

from contracts.learning import validate_pack
from migrations import MIGRATION_DIR, upgrade_database, seed_demo
from repositories.learning_repository import LearningError, transaction
from services.learning_backup import backup_learning_store
from services.native_review import NativeReviewService
from services.card_preparation import prepare_starter
from tests import test_learning as helpers
from tests.support import strip_progression_and_levels


def deck(deck_id='native-test',count=1):
    return {'schema_version':2,'id':deck_id,'kind':'deck','title':'Words in situations','title_ru':'Слова в ситуациях',
            'source':'Synthetic isolated test material; never household curriculum.',
            'items':[{'id':f'item-{i}','card_id':f'card-{i}','word_id':i+1,'type':'basic','direction':'ru-en',
                      'sense_key':f'sense-{i}','sense_label':'At breakfast','context':'Я пью кофе.',
                      'prompt':f'Prompt {i}','answer':f'Contextual answer {i}; no claim of a universal equivalent.',
                      'explanation':'This description belongs to this situation.','hint':'An answer-bearing hint.'} for i in range(count)]}


class NativeFlashcardTests(unittest.TestCase):
    post=helpers.LearningTests.post
    unlock=helpers.LearningTests.unlock
    learner=helpers.LearningTests.learner
    credential=staticmethod(helpers.LearningTests.credential)

    def setUp(self):
        helpers.LearningTests.setUp(self)
        self.review=self.services['review'];self.now=int(time.time());self.review.clock=lambda:self.now
        self.authoring=self.services['card_authoring']

    def publish(self,pack=None):
        version=self.content.import_draft(pack or deck())
        self.content.publish(self.credential(self.adult),version,'Synthetic fixture reviewer')
        return version

    def begin(self,child,profile,**changes):
        data={'profile_id':profile,'scope':{},'size':10,'submission_id':'start'};data.update(changes)
        result=self.post(child,'/api/v1/review-sessions',data)
        self.assertEqual(result.status_code,201,result.get_data(as_text=True));return result.json

    def move(self,child,saved,op,**extra):
        data={'submission_id':f'{op}-{saved["revision"]}','expected_revision':saved['revision']}
        if op in ('reveal','help','reviews','report'):data['item_id']=saved['item']['id']
        data.update(extra)
        result=self.post(child,f'/api/v1/review-sessions/{saved["id"]}/{op}',data)
        self.assertEqual(result.status_code,200,result.get_data(as_text=True));return result.json

    def rows(self,table):
        with transaction(self.db) as conn:return [dict(r) for r in conn.execute(f'SELECT * FROM {table}')]

    def test_learner_can_change_interface_language_without_adult_access(self):
        child,profile=self.learner()
        before=self.credential(child)
        token=child.get('/api/v1/household').json['csrf_token']
        self.assertEqual(child.post('/ui-language',data={'lang':'ru'}).status_code,403)
        response=child.post('/ui-language',data={'lang':'ru','next':'/#flashcards','csrf_token':token})
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.headers['Location'],'/#flashcards')
        with child.session_transaction() as browser:
            self.assertEqual(browser['ui_lang'],'ru')
            self.assertEqual(browser['household_access_id'],before)
        self.assertEqual(child.get('/api/v1/flashcards').json['profile_id'],profile)
        self.assertEqual(child.get('/post/flashcards/manage').status_code,302)

    def test_contextual_meanings_are_versions_not_a_translation_column(self):
        pack=deck();other=copy.deepcopy(pack['items'][0]);other.update(id='other',card_id='other',sense_key='another-use',answer='A different explanation in another situation.')
        pack['items'].append(other);self.publish(pack)
        child,p=self.learner();overview=child.get('/api/v1/flashcards').json
        self.assertEqual(overview['counts']['cards'],2);self.assertEqual(overview['counts']['words'],1)
        with transaction(self.db) as conn:
            self.assertNotIn('translation',{r[1] for r in conn.execute('PRAGMA table_info(words)')})
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_versions').fetchone()[0],2)

    def test_cloze_requires_exact_context_form_and_punctuation(self):
        pack=deck();item=pack['items'][0];item.update(type='cloze',direction='ru-cloze',prompt='Я пью [[blank]].',answer='кофе',context='Я пью кофе.',form_id=1)
        self.publish(pack)
        for changes in ({'answer':'кофе.'},{'answer':'школа','context':'Я пью школа.'},{'form_id':2},{'prompt':'Я пью ко[[blank]].'}):
            bad=copy.deepcopy(pack);bad['id']='bad';bad['items'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(LearningError):self.content.import_draft(bad)
        child,p=self.learner();saved=self.begin(child,p)
        self.assertNotIn('answer',saved['item']);self.assertNotIn('context',saved['item'])
        saved=self.move(child,saved,'reveal');self.assertEqual(saved['item']['answer'],'кофе')

    def test_v1_pack_is_indexed_without_mutating_its_payload(self):
        pack={'schema_version':1,'id':'old-deck','kind':'deck','title':'Old draft','source':'Synthetic test','items':[{'id':'coffee','word_id':1,'type':'basic','direction':'ru-en','prompt':'кофе','answer':'coffee'}]}
        self.publish(pack);child,p=self.learner();saved=self.begin(child,p)
        self.assertEqual(saved['item']['prompt'],'кофе')
        self.assertEqual(json.loads(self.rows('learning_content_versions')[0]['payload']),pack)

    def test_reveal_rate_resume_and_due_state_survive_service_restart(self):
        self.publish();child,p=self.learner();saved=self.begin(child,p)
        self.assertNotIn('Contextual answer',json.dumps(saved))
        saved=self.move(child,saved,'reveal');revealed=copy.deepcopy(saved)
        restored=NativeReviewService(self.db,clock=lambda:self.now).read(self.credential(child),saved['id'])
        self.assertEqual(restored,revealed)
        saved=self.move(child,saved,'reviews',rating='good')
        self.assertEqual(saved['feedback']['due_at'],self.now+600)
        saved=self.move(child,saved,'next');self.assertEqual(saved['phase'],'completed')
        overview=child.get('/api/v1/flashcards').json
        self.assertEqual(overview['counts']['due'],0);self.assertEqual(overview['counts']['practised_today'],1)
        self.assertEqual(len(self.rows('activity_attempts')),1);self.assertEqual(len(self.rows('learning_reward_entries')),0)

    def test_concurrent_duplicate_rating_has_one_schedule_and_one_attempt(self):
        self.publish();child,p=self.learner();s=self.move(child,self.begin(child,p),'reveal')
        body={'submission_id':'same','expected_revision':s['revision'],'item_id':s['item']['id'],'rating':'again'}
        def submit(_):return self.review.command(self.credential(child),s['id'],'reviews',body)
        credential=self.credential(child)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.review.command(credential,s['id'],'reviews',body),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(len(self.rows('activity_attempts')),1)
        self.assertEqual(self.rows('learner_card_state')[0]['reviews'],1)
        self.assertEqual(len(self.rows('learner_word_evidence')),1)
        with self.assertRaises(LearningError) as conflict:self.review.command(credential,s['id'],'reviews',{**body,'rating':'good'})
        self.assertEqual(conflict.exception.code,'idempotency_conflict')

    def test_grading_requires_reveal_and_stale_new_commands_cannot_replace_it(self):
        self.publish();child,p=self.learner();s=self.begin(child,p)
        body={'submission_id':'early','expected_revision':s['revision'],'item_id':s['item']['id'],'rating':'good'}
        self.assertEqual(self.post(child,f'/api/v1/review-sessions/{s["id"]}/reviews',body).status_code,400)
        shown=self.move(child,s,'reveal')
        stale=self.post(child,f'/api/v1/review-sessions/{s["id"]}/reviews',{**body,'submission_id':'stale'})
        self.assertEqual(stale.status_code,409);self.assertEqual(stale.json['error']['current_session'],shown)
        self.assertEqual(self.rows('review_events'),[])

    def test_hint_use_is_recorded_without_overriding_the_chosen_rating(self):
        self.publish();child,p=self.learner();s=self.move(child,self.begin(child,p),'help')
        self.assertTrue(s['item']['assisted']);s=self.move(child,s,'reveal');s=self.move(child,s,'reviews',rating='good')
        self.assertEqual(s['feedback']['rating'],'good');self.assertEqual(s['feedback']['due_at'],self.now+600)
        self.assertEqual(self.rows('learner_word_evidence')[0]['evidence_type'],'supported_recall')

    def test_undo_retains_audit_exposure_and_restores_effective_counts(self):
        self.publish();child,p=self.learner();s=self.move(child,self.begin(child,p),'reveal')
        before=self.rows('learner_card_state')[0]
        s=self.move(child,s,'reviews',rating='good');s=self.move(child,s,'undo')
        after=self.rows('learner_card_state')[0]
        self.assertEqual(before['scheduler_state'],after['scheduler_state']);self.assertGreater(after['revision'],before['revision'])
        self.assertEqual(len(self.rows('review_events')),1);self.assertEqual(len(self.rows('review_reversals')),1)
        self.assertEqual(child.get('/api/v1/word-pocket').json['evidence'],[])
        counts=child.get('/api/v1/flashcards').json['counts'];self.assertEqual(counts['practised_today'],0);self.assertEqual(counts['new_allowance'],4)
        s=self.move(child,s,'reviews',rating='again')
        self.assertEqual(len(self.rows('review_events')),2);self.assertEqual(self.rows('learner_card_state')[0]['reviews'],1)
        self.assertEqual(child.get('/api/v1/flashcards').json['counts']['answers_today'],1)

    def test_card_change_blocks_unsafe_undo(self):
        self.publish();child,p=self.learner();s=self.move(child,self.move(child,self.begin(child,p),'reveal'),'reviews',rating='good')
        state=self.rows('learner_card_state')[0]
        self.review.suspend(self.credential(child),'card-0',{'profile_id':p,'suspended':True,'expected_revision':state['revision']})
        result=self.post(child,f'/api/v1/review-sessions/{s["id"]}/undo',{'submission_id':'unsafe','expected_revision':s['revision']})
        self.assertEqual(result.status_code,409);self.assertEqual(result.json['error']['code'],'undo_conflict')
        self.assertEqual(self.rows('review_reversals'),[])

    def test_undo_after_advance_restores_previous_card_and_keeps_next_front_unrevealed(self):
        self.publish(deck(count=2));child,p=self.learner();s=self.move(child,self.begin(child,p),'reveal')
        original=s['item'];before=self.rows('learner_card_state')[0]
        s=self.move(child,s,'reviews',rating='good');s=self.move(child,s,'next')
        self.assertEqual(s['phase'],'front');self.assertTrue(s['can_undo'])
        self.assertNotEqual(s['item']['card_id'],original['card_id']);self.assertNotIn('answer',s['item'])
        self.assertIsNone(s['feedback'])
        s=self.move(child,s,'undo')
        self.assertEqual(s['phase'],'revealed');self.assertEqual(s['practised_cards'],0)
        self.assertEqual(s['item']['card_id'],original['card_id'])
        restored=next(row for row in self.rows('learner_card_state') if row['card_id']==original['card_id'])
        self.assertEqual(restored['scheduler_state'],before['scheduler_state'])
        self.assertEqual(len(self.rows('review_events')),1);self.assertEqual(len(self.rows('review_reversals')),1)
        s=self.move(child,s,'reviews',rating='hard');s=self.move(child,s,'next')
        self.assertEqual(s['phase'],'front');self.assertEqual(s['practised_cards'],1)
        s=self.move(child,s,'reveal');self.assertFalse(s['can_undo'])

    def test_last_answer_can_be_undone_from_automatic_completion(self):
        self.publish();child,p=self.learner();s=self.move(child,self.move(child,self.begin(child,p),'reveal'),'reviews',rating='easy')
        s=self.move(child,s,'next');self.assertEqual(s['status'],'completed');self.assertTrue(s['can_undo'])
        s=self.move(child,s,'undo');self.assertEqual(s['status'],'active');self.assertEqual(s['phase'],'revealed')
        self.assertEqual(s['practised_cards'],0)
        self.assertEqual(child.get('/api/v1/flashcards').json['active_session_id'],s['id'])
        s=self.move(child,s,'reviews',rating='good');s=self.move(child,s,'next')
        self.assertEqual(len(self.rows('review_events')),2);self.assertEqual(len(self.rows('review_reversals')),1)

    def test_undo_cannot_reopen_old_practice_after_another_session_starts(self):
        self.publish(deck(count=2));child,p=self.learner();s=self.move(child,self.move(child,self.begin(child,p,size=1),'reveal'),'reviews',rating='good')
        s=self.move(child,s,'next');self.assertTrue(s['can_undo'])
        other=self.begin(child,p,size=1,submission_id='another-practice')
        self.assertNotEqual(other['id'],s['id'])
        self.assertFalse(child.get(f'/api/v1/review-sessions/{s["id"]}').json['can_undo'])
        result=self.post(child,f'/api/v1/review-sessions/{s["id"]}/undo',{'submission_id':'late-undo','expected_revision':s['revision']})
        self.assertEqual(result.status_code,409);self.assertEqual(result.json['error']['code'],'undo_conflict')

    def test_explicit_finish_closes_undo(self):
        self.publish(deck(count=2));child,p=self.learner();s=self.move(child,self.move(child,self.begin(child,p),'reveal'),'reviews',rating='good')
        s=self.move(child,s,'next');s=self.move(child,s,'finish')
        self.assertFalse(child.get(f'/api/v1/review-sessions/{s["id"]}').json['can_undo'])
        result=self.post(child,f'/api/v1/review-sessions/{s["id"]}/undo',{'submission_id':'late-undo','expected_revision':s['revision']})
        self.assertEqual(result.status_code,409);self.assertEqual(result.json['error']['code'],'undo_unavailable')

    def test_reporting_a_bad_card_is_not_a_failed_recall(self):
        self.publish();child,p=self.learner();s=self.begin(child,p)
        s=self.move(child,s,'report',reason='meaning')
        self.assertIsNone(s['feedback']);self.assertFalse(s['can_undo'])
        self.assertEqual(self.rows('review_events'),[]);self.assertEqual(len(self.rows('card_reports')),1)
        self.assertEqual(self.rows('learner_card_state')[0]['suspended'],1)
        self.assertEqual(self.review.read(self.credential(child),s['id'])['skipped_cards'],1)
        s=self.move(child,s,'next');self.assertEqual(s['status'],'completed')

    def test_draft_withdrawal_and_profile_ownership_are_checked_before_cache(self):
        version=self.content.import_draft(deck());child,p=self.learner()
        self.assertEqual(child.get('/api/v1/flashcards').json['counts']['cards'],0)
        self.content.publish(self.credential(self.adult),version,'Test');s=self.begin(child,p);s=self.move(child,s,'reveal')
        other,_=self.learner('Other')
        self.assertEqual(other.get(f'/api/v1/review-sessions/{s["id"]}').status_code,404)
        self.content.withdraw(self.credential(self.adult),version)
        unavailable=child.get(f'/api/v1/review-sessions/{s["id"]}')
        self.assertEqual(unavailable.status_code,409);self.assertNotIn('Contextual answer',unavailable.get_data(as_text=True))
        body={'submission_id':'reveal-0','expected_revision':0,'item_id':s['item']['id']}
        self.assertEqual(self.post(child,f'/api/v1/review-sessions/{s["id"]}/reveal',body).status_code,409)
        ended=self.move(child,s,'finish');self.assertEqual(ended['phase'],'completed')

    def test_multiple_tabs_resume_one_active_review_and_preserve_start_keys(self):
        self.publish();child,p=self.learner();first=self.begin(child,p);second=self.begin(child,p,submission_id='other-tab')
        self.assertEqual(first['id'],second['id']);self.assertEqual(len(self.rows('review_sessions')),1)
        self.move(child,second,'finish')
        replay=self.begin(child,p,submission_id='other-tab');self.assertEqual(replay,second)
        self.assertEqual(len(self.rows('review_sessions')),1)

    def test_new_allowance_is_claimed_on_issue_not_queue_selection(self):
        self.publish(deck(count=3));child,p=self.learner();s=self.begin(child,p)
        self.assertEqual(s['total_cards'],3);self.assertEqual(len(self.rows('review_introductions')),1)
        self.move(child,s,'finish');self.assertEqual(child.get('/api/v1/flashcards').json['counts']['new_allowance'],4)

    def test_daily_limit_and_learning_waits_are_honest(self):
        with transaction(self.db,write=True) as conn:
            for i in range(4,8):conn.execute("INSERT INTO words(id,lemma,pos,count,lemma_difficulty) VALUES (?,?,'NOUN',0,1)",(i,f'тест{i}'))
        self.publish(deck(count=7));child,p=self.learner();s=self.begin(child,p,size=20)
        self.assertEqual(s['total_cards'],5)
        while s['phase']!='completed':
            s=self.move(child,s,'reveal');s=self.move(child,s,'reviews',rating='again');s=self.move(child,s,'next')
        counts=child.get('/api/v1/flashcards').json['counts'];self.assertEqual(counts['new_allowance'],0);self.assertEqual(counts['due'],0)
        self.now+=61
        counts=child.get('/api/v1/flashcards').json['counts'];self.assertEqual(counts['due'],5);self.assertEqual(counts['new_allowance'],0)
        s=self.begin(child,p,submission_id='later',size=20);self.assertEqual(s['total_cards'],5)

    def test_repeated_card_can_return_as_a_new_occurrence_when_due(self):
        self.publish(deck(count=2));child,p=self.learner();s=self.begin(child,p)
        first=s['item']['id'];first_card=s['item']['card_id']
        s=self.move(child,self.move(child,s,'reveal'),'reviews',rating='again');self.now+=61
        s=self.move(child,s,'next');self.assertEqual(s['item']['card_id'],first_card);self.assertNotEqual(s['item']['id'],first)
        self.assertEqual(s['total_cards'],2)

    def test_same_card_in_two_collections_has_one_memory_and_siblings_are_spaced(self):
        pack=deck();self.publish(pack);duplicate=copy.deepcopy(pack);duplicate['id']='another-deck';duplicate['title']='Another collection';self.publish(duplicate)
        child,p=self.learner();overview=child.get('/api/v1/flashcards').json
        self.assertEqual(overview['counts']['cards'],1);self.assertEqual(len(overview['cards'][0]['decks']),2)
        s=self.begin(child,p,scope={'deck':'another-deck'});self.move(child,self.move(child,s,'reveal'),'reviews',rating='good')
        self.assertEqual(len(self.rows('learner_card_state')),1)

    def test_filter_facets_remain_available_after_empty_search(self):
        pack=deck();pack['items'][0]['topic']='Everyday life';self.publish(pack)
        child,p=self.learner()
        empty=child.get('/api/v1/flashcards?q=unmatched').json
        self.assertEqual(empty['cards'],[])
        self.assertEqual(empty['facets']['topics'],['Everyday life'])
        self.assertEqual(empty['facets']['decks'][0]['title_ru'],'Слова в ситуациях')
        self.assertEqual(child.get('/api/v1/flashcards?topic=Everyday%20life').json['counts']['cards'],1)
        self.assertEqual(child.get('/api/v1/flashcards?topic=other').json['counts']['cards'],0)

    def test_media_only_hint_is_hidden_until_help_and_counts_as_supported(self):
        image=helpers.io.BytesIO();helpers.Image.new('RGB',(2,2),'blue').save(image,format='PNG')
        asset=helpers.import_asset(self.db,self.store,image.getvalue(),'Synthetic hint')
        pack=deck();pack['items'][0].pop('hint');pack['items'][0]['assets']=[{'id':asset,'role':'hint'}]
        self.publish(pack);child,p=self.learner();s=self.begin(child,p)
        self.assertTrue(s['item']['has_hint']);self.assertEqual(s['item']['assets'],[])
        s=self.move(child,s,'help');self.assertTrue(s['item']['assisted'])
        self.assertEqual(s['item']['assets'][0]['id'],asset)
        s=self.move(child,self.move(child,s,'reveal'),'reviews',rating='good')
        self.assertEqual(s['feedback']['rating'],'good')

    def test_failed_attempt_rolls_back_schedule_and_retry_is_safe(self):
        self.publish();child,p=self.learner();s=self.move(child,self.begin(child,p),'reveal');before=self.rows('learner_card_state')
        with transaction(self.db,write=True) as conn:conn.execute("CREATE TRIGGER fail_review BEFORE INSERT ON activity_attempts BEGIN SELECT RAISE(ABORT,'test failure'); END")
        body={'submission_id':'same-after-failure','expected_revision':s['revision'],'item_id':s['item']['id'],'rating':'good'}
        with self.assertRaises(sqlite3.IntegrityError):self.review.command(self.credential(child),s['id'],'reviews',body)
        self.assertEqual(self.rows('learner_card_state'),before);self.assertEqual(self.rows('review_events'),[])
        with transaction(self.db,write=True) as conn:conn.execute('DROP TRIGGER fail_review')
        result=self.review.command(self.credential(child),s['id'],'reviews',body);self.assertEqual(result['phase'],'feedback')

    def test_editing_a_meaning_creates_a_new_identity_on_approval(self):
        version=self.publish();child,p=self.learner();s=self.move(child,self.move(child,self.begin(child,p),'reveal'),'reviews',rating='good')
        old_state=self.rows('learner_card_state')
        cv=self.rows('card_versions')[0]['id']
        data={'draft_key':'edited','edit':cv,'word_id':'1','direction':'ru-en','sense_label':'At breakfast','context':'Я пью кофе.','prompt':'Prompt 0','answer':'A corrected contextual explanation.'}
        new=self.authoring.save(self.credential(self.adult),data)
        self.assertEqual(self.authoring.save(self.credential(self.adult),data),new)
        self.assertEqual(child.get('/api/v1/flashcards').json['cards'][0]['id'],'card-0')
        self.content.publish(self.credential(self.adult),new,'Test reviewer')
        self.assertEqual(child.get('/api/v1/flashcards').json['cards'][0]['id'],'card-edited')
        self.assertEqual(self.rows('learner_card_state'),old_state)
        self.assertEqual(child.get(f'/api/v1/review-sessions/{s["id"]}').status_code,409)

    def test_discard_draft_and_retire_card_preserve_sources(self):
        draft=self.content.import_draft(deck());self.authoring.discard(self.credential(self.adult),draft)
        with self.assertRaises(LearningError):self.content.publish(self.credential(self.adult),draft,'Test')
        self.assertEqual(len(self.rows('learning_content_versions')),1)
        other=deck('approved');other['items'][0]['card_id']='kept';self.publish(other)
        self.authoring.retire(self.credential(self.adult),'kept');child,p=self.learner()
        self.assertEqual(child.get('/api/v1/flashcards').json['counts']['cards'],0)

    def test_authoring_validation_retains_full_wording_and_escapes_html(self):
        token=self.adult.get('/api/v1/household').json['csrf_token']
        data={'csrf_token':token,'draft_key':'form-test','word_id':'1','direction':'ru-cloze','sense_label':'At breakfast','context':'Я пью кофе.','prompt':'Missing a blank','answer':'кофе','explanation':'<script>alert(1)</script>\nKeep all my explanation.'}
        response=self.adult.post('/post/flashcards/drafts',data=data)
        self.assertEqual(response.status_code,400,response.get_data(as_text=True))
        self.assertIn('Keep all my explanation.',response.get_data(as_text=True));self.assertNotIn('<script>alert(1)</script>',response.get_data(as_text=True))
        child,p=self.learner();self.assertEqual(child.get('/post/flashcards/manage').status_code,302)
        self.assertEqual(child.post('/post/flashcards/drafts',data=data).status_code,403)

    def test_schema_eight_session_and_pack_migrate_without_history_changes(self):
        old=Path(self.db).parent/'schema8.db'
        with sqlite3.connect(old) as conn:
            for path in sorted(MIGRATION_DIR.glob('00[1-8]_*.sql')):conn.executescript(path.read_text())
            conn.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT DEFAULT CURRENT_TIMESTAMP)');conn.execute('INSERT INTO schema_migrations(version) VALUES (8)');conn.commit()
        seed_demo(str(old))
        with sqlite3.connect(old) as conn:
            conn.execute("INSERT INTO learning_profiles VALUES ('p','Test','cat','UTC',0,NULL,1)")
            conn.execute("INSERT INTO learning_content VALUES ('d','deck',1)")
            pack={'schema_version':1,'id':'d','kind':'deck','title':'Old','source':'Test','items':[{'id':'old','word_id':1,'type':'basic','direction':'ru-en','prompt':'кофе','answer':'coffee'}]}
            conn.execute("INSERT INTO learning_content_versions VALUES ('v','d',1,'Old',?,'published','Test',1,'Test',1)",(json.dumps(pack),))
            conn.execute("INSERT INTO learning_sessions VALUES ('s','p','v','activity',0,2,'active',0,'key','hash','{}',1,2)")
            before=list(conn.execute('SELECT * FROM learning_sessions'));payload=conn.execute('SELECT payload FROM learning_content_versions').fetchone()[0];conn.commit()
        self.assertEqual(upgrade_database(str(old),backup=False)[0],latest_schema_version())
        with sqlite3.connect(old) as conn:
            self.assertEqual(list(conn.execute('SELECT * FROM learning_sessions')),before)
            self.assertEqual(conn.execute('SELECT payload FROM learning_content_versions').fetchone()[0],payload)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM card_versions').fetchone()[0],1)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_backup_restore_includes_native_history_and_reversals(self):
        self.publish();child,p=self.learner();s=self.move(child,self.move(child,self.begin(child,p),'reveal'),'reviews',rating='good');s=self.move(child,s,'undo')
        target=Path(self.db).parent/'restore-check';backup_learning_store(self.db,self.store,target)
        restored=NativeReviewService(str(target/'vocab.db'),clock=lambda:self.now)
        self.assertEqual(restored.read(self.credential(child),s['id']),s)

    def test_completed_session_does_not_authorize_replaying_withdrawn_content(self):
        version=self.publish();child,p=self.learner();start=self.begin(child,p);s=self.move(child,start,'reveal')
        body={'submission_id':'saved-answer','expected_revision':s['revision'],'item_id':s['item']['id'],'rating':'good'}
        rated=self.review.command(self.credential(child),s['id'],'reviews',body)
        alias={'profile_id':p,'scope':{},'size':10,'submission_id':'resume-at-feedback'}
        resumed=self.review.start(self.credential(child),alias)
        self.assertEqual(resumed,rated)
        self.assertEqual(self.review.start(self.credential(child),alias),resumed)
        self.move(child,rated,'finish')
        self.content.withdraw(self.credential(self.adult),version)
        for call in (lambda:self.review.command(self.credential(child),s['id'],'reviews',body),
                     lambda:self.review.start(self.credential(child),alias),
                     lambda:self.review.start(self.credential(child),{'profile_id':p,'scope':{},'size':10,'submission_id':'start'})):
            with self.assertRaises(LearningError) as error:call()
            self.assertEqual(error.exception.code,'content_unavailable')
        self.assertEqual(len(self.rows('review_events')),1)

    def test_new_allowance_uses_the_study_day_across_midnight_and_dst(self):
        self.publish(deck(count=3));child,p=self.learner()
        def instant(value):return int(datetime.fromisoformat(value).timestamp())
        with transaction(self.db,write=True) as conn:
            conn.execute('UPDATE household_access SET expires_at=?',(instant('2026-10-10T00:00:00+00:00'),))
        # Melbourne: 23:59 Saturday, then midnight Sunday; later 01:59 jumps
        # to 03:01 on that same Sunday. The DST jump must not reset allowance.
        self.now=instant('2026-10-03T13:59:00+00:00');s=self.begin(child,p,scope={'q':'Prompt 0'});self.move(child,s,'finish')
        self.assertEqual(child.get('/api/v1/flashcards').json['counts']['new_allowance'],4)
        self.now=instant('2026-10-03T14:01:00+00:00')
        self.assertEqual(child.get('/api/v1/flashcards').json['counts']['new_allowance'],5)
        s=self.begin(child,p,scope={'q':'Prompt 1'},submission_id='next-day');self.move(child,s,'finish')
        self.now=instant('2026-10-03T15:59:00+00:00');self.assertEqual(child.get('/api/v1/flashcards').json['counts']['new_allowance'],4)
        self.now=instant('2026-10-03T16:01:00+00:00');self.assertEqual(child.get('/api/v1/flashcards').json['counts']['new_allowance'],4)

    def test_starter_preparation_reports_missing_words_and_never_publishes(self):
        with transaction(self.db,write=True) as conn:
            conn.execute("INSERT INTO words(id,lemma,pos,count,lemma_difficulty) VALUES (4,'яблоко','NOUN',0,1)")
            conn.execute("INSERT INTO forms(word_id,form,count,tags,form_difficulty) VALUES (4,'яблоко',0,'{}',1)")
        dry=prepare_starter(self.db,self.content,dry_run=True)
        self.assertEqual(len(dry['prepared']),1);self.assertEqual(len(dry['unmatched']),9);self.assertEqual(self.rows('learning_content_versions'),[])
        first=prepare_starter(self.db,self.content);again=prepare_starter(self.db,self.content)
        self.assertEqual(first,again);self.assertEqual(len(self.rows('learning_content_versions')),1)
        self.assertEqual(self.rows('learning_content_versions')[0]['status'],'draft');self.assertEqual(self.rows('learner_card_state'),[])

    def test_all_four_ratings_reach_fsrs_and_undo_without_losing_history(self):
        self.publish();child,p=self.learner();s=self.move(child,self.begin(child,p),'reveal')
        initial=self.rows('learner_card_state')[0]['scheduler_state']
        for rating, numeric, seconds in [('again',1,60),('hard',2,330),('good',3,600),('easy',4,None)]:
            with self.subTest(rating=rating):
                s=self.move(child,s,'reviews',rating=rating)
                event=self.rows('review_events')[-1]
                self.assertEqual(event['rating'],rating)
                self.assertEqual(json.loads(event['scheduler_log'])['rating'],numeric)
                self.assertEqual(s['feedback']['rating'],rating)
                state=self.rows('learner_card_state')[0]
                if seconds is None:
                    self.assertGreater(state['due_at'],self.now+86400)
                    self.assertEqual(json.loads(state['scheduler_state'])['state'],2)
                else:
                    self.assertEqual(state['due_at'],self.now+seconds)
                self.assertEqual(NativeReviewService(self.db,clock=lambda:self.now).read(self.credential(child),s['id']),s)
                s=self.move(child,s,'undo')
                self.assertEqual(self.rows('learner_card_state')[0]['scheduler_state'],initial)
        self.assertEqual([r['rating'] for r in self.rows('review_events')],['again','hard','good','easy'])
        self.assertEqual(len(self.rows('review_reversals')),4)
        self.assertEqual(self.rows('learner_card_state')[0]['reviews'],0)

    def test_cloze_cue_and_dictionary_keep_inflection_separate_from_lemma(self):
        from urllib.parse import quote
        with transaction(self.db,write=True) as conn:
            conn.execute("UPDATE words SET lemma='конструкция' WHERE id=1")
            conn.execute("UPDATE forms SET form='конструкций',tags=? WHERE id=1", ('{"case":"gent","number":"plur"}',))
        pack=deck();pack['items'][0].update(type='cloze',direction='ru-cloze',form_id=1,
            prompt='Я занимаюсь изучением [[blank]] в русском языке.',
            answer='конструкций',context='Я занимаюсь изучением конструкций в русском языке.',
            cue_en='structures',context_meaning='I am studying constructions in Russian.')
        self.publish(pack);child,p=self.learner();s=self.begin(child,p)
        self.assertEqual(s['item']['cue_en'],'structures')
        self.assertNotIn('dictionary_url',s['item'])
        for field in ('answer','context','context_meaning'):
            self.assertNotIn(field,s['item'])
        s=self.move(child,s,'reveal')
        self.assertEqual(s['item']['answer'],'конструкций')
        self.assertEqual(s['item']['dictionary_url'],'https://en.openrussian.org/ru/'+quote('конструкция'))
        self.assertEqual(s['item']['cue_en'],'structures')
        self.assertEqual(s['item']['context_meaning'],'I am studying constructions in Russian.')
        self.assertEqual(s['item']['prompt'].replace('[[blank]]',s['item']['answer']),s['item']['context'])

    def test_four_rating_migration_preserves_events_reversals_and_append_only_guards(self):
        self.publish();child,p=self.learner();s=self.move(child,self.begin(child,p),'reveal')
        s=self.move(child,s,'reviews',rating='good');s=self.move(child,s,'undo')
        s=self.move(child,s,'reviews',rating='again')
        old=Path(self.db).parent/'schema11.db'
        with sqlite3.connect(self.db) as source, sqlite3.connect(old) as conn:
            source.backup(conn)
            rows=conn.execute('SELECT rowid,* FROM review_events').fetchall()
            # Install the actual old table constraint with non-contiguous rowids.
            legacy=(MIGRATION_DIR/'009_native_flashcards.sql').read_text()
            start=legacy.index('CREATE TABLE IF NOT EXISTS review_events')
            statement=legacy[start:legacy.index(';',start)+1]
            conn.execute('DROP TABLE review_events')
            conn.execute(statement)
            for row in rows:
                conn.execute('INSERT INTO review_events(rowid,attempt_id,occurrence_id,card_id,card_version_id,rating,before_state,after_state,before_session,scheduler_log,scheduler_policy,study_day,study_timezone,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(row[0]*10,*row[1:]))
            strip_progression_and_levels(conn)
            conn.execute('DROP TABLE conversation_turns')
            conn.execute('DROP TABLE conversation_sessions')
            conn.execute('DROP TABLE live_conversation_recordings')
            conn.execute('DROP TABLE live_conversation_events')
            conn.execute('DROP TABLE speaking_reviews')
            conn.execute('DROP TABLE live_conversation_sessions')
            # Remove the later region extension when constructing an older schema.
            conn.execute('DROP INDEX lesson_pick_region')
            conn.execute('ALTER TABLE lesson_word_picks DROP COLUMN reading_confirmed')
            conn.execute('ALTER TABLE lesson_word_picks DROP COLUMN region_id')
            conn.execute('DROP TABLE lesson_word_regions')
            conn.execute('ALTER TABLE word_jumble_attempts DROP COLUMN tutor_feedback')
            conn.execute('DELETE FROM schema_migrations WHERE version>=12')
            tables=['review_events','review_reversals','activity_attempts','learner_card_state','learning_sessions','review_session_items','learning_content_versions']
            before={table:conn.execute(f'SELECT rowid,* FROM {table}').fetchall() for table in tables}
            conn.commit()
        version,backup=upgrade_database(str(old))
        self.assertEqual(version,latest_schema_version());self.assertTrue(Path(backup).exists())
        with sqlite3.connect(old) as conn:
            for table in tables:
                self.assertEqual(conn.execute(f'SELECT rowid,* FROM {table}').fetchall(),before[table],table)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
            for sql in ('UPDATE review_events SET rating="hard"','DELETE FROM review_events'):
                with self.assertRaisesRegex(sqlite3.IntegrityError,'append-only'):
                    conn.execute(sql)
        self.assertEqual(upgrade_database(str(old)),(latest_schema_version(),None))

    def test_retired_card_does_not_bury_its_new_cloze_replacement(self):
        self.publish();child,p=self.learner()
        s=self.move(child,self.move(child,self.begin(child,p),'reveal'),'reviews',rating='good')
        self.move(child,s,'finish')
        replacement=deck('replacement');replacement['items'][0].update(card_id='replacement-card',type='cloze',direction='ru-cloze',prompt='Я пью [[blank]].',answer='кофе',form_id=1,cue_en='coffee')
        self.publish(replacement)
        self.assertEqual(child.get('/api/v1/flashcards?deck=replacement').json['counts']['buried'],1)
        self.authoring.retire(self.credential(self.adult),'card-0')
        overview=child.get('/api/v1/flashcards?deck=replacement').json
        self.assertEqual(overview['counts']['buried'],0)
        self.assertEqual(overview['counts']['new'],1)
        self.assertEqual(len(self.rows('review_events')),1)
