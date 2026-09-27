"""Authored, mode-specific A1 targets layered over the canonical curriculum.

The original objectives and grammar strings remain the syllabus authority.
These semantic IDs identify observable requirements, never array positions or
learner achievements. Reading this catalogue creates no learner evidence. In
particular, old topic scores cannot establish any of these targets.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re

from services.curriculum import curriculum


DATA_FILE = Path(__file__).resolve().parents[1] / 'data' / 'curriculum_targets.json'
RESPONSE_MODES = {
    'reading_selection': ('read', 'receptive'),
    'listening_selection': ('listen', 'receptive'),
    'contextual_selection': ('select', 'contextual_form'),
    'independent_writing': ('write', 'independent_production'),
    'independent_speaking': ('speak', 'independent_production'),
}
PRIMARY_SECTIONS = {
    'home': ('greetings', 'family', 'home'),
    'postoffice': ('numbers', 'daily_activities'),
    'market': ('food', 'colors', 'clothing'),
    'leavingtown': ('places', 'weather'),
}
TARGET_GROUPS = (
    'required_target_ids', 'additional_practice_target_ids',
    'independent_production_target_ids',
)
_ACTIVITY_RESPONSE_MODES = {
    'reading': 'reading_selection',
    'writing': 'independent_writing',
    'translation': 'independent_writing',
    # Word Jumble asks the learner to write a sentence using displayed words.
    'word_jumble': 'independent_writing',
    'speaking': 'independent_speaking',
}
_TARGET_ID = re.compile(r'a1\.[a-z_]+\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.(read|listen|select|write|speak)')


def _strings(value, description, *, allow_empty=False):
    if (not isinstance(value, list) or (not value and not allow_empty)
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(value) != len(set(value))):
        raise ValueError(f'{description} must be a list of distinct nonempty strings.')
    return value


def _text(record, field):
    if not isinstance(record.get(field), str) or not record[field].strip():
        raise ValueError(f'Each target or section requires {field}.')


def validate_curriculum_targets(data, source_curriculum=None):
    """Reject disconnected targets, lost source coverage and production gates.

    Source indices locate the readable syllabus text for validation only. Target
    identities stay semantic when source text is corrected or reordered. This
    first catalogue intentionally covers A1; later levels need authored mappings
    before their coverage can be claimed.
    """
    source = curriculum() if source_curriculum is None else source_curriculum
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Target catalogue must use schema version 1.')
    if data.get('catalogue_version') != 'a1-targets-v1':
        raise ValueError('Unknown authored target catalogue version.')
    if data.get('curriculum_version') != source.get('version') or data.get('levels') != ['A1']:
        raise ValueError('Target catalogue must reference the current A1 curriculum.')
    if set(_strings(data.get('response_modes'), 'Response modes')) != set(RESPONSE_MODES):
        raise ValueError('Target catalogue must declare all supported response modes.')
    policy = data.get('evidence_policy')
    if (not isinstance(policy, dict)
            or policy.get('legacy_topic_scores_are_target_evidence') is not False
            or policy.get('independent_production_required') is not False
            or policy.get('categories') != ['introduced', 'practised', 'demonstrated', 'needs_practice']
            or policy.get('required_target_preparation') != ['introduced', 'practised']):
        raise ValueError('Keep target evidence distinct from legacy scores and production diagnostic.')
    for field in ('demonstration_requires', 'supporting_grammar_references', 'listening_evidence', 'scope'):
        _text(policy, field)

    topics = {topic['id']: topic for topic in source['topics'] if topic['band'] == 'A1'}
    primary_by_topic = {topic: section for section, ids in PRIMARY_SECTIONS.items() for topic in ids}
    if set(topics) != set(primary_by_topic):
        raise ValueError('Primary sections must cover exactly the canonical A1 topics.')
    sections = data.get('sections')
    if (not isinstance(sections, list) or not all(isinstance(item, dict) for item in sections)
            or [item.get('id') for item in sections] != list(PRIMARY_SECTIONS)):
        raise ValueError('A1 sections must follow the authored home-to-leaving-town route.')
    for index, section in enumerate(sections, 1):
        if (section.get('order') != index or section.get('level') != 'A1'
                or section.get('primary_topic_ids') != list(PRIMARY_SECTIONS[section['id']])):
            raise ValueError('Each A1 topic must have its exact primary section once.')
        if section.get('independent_production_required') is not False:
            raise ValueError('Independent writing and speaking are optional diagnostics.')
        for field in ('title_en', 'title_ru'):
            _text(section, field)
        for group in TARGET_GROUPS:
            _strings(section.get(group), group, allow_empty=group == 'additional_practice_target_ids')

    targets = data.get('targets')
    if not isinstance(targets, list) or not targets or not all(isinstance(item, dict) for item in targets):
        raise ValueError('The catalogue requires authored targets.')
    _strings([target.get('id') for target in targets], 'Target IDs')
    by_id = {target['id']: target for target in targets}
    coverage = Counter()
    for target in targets:
        target_id = target['id']
        topic_id = target.get('topic_id')
        mode = target.get('response_mode')
        if not isinstance(topic_id, str) or topic_id not in topics:
            raise ValueError('Every target must reference a canonical A1 topic.')
        if not isinstance(mode, str) or mode not in RESPONSE_MODES:
            raise ValueError('Unknown target response mode.')
        suffix, evidence_kind = RESPONSE_MODES[mode]
        if (not _TARGET_ID.fullmatch(target_id) or not target_id.startswith(f'a1.{topic_id}.')
                or not target_id.endswith('.' + suffix)):
            raise ValueError('Use semantic target IDs matching their topic and response mode.')
        if (type(target.get('version')) is not int or target['version'] < 1
                or target.get('curriculum_version') != source['version']
                or target.get('target_level') != 'A1'
                or target.get('primary_section_id') != primary_by_topic[topic_id]
                or target.get('evidence_kind') != evidence_kind):
            raise ValueError('Each target requires consistent version, level, section and evidence metadata.')
        for field in ('title_en', 'title_ru', 'expected_response', 'marking_guidance', 'rubric_version'):
            _text(target, field)
        source_ref = target.get('source')
        if not isinstance(source_ref, dict) or type(source_ref.get('index')) is not int:
            raise ValueError('Each target requires a precise readable curriculum source.')
        source_field = 'grammar_focus' if target.get('kind') == 'grammar' else 'objectives'
        if target.get('kind') not in ('objective', 'grammar') or source_ref.get('field') != source_field:
            raise ValueError('Target kind must match its curriculum source field.')
        source_index = source_ref['index']
        source_entries = topics[topic_id][source_field]
        if not 0 <= source_index < len(source_entries) or source_ref.get('text') != source_entries[source_index]:
            raise ValueError('Target source must match the existing readable curriculum requirement.')
        if (target['kind'] == 'grammar') != (mode == 'contextual_selection'):
            raise ValueError('Grammar selection and mode-specific objectives must remain distinct.')
        coverage[(topic_id, source_field, source_index, mode)] += 1
        refs = _strings(target.get('supporting_grammar_target_ids'), 'Supporting grammar references',
                        allow_empty=target['kind'] == 'grammar')
        if target['kind'] == 'grammar' and refs:
            raise ValueError('A grammar target does not inherit evidence from another target.')
        for ref in refs:
            related = by_id.get(ref)
            if not related or related.get('kind') != 'grammar' or related.get('topic_id') != topic_id:
                raise ValueError('Supporting grammar must reference an authored target in the same topic.')

    expected_coverage = Counter({
        (topic_id, field, index, mode): 1
        for topic_id, topic in topics.items()
        for field in ('objectives', 'grammar_focus')
        for index in range(len(topic[field]))
        for mode in (('contextual_selection',) if field == 'grammar_focus' else
                     ('reading_selection', 'listening_selection', 'independent_writing', 'independent_speaking'))
    })
    if coverage != expected_coverage:
        raise ValueError('Cover every A1 objective in each response mode and every grammar focus exactly once.')

    for section in sections:
        section_ids = {target['id'] for target in targets if target['primary_section_id'] == section['id']}
        grouped = [target_id for group in TARGET_GROUPS for target_id in section[group]]
        if len(grouped) != len(set(grouped)) or set(grouped) != section_ids:
            raise ValueError('Section groups must partition its targets without missing, foreign or repeated references.')
        required = [by_id[target_id] for target_id in section['required_target_ids']]
        if ({target['topic_id'] for target in required} != set(section['primary_topic_ids'])
                or any(target['evidence_kind'] == 'independent_production' for target in required)):
            raise ValueError('Required receptive or selected-response targets must cover each primary topic.')
        production_ids = {target['id'] for target in targets
                          if target['primary_section_id'] == section['id']
                          and target['evidence_kind'] == 'independent_production'}
        if set(section['independent_production_target_ids']) != production_ids:
            raise ValueError('Independent writing and speaking must be separately identified as optional.')
    return data


def load_curriculum_targets(path=None):
    """Read and validate an authored catalogue without a database or Flask app."""
    target_path = DATA_FILE if path is None else Path(path)
    return validate_curriculum_targets(json.loads(target_path.read_text(encoding='utf-8')))


@lru_cache(maxsize=1)
def _catalogue():
    return load_curriculum_targets()


def curriculum_targets():
    """Return an independent copy of the complete authored target catalogue."""
    return deepcopy(_catalogue())


def get_target(target_id):
    return next((deepcopy(target) for target in _catalogue()['targets'] if target['id'] == target_id), None)


def targets_for_topic(topic_id):
    """Return A1 targets in authoring order, without changing canonical topics."""
    return [deepcopy(target) for target in _catalogue()['targets'] if target['topic_id'] == topic_id]


def get_section(section_id):
    return next((deepcopy(section) for section in _catalogue()['sections'] if section['id'] == section_id), None)


def sections_for_level(level='A1'):
    return [deepcopy(section) for section in _catalogue()['sections'] if section['level'] == level]


def section_for_topic(topic_id):
    return next((deepcopy(section) for section in _catalogue()['sections']
                 if topic_id in section['primary_topic_ids']), None)


def targets_for_section(section_id, *, required_only=False):
    """Return targets in catalogue order, or the authored required-subset order.

    These are preparation requirements, not a report that a learner has met
    them. Checkpoint content must separately declare what each response assesses.
    """
    section = get_section(section_id)
    if section is None:
        return []
    if required_only:
        targets = {target['id']: target for target in _catalogue()['targets']}
        return [deepcopy(targets[target_id]) for target_id in section['required_target_ids']]
    return [deepcopy(target) for target in _catalogue()['targets'] if target['primary_section_id'] == section_id]


def target_intent_for_activity(topic_id, activity):
    """Describe A1 teaching intent for a saved task, never assessment success.

    A generator still needs to save which targets its actual questions practise
    and what response supports each observation. The topic's full candidate list
    alone must not create target evidence or satisfy a readiness requirement.
    """
    if activity not in _ACTIVITY_RESPONSE_MODES:
        raise ValueError('Unknown curriculum activity.')
    mode = _ACTIVITY_RESPONSE_MODES[activity]
    ids = [target['id'] for target in _catalogue()['targets']
           if target['topic_id'] == topic_id and target['response_mode'] == mode]
    return {
        'target_catalogue_version': _catalogue()['catalogue_version'] if ids else None,
        'intended_target_ids': ids,
        'target_evidence_guidance': (
            'These IDs identify candidate teaching intent only. Save the targets '
            'actually introduced, practised or assessed by each task item and '
            'the response supporting each observation. An overall activity score '
            'or the presence of a target ID establishes no target achievement. '
            'Reading and contextual selection do not demonstrate independent '
            'writing or speaking; supporting grammar requires separate evidence. '
            'Speaking step-through reply selection is supported practice, not '
            'independent spoken production.'
        ),
    }
