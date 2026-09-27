"""Explicit introduction milestones, isolated by profile or guest browser."""
import sqlite3

from flask import current_app, has_request_context, session

from repositories.learning_repository import LearningError, timestamp, transaction
from utils.household_access import access_id

GUEST_ONBOARDING_KEY = 'guest_onboarding'
MILESTONES = {'coins': 'coins_introduced_at', 'progress': 'progress_introduced_at'}


def _guest_timestamps(value):
    value = value if isinstance(value, dict) else {}
    result = {field: value[field] for field in MILESTONES.values()
              if type(value.get(field)) is int and value[field] >= 0}
    if 'coins_introduced_at' not in result:
        result.pop('progress_introduced_at', None)
    return result


def _state(profile_id=None, saved=None):
    saved = saved or {}
    return {'profile_id': profile_id,
            'coins_introduced': saved.get('coins_introduced_at') is not None,
            'progress_introduced': saved.get('progress_introduced_at') is not None}


def _selected_profile(conn, credential, now):
    row = conn.execute(
        'SELECT p.id FROM household_access a JOIN learning_profiles p ON p.id=a.profile_id '
        'WHERE a.id=? AND a.expires_at>? AND p.archived=0 AND p.legacy_user_id IS NULL',
        (credential, now),
    ).fetchone()
    return row['id'] if row else None


def _profile_state(conn, profile_id):
    row = conn.execute('SELECT coins_introduced_at,progress_introduced_at FROM profile_onboarding WHERE profile_id=?',
                       (profile_id,)).fetchone()
    return _state(profile_id, dict(row) if row else None)


def onboarding_state():
    """Read current presentation state without creating rows or marking steps."""
    if not has_request_context():
        return _state()
    credential = access_id()
    if credential:
        with transaction(current_app.config['DB_PATH']) as conn:
            profile_id = _selected_profile(conn, credential, timestamp())
            if profile_id:
                try:
                    return _profile_state(conn, profile_id)
                except sqlite3.OperationalError as error:
                    # An un-upgraded preview must not expose later UI early.
                    if 'no such table: profile_onboarding' not in str(error):
                        raise
                    return _state(profile_id)
    return _state(saved=_guest_timestamps(session.get(GUEST_ONBOARDING_KEY)))


def _check_order(milestone, state):
    if milestone == 'progress' and not state['coins_introduced']:
        raise LearningError('coins_not_introduced', 'Introduce Lingo coins before showing progress.', 409)


def introduce_milestone(milestone):
    if not isinstance(milestone, str) or milestone not in MILESTONES:
        raise LearningError('invalid_milestone', 'Choose the coins or progress introduction.')
    now = timestamp()
    field = MILESTONES[milestone]
    credential = access_id()
    if credential:
        with transaction(current_app.config['DB_PATH'], write=True) as conn:
            profile_id = _selected_profile(conn, credential, now)
            if profile_id:
                _check_order(milestone, _profile_state(conn, profile_id))
                conn.execute('INSERT OR IGNORE INTO profile_onboarding(profile_id) VALUES (?)', (profile_id,))
                conn.execute(
                    f'UPDATE profile_onboarding SET {field}=COALESCE({field},?) WHERE profile_id=?',
                    (now, profile_id),
                )
                return _profile_state(conn, profile_id)
    saved = _guest_timestamps(session.get(GUEST_ONBOARDING_KEY))
    _check_order(milestone, _state(saved=saved))
    saved.setdefault(field, now)
    session[GUEST_ONBOARDING_KEY] = saved
    return _state(saved=saved)


def initialize_profile_onboarding(conn, profile_id, guest=None):
    """Initialize a new profile, optionally carrying its own guest introduction."""
    saved = _guest_timestamps(guest)
    conn.execute(
        'INSERT INTO profile_onboarding(profile_id,coins_introduced_at,progress_introduced_at) VALUES (?,?,?)',
        (profile_id, saved.get('coins_introduced_at'), saved.get('progress_introduced_at')),
    )
