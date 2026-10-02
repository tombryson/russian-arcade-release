"""Editorial delivery coverage, separate from learner records and proficiency.

Every inspected source requirement has a proposed home and visible gaps. Draft
task associations are partial, never proof that a requirement has been mastered.
Media status is checked against files on disk rather than inferred from a link.
"""
from collections import Counter
from copy import deepcopy
import json

from services.curriculum_requirement_map import content_digest, requirement_index
from services.curriculum_sequence_content import DATA_DIR, load_asset, media_inventory

VERSION = 'curriculum-delivery-coverage-v1'
STAGES = ('teaching', 'recognition', 'production', 'assessment')
DATA_FILE = DATA_DIR / 'curriculum_coverage' / (VERSION + '.json')


def _fields(value, names, label):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError(f'{label} has missing or unexpected fields.')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_coverage(data):
    _fields(data, ('schema_version', 'version', 'reference_version', 'policy', 'review', 'requirements'), 'Coverage')
    if (type(data['schema_version']) is not int or data['schema_version'] != 1
            or data['version'] != VERSION or data['reference_version'] != 'torfl-reference-v1'):
        raise ValueError('Unknown coverage version.')
    if data['policy'] != {'assessment_validated': False, 'automatic_evidence_transfer': False,
                          'task_counts_are_proficiency': False}:
        raise ValueError('The delivery inventory cannot certify assessment or transfer evidence.')
    if data['review'] != {'kind': 'internal_model', 'independently_validated': False}:
        raise ValueError('The current delivery inventory has no independent validation.')
    if not isinstance(data['requirements'], list):
        raise ValueError('Source requirements must be explicit records.')
    refs, seen, assets = requirement_index(), set(), {}
    for row in data['requirements']:
        _fields(row, ('requirement_id', 'source_refs', 'allocation', 'applicability', *STAGES), 'Requirement')
        rid = row['requirement_id']
        if not isinstance(rid, str) or rid not in refs or rid in seen or row['source_refs'] != refs[rid]['source_refs']:
            raise ValueError('Each inspected source requirement must occur once with its original locators.')
        allocation = row['allocation']
        _fields(allocation, ('package', 'unit_candidate', 'unit_status', 'assessment_family', 'assessment_validation', 'gap'), 'Allocation')
        if (allocation['package'] not in ('P1', 'P2', 'P4')
                or allocation['unit_status'] not in ('authored_candidate', 'planned')
                or allocation['assessment_validation'] != 'not_validated'
                or any(not _text(allocation[key]) for key in ('unit_candidate', 'assessment_family', 'gap'))):
            raise ValueError('Every allocation needs a candidate and an explicit unvalidated gap.')
        if allocation['unit_status'] == 'authored_candidate' and not (DATA_DIR / 'curriculum_units' / (allocation['unit_candidate'] + '.json')).is_file():
            raise ValueError('An authored candidate must exist.')
        if (rid.startswith('a1.') and allocation['package'] == 'P4') or (not rid.startswith('a1.') and allocation['package'] != 'P4'):
            raise ValueError('Later-band planning must remain separate from A1 delivery.')
        if allocation['package'] == 'P1' and load_asset(allocation['assessment_family'])['kind'] != 'task_group':
            raise ValueError('The current delivery package must reference its authored transfer family.')
        _fields(row['applicability'], STAGES, 'Applicability')
        for stage in STAGES:
            applicability = row['applicability'][stage]
            _fields(applicability, ('applicable', 'reason'), 'Stage applicability')
            if type(applicability['applicable']) is not bool or not _text(applicability['reason']):
                raise ValueError('Every stage needs an applicability decision and explanation.')
            if not isinstance(row[stage], list) or (not applicability['applicable'] and row[stage]):
                raise ValueError('Non-applicable stages cannot also claim content.')
            stage_ids = set()
            for entry in row[stage]:
                _fields(entry, ('content_id', 'version', 'content_sha256', 'criterion_ids', 'status',
                                'relation', 'review', 'scope', 'prerequisites', 'response_modes'), 'Content association')
                identity = entry['content_id']
                if not isinstance(identity, str) or identity in stage_ids:
                    raise ValueError('Content associations must be distinct within a stage.')
                if identity not in assets:
                    assets[identity] = load_asset(identity)
                asset = assets[identity]
                criteria = [c for c in asset['criteria'] if c['requirement_id'] == rid]
                if (entry['version'] != asset['version'] or entry['content_sha256'] != content_digest(asset)
                        or entry['status'] != asset['status'] or entry['review'] != asset['review']
                        or entry['relation'] != 'partial' or not _text(entry['scope'])
                        or not isinstance(entry['prerequisites'], list) or not entry['prerequisites']
                        or any(not _text(p) for p in entry['prerequisites'])):
                    raise ValueError('An association must pin unchanged partial content and honest review status.')
                if (entry['criterion_ids'] != [c['id'] for c in criteria]
                        or entry['response_modes'] != sorted({c['response_mode'] for c in criteria})):
                    raise ValueError('Associated criteria must match the frozen authored task.')
                if stage == 'teaching':
                    if asset['kind'] != 'teaching' or rid not in ('a1.language.prepositional-location', 'a1.language.accusative-destination'):
                        raise ValueError('This teaching asset only covers its declared grammar functions.')
                elif not criteria:
                    raise ValueError('A task association needs actual requirement criteria.')
                if stage == 'recognition' and asset['kind'] not in ('choice', 'reading', 'listening'):
                    raise ValueError('Recognition must not be substituted for production.')
                if stage == 'production' and asset['kind'] not in ('controlled_text', 'writing', 'speaking'):
                    raise ValueError('Production needs a produced response.')
                if (stage == 'assessment') != identity.startswith('location-transfer-'):
                    raise ValueError('Only the authored transfer family supplies scoped diagnostic assessment.')
                stage_ids.add(identity)
        seen.add(rid)
    if seen != set(refs):
        raise ValueError('Every source requirement needs an allocation or visible gap.')
    return deepcopy(data)


def load_coverage():
    return validate_coverage(json.loads(DATA_FILE.read_text(encoding='utf-8')))


def delivery_report():
    """Return static editorial data and local media checks; never open a learner DB."""
    data = load_coverage()
    media = {}
    for row in data['requirements']:
        for stage in STAGES:
            for entry in row[stage]:
                identity = entry['content_id']
                if identity not in media:
                    media[identity] = media_inventory(load_asset(identity))
        row['stage_status'] = {stage: ('not_applicable' if not row['applicability'][stage]['applicable']
                                      else 'draft' if row[stage] else 'missing') for stage in STAGES}
        # Keep controlled completion distinct from original writing/speech.
        row['production_modes'] = dict(Counter(mode for entry in row['production'] for mode in entry['response_modes']))
    data['media'] = media
    data['level_counts'] = {level: sum(r['requirement_id'].startswith(level.lower() + '.') for r in data['requirements'])
                            for level in ('A1', 'A2', 'B1', 'B2')}
    return data
