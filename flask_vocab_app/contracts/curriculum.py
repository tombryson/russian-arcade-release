"""Pure, versioned task/report validation; no grading authority or learner writes.

Only server-authored specifications may be frozen. Hashes detect changes; they
are not signatures or proof of ownership. Callers still authenticate the source
attempt, save its support record and validate actual task semantics. These
contracts enable practice/diagnostics only, not a new proficiency gate.
"""
from copy import deepcopy
import hashlib
import json
import math
import re

from services.curriculum_requirement_map import requirement_index
from services.torfl_requirements import LEVELS, VERSION
from services.vocabulary_topics import TOPICS

CONTRACT_VERSION = 'curriculum-task-v1'
RESPONSE_MODES = {'contextual_selection', 'reading_selection', 'listening_selection',
                  'controlled_text', 'reading_response', 'listening_response', 'independent_writing', 'independent_speaking'}
SUPPORT_TYPES = {'hint', 'translation', 'transcript', 'model_answer', 'audio_replay'}
_KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}')
_SPEC_FIELDS = {'schema_version', 'contract_version', 'reference_version', 'task_id',
                'activity', 'content_version', 'level', 'topic_ids', 'purpose',
                'content', 'rubric_version', 'support', 'criteria'}
_HASH_FIELDS = {'content_sha256', 'contract_sha256'}


def _fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f'{label} contains missing or unsupported fields.')


