"""Vocabulary capture from an owned story through the shared lexical pipeline."""
from hashlib import sha256
import logging

from flask import current_app, session, request
from uuid import uuid4

from repositories import StoryRepository
from repositories.learning_repository import LearningError, transaction
from services.ai_trial_budget import TrialDenied
from services.game_vocabulary_discovery import POSITIONS, read_word, save_word
from services.sync_service import SyncService

logger = logging.getLogger(__name__)


def story_key(text):
    return sha256(text.encode('utf-8')).hexdigest()


def _validate_word(word):
    if not isinstance(word, str) or not 1 <= len(word) <= 100:
        raise LearningError('invalid_word', 'Choose one Russian word from this story.', 422)


def _source(db_path, source):
    from repositories.comprehension_repository import ComprehensionRepository

    # A cached page is not an ownership grant. Profile changes can leave its
    # session data behind, and omitting an id must not make a saved task legacy.
    cached = session.get('current_story_data')
    cached = cached if isinstance(cached, dict) else {}
    story_id = source.get('story_id')
    task_id = source.get('task_id')
    if story_id in (None, ''):
        story_id = cached.get('id')
        if task_id in (None, ''):
            task_id = cached.get('task_id')
    if task_id not in (None, '') and (not isinstance(task_id, str) or not 1 <= len(task_id) <= 100):
        raise LearningError('invalid_story', 'Reopen this story before choosing a word.', 422)
    if story_id in (None, '') and task_id:
        try:
            story_id = ComprehensionRepository(db_path).load(task_id)['story_id']
        except LookupError:
            raise LearningError('story_not_found', 'Reopen this story before choosing a word.', 404) from None
    if story_id not in (None, ''):
        if len(str(story_id)) > 20 or not str(story_id).isdigit():
            raise LearningError('invalid_story', 'Reopen this story before choosing a word.', 422)
        story_id = str(story_id)
        story = StoryRepository(db_path).load(story_id)
    else:
        story = cached
    if not isinstance(story, dict) or not story.get('text'):
        raise LearningError('story_not_found', 'Reopen this story before choosing a word.', 404)
    if source.get('story_key') != story_key(story['text']):
        raise LearningError('story_changed', 'This story has changed. Reopen it before choosing a word.', 409)
    # No browser-supplied sentence, meaning or morphology is trusted here.
    return ({'vocabulary_refs': [{'sentence': story['text']}]},
            {'story_id': story_id, 'task_id': task_id})


def _with_mnemonic(conn, result):
    for reading in [result, *result.get('choices', [])]:
        if reading.get('word_id'):
            row = conn.execute('SELECT lemma,topic,mnemonic FROM words WHERE id=?', (reading['word_id'],)).fetchone()
            if row:
                missing_hint = SyncService._missing_mnemonic(row['mnemonic'], row['lemma'])
                reading['mnemonic'] = '' if missing_hint else row['mnemonic']
                reading['enrichment_pending'] = missing_hint or SyncService._missing_topics(row['topic'])
    return result


def _record_word_help(db_path, word, source):
    """Record disclosed grammar/mnemonics before the popup or capture returns."""
    from repositories.comprehension_repository import ComprehensionRepository, ComprehensionConflict
    repository = ComprehensionRepository(db_path)
    saved_id = source.get('story_id')
    task = repository.latest(saved_id) if saved_id else None
    if source.get('task_id') and (not task or source['task_id'] != task['id']):
        raise LearningError('story_changed', 'Reopen this story before choosing a word.', 409)
    if not task or task['payload'].get('support_version') != 'comprehension-support-v1':
        return
    if request.method != 'POST':
        raise LearningError('support_request_required', 'Reload this story before choosing a word.', 405)
    try:
        repository.record_support(task['id'], task['revision'], uuid4().hex, 'hint', word=word)
    except ComprehensionConflict as error:
        raise LearningError('story_changed', str(error), 409) from None
    except (ValueError, LookupError):
        raise LearningError('invalid_word', 'Choose a word from the current story.', 422) from None


def lookup_story_word(db_path, word, source):
    _validate_word(word)
    content, source = _source(db_path, source)
    _record_word_help(db_path, word, source)
    with transaction(db_path) as conn:
        return _with_mnemonic(conn, read_word(conn, content, word))


def capture_story_word(db_path, word, lemma, pos, source):
    _validate_word(word)
    _validate_word(lemma)
    if not isinstance(pos, str) or pos not in POSITIONS:
        raise LearningError('invalid_reading', 'Choose the word that fits this sentence.', 422)
    content, source = _source(db_path, source)
    _record_word_help(db_path, word, source)
    with transaction(db_path, write=True) as conn:
        result = save_word(conn, content, word, lemma, pos)
    # The configured service meters hosted provider calls and keeps retries
    # idempotent. Commit morphology first; AI must never hold a write lock.
    try:
        enrichment = current_app.extensions['services']['SyncService'].enrich_words([result['word_id']])
    except TrialDenied as error:
        raise LearningError('vocabulary_enrichment_pending',
                            'The word is saved. ' + str(error), 429,
                            {'saved': True, 'word_id': result['word_id'], 'enrichment_pending': True}) from None
    except Exception as error:
        logger.warning('Story vocabulary enrichment failed (%s)', type(error).__name__)
        enrichment = {'pending': [result['word_id']]}
    if enrichment['pending']:
        raise LearningError('vocabulary_enrichment_pending',
                            'The word is saved. Its topics and memory hint could not be prepared yet. Retry to finish adding it.',
                            503, {'saved': True, 'word_id': result['word_id'], 'enrichment_pending': True})
    with transaction(db_path) as conn:
        return _with_mnemonic(conn, result)
