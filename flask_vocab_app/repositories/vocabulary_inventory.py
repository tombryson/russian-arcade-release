"""Read current card coverage from saved identities, never increment a second counter."""
from collections import Counter
import json

from repositories.card_repository import ACTIVE_CARD_VERSIONS_SQL


def card_inventory(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='card_definitions'").fetchone():
        return []
    active = {row['card_id'] for row in conn.execute(ACTIVE_CARD_VERSIONS_SQL)}
    return [
        {**dict(row), 'status': 'retired' if row['retired'] else 'active' if row['id'] in active else 'unpublished'}
        for row in conn.execute('SELECT id,word_id,form_id,retrieval_mode,retired,created_at FROM card_definitions')
    ]


def annotate_words(conn, words):
    cards = card_inventory(conn)
    active = Counter(card['word_id'] for card in cards if card['status'] == 'active')
    saved = Counter(card['word_id'] for card in cards)
    forms = {row['word_id']: row for row in conn.execute(
        'SELECT word_id,COUNT(*) AS total,GROUP_CONCAT(DISTINCT form) AS spellings FROM forms GROUP BY word_id')}
    for word in words:
        group = forms.get(word['id'])
        word.update(native_count=active[word['id']], native_total=saved[word['id']],
                    anki_exports=word['count'], form_count=group['total'] if group else 0,
                    forms_search=group['spellings'] if group else '')
    return words


def word_inventory(conn, word_id):
    word = conn.execute('SELECT id,lemma FROM words WHERE id=?', (word_id,)).fetchone()
    if not word:
        return None
    cards = [card for card in card_inventory(conn) if card['word_id'] == word_id]
    active = Counter(card['form_id'] for card in cards if card['status'] == 'active')
    forms = []
    for row in conn.execute('SELECT id,form,tags,form_difficulty,count FROM forms WHERE word_id=? ORDER BY form,id', (word_id,)):
        try:
            tags = json.loads(row['tags'] or '{}')
        except (TypeError, ValueError):
            tags = {}
        forms.append({'id':row['id'], 'form':row['form'], 'tags':tags if isinstance(tags,dict) else {},
                      'difficulty':row['form_difficulty'], 'native_count':active[row['id']], 'anki_exports':row['count'] or 0})
    return {'word_id':word_id, 'lemma':word['lemma'], 'forms':forms,
            'cards':cards, 'native_count':sum(card['status']=='active' for card in cards),
            'native_total':len(cards)}
