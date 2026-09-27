"""Writing persistence, migration safety, provider contracts and learner-facing routes."""
from tests.support import latest_schema_version
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import httpx
import openai
from migrations import upgrade_database
from repositories.writing_repository import WritingRepository, word_count
from services.writing_service import WritingService, WritingUnavailable
from tests.support import isolated_app, strip_progression_and_levels
from tests.test_activity_cleanup import Document

TASK = dict(title='Мой город',title_en='My town',task='Опишите ваш город.',task_en='Describe your town.',required_words=['город','парк','дом'])
ADVICE = dict(score=8,strength='Your ideas are clear.',next_step='Add one detail about the park.',example='В парке много деревьев.')


class WritingCleanupTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock(spec=WritingService)
        self.service.generate_writing_task.return_value = TASK
        self.service.assess_writing.return_value = ADVICE
        self.app = isolated_app(self,{'WritingService':self.service})
        self.client = self.app.test_client()
        # These exercise behavior tests submit as the explicitly selected learner.
        self.client.environ_base['HTTP_X_CSRF_TOKEN'] = self.client.get('/api/v1/user-session').json['csrf_token']
        self.repo = WritingRepository(self.app.config['DB_PATH'])
        self.id = self.repo.create(TASK,'city','beginner',30)
        self.url = f'/writing/load/{self.id}'
        self.headers = {'Accept':'application/json'}

    def submit(self,kind='save',text='Мой город красивый.',revision=0,headers=None,**extra):
        return self.client.post('/writing/'+kind,data=dict(exercise_id=self.id,user_response=text,revision=revision,**extra),headers=self.headers if headers is None else headers)

    def test_direct_and_partial_navigation_use_titles_instructions_and_preserved_drafts(self):
        text = 'Мой город.\n«Привет!» </textarea><script>bad()</script>'
        self.assertEqual(self.submit(text=text).status_code,200)
        for headers in ({},{'HX-Request':'true','HX-Target':'mainContent'},{'HX-Request':'true','HX-Target':'writing-content'}):
            html = self.client.get(self.url,headers=headers).get_data(as_text=True)
            document = Document(html)
            self.assertEqual(document.answers['user-response'],text)
            ids = [attrs['id'] for _,attrs in document.elements if 'id' in attrs]
            self.assertEqual(len(ids),len(set(ids)))
            self.assertIn('Describe your town.',html)
            self.assertNotIn('<script>bad()',html)
            self.assertNotIn('name="task"',html)
            self.assertEqual('<!DOCTYPE html>' in html,not headers)
        self.service.assess_writing.assert_not_called()
        self.assertEqual(len(self.repo.list_saved()),1)
        self.assertEqual(self.repo.load(self.id)['attempts'],[])

    def test_checks_use_saved_task_and_append_full_versions_without_rewards(self):
        text = '  «Мой город — чудесный!»\n' + 'Здесь есть парк. '*400
        result = self.submit('assess',text,task='forged',required_words='forged',min_words=1,score=10,difficulty='advanced')
        self.assertEqual(result.status_code,200)
        payload = self.service.assess_writing.call_args.kwargs
        self.assertEqual(payload['task'],TASK['task'])
        self.assertEqual(payload['required_words'],TASK['required_words'])
        self.assertEqual(payload['response'],text)
        self.assertEqual((payload['min_words'],payload['difficulty']),(30,'beginner'))
        self.assertEqual(self.submit('assess','Новая версия.',1).status_code,200)
        self.assertEqual(self.submit('save','Поздний черновик.',2).status_code,200)
        current = self.repo.load(self.id)
        self.assertEqual(current['draft'],'Поздний черновик.')
        self.assertEqual([item['response'] for item in current['attempts']],['Новая версия.',text])
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM reward_events').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT user_response FROM writing_exercises WHERE id=?',(self.id,)).fetchone()[0],'')

    def test_short_drafts_can_be_checked_blank_drafts_can_be_saved(self):
        self.assertEqual(self.submit('assess','Дом.').status_code,200)
        self.assertEqual(self.submit('save','',1).status_code,200)
        self.assertEqual(self.submit('assess',' ',2).status_code,400)
        self.assertEqual(self.submit('save','Я'*20001,2).status_code,400)
        self.assertEqual(self.service.assess_writing.call_count,1)

    def test_failed_assessment_retains_editor_without_fabricated_grade(self):
        self.submit(text='Сохранённый черновик.')
        self.service.assess_writing.side_effect = WritingUnavailable('private diagnostics')
        for headers in (self.headers,{}):
            result = self.submit('assess','Ещё не сохранено.',1,headers=headers)
            self.assertEqual(result.status_code,503)
            self.assertNotIn('private diagnostics',result.get_data(as_text=True))
            if not headers:
                self.assertEqual(Document(result.get_data(as_text=True)).answers['user-response'],'Ещё не сохранено.')
        self.assertEqual(self.repo.load(self.id)['draft'],'Сохранённый черновик.')
        self.assertEqual(self.repo.load(self.id)['attempts'],[])

    def test_atomic_check_failure_rolls_back_draft_and_attempt(self):
        self.submit(text='Первый черновик.')
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            conn.execute("CREATE TRIGGER fail_check BEFORE INSERT ON writing_attempts BEGIN SELECT RAISE(ABORT,'test failure'); END")
        self.assertEqual(self.submit('assess','Новая версия.',1).status_code,503)
        self.assertEqual(self.repo.load(self.id)['draft'],'Первый черновик.')
        self.assertEqual(self.repo.load(self.id)['revision'],1)

    def test_stale_tabs_and_in_flight_checks_do_not_overwrite(self):
        self.submit(text='Первый черновик.')
        self.assertEqual(self.submit('assess',revision=0).status_code,409)
        self.service.assess_writing.assert_not_called()
        def race(**kwargs):
            self.repo.save(self.id,'Из другой вкладки.',1)
            return ADVICE
        self.service.assess_writing.side_effect = race
        self.assertEqual(self.submit('assess',revision=1).status_code,409)
        self.assertEqual(self.repo.load(self.id)['draft'],'Из другой вкладки.')
        self.assertEqual(self.repo.load(self.id)['attempts'],[])

    def test_generation_saves_bilingual_task_before_navigation_and_failure_keeps_setup(self):
        result = self.client.post('/writing/generate',data=dict(topic='family',difficulty='intermediate',target_words=30),headers=self.headers)
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get(result.json['url']).status_code,200)
        self.assertEqual(len(self.repo.list_saved()),2)
        self.service.generate_writing_task.assert_called_once_with('family','intermediate',30)
        self.service.generate_writing_task.side_effect = WritingUnavailable('private diagnostics')
        result = self.client.post('/writing/generate',data=dict(topic='family',difficulty='advanced',target_words=100))
        self.assertEqual(result.status_code,503)
        self.assertIn('value="B1" selected',result.get_data(as_text=True))
        self.assertIn('value="100" checked',result.get_data(as_text=True))
        self.assertEqual(len(self.repo.list_saved()),2)

    def test_generation_validation_and_obsolete_payloads_do_not_write(self):
        for data in [dict(target_words=0),dict(target_words='invalid'),dict(difficulty='fake'),dict(topic=' '*2)]:
            self.assertEqual(self.client.post('/writing/generate',data=data,headers=self.headers).status_code,400)
        self.service.generate_writing_task.assert_not_called()
        self.assertEqual(self.client.post('/writing/save',data=dict(task='fake',response='ответ')).status_code,404)
        self.assertEqual(self.client.get('/writing/load/99999').status_code,404)

    def test_language_switch_uses_bilingual_titles_and_feedback_language(self):
        english = self.client.get('/writing').get_data(as_text=True)
        self.assertIn('My town',english)
        self.assertNotIn('1: city',english)
        with self.client.session_transaction() as session:
            session['ui_lang']='ru'
        html = self.client.get(self.url).get_data(as_text=True)
        self.assertIn('Мой город',html)
        self.assertIn('Опишите ваш город.',html)
        self.assertNotIn('Describe your town.',html)
        self.submit('assess')
        self.assertEqual(self.service.assess_writing.call_args.kwargs['language'],'ru')
        self.assertEqual(self.repo.load(self.id)['attempts'][0]['ui_language'],'ru')

    def test_migration_preserves_legacy_answers_feedback_and_unknown_dates(self):
        db = self.app.config['DB_PATH']
        with sqlite3.connect(db) as conn:
            conn.execute('DELETE FROM writing_details')
            # Remove the later region extension when constructing an older schema.
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
            conn.execute('DELETE FROM schema_migrations WHERE version>=8')
            conn.execute('UPDATE writing_exercises SET user_response=?,score=95,feedback=? WHERE id=?',('  «Ответ»\n','Старый отзыв',self.id))
            before = conn.execute('SELECT * FROM writing_exercises').fetchall()
        version,backup = upgrade_database(db)
        self.assertEqual(version,latest_schema_version())
        current = self.repo.load(self.id)
        self.assertEqual(current['draft'],'  «Ответ»\n')
        self.assertIsNone(current['draft_saved_at'])
        self.assertEqual(current['attempts'][0]['feedback'],'Старый отзыв')
        self.assertIsNone(current['attempts'][0]['score_max'])
        self.assertIsNone(current['attempts'][0]['created_at'])
        self.assertNotIn('95/10',self.client.get(self.url).get_data(as_text=True))
        with sqlite3.connect(db) as conn,sqlite3.connect(backup) as snapshot:
            self.assertEqual([row[:-1] for row in conn.execute('SELECT * FROM writing_exercises')],before)
            self.assertEqual(conn.execute('SELECT DISTINCT owner_profile_id FROM writing_exercises').fetchall(), [('personal-learning',)])
            self.assertEqual(snapshot.execute('SELECT * FROM writing_exercises').fetchall(),before)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone(),('ok',))
            # Remove the later region extension when constructing an older schema.
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
            conn.execute('DELETE FROM schema_migrations WHERE version>=8')
        upgrade_database(db)
        self.assertEqual(len(self.repo.load(self.id)['attempts']),1)

    def test_legacy_escaped_word_display_does_not_rewrite_storage(self):
        with sqlite3.connect(self.app.config['DB_PATH']) as conn:
            conn.execute('UPDATE writing_exercises SET required_words=? WHERE id=?',(json.dumps([r'\u0434\u043e\u043c']),self.id))
        self.assertEqual(self.repo.load(self.id)['required_words'],['дом'])
        self.assertIn('data-insert-word="дом"',self.client.get(self.url).get_data(as_text=True))


