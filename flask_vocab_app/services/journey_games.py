"""Games purchased with Lingocoins and played with a wider vocabulary."""
import hashlib
import json
import random
import re
import sqlite3

from flask import current_app

from repositories.learning_repository import LearningError, encoded, identifier, timestamp, transaction
from services.first_delivery import _owner
from services.first_steps import completed_lessons
from services.journey_game_content import NEW_GAMES
from services.scene_builder import GAME as SCENE_GAME
from services.progression import RULES, award, snapshot, study_day
from services.game_access import access_state, require_access, mark_started, shop_state, preserve_played_access, GAME_IDS

VERSION = 'journey-games-v1'
GAMES = (
    {'id': 'pack-bag', 'title': 'Pack the bag', 'description': 'Match the Russian messages to picture cards for Barsik’s bag.',
     'lesson_id': 'bag', 'lesson_title': 'What’s in the bag?'},
    {'id': 'directions', 'title': 'Follow the directions', 'description': 'Follow Russian directions to guide Barsik through the streets.',
     'lesson_id': 'directions', 'lesson_title': 'Which way?'},
) + (SCENE_GAME,) + NEW_GAMES
OBJECTS = ({'id': 'letter', 'visual': 'letter', 'label': 'Letter'},
           {'id': 'map', 'visual': 'map', 'label': 'Map'},
           {'id': 'apple', 'visual': 'apple', 'label': 'Apple'},
           {'id': 'cup', 'visual': 'cup', 'label': 'Cup'})
HEADINGS = ('north', 'east', 'south', 'west')


def _scope(profile_id, guest_token):
    return ('profile_id=?', (profile_id,)) if profile_id else ('profile_id IS NULL AND guest_token=?', (guest_token,))


def _game(game_id):
    game = next((game for game in GAMES if game['id'] == game_id), None)
    if game is None:
        raise LearningError('not_found', 'This game was not found.', 404)
    return game


def _lesson_sources(conn, profile_id, guest_token):
    lessons = {lesson['id']: lesson for lesson in completed_lessons(conn, profile_id, guest_token)}
    where, params = _scope(profile_id, guest_token)
    for row in conn.execute('SELECT lesson_json FROM journey_game_unlocks WHERE ' + where, params):
        frozen = json.loads(row['lesson_json'])
        for lesson in [frozen, *frozen.get('related_lessons', [])]:
            lessons.setdefault(lesson['id'], {key: value for key, value in lesson.items() if key != 'related_lessons'})
    return lessons


def sync_unlocks(conn, profile_id, guest_token, *, now=None):
    """Compatibility hook for profile transfers; intro completion grants nothing."""
    if profile_id:
        preserve_played_access(conn, profile_id)


def _snapshot_legacy_unlocks(conn, profile_id, guest_token, *, now=None):
    """Historical migration 32 only. These snapshots no longer grant access."""
    now = timestamp() if now is None else now
    lessons = _lesson_sources(conn, profile_id, guest_token)
    for game in GAMES:
        lesson = lessons.get(game['lesson_id'])
        if lesson:
            lesson = dict(lesson) | {'related_lessons': list(lessons.values())}
            conn.execute('INSERT OR IGNORE INTO journey_game_unlocks(id,profile_id,guest_token,game_id,lesson_id,lesson_version,lesson_json,unlocked_at) VALUES (?,?,?,?,?,?,?,?)',
                         (identifier(), profile_id, guest_token, game['id'], lesson['id'], lesson['version'], encoded(lesson), now))


def backfill_unlocks(conn):
    """Migration-only backfill. Existing unlock snapshots are never overwritten."""
    previous = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        owners = conn.execute('SELECT profile_id,guest_token FROM first_steps_attempts WHERE completed_at IS NOT NULL UNION SELECT profile_id,guest_token FROM journey_game_unlocks').fetchall()
        for owner in owners:
            _snapshot_legacy_unlocks(conn, owner['profile_id'], owner['guest_token'])
    finally:
        conn.row_factory = previous


def read_catalogue():
    with transaction(current_app.config['DB_PATH']) as conn:
        profile_id, guest_token = _owner(conn)
        where, params = _scope(profile_id, guest_token)
        lessons = _lesson_sources(conn, profile_id, guest_token)
        public_demo = bool(current_app.config.get('PUBLIC_DEMO'))
        access = access_state(conn, profile_id, guest_token, enabled=not public_demo)
        played = {row[0] for row in conn.execute('SELECT DISTINCT game_id FROM journey_game_sessions WHERE ' + where, params)}
        active = {row['game_id']: row['id'] for row in conn.execute(
            'SELECT id,game_id FROM journey_game_sessions WHERE ' + where
            + " AND completed_at IS NULL AND superseded_at IS NULL AND (json_extract(content_json,'$.options.word_policy')='mixed-v1'"
            + " OR json_extract(content_json,'$.version') IN ('journey-delivery-v2','scene-builder-v1', 'scene-builder-v2', 'scene-builder-v3'))", params)}
        games = []
        for game in GAMES:
            if game['id'] == 'pairs':
                continue  # Existing sessions/URLs remain readable; discovery now teaches grammar.
            lesson = lessons.get(game['lesson_id'])
            games.append(dict(game) | {'lesson_title': lesson['title'] if lesson else game['lesson_title'],
                                      'lesson_href': '#first-steps/' + game['lesson_id'],
                                      **access[game['id']], 'new': access[game['id']]['new'] and game['id'] not in played,
                                      'active_session_id': active.get(game['id'])})
        games.sort(key=lambda game: GAME_IDS.index(game['id']))
        if public_demo:
            from services.demo_games import SAMPLE_GAMES
            for entry in games:
                sample = entry['id'] in SAMPLE_GAMES
                entry.update(availability='sample' if sample else 'local-only', unlocked=sample, new=False,
                             active_session_id=active.get(entry['id']) if sample else None)
        from services.journey_vocabulary import catalogue_sources
        if public_demo:
            from services.route_dispatch import catalogue as delivery_catalogue
        else:
            from services.route_mission import catalogue as delivery_catalogue
        return {'profile_id': profile_id, 'public_demo': public_demo, 'games': games,
                'shop': shop_state(conn, profile_id, enabled=not public_demo), 'sources': catalogue_sources(conn, profile_id, guest_token),
                'deliveries': delivery_catalogue() if current_app.config.get('DIRECTIONS_DELIVERIES_ENABLED', True) else []}


