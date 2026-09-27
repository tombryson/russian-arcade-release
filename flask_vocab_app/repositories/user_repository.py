from models.database import connect_db
import sqlite3


class UserRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def get_or_create_stats(self, user_id):
        with connect_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT lingocoins, elo_rating FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            if user:
                return user[0], user[1]

            cursor.execute("INSERT INTO users (user_id, lingocoins, elo_rating) VALUES (?, 0, 1000)", (user_id,))
            conn.commit()
            return 0, 1000
