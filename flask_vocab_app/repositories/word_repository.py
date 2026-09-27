from models.database import connect_db
import json
import sqlite3
from repositories.vocabulary_inventory import annotate_words


class WordRepository:
    def __init__(self, db_path):
        self.db_path = db_path

    def list_basic(self):
        with connect_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, lemma, pos, lemma_difficulty, count FROM words ORDER BY lemma")
            rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "lemma": row[1],
                "pos": row[2],
                "lemma_difficulty": row[3],
                "count": row[4] or 0,
            }
            for row in rows
        ]

    def find_basic_by_lemma(self, lemma):
        with connect_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, lemma, pos, lemma_difficulty, count FROM words WHERE lemma = ?", (lemma,))
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "lemma": row[1],
            "pos": row[2],
            "lemma_difficulty": row[3],
            "count": row[4] or 0,
        }

    def exists(self, lemma):
        with connect_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM words WHERE lemma = ?", (lemma,))
            return bool(cursor.fetchone())

    def list_topics(self):
        topics = set()
        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT topic FROM words WHERE topic IS NOT NULL")
            for row in cursor.fetchall():
                try:
                    topic_list = json.loads(row["topic"])
                except json.JSONDecodeError:
                    continue
                topics.update(topic_list)

        return sorted(topics)

    def count(self):
        with connect_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM words")
            return cursor.fetchone()[0]

    def list_vocab(self, sort_column, sort_order, limit=None, offset=None):
        allowed = {'lemma','pos','topic','lemma_difficulty','mnemonic','date_added','count'}
        sort_column = sort_column if sort_column in allowed else 'lemma'
        sort_order = 'DESC' if sort_order.upper() == 'DESC' else 'ASC'
        query = (
            "SELECT id, lemma, pos, topic, lemma_difficulty, mnemonic, date_added, count "
            f"FROM words ORDER BY {sort_column} {sort_order}, id"
        )
        params = ()
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params = (limit, offset or 0)

        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return annotate_words(conn, [self._vocab_row_to_dict(row) for row in rows])

    def difficulty_counts(self):
        distribution = {}
        word_counts = {}
        with connect_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT lemma_difficulty, SUM(count) as total FROM words GROUP BY lemma_difficulty")
            for row in cursor.fetchall():
                distribution[str(row[0])] = row[1] or 0

            cursor.execute("SELECT lemma_difficulty, COUNT(*) as word_count FROM words GROUP BY lemma_difficulty")
            for row in cursor.fetchall():
                word_counts[str(row[0])] = row[1] or 0

        return distribution, word_counts

    def topic_counts(self):
        distribution = {}
        word_counts = {}
        with connect_db(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT json_each.value as topic, SUM(count) as total
                FROM words, json_each(words.topic)
                GROUP BY json_each.value
                """
            )
            for row in cursor.fetchall():
                distribution[row["topic"]] = row["total"] or 0

            cursor.execute(
                """
                SELECT json_each.value as topic, COUNT(DISTINCT words.id) as word_count
                FROM words, json_each(words.topic)
                GROUP BY json_each.value
                """
            )
            for row in cursor.fetchall():
                word_counts[row["topic"]] = row["word_count"] or 0

        return distribution, word_counts

    def _vocab_row_to_dict(self, row):
        try:
            topic_data = json.loads(row["topic"] or "[]")
        except json.JSONDecodeError:
            topic_data = []

        return {
            "id": row["id"],
            "lemma": row["lemma"],
            "pos": row["pos"],
            "topic": [topic for topic in topic_data if isinstance(topic,str)] if isinstance(topic_data, list) else [],
            "lemma_difficulty": row["lemma_difficulty"],
            "mnemonic": row["mnemonic"] or "",
            "date_added": row["date_added"] or "",
            "count": row["count"] or 0,
        }