def purchase_game(game_id, request_id, expected_price):
    if current_app.config.get('PUBLIC_DEMO'):
        raise LearningError('demo_unavailable', 'Game purchases are unavailable in the public demo.', 403)
    from services.game_access import purchase
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile_id, _guest_token = _owner(conn)
        return purchase(conn, profile_id, game_id, request_id, expected_price)


def _clue(vocabulary):
    text = vocabulary['sentence']
    return {'text': text, 'audio_key': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def movement_path(board, commands):
    point = dict(board['start'])
    path = [dict(point)]
    for command in commands:
        direction = (HEADINGS.index(point['heading']) + {'left': -1, 'straight': 0, 'right': 1}[command]) % 4
        dx, dy = ((0, -1), (1, 0), (0, 1), (-1, 0))[direction]
        point = {'x': point['x'] + dx, 'y': point['y'] + dy, 'heading': HEADINGS[direction]}
        if not 0 <= point['x'] < board['width'] or not 0 <= point['y'] < board['height']:
            raise LearningError('invalid_route', 'Keep Barsik on the map.')
        path.append(dict(point))
    return path


def _content(game, lesson, seed):
    if game['id'] not in ('pack-bag', 'directions'):
        from services.journey_game_content import build_content
        return build_content(game, lesson, seed)
    rng = random.Random(seed)
    vocab = {item['lemma']: item for item in lesson['vocabulary']}
    rounds = []
    if game['id'] == 'pack-bag':
        vocabulary = {'letter': vocab['письмо'], 'map': vocab['карта']}
        singles = ['letter', 'map']
        rng.shuffle(singles)
        targets = [[singles[0]], [singles[1]], rng.sample(singles, 2)]
        for index, target in enumerate(targets):
            objects = [dict(item) for item in OBJECTS]
            rng.shuffle(objects)
            rounds.append({'id': f'bag-{index + 1}', 'prompt': 'Put these things in Barsik’s bag.',
                           'clues': [_clue(vocabulary[item]) for item in target], 'objects': objects,
                           'max_choices': len(target), 'expected_answer': sorted(target),
                           'hint': ' '.join(vocabulary[item]['translation'] for item in target),
                           'feedback': ' '.join(f'«{vocabulary[item]["form"]}» means {vocabulary[item]["target_meaning"]}.' for item in target)})
    else:
        vocabulary = {'straight': vocab['прямо'], 'left': vocab['налево'], 'right': vocab['направо']}
        commands = rng.sample(list(vocabulary), 3)
        targets = [[commands[0]], [commands[1]], [commands[2], rng.choice(list(vocabulary))]]
        for index, target in enumerate(targets):
            board = {'width': 5, 'height': 5, 'start': {'x': 2, 'y': 3, 'heading': 'north'},
                     'landmarks': [{'x': 0, 'y': 0, 'visual': 'post-office'}, {'x': 4, 'y': 0, 'visual': 'market'}]}
            movement_path(board, target)
            rounds.append({'id': f'directions-{index + 1}', 'prompt': 'Show Barsik which way to go.',
                           'clues': [_clue(vocabulary[item]) for item in target], 'board': board,
                           'max_choices': len(target), 'expected_answer': target,
                           'hint': ' '.join(vocabulary[item]['translation'] for item in target),
                           'feedback': ' '.join(f'«{vocabulary[item]["form"]}» means {vocabulary[item]["target_meaning"]}.' for item in target)})
    return {'version': VERSION, 'lesson_version': lesson['version'], 'title': game['title'],
            'source': {'lesson_id': lesson['id'], 'title': lesson['title'], 'href': '#first-steps/' + lesson['id']}, 'rounds': rounds,
            'vocabulary_refs': list(vocabulary.values()), 'media_texts': sorted({clue['text'] for item in rounds for clue in item['clues']})}


def normalise_answer(item, answer, game_id):
    """Validate each mechanic against its frozen choices, never client metadata."""
    if not isinstance(answer, list) or not 1 <= len(answer) <= item['max_choices'] or any(not isinstance(value, str) for value in answer):
        raise LearningError('invalid_answer', 'Choose an answer using the pieces in this round.')
    mechanic = item.get('mechanic', game_id)
    if mechanic not in ('pack-bag', 'directions') and len(answer) != item['max_choices']:
        raise LearningError('answer_incomplete', 'Try each item in this round before checking.')
    if mechanic == 'scene-builder':
        slots = item['scene_builder']['slots']
        if any(value not in {choice['id'] for choice in slot['choices']} for slot, value in zip(slots, answer)):
            raise LearningError('invalid_answer', 'Choose one form from each part of this sentence.')
        return answer
    if mechanic in ('pairs', 'mailbox-sort'):
        left = {entry['id'] for entry in item['left' if mechanic == 'pairs' else 'sentences']}
        right = {entry['id'] for entry in item['right' if mechanic == 'pairs' else 'bins']}
        mappings = [value.split(':') for value in answer]
        if any(len(pair) != 2 or pair[0] not in left or pair[1] not in right for pair in mappings):
            raise LearningError('invalid_answer', 'Use the words and choices shown in this round.')
        if len({pair[0] for pair in mappings}) != len(mappings) or (mechanic == 'pairs' and len({pair[1] for pair in mappings}) != len(mappings)):
            raise LearningError('invalid_answer', 'Give each item one answer.')
        return sorted(answer)
    if mechanic == 'pack-bag':
        allowed = {entry['id'] for entry in item['objects']}
    elif mechanic == 'directions':
        allowed = {'left', 'straight', 'right'}
    elif mechanic in ('missing-stamp', 'radio'):
        allowed = {entry['id'] for entry in item['choices']}
    elif mechanic == 'detective':
        allowed = {entry['id'] for entry in item['destinations']}
    elif mechanic == 'letter-back':
        allowed = {entry['id'] for entry in item['tiles']}
    else:
        raise LearningError('game_unavailable', 'This game needs an application update.', 409)
    if any(value not in allowed for value in answer) or (mechanic != 'directions' and len(set(answer)) != len(answer)):
        raise LearningError('invalid_answer', 'Choose the objects or directions shown in this round.')
    if mechanic == 'letter-back':
        # Two visually identical tiles are interchangeable. Canonical IDs keep
        # retries and feedback stable without requiring an invisible ID order.
        text_by_id = {tile['id']: tile['text'] for tile in item['tiles']}
        equivalent = {}
        canonical_order = [*item['expected_answer'], *(tile['id'] for tile in item['tiles'] if tile['id'] not in item['expected_answer'])]
        for tile_id in canonical_order:
            equivalent.setdefault(text_by_id[tile_id], []).append(tile_id)
        return [equivalent[text_by_id[tile_id]].pop(0) for tile_id in answer]
    return sorted(answer) if mechanic == 'pack-bag' else answer


def assess_answer(item, answer):
    """Reproducible scoring for feedback and evidence, using frozen answers.

    Old rounds keep their original all-or-nothing score. New multi-item rounds
    credit correct matches/placements, so one mistake does not erase the rest.
    """
    expected = item['expected_answer']
    correct = answer == expected
    if not item.get('mechanic'):
        return {'correct': correct, 'score': int(correct), 'matched': int(correct), 'total': 1}
    if item['mechanic'] in ('pairs', 'mailbox-sort'):
        matched = len(set(answer) & set(expected))
    elif item['mechanic'] == 'letter-back':
        text_by_id = {tile['id']: tile['text'] for tile in item['tiles']}
        matched = sum(text_by_id.get(value) == text_by_id[expected[index]]
                      for index, value in enumerate(answer) if index < len(expected))
        correct = len(answer) == len(expected) and matched == len(expected)
    else:
        matched = sum(value == expected[index] for index, value in enumerate(answer) if index < len(expected))
    return {'correct': correct, 'score': matched / len(expected), 'matched': matched, 'total': len(expected)}


def _read_row(conn, session_id, profile_id, guest_token):
    where, params = _scope(profile_id, guest_token)
    row = conn.execute('SELECT * FROM journey_game_sessions WHERE id=? AND ' + where, (session_id, *params)).fetchone()
    if row is None:
        raise LearningError('not_found', 'This game was not found for your profile.', 404)
    return row


def _reward(conn, row, awarded_now):
    if row['profile_id']:
        reason = 'awarded'
        if not row['reward_amount']:
            event = conn.execute('SELECT id,content_key,created_at FROM progression_events WHERE profile_id=? AND activity=? AND source_key=?',
                                 (row['profile_id'], 'journey_game', row['id'])).fetchone()
            claim = None
            if event:
                claim = conn.execute('SELECT amount FROM progression_claims WHERE profile_id=? AND category=? AND content_key=? AND study_day=?',
                                     (row['profile_id'], 'activity', 'journey_game:' + event['content_key'], study_day(conn, row['profile_id'], event['created_at']))).fetchone()
            reason = 'already_rewarded' if claim and claim['amount'] else 'daily_cap'
        return {'amount': row['reward_amount'], 'status': 'credited', 'awarded_now': awarded_now, 'reason': reason}
    # Saving a new profile claims completed lessons before games. Project that
    # same order without minting a temporary wallet or promising repeat coins.
    lessons = conn.execute('SELECT COUNT(*) FROM first_steps_attempts WHERE profile_id IS NULL AND guest_token=? AND completed_at IS NOT NULL', (row['guest_token'],)).fetchone()[0]
    remaining = max(0, RULES['activity_daily_cap'] - RULES['activity_coins'] * lessons)
    claimed, amount = set(), 0
    for saved in conn.execute('SELECT id,game_id,content_json FROM journey_game_sessions WHERE profile_id IS NULL AND guest_token=? AND completed_at IS NOT NULL ORDER BY created_at,rowid', (row['guest_token'],)):
        identity = (saved['game_id'], json.loads(saved['content_json'])['lesson_version'])
        eligible = 0 if identity in claimed else min(remaining, RULES['activity_coins'])
        claimed.add(identity)
        remaining -= eligible
        if saved['id'] == row['id']:
            amount = eligible
            break
    return {'amount': amount, 'status': 'pending', 'awarded_now': False, 'reason': 'profile_needed'}


def _public(conn, row, *, awarded_now=False):
    content = json.loads(row['content_json'])
    if content.get('version') == 'journey-delivery-v2':
        from services.route_jobs import public as preparation_public
        preparing = preparation_public(conn, row)
        if preparing:
            return preparing
        from services.route_delivery import public
        return public(conn, row, awarded_now)
    is_radio = content.get('version') == 'radio-broadcast-v1'
    preparation = current_app.extensions['learning'].get('radio_broadcast' if is_radio else 'journey_game_preparation')
    pending = conn.execute('SELECT status FROM journey_game_preparations WHERE session_id=?', (row['id'],)).fetchone()
    if pending and not content['rounds']:
        return {'profile_id': row['profile_id'], 'id': row['id'], 'game_id': row['game_id'], 'title': content['title'],
                'phase': 'preparing', 'round_index': 0, 'total_rounds': 4 if is_radio else content['options']['rounds'],
                'round': None, 'result': None, 'source': content['source'], 'reward': None,
                'preparation': preparation.status(conn, row)}
    answers, hints, acknowledged = (json.loads(row[column]) for column in ('answers_json', 'hints_json', 'acknowledged_json'))
    support = json.loads(row['support_json'])
    index, total = len(acknowledged), len(content['rounds'])
    item = content['rounds'][index] if index < total and row['completed_at'] is None else None
    saved = answers.get(item['id']) if item else None
    practice = support.get('_practice', {})
    practising = practice.get('active', False)
    phase = 'completed' if row['completed_at'] is not None else 'ready' if index == total else 'feedback' if saved else 'play'
    if is_radio and row['completed_at'] is None and not support.get('broadcast', {}).get('started'):
        phase, item, saved = 'listening', None, None
    if practising:
        item = next(r for r in content['rounds'] if r['id'] == practice['queue'][practice['index']])
        saved = {'answer': practice['answer']} if 'answer' in practice else None
        phase = 'practice_feedback' if saved else 'practice'
    public_round, result = None, None
    if item:
        public_fields = ('id', 'mechanic', 'prompt', 'clues', 'objects', 'board', 'max_choices', 'left', 'right', 'sentences', 'bins',
                         'sentence', 'translation', 'objective', 'visual', 'image_url', 'choices', 'destinations', 'tiles', 'audio_required', 'scene_builder')
        public_round = {key: item[key] for key in public_fields if key in item}
        if item.get('mechanic') == 'scene-builder':
            public_round.pop('translation', None)
        round_support = {**support.get('broadcast', {}), **support.get(item['id'], {})} if is_radio else support.get(item['id'], {})
        if practising and practice.get('transcript'):
            round_support = dict(round_support, transcript=True)
        public_round['support'] = {'listened_audio_keys': round_support.get('listened_audio_keys', []), 'transcript': bool(round_support.get('transcript'))}
        if item.get('audio_required') and (is_radio or not saved) and not round_support.get('transcript'):
            public_round['clues'] = [{'audio_key': clue['audio_key']} for clue in item['clues']]
        if item['id'] in hints or practising and practice.get('hint'):
            public_round['hint'] = item['hint']
            if item.get('hint_ru'):
                public_round['hint_ru'] = item['hint_ru']
        if saved:
            assessment = assess_answer(item, saved['answer'])
            result = {'answer': saved['answer'], **assessment, 'expected_answer': item['expected_answer'], 'feedback': item['feedback'], 'explanation': item.get('explanation', ''), 'explanation_ru': item.get('explanation_ru', '')}
            if item.get('mechanic') == 'scene-builder':
                from services.scene_builder import slot_results
                result.update(slot_results=slot_results(item, saved['answer']), correct_sentence=item['correct_sentence'], translation=item['translation'])
            # The public preview has no game-media endpoints or speech provider.
            # Do not advertise recordings (or a stranded Listen heading) there.
            if item.get('answer_audio') and not (content.get('sample') or current_app.config.get('PUBLIC_DEMO')):
                result['answer_audio'] = item['answer_audio'] if isinstance(item['answer_audio'], list) else [item['answer_audio']]
            if item.get('provenance'):
                result['provenance'] = item['provenance']
            if row['game_id'] == 'directions':
                result['path'] = movement_path(item['board'], item['expected_answer'])
    state = {'profile_id': row['profile_id'], 'id': row['id'], 'game_id': row['game_id'], 'title': content['title'],
             'phase': phase, 'round_index': index, 'total_rounds': total, 'round': public_round, 'result': result,
             'source': content['source'], 'reward': None, 'sample': bool(content.get('sample'))}
    if practising:
        state['practice'] = {'mode': practice['mode'], 'index': practice['index'], 'total': len(practice['queue'])}
    if is_radio and content.get('broadcast'):
        broadcast = content['broadcast']
        support_record = support.get('broadcast', {})
        if practising and practice.get('transcript'):
            support_record = dict(support_record, transcript=True)
        state['broadcast'] = {key: broadcast[key] for key in ('title', 'audio_key', 'duration_seconds')}
        state['broadcast'].update(listened=broadcast['audio_key'] in support_record.get('listened_audio_keys', []),
                                  transcript=bool(support_record.get('transcript')))
        if support_record.get('transcript') or row['completed_at'] is not None:
            state['broadcast']['script'] = broadcast['script']
    if row['completed_at'] is not None:
        from services.first_steps_practice import _identity
        state['reward'] = _reward(conn, row, awarded_now)
        state['study_available'] = bool(not content.get('sample') and not is_radio and content.get('vocabulary_refs') and current_app.config.get('NATIVE_FLASHCARDS_ENABLED'))
        known = {r[0].lower().replace('ё', 'е') for r in conn.execute('SELECT lemma FROM words')}
        state['words'] = [{key: e.get(key, '') for key in ('lemma', 'form', 'sentence', 'translation', 'target_meaning', 'pos')}
                          | {'in_vocabulary': e.get('lemma', '').lower().replace('ё', 'е') in known, 'card_key': _identity(e)}
                          for e in content.get('vocabulary_refs', []) if e.get('lemma') and not content.get('sample')]
        if is_radio:
            state['broadcast']['vocabulary'] = state['words']
        assessed = [assess_answer(item, answers[item['id']]['answer']) for item in content['rounds']]
        state['summary'] = {'correct_rounds': sum(item['correct'] for item in assessed), 'total_rounds': total, 'missed_rounds': sum(not item['correct'] for item in assessed),
                            'matched': sum(item['matched'] for item in assessed), 'total': sum(item['total'] for item in assessed)}
        if row['profile_id']:
            state['progression'] = snapshot(conn, row['profile_id'])
    return state


def _start_intro_game(game_id, request_id):
    game = _game(game_id)
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id):
        raise LearningError('invalid_request', 'Start the game again to create a new request.')
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile_id, guest_token = _owner(conn)
        where, params = _scope(profile_id, guest_token)
        now = timestamp()
        rows = conn.execute('SELECT * FROM journey_game_sessions WHERE ' + where + ' AND game_id=? ORDER BY created_at,rowid', (*params, game_id)).fetchall()
        original = next((row for row in rows if request_id in json.loads(row['request_ids_json'])), None)
        if original:
            return _public(conn, original)
        active = next((row for row in rows if row['completed_at'] is None and row['superseded_at'] is None), None)
        if active:
            requests = json.loads(active['request_ids_json'])
            requests.append(request_id)
            conn.execute('UPDATE journey_game_sessions SET request_ids_json=? WHERE id=?', (encoded(requests), active['id']))
            return _public(conn, active)
        require_access(conn, profile_id, game_id, now=now)
        lessons = _lesson_sources(conn, profile_id, guest_token)
        lesson = lessons.get(game['lesson_id'])
        if not lesson:
            raise LearningError('game_content_unavailable', 'Choose vocabulary or lesson words for this game.', 409)
        lesson = dict(lesson) | {'related_lessons': list(lessons.values())}
        mark_started(conn, profile_id, game_id, now)
        session_id, seed = identifier(), identifier()
        conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                     (session_id, profile_id, guest_token, game_id, seed, encoded([request_id]), encoded(_content(game, lesson, seed)), now, now))
        return _public(conn, _read_row(conn, session_id, profile_id, guest_token))


