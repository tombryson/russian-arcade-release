"""Recent assessed work projected from original activity evidence, not Elo."""
from datetime import datetime, timezone
import json

from repositories.learning_repository import require_access, timestamp, transaction
from services.curriculum_requirement_map import requirement_index

DOMAINS = (
    ('language_use', 'Language use', 'Лексика и грамматика'),
    ('reading', 'Reading', 'Чтение'), ('listening', 'Listening', 'Аудирование'),
    ('writing', 'Writing', 'Письмо'), ('speaking', 'Speaking', 'Говорение'),
)


def _time(value):
    if isinstance(value, (int, float)):
        return int(value)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return int(parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp())
    except (ValueError, AttributeError, TypeError):
        return 0


def _submitted(conn, activity, source, fallback):
    pending = conn.execute("SELECT 1 FROM sqlite_master WHERE name='activity_review_submissions'").fetchone()
    if pending:
        row = conn.execute('SELECT created_at FROM activity_review_submissions WHERE activity=? AND '
                           '(id=? OR CAST(json_extract(attempt_ref_json,\'$.id\') AS TEXT)=?) ORDER BY created_at DESC LIMIT 1',
                           (activity, str(source), str(source))).fetchone()
        if row:
            return row[0]
    table = {'writing': 'writing_attempts', 'comprehension': 'comprehension_attempts',
             'curriculum_unit': 'activity_attempts'}.get(activity)
    if table:
        row = conn.execute('SELECT created_at FROM ' + table + ' WHERE id=?', (source,)).fetchone()
        if row:
            return _time(row[0])
    return _time(fallback)


def _submission_order(conn, activity, source):
    # Historical stores use second-resolution clocks. Their persisted insertion
    # identity breaks same-second ties before the report's random UUID. Review
    # completion order must never be used: an older reply can finish last.
    row = conn.execute('SELECT rowid FROM activity_review_submissions WHERE activity=? AND '
        '(id=? OR CAST(json_extract(attempt_ref_json,\'$.id\') AS TEXT)=?) ORDER BY rowid DESC LIMIT 1',
        (activity, str(source), str(source))).fetchone()
    if row:
        return row[0]
    table = {'writing': 'writing_attempts', 'comprehension': 'comprehension_attempts',
             'curriculum_unit': 'activity_attempts'}.get(activity)
    if table:
        row = conn.execute('SELECT rowid FROM ' + table + ' WHERE id=?', (source,)).fetchone()
        if row:
            return row[0]
    return 0


def _order(observation):
    return observation['submitted_at'], observation.get('submission_order', 0), observation['id']


def _url(conn, activity, task_key):
    if activity == 'writing':
        return '/writing/load/' + task_key
    if activity == 'curriculum_unit':
        return '/#practice/' + task_key.split(':', 1)[0]
    if activity == 'comprehension':
        return '/comprehension/tasks/' + task_key.rsplit(':', 1)[0]
    if activity == 'unit_exchange':
        return '/#unit-exchange/' + task_key
    if activity == 'speaking':
        return '/#speaking'
    return '/#activities'


def _scope_label(conn, profile_id, activity, task_key, contract):
    from repositories.curriculum_sequence_repository import binding_for_task, owned_run
    identity = task_key.split(':', 1)[0] if activity == 'curriculum_unit' else task_key.rsplit(':', 1)[0] if activity == 'comprehension' else task_key
    binding = binding_for_task(conn, profile_id, activity, identity)
    if binding:
        manifest = owned_run(conn, profile_id, binding['run_id'])['manifest']
        asset = manifest['assets'].get(contract['content_version'])
        if asset:
            return asset['title'], asset['title_ru']
    content = contract['content']
    return content.get('title_en', 'This task'), content.get('title', 'Это задание')


