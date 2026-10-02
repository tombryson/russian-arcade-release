"""Explicit study follow-ups from owned feedback; original answers stay immutable."""
import json
import logging
import re
from urllib.parse import urlencode

from flask import current_app, has_request_context

from repositories.learning_repository import LearningError, transaction
from services.curriculum import LEVELS, normalize_level
from services.game_vocabulary_discovery import LABELS, read_word, save_word
from utils.activity_owner import activity_profile_id

logger = logging.getLogger(__name__)
READING_LABELS_RU = {'NOUN': 'существительное', 'ADJF': 'прилагательное', 'ADJS': 'краткое прилагательное',
    'COMP': 'сравнительная степень', 'VERB': 'глагол', 'INFN': 'глагол', 'PRTF': 'причастие',
    'PRTS': 'краткое причастие', 'GRND': 'деепричастие', 'NUMR': 'числительное', 'ADVB': 'наречие',
    'NPRO': 'местоимение', 'PRED': 'слово категории состояния', 'PREP': 'предлог', 'CONJ': 'союз',
    'PRCL': 'частица', 'INTJ': 'междометие'}


def capabilities():
    # The legacy sentence library has a different household owner. Do not offer
    # a learner action which would silently save into that adult workspace.
    permitted = has_request_context() and not current_app.config.get('PUBLIC_DEMO') and not current_app.config.get('WORD_POST_HOUSEHOLD_ENABLED')
    hosted_paused = has_request_context() and current_app.config.get('HOSTED_AI_TRIAL') and not current_app.config.get('AI_TRIAL_ENABLED')
    return {'phrasebook': bool(permitted), 'flashcards': bool(permitted and current_app.config.get('NATIVE_FLASHCARDS_ENABLED')
            and current_app.config.get('OPENAI_API_KEY') and not hosted_paused)}


def require_capability(kind):
    if not capabilities().get(kind):
        raise LearningError('study_unavailable', 'This study action is not available in this workspace.', 403)


def _sentences(text):
    if not isinstance(text, str):
        return []
    return list(dict.fromkeys(part.strip() for part in re.split(r'(?<=[.!?…])\s+|\n+', text)
        if 1 <= len(part.strip()) <= 1000 and re.search('[А-Яа-яЁё]', part) and not re.search('[A-Za-z]', part)))[:12]


def _speech_examples(result):
    """Use only clearly grounded corrections, never a silently repaired ASR."""
    transcript = result.get('transcript', '')
    if result.get('speech_status') not in {'russian', 'mixed'} or not isinstance(transcript, str):
        return []
    corrections = result.get('corrections') or []
    examples = []
    for sentence in _sentences(transcript):
        if any(span in sentence for span in result.get('uncertain_phrases', [])):
            continue
        updated = sentence
        for correction in corrections:
            original, replacement = correction.get('original'), correction.get('replacement')
            if (isinstance(original, str) and original and isinstance(replacement, str)
                    and transcript.count(original) == 1 and updated.count(original) == 1):
                updated = updated.replace(original, replacement, 1)
        if updated != sentence and 1 <= len(updated) <= 1000 and not re.search('[A-Za-z]', updated):
            examples.append(updated)
    return list(dict.fromkeys(examples))


def source(conn, profile_id, activity, identity):
    if activity == 'writing':
        row = conn.execute('SELECT a.example,e.id,e.topic,e.difficulty FROM writing_attempts a JOIN writing_exercises e ON e.id=a.exercise_id '
                           "WHERE a.id=? AND COALESCE(e.owner_profile_id,'personal-learning')=?", (identity, profile_id)).fetchone()
        if row:
            examples = _sentences(row['example'])
            data = {'topic': row['topic'], 'level': normalize_level(row['difficulty'], legacy='writing'), 'back_url': '/writing/load/' + str(row['id'])}
    elif activity == 'unit_exchange':
        row = conn.execute("SELECT result_json,contract_json,task_key FROM activity_review_submissions WHERE id=? AND profile_id=? AND activity='unit_exchange' AND review_status='reviewed'", (identity, profile_id)).fetchone()
        if row:
            contract = json.loads(row['contract_json'])
            examples = _speech_examples(json.loads(row['result_json']))
            data = {'topic': (contract.get('topic_ids') or ['general'])[0], 'level': contract['level'], 'back_url': '/#unit-exchange/' + row['task_key']}
    else:
        row = None
    if not row:
        raise LearningError('not_found', 'This feedback is not available for the selected profile.', 404)
    if not examples:
        raise LearningError('study_example_unavailable', 'This feedback has no suitable study sentence.', 409)
    return {**data, 'activity': activity, 'identity': str(identity), 'examples': examples}


