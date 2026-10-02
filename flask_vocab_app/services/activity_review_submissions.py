"""Sequence adapters preserve exact originals before independently retryable review.

Providers run outside database transactions. Finishing writes the legacy activity
attempt, its criterion reports, allowed effects and review receipt together.
"""
import json
import sqlite3
import hashlib

from contracts.curriculum import validate_judgements
from repositories import activity_review_repository as reviews
from repositories.learning_repository import LearningError, encoded, identifier, payload_hash, timestamp, transaction
from repositories.writing_repository import WritingRepository, timestamp as writing_timestamp
from repositories.comprehension_repository import ComprehensionRepository, support_state, validate_answers, validate_assessment, request_digest
from services.activity_evidence import load_contract, save_contract, save_report
from services.progression import award, legacy_profile
from utils.activity_owner import activity_profile_id


def binding_for_task(conn, profile_id, activity, task_key):
    from services.curriculum_sequences import binding_for_task as lookup
    return lookup(conn, profile_id, activity, str(task_key))


def _binding(conn, profile_id, activity, task_key):
    binding = binding_for_task(conn, profile_id, activity, task_key)
    if not binding:
        raise LearningError('not_found', 'This task is not part of an owned lesson.', 404)
    policy = binding.get('effects_policy') or reviews.DEFAULT_POLICY
    if policy == 'activity-default-v1':
        policy = reviews.DEFAULT_POLICY
    if policy not in (reviews.DEFAULT_POLICY, reviews.TRANSFER_POLICY):
        raise LearningError('invalid_saved_task', 'This task has an unsupported effects policy.', 409)
    return policy


def create_writing_in_transaction(conn, profile_id, asset, contract_factory):
    task = {key: asset['content'][key] for key in ('title', 'title_en', 'task', 'task_en', 'required_words')}
    task['curriculum_contract'] = contract_factory(asset, identifier(), purpose='diagnostic')
    exercise_id = WritingRepository.create_in_transaction(conn, task, asset['topic_id'], asset['level'], 30, profile_id)
    return {'activity': 'writing', 'task_key': str(exercise_id), 'href': f'/writing/load/{exercise_id}'}


def create_comprehension_in_transaction(conn, profile_id, asset, contract_factory=None):
    from services.curriculum_sequence_content import reading_contracts
    from services.comprehension_evidence import SUPPORT_VERSION, validate_contracts
    identity = identifier()
    contracts = reading_contracts(asset, identity, purpose='diagnostic')
    content = asset['content']
    questions = [row['prompt_ru'] for row in content['questions']]
    payload = {'text': content['passage'], 'questions': questions, 'audio_url': '', 'image_url': '',
               'topic': asset['topic_id'], 'difficulty': asset['level'], 'contracts': contracts, 'prior_feedback': False,
               'practice_mode': 'reading', 'support_version': SUPPORT_VERSION, 'initial_support': [],
               'authored_unit_version': 'unit-reading-v1', 'authored_asset': asset}
    validate_contracts(payload)
    cursor = conn.execute('''INSERT INTO saved_stories(title,topic,difficulty,text,audio_url,image_url,
        questions,answers,feedback,score,owner_profile_id) VALUES (?,?,?,?,'','',?,'[]','[]',0,?)''',
        (asset['title_ru'], asset['topic_id'], asset['level'], content['passage'], encoded(questions), profile_id))
    story_id = cursor.lastrowid
    conn.execute("INSERT INTO story_title_translations VALUES (?,'en',?)", (story_id, asset['title']))
    conn.execute('INSERT INTO comprehension_tasks(id,story_id,profile_id,payload_json,created_at) VALUES (?,?,?,?,?)',
                 (identity, story_id, profile_id, encoded(payload), timestamp()))
    for index, contract in contracts.items():
        save_contract(conn, profile_id, 'comprehension', f'{identity}:{index}', contract)
    return {'activity': 'comprehension', 'task_key': identity, 'story_id': story_id, 'href': f'/comprehension/load/{story_id}'}


