"""Shared short transactions; callers pass one connection through all effects."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from models.database import connect_db


class LearningError(ValueError):
    def __init__(self, code, message, status=400, details=None):
        super().__init__(message)
        self.code, self.status = code, status
        self.details = details or {}


def identifier():
    return uuid4().hex


def timestamp():
    return int(time.time())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def payload_hash(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


@contextmanager
def transaction(db_path, *, write=False):
    if not Path(db_path).is_file():
        raise LearningError('migration_required', 'Run db-upgrade before using the learning store.', 503)
    try:
        with connect_db(db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Take the writer reservation before reads. A racing retry then sees
            # the first commit, including its idempotency result and reward cap.
            conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield conn
    except sqlite3.OperationalError as error:
        code = getattr(error, 'sqlite_errorcode', 0) & 0xff
        if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise LearningError('storage_busy', 'Your save is waiting for another action. Retry the same submission.', 503) from error
        if code in (sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR):
            raise LearningError('storage_unavailable', 'The app could not access its database. Check available disk space, then try again.', 503) from error
        raise


def require_access(conn, access_id, now, *, adult=False, profile_id=None):
    row = conn.execute('SELECT * FROM household_access WHERE id=? AND expires_at>?',
                       (access_id, now)).fetchone()
    if not row:
        from flask import current_app, has_app_context
        personal = has_app_context() and not current_app.config.get('WORD_POST_HOUSEHOLD_ENABLED')
        raise LearningError('locked', 'Choose a profile to continue.' if personal else 'Ask a grown-up to unlock this household.', 401)
    if adult:
        if row['adult_until'] <= now:
            raise LearningError('adult_required', 'A grown-up needs to unlock this action.', 403)
        return row
    profile = conn.execute('SELECT * FROM learning_profiles WHERE id=? AND archived=0 AND legacy_user_id IS NULL',
                           (row['profile_id'],)).fetchone()
    if not profile or (profile_id is not None and profile['id'] != profile_id):
        raise LearningError('profile_changed', 'The learner changed. Reopen this activity for the selected learner.', 409)
    return profile
