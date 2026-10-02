"""Authored teaching sequences using the normal activity and Writing stores."""
from copy import deepcopy
from functools import lru_cache
import json
import hashlib
from pathlib import Path

from contracts.curriculum import freeze_task_contract
from contracts.learning import key, validate_pack, assess_activity_answer
from repositories.learning_repository import LearningError, encoded, identifier, require_access, timestamp, transaction
from repositories.writing_repository import WritingRepository
from services.activity_evidence import load_contract, save_contract, save_report
from services.curriculum_requirement_map import requirement_index

UNIT_IDS = ('location-destination-v1', 'possession-absence-v1',
            'objects-recipients-v1', 'present-actions-v1', 'time-routine-v1',
            'noun-adjective-agreement-v1', 'personal-reference-v1', 'basic-motion-v1',
            'numbers-quantities-v1', 'social-exchanges-v1', 'needs-company-v1',
            'action-aspect-v1', 'origins-and-destinations-v1', 'connected-messages-v1',
            'instrumental-activities-professions-v1')
DATA_DIR = Path(__file__).resolve().parents[1] / 'data' / 'curriculum_units'
# This unit has no prepared recordings. Do not infer playback from a unit ID.
LISTENING_IDS = {unit_id: unit_id.removesuffix('-v1') + '-listening-v1' for unit_id in UNIT_IDS
                 if unit_id != 'instrumental-activities-professions-v1'}


def listening_content(unit_id):
    if unit_id not in LISTENING_IDS:
        raise LearningError('content_unavailable', 'Listening is not available for this unit yet.', 404)
    identity = LISTENING_IDS[unit_id]
    content = json.loads((DATA_DIR / (identity + '.json')).read_text(encoding='utf-8'))
    directory = Path(__file__).resolve().parents[1] / 'static/audio/course/curriculum' / identity
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if content['unit_id'] != unit_id or content['id'] != identity or manifest['content_id'] != identity:
        raise ValueError('Listening content identity changed.')
    for item in content['items']:
        clip = manifest['clips'][item['id']]
        if hashlib.sha256(item['transcript'].encode('utf-8')).hexdigest() != clip['text_sha256']:
            raise ValueError('Published transcript changed. Create a new audio version.')
        expected = '/static/audio/course/curriculum/' + identity + '/' + item['id'] + '.mp3'
        if item['audio_url'] != expected:
            raise ValueError('Listening recording belongs to another question.')
        item['audio'] = {'url': expected, 'sha256': clip['audio_sha256'], 'duration_ms': round(clip['duration'] * 1000)}
    return content


def listening_available(unit_id):
    """Offer playback only when every clip still matches its saved manifest."""
    if unit_id not in LISTENING_IDS:
        return False
    from services.learning_listening import verify_audio
    try:
        for item in _pack({'id': unit_id}, 'listening')['items']:
            verify_audio(item)
    except (LearningError, ValueError, OSError, KeyError):
        return False
    return True


@lru_cache(maxsize=32)
def _load(unit_id):
    if unit_id not in UNIT_IDS:
        raise LookupError('Learning unit not found.')
    unit = json.loads((DATA_DIR / (unit_id + '.json')).read_text(encoding='utf-8'))
    if unit['id'] != unit_id:
        raise ValueError('Learning unit identity changed.')
    # Each issued stage has its own immutable pack identity. The original
    # choice pack stays unchanged when a later response mode is introduced.
    for stage in ('practice', 'forms') + (('listening',) if listening_available(unit_id) else ()):
        pack = validate_pack(_pack(unit, stage))
        for question, item in zip(_questions(unit, stage), pack['items']):
            _practice_contract(unit, item, question, 'validation')
    task = writing_task(unit)
    WritingRepository.validate_task(task)
    WritingRepository.validate_curriculum_contract(task['curriculum_contract'], task['task'],
                                                   task['required_words'], unit['level'])
    return unit


