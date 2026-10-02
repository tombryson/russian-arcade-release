"""Versioned lesson navigation over the existing activity stores.

Every allocation happens under the run's writer reservation. Reads neither
allocate tasks nor call providers. The manifest and all task assets are frozen
at start so later catalogue edits cannot change an active lesson.
"""
from copy import deepcopy
import json

from flask import current_app, has_app_context

from contracts.learning import fields, key, validate_pack
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, require_access, timestamp, transaction
from repositories.curriculum_sequence_repository import (
    binding_for_task, check_revision, owned_run, receipt, save_receipt,
)

SEQUENCE = 'location-destination-sequence-v1'
UNIT = 'location-destination-v2'
NO_EFFECTS = 'unit-transfer-no-effects-v1'
PRACTICE_PREFIX = 'curriculum-unit:sequence:'


def _assets(manifest):
    from services.curriculum_sequence_content import load_asset
    result = {}
    def collect(content_id):
        if content_id in result:
            return
        asset = load_asset(content_id)
        result[content_id] = asset
        if asset['kind'] == 'task_group':
            for family in asset['content']['families']:
                for child in family['task_ids']:
                    collect(child)
    for step in manifest['steps']:
        collect(step['content_id'])
    return result


def _bindings(conn, run_id):
    rows = conn.execute('SELECT * FROM curriculum_unit_bindings WHERE run_id=? ORDER BY ordinal', (run_id,)).fetchall()
    return {row['step_id']: dict(row) for row in rows}


def _asset(run, step):
    return run['manifest']['assets'][step['content_id']]


def _binding_asset(conn, run, binding):
    prefix = binding['task_key'] + ':'
    row = conn.execute('SELECT contract_json FROM activity_task_contracts WHERE profile_id=? AND activity=? '
        'AND (task_key=? OR substr(task_key,1,?)=?) LIMIT 1',
        (binding['profile_id'], binding['activity'], binding['task_key'], len(prefix), prefix)).fetchone()
    if row is None:
        raise LearningError('content_unavailable', 'The saved task needs to be restored.', 409)
    return run['manifest']['assets'][json.loads(row[0])['content_version']]


def _transfer_family(conn, run, asset):
    seen = {r[0] for r in conn.execute('SELECT family_id FROM curriculum_transfer_exposure WHERE profile_id=?', (run['profile_id'],))}
    families = asset['content']['families']
    playable = [f for f in families if all(_capability(run['manifest']['assets'][cid]) == 'available' for cid in f['task_ids'])]
    choices = playable or families
    unseen = next((f for f in choices if f['exposure_family_id'] not in seen), None)
    if unseen:
        return unseen
    # Once every finite form has been encountered, rotate the least recently
    # issued family. It remains repeated work; never call it fresh evidence.
    def latest(family):
        placeholders = ','.join('?' for _ in family['task_ids'])
        row = conn.execute('SELECT MAX(rowid) FROM activity_task_contracts WHERE profile_id=? '
            "AND json_extract(contract_json,'$.content_version') IN (" + placeholders + ')',
            (run['profile_id'], *family['task_ids'])).fetchone()
        return row[0] or 0
    return min(choices, key=latest)


def _repeated(conn, binding):
    prefix = binding['task_key'] + ':'
    row = conn.execute('SELECT rowid,contract_json FROM activity_task_contracts WHERE profile_id=? AND activity=? '
        'AND (task_key=? OR substr(task_key,1,?)=?) ORDER BY rowid LIMIT 1',
        (binding['profile_id'], binding['activity'], binding['task_key'], len(prefix), prefix)).fetchone()
    if not row:
        return False
    version = json.loads(row[1])['content_version']
    return conn.execute('SELECT 1 FROM activity_task_contracts WHERE profile_id=? AND rowid<? '
                        'AND json_extract(contract_json,\'$.content_version\')=? LIMIT 1',
                        (binding['profile_id'], row[0], version)).fetchone() is not None


