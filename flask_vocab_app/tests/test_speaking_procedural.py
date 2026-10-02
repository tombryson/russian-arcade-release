"""Free situation assembly, semantic replay avoidance and frozen evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from migrations import upgrade_database
from repositories.learning_repository import LearningError
from repositories.speaking_repository import _category_metadata, choose_variant, catalogue
from services.conversation_policy import scenario_instructions, russian_speech
from services.speaking_curriculum import _check_facts
from services.speaking_evidence import speaking_task_contract, validate_speaking_contract
from services.speaking_procedural import build, recipes, seed_for, parse_seed, semantic_key


class SpeakingRecipeTests(unittest.TestCase):
    def test_every_recipe_is_compatible_bilingual_and_semantically_distinct(self):
        for category, metadata in _category_metadata().items():
            for level in ('A1','A2'):
                keys = set()
                self.assertGreaterEqual(len(recipes(category,level)),24)
                for index in range(len(recipes(category,level))):
                    seed = seed_for(category,level,index)
                    with self.subTest(seed=seed):
                        task = build(seed,metadata)
                        self.assertEqual(task,build(seed,metadata))
                        _check_facts({**task,'facts':task['variation']['facts']})
                        self.assertEqual(len(task['learning_contract']['requirements']),4)
                        for field in ('opening','title_ru','description_ru','worker_brief'):
                            self.assertTrue(russian_speech(task[field]), (field,task[field]))
                        self.assertEqual(len(task['goals_ru']),3)
                        key = semantic_key(task)
                        self.assertNotIn(key,keys)
                        keys.add(key)
                        contract = speaking_task_contract(task)
                        self.assertEqual(validate_speaking_contract(contract,task),contract)
                        self.assertEqual(contract['level'],level)
                        self.assertIn('only',contract['criteria'][0]['expectation'])
                        self.assertEqual(contract['content']['goal_ids'],task['diagnostic_mapping']['goal_ids'])

    def test_semantic_history_ignores_identity_price_and_character_name(self):
        task = build(seed_for('meet-someone','A1',0),_category_metadata()['meet-someone'])
        edited = deepcopy(task)
        edited['seed']='different'
        edited['variation']['facts'].update(character='Другой',price=17)
        self.assertEqual(semantic_key(task),semantic_key(edited))
        edited['variation']['facts']['conversation_topic']=3
        self.assertNotEqual(semantic_key(task),semantic_key(edited))

    def test_register_explicit_forms_and_whole_hour_a1_times(self):
        for index, recipe in enumerate(recipes('meet-someone','A1')):
            opening=build(seed_for('meet-someone','A1',index),_category_metadata()['meet-someone'])['opening']
            self.assertIn('вас' if recipe['facts']['register']=='вы' else 'тебя',opening)
        for recipe in recipes('station','A1'):
            self.assertTrue(recipe['facts']['departure'].endswith(':00'))
            self.assertNotIn('transfer',recipe['facts'])
        for recipe in recipes('station','A2'):
            facts=recipe['facts']
            self.assertNotEqual(facts['destination'],facts['transfer'])
            self.assertLess(facts['transfer_arrival'],facts['connection_departure'])
        for recipe in recipes('shop','A1'):
            form=recipe['facts']['requested_form']
            if recipe['facts']['item']=='брюки':
                self.assertTrue(form.startswith(('синие','красные','чёрные')))

    def test_cafe_and_shop_titles_describe_situations_not_product_inventories(self):
        for recipe in recipes('cafe','A1'):
            self.assertEqual(recipe['title'],'A quick takeaway' if recipe['facts']['service']=='с собой' else 'A break at the café')
        for recipe in recipes('shop','A1'):
            self.assertIn(recipe['title'],('Trying on clothes','Shopping for clothes'))

    def test_cafe_live_character_receives_exact_ingredient_and_billing_facts(self):
        task=build('cafe-a2-p3-17',_category_metadata()['cafe'])
        prompt=scenario_instructions(task)
        self.assertIn(task['worker_brief'],prompt)
        self.assertIn(task['variation']['facts']['alternative'],prompt)
        self.assertIn(task['variation']['facts']['excluded_ingredient'],prompt)
        self.assertIn('только по-русски',prompt)

    def test_changed_facts_or_forged_mapping_cannot_acquire_original_diagnostic(self):
        original=build('cafe-a1-p3-0',_category_metadata()['cafe'])
        for field in ('facts','mapping','goal'):
            task=deepcopy(original)
            if field=='facts': task['variation']['facts']['food']='торт'
            elif field=='mapping': task['diagnostic_mapping']['requirement_id']='a1.speaking.repair'
            else: task['goals'][0]='Ask the total'
            with self.subTest(field=field),self.assertRaises(ValueError): speaking_task_contract(task)
        for seed in ('cafe-a1-p3-999999','shop-a3-p3-1','cafe-a1-p3-01','cafe-a1-p3-'+'1'*10000):
            self.assertIsNone(parse_seed(seed))


class SpeakingRecipeRepositoryTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path=Path(folder.name)/'db.sqlite3'
        upgrade_database(path,backup=False)
        self.conn=sqlite3.connect(path)
        self.conn.row_factory=sqlite3.Row
        self.addCleanup(self.conn.close)

    def test_preview_is_read_only_start_materializes_exact_seed_and_catalogue_stays_stable(self):
        before=self.conn.total_changes
        listing=catalogue(self.conn)
        preview=choose_variant(self.conn,'directions',level='A2')
        self.assertIsNotNone(parse_seed(preview['seed']))
        self.assertEqual(self.conn.total_changes,before)
        self.assertIsNone(self.conn.execute('SELECT 1 FROM speaking_scenario_variants WHERE id=?',(preview['seed'],)).fetchone())
        saved=choose_variant(self.conn,'directions',level='A2',seed=preview['seed'],persist=True)
        self.assertEqual(preview,saved)
        payload=self.conn.execute('SELECT payload_json FROM speaking_scenario_variants WHERE id=?',(preview['seed'],)).fetchone()[0]
        self.assertEqual(json.loads(payload),saved)
        self.assertEqual(catalogue(self.conn),listing)

    def test_semantic_variety_exhaustion_exclusion_and_legacy_history(self):
        recent=[]
        for index in range(24):
            task=choose_variant(self.conn,'meet-someone',level='A1',previous_seeds=recent)
            self.assertNotIn(task['seed'],recent)
            recent.insert(0,task['seed'])
        self.assertEqual(choose_variant(self.conn,'meet-someone',level='A1',previous_seeds=recent)['seed'],recent[-1])
        legacy=choose_variant(self.conn,'meet-someone',level='A1',seed='meet-someone-a1-classmate-v2')
        self.assertEqual(legacy['scenario_version'],2)
        self.assertEqual(choose_variant(self.conn,'meet-someone',level='A1',previous_seeds=[legacy['seed']])['scenario_version'],3)

    def test_disabled_or_customised_publication_does_not_get_bypassed(self):
        self.conn.execute("UPDATE speaking_scenario_variants SET enabled=0 WHERE scenario_id='shop' AND target_level='A1'")
        with self.assertRaises(LearningError): choose_variant(self.conn,'shop',level='A1',seed='shop-a1-p3-0')
        self.conn.execute("UPDATE speaking_scenario_variants SET enabled=1 WHERE id='shop-a1-hat-v2'")
        # The disabled group is not resurrected by procedural assembly.
        self.assertEqual(choose_variant(self.conn,'shop',level='A1')['seed'],'shop-a1-hat-v2')
        task=choose_variant(self.conn,'cafe',level='A2',seed='cafe-a2-p3-0',persist=True)
        self.conn.execute('UPDATE speaking_scenario_variants SET enabled=0 WHERE id=?',(task['seed'],))
        with self.assertRaises(LearningError): choose_variant(self.conn,'cafe',level='A2',seed=task['seed'])
        for _ in range(10): self.assertNotEqual(choose_variant(self.conn,'cafe',level='A2')['seed'],task['seed'])

    def test_semantically_identical_history_under_another_id_is_not_novel(self):
        from repositories.learning_repository import encoded
        recent=[]
        for index in range(24):
            task=build(seed_for('meet-someone','A1',index),_category_metadata()['meet-someone'])
            task['variation']['facts']['character']='Другое имя'
            alias=f'old-identity-{index}'
            self.conn.execute('INSERT INTO speaking_scenario_variants(id,scenario_id,payload_json,target_level) VALUES (?,?,?,?)',
                              (alias,'meet-someone',encoded(task),'A1'))
            recent.append(alias)
        # All meanings have been seen, despite none of the recipe IDs appearing
        # in history. Choose the least recent meaning rather than random UUIDs.
        selected=choose_variant(self.conn,'meet-someone',level='A1',previous_seeds=recent)
        self.assertEqual(selected['seed'],seed_for('meet-someone','A1',23))


if __name__=='__main__':
    unittest.main()
