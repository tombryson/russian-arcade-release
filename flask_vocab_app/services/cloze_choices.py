"""Reviewed grammar rules and comparable vocabulary choices for Missing Stamp.

Only narrow, unambiguous constructions become grammar questions. Morphology
alone cannot decide which case a preposition means in a sentence.
"""
import re

from utils.story_processing import get_morph

CASE_RULES = (
    (r'(?:говорю|разговариваю|гуляю|играю|встречаюсь)\s+с\s+$', 'ablt',
     'After this verb and «с», use the instrumental case.', 'После этого глагола с предлогом «с» нужен творительный падеж.'),
    (r'(?:помогаю|помогает|помогаем|помогаешь|помогают)\s+$', 'datv',
     'The person receiving help takes the dative case.', 'Тот, кому помогают, стоит в дательном падеже.'),
    (r'(?:нет|без|около|для)\s+$', 'gent',
     'This expression takes the genitive case.', 'В этом выражении нужен родительный падеж.'),
    (r'(?:думаю|говорю|рассказываю)\s+о\s+$', 'loct',
     'Use the prepositional case after «о» when naming the subject.', 'После «о» при указании темы нужен предложный падеж.'),
)
LEXICAL_FOILS = {
    'NOUN': ('книга', 'стол', 'письмо', 'собака', 'окно'),
    'VERB': ('читать', 'писать', 'покупать', 'искать', 'готовить'),
    'INFN': ('читать', 'писать', 'покупать', 'искать', 'готовить'),
    'ADJF': ('новый', 'старый', 'большой', 'маленький', 'зелёный'),
    'ADVB': ('быстро', 'медленно', 'тихо', 'громко', 'далеко'),
}


def _normal(text):
    return text.casefold().replace('ё', 'е')


def choices_for(target, alternatives, rng):
    morph = get_morph()
    parses = [p for p in morph.parse(target['form']) if _normal(p.normal_form) == _normal(target['lemma'])]
    tags = target.get('tags', {})
    compatible = [p for p in parses if all(getattr(p.tag, k, None) == tags[k]
                  for k in ('case', 'number', 'tense', 'person') if tags.get(k))]
    parsed = (compatible or parses or morph.parse(target['form']))[0]
    occurrence = re.compile(r'(?<![А-Яа-яЁё])' + re.escape(target['form']) + r'(?![А-Яа-яЁё])', re.I)
    before = occurrence.split(target['sentence'], maxsplit=1)[0].casefold()
    dimension, expected, explanation, explanation_ru = None, None, '', ''
    for pattern, case, en, ru in CASE_RULES:
        if parsed.tag.POS == 'NOUN' and parsed.tag.case == case and re.search(r'\b' + pattern, before):
            dimension, expected, explanation, explanation_ru = 'case', case, en, ru
            break
    subject = re.search(r'\b(я|ты|мы|вы|он|она|они)\s+$', before)
    if parsed.tag.POS == 'VERB' and parsed.tag.tense in ('pres', 'futr') and subject:
        persons = {'я': ('1per', 'sing'), 'ты': ('2per', 'sing'), 'мы': ('1per', 'plur'),
                   'вы': ('2per', 'plur'), 'он': ('3per', 'sing'), 'она': ('3per', 'sing'), 'они': ('3per', 'plur')}
        if (parsed.tag.person, parsed.tag.number) == persons[subject[1]]:
            dimension, expected = 'person', parsed.tag.person
            explanation = f'Use the verb form that matches «{subject[1]}».'
            explanation_ru = f'Форма глагола должна соответствовать местоимению «{subject[1]}».'
    foils = []
    if dimension:
        values = ('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct') if dimension == 'case' else ('1per', '2per', '3per')
        for value in values:
            if value == expected:
                continue
            inflected = parsed.inflect({value})
            if not inflected or _normal(inflected.word) == _normal(target['form']):
                continue
            # Syncretic alternatives which also have the required reading are
            # not wrong answers. Keep homographs attached to this lexeme.
            readings = [p for p in morph.parse(inflected.word) if _normal(p.normal_form) == _normal(parsed.normal_form)]
            if any(getattr(p.tag, dimension) == expected and p.tag.number == parsed.tag.number for p in readings):
                continue
            foils.append(inflected.word)
        if foils:
            rng.shuffle(foils)
            return {'forms': [target['form'], *list(dict.fromkeys(foils))[:3]], 'objective': 'grammar',
                    'explanation': explanation, 'explanation_ru': explanation_ru}
    # Vocabulary retrieval uses the English sentence to distinguish meanings.
    # Match part of speech and inflection, so a verb is not a noun distractor.
    candidates = [e['lemma'] for e in alternatives if _normal(e['lemma']) != _normal(target['lemma'])]
    candidates += list(LEXICAL_FOILS.get(parsed.tag.POS, ()))
    for lemma in candidates:
        if _normal(lemma) == _normal(target['lemma']):
            continue
        for candidate in morph.parse(lemma):
            if candidate.tag.POS != parsed.tag.POS and not (parsed.tag.POS == 'VERB' and candidate.tag.POS == 'INFN'):
                continue
            features = {getattr(parsed.tag, key) for key in ('case', 'number', 'gender', 'tense', 'person')
                        if getattr(parsed.tag, key) is not None}
            if parsed.tag.number == 'plur':
                features.discard(parsed.tag.gender)
            inflected = candidate.inflect(features) if features else candidate
            if inflected and _normal(inflected.word) != _normal(target['form']):
                foils.append(inflected.word)
                break
    foils = list(dict.fromkeys(foils))
    if not foils:
        # Indeclinable function words still support vocabulary retrieval. This
        # fallback is explicitly a meaning question, never a case assessment.
        foils = list(dict.fromkeys(e['form'] for e in alternatives if _normal(e['form']) != _normal(target['form'])))
    rng.shuffle(foils)
    return {'forms': [target['form'], *foils[:3]], 'objective': 'vocabulary', 'explanation': '', 'explanation_ru': ''}