def _capability(asset):
    config = current_app.config if has_app_context() else {}
    kind = asset['kind']
    if kind == 'listening':
        from services.learning_listening import verify_audio
        for item in asset['content']['items']:
            if not item.get('audio'):
                return 'audio_unavailable'
            try:
                verify_audio(_pack_item(item))
            except (LearningError, ValueError, OSError):
                return 'audio_unavailable'
    if kind in ('writing', 'speaking', 'reading') and config.get('PUBLIC_DEMO'):
        return 'unsupported_workspace'
    if kind in ('writing', 'reading') and config.get('WORD_POST_HOUSEHOLD_ENABLED'):
        return 'unsupported_workspace'
    if kind == 'speaking' and not config.get('OPENAI_API_KEY'):
        return 'provider_unavailable'
    if kind == 'speaking':
        from services.unit_exchange import UnitExchangeService
        try:
            for turn in asset['content']['turns']:
                UnitExchangeService._prompt_path(turn)
        except (LearningError, ValueError, OSError):
            return 'audio_unavailable'
    return 'available'


def _state(conn, binding):
    if not binding:
        return 'not_started'
    activity, task_key = binding['activity'], binding['task_key']
    if activity == 'curriculum_unit':
        row = conn.execute('SELECT status,current_index FROM learning_sessions WHERE id=? AND profile_id=?',
                           (task_key, binding['profile_id'])).fetchone()
        if row is None:
            raise LearningError('content_unavailable', 'The saved activity needs to be restored.', 409)
        if row['status'] == 'completed':
            return 'reviewed'
        return 'draft'
    if activity == 'unit_exchange':
        from services.unit_exchange import exchange_work_state
        return exchange_work_state(conn, binding['profile_id'], task_key)
    from services.activity_review_submissions import task_work_state
    return task_work_state(conn, binding['profile_id'], activity, task_key)


def _url(binding):
    if binding['activity'] == 'curriculum_unit':
        return '/#practice/' + binding['task_key']
    if binding['activity'] == 'writing':
        return '/writing/load/' + binding['task_key']
    if binding['activity'] == 'unit_exchange':
        return '/#unit-exchange/' + binding['task_key']
    return '/comprehension/tasks/' + binding['task_key']


def _view(conn, run):
    bindings = _bindings(conn, run['id'])
    lesson_url = '/curriculum/units/' + run['unit_id'] + '?run=' + run['id']
    steps = []
    for step in run['manifest']['steps']:
        asset = _asset(run, step)
        binding = bindings.get(step['id'])
        state = _state(conn, binding)
        availability = _capability(asset)
        repeated = _repeated(conn, binding) if binding else False
        if asset['kind'] == 'task_group':
            children = [b for name, b in bindings.items() if name.startswith(step['id'] + '/')]
            child_states = [_state(conn, child) for child in children]
            state = ('reviewed' if children and all(v == 'reviewed' for v in child_states)
                     else 'draft' if children else 'not_started')
            first = next((b for b in children if _state(conn, b) != 'reviewed'), None)
            if first:
                binding = first
            if children:
                repeated = _repeated(conn, children[0])
            child_assets = ([_binding_asset(conn, run, b) for b in children if _state(conn, b) != 'reviewed'] if children else
                            [run['manifest']['assets'][cid] for cid in _transfer_family(conn, run, asset)['task_ids']])
            unavailable = [_capability(a) for a in child_assets if _capability(a) != 'available']
            availability = unavailable[0] if unavailable else 'available'
        steps.append({'id': step['id'], 'label': step.get('title', asset['title']),
                      'label_ru': step.get('title_ru', asset.get('title_ru', asset['title'])),
                      'work_state': state, 'availability': availability,
                      'repeated': repeated,
                      'url': _url(binding) if binding else None})
    required = run['manifest']['completion_paths'][run['completion_path']]
    complete = all(next(s for s in steps if s['id'] == sid)['work_state'] == 'reviewed' for sid in required)
    candidates = [s for s in steps if s['id'] in required and s['availability'] == 'available'
                  and s['work_state'] in ('not_started', 'draft')]
    choice = next((s for s in candidates if s['id'] == run['last_step_id']), candidates[0] if candidates else None)
    if run['completion_path'] == 'guided' and run['last_step_id'] is None and not bindings:
        choice = next((s for s in steps if s['id'] == 'learn'), choice)
    return {'id': run['id'], 'profile_id': run['profile_id'], 'sequence_id': run['sequence_id'],
            'unit_id': run['unit_id'], 'revision': run['revision'], 'lesson_url': lesson_url,
            'completion_path': run['completion_path'], 'completed': complete, 'steps': steps,
            'next_action': ({'step_id': choice['id'], 'label': choice['label'], 'label_ru': choice['label_ru'],
                             'url': choice['url']} if choice else None)}


