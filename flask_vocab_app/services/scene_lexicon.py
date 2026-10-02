"""Small checked paradigms for the scene grammar engine.

These are construction vocabulary, not another learner word store. Generated
examples enter the existing vocabulary pipeline only through the normal action.
We do not guess an ending by stripping letters from an arbitrary Russian noun.
"""

CASES = ('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct')


def noun(lemma, meaning, gender, forms, *, animate=False):
    return {'lemma': lemma, 'meaning': meaning, 'gender': gender,
            'animate': animate, 'forms': dict(zip(CASES, forms))}


NOUNS = {
    'cat': noun('кот', 'cat', 'masc', ('кот', 'кота', 'коту', 'кота', 'котом', 'коте'), animate=True),
    'book': noun('книга', 'book', 'femn', ('книга', 'книги', 'книге', 'книгу', 'книгой', 'книге')),
    'ball': noun('мяч', 'ball', 'masc', ('мяч', 'мяча', 'мячу', 'мяч', 'мячом', 'мяче')),
    'cup': noun('чашка', 'cup', 'femn', ('чашка', 'чашки', 'чашке', 'чашку', 'чашкой', 'чашке')),
    'bag': noun('сумка', 'bag', 'femn', ('сумка', 'сумки', 'сумке', 'сумку', 'сумкой', 'сумке')),
    'letter': noun('письмо', 'letter', 'neut', ('письмо', 'письма', 'письму', 'письмо', 'письмом', 'письме')),
    'table': noun('стол', 'table', 'masc', ('стол', 'стола', 'столу', 'стол', 'столом', 'столе')),
    'chair': noun('стул', 'chair', 'masc', ('стул', 'стула', 'стулу', 'стул', 'стулом', 'стуле')),
    'box': noun('коробка', 'box', 'femn', ('коробка', 'коробки', 'коробке', 'коробку', 'коробкой', 'коробке')),
    'shelf': noun('полка', 'shelf', 'femn', ('полка', 'полки', 'полке', 'полку', 'полкой', 'полке')),
    'girl': noun('девочка', 'girl', 'femn', ('девочка', 'девочки', 'девочке', 'девочку', 'девочкой', 'девочке'), animate=True),
    'boy': noun('мальчик', 'boy', 'masc', ('мальчик', 'мальчика', 'мальчику', 'мальчика', 'мальчиком', 'мальчике'), animate=True),
    'parcel': noun('посылка', 'parcel', 'femn', ('посылка', 'посылки', 'посылке', 'посылку', 'посылкой', 'посылке')),
    'child': noun('ребёнок', 'child', 'masc', ('ребёнок', 'ребёнка', 'ребёнку', 'ребёнка', 'ребёнком', 'ребёнке'), animate=True),
}

# The full paradigm is explicit: the engine never promotes a spelling shortcut
# to a general declension rule. Distinct grammatical cells can share a surface.
ADJECTIVES = {
    'red': ('красный', 'red', {'masc': ('красный', 'красного', 'красному', 'красный', 'красным', 'красном'),
                             'femn': ('красная', 'красной', 'красной', 'красную', 'красной', 'красной'),
                             'neut': ('красное', 'красного', 'красному', 'красное', 'красным', 'красном')}),
    'blue': ('синий', 'blue', {'masc': ('синий', 'синего', 'синему', 'синий', 'синим', 'синем'),
                             'femn': ('синяя', 'синей', 'синей', 'синюю', 'синей', 'синей'),
                             'neut': ('синее', 'синего', 'синему', 'синее', 'синим', 'синем')}),
    'yellow': ('жёлтый', 'yellow', {'masc': ('жёлтый', 'жёлтого', 'жёлтому', 'жёлтый', 'жёлтым', 'жёлтом'),
                                 'femn': ('жёлтая', 'жёлтой', 'жёлтой', 'жёлтую', 'жёлтой', 'жёлтой'),
                                 'neut': ('жёлтое', 'жёлтого', 'жёлтому', 'жёлтое', 'жёлтым', 'жёлтом')}),
    'green': ('зелёный', 'green', {'masc': ('зелёный', 'зелёного', 'зелёному', 'зелёный', 'зелёным', 'зелёном'),
                                 'femn': ('зелёная', 'зелёной', 'зелёной', 'зелёную', 'зелёной', 'зелёной'),
                                 'neut': ('зелёное', 'зелёного', 'зелёному', 'зелёное', 'зелёным', 'зелёном')}),
}

ACTORS = (
    {'id': 'anna', 'ru': 'Анна', 'en': 'Anna', 'gender': 'femn'},
    {'id': 'nina', 'ru': 'Нина', 'en': 'Nina', 'gender': 'femn'},
    {'id': 'ivan', 'ru': 'Иван', 'en': 'Ivan', 'gender': 'masc'},
    {'id': 'sergei', 'ru': 'Сергей', 'en': 'Sergei', 'gender': 'masc'},
)


def adjective(color, gender, case, *, animate=False):
    forms = ADJECTIVES[color][2][gender]
    if gender == 'masc' and case == 'accs' and animate:
        case = 'gent'
    return forms[CASES.index(case)]


def reference(key, case):
    value = NOUNS[key]
    return (value['lemma'], value['forms'][case], 'NOUN',
            {'case': case, 'number': 'sing', 'gender': value['gender'],
             'animacy': 'anim' if value['animate'] else 'inan'}, value['meaning'])