def _writing_task(conn, profile_id, task_key):
    row = conn.execute('''SELECT e.*,m.title,m.title_en,m.task_en,COALESCE(d.revision,0) AS revision
        FROM writing_exercises e JOIN writing_details m ON m.exercise_id=e.id
        LEFT JOIN writing_drafts d ON d.exercise_id=e.id
        WHERE e.id=? AND COALESCE(e.owner_profile_id,'personal-learning')=?''', (task_key, profile_id)).fetchone()
    if row is None:
        raise LearningError('not_found', 'This writing task is not available for the selected profile.', 404)
    task = dict(row)
    task['required_words'] = json.loads(task['required_words'])
    return task


def _snapshot(task, activity):
    if activity == 'writing':
        return {key: task[key] for key in ('id', 'task', 'task_en', 'title', 'title_en', 'required_words', 'difficulty', 'topic', 'min_words')}
    return {'id': task['id'], 'story_id': task['story_id'], 'title': task['title'], 'title_en': task['title_en'], 'payload': task['payload']}


def prior_feedback(conn, profile_id, activity, task):
    """Exact earlier elicitation stays familiar across new runs and editions."""
    def signature(value):
        if activity == 'writing':
            return {'task': value['task'], 'required_words': value['required_words']}
        if activity == 'comprehension':
            return {key: value['payload'][key] for key in ('text', 'questions')}
        content = value['asset']['content']
        return {'scene': content['scene'], 'prompts': [turn['prompt'] for turn in content['turns']]}
    target = signature(task)
    if activity == 'writing':
        for row in conn.execute("SELECT task_key FROM activity_support_disclosures WHERE profile_id=? AND activity='writing'", (profile_id,)):
            previous = _writing_task(conn, profile_id, row[0])
            if signature(previous) == target:
                contract = load_contract(conn, profile_id, 'writing', row[0])
                writing_help(conn, profile_id, row[0], contract)
                return True
    return any(signature(json.loads(row[0])) == target for row in conn.execute(
        "SELECT task_json FROM activity_review_submissions WHERE profile_id=? AND activity=? AND review_status='reviewed'", (profile_id, activity)))


def safe_scene(content):
    scene = content.get('scene', {})
    # These are the learner's authored situation, not the private marking key.
    # Transfer tasks may give their context in prose rather than a place map.
    return {'places': [{key: place[key] for key in ('id', 'ru', 'en')} for place in scene.get('places', [])],
            **{key: scene[key] for key in ('instruction', 'instruction_ru') if scene.get(key)}}


def writing_help(conn, profile_id, task_key, contract):
    row = conn.execute("SELECT * FROM activity_support_disclosures WHERE profile_id=? AND activity='writing' AND task_key=? AND kind='model_answer'",
                       (profile_id, str(task_key))).fetchone()
    model = contract['content'].get('model_answer')
    if not row:
        return None
    if (not isinstance(model, str) or row['contract_sha256'] != contract['contract_sha256']
            or row['content_sha256'] != hashlib.sha256(model.encode()).hexdigest()):
        raise ValueError('The example no longer matches its saved disclosure.')
    return {'id': row['id'], 'model_answer': model}


def disclose_writing_model(db_path, task_key, revision):
    with transaction(db_path, write=True) as conn:
        owner = activity_profile_id(conn)
        _binding(conn, owner, 'writing', task_key)
        task, contract = _owned(conn, owner, 'writing', task_key)
        cached = writing_help(conn, owner, task_key, contract)
        if cached:
            return cached
        if type(revision) is not int or revision != task['revision']:
            raise LearningError('stale_revision', 'Your work changed. Reload the saved task before opening help.', 409)
        if conn.execute("SELECT 1 FROM activity_review_submissions WHERE profile_id=? AND activity='writing' AND task_key=? AND review_status!='reviewed'",
                        (owner, str(task_key))).fetchone():
            raise LearningError('review_pending', 'Finish reviewing the saved original before opening an example.', 409)
        model = contract['content'].get('model_answer')
        if not isinstance(model, str) or not model.strip() or 'model_answer' not in contract['support']['allowed']:
            raise LearningError('not_found', 'This task has no saved example.', 404)
        conn.execute('INSERT INTO activity_support_disclosures VALUES (?,?,?,?,?,?,?,?)',
                     (identifier(), owner, 'writing', str(task_key), 'model_answer', contract['contract_sha256'], hashlib.sha256(model.encode()).hexdigest(), timestamp()))
        return writing_help(conn, owner, task_key, contract)