def _pilot_scopes(conn, profile_id, level, grouped):
    pending = []
    rows = conn.execute('SELECT c.domain,c.task_json,s.id,s.created_at,r.state,r.report_json,'
        'p.id AS session_id,p.blueprint_id FROM assessment_pilot_submissions s '
        'JOIN assessment_pilot_components c ON c.id=s.component_id AND c.profile_id=s.profile_id '
        'JOIN assessment_pilot_sessions p ON p.id=c.session_id AND p.profile_id=c.profile_id '
        'JOIN assessment_pilot_reviews r ON r.submission_id=s.id WHERE s.profile_id=?', (profile_id,)).fetchall()
    for row in rows:
        domain, task, identity, submitted, state, raw, session_id, blueprint_id = row
        task = json.loads(task)
        contract = task.get('contract', task.get('curriculum_contract', {}))
        if contract.get('level') != level:
            continue
        url = '/#assessment/' + session_id
        if state != 'ready':
            pending.append({'domains': [domain], 'submitted_at': submitted, 'url': url,
                            'state': 'review_unavailable' if state == 'failed' else 'submitted'})
            continue
        report = json.loads(raw)
        judgements = report['criterion_report']['judgements']
        outcome = ('practise_and_retry' if any(j['outcome'] in ('not_satisfied', 'partial') for j in judgements)
                   else 'more_evidence_needed' if any(j['score'] is None for j in judgements) else 'demonstrated_in_task')
        scope = 'pilot:' + blueprint_id
        result = {'id': identity, 'scope_id': scope, 'level': level, 'activity': 'assessment_pilot',
                  'scope_label': 'Five-skill diagnostic', 'scope_label_ru': 'Проверка пяти навыков',
                  'submitted_at': submitted, 'date': datetime.fromtimestamp(submitted, timezone.utc).strftime('%d %b %Y'),
                  'outcome': outcome, 'condition': 'unverified' if domain == 'speaking' else 'assisted' if report['assisted'] else 'unaided_in_app',
                  'support': report['support'], 'url': url, 'feedback': [j['feedback'] for j in judgements]}
        previous = grouped[domain].get(scope)
        if previous is None or (submitted, identity) > (previous['submitted_at'], previous['id']):
            grouped[domain][scope] = result
    return pending


def _unit_actions(conn, profile_id, level):
    """Offer owned unfinished work without allocating an activity on a read."""
    from repositories.curriculum_sequence_repository import owned_run
    from services.curriculum_sequences import _view
    actions = {}
    preferred = {'language_use': ('forms', 'choices'), 'reading': ('reading',),
                 'listening': ('listening',), 'writing': ('writing',), 'speaking': ('speaking',)}
    rows = conn.execute('SELECT id FROM curriculum_unit_runs WHERE profile_id=? AND completed_at IS NULL '
                        'ORDER BY updated_at DESC,id DESC', (profile_id,)).fetchall()
    priority = {'draft': 0, 'review_unavailable': 1, 'submitted': 2, 'reviewing': 2, 'not_started': 4}
    for row in rows:
        run = owned_run(conn, profile_id, row[0])
        if run['manifest']['level'] != level:
            continue
        view = _view(conn, run)
        if view['completed']:
            continue
        for domain, ids in preferred.items():
            if domain in actions:
                continue
            candidates = [s for s in view['steps'] if s['id'] in ids and s['work_state'] != 'reviewed']
            if not candidates:
                continue
            selected = min(candidates, key=lambda s: priority.get(s['work_state'], 3))
            action = ('resume' if selected['work_state'] == 'draft' else 'retry_review' if selected['work_state'] == 'review_unavailable'
                      else 'open_saved_reply' if selected['work_state'] in ('submitted', 'reviewing')
                      else 'unavailable' if selected['availability'] != 'available' else 'continue_lesson')
            actions[domain] = {'kind': action, 'url': selected['url'] or view['lesson_url'],
                               'run_id': run['id'], 'step_id': selected['id'],
                               'label': selected['label'], 'label_ru': selected['label_ru']}
    return actions


