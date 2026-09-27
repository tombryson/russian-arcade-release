"""Card facets copied from lexical data, independent of memory state."""
import json
from utils.pos_case import POS_MAP

GRAMMAR = ('case','number','gender','animacy','tense','person','mood','aspect','voice')


def metadata_for(word, form=None):
    word, form = dict(word), dict(form or {})
    tags = form.get('tags', word.get('tags', {}))
    try:
        tags = json.loads(tags or '{}') if isinstance(tags, str) else tags
    except (ValueError,TypeError):
        tags = {}
    tags = tags if isinstance(tags, dict) else {}
    topics = word.get('topic', word.get('topics', []))
    try:
        topics = json.loads(topics or '[]') if isinstance(topics, str) else topics
    except (ValueError,TypeError):
        topics = []
    topics = topics if isinstance(topics, list) else []
    grammar = {k: str(tags[k]) for k in GRAMMAR if tags.get(k)}
    if grammar.get('case') in ('instr','prep'):
        grammar['case'] = {'instr':'ablt','prep':'loct'}[grammar['case']]
    result = {'pos': POS_MAP.get(word.get('pos'), word.get('pos') or 'unknown'), 'grammar': grammar,
              'topics': sorted({t for t in topics if isinstance(t,str) and t.strip()})}
    for name, source in (('lemma_difficulty',word),('form_difficulty',form)):
        value = source.get(name)
        if isinstance(value,int) and 1 <= value <= 8:
            result[name] = value
    return result


def enrich_item(conn, item):
    word = conn.execute('SELECT * FROM words WHERE id=?',(item['word_id'],)).fetchone()
    form = conn.execute('SELECT * FROM forms WHERE id=? AND word_id=?',(item.get('form_id'),item['word_id'])).fetchone()
    if word:
        item['metadata'] = metadata_for(word, form)
        if word['mnemonic'] and not item.get('hint'):
            item['hint'] = word['mnemonic']
    return item