def _owned(conn, profile_id, activity, task_key):
    if activity == 'writing':
        task = _writing_task(conn, profile_id, task_key)
        contract = load_contract(conn, profile_id, activity, str(task_key))
    elif activity == 'comprehension':
        task = ComprehensionRepository._task(conn, str(task_key), profile_id)
        contract = task['payload']['contracts']
    else:
        raise LearningError('invalid_input', 'Unsupported activity.')
    return task, contract


def submit(db_path, activity, task_key, data, *, language='en'):
    if not isinstance(data, dict) or set(data) - {'submission_id', 'expected_revision', 'response'}:
        raise LearningError('invalid_input', 'Send the saved task revision and your response.')
    revision, response, submission_id = data.get('expected_revision'), data.get('response'), data.get('submission_id')
    if type(revision) is not int or revision < 0 or not isinstance(response, dict):
        raise LearningError('invalid_input', 'This reply needs the saved task revision.')
    with transaction(db_path, write=True) as conn:
        owner = activity_profile_id(conn)
        policy = _binding(conn, owner, activity, task_key)
        digest = reviews.request_hash(activity, task_key, revision, response)
        cached = reviews.existing(conn, owner, submission_id, digest)
        if cached:
            return reviews.public(cached)
        task, contract = _owned(conn, owner, activity, task_key)
        if task['revision'] != revision:
            raise LearningError('stale_revision', 'Your work changed in another tab. Reload the saved version.', 409)
        if activity == 'writing':
            if set(response) != {'text'}:
                raise LearningError('invalid_input', 'Send your original written response.')
            WritingRepository.validate_answer(response['text'], checking=True)
            support = ['model_answer'] if conn.execute('SELECT 1 FROM writing_attempts WHERE exercise_id=? LIMIT 1', (task_key,)).fetchone() else []
            help_used = writing_help(conn, owner, task_key, contract)
            receipts = [help_used['id']] if help_used else []
            if help_used:
                support = ['model_answer']
        else:
            if set(response) != {'answers'}:
                raise LearningError('invalid_input', 'Send the answers for this question set.')
            validate_answers(task['payload'], response['answers'])
            state = support_state(conn, task)
            support, receipts = state['support'], state['receipt_ids']
        snapshot = _snapshot(task, activity)
        snapshot['ui_language'] = 'ru' if language == 'ru' else 'en'
        if prior_feedback(conn, owner, activity, snapshot):
            support = sorted(set(support) | {'model_answer'})
        saved = reviews.save_original(conn, profile_id=owner, activity=activity, task_key=str(task_key), submission_id=submission_id,
            task_revision=revision, original=response, task=snapshot, contract=contract,
            support=support, support_receipts=receipts, effects_policy=policy)
        if activity == 'writing':
            conn.execute('''INSERT INTO writing_drafts(exercise_id,response,revision,updated_at) VALUES (?,?,?,?)
                ON CONFLICT(exercise_id) DO UPDATE SET response=excluded.response,revision=excluded.revision,updated_at=excluded.updated_at''',
                (task_key, response['text'], revision + 1, writing_timestamp()))
        return reviews.public(saved)


def load(db_path, identity, activity=None):
    with transaction(db_path) as conn:
        saved = reviews.get(conn, activity_profile_id(conn), identity)
        if activity and saved['activity'] != activity:
            raise LearningError('not_found', 'This reply belongs to a different activity.', 404)
        return reviews.public(saved)


