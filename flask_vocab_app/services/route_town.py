"""Seeded delivery towns and finite, authored Russian mission content.

Geometry and mission facts are generated first. Russian lines describe those
facts; a language model never invents a street, address or accepted answer.
"""
from collections import deque
from copy import deepcopy
from hashlib import sha256
import random

from services.route_content import VERSION, SPEAKERS, line, validate_pack
from services.route_guidance import clarify_pack


GENERATOR_VERSION = 'delivery-town-v3.1'
TOWN_MISSION_IDS = (
    'town-detour', 'town-address', 'town-parcel', 'town-recipient',
    'town-courtyard', 'town-clarify', 'town-bus', 'town-guide',
)
_VARIANT_COUNTS = {'town-detour': 2, 'town-address': 2, 'town-parcel': 4, 'town-recipient': 2}
_TITLES = {
    'town-detour': ('The closed bridge', 'Закрытый мост', 'Find another river crossing.', 'Найди другой путь через реку.'),
    'town-address': ('An unfinished address', 'Неполный адрес', 'Find the house using its colour and neighbours.', 'Найди дом по цвету и соседним зданиям.'),
    'town-parcel': ('Collect the parcel', 'Забери посылку', 'Collect a parcel before taking it to its recipient.', 'Сначала забери посылку, потом доставь её.'),
    'town-recipient': ('A change of plan', 'Новый адрес', 'Find out where the recipient has gone.', 'Узнай, куда ушёл получатель.'),
    'town-courtyard': ('The courtyard entrance', 'Вход со двора', 'Find the right entrance to the building.', 'Найди нужный вход в здание.'),
    'town-clarify': ('Which bank?', 'Какой банк?', 'Ask for the missing detail before setting off.', 'Уточни адрес перед выходом.'),
    'town-bus': ('Two stops after the square', 'Две остановки после площади', 'Choose where to leave the bus.', 'Выбери нужную остановку.'),
    'town-guide': ('Give someone directions', 'Помоги найти дорогу', 'Guide a visitor from their position to the library.', 'Объясни гостю, как дойти до библиотеки.'),
}


def _rng(seed):
    return random.Random(int.from_bytes(sha256(str(seed).encode()).digest(), 'big'))


def _variant_index(mission_id, seed):
    value = int.from_bytes(sha256((mission_id + '\0' + str(seed)).encode()).digest(), 'big')
    return value % _VARIANT_COUNTS.get(mission_id, 1)


def variant_seeds(mission_id):
    """One reproducible seed for EVERY authored variant, for media preparation."""
    found = {}
    for candidate in range(10000):
        found.setdefault(_variant_index(mission_id, candidate), str(candidate))
        if len(found) == _VARIANT_COUNTS.get(mission_id, 1):
            return [found[index] for index in sorted(found)]
    raise ValueError('Could not enumerate authored mission variants')


def _node_id(x, y):
    return f'tile-{x}-{y}'


def _district(x, y):
    return 'postal' if x < 9 else 'riverside' if y < 8 else 'market'


