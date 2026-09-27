"""Separate movement stops from assessed destinations in generated towns."""
from services.route_content import matches_rule


def travelled_path(pack, index, path):
    closed = {item['node_id'] for item in pack['map'].get('closures', [])
              if item.get('from_leg', 0) <= index}
    blocked_at = next((i for i, node in enumerate(path[1:], 1) if node in closed), None)
    return path if blocked_at is None else path[:blocked_at]


def town_assessment(pack, index, path):
    """Judge language choices, without treating an unfinished walk as a failure."""
    if not pack.get('town'):
        return None
    leg, world = pack['legs'][index], pack['town']
    arrival = leg.get('encounter_contract', {}).get('arrival', {})
    nodes = {node['id']: node for node in pack['map']['nodes']}
    travelled = travelled_path(pack, index, path)
    blocked = len(travelled) != len(path)
    # The bridge symbol is a reasonable way to choose "by the bridge".
    # Reaching Sergei's bank-side barrier starts the encounter, never a crossing.
    meeting = ((leg.get('bridge_meeting') or (pack.get('mission_id') == 'town-detour' and leg['id'] == 'find-worker'))
               and blocked and travelled[-1] == leg['target'])
    checked_path = travelled if meeting else path
    failed_rule = next((rule for rule in leg['rules']
                        if not matches_rule(rule, checked_path, nodes)), None)
    accepted = arrival.get('accepted_nodes', [leg['target']])
    arrived = failed_rule is None and travelled[-1] in accepted and (not blocked or meeting)
    checks = []
    crossed = False
    crossing_rule = leg.get('crossing')
    if not crossing_rule and pack.get('mission_id') == 'town-detour' and leg['id'] == 'detour':
        bridge_name = pack['mission_facts']['open_bridge']
        crossing_rule = {'bridge': world['bridges'][bridge_name], 'direction': 'east'}
    if crossing_rule:
        bridge = crossing_rule['bridge']
        if bridge in travelled:
            crossing = travelled.index(bridge)
            crossed = any((nodes[n]['x'] > nodes[bridge]['x']) if crossing_rule['direction'] == 'east'
                          else (nodes[n]['x'] < nodes[bridge]['x']) for n in travelled[crossing + 1:])
        checks.append({'id': 'crossing', 'label': 'Cross the river', 'label_ru': 'Перейти реку',
                       'complete': crossed})
    checks.append({'id': 'destination', 'label': 'Reach the destination',
                   'label_ru': 'Дойти до места назначения', 'complete': arrived})

    def result(correct, code, en, ru, *, navigation=False):
        return {'correct': correct, 'code': code, 'en': en, 'ru': ru,
                'navigation': navigation, 'checks': checks}

    if arrived:
        return result(True, 'arrived',
                      'You found Sergei beside the bridge. Stop here and talk to him.' if meeting else 'You found the right place.',
                      'Сергей здесь, перед мостом. Остановись и поговори с ним.' if meeting else 'Ты нашёл нужное место.')
    if failed_rule is not None:
        return result(False, failed_rule['code'], failed_rule['en'], failed_rule['ru'])
    if blocked:
        return result(False, 'closed_bridge', 'The bridge is closed. Choose another crossing.',
                      'Мост закрыт. Выбери другой мост.')
    endpoint, target = nodes[travelled[-1]], nodes[leg['target']]
    adjacent = any(set(edge) == {endpoint['id'], target['id']} for edge in pack['map']['edges'])
    # Only the actual frontage counts as nearby. A neighbouring house, the
    # wrong bank or another entrance to the same building remains a real choice.
    nearby = ((travelled[-1] in arrival.get('near_nodes', [])) if arrival else
              (target.get('building_id') and adjacent and not endpoint.get('building_id')
               and target.get('entrance') != 'courtyard' and not leg.get('transport')))
    if nearby:
        return result(False, 'nearby',
                      'You’re outside the building. Follow the short path to its entrance.',
                      'Ты рядом с нужным зданием. Пройди по короткой дорожке к входу.', navigation=True)
    if endpoint['kind'] in ('street', 'junction', 'bridge', 'meeting', 'bus-stop') and not leg.get('transport'):
        return result(False, 'continue_route',
                      'You’ve crossed the river by the right bridge. Continue to your destination.' if crossed
                      else 'You’ve reached this point. Keep following the directions to your destination.',
                      'Ты перешёл реку по нужному мосту. Продолжай путь до места назначения.' if crossed
                      else 'Ты дошёл до этой точки. Продолжай путь по указаниям.', navigation=True)
    return result(False, 'place',
                  'This is a different place. Check the landmark or entrance in the directions.',
                  'Это другое место. Проверь, какое здание или какой вход указан в задании.')