def actions(conn, profile_id, activity, identity):
    allowed = capabilities()
    if not any(allowed.values()):
        return []
    try:
        source(conn, profile_id, activity, identity)
    except LearningError:
        return []
    base = f'/study/feedback/{activity}/{identity}'
    return [{'kind': kind, 'href': base + '?' + urlencode({'intent': kind}), 'label': label, 'label_ru': ru}
            for kind, label, ru in [('phrasebook', 'Save sentence', 'Сохранить фразу'), ('flashcards', 'Make flashcards', 'Создать карточки')]
            if allowed[kind]]


def chosen_example(data, index):
    if not isinstance(index, str) or not index.isdecimal() or len(index) > 3 or int(index) >= len(data['examples']):
        raise LearningError('invalid_example', 'Choose a sentence from this feedback.', 422)
    return data['examples'][int(index)]


def phrasebook_prefill(db_path, activity, identity, index):
    require_capability('phrasebook')
    with transaction(db_path) as conn:
        data = source(conn, activity_profile_id(conn), activity, identity)
    return {'added_russian': chosen_example(data, index), 'added_english': '', 'added_topic': data['topic'],
            'added_level': LEVELS.index(data['level']) + 1, 'add_open': True}


def word_choices(conn, text):
    content = {'vocabulary_refs': [{'sentence': text}]}
    choices = []
    for word in dict.fromkeys(re.findall(r'[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*', text)):
        found = read_word(conn, content, word)
        readings = found.get('choices') or ([found] if found.get('lemma') else [])
        for reading in readings:
            if reading.get('can_add') or reading.get('in_vocabulary'):
                choices.append({'value': json.dumps([word, reading['lemma'], reading['pos']], ensure_ascii=False),
                                'label': word + (' · ' + LABELS[reading['pos']] if len(readings) > 1 else ''),
                                'label_ru': word + (' · ' + READING_LABELS_RU[reading['pos']] if len(readings) > 1 else '')})
    return choices


def capture_for_cards(db_path, activity, identity, index, selection):
    require_capability('flashcards')
    try:
        reading = json.loads(selection) if isinstance(selection, str) and len(selection) <= 500 else None
    except (ValueError, TypeError):
        reading = None
    if not isinstance(reading, list) or len(reading) != 3 or any(not isinstance(value, str) or not 1 <= len(value) <= 100 for value in reading):
        raise LearningError('invalid_word', 'Choose one word from the study sentence.', 422)
    with transaction(db_path, write=True) as conn:
        profile_id = activity_profile_id(conn)
        data = source(conn, profile_id, activity, identity)
        text = chosen_example(data, index)
        result = save_word(conn, {'vocabulary_refs': [{'sentence': text}]}, *reading, profile_id=profile_id)
    # Exactly the same morphology + configured mnemonic/topic enrichment path
    # as explicit story capture. Never invent a translation on the lemma row.
    try:
        enrichment = current_app.extensions['services']['SyncService'].enrich_words([result['word_id']])
        if enrichment['pending']:
            raise LearningError('vocabulary_enrichment_pending', 'The word is saved. Its memory hint and topics are not ready yet. Try again to finish.', 503)
    except LearningError:
        raise
    except Exception as error:
        from services.ai_trial_budget import TrialDenied
        if isinstance(error, TrialDenied):
            raise LearningError('vocabulary_enrichment_pending', 'The word is saved. ' + str(error), 429) from None
        logger.warning('Study vocabulary enrichment pending (%s)', type(error).__name__)
        raise LearningError('vocabulary_enrichment_pending', 'The word is saved. Its memory hint and topics could not be prepared. Try again to finish.', 503) from None
    return result['word_id']
