"""The event compiler must produce truthful, distinct and replayable deliveries."""
from collections import Counter
from copy import deepcopy
import json
import unittest

from services.route_mission import (
    GENERATOR_VERSION, MISSION_ID, available_clues, build_mission, catalogue,
    clue_matches, event_library, validate_mission,
)
from services.route_world import build_world


class RouteMissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worlds = [build_world(f'events-world-{index}') for index in range(20)]
        cls.packs = [build_mission(cls.worlds[index // 10], f'events-{index}') for index in range(200)]

    def test_two_hundred_seeds_validate_actual_routes_clues_and_inventory(self):
        for pack in self.packs:
            with self.subTest(seed=pack['mission_seed']):
                self.assertTrue(validate_mission(pack))
                self.assertEqual(pack['map']['edges'], pack['town']['map']['edges'])
                inventory = set()
                edges = {frozenset(edge) for edge in pack['map']['edges']}
                for index, leg in enumerate(pack['legs']):
                    self.assertTrue(all(frozenset(edge) in edges for edge in zip(leg['route'], leg['route'][1:])))
                    if index:
                        self.assertEqual(leg['start'], pack['legs'][index - 1]['target'])
                        self.assertEqual(leg['speaker'], pack['legs'][index - 1]['arrival_speaker'])
                    if leg.get('requires_item'):
                        self.assertIn(leg['requires_item'], inventory)
                    if leg.get('arrival_item'):
                        inventory.add(leg['arrival_item']['id'])
                    if leg.get('arrival_remove_item'):
                        inventory.remove(leg['arrival_remove_item'])
                self.assertFalse(inventory)
                self.assertEqual(pack['legs'][-1]['arrival_speaker'], pack['recipient_id'])
                for fact in pack['mission_facts']['clues']:
                    self.assertEqual(clue_matches(pack['town'], fact['clue']), [fact['clue']['place']])

    def test_structural_variation_is_more_than_names_and_seed_labels(self):
        structures = {pack['mission_facts']['structural_signature'] for pack in self.packs}
        self.assertGreaterEqual(len(structures), 8)
        self.assertEqual({len(pack['legs']) for pack in self.packs}, {2, 3, 4})
        self.assertGreater(len({pack['mission_facts']['fingerprint'] for pack in self.packs}), 190)
        self.assertGreater(len({(pack['legs'][0]['speaker'], pack['legs'][0]['arrival_speaker']) for pack in self.packs}), 30)
        self.assertGreaterEqual(len({pack['mission_facts']['pickup'] for pack in self.packs}), 6)
        relationships = {fact['clue']['relation'] for pack in self.packs for fact in pack['mission_facts']['clues']}
        self.assertTrue({'same-street', 'same-bank', 'north', 'south', 'east', 'west'} <= relationships)
        self.assertEqual({event['kind'] for pack in self.packs for event in pack['mission_facts']['events']}, set(event_library()))
        self.assertLessEqual(sum(pack['composition']['attempts'] - 1 for pack in self.packs), 20)

    def test_seed_reproduces_snapshot_without_modifying_saved_world(self):
        world = self.worlds[0]
        before = deepcopy(world)
        first = build_mission(world, 'repeatable')
        self.assertEqual(first, build_mission(world, 'repeatable'))
        self.assertEqual(first, json.loads(json.dumps(first)))
        self.assertEqual(world, before)
        self.assertEqual(first['mission_id'], MISSION_ID)
        self.assertEqual(first['generator_version'], GENERATOR_VERSION)
        self.assertTrue(first['lesson_version'].endswith(first['mission_facts']['fingerprint']))

    def test_recent_semantic_assignments_are_excluded_even_with_identical_seed(self):
        recent = []
        for _ in range(25):
            pack = build_mission(self.worlds[0], 'same-input', exclude_fingerprints=recent)
            self.assertNotIn(pack['mission_facts']['fingerprint'], recent)
            recent.append(pack['mission_facts']['fingerprint'])

    def test_all_candidate_clues_identify_exactly_one_actual_building(self):
        for world in self.worlds:
            for place, clues in available_clues(world).items():
                for clue in clues:
                    self.assertEqual(clue_matches(world, clue), [place])
                    self.assertNotEqual(place, clue['anchor'])

    def test_land_towns_never_invent_a_river_in_clues_or_dialogue(self):
        for family in ('market-square', 'garden-quarter'):
            world = build_world('land-language-' + family, {'layout_family': family})
            self.assertIsNone(world['map'].get('river_x'))
            for clues in available_clues(world).values():
                for clue in clues:
                    self.assertNotEqual(clue['relation'], 'same-bank')
                    invalid_river_clue = {**clue, 'relation': 'same-bank'}
                    self.assertEqual(clue_matches(world, invalid_river_clue), [])
            for index in range(10):
                with self.subTest(family=family, mission=index):
                    pack = build_mission(world, f'land-language-{index}')
                    self.assertTrue(validate_mission(pack))
                    self.assertTrue(pack['mission_facts']['learning_decisions'])
                    spoken = [line['text'] for leg in pack['legs']
                              for line in [*leg['lines'], leg['clarify'], *(q['reply'] for q in leg.get('questions', []))]]
                    self.assertNotRegex(' '.join(spoken), r'берег|мост|рек[аиуе]')

    def test_each_delivery_requires_a_real_distinction_not_a_unique_noun(self):
        for pack in self.packs:
            decisions = pack['mission_facts']['learning_decisions']
            self.assertTrue(decisions)
            for decision in decisions:
                self.assertGreaterEqual(len(decision['candidates']), 2)
                self.assertGreater(decision['leg'], 0)
                leg = pack['legs'][decision['leg']]
                if decision['kind'] == 'distinguish_entrances':
                    self.assertTrue(leg['arrival_policy']['entrance_required'])
                    self.assertIn(leg['target'], decision['candidates'])
                else:
                    self.assertIn(leg['arrival_policy']['building_id'], decision['candidates'])

    def test_concrete_story_purpose_matches_the_item_and_is_shared_consistently(self):
        purposes = set()
        for pack in self.packs:
            premise = pack['mission_facts']['premise']
            purposes.add(premise['id'])
            self.assertEqual(premise['item'], pack['mission_facts']['item'])
            self.assertTrue(any(line['text'] == premise['ru'] for line in pack['legs'][0]['lines']))
            for leg in pack['legs']:
                contract = leg['encounter_contract']
                purpose = next(fact for fact in contract['facts'] if fact['type'] == 'delivery_purpose')
                self.assertEqual({key: value for key, value in purpose.items() if key != 'type'}, premise)
                self.assertIn({'ru': premise['ru'], 'en': premise['en']}, contract['allowed_narrative'])
                circumstance = next(fact for fact in contract['facts'] if fact['type'] == 'circumstance')
                self.assertEqual(circumstance['id'] == 'informed-of-move', leg['id'] == 'new-address')
        self.assertEqual(len(purposes), 4)

    def test_clarification_answer_stays_out_of_initial_dialogue_and_prompt(self):
        count = 0
        for pack in self.packs:
            for leg in pack['legs']:
                if not leg.get('required_question'):
                    continue
                count += 1
                reply = next(question['reply'] for question in leg['questions'] if question['id'] == leg['required_question'])
                self.assertNotIn(reply['id'], [item['id'] for item in leg['lines']])
                self.assertNotEqual(reply['id'], leg['clarify']['id'])
                self.assertNotIn('landmark_relationship', [fact['type'] for fact in leg['encounter_contract']['facts']])
                self.assertEqual(leg['encounter_contract']['required_lines'], leg['lines'])
        self.assertGreater(count, 50)

    def test_relocation_is_only_disclosed_at_the_encounter_that_explains_it(self):
        for pack in self.packs:
            for event in pack['mission_facts']['events']:
                if event['kind'] != 'relocation':
                    continue
                for leg in pack['legs'][:event['leg']]:
                    contract = leg['encounter_contract']
                    self.assertNotIn('relocation', [fact['type'] for fact in contract['facts']])
                    self.assertNotIn(event['to'], [fact.get('place') for fact in contract['facts']])
                self.assertIn('relocation', [fact['type'] for fact in pack['legs'][event['leg']]['encounter_contract']['facts']])

    def test_courtyard_entrances_are_explicit_and_other_frontage_is_not_accepted(self):
        checked = 0
        for pack in self.packs:
            nodes = {node['id']: node for node in pack['map']['nodes']}
            for leg in pack['legs']:
                acceptance = leg['arrival_policy']
                self.assertEqual(acceptance['accepted_nodes'], [leg['target']])
                self.assertTrue(all(not nodes[node].get('building_id') for node in acceptance['near_nodes']))
                if acceptance['entrance_required']:
                    checked += 1
                    self.assertEqual(nodes[leg['target']]['entrance'], 'courtyard')
                    self.assertTrue(any('вход со двора' in line['text'] for line in leg['lines']))
                    building = next(b for b in pack['town']['buildings'] if b['id'] == acceptance['building_id'])
                    self.assertGreater(len(building['entrances']), 1)
        self.assertGreater(checked, 30)

    def test_modified_checked_text_or_translation_cannot_validate(self):
        for field, replacement in [('text', 'Поверни налево у школы.'), ('english', 'Turn right after the hospital.')]:
            pack = deepcopy(self.packs[0])
            pack['legs'][0]['lines'][1][field] = replacement
            with self.assertRaisesRegex(ValueError, 'modified|omitted|context'):
                validate_mission(pack)

    def test_spatial_metadata_cannot_lie_about_the_spoken_relationship(self):
        pack = deepcopy(self.packs[0])
        fact = pack['mission_facts']['clues'][0]
        fact['clue']['anchor'] = fact['clue']['place']
        with self.assertRaisesRegex(ValueError, 'geographic clue'):
            validate_mission(pack)

    def test_clarification_cannot_be_revealed_by_repeat_request(self):
        pack = deepcopy(next(pack for pack in self.packs if any(leg.get('required_question') for leg in pack['legs'])))
        leg = next(leg for leg in pack['legs'] if leg.get('required_question'))
        leg['clarify'] = leg['questions'][0]['reply']
        with self.assertRaisesRegex(ValueError, 'before the question'):
            validate_mission(pack)

    def test_item_cannot_be_delivered_before_collection(self):
        pack = deepcopy(self.packs[0])
        del pack['legs'][0]['arrival_item']
        with self.assertRaisesRegex(ValueError, 'collected'):
            validate_mission(pack)

    def test_wrong_arrival_area_cannot_be_accepted(self):
        pack = deepcopy(self.packs[0])
        leg = pack['legs'][0]
        leg['arrival_policy']['accepted_nodes'].append(leg['start'])
        with self.assertRaisesRegex(ValueError, 'arrival target'):
            validate_mission(pack)

    def test_contextual_vocabulary_keeps_real_forms_and_english_context_meanings(self):
        cases = Counter()
        for pack in self.packs:
            for word in pack['vocabulary_refs']:
                self.assertIn(word['form'].casefold(), word['sentence'].casefold())
                self.assertTrue(any(word['sentence'] == line['text'] for line in pack['legs'][word['leg']]['lines']))
                self.assertTrue(word['target_meaning'].isascii() or word['target_meaning'] == 'café')
                cases[word['grammar']['case']] += 1
        self.assertTrue({'gent', 'accs', 'loct'} <= cases.keys())

    def test_catalogue_and_session_titles_do_not_announce_twists(self):
        self.assertEqual([choice['mission_id'] for choice in catalogue()], [MISSION_ID])
        for pack in self.packs:
            self.assertEqual(pack['title'], 'A delivery for Barsik')
            self.assertTrue(all(leg['objective'] == 'Follow the directions' for leg in pack['legs']))


if __name__ == '__main__':
    unittest.main()