def task_work_state(conn, profile_id, activity, task_key):
    row = conn.execute('SELECT review_status FROM activity_review_submissions WHERE profile_id=? AND activity=? AND task_key=? ORDER BY rowid DESC LIMIT 1',
                       (profile_id, activity, str(task_key))).fetchone()
    if row and row[0] != 'reviewed':
        return row[0]
    if activity == 'comprehension':
        draft = conn.execute('SELECT d.answers_json FROM comprehension_task_drafts d JOIN comprehension_tasks t ON t.id=d.task_id '
            'WHERE d.task_id=? AND d.profile_id=? AND t.profile_id=d.profile_id AND d.task_revision=t.revision',
            (task_key, profile_id)).fetchone()
        if draft and any(answer.strip() for answer in json.loads(draft[0])):
            return 'draft'
    if activity == 'writing':
        draft = conn.execute('SELECT d.response FROM writing_drafts d JOIN writing_exercises e ON e.id=d.exercise_id WHERE e.id=? AND COALESCE(e.owner_profile_id,\'personal-learning\')=?',
                           (task_key, profile_id)).fetchone()
        reviewed = conn.execute('SELECT response FROM writing_attempts WHERE exercise_id=? ORDER BY id DESC LIMIT 1',
                                (task_key,)).fetchone()
        if draft and ((reviewed and draft[0] != reviewed[0]) or (not reviewed and draft[0])):
            return 'draft'
    if row:
        return row[0]
    return 'not_started'


def pending_summary(conn, profile_id, level):
    from services.curriculum_requirement_map import requirement_index
    refs, result = requirement_index(), []
    for row in conn.execute("SELECT * FROM activity_review_submissions WHERE profile_id=? AND review_status!='reviewed' ORDER BY created_at,rowid", (profile_id,)):
        saved = reviews.decode(row)
        contracts = [saved['contract']] if saved['activity'] != 'comprehension' else saved['contract'].values()
        domains = sorted({refs[c['requirement_id']]['domain'] for contract in contracts
                          if contract and contract['level'] == level for c in contract['criteria']})
        if not domains:
            continue
        task_key = saved['task_key']
        href = ('/writing/load/' + task_key if saved['activity'] == 'writing' else '/comprehension/tasks/' + task_key
                if saved['activity'] == 'comprehension' else '/#unit-exchange/' + task_key)
        result.append({'domains': domains, 'submitted_at': saved['created_at'], 'url': href, 'state': saved['review_status']})
    return result


def _validate_reviewed_result(conn, saved):
    """A retry receipt is a projection of the canonical assessment, not a second score."""
    ref = saved['attempt_ref']
    if not isinstance(ref, dict) or set(ref) != {'activity', 'id'} or ref['activity'] != saved['activity']:
        raise ValueError('Reviewed work is missing its exact final attempt.')
    result = saved['result']
    if not isinstance(result, dict) or not result:
        raise ValueError('Reviewed work is missing its saved result.')
    if saved['activity'] == 'writing':
        attempt = conn.execute('SELECT response,score,score_max,strength,next_step,example,ui_language FROM writing_attempts '
                               'WHERE id=? AND exercise_id=?', (ref['id'], saved['task_key'])).fetchone()
        if (not attempt or attempt['response'] != saved['original']['text'] or attempt['score_max'] != 10
                or attempt['ui_language'] != saved['task']['ui_language']):
            raise ValueError('Writing review does not refer to its original response.')
        expected = {key: attempt[key] for key in ('score', 'strength', 'next_step', 'example')}
        reports = []
        if saved['contract'] is not None:
            row = conn.execute('SELECT r.report_json,r.support_json FROM activity_criterion_reports r '
                'JOIN activity_task_contracts c ON c.id=r.contract_id AND c.profile_id=r.profile_id '
                "WHERE c.profile_id=? AND c.activity='writing' AND c.task_key=? AND r.source_key=?",
                (saved['profile_id'], saved['task_key'], str(ref['id']))).fetchone()
            if row is None or json.loads(row['support_json']) != sorted(saved['support']):
                raise ValueError('Writing review is missing its canonical criterion report or support.')
            report = json.loads(row['report_json'])
            validate_judgements(saved['contract'], report, response_text=saved['original']['text'])
            expected['criterion_report'] = report
            reports.append(report)
        expected['outcome'] = _outcome(reports)
    elif saved['activity'] == 'comprehension':
        row = conn.execute('SELECT answers_json,assessment_json,support_json,support_receipts_json FROM comprehension_attempts '
            'WHERE id=? AND task_id=? AND profile_id=?', (ref['id'], saved['task_key'], saved['profile_id'])).fetchone()
        if (row is None or json.loads(row['answers_json']) != saved['original']['answers']
                or json.loads(row['support_json']) != saved['support']
                or json.loads(row['support_receipts_json']) != saved['support_receipts']):
            raise ValueError('Comprehension review does not refer to its original answers and support.')
        expected = json.loads(row['assessment_json'])
        validate_assessment(saved['task']['payload'], saved['original']['answers'], expected)
        expected = {**expected, 'outcome': _outcome(expected['criterion_reports'].values())}
    else:
        if ref['id'] != saved['id']:
            raise ValueError('Unit Speaking review does not refer to its original recording bundle.')
        row = conn.execute('SELECT r.report_json,r.support_json,r.response_sha256 FROM activity_criterion_reports r '
            'JOIN activity_task_contracts c ON c.id=r.contract_id AND c.profile_id=r.profile_id '
            "WHERE c.profile_id=? AND c.activity='unit_exchange' AND c.task_key=? AND r.source_key=?",
            (saved['profile_id'], saved['task_key'], saved['id'])).fetchone()
        if (row is None or encoded(json.loads(row['support_json'])) != encoded(sorted(saved['support']))
                or encoded(json.loads(row['report_json'])) != encoded(result.get('criterion_report'))):
            raise ValueError('Unit Speaking review is missing its canonical criterion report or support.')
        source = result.get('audio_source')
        if (not isinstance(source, dict) or type(source.get('duration_ms')) is not int or source['duration_ms'] <= 0
                or encoded(source) != encoded(saved['original'].get('audio_source'))
                or source.get('sha256') != row['response_sha256']):
            raise ValueError('Unit Speaking review does not retain its original audio identity.')
        from services.speaking_evidence import validate_speaking_judgements
        validate_speaking_judgements(saved['contract'], result, source['duration_ms'])
        from services.unit_exchange import validate_turn_evidence
        validate_turn_evidence(saved['contract'], result, source)
        if result.get('outcome') != _outcome([result['criterion_report']]):
            raise ValueError('Saved review result contradicts its canonical assessment.')
        return
    # Provenance is stored only on the review receipt. It is not a substitute
    # for the persisted assessment and cannot hide changed score/report fields.
    projected = {key: value for key, value in result.items() if key != 'assessment_provenance'}
    if encoded(projected) != encoded(expected):
        raise ValueError('Saved review result contradicts its canonical assessment.')


