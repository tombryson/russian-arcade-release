"""Diagnostic reports use owned saved tasks and responses, without progression."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from contracts.curriculum import freeze_task_contract
from migrations import upgrade_database
from services import activity_evidence as evidence
from services.account_import import ImportConflict, transform
from tests.test_curriculum_task_contracts import spec_for, report_for


class ActivityEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'test.db'; upgrade_database(path, backup=False)
        self.conn = sqlite3.connect(path); self.addCleanup(self.conn.close)
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute("INSERT INTO learning_profiles(id,display_name,avatar,study_timezone,created_at) VALUES ('other','Other','O','UTC',1)")
        self.conn.execute("INSERT INTO writing_exercises(id,topic,difficulty,task,required_words,min_words,created_at,owner_profile_id) VALUES (1,'home','A1','Describe where Barsik is.','[]',0,'2026-09-23','personal-learning')")
        self.conn.execute("INSERT INTO writing_exercises(id,topic,difficulty,task,required_words,min_words,created_at,owner_profile_id) VALUES (2,'home','A1','Another writing task.','[]',0,'2026-09-23','other')")
        spec = spec_for('a1.writing.personal-message')
        spec.update(activity='writing', content={'task':'Describe where Barsik is.','required_words':[]})
        self.writing = freeze_task_contract(spec)
        self.item = {'id':'location','type':'choice','prompt':'Где Барсик?',
                     'choices':[{'id':'a','text':'В школе.'},{'id':'b','text':'В школу.'}], 'answer':'a','hint':'Where he is.'}
        pack = {'schema_version':1,'id':'curriculum-unit:location-destination-v1','kind':'activity','title':'Location','source':'test','items':[self.item]}
        self.conn.execute('INSERT INTO learning_content VALUES (?,\'activity\',1)', (pack['id'],))
        self.conn.execute("INSERT INTO learning_content_versions(id,content_id,version,title,payload,status,source,created_at,approved_by,approved_at) VALUES ('unit-version',?,1,'Location',?,'published','test',1,'author',1)", (pack['id'],json.dumps(pack)))
        self.conn.execute("INSERT INTO learning_sessions(id,profile_id,version_id,kind,start_key,start_hash,start_result,created_at,updated_at) VALUES ('session','personal-learning','unit-version','activity','start','hash','{}',1,1)")
        spec = spec_for();spec.update(activity='curriculum_unit',content={'item':self.item,'explanation':'Location.','unit_id':'location-destination-v1'})
        self.unit = freeze_task_contract(spec)
        self.conn.commit()

    def writing_attempt(self, key=1, text='В школе.'):
        self.conn.execute("INSERT INTO writing_attempts(id,exercise_id,response,score,score_max,source) VALUES (?,1,?,8,10,'writing-v1')", (key,text))

    def unit_attempt(self, key='answer', choice='a', assisted=0):
        self.conn.execute("INSERT INTO activity_attempts(id,session_id,item_id,submission_id,answer,assisted,outcome,policy_version,created_at) VALUES (?,'session','location',?,?,?,?, 'test',1)",
                          (key,key,json.dumps({'choice_id':choice}),assisted,'correct' if choice=='a' else 'incorrect'))

    def test_writing_contract_and_report_are_owned_and_idempotent(self):
        key=evidence.save_contract(self.conn,'personal-learning','writing','1',self.writing)
        self.assertEqual(evidence.save_contract(self.conn,'personal-learning','writing','1',self.writing),key)
        with self.assertRaises(LookupError):evidence.load_contract(self.conn,'other','writing','1')
        self.writing_attempt();report=report_for(self.writing)
        saved=evidence.save_report(self.conn,'personal-learning','writing','1','1',report,response_text='В школе.')
        self.assertEqual(evidence.save_report(self.conn,'personal-learning','writing','1','1',report,response_text='В школе.'),saved)
        self.assertEqual(len(evidence.reports_for_task(self.conn,'personal-learning','writing','1')),1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_target_observations').fetchone()[0],0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM course_chapter_passes').fetchone()[0],0)

    def test_contract_cannot_be_replaced_or_attached_after_assessment(self):
        evidence.save_contract(self.conn,'personal-learning','writing','1',self.writing)
        spec={k:v for k,v in self.writing.items() if not k.endswith('sha256')}
        spec['criteria'][0]['expectation']='A changed criterion.'
        with self.assertRaisesRegex(ValueError,'cannot be replaced'):
            evidence.save_contract(self.conn,'personal-learning','writing','1',freeze_task_contract(spec))
        self.unit_attempt()
        with self.assertRaisesRegex(ValueError,'before the first'):
            evidence.save_contract(self.conn,'personal-learning','curriculum_unit','session:location',self.unit)


    def test_writing_cannot_attach_contract_after_first_assessment(self):
        self.writing_attempt()
        with self.assertRaisesRegex(ValueError, 'before the first'):
            evidence.save_contract(self.conn, 'personal-learning', 'writing', '1', self.writing)

    def test_fabricated_source_response_and_replacement_are_rejected(self):
        evidence.save_contract(self.conn,'personal-learning','writing','1',self.writing)
        report=report_for(self.writing)
        with self.assertRaises(ValueError):evidence.save_report(self.conn,'personal-learning','writing','1','99',report,response_text='В школе.')
        self.writing_attempt()
        with self.assertRaisesRegex(ValueError,'exact saved response'):
            evidence.save_report(self.conn,'personal-learning','writing','1','1',report,response_text='Invented')
        evidence.save_report(self.conn,'personal-learning','writing','1','1',report,response_text='В школе.')
        changed=deepcopy(report);changed['judgements'][0]['feedback']='Replacement'
        with self.assertRaisesRegex(ValueError,'different criterion report'):
            evidence.save_report(self.conn,'personal-learning','writing','1','1',changed,response_text='В школе.')
        with self.assertRaises(LookupError):evidence.save_report(self.conn,'other','writing','1','1',report,response_text='В школе.')

    def test_unit_uses_exact_issued_item_and_choice_text(self):
        altered=deepcopy(self.unit);spec={k:v for k,v in altered.items() if not k.endswith('sha256')}
        spec['content']['item']['answer']='b'
        with self.assertRaisesRegex(ValueError,'exact saved item'):
            evidence.save_contract(self.conn,'personal-learning','curriculum_unit','session:location',freeze_task_contract(spec))
        evidence.save_contract(self.conn,'personal-learning','curriculum_unit','session:location',self.unit)
        self.unit_attempt();report=report_for(self.unit)
        evidence.save_report(self.conn,'personal-learning','curriculum_unit','session:location','answer',report,response_text='В школе.')
        with self.assertRaises(ValueError):evidence.save_report(self.conn,'personal-learning','curriculum_unit','session:location','unknown',report,response_text='В школе.')
        with self.assertRaises(LookupError):evidence.load_contract(self.conn,'other','curriculum_unit','session:location')

    def test_unit_cannot_hide_hint_or_upgrade_wrong_answer(self):
        evidence.save_contract(self.conn,'personal-learning','curriculum_unit','session:location',self.unit)
        self.unit_attempt(choice='b',assisted=1);report=report_for(self.unit,'В школу.')
        with self.assertRaisesRegex(ValueError,'Support must match'):
            evidence.save_report(self.conn,'personal-learning','curriculum_unit','session:location','answer',report,response_text='В школу.')
        with self.assertRaisesRegex(ValueError,'deterministic'):
            evidence.save_report(self.conn,'personal-learning','curriculum_unit','session:location','answer',report,response_text='В школу.',support=['hint'])
        report['judgements'][0].update(outcome='not_satisfied',score=0)
        evidence.save_report(self.conn,'personal-learning','curriculum_unit','session:location','answer',report,response_text='В школу.',support=['hint'])
        before=self.conn.total_changes;evidence.validate_saved_evidence(self.conn)
        self.assertEqual(self.conn.total_changes,before)

    def test_import_typed_identity_mapping_preserves_contract_bytes(self):
        row={'id':'contract','profile_id':'personal-learning','activity':'writing','task_key':'1','contract_json':json.dumps(self.writing),'contract_sha256':self.writing['contract_sha256'],'created_at':1}
        table={'pk':['id'],'foreign':[],'rows':[row]}
        mapped=transform('activity_task_contracts',table,row,{'writing_exercises':{1:9}}, {'activity_task_contracts':table})
        self.assertEqual(mapped['task_key'],'9');self.assertEqual(mapped['contract_json'],row['contract_json'])
        report={'id':'report','contract_id':'contract','profile_id':'personal-learning','source_key':'3','report_json':'{}'}
        remapped=transform('activity_criterion_reports',{'pk':['id'],'foreign':[]},report,{'writing_attempts':{3:8}},{'activity_task_contracts':table})
        self.assertEqual(remapped['source_key'],'8')
        unsafe=deepcopy(row);payload=json.loads(unsafe['contract_json']);payload['content']['exercise_id']=1;unsafe['contract_json']=json.dumps(payload)
        with self.assertRaisesRegex(ImportConflict,'Frozen activity evidence'):
            transform('activity_task_contracts',table,unsafe,{'writing_exercises':{1:9}},{'activity_task_contracts':table})
