"""Generated assignments must remain playable, grammatical and replayable."""
from collections import Counter
from copy import deepcopy
import json
import unittest

from services.route_content import matches_rule
from services.route_dispatch import (
    CLUES, GENERATOR_VERSION, MISSION_ID, all_audio, build_mission, catalogue,
    clue_matches, validate_mission,
)
from services.route_town import build_world


class RouteDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = build_world('dispatch-tests')
        cls.packs = [build_mission(cls.world, seed) for seed in range(160)]

    def test_seed_and_frozen_town_reproduce_the_exact_assignment(self):
        before = deepcopy(self.world)
        pack = build_mission(self.world, 'replayable')
        self.assertEqual(pack, build_mission(self.world, 'replayable'))
        self.assertEqual(pack, json.loads(json.dumps(pack)))
        self.assertEqual(self.world, before)
        self.assertEqual(pack['mission_seed'], 'replayable')
        self.assertEqual(pack['generator_version'], GENERATOR_VERSION)
        self.assertEqual(pack['mission_id'], MISSION_ID)
        self.assertTrue(pack['lesson_version'].endswith(':' + pack['mission_facts']['fingerprint']))

    def test_assignments_change_places_and_events_without_changing_the_town(self):
        fingerprints = {pack['mission_facts']['fingerprint'] for pack in self.packs}
        pickups = {pack['mission_facts']['pickup'] for pack in self.packs}
        destinations = {pack['mission_facts']['destination'] for pack in self.packs}
        counts = {len(pack['legs']) for pack in self.packs}
        events = {event['kind'] for pack in self.packs for event in pack['mission_facts']['events']}
        # Variation must extend beyond changing the seed label or one of the
        # former fourteen authored variants.
        self.assertGreater(len(fingerprints), 140)
        self.assertEqual(len(pickups), 6)
        self.assertEqual(len(destinations), 13)
        self.assertEqual(counts, {2, 3, 4})
        self.assertEqual(events, {'collection', 'closed-crossing', 'relocation', 'clarification'})
        self.assertEqual(len({pack['lesson_version'] for pack in self.packs}), len(fingerprints))
        for pack in self.packs:
            self.assertEqual(pack['town'], self.world)
            self.assertEqual(pack['map']['nodes'], self.world['map']['nodes'])

    def test_recent_assignment_exclusions_do_not_repeat_the_same_story(self):
        recent = []
        # Even repeated caller seeds must not force the learner through a
        # fixed cycle when that assignment is in their recent history.
        for _ in range(25):
            pack = build_mission(self.world, 'same-seed', exclude_fingerprints=recent)
            fingerprint = pack['mission_facts']['fingerprint']
            self.assertNotIn(fingerprint, recent)
            recent.append(fingerprint)

    def test_every_encounter_is_connected_and_the_item_reaches_its_recipient(self):
        for pack in self.packs:
            with self.subTest(seed=pack['mission_seed']):
                nodes = {node['id']: node for node in pack['map']['nodes']}
                edges = {frozenset(edge) for edge in pack['map']['edges']}
                item, previous, speaker = None, self.world['places']['post'], 'postmaster'
                for leg in pack['legs']:
                    self.assertEqual(leg['start'], previous)
                    self.assertEqual(leg['speaker'], speaker)
                    self.assertNotEqual(leg['start'], leg['target'])
                    self.assertEqual(leg['route'][0], leg['start'])
                    self.assertEqual(leg['route'][-1], leg['target'])
                    self.assertTrue(all(frozenset(edge) in edges for edge in zip(leg['route'], leg['route'][1:])))
                    self.assertTrue(all(matches_rule(rule, leg['route'], nodes) for rule in leg['rules']))
                    if leg.get('requires_item'):
                        self.assertEqual(leg['requires_item'], item)
                    if leg.get('arrival_item'):
                        item = leg['arrival_item']['id']
                    if leg.get('arrival_remove_item'):
                        self.assertEqual(item, leg['arrival_remove_item'])
                        item = None
                    previous, speaker = leg['target'], leg['arrival_speaker']
                self.assertIsNone(item)
                self.assertEqual(speaker, pack['mission_facts']['recipient'])
                self.assertEqual(previous, self.world['places'][pack['mission_facts']['destination']])

    def test_clues_select_exactly_one_building_across_all_town_plans(self):
        for seed in range(20):
            world = build_world(seed)
            for clue in CLUES:
                with self.subTest(seed=seed, clue=clue['id']):
                    self.assertEqual(clue_matches(world, clue), [clue['place']])
            self.assertTrue(validate_mission(build_mission(world, 'a-new-assignment')))

    def test_spatial_checker_rejects_false_and_ambiguous_addresses(self):
        clue = next(clue for clue in CLUES if clue['id'] == 'yellow-address')
        wrong = deepcopy(self.world)
        yellow = next(building for building in wrong['buildings'] if building['id'] == 'yellow-house')
        yellow['x'] = 16  # Beyond the pharmacy, not between it and the library.
        self.assertEqual(clue_matches(wrong, clue), [])
        ambiguous = deepcopy(self.world)
        blue = next(building for building in ambiguous['buildings'] if building['id'] == 'blue-house')
        blue['colour'] = 'yellow'
        self.assertEqual(len(clue_matches(ambiguous, clue)), 2)
        for seed in range(10):
            pack = build_mission(ambiguous, seed)
            self.assertNotIn(clue['id'], {fact['clue_id'] for fact in pack['mission_facts']['clues']})

    def test_bridge_encounters_can_start_on_either_bank_and_use_the_other_crossing(self):
        directions = set()
        for pack in self.packs:
            crossing = next((leg for leg in pack['legs'] if leg.get('crossing')), None)
            if crossing is None:
                continue
            directions.add(crossing['crossing']['direction'])
            nodes = {node['id']: node for node in pack['map']['nodes']}
            index = pack['legs'].index(crossing)
            meeting = pack['legs'][index - 1]
            closure = pack['map']['closures'][0]
            self.assertTrue(meeting['bridge_meeting'])
            self.assertEqual(closure['from_leg'], index - 1)
            approach, closed = nodes[meeting['target']], nodes[closure['node_id']]
            self.assertEqual(abs(approach['x'] - closed['x']) + abs(approach['y'] - closed['y']), 1)
            self.assertNotEqual(crossing['crossing']['bridge'], closure['node_id'])
            for leg in pack['legs'][closure['from_leg']:]:
                self.assertNotIn(closure['node_id'], leg['route'])
            self.assertIn(crossing['crossing']['bridge'], crossing['route'])
            start, finish = nodes[crossing['start']], nodes[crossing['target']]
            self.assertLess((start['x'] - self.world['map']['river_x']) * (finish['x'] - self.world['map']['river_x']), 0)
        self.assertEqual(directions, {'east', 'west'})

    def test_clarification_withholds_the_specific_address_until_the_question(self):
        found = 0
        for pack in self.packs:
            for leg in pack['legs']:
                if not leg.get('required_question'):
                    continue
                found += 1
                self.assertTrue(pack['vocabulary_refs'])
                question = next(question for question in leg['questions'] if question['id'] == leg['required_question'])
                self.assertNotIn(question['reply']['text'], [item['text'] for item in leg['lines']])
                self.assertNotEqual(leg['clarify']['text'], question['reply']['text'])
                self.assertIn(question['reply']['text'], [clue['ru'] for clue in CLUES])
                self.assertTrue(question['text'].endswith('?'))
                self.assertTrue(question['reply']['audio_url'].endswith('.mp3'))
        self.assertGreater(found, 5)

    def test_recording_catalogue_covers_every_dialogue_path_without_runtime_generation(self):
        catalogue = all_audio()
        audio = {clip['id']: clip for clip in catalogue}
        self.assertEqual(len(audio), len(catalogue))
        self.assertLessEqual(len(audio), 90)
        self.assertLess(sum(len(clip['text']) for clip in catalogue), 5000)
        used = Counter()
        for pack in self.packs:
            clips = [pack['ending']]
            for leg in pack['legs']:
                clips.extend([*leg['lines'], leg['clarify'], *(question['reply'] for question in leg.get('questions', []))])
            for clip in clips:
                self.assertIn(clip['id'], audio)
                self.assertEqual(clip['text'], audio[clip['id']]['text'])
                self.assertEqual(clip['english'], audio[clip['id']]['english'])
                used[clip['id']] += 1
        self.assertGreater(len(used), 65)
        self.assertGreater(max(used.values()), 25)

    def test_starting_metadata_does_not_name_the_hidden_event_or_destination(self):
        choices = catalogue()
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0]['mission_id'], MISSION_ID)
        for pack in self.packs:
            self.assertEqual(pack['title'], 'A new delivery')
            self.assertNotIn('closed', pack['title'].lower())
            self.assertNotIn('bridge', pack['summary'].lower())
            for leg in pack['legs']:
                self.assertEqual(leg['objective'], 'Follow the directions')

    def test_corrupt_snapshot_cannot_claim_a_different_destination_or_uncollected_item(self):
        pack = deepcopy(self.packs[0])
        pack['mission_facts']['destination'] = 'post'
        with self.assertRaisesRegex(ValueError, 'final encounter'):
            validate_mission(pack)
        pack = deepcopy(self.packs[0])
        pack['legs'][0].pop('arrival_item')
        with self.assertRaisesRegex(ValueError, 'collected'):
            validate_mission(pack)


if __name__ == '__main__':
    unittest.main()