def _refresh_completion(conn, run):
    view = _view(conn, run)
    if view['completed'] and run['completed_at'] is None:
        conn.execute('UPDATE curriculum_unit_runs SET completed_at=?,updated_at=? WHERE id=?',
                     (timestamp(), timestamp(), run['id']))
    return view


def _pack_item(item):
    allowed = ('id', 'type', 'prompt', 'answer', 'choices', 'hint', 'accepted_answers', 'audio', 'transcript')
    return {name: deepcopy(item[name]) for name in allowed if name in item}


def _prior_disclosed_attempt(conn, profile_id, version_id, item_id, exclude_session=None):
    from services.learning_listening import feedback_is_deferred, recording_transcript_disclosed
    rows = conn.execute('SELECT a.id,a.session_id,s.current_index,v.payload FROM activity_attempts a '
        'JOIN learning_sessions s ON s.id=a.session_id JOIN learning_content_versions v ON v.id=s.version_id '
        'WHERE s.profile_id=? AND s.version_id=? AND a.item_id=? '
        'AND (? IS NULL OR s.id<>?) ORDER BY a.created_at DESC,a.rowid DESC',
        (profile_id, version_id, item_id, exclude_session, exclude_session))
    for row in rows:
        pack = json.loads(row['payload'])
        item = next(i for i in pack['items'] if i['id'] == item_id)
        if (feedback_is_deferred(pack, row['current_index'], item)
                and not recording_transcript_disclosed(conn, row['session_id'], item, pack['items'])):
            continue
        return row['id']
    return None


