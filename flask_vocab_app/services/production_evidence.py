"""Narrow observations from translation and vocabulary-supported composition.

The original task and response remain authoritative. These observations do not
establish independent writing, proficiency, rewards or progression gates.
"""
from copy import deepcopy
import hashlib
import json
import re

from contracts.curriculum import CONTRACT_VERSION, freeze_task_contract, validate_task_contract, validate_judgements
from services.curriculum import normalize_level
from services.torfl_requirements import VERSION, reference_for_level
from services.vocabulary_topics import TOPICS

CONTENT_VERSION = 'sentence-production-v1'
RUBRIC_VERSION = 'sentence-production-focus-v1'
TABLES = {'translation': ('sentences', 'translation_attempts', 'sentence_id'),
          'word_jumble': ('word_jumble_games', 'word_jumble_attempts', 'game_id')}
JUMBLE_FOCUS = {
    'A2': ('a1.language.time-and-reason-clauses',
           'Connect the two ideas through time or a reason, as requested. Accept either relationship and natural Russian alternatives.'),
    'B1': ('a2.language.cause-consequence',
           'Explain a reason or consequence of the described situation, preserving which event explains or follows from the other.'),
    'B2': ('b1.language.condition-concession-comparison',
           'Compare the two options and make clear the circumstances in which one would be chosen over the other.'),
}
REPORT_INSTRUCTION = '''Return criterion_report for the frozen curriculum_contract separately from ordinary tutor feedback.
Assess ONLY its explicit expectation, not every rule mentioned in curriculum background or every feature of the reference.
Accept valid synonyms, inflections, natural word order, ё/е and different constructions that satisfy the task.
A correct alternative which does not demonstrate the particular grammatical feature is insufficient_evidence with null score,
not a failed criterion or a reason to lower the ordinary tutor score. Uncertainty is also insufficient_evidence, never zero.
Score this narrow observation 2 satisfied, 1 partial, 0 not_satisfied; cite the learner's EXACT original words with Unicode
start/end offsets for every scored judgement. Never cite the reference, a correction, or an imagined answer as evidence.
Keep feedback brief and in the interface language. Supplied English or target words are task conditions, not independent writing.
Previous feedback is assistance. Do not infer mastery, a level pass, coins or eligibility from this report.'''


def translation_candidates(level):
    reference = reference_for_level(level)
    return {item['id']: item for item in reference['requirements'] if item['domain'] == 'language_use'} if reference else {}


