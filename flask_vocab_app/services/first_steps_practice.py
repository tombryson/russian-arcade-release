"""Carry authored chapter language into the existing native practice tools."""
import json
from datetime import datetime, timezone
from urllib.parse import quote

from repositories.card_repository import load_card
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, require_access, transaction
from services.card_metadata import GRAMMAR, metadata_for
from services.lesson_cards import LessonCards, normal
from utils.story_processing import get_morph
from utils.pos_case import POS_MAP

TOPIC = 'First steps'


def _identity(candidate):
    return payload_hash({key: candidate.get(key) for key in ('lemma', 'form', 'sentence', 'translation', 'grammar')})


def _prior_items(conn, owner, batch_id):
    """Point at original native items, including unfinished and retired ones."""
    previous = {}
    for row in conn.execute(
        'SELECT i.id,i.batch_id,i.selection FROM native_card_generation_items i '
        'JOIN native_card_batches b ON b.id=i.batch_id WHERE b.owner_id=? '
        'AND b.rowid<(SELECT rowid FROM native_card_batches WHERE id=?) ORDER BY b.rowid,i.position',
        (owner, batch_id),
    ):
        source = json.loads(row['selection']).get('first_steps_source')
        if source:
            previous.setdefault(source['identity'], {'batch_id': row['batch_id'], 'item_id': row['id'], 'identity': source['identity']})
    return previous


def _native_reference(conn, owner, batch_id, candidate):
    """Reference a native card's original owned item, keeping its schedule."""
    source = candidate.get('source', {})
    card_id = source.get('id') if source.get('kind') == 'card' else source.get('card_id')
    version = source.get('version') if source.get('kind') == 'card' else source.get('card_version')
    if not card_id or not version:
        return None
    frozen = conn.execute('SELECT id FROM card_versions WHERE card_id=? AND content_version_id=?', (card_id, version)).fetchone()
    original = conn.execute(
        'SELECT i.id,i.batch_id FROM native_card_generation_items i JOIN native_card_batches b ON b.id=i.batch_id '
        'JOIN learning_content_versions original ON original.id=i.version_id '
        'JOIN learning_content_versions frozen ON frozen.content_id=original.content_id '
        'WHERE frozen.id=? AND b.owner_id=? '
        'AND b.rowid<(SELECT rowid FROM native_card_batches WHERE id=?) ORDER BY b.rowid,i.position LIMIT 1',
        (version, owner, batch_id),
    ).fetchone()
    if not original or not frozen:
        raise LearningError('source_card_unavailable', 'The original card was not found in your saved cards.', 409)
    _, item = load_card(conn, frozen['id'], published=False)
    target = item['prompt'] if item['direction'] == 'ru-en' else item['answer']
    if (normal(target) != normal(candidate['form']) or item['context'] != candidate['sentence']
            or item.get('context_meaning') != candidate['translation']):
        raise LearningError('source_card_changed', 'This game example no longer matches its original saved card.', 409)
    identity = payload_hash({'card_id': card_id, 'content_version_id': version})
    return {'batch_id': original['batch_id'], 'item_id': original['id'], 'identity': identity,
            'card_id': card_id, 'content_version_id': version}