def get_unit(unit_id):
    unit = deepcopy(_load(unit_id))
    # Presentation availability is derived from prepared media, not a promise
    # in a content draft. It is not included in an issued task contract.
    unit['listening_available'] = listening_available(unit_id)
    if unit['listening_available']:
        listening = listening_content(unit_id)
        unit['listening_title'] = listening['title']
        unit['listening_title_ru'] = listening['title_ru']
    return unit


def unit_summaries():
    return [{k: unit[k] for k in ('id', 'level', 'topic_id', 'title', 'title_ru', 'summary', 'summary_ru')}
            for unit in (get_unit(unit_id) for unit_id in UNIT_IDS)]


def _questions(unit, stage):
    if stage == 'listening':
        return listening_content(unit['id'])['items']
    return unit['forms']['questions'] if stage == 'forms' else unit['questions']


def _pack(unit, stage='practice'):
    if stage not in ('practice', 'forms', 'listening'):
        raise LookupError('Learning stage not found.')
    if stage == 'listening':
        listening = listening_content(unit['id'])
        identity = unit['id'] + ':' + listening['version']
        return {'schema_version': 1, 'id': 'curriculum-unit:' + identity, 'kind': 'activity',
                'title': listening['title'], 'source': 'Original application practice: ' + identity,
                'items': [{'id': q['id'], 'type': 'listening_choice',
                           **{k: q[k] for k in ('prompt', 'choices', 'answer', 'hint', 'audio', 'transcript')}}
                          for q in listening['items']]}
    forms = stage == 'forms'
    identity = unit['id'] + (':' + unit['forms']['version'] if forms else '')
    fields = ('prompt', 'accepted_answers', 'answer', 'hint') if forms else ('prompt', 'choices', 'answer', 'hint')
    return {'schema_version': 1, 'id': 'curriculum-unit:' + identity, 'kind': 'activity',
            'title': unit['forms']['title'] if forms else unit['title'],
            'source': 'Original application practice: ' + identity,
            'items': [{'id': q['id'], 'type': 'controlled_text' if forms else 'choice', **{k: q[k] for k in fields}}
                      for q in _questions(unit, stage)]}


def _spec(unit, task_id, activity, content, criteria):
    return {'schema_version': 1, 'contract_version': 'curriculum-task-v1',
            'reference_version': 'torfl-reference-v1', 'task_id': task_id, 'activity': activity,
            'content_version': unit['id'], 'level': unit['level'], 'topic_ids': [unit['topic_id']],
            'purpose': 'practice', 'content': content, 'rubric_version': unit['id'],
            'support': {'allowed': ['hint'], 'independence_breakers': ['hint']}, 'criteria': criteria}


def _criterion(requirement_id, criterion_id, target_id, expectation, *, mode=None, scope='reference'):
    requirement = requirement_index()[requirement_id]
    return {'id': criterion_id, 'target_id': target_id, 'requirement_id': requirement_id,
            'response_mode': mode or requirement['response_mode'], 'evidence_scope': scope,
            'expectation': expectation, 'max_score': 2, 'source_refs': requirement['source_refs']}


def _practice_contract(unit, item, question, session_id):
    controlled = item['type'] == 'controlled_text'
    criterion = _criterion(question['requirement_id'], question['id'],
                           'unit.' + unit['id'] + '.' + question['id'], question['expectation'],
                           mode='controlled_text' if controlled else None,
                           scope='controlled_production' if controlled else 'reference')
    spec = _spec(unit, session_id + ':' + item['id'], 'curriculum_unit',
        {'item': item, 'explanation': question['explanation'], 'unit_id': unit['id']}, [criterion])
    if controlled:
        spec['content_version'] = unit['id'] + ':' + unit['forms']['version']
        spec['rubric_version'] = 'authored-controlled-form-v1'
    if item['type'] == 'listening_choice':
        spec['content_version'] = unit['id'] + ':' + listening_content(unit['id'])['version']
        spec['rubric_version'] = 'authored-listening-choice-v1'
        spec['support'] = {'allowed': ['hint', 'transcript'], 'independence_breakers': ['hint', 'transcript']}
    return freeze_task_contract(spec)


