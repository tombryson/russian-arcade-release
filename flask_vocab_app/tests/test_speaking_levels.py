"""Authored practice targets, not proficiency-placement accuracy tests."""
from tests.support import latest_schema_version
import json
import sqlite3
import unittest

from migrations import upgrade_database
from repositories.learning_repository import transaction
from repositories.speaking_repository import catalogue, choose_variant
from services.conversation_policy import scenario_instructions
from services.speaking_assessment import _INSTRUCTIONS
from tests.support import isolated_app
from tests.test_conversation import FakeAI, FakeSpeech
from tests.test_live_conversation import FakeLive


class SpeakingLevelTests(unittest.TestCase):
    def setUp(self):
        self.provider, self.speech, self.ai = FakeLive(), FakeSpeech(), FakeAI()
        self.app = isolated_app(self, {'LiveVoiceProvider':self.provider,
                                     'SpeechProvider':self.speech,'ConversationAI':self.ai})
        self.db = self.app.config['DB_PATH']
        self.service = self.app.extensions['learning']['live_conversation']
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/v1/household').json['csrf_token']
        self.addCleanup(self.service.executor.shutdown, wait=True)
        self.addCleanup(self.service.reviews.executor.shutdown, wait=True)
        self.addCleanup(self.app.extensions['learning']['conversation'].executor.shutdown, wait=True)

    def post(self, **body):
        return self.client.post('/api/v1/live-conversations',json=body,
                                headers={'X-CSRF-Token':self.csrf})

    def preview(self, scenario='cafe', level='A1', **query):
        return self.client.get('/api/v1/live-conversations/options',
                               query_string={'scenario_id':scenario,'level':level,**query})

    def test_every_scenario_has_a1_and_a2_content_without_fabricated_higher_levels(self):
        expected_counts = {'A1':15,'A2':15,'B1':0,'B2':0}
        for level in expected_counts:
            response = self.client.get('/api/v1/live-conversations/scenarios',query_string={'level':level})
            self.assertEqual(response.status_code, 200, response.json)
            result = response.json
            self.assertEqual(result['selected_level'],level)
            self.assertEqual({row['id']:row['available_count'] for row in result['levels']},expected_counts)
            self.assertEqual(len(result['scenarios']),5)
            self.assertTrue(all(row['levels']==['A1','A2'] for row in result['scenarios']))
            self.assertTrue(all(row['available']==(level in ('A1','A2')) for row in result['scenarios']))
            self.assertEqual(sum(row['variant_count'] for row in result['scenarios']),expected_counts[level])
        self.assertEqual(self.provider.creates,[])
        self.assertEqual(self.speech.calls,[])
        self.assertEqual(self.ai.assessments,[])

    def test_each_a1_and_a2_preview_has_an_authored_contract_and_can_start(self):
        for scenario in ('cafe','shop','directions','station','meet-someone'):
            for level in ('A1','A2'):
                with self.subTest(scenario=scenario,level=level):
                    preview = self.preview(scenario,level)
                    self.assertEqual(preview.status_code,200,preview.json)
                    snapshot=preview.json['scenario']
                    self.assertEqual(snapshot['target_level'],level)
                    contract=snapshot['learning_contract']
                    self.assertEqual(contract['target_level'],level)
                    self.assertTrue(contract['grammar_focus'])
                    self.assertTrue(contract['vocabulary_focus'])
                    self.assertEqual(contract['communicative_objectives'],snapshot['goals'])
                    response=self.post(submission_id=f'{scenario}-{level}',scenario_id=scenario,
                                       scenario_seed=snapshot['seed'],target_level=level)
                    self.assertEqual(response.status_code,201,response.json)
                    self.assertEqual(response.json['scenario'],snapshot)
                    self.assertEqual(response.json['target_level'],level)
        self.assertEqual(self.provider.creates,[])

    def test_higher_level_preview_is_empty_and_cannot_start_a_lower_level_by_accident(self):
        for level in ('B1','B2'):
            preview=self.preview('cafe',level)
            self.assertEqual(preview.status_code,200,preview.json)
            self.assertIsNone(preview.json['scenario'])
            self.assertEqual(preview.json['available_count'],0)
            response=self.post(submission_id=level,scenario_id='cafe',target_level=level)
            self.assertEqual(response.status_code,409,response.json)
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM live_conversation_sessions').fetchone()[0],0)

    def test_cross_level_and_invalid_level_requests_are_rejected(self):
        for body in (
            {'target_level':'A2','scenario_seed':'cafe-a1-warm-lunch-v2'},
            {'target_level':'A1','scenario_seed':'cafe-a2-milk-v2'},
            {'target_level':'C2'}, {'target_level':['A1']},
            {'target_level':'A1','level':'A2'},
        ):
            response=self.post(submission_id='invalid',scenario_id='cafe',**body)
            self.assertEqual(response.status_code,400,response.json)
        self.assertEqual(self.preview(level='C2').status_code,400)
        self.assertEqual(self.client.get('/api/v1/live-conversations/scenarios?level=expert').status_code,400)

    def test_level_is_stable_on_idempotent_retry_and_catalogue_changes(self):
        body={'submission_id':'same','scenario_id':'cafe','scenario_seed':'cafe-a1-warm-lunch-v2','target_level':'A1'}
        saved=self.post(**body).json
        self.assertEqual(self.post(**body).json,saved)
        self.assertEqual(self.post(**{**body,'target_level':'A2'}).status_code,409)
        with transaction(self.db,write=True) as conn:
            raw=conn.execute('SELECT scenario_json FROM live_conversation_sessions WHERE id=?',(saved['id'],)).fetchone()[0]
            payload=json.loads(conn.execute("SELECT payload_json FROM speaking_scenario_variants WHERE id='cafe-a1-warm-lunch-v2'").fetchone()[0])
            payload['learning_contract']['grammar_focus']=['Changed later']
            conn.execute("UPDATE speaking_scenario_variants SET payload_json=? WHERE id='cafe-a1-warm-lunch-v2'",(json.dumps(payload),))
        again=self.client.get('/api/v1/live-conversations/'+saved['id']).json
        self.assertEqual(again['scenario'],saved['scenario'])
        with transaction(self.db) as conn:
            self.assertEqual(conn.execute('SELECT scenario_json FROM live_conversation_sessions WHERE id=?',(saved['id'],)).fetchone()[0],raw)

    def test_repeat_avoidance_stays_inside_the_selected_level(self):
        with transaction(self.db) as conn:
            a2=catalogue(conn,'A2')
            self.assertEqual(next(s for s in a2['scenarios'] if s['id']=='cafe')['variant_count'],3)
            next_variant=choose_variant(conn,'cafe',level='A2',previous_seeds=['cafe-a2-milk-v2','cafe-a2-sugar-v2','cafe-a1-warm-lunch-v2'])
            self.assertEqual(next_variant['seed'],'cafe-a2-onion-v2')
            self.assertEqual(choose_variant(conn,'cafe',level='A2',previous_seeds=['cafe-a2-onion-v2','cafe-a2-sugar-v2','cafe-a2-milk-v2'])['seed'],'cafe-a2-milk-v2')

    def test_level_prompts_differ_and_assessment_never_converts_scores_to_proficiency(self):
        with transaction(self.db) as conn:
            a1=choose_variant(conn,'station',level='A1')
            a2=choose_variant(conn,'station',level='A2',seed='station-a2-connection-v2')
        easy=scenario_instructions(a1)
        harder=scenario_instructions(a2)
        self.assertIn('Не требуй объяснять причины',easy)
        self.assertIn('попросить простую причину',harder)
        self.assertIn('повтори проще',easy)
        self.assertIn('не оценка владения языком',easy)
        self.assertIn('not the learner\'s established proficiency',_INSTRUCTIONS)
        self.assertIn('do not require advanced forms',_INSTRUCTIONS)
        self.assertNotEqual(a1['goals'],a2['goals'])

    def test_simplified_directions_does_not_show_the_route_in_reference(self):
        with transaction(self.db) as conn:
            scenario=choose_variant(conn,'directions',level='A1',seed='directions-a1-park-v2')
        reference=json.dumps(scenario['reference'],ensure_ascii=False).lower()
        self.assertNotIn('прямо',reference)
        self.assertNotIn('справа',reference)
        self.assertNotIn('пять минут',reference)
        self.assertIn('пять минут',scenario['worker_brief'])

    def test_database_rejects_unknown_target_levels(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.db,write=True) as conn:
                conn.execute("UPDATE speaking_scenario_variants SET target_level='expert' WHERE id='cafe-a1-warm-lunch-v2'")

    def test_migration24_does_not_relabel_or_rewrite_historical_session(self):
        with transaction(self.db,write=True) as conn:
            conn.execute("UPDATE speaking_scenario_variants SET enabled=1 WHERE id='cafe-for-two-v1'")
        saved=self.post(submission_id='historical',scenario_id='cafe',scenario_seed='cafe-for-two-v1').json
        original='{"seed": "cafe-for-two-v1", "title": "My original lesson", "menu": {"чай": 17}}'
        with transaction(self.db,write=True) as conn:
            conn.execute('UPDATE live_conversation_sessions SET scenario_json=? WHERE id=?',(original,saved['id']))
            # Recreate the genuine pre-024 shape, including later game tables.
            from tests.support import strip_progression_and_levels
            strip_progression_and_levels(conn)
            from migrations import MIGRATION_DIR
            conn.executescript((MIGRATION_DIR / '023_shared_progression.sql').read_text())
            from services.progression import seed_progression
            seed_progression(conn)
            conn.execute('INSERT INTO schema_migrations(version) VALUES (23)')
            conn.execute("DELETE FROM speaking_scenario_variants WHERE id IN ('directions-park-a1-v1','station-simple-ticket-a1-v1')")
            before=dict(conn.execute('SELECT * FROM live_conversation_sessions WHERE id=?',(saved['id'],)).fetchone())
        self.assertEqual(upgrade_database(self.db,backup=False),(latest_schema_version(),None))
        with transaction(self.db) as conn:
            after=dict(conn.execute('SELECT * FROM live_conversation_sessions WHERE id=?',(saved['id'],)).fetchone())
            self.assertEqual({key:after[key] for key in before},before)
            self.assertIsNone(after['target_level'])
            self.assertEqual(after['scenario_json'],original)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM speaking_scenario_variants WHERE target_level IS NOT NULL').fetchone()[0],48)


if __name__=='__main__':
    unittest.main()