def build_world(seed):
    """Assemble streets, enclosed blocks and their plots from a seeded plan.

    Main roads join two river crossings. Four block plans vary the western
    side street and its offset junction. Landmark plots reserve the spatial
    relationships used by the recorded directions before decoration is added.
    """
    seed = str(seed)
    rng = _rng(seed)
    plan = rng.randrange(4)
    west_inner, west_middle = (6, 7)[plan % 2], (7, 8)[plan // 2]
    width, height, river_x = 19, 15, 9
    nodes, edge_kinds = {}, {}
    places, buildings, plots = {}, [], []
    priority = {'path': 0, 'residential': 1, 'main': 2}

    def street(points, kind):
        """Create only explicit adjacent connections; nearby paths never fuse."""
        for x, y in points:
            nodes.setdefault((x, y), {'id': _node_id(x, y), 'x': x, 'y': y,
                                     'kind': 'street', 'label': 'Улица', 'label_en': 'Street',
                                     'district': _district(x, y)})
        for a, b in zip(points, points[1:]):
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
                raise ValueError('A street must connect neighbouring tiles')
            edge = tuple(sorted((_node_id(*a), _node_id(*b))))
            previous = edge_kinds.get(edge)
            if previous is None or priority[kind] > priority[previous]:
                edge_kinds[edge] = kind

    def horizontal(y, x1, x2, kind='residential'):
        street([(x, y) for x in range(x1, x2 + 1)], kind)

    def vertical(x, y1, y2, kind='residential'):
        street([(x, y) for y in range(y1, y2 + 1)], kind)

    # Through roads, followed by side streets. The short east street ends in a
    # T-junction; it does not continue through the river or repeat every block.
    horizontal(3, 2, 17, 'main')
    horizontal(12, 2, 17, 'main')
    vertical(2, 3, 12, 'main')
    vertical(17, 3, 12, 'main')
    vertical(west_inner, 3, 12)
    horizontal(west_middle, 2, west_inner)
    horizontal(8, 11, 17)
    vertical(11, 8, 12)
    # A river walk provides a pedestrian alternative, never a bus shortcut.
    vertical(10, 3, 12, 'path')
    horizontal(8, 10, 11, 'path')

    blocks = [
        {'id': 'market-square', 'x': 2.9, 'y': 3.9, 'width': west_inner - 2.8,
         'height': west_middle - 3.8, 'kind': 'market'},
        {'id': 'garden-quarter', 'x': 2.9, 'y': west_middle + .9,
         'width': west_inner - 2.8, 'height': 11.2 - west_middle, 'kind': 'park'},
        {'id': 'civic-high-street', 'x': 10.9, 'y': 3.9, 'width': 6.2,
         'height': 3.9, 'kind': 'civic'},
        {'id': 'residential-courtyard', 'x': 11.9, 'y': 8.9, 'width': 5.2,
         'height': 3.2, 'kind': 'courtyard'},
        {'id': 'north-houses', 'x': 2.8, 'y': .7, 'width': 3.4,
         'height': 2.1, 'kind': 'residential'},
    ]

    def entrance(key, pos, neighbour, kind, ru, en, building=None, entrance_kind='main'):
        if neighbour not in nodes:
            raise ValueError('An entrance must meet a road or path')
        if pos in nodes and nodes[pos].get('building_id'):
            raise ValueError('Two buildings cannot share an entrance')
        street([neighbour, pos], 'path')
        nid = _node_id(*pos)
        nodes[pos].update(kind=kind, label=ru, label_en=en, entrance=entrance_kind)
        if building:
            nodes[pos]['building_id'] = building
        places[key] = nid
        return nid

    def building(key, pos, door, neighbour, kind, ru, en, colour=None, block=None):
        if pos in nodes or any((b['x'], b['y']) == pos for b in buildings):
            raise ValueError('A building cannot cover a road or another building')
        nid = entrance(key, door, neighbour, kind, ru, en, key)
        frontage = {(0, -1): 'n', (1, 0): 'e', (0, 1): 's', (-1, 0): 'w'}[(door[0] - pos[0], door[1] - pos[1])]
        item = {'id': key, 'x': pos[0], 'y': pos[1], 'kind': kind, 'label': ru, 'label_en': en,
                'district': _district(*pos), 'entrances': [nid], 'frontage': frontage}
        if block:
            item['block_id'] = block
        if colour:
            item['colour'] = colour
            nodes[door]['colour'] = colour
        buildings.append(item)
        plots.append({'id': key + '-plot', 'building_id': key, 'x': pos[0], 'y': pos[1],
                      'width': 1, 'height': 1, 'kind': 'lawn' if kind == 'park' else 'garden' if kind == 'house' else 'paved',
                      'frontage': frontage})

    # Most destinations sit within street-enclosed blocks, with short footways
    # into their plots. They no longer hang from the town's outside boundary.
    building('post', (0, west_middle), (1, west_middle), (2, west_middle), 'post', 'Почта', 'Post office')
    building('bakery', (3, 5), (3, 4), (3, 3), 'bakery', 'Пекарня', 'Bakery', block='market-square')
    building('market', (5, 5), (5, 4), (5, 3), 'market', 'Рынок', 'Market', block='market-square')
    bank_x = rng.choice((3, 4))
    building('bank-west', (bank_x, west_middle + 2), (bank_x, west_middle + 1), (bank_x, west_middle),
             'bank-office', 'Банк', 'Bank', block='garden-quarter')
    building('park', (5, west_middle + 2), (5, west_middle + 1), (5, west_middle),
             'park', 'Парк', 'Park', block='garden-quarter')
    yellow_x, blue_x = rng.sample((3, 5), 2)
    building('yellow-house-west', (yellow_x, 1), (yellow_x, 2), (yellow_x, 3),
             'house', 'Жёлтый дом', 'Yellow house', 'yellow', 'north-houses')
    building('blue-house-west', (blue_x, 1), (blue_x, 2), (blue_x, 3),
             'house', 'Синий дом', 'Blue house', 'blue', 'north-houses')

    building('library', (11, 5), (11, 4), (11, 3), 'library', 'Библиотека', 'Library', block='civic-high-street')
    yellow_x, blue_x = rng.sample((12, 13), 2)
    building('yellow-house', (yellow_x, 5), (yellow_x, 4), (yellow_x, 3),
             'house', 'Жёлтый дом', 'Yellow house', 'yellow', 'civic-high-street')
    building('blue-house', (blue_x, 5), (blue_x, 4), (blue_x, 3),
             'house', 'Синий дом', 'Blue house', 'blue', 'civic-high-street')
    building('bank-east', (14, 5), (14, 4), (14, 3), 'bank-office', 'Банк', 'Bank', block='civic-high-street')
    building('pharmacy', (15, 5), (15, 4), (15, 3), 'pharmacy', 'Аптека', 'Pharmacy', block='civic-high-street')
    building('station', (16, 7), (16, 6), (17, 6), 'station', 'Вокзал', 'Station', block='civic-high-street')
    building('cafe', (16, 10), (16, 9), (16, 8), 'cafe', 'Кафе', 'Café', block='residential-courtyard')
    building('courtyard-house', (13, 10), (13, 9), (13, 8),
             'house', 'Дом с двором', 'Courtyard house', 'coral', 'residential-courtyard')
    rear = entrance('courtyard', (13, 11), (13, 12), 'courtyard', 'Вход со двора',
                    'Courtyard entrance', 'courtyard-house', 'courtyard')
    buildings[-1]['entrances'].append(rear)
    plots.extend([
        {'id': 'market-paving', 'x': 3.1, 'y': 5.9, 'width': west_inner - 3.1,
         'height': west_middle - 5.9, 'kind': 'paved'},
        {'id': 'park-lawn', 'x': 4.7, 'y': west_middle + 1.8, 'width': west_inner - 4.6,
         'height': 10.4 - west_middle, 'kind': 'lawn'},
        {'id': 'shared-court', 'x': 12, 'y': 10.8, 'width': 4.6, 'height': 1.1, 'kind': 'paved'},
        {'id': 'library-garden', 'x': 11, 'y': 6.1, 'width': 4.7, 'height': 1.3, 'kind': 'garden'},
    ])

    bridges = {}
    for name, y, ru, en in (('north', 3, 'Северный мост', 'North bridge'), ('south', 12, 'Южный мост', 'South bridge')):
        bridges[name] = places['bridge-' + name] = _node_id(river_x, y)
        nodes[(river_x, y)].update(kind='bridge', label=ru, label_en=en)
        places[name + '-approach'] = _node_id(river_x - 1, y)
        nodes[(river_x - 1, y)].update(kind='meeting', label='У ' + ('северного' if name == 'north' else 'южного') + ' моста',
                                     label_en=('North' if name == 'north' else 'South') + ' bridge approach')
    bus_stops = [(2, west_middle, 'bus-post', 'Почта', 'Post office'), (5, 3, 'square', 'Площадь', 'Square'),
                 (11, 3, 'bus-library', 'Библиотека', 'Library'), (17, 7, 'bus-station', 'Вокзал', 'Station')]
    for x, y, key, ru, en in bus_stops:
        places[key] = _node_id(x, y)
        if nodes[(x, y)].get('building_id'):
            raise ValueError('A bus stop cannot replace a building entrance')
        nodes[(x, y)].update(kind='bus-stop', label=ru, label_en=en, bus_stop=True)
    exits = {node['id']: [] for node in nodes.values()}
    by_id = {n['id']: n for n in nodes.values()}
    for a, b in edge_kinds:
        dx, dy = by_id[b]['x'] - by_id[a]['x'], by_id[b]['y'] - by_id[a]['y']
        direction = {(1, 0): ('e', 'w'), (-1, 0): ('w', 'e'), (0, 1): ('s', 'n'), (0, -1): ('n', 's')}[(dx, dy)]
        exits[a].append(direction[0]); exits[b].append(direction[1])
    building_tiles = {(b['x'], b['y']): b for b in buildings}
    tiles = []
    for y in range(height):
        for x in range(width):
            tile = {'x': x, 'y': y, 'kind': 'river' if x == river_x else 'grass'}
            if (x, y) in nodes:
                n = nodes[(x, y)]
                tile.update(kind='bridge' if n['kind'] == 'bridge' else 'courtyard' if n['kind'] == 'courtyard' else 'road',
                            node_id=n['id'], exits=sorted(exits[n['id']]))
            elif (x, y) in building_tiles:
                b = building_tiles[(x, y)]
                tile.update(kind='building', building_id=b['id'], building_kind=b['kind'], label=b['label'],
                            label_en=b['label_en'], frontage=b['frontage'])
                if b.get('colour'):
                    tile['colour'] = b['colour']
            tiles.append(tile)
    world = {'generator_version': GENERATOR_VERSION, 'seed': seed, 'layout_id': 'neighbourhood-' + str(plan + 1),
             'places': places, 'buildings': buildings, 'bridges': bridges,
             'bus': {'id': 'bus-5', 'label': 'Bus 5', 'label_ru': 'Автобус № 5',
                     'stops': [places[k] for k in ('bus-post', 'square', 'bus-library', 'bus-station')]},
             'map': {'scene': 'town', 'name_ru': 'ГОРОД БАРСИКА', 'name_en': 'Barsik’s town',
                     'width': width, 'height': height, 'tile_size': 100, 'river_x': river_x,
                     'nodes': sorted(nodes.values(), key=lambda n: (n['y'], n['x'])),
                     'edges': [list(e) for e in sorted(edge_kinds)], 'tiles': tiles,
                     'street_segments': [{'from': a, 'to': b, 'kind': edge_kinds[(a, b)]} for a, b in sorted(edge_kinds)],
                     'blocks': blocks, 'plots': plots,
                     'districts': [
                         {'id': 'postal', 'name': 'Postal Quarter', 'name_ru': 'Почтовый квартал', 'x': 0, 'y': 0, 'width': 9, 'height': height},
                         {'id': 'riverside', 'name': 'Riverside', 'name_ru': 'Заречье', 'x': 10, 'y': 0, 'width': 9, 'height': 8},
                         {'id': 'market', 'name': 'Garden Quarter', 'name_ru': 'Садовый квартал', 'x': 10, 'y': 8, 'width': 9, 'height': 7},
                     ]}}
    validate_world(world)
    return world


def shortest_path(world, start, target, *, avoid=(), transport=None):
    """Deterministic BFS; raises instead of silently dropping an impossible rule."""
    blocked = set(avoid)
    adjacency = {n['id']: [] for n in world['map']['nodes']}
    allowed = None
    if transport == 'bus' and world['map'].get('street_segments'):
        allowed = {frozenset((s['from'], s['to'])) for s in world['map']['street_segments'] if s['kind'] != 'path'}
    for a, b in world['map']['edges']:
        if allowed is None or frozenset((a, b)) in allowed:
            adjacency[a].append(b); adjacency[b].append(a)
    if start not in adjacency or target not in adjacency or start in blocked or target in blocked:
        raise ValueError('Unreachable mission endpoint')
    queue, parents = deque([start]), {start: None}
    while queue:
        node = queue.popleft()
        if node == target:
            result = []
            while node is not None:
                result.append(node); node = parents[node]
            return result[::-1]
        for neighbour in sorted(adjacency[node]):
            if neighbour not in parents and neighbour not in blocked:
                parents[neighbour] = node; queue.append(neighbour)
    raise ValueError('No route satisfies the mission restrictions')


def validate_world(world):
    m = world['map']
    nodes = {n['id']: n for n in m['nodes']}
    coords = {(n['x'], n['y']) for n in nodes.values()}
    if len(nodes) != len(m['nodes']) or len(coords) != len(nodes):
        raise ValueError('Duplicate town node')
    if not 50 <= len(nodes) <= 140:
        raise ValueError('Town has an unsuitable number of walkable tiles')
    tiles = {(t['x'], t['y']): t for t in m['tiles']}
    if len(tiles) != len(m['tiles']) or len(tiles) != m['width'] * m['height']:
        raise ValueError('Town artwork must cover the map exactly once')
    adjacency = {nid: set() for nid in nodes}
    for a, b in m['edges']:
        if a not in nodes or b not in nodes:
            raise ValueError('Street references an unknown tile')
        p, q = nodes[a], nodes[b]
        if abs(p['x'] - q['x']) + abs(p['y'] - q['y']) != 1:
            raise ValueError('A street must connect neighbouring tiles')
        adjacency[a].add(b); adjacency[b].add(a)
    seen, queue = set(), [next(iter(nodes))]
    while queue:
        node = queue.pop()
        if node not in seen:
            seen.add(node); queue.extend(adjacency[node] - seen)
    if seen != set(nodes) or len(m['edges']) < len(nodes):
        raise ValueError('Town must be connected and contain alternate routes')
    for n in nodes.values():
        if not 0 <= n['x'] < m['width'] or not 0 <= n['y'] < m['height']:
            raise ValueError('Town node leaves the map')
        expected = set()
        for nid in adjacency[n['id']]:
            q = nodes[nid]
            expected.add({(1, 0): 'e', (-1, 0): 'w', (0, 1): 's', (0, -1): 'n'}[(q['x']-n['x'], q['y']-n['y'])])
        if set(tiles[(n['x'], n['y'])].get('exits', [])) != expected:
            raise ValueError('Road artwork contradicts its connections')
    building_coords = {(b['x'], b['y']) for b in world['buildings']}
    if len(building_coords) != len(world['buildings']):
        raise ValueError('Two buildings occupy the same plot')
    for building in world['buildings']:
        if (building['x'], building['y']) in coords:
            raise ValueError('A building occupies a street')
        for nid in building['entrances']:
            n = nodes[nid]
            if abs(n['x']-building['x']) + abs(n['y']-building['y']) != 1 or n.get('building_id') != building['id']:
                raise ValueError('Building entrance is misplaced')
    west, east = world['places']['post'], world['places']['library']
    for bridge in world['bridges'].values():
        shortest_path(world, west, east, avoid=[bridge])
    try:
        shortest_path(world, west, east, avoid=world['bridges'].values())
    except ValueError:
        pass
    else:
        raise ValueError('A road crosses the river without a bridge')
    # New maps carry the geometry used by the renderer. Older saved maps keep
    # their existing topology and are validated without requiring new metadata.
    if m.get('street_segments'):
        segments = {frozenset((s['from'], s['to'])): s for s in m['street_segments']}
        if len(segments) != len(m['street_segments']) or set(segments) != {frozenset(e) for e in m['edges']}:
            raise ValueError('Street artwork must describe every graph edge exactly once')
        if any(s['kind'] not in ('main', 'residential', 'path') for s in segments.values()):
            raise ValueError('Unknown street class')
        driving_nodes = {nid for edge, segment in segments.items() if segment['kind'] != 'path' for nid in edge}
        blocks = {b['id']: b for b in m.get('blocks', [])}
        plots = m.get('plots', [])
        if len(blocks) != len(m.get('blocks', [])) or len({p['id'] for p in plots}) != len(plots):
            raise ValueError('Duplicate block or plot')

        def contains(rect, x, y):
            return rect['x'] < x < rect['x'] + rect['width'] and rect['y'] < y < rect['y'] + rect['height']

        for rect in [*blocks.values(), *plots]:
            if (rect['width'] <= 0 or rect['height'] <= 0 or rect['x'] < 0 or rect['y'] < 0
                    or rect['x'] + rect['width'] > m['width'] or rect['y'] + rect['height'] > m['height']):
                raise ValueError('A block or plot leaves the town')
            if rect['x'] < m['river_x'] + 1 and rect['x'] + rect['width'] > m['river_x']:
                raise ValueError('A block or plot overlaps the river')
            if any(contains(rect, nodes[nid]['x'] + .5, nodes[nid]['y'] + .5) for nid in driving_nodes):
                raise ValueError('A block or plot overlaps a road')
        for building in world['buildings']:
            block = blocks.get(building.get('block_id'))
            if building.get('block_id') and (block is None or not contains(block, building['x'] + .5, building['y'] + .5)):
                raise ValueError('A building is outside its assigned block')
            own_plots = [p for p in plots if p.get('building_id') == building['id']]
            if len(own_plots) != 1 or not contains(own_plots[0], building['x'] + .5, building['y'] + .5):
                raise ValueError('A building needs its own occupied plot')
            door = nodes[building['entrances'][0]]
            frontage = {(0, -1): 'n', (1, 0): 'e', (0, 1): 's', (-1, 0): 'w'}[(door['x'] - building['x'], door['y'] - building['y'])]
            if building.get('frontage') != frontage or own_plots[0].get('frontage') != frontage:
                raise ValueError('A building must face its entrance')
        # An enclosing street must exist on each side of an interior landmark;
        # this prevents another visually empty town with perimeter-only plots.
        def surrounded(building):
            x, y = building['x'], building['y']
            return all(any(test(nodes[nid]) for nid in driving_nodes) for test in (
                lambda n: n['x'] < x and abs(n['y'] - y) <= 1,
                lambda n: n['x'] > x and abs(n['y'] - y) <= 1,
                lambda n: n['y'] < y and abs(n['x'] - x) <= 1,
                lambda n: n['y'] > y and abs(n['x'] - x) <= 1,
            ))
        if sum(surrounded(b) for b in world['buildings']) < len(world['buildings']) * .6:
            raise ValueError('Most landmarks must occupy interior blocks')
        for a, b in zip(world['bus']['stops'], world['bus']['stops'][1:]):
            shortest_path(world, a, b, transport='bus')
    return True


def _speaker(key, name, en, role, role_en, portrait):
    return {'name': name, 'name_en': en, 'role': role, 'role_en': role_en, 'portrait': portrait}


def _leg(world, key, start, target, speaker, arrival, text, english, *, rules=None, route=None, **extra):
    route = route or shortest_path(world, start, target)
    a, b = ({n['id']: n for n in world['map']['nodes']}[nid] for nid in route[:2])
    heading = 'east' if b['x'] > a['x'] else 'west' if b['x'] < a['x'] else 'south' if b['y'] > a['y'] else 'north'
    return {'id': key, 'start': start, 'target': target, 'speaker': speaker, 'arrival_speaker': arrival,
            'heading': heading, 'route': route, 'rules': rules or [], 'objective': 'Find the next stop',
            'objective_ru': 'Найди следующую остановку', 'review_title': 'Finding the way', 'review_title_ru': 'Поиск пути',
            'lines': [line(speaker, text, english)], 'clarify': line(speaker, text, english),
            'clarify_prompt': 'Повтори, пожалуйста.', **extra}


def _rule(kind, nodes, code, en, ru):
    return {'kind': kind, 'nodes': list(nodes), 'code': code, 'en': en, 'ru': ru}


def _word(legs, index, lemma, form, meaning, case):
    source = legs[index]['lines'][0]
    return {'lemma': lemma, 'form': form, 'sentence': source['text'], 'translation': source['english'],
            'target_meaning': meaning, 'pos': 'NOUN', 'grammar': {'case': case, 'number': 'sing'}, 'leg': index}


def build_mission(world, mission_id, seed=None, *, sample=False):
    """Freeze one mission against a persisted world; no runtime AI or media calls."""
    if mission_id not in TOWN_MISSION_IDS:
        raise ValueError('Unknown town delivery')
    validate_world(world)
    mission_seed = str(seed if seed is not None else world['seed'])
    variant = _variant_index(mission_id, mission_seed)
    facts = {'variant': variant}
    p, bridges = world['places'], world['bridges']
    speakers = deepcopy(SPEAKERS)
    speakers.update({
        'neighbour': _speaker('neighbour', 'Катя', 'Katya', 'Соседка', 'Neighbour', 'anna'),
        'clerk': _speaker('clerk', 'Марина', 'Marina', 'Сотрудник банка', 'Bank worker', 'lena'),
        'visitor': _speaker('visitor', 'Павел', 'Pavel', 'Гость города', 'Visitor', 'dima'),
        'driver': _speaker('driver', 'Виктор', 'Viktor', 'Водитель', 'Driver', 'nikolai'),
        'worker': _speaker('worker', 'Сергей', 'Sergei', 'Дорожный рабочий', 'Road worker', 'boris'),
        'caretaker': _speaker('caretaker', 'Игорь', 'Igor', 'Дворник', 'Caretaker', 'nikolai'),
    })
    closure = None
    if mission_id == 'town-detour':
        closed_name, open_name = ('north', 'south') if variant == 0 else ('south', 'north')
        closed, approach = bridges[closed_name], p[closed_name + '-approach']
        facts.update(closed_bridge=closed_name, open_bridge=open_name)
        first_ru = ('Отнеси письмо в библиотеку. У северного моста рабочий Сергей подскажет, где перейти реку.' if variant == 0
                    else 'Отнеси письмо в библиотеку. У южного моста рабочий Сергей подскажет, где перейти реку.')
        first_en = f'Take the letter to the library. Sergei, the worker by the {closed_name} bridge, can tell you where to cross the river.'
        second_ru = ('Северный мост закрыт. Перейди реку по южному мосту, затем найди библиотеку.' if variant == 0
                     else 'Южный мост закрыт. Перейди реку по северному мосту, затем найди библиотеку.')
        second_en = f'The {closed_name} bridge is closed. Cross the river using the {open_name} bridge, then find the library.'
        rule = _rule('avoid', [closed], 'closed_bridge', f'The {closed_name} bridge is closed. Use the {open_name} bridge.',
                     'Северный мост закрыт. Перейди по южному мосту.' if variant == 0 else 'Южный мост закрыт. Перейди по северному мосту.')
        legs = [
            _leg(world, 'find-worker', p['post'], approach, 'postmaster', 'worker', first_ru, first_en,
                 route=shortest_path(world, p['post'], approach, avoid=[closed]), rules=[rule],
                 objective='Find Sergei by the bridge', objective_ru='Найди Сергея у моста',
                 review_title='Finding the road worker', review_title_ru='Встреча с рабочим'),
            _leg(world, 'detour', approach, p['library'], 'worker', 'lena', second_ru, second_en,
                 route=shortest_path(world, approach, p['library'], avoid=[closed]), rules=[rule],
                 objective='Deliver the letter to the library', objective_ru='Отнеси письмо в библиотеку',
                 review_title='Choosing a detour', review_title_ru='Обход закрытого моста'),
        ]
        refs = [_word(legs, 1, 'мост', 'мосту', 'bridge', 'datv'), _word(legs, 1, 'библиотека', 'библиотеку', 'library', 'accs')]
        closure = {'node_id': closed, 'reason': 'Bridge closed for repairs', 'reason_ru': 'Мост закрыт на ремонт'}
    elif mission_id == 'town-address':
        colour = 'yellow' if variant == 0 else 'blue'
        facts['house_colour'] = colour
        instruction = ('Анна живёт в жёлтом доме между библиотекой и аптекой. Отнеси ей письмо.' if variant == 0
                       else 'Анна живёт в синем доме между библиотекой и аптекой. Отнеси ей письмо.')
        legs = [
            _leg(world, 'ask-librarian', p['post'], p['library'], 'postmaster', 'lena',
                 'На конверте только имя Анны. Лена в библиотеке знает её адрес. Сначала найди Лену.',
                 'The envelope only has Anna’s name. Lena at the library knows her address. Find Lena first.',
                 objective='Ask Lena about the address', objective_ru='Узнай адрес у Лены',
                 review_title='Finding someone who knows', review_title_ru='Поиск адреса'),
            _leg(world, 'address', p['library'], p[colour + '-house'], 'lena', 'anna', instruction,
                 f'Anna lives in the {colour} house between the library and the pharmacy. Take her the letter.',
                 objective='Find Anna’s house', objective_ru='Найди дом Анны',
                 review_title='Combining address clues', review_title_ru='Поиск дома по приметам'),
        ]
        refs = [_word(legs, 1, 'дом', 'доме', 'house', 'loct'), _word(legs, 1, 'аптека', 'аптекой', 'pharmacy', 'ablt')]
    elif mission_id == 'town-parcel':
        pickup = 'bakery' if variant < 2 else 'market'
        destination = 'cafe' if variant % 2 == 0 else 'library'
        supplier = 'olya' if pickup == 'bakery' else 'boris'
        receiver = 'vera' if destination == 'cafe' else 'lena'
        facts.update(pickup=pickup, destination=destination)
        first_ru = ('Сначала забери посылку у Оли в пекарне. Она ждёт тебя.' if pickup == 'bakery'
                    else 'Сначала забери посылку у Бориса на рынке. Он ждёт тебя.')
        first_en = ('First collect the parcel from Olya at the bakery. She is expecting you.' if pickup == 'bakery'
                    else 'First collect the parcel from Boris at the market. He is expecting you.')
        second_ru = ('Теперь отнеси посылку Вере в кафе. Кафе находится к югу от вокзала.' if destination == 'cafe'
                     else 'Теперь отнеси посылку Лене в библиотеку. Библиотека находится на другом берегу реки.')
        second_en = ('Now take the parcel to Vera at the café. The café is south of the station.' if destination == 'cafe'
                     else 'Now take the parcel to Lena at the library. The library is on the other side of the river.')
        legs = [
            _leg(world, 'collect', p['post'], p[pickup], 'postmaster', supplier, first_ru, first_en,
                 objective='Collect the parcel', objective_ru='Забери посылку', arrival_item={'id': 'parcel', 'label': 'Parcel', 'label_ru': 'Посылка'},
                 arrival_text='Olya hands you the parcel.' if supplier == 'olya' else 'Boris hands you the parcel.',
                 arrival_text_ru='Оля передаёт тебе посылку.' if supplier == 'olya' else 'Борис передаёт тебе посылку.',
                 arrival_action_label='Ask where it goes', arrival_action_label_ru='Узнать адрес'),
            _leg(world, 'deliver-parcel', p[pickup], p[destination], supplier, receiver, second_ru, second_en,
                 requires_item='parcel', arrival_remove_item='parcel', objective='Deliver the parcel', objective_ru='Доставь посылку',
                 review_title='Delivering the parcel', review_title_ru='Доставка посылки'),
        ]
        refs = [_word(legs, 0, 'посылка', 'посылку', 'parcel', 'accs'),
                _word(legs, 1, 'вокзал', 'вокзала', 'station', 'gent') if destination == 'cafe' else _word(legs, 1, 'река', 'реки', 'river', 'gent')]
    elif mission_id == 'town-recipient':
        destination = 'market' if variant == 0 else 'park'
        facts['destination'] = destination
        second_ru = 'Оля уже ушла на рынок. Найди её у прилавка с фруктами.' if variant == 0 else 'Оля уже ушла в парк. Найди её у скамейки.'
        second_en = 'Olya has already gone to the market. Find her by the fruit stall.' if variant == 0 else 'Olya has already gone to the park. Find her by the bench.'
        legs = [
            _leg(world, 'old-address', p['post'], p['blue-house'], 'postmaster', 'neighbour',
                 'Отнеси письмо Оле. Она живёт в синем доме между библиотекой и аптекой.',
                 'Take the letter to Olya. She lives in the blue house between the library and the pharmacy.',
                 objective='Find Olya at home', objective_ru='Найди Олю дома',
                 arrival_text='A neighbour answers the door.', arrival_text_ru='Дверь открывает соседка.'),
            _leg(world, 'new-address', p['blue-house'], p[destination], 'neighbour', 'olya', second_ru, second_en,
                 objective='Find Olya', objective_ru='Найди Олю',
                 review_title='Following new information', review_title_ru='Изменение маршрута'),
        ]
        refs = [_word(legs, 0, 'дом', 'доме', 'house', 'loct'),
                _word(legs, 1, 'рынок', 'рынок', 'market', 'accs') if variant == 0 else _word(legs, 1, 'парк', 'парк', 'park', 'accs')]
    elif mission_id == 'town-courtyard':
        legs = [
            _leg(world, 'find-caretaker', p['post'], p['courtyard-house'], 'postmaster', 'caretaker',
                 'Отнеси письмо Николаю в дом с двором. У главного входа дежурит дворник Игорь.',
                 'Take the letter to Nikolai in the courtyard house. Igor, the caretaker, is by the main entrance.',
                 objective='Find Igor at the main entrance', objective_ru='Найди Игоря у главного входа',
                 arrival_text='Igor explains that the main door is closed.', arrival_text_ru='Игорь объясняет, что главный вход закрыт.'),
            _leg(world, 'back-door', p['courtyard-house'], p['courtyard'], 'caretaker', 'nikolai',
                 'Главный вход закрыт. Вход со двора, с южной стороны дома. Обойди дом по улице.',
                 'The main entrance is closed. The courtyard entrance is on the south side of the house. Walk around the building using the street.',
                 objective='Find the courtyard entrance', objective_ru='Найди вход со двора',
                 review_title='Choosing an entrance', review_title_ru='Выбор входа'),
        ]
        refs = [_word(legs, 1, 'двор', 'двора', 'courtyard', 'gent'), _word(legs, 1, 'вход', 'вход', 'entrance', 'nomn')]
    elif mission_id == 'town-clarify':
        legs = [_leg(world, 'clarify', p['post'], p['bank-east'], 'postmaster', 'clerk',
                     'Отнеси это письмо в банк.', 'Take this letter to the bank.',
                     questions=[{'id': 'which-bank', 'text': 'В какой банк?', 'text_en': 'Which bank?',
                                 'reply': line('postmaster', 'В банк рядом с аптекой, на другом берегу реки.', 'The bank beside the pharmacy, on the other side of the river.')}],
                     required_question='which-bank', objective='Ask which bank needs the letter', objective_ru='Узнай, в какой банк нужно отнести письмо',
                     review_title='Clarifying an address', review_title_ru='Уточнение адреса')]
        refs = [_word(legs, 0, 'банк', 'банк', 'bank', 'accs')]
    elif mission_id == 'town-bus':
        bus = deepcopy(world['bus'])
        bus.update(board=bus['stops'][0], alight=bus['stops'][-1])
        bus_route = [bus['board']]
        for a, b in zip(bus['stops'], bus['stops'][1:]):
            bus_route.extend(shortest_path(world, a, b, transport='bus')[1:])
        legs = [
            _leg(world, 'reach-stop', p['post'], bus['board'], 'postmaster', 'driver',
                 'Сегодня письмо нужно доставить на вокзал. Автобус номер пять останавливается рядом с почтой.',
                 'Today the letter needs to reach the station. Bus five stops beside the post office.',
                 objective='Find the bus stop', objective_ru='Найди автобусную остановку',
                 arrival_action_label='Talk to the driver', arrival_action_label_ru='Поговорить с водителем'),
            _leg(world, 'bus-ride', bus['board'], bus['alight'], 'driver', 'dima',
                 'Садись в автобус номер пять. Выйди на второй остановке после площади.',
                 'Take bus five. Get off at the second stop after the square.', route=bus_route, transport=bus,
                 objective='Choose where to get off', objective_ru='Выбери, где выйти',
                 review_title='Counting stops', review_title_ru='Выбор остановки'),
            _leg(world, 'station-door', bus['alight'], p['station'], 'dima', 'irina',
                 'Ирина ждёт письмо у входа в вокзал. Отнеси его ей.',
                 'Irina is waiting for the letter at the station entrance. Take it to her.',
                 objective='Deliver the letter at the station', objective_ru='Доставь письмо на вокзал'),
        ]
        refs = [_word(legs, 1, 'автобус', 'автобус', 'bus', 'accs'), _word(legs, 1, 'площадь', 'площади', 'square', 'gent')]
    else:
        legs = [_leg(world, 'guide', p['post'], p['library'], 'visitor', 'visitor',
                     'Как пройти к библиотеке? Я стою у почты и смотрю на восток. Подскажи дорогу, пожалуйста.',
                     'How do I get to the library? I am outside the post office, facing east. Please tell me the way.',
                     guide=True, heading='east', objective='Guide Pavel to the library', objective_ru='Проведи Павла к библиотеке',
                     review_title='Giving directions', review_title_ru='Объяснение пути')]
        refs = [_word(legs, 0, 'библиотека', 'библиотеке', 'library', 'datv'), _word(legs, 0, 'почта', 'почты', 'post office', 'gent')]
    recipient = legs[-1]['arrival_speaker']
    title, title_ru, summary, summary_ru = _TITLES[mission_id]
    map_data = deepcopy(world['map'])
    if closure:
        map_data['closures'] = [closure]
    ending_text = 'Спасибо за посылку, Барсик!' if mission_id == 'town-parcel' else 'Спасибо за помощь, Барсик!' if mission_id == 'town-guide' else 'Спасибо за письмо, Барсик!'
    ending_en = 'Thank you for the parcel, Barsik!' if mission_id == 'town-parcel' else 'Thank you for your help, Barsik!' if mission_id == 'town-guide' else 'Thank you for the letter, Barsik!'
    completion = ('You helped Pavel reach the library.', 'Ты помог Павлу дойти до библиотеки.') if mission_id == 'town-guide' else ('The parcel reached its recipient.', 'Посылка доставлена получателю.') if mission_id == 'town-parcel' else ('The letter reached its recipient.', 'Письмо доставлено получателю.')
    pack = {'version': VERSION, 'lesson_version': GENERATOR_VERSION + ':' + mission_id, 'mission_id': mission_id,
            'generator_version': GENERATOR_VERSION, 'mission_seed': mission_seed, 'mission_facts': facts,
            'town': deepcopy(world), 'map': map_data, 'area': 'town', 'title': title, 'title_ru': title_ru,
            'summary': summary, 'summary_ru': summary_ru, 'source': {'kind': 'route', 'title': 'Town deliveries', 'href': '#games/directions'},
            'options': {'source': 'authored', 'word_policy': 'mixed-v1'}, 'sample': sample, 'speakers': speakers,
            'recipient_id': recipient, 'recipient': speakers[recipient], 'envelope': 'Посылка' if mission_id == 'town-parcel' else 'Помощь гостю' if mission_id == 'town-guide' else 'Письмо',
            'legs': legs, 'rounds': [], 'vocabulary_refs': refs, 'media_texts': [],
            'ending': line(recipient, ending_text, ending_en), 'completion_text': completion[0], 'completion_text_ru': completion[1]}
    pack = clarify_pack(pack)
    validate_mission(pack)
    return pack


def validate_mission(pack):
    validate_pack(pack)
    world, p = pack['town'], pack['town']['places']
    nodes = {n['id']: n for n in pack['map']['nodes']}
    inventory = set()
    for leg in pack['legs']:
        if leg.get('requires_item') and leg['requires_item'] not in inventory:
            raise ValueError('Delivery requires an item that cannot be collected')
        if leg.get('arrival_item'):
            inventory.add(leg['arrival_item']['id'])
        if leg.get('arrival_remove_item'):
            if leg['arrival_remove_item'] not in inventory:
                raise ValueError('Delivery removes an item that is not carried')
            inventory.remove(leg['arrival_remove_item'])
        if leg.get('required_question') not in {None, *(q['id'] for q in leg.get('questions', []))}:
            raise ValueError('Required clarification is unavailable')
        for q in leg.get('questions', []):
            if not q.get('text') or not q.get('text_en') or not all(q.get('reply', {}).get(k) for k in ('text', 'english', 'audio_url')):
                raise ValueError('Clarification is incomplete')
        if leg.get('transport'):
            bus = leg['transport']
            if leg['start'] != bus['board'] or leg['target'] != bus['alight'] or len(set(bus['stops'])) != len(bus['stops']):
                raise ValueError('Bus endpoints or stops are inconsistent')
            if bus['stops'].index(bus['alight']) - bus['stops'].index(p['square']) != 2:
                raise ValueError('Bus instruction does not describe the alighting stop')
            for a, b in zip(bus['stops'], bus['stops'][1:]):
                shortest_path(world, a, b, transport='bus')
            if world['map'].get('street_segments'):
                driving_edges = {frozenset((s['from'], s['to'])) for s in world['map']['street_segments'] if s['kind'] != 'path'}
                if any(frozenset((a, b)) not in driving_edges for a, b in zip(leg['route'], leg['route'][1:])):
                    raise ValueError('A bus route enters a pedestrian path')
            visited_stops = [nid for nid in leg['route'] if nid in bus['stops']]
            if visited_stops != bus['stops']:
                raise ValueError('A bus route visits its stops in the wrong order')
        for closed in pack['map'].get('closures', []):
            if closed['node_id'] in leg['route']:
                raise ValueError('Prepared route enters a closed place')
    if pack['mission_id'] in ('town-address', 'town-recipient'):
        buildings = {b['id']: b for b in world['buildings']}
        a, b = buildings['library'], buildings['pharmacy']
        colour = pack['mission_facts']['house_colour'] if pack['mission_id'] == 'town-address' else 'blue'
        matches = [h for h in buildings.values() if h['kind'] == 'house' and h.get('colour') == colour
                   and h['y'] == a['y'] == b['y'] and a['x'] < h['x'] < b['x']]
        address_leg = pack['legs'][-1] if pack['mission_id'] == 'town-address' else pack['legs'][0]
        if len(matches) != 1 or address_leg['target'] not in matches[0]['entrances']:
            raise ValueError('Address clues do not identify exactly one house')
    if pack['mission_id'] == 'town-courtyard':
        target = nodes[pack['legs'][-1]['target']]
        front = nodes[p['courtyard-house']]
        if target.get('entrance') != 'courtyard' or target['building_id'] != front['building_id'] or target['y'] <= front['y']:
            raise ValueError('Courtyard description contradicts the building')
    if pack['mission_id'] == 'town-parcel':
        buildings = {b['id']: b for b in world['buildings']}
        pickup, destination = (buildings[pack['mission_facts'][key]] for key in ('pickup', 'destination'))
        if destination['id'] == 'cafe' and destination['y'] <= buildings['station']['y']:
            raise ValueError('The café must be south of the station')
        if destination['id'] == 'library':
            bridge = nodes[world['bridges']['north']]
            if not pickup['x'] < bridge['x'] < destination['x']:
                raise ValueError('The library must be across the river from the pickup')
    if pack['mission_id'] == 'town-clarify':
        banks = [b for b in world['buildings'] if b['kind'] == 'bank-office']
        pharmacy = next(b for b in world['buildings'] if b['id'] == 'pharmacy')
        matches = [b for b in banks if abs(b['x'] - pharmacy['x']) + abs(b['y'] - pharmacy['y']) == 1]
        if len(banks) < 2 or len(matches) != 1 or pack['legs'][0]['target'] not in matches[0]['entrances']:
            raise ValueError('Clarification does not resolve the ambiguous bank')
        if not nodes[p['post']]['x'] < nodes[world['bridges']['north']]['x'] < matches[0]['x']:
            raise ValueError('The bank must be across the river from the post office')
    return True


def catalogue():
    return [{'mission_id': key, 'title': values[0], 'title_ru': values[1], 'area': 'town',
             'summary': values[2], 'summary_ru': values[3]} for key, values in _TITLES.items()]


def all_audio():
    """Every finite dialogue line; identical text IDs are shared across towns."""
    world = build_world('audio-catalogue')
    unique = {}
    for mission_id in TOWN_MISSION_IDS:
        for seed in variant_seeds(mission_id):
            pack = build_mission(world, mission_id, seed=seed)
            for leg in pack['legs']:
                for item in [*leg['lines'], leg['clarify'], *(q['reply'] for q in leg.get('questions', []))]:
                    unique[item['id']] = dict(item, speaker=leg['speaker'])
            unique[pack['ending']['id']] = dict(pack['ending'], speaker=pack['recipient_id'])
    return list(unique.values())