def _game_word(conn, candidate):
    """Use existing relational IDs; resolve morphology only for new readings."""
    word_id, form_id = candidate.get('word_id'), candidate.get('form_id')
    row = conn.execute('SELECT * FROM words WHERE id=?', (word_id,)).fetchone() if word_id is not None else None
    form = conn.execute('SELECT * FROM forms WHERE id=?', (form_id,)).fetchone() if form_id is not None else None
    if word_id is not None and (not row or normal(row['lemma']) != normal(candidate['lemma'])):
        raise LearningError('source_word_changed', 'This word no longer matches the saved game.', 409)
    if form_id is not None and (not form or form['word_id'] != word_id or normal(form['form']) != normal(candidate['form'])):
        raise LearningError('source_form_changed', 'This word form no longer matches the saved game.', 409)
    if row and (form or normal(candidate['form']) == normal(row['lemma'])):
        tags = json.loads(form['tags'] or '{}') if form else candidate.get('tags', {})
        if not isinstance(tags, dict):
            raise LearningError('invalid_word_tags', 'Check this word’s grammatical details before making its card.', 409)
        return {'word_id': row['id'], 'form_id': form['id'] if form else None, 'lemma': row['lemma'],
                'form': candidate['form'], 'pos': row['pos'], 'tags': tags,
                'metadata': metadata_for(row, form), 'mnemonic': row['mnemonic'] or ''}
    tags = candidate.get('grammar') or candidate.get('tags') or candidate.get('metadata', {}).get('grammar', {})
    pos = str(candidate.get('pos', '')).upper()
    # Real rows can use labels such as "noun". The dictionary supplies the
    # exact OpenCorpora POS required by the existing resolver, never an LLM.
    parses = [p for p in get_morph().parse(normal(candidate['form'])) if p.is_known
              and p.normal_form == normal(candidate['lemma'])
              and (pos not in POS_MAP or p.tag.POS == pos)
              and all(getattr(p.tag, key, None) == value for key, value in tags.items()
                      if key in GRAMMAR and value and not (key == 'voice' and p.tag.POS in ('VERB', 'INFN')))]
    positions = {p.tag.POS for p in parses}
    if len(positions) != 1:
        raise LearningError('ambiguous_word_form', 'This selected word needs a clearer grammatical context before making a card.', 409)
    if row:
        signatures = {tuple(getattr(p.tag, key, None) for key in GRAMMAR) for p in parses}
        if len(signatures) != 1:
            raise LearningError('ambiguous_word_form', 'This word form needs a clearer grammatical context.', 409)
        grammar = {key: getattr(parses[0].tag, key) for key in GRAMMAR if getattr(parses[0].tag, key, None)}
        forms = [form for form in conn.execute('SELECT * FROM forms WHERE word_id=?', (row['id'],))
                 if normal(form['form']) == normal(candidate['form']) and json.loads(form['tags'] or '{}') == grammar]
        if not forms:
            conn.execute('INSERT INTO forms(word_id,form,count,tags) VALUES (?,?,0,?)', (row['id'], normal(candidate['form']), encoded(grammar)))
            form = conn.execute('SELECT * FROM forms WHERE id=last_insert_rowid()').fetchone()
        else:
            form = forms[0]
        return {'word_id': row['id'], 'form_id': form['id'], 'lemma': row['lemma'], 'form': candidate['form'],
                'pos': row['pos'], 'tags': grammar, 'metadata': metadata_for(row, form), 'mnemonic': row['mnemonic'] or ''}
    try:
        resolved = LessonCards.resolve(conn, {**candidate, 'surface': candidate['form'], 'pos': positions.pop(), 'grammar': tags})
    except ValueError as error:
        raise LearningError('ambiguous_word_form', str(error), 409) from error
    return resolved


def _completed(conn, credential, now):
    from services.first_steps import completed_lessons
    access = require_access(conn, credential, now, adult=True)
    if not access['profile_id']:
        raise LearningError('profile_required', 'Choose your profile to save this practice.', 403)
    return access['profile_id'], completed_lessons(conn, access['profile_id'])


def _selection(lessons, lesson_id):
    if lesson_id == 'chapter':
        if len(lessons) != 5:
            raise LearningError('lesson_incomplete', 'Finish the chapter before making its full card set.', 409)
        return lessons
    selected = [lesson for lesson in lessons if lesson['id'] == lesson_id]
    if not selected:
        raise LearningError('lesson_incomplete', 'Finish this lesson before making its flashcards.', 409)
    return selected


def create_flashcards(generator, credential, lesson_id):
    """Freeze authored clozes; the native batch runner supplies all three media."""
    def source(conn):
        _, lessons = _completed(conn, credential, generator.clock())
        selected = _selection(lessons, lesson_id)
        title = 'First steps with Barsik' if lesson_id == 'chapter' else selected[0]['title']
        url = '/#first-delivery' if lesson_id == 'hello' else '/#first-steps' + ('' if lesson_id == 'chapter' else '/' + lesson_id)
        return ([word for lesson in selected for word in lesson.get('vocabulary', [])],
                {'lesson_id': lesson_id, 'title': title, 'url': url}, 'first-steps:' + lesson_id)
    return _create_context_flashcards(generator, credential, source)


def create_game_flashcards(generator, credential, session_id, items=None):
    """Keep the contextual words from this completed game in native practice."""
    def source(conn):
        access = require_access(conn, credential, generator.clock(), adult=True)
        row = conn.execute('SELECT * FROM journey_game_sessions WHERE id=? AND profile_id=?',
                           (session_id, access['profile_id'])).fetchone()
        if row is None:
            raise LearningError('not_found', 'This game was not found for your profile.', 404)
        if row['completed_at'] is None:
            raise LearningError('game_incomplete', 'Finish this game before making its flashcards.', 409)
        content = json.loads(row['content_json'])
        candidates = content.get('vocabulary_refs', [])
        if items is not None:
            if (not isinstance(items, list) or not items or len(items) > 100
                    or any(not isinstance(item, str) for item in items)
                    or len(set(items)) != len(items)):
                raise LearningError('invalid_input', 'Choose at least one word from this game.')
            available = {_identity(candidate) for candidate in candidates}
            if not set(items) <= available:
                raise LearningError('invalid_input', 'Choose words from this saved game.')
            candidates = [candidate for candidate in candidates if _identity(candidate) in items]
        return (candidates, {'lesson_id': 'game:' + row['game_id'], 'title': content['title'], 'topic': 'Journey games',
                             'url': '/#games/session/' + row['id']}, 'journey-game:' + row['game_id'])
    return _create_context_flashcards(generator, credential, source)


