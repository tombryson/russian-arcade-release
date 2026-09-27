"""Owned delivery play, listening support and separate post-delivery practice."""
import json
import re
from copy import deepcopy
from hashlib import sha256

from flask import current_app
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, timestamp, transaction
from services.route_content import VERSION, SPEAKERS, MISSION_IDS, build_mission, compatible_pack, matches_rule
from services.route_guidance import clarify_pack
from services.route_arrival import town_assessment, travelled_path


def _new_state(pack, mode='reading', leg=0):
    encounter = pack['legs'][leg]
    inventory = []
    # Section practice starts with the items available at that point.
    for earlier in pack['legs'][:leg]:
        if earlier.get('arrival_item'):
            inventory.append(deepcopy(earlier['arrival_item']))
        inventory = [item for item in inventory if item['id'] != earlier.get('arrival_remove_item')]
    return {'leg': leg, 'phase': 'dialogue', 'position': encounter['start'],
            'heading': encounter['heading'], 'draft': [encounter['start']], 'walked': [encounter['start']],
            'support': {}, 'feedback': None, 'last_path': [], 'mode': mode,
            'heard': {}, 'text_seen': {str(leg): True} if mode == 'reading' else {},
            'questions': {}, 'inventory': inventory, 'transport': {}}


def initialize(conn, session_id, pack, mode):
    conn.execute('INSERT INTO journey_route_state(session_id,state_json) VALUES (?,?)',
                 (session_id, encoded(_new_state(pack, mode))))


