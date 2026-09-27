"""Clarify authored directions without changing a saved town or route history.

Only recognised geometry receives these directions. In particular, the bridge
meeting point is on the starting bank and the library is between the river and
the yellow house. Entrance wording works with both older south-facing entrances
and the current north-facing plots.
"""
from copy import deepcopy

from services.route_content import line


CONTENT_REVISION = 'detour-guidance-v1'


def _detour_context(pack):
    if pack.get('mission_id') != 'town-detour' or pack.get('map', {}).get('scene') != 'town':
        return None
    world = pack.get('town', {})
    places, bridges = world.get('places', {}), world.get('bridges', {})
    facts, legs = pack.get('mission_facts', {}), pack.get('legs', [])
    closed, opened = facts.get('closed_bridge'), facts.get('open_bridge')
    if {closed, opened} != {'north', 'south'} or len(legs) != 2:
        return None
    nodes = {node['id']: node for node in pack['map'].get('nodes', [])}
    buildings = {building['id']: building for building in world.get('buildings', [])}
    try:
        approach = places[closed + '-approach']
        bridge, start = nodes[bridges[closed]], nodes[places['post']]
        meeting, door = nodes[approach], nodes[places['library']]
        library, yellow = buildings['library'], buildings['yellow-house']
        matches = (
            legs[0]['target'] == approach and legs[1]['start'] == approach
            and legs[1]['target'] == places['library']
            and start['x'] < bridge['x']
            and meeting['x'] == bridge['x'] - 1 and meeting['y'] == bridge['y']
            and bridge['x'] < library['x'] < yellow['x']
            and library['y'] == yellow['y']
            and door.get('building_id') == 'library'
            and abs(door['x'] - library['x']) + abs(door['y'] - library['y']) == 1
        )
    except (KeyError, TypeError):
        return None
    return (closed, opened, approach) if matches else None


def clarify_pack(pack):
    """Return a clarified copy of a known detour pack; leave other packs alone.

    This is a read-time content projection, not a database migration. Geometry,
    routes and recorded attempts remain exactly as saved. The finite wording
    also lets the regular audio catalogue prepare every recording in advance.
    """
    context = _detour_context(pack)
    if context is None:
        return pack
    closed, opened, approach = context
    result = deepcopy(pack)
    result['content_revision'] = CONTENT_REVISION
    first, second = result['legs']
    adjective = {'north': 'северным', 'south': 'южным'}[closed]
    first['lines'] = [line(
        first['speaker'],
        f'Это письмо для Лены в библиотеке. Сергей ждёт тебя перед {adjective} мостом, на этом берегу. Подойди к нему, но на мост не заходи.',
        f'This letter is for Lena at the library. Sergei is waiting before the {closed} bridge, on this bank. Walk over to him, but do not go onto the bridge.',
    )]
    first['clarify'] = deepcopy(first['lines'][0])
    first['objective'] = f'Meet Sergei before the {closed} bridge'
    first['objective_ru'] = f'Встреться с Сергеем перед {adjective} мостом'
    first['visible_contacts'] = [{'position': approach, 'speaker': 'worker'}]
    closed_ru = {'north': 'Северный', 'south': 'Южный'}[closed]
    opened_ru = {'north': 'северному', 'south': 'южному'}[opened]
    second['lines'] = [line(
        second['speaker'],
        f'{closed_ru} мост закрыт. Перейди реку по {opened_ru} мосту. Найди библиотеку между рекой и жёлтым домом. Пройди по дорожке до входа и передай письмо Лене.',
        f'The {closed} bridge is closed. Cross the river using the {opened} bridge. Find the library between the river and the yellow house. Follow the path to its entrance and give Lena the letter.',
    )]
    second['clarify'] = deepcopy(second['lines'][0])
    second['objective'] = 'Give Lena the letter at the library entrance'
    second['objective_ru'] = 'Передай письмо Лене у входа в библиотеку'
    for ref in result.get('vocabulary_refs', []):
        if ref.get('leg') in (0, 1):
            source = result['legs'][ref['leg']]['lines'][0]
            ref.update(sentence=source['text'], translation=source['english'])
    return result