def _text(value, label, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        raise ValueError(f'{label} requires bounded nonempty text.')


def _key(value, label):
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise ValueError(f'{label} requires a stable identifier.')


def _json(value):
    def check(item, depth=0):
        if depth > 30:
            raise ValueError('Task JSON nesting is too deep.')
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError('Task JSON object keys must be strings.')
                check(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                check(child, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError('Task content must be plain JSON.')
    check(value)
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('Task content must be finite JSON.') from exc
    if len(encoded.encode('utf-8')) > 1_000_000:
        raise ValueError('Task contract is too large.')
    return encoded


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _distinct(values, allowed, label):
    if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
            or len(values) != len(set(values)) or not set(values) <= set(allowed)):
        raise ValueError(f'{label} requires distinct known values.')


def _number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number, not a boolean.')


def _validate_spec(spec):
    _fields(spec, _SPEC_FIELDS, 'Task specification')
    if (type(spec['schema_version']) is not int or spec['schema_version'] != 1
            or spec['contract_version'] != CONTRACT_VERSION or spec['reference_version'] != VERSION):
        raise ValueError('Unsupported curriculum contract version.')
    for name in ('task_id', 'activity', 'content_version', 'rubric_version'):
        _key(spec[name], name)
    if spec['level'] not in LEVELS or spec['purpose'] not in ('practice', 'diagnostic'):
        raise ValueError('Use a known level and practice/diagnostic purpose; this is not a released assessment gate.')
    _distinct(spec['topic_ids'], TOPICS, 'Topics')
    if not spec['topic_ids'] or not isinstance(spec['content'], dict) or not spec['content']:
        raise ValueError('A task needs canonical topics and its actual saved content.')
    support = spec['support']
    _fields(support, ('allowed', 'independence_breakers'), 'Support policy')
    _distinct(support['allowed'], SUPPORT_TYPES, 'Available support')
    _distinct(support['independence_breakers'], support['allowed'], 'Support affecting independence')
    if 'model_answer' in support['allowed'] and 'model_answer' not in support['independence_breakers']:
        raise ValueError('A supplied model answer cannot remain independent evidence.')
    criteria = spec['criteria']
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 24:
        raise ValueError('A task needs between one and 24 explicit criteria.')
    refs, ids, target_ids = requirement_index(), set(), set()
    for criterion in criteria:
        _fields(criterion, ('id', 'target_id', 'requirement_id', 'response_mode', 'evidence_scope',
                            'expectation', 'max_score', 'source_refs'), 'Criterion')
        for key in ('id', 'target_id', 'requirement_id'):
            _key(criterion[key], key)
        rid = criterion['requirement_id']
        if rid not in refs or criterion['id'] in ids or criterion['target_id'] in target_ids:
            raise ValueError('Criteria need known requirements and distinct criterion/target IDs.')
        ref = refs[rid]
        if LEVELS.index(rid[:2].upper()) > LEVELS.index(spec['level']):
            raise ValueError('A task cannot claim a requirement above its declared level.')
        mode, scope = criterion['response_mode'], criterion['evidence_scope']
        if mode not in RESPONSE_MODES:
            raise ValueError('Unknown criterion response mode.')
        if scope == 'reference':
            if mode != ref['response_mode']:
                raise ValueError('Reference evidence must preserve its exact response mode.')
        elif scope == 'controlled_production':
            if (mode != 'controlled_text' or ref['domain'] != 'language_use'
                    or criterion['target_id'] == rid):
                raise ValueError('Controlled production needs a distinct application target and a language-use reference.')
        elif scope == 'reading_comprehension':
            if (mode != 'reading_response' or ref['domain'] != 'reading'
                    or ref['response_mode'] != 'reading_selection' or criterion['target_id'] == rid):
                raise ValueError('Open reading responses need a distinct application target and a reading reference.')
        elif scope == 'listening_comprehension':
            if (mode != 'listening_response' or ref['domain'] != 'listening'
                    or ref['response_mode'] != 'listening_selection' or criterion['target_id'] == rid):
                raise ValueError('Open listening responses need a distinct application target and a listening reference.')
        else:
            raise ValueError('Use reference or an explicitly scoped application evidence mode.')
        _text(criterion['expectation'], 'Observable criterion')
        _number(criterion['max_score'], 'Maximum score')
        if not 0 < criterion['max_score'] <= 100:
            raise ValueError('Maximum criterion score must be positive and bounded.')
        if criterion['source_refs'] != ref['source_refs']:
            raise ValueError('Criterion source locators must match the inspected requirement.')
        if mode in ('listening_selection', 'listening_response'):
            if 'transcript' in support['allowed'] and 'transcript' not in support['independence_breakers']:
                raise ValueError('Listening with a transcript cannot be independent listening evidence.')
        if mode in ('reading_selection', 'reading_response', 'listening_selection', 'listening_response', 'independent_writing', 'independent_speaking'):
            if 'translation' in support['allowed'] and 'translation' not in support['independence_breakers']:
                raise ValueError('Answer-supporting translation must change the independence condition.')
        ids.add(criterion['id'])
        target_ids.add(criterion['target_id'])
    _json(spec)


def freeze_task_contract(spec):
    """Freeze a server-owned JSON specification; return an independent snapshot."""
    _validate_spec(spec)
    frozen = deepcopy(spec)
    frozen['content_sha256'] = _digest(frozen['content'])
    frozen['contract_sha256'] = _digest(frozen)
    return frozen


def validate_task_contract(contract):
    """Reject payload, criterion, rubric or support changes after freezing."""
    _fields(contract, _SPEC_FIELDS | _HASH_FIELDS, 'Frozen task contract')
    spec = {key: contract[key] for key in _SPEC_FIELDS}
    _validate_spec(spec)
    if contract['content_sha256'] != _digest(contract['content']):
        raise ValueError('Saved task content hash does not match.')
    without_hash = {key: value for key, value in contract.items() if key != 'contract_sha256'}
    if contract['contract_sha256'] != _digest(without_hash):
        raise ValueError('Saved task contract hash does not match.')
    return deepcopy(contract)


def validate_judgements(contract, report, *, response_text=None, audio_duration_ms=None):
    """Check a bounded report against a saved contract and original evidence.

    Audio spans prove only that cited intervals exist, not that an assessor heard
    them correctly. Selection/text spans use Python Unicode code-point offsets.
    This validates structure, not grading correctness, support eligibility,
    authentication, mastery, coins or continuation rights.
    """
    validate_task_contract(contract)
    _fields(report, ('contract_sha256', 'judgements'), 'Judgement report')
    if report['contract_sha256'] != contract['contract_sha256']:
        raise ValueError('Judgement belongs to a different saved contract.')
    if response_text is not None and not isinstance(response_text, str):
        raise ValueError('Original response text must be a string.')
    if audio_duration_ms is not None and (type(audio_duration_ms) is not int or audio_duration_ms <= 0):
        raise ValueError('Original audio duration must be positive milliseconds.')
    judgements = report['judgements']
    expected = {item['id']: item for item in contract['criteria']}
    if not isinstance(judgements, list) or len(judgements) != len(expected):
        raise ValueError('Return exactly one judgement for every saved criterion.')
    seen = set()
    for judgement in judgements:
        _fields(judgement, ('criterion_id', 'outcome', 'score', 'feedback', 'evidence'), 'Criterion judgement')
        cid = judgement['criterion_id']
        if not isinstance(cid, str) or cid not in expected or cid in seen:
            raise ValueError('A judgement cannot add or duplicate criterion IDs.')
        criterion, outcome = expected[cid], judgement['outcome']
        if outcome not in ('satisfied', 'partial', 'not_satisfied', 'insufficient_evidence'):
            raise ValueError('Use a criterion outcome, never a mastery or level claim.')
        _text(judgement['feedback'], 'Criterion feedback')
        evidence = judgement['evidence']
        if not isinstance(evidence, list) or len(evidence) > 12:
            raise ValueError('Use a bounded list of original response spans.')
        if outcome == 'insufficient_evidence':
            if judgement['score'] is not None:
                raise ValueError('Insufficient evidence is unscored, not a zero.')
        else:
            score = judgement['score']
            _number(score, 'Criterion score')
            maximum = criterion['max_score']
            if (not 0 <= score <= maximum or (outcome == 'satisfied' and score != maximum)
                    or (outcome == 'not_satisfied' and score != 0)
                    or (outcome == 'partial' and not 0 < score < maximum)):
                raise ValueError('Criterion score and outcome disagree.')
            if not evidence:
                raise ValueError('A scored criterion needs cited original response evidence.')
        for span in evidence:
            if criterion['response_mode'] == 'independent_speaking':
                _fields(span, ('start_ms', 'end_ms'), 'Audio evidence')
                start, end = span['start_ms'], span['end_ms']
                if (audio_duration_ms is None or type(start) is not int or type(end) is not int
                        or not 0 <= start < end <= audio_duration_ms):
                    raise ValueError('Cite an interval within the original audio, not repaired captions.')
            else:
                _fields(span, ('quote', 'start', 'end'), 'Text evidence')
                start, end = span['start'], span['end']
                if (response_text is None or type(start) is not int or type(end) is not int
                        or not 0 <= start < end <= len(response_text)
                        or span['quote'] != response_text[start:end]):
                    raise ValueError('Cited text must match the original response exactly.')
        seen.add(cid)
    return deepcopy(report)
