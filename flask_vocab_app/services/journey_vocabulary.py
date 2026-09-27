"""Read real vocabulary and selected lesson occurrences for reusable practice.

This adapter does not translate lemmas, create cards, correct OCR or write any
lexical/progress rows. Context and media are reused only within their owner.
"""
from copy import deepcopy
import json
import random
import re

from flask import current_app, has_app_context

from repositories.card_repository import ACTIVE_CARD_VERSIONS_SQL, load_card
from repositories.learning_repository import LearningError, payload_hash
from services.card_metadata import GRAMMAR, metadata_for
from services.learning_content import normalize_form
from services.lesson_cards import lesson_link
from utils.pos_case import POS_MAP
from utils.story_processing import get_morph


def _json(value, fallback):
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        return parsed if fallback is None or isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def _word(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[а-яё]+(?:-[а-яё]+)*', normalize_form(value)))


def _pos(value):
    value = str(value or '').upper()
    value = {'ADJECTIVE': 'ADJ', 'ADVERB': 'ADVB', 'PRONOUN': 'NPRO', 'NUMERAL': 'NUMR',
             'PARTICIPLE': 'PART', 'PARTICLE': 'PRCL', 'PREPOSITION': 'PREP', 'CONJUNCTION': 'CONJ'}.get(value, value)
    return POS_MAP.get(value, value)


def _owner(profile_id):
    if not profile_id:
        return None
    return 'household' if has_app_context() and current_app.config.get('WORD_POST_HOUSEHOLD_ENABLED') else profile_id


def _scope(profile_id, guest_token):
    return ('profile_id=?', (profile_id,)) if profile_id else ('profile_id IS NULL AND guest_token=?', (guest_token,))


def _identity(record, *, occurrence=None):
    return payload_hash({'word_id': record.get('word_id'), 'form_id': record.get('form_id'),
                         'lemma': normalize_form(record['lemma']), 'form': normalize_form(record['form']),
                         'tags': record['tags'], 'occurrence': occurrence})


def _vocabulary(conn, options=None):
    options = options or {}
    records = []
    forms = {}
    for row in conn.execute('SELECT * FROM forms ORDER BY id'):
        forms.setdefault(row['word_id'], []).append(dict(row))
    for row in conn.execute('SELECT * FROM words ORDER BY id'):
        word = dict(row)
        if not _word(word['lemma']):
            continue
        for form in forms.get(word['id']) or [None]:
            surface = form['form'] if form else word['lemma']
            tags = _json(form['tags'], {}) if form else {}
            if not _word(surface) or form and not isinstance(_json(form['tags'], None), dict):
                # A malformed tag string is not an invitation to invent its case.
                continue
            metadata = metadata_for(word, form)
            if options.get('topic') and options['topic'] not in metadata['topics']:
                continue
            if options.get('difficulty') and options['difficulty'] != metadata.get('form_difficulty', metadata.get('lemma_difficulty')):
                continue
            record = {'word_id': word['id'], 'form_id': form['id'] if form else None,
                      'lemma': word['lemma'], 'form': surface, 'pos': word['pos'], 'tags': tags,
                      'metadata': metadata, 'mnemonic': word['mnemonic'] or '',
                      'source': {'kind': 'vocabulary', 'id': str(word['id']), 'title': word['lemma'], 'url': '/vocab'}}
            record['identity'] = _identity(record)
            records.append(record)
    return records


def _assets(conn, values):
    assets = []
    store = current_app.extensions.get('learning', {}).get('assets') if has_app_context() else None
    for item in values or []:
        if not isinstance(item, dict) or item.get('kind') not in ('image', 'word_audio', 'sentence_audio'):
            continue
        asset = conn.execute('SELECT * FROM learning_assets WHERE id=?', (item.get('id'),)).fetchone()
        if not asset or not asset['media_type'].startswith('image/' if item['kind'] == 'image' else 'audio/'):
            continue
        if store and not store.path(asset['storage_key']).is_file():
            continue
        assets.append({'id': item['id'], 'kind': item['kind']})
    return assets


def _prepared(record):
    return all(isinstance(record.get(key), str) and record[key].strip() for key in ('sentence', 'translation', 'target_meaning'))


def cache_source_available(conn, record, profile_id):
    """A cache may not restore a native example its owner set aside.

    Historical games keep their own immutable snapshots. This check applies
    only when choosing examples for a new game or filling its preparation.
    """
    source = record.get('source', {})
    if not isinstance(source, dict):
        return False
    card_id = source.get('id') if source.get('kind') == 'card' else source.get('card_id')
    if not card_id:
        return source.get('kind') != 'card'
    owner = _owner(profile_id)
    if owner is None:
        return False
    version = source.get('version') if source.get('kind') == 'card' else source.get('card_version')
    if version and not conn.execute("SELECT 1 FROM card_versions cv JOIN learning_content_versions v ON v.id=cv.content_version_id "
                                    "WHERE cv.card_id=? AND v.id=? AND v.status='published'", (card_id, version)).fetchone():
        return False
    return bool(conn.execute(
        "SELECT 1 FROM card_versions cv JOIN card_definitions d ON d.id=cv.card_id "
        "JOIN learning_content_versions v ON v.id=cv.content_version_id "
        "WHERE d.id=? AND d.retired=0 AND v.status='published' "
        "AND v.version=(SELECT MAX(p.version) FROM learning_content_versions p WHERE p.content_id=v.content_id AND p.status='published') "
        "AND NOT EXISTS (SELECT 1 FROM learning_content_versions removed WHERE removed.content_id=v.content_id "
        "AND removed.version>v.version AND removed.status='withdrawn') "
        "AND EXISTS (SELECT 1 FROM native_card_generation_items i JOIN native_card_batches b ON b.id=i.batch_id "
        "JOIN learning_content_versions original ON original.id=i.version_id WHERE b.owner_id=? AND original.content_id=v.content_id)",
        (card_id, owner),
    ).fetchone())


def _native_contexts(conn, profile_id):
    """Published, non-retired cards selected through the native owner's batches."""
    owner = _owner(profile_id)
    if owner is None:
        return {}
    owned = {row[0] for row in conn.execute('SELECT DISTINCT cv.card_id FROM native_card_generation_items i '
                                          'JOIN native_card_batches b ON b.id=i.batch_id '
                                          'JOIN learning_content_versions original ON original.id=i.version_id '
                                          'JOIN learning_content_versions current ON current.content_id=original.content_id '
                                          'JOIN card_versions cv ON cv.content_version_id=current.id '
                                          'WHERE b.owner_id=?', (owner,))}
    contexts = {}
    for row in conn.execute(ACTIVE_CARD_VERSIONS_SQL):
        if row['card_id'] not in owned:
            continue
        meta, item = load_card(conn, row['id'])
        if not cache_source_available(conn, {'source': {'kind': 'card', 'id': row['card_id'], 'version': meta['content_version_id']}}, profile_id):
            continue
        target = item.get('prompt') if item['direction'] == 'ru-en' else item.get('answer')
        meaning = item.get('cue_en') or (item.get('answer') if item['direction'] == 'ru-en' else item.get('prompt') if item['direction'] == 'en-ru' else None)
        if not _word(target) or not all(isinstance(value, str) and value.strip() for value in (item.get('context'), item.get('context_meaning'), meaning)):
            continue
        text = normalize_form(item['context'])
        if len(re.findall(r'(?<!\w)' + re.escape(normalize_form(target)) + r'(?!\w)', text)) != 1:
            continue
        key = (meta['word_id'], item.get('form_id'), normalize_form(target))
        contexts.setdefault(key, {'form': target, 'sentence': item['context'], 'translation': item['context_meaning'],
                                  'target_meaning': meaning, 'notes': item.get('explanation', ''), 'assets': _assets(conn, item.get('assets')),
                                  'source': {'kind': 'card', 'id': meta['card_id'], 'title': meta['title'],
                                             'url': '/#flashcards?word_id=' + str(meta['word_id']), 'version': meta['content_version_id']}})
    return contexts


def _unavailable_item(conn, item_id, profile_id):
    rows = conn.execute('SELECT cv.card_id,cv.content_version_id FROM native_card_generation_items i '
                        'JOIN card_versions cv ON cv.content_version_id=i.version_id WHERE i.id=?', (item_id,)).fetchall()
    return bool(rows and not any(cache_source_available(conn, {'source': {'kind': 'card', 'id': row['card_id'],
                                'version': row['content_version_id']}}, profile_id) for row in rows))


def _selected_context(row, selection, response):
    if not selection or not response or not _word(selection.get('lemma')) or not _word(selection.get('form')):
        return None
    if not all(isinstance(response.get(key), str) and response[key].strip() for key in ('sentence', 'sentence_english', 'english')):
        return None
    record = {'word_id': selection.get('word_id'), 'form_id': selection.get('form_id'), 'lemma': selection['lemma'],
              'form': selection['form'], 'pos': selection['pos'], 'tags': selection.get('tags', {}),
              'metadata': selection.get('metadata', {}), 'mnemonic': selection.get('mnemonic', ''),
              'sentence': response['sentence'], 'translation': response['sentence_english'], 'target_meaning': response['english'],
              'notes': response.get('notes', ''), 'source': {'kind': 'lesson', 'id': row['lesson_id'], 'title': row['title'],
               'url': lesson_link(row['lesson_id'], row['revision_id'], row['page'], 'materials'), 'version': row['revision_id'],
               'page': row['page'], 'origin': selection.get('lesson_source', {}).get('origin', 'source')}}
    record['identity'] = _identity(record, occurrence={'lesson': row['lesson_id'], 'context': normalize_form(record['sentence'])})
    return record


def _pending_context(conn, row):
    if not _word(row['surface']) or not row['context'].strip():
        return None
    region = _json(row['region_payload'], {})
    if not row['reading_confirmed'] and region.get('needs_check') is not False:
        return None
    parses = [p for p in get_morph().parse(normalize_form(row['surface'])) if p.is_known]
    lexemes = {(p.normal_form, p.tag.POS) for p in parses}
    if len(lexemes) != 1:
        # A spelling such as «печь» cannot select its own noun/verb reading.
        return None
    lemma, pos = next(iter(lexemes))
    if not _word(lemma):
        return None
    tags = {key: str(getattr(parses[0].tag, key)) for key in GRAMMAR if getattr(parses[0].tag, key, None)
            and all(getattr(p.tag, key, None) == getattr(parses[0].tag, key) for p in parses)}
    words = [dict(word) for word in conn.execute('SELECT * FROM words')
             if normalize_form(word['lemma']) == normalize_form(lemma) and _pos(word['pos']) == _pos(pos)]
    if len(words) > 1:
        return None
    word = words[0] if words else {'id': None, 'lemma': lemma, 'pos': pos, 'mnemonic': '', 'topic': '[]'}
    signatures = {tuple(getattr(p.tag, key, None) for key in GRAMMAR) for p in parses}
    forms = [dict(form) for form in conn.execute('SELECT * FROM forms WHERE word_id=?', (word['id'],))
             if normalize_form(form['form']) == normalize_form(row['surface']) and all(_json(form['tags'], {}).get(key) == value for key, value in tags.items())] if len(signatures) == 1 else []
    form = forms[0] if len(forms) == 1 else None
    record = {'word_id': word['id'], 'form_id': form['id'] if form else None, 'lemma': lemma, 'form': row['surface'],
              'pos': pos, 'tags': tags, 'metadata': metadata_for(word, {'tags': tags}), 'mnemonic': word.get('mnemonic') or '',
              'source': {'kind': 'lesson', 'id': row['lesson_id'], 'title': row['title'],
                         'url': lesson_link(row['lesson_id'], row['revision_id'], row['page'], 'materials'), 'version': row['revision_id'],
                         'page': row['page'], 'pick_id': row['id'], 'origin': 'selection', 'context': row['context']}}
    record['identity'] = _identity(record, occurrence={'pick': row['id'], 'context': normalize_form(row['context'])})
    return record


def _lesson_records(conn, profile_id, lesson_id=None):
    owner = _owner(profile_id)
    if owner is None:
        return []
    params, condition = [owner], ''
    if lesson_id:
        condition = ' AND p.lesson_id=?'
        params.append(lesson_id)
    records, seen_items = [], set()
    rows = conn.execute('SELECT p.*,l.title,r.payload AS region_payload,i.selection AS item_selection,i.response AS item_response,b.owner_id AS item_owner '
                        'FROM lesson_word_picks p JOIN lessons l ON l.id=p.lesson_id LEFT JOIN lesson_word_regions r ON r.id=p.region_id '
                        'LEFT JOIN native_card_generation_items i ON i.id=p.item_id '
                        'LEFT JOIN native_card_batches b ON b.id=i.batch_id '
                        'WHERE p.owner_id=? AND p.selected=1' + condition + ' ORDER BY p.created_at,p.rowid', params)
    for row in rows:
        if row['item_id'] and row['item_owner'] != owner:
            continue
        if row['item_id'] and _unavailable_item(conn, row['item_id'], profile_id):
            continue
        record = _selected_context(row, _json(row['item_selection'], {}), _json(row['item_response'], {})) if row['item_id'] else _pending_context(conn, row)
        if record:
            records.append(record)
            if row['item_id']:
                seen_items.add(row['item_id'])
    params, condition = [owner], ''
    if lesson_id:
        condition = ' AND r.lesson_id=?'
        params.append(lesson_id)
    rows = conn.execute('SELECT DISTINCT i.id AS item_id,i.selection,i.response,r.lesson_id,r.revision_id,s.page,l.title '
                        'FROM lesson_card_sources s JOIN lesson_card_requests r ON r.id=s.request_id '
                        'JOIN native_card_generation_items i ON i.id=s.item_id JOIN native_card_batches b ON b.id=i.batch_id '
                        'JOIN lessons l ON l.id=r.lesson_id WHERE r.owner_id=? AND b.owner_id=r.owner_id' + condition, params)
    for row in rows:
        if row['item_id'] in seen_items or _unavailable_item(conn, row['item_id'], profile_id):
            continue
        record = _selected_context(row, _json(row['selection'], {}), _json(row['response'], {}))
        if record:
            records.append(record)
            seen_items.add(row['item_id'])
    return list({record['identity']: record for record in records}.values())


def _cache(conn, profile_id, guest_token):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='journey_game_examples'").fetchone():
        return {}
    where, params = _scope(profile_id, guest_token)
    cached = {}
    for row in conn.execute('SELECT * FROM journey_game_examples WHERE ' + where + ' ORDER BY created_at,id', params):
        record = _json(row['content_json'], {})
        if cache_source_available(conn, record, profile_id):
            cached[row['identity']] = (row['id'], record)
    return cached


def _recent(conn, profile_id, guest_token):
    where, params = _scope(profile_id, guest_token)
    words, forms = {}, {}
    for age, row in enumerate(conn.execute('SELECT content_json FROM journey_game_sessions WHERE ' + where + ' ORDER BY created_at DESC,rowid DESC LIMIT 10', params)):
        content = _json(row['content_json'], {})
        for ref in [*content.get('vocabulary_refs', []), *content.get('examples', []), *content.get('selected_examples', [])]:
            if isinstance(ref, dict) and isinstance(ref.get('lemma'), str):
                words.setdefault(normalize_form(ref['lemma']), 10 - age)
                forms.setdefault((normalize_form(ref['lemma']), normalize_form(ref.get('form', ''))), 10 - age)
    return words, forms


def catalogue_sources(conn, profile_id, guest_token):
    vocabulary = _vocabulary(conn)
    lessons = {}
    for record in _lesson_records(conn, profile_id):
        source = record['source']
        lesson = lessons.setdefault(source['id'], {'id': source['id'], 'title': source['title'], 'count': 0})
        lesson['count'] += 1
    return {'word_count': len({record['word_id'] for record in vocabulary}),
            'form_count': len({record['form_id'] for record in vocabulary if record['form_id'] is not None}),
            'topics': sorted({topic for record in vocabulary for topic in record['metadata']['topics']}),
            'lessons': sorted(lessons.values(), key=lambda lesson: lesson['title'].casefold())}


def select_examples(conn, profile_id, guest_token, options, seed, limit=6):
    source = options.get('source', 'vocabulary')
    if source not in ('vocabulary', 'lesson'):
        raise LearningError('invalid_source', 'Choose your vocabulary or a lesson.')
    if type(limit) is not int or not 1 <= limit <= 20:
        raise LearningError('invalid_quantity', 'Choose a short practice set.')
    if source == 'lesson':
        if not isinstance(options.get('lesson_id'), str) or not options['lesson_id']:
            raise LearningError('invalid_lesson', 'Choose a lesson to practise.')
        records = _lesson_records(conn, profile_id, options['lesson_id'])
    else:
        records = _vocabulary(conn, options)
    contexts, cached = _native_contexts(conn, profile_id), _cache(conn, profile_id, guest_token)
    for record in records:
        native = contexts.get((record['word_id'], record['form_id'], normalize_form(record['form'])))
        if not _prepared(record):
            if native and source == 'vocabulary':
                record.update(deepcopy(native))
            elif record['identity'] in cached:
                cached_id, example = cached[record['identity']]
                if (_prepared(example) and normalize_form(example.get('form', '')) == normalize_form(record['form'])
                        and normalize_form(example.get('lemma', '')) == normalize_form(record['lemma'])):
                    record.update({key: deepcopy(example[key]) for key in ('sentence', 'translation', 'target_meaning', 'notes', 'assets') if key in example})
                    record['cached_id'] = cached_id
        elif native and native['sentence'] == record['sentence'] and native['translation'] == record['translation']:
            # A lesson keeps its page provenance. Its already-created card's
            # picture and speech belong only to that same saved occurrence.
            record['assets'] = deepcopy(native['assets'])
            record['target_meaning'] = native['target_meaning']
            record['notes'] = native['notes']
            record['source']['card_id'] = native['source']['id']
            record['source']['card_version'] = native['source']['version']
        if record.get('assets'):
            record['assets'] = _assets(conn, record['assets'])
    recent_words, recent_forms = _recent(conn, profile_id, guest_token)
    rng = random.Random(seed)
    rng.shuffle(records)
    records.sort(key=lambda item: (int(normalize_form(item['lemma']) in recent_words),
                                   recent_forms.get((normalize_form(item['lemma']), normalize_form(item['form'])), 0),
                                   0 if _prepared(item) else 1))
    chosen, used_words = [], set()
    for record in records:
        word = (record['word_id'], normalize_form(record['lemma']))
        if word not in used_words:
            chosen.append(record)
            used_words.add(word)
            if len(chosen) == limit:
                return chosen
    for record in records:
        if all(record['identity'] != selected['identity'] for selected in chosen):
            chosen.append(record)
            if len(chosen) == limit:
                break
    return chosen
