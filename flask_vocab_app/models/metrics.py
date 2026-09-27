import json
from flask import make_response
from .database import get_db
from utils.pos_case import POS_LIST

def get_metrics(db_path):
    try:
        db = get_db(db_path)
        cursor = db.cursor()

        cursor.execute("SELECT COUNT(*) FROM words")
        total_words = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(count) FROM words")
        flashcard_total = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM words WHERE count > 0")
        words_with_flashcards = cursor.fetchone()[0]
        flashcard_percentage = (words_with_flashcards / total_words * 100) if total_words > 0 else 0

        cursor.execute("SELECT pos, COUNT(*) as count FROM words WHERE count > 0 GROUP BY pos")
        pos_counts = {row['pos']: row['count'] for row in cursor.fetchall()}
        pos_distribution = {
            pos['label']: sum(pos_counts.get(p, 0) for p in pos['value'])
            for pos in POS_LIST
        }

        try:
            cursor.execute('''
                SELECT f.tags->>'case' as case_tag, SUM(f.count) as count
                FROM forms f
                JOIN words w ON f.word_id = w.id
                WHERE w.pos IN ('NOUN', 'ADJF', 'ADJS') AND f.count > 0 AND f.tags->>'case' IS NOT NULL
                GROUP BY f.tags->>'case'
            ''')
            case_distribution = {
                case_tag: int(row['count']) for row in cursor.fetchall()
                if (case_tag := row['case_tag'].lower()) in ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']
            }
        except Exception:
            case_distribution = {case: 0 for case in ['nomn', 'gent', 'datv', 'accs', 'ablt', 'loct']}

        response = {
            'total_words': total_words,
            'flashcard_total': flashcard_total,
            'flashcard_percentage': round(flashcard_percentage, 2),
            'pos_distribution': pos_distribution,
            'case_distribution': case_distribution,
        }

        return make_response(json.dumps(response, ensure_ascii=False), 200, {'Content-Type': 'application/json; charset=utf-8'})
    except Exception as e:
        return make_response(json.dumps({'error': str(e)}, ensure_ascii=False), 500, {'Content-Type': 'application/json; charset=utf-8'})