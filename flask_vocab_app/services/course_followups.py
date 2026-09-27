"""Reuse owned, completed letters in the existing word and writing stores."""
import json
import logging

from flask import current_app
from repositories.learning_repository import LearningError, encoded, timestamp, transaction
from repositories.writing_repository import WritingRepository
from services.course_progression import _attempt, key
from services.game_vocabulary_discovery import read_word, save_word
from services.story_vocabulary import _with_mnemonic

logger = logging.getLogger(__name__)


def _completed(conn, profile_id, attempt_id):
    row = _attempt(conn, profile_id, attempt_id)
    if row['status'] == 'active':
        raise LearningError('checkpoint_unfinished', 'Check your answers before using this letter for more practice.', 409)
    return json.loads(row['frozen_json'])['variant']


def writing_followup(conn, profile_id, attempt_id, request_id):
    key(request_id, 'Request ID')
    variant = _completed(conn, profile_id, attempt_id)
    task = variant.get('writing_task')
    if not task:
        raise LearningError('writing_unavailable', 'This earlier letter has no writing task.', 404)
    existing = conn.execute("SELECT item_id FROM course_checkpoint_followups WHERE attempt_id=? AND profile_id=? AND kind='writing' AND source_key='reply'",
                            (attempt_id, profile_id)).fetchone()
    if existing:
        exercise_id = existing['item_id']
    else:
        from services.curriculum import curriculum
        topic = next(t for t in curriculum()['topics'] if t['id'] == task['topic_id'])
        exercise_id = WritingRepository.create_in_transaction(conn, task, topic['id'], 'A1', 30, profile_id)
        conn.execute('INSERT INTO course_checkpoint_followups VALUES (?,?,?,?,?,?)',
                     (attempt_id, profile_id, 'writing', 'reply', exercise_id, timestamp()))
    return {'href': f'/writing/load/{exercise_id}', 'exercise_id': exercise_id}


def create_flashcards(generator, credential, attempt_id):
    """Ordinary native batches preserve contextual forms, media and schedules."""
    from services.first_steps_practice import _create_context_flashcards
    from repositories.learning_repository import require_access
    from services.curriculum import get_topic
    def source(conn):
        access = require_access(conn, credential, generator.clock(), adult=True)
        variant = _completed(conn, access['profile_id'], attempt_id)
        if not variant.get('flashcard_candidates') or not variant.get('writing_task'):
            raise LearningError('flashcards_unavailable', 'This earlier letter has no flashcard set.', 404)
        row = _attempt(conn, access['profile_id'], attempt_id)
        topic = get_topic(variant['writing_task']['topic_id'])
        origin = {'lesson_id': 'course:' + row['release_id'] + ':' + variant['id'],
                  'kind': 'course', 'release_id': row['release_id'], 'attempt_id': attempt_id,
                  'title': variant['letter_title'], 'url': '/#journey/checkpoint/' + attempt_id,
                  'topic': topic['id']}
        return variant.get('flashcard_candidates', []), origin, 'course:' + row['release_id'] + ':' + variant['id']
    return _create_context_flashcards(generator, credential, source)


def capture_vocabulary(db_path, profile_id, attempt_id, word, request_id, lemma=None, pos=None):
    key(request_id, 'Request ID')
    if not isinstance(word, str) or not 1 <= len(word) <= 100:
        raise LearningError('invalid_word', 'Choose one Russian word from the letter.', 422)
    with transaction(db_path, write=True) as conn:
        variant = _completed(conn, profile_id, attempt_id)
        content = {'vocabulary_refs': [{'sentence': variant['letter']}]}
        reading = read_word(conn, content, word)
        if not reading.get('lemma') and not reading.get('choices'):
            raise LearningError('unknown_word', 'This spelling could not be found in the Russian dictionary.', 422)
        if lemma is None or pos is None:
            if not reading.get('lemma') or not reading.get('pos'):
                return _with_mnemonic(conn, reading) | {'needs_choice': True}
            lemma, pos = reading['lemma'], reading['pos']
        result = save_word(conn, content, word, lemma, pos, profile_id=profile_id)
        conn.execute('INSERT OR IGNORE INTO course_checkpoint_followups VALUES (?,?,?,?,?,?)',
                     (attempt_id, profile_id, 'word', encoded([word, lemma, pos]), result['word_id'], timestamp()))
    # Same enrichment service as story capture: canonical morphology commits
    # first; paid mnemonic/topic calls run outside the database write lock.
    pending = False
    try:
        enrichment = current_app.extensions['services']['SyncService'].enrich_words([result['word_id']])
        pending = bool(enrichment['pending'])
    except Exception as error:
        logger.warning('Course vocabulary enrichment pending (%s)', type(error).__name__)
        pending = True
    with transaction(db_path) as conn:
        result = _with_mnemonic(conn, result)
    return result | {'needs_choice': False, 'status': 'saved', 'enrichment_pending': pending,
                     'href': '/vocab', 'flashcards_href': f"/#generate?word_id={result['word_id']}"}
