"""Compile authored speaking situations into reproducible curriculum snapshots.

The bundles contain compatible facts, never independently sampled prices,
connections or ingredients. Compilation is free and runs during migration.
SQLite owns the published catalogue; attempts keep their original snapshots.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from services.curriculum import generation_context, get_topic

DATA_FILE = Path(__file__).resolve().parents[1] / 'data' / 'speaking_curriculum.json'
CATEGORIES = ('cafe', 'shop', 'directions', 'station', 'meet-someone')
LEVELS = ('A1', 'A2')


def _check_facts(bundle):
    """Reject incompatible authored money/timetable bundles before publication."""
    facts = bundle['facts']
    menu = bundle.get('menu', {})
    if menu and any(type(price) is not int or price <= 0 for price in menu.values()):
        raise ValueError('Speaking menu prices must be positive whole roubles.')
    if menu and 'total' in facts:
        total = sum(menu[facts[item]] * facts.get(item + '_count', 1)
                    for item in ('food', 'drink') if item in facts)
        if facts['total'] != total:
            raise ValueError('Speaking menu and order total disagree.')
    if 'change' in facts and facts['change'] != facts['cash'] - facts['price']:
        raise ValueError('Speaking change does not match the cash and price.')
    if 'unit_price' in facts and 'total' in facts:
        if facts['total'] != facts['unit_price'] * facts['ticket_count']:
            raise ValueError('Speaking ticket total does not match the passenger count.')
    if 'transfer_arrival' in facts and facts['transfer_arrival'] >= facts['connection_departure']:
        raise ValueError('A speaking train connection leaves before the traveller arrives.')
    if 'options' in facts:
        options = facts['options']
        if not all(option['departure'] < option['change'] < option['arrival'] for option in options):
            raise ValueError('Speaking train connections are not in time order.')
        if sum(option['arrival'] < facts['deadline'] for option in options) != 1:
            raise ValueError('A timed speaking task needs exactly one suitable connection.')


@lru_cache(maxsize=1)
def _content():
    data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    if data.get('version') != 2:
        raise ValueError('Unknown speaking curriculum version.')
    groups = data.get('groups', [])
    keys = [(g['scenario_id'], g['target_level']) for g in groups]
    if len(keys) != len(set(keys)) or set(keys) != {(c, l) for c in CATEGORIES for l in LEVELS}:
        raise ValueError('Speaking requires an authored group for each category and level.')
    for group in groups:
        if get_topic(group['topic_id']) is None:
            raise ValueError('Speaking references an unknown curriculum topic.')
        for field in ('title', 'title_ru', 'description', 'description_ru'):
            if not group.get(field):
                raise ValueError('Speaking groups require bilingual catalogue text.')
        bundles = group.get('bundles', [])
        if len(bundles) < 3 or len({b['id'] for b in bundles}) != len(bundles):
            raise ValueError('Each speaking category/level requires three distinct situations.')
        facts = [json.dumps(b['facts'], sort_keys=True, ensure_ascii=False) for b in bundles]
        if len(set(facts)) != len(facts):
            raise ValueError('Speaking variations must change the facts, not only the wording.')
        for bundle in bundles:
            _check_facts(bundle)
            if not all(len(bundle.get(field, [])) == 3 for field in ('goals', 'goals_ru', 'completion_criteria')):
                raise ValueError('Speaking bundles need three matching bilingual objectives and criteria.')
            if not bundle.get('worker_brief') or not bundle.get('description') or not bundle.get('description_ru'):
                raise ValueError('Speaking bundles require both learner context and character facts.')
    return data


def scenario_for_topic(topic_id, level):
    """Return a supported topic/level route; absent topics remain explicitly unbuilt."""
    return next((g['scenario_id'] for g in _content()['groups']
                 if g['topic_id'] == topic_id and g['target_level'] == level), None)


def level_details():
    return [dict(scenario_id=g['scenario_id'], target_level=g['target_level'],
                 **{key:g[key] for key in ('title','title_ru','description','description_ru','topic_id')})
            for g in _content()['groups']]


def compiled_situations(category_metadata):
    """Return independent snapshots ready for insertion; never change vocabulary."""
    result = []
    closing = ('Когда договорённость достигнута, кратко подтверди её и дай собеседнику попрощаться. '
               'Затем естественно закончи разговор, не начинай новую тему. '
               'При явном прощании можно закончить раньше. Пауза или ошибка не означают конец. '
               'Не объявляй оценки и учебные цели.')
    for group in _content()['groups']:
        category = category_metadata[group['scenario_id']]
        level = group['target_level']
        curriculum = generation_context(group['topic_id'], level, 'speaking')
        for bundle in group['bundles']:
            seed = f"{group['scenario_id']}-{level.lower()}-{bundle['id']}-v2"
            grammar = bundle.get('grammar_focus', group['grammar_focus'])
            requirements = [dict(id=f'objective-{i+1}', kind='communicative',
                                 description=objective, evidence_hint=bundle['completion_criteria'][i])
                            for i, objective in enumerate(bundle['goals'])]
            requirements.append(dict(id='grammar-in-context', kind='grammar', description=grammar[0],
                                     evidence_hint=bundle.get('grammar_evidence_hint',group['grammar_evidence_hint'])))
            contract = dict(version='speaking-curriculum-v2', target_level=level,
                alignment_status='authored_curriculum_task', topic_id=group['topic_id'],
                communicative_objectives=list(bundle['goals']), grammar_focus=list(grammar),
                vocabulary_focus=list(curriculum['target_vocabulary']), requirements=requirements,
                agent_complexity=dict(max_sentences_per_turn=2, one_question_at_a_time=True,
                    task_complexity=('One concrete request at a time; familiar words and whole-hour times. '
                                     'Do not add reasons, obstacles or extra conditions.' if level=='A1' else
                                     'Include the authored clarification, condition or alternative. '
                                     'Keep it routine and concrete; do not replace it with a simple order or greeting.')),
                support=dict(repeat_on_request=True, rephrase_on_request=True,
                             offer_two_choices_when_stuck=True, supply_full_task_answer=False),
                assessment_policy=('Assess the forms and meaning actually attempted. These are task targets, '
                    'not a proficiency certificate. Accept correct short replies and alternative phrasing. '
                    'Fluent speakers need not recite the grammar example; guided examples must demonstrate it.'))
            snapshot = dict(id=seed, seed=seed, scenario_id=group['scenario_id'], scenario_version=2,
                target_level=level, category_title=group['title'], category_title_ru=group['title_ru'],
                role=category['role'], role_ru=category['role_ru'], icon=category['icon'], sign=category['sign'],
                conversation_role=category['conversation_role'],
                title=bundle['title'], title_ru=bundle['title_ru'],
                description=bundle['description'], description_ru=bundle['description_ru'],
                opening=bundle.get('opening',group['opening']),
                opening_english=bundle.get('opening_english',group['opening_english']),
                goals=list(bundle['goals']), goals_ru=list(bundle['goals_ru']),
                goal_ids=[f'objective-{i+1}' for i in range(3)],
                completion_criteria=list(bundle['completion_criteria']),
                worker_brief=bundle['worker_brief'], closing_instruction=closing,
                menu=dict(bundle.get('menu',{})), reference=deepcopy(bundle.get('reference',{})),
                complication='', complication_ru='', learning_contract=contract,
                curriculum_context=deepcopy(curriculum),
                variation=dict(version=2, family_id=f"{group['scenario_id']}-{level.lower()}",
                               bundle_id=bundle['id'], facts=deepcopy(bundle['facts'])))
            result.append(snapshot)
    return result
