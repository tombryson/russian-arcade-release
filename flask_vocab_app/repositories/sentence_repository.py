from models.database import connect_db
from utils.activity_owner import activity_profile_id
import logging
import sqlite3

logger = logging.getLogger(__name__)


class SentenceRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def list_saved(self):
        try:
            with connect_db(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, sentence, english, score, topic, difficulty, audio_url, created_at "
                    "FROM sentences WHERE COALESCE(owner_profile_id,'personal-learning')=? ORDER BY created_at DESC",
                    (activity_profile_id(conn),)
                )
                sentences = [
                    {
                        "id": row["id"],
                        "sentence": row["sentence"] or "",
                        "english": row["english"] or "",
                        "score": row["score"],
                        "topic": row["topic"] or "",
                        "difficulty": row["difficulty"],
                        "audio_url": row["audio_url"] or "",
                        "created_at": row["created_at"],
                    }
                    for row in cursor.fetchall()
                ]
            logger.debug("Retrieved %s sentences: %s", len(sentences), [s["audio_url"] for s in sentences])
            return sentences
        except sqlite3.Error as e:
            logger.error("Error fetching sentences: %s", str(e), exc_info=True)
            return []

    def load(self, sentence_id):
        try:
            with connect_db(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, sentence, english, score, topic, difficulty, audio_url, created_at "
                    "FROM sentences WHERE id = ? AND COALESCE(owner_profile_id,'personal-learning')=?",
                    (sentence_id, activity_profile_id(conn)),
                )
                sentence = cursor.fetchone()
                if not sentence:
                    logger.error("Sentence not found: %s", sentence_id)
                    return None
                sentence_data = {
                    "id": sentence["id"],
                    "sentence": sentence["sentence"] or "",
                    "english": sentence["english"] or "",
                    "score": sentence["score"],
                    "topic": sentence["topic"] or "",
                    "difficulty": sentence["difficulty"],
                    "audio_url": sentence["audio_url"] or "",
                    "created_at": sentence["created_at"],
                }
            logger.debug("Loaded sentence: %s, audio_url=%s", sentence_data["sentence"], sentence_data["audio_url"])
            return sentence_data
        except sqlite3.Error as e:
            logger.error("Error loading sentence %s: %s", sentence_id, str(e), exc_info=True)
            return None
