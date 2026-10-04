"""Optional vocabulary help from the learner's frozen generated passage.

Explicit captures retain a versioned source in the durable command receipt,
retrievable through ``saved_words`` after the activity finishes. This is source
provenance, not a prepared flashcard: generated passages have no full sentence
translation, and unannotated words have no established contextual meaning.
They must not enter the complete-example cache until those details and the
contextual morphology are prepared. Normal vocabulary card generation remains
available, but does not yet reuse these original passage sentences automatically.
"""
from hashlib import sha256
import json
import re

from contracts.learning import fields, key, revision
from repositories.learning_repository import LearningError, encoded, payload_hash, transaction
from services.game_vocabulary_discovery import POSITIONS, read_word, save_word
from services.learning_content import normalize_form
from services.learning_listening import capture_shared_support, current_item_support, record_support
from services.story_vocabulary import _with_mnemonic, enrich_captured_word

SOURCE_VERSION = 'passage-vocabulary-source-v1'
TOKEN = re.compile(r'[А-Яа-яЁё][А-Яа-яЁё\u0300-\u036f]*(?:-[А-Яа-яЁё][А-Яа-яЁё\u0300-\u036f]*)*')


def _content(conn, profile_id, session_id, item, word, offset):
    row = conn.execute('SELECT document_json FROM curriculum_situations WHERE session_id=? AND profile_id=?',
                       (session_id, profile_id)).fetchone()
    if not row or not row[0]:
        raise LearningError('not_found', 'Word help is unavailable for this passage.', 404)
    text = item.get('passage') if item['type'] != 'listening_choice' else item['transcript']
    if not isinstance(text, str):
        raise LearningError('not_found', 'This activity has no saved passage.', 404)
    # Offsets identify occurrences, not just spellings. The client cannot supply
    # its own sentence, translation, lemma annotation or grammatical evidence.
    tokens = TOKEN.finditer(text)
    if not any(token.start() == offset and token.group() == word for token in tokens):
        raise LearningError('invalid_word', 'Choose a word from this saved passage.', 422)
    start = 0
    for boundary in re.finditer(r'(?<=[.!?…])\s+|\n\s*\n', text):
        if boundary.end() <= offset:
            start = boundary.end()
        elif boundary.start() >= offset + len(word):
            end = boundary.start()
            break
    else:
        end = len(text)
    sentence = text[start:end].strip()
    sentence_start = start + len(text[start:end]) - len(text[start:end].lstrip())
    response = json.loads(row[0])['response']
    if response['text'] != text:
        raise LearningError('content_unavailable', 'Reopen this saved activity before choosing a word.', 409)
    references = [{'sentence': sentence}]
    matching_forms = [token for token in TOKEN.finditer(sentence)
                      if normalize_form(token.group()) == normalize_form(word)]
    for annotation in response.get('new_vocabulary', []):
        # Current annotations identify a sentence, not a token occurrence.
        # A repeated homograph may carry different meanings/POS in that same
        # sentence; neither occurrence may inherit an unlocated annotation.
        if len(matching_forms) != 1:
            continue
        if normalize_form(annotation['form']) != normalize_form(word):
            continue
        if annotation['sentence'] != sentence:
            continue
        references.insert(0, {**annotation, 'target_meaning': annotation['meaning_en']})
    return {'vocabulary_refs': references, 'source': {
        'version': SOURCE_VERSION, 'kind': 'practice_passage', 'item_id': item['id'],
        'mode': 'listening' if item['type'] == 'listening_choice' else 'reading',
        'passage_sha256': sha256(text.encode('utf-8')).hexdigest(),
        'word_offset': offset, 'context_offset': offset - sentence_start,
    }}