def start(request_id, *, new_game=False, sample=False, options=None):
    from services.journey_games import _owner, _scope, _read_row, _public
    from services.game_access import require_access, mark_started
    from services.route_town import GENERATOR_VERSION, TOWN_MISSION_IDS, build_world, build_mission as build_town_mission, variant_seeds
    from services.route_dispatch import MISSION_ID as GENERATED_MISSION, build_mission as compose_delivery
    from services.route_mission import MISSION_ID as PROCEDURAL_MISSION, build_mission as compose_procedural
    from services.route_world import GENERATOR_VERSION as WORLD_VERSION, LAYOUT_FAMILIES, build_world as assemble_world
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id):
        raise LearningError('invalid_request', 'Please start the delivery again.')
    options = {} if options is None else options
    if not isinstance(options, dict):
        raise LearningError('invalid_options', 'Choose a delivery and how to practise.')
    explore_new_town = options.get('delivery_new_town', False)
    if type(explore_new_town) is not bool:
        raise LearningError('invalid_options', 'Choose whether to explore a new town.')
    procedural = not sample and not current_app.config.get('PUBLIC_DEMO')
    mission_id, mode = options.get('delivery_id') or (PROCEDURAL_MISSION if procedural else GENERATED_MISSION), options.get('delivery_mode', 'reading')
    if (not isinstance(mission_id, str) or mission_id not in (*MISSION_IDS, *TOWN_MISSION_IDS, GENERATED_MISSION, PROCEDURAL_MISSION)) or mode not in ('reading', 'listening'):
        raise LearningError('invalid_options', 'Choose one of the available deliveries and practice modes.')
    if mission_id == PROCEDURAL_MISSION and not procedural:
        raise LearningError('demo_unavailable', 'New deliveries can be prepared in a local installation.', 403)
    if mission_id == PROCEDURAL_MISSION and explore_new_town:
        new_game = True
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile, guest = _owner(conn)
        where, args = _scope(profile, guest)
        now = timestamp()
        rows = conn.execute('SELECT * FROM journey_game_sessions WHERE '+where+" AND game_id='directions' ORDER BY created_at,rowid", args).fetchall()
        for row in rows:
            if request_id in json.loads(row['request_ids_json']):
                return _public(conn, row)
        active = next((r for r in rows if r['completed_at'] is None and r['superseded_at'] is None), None)
        if active and not new_game:
            requests = json.loads(active['request_ids_json'])
            conn.execute('UPDATE journey_game_sessions SET request_ids_json=? WHERE id=?', (encoded([*requests, request_id]), active['id']))
            return _public(conn, active)
        if not sample:
            require_access(conn, profile, 'directions', now=now)
        if active:
            conn.execute('UPDATE journey_game_sessions SET superseded_at=? WHERE id=?', (now, active['id']))
            conn.execute("UPDATE journey_route_preparations SET status='failed',error='A newer delivery has been started.',claim_id=NULL,lease_until=0,updated_at=? WHERE session_id=? AND status!='ready'",
                         (now, active['id']))
        count = sum(json.loads(r['content_json']).get('version') == VERSION for r in rows)
        if mission_id == PROCEDURAL_MISSION:
            previous_missions = [json.loads(r['content_json']) for r in rows]
            town = next((p['town'] for p in reversed(previous_missions)
                         if p.get('town', {}).get('generator_version') == WORLD_VERSION), None)
            if explore_new_town:
                previous_town = next((p['town'] for p in reversed(previous_missions) if p.get('town')), None)
                previous_family = previous_town.get('layout_family') if previous_town else None
                if previous_town and not previous_family and previous_town['map'].get('river_x') is not None:
                    previous_family = 'riverside'
                families = [family for family in LAYOUT_FAMILIES if family != previous_family]
                world_seed = identifier()
                choice = int.from_bytes(sha256(world_seed.encode()).digest(), 'big') % len(families)
                town = assemble_world(world_seed, requirements={'layout_family': families[choice]})
            else:
                town = town or assemble_world(identifier())
            recent = [p['mission_facts']['fingerprint'] for p in previous_missions
                      if p.get('mission_id') == PROCEDURAL_MISSION][-20:]
            pack = compose_procedural(town, identifier(), exclude_fingerprints=recent)
            pack = current_app.extensions['learning']['route_preparation'].plan(
                pack, scope=('profile:' + profile) if profile else ('guest:' + guest))
        elif mission_id in (*TOWN_MISSION_IDS, GENERATED_MISSION):
            # Reuse a frozen town with the current format. Older sessions retain
            # their snapshots; a format upgrade only affects future deliveries.
            previous = next((json.loads(r['content_json']).get('town') for r in reversed(rows)
                             if json.loads(r['content_json']).get('town', {}).get('generator_version') == GENERATOR_VERSION), None)
            town = previous or build_world('public-demo-town-v1' if sample else identifier())
            previous_missions = [json.loads(r['content_json']) for r in rows]
            if mission_id == GENERATED_MISSION:
                recent = [p['mission_facts']['fingerprint'] for p in previous_missions
                          if p.get('mission_id') == GENERATED_MISSION and p.get('mission_facts', {}).get('fingerprint')][-20:]
                pack = compose_delivery(town, identifier(), exclude_fingerprints=recent, sample=sample)
            else:
                # Older explicit mission IDs stay usable for saved routes and
                # integration clients, but are no longer the game's catalogue.
                occurrence = sum(p.get('mission_id') == mission_id and p.get('generator_version') == GENERATOR_VERSION
                                 for p in previous_missions)
                seeds = variant_seeds(mission_id)
                pack = build_town_mission(town, mission_id, seed=seeds[occurrence % len(seeds)])
            pack['sample'] = sample
        else:
            pack = build_mission(count, sample=sample, mission_id=mission_id)
        session_id = identifier()
        conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                     (session_id, profile, guest, 'directions', identifier(), encoded([request_id]), encoded(pack), now, now))
        initialize(conn, session_id, pack, mode)
        if mission_id == PROCEDURAL_MISSION:
            conn.execute('INSERT INTO journey_route_preparations(session_id,created_at,updated_at) VALUES (?,?,?)',
                         (session_id, now, now))
        mark_started(conn, profile, 'directions', now)
        return _public(conn, _read_row(conn, session_id, profile, guest))


def _runtime(conn, row):
    saved = conn.execute('SELECT * FROM journey_route_state WHERE session_id=?', (row['id'],)).fetchone()
    if not saved:
        raise LearningError('route_unavailable', 'This delivery needs its saved route state.', 409)
    state = json.loads(saved['state_json'])
    # Original v2 sessions always displayed their received Russian text.
    state.setdefault('mode', 'reading')
    state.setdefault('heard', {})
    state.setdefault('text_seen', {str(i): True for i in range(state['leg']+1)})
    state.setdefault('questions', {})
    state.setdefault('inventory', [])
    state.setdefault('transport', {})
    pack = clarify_pack(compatible_pack(json.loads(row['content_json'])))
    if pack.get('town'):
        for current in [state, *([state['review']] if state.get('review') else [])]:
            index = current['leg']
            start = pack['legs'][index]['start']
            previous = current.get('last_path', [])
            current.setdefault('walked', previous[:] if previous and previous[0] == start else [start])
            # Repair only known ambiguous arrivals in the effective view. Keep
            # the original content and action receipts intact for audit/replay.
            if current['phase'] == 'feedback' and not current.get('feedback', {}).get('navigation'):
                action = conn.execute("SELECT submitted_json,result_json FROM journey_route_actions WHERE session_id=? AND leg=? AND operation='go' ORDER BY rowid DESC LIMIT 1", (row['id'], index)).fetchone()
                if action:
                    previous_result = json.loads(action['result_json'])
                    if current.get('id') == previous_result.get('review_id'):
                        payload = json.loads(action['submitted_json'])
                        result = _effective_arrival(pack, index, payload, previous_result)
                        if result != previous_result:
                            walked = travelled_path(pack, index, payload['path'])
                            current.update(feedback=result, walked=walked, position=walked[-1],
                                           phase='arrived' if result['correct'] else 'feedback')
    return saved, state, pack


