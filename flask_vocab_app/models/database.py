"""Shared SQLite policy for requests, repositories, and services."""
import sqlite3
from flask import g


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect_db(db_path, timeout=10):
    conn = sqlite3.connect(db_path, timeout=timeout, factory=ManagedConnection)
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def get_db(db_path):
    if 'db' not in g:
        g.db = connect_db(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
