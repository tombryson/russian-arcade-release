"""Assemble saved delivery towns from versioned blocks and landmark definitions.

Blocks own their internal routes and plots. The assembler joins matching boundary
sockets, then assigns landmark roles; neither dialogue nor artwork creates edges.
"""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import random

GENERATOR_VERSION = 'delivery-block-town-v2'
LAYOUT_FAMILIES = ('market-square', 'garden-quarter', 'riverside')
_CONTENT = Path(__file__).resolve().parents[1] / 'content' / 'deliveries'
_DIRECTIONS = {(0, -1): 'n', (1, 0): 'e', (0, 1): 's', (-1, 0): 'w'}
_SIDES = ('north', 'east', 'south', 'west')
_PRIORITY = {'path': 0, 'residential': 1, 'main': 2}


@lru_cache(maxsize=3)
def _read_library(name):
    with (_CONTENT / name).open(encoding='utf-8') as source:
        return json.load(source)


def _rng(seed):
    return random.Random(int.from_bytes(sha256(str(seed).encode()).digest(), 'big'))


def _node(x, y):
    return f'tile-{x}-{y}'


def _rotate(point, turns, size=9):
    x, y = point
    for _ in range(turns):
        x, y = size - 1 - y, x
    return x, y


def _expand(points):
    """Expand orthogonal polylines; diagonal geometry is a content error."""
    result = [tuple(points[0])]
    for end in points[1:]:
        x, y = result[-1]
        tx, ty = end
        if x != tx and y != ty:
            raise ValueError('Block routes must be orthogonal')
        while (x, y) != (tx, ty):
            x += (tx > x) - (tx < x)
            y += (ty > y) - (ty < y)
            result.append((x, y))
    return result


def _connected(nodes, edges, blocked=()):
    blocked = set(blocked)
    adjacency = {key: set() for key in nodes if key not in blocked}
    for a, b in edges:
        if a in adjacency and b in adjacency:
            adjacency[a].add(b)
            adjacency[b].add(a)
    if not adjacency:
        return set()
    seen, pending = set(), [next(iter(adjacency))]
    while pending:
        current = pending.pop()
        if current not in seen:
            seen.add(current)
            pending.extend(adjacency[current] - seen)
    return seen


