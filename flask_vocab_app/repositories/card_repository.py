"""Read projections from approved content. No second editable answer store."""
import json

from contracts.flashcards import card_item
from repositories.learning_repository import LearningError


# Shared by the reviewer and vocabulary counts: one published membership can
# have several revisions, but its stable card identity is counted only once.
ACTIVE_CARD_VERSIONS_SQL = (
    "SELECT cv.id,cv.card_id FROM card_versions cv JOIN card_definitions d ON d.id=cv.card_id "
    "JOIN learning_content_versions v ON v.id=cv.content_version_id "
    "WHERE d.retired=0 AND v.status='published' AND v.version=(SELECT MAX(v2.version) FROM learning_content_versions v2 "
    "WHERE v2.content_id=v.content_id AND v2.status='published') ORDER BY v.created_at DESC,v.rowid DESC,cv.id"
)


def contextual_cue(conn, meta, item):
    if item.get('cue_en'):
        return item['cue_en']
    # Compatibility with generated clozes saved before cue_en was retained.
    # Recover the provider's explicit field, never a guessed translation or
    # excerpt. Edited/manual cards and different examples must not inherit it.
    pack = json.loads(meta['payload'])
    if item['direction'] != 'ru-cloze' or not pack.get('source','').startswith('Automatically generated from the vocabulary library.'):
        return None
    original = conn.execute('SELECT g.response,g.selection FROM native_card_generation_items g '
                            'JOIN card_versions cv ON cv.content_version_id=g.version_id '
                            'WHERE cv.card_id=? AND g.status=? LIMIT 1', (meta['card_id'],'saved')).fetchone()
    if original and original['response']:
        response, selection = json.loads(original['response']), json.loads(original['selection'])
        cue = response.get('english')
        if (response.get('sentence','').strip() == item['context']
                and response.get('sentence_english') == item.get('context_meaning')
                and selection.get('form','').casefold() == item['answer'].casefold()
                and isinstance(cue,str) and 0 < len(cue.strip()) <= 2000):
            return cue.strip()
    return None


def _usable_hint(value, lemma):
    return (isinstance(value, str) and bool(value.strip())
            and value.strip() != f'Recall {lemma} phonetically.')


def load_card(conn, version_id, *, published=True):
    row = conn.execute(
        'SELECT cv.*,v.payload,v.status,v.title,v.content_id,d.retired,d.word_id,d.sibling_key,w.lemma,w.mnemonic AS word_mnemonic '
        'FROM card_versions cv JOIN learning_content_versions v ON v.id=cv.content_version_id '
        'JOIN card_definitions d ON d.id=cv.card_id LEFT JOIN words w ON w.id=d.word_id WHERE cv.id=?', (version_id,)).fetchone()
    if not row or (published and (row['status'] != 'published' or row['retired'])):
        raise LearningError('content_unavailable', 'This card has been set aside or withdrawn. Your saved practice is kept.', 409)
    pack = json.loads(row['payload'])
    item = next(i for i in pack['items'] if i['id'] == row['item_id'])
    card = card_item(pack, item)
    # Vocabulary enrichment can finish after a card is published. Read its
    # mnemonic without rewriting the immutable example or review history;
    # an explicitly authored card hint continues to take precedence.
    if not _usable_hint(card.get('hint'), row['lemma']):
        card.pop('hint', None)
        if _usable_hint(row['word_mnemonic'], row['lemma']):
            card['hint'] = row['word_mnemonic'].strip()
    cue = contextual_cue(conn,row,card)
    if cue:
        card['cue_en'] = cue
    return dict(row), card


def active_cards(conn):
    # A stable card can occur in several packs. Select one published version,
    # keeping a single memory identity. Old versions remain available to history.
    rows = conn.execute(ACTIVE_CARD_VERSIONS_SQL).fetchall()
    seen, result = set(), []
    for row in rows:
        if row['card_id'] not in seen:
            seen.add(row['card_id'])
            meta, item = load_card(conn, row['id'])
            # Collect every current membership independently from the chosen version.
            memberships = [dict(r) for r in conn.execute(
                "SELECT DISTINCT v.content_id,v.title,json_extract(v.payload,'$.title_ru') AS title_ru FROM card_versions cv JOIN learning_content_versions v ON v.id=cv.content_version_id "
                "WHERE cv.card_id=? AND v.status='published' AND v.version=(SELECT MAX(v2.version) FROM learning_content_versions v2 "
                "WHERE v2.content_id=v.content_id AND v2.status='published') ORDER BY v.title", (row['card_id'],))]
            result.append({'meta': meta, 'item': item, 'decks': memberships})
    return result


def learner_state(conn, profile_id, card_id):
    row = conn.execute('SELECT * FROM learner_card_state WHERE profile_id=? AND card_id=?', (profile_id,card_id)).fetchone()
    return dict(row) if row else None
