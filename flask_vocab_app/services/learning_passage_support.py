"""Optional saved passage support, disclosed only after an owned receipt.

Use the existing command journal and assistance records. A passage hash scopes
the disclosure across its questions; opening support never changes past answers.
"""
from hashlib import sha256
import json

from contracts.learning import fields, key, revision
from repositories.learning_repository import LearningError, encoded, payload_hash, transaction
from services.learning_listening import capture_shared_support, current_item_support, record_support


def _passage_hash(item):
    return sha256((item.get('passage') or item.get('transcript') or '').encode('utf-8')).hexdigest()


def disclosed(conn, session_id, item):
    """The journal retains a disclosure without exposing help in old packs."""
    return conn.execute(
        "SELECT 1 FROM learning_commands WHERE session_id=? "
        "AND json_extract(result,'$.passage_help_receipt.passage_sha256')=? LIMIT 1",
        (session_id, _passage_hash(item))).fetchone() is not None


def child_support(conn, session_id, item, *, transcript_used=False):
    if not item.get('passage_support') or (item['type'] == 'listening_choice' and not transcript_used):
        return {}
    return {'has_passage_support': True,
            **({'passage_support': item['passage_support']} if disclosed(conn, session_id, item) else {})}


def command(learning, access_id, session_id, data):
    fields(data, {'submission_id', 'expected_revision', 'item_id'})
    key(data['submission_id']); key(data['item_id']); revision(data['expected_revision'])
    digest = payload_hash({'operation': 'passage_help', **data})
    with transaction(learning.db_path, write=True) as conn:
        _, saved, _, pack = learning._owned_session(conn, access_id, session_id)
        cached = conn.execute('SELECT payload_hash,result FROM learning_commands WHERE session_id=? AND submission_id=?',
                              (session_id, data['submission_id'])).fetchone()
        if cached:
            if cached[0] != digest:
                raise LearningError('idempotency_conflict', 'This request ID was used for another action.', 409)
            return json.loads(cached[1])
        if saved['revision'] != data['expected_revision']:
            raise LearningError('stale_revision', 'The activity changed. Reopen the current question.', 409,
                                {'current_session': learning._snapshot(conn, session_id, pack)})
        if saved['status'] != 'active' or pack['items'][saved['current_index']]['id'] != data['item_id']:
            raise LearningError('wrong_item', 'Open help for the current question.', 409)
        item = pack['items'][saved['current_index']]
        if not item.get('passage_support'):
            raise LearningError('not_found', 'This passage has no saved word support.', 404)
        if item['type'] == 'listening_choice' and 'transcript' not in current_item_support(
                conn, session_id, item, pack, saved['current_index'])['support']:
            raise LearningError('transcript_required', 'Open the transcript before using word support.', 409)
        now = learning.clock()
        capture_shared_support(conn, session_id, pack, now)
        if item['type'] == 'listening_choice':
            # The transcript receipt already covers remaining questions about
            # this recording. Record this additional help on the current one.
            record_support(conn, session_id, item, 'help', now)
        else:
            for pending in pack['items'][saved['current_index']:]:
                if pending.get('passage') == item['passage']:
                    conn.execute('INSERT OR IGNORE INTO learning_hint_usage VALUES (?,?)', (session_id, pending['id']))
        receipt = {'passage_help_receipt': {'passage_sha256': _passage_hash(item)}}
        # Write the receipt before projecting the snapshot, in the same
        # transaction. Reload and a retried request see the same disclosure.
        conn.execute('INSERT INTO learning_commands VALUES (?,?,?,?,?)',
                     (session_id, data['submission_id'], digest, encoded(receipt), now))
        conn.execute('UPDATE learning_sessions SET revision=revision+1,updated_at=? WHERE id=?', (now, session_id))
        result = {**learning._snapshot(conn, session_id, pack), **receipt}
        conn.execute('UPDATE learning_commands SET result=? WHERE session_id=? AND submission_id=?',
                     (encoded(result), session_id, data['submission_id']))
        return result
