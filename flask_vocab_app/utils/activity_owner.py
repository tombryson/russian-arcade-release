"""Ownership of saved practice in the local workspace.

Command-line imports and the household adult workspace retain the original
learner. Personal web requests always use their selected session profile.
"""
import sqlite3

from flask import current_app, has_request_context

PERSONAL_PROFILE = 'personal-learning'


def activity_profile_id(conn):
    if not has_request_context() or current_app.config.get('WORD_POST_HOUSEHOLD_ENABLED'):
        return PERSONAL_PROFILE
    from utils.household_access import active_profile_id
    factory = conn.row_factory
    try:
        conn.row_factory = sqlite3.Row
        return active_profile_id(conn)
    finally:
        conn.row_factory = factory