def _text(value, label, maximum=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        raise ValueError(f'Invalid {label}.')


def _freeze(activity, task, focus, topic_id, level, reference):
    content = {**deepcopy(task), 'focus': deepcopy(focus), 'topic_id': topic_id}
    identity = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    rid = reference['id']
    return freeze_task_contract({
        'schema_version': 1, 'contract_version': CONTRACT_VERSION, 'reference_version': VERSION,
        'task_id': f'{activity}-production-{identity}', 'activity': activity,
        'content_version': CONTENT_VERSION, 'level': level, 'topic_ids': [topic_id],
        'purpose': 'diagnostic', 'content': content, 'rubric_version': RUBRIC_VERSION,
        'support': {'allowed': ['model_answer'], 'independence_breakers': ['model_answer']},
        'criteria': [{'id': 'language-focus', 'target_id': f'{activity}-production.{rid}', 'requirement_id': rid,
                      'response_mode': 'controlled_text', 'evidence_scope': 'controlled_production',
                      'expectation': focus['expectation'], 'max_score': 2, 'source_refs': reference['source_refs']}],
    })


def translation_contract(task, focus, topic_id):
    level = normalize_level(task['difficulty'], legacy='translation')
    candidates = translation_candidates(level)
    if not candidates:
        return None
    for key in ('sentence', 'english', 'topic'):
        _text(task.get(key), key)
    if topic_id not in TOPICS or (task['topic'] != 'any' and topic_id != task['topic']):
        raise ValueError('Translation requires its selected canonical topic.')
    if not isinstance(focus, dict) or set(focus) != {'requirement_id', 'english_excerpt', 'russian_excerpt', 'expectation'}:
        raise ValueError('Translation requires one explicit language focus.')
    rid = focus['requirement_id']
    if not isinstance(rid, str) or rid not in candidates:
        raise ValueError('Translation focus must use a language requirement at its selected level.')
    for key, source in (('english_excerpt', 'english'), ('russian_excerpt', 'sentence')):
        _text(focus[key], key)
        if focus[key] not in task[source]:
            raise ValueError('The language focus must cite the exact translation task.')
    _text(focus['expectation'], 'expectation')
    return _freeze('translation', {key: task[key] for key in ('sentence', 'english', 'topic', 'difficulty')},
                   focus, topic_id, level, candidates[rid])


def jumble_contract(task):
    """Only visible connective goals are mapped; unrestricted creativity stays so."""
    level, instruction = task['difficulty'], task.get('task_contract')
    if level not in JUMBLE_FOCUS or not isinstance(instruction, dict):
        return None
    if task['topic'] != 'any' and task['topic'] not in TOPICS:
        return None
    from services.word_jumble_service import TASK_INSTRUCTIONS
    if (instruction.get('target_level') != level or instruction.get('version') != 1
            or any(TASK_INSTRUCTIONS[level][lang] not in instruction.get('instruction', {}).get(lang, '')
                   for lang in ('en', 'ru'))):
        raise ValueError('Word Jumble criteria require their original visible instructions.')
    words = task.get('words')
    if not isinstance(words, list) or not words or any(not isinstance(word, str) or not word for word in words):
        raise ValueError('Word Jumble requires its supplied vocabulary.')
    rid, expectation = JUMBLE_FOCUS[level]
    ref = next(item for item in reference_for_level(rid[:2].upper())['requirements'] if item['id'] == rid)
    focus = {'requirement_id': rid, 'expectation': expectation,
             'instruction_en': TASK_INSTRUCTIONS[level]['en'], 'instruction_ru': TASK_INSTRUCTIONS[level]['ru']}
    return _freeze('word_jumble', {key: task[key] for key in ('words', 'topic', 'difficulty', 'task_contract')},
                   focus, task['topic'] if task['topic'] != 'any' else 'grammar', level, ref)


def check_content(task, activity, contract):
    validate_task_contract(contract)
    if activity == 'translation':
        expected = translation_contract(task, contract['content'].get('focus'), contract['content'].get('topic_id'))
    elif activity == 'word_jumble':
        expected = jumble_contract(task)
    else:
        raise ValueError('Unsupported production activity.')
    if expected is None or expected != contract:
        raise ValueError('Criteria must match the exact saved task, vocabulary and language focus.')


def production_report(contract, report, response):
    from services.writing_service import _ground_criterion_spans
    grounded = _ground_criterion_spans(report, response)
    return validate_judgements(contract, grounded, response_text=response)


def _task_key(activity, task_key):
    if activity not in TABLES or not isinstance(task_key, str):
        raise ValueError('Invalid production task identity.')
    if activity == 'translation':
        return _decimal(task_key)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', task_key):
        raise ValueError('Invalid Word Jumble identity.')
    return task_key


def _decimal(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or str(int(value)) != value or int(value) < 1:
        raise ValueError('Invalid saved attempt or sentence identity.')
    return int(value)


def owned_task(conn, profile_id, activity, task_key):
    identity = _task_key(activity, task_key)
    table = TABLES[activity][0]
    fields = 'sentence,english,topic,difficulty' if activity == 'translation' else 'words,topic,difficulty,task_json'
    row = conn.execute(f"SELECT {fields} FROM {table} WHERE id=? AND COALESCE(owner_profile_id,'personal-learning')=?",
                       (identity, profile_id)).fetchone()
    if row is None:
        raise LookupError('Practice not found for this profile.')
    if activity == 'translation':
        return dict(zip(('sentence', 'english', 'topic', 'difficulty'), row))
    return {'words': json.loads(row[0]), 'topic': row[1], 'difficulty': row[2],
            'task_contract': json.loads(row[3]) if row[3] else None}


def answered(conn, activity, task_key):
    identity = _task_key(activity, task_key)
    _, table, foreign = TABLES[activity]
    return conn.execute(f'SELECT 1 FROM {table} WHERE {foreign}=? LIMIT 1', (identity,)).fetchone()


def attempt_support(conn, activity, task_key, source_key=None):
    identity = _task_key(activity, task_key)
    _, table, foreign = TABLES[activity]
    condition, params = (' AND id<?', (identity, _decimal(source_key))) if source_key is not None else ('', (identity,))
    if conn.execute(f'SELECT 1 FROM {table} WHERE {foreign}=?{condition} LIMIT 1', params).fetchone():
        return ['model_answer']
    if activity == 'translation':
        receipt = conn.execute("SELECT v.after_attempt_id FROM translation_reference_views v JOIN sentences s ON s.id=v.sentence_id "
                               "WHERE v.sentence_id=? AND v.profile_id=COALESCE(s.owner_profile_id,'personal-learning')", (identity,)).fetchone()
        if receipt and receipt[0] is not None and not conn.execute(
                'SELECT 1 FROM translation_attempts WHERE id=? AND sentence_id=?', (receipt[0], identity)).fetchone():
            raise ValueError('A reference receipt cannot reference another task attempt.')
        if receipt and (source_key is None or receipt[0] is None or _decimal(source_key) > receipt[0]):
            return ['model_answer']
    return []


def saved_response(conn, profile_id, activity, task_key, source_key):
    owned_task(conn, profile_id, activity, task_key)
    _, table, foreign = TABLES[activity]
    row = conn.execute(f'SELECT response,criterion_report_json,criterion_support_json FROM {table} WHERE id=? AND {foreign}=?',
                       (_decimal(source_key), _task_key(activity, task_key))).fetchone()
    if row is None or not row[1] or row[2] is None:
        raise ValueError('The criterion report requires its saved original response and support.')
    report, support = json.loads(row[1]), json.loads(row[2])
    if support != attempt_support(conn, activity, task_key, source_key):
        raise ValueError('Assistance must match earlier saved feedback for this task.')
    return row[0], report, support


def validate_saved_evidence(conn):
    """Reject partial/forged imports, including missing or orphan reports."""
    from services.activity_evidence import load_contract, reports_for_task
    for sentence_id, profile_id, after_id in conn.execute('SELECT sentence_id,profile_id,after_attempt_id FROM translation_reference_views'):
        owned_task(conn, profile_id, 'translation', str(sentence_id))
        if load_contract(conn, profile_id, 'translation', str(sentence_id)) is None:
            raise ValueError('A reference receipt needs an owned scoped translation.')
        if after_id is not None and not conn.execute('SELECT 1 FROM translation_attempts WHERE id=? AND sentence_id=?',
                                                    (after_id, sentence_id)).fetchone():
            raise ValueError('A reference receipt cannot reference another task attempt.')
    for activity, (task_table, attempt_table, foreign) in TABLES.items():
        contracts = conn.execute('SELECT profile_id,task_key FROM activity_task_contracts WHERE activity=?', (activity,)).fetchall()
        for profile_id, task_key in contracts:
            contract = load_contract(conn, profile_id, activity, task_key)
            reports = reports_for_task(conn, profile_id, activity, task_key)
            attempts = conn.execute(f'SELECT id FROM {attempt_table} WHERE {foreign}=?', (_task_key(activity, task_key),)).fetchall()
            if set(reports) != {str(row[0]) for row in attempts}:
                raise ValueError('Every scoped production attempt needs its matching criterion report.')
            for (source_id,) in attempts:
                raw, report, support = saved_response(conn, profile_id, activity, task_key, str(source_id))
                validate_judgements(contract, report, response_text=raw)
                if reports[str(source_id)] != {'report': report, 'support': support}:
                    raise ValueError('The criterion report does not match its original assessed response.')
        orphan = conn.execute(f'''SELECT 1 FROM {attempt_table} a LEFT JOIN {task_table} t ON t.id=a.{foreign}
            LEFT JOIN activity_task_contracts c ON c.activity=? AND c.task_key=CAST(t.id AS TEXT)
            AND c.profile_id=COALESCE(t.owner_profile_id,'personal-learning')
            WHERE (a.criterion_report_json IS NOT NULL OR a.criterion_support_json IS NOT NULL) AND c.id IS NULL LIMIT 1''',
            (activity,)).fetchone()
        if orphan:
            raise ValueError('Production evidence has no matching owned frozen task.')


def present_details(item, language):
    """Use the same compact optional evidence summary as Writing."""
    contract = item.get('curriculum_contract')
    if contract is None:
        return
    from services.curriculum_requirement_map import requirement_index
    criteria = {criterion['id']: criterion for criterion in contract['criteria']}
    refs = requirement_index()
    outcomes = {'satisfied': ('Shown in this response', 'Есть в этом ответе'),
                'partial': ('Partly shown', 'Показано частично'),
                'not_satisfied': ('Needs practice', 'Стоит потренировать'),
                'insufficient_evidence': ('Not enough evidence', 'Недостаточно материала')}
    for attempt in item.get('attempts', []):
        attempt['criterion_details'] = [
            {'label': refs[criteria[judgement['criterion_id']]['requirement_id']]['label_ru' if language == 'ru' else 'label_en'],
             'outcome': outcomes[judgement['outcome']][language == 'ru'], 'feedback': judgement['feedback']}
            for judgement in attempt.get('criterion_report', {}).get('judgements', [])]