def _review_action(conn, profile_id, latest):
    """Choose authored follow-up content without allocating it on a read."""
    if not latest or latest['outcome'] not in ('practise_and_retry', 'more_evidence_needed'):
        return None
    reference = latest.get('reference')
    if not reference:
        return None  # Pilot feedback retains its own blueprint and route.
    from repositories.curriculum_sequence_repository import binding_for_task, owned_run
    from services.curriculum_sequences import _view
    activity, task_key = reference['activity'], reference['task_key']
    identity = task_key.split(':', 1)[0] if activity == 'curriculum_unit' else task_key.rsplit(':', 1)[0] if activity == 'comprehension' else task_key
    binding = binding_for_task(conn, profile_id, activity, identity)
    if not binding:
        return None
    run = owned_run(conn, profile_id, binding['run_id'])
    manifest = run['manifest']
    kind = 'new_example' if latest['outcome'] == 'more_evidence_needed' else 'focused_practice'
    if kind == 'new_example':
        # Transfer offers another authored situation; reopening the exact
        # reviewed response would only display its existing feedback.
        target = next((s['id'] for s in manifest['steps'] if s['adapter'] == 'task_group'), None)
    else:
        failed = {requirement for requirement, outcome in latest.get('_findings', [])
                  if outcome in ('partial', 'not_satisfied')}
        targets = {manifest.get('remediation', {}).get(requirement) for requirement in failed}
        target = next((s['id'] for s in manifest['steps'] if s['id'] in targets), None)
    if target is None:
        return None
    view = _view(conn, run)
    step = next(s for s in view['steps'] if s['id'] == target)
    if step['work_state'] in ('draft', 'submitted', 'reviewing', 'review_unavailable'):
        kind = ('resume' if step['work_state'] == 'draft' else 'retry_review'
                if step['work_state'] == 'review_unavailable' else 'open_saved_reply')
        url = step['url']
    else:
        url = view['lesson_url'] + '#sequence-step-' + target
        if step['availability'] != 'available':
            kind = 'unavailable'
    return {'kind': kind, 'url': url, 'run_id': run['id'], 'step_id': target,
            'label': step['label'], 'label_ru': step['label_ru']}


