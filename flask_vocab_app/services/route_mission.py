"""Bind reusable delivery events to verified town facts.

The composer owns meaning, arrival conditions and disclosure. A preparation
adapter may add conversation around the checked clauses, but cannot change
them. No network or database work belongs in this module.
"""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import random

from services.route_content import VERSION, SPEAKERS, line, validate_pack
from services.route_town import shortest_path


MISSION_ID = 'town-procedural'
GENERATOR_VERSION = 'delivery-events-v1'
CONTRACT_VERSION = 'delivery-encounter-v1'
_LIBRARY = Path(__file__).resolve().parents[1] / 'content' / 'deliveries' / 'events.json'
_PEOPLE = {
    'postmaster': ('Нина', 'Нины', 'Нине', 'Нина ушла', 'Nina', 'she'),
    'sasha': ('Саша', 'Саши', 'Саше', 'Саша ушёл', 'Sasha', 'he'),
    'olya': ('Оля', 'Оли', 'Оле', 'Оля ушла', 'Olya', 'she'),
    'anna': ('Анна', 'Анны', 'Анне', 'Анна ушла', 'Anna', 'she'),
    'nikolai': ('Николай', 'Николая', 'Николаю', 'Николай ушёл', 'Nikolai', 'he'),
    'vera': ('Вера', 'Веры', 'Вере', 'Вера ушла', 'Vera', 'she'),
    'boris': ('Борис', 'Бориса', 'Борису', 'Борис ушёл', 'Boris', 'he'),
    'lena': ('Лена', 'Лены', 'Лене', 'Лена ушла', 'Lena', 'she'),
    'dima': ('Дима', 'Димы', 'Диме', 'Дима ушёл', 'Dima', 'he'),
    'irina': ('Ирина', 'Ирины', 'Ирине', 'Ирина ушла', 'Irina', 'she'),
}
_FALLBACK_FORMS = {
    'post': ('почта', 'почты', 'почте', 'почту', 'почтой', 'почте'),
    'bakery': ('пекарня', 'пекарни', 'пекарне', 'пекарню', 'пекарней', 'пекарне'),
    'market': ('рынок', 'рынка', 'рынку', 'рынок', 'рынком', 'рынке'),
    'park': ('парк', 'парка', 'парку', 'парк', 'парком', 'парке'),
    'library': ('библиотека', 'библиотеки', 'библиотеке', 'библиотеку', 'библиотекой', 'библиотеке'),
    'cafe': ('кафе', 'кафе', 'кафе', 'кафе', 'кафе', 'кафе'),
    'station': ('вокзал', 'вокзала', 'вокзалу', 'вокзал', 'вокзалом', 'вокзале'),
    'pharmacy': ('аптека', 'аптеки', 'аптеке', 'аптеку', 'аптекой', 'аптеке'),
    'bank-office': ('банк', 'банка', 'банку', 'банк', 'банком', 'банке'),
    'house': ('дом', 'дома', 'дому', 'дом', 'домом', 'доме'),
}
_ADJECTIVES = {
    'yellow': ('жёлтый', 'жёлтого', 'жёлтому', 'жёлтый', 'жёлтым', 'жёлтом'),
    'blue': ('синий', 'синего', 'синему', 'синий', 'синим', 'синем'),
}
_CARDINALS = {
    'north': ('к северу от', 'north of'), 'south': ('к югу от', 'south of'),
    'east': ('к востоку от', 'east of'), 'west': ('к западу от', 'west of'),
}
_MEANINGS = {'post': 'post office', 'bakery': 'bakery', 'market': 'market', 'park': 'park',
             'library': 'library', 'cafe': 'café', 'station': 'station', 'pharmacy': 'pharmacy',
             'bank-office': 'bank', 'house': 'house'}


@lru_cache(maxsize=1)
def _content_library():
    data = json.loads(_LIBRARY.read_text(encoding='utf-8'))
    events = {event['id']: event for event in data['events']}
    if set(events) != {'collection', 'address_clarification', 'entrance_choice', 'relocation'}:
        raise ValueError('Unsupported delivery event library')
    if any(not 0 <= event['weight'] <= 1 or not event['requires'] or not event['effects'] for event in events.values()):
        raise ValueError('Invalid delivery event definition')
    if not data.get('premises') or any(p['item'] not in ('letter', 'parcel') or not p['ru'] or not p['en'] for p in data['premises']):
        raise ValueError('Invalid delivery premise library')
    return data


