"""Target evidence follows saved decisions and support rather than totals."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from migrations import upgrade_database
from repositories.learning_repository import LearningError, encoded, timestamp
from services.course_targets import (practice_action, practice_catalogue, practice_get, practice_start,
    record_checkpoint_targets, record_event_targets, record_speaking_targets, target_coverage, validate_practice)
from services.curriculum_targets import sections_for_level
from services.course_progression import checkpoint_start, course_snapshot
from services.progression import award, personal_profile, reverse


class CourseTargetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = str(Path(directory.name) / 'course.db')
        upgrade_database(path, backup=False)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.pid, self.now, self.serial = personal_profile(self.conn), timestamp(), 0
        self.conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)", (self.now,))

    def action(self, state, action, **body):
        self.serial += 1
        return practice_action(self.conn,self.pid,state['id'],action,{'item_id':state['current_item']['id'],**body},f'command-{self.serial}')

    def correct(self, state):
        items = json.loads(self.conn.execute('SELECT content_json FROM course_target_practice_attempts WHERE id=?',(state['id'],)).fetchone()[0])
        return next(i['question']['answer'] for i in items if i['id']==state['current_item']['id'])

    def test_catalogue_covers_required_targets_and_rejects_answer_or_transcript_leaks(self):
        catalogue = practice_catalogue()
        self.assertEqual(len(catalogue['items']),32)
        self.assertEqual(sum(bool(i['question'].get('audio_url')) for i in catalogue['items']),5)
        with self.assertRaises(ValueError): validate_practice(dict(catalogue,items=catalogue['items'][:-1]))
        bad=deepcopy(catalogue);bad['items'][0]['question']['answer']='missing'
        with self.assertRaises(ValueError): validate_practice(bad)
        bad=deepcopy(catalogue)
        listening=next(i for i in bad['items'] if i['question'].get('audio_url'))
        listening['question']['passage']=listening['question']['transcript']
        with self.assertRaises(ValueError): validate_practice(bad)

    def test_all_sections_play_to_completion_without_rewards_or_inferred_mastery(self):
        for section in sections_for_level():
            state=practice_start(self.conn,self.pid,section['id'],'start-'+section['id'])
            self.assertEqual(state['total_count'],8)
            while state['status']=='active':
                self.assertEqual(state['current_item']['stage'],'learn')
                self.assertIsNone(state['current_item']['question'])
                state=self.action(state,'learn')
                if state['current_item']['question'].get('audio_url'): state=self.action(state,'listened')
                self.assertNotIn('"answer":',json.dumps(state['current_item']['question']))
                state=self.action(state,'answer',choice_id=self.correct(state))
                self.assertEqual(state['current_item']['stage'],'feedback')
                state=self.action(state,'next')
            self.assertTrue(state['coverage']['ready'])
            self.assertEqual(state['completed_count'],8)
            self.assertEqual(state['coverage']['prepared_count'],8)
            self.assertFalse(any(t['demonstrated'] for t in state['coverage']['targets']))
        for table in ('progression_events','progression_entries','course_chapter_passes'):
            self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_reads_and_forged_aggregate_metadata_do_not_create_targets(self):
        self.assertEqual(target_coverage(self.conn,self.pid,'home')['prepared_count'],0)
        state=practice_start(self.conn,self.pid,'home','start')
        practice_get(self.conn,self.pid,state['id'])
        task=self.conn.execute("INSERT INTO sentences(sentence,english,topic,difficulty,owner_profile_id) VALUES ('Привет!','Hello!','greetings','A1',?)",(self.pid,)).lastrowid
        aid=self.conn.execute("INSERT INTO translation_attempts(sentence_id,response,score,strength,next_step,example,ui_language,created_at,coins_earned,elo_change,already_rewarded) VALUES (?,'Привет!',4,'Clear','Continue','Привет!','en',?,0,0,0)",(task,str(self.now))).lastrowid
        award(self.conn,self.pid,activity='translation',content_key=f'translation:{task}',source_key=f'translation-attempt:{aid}',title='Translation',evidence={'_course_targets':{'all':'demonstrated'}})
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0],0)
        self.assertNotIn('_course_targets',json.loads(self.conn.execute('SELECT evidence_json FROM progression_events').fetchone()[0]))

    def test_idempotency_resume_and_ownership(self):
        state=practice_start(self.conn,self.pid,'home','start')
        self.assertEqual(state,practice_start(self.conn,self.pid,'home','start'))
        self.assertEqual(state,practice_start(self.conn,self.pid,'home','resume'))
        with self.assertRaises(LearningError): practice_start(self.conn,self.pid,'market','start')
        body={'item_id':state['current_item']['id']}
        learned=practice_action(self.conn,self.pid,state['id'],'learn',body,'learn')
        self.assertEqual(learned,practice_action(self.conn,self.pid,state['id'],'learn',body,'learn'))
        with self.assertRaises(LearningError): practice_action(self.conn,self.pid,state['id'],'hint',body,'learn')
        with self.assertRaises(LearningError): practice_get(self.conn,'other',state['id'])
        with self.assertRaises(LearningError): practice_action(self.conn,'other',state['id'],'learn',body,'learn')
        with self.assertRaises(LearningError): practice_action(self.conn,self.pid,state['id'],'answer',dict(body,choice_id='made-up'),'bad-choice')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0],1)

    def test_first_error_is_immutable_and_hint_recorded(self):
        state=practice_start(self.conn,self.pid,'home','start')
        with self.assertRaises(LearningError): self.action(state,'answer',choice_id='1')
        state=self.action(state,'learn');correct=self.correct(state)
        wrong=next(c['id'] for c in state['current_item']['question']['choices'] if c['id']!=correct)
        state=self.action(state,'hint');state=self.action(state,'answer',choice_id=wrong)
        self.assertFalse(state['current_item']['feedback']['correct'])
        with self.assertRaises(LearningError): self.action(state,'answer',choice_id=correct)
        observation=self.conn.execute('SELECT * FROM course_target_observations WHERE practised=1').fetchone()
        self.assertEqual(json.loads(observation['first_response_json']),{'choice_id':wrong})
        self.assertEqual(observation['needs_practice'],1)
        self.assertTrue(json.loads(observation['support_json'])['hint'])

    def test_audio_must_be_played_or_explicit_transcript_support_used(self):
        state=practice_start(self.conn,self.pid,'home','start')
        while not state['current_item']['target_id'].endswith('.listen'):
            state=self.action(state,'learn');state=self.action(state,'answer',choice_id=self.correct(state));state=self.action(state,'next')
        state=self.action(state,'learn')
        self.assertIsNone(state['current_item']['transcript'])
        self.assertIsNone(state['current_item']['question']['passage'])
        with self.assertRaises(LearningError): self.action(state,'answer',choice_id=self.correct(state))
        state=self.action(state,'transcript')
        self.assertIn('письмо',state['current_item']['transcript'])
        state=self.action(state,'answer',choice_id=self.correct(state))
        row=self.conn.execute("SELECT * FROM course_target_observations WHERE practised=1 AND response_mode='listening_selection'").fetchone()
        self.assertEqual(row['demonstrated'],0)
        self.assertTrue(json.loads(row['support_json'])['transcript'])

    def checkpoint(self,support=None,wrong=False):
        question={'id':'q1','kind':'reading','answer':'a','target_ids':['a1.home.locate-object.read'], 'choices':[{'id':'a','text':'На столе.'},{'id':'b','text':'В сумке.'}]}
        aid='checkpoint-'+str(self.serial);self.serial+=1
        self.conn.execute('''INSERT INTO course_checkpoint_attempts
            (id,profile_id,chapter_id,chapter_number,variant_id,content_version,rubric_version,frozen_json,status,support_json,listened_at,answers_json,created_at,release_id,band)
            VALUES (?,?,'a1-home',1,'variant',2,'test-rubric',?,'retry',?,?,?,?,'a1-v1','A1')''',
            (aid,self.pid,encoded({'variant':{'questions':[question]}}),encoded(support or []),self.now,encoded({'q1':'b' if wrong else 'a'}),self.now))
        return aid

    def test_checkpoint_uses_owned_saved_answers_not_caller_total_or_answers(self):
        aid=self.checkpoint(wrong=True)
        self.assertEqual(record_checkpoint_targets(self.conn,self.pid,aid,{}, {'q1':'a'},False,self.now),1)
        row=self.conn.execute('SELECT * FROM course_target_observations WHERE checkpoint_id=?',(aid,)).fetchone()
        self.assertEqual((row['score'],row['demonstrated'],row['needs_practice']),(0,0,1))
        self.assertEqual(record_checkpoint_targets(self.conn,self.pid,aid,{}, {},False,self.now),0)
        with self.assertRaises(LearningError):record_checkpoint_targets(self.conn,'other',aid,{}, {},False,self.now)
        aid=self.checkpoint(support=['hint:q1']);record_checkpoint_targets(self.conn,self.pid,aid,{}, {},False,self.now)
        self.assertEqual(self.conn.execute('SELECT demonstrated FROM course_target_observations WHERE checkpoint_id=?',(aid,)).fetchone()[0],0)
        aid=self.checkpoint();record_checkpoint_targets(self.conn,self.pid,aid,{}, {},True,self.now)
        self.assertEqual(tuple(self.conn.execute('SELECT introduced,practised,demonstrated FROM course_target_observations WHERE checkpoint_id=?',(aid,)).fetchone()),(0,1,1))

    def test_independent_answer_prepares_target_without_an_intro_and_skips_it_in_gap_practice(self):
        aid = self.checkpoint()
        record_checkpoint_targets(self.conn, self.pid, aid, {}, {}, False, self.now)
        coverage = target_coverage(self.conn, self.pid, 'home')
        target = next(t for t in coverage['targets'] if t['id'] == 'a1.home.locate-object.read')
        self.assertFalse(target['introduced'])
        self.assertTrue(target['demonstrated'])
        self.assertTrue(target['prepared'])
        self.assertEqual(coverage['prepared_count'], 1)
        state = practice_start(self.conn, self.pid, 'home', 'skip-demonstrated')
        items = json.loads(self.conn.execute('SELECT content_json FROM course_target_practice_attempts WHERE id=?', (state['id'],)).fetchone()[0])
        self.assertEqual(len(items), 7)
        self.assertNotIn(target['id'], {item['target_id'] for item in items})

    def test_wrong_and_hinted_answers_without_teaching_do_not_prepare_or_demonstrate(self):
        for kwargs in ({'wrong': True}, {'support': ['hint:q1']}):
            aid = self.checkpoint(**kwargs)
            record_checkpoint_targets(self.conn, self.pid, aid, {}, {}, False, self.now)
        coverage = target_coverage(self.conn, self.pid, 'home')
        target = next(t for t in coverage['targets'] if t['id'] == 'a1.home.locate-object.read')
        self.assertTrue(target['practised'])
        self.assertFalse(target['demonstrated'])
        self.assertFalse(target['prepared'])
        self.assertEqual(coverage['prepared_count'], 0)

    def test_latest_difficulty_can_still_recommend_a_previously_demonstrated_target(self):
        for wrong in (False, True):
            aid = self.checkpoint(wrong=wrong)
            record_checkpoint_targets(self.conn, self.pid, aid, {}, {}, False, self.now)
        coverage = target_coverage(self.conn, self.pid, 'home')
        target = next(t for t in coverage['targets'] if t['id'] == 'a1.home.locate-object.read')
        self.assertTrue(target['prepared'])
        self.assertTrue(target['needs_practice'])
        state = practice_start(self.conn, self.pid, 'home', 'review-difficulty')
        self.assertEqual(state['total_count'], 8)

    def test_target_practice_is_an_alternative_to_activity_preparation_not_a_pass(self):
        state = practice_start(self.conn, self.pid, 'home', 'target-route')
        while state['status'] == 'active':
            state = self.action(state, 'learn')
            if state['current_item']['question'].get('audio_url'):
                state = self.action(state, 'listened')
            state = self.action(state, 'answer', choice_id=self.correct(state))
            state = self.action(state, 'next')
        course = course_snapshot(self.conn, self.pid)
        chapter = course['chapters'][0]
        self.assertEqual(course['preparation_policy'], 'activity-or-target-practice-v1')
        self.assertEqual((chapter['status'], chapter['progress']), ('ready', 1))
        self.assertEqual(chapter['preparation_basis'], 'target_practice')
        self.assertEqual((chapter['activity_preparation_progress'], chapter['target_preparation_progress']), (0, 1))
        self.assertTrue(all(t['prepared'] and not t['demonstrated'] for t in chapter['target_coverage']['targets']))
        self.assertEqual(course['completed_milestones'], 0)
        self.assertEqual(course['assessment_scope'], 'journey_checkpoint')
        self.assertFalse(course['awards_proficiency_level'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_evidence').fetchone()[0], 0)
        attempt = checkpoint_start(self.conn, self.pid, 'home', 'normal-after-target-practice')
        frozen = json.loads(self.conn.execute('SELECT frozen_json FROM course_checkpoint_attempts WHERE id=?', (attempt['id'],)).fetchone()[0])
        self.assertEqual(frozen['preparation_policy'], course['preparation_policy'])

    def step(self,wrong=False,hint=False,quote='Где парк?'):
        seed,raw=self.conn.execute("SELECT id,payload_json FROM speaking_scenario_variants WHERE id='directions-a1-park-v2'").fetchone()
        turns=[{'id':'turn-1','npc':{'russian':'Здравствуйте!','english':'Hello!'},'options':[{'id':'a','russian':'Где парк?','correct':True},{'id':'b','russian':'Спасибо!','correct':False}]}]
        dialogue={'turns':turns,'coverage':[{'requirement_id':'objective-1','turn':1,'role':'learner','quote':quote}]}
        sid='step-'+str(self.serial);self.serial+=1
        self.conn.execute('''INSERT INTO step_conversation_sessions
            (id,profile_id,start_key,request_hash,scenario_id,variant_id,scenario_json,target_level,language,voice_id,state,created_at,dialogue_json,progress_json)
            VALUES (?,?,?,'test','directions',?,?,'A1','en','test','completed',?,?,?)''',
            (sid,self.pid,sid,seed,raw,self.now,encoded(dialogue),encoded({'turn-1':{'answered':True,'hint_used':hint}})))
        if wrong:self.conn.execute('INSERT INTO step_conversation_answers VALUES (?,?,?,?,0,?)',(sid,'wrong','turn-1','b',self.now))
        self.conn.execute('INSERT INTO step_conversation_answers VALUES (?,?,?,?,1,?)',(sid,'correct','turn-1','a',self.now))
        award(self.conn,self.pid,activity='speaking_step',content_key=seed,source_key=sid,title='Speaking',target_level='A1',now=self.now)
        return sid

    def test_guided_speaking_quotes_selected_answer_and_reverses_without_claiming_speech(self):
        sid=self.step();rows=self.conn.execute('SELECT * FROM course_target_observations').fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['target_id'],rows[0]['response_mode'],rows[0]['demonstrated']),('a1.places.ask-location.read','reading_selection',1))
        self.assertEqual(target_coverage(self.conn,self.pid,'leavingtown')['prepared_count'],1)
        event=self.conn.execute('SELECT id FROM progression_events WHERE source_key=?',(sid,)).fetchone()[0]
        self.assertEqual(record_event_targets(self.conn,self.pid,event,self.now),0)
        self.assertEqual(record_event_targets(self.conn,'other',event,self.now),0)
        reverse(self.conn,self.pid,'speaking_step',sid)
        self.assertEqual(target_coverage(self.conn,self.pid,'leavingtown')['prepared_count'],0)

    def test_guided_speaking_preserves_first_error_and_correction(self):
        self.step(wrong=True,hint=True)
        row=self.conn.execute('SELECT * FROM course_target_observations').fetchone()
        self.assertEqual(json.loads(row['first_response_json'])['choice_id'],'b')
        self.assertEqual(json.loads(row['response_json'])['choice_id'],'a')
        self.assertEqual((row['demonstrated'],row['needs_practice']),(0,1))
        self.assertEqual(json.loads(row['support_json']),{'hint':True,'prior_incorrect':True})

    def live_report(self, quote='Можно суп и чай, пожалуйста?', uncertain=False):
        raw=self.conn.execute("SELECT payload_json FROM speaking_scenario_variants WHERE id='cafe-a1-warm-lunch-v2'").fetchone()[0]
        self.conn.execute("""INSERT INTO live_conversation_sessions
          (id,profile_id,start_key,scenario_json,language,model,backend_model,voice,state,created_at,heartbeat_at,target_level)
          VALUES ('live',?,'live',?,'en','test','test','test','ended',?,?,'A1')""",(self.pid,raw,self.now,self.now))
        report={'basis':'audio_review','rubric_version':'speaking-audio-v1','speech_status':'insufficient',
                'transcript':'Можно суп и чай, пожалуйста?','uncertain_phrases':[quote] if uncertain else [],
                'grammar':{'score':None},'fluency':{'score':None},
                'goals':[{'id':'objective-1','status':'completed','evidence':[quote]},
                         {'id':'objective-2','status':'not_yet','evidence':[]}]}
        self.conn.execute("INSERT INTO speaking_reviews(session_id,state,report_json,created_at,updated_at) VALUES ('live','ready',?,?,?)",(encoded(report),self.now,self.now))

    def test_short_spoken_goal_survives_null_grammar_without_claiming_independence(self):
        self.live_report()
        self.assertEqual(record_speaking_targets(self.conn,self.pid,'live'),1)
        self.assertEqual(record_speaking_targets(self.conn,self.pid,'live'),0)
        self.assertEqual(record_speaking_targets(self.conn,'other','live'),0)
        row=self.conn.execute('SELECT * FROM course_target_observations').fetchone()
        self.assertEqual(row['target_id'],'a1.food.make-request.speak')
        self.assertEqual((row['introduced'],row['practised'],row['demonstrated'],row['score']),(0,1,0,1))
        self.assertTrue(json.loads(row['support_json'])['independence_unverified'])
        self.assertEqual(target_coverage(self.conn,self.pid,'market')['prepared_count'],0)

    def test_uncertain_spoken_goal_is_not_an_observation(self):
        self.live_report(uncertain=True)
        self.assertEqual(record_speaking_targets(self.conn,self.pid,'live'),0)

    def test_invented_spoken_quote_is_not_an_observation(self):
        self.live_report(quote='Я хочу кофе.')
        self.assertEqual(record_speaking_targets(self.conn,self.pid,'live'),0)

    def test_first_steps_maps_only_saved_relevant_decisions(self):
        authored=json.loads((Path(__file__).resolve().parents[1]/'data'/'first_steps.json').read_text())
        lesson=next(item for item in authored['lessons'] if item['id']=='set-off')
        frozen=lesson|{'chapter_id':'first-steps','version':authored['version']}
        answers={q['id']:{'answer':q['answer'],'correct':True,'hint_used':False} for q in lesson['questions']}
        self.conn.execute("""INSERT INTO first_steps_attempts
          (id,profile_id,chapter_id,lesson_id,version,content_json,learned_json,answers_json,completed_at,created_at,updated_at)
          VALUES ('intro',?,'first-steps','set-off',?,?,?,?,?,?,?)""",
          (self.pid,authored['version'],encoded(frozen),encoded([item['id'] for item in lesson['teaching']]),encoded(answers),self.now,self.now,self.now))
        award(self.conn,self.pid,activity='first_steps',content_key='first-steps:set-off:'+authored['version'],source_key='intro',title='First steps',target_level='A1')
        rows=self.conn.execute('SELECT target_id,introduced,practised,demonstrated FROM course_target_observations').fetchall()
        self.assertEqual({r[0] for r in rows},{'a1.greetings.polite-greeting.read','a1.places.follow-directions.read'})
        self.assertTrue(all(tuple(r[1:])==(1,1,0) for r in rows))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0],0)

    def test_nonmatching_quote_creates_no_evidence(self):
        self.step(quote='Когда автобус?')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0],0)


class TargetMigrationTests(unittest.TestCase):
    def test_populated_045_upgrade_does_not_rewrite_or_infer_old_evidence(self):
        import migrations
        import shutil
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);scripts=root/'migrations';scripts.mkdir();db=str(root/'saved.db')
            for path in migrations.MIGRATION_DIR.glob('*.sql'):
                if int(path.name.split('_')[0])<=45:shutil.copy(path,scripts/path.name)
            with patch.object(migrations,'MIGRATION_DIR',scripts):
                self.assertEqual(upgrade_database(db,backup=False),(45,None))
            with sqlite3.connect(db) as conn:
                pid=personal_profile(conn)
                conn.execute("INSERT INTO progression_events VALUES ('past',?,'writing','old-check','old-task','Old work','activity','A1','{}',1,NULL)",(pid,))
                conn.execute("INSERT INTO course_evidence VALUES ('past',?,'home','writing','old-task','A1',1,'a1-course-practice-v1',1)",(pid,))
                tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
                before={t:conn.execute('SELECT * FROM '+t).fetchall() for t in tables}
            shutil.copy(migrations.MIGRATION_DIR/'046_course_targets.sql',scripts/'046_course_targets.sql')
            with patch.object(migrations,'MIGRATION_DIR',scripts):
                self.assertEqual(upgrade_database(db,backup=False),(46,None))
                self.assertEqual(upgrade_database(db,backup=False),(46,None))
            with sqlite3.connect(db) as conn:
                for table,rows in before.items():
                    with self.subTest(table=table):self.assertEqual(conn.execute('SELECT * FROM '+table).fetchall(),rows)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0],0)
                self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')


if __name__=='__main__':unittest.main()
