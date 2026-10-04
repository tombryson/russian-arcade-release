"""Bounded, contextual support for newly generated passages.

Morphology identifies candidate readings, not a dictionary sense or a mastery
claim. Unknown content words must have a source-linked annotation. Function
words and proper names have separate policies; neither licenses an untaught
construction. Old source revisions never call these checks.
"""
import re
import unicodedata
from functools import lru_cache

from utils.story_processing import get_morph

WORD = re.compile(r'[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)?')
CONTENT_PARTS = {'NOUN', 'VERB', 'INFN', 'ADJF', 'ADJS', 'ADVB', 'COMP', 'PRTF', 'PRTS', 'GRND'}
# These are discourse/grammatical words, not a list of content vocabulary known
# by every A1 learner. Their constructions remain bounded by the taught plan.
FUNCTION_LEMMAS = frozenset('в на о об у из с со к ко от до по для при без через перед после между над под я ты он она оно мы вы они себя свой мой твой наш ваш кто что какой который чей этот тот весь каждый другой один два три четыре пять шесть семь восемь девять десять и а но или да нет не ни вот это бы же ли ведь уже ещё тоже только даже именно просто очень как так где куда откуда когда почему сколько здесь там сейчас потом сегодня вчера завтра всегда часто иногда снова опять вместе сначала теперь'.split())


def normal(value):
    return ' '.join(WORD.findall(unicodedata.normalize('NFKC', value).lower().replace('ё', 'е')))


@lru_cache(maxsize=8192)
def analyses(form):
    return tuple(p for p in get_morph().parse(form) if p.is_known)


FOUNDATION_PHRASES = ({'ru': 'Привет', 'en': 'Hi'}, {'ru': 'Спасибо', 'en': 'Thank you'})


def phrase_variants(plan, foundation=()):
    """Only concrete supplied expressions can become visible support."""
    result = []
    for row in [*plan.get('supported_phrases', []), *foundation]:
        for variant in row['ru'].split(' / '):
            variant = variant.strip()
            if not variant or '...' in variant or '…' in variant:
                continue
            result.append({'text': variant, 'meaning_en': row['en']})
    return result


def used_phrases(request, body):
    result = []
    source = body.lower().replace('ё', 'е')
    for row in phrase_variants(request['language_plan'], request.get('support_policy', {}).get('foundation_phrases', [])):
        tokens = WORD.findall(row['text'].lower().replace('ё', 'е'))
        pattern = r'(?<![а-яё])' + r'[^а-яё]+'.join(map(re.escape, tokens)) + r'(?![а-яё])'
        match = re.search(pattern, source) if tokens else None
        if match and not any(normal(old['text']) == normal(row['text']) for old in result):
            result.append({'text': body[match.start():match.end()], 'meaning_en': row['meaning_en']})
    return result


def annotation_spans(payload):
    """Bind a supplied reading to one source occurrence, without choosing a sense.

The provider supplies the POS and contextual gloss. Morphology only verifies
that reading is possible. A repeated homograph cannot inherit the gloss from
another occurrence, even when its spelling and lemma are identical.
"""
    body, result = payload['text'], set()
    for row in payload['new_vocabulary']:
        sentence = row['sentence']
        start = body.find(sentence)
        if start < 0 or body.find(sentence, start + 1) >= 0:
            raise ValueError('An annotation must identify one unambiguous source sentence.')
        matches = [token for token in WORD.finditer(sentence)
                   if normal(token.group()) == normal(row['form']) and any(
                       normal(p.normal_form) == normal(row['lemma'])
                       and (p.tag.POS == row['pos'] or (p.tag.POS == 'INFN' and row['pos'] == 'VERB'))
                       for p in analyses(token.group()))]
        if len(matches) != 1:
            raise ValueError('An annotation must identify one unambiguous occurrence and lexical reading.')
        span = (start + matches[0].start(), start + matches[0].end())
        if span in result:
            raise ValueError('An unfamiliar occurrence can have only one contextual annotation.')
        result.add(span)
    return result


def unfamiliar_content(request, payload):
    """Return unresolved content surfaces with all plausible lexical readings.

A matching known analysis is enough to avoid a false rejection of a homograph;
this does not prove the writer chose its familiar sense. Sense/grammar review is
still required. Supplied phrases support their actual occurrence, not every
other word sharing one of their lemmas. An annotation supports only its cited,
unambiguous occurrence; other uses need their own contextual annotations.
"""
    body = payload['text']
    known = {normal(lemma) for lemma in request.get('known_lemmas', [])}
    annotations = annotation_spans(payload)
    function_words = {normal(word) for word in request.get('support_policy', {}).get('function_words', FUNCTION_LEMMAS)}
    support_spans = []
    # Match concrete phrases against original text to retain word boundaries.
    # Case/ё differences are spelling variants, not guessed inflections.
    folded = unicodedata.normalize('NFKC', body).lower().replace('ё', 'е')
    for row in phrase_variants(request['language_plan'], request.get('support_policy', {}).get('foundation_phrases', [])):
        tokens = WORD.findall(row['text'].lower().replace('ё', 'е'))
        if not tokens:
            continue
        pattern = r'(?<![а-яё])' + r'[^а-яё]+'.join(map(re.escape, tokens)) + r'(?![а-яё])'
        support_spans.extend((m.start(), m.end()) for m in re.finditer(pattern, folded))
    unresolved = {}
    for token in WORD.finditer(body):
        form = token.group()
        if (token.start(), token.end()) in annotations:
            continue
        if any(start <= token.start() and token.end() <= end for start, end in support_spans):
            continue
        parses = analyses(form)
        lemmas = {normal(p.normal_form) for p in parses}
        if lemmas & (known | function_words):
            continue
        # A genuine proper-name reading is not a new common-noun translation.
        # Only capitalised occurrences qualify: мир must not become a name.
        if form[0].isupper() and any(any(tag in p.tag for tag in ('Name', 'Surn', 'Patr', 'Geox')) for p in parses):
            continue
        if parses and not any(p.tag.POS in CONTENT_PARTS for p in parses):
            continue
        unresolved.setdefault(normal(form), {'form': form, 'possible_lemmas': sorted(lemmas)})
    return list(unresolved.values())


def validate_language_support(request, payload):
    unknown = unfamiliar_content(request, payload)
    if unknown:
        # Internal validation detail, not learner-facing prose. Do not silently
        # invent a gloss or make another paid request to repair the omission.
        raise ValueError('Unfamiliar passage words need contextual support: ' + ', '.join(row['form'] for row in unknown))
    if len(support_entries(request, payload)) > 8:
        raise ValueError('Keep optional word and phrase support to eight useful entries.')


def support_entries(request, payload):
    words = [{'kind': 'word', 'text': row['form'], 'meaning_en': row['meaning_en'], 'sentence': row['sentence']}
             for row in payload['new_vocabulary']]
    phrases = [{'kind': 'phrase', **row} for row in used_phrases(request, payload['text'])]
    return words + phrases