def build_world(seed, requirements=None):
    """Create a deterministic town; requirements never mutate an existing town.

    ``layout_family`` selects a library layout; otherwise the seed chooses it.
    ``block_rows`` may be two or three. ``landmark_tags`` and ``landmark_kinds``
    require library capabilities and fail clearly when unavailable. Missions bind
    to the returned buildings rather than assuming a landmark's old coordinates.
    """
    requirements = requirements or {}
    rows = requirements.get('block_rows', 2)
    if type(rows) is not int or rows not in (2, 3):
        raise ValueError('Delivery towns support two or three block rows')
    seed = str(seed)
    rng = _rng(seed)
    layout_library = _read_library('town-layouts.json')
    family = requirements.get('layout_family') or rng.choice(LAYOUT_FAMILIES)
    if family not in LAYOUT_FAMILIES:
        raise ValueError('Unknown delivery town layout family')
    layout = next(item for item in layout_library['layouts'] if item['id'] == family)
    block_library = _read_library('map-blocks.json')
    landmark_library = _read_library('landmarks.json')
    definitions = landmark_library['landmarks']
    available_tags = {tag for item in definitions for tag in item['tags']}
    available_kinds = {item['kind'] for item in definitions}
    if not set(requirements.get('landmark_tags', ())) <= available_tags:
        raise ValueError('Required landmark tag is not available in the content library')
    if not set(requirements.get('landmark_kinds', ())) <= available_kinds:
        raise ValueError('Required landmark kind is not available in the content library')
    pitch_x, pitch_y = 9 + layout['block_gap_x'], 9 + layout['block_gap_y']
    width, height = pitch_x + 9, rows * pitch_y - layout['block_gap_y']
    center_x = width // 2
    river_x = center_x if layout['river'] else None
    nodes, edge_kinds, slots, assembly, blocks = {}, {}, [], [], []
    places, buildings, plots, connectors, terrain_features = {}, [], [], [], []

    def district(x, y):
        return ('west' if x < center_x else 'east') + '-' + str(min(rows - 1, y // pitch_y))

    def path(points, kind='residential'):
        points = _expand(points)
        for x, y in points:
            nodes.setdefault((x, y), {'id': _node(x, y), 'x': x, 'y': y,
                                     'kind': 'street', 'label': 'Улица', 'label_en': 'Street',
                                     'district': district(x, y)})
        for a, b in zip(points, points[1:]):
            edge = tuple(sorted((_node(*a), _node(*b))))
            if _PRIORITY[kind] > _PRIORITY.get(edge_kinds.get(edge), -1):
                edge_kinds[edge] = kind

    courtyard_block = rng.randrange(rows * 2)
    courtyard_templates = [b for b in block_library['blocks'] if 'separate-courtyard' in b.get('features', ())]

    # Neighbourhood sockets are assembled first. The family then determines
    # whether their shared space is a river, a street square or pedestrian park.
    for bank, origin_x in (('west', 0), ('east', pitch_x)):
        for row in range(rows):
            pool = courtyard_templates if len(assembly) == courtyard_block else block_library['blocks']
            definition = rng.choice(pool)
            turns = rng.choice(definition['rotations']) // 90
            origin_y = row * pitch_y
            block_id = f'{bank}-{row}'
            required = ({'north'} if row else set()) | ({'south'} if row < rows - 1 else set())
            if not layout['river'] or row in (0, rows - 1):
                required.add('east' if bank == 'west' else 'west')

            def transform(point):
                x, y = _rotate(point, turns)
                return origin_x + x, origin_y + y

            connections = []
            for connection in definition['connections']:
                side = _SIDES[(_SIDES.index(connection['side']) + turns) % 4]
                if side in required:
                    connections.append({'side': side, 'cell': list(transform(connection['cell'])),
                                        'kind': connection['kind'], 'width': connection['width']})
            for route in definition['routes']:
                if route.get('socket'):
                    side = _SIDES[(_SIDES.index(route['socket']) + turns) % 4]
                    if side not in required:
                        continue
                path([transform(point) for point in route['points']], route['kind'])
            grounds = []
            for index, ground in enumerate(definition['ground']):
                corners = [transform((ground['x'] + dx, ground['y'] + dy))
                           for dx in (0, ground['width'] - 1) for dy in (0, ground['height'] - 1)]
                x, y = min(p[0] for p in corners), min(p[1] for p in corners)
                ground_id = f'{block_id}-ground-{index}'
                item = {'id': ground_id, 'x': x, 'y': y,
                        'width': max(p[0] for p in corners) - x + 1,
                        'height': max(p[1] for p in corners) - y + 1, 'kind': definition['kind']}
                blocks.append(item)
                grounds.append(item)
            for slot in definition['plots']:
                pos = transform(slot['cell'])
                ground = next(g for g in grounds if g['x'] <= pos[0] < g['x'] + g['width'] and g['y'] <= pos[1] < g['y'] + g['height'])
                slots.append({'id': block_id + '-' + slot['id'], 'bank': bank,
                              'pos': pos, 'door': transform(slot['entrance']),
                              'street': transform(slot['street']), 'tags': slot['tags'],
                              'block_id': ground['id'],
                              'courtyard_path': [transform(p) for p in slot.get('courtyard_path', [])]})
            assembly.append({'id': block_id, 'template': definition['id'], 'rotation': turns * 90,
                             'origin': [origin_x, origin_y], 'connections': connections})

    # Store complete socket-to-socket routes rather than assuming every block
    # touches its neighbour. Land families reserve three cells between blocks.
    def connect(start, end, kind='residential'):
        points = _expand([start, end])
        path(points, kind)
        connectors.append({'from': _node(*start), 'to': _node(*end),
                           'path': [_node(*point) for point in points], 'kind': kind})

    for origin_x in (0, pitch_x):
        for row in range(rows - 1):
            connect((origin_x + 4, row * pitch_y + 8),
                    (origin_x + 4, (row + 1) * pitch_y))
    bridges = {}
    for row in range(rows):
        if layout['river'] and row not in (0, rows - 1):
            continue
        y = row * pitch_y + 4
        connect((8, y), (pitch_x, y), 'main' if layout['river'] else 'residential')
        if not layout['river']:
            continue
        name = 'north' if row == 0 else 'south'
        ru, en = ('Северный мост', 'North bridge') if name == 'north' else ('Южный мост', 'South bridge')
        bridges[name] = places['bridge-' + name] = _node(center_x, y)
        nodes[(center_x, y)].update(kind='bridge', label=ru, label_en=en)
        for side, x in (('west', 8), ('east', pitch_x)):
            key = name + '-approach' + ('-east' if side == 'east' else '')
            places[key] = _node(x, y)
            nodes[(x, y)].update(kind='meeting', label='У ' + ('северного' if name == 'north' else 'южного') + ' моста',
                                 label_en=en + ' approach')

    if not layout['river']:
        for row in range(rows - 1):
            cx, cy = center_x, row * pitch_y + 10
            feature_id = 'central-' + str(row)
            for route in layout['central_routes']:
                path([(cx + x, cy + y) for x, y in route['points']], route['kind'])
            ground = layout['ground']
            blocks.append({'id': feature_id, 'x': cx + ground['x'], 'y': cy + ground['y'],
                           'width': ground['width'], 'height': ground['height'], 'kind': ground['kind']})
            terrain_features.append({'id': feature_id, 'kind': layout['central_feature'],
                                     'x': cx - 2, 'y': cy - 2, 'width': 5, 'height': 5})
            if row == 0:
                dx, dy = layout['central_entrance']
                sx, sy = layout['central_street']
                slots.append({'id': feature_id, 'bank': 'central', 'pos': (cx, cy),
                              'door': (cx + dx, cy + dy), 'street': (cx + sx, cy + sy),
                              'tags': ['building', 'public'], 'block_id': feature_id,
                              'courtyard_path': [], 'landmark_id': layout['central_landmark']})

    # Reserve specialist plots first, then side-constrained duplicate landmarks.
    # The remaining destinations can occupy any free interior plot.
    ordered = sorted(definitions, key=lambda item: (-1 if item['id'] == layout.get('central_landmark') else
                                                    0 if 'courtyard' in item['tags'] else 1 if item.get('bank') else 2))
    used_slots = set()
    for item in ordered:
        candidates = [slot for slot in slots if slot['id'] not in used_slots
                      and (slot.get('landmark_id') == item['id'] if item['id'] == layout.get('central_landmark')
                           else not slot.get('landmark_id'))
                      and (not item.get('bank') or slot['bank'] == item['bank'])
                      and ('courtyard' not in item['tags'] or ('courtyard' in slot['tags']
                           and slot['courtyard_path'][0] not in nodes))]
        # Leave enough plots for the five required west-bank and four east-bank
        # landmarks when the courtyard receives the first allocation.
        if 'courtyard' in item['tags']:
            candidates = [slot for slot in candidates if sum(s['bank'] == slot['bank'] for s in slots) >
                          sum(d.get('bank') == slot['bank'] for d in definitions)]
        if not candidates:
            raise ValueError('No compatible plot remains for a required landmark')
        slot = rng.choice(candidates)
        used_slots.add(slot['id'])
        pos, door, street = slot['pos'], slot['door'], slot['street']
        if pos in nodes:
            raise ValueError('A content plot overlaps its block streets')
        path([street, door], 'path')
        nodes[door].update(kind=item['kind'], label=item['label'], label_en=item['label_en'],
                           building_id=item['id'], entrance='main')
        places[item['id']] = _node(*door)
        frontage = _DIRECTIONS[(door[0] - pos[0], door[1] - pos[1])]
        building = {key: deepcopy(item[key]) for key in ('id', 'kind', 'label', 'label_en', 'forms', 'tags')}
        building.update(x=pos[0], y=pos[1], district=district(*pos),
                        entrances=[_node(*door)], frontage=frontage, block_id=slot['block_id'])
        if item.get('colour'):
            building['colour'] = nodes[door]['colour'] = item['colour']
        if 'courtyard' in item['tags']:
            access = slot['courtyard_path']
            path(access, 'path')
            rear = access[0]
            nodes[rear].update(kind='courtyard', label='Вход со двора', label_en='Courtyard entrance',
                               building_id=item['id'], entrance='courtyard')
            places['courtyard'] = _node(*rear)
            building['entrances'].append(_node(*rear))
        buildings.append(building)
        plots.append({'id': item['id'] + '-plot', 'building_id': item['id'], 'x': pos[0], 'y': pos[1],
                      'width': 1, 'height': 1, 'frontage': frontage,
                      'kind': 'lawn' if item['kind'] == 'park' else 'garden' if item['kind'] == 'house' else 'paved'})

    # Mark vacant plots as gardens rather than drawing empty duplicate houses.
    decoration = {slot['pos'] for slot in slots if slot['id'] not in used_slots}
    exits = {n['id']: set() for n in nodes.values()}
    by_id = {n['id']: n for n in nodes.values()}
    for a, b in edge_kinds:
        p, q = by_id[a], by_id[b]
        dx, dy = q['x'] - p['x'], q['y'] - p['y']
        exits[a].add(_DIRECTIONS[(dx, dy)])
        exits[b].add(_DIRECTIONS[(-dx, -dy)])
    occupied = {(b['x'], b['y']): b for b in buildings}
    tiles = []
    for y in range(height):
        for x in range(width):
            tile = {'x': x, 'y': y, 'kind': 'river' if x == river_x else 'garden' if (x, y) in decoration else 'grass'}
            if (x, y) in nodes:
                n = nodes[(x, y)]
                tile.update(kind='bridge' if n['kind'] == 'bridge' else 'courtyard' if n['kind'] == 'courtyard' else 'road',
                            node_id=n['id'], exits=sorted(exits[n['id']]))
            elif (x, y) in occupied:
                b = occupied[(x, y)]
                tile.update(kind='building', building_id=b['id'], building_kind=b['kind'],
                            label=b['label'], label_en=b['label_en'], frontage=b['frontage'])
                if b.get('colour'):
                    tile['colour'] = b['colour']
            tiles.append(tile)
    topology = sha256(json.dumps(sorted(edge_kinds), separators=(',', ':')).encode()).hexdigest()[:16]
    world = {'generator_version': GENERATOR_VERSION, 'seed': seed, 'layout_family': family,
             'layout_id': family + '-' + topology,
             'content_versions': {'blocks': block_library['version'], 'landmarks': landmark_library['version'],
                                  'layouts': layout_library['version']},
             'assembly': assembly, 'connectors': connectors, 'places': places, 'buildings': buildings, 'bridges': bridges,
             'bus': {'id': 'bus-5', 'label': 'Bus 5', 'label_ru': 'Автобус № 5', 'stops': []},
             'map': {'scene': 'town', 'layout_family': family, 'name_ru': layout['name_ru'], 'name_en': layout['name'],
                     'width': width, 'height': height, 'tile_size': 100, 'river_x': river_x,
                     'nodes': sorted(nodes.values(), key=lambda n: (n['y'], n['x'])),
                     'edges': [list(edge) for edge in sorted(edge_kinds)], 'tiles': tiles,
                     'street_segments': [{'from': a, 'to': b, 'kind': edge_kinds[(a, b)]} for a, b in sorted(edge_kinds)],
                     'blocks': blocks, 'plots': plots, 'terrain_features': terrain_features,
                     'districts': [{'id': f'{bank}-{row}',
                                    'name': (('North' if row == 0 else 'South' if row == rows - 1 else '') + bank).capitalize() + ' quarter',
                                    'name_ru': ('Северо-' if row == 0 else 'Юго-' if row == rows - 1 else '') + ('западный квартал' if bank == 'west' else 'восточный квартал'),
                                    'x': x, 'y': row * pitch_y, 'width': 9, 'height': 9}
                                   for bank, x in (('west', 0), ('east', pitch_x)) for row in range(rows)]}}
    validate_world(world)
    return world


def validate_world(world):
    """Validate geometry, rendered connectivity and saved landmark contracts."""
    m = world['map']
    nodes = {n['id']: n for n in m['nodes']}
    coords = {(n['x'], n['y']) for n in nodes.values()}
    if not nodes or len(nodes) != len(m['nodes']) or len(coords) != len(nodes):
        raise ValueError('Town nodes must be distinct')
    if any(type(n['x']) is not int or type(n['y']) is not int or not 0 <= n['x'] < m['width'] or not 0 <= n['y'] < m['height'] for n in nodes.values()):
        raise ValueError('Town node leaves its integer grid')
    adjacency = {nid: set() for nid in nodes}
    for a, b in m['edges']:
        if a not in nodes or b not in nodes:
            raise ValueError('Street references an unknown node')
        p, q = nodes[a], nodes[b]
        if abs(p['x'] - q['x']) + abs(p['y'] - q['y']) != 1:
            raise ValueError('Street skips a grid cell')
        if b in adjacency[a]:
            raise ValueError('Street edge is duplicated')
        adjacency[a].add(b)
        adjacency[b].add(a)
    if _connected(nodes, m['edges']) != set(nodes):
        raise ValueError('Town has disconnected streets or entrances')
    segments = {frozenset((s['from'], s['to'])): s for s in m['street_segments']}
    if len(segments) != len(m['street_segments']) or set(segments) != {frozenset(e) for e in m['edges']}:
        raise ValueError('Road artwork differs from its graph')
    if any(s['kind'] not in _PRIORITY for s in segments.values()):
        raise ValueError('Unknown street class')
    tiles = {(t['x'], t['y']): t for t in m['tiles']}
    if len(tiles) != len(m['tiles']) or set(tiles) != {(x, y) for x in range(m['width']) for y in range(m['height'])}:
        raise ValueError('Artwork must cover the grid exactly once')
    for nid, n in nodes.items():
        expected = {_DIRECTIONS[(nodes[q]['x'] - n['x'], nodes[q]['y'] - n['y'])] for q in adjacency[nid]}
        if set(tiles[(n['x'], n['y'])].get('exits', ())) != expected:
            raise ValueError('Road exits differ from actual neighbours')
    driving = {nid for segment in segments.values() if segment['kind'] != 'path' for nid in (segment['from'], segment['to'])}
    grounds = {ground['id']: ground for ground in m['blocks']}
    for ground in grounds.values():
        if ground['width'] <= 0 or ground['height'] <= 0 or ground['x'] < 0 or ground['y'] < 0 or ground['x'] + ground['width'] > m['width'] or ground['y'] + ground['height'] > m['height']:
            raise ValueError('Neighbourhood ground leaves the map')
        if any(ground['x'] < nodes[n]['x'] + .5 < ground['x'] + ground['width'] and ground['y'] < nodes[n]['y'] + .5 < ground['y'] + ground['height'] for n in driving):
            raise ValueError('Neighbourhood ground covers a road')
    occupied = {(b['x'], b['y']) for b in world['buildings']}
    if len(occupied) != len(world['buildings']) or occupied & coords:
        raise ValueError('Buildings overlap each other or the streets')
    for b in world['buildings']:
        ground = grounds.get(b['block_id'])
        if not ground or not (ground['x'] <= b['x'] < ground['x'] + ground['width'] and ground['y'] <= b['y'] < ground['y'] + ground['height']):
            raise ValueError('Building is outside its neighbourhood ground')
        if not b['entrances'] or world['places'].get(b['id']) != b['entrances'][0]:
            raise ValueError('Landmark has no primary entrance')
        for nid in b['entrances']:
            n = nodes.get(nid)
            if not n or n.get('building_id') != b['id'] or abs(n['x'] - b['x']) + abs(n['y'] - b['y']) != 1:
                raise ValueError('Landmark entrance does not meet its building')
        door = nodes[b['entrances'][0]]
        if b['frontage'] != _DIRECTIONS[(door['x'] - b['x'], door['y'] - b['y'])]:
            raise ValueError('Landmark faces away from its entrance')
        if tiles[(b['x'], b['y'])].get('building_id') != b['id']:
            raise ValueError('Building artwork differs from its landmark')
    bridge_ids = set(world['bridges'].values())
    river_x = m.get('river_x')
    if river_x is not None:
        if {n['id'] for n in nodes.values() if n['x'] == river_x} != bridge_ids:
            raise ValueError('River crossings must be declared bridges')
        for bridge in bridge_ids:
            if _connected(nodes, m['edges'], (bridge,)) != set(nodes) - {bridge}:
                raise ValueError('Closing one bridge strands part of the town')
        if _connected(nodes, m['edges'], bridge_ids) == set(nodes) - bridge_ids:
            raise ValueError('Town bypasses the river without a bridge')
    elif bridge_ids or any(tile['kind'] in ('river', 'bridge') for tile in m['tiles']):
        raise ValueError('A land town cannot contain a river or bridge')
    sockets = {_node(*c['cell']): c for block in world['assembly'] for c in block['connections']}
    opposite = {'north': 'south', 'east': 'west', 'south': 'north', 'west': 'east'}
    joined = set()
    for connector in world['connectors']:
        first, last = connector['from'], connector['to']
        a, b = sockets.get(first), sockets.get(last)
        if not a or not b or opposite[a['side']] != b['side'] or (a['kind'], a['width']) != (b['kind'], b['width']):
            raise ValueError('A block boundary socket has no compatible connection')
        if first in joined or last in joined:
            raise ValueError('A boundary socket is joined more than once')
        route = connector['path']
        if not route or route[0] != first or route[-1] != last:
            raise ValueError('Boundary connector endpoints differ from their sockets')
        if any(y not in adjacency.get(x, set()) for x, y in zip(route, route[1:])):
            raise ValueError('Boundary sockets are not joined by a real route')
        joined.update((first, last))
    if joined != set(sockets):
        raise ValueError('A block boundary socket is unconnected')
    return True