def _effective_arrival(pack, index, payload, result):
    """Correct historic barrier/frontage ambiguity without regrading real mistakes."""
    if (not pack.get('town') or result.get('correct') or result.get('navigation')
            or result.get('code') not in ('closed_bridge', 'place') or not payload.get('path')):
        return result
    updated = town_assessment(pack, index, payload['path'])
    if updated['correct'] or updated.get('navigation'):
        return {**result, **updated}
    return result


def _first_checks(conn, row, pack):
    attempts = conn.execute("SELECT leg,submitted_json,result_json FROM journey_route_actions WHERE session_id=? AND attempt_kind IN ('first','correction') ORDER BY rowid", (row['id'],)).fetchall()
    checks = {}
    for attempt in attempts:
        index = attempt['leg']
        result = _effective_arrival(pack, index, json.loads(attempt['submitted_json']), json.loads(attempt['result_json']))
        if index not in checks and not result.get('navigation'):
            checks[index] = {'leg': index, **result}
    return [checks[index] for index in sorted(checks)]


def _visible_text(state, index):
    return state['mode'] == 'reading' or bool(state['support'].get(str(index), {}).get('transcript'))


def _line(item, *, translated=False, visible=True):
    return {k: v for k, v in item.items() if k in ('id', 'text', 'english', 'audio_url', 'asset_id')
            and (k != 'english' or translated) and (k != 'text' or visible)}


def _received_words(pack, index):
    return [word for word in pack['vocabulary_refs'] if word['leg'] <= index]


def _received_lines(leg, state, index):
    asked = state.get('questions', {}).get(str(index), [])
    questions = {q['id']: q for q in leg.get('questions', [])}
    return [*leg['lines'], *(questions[q]['reply'] for q in asked if q in questions)]


def _can_go(pack, state):
    index = state['leg']
    support = state['support'].get(str(index), {})
    heard = set(state['heard'].get(str(index), []))
    leg = pack['legs'][index]
    asked = state.get('questions', {}).get(str(index), [])
    if leg.get('required_question') and leg['required_question'] not in asked:
        return False
    replies_heard = all(q['reply']['id'] in heard for q in leg.get('questions', []) if q['id'] in asked)
    return (_visible_text(state, index) or any(support.get(key) for key in ('english', 'route'))
            or all(line['id'] in heard for line in _received_lines(leg, state, index))
            or (pack.get('mission_id') not in ('town-generated', 'town-procedural') and support.get('clarify')
                and leg['clarify']['id'] in heard and replies_heard))


