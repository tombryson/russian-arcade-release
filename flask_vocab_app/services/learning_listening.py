"""Owned playback/support receipts; never a claim that a person paid attention."""
import hashlib
import json
from pathlib import Path

from repositories.learning_repository import LearningError

STATIC_ROOT = Path(__file__).resolve().parents[1] / 'static'


def verify_audio(item, *, media_root=None):
    from contracts.learning import validate_pack
    validate_pack({'schema_version': 1, 'id': 'audio-check', 'kind': 'activity',
                   'title': 'Audio check', 'source': 'Bundled audio', 'items': [item]})
    if item['audio'].get('kind') == 'generated':
        from flask import current_app, has_app_context
        from services.curriculum_generated_audio import verify_generated_audio
        if media_root is None and has_app_context():
            media_root = current_app.config['APP_MEDIA_DIR']
        return verify_generated_audio(item['audio'], item['transcript'], media_root)
    path = STATIC_ROOT / item['audio']['url'].removeprefix('/static/')
    if (not path.is_file() or not path.resolve().is_relative_to(STATIC_ROOT.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != item['audio']['sha256']):
        raise LearningError('audio_unavailable', 'This recording is unavailable. Try again or read the transcript.', 409)
    return path


def item_support(conn, session_id, item):
    row = conn.execute('SELECT audio_sha256,listened_at,transcript_at,hint_at FROM learning_item_support '
                       'WHERE session_id=? AND item_id=?', (session_id, item['id'])).fetchone()
    if row is None:
        return {'listened': False, 'support': []}
    if item['type'] != 'listening_choice' or row[0] != item['audio']['sha256']:
        raise ValueError('Listening receipt does not match its saved recording.')
    return {'listened': row[1] is not None,
            'support': (['hint'] if row[3] is not None else []) + (['transcript'] if row[2] is not None else [])}


def same_recording(left, right):
    return (left.get('type') == right.get('type') == 'listening_choice'
            and left.get('audio', {}).get('sha256') == right.get('audio', {}).get('sha256')
            and left.get('transcript') == right.get('transcript'))


def feedback_is_deferred(pack, current_index, item):
    """One message may answer several questions; hold its key until all are done."""
    return any(same_recording(item, pending) for pending in pack['items'][current_index:])


def recording_transcript_disclosed(conn, session_id, item, items):
    return any(same_recording(item, other) and 'transcript' in item_support(conn, session_id, other)['support']
               for other in items)


def current_item_support(conn, session_id, item, pack=None, current_index=None):
    """Project this session's earlier playback and disclosed transcript."""
    result = item_support(conn, session_id, item)
    if pack is None or current_index is None:
        row = conn.execute('SELECT v.payload,s.current_index FROM learning_sessions s '
                           'JOIN learning_content_versions v ON v.id=s.version_id WHERE s.id=?', (session_id,)).fetchone()
        if row is None:
            return result
        pack, current_index = json.loads(row[0]), row[1]
    # Completed items must retain the help recorded when their answer was saved.
    if current_index >= len(pack['items']) or pack['items'][current_index]['id'] != item['id']:
        return result
    prior_items = pack['items'][:current_index]
    # One completed playback covers every question about that exact message.
    # Reusing a recording in another run does not carry its playback receipt.
    if not result['listened'] and any(
            same_recording(item, previous) and item_support(conn, session_id, previous)['listened']
            for previous in prior_items):
        result = {**result, 'listened': True}
    if 'transcript' in result['support']:
        return result
    if recording_transcript_disclosed(conn, session_id, item, prior_items):
        return {**result, 'support': [*result['support'], 'transcript']}
    # Another tab can expose the whole recording before saving any answer.
    # Match the same owner's frozen version, not just a reused media URL.
    disclosed = conn.execute('SELECT r.item_id FROM learning_item_support r '
        'JOIN learning_sessions other ON other.id=r.session_id '
        'JOIN learning_sessions current ON current.id=? AND current.profile_id=other.profile_id '
        'AND current.version_id=other.version_id '
        'WHERE other.id<>current.id AND r.transcript_at IS NOT NULL AND r.audio_sha256=?',
        (session_id, item['audio']['sha256'])).fetchall()
    by_id = {entry['id']: entry for entry in pack['items']}
    if any(row[0] in by_id and same_recording(item, by_id[row[0]]) for row in disclosed):
        return {**result, 'support': [*result['support'], 'transcript']}
    return result


def capture_shared_support(conn, session_id, pack, now):
    """Freeze shared playback/help for the current question, never past answers."""
    index = conn.execute('SELECT current_index FROM learning_sessions WHERE id=?', (session_id,)).fetchone()[0]
    if index >= len(pack['items']):
        return
    item = pack['items'][index]
    if item['type'] != 'listening_choice':
        return
    support = current_item_support(conn, session_id, item, pack, index)
    if support['listened'] and not item_support(conn, session_id, item)['listened']:
        # The earlier receipt already verified these exact bytes and transcript.
        # This records inherited playback, not another file request or assistance.
        conn.execute('INSERT OR IGNORE INTO learning_item_support(session_id,item_id,audio_sha256) VALUES (?,?,?)',
                     (session_id, item['id'], item['audio']['sha256']))
        conn.execute('UPDATE learning_item_support SET listened_at=COALESCE(listened_at,?) WHERE session_id=? AND item_id=?',
                     (now, session_id, item['id']))
    if 'transcript' in support['support']:
        record_support(conn, session_id, item, 'transcript', now)


def record_support(conn, session_id, item, operation, now, *, media_root=None):
    if item['type'] != 'listening_choice':
        raise LearningError('invalid_input', 'This question has no recording or transcript.')
    if operation == 'listened':
        verify_audio(item, media_root=media_root)
    item_support(conn, session_id, item)
    # Only the current item can reach this function through LearningService.
    # After its answer is saved these timestamps cannot change via the API.
    column = {'listened': 'listened_at', 'transcript': 'transcript_at', 'help': 'hint_at'}[operation]
    conn.execute('INSERT OR IGNORE INTO learning_item_support(session_id,item_id,audio_sha256) VALUES (?,?,?)',
                 (session_id, item['id'], item['audio']['sha256']))
    conn.execute(f'UPDATE learning_item_support SET {column}=COALESCE({column},?) WHERE session_id=? AND item_id=?',
                 (now, session_id, item['id']))


def validate_saved_support(conn):
    """Check offline import receipts even when no answer/report was saved yet."""
    for row in conn.execute('SELECT r.session_id,r.item_id,v.payload,s.current_index,s.created_at,s.updated_at,'
                            'r.listened_at,r.transcript_at,r.hint_at FROM learning_item_support r '
                            'LEFT JOIN learning_sessions s ON s.id=r.session_id '
                            'LEFT JOIN learning_content_versions v ON v.id=s.version_id').fetchall():
        if row[2] is None:
            raise ValueError('Listening receipt has no saved session content.')
        items = json.loads(row[2])['items']
        matches = [item for item in items if item['id'] == row[1]]
        if len(matches) != 1:
            raise ValueError('Listening receipt references an unknown saved question.')
        item_support(conn, row[0], matches[0])
        index = items.index(matches[0])
        times = [value for value in row[6:] if value is not None]
        if (index > row[3] or not times
                or any(type(value) is not int or value < row[4] or value > row[5] for value in times)):
            raise ValueError('Listening receipt is outside its saved item timeline.')
        if index < row[3]:
            attempts = conn.execute('SELECT created_at FROM activity_attempts WHERE session_id=? AND item_id=?',
                                    (row[0], row[1])).fetchall()
            if len(attempts) != 1 or any(value > attempts[0][0] for value in times):
                raise ValueError('Listening support cannot be added after its saved answer.')