def _unit_for_pack(pack):
    if pack['id'].startswith('curriculum-unit:g1:'):
        return None
    prefix = 'curriculum-unit:'
    if not pack['id'].startswith(prefix):
        return None
    if pack['id'].startswith('curriculum-unit:sequence:'):
        return None
    identity = pack['id'][len(prefix):]
    unit_id, separator, version = identity.partition(':')
    unit = get_unit(unit_id)
    if not separator:
        stage = 'practice'
    elif version == unit['forms']['version']:
        stage = 'forms'
    elif unit_id in LISTENING_IDS and version == listening_content(unit_id)['version']:
        stage = 'listening'
    else:
        raise ValueError('Unknown published unit stage version.')
    if _pack(unit, stage) != pack:
        raise ValueError('Published unit changed. Retain its original content and create a new version.')
    return unit, stage


def freeze_practice(conn, profile_id, session_id, pack):
    if pack['id'].startswith('curriculum-unit:g1:'):
        from services.curriculum_fresh_practice import freeze
        return freeze(conn, profile_id, session_id, pack)
    origin = _unit_for_pack(pack)
    if origin is None:
        return
    unit, stage = origin
    for item, question in zip(pack['items'], _questions(unit, stage)):
        save_contract(conn, profile_id, 'curriculum_unit', session_id + ':' + item['id'],
                      _practice_contract(unit, item, question, session_id))


def observe_answer(conn, profile_id, session_id, pack, item, attempt_id, answer, assisted, *, support=None):
    if not pack['id'].startswith('curriculum-unit:'):
        return
    if pack['id'].startswith('curriculum-unit:sequence:'):
        from services.curriculum_sequences import observe_answer as observe_sequence_answer
        return observe_sequence_answer(conn, profile_id, session_id, item, attempt_id, answer,
                                       support if support is not None else ['hint'] if assisted else [])
    task_key = session_id + ':' + item['id']
    contract = load_contract(conn, profile_id, 'curriculum_unit', task_key)
    if contract is None:
        raise ValueError('The practice task has no saved criteria.')
    text, correct = assess_activity_answer(item, answer)
    criterion = contract['criteria'][0]
    report = {'contract_sha256': contract['contract_sha256'], 'judgements': [{
        'criterion_id': criterion['id'], 'outcome': 'satisfied' if correct else 'not_satisfied',
        'score': criterion['max_score'] if correct else 0,
        'feedback': contract['content']['explanation'],
        'evidence': [{'quote': text, 'start': 0, 'end': len(text)}]}]}
    save_report(conn, profile_id, 'curriculum_unit', task_key, attempt_id, report,
                response_text=text, support=support if support is not None else ['hint'] if assisted else [])


def practice_context(pack):
    if pack['id'].startswith('curriculum-unit:g1:'):
        from services.curriculum_fresh_practice import origin
        return origin(pack)
    origin = _unit_for_pack(pack)
    if origin is None:
        return None
    unit, stage = origin
    return {'href': '/curriculum/units/' + unit['id'], 'title': unit['title'],
            'explanations': {q['id']: q['explanation'] for q in _questions(unit, stage)}}