def projection(conn, profile_id, level='A1'):
    refs = requirement_index()
    rows = conn.execute('SELECT c.activity,c.task_key,c.contract_json,r.id,r.source_key,r.report_json,r.support_json,r.created_at '
                        'FROM activity_criterion_reports r JOIN activity_task_contracts c ON c.id=r.contract_id '
                        'AND c.profile_id=r.profile_id WHERE r.profile_id=?', (profile_id,)).fetchall()
    grouped = {domain: {} for domain, _, _ in DOMAINS}
    submissions = {}
    practice_sessions = {}
    latest_reading = {}
    retained = []
    for row in rows:
        if row[0] != 'comprehension':
            retained.append(row)
            continue
        order = (_submitted(conn, row[0], row[4], row[7]), _submission_order(conn, row[0], row[4]), row[3])
        previous = latest_reading.get(row[1])
        if previous is None or order > previous[0]:
            latest_reading[row[1]] = order, row
    rows = [*retained, *(entry[1] for entry in latest_reading.values())]
    for row in rows:
        contract, report, support = json.loads(row[2]), json.loads(row[5]), json.loads(row[6])
        if contract['level'] != level:
            continue
        if row[0] == 'curriculum_unit':
            from services.learning_listening import feedback_is_deferred
            session_id, item_id = row[1].split(':', 1)
            if session_id not in practice_sessions:
                saved = conn.execute('SELECT s.current_index,v.payload FROM learning_sessions s '
                    'JOIN learning_content_versions v ON v.id=s.version_id WHERE s.id=? AND s.profile_id=?',
                    (session_id, profile_id)).fetchone()
                practice_sessions[session_id] = (saved[0], json.loads(saved[1])) if saved else None
            saved = practice_sessions[session_id]
            if saved:
                current_index, pack = saved
                item = next((item for item in pack['items'] if item['id'] == item_id), None)
                # A second tab must not reveal a message's answers while the
                # learner is still answering questions about that recording.
                if item and feedback_is_deferred(pack, current_index, item):
                    continue
        criteria = {c['id']: c for c in contract['criteria']}
        by_domain = {}
        for judgement in report['judgements']:
            criterion = criteria[judgement['criterion_id']]
            domain = refs[criterion['requirement_id']]['domain']
            by_domain.setdefault(domain, []).append(judgement)
        submitted = _submitted(conn, row[0], row[4], row[7])
        label, label_ru = _scope_label(conn, profile_id, row[0], row[1], contract)
        for domain, judgements in by_domain.items():
            outcome = ('practise_and_retry' if any(j['outcome'] in ('not_satisfied', 'partial') for j in judgements)
                       else 'more_evidence_needed' if any(j['score'] is None for j in judgements) else 'demonstrated_in_task')
            scope = contract['content_version']
            observation = {'id': row[3], 'scope_id': scope, 'level': level, 'activity': row[0],
                           'scope_label': label, 'scope_label_ru': label_ru,
                           'submitted_at': submitted, 'date': datetime.fromtimestamp(submitted, timezone.utc).strftime('%d %b %Y'),
                           'submission_order': _submission_order(conn, row[0], row[4]),
                           'outcome': outcome, 'condition': 'unverified' if row[0] in ('speaking', 'unit_exchange') else 'assisted' if support else 'unaided_in_app',
                           'support': support,
                           '_findings': [(criteria[j['criterion_id']]['requirement_id'], j['outcome']) for j in judgements],
                           'reference': {'activity': row[0], 'task_key': row[1], 'source_key': row[4]},
                           'url': _url(conn, row[0], row[1]), 'feedback': [j['feedback'] for j in judgements]}
            # Per-question reports belong to a single exercised task. Showing
            # only its last question would hide earlier errors in that task.
            group_id = (row[1].split(':', 1)[0] if row[0] == 'curriculum_unit' else
                        row[1].rsplit(':', 1)[0] if row[0] == 'comprehension' else row[4])
            group_key = (domain, scope, group_id)
            previous = submissions.get(group_key)
            if previous:
                rank = {'demonstrated_in_task': 0, 'more_evidence_needed': 1, 'practise_and_retry': 2}
                latest, earlier = ((observation, previous) if _order(observation) > _order(previous)
                                   else (previous, observation))
                latest['outcome'] = max((latest['outcome'], earlier['outcome']), key=rank.get)
                latest['feedback'] = list(dict.fromkeys([*earlier['feedback'], *latest['feedback']]))
                latest['support'] = list(dict.fromkeys([*earlier['support'], *latest['support']]))
                latest['_findings'] = list(dict.fromkeys([*earlier['_findings'], *latest['_findings']]))
                if latest['condition'] != 'unverified' and latest['support']:
                    latest['condition'] = 'assisted'
                submissions[group_key] = latest
            else:
                submissions[group_key] = observation
    for (domain, scope, _), observation in submissions.items():
        previous = grouped[domain].get(scope)
        if previous is None or _order(observation) > _order(previous):
            grouped[domain][scope] = observation
    pilot_pending = _pilot_scopes(conn, profile_id, level, grouped)
    actions = _unit_actions(conn, profile_id, level)
    result = []
    for domain, en, ru in DOMAINS:
        scopes = sorted(grouped[domain].values(), key=_order, reverse=True)
        latest = scopes[0] if scopes else None
        result.append({'id': domain, 'label': en, 'label_ru': ru, 'latest': latest,
                       'scopes': scopes, 'pending': None,
                       'next_action': actions.get(domain) or {'kind': 'open_feedback' if latest else 'choose_task',
                                                            'url': latest['url'] if latest else '/curriculum/levels/' + level}})
    # Pending review is displayed alongside, never in place of, prior evidence.
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='activity_review_submissions'").fetchone()
    if exists:
        from services.activity_review_submissions import pending_summary
        for pending in [*pilot_pending, *pending_summary(conn, profile_id, level)]:
            for domain in pending['domains']:
                item = next((v for v in result if v['id'] == domain), None)
                if item and (item['pending'] is None or pending['submitted_at'] > item['pending']['submitted_at']):
                    item['pending'] = pending
    for item in result:
        action, pending = item['next_action'], item['pending']
        if pending and action['kind'] != 'resume':
            item['next_action'] = {'kind': 'retry_review' if pending['state'] == 'review_unavailable' else 'open_saved_reply',
                                   'url': pending['url']}
        elif action['kind'] not in ('resume', 'retry_review', 'open_saved_reply', 'unavailable'):
            follow_up = _review_action(conn, profile_id, item['latest'])
            if follow_up and (not action.get('run_id') or action['run_id'] == follow_up['run_id']):
                item['next_action'] = follow_up
        for scope in item['scopes']:
            scope.pop('_findings', None)
    return {'profile_id': profile_id, 'level': level, 'domains': result}


def summary(db_path, credential, level='A1'):
    from repositories.learning_repository import LearningError
    if level not in ('A1', 'A2', 'B1', 'B2'):
        raise LearningError('invalid_input', 'Choose a supported curriculum level.')
    with transaction(db_path) as conn:
        profile = require_access(conn, credential, timestamp())
        return projection(conn, profile['id'], level)
