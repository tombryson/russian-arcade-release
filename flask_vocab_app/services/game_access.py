"""Permanent game ownership and purchases from the shared Lingocoin wallet.

The caller supplies a write transaction for purchases. Wallet debit, ownership
and the idempotency receipt are committed together; catalogue reads never grant
access. Historical milestones are retained only by migration 038.
"""
import json
import sqlite3

from contracts.learning import key
from repositories.learning_repository import LearningError, encoded, identifier, timestamp

POLICY = 'game-shop-v1'
FIRST_GAME_PRICE = 25
GAME_PRICE = 50
# Stable display order, independent of price or progress.
GAME_IDS = ('pack-bag', 'scene-builder', 'missing-stamp', 'mailbox-sort',
            'directions', 'radio', 'letter-back', 'detective')
LEGACY_THRESHOLDS = {
    'pack-bag': 12, 'scene-builder': 24, 'pairs': 24, 'missing-stamp': 36,
    'mailbox-sort': 48, 'directions': 60, 'radio': 72, 'letter-back': 84, 'detective': 96,
}
CORE_ACTIVITIES = ('reading', 'writing', 'translation', 'word_jumble', 'lessons', 'speaking', 'flashcards')


def wallet_balance(conn, profile_id):
    if not profile_id:
        return None
    return conn.execute('SELECT COALESCE(SUM(amount),0) FROM progression_entries WHERE profile_id=?',
                        (profile_id,)).fetchone()[0]


def shop_state(conn, profile_id, *, enabled=True):
    paid = profile_id and conn.execute(
        'SELECT 1 FROM journey_game_purchases WHERE profile_id=? AND charged>0 LIMIT 1',
        (profile_id,)).fetchone()
    return {'balance': wallet_balance(conn, profile_id), 'first_purchase': not bool(paid),
            'price': GAME_PRICE if paid else FIRST_GAME_PRICE, 'enabled': bool(enabled)}


def access_state(conn, profile_id, guest=None, *, enabled=True):
    shop = shop_state(conn, profile_id, enabled=enabled)
    grants = {row['game_id']: row for row in conn.execute(
        'SELECT * FROM journey_game_access WHERE profile_id=?', (profile_id,))} if profile_id else {}
    return {game: {
        'unlocked': game in grants,
        'new': bool(game in grants and grants[game]['first_started_at'] is None),
        'purchase': {'price': shop['price'], 'owned': game in grants,
                     'can_purchase': bool(enabled and profile_id and game not in grants
                                          and shop['balance'] >= shop['price'])},
    } for game in (*GAME_IDS, 'pairs')}


def require_access(conn, profile_id, game_id, *, now=None):
    if not profile_id or not conn.execute(
            'SELECT 1 FROM journey_game_access WHERE profile_id=? AND game_id=?',
            (profile_id, game_id)).fetchone():
        raise LearningError('game_locked', 'Unlock this game in the shop to play.', 409)