def public(conn, row, awarded_now=False):
    from services.journey_games import _reward
    from services.progression import snapshot
    from services.first_steps_practice import _identity
    saved, root, pack = _runtime(conn, row)
    from services.route_jobs import project_audio
    project_audio(pack, row['id'])
    state = root.get('review') or root
    reviewing = bool(root.get('review'))
    index, phase = state['leg'], state['phase']
    leg = pack['legs'][index]
    support = state['support'].get(str(index), {})
    speakers = pack.get('speakers', SPEAKERS)
    first_checks = _first_checks(conn, row, pack)
    notebook = [{'speaker': speakers[item['speaker']], 'lines': [_line(x, visible=_visible_text(state, i), translated=bool(state['support'].get(str(i), {}).get('english'))) for x in _received_lines(item, state, i)]}
                for i, item in enumerate(pack['legs'][:index+1]) if not reviewing or i == index]
    encounters = [{'position': pack['legs'][0]['start'], 'speaker': speakers[pack['legs'][0]['speaker']]}]
    for i, item in enumerate(pack['legs']):
        if i <= index:
            for contact in item.get('visible_contacts', []):
                encounters.append({'position': contact['position'], 'speaker': speakers[contact['speaker']]})
        if index > i or (index == i and phase in ('arrived', 'completed')):
            if not any(contact['position'] == item['target'] for contact in encounters):
                encounters.append({'position': item['target'], 'speaker': speakers[item['arrival_speaker']]})
    received_words = _received_words(pack, index)
    stages = [{'name': speakers[item['arrival_speaker']]['name_en'] if i < len(pack['legs'])-1 else 'The letter',
               'name_ru': speakers[item['arrival_speaker']]['name'] if i < len(pack['legs'])-1 else 'Письмо',
               'title': item['review_title'] if phase == 'completed' or reviewing else '',
               'title_ru': item['review_title_ru'] if phase == 'completed' or reviewing else ''}
              for i, item in enumerate(pack['legs'])]
    if pack.get('town'):
        for i, stage in enumerate(stages):
            if not (i < index or phase == 'completed' or (i == index and phase == 'arrived')):
                stage.update(name=f'Stop {i + 1}', name_ru=f'Остановка {i + 1}')
        stages[-1].update(name='Complete', name_ru='Завершение')
    unresolved_town = pack.get('town') and phase != 'completed'
    delivery = {'revision': saved['revision'], 'phase': phase, 'leg': index, 'title_ru': 'Доставка для Барсика' if unresolved_town else pack['title_ru'],
                'envelope': pack['envelope'], 'map': deepcopy(pack['map']), 'position': state['position'], 'heading': state['heading'],
                'draft': state['draft'], 'last_path': state['last_path'], 'objective': leg['objective'], 'objective_ru': leg['objective_ru'],
                'speaker': speakers[leg['speaker']], 'lines': [_line(x, visible=_visible_text(state, index), translated=bool(support.get('english'))) for x in _received_lines(leg, state, index)],
                'support': support, 'feedback': state['feedback'], 'notebook': notebook, 'encounters': encounters,
                'mode': state['mode'], 'heard': state['heard'].get(str(index), []), 'can_go': bool(_can_go(pack, state)),
                'text_visible': _visible_text(state, index), 'reviewing': reviewing, 'stages': stages,
                'clarify_prompt': leg['clarify_prompt'],
                'glossary': [{'form': w['form'], 'lemma': w['lemma']} for w in received_words] if _visible_text(state, index) else [],
                'arrival_speaker': {**speakers[leg['arrival_speaker']], **({} if phase in ('arrived', 'completed') else {'role': '', 'role_en': ''})}, 'first_checks': first_checks}
    if pack.get('town'):
        # UI headings must not translate the clue before the learner reads or
        # hears it. English directions remain an explicit, recorded help action.
        if not support.get('english'):
            delivery['objective'] = 'Follow the directions'
            delivery['objective_ru'] = 'Следуй указаниям'
        if phase not in ('arrived', 'completed'):
            delivery['arrival_speaker'] = {'name': '', 'name_en': '', 'role': '', 'role_en': '', 'portrait': ''}
        delivery['map']['closures'] = [closure for closure in delivery['map'].get('closures', [])
                                      if closure.get('from_leg', 0) <= index]
        asked = state.get('questions', {}).get(str(index), [])
        delivery.update(
            walked=state['walked'],
            questions=[{**{key: q[key] for key in ('id', 'text', 'text_en') if key in q},
                        **({'reply': _line(q['reply'], visible=_visible_text(state, index), translated=bool(support.get('english')))} if q['id'] in asked else {})}
                       for q in leg.get('questions', [])],
            question_required=bool(leg.get('required_question') and leg['required_question'] not in asked),
            inventory=deepcopy(state.get('inventory', [])),
            interaction='guide' if leg.get('guide') else None,
            transport_leg=bool(leg.get('transport')),
        )
        if phase in ('arrived', 'completed'):
            for field in ('arrival_text', 'arrival_text_ru', 'arrival_action_label', 'arrival_action_label_ru'):
                if leg.get(field):
                    delivery[field] = leg[field]
        if phase == 'completed':
            for field in ('completion_text', 'completion_text_ru'):
                if pack.get(field):
                    delivery[field] = pack[field]
        if leg.get('transport'):
            bus = leg['transport']
            transit = state.get('transport', {}).get(str(index), {})
            nodes = {node['id']: node for node in pack['map']['nodes']}
            delivery['transport'] = {key: bus[key] for key in ('id', 'label', 'label_ru', 'board')}
            delivery['transport'].update(status=transit.get('status', 'waiting'),
                stop_id=transit.get('stop_id', bus['board']),
                stops=[{'id': stop, 'label': nodes[stop]['label_en'], 'label_ru': nodes[stop]['label']} for stop in bus['stops']])
    if support.get('clarify'):
        delivery['clarification'] = _line(leg['clarify'], visible=_visible_text(state, index), translated=bool(support.get('english')))
    if support.get('route'):
        delivery['guided_path'] = leg['route']
    if support.get('word'):
        word = next(w for w in received_words if w['lemma'] == support['word'])
        delivery['word'] = {k: word[k] for k in ('form', 'lemma', 'sentence', 'translation', 'target_meaning')}
    if phase == 'completed':
        delivery['ending'] = _line(pack['ending'], translated=True)
        checks = {r['leg']: r for r in first_checks}
        delivery['practice_sections'] = [{'leg': i, **stage, 'needs_practice': not checks.get(i, {}).get('correct') or bool(checks.get(i, {}).get('assisted'))} for i, stage in enumerate(stages)]
    result = {'profile_id': row['profile_id'], 'id': row['id'], 'game_id': 'directions', 'title': 'A delivery for Barsik' if unresolved_town else pack['title'],
              'phase': 'practice' if reviewing else 'completed' if phase == 'completed' else 'play',
              'round_index': index, 'total_rounds': len(pack['legs']), 'round': None, 'result': None,
              'source': pack['source'], 'reward': None, 'sample': pack.get('sample', False), 'delivery': delivery}
    if phase == 'completed':
        known = {r[0].casefold() for r in conn.execute('SELECT lemma FROM words')}
        result['reward'] = _reward(conn, row, awarded_now)
        result['words'] = [] if pack.get('sample') else [dict(w, card_key=_identity(w), in_vocabulary=w['lemma'].casefold() in known) for w in pack['vocabulary_refs']]
        result['study_available'] = bool(not pack.get('sample') and current_app.config.get('NATIVE_FLASHCARDS_ENABLED'))
        if row['profile_id']:
            result['progression'] = snapshot(conn, row['profile_id'])
    return result


