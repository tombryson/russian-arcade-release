"""Shared coins and route state against real, isolated SQLite transactions."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from migrations import MIGRATION_DIR, upgrade_database
from repositories.learning_repository import transaction, timestamp
from services.progression import award, reverse, snapshot, personal_profile, award_speaking, study_day
from tests.support import isolated_app, latest_schema_version


class ProgressionTests(unittest.TestCase):
    def setUp(self):
        self.app = isolated_app(self)
        self.db = self.app.config['DB_PATH']
        self.client = self.app.test_client()
        data = self.client.get('/api/v1/progression').json
        self.pid, self.token = data['profile_id'], data['csrf_token']

    def post(self, path, data):
        return self.client.post('/api/v1/'+path,json=data,headers={'X-CSRF-Token':self.token})

    def earn(self, source, content=None, category='activity', now=None):
        with transaction(self.db,write=True) as conn:
            return award(conn,self.pid,activity='test',source_key=source,content_key=content or source,
                         title='Test practice',category=category,now=now)

    def state(self):
        return self.client.get('/api/v1/progression').json

    def test_views_never_award_and_levels_are_preferences_not_access(self):
        for _ in range(3):
            self.client.get('/api/v1/journey/post-office')
            self.client.get('/api/v1/live-conversations/scenarios?level=A2')
        self.assertEqual(self.state()['balance'],0)
        self.assertEqual(self.post('progression/preferences',{'level':'B2'}).json['preferred_level'],'B2')
        self.assertEqual(self.client.get('/api/v1/live-conversations/scenarios?level=A1').status_code,200)
        self.assertEqual(self.post('progression/preferences',{'level':'expert'}).status_code,400)
        self.assertEqual(self.client.post('/api/v1/progression/preferences',json={'level':'A1'}).status_code,403)
        self.assertEqual(self.state()['skill']['status'],'not_calibrated')
        self.assertTrue(all(item['rating'] is None for item in self.state()['skill']['skills']))

    def test_concurrent_retry_and_shared_daily_cap(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            values=list(pool.map(self.earn,['same']*6))
        self.assertEqual(sum(values),3)
        with ThreadPoolExecutor(max_workers=6) as pool:
            values=list(pool.map(self.earn,[str(i) for i in range(10)]))
        self.assertEqual(sum(values),9)
        self.assertEqual(self.earn('review',category='review'),1)
        self.assertEqual(self.state()['balance'],13)

    def test_same_content_once_per_local_day_and_undo_reclaim(self):
        now=timestamp()
        self.assertEqual(self.earn('r1','card','review',now),1)
        self.assertEqual(self.earn('r2','card','review',now),0)
        with transaction(self.db,write=True) as conn:
            self.assertEqual(reverse(conn,self.pid,'test','r1',now),-1)
            self.assertEqual(reverse(conn,self.pid,'test','r1',now),0)
        self.assertEqual(self.earn('r3','card','review',now),1)
        self.assertEqual(self.earn('r4','card','review',now+86400),1)
        self.assertEqual(self.state()['balance'],2)

    def test_completion_and_earnings_unlock_a_permanent_destination(self):
        self.assertEqual(self.client.get('/api/v1/journey/market-town').status_code,403)
        result=self.post('journey/post-office/answer',{'answer':'market','submission_id':'first'}).json
        self.assertTrue(result['scene']['completed'])
        self.assertEqual(result['coins_earned'],3)
        for i in range(9): self.earn('review'+str(i),category='review')
        self.assertTrue(self.state()['journey']['worlds'][1]['unlocked'])
        with transaction(self.db,write=True) as conn:
            reverse(conn,self.pid,'test','review8')
        self.assertEqual(self.state()['earned_total'],11)
        self.assertTrue(self.state()['journey']['worlds'][1]['unlocked'])
        self.assertEqual(self.client.get('/api/v1/journey/market-town').status_code,200)

    def test_scene_retries_are_idempotent_and_wrong_answers_allow_learning(self):
        data={'answer':'forest','submission_id':'wrong'}
        first=self.post('journey/post-office/answer',data)
        self.assertEqual(first.json,self.post('journey/post-office/answer',data).json)
        self.assertFalse(first.json['scene']['completed'])
        self.assertEqual(first.json['coins_earned'],3)
        self.assertNotIn('answer',first.json['scene'])
        self.assertEqual(self.post('journey/post-office/answer',{'answer':'market','submission_id':'wrong'}).status_code,409)
        self.assertEqual(self.post('journey/post-office/answer',{'answer':'invalid','submission_id':'invalid'}).status_code,400)
        fixed=self.post('journey/post-office/answer',{'answer':'market','submission_id':'fixed'}).json
        self.assertTrue(fixed['scene']['completed']);self.assertEqual(fixed['coins_earned'],0)
        self.assertEqual(self.client.get('/api/v1/journey/missing').status_code,404)

    def test_wallet_is_profile_scoped_and_append_only(self):
        self.earn('one')
        with transaction(self.db,write=True) as conn:
            conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','cat','UTC',?)",(timestamp(),))
            self.assertEqual(snapshot(conn,'other')['balance'],0)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('DELETE FROM progression_entries')
            self.assertEqual(snapshot(conn,self.pid)['balance'],3)

    def test_failed_attempt_transaction_cannot_leave_a_reward(self):
        with self.assertRaises(ValueError):
            with transaction(self.db,write=True) as conn:
                award(conn,self.pid,activity='writing',content_key='task',source_key='attempt',title='Writing')
                raise ValueError('The attempt could not save')
        self.assertEqual(self.state()['balance'],0)

    def test_speaking_rewards_participation_not_high_scores_or_english(self):
        session={'id':'call','profile_id':self.pid,'created_at':timestamp()+1,'scenario_json':json.dumps({'seed':'test','title':'At the café','target_level':'A1'})}
        english={'speech_status':'no_russian','transcript':'I want some tea please'}
        russian={'speech_status':'russian','transcript':'Мне чай пожалуйста','grammar':{'score':None},'fluency':{'score':None},'goals':[{'status':'completed','evidence':['Мне чай пожалуйста']}]}
        with transaction(self.db,write=True) as conn:
            self.assertEqual(award_speaking(conn,session,english),0)
            self.assertEqual(award_speaking(conn,session,russian),3)
            self.assertEqual(award_speaking(conn,session,russian),0)
            self.assertEqual(award_speaking(conn,{**session,'id':'old','created_at':1},russian),0)

    def test_delayed_speaking_feedback_uses_the_day_of_the_conversation(self):
        now=timestamp();ended=now-86400
        session={'id':'first-call','profile_id':self.pid,'created_at':ended-60,'ended_at':ended,
                 'scenario_json':json.dumps({'seed':'same-variant','title':'At the café','target_level':'A1'})}
        report={'speech_status':'russian','transcript':'Мне чай пожалуйста','goals':[{'status':'completed','evidence':['Мне чай пожалуйста']}]}
        with transaction(self.db,write=True) as conn:
            conn.execute("UPDATE progression_settings SET value='0' WHERE key='activated_at'")
            self.assertEqual(award_speaking(conn,session,report),3)
            with patch('services.progression.timestamp',return_value=now+86400):
                self.assertEqual(award_speaking(conn,{**session,'id':'second-call'},report),0)
            self.assertEqual(conn.execute('SELECT study_day FROM progression_entries').fetchone()[0],study_day(conn,self.pid,ended))


class ProgressionMigrationTests(unittest.TestCase):
    def test_import_preserves_legacy_balance_without_unlocking_or_regrading(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'migrations';old.mkdir();db=str(root/'vocab.db')
            for file in MIGRATION_DIR.glob('*.sql'):
                if int(file.name[:3])<=22:shutil.copy2(file,old/file.name)
            with patch('migrations.MIGRATION_DIR',old):upgrade_database(db,backup=False)
            with sqlite3.connect(db) as conn:
                conn.execute('UPDATE users SET lingocoins=730,elo_rating=1583 WHERE user_id=1')
                pid=personal_profile(conn);now=timestamp();day=study_day(conn,pid,now)
                conn.execute("INSERT INTO learning_sessions(id,profile_id,kind,start_key,start_hash,start_result,created_at,updated_at) VALUES ('old-session',?,'review','old-key','hash','{}',?,?)",(pid,now,now))
                conn.execute("INSERT INTO activity_attempts VALUES ('old-attempt','old-session','old-item','old-submit','{}',0,'correct','old-policy',?)",(now,))
                conn.execute("INSERT INTO learning_reward_entries VALUES ('old-reward',?,'old-attempt',?,?,3,'activity','old-policy',?)",(pid,'activity:old-content:'+day,day,now))
            self.assertEqual(upgrade_database(db,backup=False)[0],latest_schema_version())
            with transaction(db) as conn:
                state=snapshot(conn,'personal-learning')
                self.assertEqual((state['balance'],state['legacy_balance'],state['earned_total']),(733,730,3))
                self.assertFalse(state['journey']['worlds'][1]['unlocked'])
                self.assertEqual(tuple(conn.execute('SELECT lingocoins,elo_rating FROM users').fetchone()),(730,1583))
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM progression_events').fetchone()[0],0)
            upgrade_database(db,backup=False)
            with transaction(db,write=True) as conn:
                self.assertEqual(snapshot(conn,'personal-learning')['balance'],733)
                self.assertEqual(award(conn,pid,activity='activity',content_key='old-content',source_key='new-attempt',title='Existing activity',now=now),0)


class NativeRewardIntegrationTests(unittest.TestCase):
    # Reuse the real review fixture without rerunning its entire suite here.
    from tests.test_native_flashcards import NativeFlashcardTests as Fixture
    setUp=Fixture.setUp
    post=Fixture.post
    unlock=Fixture.unlock
    learner=Fixture.learner
    credential=staticmethod(Fixture.credential)
    publish=Fixture.publish
    begin=Fixture.begin
    move=Fixture.move

    def test_rating_undo_rerating_rewards_once_and_keeps_fsrs_independent(self):
        self.publish();client,pid=self.learner();saved=self.begin(client,pid)
        saved=self.move(client,saved,'reveal')
        saved=self.move(client,saved,'reviews',rating='again')
        self.assertEqual(client.get('/api/v1/progression').json['balance'],1)
        saved=self.move(client,saved,'undo')
        self.assertEqual(client.get('/api/v1/progression').json['balance'],0)
        saved=self.move(client,saved,'reviews',rating='easy')
        self.assertEqual(client.get('/api/v1/progression').json['balance'],1)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM review_events').fetchone()[0],2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM review_reversals').fetchone()[0],1)


if __name__=='__main__':unittest.main()
