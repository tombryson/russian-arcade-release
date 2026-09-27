"""Definition links cannot manufacture learner evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from services import curriculum_requirement_map as maps

class CurriculumRequirementMapTests(unittest.TestCase):
    def test_total_coverage_and_conservative_mapping(self):
        data = maps.load_requirement_map()
        self.assertEqual(len(data['requirements']), 239)
        self.assertEqual(len(data['mappings']), 110)
        self.assertEqual({r['requirement_id'] for r in data['requirements']}, set(maps.requirement_index()))
        self.assertFalse(data['review']['human_validated'])
        self.assertFalse(data['policy']['automatic_evidence_transfer'])
        rows = {r['legacy_target_id']: r for r in data['mappings']}
        self.assertEqual(rows['a1.greetings.name-pattern.select']['links'][0]['relation'], 'equivalent')
        self.assertEqual(rows['a1.home.singular-plural.select']['links'][0]['relation'], 'partial')
        self.assertEqual(rows['a1.places.location-versus-direction.select']['links'][0]['relation'], 'related')
        self.assertEqual(rows['a1.food.identify-food-drink.write']['links'], [])
        self.assertTrue(rows['a1.food.identify-food-drink.write']['unmapped_reason'])

    def test_missing_duplicate_stale_and_invented_coverage_rejected(self):
        original = maps.load_requirement_map()
        for mutate in (
            lambda d: d['requirements'].pop(), lambda d: d['mappings'].pop(),
            lambda d: d['requirements'].append(deepcopy(d['requirements'][0])),
            lambda d: d['mappings'][0].update(legacy_definition_sha256='0'*64),
            lambda d: d['requirements'][0]['source_refs'][0].update(locator='invented'),
            lambda d: d['review'].update(human_validated=True),
            lambda d: d['policy'].update(automatic_evidence_transfer=True),
        ):
            broken = deepcopy(original); mutate(broken)
            with self.assertRaises(ValueError): maps.validate_requirement_map(broken)

    def test_cross_mode_and_related_evidence_authorisation_rejected(self):
        broken = maps.load_requirement_map()
        broken['mappings'][1]['links'][0].update(requirement_id='a1.speaking.social-etiquette', relation='equivalent')
        with self.assertRaisesRegex(ValueError, 'same evidence mode'): maps.validate_requirement_map(broken)
        broken = maps.load_requirement_map()
        link = next(x for r in broken['mappings'] for x in r['links'] if x['relation'] == 'related')
        link['allowed_response_modes'] = ['contextual_selection']
        with self.assertRaisesRegex(ValueError, 'cannot authorise'): maps.validate_requirement_map(broken)

    def test_report_reads_shipped_items_without_database(self):
        with patch('sqlite3.connect', side_effect=AssertionError('No learner DB')):
            report = maps.coverage_report()
        self.assertEqual(report['shipped_item_counts'], {'focused_practice': 32, 'checkpoint': 120})
        self.assertEqual(sum(r['kind'] == 'checkpoint' for r in report['unattributed_items']), 96)
        self.assertTrue(all(row['assessment_validation'] == 'not_validated' for row in report['requirements']))
        self.assertTrue(all(not row['candidate_items'] for row in report['requirements'] if row['level'] != 'A1' or row['domain'] in ('writing', 'speaking')))
        matched = next(r for r in report['requirements'] if r['requirement_id'] == 'a1.reading.practical-information')
        self.assertGreater(matched['checkpoint_item_count'], 0)
        self.assertTrue(all(len(i['content_sha256']) == 64 for i in matched['candidate_items']))

    def test_defensive_copy_and_generated_report(self):
        data = maps.load_requirement_map(); data['mappings'].clear()
        self.assertEqual(len(maps.load_requirement_map()['mappings']), 110)
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location('coverage_renderer', root / 'scripts/render_curriculum_coverage.py')
        renderer = importlib.util.module_from_spec(spec); spec.loader.exec_module(renderer)
        self.assertEqual((root / 'docs/curriculum-coverage.md').read_text(encoding='utf-8'), renderer.render())

    def test_new_units_are_counted_without_inventing_unprepared_listening(self):
        report = maps.coverage_report()
        tasks = report['direct_task_contracts']
        listening = [item for item in tasks if item['kind'] == 'unit_listening_choice']
        self.assertEqual(len(listening), 6)
        self.assertEqual({item['id'].split(':')[0] for item in listening},
                         {'location-destination-v1', 'possession-absence-v1'})
        for unit_id, forms in (('possession-absence-v1', 4), ('objects-recipients-v1', 4), ('time-routine-v1', 5),
                               ('noun-adjective-agreement-v1', 4), ('personal-reference-v1', 4), ('basic-motion-v1', 4)):
            authored = [item for item in tasks if item['id'].startswith(unit_id + ':')]
            self.assertEqual(sum(item['kind'] == 'unit_choice' for item in authored), 6)
            self.assertEqual(sum(item['kind'] == 'unit_controlled_text' for item in authored), forms)
            self.assertEqual(sum(item['kind'] == 'unit_writing' for item in authored), 1)
            self.assertEqual(sum(item['kind'] == 'unit_listening_choice' for item in authored),
                             3 if unit_id == 'possession-absence-v1' else 0)