def validate_path(pack, leg, path, *, arrival=False):
    nodes = {n['id']: n for n in pack['map']['nodes']}
    edges = {frozenset(e) for e in pack['map']['edges']}
    if (not isinstance(path, list) or not 1 <= len(path) <= (128 if pack.get('town') else 32)
            or any(not isinstance(n, str) or n not in nodes for n in path) or path[0] != leg['start']
            or any(frozenset((a, b)) not in edges for a, b in zip(path, path[1:]))):
        raise LearningError('invalid_route', 'Choose connected points, starting from the current encounter.')
    if arrival and (len(path) < 2 or (not pack.get('town') and (path[-1] == leg['start'] or nodes[path[-1]]['kind'] in ('street', 'junction')))):
        raise LearningError('arrival_required', 'Choose a place or doorway to finish your route.')


def assess(pack, index, path):
    pack = clarify_pack(compatible_pack(pack))
    if pack.get('town'):
        return town_assessment(pack, index, path)
    leg = pack['legs'][index]
    nodes = {n['id']: n for n in pack['map']['nodes']}
    for rule in leg['rules']:
        if not matches_rule(rule, path, nodes):
            return {'correct': False, **{key: rule[key] for key in ('code', 'en', 'ru')}}
    if path[-1] != leg['target']:
        return {'correct': False, 'code': 'place',
                'en': 'You have reached a different place. Read or replay the directions and choose where to stop.',
                'ru': 'Ты пришёл в другое место. Прочитай или послушай указания и выбери, где остановиться.'}
    return {'correct': True, 'code': 'arrived', 'en': 'You found the right place.', 'ru': 'Ты нашёл нужное место.'}


def _arrival_effects(leg, state):
    inventory = state.setdefault('inventory', [])
    item = leg.get('arrival_item')
    if item and not any(saved['id'] == item['id'] for saved in inventory):
        inventory.append(deepcopy(item))
    state['inventory'] = [item for item in inventory if item['id'] != leg.get('arrival_remove_item')]


