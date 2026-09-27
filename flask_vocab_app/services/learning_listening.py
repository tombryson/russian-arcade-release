"""Owned playback/support receipts; never a claim that a person paid attention."""
import hashlib
import json
from pathlib import Path

from repositories.learning_repository import LearningError

STATIC_ROOT = Path(__file__).resolve().parents[1] / 'static'


def verify_audio(item):
    from contracts.learning import validate_pack
    validate_pack({'schema_version': 1, 'id': 'audio-check', 'kind': 'activity',
                   'title': 'Audio check', 'source': 'Bundled audio', 'items': [item]})
    path = STATIC_ROOT / item['audio']['url'].removeprefix('/static/')
    if (not path.is_file() or not path.resolve().is_relative_to(STATIC_ROOT.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != item['audio']['sha256']):
        raise LearningError('audio_unavailable', 'This recording is unavailable. Try again or read the transcript.', 409)


def item_support(conn, session_id, item):
    row = conn.execute('SELECT audio_sha256,listened_at,transcript_at,hint_at FROM learning_item_support '
                       'WHERE session_id=? AND item_id=?', (session_id, item['id'])).fetchone()
    if row is None:
        return {'listened': False, 'support': []}
    if item['type'] != 'listening_choice' or row[0] != item['audio']['sha256']:
        raise ValueError('Listening receipt does not match its saved recording.')
    return {'listened': row[1] is not None,
            'support': (['hint'] if row[3] is not None else []) + (['transcript'] if row[2] is not None else [])}


def record_support(conn, session_id, item, operation, now):
    if item['type'] != 'listening_choice':
        raise LearningError('invalid_input', 'This question has no recording or transcript.')
    if operation == 'listened':
        verify_audio(item)
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