def validate_saved_reviews(conn, *, unit_exchange_audio_root=None, require_audio=False):
    """Read-only import audit of original identity, frozen policy and final source."""
    from pathlib import Path
    from services.assessment_pilot import verify_recording
    from services.unit_exchange import owned_task as exchange_task
    factory = conn.row_factory; conn.row_factory = sqlite3.Row
    verified = {}
    try:
        from repositories.curriculum_sequence_repository import validate_saved_sequences
        validate_saved_sequences(conn)
        for disclosure in conn.execute('SELECT * FROM activity_support_disclosures'):
            _, contract = _owned(conn, disclosure['profile_id'], disclosure['activity'], disclosure['task_key'])
            _binding(conn, disclosure['profile_id'], disclosure['activity'], disclosure['task_key'])
            writing_help(conn, disclosure['profile_id'], disclosure['task_key'], contract)
        for row in conn.execute('SELECT id,profile_id FROM curriculum_unit_exchanges'):
            exchange_task(conn, row['profile_id'], row['id'])
        for row in conn.execute('SELECT audio_json FROM curriculum_unit_exchange_turns'):
            manifest = json.loads(row['audio_json'])
            if unit_exchange_audio_root is None:
                if require_audio:
                    raise ValueError('Unit Speaking recordings require their original audio directory.')
                continue
            root = Path(unit_exchange_audio_root)
            verify_recording(root, manifest)
            for filename, sha in ((manifest['filename'], manifest['sha256']), (manifest['assessment_filename'], manifest['assessment_sha256'])):
                path = str(root / filename)
                if path in verified and verified[path] != sha:
                    raise ValueError('Saved unit recordings have conflicting media identities.')
                verified[path] = sha
        for row in conn.execute('SELECT * FROM activity_review_submissions'):
            saved = reviews.decode(row)
            if saved['request_sha256'] != reviews.request_hash(saved['activity'], saved['task_key'], saved['task_revision'], saved['original']):
                raise ValueError('Saved activity original no longer matches its submission digest.')
            policy = _binding(conn, saved['profile_id'], saved['activity'], saved['task_key'])
            if policy != saved['effects_policy']:
                raise ValueError('Saved effects policy does not match the owned lesson binding.')
            if saved['activity'] == 'unit_exchange':
                task = exchange_task(conn, saved['profile_id'], saved['task_key'])
                if saved['contract'] != task['contract'] or saved['task']['asset'] != task['asset']:
                    raise ValueError('Saved unit Speaking response has a changed prompt bundle.')
                originals = [{'turn_id': turn['turn_id'], 'audio': json.loads(turn['audio_json'])} for turn in conn.execute(
                    'SELECT turn_id,audio_json FROM curriculum_unit_exchange_turns WHERE exchange_id=? ORDER BY rowid', (saved['task_key'],))]
                if originals != saved['original']['recordings'] or len(originals) != 2:
                    raise ValueError('The exchange submission must retain both exact originals.')
            else:
                task, contract = _owned(conn, saved['profile_id'], saved['activity'], saved['task_key'])
                if ({**_snapshot(task, saved['activity']), 'ui_language': saved['task']['ui_language']} != saved['task']
                        or contract != saved['contract']):
                    raise ValueError('Saved activity response has a changed task or criterion contract.')
                if saved['activity'] == 'writing' and saved['support_receipts']:
                    disclosed = writing_help(conn, saved['profile_id'], saved['task_key'], contract)
                    if (not disclosed or saved['support_receipts'] != [disclosed['id']]
                            or 'model_answer' not in saved['support']):
                        raise ValueError('The original response does not match its saved example disclosure.')
                    when = conn.execute('SELECT created_at FROM activity_support_disclosures WHERE id=?', (disclosed['id'],)).fetchone()[0]
                    if when > saved['created_at']:
                        raise ValueError('Example help must be disclosed before the original response is saved.')
            if saved['review_status'] == 'reviewed':
                _validate_reviewed_result(conn, saved)
            elif saved['result'] is not None or saved['attempt_ref'] is not None:
                raise ValueError('Unreviewed work cannot contain a final assessment.')
        return verified
    finally:
        conn.row_factory = factory


