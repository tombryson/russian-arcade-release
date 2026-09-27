"""Replayable mechanics over complete contextual examples, never a fixed word list."""
from copy import deepcopy
import hashlib
import random
import re

from repositories.learning_repository import LearningError, payload_hash

VERSION = 'journey-vocabulary-v1'
DIRECTIONS = {'left': 'Налево.', 'straight': 'Прямо.', 'right': 'Направо.'}


def audio(text):
    return {'text': text, 'audio_key': hashlib.sha256(text.encode()).hexdigest()}


def _image(example, session_id):
    asset = next((a for a in example.get('assets', []) if a['kind'] == 'image'), None)
    if not asset:
        raise LearningError('media_required', 'Finish preparing the pictures before playing.', 409)
    return f'/api/v1/games/sessions/{session_id}/assets/{asset["id"]}'


def _picture(example, session_id, token):
    return {'id': token, 'visual': 'postcard', 'label': example['translation'],
            'image_url': _image(example, session_id)}


def _round(index, mechanic, prompt, expected, **fields):
    return {'id': f'round-{index+1}', 'mechanic': mechanic, 'prompt': prompt,
            'clues': [], 'max_choices': len(expected), 'expected_answer': expected, **fields}


def _others(examples, target, count, rng):
    candidates = [e for e in examples if e['identity'] != target['identity']
                  and e['sentence'] != target['sentence'] and e['translation'] != target['translation']]
    rng.shuffle(candidates)
    chosen = [target]
    for example in candidates:
        # Two selected words can belong to the same lesson sentence. They are
        # valid cloze targets, but cannot be distinguishable matching choices.
        image_id = next((a['id'] for a in example.get('assets', []) if a['kind'] == 'image'), None)
        if any(example['sentence'].casefold().strip() == prior['sentence'].casefold().strip()
               or example['translation'].casefold().strip() == prior['translation'].casefold().strip()
               or (image_id and any(a['kind'] == 'image' and a['id'] == image_id for a in prior.get('assets', [])))
               for prior in chosen):
            continue
        chosen.append(example)
        if len(chosen) == count:
            break
    return chosen


def _feedback(example):
    return f'«{example["sentence"]}» — {example["translation"]}'


def _route(rng, length):
    return [rng.choice(list(DIRECTIONS)) for _ in range(length)]


def _route_clue(route):
    return audio(' '.join(DIRECTIONS[move] for move in route))


def _opaque_choices(item, rng):
    """Public identifiers must not encode which choices were created first."""
    groups = [item.get(key, []) for key in ('objects', 'left', 'right', 'sentences', 'bins', 'choices', 'destinations', 'tiles')]
    groups.append(item.get('board', {}).get('landmarks', []))
    mapping = {}
    for group in groups:
        for choice in group:
            old = choice['id']
            mapping.setdefault(old, 'choice-'+f'{rng.getrandbits(64):016x}')
            choice['id'] = mapping[old]
    item['expected_answer'] = [':'.join(mapping.get(part, part) for part in answer.split(':'))
                               for answer in item['expected_answer']]
    if item['mechanic'] in ('pairs', 'mailbox-sort', 'pack-bag'):
        item['expected_answer'].sort()


