"""Load sample words prepared by the full vocabulary import pipeline."""
import json
from functools import lru_cache
from pathlib import Path

from services.vocabulary_topics import TOPICS

SAMPLE_VOCABULARY_PATH = Path(__file__).resolve().parents[1] / 'data/sample_vocabulary.json'

@lru_cache(maxsize=1)
def prepared_vocabulary():
    payload = json.loads(SAMPLE_VOCABULARY_PATH.read_text(encoding='utf-8'))
    if payload.get('schema_version') != 1 or payload.get('pipeline') != 'SyncService.process_word + SyncService.enrich_words':
        raise ValueError('Prepare sample vocabulary through scripts/prepare_sample_vocabulary.py.')
    entries = {}
    for word in payload['words']:
        topics, mnemonic = word.get('topics'), word.get('mnemonic')
        key = (word['lemma'], word['pos'])
        if (key in entries or not isinstance(topics, list) or not topics
                or any(topic not in TOPICS for topic in topics)
                or not isinstance(mnemonic, str) or not mnemonic.strip()
                or mnemonic.startswith('Recall ') or len(mnemonic.split()) > 7):
            raise ValueError('Sample vocabulary enrichment is incomplete. Re-run its preparation script.')
        entries[key] = word
    return entries


def _topics(value):
    try:
        result = json.loads(value or '[]')
    except (ValueError, TypeError):
        return []
    return result if isinstance(result, list) else []


def sample_needs_repair(conn):
    prepared = prepared_vocabulary()
    for lemma, pos, topic, mnemonic in conn.execute('SELECT lemma,pos,topic,mnemonic FROM words'):
        if ((lemma, pos) in prepared
                and ('First steps' in _topics(topic) or not _topics(topic)
                     or not mnemonic or not mnemonic.strip() or mnemonic.startswith('Recall '))):
            return True
    return False


@lru_cache(maxsize=1)
def _pipeline():
    from services.sync_service import SyncService
    return SyncService(':memory:', drive_service=object(), api_key='', config={})


def seed_sample_items(conn, prefix):
    from services.first_steps import HELLO, chapter_content
    from services.lesson_cards import LessonCards, normal
    from utils.story_processing import get_morph
    items = []
    for lesson in [HELLO, *chapter_content()['lessons']]:
        for word in lesson['vocabulary']:
            prepared = prepared_vocabulary().get((word['lemma'], word['pos']))
            if not prepared:
                raise ValueError('Run scripts/prepare_sample_vocabulary.py for new sample words.')
            topics = prepared['topics']
            resolved = LessonCards.resolve(conn, {**word, 'surface': word['form']})
            row = conn.execute('SELECT * FROM words WHERE id=?', (resolved['word_id'],)).fetchone()
            previous = _topics(row['topic'])
            # Only repair the known seed marker. Preserve user categories,
            # counts, mnemonics and the relational IDs referenced by cards.
            if 'First steps' in previous:
                previous = [topic for topic in previous if topic != 'First steps']
                parsed = next(p for p in get_morph().parse(normal(word['form']))
                              if p.is_known and p.normal_form == word['lemma'] and p.tag.POS == word['pos']
                              and all(getattr(p.tag, key, None) == value for key, value in word['grammar'].items()))
                # The old seed hard-coded 1 rather than computing difficulty.
                conn.execute('UPDATE words SET lemma_difficulty=0 WHERE id=? AND lemma_difficulty=1', (row['id'],))
                if not _pipeline().process_word(word['lemma'], conn, conn.cursor(), parsed=parsed, word_id=row['id']):
                    raise ValueError('Could not repair sample word forms.')
            conn.execute('UPDATE words SET topic=? WHERE id=?',
                         (json.dumps(previous or topics, ensure_ascii=False), row['id']))
            mnemonic = row['mnemonic']
            if not mnemonic or not mnemonic.strip() or mnemonic.startswith('Recall '):
                mnemonic = prepared['mnemonic']
                conn.execute('UPDATE words SET mnemonic=? WHERE id=?', (mnemonic, row['id']))
            context, answer = word['sentence'], word['form']
            if answer not in context:
                raise ValueError('Sample sentence is missing its target form.')
            identifier = f'{prefix}-{len(items) + 1}'
            items.append(dict(id=identifier, card_id=identifier, word_id=resolved['word_id'], form_id=resolved['form_id'],
                type='cloze', direction='ru-cloze', sense_key=identifier, sense_label=lesson['title'],
                context=context, prompt=context.replace(answer, '[[blank]]', 1), answer=answer,
                cue_en=word['target_meaning'], context_meaning=word['translation'], hint=mnemonic))
    return items