def event_library():
    return {event['id']: event for event in _content_library()['events']}


def catalogue():
    return [{'mission_id': MISSION_ID, 'title': 'A delivery for Barsik', 'title_ru': 'Доставка для Барсика',
             'area': 'town', 'summary': 'Meet people around town and follow their Russian directions.',
             'summary_ru': 'Знакомься с жителями города и следуй их указаниям.'}]


def _forms(building):
    if all(building.get('forms', {}).get(key) for key in ('nom', 'gen', 'dat', 'acc', 'inst', 'prep')):
        return building['forms']
    values = _FALLBACK_FORMS[building['kind']]
    if building.get('colour') in _ADJECTIVES:
        values = tuple(f'{adjective} {noun}' for adjective, noun in zip(_ADJECTIVES[building['colour']], values))
    elif len(building['entrances']) > 1:
        values = tuple(f'{noun} со двором' for noun in values)
    return dict(zip(('nom', 'gen', 'dat', 'acc', 'inst', 'prep'), values))


def _description(building):
    result = {'kind': building['kind']}
    if building.get('colour'):
        result['colour'] = building['colour']
    if len(building['entrances']) > 1:
        result['feature'] = 'courtyard'
    return result


def _describes(building, description):
    return (building['kind'] == description['kind']
            and (not description.get('colour') or building.get('colour') == description['colour'])
            and (description.get('feature') != 'courtyard' or len(building['entrances']) > 1))


def _frontage(world, building):
    """Street-side nodes are derived from edges, never guessed coordinates."""
    nodes = {node['id']: node for node in world['map']['nodes']}
    door = building['entrances'][0]
    return [nodes[b if a == door else a] for a, b in world['map']['edges']
            if door in (a, b) and not nodes[b if a == door else a].get('building_id')]


def _same_street(world, first, second):
    nodes = {node['id']: node for node in world['map']['nodes']}
    coordinates = {(node['x'], node['y']): node['id'] for node in nodes.values() if not node.get('building_id')}
    edges = {frozenset(edge) for edge in world['map']['edges']}
    for a in _frontage(world, first):
        for b in _frontage(world, second):
            if a['y'] == b['y']:
                span = [(x, a['y']) for x in range(min(a['x'], b['x']), max(a['x'], b['x']) + 1)]
            elif a['x'] == b['x']:
                span = [(a['x'], y) for y in range(min(a['y'], b['y']), max(a['y'], b['y']) + 1)]
            else:
                continue
            ids = [coordinates.get(point) for point in span]
            if all(ids) and all(frozenset(edge) in edges for edge in zip(ids, ids[1:])):
                return True
    return False


def _relation_matches(world, target, anchor, relation):
    dx, dy = target['x'] - anchor['x'], target['y'] - anchor['y']
    if relation in _CARDINALS:
        return {'north': dy < 0, 'south': dy > 0, 'west': dx < 0, 'east': dx > 0}[relation]
    if relation == 'same-bank':
        river = world['map'].get('river_x')
        return river is not None and (target['x'] - river) * (anchor['x'] - river) > 0
    if relation == 'same-street':
        return _same_street(world, target, anchor)
    if relation == 'opposite':
        # Opposite means facing each other across the SAME straight street.
        for a in _frontage(world, target):
            for b in _frontage(world, anchor):
                if a['id'] != b['id']:
                    continue
                tx, ty = target['x'] - a['x'], target['y'] - a['y']
                ax, ay = anchor['x'] - b['x'], anchor['y'] - b['y']
                if (tx == ax == 0 and ty * ay < 0) or (ty == ay == 0 and tx * ax < 0):
                    return True
        return False
    raise ValueError('Unsupported delivery landmark relationship')


def clue_matches(world, clue):
    buildings = {building['id']: building for building in world['buildings']}
    anchor = buildings.get(clue.get('anchor'))
    if anchor is None:
        return []
    return [building['id'] for building in buildings.values()
            if building['id'] != anchor['id'] and _describes(building, clue['description'])
            and _relation_matches(world, building, anchor, clue['relation'])]