def _outcome(reports):
    judgements = [j for report in reports for j in report['judgements']]
    if any(j['outcome'] in ('partial', 'not_satisfied') for j in judgements):
        return 'practise_and_retry'
    if not judgements or any(j['outcome'] == 'insufficient_evidence' for j in judgements):
        return 'more_evidence_needed'
    return 'demonstrated_in_task'


def _finish_writing(conn, saved, assessment):
    WritingRepository.validate_assessment(assessment)
    response, contract = saved['original']['text'], saved['contract']
    if contract:
        validate_judgements(contract, assessment.get('criterion_report'), response_text=response)
    task, owner = saved['task'], saved['profile_id']
    attempt = conn.execute('''INSERT INTO writing_attempts
        (exercise_id,response,score,score_max,strength,next_step,example,ui_language,created_at,source)
        VALUES (?,?,?,10,?,?,?,?,?,'writing-v1')''',
        (int(saved['task_key']), response, assessment['score'], assessment['strength'], assessment['next_step'], assessment['example'], task['ui_language'], writing_timestamp()))
    source = str(attempt.lastrowid)
    if contract:
        save_report(conn, owner, 'writing', saved['task_key'], source, assessment['criterion_report'], response_text=response, support=saved['support'])
    if saved['effects_policy'] != reviews.TRANSFER_POLICY:
        pid = legacy_profile(conn)
        if pid:
            award(conn, pid, activity='writing', content_key=f"writing:{saved['task_key']}", source_key=f'writing-attempt:{source}',
                  title='Writing', evidence={'score': assessment['score'], 'score_max': 10, 'assisted': bool(saved['support'])})
    return {'activity': 'writing', 'id': source}, {**assessment, 'outcome': _outcome([assessment['criterion_report']] if contract else [])}