def _check_arrival(conn, session_id, pack, state, root, path):
    index = state['leg']
    result = assess(pack, index, path)
    result.update(assisted=bool(state['support'].get(str(index))),
                  presentation='reading' if state['text_seen'].get(str(index)) else 'listening',
                  recordings=list(state['heard'].get(str(index), [])))
    if result.get('navigation'):
        kind = 'navigation'
        if root.get('review'):
            result['review_id'] = state['id']
    elif root.get('review'):
        kind = 'review'
        result['review_id'] = state['id']
    else:
        kind = 'correction' if conn.execute("SELECT 1 FROM journey_route_actions WHERE session_id=? AND leg=? AND attempt_kind='first'", (session_id, index)).fetchone() else 'first'
    # A closed crossing stops movement there, even when the submitted plan
    # continues farther. Keep the submitted route in its separate action receipt.
    travelled = travelled_path(pack, index, path)
    prior_steps = len(state.get('walked', [path[0]]))
    movement = travelled[max(0, prior_steps - 1):] if pack.get('town') else travelled
    state.update(position=travelled[-1], walked=travelled[:], last_path=movement, feedback=result,
                 phase='arrived' if result['correct'] else 'feedback')
    if len(travelled) > 1:
        nodes = {node['id']: node for node in pack['map']['nodes']}
        a, b = nodes[travelled[-2]], nodes[travelled[-1]]
        state['heading'] = 'east' if b['x'] > a['x'] else 'west' if b['x'] < a['x'] else 'south' if b['y'] > a['y'] else 'north'
    if result['correct']:
        _arrival_effects(pack['legs'][index], state)
    return kind, result


def _transport_path(pack, stops):
    """Resolve the ordered bus stops to connected streets in the frozen map."""
    from collections import deque
    # New towns distinguish roads from footpaths. Older saved maps predate
    # that metadata and retain their original route graph.
    segments = pack['map'].get('street_segments')
    drivable = None if segments is None else {
        frozenset((segment['from'], segment['to'])) for segment in segments
        if segment['kind'] in ('main', 'residential')
    }
    adjacent = {}
    for a, b in pack['map']['edges']:
        if drivable is not None and frozenset((a, b)) not in drivable:
            continue
        adjacent.setdefault(a, []).append(b)
        adjacent.setdefault(b, []).append(a)
    path = [stops[0]]
    for target in stops[1:]:
        queue, seen = deque([[path[-1]]]), {path[-1]}
        found = None
        while queue:
            route = queue.popleft()
            if route[-1] == target:
                found = route
                break
            for node in sorted(adjacent.get(route[-1], [])):
                if node not in seen:
                    seen.add(node)
                    queue.append([*route, node])
        if found is None:
            raise LearningError('route_unavailable', 'This bus route is unavailable.', 409)
        path.extend(found[1:])
    return path