def _clue_text(target, anchor, relation):
    destination, reference = _forms(target), _forms(anchor)
    if relation in _CARDINALS:
        ru, en = _CARDINALS[relation]
        clause = f'{ru} {reference["gen"]}'
        english = f'{en} the {anchor["label_en"].lower()}'
        form, case = reference['gen'], 'gent'
    elif relation == 'same-bank':
        clause = f'на том же берегу, что и {reference["nom"]}'
        english = f'on the same bank of the river as the {anchor["label_en"].lower()}'
        form, case = 'берегу', 'loct'
    elif relation == 'same-street':
        clause = f'на той же улице, что и {reference["nom"]}'
        english = f'on the same street as the {anchor["label_en"].lower()}'
        form, case = 'улице', 'loct'
    else:
        clause = f'напротив {reference["gen"]}'
        english = f'opposite the {anchor["label_en"].lower()}'
        form, case = reference['gen'], 'gent'
    lemma = 'берег' if relation == 'same-bank' else 'улица' if relation == 'same-street' else _FALLBACK_FORMS[anchor['kind']][0]
    # Phrase-level adjectives are not represented as a fake noun lemma.
    if relation not in ('same-bank', 'same-street'):
        plain_forms = dict(zip(('nom', 'gen', 'dat', 'acc', 'inst', 'prep'), _FALLBACK_FORMS[anchor['kind']]))
        form = plain_forms['gen']
    return {'ru': f'Найди {destination["acc"]} {clause}.',
            'en': f'Find the {target["label_en"].lower()} {english}.',
            'word': {'lemma': lemma, 'form': form, 'case': case,
                     'meaning': 'riverbank' if relation == 'same-bank' else 'street' if relation == 'same-street'
                     else _MEANINGS[anchor['kind']]}}


def available_clues(world):
    """Use only uniquely identified anchors and uniquely resolving statements."""
    buildings = world['buildings']
    anchors = [building for building in buildings
               if sum(_describes(other, _description(building)) for other in buildings) == 1]
    result = {}
    relations = ('opposite', 'same-street', *_CARDINALS)
    if world['map'].get('river_x') is not None:
        relations = ('opposite', 'same-street', 'same-bank', *_CARDINALS)
    for target in buildings:
        possibilities = []
        for anchor in anchors:
            if anchor['id'] == target['id']:
                continue
            for relation in relations:
                clue = {'place': target['id'], 'anchor': anchor['id'], 'relation': relation,
                        'description': _description(target)}
                if clue_matches(world, clue) == [target['id']]:
                    clue.update(_clue_text(target, anchor, relation))
                    possibilities.append(clue)
        if possibilities:
            result[target['id']] = possibilities
    return result


def _clip(speaker, text, english, role):
    return {**line(speaker, text, english), 'role': role}


def _clue_clip(speaker, clue):
    return _clip(speaker, clue['ru'], clue['en'], 'direction')


def _arrival(world, target, *, courtyard=False):
    nodes = {node['id']: node for node in world['map']['nodes']}
    building = next(building for building in world['buildings'] if target in building['entrances'])
    adjacent = [b if a == target else a for a, b in world['map']['edges'] if target in (a, b)]
    return {'building_id': building['id'], 'target_node': target, 'accepted_nodes': [target],
            'near_nodes': [nid for nid in adjacent if not nodes[nid].get('building_id')],
            'entrance_required': courtyard,
            'entrance_kind': 'courtyard' if courtyard else nodes[target].get('entrance', 'main')}


def _target(world, building, courtyard=False):
    if not courtyard:
        return world['places'][building['id']]
    nodes = {node['id']: node for node in world['map']['nodes']}
    return next(nid for nid in building['entrances'] if nodes[nid].get('entrance') == 'courtyard')


