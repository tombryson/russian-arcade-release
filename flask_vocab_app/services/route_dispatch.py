"""Compose deliveries from town facts, with a finite recorded sentence library.

The town is a reusable graph. A delivery independently chooses its collection
point, recipient, address and encounters; it is not an index into whole stories.
Russian case forms are authored explicitly, and spatial clues are checked before
they can be selected. Session snapshots contain the complete resolved assignment.
"""
from copy import deepcopy
from hashlib import sha256
import json
import random

from services.route_content import VERSION, SPEAKERS, line, validate_pack
from services.route_town import shortest_path, validate_world


MISSION_ID = 'town-generated'
GENERATOR_VERSION = 'delivery-dispatch-v1'
RECIPIENTS = {
    'anna': {'genitive': 'Анны', 'dative': 'Анне', 'left': 'Анна уже ушла.'},
    'nikolai': {'genitive': 'Николая', 'dative': 'Николаю', 'left': 'Николай уже ушёл.'},
    'vera': {'genitive': 'Веры', 'dative': 'Вере', 'left': 'Вера уже ушла.'},
}
PICKUPS = {
    'bakery': ('у входа в пекарню', 'outside the bakery entrance'),
    'market': ('у входа на рынок', 'at the market entrance'),
    'park': ('у входа в парк', 'at the park entrance'),
    'library': ('у входа в библиотеку', 'outside the library entrance'),
    'cafe': ('у входа в кафе', 'outside the café entrance'),
    'station': ('у входа в здание вокзала', 'outside the station entrance'),
}

# The predicates, not the prose, determine whether a clue is true and unique.
# Specific Russian forms belong to each sentence; there is no concatenation of
# translated dictionary headwords or guessed declensions.
CLUES = (
    {'id': 'library-river', 'place': 'library', 'kind': 'library', 'relation': 'between', 'anchors': ['river', 'yellow-house'],
     'ru': 'Найди библиотеку между рекой и жёлтым домом.', 'en': 'Find the library between the river and the yellow house.',
     'word': ('библиотека', 'библиотеку', 'library', 'accs')},
    {'id': 'cafe-station', 'place': 'cafe', 'kind': 'cafe', 'relation': 'south', 'anchors': ['station'],
     'ru': 'Найди кафе к югу от вокзала.', 'en': 'Find the café south of the station.',
     'word': ('вокзал', 'вокзала', 'station', 'gent')},
    {'id': 'station-cafe', 'place': 'station', 'kind': 'station', 'relation': 'north', 'anchors': ['cafe'],
     'ru': 'Найди вокзал к северу от кафе.', 'en': 'Find the station north of the café.',
     'word': ('вокзал', 'вокзал', 'station', 'accs')},
    {'id': 'bakery-market', 'place': 'bakery', 'kind': 'bakery', 'relation': 'same-street', 'anchors': ['market'],
     'ru': 'Найди пекарню на той же улице, что и рынок.', 'en': 'Find the bakery on the same street as the market.',
     'word': ('пекарня', 'пекарню', 'bakery', 'accs')},
    {'id': 'market-bakery', 'place': 'market', 'kind': 'market', 'relation': 'same-street', 'anchors': ['bakery'],
     'ru': 'Найди рынок на той же улице, что и пекарня.', 'en': 'Find the market on the same street as the bakery.',
     'word': ('рынок', 'рынок', 'market', 'accs')},
    {'id': 'park-market', 'place': 'park', 'kind': 'park', 'relation': 'south', 'anchors': ['market'],
     'ru': 'Найди парк к югу от рынка.', 'en': 'Find the park south of the market.',
     'word': ('парк', 'парк', 'park', 'accs')},
    {'id': 'pharmacy-bank', 'place': 'pharmacy', 'kind': 'pharmacy', 'relation': 'beside', 'anchors': ['bank-east'],
     'ru': 'Найди аптеку рядом с банком.', 'en': 'Find the pharmacy beside the bank.',
     'word': ('аптека', 'аптеку', 'pharmacy', 'accs')},
    {'id': 'bank-pharmacy', 'place': 'bank-east', 'kind': 'bank-office', 'relation': 'beside', 'anchors': ['pharmacy'],
     'ru': 'Тебе нужен банк рядом с аптекой.', 'en': 'You need the bank beside the pharmacy.',
     'word': ('аптека', 'аптекой', 'pharmacy', 'ablt')},
    {'id': 'bank-post', 'place': 'bank-west', 'kind': 'bank-office', 'relation': 'same-bank', 'anchors': ['post'],
     'ru': 'Тебе нужен банк на том же берегу, что и почта.', 'en': 'You need the bank on the same side of the river as the post office.',
     'word': ('берег', 'берегу', 'riverbank', 'loct')},
    {'id': 'yellow-address', 'place': 'yellow-house', 'kind': 'house', 'colour': 'yellow', 'relation': 'between', 'anchors': ['library', 'pharmacy'],
     'ru': 'Найди жёлтый дом между библиотекой и аптекой.', 'en': 'Find the yellow house between the library and the pharmacy.',
     'word': ('дом', 'дом', 'house', 'accs')},
    {'id': 'blue-address', 'place': 'blue-house', 'kind': 'house', 'colour': 'blue', 'relation': 'between', 'anchors': ['library', 'pharmacy'],
     'ru': 'Найди синий дом между библиотекой и аптекой.', 'en': 'Find the blue house between the library and the pharmacy.',
     'word': ('библиотека', 'библиотекой', 'library', 'ablt')},
    {'id': 'yellow-post', 'place': 'yellow-house-west', 'kind': 'house', 'colour': 'yellow', 'relation': 'same-bank', 'anchors': ['post'],
     'ru': 'Найди жёлтый дом на том же берегу, что и почта.', 'en': 'Find the yellow house on the same side of the river as the post office.',
     'word': ('берег', 'берегу', 'riverbank', 'loct')},
    {'id': 'blue-post', 'place': 'blue-house-west', 'kind': 'house', 'colour': 'blue', 'relation': 'same-bank', 'anchors': ['post'],
     'ru': 'Найди синий дом на том же берегу, что и почта.', 'en': 'Find the blue house on the same side of the river as the post office.',
     'word': ('берег', 'берегу', 'riverbank', 'loct')},
)
CLUE_BY_ID = {clue['id']: clue for clue in CLUES}
AMBIGUITIES = {
    'bank-office': ('Получатель сейчас в банке.', 'The recipient is at a bank.', 'В какой банк идти?', 'Which bank should I go to?'),
    'yellow': ('Получатель сейчас в жёлтом доме.', 'The recipient is in a yellow house.', 'В каком жёлтом доме?', 'Which yellow house?'),
    'blue': ('Получатель сейчас в синем доме.', 'The recipient is in a blue house.', 'В каком синем доме?', 'Which blue house?'),
}


