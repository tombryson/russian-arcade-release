from models.database import connect_db
import json
import sqlite3


class FormRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def list_all(self):
        with connect_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT form, tags, count FROM forms")
            rows = cursor.fetchall()

        return [
            {
                "form": row[0],
                "tags": json.loads(row[1] or "{}"),
                "count": row[2] or 0,
            }
            for row in rows
        ]
