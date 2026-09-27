"""Tutor feedback stays structured without turning it into a checklist on screen."""
import re


def text(limit, required=True):
    return {'type': 'string', 'minLength': 1 if required else 0, 'maxLength': limit}


def object_schema(properties):
    return {'type': 'object', 'additionalProperties': False,
            'properties': properties, 'required': list(properties)}


FEEDBACK_SCHEMA = object_schema({
    'score': {'type': 'integer', 'minimum': 0, 'maximum': 4},
    'commentary': text(2000),
    'corrections': {'type': 'array', 'maxItems': 3, 'items': object_schema({
        'original': text(200), 'replacement': text(200),
        'explanation': {**text(280), 'description': 'One short, friendly explanation in the interface language. Explain only the change needed, in everyday language.'},
    })},
    'polished_sentence': text(1500, False),
    'phrasing_note': text(800, False),
    'extension': text(600, False),
})


def validate_feedback(value, answer, language=None):
    if not isinstance(value, dict) or set(value) != set(FEEDBACK_SCHEMA['required']):
        raise ValueError('Invalid tutor feedback')
    if type(value['score']) is not int or not 0 <= value['score'] <= 4:
        raise ValueError('Invalid score')
    for name in ('commentary', 'polished_sentence', 'phrasing_note', 'extension'):
        field = FEEDBACK_SCHEMA['properties'][name]
        if not isinstance(value[name], str) or len(value[name]) > field['maxLength']:
            raise ValueError('Invalid feedback text')
        if field['minLength'] and not value[name].strip():
            raise ValueError('Empty tutor response')
    if value['phrasing_note'].strip() and not value['polished_sentence'].strip():
        raise ValueError('Phrasing advice needs its example')
    corrections = value['corrections']
    if not isinstance(corrections, list) or len(corrections) > 3:
        raise ValueError('Invalid corrections')
    if corrections and value['extension'].strip():
        raise ValueError('Finish corrections before offering an extension')
    seen = set()
    for correction in corrections:
        if not isinstance(correction, dict) or set(correction) != {'original', 'replacement', 'explanation'}:
            raise ValueError('Invalid correction')
        for name, limit in (('original', 200), ('replacement', 200), ('explanation', 800)):
            if not isinstance(correction[name], str) or not correction[name].strip() or len(correction[name]) > limit:
                raise ValueError('Invalid correction text')
        if correction['original'] not in answer or correction['original'] == correction['replacement']:
            raise ValueError('Correction does not match the answer')
        if correction['original'] in seen:
            raise ValueError('Duplicate correction')
        seen.add(correction['original'])
    if language in ('en', 'ru'):
        # Include individual explanations, not just the introductory paragraph.
        # Russian examples are welcome inside English prose.
        prose_fields = [value['commentary'], value['phrasing_note'], value['extension']]
        prose_fields.extend(item['explanation'] for item in corrections)
        for prose in prose_fields:
            latin = len(re.findall('[A-Za-z]', prose))
            cyrillic = len(re.findall('[А-Яа-яЁё]', prose))
            foreign, expected = (cyrillic, latin) if language == 'en' else (latin, cyrillic)
            if foreign > 20 and foreign > 2 * expected:
                raise ValueError('Feedback language does not match the interface')


def tidy_corrections(value, answer):
    """Remove mechanically redundant fixes from validated NEW feedback only.

    Never infer grammar or change a grade here. Old attempts retain their text.
    """
    kept = []
    punctuation_only = False
    without_stop = lambda text: text.rstrip().removesuffix('.').rstrip()
    for item in sorted(value['corrections'], key=lambda item: len(item['original'])):
        original, replacement = item['original'], item['replacement']
        at_end = answer.rstrip().endswith(original.rstrip())
        if at_end and without_stop(original) == without_stop(replacement):
            punctuation_only = True
            continue
        revised = original
        for earlier in kept:
            if revised.count(earlier['original']) == 1:
                revised = revised.replace(earlier['original'], earlier['replacement'], 1)
        # Drop a longer repeat only if its result is exactly accounted for by
        # the smaller fixes (and, at the end of the answer, an optional stop).
        if revised != original and (revised == replacement or
                (at_end and without_stop(revised) == without_stop(replacement))):
            continue
        kept.append(item)
    if punctuation_only and not kept and value['score'] < 4:
        raise ValueError('A final full stop is optional; reassess without treating it as a mistake')
    return {**value, 'corrections': [item for item in value['corrections'] if item in kept]}


def readable_feedback(value):
    """Retain a plain-text summary for legacy readers and exports."""
    parts = [value['commentary']]
    parts.extend(f"{item['original']} → {item['replacement']}: {item['explanation']}"
                 for item in value['corrections'])
    parts.extend(value[name] for name in ('polished_sentence', 'phrasing_note', 'extension') if value[name].strip())
    return '\n\n'.join(parts)