class WritingProviderTests(unittest.TestCase):
    def setUp(self):
        self.service = WritingService.__new__(WritingService)
        self.service.client = Mock()

    def output(self,value,status='completed'):
        self.service.client.responses.create.return_value=SimpleNamespace(status=status,output_text=json.dumps(value))

    def test_invalid_feedback_and_refusals_are_not_scores(self):
        for value in [dict(ADVICE,score=-1),dict(ADVICE,score=True),dict(ADVICE,score=11),dict(ADVICE,next_step=''),[],{}]:
            self.output(value)
            with self.assertRaises(WritingUnavailable):
                self.service.assess_writing('Task',['дом'],30,'Дом.')
        self.output(ADVICE,status='incomplete')
        with self.assertRaises(WritingUnavailable):
            self.service.assess_writing('Task',['дом'],30,'Дом.')
        self.service.client.responses.create.return_value=SimpleNamespace(status='completed',output_text='')
        with self.assertRaises(WritingUnavailable):
            self.service.generate_writing_task('city','beginner')

    def test_generation_requires_titles_and_matching_word_count(self):
        for value in [dict(TASK,title_en=''),dict(TASK,required_words=['дом']),dict(TASK,task_en='')]:
            self.output(value)
            with self.assertRaises(WritingUnavailable):
                self.service.generate_writing_task('city','C1')
        self.output(TASK)
        self.assertEqual(self.service.generate_writing_task('city','C1'),TASK)

    def test_sdk_serializes_schema_and_complete_answer(self):
        captured=[]
        def handle(request):
            payload=json.loads(request.content);captured.append(payload)
            value=TASK if payload['text']['format']['name']=='writing_task' else ADVICE
            return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':0,'model':'gpt-5-mini','status':'completed','output':[
                {'id':'msg_test','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps(value),'annotations':[]}]}]})
        self.service.client=openai.OpenAI(api_key='test-only',http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        self.addCleanup(self.service.client.close)
        self.service.generate_writing_task('city','C1')
        answer='  «Привет!»\n'+'Это мой город. '*200
        self.service.assess_writing(TASK['task'],TASK['required_words'],30,answer,language='ru')
        self.assertEqual(json.loads(captured[1]['input'][1]['content'])['russian_answer'],answer)
        for payload in captured:
            self.assertTrue(payload['text']['format']['strict'])
            self.assertEqual(payload['reasoning'],{'effort':'low'})
            self.assertFalse(payload['store'])
            self.assertNotIn('temperature',payload)
        self.assertEqual(word_count('Привет, мир! Где-то дома. 42'),5)