def _finish_comprehension(conn, saved, assessment):
    task, owner, answers = saved['task'], saved['profile_id'], saved['original']['answers']
    assessment = dict(assessment)
    provenance = assessment.pop('assessment_provenance', None)
    validate_assessment(task['payload'], answers, assessment)
    identity = identifier()
    digest = request_digest(saved['task_key'], saved['task_revision'], answers)
    # Existing evidence audits use this stable internal token, independent of
    # the public idempotency key's UUID formatting.
    internal_submission = payload_hash({'review_submission': saved['id']})[:32]
    conn.execute('''INSERT INTO comprehension_attempts
        (id,task_id,profile_id,submission_id,request_sha256,answers_json,assessment_json,support_json,created_at,support_receipts_json)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (identity, saved['task_key'], owner, internal_submission, digest, encoded(answers), encoded(assessment),
         encoded(saved['support']), timestamp(), encoded(saved['support_receipts'])))
    for index, report in assessment['criterion_reports'].items():
        save_report(conn, owner, 'comprehension', f"{saved['task_key']}:{index}", identity, report,
                    response_text=answers[int(index)], support=saved['support'])
    conn.execute('UPDATE saved_stories SET answers=?,feedback=?,score=? WHERE id=?',
                 (encoded(answers), encoded(assessment['feedback']), assessment['total_score'], task['story_id']))
    conn.execute('UPDATE comprehension_tasks SET revision=revision+1 WHERE id=?', (saved['task_key'],))
    if saved['effects_policy'] != reviews.TRANSFER_POLICY:
        pid = legacy_profile(conn)
        if pid:
            award(conn, pid, activity='reading', content_key=f"story:{task['story_id']}", source_key=f'comprehension-check:{identity}',
                  title=task['title_en'] or task['title'], evidence={'score': assessment['total_score'], 'score_max': 10,
                  'answered_questions': len(answers), 'first_fresh_assessment': not saved['support'],
                  'course_task_context_matches': True, 'course_task_questions_hash': payload_hash(task['payload']['questions'])})
    return {'activity': 'comprehension', 'id': identity}, {**assessment, 'outcome': _outcome(assessment['criterion_reports'].values()),
        **({'assessment_provenance': provenance} if provenance is not None else {})}


def review(db_path, identity, provider, *, activity=None):
    with transaction(db_path, write=True) as conn:
        owner = activity_profile_id(conn)
        saved = reviews.get(conn, owner, identity)
        if activity and saved['activity'] != activity:
            raise LearningError('not_found', 'This reply belongs to a different activity.', 404)
        _binding(conn, owner, saved['activity'], saved['task_key'])
        saved, token = reviews.claim(conn, owner, identity)
    if token is None:
        return reviews.public(saved)
    try:
        if saved['activity'] == 'writing':
            task = saved['task']
            assessment = provider.assess_writing(task=task['task'], required_words=task['required_words'], min_words=task['min_words'],
                response=saved['original']['text'], difficulty=task['difficulty'], language=task['ui_language'], topic=task['topic'],
                curriculum_contract=saved['contract'], include_provenance=True)
        else:
            assessment = provider.assess_task(saved['task']['payload'], saved['original']['answers'],
                                              include_provenance=True, language=saved['task']['ui_language'])
        with transaction(db_path, write=True) as conn:
            if activity_profile_id(conn) != owner:
                raise LearningError('profile_changed', 'Your profile changed. Reopen your saved reply.', 409)
            current = reviews.assert_lease(conn, owner, identity, token)
            policy = _binding(conn, owner, saved['activity'], saved['task_key'])
            task, contract = _owned(conn, owner, saved['activity'], saved['task_key'])
            if ({**_snapshot(task, saved['activity']), 'ui_language': saved['task']['ui_language']} != saved['task']
                    or contract != saved['contract'] or policy != saved['effects_policy']):
                raise LearningError('invalid_saved_task', 'This task changed. Your original reply remains saved.', 409)
            attempt_ref, result = (_finish_writing if saved['activity'] == 'writing' else _finish_comprehension)(conn, current, assessment)
            completed = reviews.finish(conn, owner, identity, token, attempt_ref, result)
        return reviews.public(completed)
    except Exception as error:
        from services.ai_trial_budget import TrialDenied
        code = 'budget_exhausted' if isinstance(error, TrialDenied) else 'provider_unavailable'
        with transaction(db_path, write=True) as conn:
            reviews.fail(conn, owner, identity, token, code)
        if isinstance(error, LearningError):
            raise
        return load(db_path, identity, activity)