def _allocate_practice(conn, profile_id, asset, allocation_key):
    from services.curriculum_sequence_content import task_contract
    from services.activity_evidence import save_contract
    items = [_pack_item(item) for item in asset['content']['items']]
    pack = validate_pack({'schema_version': 1, 'id': PRACTICE_PREFIX + asset['id'], 'kind': 'activity',
                          'title': asset['title'], 'source': 'Original curriculum sequence: ' + asset['id'], 'items': items})
    if asset['kind'] == 'listening':
        from services.learning_listening import verify_audio
        for item in items:
            verify_audio(item)
    row = conn.execute('SELECT id,payload FROM learning_content_versions WHERE content_id=?', (pack['id'],)).fetchone()
    now = timestamp()
    if row:
        if row['payload'] != encoded(pack):
            raise LearningError('content_changed', 'This lesson needs a new content version.', 409)
        version_id = row['id']
    else:
        version_id = identifier()
        conn.execute('INSERT INTO learning_content(id,kind,created_at) VALUES (?,?,?)', (pack['id'], 'activity', now))
        conn.execute("INSERT INTO learning_content_versions(id,content_id,version,title,payload,source,status,approved_by,approved_at,created_at) VALUES (?,?,1,?,?,?,'published','authored sequence',?,?)",
                     (version_id, pack['id'], pack['title'], encoded(pack), pack['source'], now, now))
    sid = identifier()
    conn.execute('INSERT INTO learning_sessions(id,profile_id,version_id,kind,start_key,start_hash,start_result,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                 (sid, profile_id, version_id, 'activity', allocation_key, payload_hash(pack), '{}', now, now))
    for item in items:
        contract = task_contract(asset, sid + ':' + item['id'], item_id=item['id'])
        save_contract(conn, profile_id, 'curriculum_unit', sid + ':' + item['id'], contract)
        previous = _prior_disclosed_attempt(conn, profile_id, version_id, item['id'])
        if previous:
            conn.execute('INSERT INTO learning_prior_feedback VALUES (?,?,?)', (sid, item['id'], previous))
    return {'activity': 'curriculum_unit', 'task_key': sid}


def _allocate(conn, run, step_id, asset, ordinal, policy):
    from services.curriculum_sequence_content import task_contract
    allocation_key = 'sequence:' + payload_hash([run['id'], step_id, ordinal])[:48]
    if asset['kind'] in ('choice', 'controlled_text', 'listening'):
        task = _allocate_practice(conn, run['profile_id'], asset, allocation_key)
    elif asset['kind'] in ('reading', 'writing'):
        from services.activity_review_submissions import create_comprehension_in_transaction, create_writing_in_transaction
        factory = create_comprehension_in_transaction if asset['kind'] == 'reading' else create_writing_in_transaction
        task = factory(conn, run['profile_id'], asset, task_contract)
    elif asset['kind'] == 'speaking':
        from services.unit_exchange import create_in_transaction
        task = create_in_transaction(conn, run['profile_id'], asset, task_contract)
    else:
        raise LearningError('invalid_step', 'Open the lesson explanation before continuing.')
    conn.execute('INSERT INTO curriculum_unit_bindings VALUES (?,?,?,?,?,?,?,?,?)',
                 (identifier(), run['id'], run['profile_id'], step_id, ordinal, task['activity'], str(task['task_key']), policy, timestamp()))
    return {**task, 'profile_id': run['profile_id']}


class CurriculumSequenceService:
    def __init__(self, db_path):
        self.db_path = db_path

    def start(self, credential, unit_id, data):
        fields(data, {'submission_id', 'sequence_id'}, {'completion_path'})
        key(data['submission_id'])
        if unit_id != UNIT or data['sequence_id'] != SEQUENCE:
            raise LearningError('not_found', 'Lesson not found.', 404)
        from services.curriculum_sequence_content import load_manifest
        manifest = deepcopy(load_manifest(data['sequence_id']))
        path = data.get('completion_path', 'guided')
        if not isinstance(path, str) or path not in manifest['completion_paths']:
            raise LearningError('invalid_input', 'Choose an available lesson path.')
        with transaction(self.db_path, write=True) as conn:
            profile = require_access(conn, credential, timestamp())
            digest, cached = receipt(conn, profile['id'], data['submission_id'], 'start', {'unit_id': unit_id, **data})
            if cached is not None:
                return cached
            active = conn.execute('SELECT id FROM curriculum_unit_runs WHERE profile_id=? AND sequence_id=? AND completed_at IS NULL',
                                  (profile['id'], manifest['id'])).fetchone()
            if active:
                old = owned_run(conn, profile['id'], active['id'])
                if not _refresh_completion(conn, old)['completed']:
                    result = _view(conn, old)
                    save_receipt(conn, profile['id'], data['submission_id'], 'start', digest, result)
                    return result
            manifest['assets'] = _assets(manifest)
            now, run_id = timestamp(), identifier()
            conn.execute('INSERT INTO curriculum_unit_runs(id,profile_id,sequence_id,unit_id,manifest_json,manifest_sha256,completion_path,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                         (run_id, profile['id'], manifest['id'], unit_id, encoded(manifest), payload_hash(manifest), path, now, now))
            result = _view(conn, owned_run(conn, profile['id'], run_id))
            save_receipt(conn, profile['id'], data['submission_id'], 'start', digest, result)
            return result

    def read(self, credential, run_id):
        with transaction(self.db_path) as conn:
            profile = require_access(conn, credential, timestamp())
            return _view(conn, owned_run(conn, profile['id'], run_id))

    def command(self, credential, run_id, operation, data, step_id=None):
        optional = {'step_id', 'completion_path', 'skipped'} if operation == 'navigation' else set()
        fields(data, {'submission_id', 'expected_revision'}, optional)
        with transaction(self.db_path, write=True) as conn:
            profile = require_access(conn, credential, timestamp())
            run = owned_run(conn, profile['id'], run_id)
            digest, cached = receipt(conn, profile['id'], data['submission_id'], operation,
                                     {'run_id': run_id, 'step_id': step_id, **data})
            if cached is not None:
                return cached
            check_revision(run, data['expected_revision'])
            if operation == 'retry' and _view(conn, run)['completed']:
                raise LearningError('lesson_complete', 'Start a new lesson to practise again. Your finished work is saved.', 409)
            target = data.get('step_id') if operation == 'navigation' else step_id
            steps = {s['id']: s for s in run['manifest']['steps']}
            if target is not None and (not isinstance(target, str) or target not in steps):
                raise LearningError('invalid_step', 'Choose an activity from this lesson.')
            url = '/curriculum/units/' + run['unit_id'] + '?run=' + run_id
            if operation == 'navigation':
                path = data.get('completion_path', run['completion_path'])
                if not isinstance(path, str) or path not in run['manifest']['completion_paths']:
                    raise LearningError('invalid_input', 'Choose an available lesson path.')
                if path != run['completion_path'] and (_view(conn, run)['completed'] or run['completed_at'] is not None):
                    raise LearningError('lesson_complete', 'Start a new lesson to choose another path. Your finished work is saved.', 409)
                conn.execute('UPDATE curriculum_unit_runs SET completion_path=? WHERE id=?', (path, run_id))
            elif operation in ('start_step', 'retry'):
                step, bindings = steps[target], _bindings(conn, run_id)
                asset = _asset(run, step)
                availability = _capability(asset)
                if availability != 'available':
                    raise LearningError(availability, 'This activity is currently unavailable. Your lesson is saved.', 409)
                existing = bindings.get(target)
                if asset['kind'] == 'teaching':
                    url += '#learn'
                elif existing and operation != 'retry':
                    url = _url(existing)
                elif asset['kind'] == 'task_group':
                    current = [b for sid, b in bindings.items() if sid.startswith(target + '/')]
                    if current and operation != 'retry':
                        selected = next((b for b in current if _state(conn, b) != 'reviewed'), current[-1])
                        url = _url(selected)
                    else:
                        family = _transfer_family(conn, run, asset)
                        for content_id in family['task_ids']:
                            available = _capability(run['manifest']['assets'][content_id])
                            if available != 'available':
                                raise LearningError(available, 'This situation is not ready yet. Your saved work is kept.', 409)
                        conn.execute('INSERT OR IGNORE INTO curriculum_transfer_exposure VALUES (?,?,?,?)',
                                     (profile['id'], family['exposure_family_id'], run_id, timestamp()))
                        # Keep old forms in history but only the new family's slots current.
                        group_ordinal = max((b['ordinal'] for b in current), default=-1) + 1
                        allocated = [_allocate(conn, run, target + '/' + str(i), run['manifest']['assets'][cid], group_ordinal, NO_EFFECTS)
                                     for i, cid in enumerate(family['task_ids'])]
                        url = _url(allocated[0])
                else:
                    created = _allocate(conn, run, target, asset, existing['ordinal'] + 1 if existing else 0,
                                        step.get('effects_policy', 'existing-activity-effects-v1'))
                    url = _url(created)
            else:
                raise LearningError('invalid_input', 'Unknown lesson operation.')
            conn.execute('UPDATE curriculum_unit_runs SET last_step_id=COALESCE(?,last_step_id),revision=revision+1,updated_at=? WHERE id=?',
                         (target, timestamp(), run_id))
            result = {'url': url, 'run': _refresh_completion(conn, owned_run(conn, profile['id'], run_id))}
            save_receipt(conn, profile['id'], data['submission_id'], operation, digest, result)
            return result


def activity_context(conn, profile_id, activity, task_key):
    binding = binding_for_task(conn, profile_id, activity, task_key)
    if not binding:
        return None
    run = owned_run(conn, profile_id, binding['run_id'])
    view = _view(conn, run)
    step = next(s for s in view['steps'] if s['id'] == binding['step_id'].split('/')[0])
    return {'run_id': run['id'], 'step_id': binding['step_id'], 'lesson_url': view['lesson_url'],
            'step_label': step['label'], 'step_label_ru': step['label_ru'],
            'repeated': _repeated(conn, binding),
            'next_action': view['next_action']}


def practice_context(conn, profile_id, session_id):
    return activity_context(conn, profile_id, 'curriculum_unit', session_id)


def capture_prior_feedback(conn, profile_id, session_id, item_id):
    """Freeze disclosures that occurred after allocation, including other tabs."""
    saved = conn.execute('SELECT version_id FROM learning_sessions WHERE id=? AND profile_id=?',
                         (session_id, profile_id)).fetchone()
    previous = _prior_disclosed_attempt(conn, profile_id, saved['version_id'], item_id, session_id) if saved else None
    if previous:
        conn.execute('INSERT OR IGNORE INTO learning_prior_feedback VALUES (?,?,?)', (session_id, item_id, previous))


def practice_support(conn, profile_id, session_id, item_id, support):
    """An exact answer already disclosed in a prior attempt is still help.

    Match the frozen content version and item, not vocabulary or a broad unit:
    earlier teaching must not taint every subsequent use of a learned pattern.
    """
    from services.activity_evidence import load_contract
    contract = load_contract(conn, profile_id, 'curriculum_unit', session_id + ':' + item_id)
    if contract is None or contract['schema_version'] < 2:
        return support
    previous = conn.execute('SELECT 1 FROM learning_prior_feedback p '
        'JOIN learning_sessions s ON s.id=p.session_id WHERE p.session_id=? AND s.profile_id=? AND p.item_id=?',
        (session_id, profile_id, item_id)).fetchone()
    return list(dict.fromkeys([*support, *(['model_answer'] if previous else [])]))


def observe_answer(conn, profile_id, session_id, item, attempt_id, answer, support):
    from flask import has_request_context, session
    from contracts.learning import assess_activity_answer
    from services.activity_evidence import load_contract, save_report
    contract = load_contract(conn, profile_id, 'curriculum_unit', session_id + ':' + item['id'])
    text, correct = assess_activity_answer(item, answer)
    criterion = contract['criteria'][0]
    content = contract['content']
    explanation = content.get('explanation_ru', content['explanation']) if has_request_context() and session.get('ui_lang') == 'ru' else content['explanation']
    report = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
        'criterion_id': criterion['id'], 'outcome': 'satisfied' if correct else 'not_satisfied',
        'score': criterion['max_score'] if correct else 0, 'feedback': explanation,
        **({'reason_code': None} if contract['schema_version'] == 2 else {}),
        'evidence': [{'quote': text, 'start': 0, 'end': len(text)}]}]}
    save_report(conn, profile_id, 'curriculum_unit', session_id + ':' + item['id'], attempt_id,
                report, response_text=text, support=support)


def award_practice(conn, profile, binding, attempt_id, content_id, now):
    if binding and binding['effects_policy'] == NO_EFFECTS:
        return 0
    from services.learning_service import award_participation
    if not binding:
        return award_participation(conn, profile, attempt_id, content_id, now)
    from services.progression import study_day
    run = owned_run(conn, profile['id'], binding['run_id'])
    step = next(s for s in run['manifest']['steps'] if s['id'] == binding['step_id'])
    family = step.get('reward_family', content_id)
    aliases = step.get('reward_aliases', [])
    keys = ['activity:' + value for value in [family, content_id, *aliases]]
    if conn.execute('SELECT 1 FROM progression_claims WHERE profile_id=? AND study_day=? AND amount>0 AND content_key IN (' + ','.join('?' for _ in keys) + ')',
                    (profile['id'], study_day(conn, profile['id'], now), *keys)).fetchone():
        return 0
    return award_participation(conn, profile, attempt_id, family, now)