def catalogue():
    return [{'mission_id': MISSION_ID, 'title': 'A new delivery', 'title_ru': 'Новая доставка', 'area': 'town',
             'summary': 'Meet the people in town and follow their Russian directions.',
             'summary_ru': 'Знакомься с жителями города и следуй их указаниям.'}]


def _clip(speaker, ru, en):
    return line(speaker, ru, en)


def _pickup_intro(kind, recipient):
    ru = 'письмо' if kind == 'letter' else 'посылку'
    return _clip('postmaster', f'Забери у Саши {ru} для {RECIPIENTS[recipient]["genitive"]}.',
                 f'Collect a {kind} for {SPEAKERS[recipient]["name_en"]} from Sasha.')


def _pickup_address(place):
    ru, en = PICKUPS[place]
    return _clip('postmaster', f'Саша ждёт тебя {ru}.', f'Sasha is waiting {en}.')


def _handover(kind, recipient):
    ru = 'письмо' if kind == 'letter' else 'посылку'
    return _clip('sasha', f'Отнеси это {ru} {RECIPIENTS[recipient]["dative"]}.' if kind == 'letter'
                 else f'Отнеси эту {ru} {RECIPIENTS[recipient]["dative"]}.',
                 f'Take this {kind} to {SPEAKERS[recipient]["name_en"]}.')


def _direction(speaker, clue):
    return _clip(speaker, clue['ru'], clue['en'])


def _entrance(speaker):
    return _clip(speaker, 'Подойди к входу и остановись там.', 'Walk up to the entrance and stop there.')


def _worker_address(name):
    adjective = 'северным' if name == 'north' else 'южным'
    return _clip('sasha', f'На этом берегу перед {adjective} мостом тебя ждёт рабочий Сергей.',
                 f'Sergei, the road worker, is waiting on this bank, just before the {name} bridge.')


