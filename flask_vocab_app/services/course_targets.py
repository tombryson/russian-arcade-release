"""Response-level curriculum evidence and short, authored preparation.

An activity score never becomes target mastery. These observations name the
saved item, response, rubric and support used. The caller owns the transaction;
this service neither awards money nor changes course passes or skill ratings.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote

from contracts.learning import key
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, timestamp
from services.curriculum_targets import curriculum_targets, get_section, get_target, targets_for_section
from services.course_releases import release_metadata

PRACTICE_FILE = Path(__file__).resolve().parents[1] / 'data' / 'course_target_practice.json'
PRACTICE_VERSION = 'a1-target-practice-v1'
CATALOGUE_VERSION = 'a1-targets-v1'
PREPARATION_RELEASE = 'a1-journey-v2'


def _execute(conn, sql, args=()):
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute(sql, args)


def _profile(conn, profile_id):
    if not _execute(conn, 'SELECT id FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL', (profile_id,)).fetchone():
        raise LearningError('profile_changed', 'Choose an available learner.', 409)


def _ready(conn):
    return bool(_execute(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name='course_target_observations'").fetchone())


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and '\x00' not in value


def validate_practice(data):
    """All required targets need a distinct teaching example and checked item."""
    def require(test, message):
        if not test:
            raise ValueError(message)
    require(isinstance(data, dict) and data.get('version') == PRACTICE_VERSION, 'Unknown preparation content version.')
    items = data.get('items')
    require(isinstance(items, list) and items, 'Preparation needs authored items.')
    expected = {tid for section in curriculum_targets()['sections'] for tid in section['required_target_ids']}
    ids, targets = set(), set()
    for item in items:
        require(isinstance(item, dict) and _nonempty(item.get('id')) and item['id'] not in ids, 'Preparation item IDs must be distinct.')
        ids.add(item['id'])
        target = get_target(item.get('target_id'))
        require(target and target['id'] not in targets, 'Each required target needs one authored item.')
        targets.add(target['id'])
        require(_nonempty(item.get('rubric_version')), 'Every item needs its marking version.')
        teaching = item.get('teaching', {})
        require(all(_nonempty(teaching.get(f)) for f in ('explanation', 'explanation_ru', 'example_ru', 'example_en')), 'Preparation needs a bilingual teaching example.')
        question = item.get('question', {})
        require(all(_nonempty(question.get(f)) for f in ('prompt', 'prompt_ru', 'explanation', 'explanation_ru')), 'Every item needs bilingual prompts and feedback.')
        choices = question.get('choices', [])
        require(isinstance(choices, list) and 2 <= len(choices) <= 6 and all(isinstance(c, dict) and _nonempty(c.get('id')) and _nonempty(c.get('text')) for c in choices), 'Choose from authored Russian options.')
        require(len({c['id'] for c in choices}) == len(choices) and len({c['text'] for c in choices}) == len(choices) and question.get('answer') in {c['id'] for c in choices}, 'The answer must identify a distinct offered option.')
        require(all(_nonempty(item.get('hint', {}).get(f)) for f in ('en', 'ru')), 'Each item needs optional bilingual help.')
        if target['response_mode'] == 'listening_selection':
            require(question.get('passage') is None and _nonempty(question.get('transcript')) and question.get('audio_url') == f"/static/audio/course/a1-targets-v1/{item['id']}.mp3", 'Listening needs its own audio and a hidden transcript.')
            require(question['transcript'] != teaching['example_ru'], 'The teaching example must not reveal the listening task.')
        else:
            require(_nonempty(question.get('passage')) and not question.get('audio_url'), 'Reading or contextual selection needs the saved passage.')
    require(targets == expected, 'Preparation must cover exactly the required A1 target subset.')
    return data


@lru_cache(maxsize=1)
def practice_catalogue():
    return validate_practice(json.loads(PRACTICE_FILE.read_text(encoding='utf-8')))


def _target_prepared(target):
    """Independent success can replace an introductory teaching receipt."""
    return bool(target['demonstrated'] or (target['introduced'] and target['practised']))


def preparation_metadata(release_id):
    """Resolve published preparation without silently replacing its versions."""
    release = release_metadata(release_id)
    preparation = release.get('preparation')
    if not isinstance(preparation, dict):
        raise LearningError('practice_unavailable', 'This course has no focused preparation.', 404)
    if (preparation.get('target_catalogue_version') != CATALOGUE_VERSION
            or preparation.get('content_version') != PRACTICE_VERSION):
        raise LearningError('practice_content_unavailable', 'This saved preparation version is unavailable.', 409)
    return {'release_id': release_id, **preparation}


def _target_snapshot(section_id, catalogue_version):
    # The retained A1 registry is resolved by its identity, never by a new
    # default catalogue. Future catalogues need their own explicit loader.
    if catalogue_version != CATALOGUE_VERSION:
        raise LearningError('practice_content_unavailable', 'This saved target catalogue is unavailable.', 409)
    section = get_section(section_id)
    if not section:
        raise LearningError('section_not_found', 'That practice section was not found.', 404)
    return {'catalogue_version': catalogue_version, 'section_id': section_id,
            'targets': targets_for_section(section_id, required_only=True)}


def _practice_context(row):
    identity = preparation_metadata(row['release_id'])
    if (row['target_catalogue_version'] != identity['target_catalogue_version']
            or row['content_version'] != identity['content_version']):
        raise LearningError('practice_content_unavailable', 'This saved preparation version is unavailable.', 409)
    expected = _target_snapshot(row['section_id'], row['target_catalogue_version'])
    snapshot = json.loads(row['target_snapshot_json']) if row['target_snapshot_json'] else expected
    known = {target['id'] for target in expected['targets']}
    targets = snapshot.get('targets') if isinstance(snapshot, dict) else None
    if (not isinstance(targets, list) or not targets
            or snapshot.get('section_id') != row['section_id']
            or snapshot.get('catalogue_version') != row['target_catalogue_version']
            or any(not isinstance(t, dict) or t.get('id') not in known
                   or type(t.get('version')) is not int or t['version'] < 1
                   or any(not _nonempty(t.get(field)) for field in ('topic_id', 'title_en', 'title_ru', 'response_mode'))
                   for t in targets)
            or len(targets) != len(known) or {t['id'] for t in targets} != known):
        raise LearningError('practice_content_unavailable', 'This saved target contract is unavailable.', 409)
    items = json.loads(row['content_json'])
    if not isinstance(items, list) or not items or any(not isinstance(item, dict) or item.get('target_id') not in known for item in items):
        raise LearningError('practice_content_unavailable', 'This saved preparation has an unknown target.', 409)
    return identity, snapshot


def target_coverage(conn, profile_id, section_id, *, release_id=PREPARATION_RELEASE, target_snapshot=None):
    identity = preparation_metadata(release_id)
    snapshot = target_snapshot or _target_snapshot(section_id, identity['target_catalogue_version'])
    records = []
    if _ready(conn):
        records = _execute(conn, '''SELECT o.* FROM course_target_observations o
            LEFT JOIN progression_events e ON e.id=o.event_id
            WHERE o.profile_id=? AND o.catalogue_version=?
              AND (o.event_id IS NULL OR (e.profile_id=o.profile_id AND e.reversed_at IS NULL))
            ORDER BY o.created_at,o.rowid''', (profile_id, snapshot['catalogue_version'])).fetchall()
    targets = []
    for target in snapshot['targets']:
        observations = [r for r in records if r['target_id'] == target['id'] and r['target_version'] == target['version']]
        answered = [r for r in observations if r['practised']]
        summary = {name: target[name] for name in ('id', 'topic_id')} | {
            'title': target['title_en'], 'title_ru': target['title_ru'], 'required': True,
            'introduced': any(bool(r['introduced']) for r in observations),
            'practised': bool(answered), 'demonstrated': any(bool(r['demonstrated']) for r in answered),
            'needs_practice': bool(answered and answered[-1]['needs_practice'])}
        summary['prepared'] = _target_prepared(summary)
        targets.append(summary)
    prepared = sum(t['prepared'] for t in targets)
    return {**identity, 'section_id': section_id, 'targets': targets, 'required_count': len(targets),
            'prepared_count': prepared, 'ready': prepared == len(targets),
            'practice_href': '/#journey/release/' + quote(release_id, safe='') + '/practice/start/' + quote(section_id, safe='')}


def _observe(conn, profile_id, target_id, *, activity, source_key, item_id, content_hash,
             rubric_version, introduced=False, practised=False, score=None,
             first_response=None, response=None, support=None, event_id=None,
             checkpoint_id=None, practice_id=None, now=None, target=None, catalogue_version=CATALOGUE_VERSION):
    """Private write boundary. Callers must resolve a server-owned item first."""
    target = get_target(target_id) if target is None else target
    if not target or not _ready(conn):
        return False
    support = support or {}
    supported = any(bool(value) for value in support.values())
    demonstrated = bool(practised and score == 1 and not supported)
    result = _execute(conn, '''INSERT OR IGNORE INTO course_target_observations
        (id,profile_id,target_id,catalogue_version,target_version,response_mode,activity,source_key,item_id,
        content_hash,rubric_version,introduced,practised,demonstrated,needs_practice,score,
        first_response_json,response_json,support_json,event_id,checkpoint_id,practice_id,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        identifier(), profile_id, target_id, catalogue_version, target['version'], target['response_mode'], activity,
        source_key, item_id, content_hash, rubric_version, int(introduced), int(practised), int(demonstrated),
        int(practised and score is not None and score < 1), score,
        encoded(first_response) if first_response is not None else None,
        encoded(response) if response is not None else None, encoded(support), event_id,
        checkpoint_id, practice_id, timestamp() if now is None else now))
    return result.rowcount == 1


def _owned(conn, profile_id, attempt_id):
    _profile(conn, profile_id)
    row = _execute(conn, 'SELECT * FROM course_target_practice_attempts WHERE id=? AND profile_id=?', (attempt_id, profile_id)).fetchone()
    if not row:
        raise LearningError('practice_not_found', 'This practice was not found.', 404)
    return row


def practice_get(conn, profile_id, attempt_id):
    row = _owned(conn, profile_id, attempt_id)
    identity, snapshot = _practice_context(row)
    items, state = json.loads(row['content_json']), json.loads(row['state_json'])
    current = None
    if row['status'] == 'active':
        item = items[row['current_index']]
        target = next(target for target in snapshot['targets'] if target['id'] == item['target_id'])
        saved = state.get(item['id'], {})
        question = item['question']
        # Do not return the task before its teaching action or return solutions
        # with unattempted questions. Listening transcripts need explicit help.
        stage = 'feedback' if 'answer' in saved else 'question' if saved.get('learned') else 'learn'
        current = {'id': item['id'], 'target_id': item['target_id'],
                   'title': item.get('title', target['title_en']), 'title_ru': item.get('title_ru', target['title_ru']), 'stage': stage,
                   'teaching': deepcopy(item['teaching']), 'question': None,
                   'hint': deepcopy(item['hint']) if saved.get('hint') else None,
                   'feedback': None, 'selected_choice': saved.get('answer'), 'listened': bool(saved.get('listened')),
                   'transcript': question.get('transcript') if saved.get('transcript') else None}
        if stage != 'learn':
            current['question'] = {name: deepcopy(question.get(name)) for name in ('prompt', 'prompt_ru', 'passage', 'audio_url', 'choices')}
        if stage == 'feedback':
            current['feedback'] = {'correct': saved['answer'] == question['answer'],
                                   'answer': next(c['text'] for c in question['choices'] if c['id'] == question['answer']),
                                   'explanation': question['explanation'], 'explanation_ru': question['explanation_ru']}
    return {**identity, 'id': row['id'], 'profile_id': profile_id, 'section_id': row['section_id'],
            'status': row['status'], 'completed_count': row['current_index'], 'total_count': len(items),
            'current_item': current, 'coverage': target_coverage(conn, profile_id, row['section_id'],
                release_id=row['release_id'], target_snapshot=snapshot)}


def practice_start(conn, profile_id, section_id, request_id, *, release_id=None, enrol=False):
    _profile(conn, profile_id)
    key(request_id, 'Practice request ID')
    choices = {'section_id': section_id}
    if release_id is not None:
        release_metadata(release_id)
        choices['release_id'] = release_id
    digest = payload_hash(choices)
    previous = _execute(conn, 'SELECT payload_hash,attempt_id FROM course_target_practice_requests WHERE profile_id=? AND request_id=?', (profile_id, request_id)).fetchone()
    if previous:
        saved = _owned(conn, profile_id, previous['attempt_id'])
        # Before schema 048 the API accepted release_id but saved only section
        # in its fingerprint. Keep those requests replayable, without allowing
        # the caller to rebind an old request to a different release.
        legacy_match = (previous['payload_hash'] == payload_hash({'section_id': section_id})
                        and (release_id is None or release_id == saved['release_id']))
        if previous['payload_hash'] != digest and not legacy_match:
            raise LearningError('request_conflict', 'This request belongs to different practice.', 409)
        return practice_get(conn, profile_id, previous['attempt_id'])
    if enrol:
        from services.course_progression import course_snapshot
        state = course_snapshot(conn, profile_id, release_id=release_id)
        if not state['is_current_release']:
            raise LearningError('course_release_mismatch', 'Reopen your current journey before starting this practice.', 409)
        release_id = state['release_id']
    release_id = release_id or PREPARATION_RELEASE
    identity = preparation_metadata(release_id)
    snapshot = _target_snapshot(section_id, identity['target_catalogue_version'])
    coverage = target_coverage(conn, profile_id, section_id, release_id=release_id, target_snapshot=snapshot)
    if enrol:
        _execute(conn, 'INSERT OR IGNORE INTO course_enrolments(profile_id,band,release_id,started_at) VALUES (?,?,?,?)',
                 (profile_id, state['band'], release_id, timestamp()))
    active = _execute(conn, "SELECT id FROM course_target_practice_attempts WHERE profile_id=? AND release_id=? AND section_id=? AND status='active'", (profile_id, release_id, section_id)).fetchone()
    if active:
        attempt_id = active['id']
    else:
        required = {t['id'] for t in coverage['targets']}
        gaps = {t['id'] for t in coverage['targets'] if not t['prepared'] or t['needs_practice']}
        chosen = gaps or required
        items = [deepcopy(item) for item in practice_catalogue()['items'] if item['target_id'] in chosen]
        # Rotate answer positions per attempt without changing authored meaning.
        import random
        for item in items:
            random.SystemRandom().shuffle(item['question']['choices'])
        attempt_id = identifier()
        _execute(conn, '''INSERT INTO course_target_practice_attempts
            (id,profile_id,section_id,content_version,content_json,created_at,release_id,target_catalogue_version,target_snapshot_json)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (attempt_id, profile_id, section_id, identity['content_version'], encoded(items), timestamp(),
             release_id, identity['target_catalogue_version'], encoded(snapshot)))
    _execute(conn, 'INSERT INTO course_target_practice_requests VALUES (?,?,?,?)', (profile_id, request_id, digest, attempt_id))
    return practice_get(conn, profile_id, attempt_id)


def practice_action(conn, profile_id, attempt_id, action, body, request_id):
    row = _owned(conn, profile_id, attempt_id)
    key(request_id, 'Practice request ID')
    if action not in ('learn', 'answer', 'next', 'hint', 'listened', 'transcript') or not isinstance(body, dict):
        raise LearningError('invalid_action', 'Choose an available practice action.')
    item_id = key(body.get('item_id'), 'Practice item ID')
    if set(body) - {'item_id', 'choice_id', 'request_id', 'submission_id'}:
        raise LearningError('invalid_input', 'This practice action has unexpected fields.')
    choice_id = key(body.get('choice_id'), 'Choice ID') if action == 'answer' else None
    if action != 'answer' and 'choice_id' in body:
        raise LearningError('invalid_input', 'Only an answer can choose an option.')
    digest = payload_hash({'attempt_id': attempt_id, 'action': action, 'item_id': item_id, 'choice_id': choice_id})
    receipt = _execute(conn, 'SELECT payload_hash,result_json FROM course_target_practice_receipts WHERE profile_id=? AND request_id=?', (profile_id, request_id)).fetchone()
    if receipt:
        if receipt['payload_hash'] != digest:
            raise LearningError('request_conflict', 'This request belongs to a different practice action.', 409)
        return json.loads(receipt['result_json'])
    identity, snapshot = _practice_context(row)
    items, states = json.loads(row['content_json']), json.loads(row['state_json'])
    if row['status'] != 'active' or items[row['current_index']]['id'] != item_id:
        raise LearningError('stale_practice', 'This practice has moved on. Reload it to continue.', 409)
    item = items[row['current_index']]
    saved = states.setdefault(item_id, {})
    question = item['question']
    now = timestamp()
    observation = dict(activity='course_preparation', item_id=item_id, content_hash=payload_hash(item),
                       rubric_version=item['rubric_version'], practice_id=attempt_id, now=now,
                       catalogue_version=identity['target_catalogue_version'],
                       target=next(target for target in snapshot['targets'] if target['id'] == item['target_id']))
    if action == 'learn':
        if saved.get('learned'):
            raise LearningError('stale_practice', 'This example has already been introduced.', 409)
        saved['learned'] = True
        _observe(conn, profile_id, item['target_id'], source_key=attempt_id + ':learn', introduced=True, **observation)
    elif not saved.get('learned'):
        raise LearningError('introduction_required', 'Try the example before answering.', 409)
    elif action == 'next':
        if 'answer' not in saved:
            raise LearningError('answer_required', 'Choose a reply before continuing.', 409)
        index = row['current_index'] + 1
        _execute(conn, 'UPDATE course_target_practice_attempts SET current_index=?,status=?,completed_at=? WHERE id=?',
                 (index, 'completed' if index == len(items) else 'active', now if index == len(items) else None, attempt_id))
    elif 'answer' in saved:
        raise LearningError('stale_practice', 'This answer is saved. Continue to the next item.', 409)
    elif action == 'answer':
        if choice_id not in {choice['id'] for choice in question['choices']}:
            raise LearningError('invalid_choice', 'Choose one of the displayed replies.')
        if question.get('audio_url') and not (saved.get('listened') or saved.get('transcript')):
            raise LearningError('listen_required', 'Listen to the message before answering.', 409)
        saved['answer'] = choice_id
        # An immediately taught recognition task is practice, not an independent
        # demonstration. The checkpoint assesses retention with different facts.
        _observe(conn, profile_id, item['target_id'], source_key=attempt_id + ':answer', practised=True,
                 score=float(choice_id == question['answer']), first_response={'choice_id': choice_id},
                 response={'choice_id': choice_id}, support={'teaching': True, 'hint': bool(saved.get('hint')),
                 'transcript': bool(saved.get('transcript'))}, **observation)
    elif action == 'hint':
        saved['hint'] = True
    elif action in ('listened', 'transcript'):
        if not question.get('audio_url'):
            raise LearningError('invalid_action', 'This question uses the written message.')
        saved[action] = True
    _execute(conn, 'UPDATE course_target_practice_attempts SET state_json=? WHERE id=?', (encoded(states), attempt_id))
    result = practice_get(conn, profile_id, attempt_id)
    _execute(conn, 'INSERT INTO course_target_practice_receipts VALUES (?,?,?,?,?,?)', (profile_id, request_id, attempt_id, digest, encoded(result), now))
    return result


def record_checkpoint_targets(conn, profile_id, attempt_id, frozen, answers, supported, now=None):
    """Record exact response evidence; no checkpoint total is spread over targets.

    The frozen snapshot and submitted answers are reloaded from the owned saved
    attempt. Parameters exist for callers already holding them, never as a way to
    override authoritative content. Legacy attempts have no target IDs.
    """
    if not _ready(conn):
        return 0
    row = _execute(conn, 'SELECT * FROM course_checkpoint_attempts WHERE id=? AND profile_id=?', (attempt_id, profile_id)).fetchone()
    if not row:
        raise LearningError('checkpoint_not_found', 'That letter was not found.', 404)
    # Actual schema field names are stable since the v1 checkpoint migration.
    snapshot = json.loads(row['frozen_json'])
    answers = json.loads(row['answers_json']) if row['answers_json'] else {}
    support = json.loads(row['support_json'])
    count = 0
    for question in snapshot.get('variant', {}).get('questions', []):
        answer = answers.get(question['id'])
        if answer is None:
            continue
        chosen = answer.get('choice_id') if isinstance(answer, dict) else answer
        score = float(chosen == question['answer'])
        has_support = bool('translation' in support or (question.get('kind') == 'listening' and 'transcript' in support) or 'hint:' + question['id'] in support)
        if question.get('kind') == 'listening' and not row['listened_at']:
            continue
        for target_id in question.get('target_ids', []):
            target = get_target(target_id)
            if not target or target['evidence_kind'] == 'independent_production':
                continue
            count += _observe(conn, profile_id, target_id, activity='course_checkpoint', source_key=attempt_id,
                              item_id=question['id'], content_hash=payload_hash(question), rubric_version=row['rubric_version'],
                              practised=True, score=score, first_response=answer, response=answer,
                              support={'assisted': has_support}, checkpoint_id=attempt_id, now=now)
    return count


def _step_target_map(scenario):
    """Small authored mappings for already constrained A1 dialogue contracts.

    Only requirements with a direct selected-response equivalent are mapped.
    No written/spoken production or every target in the topic is inferred.
    A correct grammar quote alone is insufficient: the options must actually
    test that form, which existing step dialogues do not guarantee.
    """
    contract = scenario.get('learning_contract') or {}
    if contract.get('version') != 'speaking-curriculum-v2' or contract.get('target_level') != 'A1':
        return {}
    family = scenario.get('scenario_id')
    bundle = (scenario.get('variation') or {}).get('bundle_id')
    if family == 'cafe' and bundle in ('takeaway', 'warm-lunch', 'two-drinks'):
        return {'objective-1': ['a1.food.make-request.read']}
    if family == 'directions' and bundle in ('park', 'pharmacy', 'post-office'):
        return {'objective-1': ['a1.places.ask-location.read'],
                'objective-2': ['a1.places.follow-directions.read']}
    if family == 'meet-someone' and bundle in ('classmate', 'neighbour', 'club'):
        return {'objective-1': ['a1.greetings.exchange-names.read'],
                'objective-2': ['a1.greetings.exchange-names.read']}
    if family == 'shop' and bundle in ('tshirt', 'hat', 'trousers'):
        return {'objective-1': ['a1.clothing.identify-clothes.read'],
                'objective-2': ['a1.clothing.identify-clothing-description.read']}
    return {}


def record_event_targets(conn, profile_id, event_id, now=None):
    """Read saved turn-level contracts after an activity event is persisted.

    Aggregate-marked writing/translation/reading remain topic evidence. Their
    old records lack an item rubric, so they intentionally create no targets.
    """
    if not _ready(conn):
        return 0
    event = _execute(conn, 'SELECT * FROM progression_events WHERE id=? AND profile_id=? AND reversed_at IS NULL', (event_id, profile_id)).fetchone()
    if not event or event['target_level'] != 'A1':
        return 0
    if event['activity'] == 'first_steps':
        return _record_first_steps(conn, profile_id, event, now)
    if event['activity'] != 'speaking_step':
        return 0
    row = _execute(conn, "SELECT * FROM step_conversation_sessions WHERE id=? AND profile_id=? AND state='completed' AND target_level='A1'", (event['source_key'], profile_id)).fetchone()
    if not row or row['variant_id'] != event['content_key'] or not row['dialogue_json']:
        return 0
    scenario, dialogue, progress = json.loads(row['scenario_json']), json.loads(row['dialogue_json']), json.loads(row['progress_json'])
    target_map = _step_target_map(scenario)
    requirements = {item['id']: item for item in (scenario.get('learning_contract') or {}).get('requirements', [])}
    turns = dialogue.get('turns', [])
    count = 0
    import re
    for coverage in dialogue.get('coverage', []):
        requirement = requirements.get(coverage.get('requirement_id'))
        ordinal = coverage.get('turn')
        if (not requirement or coverage.get('role') != 'learner' or type(ordinal) is not int or not 1 <= ordinal <= len(turns)):
            continue
        turn = turns[ordinal - 1]
        correct = next((item for item in turn.get('options', []) if item.get('correct') is True), None)
        quote = coverage.get('quote')
        if (not correct or not isinstance(quote, str) or len(re.findall(r'[А-Яа-яЁё]', quote)) < 2
                or not re.search(r'(?<!\w)' + re.escape(quote) + r'(?!\w)', correct.get('russian', ''))):
            continue
        answers = _execute(conn, 'SELECT * FROM step_conversation_answers WHERE session_id=? AND turn_id=? ORDER BY created_at,rowid', (row['id'], turn['id'])).fetchall()
        if not answers or not progress.get(turn['id'], {}).get('answered'):
            continue
        first, last = answers[0], answers[-1]
        if not last['correct'] or last['option_id'] != correct['id']:
            continue
        # First attempt is retained even if a later correction completed the turn.
        first_reply = next((item for item in turn['options'] if item['id'] == first['option_id']), None)
        if not first_reply:
            continue
        for target_id in target_map.get(requirement['id'], []):
            count += _observe(conn, profile_id, target_id, activity='speaking_step', source_key=row['id'],
                item_id=turn['id'], content_hash=payload_hash({'turn': turn, 'requirement': requirement, 'coverage': coverage}),
                rubric_version='speaking-selection-targets-v1', introduced=True, practised=True,
                score=float(bool(first['correct'])), first_response={'choice_id': first['option_id'], 'russian': first_reply['russian']},
                response={'choice_id': last['option_id'], 'russian': correct['russian'], 'evidence_quote': quote},
                support={'hint': bool(progress.get(turn['id'], {}).get('hint_used')), 'prior_incorrect': len(answers) > 1},
                event_id=event_id, now=now)
    return count


def _record_first_steps(conn, profile_id, event, now):
    """Reuse only individual authored decisions with a matching A1 target.

    Familiar words alone do not establish a topic. This is called for new
    completion events, never a historical backfill or a second welcome reward.
    """
    row = _execute(conn, 'SELECT * FROM first_steps_attempts WHERE id=? AND profile_id=? AND completed_at IS NOT NULL',
                   (event['source_key'], profile_id)).fetchone()
    if not row or event['content_key'] != f'first-steps:{row["lesson_id"]}:{row["version"]}':
        return 0
    lesson = json.loads(row['content_json'])
    authored = json.loads((PRACTICE_FILE.parent / 'first_steps.json').read_text(encoding='utf-8'))
    original = next((item for item in authored['lessons'] if item['id'] == row['lesson_id']), None)
    if not original or row['version'] != authored['version']:
        return 0
    mapping = {'help-ask-where': 'a1.places.ask-location.read',
               'set-off-greet': 'a1.greetings.polite-greeting.read',
               'set-off-turn': 'a1.places.follow-directions.read'}
    answers = json.loads(row['answers_json'])
    learned = json.loads(row['learned_json'])
    fully_taught = {item['id'] for item in lesson.get('teaching', [])} <= set(learned)
    count = 0
    for question in lesson.get('questions', []):
        target_id = mapping.get(question['id'])
        if not target_id or question not in original['questions']:
            continue
        answer = answers.get(question['id'])
        if not isinstance(answer, dict) or answer.get('answer') not in {c['id'] for c in question['choices']}:
            continue
        count += _observe(conn, profile_id, target_id, activity='first_steps', source_key=row['id'],
            item_id=question['id'], content_hash=payload_hash(question), rubric_version='first-steps-targets-v1',
            introduced=fully_taught, practised=True, score=float(answer['answer'] == question['answer']),
            first_response=answer, response=answer, support={'teaching': True, 'hint': bool(answer.get('hint_used'))},
            event_id=event['id'], now=now)
    return count


def record_speaking_targets(conn, profile_id, session_id, now=None):
    """Optional spoken-goal diagnostics from the separate microphone review.

    A short valid request can provide useful goal evidence while grammar/fluency
    remain unscored. Existing live support telemetry cannot prove independence;
    these observations therefore never establish an independent demonstration.
    """
    if not _ready(conn) or not _execute(conn, 'SELECT 1 FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL', (profile_id,)).fetchone():
        return 0
    row = _execute(conn, '''SELECT s.scenario_json,s.target_level,r.report_json
        FROM live_conversation_sessions s JOIN speaking_reviews r ON r.session_id=s.id
        WHERE s.id=? AND s.profile_id=? AND r.state='ready' ''', (session_id, profile_id)).fetchone()
    if not row or row['target_level'] != 'A1' or not row['report_json']:
        return 0
    scenario, report = json.loads(row['scenario_json']), json.loads(row['report_json'])
    if (report.get('basis') != 'audio_review' or report.get('rubric_version') != 'speaking-audio-v1'
            or report.get('speech_status') not in ('russian', 'mixed', 'insufficient')):
        return 0
    mapping = _step_target_map(scenario)
    allowed = set(scenario.get('goal_ids') or [])
    transcript = report.get('transcript')
    uncertain = report.get('uncertain_phrases', [])
    if not isinstance(transcript, str) or not isinstance(uncertain, list):
        return 0
    event = _execute(conn, "SELECT id,reversed_at FROM progression_events WHERE profile_id=? AND activity='speaking' AND source_key=?", (profile_id, session_id)).fetchone()
    if event and event['reversed_at'] is not None:
        return 0
    count = 0
    import re
    for goal in report.get('goals', []):
        if goal.get('id') not in allowed or goal.get('status') not in ('completed', 'not_yet'):
            continue
        quotes = goal.get('evidence')
        if (not isinstance(quotes, list) or not quotes or any(not isinstance(quote, str)
                or not re.search(r'[А-Яа-яЁё]', quote) or quote not in transcript or '[unclear]' in quote
                or any(isinstance(span, str) and (span in quote or quote in span) for span in uncertain)
                for quote in quotes)):
            continue
        for selection_id in mapping.get(goal['id'], []):
            target_id = selection_id.removesuffix('.read') + '.speak'
            count += _observe(conn, profile_id, target_id, activity='speaking', source_key=session_id,
                item_id=goal['id'], content_hash=payload_hash({'scenario': scenario, 'goal': goal}),
                rubric_version='speaking-audio-goals-v1', practised=True, score=float(goal['status'] == 'completed'),
                first_response={'quotes': quotes}, response={'quotes': quotes, 'status': goal['status'], 'basis': 'independent_audio_review'},
                support={'independence_unverified': True}, event_id=event['id'] if event else None, now=now)
    return count