def saved_words(learning, access_id, session_id):
    """Read explicitly retained source records without lookup or provider work.

The receipt owns the exact form, chosen lexical reading and sentence. Its source
offset distinguishes homographs, while the hash binds it to the frozen passage.
Repeated capture requests collapse to one record per occurrence and reading.
Missing translations are deliberately absent, never filled with a word gloss.
"""
    with transaction(learning.db_path) as conn:
        _, saved, _, pack = learning._owned_session(conn, access_id, session_id)
        records = {}
        for row in conn.execute('SELECT submission_id,result FROM learning_commands WHERE session_id=? ORDER BY created_at,rowid', (session_id,)):
            word = json.loads(row['result']).get('word', {})
            source = word.get('source', {})
            if source.get('version') != SOURCE_VERSION:
                continue
            identity = (source['passage_sha256'], source['word_offset'], word['lemma'], word['pos'])
            if identity in records:
                continue
            records[identity] = {
                **{name: word[name] for name in ('word', 'lemma', 'pos', 'word_id', 'context', 'meaning') if name in word},
                'source': {**source, 'session_id': saved['id'], 'version_id': saved['version_id'],
                           'capture_id': row['submission_id'], 'title': pack['title']},
                'prepared_example': False,
            }
        return {'session_id': saved['id'], 'words': list(records.values())}


def command(learning, access_id, session_id, data, *, capture=False):
    fields(data, {'submission_id', 'expected_revision', 'item_id', 'word', 'offset'}
           | ({'lemma', 'pos'} if capture else set()))
    key(data['submission_id']); key(data['item_id']); revision(data['expected_revision'])
    if (not isinstance(data['word'], str) or not 1 <= len(data['word']) <= 100
            or type(data['offset']) is not int or data['offset'] < 0):
        raise LearningError('invalid_word', 'Choose one Russian word from this passage.', 422)
    if capture and (not isinstance(data['lemma'], str) or not 1 <= len(data['lemma']) <= 100
                    or not isinstance(data['pos'], str) or data['pos'] not in POSITIONS):
        raise LearningError('invalid_reading', 'Choose the word that fits this sentence.', 422)
    digest = payload_hash({'operation': 'save_passage_word' if capture else 'lookup_passage_word', **data})
    with transaction(learning.db_path, write=True) as conn:
        profile, saved, _, pack = learning._owned_session(conn, access_id, session_id)
        cached = conn.execute('SELECT payload_hash,result FROM learning_commands WHERE session_id=? AND submission_id=?',
                              (session_id, data['submission_id'])).fetchone()
        if cached:
            if cached[0] != digest:
                raise LearningError('idempotency_conflict', 'This request ID was used for another action.', 409)
            result = json.loads(cached[1])
        else:
            if saved['revision'] != data['expected_revision']:
                raise LearningError('stale_revision', 'The activity changed. Reopen the current question.', 409,
                                    {'current_session': learning._snapshot(conn, session_id, pack)})
            if saved['status'] != 'active' or pack['items'][saved['current_index']]['id'] != data['item_id']:
                raise LearningError('wrong_item', 'Choose a word from the current question.', 409)
            item = pack['items'][saved['current_index']]
            if item['type'] == 'listening_choice' and 'transcript' not in current_item_support(conn, session_id, item, pack, saved['current_index'])['support']:
                raise LearningError('transcript_required', 'Open the transcript before choosing a word.', 409)
            content = _content(conn, profile['id'], session_id, item, data['word'], data['offset'])
            word = (save_word(conn, content, data['word'], data['lemma'], data['pos'], profile_id=profile['id'])
                    if capture else read_word(conn, content, data['word']))
            if capture:
                word['source'] = content['source']
            now = learning.clock()
            capture_shared_support(conn, session_id, pack, now)
            if item['type'] == 'listening_choice':
                record_support(conn, session_id, item, 'help', now)
            else:
                # Word help can resolve any remaining question about this text.
                # Keep past answers intact and do not disclose the saved hint.
                for pending in pack['items'][saved['current_index']:]:
                    if pending.get('passage') == item['passage']:
                        conn.execute('INSERT OR IGNORE INTO learning_hint_usage VALUES (?,?)', (session_id, pending['id']))
            conn.execute('UPDATE learning_sessions SET revision=revision+1,updated_at=? WHERE id=?', (now, session_id))
            result = {**learning._snapshot(conn, session_id, pack), 'word': _with_mnemonic(conn, word)}
            conn.execute('INSERT INTO learning_commands VALUES (?,?,?,?,?)',
                         (session_id, data['submission_id'], digest, encoded(result), now))
    if capture:
        # Commit lexical identity/support first. Retrying an uncertain command
        # reuses both, while incomplete metered enrichment can still be finished.
        try:
            result['word'] = enrich_captured_word(learning.db_path, result['word'])
        except LearningError as error:
            error.details['current_session'] = result
            raise
    return result