def _apply_action(conn, session_id, pack, root, action, payload):
    """Mutate runtime only; the caller writes one receipt in the same transaction."""
    state = root.get('review') or root
    reviewing = bool(root.get('review'))
    index, phase = state['leg'], state['phase']
    leg = pack['legs'][index]
    kind, result, complete = None, {}, False
    if action == 'review_start' and root['phase'] == 'completed' and not reviewing:
        chosen = payload['leg']
        if type(chosen) is not int or not 0 <= chosen < len(pack['legs']):
            raise LearningError('invalid_section', 'Choose a section from this delivery.')
        root['review'] = _new_state(pack, root['mode'], chosen)
        root['review']['id'] = identifier()
        return chosen, None, {}, False
    if action == 'review_exit' and reviewing:
        root.pop('review')
        return index, None, {}, False
    if phase == 'completed':
        raise LearningError('delivery_finished', 'Choose a section to practise or start another delivery.', 409)
    if action == 'begin' and phase == 'dialogue':
        state['phase'] = 'planning'
    elif action == 'ask' and phase in ('dialogue', 'planning', 'feedback'):
        question_id = payload['question_id']
        question = next((q for q in leg.get('questions', []) if q['id'] == question_id), None)
        if not isinstance(question_id, str) or question is None:
            raise LearningError('invalid_question', 'Choose one of the questions in this conversation.')
        asked = state.setdefault('questions', {}).setdefault(str(index), [])
        if question_id not in asked:
            asked.append(question_id)
    elif action in ('board', 'ride', 'alight') and phase == 'planning' and leg.get('transport'):
        bus = leg['transport']
        transit = state.setdefault('transport', {}).setdefault(str(index), {'status': 'waiting', 'stop_id': bus['board'], 'path': [bus['board']]})
        if action == 'board':
            if payload['transport_id'] != bus['id'] or transit['status'] != 'waiting' or state['position'] != bus['board']:
                raise LearningError('invalid_transport', 'Board this bus at its departure stop.', 409)
            if not _can_go(pack, state):
                raise LearningError('listen_first', 'Listen to or read the directions before boarding.', 409)
            transit['status'] = 'aboard'
        elif action == 'ride':
            target = payload['stop_id']
            if transit['status'] != 'aboard' or not isinstance(target, str) or target not in bus['stops']:
                raise LearningError('invalid_stop', 'Choose an upcoming stop on this bus.', 409)
            start_index, end_index = bus['stops'].index(transit['stop_id']), bus['stops'].index(target)
            if end_index <= start_index:
                raise LearningError('invalid_stop', 'Choose a stop ahead of the bus.', 409)
            travelled = _transport_path(pack, bus['stops'][start_index:end_index+1])
            transit['path'].extend(travelled[1:])
            transit['stop_id'] = target
            state.update(position=target, draft=transit['path'][:], last_path=travelled)
        else:
            if transit['status'] != 'aboard' or transit['stop_id'] == bus['board']:
                raise LearningError('invalid_stop', 'Travel to a stop before getting off.', 409)
            kind, result = _check_arrival(conn, session_id, pack, state, root, transit['path'])
            transit['status'] = 'arrived' if result['correct'] else 'waiting'
    elif action == 'mode' and phase in ('dialogue', 'planning', 'feedback'):
        if payload['mode'] not in ('reading', 'listening'):
            raise LearningError('invalid_mode', 'Choose reading or listening practice.')
        state['mode'] = payload['mode']
        if state['mode'] == 'reading':
            state['text_seen'][str(index)] = True
    elif action == 'listen' and phase in ('dialogue', 'planning', 'feedback', 'arrived'):
        sources = _received_lines(leg, state, index)
        if state['support'].get(str(index), {}).get('clarify'):
            sources.append(leg['clarify'])
        if type(payload['leg']) is not int or payload['leg'] != index or payload['line_id'] not in [line['id'] for line in sources]:
            raise LearningError('invalid_recording', 'Replay a recording from the current conversation.')
        heard = state['heard'].setdefault(str(index), [])
        if payload['line_id'] not in heard:
            heard.append(payload['line_id'])
    elif action in ('plan', 'go') and phase == 'planning':
        if leg.get('transport'):
            raise LearningError('transport_required', 'Board the bus and choose where to get off.', 409)
        path = payload['path']
        validate_path(pack, leg, path, arrival=action == 'go')
        walked = state.get('walked', [leg['start']])
        if pack.get('town') and (path[:len(walked)] != walked or (action == 'go' and len(path) <= len(walked))):
            raise LearningError('invalid_route', 'Continue the route from Barsik’s current position.')
        if action == 'go' and leg.get('requires_item') and not any(item['id'] == leg['requires_item'] for item in state.get('inventory', [])):
            raise LearningError('item_required', 'Collect the parcel before continuing.', 409)
        if action == 'go' and not _can_go(pack, state):
            raise LearningError('listen_first', 'Listen to the directions, or choose to read them.', 409)
        state['draft'] = path
        if action == 'go':
            kind, result = _check_arrival(conn, session_id, pack, state, root, path)
    elif action == 'talk' and phase == 'arrived' and index < len(pack['legs'])-1 and not reviewing:
        next_index = index+1
        next_leg = pack['legs'][next_index]
        state.update(leg=next_index, phase='dialogue', heading=next_leg['heading'], draft=[next_leg['start']], walked=[next_leg['start']], last_path=[], feedback=None)
        if state['mode'] == 'reading':
            state['text_seen'][str(next_index)] = True
    elif action == 'continue' and phase == 'feedback' and state['feedback'].get('navigation'):
        state.update(phase='planning', draft=state['walked'][:], last_path=[], feedback=None)
    elif action == 'retry' and phase == 'feedback':
        state.update(phase='planning', position=leg['start'], heading=leg['heading'], draft=[leg['start']], walked=[leg['start']], last_path=[], feedback=None)
        state.get('transport', {}).pop(str(index), None)
    elif action == 'help' and phase in ('dialogue', 'planning', 'feedback'):
        option = payload['kind']
        permitted = {'english', 'clarify', 'route', 'transcript'} | {'word:'+w['lemma'] for w in _received_words(pack, index)}
        if not isinstance(option, str) or option not in permitted:
            raise LearningError('invalid_help', 'Choose help for the directions you have received.')
        support = state['support'].setdefault(str(index), {})
        if option.startswith('word:'):
            support['word'] = option[5:]
            state['text_seen'][str(index)] = True
        else:
            support[option] = True
        if option in ('transcript', 'english'):
            state['text_seen'][str(index)] = True
        if option == 'route':
            state.update(phase='planning', position=leg['start'], heading=leg['heading'], draft=leg['route'], walked=[leg['start']], last_path=[], feedback=None)
            if leg.get('transport'):
                state['draft'] = [leg['start']]
                state.get('transport', {}).pop(str(index), None)
    elif action == 'deliver' and phase == 'arrived' and index == len(pack['legs'])-1 and not reviewing:
        state['phase'] = 'completed'
        complete = True
    else:
        raise LearningError('wrong_phase', 'Continue from the current part of this delivery.', 409)
    return index, kind, result, complete