def _leg(world, key, start, target, speaker, arrival, lines, *, stage, facts, courtyard=False, **extra):
    route = shortest_path(world, start, target)
    if len(route) < 3:
        raise ValueError('An encounter needs a meaningful change of location')
    nodes = {node['id']: node for node in world['map']['nodes']}
    a, b = nodes[route[0]], nodes[route[1]]
    heading = 'east' if b['x'] > a['x'] else 'west' if b['x'] < a['x'] else 'south' if b['y'] > a['y'] else 'north'
    acceptance = _arrival(world, target, courtyard=courtyard)
    leg = {'id': key, 'start': start, 'target': target, 'speaker': speaker, 'arrival_speaker': arrival,
           'heading': heading, 'route': route, 'rules': [], 'lines': lines, 'clarify': lines[-1],
           'clarify_prompt': 'Повтори, пожалуйста.', 'objective': 'Follow the directions', 'objective_ru': 'Следуй указаниям',
           'review_title': 'Following the directions', 'review_title_ru': 'Понимание указаний',
           'arrival_policy': acceptance, **extra}
    leg['encounter_contract'] = {
        'version': CONTRACT_VERSION, 'speaker': speaker, 'stage': stage, 'task_type': 'find_place',
        'facts': facts, 'required_lines': deepcopy(lines),
        'allowed_entity_ids': sorted({value for fact in facts for key, value in fact.items()
                                      if key in ('id', 'place', 'anchor', 'person', 'recipient') and isinstance(value, str)}),
        'arrival': acceptance,
        'allowed_narrative': [{'ru': 'Спасибо, что помогаешь с доставкой.', 'en': 'Thank you for helping with the delivery.'}],
    }
    return leg


def _choose_clue(rng, clues):
    # Relationships, not cosmetic phrasing, are selected first. This prevents
    # four cardinal alternatives from overwhelming less common useful clues.
    relation = rng.choice(sorted({clue['relation'] for clue in clues}))
    return deepcopy(rng.choice([clue for clue in clues if clue['relation'] == relation]))


