"""Owned, resumable delivery preparation. Network work never holds a DB lock."""
import json

from flask import current_app

from repositories.learning_repository import LearningError, encoded, identifier, timestamp, transaction

LEASE_SECONDS = 180
MAX_ATTEMPTS = 100
FAILURE_MESSAGE = 'Preparation paused. Your town and delivery are saved. Retry to continue.'
UNCERTAIN_MESSAGE = 'The last preparation request did not finish saving. Retry to continue; its provider request may already have completed.'


def status(conn, row):
    record = conn.execute('SELECT * FROM journey_route_preparations WHERE session_id=?', (row['id'],)).fetchone()
    if not record:
        return None
    pack = json.loads(row['content_json'])
    progress = current_app.extensions['learning']['route_preparation'].status(pack)
    if record['status'] == 'ready':
        if progress['stage'] == 'ready':
            return None
        return {**progress, 'status': 'failed',
                'error': 'Some recordings are unavailable. Retry to restore them and keep this delivery.'}
    expired = record['status'] == 'running' and record['lease_until'] <= timestamp()
    return {**progress, 'status': 'failed' if expired else record['status'],
            'error': UNCERTAIN_MESSAGE if expired else record['error']}


def public(conn, row):
    progress = status(conn, row)
    if progress is None:
        return None
    pack = json.loads(row['content_json'])
    return {'profile_id': row['profile_id'], 'id': row['id'], 'game_id': 'directions',
            'title': 'A delivery for Barsik', 'phase': 'preparing', 'round_index': 0,
            'total_rounds': len(pack['legs']), 'round': None, 'result': None,
            'source': pack['source'], 'reward': None, 'preparation': progress}


def advance(session_id, *, retry=False):
    from services.journey_games import authorize_preparation, _public
    if current_app.config.get('PUBLIC_DEMO'):
        raise LearningError('demo_unavailable', 'New deliveries can be prepared in a local installation.', 403)
    db = current_app.config['DB_PATH']
    helper = current_app.extensions['learning']['route_preparation']
    with transaction(db, write=True) as conn:
        row = authorize_preparation(conn, session_id)
        if row['superseded_at'] is not None:
            raise LearningError('delivery_finished', 'This delivery is no longer active.', 409)
        record = conn.execute('SELECT * FROM journey_route_preparations WHERE session_id=?', (session_id,)).fetchone()
        if not record or (record['status'] == 'ready' and helper.status(json.loads(row['content_json']))['stage'] == 'ready'):
            return _public(conn, row)
        now = timestamp()
        if record['status'] == 'running' and record['lease_until'] > now:
            return _public(conn, row)
        # An expired claim may have incurred a provider charge. Do not retry it
        # automatically just because a browser tab resumed polling.
        if not retry and record['status'] in ('running', 'failed', 'ready'):
            return _public(conn, row)
        if record['attempts'] >= MAX_ATTEMPTS:
            raise LearningError('preparation_limit', 'This delivery reached its preparation limit. Start a new delivery.', 429)
        claim = identifier()
        pack = json.loads(row['content_json'])
        conn.execute("UPDATE journey_route_preparations SET status='running',error=NULL,claim_id=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE session_id=?",
                     (claim, now + LEASE_SECONDS, now, session_id))
    try:
        prepared = helper.advance(pack)
        progress = helper.status(prepared)
        ready = progress['stage'] == 'ready'
        failed = progress.get('status') == 'failed'
    except Exception:
        # Provider exceptions can contain response bodies or credentials.
        # Keep those out of the UI and logs; frozen input remains retryable.
        with transaction(db, write=True) as conn:
            conn.execute("UPDATE journey_route_preparations SET status='failed',error=?,claim_id=NULL,lease_until=0,updated_at=? WHERE session_id=? AND claim_id=?",
                         (FAILURE_MESSAGE, timestamp(), session_id, claim))
            return _public(conn, authorize_preparation(conn, session_id))
    with transaction(db, write=True) as conn:
        row = authorize_preparation(conn, session_id)
        if row['superseded_at'] is not None:
            raise LearningError('delivery_finished', 'This delivery is no longer active.', 409)
        changed = conn.execute("UPDATE journey_route_preparations SET status=?,error=?,claim_id=NULL,lease_until=0,updated_at=? WHERE session_id=? AND claim_id=?",
                               ('failed' if failed else 'ready' if ready else 'pending', progress.get('error') if failed else None,
                                timestamp(), session_id, claim)).rowcount
        if not changed:
            raise LearningError('preparation_changed', 'Another request has taken over preparation. Reopen this delivery.', 409)
        conn.execute('UPDATE journey_game_sessions SET content_json=?,updated_at=? WHERE id=?',
                     (encoded(prepared), timestamp(), session_id))
        return _public(conn, authorize_preparation(conn, session_id))


def audio_url(session_id, asset_id):
    return f'/api/v1/games/sessions/{session_id}/assets/{asset_id}'


def project_audio(pack, session_id):
    """Called on a private copy before disclosure filtering, never on storage."""
    lines = [pack['ending']]
    for leg in pack['legs']:
        lines.extend([*leg['lines'], leg['clarify'], *(q['reply'] for q in leg.get('questions', []))])
    for line in lines:
        if line.get('asset_id'):
            line['audio_url'] = audio_url(session_id, line['asset_id'])
    return pack


def disclosed_asset_ids(public_state):
    """Only public dialogue can be fetched, even by the owner of a delivery."""
    result = set()
    def visit(value):
        if isinstance(value, dict):
            if value.get('asset_id') and value.get('audio_url'):
                result.add(value['asset_id'])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(public_state)
    return result
