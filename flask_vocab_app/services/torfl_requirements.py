"""Source-backed A1–B2 planning requirements, separate from learner evidence.

These original task specifications interpret the cited reference editions. They
are not an official exam bank, a complete lexical minimum or an award of a level.
Published journey targets and their saved observations retain their identities.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from services.vocabulary_topics import TOPICS


DATA_DIR = Path(__file__).resolve().parents[1] / 'data' / 'torfl'
VERSION = 'torfl-reference-v1'
LEVELS = ('A1', 'A2', 'B1', 'B2')
DOMAINS = {
    'language_use': ('Language use', 'Лексика и грамматика', 'contextual_selection'),
    'reading': ('Reading', 'Чтение', 'reading_selection'),
    'listening': ('Listening', 'Аудирование', 'listening_selection'),
    'writing': ('Writing', 'Письмо', 'independent_writing'),
    'speaking': ('Speaking', 'Говорение', 'independent_speaking'),
}
GRAMMAR_LABELS = {
    'noun_forms': ('Noun forms', 'Формы существительных'), 'nouns': ('Nouns', 'Существительные'),
    'cases': ('Cases', 'Падежи'), 'pronouns': ('Pronouns', 'Местоимения'),
    'adjectives': ('Adjectives', 'Прилагательные'), 'verbs': ('Verb forms', 'Формы глагола'),
    'motion': ('Verbs of motion', 'Глаголы движения'), 'numbers': ('Numbers', 'Числительные'),
    'numerals': ('Numbers', 'Числительные'), 'word_formation': ('Word formation', 'Словообразование'),
    'adverbs': ('Adverbs', 'Наречия'), 'syntax': ('Sentence structure', 'Строение предложения'),
    'particles': ('Particles', 'Частицы'), 'prepositions': ('Prepositions', 'Предлоги'),
    'aspect': ('Verb aspect', 'Вид глагола'), 'mood': ('Verb mood', 'Наклонение глагола'),
    'participles': ('Participles and adverbial participles', 'Причастия и деепричастия'),
    'discourse': ('Connecting ideas', 'Связь мыслей'),
    'syntax_transformations': ('Sentence transformations', 'Преобразование предложений'),
    'register': ('Register', 'Стиль речи'), 'vocabulary': ('Vocabulary in context', 'Лексика в контексте'),
}
CASE_LABELS = {
    'nominative': ('Nominative', 'Именительный'), 'genitive': ('Genitive', 'Родительный'),
    'dative': ('Dative', 'Дательный'), 'accusative': ('Accusative', 'Винительный'),
    'instrumental': ('Instrumental', 'Творительный'), 'prepositional': ('Prepositional', 'Предложный'),
}
_ID = re.compile(r'^(a1|a2|b1|b2)\.[a-z_]+\.[a-z0-9]+(?:-[a-z0-9]+)*$')
_ACTIVITY_DOMAIN = {'reading': 'reading', 'writing': 'writing',
                    'translation': 'language_use', 'word_jumble': 'language_use', 'speaking': 'speaking'}


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and '\x00' not in value


def validate_reference(data):
    """Reject incomplete sources, confused evidence modes and unknown topics."""
    if not isinstance(data, dict) or data.get('schema_version') != 1 or data.get('catalogue_version') != VERSION:
        raise ValueError('Unknown TORFL reference schema or version.')
    level = data.get('level')
    if level not in LEVELS:
        raise ValueError('Reference levels are A1, A2, B1 and B2.')
    predecessor = None if level == 'A1' else LEVELS[LEVELS.index(level) - 1]
    if data.get('extends') != predecessor:
        raise ValueError('Reference levels must preserve cumulative learning.')
    sources = data.get('sources')
    if not isinstance(sources, list) or not sources or any(not isinstance(s, dict) for s in sources):
        raise ValueError('Each level needs its inspected sources.')
    source_ids = set()
    for source in sources:
        if any(not _text(source.get(field)) for field in ('id', 'title', 'edition', 'url', 'accessed', 'kind', 'note')):
            raise ValueError('Sources require edition, location and provenance notes.')
        if source['id'] in source_ids or source['kind'] not in ('standard', 'sample_exam', 'model_test'):
            raise ValueError('Source IDs must be distinct and source kinds explicit.')
        if urlparse(source['url']).scheme != 'https' or not urlparse(source['url']).netloc:
            raise ValueError('Sources require direct HTTPS references.')
        source_ids.add(source['id'])
    entries = data.get('requirements')
    if not isinstance(entries, list) or not entries:
        raise ValueError('A reference level needs observable requirements.')
    ids, domains = set(), set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError('A requirement must be an object.')
        if any(not _text(item.get(field)) for field in ('id', 'domain', 'category', 'label_en', 'label_ru', 'expectation', 'response_mode')):
            raise ValueError('A requirement needs a name, scope and evidence mode.')
        if not _ID.fullmatch(item['id']) or not item['id'].startswith(level.lower() + '.') or item['id'] in ids:
            raise ValueError('Use distinct semantic requirement IDs at the declared level.')
        domain = item['domain']
        if domain not in DOMAINS or item['response_mode'] != DOMAINS[domain][2]:
            raise ValueError('Selection cannot stand in for independent writing or speaking.')
        if domain == 'language_use' and item['category'] not in GRAMMAR_LABELS:
            raise ValueError('Language requirements need a named grammatical category.')
        if item['category'] == 'cases' and item.get('case') not in CASE_LABELS:
            raise ValueError('A case function must identify its case.')
        topics = item.get('topic_ids')
        if (not isinstance(topics, list) or not topics or any(not isinstance(t, str) for t in topics)
                or len(topics) != len(set(topics))
                or (topics != ['*'] and any(t not in TOPICS for t in topics))):
            raise ValueError('Requirements must reference canonical topics or an explicit cross-topic scope.')
        refs = item.get('source_refs')
        if (not isinstance(refs, list) or not refs or any(not isinstance(ref, dict)
                or ref.get('source_id') not in source_ids or not _text(ref.get('locator')) for ref in refs)):
            raise ValueError('Each requirement needs an inspected source and page or section locator.')
        ids.add(item['id'])
        domains.add(domain)
    if domains != set(DOMAINS):
        raise ValueError('A level reference must cover all five assessment domains.')
    return data


@lru_cache(maxsize=1)
def _catalogue():
    result = {}
    sources = {}
    for level in LEVELS:
        data = validate_reference(json.loads((DATA_DIR / f'{level}.json').read_text(encoding='utf-8')))
        if data['level'] != level:
            raise ValueError('Reference file and level disagree.')
        for source in data['sources']:
            if source['id'] in sources and source != sources[source['id']]:
                raise ValueError('Shared source IDs must identify the same edition and provenance.')
            sources[source['id']] = source
        result[level] = data
    return result


def reference_for_level(level, *, cumulative=False):
    """Read definitions only; never look up a profile or infer achievement."""
    if level not in LEVELS:
        return None
    data = deepcopy(_catalogue()[level])
    if cumulative:
        included = LEVELS[:LEVELS.index(level) + 1]
        data['requirements'] = [deepcopy(item) for band in included for item in _catalogue()[band]['requirements']]
        sources = {source['id']: source for band in included for source in _catalogue()[band]['sources']}
        data['sources'] = deepcopy(list(sources.values()))
    return data


def requirement_groups(level, language='en'):
    """Compact curriculum reference; earlier levels are linked, not duplicated."""
    data = reference_for_level(level)
    if data is None:
        return None
    lang = 'ru' if language == 'ru' else 'en'
    groups = []
    for domain, names in DOMAINS.items():
        items = [{**item, 'label': item['label_' + lang]} for item in data['requirements'] if item['domain'] == domain]
        sections = {}
        if domain == 'language_use':
            for item in items:
                key = item.get('case', item['category'])
                labels = CASE_LABELS[key] if item['category'] == 'cases' else GRAMMAR_LABELS[key]
                sections.setdefault(key, {'label': labels[1 if lang == 'ru' else 0], 'items': []})['items'].append(item)
        groups.append({'id': domain, 'label': names[1 if lang == 'ru' else 0],
                       'items': items, 'sections': list(sections.values())})
    return {'level': level, 'extends': data['extends'], 'version': VERSION, 'groups': groups, 'sources': data['sources']}


def _varied(items, limit):
    """Keep a brief from being occupied entirely by the first grammar category."""
    chosen, categories = [], set()
    for item in items:
        if item['category'] not in categories:
            chosen.append(item)
            categories.add(item['category'])
            if len(chosen) == limit:
                return chosen
    for item in items:
        if item not in chosen:
            chosen.append(item)
            if len(chosen) == limit:
                break
    return chosen


def _at_level_first(items, level, limit):
    current = [item for item in items if item['id'].startswith(level.lower() + '.')]
    chosen = _varied(current, limit)
    if len(chosen) < limit:
        earlier = [item for item in items if item not in current]
        chosen += _varied(earlier, limit - len(chosen))
    return chosen


def generation_reference(topic_id, level, activity):
    """A bounded planning brief, never a claim that a generated task tests it.

    Existing activities save/grade their actual task. This reference must not
    turn every candidate construction into a required response or a target
    observation. Higher-level practice keeps lower-level language available.
    """
    if level not in LEVELS or activity not in _ACTIVITY_DOMAIN:
        return None
    data = reference_for_level(level, cumulative=True)
    domain = _ACTIVITY_DOMAIN[activity]
    # Current-level demands come first, even when an earlier topic is reused.
    relevant = [item for item in data['requirements'] if topic_id in item['topic_ids'] or item['topic_ids'] == ['*']]
    relevant.sort(key=lambda item: (not item['id'].startswith(level.lower() + '.'), topic_id not in item['topic_ids']))
    # Controlled sentence tasks do not ask for an independent letter or essay.
    # Audio-only criteria belong to listening and are excluded from text tasks.
    selected = _at_level_first([item for item in relevant if item['domain'] == domain], level,
                              8 if domain == 'language_use' else 4)
    if domain != 'language_use':
        selected += _at_level_first([item for item in relevant if item['domain'] == 'language_use'], level, 4)
    return {'catalogue_version': VERSION, 'level': level, 'scope': 'teaching_reference',
            'requirements': [{key: item[key] for key in ('id', 'domain', 'expectation', 'response_mode')} for item in selected],
            'use': ('Use relevant requirements to plan one focused task at the selected level. '
                    'This is a sample of the level reference, not a checklist for every answer. '
                    'Assess only the demands explicitly set by the saved task. '
                    'Earlier constructions remain available. Topic band and word difficulty are separate. '
                    'Do not claim target achievement, a level pass or certification from these IDs. '
                    'Reply selection is not spoken production; written answers do not establish listening. '
                    'Prioritise communication, then explain a useful correction; distinguish meaning-changing errors from minor slips.')}