def _worker_stop():
    return _clip('sasha', 'Подойди к Сергею перед мостом: он объяснит, где перейти реку.',
                 'Meet Sergei before the bridge; he will tell you where to cross the river.')


def _closure(name):
    adjective = 'Северный' if name == 'north' else 'Южный'
    return _clip('worker', f'{adjective} мост закрыт.', f'The {name} bridge is closed.')


def _crossing(name):
    adjective = 'северному' if name == 'north' else 'южному'
    return _clip('worker', f'Перейди реку по {adjective} мосту.', f'Cross the river using the {name} bridge.')


def _relocation(recipient):
    return _clip('neighbour', RECIPIENTS[recipient]['left'], f'{SPEAKERS[recipient]["name_en"]} has already left.')


def _ending(kind, recipient):
    return _clip(recipient, 'Спасибо за письмо, Барсик!' if kind == 'letter' else 'Спасибо за посылку, Барсик!',
                 f'Thank you for the {kind}, Barsik!')


def clue_matches(world, clue):
    """Return every building satisfying a clue, without trusting its place ID."""
    buildings = {building['id']: building for building in world['buildings']}
    nodes = {node['id']: node for node in world['map']['nodes']}
    river_x = world['map']['river_x']
    anchors = [({'x': river_x, 'y': None} if key == 'river' else buildings[key]) for key in clue['anchors']]

    def frontage_street(building):
        entrance = building['entrances'][0]
        neighbours = [b if a == entrance else a for a, b in world['map']['edges'] if entrance in (a, b)]
        return [nodes[nid] for nid in neighbours if not nodes[nid].get('building_id')]

    def matches(building):
        if building['kind'] != clue['kind'] or (clue.get('colour') and building.get('colour') != clue['colour']):
            return False
        x, y = building['x'], building['y']
        anchor = anchors[0]
        relation = clue['relation']
        if relation == 'between':
            left, right = sorted(anchors, key=lambda value: value['x'])
            return left['x'] < x < right['x'] and all(a['y'] is None or a['y'] == y for a in anchors)
        if relation == 'beside':
            return abs(x - anchor['x']) + abs(y - anchor['y']) == 1
        if relation == 'same-bank':
            return (x - river_x) * (anchor['x'] - river_x) > 0
        if relation in ('south', 'north'):
            return x == anchor['x'] and (y > anchor['y'] if relation == 'south' else y < anchor['y'])
        if relation == 'same-street':
            edges = {frozenset(edge) for edge in world['map']['edges']}
            coordinates = {(node['x'], node['y']): node['id'] for node in nodes.values()}
            for a in frontage_street(building):
                for b in frontage_street(anchor):
                    if a['y'] != b['y']:
                        continue
                    span = [coordinates.get((x, a['y'])) for x in range(min(a['x'], b['x']), max(a['x'], b['x']) + 1)]
                    if all(span) and all(frozenset(edge) in edges for edge in zip(span, span[1:])):
                        return True
            return False
        raise ValueError('Unknown delivery clue relationship')

    return [building['id'] for building in buildings.values() if matches(building)]


def _leg(world, key, start, target, speaker, arrival, lines, *, avoid=(), **extra):
    route = shortest_path(world, start, target, avoid=avoid)
    if len(route) < 2:
        raise ValueError('An encounter must require travelling to another place')
    nodes = {node['id']: node for node in world['map']['nodes']}
    a, b = nodes[route[0]], nodes[route[1]]
    heading = 'east' if b['x'] > a['x'] else 'west' if b['x'] < a['x'] else 'south' if b['y'] > a['y'] else 'north'
    rules = [{'kind': 'avoid', 'nodes': list(avoid), 'code': 'closed_bridge',
              'en': 'This bridge is closed. Use the other crossing.', 'ru': 'Этот мост закрыт. Перейди реку по другому мосту.'}] if avoid else []
    return {'id': key, 'start': start, 'target': target, 'speaker': speaker, 'arrival_speaker': arrival,
            'heading': heading, 'route': route, 'rules': rules, 'lines': lines, 'clarify': lines[-1],
            'clarify_prompt': 'Повтори, пожалуйста.', 'objective': 'Follow the directions', 'objective_ru': 'Следуй указаниям',
            'review_title': 'Following the directions', 'review_title_ru': 'Понимание указаний', **extra}