def _options(value):
    from contracts.learning import fields
    fields(value, set(), {'source', 'lesson_id', 'topic', 'difficulty', 'rounds'})
    result = {'source': value.get('source', 'vocabulary'), 'rounds': value.get('rounds', 5), 'word_policy': 'mixed-v1'}
    if result['source'] not in ('vocabulary', 'lesson', 'first_steps') or type(result['rounds']) is not int or result['rounds'] not in (5, 10):
        raise LearningError('invalid_options', 'Choose a word collection and five or ten rounds.')
    for name in ('topic', 'lesson_id'):
        entry = value.get(name)
        if entry is not None:
            if not isinstance(entry, str) or not 1 <= len(entry) <= 160:
                raise LearningError('invalid_options', 'Choose a valid lesson or topic.')
            result[name] = entry
    if result['source'] == 'lesson' and not result.get('lesson_id'):
        raise LearningError('invalid_options', 'Choose a lesson for this game.')
    if value.get('difficulty') is not None:
        if type(value['difficulty']) is not int or not 1 <= value['difficulty'] <= 8:
            raise LearningError('invalid_options', 'Choose a word difficulty from 1 to 8.')
        result['difficulty'] = value['difficulty']
    return result


def start_game(game_id, request_id, options=None, *, new_game=False):
    if game_id == 'scene-builder':
        from services.scene_builder import start
        return start(request_id, options, new_game=new_game, sample=bool(current_app.config.get('PUBLIC_DEMO')))
    if (game_id == 'directions' and current_app.config.get('DIRECTIONS_DELIVERIES_ENABLED', True)
            and (current_app.config.get('PUBLIC_DEMO') or not isinstance(options, dict) or options.get('source') != 'first_steps')):
        from services.route_delivery import start
        return start(request_id, new_game=new_game, sample=bool(current_app.config.get('PUBLIC_DEMO')), options=options)
    if current_app.config.get('PUBLIC_DEMO'):
        from services.demo_games import start_sample
        return start_sample(game_id, request_id)
    from services.journey_vocabulary import select_examples
    from services.journey_vocabulary_games import VERSION
    from services.game_activity_policy import activity_policy, discovery_request
    game, options = _game(game_id), _options(options or {})
    # Retain the authored introduction for explicit tutorial/legacy callers.
    # A normal start always uses the vocabulary library, including API callers.
    if options['source'] == 'first_steps':
        return _start_intro_game(game_id, request_id)
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id):
        raise LearningError('invalid_request', 'Start the game again to create a new request.')
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile_id, guest_token = _owner(conn)
        where, params = _scope(profile_id, guest_token)
        now = timestamp()
        rows = conn.execute('SELECT * FROM journey_game_sessions WHERE '+where+' AND game_id=? ORDER BY created_at,rowid', (*params, game_id)).fetchall()
        original = next((r for r in rows if request_id in json.loads(r['request_ids_json'])), None)
        if original:
            if json.loads(original['content_json']).get('options') != options:
                raise LearningError('idempotency_conflict', 'This start request already has different words selected.', 409)
            return _public(conn, original)
        active = next((r for r in rows if r['completed_at'] is None and r['superseded_at'] is None), None)
        if active and not new_game and json.loads(active['content_json']).get('options') == options:
            requests = [*json.loads(active['request_ids_json']), request_id]
            conn.execute('UPDATE journey_game_sessions SET request_ids_json=? WHERE id=?', (encoded(requests), active['id']))
            return _public(conn, active)
        require_access(conn, profile_id, game_id, now=now)
        session_id, seed = identifier(), identifier()
        policy = activity_policy(game_id)
        known_lemmas = [word[0] for word in conn.execute('SELECT lemma FROM words')]
        examples = [] if policy['kind'] == 'route' else select_examples(conn, profile_id, guest_token, options, seed, limit=policy.get('familiar', 4))
        source = {'kind': options['source'], 'lesson_id': options.get('lesson_id', 'vocabulary'),
                  'title': 'My vocabulary', 'href': '#words'}
        if options['source'] == 'lesson' and examples:
            source.update(title=examples[0]['source']['title'], href=examples[0]['source']['url'])
        if policy['kind'] == 'broadcast':
            from services.radio_broadcast import initial_request
            content, prepared_items = initial_request(game, examples, known_lemmas, seed, session_id, options, source)
        elif policy['kind'] == 'route':
            from services.journey_vocabulary_games import build_routes
            content, prepared_items = build_routes(game, seed, options), None
        else:
            familiar = [dict(e) | {'required_media': policy['required_media']} for e in examples]
            discoveries = [discovery_request(known_lemmas, familiar, options, seed+'-'+str(i), policy['required_media'])
                           for i in range(policy['familiar'] + policy['new'] - len(familiar))]
            prepared_items = familiar + discoveries
            content = {'version': VERSION, 'lesson_version': 'preparing:'+session_id, 'title': game['title'], 'rounds': [],
                       'source': source, 'options': options, 'vocabulary_refs': familiar, 'media_texts': [], 'activity_policy': policy}
        if active:
            conn.execute('UPDATE journey_game_sessions SET superseded_at=? WHERE id=?', (now, active['id']))
        mark_started(conn, profile_id, game_id, now)
        conn.execute('INSERT INTO journey_game_sessions(id,profile_id,guest_token,game_id,seed,request_ids_json,content_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                     (session_id, profile_id, guest_token, game_id, seed, encoded([request_id]), encoded(content), now, now))
        if prepared_items is not None:
            conn.execute('INSERT INTO journey_game_preparations(session_id,items_json,created_at,updated_at) VALUES (?,?,?,?)',
                         (session_id, encoded(prepared_items), now, now))
        return _public(conn, _read_row(conn, session_id, profile_id, guest_token))


def authorize_preparation(conn, session_id):
    return _read_row(conn, session_id, *_owner(conn))


def prepare_session(session_id, retry=False):
    from services.journey_vocabulary_games import build_content, _others
    from services.journey_vocabulary import select_examples
    with transaction(current_app.config['DB_PATH']) as conn:
        initial = json.loads(authorize_preparation(conn, session_id)['content_json'])
    if initial.get('version') == 'journey-delivery-v2':
        from services.route_jobs import advance
        return advance(session_id, retry=retry)
    is_radio = initial.get('version') == 'radio-broadcast-v1'
    preparation = current_app.extensions['learning']['radio_broadcast' if is_radio else 'journey_game_preparation']
    preparation.advance(session_id, retry=retry)
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        row = authorize_preparation(conn, session_id)
        content = json.loads(row['content_json'])
        if not content['rounds']:
            if is_radio:
                ready = preparation.content(conn, session_id)
                if ready:
                    conn.execute('UPDATE journey_game_sessions SET content_json=?,updated_at=? WHERE id=?', (encoded(ready), timestamp(), session_id))
                return _public(conn, authorize_preparation(conn, session_id))
            examples = preparation.records(conn, session_id)
            if examples:
                # Several selected lesson words may share one sentence/picture.
                # Keep those cloze targets, but add distinct library examples so
                # matching games never grade indistinguishable choices.
                distinct = _others(examples, examples[0], 4, random.Random(row['seed']))
                if len(distinct) < 4 and not content.get('activity_policy'):
                    known_words = {e.get('word_id') or e['lemma'] for e in examples}
                    candidates = select_examples(conn, row['profile_id'], row['guest_token'],
                                                 {'source': 'vocabulary'}, row['seed']+'-distinct', limit=20)
                    added = [dict(e) | {'role': 'distractor'} for e in candidates
                             if (e.get('word_id') or e['lemma']) not in known_words][:4-len(distinct)]
                    if added:
                        examples += added
                        content['vocabulary_refs'] = examples
                        conn.execute('UPDATE journey_game_preparations SET items_json=?,status=\'pending\',error=NULL WHERE session_id=?',
                                     (encoded(examples), session_id))
                        conn.execute('UPDATE journey_game_sessions SET content_json=?,updated_at=? WHERE id=?',
                                     (encoded(content), timestamp(), session_id))
                        return _public(conn, authorize_preparation(conn, session_id))
                content = build_content(_game(row['game_id']), examples, row['seed'], session_id, content['options'], content['source'])
                conn.execute('UPDATE journey_game_sessions SET content_json=?,updated_at=? WHERE id=?', (encoded(content), timestamp(), session_id))
        return _public(conn, authorize_preparation(conn, session_id))


def game_image(session_id, asset_id):
    with transaction(current_app.config['DB_PATH']) as conn:
        row = authorize_preparation(conn, session_id)
        content = json.loads(row['content_json'])
        allowed = {a['id'] for e in content.get('vocabulary_refs', []) for a in e.get('assets', []) if a.get('kind') == 'image'}
        media_prefix = 'image/'
        if content.get('mission_id') == 'town-procedural':
            from services.route_jobs import disclosed_asset_ids
            allowed = disclosed_asset_ids(_public(conn, row))
            media_prefix = 'audio/'
        asset = conn.execute('SELECT * FROM learning_assets WHERE id=?', (asset_id,)).fetchone() if asset_id in allowed else None
        if not asset or not asset['media_type'].startswith(media_prefix):
            raise LearningError('not_found', 'This media was not found.', 404)
        path = current_app.extensions['learning']['assets'].path(asset['storage_key'])
        if not path.is_file():
            raise LearningError('asset_missing', 'This media is unavailable.', 404)
        return path, asset['media_type']


def read_session(session_id):
    with transaction(current_app.config['DB_PATH']) as conn:
        return _public(conn, _read_row(conn, session_id, *_owner(conn)))


def game_word(session_id, word, *, lemma=None, pos=None):
    from services.game_vocabulary_discovery import read_word, save_word
    with transaction(current_app.config['DB_PATH'], write=lemma is not None) as conn:
        row = _read_row(conn, session_id, *_owner(conn))
        content = json.loads(row['content_json'])
        transcript_open = bool(content.get('broadcast') and json.loads(row['support_json']).get('broadcast', {}).get('transcript'))
        if row['completed_at'] is None and not transcript_open:
            raise LearningError('game_incomplete', 'Finish this activity to explore and save its words.', 409)
        result = read_word(conn, content, word) if lemma is None else save_word(
            conn, content, word, lemma, pos, profile_id=row['profile_id'], guest_token=row['guest_token'])
    if lemma is not None:
        enrichment = current_app.extensions['services']['SyncService'].enrich_words([result['word_id']])
        if enrichment['pending']:
            raise LearningError('vocabulary_enrichment_pending',
                                'The word is saved. Its topics and memory hint could not be prepared yet. Try again to finish adding it.',
                                503, {'saved': True, 'word_id': result['word_id'], 'enrichment_pending': True})
    return result


def _credit(conn, row, now):
    content = json.loads(row['content_json'])
    amount = award(conn, row['profile_id'], activity='journey_game',
                   content_key=f'journey-game:{row["game_id"]}:{content["lesson_version"]}', source_key=row['id'],
                   title=content['title'], target_level=None if content.get('version') in ('journey-vocabulary-v1', 'radio-broadcast-v1', 'journey-delivery-v2', 'scene-builder-v1', 'scene-builder-v2', 'scene-builder-v3') else 'A1', now=now,
                   evidence={'basis': 'first_unassisted_answers', 'game_id': row['game_id']})
    conn.execute('UPDATE journey_game_sessions SET reward_amount=? WHERE id=?', (amount, row['id']))
    return amount


def session_command(session_id, operation, data):
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile_id, guest_token = _owner(conn)
        row = _read_row(conn, session_id, profile_id, guest_token)
        if json.loads(row['content_json']).get('version') == 'journey-delivery-v2':
            raise LearningError('delivery_action_required', 'Use the actions in this delivery.', 409)
        from services.journey_game_corrections import OPERATIONS, command
        if operation in OPERATIONS:
            command(conn, row, operation, data)
            return _public(conn, _read_row(conn, session_id, profile_id, guest_token))
        if row['completed_at'] is not None:
            return _public(conn, row)
        if json.loads(row['support_json']).get('_practice', {}).get('active'):
            raise LearningError('practice_active', 'Continue or close this correction before returning to the game.', 409)
        content = json.loads(row['content_json'])
        rounds = content['rounds']
        if not rounds:
            raise LearningError('preparation_required', 'Finish preparing this game before answering.', 409)
        answers, hints, acknowledged = (json.loads(row[column]) for column in ('answers_json', 'hints_json', 'acknowledged_json'))
        support = json.loads(row['support_json'])
        now, awarded_now = timestamp(), False
        if content.get('broadcast'):
            broadcast = content['broadcast']
            shared = support.setdefault('broadcast', {})
            if operation == 'quiz' or (operation in ('listen', 'transcript') and data.get('round_id') == 'broadcast'):
                if operation == 'quiz':
                    if not shared.get('transcript') and broadcast['audio_key'] not in shared.get('listened_audio_keys', []):
                        raise LearningError('listen_required', 'Listen to the programme before starting its questions.', 409)
                    shared['started'] = True
                elif operation == 'transcript':
                    shared['transcript'] = True
                else:
                    if data.get('audio_key') != broadcast['audio_key']:
                        raise LearningError('invalid_audio', 'Listen to this programme.', 409)
                    media = current_app.extensions['learning']['journey_game_media']
                    if media.status(broadcast['audio_key'])['status'] != 'ready':
                        raise LearningError('audio_not_ready', 'The programme recording is not ready.', 409)
                    shared['listened_audio_keys'] = [broadcast['audio_key']]
                conn.execute('UPDATE journey_game_sessions SET support_json=?,updated_at=? WHERE id=?', (encoded(support), now, session_id))
                return _public(conn, _read_row(conn, session_id, profile_id, guest_token))
            if not shared.get('started'):
                raise LearningError('listen_required', 'Listen to the programme, then start its questions.', 409)
        elif operation == 'quiz':
            raise LearningError('invalid_action', 'This game does not have a broadcast.', 409)
        if operation == 'complete':
            if acknowledged != [item['id'] for item in rounds]:
                raise LearningError('feedback_required', 'Finish each round and read its feedback before completing the game.', 409)
            conn.execute('UPDATE journey_game_sessions SET completed_at=?,updated_at=? WHERE id=?', (now, now, session_id))
            if profile_id:
                awarded_now = bool(_credit(conn, _read_row(conn, session_id, profile_id, guest_token), now))
        else:
            round_id = data['round_id']
            item = next((item for item in rounds if item['id'] == round_id), None) if isinstance(round_id, str) else None
            if item is None:
                raise LearningError('invalid_round', 'Choose a round from this game.')
            saved = answers.get(round_id)
            answer = data.get('answer')
            if operation == 'answer':
                answer = normalise_answer(item, answer, row['game_id'])
                if saved:
                    if answer != saved['answer']:
                        raise LearningError('answer_already_saved', 'Your first answer is saved. Continue after the feedback.', 409)
                    return _public(conn, row)
            if operation == 'hint' and round_id in hints or operation == 'continue' and round_id in acknowledged:
                return _public(conn, row)
            round_support = {**support.get('broadcast', {}), **support.get(round_id, {})} if content.get('broadcast') else support.get(round_id, {})
            if (operation == 'transcript' and round_support.get('transcript')
                    or operation == 'listen' and data.get('audio_key') in round_support.get('listened_audio_keys', [])):
                return _public(conn, row)
            if len(acknowledged) >= len(rounds) or round_id != rounds[len(acknowledged)]['id']:
                raise LearningError('wrong_round', 'Continue with the current round.', 409)
            if operation in ('listen', 'transcript'):
                if not item.get('audio_required'):
                    raise LearningError('invalid_support', 'This option belongs to the listening game.', 409)
                if saved:
                    raise LearningError('answer_already_saved', 'Your first answer is saved. Continue after the feedback.', 409)
                if operation == 'transcript':
                    round_support['transcript'] = True
                else:
                    key = data['audio_key']
                    if not isinstance(key, str) or key not in {clue['audio_key'] for clue in item['clues']}:
                        raise LearningError('invalid_audio', 'Listen to the message for this round.')
                    media = current_app.extensions['learning'].get('journey_game_media')
                    if media is None or media.status(key)['status'] != 'ready':
                        raise LearningError('audio_not_ready', 'Prepare and play the message, or read its transcript.', 409)
                    round_support['listened_audio_keys'] = list(dict.fromkeys([*round_support.get('listened_audio_keys', []), key]))
                support[round_id] = round_support
            elif operation == 'hint':
                if saved:
                    raise LearningError('answer_already_saved', 'Your answer is already saved. Read the feedback, then continue.', 409)
                hints.append(round_id)
            elif operation == 'answer':
                if item.get('audio_required'):
                    required_audio = {clue['audio_key'] for clue in item['clues']}
                    if not round_support.get('transcript') and not required_audio.issubset(round_support.get('listened_audio_keys', [])):
                        raise LearningError('listen_required', 'Listen to the message, or read its transcript, before choosing an answer.', 409)
                if row['game_id'] == 'directions':
                    movement_path(item['board'], answer)
                answers[round_id] = {'answer': answer, **assess_answer(item, answer), 'hint_used': round_id in hints, 'answered_at': now,
                                    'listened_audio_keys': round_support.get('listened_audio_keys', []), 'transcript_used': bool(round_support.get('transcript'))}
            elif operation == 'continue':
                if saved is None:
                    raise LearningError('answer_required', 'Try this round before continuing.', 409)
                acknowledged.append(round_id)
            conn.execute('UPDATE journey_game_sessions SET answers_json=?,hints_json=?,acknowledged_json=?,support_json=?,updated_at=? WHERE id=?',
                         (encoded(answers), encoded(hints), encoded(acknowledged), encoded(support), now, session_id))
        return _public(conn, _read_row(conn, session_id, profile_id, guest_token), awarded_now=awarded_now)


def claim_guest_games(conn, profile_id, guest_token, *, now=None):
    """Called only while creating a new personal profile, after lesson transfer."""
    now = timestamp() if now is None else now
    rows = conn.execute('SELECT * FROM journey_game_sessions WHERE profile_id IS NULL AND guest_token=? ORDER BY created_at,rowid', (guest_token,)).fetchall()
    conn.execute('UPDATE journey_game_unlocks SET profile_id=?,guest_token=NULL WHERE profile_id IS NULL AND guest_token=?', (profile_id, guest_token))
    # Profile creation carries prepared contexts as well as attempts; selecting
    # an existing profile never calls this transfer.
    conn.execute('UPDATE journey_game_examples SET profile_id=?,guest_token=NULL WHERE profile_id IS NULL AND guest_token=? '
                 'AND identity NOT IN (SELECT identity FROM journey_game_examples WHERE profile_id=?)',
                 (profile_id, guest_token, profile_id))
    for row in rows:
        conn.execute('UPDATE journey_game_sessions SET profile_id=?,guest_token=NULL,updated_at=? WHERE id=?', (profile_id, now, row['id']))
        if row['completed_at'] is not None:
            _credit(conn, _read_row(conn, row['id'], profile_id, None), now)
    sync_unlocks(conn, profile_id, None, now=now)


def allowlisted_media(conn, key):
    """Resolve only audio already present in this owner's completed lessons/game."""
    profile_id, guest_token = _owner(conn)
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise LearningError('not_found', 'This audio was not found.', 404)
    texts = set()
    for lesson in completed_lessons(conn, profile_id, guest_token):
        if lesson['id'] in {game['lesson_id'] for game in GAMES}:
            texts.update(item['sentence'] for item in lesson['vocabulary'])
    where, params = _scope(profile_id, guest_token)
    for row in conn.execute('SELECT lesson_json FROM journey_game_unlocks WHERE ' + where, params):
        frozen = json.loads(row['lesson_json'])
        texts.update(item['sentence'] for lesson in [frozen, *frozen.get('related_lessons', [])] for item in lesson['vocabulary'])
    for row in conn.execute('SELECT content_json,answers_json FROM journey_game_sessions WHERE ' + where, params):
        content = json.loads(row['content_json'])
        if content.get('version') in ('scene-builder-v1', 'scene-builder-v2', 'scene-builder-v3'):
            answered = json.loads(row['answers_json'])
            texts.update(audio['text'] for item in content['rounds'] if item['id'] in answered for audio in item.get('answer_audio', []))
            continue
        texts.update(content.get('media_texts', []))
        texts.update(clue['text'] for item in content['rounds'] for clue in item['clues'])
    text = next((text for text in texts if hashlib.sha256(text.encode('utf-8')).hexdigest() == key), None)
    if text is None:
        raise LearningError('not_found', 'This audio was not found for your profile.', 404)
    return {'text': text, 'profile_id': profile_id, 'guest_token': guest_token}
