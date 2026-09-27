"""Provisional editorial crosswalk and shipped-content inventory; no learner writes.

A link compares definitions. It never transfers a grade, proves item validity,
marks a requirement covered, or changes a published course's scoring policy.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from services.curriculum_targets import curriculum_targets
from services.torfl_requirements import LEVELS, VERSION, reference_for_level

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
DATA_FILE = DATA_DIR / 'curriculum_requirement_map.json'
MAP_VERSION = 'curriculum-requirement-map-v1'
RELATIONS = {'equivalent', 'partial', 'related'}


def content_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def requirement_index():
    """Return original reference rows, each exactly once (inheritance not repeated)."""
    return {row['id']: row for level in LEVELS
            for row in reference_for_level(level)['requirements']}


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f'{label} has missing or unsupported fields.')


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and '\x00' not in value


def validate_requirement_map(data):
    """Validate total source/legacy coverage and conservative response-mode links."""
    _fields(data, ('schema_version', 'map_version', 'reference_version',
                  'legacy_catalogue_version', 'review', 'policy', 'requirements', 'mappings'), 'Map')
    legacy = curriculum_targets()
    targets = {item['id']: item for item in legacy['targets']}
    refs = requirement_index()
    if (type(data['schema_version']) is not int or data['schema_version'] != 1
            or data['map_version'] != MAP_VERSION or data['reference_version'] != VERSION
            or data['legacy_catalogue_version'] != legacy['catalogue_version']):
        raise ValueError('Unknown requirement-map versions.')
    _fields(data['review'], ('kind', 'reviewed_on', 'human_validated', 'note'), 'Review')
    if (data['review']['kind'] != 'model_review' or data['review']['human_validated'] is not False
            or not _text(data['review']['reviewed_on']) or not _text(data['review']['note'])):
        raise ValueError('This provisional map cannot claim human validation.')
    if data['policy'] != {'automatic_evidence_transfer': False,
                          'legacy_item_links_establish_reference_coverage': False}:
        raise ValueError('Definition links cannot transfer learner evidence or certify coverage.')
    if not isinstance(data['requirements'], list) or not isinstance(data['mappings'], list):
        raise ValueError('Source and legacy coverage must be explicit lists.')
    seen = set()
    for row in data['requirements']:
        _fields(row, ('requirement_id', 'source_refs', 'source_review', 'assessment_validation'), 'Reference row')
        rid = row['requirement_id']
        if not isinstance(rid, str) or rid not in refs or rid in seen:
            raise ValueError('Reference coverage contains an unknown or duplicate requirement.')
        if (row['source_refs'] != refs[rid]['source_refs'] or row['source_review'] != 'model_reviewed'
                or row['assessment_validation'] != 'not_validated'):
            raise ValueError('Preserve inspected source locators and unresolved assessment validation.')
        seen.add(rid)
    if seen != set(refs):
        raise ValueError('Every reference requirement must appear, including unmapped gaps.')
    seen = set()
    for row in data['mappings']:
        _fields(row, ('legacy_target_id', 'legacy_definition_sha256', 'review_status',
                      'links', 'unmapped_reason'), 'Legacy mapping')
        tid = row['legacy_target_id']
        if not isinstance(tid, str) or tid not in targets or tid in seen:
            raise ValueError('Legacy mappings contain an unknown or duplicate target.')
        target = targets[tid]
        if (row['legacy_definition_sha256'] != content_digest(target)
                or row['review_status'] != 'model_reviewed'):
            raise ValueError('Legacy definition changed; review its mapping explicitly.')
        links = row['links']
        if not isinstance(links, list) or (not links and not _text(row['unmapped_reason'])):
            raise ValueError('Unmapped targets need an explicit reason.')
        if links and row['unmapped_reason'] is not None:
            raise ValueError('Mapped targets cannot also be declared unmapped.')
        link_ids = set()
        for link in links:
            _fields(link, ('requirement_id', 'relation', 'rationale', 'allowed_response_modes'), 'Definition link')
            rid, relation = link['requirement_id'], link['relation']
            if (not isinstance(rid, str) or rid not in refs or rid in link_ids
                    or relation not in RELATIONS or not _text(link['rationale'])):
                raise ValueError('Each link needs a distinct known requirement, relation and rationale.')
            expected = [] if relation == 'related' else [target['response_mode']]
            if link['allowed_response_modes'] != expected:
                raise ValueError('Related content cannot authorise evidence-mode transfer.')
            if relation != 'related' and target['response_mode'] != refs[rid]['response_mode']:
                raise ValueError('Equivalent or partial links require the same evidence mode.')
            link_ids.add(rid)
        seen.add(tid)
    if seen != set(targets):
        raise ValueError('Every legacy target needs a reviewed mapping or explicit unmapped reason.')
    return deepcopy(data)


def load_requirement_map(path=None):
    return validate_requirement_map(json.loads(Path(path or DATA_FILE).read_text(encoding='utf-8')))


def _shipped_items():
    """Inspect released static assets only. Runtime-generated tasks remain unknown."""
    from services.course_releases import RELEASES, load_release
    items, unattributed = [], []
    practice = json.loads((DATA_DIR / 'course_target_practice.json').read_text(encoding='utf-8'))
    for item in practice['items']:
        items.append({'id': f"{practice['version']}:{item['id']}", 'kind': 'focused_practice',
                      'target_ids': [item['target_id']], 'has_teaching': bool(item.get('teaching')),
                      'source': 'course_target_practice.json', 'content_sha256': content_digest(item)})
    for release_id, metadata in sorted(RELEASES.items()):
        if metadata['status'] != 'published':
            continue
        data = load_release(release_id)
        for chapter in data['chapters']:
            for variant in chapter['variants']:
                for question in variant['questions']:
                    item = {'id': f"{release_id}:{variant['id']}:{question['id']}", 'kind': 'checkpoint',
                            'target_ids': question.get('target_ids', []), 'has_teaching': False,
                            'source': metadata['catalogue_file'], 'content_sha256': content_digest(question)}
                    (items if item['target_ids'] else unattributed).append(item)
                if variant.get('writing_task'):
                    unattributed.append({'id': f"{release_id}:{variant['id']}:writing-task",
                                         'kind': 'optional_writing_prompt', 'source': metadata['catalogue_file']})
    return items, unattributed


def coverage_report():
    """All requirements with traceable legacy associations, never mastery scores.

    Counts describe candidate source links only. Even an equivalent definition
    needs item-level validation before it can supply new-reference evidence.
    """
    mapping, refs = load_requirement_map(), requirement_index()
    items, unattributed = _shipped_items()
    # Import lazily: unit validation itself uses this module's reference index.
    # These functions read authored content only; they never start an activity.
    from services.curriculum_units import UNIT_IDS, LISTENING_IDS, get_unit, writing_task, listening_content
    direct = []
    for unit_id in UNIT_IDS:
        unit = get_unit(unit_id)
        for question in unit['questions']:
            direct.append({'id': f"{unit_id}:{question['id']}", 'kind': 'unit_choice',
                           'requirement_id': question['requirement_id'],
                           'source': f'curriculum_units/{unit_id}.json',
                           'content_sha256': content_digest(question)})
        for question in unit.get('forms', {}).get('questions', []):
            direct.append({'id': f"{unit_id}:{unit['forms']['version']}:{question['id']}",
                           'kind': 'unit_controlled_text', 'requirement_id': question['requirement_id'],
                           'source': f'curriculum_units/{unit_id}.json',
                           'content_sha256': content_digest(question)})
        listening = listening_content(unit_id) if unit_id in LISTENING_IDS else None
        for question in listening['items'] if listening else []:
            direct.append({'id': f"{unit_id}:{listening['version']}:{question['id']}",
                           'kind': 'unit_listening_choice', 'requirement_id': question['requirement_id'],
                           'source': f"curriculum_units/{listening['id']}.json",
                           'content_sha256': content_digest(question)})
        writing = writing_task(unit)['curriculum_contract']
        for criterion in writing['criteria']:
            direct.append({'id': f"{unit_id}:writing:{criterion['id']}", 'kind': 'unit_writing',
                           'requirement_id': criterion['requirement_id'],
                           'source': f'curriculum_units/{unit_id}.json',
                           'content_sha256': writing['content_sha256']})
    from services.speaking_curriculum import compiled_situations
    from services.speaking_evidence import speaking_task_contract
    speaking = json.loads((DATA_DIR / 'speaking_catalogue.json').read_text(encoding='utf-8'))
    metadata = {s['id']: {**s, 'conversation_role': s['variants'][0]['conversation_role']}
                for s in speaking['scenarios']}
    for scenario in compiled_situations(metadata):
        contract = speaking_task_contract(scenario)
        if contract is None:
            continue
        for criterion in contract['criteria']:
            direct.append({'id': contract['task_id'] + ':' + criterion['id'],
                           'kind': 'speaking_audio_diagnostic', 'requirement_id': criterion['requirement_id'],
                           'source': 'speaking_curriculum.json', 'content_sha256': contract['content_sha256']})
    targets = {r['legacy_target_id']: r for r in mapping['mappings']}
    if any(tid not in targets for item in items for tid in item['target_ids']):
        raise ValueError('A shipped item references an unknown legacy target.')
    rows = []
    for rid, ref in refs.items():
        links = [{'legacy_target_id': row['legacy_target_id'], **link}
                 for row in mapping['mappings'] for link in row['links'] if link['requirement_id'] == rid]
        eligible = {link['legacy_target_id'] for link in links if link['relation'] != 'related'}
        related = [deepcopy(item) for item in items if eligible.intersection(item['target_ids'])]
        authored = [deepcopy(item) for item in direct if item['requirement_id'] == rid]
        rows.append({'requirement_id': rid, 'level': rid[:2].upper(), 'domain': ref['domain'],
                     'label_en': ref['label_en'], 'response_mode': ref['response_mode'],
                     'source_refs': deepcopy(ref['source_refs']), 'legacy_links': links,
                     'candidate_items': related, 'teaching_item_count': sum(i['has_teaching'] for i in related),
                     'practice_item_count': sum(i['kind'] == 'focused_practice' for i in related),
                     'checkpoint_item_count': sum(i['kind'] == 'checkpoint' for i in related),
                     'direct_task_contracts': authored,
                     'reference_contract_status': 'diagnostic_tasks_present' if authored else 'not_audited',
                     'assessment_validation': 'not_validated'})
    relations = Counter(link['relation'] for row in mapping['mappings'] for link in row['links'])
    relations['unmapped'] = sum(not row['links'] for row in mapping['mappings'])
    return {'map_version': MAP_VERSION, 'reference_version': VERSION, 'review': deepcopy(mapping['review']),
            'requirements': rows, 'legacy_mappings': deepcopy(mapping['mappings']),
            'mapping_counts': dict(relations), 'shipped_item_counts': dict(Counter(i['kind'] for i in items)),
            'unattributed_items': unattributed,
            'direct_task_contracts': direct,
            'runtime_activity_coverage': 'not_audited',
            'note': 'Static item associations are candidates for review, not complete teaching or validated assessment coverage.'}
