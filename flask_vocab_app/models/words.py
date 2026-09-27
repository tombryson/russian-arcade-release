from .database import get_db

def get_words(db_path):
    db = get_db(db_path)
    cursor = db.cursor()
    cursor.execute("SELECT id, lemma, pos, lemma_difficulty, count FROM words ORDER BY lemma")
    rows = cursor.fetchall()
    return [{'id': row[0], 'lemma': row[1], 'pos': row[2], 'lemma_difficulty': row[3], 'count': row[4]} for row in rows]

def get_word_by_id(db_path, word_id):
    db = get_db(db_path)
    cursor = db.cursor()
    cursor.execute("SELECT id, lemma, pos, lemma_difficulty, count FROM words WHERE id = ?", (word_id,))
    row = cursor.fetchone()
    if row:
        return {'id': row[0], 'lemma': row[1], 'pos': row[2], 'lemma_difficulty': row[3], 'count': row[4]}
    return None

def get_word_by_lemma(db_path, lemma):
    db = get_db(db_path)
    cursor = db.cursor()
    cursor.execute("SELECT id, lemma, pos, lemma_difficulty, count FROM words WHERE lemma = ?", (lemma,))
    row = cursor.fetchone()
    if row:
        return {'id': row[0], 'lemma': row[1], 'pos': row[2], 'lemma_difficulty': row[3], 'count': row[4]}
    return None

def update_word_count(db_path, word_id):
    db = get_db(db_path)
    db.execute("UPDATE words SET count = count + 1 WHERE id = ?", (word_id,))
    db.commit()