def command(session_id, data):
    from services.journey_games import _owner, _read_row, _credit
    fields = {'request_id', 'revision', 'action', 'payload'}
    if not isinstance(data, dict) or set(data) != fields or not isinstance(data['payload'], dict):
        raise LearningError('invalid_input', 'Send a delivery action with its saved version.')
    request_id, action, payload = data['request_id'], data['action'], data['payload']
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id) or type(data['revision']) is not int:
        raise LearningError('invalid_request', 'Reload this delivery and try again.')
    allowed = {'begin': set(), 'plan': {'path'}, 'go': {'path'}, 'talk': set(), 'deliver': set(), 'retry': set(), 'continue': set(),
               'help': {'kind'}, 'mode': {'mode'}, 'listen': {'line_id', 'leg'}, 'review_start': {'leg'}, 'review_exit': set(),
               'ask': {'question_id'}, 'board': {'transport_id'}, 'ride': {'stop_id'}, 'alight': set()}
    if not isinstance(action, str) or action not in allowed or set(payload) != allowed[action]:
        raise LearningError('invalid_action', 'Choose an available delivery action.')
    digest = payload_hash(data)
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile, guest = _owner(conn)
        row = _read_row(conn, session_id, profile, guest)
        if json.loads(row['content_json']).get('version') != VERSION:
            raise LearningError('legacy_route', 'This saved game uses the earlier route format.', 409)
        prior = conn.execute('SELECT payload_hash FROM journey_route_actions WHERE session_id=? AND request_id=?', (session_id, request_id)).fetchone()
        if prior:
            if prior[0] != digest:
                raise LearningError('idempotency_conflict', 'This request already has different contents.', 409)
            return public(conn, row)
        from services.route_jobs import status as preparation_status
        preparing = preparation_status(conn, row)
        if preparing:
            raise LearningError('preparation_required', 'Finish preparing this delivery before setting off.', 409)
        saved, root, pack = _runtime(conn, row)
        if data['revision'] != saved['revision']:
            raise LearningError('state_conflict', 'This delivery changed in another tab. Reopen the current route.', 409)
        if row['superseded_at'] is not None:
            raise LearningError('delivery_finished', 'This delivery is no longer active.', 409)
        if conn.execute('SELECT COUNT(*) FROM journey_route_actions WHERE session_id=?', (session_id,)).fetchone()[0] >= 1500:
            raise LearningError('action_limit', 'Start a new delivery to continue practising.', 429)
        index, kind, result, complete = _apply_action(conn, session_id, pack, root, action, payload)
        now, credited = timestamp(), False
        if complete:
            conn.execute('UPDATE journey_game_sessions SET completed_at=?,updated_at=? WHERE id=?', (now, now, session_id))
            if profile:
                credited = bool(_credit(conn, _read_row(conn, session_id, profile, guest), now))
        conn.execute('INSERT INTO journey_route_actions VALUES (?,?,?,?,?,?,?,?,?,?)',
                     (identifier(), session_id, request_id, digest, action, index, kind, encoded(payload), encoded(result), now))
        conn.execute('UPDATE journey_route_state SET revision=revision+1,state_json=? WHERE session_id=?', (encoded(root), session_id))
        conn.execute('UPDATE journey_game_sessions SET updated_at=? WHERE id=?', (now, session_id))
        return public(conn, _read_row(conn, session_id, profile, guest), credited)
