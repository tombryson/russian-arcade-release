"""Owned starts for generated grammar, using the existing activity player."""
import hashlib
import json

from contracts.curriculum import freeze_task_contract
from contracts.learning import key
from repositories.learning_repository import (
    LearningError, encoded, identifier, payload_hash, require_access, timestamp, transaction,
)
from services import curriculum_generation as generation


def origin(pack):
    identity = generation.decode(pack)
    if identity is None:
        return None
    from services.curriculum_units import get_unit
    unit = get_unit(identity[0])
    target = 'location-destination-v2' if unit['id'] == 'location-destination-v1' else unit['id']
    return {'href': '/curriculum/units/' + target, 'title': unit['title'], 'explanations': {}}


def freeze(conn, profile_id, session_id, pack):
    from services.curriculum_units import _criterion, _spec
    from services.activity_evidence import save_contract
    unit_id, seed, stage = generation.decode(pack)
    expected, unit, questions = generation.build(unit_id, seed, stage)
    if pack != expected:
        raise ValueError('Generated practice differs from its versioned rules.')
    for item, question in zip(pack['items'], questions):
        controlled = stage == 'forms'
        criterion = _criterion(question['requirement_id'], question['id'],
            'unit.' + unit_id + '.' + question['rule'], question['expectation'],
            mode='controlled_text' if controlled else None,
            scope='controlled_production' if controlled else 'reference')
        content = {'item': item, 'unit_id': unit_id, 'title_en': unit['title'],
                   'title': unit['title_ru'], 'title_ru': unit['title_ru'],
                   'explanation': question['explanation'], 'explanation_ru': question['explanation_ru'],
                   'item_locale_ru': {'prompt': question['prompt_ru'], 'hint': question['hint_ru']},
                   'generator': 'g1', 'semantic_fingerprint': question['semantic']}
        spec = _spec(unit, session_id + ':' + item['id'], 'curriculum_unit', content, [criterion])
        spec.update(content_version=pack['id'], rubric_version='authored-controlled-form-v1' if controlled else 'rule-generated-choice-v1')
        spec['support'] = {'allowed': ['hint', 'model_answer'], 'independence_breakers': ['hint', 'model_answer']}
        save_contract(conn, profile_id, 'curriculum_unit', session_id + ':' + item['id'], freeze_task_contract(spec))


def _select(conn, profile_id, unit_id, stage, request_id):
    prefix = generation.PREFIX + unit_id + ':' + ('f' if stage == 'forms' else 'p') + ':'
    # Exposure begins when a set is issued, including abandoned sets. Read both
    # response modes: seeing a choice already exposes the related typed task.
    rows = conn.execute('SELECT v.payload FROM learning_sessions s JOIN learning_content_versions v ON v.id=s.version_id '
        'WHERE s.profile_id=? AND substr(v.content_id,1,?)=? ORDER BY s.created_at DESC,s.rowid DESC LIMIT 30',
        (profile_id, len(generation.PREFIX + unit_id + ':'), generation.PREFIX + unit_id + ':')).fetchall()
    seen = {item['id'] for row in rows for item in json.loads(row[0])['items']}
    best, overlap = None, 100
    for ordinal in range(24):
        seed = hashlib.sha256(encoded([profile_id, request_id, unit_id, stage, ordinal]).encode()).hexdigest()[:20]
        pack, _, _ = generation.build(unit_id, seed, stage)
        repeats = sum(item['id'] in seen for item in pack['items'])
        if repeats < overlap:
            best, overlap = pack, repeats
        if not repeats:
            break
    return prefix, best