def purchase(conn, profile_id, game_id, request_id, expected_price, *, now=None):
    """Purchase within BEGIN IMMEDIATE, including read/check/write and retry receipt."""
    key(request_id, 'Purchase request')
    if type(expected_price) is not int or expected_price < 0:
        raise LearningError('invalid_price', 'Choose a game at its displayed price.')
    if game_id not in GAME_IDS:
        raise LearningError('not_found', 'This game was not found.', 404)
    if not profile_id or not conn.execute(
            'SELECT 1 FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL',
            (profile_id,)).fetchone():
        raise LearningError('profile_required', 'Choose a profile before unlocking a game.', 401)
    previous = conn.execute('SELECT * FROM journey_game_purchases WHERE profile_id=? AND request_id=?',
                            (profile_id, request_id)).fetchone()
    if previous:
        if previous['game_id'] != game_id or previous['expected_price'] != expected_price:
            raise LearningError('idempotency_conflict', 'This purchase request was already used for a different choice.', 409)
        return json.loads(previous['result_json'])
    owned = bool(conn.execute('SELECT 1 FROM journey_game_access WHERE profile_id=? AND game_id=?',
                              (profile_id, game_id)).fetchone())
    shop = shop_state(conn, profile_id)
    charged, entry_id = 0, None
    now = timestamp() if now is None else now
    if not owned:
        if expected_price != shop['price']:
            raise LearningError('price_changed', 'The price has changed. Check the new price before unlocking this game.',
                                409, {'price': shop['price'], 'balance': shop['balance']})
        if shop['balance'] < shop['price']:
            raise LearningError('insufficient_coins', 'Earn a few more Lingocoins to unlock this game.',
                                409, {'price': shop['price'], 'balance': shop['balance']})
        from services.progression import study_day
        charged, entry_id = shop['price'], identifier()
        conn.execute('INSERT INTO progression_entries VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                     (entry_id, profile_id, None, 'game-purchase:' + request_id, -charged,
                      0, 'purchase', study_day(conn, profile_id, now), 'Game unlock: ' + game_id, POLICY, now))
        conn.execute('INSERT INTO journey_game_access(profile_id,game_id,unlocked_at,policy_version) VALUES (?,?,?,?)',
                     (profile_id, game_id, now, POLICY))
    result = {'game_id': game_id, 'charged': charged, 'balance': shop['balance'] - charged,
              'owned': True, 'already_owned': owned}
    conn.execute('INSERT INTO journey_game_purchases '
                 '(profile_id,request_id,game_id,expected_price,charged,entry_id,result_json,created_at) '
                 'VALUES (?,?,?,?,?,?,?,?)',
                 (profile_id, request_id, game_id, expected_price, charged, entry_id, encoded(result), now))
    return result


def mark_started(conn, profile_id, game_id, now):
    if profile_id:
        conn.execute('UPDATE journey_game_access SET first_started_at=COALESCE(first_started_at,?) '
                     'WHERE profile_id=? AND game_id=?', (now, profile_id, game_id))


def preserve_played_access(conn, profile_id=None):
    """Preserve real saved games during migration or an existing guest's transfer.

    Tutorial unlock snapshots alone and public demo samples do not grant rights.
    Already acquired rights are left intact, including their first-start record.
    """
    clause, args = (' AND profile_id=?', (profile_id,)) if profile_id else ('', ())
    conn.execute('INSERT OR IGNORE INTO journey_game_access '
                 '(profile_id,game_id,unlocked_at,first_started_at,policy_version) '
                 "SELECT profile_id,game_id,MIN(created_at),MIN(created_at),'grandfathered-play-v1' "
                 'FROM journey_game_sessions WHERE profile_id IS NOT NULL '
                 "AND COALESCE(json_extract(content_json,'$.sample'),0)=0" + clause +
                 ' GROUP BY profile_id,game_id', args)


def backfill_access(conn):
    """Frozen migration 038 policy; never called by current reward or read paths."""
    previous = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ','.join('?' for _ in CORE_ACTIVITIES)
        for profile_id, in conn.execute('SELECT id FROM learning_profiles').fetchall():
            earned = conn.execute(
                'SELECT COALESCE(SUM(e.amount),0) FROM progression_entries e '
                'JOIN progression_events v ON v.id=e.event_id AND v.profile_id=e.profile_id '
                f'WHERE e.profile_id=? AND e.eligible=1 AND v.activity IN ({placeholders})',
                (profile_id, *CORE_ACTIVITIES)).fetchone()[0]
            for game, required in LEGACY_THRESHOLDS.items():
                if earned >= required:
                    conn.execute('INSERT OR IGNORE INTO journey_game_access '
                                 '(profile_id,game_id,required_coins,earned_coins,unlocked_at,policy_version) '
                                 'VALUES (?,?,?,?,?,?)', (profile_id, game, required, earned, timestamp(), 'practice-coins-v1'))
        conn.execute('UPDATE journey_game_access SET first_started_at=('
                     'SELECT MIN(s.created_at) FROM journey_game_sessions s '
                     'WHERE s.profile_id=journey_game_access.profile_id '
                     'AND s.game_id=journey_game_access.game_id)')
    finally:
        conn.row_factory = previous
