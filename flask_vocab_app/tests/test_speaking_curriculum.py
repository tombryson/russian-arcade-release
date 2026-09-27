"""Content publication, curriculum relations and compatible scenario facts."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from migrations import upgrade_database
from repositories.speaking_repository import catalogue, choose_variant
from repositories.learning_repository import LearningError
from services.curriculum import generation_context
from services.speaking_curriculum import _check_facts, _content, scenario_for_topic
from tests.support import strip_course_progression


class SpeakingCurriculumTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'speaking.sqlite3'
        upgrade_database(self.path, backup=False)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)

    def snapshots(self):
        return [json.loads(row[0]) for row in self.conn.execute(
            'SELECT payload_json FROM speaking_scenario_variants WHERE enabled=1')]

    def test_curriculum_relationships_and_summaries_are_complete_for_the_supported_scope(self):
        mapping = {'cafe':('food','restaurant'), 'shop':('clothing','shopping'),
                   'directions':('places','places'), 'station':('travel','travel'),
                   'meet-someone':('greetings','hobbies')}
        result = catalogue(self.conn)
        self.assertEqual(len(result['scenarios']), 5)
        for category in result['scenarios']:
            self.assertEqual(category['variant_count'], 6)
            details = category['level_details']
            self.assertNotEqual(details['A1']['description'], details['A2']['description'])
            for index,level in enumerate(('A1','A2')):
                self.assertEqual(details[level]['topic_id'], mapping[category['id']][index])
                self.assertTrue(all(details[level][field] for field in ('title','title_ru','description','description_ru')))
                self.assertEqual(scenario_for_topic(details[level]['topic_id'],level), category['id'])
        self.assertIsNone(scenario_for_topic('science','A2'))
        self.assertIsNone(scenario_for_topic('food','B1'))

    def test_new_variants_preserve_shared_curriculum_and_scoped_learning_requirements(self):
        snapshots = self.snapshots()
        self.assertEqual(len(snapshots), 30)
        for snapshot in snapshots:
            with self.subTest(seed=snapshot['seed']):
                context = snapshot['curriculum_context']
                self.assertEqual(context, generation_context(context['topic_id'],snapshot['target_level'],'speaking'))
                self.assertEqual(snapshot['learning_contract']['topic_id'], context['topic_id'])
                requirements = snapshot['learning_contract']['requirements']
                self.assertEqual(len(requirements),4)
                self.assertEqual(len({r['id'] for r in requirements}),4)
                self.assertEqual([r['kind'] for r in requirements], ['communicative']*3+['grammar'])
                self.assertTrue(all(r['description'] and r['evidence_hint'] for r in requirements))
                self.assertEqual(snapshot['goal_ids'],[r['id'] for r in requirements[:3]])
                _check_facts({**snapshot,'facts':snapshot['variation']['facts']})

    def test_each_level_and_category_has_distinct_compatible_facts(self):
        for group in _content()['groups']:
            with self.subTest(category=group['scenario_id'],level=group['target_level']):
                facts = [b['facts'] for b in group['bundles']]
                self.assertEqual(len(facts),3)
                # Require more than a cosmetic title or cost change.
                substantive = [{k:v for k,v in fact.items() if k not in ('price','total','unit_price','cash','change')}
                               for fact in facts]
                self.assertEqual(len({json.dumps(f,sort_keys=True) for f in substantive}),3)

    def test_bundle_openings_match_register_and_situation(self):
        snapshots = {item['seed']:item for item in self.snapshots()}
        neighbour = snapshots['meet-someone-a1-neighbour-v2']
        self.assertIn('Как вас зовут?',neighbour['opening'])
        self.assertNotIn('тебя',neighbour['opening'])
        for bundle in ('size','smaller','shoes'):
            self.assertIn('Размер подошёл?',snapshots[f'shop-a2-{bundle}-v2']['opening'])
        self.assertIn('велосипеде',snapshots['meet-someone-a2-cycling-v2']['opening'])
        self.assertIn('фильмы',snapshots['meet-someone-a2-cinema-v2']['opening'])

    def test_a2_requires_topic_specific_clarifications_missing_from_the_old_catalogue(self):
        snapshots = self.snapshots()
        for snapshot in snapshots:
            if snapshot['target_level'] != 'A2':
                continue
            facts=snapshot['variation']['facts']
            if snapshot['scenario_id']=='cafe':
                self.assertEqual(facts['people'],2)
                self.assertIn('excluded_ingredient',facts)
                self.assertIn('Ask whether',snapshot['goals'][0])
                self.assertIn('bill',snapshot['goals'][-1])
            elif snapshot['scenario_id']=='shop':
                self.assertNotEqual(facts['initial_size'],facts['wanted_size'])
                self.assertEqual(facts['change'],facts['cash']-facts['price'])
            elif snapshot['scenario_id']=='station':
                self.assertTrue(facts['transfer'])
                self.assertIn('change',snapshot['goals'][1])

    def test_bad_money_or_unreachable_train_connections_cannot_publish(self):
        cases=[dict(facts=dict(food='суп',total=10),menu={'суп':100}),
               dict(facts=dict(price=700,cash=1000,change=500)),
               dict(facts=dict(unit_price=100,ticket_count=2,total=100)),
               dict(facts=dict(transfer_arrival='10:00',connection_departure='09:00')),
               dict(facts=dict(deadline='12:00',options=[dict(departure='09:00',change='10:00',arrival='13:00')]))]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                _check_facts(case)

    def test_historic_catalogue_rows_remain_but_are_not_selected(self):
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM speaking_scenario_variants WHERE enabled=0').fetchone()[0],18)
        with self.assertRaises(LearningError):
            choose_variant(self.conn,'cafe',seed='cafe-for-two-v1')
        for _ in range(20):
            self.assertTrue(choose_variant(self.conn,'cafe',level='A2')['seed'].endswith('-v2'))

    def test_migration_preserves_attempts_and_custom_variants_without_inserting_words(self):
        # Recreate catalogue data before 042, with a historical immutable attempt.
        strip_course_progression(self.conn)
        self.conn.execute('DELETE FROM speaking_scenario_variants WHERE id LIKE ? ',('%-v2',))
        self.conn.execute('UPDATE speaking_scenario_variants SET enabled=1')
        self.conn.execute('DELETE FROM speaking_scenario_levels')
        self.conn.execute('DELETE FROM schema_migrations WHERE version>=42')
        old='{"seed":"cafe-for-two-v1","title":"Original task","menu":{"чай":17}}'
        self.conn.execute("""INSERT INTO live_conversation_sessions
            (id,profile_id,start_key,scenario_json,language,model,backend_model,voice,state,
             created_at,heartbeat_at,scenario_id,variant_id,target_level)
            VALUES ('historic','personal-learning','historic',?,'en','original','original','cedar',
                    'completed',1,2,'cafe','cafe-for-two-v1','A1')""",(old,))
        self.conn.execute("INSERT INTO speaking_scenario_variants(id,scenario_id,payload_json,target_level) VALUES ('custom','cafe','{}','A1')")
        before=dict(self.conn.execute("SELECT * FROM live_conversation_sessions WHERE id='historic'").fetchone())
        words_before=[tuple(row) for row in self.conn.execute('SELECT * FROM words')]
        self.conn.commit()
        upgrade_database(self.path,backup=False)
        after=dict(self.conn.execute("SELECT * FROM live_conversation_sessions WHERE id='historic'").fetchone())
        self.assertEqual(before,after)
        self.assertEqual([tuple(row) for row in self.conn.execute('SELECT * FROM words')],words_before)
        self.assertEqual(self.conn.execute("SELECT enabled FROM speaking_scenario_variants WHERE id='custom'").fetchone()[0],1)
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(),[])
        # Already-applied migrations do not overwrite later catalogue edits.
        self.conn.execute("UPDATE speaking_scenario_levels SET title='Edited' WHERE scenario_id='cafe' AND target_level='A1'")
        self.conn.commit()
        upgrade_database(self.path,backup=False)
        self.assertEqual(catalogue(self.conn)['scenarios'][0]['level_details']['A1']['title'],'Edited')


if __name__=='__main__':
    unittest.main()
