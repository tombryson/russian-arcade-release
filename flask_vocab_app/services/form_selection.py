"""Coverage-aware selection from the existing lexical tables.

Frequency preferences match the importer, but never delete a stored form or
override an explicitly selected lesson occurrence. Count means export history,
not learner mastery; native selection history is kept separately.
"""
from collections import Counter
from functools import lru_cache
import json

from wordfreq import word_frequency


GRAMMAR_VALUES = {
    'pos': frozenset(('NOUN', 'ADJF', 'ADJS', 'COMP', 'VERB', 'INFN', 'PRTF', 'PRTS',
                      'GRND', 'NUMR', 'ADVB', 'NPRO', 'PRED', 'PREP', 'CONJ', 'PRCL', 'INTJ')),
    'case': frozenset(('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct', 'voct', 'gen1', 'gen2', 'acc2', 'loc1', 'loc2')),
    'number': frozenset(('sing', 'plur')),
    'gender': frozenset(('masc', 'femn', 'neut', 'ms-f')),
    'animacy': frozenset(('anim', 'inan')),
    'tense': frozenset(('pres', 'past', 'futr')),
    'aspect': frozenset(('perf', 'impf')),
    'mood': frozenset(('indc', 'impr')),
    'person': frozenset(('1per', '2per', '3per')),
    'voice': frozenset(('actv', 'pssv')),
    'transitivity': frozenset(('tran', 'intr')),
    'involvement': frozenset(('incl', 'excl')),
    'degree': frozenset(('comp', 'Supr')),
}


def canonical_tags(tags):
    """Serialize an analysis consistently without changing its readings or spelling."""
    if not isinstance(tags, dict) or any(not isinstance(key, str) or not isinstance(value, str)
                                         or not value for key, value in tags.items()):
        raise ValueError('Form tags must be a mapping of names to nonempty strings.')
    # Retain the existing spacing convention for older JSON-text consumers.
    return json.dumps(tags, sort_keys=True, ensure_ascii=False)


def _constraints(values):
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError('Grammatical constraints must be a mapping.')
    result = {}
    for name, value in values.items():
        if name not in GRAMMAR_VALUES:
            raise ValueError(f'Unknown grammatical constraint: {name}')
        choices = [value] if isinstance(value, str) else value
        if (not isinstance(choices, (list, tuple, set, frozenset)) or not choices
                or any(not isinstance(item, str) or item not in GRAMMAR_VALUES[name] for item in choices)):
            raise ValueError(f'Invalid grammatical constraint: {name}')
        result[name] = frozenset(choices)
    return result


@lru_cache(maxsize=10000)
def frequency(surface):
    return word_frequency(surface, 'ru')


def coverage(conn, owner=None):
    words, forms, grammar = Counter(), Counter(), Counter()
    sql = "SELECT selection FROM native_card_generation_items i JOIN native_card_batches b ON b.id=i.batch_id WHERE i.status != 'failed'"
    for row in conn.execute(sql + (' AND b.owner_id=?' if owner else ''), (owner,) if owner else ()):
        item = json.loads(row[0])
        words[item.get('word_id')] += 1
        forms[item.get('form_id')] += 1
        grammar[bucket(item.get('tags', {}))] += 1
    return words, forms, grammar


def bucket(tags):
    return tuple((key, tags[key]) for key in GRAMMAR_VALUES
                 if isinstance(tags.get(key), str) and tags[key])


def choose_form(forms, lemma, used, grammar, *, constraints=None):
    """Choose a stored reading matching every named grammatical constraint.

    Values are analyser tags, or nonempty collections of allowed alternatives.
    Missing historical tags do not satisfy a constraint. No match returns None;
    a caller must not turn that into a supposedly equivalent lemma. Constraints
    describe morphology: the task's saved sentence establishes its function.
    Source-specific occurrences continue to bypass this bulk-selection helper.
    """
    required = _constraints(constraints)

    def rank(form):
        tags = json.loads(form['tags'] or '{}')
        freq = frequency(form['form'])
        participle = tags.get('pos') in ('PRTF', 'PRTS', 'PART', 'participle', 'short participle')
        uncommon = freq < (2e-6 if participle else 6e-7)
        return (uncommon, used[form['id']], grammar[bucket(tags)],
                form['form'].casefold() == lemma.casefold(), -freq, form['id'])
    valid = []
    for form in forms:
        try:
            tags = json.loads(form['tags'] or '{}')
            canonical_tags(tags)
            if all(tags.get(name) in values for name, values in required.items()):
                valid.append(form)
        except (ValueError, TypeError):
            continue
    return min(valid, key=rank) if valid else None
