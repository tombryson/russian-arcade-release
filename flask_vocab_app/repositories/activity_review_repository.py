"""Immutable originals and short review leases, independent of provider calls."""
import json
import re

from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, timestamp

LEASE_SECONDS = 180
TRANSFER_POLICY = 'unit-transfer-no-effects-v1'
DEFAULT_POLICY = 'existing-activity-effects-v1'


def decode(row):
    item = dict(row)
    for key in ('original', 'task', 'contract', 'support', 'support_receipts', 'attempt_ref', 'result'):
        value = item.pop(key + '_json')
        item[key] = json.loads(value) if value is not None else None
    return item


def get(conn, profile_id, identity):
    row = conn.execute('SELECT * FROM activity_review_submissions WHERE id=? AND profile_id=?',
                       (identity, profile_id)).fetchone()
    if row is None:
        raise LearningError('not_found', 'This saved reply is not available for the selected profile.', 404)
    return decode(row)


def request_hash(activity, task_key, revision, response):
    return payload_hash({'activity': activity, 'task_key': str(task_key), 'revision': revision, 'response': response})


def existing(conn, profile_id, submission_id, digest):
    row = conn.execute('SELECT * FROM activity_review_submissions WHERE profile_id=? AND submission_id=?',
                       (profile_id, submission_id)).fetchone()
    if row is None:
        return None
    if row['request_sha256'] != digest:
        raise LearningError('submission_conflict', 'This submission identity belongs to another reply.', 409)
    return decode(row)


def save_original(conn, *, profile_id, activity, task_key, submission_id, task_revision,
                  original, task, contract, support, support_receipts, effects_policy):
    if (activity not in ('writing', 'comprehension', 'unit_exchange')
            or not isinstance(submission_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', submission_id)
            or type(task_revision) is not int or task_revision < 0
            or effects_policy not in (DEFAULT_POLICY, TRANSFER_POLICY)):
        raise LearningError('invalid_input', 'This saved reply needs a valid identity and revision.')
    digest = request_hash(activity, task_key, task_revision, original)
    cached = existing(conn, profile_id, submission_id, digest)
    if cached:
        return cached
    pending = conn.execute("SELECT id FROM activity_review_submissions WHERE profile_id=? AND activity=? "
                           "AND task_key=? AND review_status!='reviewed' ORDER BY rowid DESC LIMIT 1",
                           (profile_id, activity, str(task_key))).fetchone()
    if pending:
        raise LearningError('review_pending', 'Your reply is already saved. Retry feedback on that reply before submitting another.',
                            409, {'submission_id': pending['id']})
    previous = conn.execute('SELECT id FROM activity_review_submissions WHERE profile_id=? AND activity=? AND task_key=? AND task_revision=?',
                            (profile_id, activity, str(task_key), task_revision)).fetchone()
    if previous:
        raise LearningError('already_submitted', 'This response revision is already saved. Open its feedback to retry review.', 409,
                            {'submission_id': previous['id']})
    identity, now = identifier(), timestamp()
    conn.execute('''INSERT INTO activity_review_submissions
        (id,profile_id,activity,task_key,submission_id,request_sha256,task_revision,original_json,task_json,
         contract_json,support_json,support_receipts_json,effects_policy,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (identity, profile_id, activity, str(task_key), submission_id, digest, task_revision, encoded(original),
         encoded(task), encoded(contract), encoded(support), encoded(support_receipts), effects_policy, now, now))
    return get(conn, profile_id, identity)


def claim(conn, profile_id, identity):
    saved = get(conn, profile_id, identity)
    if saved['review_status'] == 'reviewed':
        return saved, None
    now = timestamp()
    if saved['review_status'] == 'reviewing' and now - saved['review_started_at'] < LEASE_SECONDS:
        raise LearningError('review_busy', 'Your reply is saved and feedback is being prepared.', 409)
    token = identifier()
    conn.execute("UPDATE activity_review_submissions SET review_status='reviewing',review_token=?,review_started_at=?,review_error=NULL,updated_at=? WHERE id=?",
                 (token, now, now, identity))
    return get(conn, profile_id, identity), token


def assert_lease(conn, profile_id, identity, token):
    saved = get(conn, profile_id, identity)
    if saved['review_status'] != 'reviewing' or not token or saved['review_token'] != token:
        raise LearningError('stale_review', 'This feedback request has changed. Reload the saved reply.', 409)
    # The original hash is checked again before any activity attempt or effect.
    if saved['request_sha256'] != request_hash(saved['activity'], saved['task_key'], saved['task_revision'], saved['original']):
        raise LearningError('invalid_saved_response', 'The saved reply could not be verified.', 409)
    return saved


def finish(conn, profile_id, identity, token, attempt_ref, result):
    assert_lease(conn, profile_id, identity, token)
    conn.execute("UPDATE activity_review_submissions SET review_status='reviewed',attempt_ref_json=?,result_json=?,review_token=NULL,review_error=NULL,updated_at=? WHERE id=?",
                 (encoded(attempt_ref), encoded(result), timestamp(), identity))
    return get(conn, profile_id, identity)


def fail(conn, profile_id, identity, token, code='provider_unavailable'):
    conn.execute("UPDATE activity_review_submissions SET review_status='review_unavailable',review_token=NULL,review_error=?,updated_at=? WHERE id=? AND profile_id=? AND review_status='reviewing' AND review_token=?",
                 (code, timestamp(), identity, profile_id, token))


def public(saved):
    result = saved.get('result') or {}
    return {key: saved[key] for key in ('id', 'activity', 'task_key', 'task_revision', 'original', 'attempt_ref', 'created_at', 'updated_at')} | {
        'work_state': saved['review_status'], 'outcome': result.get('outcome'),
        'availability': saved.get('review_error') or 'available',
        'condition': 'unverified' if saved['activity'] == 'unit_exchange' else 'assisted' if saved['support'] else 'unaided_in_app',
        'feedback': result or None, 'support': saved['support'],
        'message': 'Your reply is saved. Feedback is unavailable.' if saved['review_status'] == 'review_unavailable' else 'Your reply is saved.'}
