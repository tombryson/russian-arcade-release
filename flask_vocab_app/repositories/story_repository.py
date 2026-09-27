from models.database import connect_db
from utils.activity_owner import activity_profile_id
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def has_title_translations(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='story_title_translations'").fetchone() is not None


def english_story_title(conn, story_id):
    if not has_title_translations(conn):
        return ""
    row = conn.execute("SELECT title FROM story_title_translations WHERE story_id=? AND language='en'", (story_id,)).fetchone()
    return row[0] if row else ""


class StoryRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def list_saved(self):
        logger.debug("Fetching saved stories from database")
        try:
            with connect_db(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                translated = has_title_translations(conn)
                title_field = "t.title" if translated else "NULL"
                title_join = "LEFT JOIN story_title_translations t ON t.story_id=s.id AND t.language='en'" if translated else ""
                cursor.execute(f"SELECT s.id, s.title, s.topic, s.difficulty, s.questions, {title_field} AS title_en FROM saved_stories s {title_join} WHERE COALESCE(s.owner_profile_id,'personal-learning')=? ORDER BY s.id DESC", (activity_profile_id(conn),))
                stories = [
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "title_en": row["title_en"] or "",
                        "topic": row["topic"] or "any",
                        "difficulty": row["difficulty"] or "beginner",
                        "questions": row["questions"],
                    }
                    for row in cursor.fetchall()
                ]
            logger.debug("Retrieved %s saved stories", len(stories))
            return stories
        except sqlite3.Error as e:
            logger.error("Error fetching saved stories: %s", str(e))
            return []

    def find_existing(self, text, topic, difficulty):
        try:
            with connect_db(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM saved_stories WHERE text = ? AND topic = ? AND difficulty = ? AND COALESCE(owner_profile_id,'personal-learning')=?",
                    (text, topic, difficulty, activity_profile_id(conn)),
                )
                result = cursor.fetchone()
            return result[0] if result else None
        except sqlite3.Error as e:
            logger.error("Error finding existing story: %s", str(e))
            return None

    def load(self, story_id):
        try:
            with connect_db(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM saved_stories WHERE id = ? AND COALESCE(owner_profile_id,'personal-learning')=?", (story_id, activity_profile_id(conn)))
                story = cursor.fetchone()
                if not story:
                    logger.error("Story not found: %s", story_id)
                    return None

                story_data = {
                    "id": story["id"],
                    "title": story["title"],
                    "title_en": english_story_title(conn, story_id),
                    "topic": story["topic"],
                    "difficulty": story["difficulty"],
                    "text": story["text"],
                    "audio_url": story["audio_url"] or "",
                    "image_url": story["image_url"] or "",
                    "questions": json.loads(story["questions"] or "[]"),
                    "answers": json.loads(story["answers"] or "[]"),
                    "feedback": json.loads(story["feedback"] or "[]") if story["feedback"] else [],
                    "score": story["score"] or 0,
                }
            logger.debug("Loaded story data: questions=%s, answers=%s", story_data["questions"], story_data["answers"])
            return story_data
        except json.JSONDecodeError as e:
            logger.error("JSON decode error in load_story: %s", str(e))
            return None
        except sqlite3.Error as e:
            logger.error("Load story error: %s", str(e))
            raise