def start(db_path, credential, unit_id, request_id, *, expected_profile_id, stage='practice'):
    from services.learning_service import LearningService
    key(request_id, 'Request ID')
    if unit_id == 'location-destination-v2':
        unit_id = 'location-destination-v1'
    if unit_id not in generation.BUILDERS or stage not in ('practice', 'forms'):
        raise LearningError('not_found', 'This practice is not available.', 404)
    service = LearningService(db_path)
    with transaction(db_path, write=True) as conn:
        now = timestamp()
        profile = require_access(conn, credential, now, profile_id=expected_profile_id)
        prefix = generation.PREFIX + unit_id + ':' + ('f' if stage == 'forms' else 'p') + ':'
        digest = payload_hash({'unit_id': unit_id, 'stage': stage})
        receipt = conn.execute('SELECT request_sha256,session_id FROM curriculum_generated_starts WHERE profile_id=? AND request_id=?',
                               (profile['id'], request_id)).fetchone()
        if receipt:
            if receipt[0] != digest:
                raise LearningError('idempotency_conflict', 'This request already belongs to another exercise.', 409)
            row = conn.execute('SELECT v.payload FROM learning_sessions s JOIN learning_content_versions v ON v.id=s.version_id WHERE s.id=? AND s.profile_id=?',
                               (receipt[1], profile['id'])).fetchone()
            if row is None:
                raise LearningError('not_found', 'The saved exercise is unavailable.', 404)
            return service._snapshot(conn, receipt[1], json.loads(row[0]))
        def remember(sid):
            conn.execute('INSERT INTO curriculum_generated_starts VALUES (?,?,?,?,?)', (profile['id'], request_id, digest, sid, now))
        previous = conn.execute('SELECT s.*,v.payload,v.content_id FROM learning_sessions s JOIN learning_content_versions v ON v.id=s.version_id '
            'WHERE s.profile_id=? AND s.start_key=?', (profile['id'], request_id)).fetchone()
        if previous:
            if not previous['content_id'].startswith(prefix):
                raise LearningError('idempotency_conflict', 'This request already belongs to another exercise.', 409)
            remember(previous['id'])
            return service._snapshot(conn, previous['id'], json.loads(previous['payload']))
        active = conn.execute("SELECT s.id,v.payload FROM learning_sessions s JOIN learning_content_versions v ON v.id=s.version_id "
            "WHERE s.profile_id=? AND s.status='active' AND substr(v.content_id,1,?)=? ORDER BY s.created_at DESC,s.rowid DESC LIMIT 1",
            (profile['id'], len(prefix), prefix)).fetchone()
        if active:
            remember(active['id'])
            return service._snapshot(conn, active['id'], json.loads(active['payload']))
        _, pack = _select(conn, profile['id'], unit_id, stage, request_id)
        version_id, session_id = identifier(), identifier()
        conn.execute("INSERT INTO learning_content(id,kind,created_at) VALUES (?,'activity',?)", (pack['id'], now))
        conn.execute("INSERT INTO learning_content_versions(id,content_id,version,title,payload,source,status,approved_by,approved_at,created_at) "
            "VALUES (?,?,1,?,?,?,'published','validated grammar rules',?,?)",
            (version_id, pack['id'], pack['title'], encoded(pack), pack['source'], now, now))
        data = {'profile_id': profile['id'], 'version_id': version_id, 'submission_id': request_id}
        conn.execute("INSERT INTO learning_sessions(id,profile_id,version_id,kind,start_key,start_hash,start_result,created_at,updated_at) VALUES (?,?,?,'activity',?,?,'{}',?,?)",
            (session_id, profile['id'], version_id, request_id, payload_hash(data), now, now))
        freeze(conn, profile['id'], session_id, pack)
        remember(session_id)
        result = service._snapshot(conn, session_id, pack)
        conn.execute('UPDATE learning_sessions SET start_result=? WHERE id=?', (encoded(result), session_id))
        return result


def reward_family(content_id):
    if not content_id.startswith(generation.PREFIX):
        return content_id
    unit_id, mode, _ = content_id[len(generation.PREFIX):].split(':')
    # New seeds and answer modes do not create another daily reward identity.
    return 'curriculum-unit:' + unit_id


def same_question(current_pack, old_pack, item_id):
    """An option shuffle or typed reply does not make a disclosed answer new."""
    from contracts.learning import activity_answer_text
    if not all(p['id'].startswith(generation.PREFIX) for p in (current_pack, old_pack)):
        return False
    current = next((i for i in current_pack['items'] if i['id'] == item_id), None)
    old = next((i for i in old_pack['items'] if i['id'] == item_id), None)
    # Rule-level semantic IDs deliberately ignore actor renaming. That is
    # the same question for exposure purposes even if the display text differs.
    return bool(current and old and generation.decode(current_pack)[0] == generation.decode(old_pack)[0]
                and activity_answer_text(current) == activity_answer_text(old))


def capture_support(conn, profile_id, session_id, item, support):
    current = conn.execute('SELECT v.payload FROM learning_sessions s JOIN learning_content_versions v ON v.id=s.version_id WHERE s.id=? AND s.profile_id=?',
                           (session_id, profile_id)).fetchone()
    if current is None:
        raise LearningError('not_found', 'The saved exercise is unavailable.', 404)
    pack = json.loads(current[0])
    for old in conn.execute('SELECT a.id,v.payload FROM activity_attempts a JOIN learning_sessions s ON s.id=a.session_id '
        'JOIN learning_content_versions v ON v.id=s.version_id WHERE s.profile_id=? AND a.session_id<>? AND a.item_id=? ORDER BY a.rowid DESC',
        (profile_id, session_id, item['id'])):
        if same_question(pack, json.loads(old[1]), item['id']):
            conn.execute('INSERT OR IGNORE INTO learning_prior_feedback VALUES (?,?,?)', (session_id, item['id'], old[0]))
            break
    return saved_support(conn, session_id, item['id'], support)


def saved_support(conn, session_id, item_id, support):
    previous = conn.execute('SELECT 1 FROM learning_prior_feedback WHERE session_id=? AND item_id=?', (session_id, item_id)).fetchone()
    return list(dict.fromkeys([*support, *(['model_answer'] if previous else [])]))
