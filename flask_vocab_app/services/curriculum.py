"""Versioned course topics and task levels, independent of lexical difficulty.

This catalogue is authored source data. Reading it never inserts vocabulary,
reclassifies a learner's words or changes an existing activity's level.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from services.vocabulary_topics import TOPICS

LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')
BANDS = ('A1', 'A2', 'B1', 'B2', 'C1-C2')
DATA_FILE = Path(__file__).resolve().parents[1] / 'data' / 'curriculum.json'
ACTIVITIES = ('reading', 'writing', 'translation', 'word_jumble', 'speaking')
LEGACY_LEVELS = {
    'reading': {'beginner': 'A1', 'intermediate': 'A2', 'advanced': 'B1'},
    'writing': {'beginner': 'A1', 'intermediate': 'A2', 'advanced': 'B1'},
    'word_jumble': {'easy': 'A1', 'intermediate': 'B1', 'expert': 'C1'},
    'translation': {str(index): level for index, level in enumerate(LEVELS, 1)},
}


def normalize_level(value, legacy='reading'):
    """Accept explicit course levels and known historic activity settings only."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('Choose a practice level from A1 to C2.')
    raw = str(value).strip()
    if raw.upper() in LEVELS:
        return raw.upper()
    mapped = LEGACY_LEVELS.get(legacy, {}).get(raw.lower())
    if mapped:
        return mapped
    raise ValueError('Choose a practice level from A1 to C2.')


def validate_curriculum(data):
    """Fail on incomplete or disconnected authoring, before serving a course."""
    if data.get('version') != 1 or set(data.get('levels', {})) != set(LEVELS):
        raise ValueError('Curriculum must define version 1 and all six task levels.')
    if [band['id'] for band in data.get('bands', [])] != list(BANDS):
        raise ValueError('Curriculum bands are missing or out of order.')
    topics = data.get('topics', [])
    if [topic['id'] for topic in topics] != list(TOPICS[:-1]):
        raise ValueError('Curriculum must cover the 50 canonical topics in order.')
    for index, topic in enumerate(topics):
        if topic['order'] != index + 1 or topic['band'] != BANDS[index // 10]:
            raise ValueError('Each curriculum band must contain its ten ordered topics.')
        for field in ('title_en', 'title_ru'):
            if not isinstance(topic.get(field), str) or not topic[field].strip():
                raise ValueError('Each topic requires both language titles.')
        for field in ('lemmas', 'objectives', 'grammar_focus'):
            entries = topic.get(field)
            if not isinstance(entries, list) or not entries or not all(isinstance(item, str) and item.strip() for item in entries):
                raise ValueError('Each topic requires vocabulary, objectives and grammar.')
        if len(topic['lemmas']) != len(set(topic['lemmas'])) or any(' ' in item.strip() for item in topic['lemmas']):
            raise ValueError('Use distinct single-word lemmas; put expressions in phrases.')
        if not isinstance(topic.get('phrases'), list):
            raise ValueError('Each topic must declare its useful expressions separately.')
        if set(topic.get('practice', {})) != set(ACTIVITIES) or not all(topic['practice'].values()):
            raise ValueError('Each topic requires a brief for every curriculum activity.')
        if not topic.get('practice_ru', {}).get('word_jumble'):
            raise ValueError('Each topic requires a Russian Word Jumble task brief.')
    for level in LEVELS:
        if not data['levels'][level].get('generation_guidance'):
            raise ValueError('Every task level requires generation guidance.')
    return data


@lru_cache(maxsize=1)
def _catalogue():
    return validate_curriculum(json.loads(DATA_FILE.read_text(encoding='utf-8')))


def curriculum():
    """Return an independent copy; callers cannot change the cached syllabus."""
    return deepcopy(_catalogue())


def get_topic(topic_id):
    return next((deepcopy(topic) for topic in _catalogue()['topics'] if topic['id'] == topic_id), None)


def topic_options(language='en'):
    language = 'ru' if language == 'ru' else 'en'
    options = [dict(value=topic['id'], label=topic['title_' + language], band=topic['band'],
                 level='C1' if topic['band'] == 'C1-C2' else topic['band'])
            for topic in _catalogue()['topics']]
    # The existing function-word classification spans the entire course.
    return options + [dict(value='grammar', label='Грамматика' if language == 'ru' else 'Grammar', band='', level='')]


def level_options(language='en'):
    language = 'ru' if language == 'ru' else 'en'
    return [dict(value=level, label=f"{level} · {_catalogue()['levels'][level]['label_' + language]}")
            for level in LEVELS]


def generation_context(topic_id, level, activity):
    """Supply the same teaching brief to every supported activity generator.

    A topic has a primary teaching band. Learners can still revisit it at a
    different task level. Neither choice is an estimate of word difficulty.
    """
    if activity not in ACTIVITIES:
        raise ValueError('Unknown curriculum activity.')
    level = normalize_level(level, legacy=activity)
    topic = get_topic(topic_id)
    context = {
        'curriculum_version': _catalogue()['version'],
        'topic_id': topic['id'] if topic else topic_id,
        'topic_band': topic['band'] if topic else None,
        'target_level': level,
        'objectives': topic['objectives'] if topic else [],
        'grammar_focus': topic['grammar_focus'] if topic else [],
        'target_vocabulary': topic['lemmas'] if topic else [],
        'phrases': topic['phrases'] if topic else [],
        'activity_brief': topic['practice'][activity] if topic else '',
        'activity_brief_ru': topic.get('practice_ru', {}).get(activity, '') if topic else '',
        'level_guidance': deepcopy(_catalogue()['levels'][level]['generation_guidance']),
        'adaptation': (
            'The target level controls task complexity. Use the topic objectives and '
            'grammar that fit this level; simplify or extend them when revisiting a '
            'topic from another band. Use appropriate inflections in context. '
            'Vocabulary is a teaching resource, not a closed whitelist: combine '
            'relevant saved words with new words. Do not force every listed word into one task.'
        ),
    }
    if level == 'A1' and topic and topic['band'] == 'A1':
        # The target registry validates against this syllabus. Keep this import
        # lazy so catalogue validation does not form an import/load cycle.
        from services.curriculum_targets import target_intent_for_activity
        context.update(target_intent_for_activity(topic['id'], activity))
    from services.torfl_requirements import generation_reference
    reference = generation_reference(topic_id, level, activity)
    if reference:
        context['proficiency_reference'] = reference
    return context


def band_summaries(language='en'):
    language = 'ru' if language == 'ru' else 'en'
    data = curriculum()
    result = []
    for band in data['bands']:
        topics = [topic for topic in data['topics'] if topic['band'] == band['id']]
        result.append({**band, 'label': band['name_' + language],
                       'summary': band['summary_' + language], 'topics': topics,
                       'lemma_count': len({word for topic in topics for word in topic['lemmas']})})
    return result