def _compose(world, rng, *, sample):
    p, bridges = world['places'], world['bridges']
    nodes = {node['id']: node for node in world['map']['nodes']}
    by_coordinate = {(node['x'], node['y']): node['id'] for node in nodes.values()}
    available = [clue for clue in CLUES if clue_matches(world, clue) == [clue['place']]]
    pickup = rng.choice(tuple(PICKUPS))
    candidates = [clue for clue in available if clue['place'] != pickup and len(shortest_path(world, p[pickup], p[clue['place']])) >= 5]
    if not candidates:
        raise ValueError('The town has no suitable delivery addresses')
    first_clue = rng.choice(candidates)
    recipient, kind = rng.choice(tuple(RECIPIENTS)), rng.choice(('letter', 'parcel'))
    relocate = rng.random() < .45
    later = [clue for clue in available if clue['place'] not in (pickup, first_clue['place'])
             and len(shortest_path(world, p[first_clue['place']], p[clue['place']])) >= 5]
    relocate = relocate and bool(later)
    final_clue = rng.choice(later) if relocate else first_clue
    river_x = world['map']['river_x']
    opposite_banks = (nodes[p[pickup]]['x'] - river_x) * (nodes[p[first_clue['place']]]['x'] - river_x) < 0
    bridge_encounter = opposite_banks and rng.random() < .6
    ambiguity_key = first_clue.get('colour', first_clue['kind'])
    clarify = not bridge_encounter and ambiguity_key in AMBIGUITIES and rng.random() < .5
    speakers = deepcopy(SPEAKERS)
    speakers['sasha'].update(role='Знакомый', role_en='Friend')
    speakers.update({
        'worker': {'name': 'Сергей', 'name_en': 'Sergei', 'role': 'Дорожный рабочий', 'role_en': 'Road worker', 'portrait': 'boris'},
        'neighbour': {'name': 'Катя', 'name_en': 'Katya', 'role': 'Жительница города', 'role_en': 'Local resident', 'portrait': 'anna'},
    })
    item = {'id': kind, 'label': 'Letter' if kind == 'letter' else 'Parcel', 'label_ru': 'Письмо' if kind == 'letter' else 'Посылка'}
    first_lines = [_pickup_intro(kind, recipient), _pickup_address(pickup)]
    legs = [_leg(world, 'collect', p['post'], p[pickup], 'postmaster', 'sasha', first_lines,
                 arrival_item=item, arrival_text=f'Sasha hands you the {kind}.',
                 arrival_text_ru='Саша передаёт тебе письмо.' if kind == 'letter' else 'Саша передаёт тебе посылку.',
                 arrival_action_label='Ask where to take it', arrival_action_label_ru='Узнать адрес')]
    events = [{'kind': 'collection', 'leg': 0, 'place': pickup}]
    cluefacts, closures, blocked = [], [], []
    departure, guide = p[pickup], 'sasha'
    arrival = 'neighbour' if relocate else recipient
    onward_lines = [_handover(kind, recipient)]
    if bridge_encounter:
        closed_name = rng.choice(('north', 'south'))
        open_name = 'south' if closed_name == 'north' else 'north'
        closed, bridge = bridges[closed_name], nodes[bridges[closed_name]]
        bank_x = river_x - 1 if nodes[departure]['x'] < river_x else river_x + 1
        approach = by_coordinate[(bank_x, bridge['y'])]
        blocked = [closed]
        closures = [{'node_id': closed, 'from_leg': len(legs), 'reason': 'Bridge closed for repairs', 'reason_ru': 'Мост закрыт на ремонт'}]
        legs.append(_leg(world, 'meet-worker', departure, approach, guide, 'worker',
                         [*onward_lines, _worker_address(closed_name), _worker_stop()], avoid=blocked,
                         bridge_meeting=True, visible_contacts=[{'position': approach, 'speaker': 'worker'}],
                         requires_item=kind, clarify=_worker_address(closed_name)))
        events.append({'kind': 'closed-crossing', 'leg': len(legs) - 1, 'closed_bridge': closed_name, 'open_bridge': open_name})
        departure, guide = approach, 'worker'
        onward_lines = [_closure(closed_name), _crossing(open_name)]
    direction = _direction(guide, first_clue)
    extra = {'clarify': direction, 'requires_item': kind}
    if bridge_encounter:
        extra['crossing'] = {'bridge': bridges[open_name],
                             'direction': 'east' if nodes[p[first_clue['place']]]['x'] > river_x else 'west',
                             'label': f'Cross by the {open_name} bridge',
                             'label_ru': 'Перейти по ' + ('южному' if open_name == 'south' else 'северному') + ' мосту'}
    if clarify:
        vague, vague_en, question, question_en = AMBIGUITIES[ambiguity_key]
        incomplete_address = _clip(guide, vague, vague_en)
        onward_lines.append(incomplete_address)
        extra.update(questions=[{'id': 'which-address', 'text': question, 'text_en': question_en, 'reply': direction}],
                     required_question='which-address', clarify=incomplete_address)
        events.append({'kind': 'clarification', 'leg': len(legs), 'clue_id': first_clue['id']})
    else:
        onward_lines.append(direction)
    onward_lines.append(_entrance(guide))
    if relocate:
        extra.update(arrival_text='Katya comes to meet you.', arrival_text_ru='Тебя встречает Катя.')
    else:
        extra['arrival_remove_item'] = kind
    cluefacts.append({'leg': len(legs), 'clue_id': first_clue['id'], 'place': first_clue['place'],
                      'question': 'which-address' if clarify else None})
    legs.append(_leg(world, 'find-recipient', departure, p[first_clue['place']], guide, arrival, onward_lines,
                     avoid=blocked, **extra))
    if relocate:
        events.append({'kind': 'relocation', 'leg': len(legs), 'from': first_clue['place'], 'to': final_clue['place']})
        direction = _direction('neighbour', final_clue)
        cluefacts.append({'leg': len(legs), 'clue_id': final_clue['id'], 'place': final_clue['place'], 'question': None})
        legs.append(_leg(world, 'new-address', p[first_clue['place']], p[final_clue['place']], 'neighbour', recipient,
                         [_relocation(recipient), direction, _entrance('neighbour')], avoid=blocked,
                         clarify=direction, requires_item=kind, arrival_remove_item=kind))
    facts = {'pickup': pickup, 'recipient': recipient, 'item': kind, 'destination': final_clue['place'],
             'events': events, 'clues': cluefacts, 'waypoints': [leg['target'] for leg in legs]}
    signature = json.dumps(facts, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    facts['fingerprint'] = sha256(signature.encode()).hexdigest()[:24]
    vocabulary = [{'lemma': 'письмо' if kind == 'letter' else 'посылка',
                   'form': 'письмо' if kind == 'letter' else 'посылку',
                   'sentence': first_lines[0]['text'], 'translation': first_lines[0]['english'],
                   'target_meaning': kind, 'pos': 'NOUN', 'grammar': {'case': 'accs', 'number': 'sing'}, 'leg': 0}]
    for fact in cluefacts:
        # A required-question reply is genuinely received only after asking.
        # Keep vocabulary extraction to regular delivered lines, as required by
        # the existing saved-card provenance validator.
        if fact['question']:
            continue
        clue = CLUE_BY_ID[fact['clue_id']]
        source = next(item for item in legs[fact['leg']]['lines'] if item['text'] == clue['ru'])
        lemma, form, meaning, case = clue['word']
        vocabulary.append({'lemma': lemma, 'form': form, 'sentence': source['text'], 'translation': source['english'],
                           'target_meaning': meaning, 'pos': 'NOUN', 'grammar': {'case': case, 'number': 'sing'}, 'leg': fact['leg']})
    map_data = deepcopy(world['map'])
    map_data['closures'] = closures
    choice = catalogue()[0]
    return {'version': VERSION, 'lesson_version': GENERATOR_VERSION + ':' + facts['fingerprint'], 'mission_id': MISSION_ID,
            'generator_version': GENERATOR_VERSION, 'mission_facts': facts, 'town': deepcopy(world), 'map': map_data,
            'area': 'town', 'title': choice['title'], 'title_ru': choice['title_ru'], 'summary': choice['summary'], 'summary_ru': choice['summary_ru'],
            'source': {'kind': 'route', 'title': 'Town deliveries', 'href': '#games/directions'},
            'options': {'source': 'composed', 'word_policy': 'mixed-v1'}, 'sample': sample,
            'speakers': speakers, 'recipient_id': recipient, 'recipient': speakers[recipient], 'envelope': item['label_ru'],
            'legs': legs, 'rounds': [], 'vocabulary_refs': vocabulary, 'media_texts': [],
            'ending': _ending(kind, recipient), 'completion_text': f'The {kind} reached its recipient.',
            'completion_text_ru': 'Письмо доставлено получателю.' if kind == 'letter' else 'Посылка доставлена получателю.'}


def validate_mission(pack):
    validate_pack(pack)
    world = pack['town']
    if pack['map']['nodes'] != world['map']['nodes'] or pack['map']['edges'] != world['map']['edges']:
        raise ValueError('Delivery geography differs from the saved town')
    facts, legs = pack['mission_facts'], pack['legs']
    if not 2 <= len(legs) <= 4 or len({leg['target'] for leg in legs}) != len(legs):
        raise ValueError('A delivery needs two to four distinct encounters')
    if facts['waypoints'] != [leg['target'] for leg in legs]:
        raise ValueError('Delivery waypoints differ from their encounters')
    if legs[-1]['target'] != world['places'][facts['destination']] or legs[-1]['arrival_speaker'] != facts['recipient']:
        raise ValueError('The final encounter must reach the recipient')
    for fact in facts['clues']:
        clue = CLUE_BY_ID[fact['clue_id']]
        leg = legs[fact['leg']]
        if clue_matches(world, clue) != [fact['place']] or leg['target'] != world['places'][fact['place']]:
            raise ValueError('A spoken clue must identify exactly its actual destination')
        received = [*leg['lines'], *(question['reply'] for question in leg.get('questions', []))]
        if not any(item['text'] == clue['ru'] and item['english'] == clue['en'] for item in received):
            raise ValueError('A delivery clue must be included in the encounter')
    inventory = set()
    for index, leg in enumerate(legs):
        if leg.get('requires_item') and leg['requires_item'] not in inventory:
            raise ValueError('The item must be collected before delivery')
        if leg.get('arrival_item'):
            inventory.add(leg['arrival_item']['id'])
        if leg.get('arrival_remove_item'):
            inventory.remove(leg['arrival_remove_item'])
        if leg.get('required_question') not in {None, *(question['id'] for question in leg.get('questions', []))}:
            raise ValueError('A required question has no reply')
        for closure in pack['map']['closures']:
            if closure['from_leg'] <= index and closure['node_id'] in leg['route']:
                raise ValueError('A route crosses a closed bridge')
        crossing = leg.get('crossing')
        if crossing and crossing['bridge'] not in leg['route']:
            raise ValueError('The instructed crossing must be on the route')
    if inventory:
        raise ValueError('The delivery must hand over its collected item')
    return True


def build_mission(world, seed, exclude_fingerprints=(), *, sample=False):
    validate_world(world)
    rng = random.Random(int.from_bytes(sha256(str(seed).encode()).digest(), 'big'))
    excluded = set(exclude_fingerprints)
    for _ in range(256):
        pack = _compose(world, rng, sample=sample)
        if pack['mission_facts']['fingerprint'] not in excluded:
            pack['mission_seed'] = str(seed)
            validate_mission(pack)
            return pack
    raise ValueError('Could not create a delivery different from recent assignments')


def all_audio():
    """Exhaust the sentence library without sampling missions or making calls."""
    clips = []
    for recipient in RECIPIENTS:
        for kind in ('letter', 'parcel'):
            clips.extend([_pickup_intro(kind, recipient), _handover(kind, recipient), _ending(kind, recipient)])
        clips.append(_relocation(recipient))
    clips.extend(_pickup_address(place) for place in PICKUPS)
    for speaker in ('sasha', 'worker', 'neighbour'):
        clips.append(_entrance(speaker))
        clips.extend(_direction(speaker, clue) for clue in CLUES)
    for name in ('north', 'south'):
        clips.extend([_worker_address(name), _closure(name), _crossing(name)])
    clips.append(_worker_stop())
    clips.extend(_clip('sasha', value[0], value[1]) for value in AMBIGUITIES.values())
    # line() deliberately leaves the speaker out of browser payloads. Restore
    # it here for the offline recording command using its stable content hash.
    speakers = ('postmaster', 'sasha', 'worker', 'neighbour', *RECIPIENTS)
    result = {}
    for clip in clips:
        speaker = next(key for key in speakers if line(key, clip['text'], clip['english'])['id'] == clip['id'])
        result[clip['id']] = {**clip, 'speaker': speaker}
    return list(result.values())
