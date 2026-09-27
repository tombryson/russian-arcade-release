"""Read historical lesson records without rewriting their questions or answers.

New preparation and attempts live in LessonCompanion. This compatibility reader
preserves the original JSON, including the earliest question/answer format.
"""
import hashlib
import json
import re
import sqlite3

from models.database import connect_db
from utils.activity_owner import activity_profile_id, PERSONAL_PROFILE


class LessonService:
    def __init__(self, db_path, openai_service=None, api_key="", upload_folder=None):
        self.db_path = db_path

    def get_lesson(self, lesson_id):
        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM lessons WHERE id=?", (lesson_id,)
            ).fetchone()
            show_legacy_answers = activity_profile_id(conn) == PERSONAL_PROFILE
        if not row:
            return None
        lesson = dict(row)
        for key in ("images", "prompts", "responses"):
            value = json.loads(lesson[key] or "[]")
            lesson[key] = value if isinstance(value, list) else []
        # Historical answers predate profiles and belong to the original user.
        # The lesson material and generated prompts remain shared content.
        if not show_legacy_answers:
            lesson['responses'] = []
        used = set()
        prompts = []
        for index, value in enumerate(lesson["prompts"]):
            p = dict(value) if isinstance(value, dict) else {"prompt": str(value)}
            original = str(p.get("id") or "")
            task_id = (
                original
                if original
                and original not in used
                and re.fullmatch(r"[A-Za-z0-9_-]+", original)
                else "legacy-"
                + hashlib.sha256(f"{lesson_id}:{index}".encode()).hexdigest()[:16]
            )
            used.add(task_id)
            prompts.append(
                {
                    **p,
                    "id": task_id,
                    "prompt": p.get("prompt") or p.get("question", ""),
                    "reference_answer": p.get("answer", ""),
                }
            )
        lesson["prompts"] = prompts
        return lesson

    def get_saved_lessons(self):
        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT id,title,created_at FROM lessons ORDER BY created_at DESC"
                )
            ]
