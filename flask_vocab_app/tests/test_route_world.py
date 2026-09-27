"""Map contracts checked independently of the procedural assembler."""
from collections import Counter, deque
from copy import deepcopy
import json
import unittest

from services.route_town import shortest_path
from services.route_world import GENERATOR_VERSION, LAYOUT_FAMILIES, build_world, validate_world


def reachable(world, start, avoid=()):
    adjacency = {node['id']: set() for node in world['map']['nodes']}
    for a, b in world['map']['edges']:
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen, queue, avoid = set(), deque([start]), set(avoid)
    while queue:
        node = queue.popleft()
        if node not in seen and node not in avoid:
            seen.add(node)
            queue.extend(adjacency[node] - seen - avoid)
    return seen


class RouteWorldTests(unittest.TestCase):
    def test_saved_world_is_reproducible_and_json_roundtrips(self):
        world = build_world('same-household')
        self.assertEqual(world, build_world('same-household'))
        self.assertEqual(world, json.loads(json.dumps(world)))
        self.assertEqual(world['generator_version'], GENERATOR_VERSION)
        world['buildings'][0]['forms']['nom'] = 'changed'
        self.assertNotEqual(world, build_world('same-household'))

    def test_two_hundred_worlds_have_real_street_and_place_variation(self):
        roads, placements, templates, families = set(), set(), set(), Counter()
        for seed in range(200):
            with self.subTest(seed=seed):
                world = build_world(seed)
                nodes = {node['id'] for node in world['map']['nodes']}
                self.assertEqual(reachable(world, world['places']['post']), nodes)
                self.assertTrue(validate_world(world))
                # Exclude the changing doorstep paths: distinct streets must
                # come from block assembly, not merely shuffled landmark names.
                roads.add(tuple((s['from'], s['to']) for s in world['map']['street_segments'] if s['kind'] != 'path'))
                placements.add(tuple((b['id'], b['x'], b['y']) for b in world['buildings']))
                templates.update(block['template'] for block in world['assembly'])
                families[world['layout_family']] += 1
                self.assertEqual(len(world['assembly']), 4)
                self.assertEqual(len(world['map']['tiles']), world['map']['width'] * world['map']['height'])
        self.assertGreaterEqual(len(roads), 150)
        self.assertEqual(len(placements), 200)
        self.assertEqual(len(templates), 6)
        self.assertEqual(set(families), set(LAYOUT_FAMILIES))
        self.assertTrue(all(count >= 40 for count in families.values()))

    def test_each_bridge_can_close_without_hiding_a_destination(self):
        for seed in range(30):
            world = build_world(seed, {'layout_family': 'riverside'})
            for bridge in world['bridges'].values():
                seen = reachable(world, world['places']['post'], [bridge])
                self.assertTrue(set(world['places'].values()) - {bridge} <= seen)
                shortest_path(world, world['places']['post'], world['places']['library'], avoid=[bridge])
            self.assertNotIn(world['places']['library'], reachable(world, world['places']['post'], world['bridges'].values()))

    def test_boundary_ports_are_compatible_and_connected(self):
        world = build_world('ports')
        nodes = {node['id']: node for node in world['map']['nodes']}
        for block in world['assembly']:
            for socket in block['connections']:
                x, y = socket['cell']
                self.assertIn(f'tile-{x}-{y}', nodes)
        broken = deepcopy(world)
        broken['assembly'][0]['connections'][0]['width'] = 2
        with self.assertRaisesRegex(ValueError, 'compatible'):
            validate_world(broken)

    def test_landmarks_have_reachable_interior_plots_and_checked_forms(self):
        for seed in range(20):
            world = build_world(seed)
            nodes = {node['id']: node for node in world['map']['nodes']}
            positions = {(node['x'], node['y']) for node in nodes.values()}
            for building in world['buildings']:
                self.assertTrue(1 < building['x'] < world['map']['width'] - 2)
                self.assertTrue(1 < building['y'] < world['map']['height'] - 2)
                self.assertNotIn((building['x'], building['y']), positions)
                self.assertEqual(set(building['forms']), {'nom', 'gen', 'dat', 'acc', 'inst', 'prep'})
                for entrance in building['entrances']:
                    node = nodes[entrance]
                    self.assertEqual(node['building_id'], building['id'])
                    self.assertEqual(abs(node['x'] - building['x']) + abs(node['y'] - building['y']), 1)
                    self.assertGreater(len(shortest_path(world, world['places']['post'], entrance)), 0)

    def test_courtyard_is_a_distinct_walkable_entrance_off_the_driving_roads(self):
        for seed in range(50):
            world = build_world(seed)
            house = next(b for b in world['buildings'] if b['id'] == 'courtyard-house')
            self.assertEqual(len(house['entrances']), 2)
            self.assertNotEqual(world['places']['courtyard'], world['places']['courtyard-house'])
            driving_nodes = {n for edge in world['map']['street_segments'] if edge['kind'] != 'path' for n in (edge['from'], edge['to'])}
            self.assertNotIn(world['places']['courtyard'], driving_nodes)
            shortest_path(world, world['places']['courtyard-house'], world['places']['courtyard'])

    def test_duplicate_landmarks_remain_visually_and_geographically_distinguishable(self):
        world = build_world('duplicates')
        buildings = {b['id']: b for b in world['buildings']}
        for base in ('bank', 'yellow-house', 'blue-house'):
            west = buildings['bank-west' if base == 'bank' else base + '-west']
            east = buildings['bank-east' if base == 'bank' else base]
            self.assertEqual(west['label'], east['label'])
            self.assertLess(west['x'], world['map']['width'] // 2)
            self.assertGreater(east['x'], world['map']['width'] // 2)
        self.assertEqual(buildings['library']['forms']['gen'], 'библиотеки')
        self.assertEqual(buildings['pharmacy']['forms']['inst'], 'аптекой')

    def test_larger_town_keeps_connections_and_required_landmarks(self):
        world = build_world('three-rows', {'block_rows': 3, 'layout_family': 'garden-quarter', 'landmark_tags': ['courtyard', 'collection'], 'landmark_kinds': ['library']})
        self.assertEqual(world['map']['height'], 33)
        self.assertEqual(len(world['assembly']), 6)
        self.assertEqual(len(world['buildings']), 15)
        self.assertTrue(validate_world(world))
        for requirements in ({'block_rows': 1}, {'block_rows': True}, {'layout_family': 'unknown'}, {'landmark_tags': ['airport']}, {'landmark_kinds': ['airport']}):
            with self.assertRaises(ValueError):
                build_world('unsupported', requirements)

    def test_validator_rejects_invisible_edges_and_wrong_frontages(self):
        world = build_world('damage')
        corrupted = deepcopy(world)
        corrupted['map']['edges'].append([world['places']['post'], world['places']['library']])
        with self.assertRaisesRegex(ValueError, 'skips'):
            validate_world(corrupted)
        corrupted = deepcopy(world)
        first = corrupted['buildings'][0]
        first['frontage'] = {'n': 's', 's': 'n', 'e': 'w', 'w': 'e'}[first['frontage']]
        with self.assertRaisesRegex(ValueError, 'faces away'):
            validate_world(corrupted)
        corrupted = deepcopy(world)
        tile = next(t for t in corrupted['map']['tiles'] if t.get('exits'))
        tile['exits'] = []
        with self.assertRaisesRegex(ValueError, 'exits'):
            validate_world(corrupted)

    def test_land_families_have_real_central_features_and_no_water(self):
        for family, kind in [('market-square', 'market'), ('garden-quarter', 'park')]:
            with self.subTest(family=family):
                world = build_world('family-geometry', {'layout_family': family})
                self.assertEqual(world['layout_family'], family)
                self.assertEqual(world['map']['layout_family'], family)
                self.assertIsNone(world['map']['river_x'])
                self.assertEqual(world['bridges'], {})
                self.assertFalse(any(t['kind'] in ('river', 'bridge') for t in world['map']['tiles']))
                self.assertFalse(any(key.startswith('bridge-') for key in world['places']))
                feature = world['map']['terrain_features'][0]
                self.assertEqual((feature['width'], feature['height']), (5, 5))
                landmark = next(b for b in world['buildings'] if b['id'] == kind)
                self.assertEqual((landmark['x'], landmark['y']), (10, 10))
                self.assertEqual(landmark['block_id'], feature['id'])
                centre_nodes = {n['id'] for n in world['map']['nodes'] if 8 <= n['x'] <= 12 and 8 <= n['y'] <= 12}
                centre_edges = [e for e in world['map']['street_segments'] if e['from'] in centre_nodes and e['to'] in centre_nodes]
                if family == 'garden-quarter':
                    self.assertTrue(centre_edges)
                    self.assertTrue(all(e['kind'] == 'path' for e in centre_edges))
                else:
                    self.assertTrue(any(e['kind'] == 'residential' for e in centre_edges))
                broken = deepcopy(world)
                broken['map']['tiles'][0]['kind'] = 'river'
                with self.assertRaisesRegex(ValueError, 'land town'):
                    validate_world(broken)

    def test_layout_families_change_routes_instead_of_recolouring_water(self):
        worlds = [build_world('matching-seed', {'layout_family': family}) for family in LAYOUT_FAMILIES]
        graphs = {tuple(tuple(edge) for edge in world['map']['edges']) for world in worlds}
        driving = {tuple((edge['from'], edge['to']) for edge in world['map']['street_segments'] if edge['kind'] != 'path') for world in worlds}
        self.assertEqual(len(graphs), 3)
        self.assertEqual(len(driving), 3)
        for world in worlds:
            self.assertEqual(world, build_world('matching-seed', {'layout_family': world['layout_family']}))
            for landmark in world['buildings']:
                shortest_path(world, world['places']['post'], landmark['entrances'][0])

    def test_saved_legacy_world_stays_separate(self):
        from services.route_town import build_world as legacy_world
        before = legacy_world('existing-session')
        build_world('existing-session')
        self.assertEqual(before, legacy_world('existing-session'))
        self.assertNotEqual(before['generator_version'], GENERATOR_VERSION)