def start_practice(db_path, credential, unit_id, request_id, *, expected_profile_id, stage='practice'):
    from services.learning_service import LearningService
    key(request_id, 'Request ID')
    unit = get_unit(unit_id)
    if stage == 'listening' and not unit['listening_available']:
        # A missing recording must not strand an already issued activity: its
        # saved transcript remains available as explicitly supported practice.
        with transaction(db_path) as conn:
            profile = require_access(conn, credential, timestamp(), profile_id=expected_profile_id)
            active = conn.execute(
                "SELECT s.id FROM learning_sessions s JOIN learning_content_versions v ON v.id=s.version_id "
                "WHERE s.profile_id=? AND v.content_id=? AND s.status='active' ORDER BY s.created_at DESC LIMIT 1",
                (profile['id'], 'curriculum-unit:' + unit_id + ':listening-v1')).fetchone()
        if active:
            return LearningService(db_path).read(credential, active['id'])
        raise LearningError('audio_unavailable', 'This recording is unavailable. Your other practice is still available.', 409)
    pack = _pack(unit, stage)
    with transaction(db_path, write=True) as conn:
        profile = require_access(conn, credential, timestamp(), profile_id=expected_profile_id)
        row = conn.execute('SELECT id,payload,status FROM learning_content_versions WHERE content_id=? ORDER BY version DESC LIMIT 1',
                           (pack['id'],)).fetchone()
        if row:
            if row['payload'] != encoded(pack) or row['status'] != 'published':
                raise LearningError('content_unavailable', 'This practice is being updated. Your saved work is kept.', 409)
            version_id = row['id']
        else:
            version_id = identifier()
            now = timestamp()
            conn.execute('INSERT INTO learning_content(id,kind,created_at) VALUES (?,?,?)', (pack['id'], 'activity', now))
            conn.execute("INSERT INTO learning_content_versions(id,content_id,version,title,payload,source,status,approved_by,approved_at,created_at) "
                         "VALUES (?,?,1,?,?,?,'published','application-authored practice',?,?)",
                         (version_id, pack['id'], pack['title'], encoded(pack), pack['source'], now, now))
        active = conn.execute("SELECT id FROM learning_sessions WHERE profile_id=? AND version_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
                              (profile['id'], version_id)).fetchone()
        profile_id = profile['id']
    service = LearningService(db_path)
    if active:
        return service.read(credential, active['id'])
    return service.start(credential, {'profile_id': profile_id, 'version_id': version_id, 'submission_id': request_id})


def writing_task(unit):
    task = deepcopy(unit['writing'])
    # Retain the original unit's issued contract exactly. New versions carry
    # their own communicative criterion, rather than inheriting a location task.
    focus = unit.get('writing_focus', {
        'requirement_id': 'a1.writing.personal-message', 'id': 'clear-meeting-message',
        'expectation': 'Write an original message to a friend that identifies your current place, your destination and where you will wait. '
                       'Accept short intelligible sentences and natural alternatives. Do not require a greeting, word count or a particular set of places.'})
    spec = _spec(unit, 'unit-writing:' + unit['id'], 'writing', deepcopy(task), [
        _criterion(focus['requirement_id'], focus['id'], 'unit.' + unit['id'] + '.message', focus['expectation'])])
    spec['support'] = {'allowed': ['model_answer'], 'independence_breakers': ['model_answer']}
    # Grammar corrections remain useful tutor feedback. Original writing is not
    # relabelled as a multiple-choice or narrowly controlled form exercise.
    task['curriculum_contract'] = freeze_task_contract(spec)
    return task


def start_writing(db_path, credential, unit_id, *, expected_profile_id):
    unit = get_unit(unit_id)
    with transaction(db_path, write=True) as conn:
        profile = require_access(conn, credential, timestamp(), profile_id=expected_profile_id)
        existing = conn.execute("SELECT task_key FROM activity_task_contracts WHERE profile_id=? AND activity='writing' "
                                "AND json_extract(contract_json,'$.content_version')=? ORDER BY created_at DESC LIMIT 1",
                                (profile['id'], unit_id)).fetchone()
        if existing:
            # The same unit resumes its saved draft and feedback.
            load_contract(conn, profile['id'], 'writing', existing['task_key'])
            return int(existing['task_key'])
        return WritingRepository.create_in_transaction(conn, writing_task(unit), unit['topic_id'], unit['level'], 30, profile['id'])