def _compose(world, rng, clues, *, sample):
    events = event_library()
    buildings = {building['id']: building for building in world['buildings']}
    nodes = {node['id']: node for node in world['map']['nodes']}
    places = world['places']
    usable = [key for key in clues if key != 'post']
    repeated = [key for key in usable
                if sum(_describes(other, _description(buildings[key])) for other in buildings.values()) > 1]
    courtyards = [key for key in usable if any(nodes[nid].get('entrance') == 'courtyard'
                                              for nid in buildings[key]['entrances'])]
    want_question = bool(repeated) and rng.random() < events['address_clarification']['weight']
    want_relocation = rng.random() < events['relocation']['weight']
    want_entrance = bool(courtyards) and rng.random() < events['entrance_choice']['weight']
    if want_question and want_entrance:
        want_relocation = True
    # A unique noun is not a spatial comprehension task. Every delivery must
    # require either distinguishing matching buildings or choosing an entrance.
    # The collection point can be easier, so the first walk teaches the controls.
    first_address = rng.choice(courtyards if want_entrance and not want_question else repeated or courtyards)
    if first_address in courtyards and not repeated:
        want_entrance = True
    final_address = (rng.choice([key for key in (courtyards if want_entrance and want_question else usable)
                                 if key != first_address]) if want_relocation else first_address)
    courtyard_address = final_address if want_entrance and want_question else first_address if want_entrance else None
    sources = [key for key in usable if key not in (first_address, final_address)
               and (buildings[key]['kind'] in ('bakery', 'market', 'library', 'cafe', 'station', 'park')
                    or 'collection_point' in buildings[key].get('tags', []))]
    pickup = rng.choice(sources)
    # A local who knows an address is a separate encounter in some deliveries.
    # Other assignments ask the collection contact directly.
    detour = want_question and rng.random() < .5
    helper_place = rng.choice([key for key in usable if key not in (pickup, first_address, final_address)]) if detour else None
    origin = rng.choice([key for key in buildings if key not in (pickup, first_address, final_address, helper_place)])
    cast = rng.sample(sorted(_PEOPLE), 5)
    initiator, collector, informer, recipient, neighbour = cast
    kind = rng.choice(('letter', 'parcel'))
    premise = deepcopy(rng.choice([premise for premise in _content_library()['premises'] if premise['item'] == kind]))
    object_ru = 'письмо' if kind == 'letter' else 'посылку'
    object_phrase = 'это письмо' if kind == 'letter' else 'эту посылку'
    item = {'id': kind, 'label': kind.title(), 'label_ru': 'Письмо' if kind == 'letter' else 'Посылка'}
    speakers = deepcopy(SPEAKERS)
    for speaker in cast:
        speakers[speaker].update(role='Житель города', role_en='Local resident')
    speakers[initiator].update(role='Отправитель', role_en='Sender')
    speakers[collector].update(role='Помогает с доставкой', role_en='Helping with the delivery')
    speakers[recipient].update(role='Получатель', role_en='Recipient')
    pickup_clue = _choose_clue(rng, clues[pickup])
    first_clue = _choose_clue(rng, clues[first_address])
    final_clue = _choose_clue(rng, clues[final_address]) if want_relocation else first_clue
    first_lines = [
        _clip(initiator, f'Забери у {_PEOPLE[collector][1]} {object_ru} для {_PEOPLE[recipient][1]}.',
              f'Collect a {kind} for {_PEOPLE[recipient][4]} from {_PEOPLE[collector][4]}.', 'collection'),
        _clip(initiator, premise['ru'], premise['en'], 'purpose'),
        _clue_clip(initiator, pickup_clue),
        _clip(initiator, f'{_PEOPLE[collector][0]} ждёт тебя у главного входа.',
              f'{_PEOPLE[collector][4]} is waiting at the main entrance.', 'arrival'),
    ]
    legs = [_leg(world, 'collect', places[origin], places[pickup], initiator, collector, first_lines,
                 stage='collection', facts=[{'type': 'collection', 'id': kind, 'person': collector, 'recipient': recipient},
                                             {'type': 'landmark_relationship', **pickup_clue}],
                 arrival_item=item, arrival_text=f'{_PEOPLE[collector][4]} hands you the {kind}.',
                 arrival_text_ru=f'{_PEOPLE[collector][0]} передаёт тебе {object_ru}.',
                 arrival_action_label='Continue the delivery', arrival_action_label_ru='Продолжить доставку')]
    fact_events = [{'kind': 'collection', 'leg': 0, 'place': pickup}]
    cluefacts = [{'leg': 0, 'clue': pickup_clue, 'question': None}]
    departure, guide = places[pickup], collector
    handover = _clip(guide, f'Отнеси {object_phrase} {_PEOPLE[recipient][2]}.',
                     f'Take this {kind} to {_PEOPLE[recipient][4]}.', 'handover')
    onward = [handover]
    if detour:
        helper_clue = _choose_clue(rng, clues[helper_place])
        helper_lines = [handover,
                        _clip(guide, f'{_PEOPLE[informer][0]} знает точный адрес и объяснит дорогу.',
                              f'{_PEOPLE[informer][4]} knows the exact address and will explain the way.', 'information_contact'),
                        _clue_clip(guide, helper_clue),
                        _clip(guide, f'{_PEOPLE[informer][0]} ждёт у главного входа.',
                              f'{_PEOPLE[informer][4]} is waiting at the main entrance.', 'arrival')]
        legs.append(_leg(world, 'ask-a-local', departure, places[helper_place], guide, informer, helper_lines,
                         stage='address_clarification', facts=[{'type': 'information_contact', 'id': informer},
                                                                 {'type': 'landmark_relationship', **helper_clue}],
                         requires_item=kind))
        cluefacts.append({'leg': len(legs) - 1, 'clue': helper_clue, 'question': None})
        fact_events.append({'kind': 'address_clarification', 'leg': len(legs) - 1, 'place': helper_place, 'mode': 'local'})
        departure, guide, onward = places[helper_place], informer, []
    initial_target = _target(world, buildings[first_address], first_address == courtyard_address)
    direction = _clue_clip(guide, first_clue)
    disclosed = [{'type': 'item', 'id': kind}, {'type': 'recipient', 'id': recipient}]
    extra = {'requires_item': kind, 'clarify': direction}
    if want_question:
        forms = _forms(buildings[first_address])
        vague = _clip(guide, f'{_PEOPLE[recipient][0]} сейчас в {forms["prep"]}.',
                      f'{_PEOPLE[recipient][4]} is now in a {buildings[first_address]["label_en"].lower()}.', 'incomplete_address')
        question = ('В каком доме?' if buildings[first_address]['kind'] == 'house' else 'В каком банке?')
        extra.update(questions=[{'id': 'which-address', 'text': question,
                                 'text_en': 'Which house?' if buildings[first_address]['kind'] == 'house' else 'Which bank?',
                                 'reply': direction}], required_question='which-address', clarify=vague)
        onward.append(vague)
        disclosed.append({'type': 'incomplete_address', **_description(buildings[first_address])})
        if not detour:
            fact_events.append({'kind': 'address_clarification', 'leg': len(legs), 'place': pickup, 'mode': 'collection'})
    else:
        onward.append(direction)
        disclosed.append({'type': 'landmark_relationship', **first_clue})
    entrance_ru, entrance_en = ('Тебе нужен вход со двора, не главный вход.', 'Use the courtyard entrance, not the main entrance.') if first_address == courtyard_address else ('Подойди к главному входу.', 'Walk up to the main entrance.')
    onward.append(_clip(guide, entrance_ru, entrance_en, 'arrival'))
    if first_address == courtyard_address:
        fact_events.append({'kind': 'entrance_choice', 'leg': len(legs), 'place': first_address, 'entrance': 'courtyard'})
        disclosed.append({'type': 'entrance', 'entrance': 'courtyard'})
    if want_relocation:
        extra.update(arrival_text=f'{_PEOPLE[neighbour][4]} comes to meet you.',
                     arrival_text_ru=f'Тебя встречает {_PEOPLE[neighbour][0]}.')
    else:
        extra['arrival_remove_item'] = kind
    cluefacts.append({'leg': len(legs), 'clue': first_clue, 'question': 'which-address' if want_question else None})
    legs.append(_leg(world, 'find-address', departure, initial_target, guide, neighbour if want_relocation else recipient,
                     onward, stage='address_clarification' if want_question else 'entrance_choice' if first_address == courtyard_address else 'delivery',
                     facts=disclosed, courtyard=first_address == courtyard_address, **extra))
    if want_relocation:
        final_target = _target(world, buildings[final_address], final_address == courtyard_address)
        relocation_line = _clip(neighbour, f'{_PEOPLE[recipient][3]}, но попросил передать новый адрес.' if _PEOPLE[recipient][5] == 'he'
                                else f'{_PEOPLE[recipient][3]}, но попросила передать новый адрес.',
                                f'{_PEOPLE[recipient][4]} has left, but asked me to give you the new address.', 'relocation')
        final_lines = [relocation_line, _clue_clip(neighbour, final_clue),
                       _clip(neighbour, 'Тебе нужен вход со двора, не главный вход.' if final_address == courtyard_address else 'Подойди к главному входу.',
                             'Use the courtyard entrance, not the main entrance.' if final_address == courtyard_address else 'Walk up to the main entrance.', 'arrival')]
        fact_events.append({'kind': 'relocation', 'leg': len(legs), 'from': first_address, 'to': final_address})
        if final_address == courtyard_address:
            fact_events.append({'kind': 'entrance_choice', 'leg': len(legs), 'place': final_address, 'entrance': 'courtyard'})
        cluefacts.append({'leg': len(legs), 'clue': final_clue, 'question': None})
        legs.append(_leg(world, 'new-address', initial_target, final_target, neighbour, recipient, final_lines,
                         stage='relocation', facts=[{'type': 'relocation', 'id': recipient},
                                                    {'type': 'landmark_relationship', **final_clue}],
                         courtyard=final_address == courtyard_address, clarify=final_lines[1],
                         requires_item=kind, arrival_remove_item=kind))
    for leg in legs:
        contract = leg['encounter_contract']
        circumstance_id = ('sender-stays' if leg['id'] == 'collect' else 'informed-of-move' if leg['id'] == 'new-address'
                           else 'knows-address' if leg.get('required_question') else 'recipient-expects')
        circumstance = _content_library()['circumstances'][circumstance_id]
        contract['facts'].extend([
            {'type': 'delivery_purpose', **premise},
            {'type': 'circumstance', 'id': circumstance_id, **circumstance},
        ])
        contract['allowed_narrative'] = [{'ru': premise['ru'], 'en': premise['en']}, deepcopy(circumstance)]
    decisions = []
    for index, leg in enumerate(legs):
        if index == 0 or leg['id'] == 'ask-a-local':
            continue
        policy = leg['arrival_policy']
        target = buildings[policy['building_id']]
        matching = [building['id'] for building in buildings.values() if _describes(building, _description(target))]
        if len(matching) > 1:
            decisions.append({'leg': index, 'kind': 'distinguish_buildings', 'candidates': matching})
        if policy['entrance_required']:
            decisions.append({'leg': index, 'kind': 'distinguish_entrances', 'candidates': target['entrances']})
    facts = {'origin': origin, 'pickup': pickup, 'recipient': recipient, 'item': kind, 'premise': premise, 'destination': final_address,
             'events': fact_events, 'clues': cluefacts, 'waypoints': [leg['target'] for leg in legs]}
    facts['learning_decisions'] = decisions
    semantic = {'events': fact_events, 'origin': origin, 'pickup': pickup, 'destination': final_address,
                'clues': [{'place': fact['clue']['place'], 'anchor': fact['clue']['anchor'],
                           'relation': fact['clue']['relation'], 'question': fact['question']} for fact in cluefacts],
                'entrances': [leg['arrival_policy']['entrance_kind'] for leg in legs]}
    facts['fingerprint'] = sha256(json.dumps(semantic, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]
    facts['structural_signature'] = ':'.join(event['kind'] + ('-local' if event.get('mode') == 'local' else '') for event in fact_events)
    vocabulary = [{'lemma': 'письмо' if kind == 'letter' else 'посылка', 'form': object_ru,
                   'sentence': first_lines[0]['text'], 'translation': first_lines[0]['english'],
                   'target_meaning': kind, 'pos': 'NOUN', 'grammar': {'case': 'accs', 'number': 'sing'}, 'leg': 0}]
    for fact in cluefacts:
        if fact['question']:
            continue
        clue = fact['clue']
        vocabulary.append({'lemma': clue['word']['lemma'], 'form': clue['word']['form'],
                           'sentence': clue['ru'], 'translation': clue['en'], 'target_meaning': clue['word']['meaning'],
                           'pos': 'NOUN', 'grammar': {'case': clue['word']['case'], 'number': 'sing'}, 'leg': fact['leg']})
    ending = line(recipient, f'Спасибо за {object_ru}, Барсик!', f'Thank you for the {kind}, Barsik!')
    choice = catalogue()[0]
    return {'version': VERSION, 'lesson_version': GENERATOR_VERSION + ':' + facts['fingerprint'], 'mission_id': MISSION_ID,
            'generator_version': GENERATOR_VERSION, 'mission_facts': facts, 'town': deepcopy(world), 'map': deepcopy(world['map']),
            'area': 'town', 'title': choice['title'], 'title_ru': choice['title_ru'], 'summary': choice['summary'], 'summary_ru': choice['summary_ru'],
            'source': {'kind': 'route', 'title': 'Town deliveries', 'href': '#games/directions'},
            'options': {'source': 'procedural', 'word_policy': 'mixed-v1'}, 'sample': sample,
            'speakers': speakers, 'recipient_id': recipient, 'recipient': speakers[recipient], 'envelope': item['label_ru'],
            'legs': legs, 'rounds': [], 'vocabulary_refs': vocabulary, 'media_texts': [], 'ending': ending,
            'completion_text': f'The {kind} reached its recipient.',
            'completion_text_ru': 'Письмо доставлено получателю.' if kind == 'letter' else 'Посылка доставлена получателю.'}


def validate_mission(pack):
    validate_pack(pack)
    world, legs, facts = pack['town'], pack['legs'], pack['mission_facts']
    if pack['map']['nodes'] != world['map']['nodes'] or pack['map']['edges'] != world['map']['edges']:
        raise ValueError('A delivery cannot change its saved town')
    if not 2 <= len(legs) <= 4 or len({leg['target'] for leg in legs}) != len(legs):
        raise ValueError('A delivery needs two to four distinct encounters')
    if facts['waypoints'] != [leg['target'] for leg in legs]:
        raise ValueError('Delivery waypoints differ from their encounters')
    destination = next(building for building in world['buildings'] if building['id'] == facts['destination'])
    if legs[-1]['target'] not in destination['entrances'] or legs[-1]['arrival_speaker'] != facts['recipient']:
        raise ValueError('The final encounter must reach the recipient')
    inventory = set()
    for leg in legs:
        if leg.get('requires_item') and leg['requires_item'] not in inventory:
            raise ValueError('An item must be collected before it is delivered')
        if leg.get('arrival_item'):
            inventory.add(leg['arrival_item']['id'])
        if leg.get('arrival_remove_item'):
            if leg['arrival_remove_item'] not in inventory:
                raise ValueError('Cannot deliver an item which was not collected')
            inventory.remove(leg['arrival_remove_item'])
        contract = leg['encounter_contract']
        if contract['speaker'] != leg['speaker'] or contract['arrival'] != leg['arrival_policy']:
            raise ValueError('The encounter contract differs from the runtime')
        received = {item['id']: item for item in leg['lines']}
        for required in contract['required_lines']:
            current = received.get(required['id'])
            if not current or any(current.get(key) != required[key] for key in ('text', 'english')):
                raise ValueError('A checked instruction was modified or omitted')
        policy = leg['arrival_policy']
        if policy['target_node'] != leg['target'] or policy['accepted_nodes'] != [leg['target']]:
            raise ValueError('The arrival target differs from its contract')
        if policy != _arrival(world, leg['target'], courtyard=policy['entrance_required']):
            raise ValueError('The arrival area is not the verified entrance')
        if policy['entrance_required']:
            target = next(node for node in world['map']['nodes'] if node['id'] == leg['target'])
            if target.get('entrance') != 'courtyard':
                raise ValueError('An entrance task must target a real courtyard entrance')
        if leg.get('required_question'):
            questions = {question['id']: question for question in leg.get('questions', [])}
            if leg['required_question'] not in questions:
                raise ValueError('A clarification has no reply')
            reply = questions[leg['required_question']]['reply']
            if reply['id'] in received or leg['clarify']['id'] == reply['id']:
                raise ValueError('The missing address was disclosed before the question')
            if any(fact['type'] == 'landmark_relationship' for fact in contract['facts']):
                raise ValueError('The dialogue prompt discloses a hidden address')
    if inventory:
        raise ValueError('The delivery did not hand over its item')
    if not facts.get('learning_decisions'):
        raise ValueError('A delivery needs a real spatial or entrance distinction')
    for decision in facts['learning_decisions']:
        leg = legs[decision['leg']]
        building = next(building for building in world['buildings'] if building['id'] == leg['arrival_policy']['building_id'])
        candidates = (building['entrances'] if decision['kind'] == 'distinguish_entrances' else
                      [other['id'] for other in world['buildings'] if _describes(other, _description(building))])
        if len(candidates) < 2 or decision['candidates'] != candidates:
            raise ValueError('A claimed learning decision has no plausible distractor')
    for fact in facts['clues']:
        clue, leg = fact['clue'], legs[fact['leg']]
        if clue_matches(world, clue) != [clue['place']]:
            raise ValueError('A geographic clue must uniquely identify its actual destination')
        destination = next(building for building in world['buildings'] if building['id'] == clue['place'])
        if leg['target'] not in destination['entrances']:
            raise ValueError('A spoken clue targets another building')
        anchor = next(building for building in world['buildings'] if building['id'] == clue['anchor'])
        expected = _clue_text(destination, anchor, clue['relation'])
        if (clue['ru'], clue['en']) != (expected['ru'], expected['en']):
            raise ValueError('A spoken clue contradicts its spatial relationship')
        lines = [question['reply'] for question in leg.get('questions', []) if question['id'] == fact['question']] if fact['question'] else leg['lines']
        if not any(item['text'] == clue['ru'] and item['english'] == clue['en'] for item in lines):
            raise ValueError('The verified destination was not spoken at the right time')
        if fact['question'] and sum(_describes(building, clue['description']) for building in world['buildings']) < 2:
            raise ValueError('A clarification needs a genuinely incomplete initial address')
    return True


def build_mission(world, seed, exclude_fingerprints=(), *, sample=False):
    from services.route_world import validate_world
    validate_world(world)
    rng = random.Random(int.from_bytes(sha256(str(seed).encode()).digest(), 'big'))
    clues = available_clues(world)
    if len(clues) < 6:
        raise ValueError('The town needs more usable, distinguishable landmarks')
    excluded = set(exclude_fingerprints)
    rejections = []
    for attempt in range(128):
        try:
            pack = _compose(world, rng, clues, sample=sample)
            if pack['mission_facts']['fingerprint'] in excluded:
                rejections.append('recent-semantic-repeat')
                continue
            validate_mission(pack)
        except (ValueError, IndexError) as error:
            rejections.append(str(error))
            continue
        pack['mission_seed'] = str(seed)
        pack['composition'] = {'attempts': attempt + 1, 'rejections': rejections, 'library_version': GENERATOR_VERSION}
        return pack
    raise ValueError('Could not assemble a valid, distinct delivery after bounded retries')
