"""Read-only validation of pilot envelopes and their original evidence.

Hashes detect inconsistent saved data; they are not signatures or proof of an
independent performance. Historical draft bodies are not retained, so their
request digests cannot be reconstructed. Source audio is verified only when a
directory is explicitly supplied; imports require it for every saved recording.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import wave

from contracts.curriculum import validate_judgements
from repositories.assessment_pilot_repository import empty_response, response_for
from repositories.learning_repository import encoded, payload_hash
from services.assessment_pilot_content import DOMAIN_IDS, validate_blueprint


PILOT_TABLES = ('assessment_pilot_sessions', 'assessment_pilot_components', 'assessment_pilot_support',
                'assessment_pilot_submissions', 'assessment_pilot_reviews', 'assessment_pilot_requests')
_ID = re.compile(r'[0-9a-f]{32}')
_KEY = re.compile(r'[A-Za-z0-9_.:-]{1,100}')
_HASH = re.compile(r'[0-9a-f]{64}')
_AUDIO_FIELDS = {'id', 'filename', 'sha256', 'size_bytes', 'duration_ms',
                 'assessment_filename', 'assessment_sha256', 'assessment_size_bytes'}
_REPORT_FIELDS = {'criterion_report', 'feedback', 'outcome', 'assisted', 'support',
                  'source_sha256', 'assessor', 'audio_source', 'production_feedback'}


def _rows(conn, table):
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    return [dict(row) for row in cursor.execute('SELECT rowid AS _rowid,* FROM ' + table + ' ORDER BY rowid')]


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _object(value, fields, label):
    _require(isinstance(value, dict) and set(value) == set(fields), label + ' has invalid fields.')


def _same(left, right):
    return encoded(left) == encoded(right)


def _read_audio(root, filename, expected_size, expected_hash, maximum):
    path = root / filename
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as source:
        _require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), 'Pilot audio must be a regular file.')
        data = source.read(maximum + 1)
    _require(len(data) == expected_size and len(data) <= maximum
             and hashlib.sha256(data).hexdigest() == expected_hash, 'Pilot original or assessment audio bytes changed.')
    return data


def validate_pilot_audio(source, *, audio_root=None, require_audio=False):
    """Validate immutable upload/derivative identities without copying media."""
    _object(source, _AUDIO_FIELDS, 'Pilot audio identity')
    _require(_matches(_ID, source['id']), 'Pilot audio has an invalid recording ID.')
    allowed = {source['id'] + '.' + ext for ext in ('wav', 'webm', 'ogg', 'mp4', 'm4a', 'mp3')}
    _require(source['filename'] in allowed and source['assessment_filename'] == source['id'] + '-review.wav',
             'Pilot audio has an unsafe or mismatched filename.')
    _require(_matches(_HASH, source['sha256']) and _matches(_HASH, source['assessment_sha256']),
             'Pilot audio needs both immutable source hashes.')
    _require(_integer(source['size_bytes'], 1) and source['size_bytes'] <= 8 * 1024 * 1024
             and _integer(source['assessment_size_bytes'], 44) and source['assessment_size_bytes'] <= 32 * 1024 * 1024
             and _integer(source['duration_ms'], 200) and source['duration_ms'] <= 90000,
             'Pilot recording size or duration is invalid.')
    if audio_root is None:
        _require(not require_audio, 'Pilot Speaking requires --local-pilot-audio-root to verify its original recordings.')
        return {}
    root = Path(audio_root).resolve(strict=True)
    _require(root.is_dir(), 'Pilot audio root must be a directory.')
    _read_audio(root, source['filename'], source['size_bytes'], source['sha256'], 8 * 1024 * 1024)
    derivative = _read_audio(root, source['assessment_filename'], source['assessment_size_bytes'],
                             source['assessment_sha256'], 32 * 1024 * 1024)
    with wave.open(io.BytesIO(derivative), 'rb') as recording:
        _require(recording.getnchannels() == 1 and recording.getsampwidth() == 2
                 and 8000 <= recording.getframerate() <= 48000 and recording.getcomptype() == 'NONE',
                 'Pilot review audio must be uncompressed mono PCM16.')
        duration = round(recording.getnframes() * 1000 / recording.getframerate())
        _require(abs(duration - source['duration_ms']) <= 1, 'Pilot review duration no longer matches its frozen source.')
        _require(len(recording.readframes(recording.getnframes())) == recording.getnframes() * 2,
                 'Pilot review audio is incomplete.')
    return {str(root / source['filename']): source['sha256'],
            str(root / source['assessment_filename']): source['assessment_sha256']}


def _report(task, submission, report, support, audio, listened, language):
    _object(report, _REPORT_FIELDS, 'Pilot review')
    _require(isinstance(report['feedback'], str) and bool(report['feedback'].strip())
             and len(report['feedback']) <= 12000 and '\x00' not in report['feedback'], 'Pilot feedback is invalid.')
    _object(report['assessor'], ('version', 'model', 'prompt_sha256', 'rubric_version'), 'Pilot assessor')
    _require(report['assessor']['version'] == 'assessment-pilot-v1'
             and isinstance(report['assessor']['model'], str) and 0 < len(report['assessor']['model']) <= 200
             and _matches(_HASH, report['assessor']['prompt_sha256'])
             and isinstance(report['assessor']['rubric_version'], str) and 0 < len(report['assessor']['rubric_version']) <= 200,
             'Unknown pilot assessor version or model.')
    _require(_same(report['support'], support), 'Pilot feedback changed its saved support conditions.')
    assisted = bool(set(support).intersection(task['contract']['support']['independence_breakers']))
    _require(type(report['assisted']) is bool and report['assisted'] == assisted,
             'Pilot feedback misstates support affecting independence.')
    response = json.loads(submission['response_json'])
    production = report['production_feedback']
    if task['domain'] in ('writing', 'speaking') and response != {'unavailable': True}:
        _require(isinstance(production, dict) and _same(production.get('criterion_report'), report['criterion_report']),
                 'Pilot production review lost or changed its full provider criterion feedback.')
        _require(_same(production.get('assessment_provenance'), {key: value for key, value in report['assessor'].items() if key != 'version'}),
                 'Pilot assessor identity differs from its retained production provenance.')
        if task['domain'] == 'writing':
            from repositories.writing_repository import WritingRepository
            WritingRepository.validate_assessment(production)
            _require(report['feedback'] == production['strength'] + '\n' + production['next_step'],
                     'Pilot Writing summary differs from its retained production feedback.')
        else:
            from services.speaking_assessment import validate_assessment
            from services.speaking_evidence import validate_speaking_judgements
            _require(audio is not None, 'A Speaking production review needs original audio.')
            fields = ('transcript', 'speech_status', 'uncertain_phrases', 'grammar', 'fluency',
                      'goals', 'summary', 'next_step', 'corrections', 'uncertainty', 'criterion_report')
            original = {key: production[key] for key in fields}
            checked = validate_assessment(deepcopy(original), [{'id': identity} for identity in task['scenario']['goal_ids']],
                                          language, curriculum_contract=task['contract'], audio_duration_ms=audio['duration_ms'])
            _require(_same(checked, original), 'Pilot Speaking review needs normalization inconsistent with its saved feedback.')
            validate_speaking_judgements(task['contract'], production, audio['duration_ms'])
            _require(report['feedback'] == production['summary'] + '\n' + production['next_step'],
                     'Pilot Speaking summary differs from its retained production feedback.')
    else:
        _require(production is None, 'Selection or unavailable evidence cannot contain a production review.')
    if task['domain'] == 'speaking' and audio is not None:
        _require(_same(report['audio_source'], audio) and report['source_sha256'] == audio['sha256'],
                 'Speaking feedback does not belong to the original recording.')
        validate_judgements(task['contract'], report['criterion_report'], audio_duration_ms=audio['duration_ms'])
    else:
        text = response['text'] if task['domain'] == 'writing' else encoded(response)
        _require(report['audio_source'] is None and report['source_sha256'] == hashlib.sha256(text.encode()).hexdigest(),
                 'Pilot feedback does not belong to the original response.')
        validate_judgements(task['contract'], report['criterion_report'], response_text=text)
    judgements = report['criterion_report']['judgements']
    insufficient = (response == {'unavailable': True} or (task['domain'] == 'speaking' and audio is None)
                    or (task['domain'] == 'listening' and (task['audio'] is None or not listened)))
    if production is None:
        model = 'unmeasured' if insufficient else 'authored-key-v1'
        _require(_same(report['assessor'], {'version': 'assessment-pilot-v1', 'model': model,
                    'prompt_sha256': hashlib.sha256(model.encode()).hexdigest(), 'rubric_version': task['contract']['rubric_version']}),
                 'Pilot deterministic assessor provenance changed.')
    if insufficient:
        _require(all(item['outcome'] == 'insufficient_evidence' for item in judgements),
                 'Unavailable audio cannot become scored audio evidence.')
    elif task['format'] == 'choice_set':
        text = encoded(response)
        by_id = {item['criterion_id']: item for item in judgements}
        for item in task['items']:
            chosen = response['answers'][item['id']]
            quote = encoded(item['id']) + ':' + encoded(chosen)
            start = text.index(quote)
            correct = chosen == item['answer']
            judgement = by_id[item['id']]
            _require(judgement['outcome'] == ('satisfied' if correct else 'not_satisfied')
                     and judgement['score'] == (1 if correct else 0)
                     and judgement['feedback'] == item['explanation']
                     and _same(judgement['evidence'], [{'quote': quote, 'start': start, 'end': start + len(quote)}]),
                     'Pilot selection feedback disagrees with its frozen answer key and exact response field.')
    outcomes = {item['outcome'] for item in judgements}
    outcome = ('more_evidence_needed' if 'insufficient_evidence' in outcomes else
               'demonstrated_in_task' if outcomes == {'satisfied'} else 'practise_and_retry')
    _require(report['outcome'] == outcome, 'Pilot summary outcome disagrees with its criterion results.')


def validate_saved_pilot(conn, *, audio_root=None, require_audio=False):
    """Validate all pilot rows and return verified audio paths/hashes; no writes."""
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    present = set(PILOT_TABLES).intersection(tables)
    if not present:
        return {}
    _require(present == set(PILOT_TABLES), 'Pilot evidence tables are incomplete.')
    sessions = _rows(conn, 'assessment_pilot_sessions')
    components = _rows(conn, 'assessment_pilot_components')
    receipts = _rows(conn, 'assessment_pilot_support')
    submissions = _rows(conn, 'assessment_pilot_submissions')
    reviews = _rows(conn, 'assessment_pilot_reviews')
    requests = _rows(conn, 'assessment_pilot_requests')
    profiles = {row[0] for row in conn.execute('SELECT id FROM learning_profiles')}
    by_session = {row['id']: row for row in sessions}
    by_component = {row['id']: row for row in components}
    by_submission = {row['id']: row for row in submissions}
    by_review = {row['submission_id']: row for row in reviews}
    by_component_submission = {row['component_id']: row for row in submissions}
    _require(len(by_component_submission) == len(submissions), 'A pilot component has multiple originals.')
    blueprints, tasks, owned_components = {}, {}, defaultdict(list)
    support_rows, operation_counts, verified = defaultdict(list), Counter(), {}
    by_request = {}
    for session in sessions:
        _require(_matches(_ID, session['id']) and session['profile_id'] in profiles
                 and _matches(_KEY, session['start_key']) and session['language'] in ('en', 'ru')
                 and _integer(session['created_at']), 'Pilot session identity or ownership is invalid.')
        payload = validate_blueprint(json.loads(session['blueprint_json']))
        _require(session['blueprint_id'] == payload['id'] and session['blueprint_sha256'] == payload_hash(payload),
                 'Pilot blueprint no longer matches its saved identity and digest.')
        blueprints[session['id']] = payload
    seen = defaultdict(list)
    for component in components:
        session = by_session.get(component['session_id'])
        _require(session is not None and component['profile_id'] == session['profile_id']
                 and _matches(_ID, component['id']) and component['domain'] in DOMAIN_IDS
                 and _integer(component['ordinal']) and _integer(component['revision'])
                 and _integer(component['created_at']) and component['created_at'] >= session['created_at']
                 and type(component['repeated']) is int and component['repeated'] in (0, 1)
                 and type(component['prior_feedback']) is int and component['prior_feedback'] in (0, 1),
                 'Pilot component identity, ownership or chronology is invalid.')
        task = json.loads(component['task_json'])
        forms = blueprints[session['id']]['forms'][component['domain']]
        _require(component['task_sha256'] == payload_hash(task) and any(_same(task, form) for form in forms),
                 'Pilot component is not one of its frozen authored forms.')
        family = (component['profile_id'], session['blueprint_id'], component['domain'])
        prior_forms = [tasks[row['id']]['form_id'] for row in seen[family]]
        _require(not seen[family] or seen[family][-1]['created_at'] <= component['created_at'],
                 'Pilot form creation times are out of order.')
        expected_form = next((form for form in forms if form['form_id'] not in prior_forms), forms[len(prior_forms) % len(forms)])
        _require(_same(task, expected_form) and bool(component['repeated']) == (task['form_id'] in prior_forms),
                 'Pilot form order or repeated-task marker changed.')
        previous_feedback = []
        for prior in seen[family]:
            old_submission = by_component_submission.get(prior['id'])
            old_review = by_review.get(old_submission['id']) if old_submission else None
            if (prior['task_sha256'] == component['task_sha256'] and old_review
                    and old_review['state'] == 'ready' and old_review['updated_at'] <= component['created_at']):
                previous_feedback.append(old_review['updated_at'])
        # Integer-second timestamps cannot order a review and new component
        # occurring in the same second. A true flag still needs a real source.
        _require((not component['prior_feedback'] or bool(previous_feedback))
                 and (component['prior_feedback'] or not any(t < component['created_at'] for t in previous_feedback)),
                 'Pilot prior-feedback marker has no consistent earlier source.')
        response_for(task, json.loads(component['draft_json']))
        tasks[component['id']] = task
        owned_components[(session['id'], component['domain'])].append(component)
        seen[family].append(component)
    for session in sessions:
        for domain in DOMAIN_IDS:
            rows = owned_components[(session['id'], domain)]
            _require(rows and [row['ordinal'] for row in rows] == list(range(len(rows))),
                     'Pilot component ordinals are incomplete or out of order.')
            for previous, current in zip(rows, rows[1:]):
                original = by_component_submission.get(previous['id'])
                _require(original is not None and original['created_at'] <= current['created_at'],
                         'A new pilot form was issued before the previous original was saved.')
    for request in requests:
        session = by_session.get(request['session_id'])
        op = request['operation']
        _require(session is not None and _matches(_KEY, request['request_key']) and _matches(_HASH, request['request_sha256'])
                 and _integer(request['created_at']) and request['created_at'] >= session['created_at']
                 and (op in ('start', 'retry') or op in {action + ':' + domain for action in ('draft', 'support', 'submit', 'review') for domain in DOMAIN_IDS}),
                 'Pilot request metadata is invalid or orphaned.')
        if op == 'start':
            _require(request['request_sha256'] == payload_hash({'submission_id': request['request_key']}),
                     'Pilot resume request digest changed.')
        by_request[(request['session_id'], request['request_key'])] = request
        operation_counts[(request['session_id'], op)] += 1
    for receipt in receipts:
        component = by_component.get(receipt['component_id'])
        _require(component is not None and receipt['profile_id'] == component['profile_id'] and _matches(_ID, receipt['id'])
                 and receipt['kind'] in ('hint', 'listened', 'transcript') and _integer(receipt['revision'])
                 and receipt['revision'] < component['revision'] and _integer(receipt['created_at'])
                 and receipt['created_at'] >= component['created_at'], 'Pilot support receipt is invalid or orphaned.')
        task = tasks[component['id']]
        _require(receipt['kind'] == 'hint' or task['domain'] == 'listening', 'Audio support belongs to a non-listening task.')
        expected_detail = {}
        if receipt['kind'] == 'listened':
            _require(task['audio'] is not None, 'A listening receipt has no frozen source recording.')
            expected_detail = {'audio_sha256': task['audio']['sha256']}
        _require(_same(json.loads(receipt['detail_json']), expected_detail), 'Pilot support receipt changed its disclosed content identity.')
        matching_requests = [request for request in requests
            if request['session_id'] == component['session_id'] and request['operation'] == 'support:' + component['domain']
            and component['created_at'] <= request['created_at'] <= receipt['created_at']
            and request['request_sha256'] == payload_hash({
                'submission_id': request['request_key'], 'component_id': component['id'],
                'expected_revision': receipt['revision'], 'kind': receipt['kind']})]
        _require(len(matching_requests) == 1, 'Pilot support receipt has no exact component-bound request.')
        prior = support_rows[component['id']]
        _require(not prior or (prior[-1]['revision'] < receipt['revision'] and prior[-1]['created_at'] <= receipt['created_at']),
                 'Pilot support receipt revisions or times are out of order.')
        prior.append(receipt)
    audio_ids = set()
    for submission in submissions:
        component = by_component.get(submission['component_id'])
        _require(component is not None and submission['profile_id'] == component['profile_id'] and _matches(_ID, submission['id'])
                 and _matches(_KEY, submission['submission_key']) and _integer(submission['submitted_revision'])
                 and component['revision'] == submission['submitted_revision'] + 1
                 and _integer(submission['created_at']) and submission['created_at'] >= component['created_at'],
                 'Pilot original response is invalid or belongs to another component.')
        task = tasks[component['id']]
        response = response_for(task, json.loads(submission['response_json']), complete=True)
        _require(_same(response, json.loads(component['draft_json'])), 'Submitted pilot original and final draft disagree.')
        attached = support_rows[component['id']]
        _require(all(row['revision'] < submission['submitted_revision'] and row['created_at'] <= submission['created_at'] for row in attached),
                 'Pilot support was recorded after the original was submitted.')
        support = sorted({row['kind'] for row in attached if row['kind'] != 'listened'}
                         | ({'model_answer'} if component['prior_feedback'] else set()))
        listened = any(row['kind'] == 'listened' for row in attached)
        _require(_same(json.loads(submission['support_json']), support)
                 and _same(json.loads(submission['receipt_ids_json']), [row['id'] for row in attached]),
                 'Pilot original lost or changed its exact support receipt snapshot.')
        _require(task['domain'] != 'listening' or listened or 'transcript' in support or response == {'unavailable': True},
                 'A listening answer has no listening or transcript receipt.')
        audio = json.loads(submission['audio_json']) if submission['audio_json'] is not None else None
        _require((task['domain'] == 'speaking' and (audio is not None or response == {'unavailable': True}))
                 or (task['domain'] != 'speaking' and audio is None), 'Pilot audio belongs to the wrong response mode.')
        if audio is not None:
            _require(response != {'unavailable': True}, 'A recording cannot also be marked unavailable.')
            current_audio = validate_pilot_audio(audio, audio_root=audio_root, require_audio=require_audio)
            _require(audio['id'] not in audio_ids, 'Pilot originals reuse a recording identity.')
            audio_ids.add(audio['id'])
            verified.update(current_audio)
        body = {'submission_id': submission['submission_key'], 'component_id': component['id'],
                'expected_revision': submission['submitted_revision'],
                'response': response, 'audio': audio}
        request = by_request.get((component['session_id'], submission['submission_key']))
        _require(submission['request_sha256'] == payload_hash(body) and request is not None
                 and request['operation'] == 'submit:' + component['domain']
                 and request['request_sha256'] == submission['request_sha256']
                 and component['created_at'] <= request['created_at'] <= submission['created_at'],
                 'Pilot original request digest or submission receipt changed.')
        review = by_review.get(submission['id'])
        _require(review is not None, 'A pilot original has no review state.')
        _require(review['state'] in ('pending', 'running', 'ready', 'failed') and _integer(review['updated_at'])
                 and review['updated_at'] >= submission['created_at'] and _integer(review['lease_until']),
                 'Pilot review state or chronology is invalid.')
        if review['state'] == 'running':
            _require(_matches(_ID, review['claim_token']) and review['lease_until'] > review['updated_at']
                     and review['report_json'] is None and review['error'] is None, 'Running pilot review has inconsistent claim state.')
        else:
            _require(review['claim_token'] is None and review['lease_until'] == 0, 'Finished pilot review retains a provider claim.')
            _require((review['state'] == 'ready') == (review['report_json'] is not None), 'Pilot ready state and saved report disagree.')
            _require(review['state'] == 'failed' or review['error'] is None, 'A nonfailed pilot review retains an error.')
        if review['state'] == 'ready':
            _report(task, submission, json.loads(review['report_json']), support, audio, listened,
                    by_session[component['session_id']]['language'])
    _require(set(by_review) == set(by_submission), 'Pilot reviews contain orphan originals.')
    for request in requests:
        if request['operation'].startswith('review:'):
            domain = request['operation'].split(':', 1)[1]
            matches = [row for row in owned_components[(request['session_id'], domain)]
                if row['id'] in by_component_submission
                and by_component_submission[row['id']]['created_at'] <= request['created_at']
                and request['request_sha256'] == payload_hash({'submission_id': request['request_key'], 'component_id': row['id']})]
            _require(len(matches) == 1, 'Pilot review request has no exact submitted component.')
    for session in sessions:
        extra = 0
        for domain in DOMAIN_IDS:
            rows = owned_components[(session['id'], domain)]
            saved = sum(row['id'] in by_component_submission for row in rows)
            disclosed = sum(len(support_rows[row['id']]) for row in rows)
            drafts = sum(row['revision'] for row in rows) - saved - disclosed
            _require(drafts >= 0 and operation_counts[(session['id'], 'draft:' + domain)] == drafts
                     and operation_counts[(session['id'], 'support:' + domain)] == disclosed
                     and operation_counts[(session['id'], 'submit:' + domain)] == saved,
                     'Pilot revision advances no longer match their saved operation receipts.')
            for row in rows:
                if row['revision'] == 0:
                    _require(_same(json.loads(row['draft_json']), empty_response(tasks[row['id']])),
                             'An untouched pilot task has a changed initial draft.')
            extra += len(rows) - 1
        retries = operation_counts[(session['id'], 'retry')]
        _require(retries <= extra <= retries * len(DOMAIN_IDS), 'Pilot retry receipts do not match issued forms.')
    return verified