def build_content(game, examples, seed, session_id, options, source):
    """Use saved forms, meanings and media. Freeze choices before any answer.

    The prepared selection can be any vocabulary or lesson collection. Each
    next selection is chosen by the shared library adapter, not this template.
    """
    if not examples:
        raise LearningError('no_game_content', 'Choose some words for this game.', 409)
    rng = random.Random(seed)
    pool = deepcopy(examples)
    rng.shuffle(pool)
    targets = [item for item in pool if item.get('role') != 'distractor'] or pool
    rounds, game_id = [], game['id']
    for index in range(options['rounds']):
        target = targets[index % len(targets)]
        alternatives = _others(pool, target, 4, rng)
        if len(alternatives) < 2 and game_id not in ('letter-back',):
            raise LearningError('distinct_examples_required', 'Prepare another example to give this game distinct choices.', 409)
        if game_id == 'pack-bag':
            chosen = alternatives[:2] if index % 3 == 2 and len(alternatives) > 2 else [target]
            objects = [_picture(e, session_id, f'picture-{i}') for i, e in enumerate(alternatives)]
            expected = sorted(objects[i]['id'] for i in range(len(chosen)))
            rng.shuffle(objects)
            item = _round(index, game_id, 'Pack the picture cards that match the messages.', expected,
                          objects=objects, clues=[audio(e['sentence']) for e in chosen],
                          hint=' '.join(e['translation'] for e in chosen),
                          feedback=' '.join(_feedback(e) for e in chosen))
        elif game_id == 'pairs':
            chosen = alternatives[:min(3, len(alternatives))]
            left = [{'id': f'message-{i}', 'text': e['sentence'], 'audio_key': audio(e['sentence'])['audio_key']}
                    for i, e in enumerate(chosen)]
            right = [_picture(e, session_id, f'picture-{i}') for i, e in enumerate(chosen)]
            expected = sorted(f'{left[i]["id"]}:{right[i]["id"]}' for i in range(len(chosen)))
            rng.shuffle(left); rng.shuffle(right)
            item = _round(index, game_id, 'Match the Russian messages to their pictures.', expected,
                          left=left, right=right, hint=' '.join(e['translation'] for e in chosen),
                          feedback=' '.join(_feedback(e) for e in chosen))
        elif game_id == 'missing-stamp':
            pattern = re.compile(r'(?<![А-Яа-яЁё])'+re.escape(target['form'])+r'(?![А-Яа-яЁё])', re.I)
            if len(list(pattern.finditer(target['sentence']))) != 1:
                raise LearningError('invalid_context', 'This word needs a clearer example before it can be used.', 409)
            from services.cloze_choices import choices_for
            selection = choices_for(target, alternatives, rng)
            forms = selection['forms']
            rng.shuffle(forms)
            choices = [{'id': f'word-{i}', 'text': form} for i, form in enumerate(forms)]
            answer = next(c['id'] for c in choices if c['text'] == target['form'])
            item = _round(index, game_id, 'Complete the Russian message using its English translation.', [answer],
                          sentence=pattern.sub('[[blank]]', target['sentence']), translation=target['translation'],
                          choices=choices,
                          hint=target.get('mnemonic') or 'Read the whole English sentence, then choose the Russian form that fits.',
                          feedback=_feedback(target), answer_audio=[audio(target['sentence'])])
            item.update(objective=selection['objective'], explanation=selection['explanation'], explanation_ru=selection['explanation_ru'])
            if any(a.get('kind') == 'image' for a in target.get('assets', [])):
                item['image_url'] = _image(target, session_id)
        elif game_id == 'radio':
            choices = [_picture(e, session_id, f'picture-{i}') for i, e in enumerate(alternatives)]
            answer = choices[0]['id']; rng.shuffle(choices)
            item = _round(index, game_id, 'Listen to the message. Which picture matches?', [answer],
                          clues=[audio(target['sentence'])], choices=choices, audio_required=True,
                          hint=target['translation'], feedback=_feedback(target))
        elif game_id == 'mailbox-sort':
            # Whole contextual meanings, rather than arbitrary semantic labels
            # or claiming that an ambiguous spelling has one grammatical case.
            chosen = alternatives[:min(3, len(alternatives))]
            sentences = [{'id': f'message-{i}', 'text': e['sentence'], 'audio_key': audio(e['sentence'])['audio_key']}
                         for i, e in enumerate(chosen)]
            bins = [{'id': f'mailbox-{i}', 'label': e['translation']} for i, e in enumerate(chosen)]
            expected = sorted(f'{sentences[i]["id"]}:{bins[i]["id"]}' for i in range(len(chosen)))
            rng.shuffle(sentences); rng.shuffle(bins)
            item = _round(index, game_id, 'Sort the messages by their English meaning.', expected,
                          sentences=sentences, bins=bins,
                          hint=' '.join(f'«{e["form"]}» here means {e["target_meaning"]}.' for e in chosen),
                          feedback=' '.join(_feedback(e) for e in chosen))
        elif game_id == 'letter-back':
            words = target['sentence'].split()
            step = 2 if len(words) > 5 else 1
            chunks = [' '.join(words[i:i+step]) for i in range(0, len(words), step)]
            tiles = [{'id': f'piece-{rng.getrandbits(40):010x}', 'text': text} for text in chunks]
            expected = [tile['id'] for tile in tiles]; rng.shuffle(tiles)
            item = _round(index, game_id, 'Listen, then rebuild the message in the order you heard it.', expected,
                          tiles=tiles, translation=target['translation'], clues=[audio(target['sentence'])],
                          audio_required=True, hint=target['translation'], feedback=_feedback(target),
                          answer_audio=[audio(target['sentence'])])
        elif game_id == 'detective':
            other = alternatives[1] if len(alternatives) > 1 else target
            route = _route(rng, 1 + index % 3)
            wrong = list(route); wrong[-1] = rng.choice([d for d in DIRECTIONS if d != wrong[-1]])
            combinations = [(target, route), (other, route), (target, wrong), (other, wrong)]
            destinations = [_picture(e, session_id, f'delivery-{i}') | {'route': commands,
                            'label': e['translation']+' · '+', then '.join(commands)}
                            for i, (e, commands) in enumerate(combinations)]
            expected = [destinations[0]['id']]; rng.shuffle(destinations)
            item = _round(index, game_id, 'Find the picture and route that match both clues.', expected,
                          clues=[audio(target['sentence']), _route_clue(route)], destinations=destinations,
                          hint=target['translation']+' '+', then '.join(route), feedback=_feedback(target))
        elif game_id == 'directions':
            from services.journey_games import movement_path
            route = _route(rng, 1 + index % 3)
            board = {'width': 7, 'height': 7, 'start': {'x': 3, 'y': 3, 'heading': rng.choice(['north','east','south','west'])},
                     'landmarks': []}
            destination = movement_path(board, route)[-1]
            positions = [(x, y) for x in range(7) for y in range(7)
                         if (x, y) not in ((3, 3), (destination['x'], destination['y']))]
            rng.shuffle(positions)
            for i, e in enumerate(alternatives):
                x, y = (destination['x'], destination['y']) if i == 0 else positions.pop()
                board['landmarks'].append(_picture(e, session_id, f'place-{i}') | {'x': x, 'y': y})
            item = _round(index, game_id, 'Find the matching picture. Follow the directions to reach it.', route,
                          board=board, clues=[audio(target['sentence']), _route_clue(route)],
                          hint=target['translation']+' '+', then '.join(route), feedback=_feedback(target))
        else:
            raise LearningError('not_found', 'This game was not found.', 404)
        evidence_examples = chosen if game_id in ('pack-bag', 'pairs', 'mailbox-sort') else [target]
        item['evidence_texts'] = [e['sentence'] for e in evidence_examples]
        _opaque_choices(item, rng)
        rounds.append(item)
    refs = [dict(item) | {'grammar': item.get('tags', {})} for item in pool]
    fingerprint = payload_hash(sorted((e['identity'], e['sentence']) for e in targets))
    difficulties = [e.get('metadata', {}).get('form_difficulty') or e.get('metadata', {}).get('lemma_difficulty') for e in targets]
    values = [value for value in difficulties if type(value) is int and 1 <= value <= 8]
    difficulty = options.get('difficulty') or (round(sum(values)/len(values)) if values else None)
    return {'version': VERSION, 'lesson_version': 'vocabulary:'+fingerprint, 'title': game['title'],
            'source': source, 'rounds': rounds, 'options': options, 'vocabulary_refs': refs,
            'word_count': len({e.get('word_id') or e['lemma'] for e in targets}),
            'word_difficulty': difficulty,
            'media_texts': sorted({clue['text'] for r in rounds for clue in [*r['clues'], *r.get('answer_audio', [])]}
                                 | {e['sentence'] for e in pool})}


def build_routes(game, seed, options):
    """Route practice needs a map and instructions, not generated photographs."""
    from services.journey_games import movement_path
    rng = random.Random(seed)
    rounds = []
    for index in range(options['rounds']):
        route = _route(rng, 1 + index % 3)
        board = {'width': 7, 'height': 7,
                 'start': {'x': 3, 'y': 3, 'heading': rng.choice(['north', 'east', 'south', 'west'])},
                 'landmarks': [{'x': 0, 'y': 0, 'visual': 'post-office'}, {'x': 6, 'y': 0, 'visual': 'market'}]}
        movement_path(board, route)
        rounds.append(_round(index, 'directions', 'Follow the Russian directions to guide Barsik.', route,
                             board=board, clues=[_route_clue(route)], hint=', then '.join(route)+'.',
                             feedback=' '.join(DIRECTIONS[move] for move in route)+' — '+', then '.join(route)+'.'))
    return {'version': 'journey-routes-v1', 'lesson_version': 'route-language-v1', 'title': game['title'],
            'source': {'kind': 'route', 'title': 'Directions', 'href': '#activities'}, 'options': options,
            'rounds': rounds, 'vocabulary_refs': [], 'media_texts': sorted({c['text'] for r in rounds for c in r['clues']})}
