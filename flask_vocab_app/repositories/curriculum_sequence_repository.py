"""Small, owned lesson envelopes and strict mutation receipts."""
import json

from contracts.learning import key, revision
from repositories.learning_repository import LearningError, encoded, payload_hash, timestamp


def owned_run(conn, profile_id, run_id):
    key(run_id)
    row = conn.execute('SELECT * FROM curriculum_unit_runs WHERE id=? AND profile_id=?',
                       (run_id, profile_id)).fetchone()
    if row is None:
        raise LearningError('not_found', 'This lesson is not available for the selected learner.', 404)
    result = dict(row)
    result['manifest'] = json.loads(result.pop('manifest_json'))
    if payload_hash(result['manifest']) != result['manifest_sha256']:
        raise LearningError('content_unavailable', 'This saved lesson needs to be restored.', 409)
    return result


def check_revision(run, expected):
    revision(expected)
    if run['revision'] != expected:
        raise LearningError('stale_revision', 'This lesson changed in another tab. Reload it to continue.', 409)


def receipt(conn, profile_id, request_id, operation, payload):
    key(request_id, 'Submission ID')
    digest = payload_hash({'operation': operation, 'payload': payload})
    row = conn.execute('SELECT request_sha256,response_json FROM curriculum_unit_requests WHERE profile_id=? AND request_id=?',
                       (profile_id, request_id)).fetchone()
    if row:
        if row[0] != digest:
            raise LearningError('idempotency_conflict', 'This request identifier was used for different work.', 409)
        return digest, json.loads(row[1])
    return digest, None


def save_receipt(conn, profile_id, request_id, operation, digest, result):
    conn.execute('INSERT INTO curriculum_unit_requests VALUES (?,?,?,?,?,?)',
                 (profile_id, request_id, operation, digest, encoded(result), timestamp()))


def binding_for_task(conn, profile_id, activity, task_key):
    row = conn.execute('SELECT * FROM curriculum_unit_bindings WHERE profile_id=? AND activity=? AND task_key=?',
                       (profile_id, activity, str(task_key))).fetchone()
    return dict(row) if row else None


def validate_saved_sequences(conn):
    """Called by import validation; compare saved content without upgrading it."""
    from services.curriculum_generation import decode
    for row in conn.execute('SELECT r.profile_id,r.request_sha256,s.profile_id AS session_owner,v.payload '
                            'FROM curriculum_generated_starts r JOIN learning_sessions s ON s.id=r.session_id '
                            'JOIN learning_content_versions v ON v.id=s.version_id'):
        identity = decode(json.loads(row['payload']))
        if (identity is None or row['profile_id'] != row['session_owner']
                or row['request_sha256'] != payload_hash({'unit_id': identity[0], 'stage': identity[2]})):
            raise ValueError('Generated practice receipts must refer to the original owned unit and response mode.')
    for row in conn.execute('SELECT id,profile_id FROM curriculum_unit_runs').fetchall():
        run = owned_run(conn, row[1], row[0])
        manifest = run['manifest']
        steps = {step['id'] for step in manifest['steps']}
        if (run['completion_path'] not in manifest['completion_paths']
                or run['last_step_id'] is not None and run['last_step_id'] not in steps
                or any(not set(path) <= steps for path in manifest['completion_paths'].values())):
            raise ValueError('Saved lesson navigation does not match its frozen manifest.')
        for binding in conn.execute('SELECT step_id,effects_policy FROM curriculum_unit_bindings WHERE run_id=?', (run['id'],)):
            if binding[0].split('/')[0] not in steps:
                raise ValueError('Saved activity is not part of its lesson.')
            step = next(s for s in manifest['steps'] if s['id'] == binding[0].split('/')[0])
            if binding[1] != step['effects_policy']:
                raise ValueError('Saved activity effects must match the frozen lesson policy.')
    for row in conn.execute('SELECT d.*,t.profile_id AS task_owner,t.revision AS current_revision,t.payload_json '
                            'FROM comprehension_task_drafts d JOIN comprehension_tasks t ON t.id=d.task_id'):
        answers = json.loads(row['answers_json'])
        payload = json.loads(row['payload_json'])
        if (row['profile_id'] != row['task_owner'] or row['task_revision'] > row['current_revision']
                or not binding_for_task(conn, row['profile_id'], 'comprehension', row['task_id'])
                or not isinstance(answers, list) or len(answers) != len(payload['questions'])
                or any(not isinstance(answer, str) or len(answer) > 4000 or '\x00' in answer for answer in answers)):
            raise ValueError('Saved reading draft does not match its owned task.')
    for row in conn.execute('SELECT d.item_id,d.response_json,v.payload FROM learning_session_drafts d '
                            'JOIN learning_sessions s ON s.id=d.session_id '
                            'JOIN learning_content_versions v ON v.id=s.version_id'):
        items = {i['id']: i for i in json.loads(row[2])['items']}
        response = json.loads(row[1])
        if (row[0] not in items or items[row[0]]['type'] != 'controlled_text'
                or set(response) != {'text'} or not isinstance(response['text'], str)
                or len(response['text']) > 200 or '\x00' in response['text']):
            raise ValueError('Saved lesson draft does not match its task.')
    for row in conn.execute('SELECT p.session_id,p.item_id,s.profile_id,s.version_id,a.session_id AS source_session,'
                            'a.item_id AS source_item,old.profile_id AS source_profile,old.version_id AS source_version '
                            'FROM learning_prior_feedback p JOIN learning_sessions s ON s.id=p.session_id '
                            'JOIN activity_attempts a ON a.id=p.source_attempt_id JOIN learning_sessions old ON old.id=a.session_id'):
        same_version = row['version_id'] == row['source_version']
        if not same_version:
            from services.curriculum_fresh_practice import same_question
            packs = [json.loads(conn.execute('SELECT payload FROM learning_content_versions WHERE id=?', (v,)).fetchone()[0])
                     for v in (row['version_id'], row['source_version'])]
            same_version = same_question(*packs, row['item_id'])
        if (row['session_id'] == row['source_session'] or row['item_id'] != row['source_item']
                or row['profile_id'] != row['source_profile'] or not same_version):
            raise ValueError('Prior feedback must refer to the same owned, frozen question in an earlier attempt.')
    for row in conn.execute('SELECT h.item_id,v.payload FROM learning_hint_usage h JOIN learning_sessions s ON s.id=h.session_id '
                            'JOIN learning_content_versions v ON v.id=s.version_id'):
        item = next((item for item in json.loads(row[1])['items'] if item['id'] == row[0]), None)
        if item is None or not item.get('hint'):
            raise ValueError('Saved help must belong to an issued question with a hint.')
