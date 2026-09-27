"""Diagnostic criteria attached to owned, immutable tasks and saved responses.

Call within the activity's write transaction. The caller owns authentication;
these adapters independently check profile/task/response relationships. Nothing
here changes a target observation, reward, milestone or continuation right.
"""
import hashlib
import json
import re

from contracts.curriculum import validate_task_contract, validate_judgements
from repositories.learning_repository import encoded, identifier, timestamp
from services.speaking_evidence import validate_speaking_contract, validate_speaking_judgements, verify_audio_source


def _positive_decimal(value, label):
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or int(value) < 1 or str(int(value)) != value:
        raise ValueError(f'Invalid {label} identity.')
    return int(value)


def _writing_row(conn, profile_id, task_key):
    exercise_id = _positive_decimal(task_key, 'writing task')
    row = conn.execute("SELECT task,required_words FROM writing_exercises WHERE id=? "
                       "AND COALESCE(owner_profile_id,'personal-learning')=?", (exercise_id, profile_id)).fetchone()
    if row is None:
        raise LookupError('Writing not found for this profile.')
    return row


def _writing(conn, profile_id, task_key):
    row = _writing_row(conn, profile_id, task_key)
    return {'task': row[0], 'required_words': json.loads(row[1])}


def _comprehension_task(conn, profile_id, task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', task_id):
        raise ValueError('Invalid comprehension task identity.')
    row = conn.execute('SELECT t.payload_json,t.created_at,t.revision,s.text,s.topic,s.difficulty,t.story_id '
                       'FROM comprehension_tasks t JOIN saved_stories s ON s.id=t.story_id '
                       "WHERE t.id=? AND t.profile_id=? AND COALESCE(s.owner_profile_id,'personal-learning')=?",
                       (task_id, profile_id, profile_id)).fetchone()
    if row is None:
        raise LookupError('Comprehension task not found for this profile.')
    payload = json.loads(row[0])
    if (not isinstance(payload, dict) or not isinstance(payload.get('text'), str) or not payload['text'].strip()
            or (payload.get('text'), payload.get('topic'), payload.get('difficulty')) != tuple(row[3:6])
            or type(payload.get('prior_feedback')) is not bool
            or any(not isinstance(payload.get(key), str) for key in ('audio_url', 'image_url'))
            or type(row[1]) is not int or row[1] < 0 or type(row[2]) is not int or row[2] < 0):
        raise ValueError('Comprehension task does not match its owned story.')
    questions, contracts = payload.get('questions'), payload.get('contracts')
    if (not isinstance(questions, list) or not 5 <= len(questions) <= 20
            or any(not isinstance(value, str) or not value.strip() or len(value) > 2000 or '\x00' in value for value in questions)
            or len(set(questions)) != len(questions)
            or not isinstance(contracts, dict)):
        raise ValueError('Comprehension requires its saved questions and criterion mapping.')
    for index in contracts:
        if (not isinstance(index, str) or not index.isascii() or not index.isdecimal()
                or str(int(index)) != index or not 0 <= int(index) < len(questions)):
            raise ValueError('Comprehension criteria reference an unknown question.')
    from services.comprehension_evidence import validate_contracts
    validate_contracts(payload)
    return {'task_id': task_id, 'profile_id': profile_id, 'payload': payload, 'created_at': row[1], 'revision': row[2], 'story_id': row[6]}


def _comprehension(conn, profile_id, task_key):
    if not isinstance(task_key, str) or ':' not in task_key:
        raise ValueError('Invalid comprehension question identity.')
    task_id, index = task_key.rsplit(':', 1)
    task = _comprehension_task(conn, profile_id, task_id)
    if (not index.isascii() or not index.isdecimal() or str(int(index)) != index
            or not 0 <= int(index) < len(task['payload']['questions'])):
        raise ValueError('Comprehension question is not in the saved task.')
    return {**task, 'question_index': int(index)}


def _comprehension_attempt(conn, profile_id, task, source_key):
    if not isinstance(source_key, str) or not source_key:
        raise ValueError('Invalid comprehension attempt identity.')
    columns = {item[1] for item in conn.execute('PRAGMA table_info(comprehension_attempts)')}
    receipt_column = 'support_receipts_json' if 'support_receipts_json' in columns else "'[]'"
    row = conn.execute('SELECT answers_json,assessment_json,support_json,created_at,request_sha256,submission_id,rowid,' + receipt_column + ' '
                       'FROM comprehension_attempts '
                       'WHERE id=? AND task_id=? AND profile_id=?',
                       (source_key, task['task_id'], profile_id)).fetchone()
    if row is None:
        raise ValueError('The comprehension response is not saved for this task and profile.')
    answers, assessment, support = (json.loads(value) for value in row[:3])
    from repositories.comprehension_repository import request_digest, validate_answers, validate_assessment
    validate_answers(task['payload'], answers)
    validate_assessment(task['payload'], answers, assessment)
    ordinal = conn.execute('SELECT COUNT(*) FROM comprehension_attempts WHERE task_id=? AND rowid<?',
                           (task['task_id'], row[6])).fetchone()[0]
    from services.comprehension_support import attempt_support
    expected_support = attempt_support(conn, task, ordinal, json.loads(row[7]), created_at=row[3])
    if (support != expected_support or type(row[3]) is not int or row[3] < task['created_at']
            or row[4] != request_digest(task['task_id'], ordinal, answers)
            or not isinstance(row[5], str) or not re.fullmatch(r'[a-f0-9]{32}', row[5])):
        raise ValueError('Comprehension assessment does not match the saved response and criteria.')
    return answers, assessment, support


def _comprehension_response(conn, profile_id, task_key, source_key):
    task = _comprehension(conn, profile_id, task_key)
    answers, assessment, support = _comprehension_attempt(conn, profile_id, task, source_key)
    index = str(task['question_index'])
    if index not in assessment['criterion_reports']:
        raise ValueError('This comprehension question has no frozen criterion report.')
    return answers[task['question_index']], assessment['criterion_reports'][index], support


def _speaking(conn, profile_id, task_key):
    if not isinstance(task_key, str) or not task_key:
        raise ValueError('Invalid Speaking session identity.')
    row = conn.execute('SELECT scenario_json,state FROM live_conversation_sessions WHERE id=? AND profile_id=?',
                       (task_key, profile_id)).fetchone()
    if row is None:
        raise LookupError('Speaking session not found for this profile.')
    return {'scenario': json.loads(row[0]), 'state': row[1]}


def _speaking_response(conn, profile_id, task_key, source_key):
    _speaking(conn, profile_id, task_key)
    if source_key != task_key:
        raise ValueError('Speaking evidence belongs to a different session.')
    row = conn.execute('SELECT state,report_json FROM speaking_reviews WHERE session_id=?', (task_key,)).fetchone()
    if row is None or row[0] != 'ready' or not row[1]:
        raise ValueError('Speaking evidence requires a saved original-audio review.')
    review = json.loads(row[1])
    if not isinstance(review, dict) or review.get('basis') != 'audio_review':
        raise ValueError('Speaking evidence cannot be derived from captions.')
    source = verify_audio_source(conn, profile_id, task_key, review.get('audio_source'))
    return review, source


def _unit(conn, profile_id, task_key):
    if not isinstance(task_key, str) or ':' not in task_key:
        raise ValueError('Invalid curriculum-unit task identity.')
    session_id, item_id = task_key.split(':', 1)
    row = conn.execute('SELECT v.payload,v.status,v.content_id FROM learning_sessions s '
                       'JOIN learning_content_versions v ON v.id=s.version_id '
                       "WHERE s.id=? AND s.profile_id=? AND s.kind='activity'", (session_id, profile_id)).fetchone()
    if row is None:
        raise LookupError('Curriculum session not found for this profile.')
    pack = json.loads(row[0])
    if (not isinstance(pack, dict) or pack.get('kind') != 'activity'
            or not isinstance(pack.get('id'), str) or not pack['id'].startswith('curriculum-unit:')
            or pack['id'] != row[2]):
        raise ValueError('This session is not an authored curriculum unit.')
    matches = [item for item in pack.get('items', []) if item.get('id') == item_id]
    if len(matches) != 1 or matches[0].get('type') not in ('choice', 'controlled_text', 'listening_choice'):
        raise ValueError('The unit item is not a unique saved practice task.')
    return {'item': matches[0], 'session_id': session_id, 'item_id': item_id,
            'content_id': pack['id'], 'status': row[1]}


def _owned_task(conn, profile_id, activity, task_key):
    if activity in ('translation', 'word_jumble'):
        from services.production_evidence import owned_task
        return owned_task(conn, profile_id, activity, task_key)
    if activity == 'writing':
        return _writing(conn, profile_id, task_key)
    if activity == 'curriculum_unit':
        return _unit(conn, profile_id, task_key)
    if activity == 'speaking':
        return _speaking(conn, profile_id, task_key)
    if activity == 'comprehension':
        return _comprehension(conn, profile_id, task_key)
    raise ValueError('This activity has no criterion evidence adapter yet.')


def _check_content(task, activity, contract):
    validate_task_contract(contract)
    if contract['activity'] != activity:
        raise ValueError('Criteria belong to a different activity.')
    if activity in ('translation', 'word_jumble'):
        from services.production_evidence import check_content
        check_content(task, activity, contract)
    elif activity == 'writing':
        if (contract['content'].get('task') != task['task']
                or contract['content'].get('required_words') != task['required_words']):
            raise ValueError('Criteria must describe the exact saved writing task and vocabulary guidance.')
    elif activity == 'speaking':
        validate_speaking_contract(contract, task['scenario'])
    elif activity == 'comprehension':
        from services.curriculum import normalize_level
        payload, index = task['payload'], task['question_index']
        content = contract['content']
        mode = payload.get('practice_mode', 'reading')
        if (payload['contracts'].get(str(index)) != contract
                or content.get('text') != payload['text'] or content.get('questions') != payload['questions']
                or type(content.get('question_index')) is not int or content['question_index'] != index
                or ('question' in content and content['question'] != payload['questions'][index])
                or contract['level'] != normalize_level(payload['difficulty'], legacy='reading')
                or any(criterion['response_mode'] != mode + '_response'
                       or criterion['evidence_scope'] != mode + '_comprehension' for criterion in contract['criteria'])):
            raise ValueError('Comprehension criteria must describe the exact saved question and open response mode.')
    elif activity == 'curriculum_unit':
        controlled = task['item']['type'] == 'controlled_text'
        listening = task['item']['type'] == 'listening_choice'
        modes = ('listening_selection',) if listening else ('controlled_text',) if controlled else ('contextual_selection', 'reading_selection')
        if (contract['content'].get('item') != task['item']
                or len(contract['criteria']) != 1
                or contract['criteria'][0]['response_mode'] not in modes
                or contract['criteria'][0]['evidence_scope'] != ('controlled_production' if controlled else 'reference')
                or (controlled and contract['rubric_version'] != 'authored-controlled-form-v1')
                or (listening and (contract['rubric_version'] != 'authored-listening-choice-v1'
                    or contract['support'] != {'allowed': ['hint', 'transcript'], 'independence_breakers': ['hint', 'transcript']}))):
            raise ValueError('A unit contract must describe its exact saved item and matching response mode.')


def save_contract(conn, profile_id, activity, task_key, contract):
    task = _owned_task(conn, profile_id, activity, task_key)
    _check_content(task, activity, contract)
    frozen = encoded(contract)
    row = conn.execute('SELECT id,contract_json FROM activity_task_contracts '
                       'WHERE profile_id=? AND activity=? AND task_key=?', (profile_id, activity, task_key)).fetchone()
    if row:
        if row[1] != frozen:
            raise ValueError('A saved task contract cannot be replaced.')
        return row[0]
    if activity in ('translation', 'word_jumble'):
        from services.production_evidence import answered as has_answers
        answered = has_answers(conn, activity, task_key)
    elif activity == 'writing':
        answered = conn.execute('SELECT 1 FROM writing_attempts WHERE exercise_id=? LIMIT 1', (int(task_key),)).fetchone()
    elif activity == 'comprehension':
        answered = conn.execute('SELECT 1 FROM comprehension_attempts WHERE task_id=? LIMIT 1', (task['task_id'],)).fetchone()
    elif activity == 'speaking':
        if task['state'] != 'new':
            raise ValueError('Speaking criteria must be frozen when the session is created.')
        answered = (conn.execute('SELECT 1 FROM live_conversation_recordings WHERE session_id=? LIMIT 1', (task_key,)).fetchone()
                    or conn.execute('SELECT 1 FROM speaking_reviews WHERE session_id=?', (task_key,)).fetchone())
    else:
        if task['status'] != 'published':
            raise ValueError('A new unit contract needs published content.')
        answered = conn.execute('SELECT 1 FROM activity_attempts WHERE session_id=? AND item_id=? LIMIT 1',
                                (task['session_id'], task['item_id'])).fetchone()
    if answered:
        raise ValueError('Criteria must be frozen before the first assessed response.')
    contract_id = identifier()
    conn.execute('INSERT INTO activity_task_contracts VALUES (?,?,?,?,?,?,?)',
                 (contract_id, profile_id, activity, task_key, frozen, contract['contract_sha256'], timestamp()))
    return contract_id


def load_contract(conn, profile_id, activity, task_key):
    row = conn.execute('SELECT contract_json,contract_sha256 FROM activity_task_contracts '
                       'WHERE profile_id=? AND activity=? AND task_key=?', (profile_id, activity, task_key)).fetchone()
    if row is None:
        # Legacy Writing rows deliberately tolerate unreadable word lists in
        # the repository. Prove ownership without interpreting absent criteria.
        if activity == 'writing':
            _writing_row(conn, profile_id, task_key)
        else:
            _owned_task(conn, profile_id, activity, task_key)
        return None
    task = _owned_task(conn, profile_id, activity, task_key)
    contract = json.loads(row[0])
    _check_content(task, activity, contract)
    if row[1] != contract['contract_sha256']:
        raise ValueError('Stored contract identity does not match its frozen content.')
    return contract


def _saved_response(conn, profile_id, activity, task_key, source_key):
    task = _owned_task(conn, profile_id, activity, task_key)
    if activity in ('translation', 'word_jumble'):
        from services.production_evidence import saved_response
        response, _, _ = saved_response(conn, profile_id, activity, task_key, source_key)
        return response, None
    if activity == 'comprehension':
        response, _, _ = _comprehension_response(conn, profile_id, task_key, source_key)
        return response, None
    if activity == 'writing':
        attempt_id = _positive_decimal(source_key, 'writing attempt')
        attempt = conn.execute('SELECT response FROM writing_attempts WHERE id=? AND exercise_id=?',
                               (attempt_id, int(task_key))).fetchone()
        if attempt is None:
            raise ValueError('The writing response is not saved for this task.')
        return attempt[0], None
    if not isinstance(source_key, str) or not source_key:
        raise ValueError('Invalid activity attempt identity.')
    attempt = conn.execute('SELECT answer,assisted,outcome,policy_version FROM activity_attempts '
                           'WHERE id=? AND session_id=? AND item_id=?',
                           (source_key, task['session_id'], task['item_id'])).fetchone()
    if attempt is None:
        raise ValueError('The selected answer is not saved for this unit item.')
    if task['item']['type'] == 'controlled_text' and attempt[3] != 'authored-controlled-form-v1':
        raise ValueError('This saved controlled-form marking version is unavailable.')
    from contracts.learning import assess_activity_answer
    from repositories.learning_repository import LearningError
    try:
        response_text, correct = assess_activity_answer(task['item'], json.loads(attempt[0]))
    except LearningError as error:
        raise ValueError('The saved response does not match its issued response mode.') from error
    if attempt[2] != ('correct' if correct else 'incorrect'):
        raise ValueError('The stored outcome contradicts the issued answer key.')
    support = ['hint'] if attempt[1] else []
    if task['item']['type'] == 'listening_choice':
        from services.learning_listening import item_support
        saved = item_support(conn, task['session_id'], task['item'])
        support = saved['support']
        if (attempt[3] != 'authored-listening-choice-v1'
                or (not saved['listened'] and 'transcript' not in support)
                or bool(attempt[1]) != bool(support)):
            raise ValueError('Listening evidence must match its playback and support receipts.')
    return response_text, {'assisted': bool(attempt[1]), 'correct': correct, 'support': support}


def save_report(conn, profile_id, activity, task_key, source_key, report, *, response_text=None, audio_source=None, support=()):
    contract = load_contract(conn, profile_id, activity, task_key)
    if contract is None:
        raise ValueError('The task did not define these criteria before assessment.')
    unit = None
    if activity == 'speaking':
        review, saved_source = _speaking_response(conn, profile_id, task_key, source_key)
        if response_text is not None or audio_source != saved_source or report != review.get('criterion_report') or support:
            raise ValueError('Speaking evidence must match its saved audio review; independence remains unverified.')
        validate_speaking_judgements(contract, review, saved_source['duration_ms'])
        digest = saved_source['sha256']
    elif activity in ('comprehension', 'translation', 'word_jumble'):
        if activity == 'comprehension':
            saved_text, saved_report, saved_support = _comprehension_response(conn, profile_id, task_key, source_key)
        else:
            from services.production_evidence import saved_response
            saved_text, saved_report, saved_support = saved_response(conn, profile_id, activity, task_key, source_key)
        if (saved_text != response_text or report != saved_report or audio_source is not None
                or not isinstance(support, (list, tuple)) or list(support) != saved_support):
            raise ValueError('Activity evidence must match the exact saved answer, report and support.')
        validate_judgements(contract, report, response_text=response_text)
        digest = hashlib.sha256(response_text.encode('utf-8')).hexdigest()
    else:
        saved_text, unit = _saved_response(conn, profile_id, activity, task_key, source_key)
        if saved_text != response_text or audio_source is not None:
            raise ValueError('The report must use the exact saved response.')
        validate_judgements(contract, report, response_text=response_text)
        digest = hashlib.sha256(response_text.encode('utf-8')).hexdigest()
    if (not isinstance(support, (list, tuple)) or any(not isinstance(item, str) for item in support)
            or len(support) != len(set(support)) or set(support) - set(contract['support']['allowed'])):
        raise ValueError('Unknown support use.')
    if unit is not None:
        if set(support) != set(unit['support']):
            raise ValueError('Support must match the saved unit attempt.')
        judgement, criterion = report['judgements'][0], contract['criteria'][0]
        if (judgement['outcome'] != ('satisfied' if unit['correct'] else 'not_satisfied')
                or judgement['score'] != (criterion['max_score'] if unit['correct'] else 0)):
            raise ValueError('Unit evidence must retain the deterministic saved result.')
    contract_id = conn.execute('SELECT id FROM activity_task_contracts '
                              'WHERE profile_id=? AND activity=? AND task_key=?',
                              (profile_id, activity, task_key)).fetchone()[0]
    frozen, supports = encoded(report), encoded(sorted(support))
    row = conn.execute('SELECT id,response_sha256,report_json,support_json FROM activity_criterion_reports '
                       'WHERE contract_id=? AND source_key=?', (contract_id, source_key)).fetchone()
    if row:
        if tuple(row[1:]) != (digest, frozen, supports):
            raise ValueError('This saved response already has a different criterion report.')
        return row[0]
    report_id = identifier()
    conn.execute('INSERT INTO activity_criterion_reports VALUES (?,?,?,?,?,?,?,?)',
                 (report_id, contract_id, profile_id, source_key, digest, frozen, supports, timestamp()))
    return report_id


def reports_for_task(conn, profile_id, activity, task_key):
    if load_contract(conn, profile_id, activity, task_key) is None:
        return {}
    rows = conn.execute('SELECT r.source_key,r.report_json,r.support_json FROM activity_criterion_reports r '
                        'JOIN activity_task_contracts c ON c.id=r.contract_id AND c.profile_id=r.profile_id '
                        'WHERE c.profile_id=? AND c.activity=? AND c.task_key=? ORDER BY r.created_at,r.rowid',
                        (profile_id, activity, task_key))
    return {row[0]: {'report': json.loads(row[1]), 'support': json.loads(row[2])} for row in rows}


def _validate_comprehension_evidence(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='comprehension_tasks'").fetchone():
        return
    tasks = {}
    for task_id, profile_id in conn.execute('SELECT id,profile_id FROM comprehension_tasks ORDER BY rowid').fetchall():
        task = _comprehension_task(conn, profile_id, task_id)
        from services.comprehension_support import receipts
        receipts(conn, task)
        tasks[(task_id, profile_id)] = task
        for index, frozen in task['payload']['contracts'].items():
            task_key = task_id + ':' + index
            saved = load_contract(conn, profile_id, 'comprehension', task_key)
            if saved is None or saved != frozen:
                raise ValueError('A comprehension question is missing its original frozen contract.')
            created_at = conn.execute('SELECT created_at FROM activity_task_contracts '
                                      "WHERE profile_id=? AND activity='comprehension' AND task_key=?",
                                      (profile_id, task_key)).fetchone()[0]
            first = conn.execute('SELECT MIN(created_at) FROM comprehension_attempts WHERE task_id=?', (task_id,)).fetchone()[0]
            if (type(created_at) is not int or created_at < task['created_at']
                    or (first is not None and created_at > first)):
                raise ValueError('Comprehension criteria must precede the first saved response.')
    contract_count = conn.execute("SELECT COUNT(*) FROM activity_task_contracts WHERE activity='comprehension'").fetchone()[0]
    if contract_count != sum(len(task['payload']['contracts']) for task in tasks.values()):
        raise ValueError('Comprehension has criteria outside its frozen question sets.')
    counts = {}
    for source_key, task_id, profile_id in conn.execute(
            'SELECT id,task_id,profile_id FROM comprehension_attempts ORDER BY rowid').fetchall():
        task = tasks.get((task_id, profile_id))
        if task is None:
            raise ValueError('A comprehension attempt has no matching owned task.')
        answers, assessment, support = _comprehension_attempt(conn, profile_id, task, source_key)
        counts[(task_id, profile_id)] = counts.get((task_id, profile_id), 0) + 1
        for index, contract in task['payload']['contracts'].items():
            report = assessment['criterion_reports'][index]
            validate_judgements(contract, report, response_text=answers[int(index)])
            row = conn.execute('SELECT r.report_json,r.support_json,r.response_sha256 FROM activity_criterion_reports r '
                               'JOIN activity_task_contracts c ON c.id=r.contract_id AND c.profile_id=r.profile_id '
                               "WHERE c.profile_id=? AND c.activity='comprehension' AND c.task_key=? AND r.source_key=?",
                               (profile_id, task_id + ':' + index, source_key)).fetchone()
            response_digest = hashlib.sha256(answers[int(index)].encode('utf-8')).hexdigest()
            if (row is None or json.loads(row[0]) != report or json.loads(row[1]) != support
                    or row[2] != response_digest):
                raise ValueError('A saved comprehension assessment is missing its matching criterion evidence.')
    report_count = conn.execute('SELECT COUNT(*) FROM activity_criterion_reports r JOIN activity_task_contracts c '
                                "ON c.id=r.contract_id WHERE c.activity='comprehension'").fetchone()[0]
    if report_count != sum(count * len(tasks[key]['payload']['contracts']) for key, count in counts.items()):
        raise ValueError('Comprehension has criterion reports outside its saved attempts.')
    story_exposure = {}
    for key, task in tasks.items():
        count = counts.get(key, 0)
        story_key = (task['story_id'], key[1])
        if task['revision'] != count:
            raise ValueError('Comprehension revision does not match its saved attempts.')
        if task['payload']['prior_feedback'] != story_exposure.get(story_key, False):
            raise ValueError('Comprehension must retain feedback exposure from earlier question sets.')
        story_exposure[story_key] = task['payload']['prior_feedback'] or bool(count)


def validate_saved_evidence(conn, *, audio_root=None):
    """Audit an offline import without changing contracts, reports or outcomes."""
    from services.learning_listening import validate_saved_support
    validate_saved_support(conn)
    _validate_comprehension_evidence(conn)
    from services.production_evidence import validate_saved_evidence as validate_production
    validate_production(conn)
    for row in conn.execute('SELECT profile_id,activity,task_key FROM activity_task_contracts').fetchall():
        load_contract(conn, row[0], row[1], row[2])
    rows = conn.execute('SELECT r.id,r.profile_id,c.activity,c.task_key,r.source_key,r.report_json,r.support_json '
                        'FROM activity_criterion_reports r JOIN activity_task_contracts c '
                        'ON c.id=r.contract_id AND c.profile_id=r.profile_id').fetchall()
    if len(rows) != conn.execute('SELECT COUNT(*) FROM activity_criterion_reports').fetchone()[0]:
        raise ValueError('An imported report has no matching owned contract.')
    for row in rows:
        options = {}
        if row[2] == 'speaking':
            _, source = _speaking_response(conn, row[1], row[3], row[4])
            verify_audio_source(conn, row[1], row[3], source, audio_root=audio_root)
            options['audio_source'] = source
        else:
            response, _ = _saved_response(conn, row[1], row[2], row[3], row[4])
            options['response_text'] = response
        # This exact key already exists. save_report's idempotency branch only
        # compares it; it cannot insert, replace or refresh the saved record.
        existing = save_report(conn, row[1], row[2], row[3], row[4], json.loads(row[5]),
                               **options, support=json.loads(row[6]))
        if existing != row[0]:
            raise ValueError('An imported report changed identity.')
