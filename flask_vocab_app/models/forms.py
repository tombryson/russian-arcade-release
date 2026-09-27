import json
from .database import get_db

def get_form_by_word_id(db_path, word_id, case=None):
    db = get_db(db_path)
    cursor = db.cursor()
    query = "SELECT form, tags, count FROM forms WHERE word_id = ?"
    params = [word_id]
    if case:
        query += " AND tags LIKE ?"
        params.append(f'%\"case\":\"{case}\"%')
    query += " ORDER BY count ASC, RANDOM() LIMIT 1"
    cursor.execute(query, params)
    return cursor.fetchone()

def get_all_forms(db_path):
    db = get_db(db_path)
    cursor = db.cursor()
    cursor.execute("SELECT form, tags, count FROM forms")
    rows = cursor.fetchall()
    return [{'form': row[0], 'tags': json.loads(row[1]), 'count': row[2]} for row in rows]

def update_form_count(db_path, form_id):
    db = get_db(db_path)
    db.execute("UPDATE forms SET count = count + 1 WHERE id = ?", (form_id,))
    db.commit()