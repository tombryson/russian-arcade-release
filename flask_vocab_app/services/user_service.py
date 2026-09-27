"""Compatibility access to progress; old users totals remain historical data."""
import logging
import sqlite3
from typing import Optional, Dict, Any

from models.database import connect_db
from services.progression import legacy_profile, snapshot

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @staticmethod
    def stats_in_transaction(conn, user_id=1):
        factory = conn.row_factory
        try:
            profile_id = legacy_profile(conn)
            balance = snapshot(conn, profile_id)['balance'] if profile_id else 0
            row = conn.execute('SELECT elo_rating FROM users WHERE user_id=?', (user_id,)).fetchone() if profile_id == 'personal-learning' else None
            return {'lingocoins': balance, 'elo_rating': row[0] if row else None,
                    'lingocoins_earned': 0, 'elo_change': 0, 'already_rewarded': False}
        finally:
            conn.row_factory = factory

    def update_user_stats(self, user_id: int, marks: int, max_marks: int, difficulty: int,
                          task_type: str, reward_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Deprecated compatibility call. Assessed activities award at their save boundary."""
        try:
            with connect_db(self.db_path) as conn:
                return self.stats_in_transaction(conn, user_id)
        except sqlite3.Error:
            logger.exception('Could not read learning progress')
            return None

    @staticmethod
    def award_in_transaction(conn, user_id, marks, max_marks, difficulty, task_type, reward_key=None):
        """Never turn old score/difficulty arguments into new coins or proficiency."""
        return UserService.stats_in_transaction(conn, user_id)

    def check_anki_cards(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Inspect the optional Anki collection without altering historical rewards."""
        try:
            with connect_db(self.db_path) as conn:
                eligible = conn.execute('''SELECT COUNT(*) FROM anki_cards
                    WHERE interval>5 AND lapses<=1 AND reps>0''').fetchone()[0]
            return {'cards_processed': 0, 'cards_eligible': eligible, 'lingocoins_earned': 0,
                    'feedback': 'Anki progress stays in Anki. Practise in the app to earn Lingocoins.'}
        except sqlite3.Error:
            logger.exception('Could not inspect Anki progress')
            return None