def _create_context_flashcards(generator, credential, source_loader):
    # Both entry points share native identities, media jobs and retired-card
    # handling. A game replay cannot silently create the same cards again.
    with transaction(generator.db_path, write=True) as conn:
        candidates, origin, request_prefix = source_loader(conn)
        title = origin['title']
        owner = generator._owner(conn, credential)
        if not candidates:
            raise LearningError('no_lesson_cards', 'This lesson has no flashcard words yet.', 409)
        content_hash = payload_hash(candidates)
        request_key = request_prefix + ':' + content_hash
        old = conn.execute('SELECT id,options FROM native_card_batches WHERE owner_id=? AND request_key=?', (owner, request_key)).fetchone()
        if old:
            batch_id = old['id']
            options = json.loads(old['options'])
            source = options['first_steps']
        else:
            topic = origin.get('topic', TOPIC)
            source = dict(origin) | {'study_url': '#flashcards?topic=' + quote(topic), 'reused': 0}
            options = {'kind': 'ru-cloze', 'quantity': len(candidates), 'audio': True, 'image': True, 'topic': topic, 'first_steps': source}
            batch_id = identifier()
            conn.execute('INSERT INTO native_card_batches VALUES (?,?,?,?,?,?)', (batch_id, owner, request_key, content_hash, encoded(options), generator.clock()))
            # Keep one contextual card per owner across lesson and chapter buttons.
            # Retired/removed cards do not get silently recreated by a later click.
            previous = _prior_items(conn, owner, batch_id)
            for candidate in candidates:
                reference = _native_reference(conn, owner, batch_id, candidate)
                if reference:
                    previous.setdefault(_identity(candidate), reference)
            included = set(previous)
            position = 0
            for candidate in candidates:
                identity = _identity(candidate)
                if identity in included:
                    continue
                word = _game_word(conn, candidate) if origin['lesson_id'].startswith('game:') else LessonCards.resolve(conn, {**candidate, 'surface': candidate['form']})
                word['first_steps_source'] = {'identity': identity, 'title': title, 'url': source['url'],
                                             'kind': origin.get('kind', 'game' if origin['lesson_id'].startswith('game:') else 'lesson')}
                if candidate.get('assets'):
                    word['reused_assets'] = candidate['assets']
                if candidate.get('source'):
                    word['practice_source'] = candidate['source']
                response = {'english': candidate['target_meaning'], 'sentence': candidate['sentence'],
                            'sentence_english': candidate['translation'], 'notes': candidate.get('notes', '')}
                item_id = identifier()
                generator.pack(item_id, word, options, response)  # Validate the cloze before saving vocabulary or batch.
                conn.execute('INSERT INTO native_card_generation_items(id,batch_id,position,selection,response) VALUES (?,?,?,?,?)',
                             (item_id, batch_id, position, encoded(word), encoded(response)))
                included.add(identity)
                position += 1
        # Persist selected item references rather than treating an unfinished
        # earlier request as a ready card. Also repair pre-reference batches on
        # their normal idempotent create route without moving or copying items.
        previous = _prior_items(conn, owner, batch_id)
        for candidate in candidates:
            reference = _native_reference(conn, owner, batch_id, candidate)
            if reference:
                previous.setdefault(_identity(candidate), reference)
        wanted = dict.fromkeys(_identity(candidate) for candidate in candidates)
        source['reused_items'] = [previous[identity] for identity in wanted if identity in previous]
        source['reused'] = len(source['reused_items'])
        if origin['lesson_id'].startswith('game:') and source['reused_items']:
            word_ids = {candidate.get('word_id') for candidate in candidates}
            source['study_url'] = '#flashcards' + ('?word_id=' + str(next(iter(word_ids))) if len(word_ids) == 1 and None not in word_ids else '')
        if origin['lesson_id'] == 'hello':
            source['url'] = '/#first-delivery'
        conn.execute('UPDATE native_card_batches SET options=? WHERE id=?', (encoded(options), batch_id))
    generator.enrich_batch(credential, batch_id)
    return generator.read(credential, batch_id)


def create_word_jumble(db_path, credential, now):
    """An ordinary saved Word Jumble game, using language from the chapter."""
    with transaction(db_path, write=True) as conn:
        profile_id, lessons = _completed(conn, credential, now)
        _selection(lessons, 'chapter')
        # A repeat click opens the same saved practice instead of making clutter.
        game_id = 'first-steps-' + payload_hash({'profile': profile_id, 'chapter': 'first-steps-v1'})[:32]
        if not conn.execute('SELECT 1 FROM word_jumble_games WHERE id=? AND owner_profile_id=?', (game_id, profile_id)).fetchone():
            conn.execute('INSERT INTO word_jumble_games(id,topic,difficulty,words,created_at,owner_profile_id) VALUES (?,?,?,?,?,?)',
                         (game_id, 'first_steps', 'easy', encoded(['это', 'письмо', 'сумка']), datetime.fromtimestamp(now, timezone.utc).isoformat(), profile_id))
    return {'url': '/word_jumble/load/' + game_id}
