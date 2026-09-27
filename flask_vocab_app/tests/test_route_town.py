"""Independent geometry and mission checks across generated towns."""
from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import unittest

from services.route_content import matches_rule
from services.route_town import (
    GENERATOR_VERSION, TOWN_MISSION_IDS, all_audio, build_mission, build_world,
    catalogue, shortest_path, validate_mission, validate_world, variant_seeds,
)


def reachable(map_data, start, blocked=()):
    blocked, seen = set(blocked), set()
    adjacency = {n['id']: set() for n in map_data['nodes']}
    for a, b in map_data['edges']:
        adjacency[a].add(b); adjacency[b].add(a)
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node not in seen and node not in blocked:
            seen.add(node); queue.extend(adjacency[node] - seen - blocked)
    return seen


class RouteTownTests(unittest.TestCase):
    def test_seed_is_deterministic_and_changes_geography(self):
        first = build_world('household-town')
        self.assertEqual(first, build_world('household-town'))
        self.assertEqual(first['generator_version'], GENERATOR_VERSION)
        self.assertEqual(first, json.loads(json.dumps(first)))
        shapes = {json.dumps(build_world(seed)['map']['edges']) for seed in range(20)}
        self.assertGreaterEqual(len(shapes), 4)

    def test_many_seeds_have_connected_loops_and_exact_tile_exits(self):
        vectors = {'n': (0, -1), 'e': (1, 0), 's': (0, 1), 'w': (-1, 0)}
        for seed in range(40):
            with self.subTest(seed=seed):
                world = build_world(seed)
                m = world['map']
                nodes = {n['id']: n for n in m['nodes']}
                coordinates = {(n['x'], n['y']): nid for nid, n in nodes.items()}
                edges = {frozenset(e) for e in m['edges']}
                self.assertTrue(50 <= len(nodes) <= 140)
                self.assertGreater(len(edges), len(nodes))
                self.assertEqual(reachable(m, world['places']['post']), set(nodes))
                self.assertEqual(len(m['districts']), 3)
                self.assertEqual(len(m['tiles']), m['width'] * m['height'])
                for tile in m['tiles']:
                    nid = coordinates.get((tile['x'], tile['y']))
                    if nid is None:
                        self.assertFalse(tile.get('exits'))
                        continue
                    expected = set()
                    for direction, (dx, dy) in vectors.items():
                        neighbour = coordinates.get((tile['x'] + dx, tile['y'] + dy))
                        if neighbour and frozenset((nid, neighbour)) in edges:
                            expected.add(direction)
                    self.assertEqual(set(tile['exits']), expected)

    def test_both_crossings_work_independently_and_no_invisible_crossing(self):
        for seed in range(30):
            world = build_world(seed)
            m, p, bridges = world['map'], world['places'], world['bridges']
            for closed in bridges.values():
                self.assertIn(p['library'], reachable(m, p['post'], [closed]))
            self.assertNotIn(p['library'], reachable(m, p['post'], bridges.values()))
            river_x = m['river_x']
            crossings = {(n['x'], n['y']) for n in m['nodes'] if n['id'] in bridges.values()}
            self.assertEqual({(n['x'], n['y']) for n in m['nodes'] if n['x'] == river_x}, crossings)

    def test_buildings_have_real_adjacent_distinct_entrances(self):
        world = build_world('doors')
        nodes = {n['id']: n for n in world['map']['nodes']}
        for building in world['buildings']:
            self.assertNotIn((building['x'], building['y']), {(n['x'], n['y']) for n in nodes.values()})
            for door in building['entrances']:
                node = nodes[door]
                self.assertEqual(node['building_id'], building['id'])
                self.assertEqual(abs(node['x'] - building['x']) + abs(node['y'] - building['y']), 1)
        courtyard = next(b for b in world['buildings'] if b['id'] == 'courtyard-house')
        self.assertEqual(len(courtyard['entrances']), 2)
        self.assertEqual({nodes[n]['entrance'] for n in courtyard['entrances']}, {'main', 'courtyard'})

    def test_neighbourhoods_have_interior_landmarks_and_distinct_street_classes(self):
        layouts = set()
        for seed in range(40):
            world = build_world(seed)
            layouts.add(world['layout_id'])
            m = world['map']
            nodes = {n['id']: n for n in m['nodes']}
            segments = m['street_segments']
            self.assertEqual({s['kind'] for s in segments}, {'main', 'residential', 'path'})
            self.assertEqual({frozenset((s['from'], s['to'])) for s in segments}, {frozenset(e) for e in m['edges']})
            self.assertGreaterEqual({b['kind'] for b in m['blocks']}, {'market', 'park', 'courtyard', 'civic'})
            driving = {nid for s in segments if s['kind'] != 'path' for nid in (s['from'], s['to'])}
            interiors = []
            for b in world['buildings']:
                x, y = b['x'], b['y']
                around = [
                    any(nodes[n]['x'] < x and abs(nodes[n]['y'] - y) <= 1 for n in driving),
                    any(nodes[n]['x'] > x and abs(nodes[n]['y'] - y) <= 1 for n in driving),
                    any(nodes[n]['y'] < y and abs(nodes[n]['x'] - x) <= 1 for n in driving),
                    any(nodes[n]['y'] > y and abs(nodes[n]['x'] - x) <= 1 for n in driving),
                ]
                if all(around):
                    interiors.append(b['id'])
                plots = [p for p in m['plots'] if p.get('building_id') == b['id']]
                self.assertEqual(len(plots), 1)
                self.assertEqual(plots[0]['frontage'], b['frontage'])
            self.assertGreaterEqual(len(interiors), 10)
            self.assertTrue({'market', 'bakery', 'library', 'pharmacy', 'courtyard-house', 'cafe'} <= set(interiors))
            degrees = {nid: 0 for nid in driving}
            for s in segments:
                if s['kind'] != 'path':
                    degrees[s['from']] += 1
                    degrees[s['to']] += 1
            self.assertGreaterEqual(sum(degree == 3 for degree in degrees.values()), 4)
        self.assertEqual(len(layouts), 4)

    def test_bus_uses_roads_and_never_the_river_walk(self):
        for seed in range(12):
            world = build_world(seed)
            leg = build_mission(world, 'town-bus')['legs'][1]
            road_edges = {frozenset((s['from'], s['to'])) for s in world['map']['street_segments'] if s['kind'] != 'path'}
            self.assertTrue(all(frozenset((a, b)) in road_edges for a, b in zip(leg['route'], leg['route'][1:])))
            self.assertEqual([nid for nid in leg['route'] if nid in world['bus']['stops']], world['bus']['stops'])
        broken = build_mission(build_world('bus-path'), 'town-bus')
        leg = broken['legs'][1]
        edge = frozenset(leg['route'][:2])
        segment = next(s for s in broken['town']['map']['street_segments'] if frozenset((s['from'], s['to'])) == edge)
        segment['kind'] = 'path'
        with self.assertRaisesRegex(ValueError, 'pedestrian path'):
            validate_mission(broken)

    def test_spoken_geography_rejects_incorrect_parcel_and_bank_positions(self):
        world = build_world('spoken-relations')
        for seed in variant_seeds('town-parcel'):
            pack = build_mission(world, 'town-parcel', seed=seed)
            buildings = {b['id']: b for b in pack['town']['buildings']}
            if pack['mission_facts']['destination'] == 'cafe':
                self.assertEqual(buildings['cafe']['x'], buildings['station']['x'])
                self.assertGreater(buildings['cafe']['y'], buildings['station']['y'])
                buildings['cafe']['y'] = buildings['station']['y'] - 1
                error = 'south of the station'
            else:
                buildings['library']['x'] = buildings[pack['mission_facts']['pickup']]['x']
                error = 'across the river'
            with self.assertRaisesRegex(ValueError, error):
                validate_mission(pack)
        pack = build_mission(world, 'town-clarify')
        buildings = {b['id']: b for b in pack['town']['buildings']}
        buildings['bank-east']['x'], buildings['pharmacy']['x'] = 3, 4
        with self.assertRaisesRegex(ValueError, 'across the river'):
            validate_mission(pack)

    def test_invalid_plots_and_street_metadata_fail_explicitly(self):
        world = build_world('plot-validation')
        broken = deepcopy(world)
        broken['map']['street_segments'].pop()
        with self.assertRaisesRegex(ValueError, 'every graph edge'):
            validate_world(broken)
        broken = deepcopy(world)
        road = next(n for n in broken['map']['nodes'] if n['id'] == broken['places']['square'])
        plot = broken['map']['plots'][0]
        plot.update(x=road['x'], y=road['y'])
        with self.assertRaisesRegex(ValueError, 'overlaps a road'):
            validate_world(broken)
        broken = deepcopy(world)
        broken['map']['plots'][0]['frontage'] = 's'
        with self.assertRaisesRegex(ValueError, 'face its entrance'):
            validate_world(broken)
        broken = deepcopy(world)
        broken['buildings'][1]['entrances'] = broken['buildings'][0]['entrances']
        with self.assertRaisesRegex(ValueError, 'entrance is misplaced'):
            validate_world(broken)

    def test_all_missions_are_solvable_and_frozen_across_seeds(self):
        for seed in range(30):
            world = build_world(seed)
            before = deepcopy(world)
            for mission_id in TOWN_MISSION_IDS:
                with self.subTest(seed=seed, mission=mission_id):
                    pack = build_mission(world, mission_id, seed='mission-1')
                    self.assertEqual(pack, build_mission(world, mission_id, seed='mission-1'))
                    self.assertEqual(pack['town'], world)
                    self.assertIsNot(pack['town'], world)
                    self.assertEqual(pack['version'], 'journey-delivery-v2')
                    nodes = {n['id']: n for n in pack['map']['nodes']}
                    edges = {frozenset(e) for e in pack['map']['edges']}
                    for index, leg in enumerate(pack['legs']):
                        self.assertEqual(leg['route'][0], leg['start'])
                        self.assertEqual(leg['route'][-1], leg['target'])
                        self.assertTrue(all(frozenset((a, b)) in edges for a, b in zip(leg['route'], leg['route'][1:])))
                        self.assertTrue(all(matches_rule(rule, leg['route'], nodes) for rule in leg['rules']))
                        if index:
                            self.assertEqual(leg['start'], pack['legs'][index - 1]['target'])
                    self.assertTrue(validate_mission(pack))
            self.assertEqual(world, before)

    def test_detour_has_more_than_one_acceptable_route(self):
        world = build_world('alternate-detours')
        pack = build_mission(world, 'town-detour')
        leg = pack['legs'][-1]
        nodes = {n['id']: n for n in world['map']['nodes']}
        closed = pack['map']['closures'][0]['node_id']
        self.assertNotIn(closed, leg['route'])
        self.assertIn(world['bridges'][pack['mission_facts']['open_bridge']], leg['route'])
        alternatives = []
        for node in leg['route'][1:-1]:
            if node in world['bridges'].values():
                continue
            try:
                path = shortest_path(world, leg['start'], leg['target'], avoid=[closed, node])
            except ValueError:
                continue
            if path != leg['route'] and all(matches_rule(rule, path, nodes) for rule in leg['rules']):
                alternatives.append(path)
        self.assertTrue(alternatives, 'The task should allow multiple sensible detours')

    def test_address_needs_colour_and_location_not_colour_alone(self):
        for seed in range(10):
            world = build_world(seed)
            buildings = {b['id']: b for b in world['buildings']}
            for mission_id in ('town-address', 'town-recipient'):
                pack = build_mission(world, mission_id)
                colour = pack['mission_facts']['house_colour'] if mission_id == 'town-address' else 'blue'
                same_colour = [b for b in buildings.values() if b.get('colour') == colour]
                self.assertGreaterEqual(len(same_colour), 2)
                matches = [b for b in same_colour if b['y'] == buildings['library']['y'] == buildings['pharmacy']['y']
                           and buildings['library']['x'] < b['x'] < buildings['pharmacy']['x']]
                self.assertEqual(len(matches), 1)
                self.assertIn((pack['legs'][-1] if mission_id == 'town-address' else pack['legs'][0])['target'], matches[0]['entrances'])

    def test_inventory_moved_recipient_and_clarification_are_real_state_contracts(self):
        world = build_world('mechanics')
        parcel = build_mission(world, 'town-parcel')['legs']
        self.assertEqual(parcel[0]['arrival_item']['id'], 'parcel')
        self.assertEqual(parcel[1]['requires_item'], 'parcel')
        self.assertEqual(parcel[1]['arrival_remove_item'], 'parcel')
        moved = build_mission(world, 'town-recipient')['legs']
        self.assertEqual(moved[0]['target'], world['places']['blue-house'])
        self.assertIn(moved[1]['target'], [world['places']['market'], world['places']['park']])
        self.assertNotIn('рынок', moved[0]['lines'][0]['text'])
        clarify = build_mission(world, 'town-clarify')['legs'][0]
        self.assertEqual(clarify['required_question'], clarify['questions'][0]['id'])
        self.assertNotIn('аптек', clarify['lines'][0]['text'])
        self.assertIn('аптек', clarify['questions'][0]['reply']['text'])

    def test_bus_stops_and_guide_start_match_their_instructions(self):
        for seed in range(10):
            world = build_world(seed)
            bus_pack = build_mission(world, 'town-bus')
            ride = bus_pack['legs'][1]
            bus = ride['transport']
            self.assertEqual(ride['start'], bus['board'])
            self.assertEqual(ride['target'], bus['alight'])
            self.assertEqual(bus['stops'].index(bus['alight']) - bus['stops'].index(world['places']['square']), 2)
            self.assertFalse(ride['rules'], 'Riding accepts the route between stops, not a hidden preferred path')
            guide = build_mission(world, 'town-guide')['legs'][0]
            self.assertTrue(guide['guide'])
            self.assertEqual(guide['heading'], 'east')
            self.assertEqual(guide['start'], world['places']['post'])
            self.assertFalse(guide['rules'])

    def test_mission_seed_changes_real_facts_and_routes_in_the_same_town(self):
        world = build_world('persistent-household-world')
        for mission_id, count in (('town-detour', 2), ('town-address', 2), ('town-parcel', 4), ('town-recipient', 2)):
            packs = [build_mission(world, mission_id, seed=seed) for seed in variant_seeds(mission_id)]
            self.assertEqual(len(packs), count)
            self.assertEqual(len({json.dumps(p['mission_facts'], sort_keys=True) for p in packs}), count)
            self.assertEqual(len({json.dumps([leg['route'] for leg in p['legs']]) for p in packs}), count)
            self.assertEqual(len({json.dumps([leg['lines'] for leg in p['legs']]) for p in packs}), count)
            self.assertTrue(all(len(p['legs']) >= 2 for p in packs))
            self.assertTrue(all(p['town'] == world for p in packs))
        courtyard = build_mission(world, 'town-courtyard')
        self.assertEqual(len(courtyard['legs']), 2)
        self.assertEqual(courtyard['legs'][0]['target'], world['places']['courtyard-house'])
        self.assertEqual(courtyard['legs'][1]['target'], world['places']['courtyard'])
        guide = build_mission(world, 'town-guide')
        self.assertEqual(guide['recipient_id'], 'visitor')
        self.assertIn('помощь', guide['ending']['text'])

    def test_audio_catalogue_covers_every_generated_line_without_network_calls(self):
        audio = {item['id']: item for item in all_audio()}
        self.assertTrue(audio)
        root = Path(__file__).resolve().parents[1]
        for clip in audio.values():
            path = root / clip['audio_url'].lstrip('/')
            self.assertTrue(path.is_file(), f'Missing authored recording: {path.name}')
            self.assertGreater(path.stat().st_size, 1024)
        self.assertEqual({row['mission_id'] for row in catalogue()}, set(TOWN_MISSION_IDS))
        for seed in range(12):
            for mission_id in TOWN_MISSION_IDS:
                pack = build_mission(build_world(seed), mission_id)
                lines = [pack['ending']]
                for leg in pack['legs']:
                    lines.extend([*leg['lines'], leg['clarify'], *(q['reply'] for q in leg.get('questions', []))])
                for item in lines:
                    self.assertIn(item['id'], audio)
                    self.assertEqual(audio[item['id']]['text'], item['text'])

    def test_bad_world_and_impossible_constraints_fail_explicitly(self):
        world = build_world('invalid')
        broken = deepcopy(world)
        broken['map']['tiles'][0]['exits'] = ['e']
        # Tamper an actual road exit; background decoration is not path data.
        next(t for t in broken['map']['tiles'] if t.get('node_id'))['exits'] = []
        with self.assertRaisesRegex(ValueError, 'artwork'):
            validate_world(broken)
        with self.assertRaisesRegex(ValueError, 'No route'):
            shortest_path(world, world['places']['post'], world['places']['library'], avoid=world['bridges'].values())
        pack = build_mission(world, 'town-parcel')
        pack['legs'][0].pop('arrival_item')
        with self.assertRaisesRegex(ValueError, 'cannot be collected'):
            validate_mission(pack)


class TownMediaAccessTests(unittest.TestCase):
    def test_bundled_recordings_work_without_household_login(self):
        from tests.support import isolated_app
        app = isolated_app(self)
        app.config.update(WORD_POST_HOUSEHOLD_ENABLED=True, SECRET_KEY='synthetic-test-secret-' * 3)
        visitor = app.test_client()
        for clip in all_audio():
            with self.subTest(clip=clip['id']):
                response = visitor.get(clip['audio_url'])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, 'audio/mpeg')
                response.close()
        # The narrow audio allowlist must not expose the preparation manifest.
        response = visitor.get('/static/audio/deliveries/manifest.json')
        self.assertNotEqual(response.status_code, 200)
        response.close()


if __name__ == '__main__':
    unittest.main()
