"""Frozen A1 situations about people, descriptions and everyday actions.

These are event and language contracts, not finished passages. A writer chooses
the prose after the people, relations and answer frames have been selected.
Names have verified case forms; knowing a lemma never grants its whole paradigm.
"""
from copy import deepcopy
import random
import re

VERSION = 'curriculum-language-plan-v5'
UNITS = (
    'personal-reference-v1', 'noun-adjective-agreement-v1',
    'present-actions-v1', 'time-routine-v1', 'possession-absence-v1',
    'objects-recipients-v1', 'social-exchanges-v1',
)

# Form tables describe lexical constructions. They are not learner vocabulary
# whitelists, or a license for a writer to add all the displayed words at once.
_PEOPLE = (
    ('Олег', 'Oleg', 'masculine', 'Олега', 'Олегу'),
    ('Дима', 'Dima', 'masculine', 'Димы', 'Диме'),
    ('Иван', 'Ivan', 'masculine', 'Ивана', 'Ивану'),
    ('Миша', 'Misha', 'masculine', 'Миши', 'Мише'),
    ('Анна', 'Anna', 'feminine', 'Анны', 'Анне'),
    ('Нина', 'Nina', 'feminine', 'Нины', 'Нине'),
    ('Лена', 'Lena', 'feminine', 'Лены', 'Лене'),
    ('Оля', 'Olya', 'feminine', 'Оли', 'Оле'),
    ('Вера', 'Vera', 'feminine', 'Веры', 'Вере'),
)
_OBJECTS = (
    {'lemma': 'книга', 'nom': 'книга', 'acc': 'книгу', 'gen': 'книги', 'en': 'book'},
    {'lemma': 'ручка', 'nom': 'ручка', 'acc': 'ручку', 'gen': 'ручки', 'en': 'pen'},
    {'lemma': 'телефон', 'nom': 'телефон', 'acc': 'телефон', 'gen': 'телефона', 'en': 'phone'},
    {'lemma': 'сумка', 'nom': 'сумка', 'acc': 'сумку', 'gen': 'сумки', 'en': 'bag'},
    {'lemma': 'билет', 'nom': 'билет', 'acc': 'билет', 'gen': 'билета', 'en': 'ticket'},
    {'lemma': 'журнал', 'nom': 'журнал', 'acc': 'журнал', 'gen': 'журнала', 'en': 'magazine'},
)
_RELATIVES = (
    {'lemma': 'мама', 'dat': 'маме', 'en': 'mother'},
    {'lemma': 'папа', 'dat': 'папе', 'en': 'father'},
    {'lemma': 'брат', 'dat': 'брату', 'en': 'brother'},
    {'lemma': 'сестра', 'dat': 'сестре', 'en': 'sister'},
    {'lemma': 'друг', 'dat': 'другу', 'en': 'friend'},
    {'lemma': 'подруга', 'dat': 'подруге', 'en': 'friend'},
)
_CLOTHES = (
    {'lemma': 'шарф', 'noun': 'шарф', 'gender': 'masc', 'number': 'sing', 'question': 'Какой', 'en': 'scarf'},
    {'lemma': 'шапка', 'noun': 'шапка', 'gender': 'femn', 'number': 'sing', 'question': 'Какая', 'en': 'hat'},
    {'lemma': 'сумка', 'noun': 'сумка', 'gender': 'femn', 'number': 'sing', 'question': 'Какая', 'en': 'bag'},
    {'lemma': 'пальто', 'noun': 'пальто', 'gender': 'neut', 'number': 'sing', 'question': 'Какое', 'en': 'coat'},
    {'lemma': 'ботинок', 'noun': 'ботинки', 'number': 'plur', 'question': 'Какие', 'en': 'boots'},
)
_COLORS = {
    'красный': {'masc': 'красный', 'femn': 'красная', 'neut': 'красное', 'plur': 'красные', 'en': 'red'},
    'синий': {'masc': 'синий', 'femn': 'синяя', 'neut': 'синее', 'plur': 'синие', 'en': 'blue'},
    'белый': {'masc': 'белый', 'femn': 'белая', 'neut': 'белое', 'plur': 'белые', 'en': 'white'},
}
_WEEKDAYS = (
    ('понедельник', 'в понедельник'), ('вторник', 'во вторник'),
    ('среда', 'в среду'), ('четверг', 'в четверг'),
    ('пятница', 'в пятницу'), ('суббота', 'в субботу'),
)
_HOURS = ('в восемь', 'в девять', 'в десять', 'в одиннадцать', 'в двенадцать')
_FAMILIES = {
    UNITS[0]: ('reference-giving-and-calling', 'reference-shared-belongings'),
    UNITS[1]: ('agreement-find-clothes', 'agreement-separate-sets'),
    UNITS[2]: ('present-individual-and-pair', 'present-reading-turns'),
    UNITS[3]: ('routine-meeting-plan', 'routine-three-days'),
    UNITS[4]: ('possession-borrow-missing-item', 'possession-owner-and-holder'),
    UNITS[5]: ('recipient-handover-and-call', 'recipient-buy-and-give'),
    UNITS[6]: ('social-names-and-repeat', 'social-ask-permission'),
}


def _person(row):
    name, english, gender, genitive, dative = row
    return {'name_ru': name, 'name_en': english, 'gender': gender,
            'genitive_ru': genitive, 'dative_ru': dative}


def _family(identity, seed, recent_families):
    values = _FAMILIES[identity]
    history = [value for value in recent_families if value in values]
    def rank(value):
        return history.count(value), -(history.index(value) if value in history else len(history))
    best = min(rank(value) for value in values)
    return random.Random(VERSION + ':family:' + identity + ':' + seed).choice(
        [value for value in values if rank(value) == best])


def _token(surface, lemma, *tags):
    return {'surface_ru': surface, 'lemma': lemma, 'tags': list(tags)}


def _support(plan, ru, en, scope):
    if not any(value['ru'] == ru for value in plan['supported_phrases']):
        plan['supported_phrases'].append({'ru': ru, 'en': en, 'scope': scope})


def _scope(plan, setting, purpose, relationships, constraints):
    plan.update(setting=setting, purpose=purpose)
    plan['family_contract'].update(relationships_en=relationships,
                                  implausible_combinations=list(constraints), question_purpose_en=purpose)
    plan['meaning_plan'].update(context_en=setting, purpose_en=purpose, timeline_en=relationships)
    plan['meaning_plan']['constraints'].extend(constraints)


def _frame(plan, role, requirement, question_pattern, rule, meaning):
    if any(frame['role'] == role and frame['requirement_id'] == requirement for frame in plan['answer_frames']):
        return
    key = requirement.rsplit('.', 1)[-1].replace('-', '_')
    plan['answer_frames'].append({'role': role, 'question_ru': question_pattern,
        'question_pattern_ru': question_pattern, 'requirement_id': requirement, 'form_key': key})
    if not any(row['requirement_id'] == requirement for row in plan['contrast_rules']):
        plan['contrast_rules'].append({'requirement_id': requirement, 'rule': rule,
                                      'form_key': key, 'meaning_en': meaning})
        plan['language_requirement_ids'].append(requirement)


def _hint_details(plan, subject, role, requirement, source, index):
    """Authored indirect prompts, not lowercased or mechanically rewritten questions."""
    family = plan['family_id']
    name, en = subject['name_ru'], subject['name_en']
    if role == 'recipient':
        return ((f'the person {en} calls', f'кому звонит {name}') if 'звонит' in source
                else (f'the person {en} gives the item to', f'кому {name} даёт вещь'))
    if role == 'owner':
        if requirement == 'a1.language.genitive-owner-u' or requirement is None:
            return 'who has the item now', 'у кого вещь сейчас'
        return 'who the specified item belongs to', 'кому принадлежит названная вещь'
    if role == 'description':
        return 'the colour of the clothing named in the question', 'какого цвета названная одежда'
    if role == 'person':
        if family == 'social-names-and-repeat':
            return (('the new male classmate’s name', 'имя нового ученика') if index == 0
                    else ('the new female classmate’s name', 'имя новой ученицы'))
        if family == 'present-reading-turns':
            return (('the name of the first reader', 'имя того, кто читает сначала'),
                    ('the name of the next reader', 'имя того, кто читает потом'),
                    ('the name of the person speaking Russian', 'имя того, кто говорит по-русски'))[index]
        return (('the name of the person reading now', 'имя того, кто сейчас читает') if index == 0
                else ('the other person in the pair', 'имя второго человека в паре'))
    if role == 'activity':
        if family == 'present-individual-and-pair':
            return 'what the two friends are doing together', 'что два друга делают вместе'
        if family == 'routine-three-days':
            return ((f'what {en} did yesterday', f'что {name} делал{ "а" if subject["gender"] == "feminine" else ""} вчера'),
                    (f'what {en} is doing today', f'что {name} делает сегодня'),
                    (f'what {en} plans to do tomorrow', f'что {name} будет делать завтра'))[index]
        return f'what {en} does during the session', f'что {name} делает на занятии'
    if role == 'time':
        return (('the day of the session', 'в какой день проходит занятие') if index == 0
                else ('the starting time of the session', 'во сколько начинается занятие'))
    if role == 'request':
        return 'the detail the speaker asks to hear again', 'какую информацию просят повторить'
    if role == 'item':
        if requirement == 'a1.language.nominative-existence':
            return f'what {en} has', f'что есть у {subject["genitive_ru"]}'
        if requirement == 'a1.language.genitive-absence':
            return f'what {en} does not have', f'чего нет у {subject["genitive_ru"]}'
        if requirement == 'a1.language.impersonal-modal':
            return f'the item {en} asks to take', f'что {name} просит разрешить взять'
        if 'покупает' in source:
            return f'the item {en} buys', f'что покупает {name}'
        return f'the item {en} gives', f'что {name} даёт'
    raise ValueError(f'No authored hint for {family}: {role}')


def _fact(plan, subject, role, value, alternatives, question, question_en, source,
          relation, feedback_en, feedback_ru, *, requirement=None, pattern=None,
          rule=None, checks=(), alternative_checks=(), source_checks=()):
    """Preserve a semantic fact, its reference sentence and verified choice forms."""
    number = len(plan['meaning_plan']['facts']) + 1
    detail_en, detail_ru = _hint_details(plan, subject, role, requirement, source, number - 1)
    fact = {'id': f'f{number}', 'role': role, 'subject_name': subject['name_ru'],
        'subject_en': subject['name_en'], 'value_ru': value,
        'alternative_frames': list(alternatives), 'question_frame_ru': question,
        'question_en': question_en, 'checked_source_frame_ru': source,
        'relation_en': relation, 'requirement_id': requirement,
        'form_key': requirement.rsplit('.', 1)[-1].replace('-', '_') if requirement else None,
        'feedback': {'detail_en': detail_en,
            'detail_ru': detail_ru, 'caption_en': feedback_en,
            'caption_ru': feedback_ru}, 'source_checks': list(source_checks)}
    plan['meaning_plan']['facts'].append(fact)
    if requirement:
        _frame(plan, role, requirement, pattern, rule, relation)
        key = requirement.rsplit('.', 1)[-1].replace('-', '_')
        option_checks = [list(checks), *[list(c) for c in alternative_checks]]
        for index, phrase in enumerate([value, *alternatives]):
            row = {key: phrase,
                   'fact_id': fact['id'], 'role': role,
                   'grammatical_checks': option_checks[index] if index < len(option_checks) else []}
            plan['checked_forms'].append(row)
    return fact


def _object_checks(row, case):
    key, tag = {'nom': ('nom', 'nomn'), 'acc': ('acc', 'accs'), 'gen': ('gen', 'gent')}[case]
    return [_token(row[key], row['lemma'], 'NOUN', tag, 'sing')]


def _personal(plan, rng, people):
    male = next(p for p in people if p['gender'] == 'masculine')
    female = next(p for p in people if p['gender'] == 'feminine')
    other = next(p for p in people if p not in (male, female))
    if plan['family_id'] == 'reference-giving-and-calling':
        requirement = 'a1.language.personal-pronoun-cases'
        plan['meaning_plan']['event_policy'] = {
            'unplanned_presence_event_lemmas': ['видеть', 'встретить', 'встречать', 'приходить', 'прийти', 'стоять', 'находиться'],
            'unplanned_presence_markers': ['здесь', 'тут', 'рядом'],
        }
        item = rng.choice([row for row in _OBJECTS if row['lemma'] in ('книга', 'сумка', 'телефон')])
        _scope(plan, 'passing on an item and contacting a different friend',
            'Keep the person receiving an item separate from the person receiving a phone call.',
            f"{other['name_en']} gives one item to {male['name_en']} and calls {female['name_en']}. The recipients are different.",
            ['Introduce each named recipient immediately before the matching ему/ей clause. The gender of the actor does not change the recipient pronoun.',
             'Do not imply that the person given the item is also called. Use звонит, not telephone speech invented as dialogue.',
             'The plan does not place the telephone recipient beside the caller. Do not invent seeing, meeting or being here/nearby as an introduction before calling.',
             'Introduce a recipient by name without inventing an extra encounter, location or action.'])
        for recipient, pronoun, verb, question_verb in ((male, 'ему', f"даёт {item['acc']}", f"даёт {item['acc']}"),
                                                       (female, 'ей', 'звонит', 'звонит')):
            others = [form for form in ('ему', 'ей', 'им') if form != pronoun]
            # A name in a separate introductory clause establishes reference;
            # the governed form itself remains the object of comprehension.
            source = (f"Это {recipient['name_ru']}. {other['name_ru']} даёт {pronoun} {item['acc']}."
                      if pronoun == 'ему' else f"Это {recipient['name_ru']}. {other['name_ru']} звонит {pronoun}.")
            action_en = 'give the item to' if pronoun == 'ему' else 'call'
            _fact(plan, other, 'recipient', pronoun, others,
                f"Кому {other['name_ru']} {'даёт вещь' if pronoun == 'ему' else question_verb}?",
                f"Who does {other['name_en']} {action_en}?", source,
                f"The dative pronoun refers to {recipient['name_en']}, the named recipient.",
                f"{pronoun.capitalize()} refers to {recipient['name_en']}, who receives {'the item' if pronoun == 'ему' else 'the call'}.",
                f"«{pronoun.capitalize()}» — это {recipient['name_ru']}, {'получатель вещи' if pronoun == 'ему' else 'тот, кому звонят'}.",
                requirement=requirement, pattern=r'^кому\b', rule='personal-pronoun-dative',
                checks=[_token(pronoun, 'он' if pronoun == 'ему' else 'она', 'NPRO', 'datv')],
                alternative_checks=[[_token(form, {'ему': 'он', 'ей': 'она', 'им': 'они'}[form], 'NPRO', 'datv')] for form in others])
        options = [row for row in _OBJECTS if row['lemma'] in ('книга', 'сумка', 'телефон') and row != item]
        _fact(plan, other, 'item', item['acc'], [row['acc'] for row in options],
            f"Что {other['name_ru']} даёт?",
            f"What does {other['name_en']} give?",
            f"Это {male['name_ru']}. {other['name_ru']} даёт ему {item['acc']}.",
            'The one item being handed over, not an object mentioned as a setting.',
            f"The item handed over is the {item['en']}.", 'Здесь названа вещь, которую передают.')
        _support(plan, f"даёт ему {item['acc']}", f"gives him the {item['en']}", 'The complete handover phrase supports a taught dative pronoun.')
        _support(plan, 'звонит ей', 'calls her', 'The person receiving a call is dative after звонить.')
        _support(plan, 'вещь', 'item / thing', 'Question support that identifies the handover without revealing which item it is.')
    else:
        requirement = 'a1.language.pronoun-reference'
        rows = rng.sample([row for row in _OBJECTS if row['lemma'] in ('книга', 'сумка', 'телефон', 'журнал')], 3)
        _scope(plan, 'sorting belongings before friends leave',
            'Identify which belongings belong to each friend and which they share.',
            f"{male['name_en']} owns one item, {female['name_en']} owns another, and they share the third.",
            ['Ownership is explicit. Do not infer ownership merely from holding an item or standing nearby.',
             'Keep его and её linked to their named owner. Introduce both owners before using их for the shared item.',
             'Use a complete naming or ownership clause. Do not append bare owner names after a colon following the object.'])
        for owner, pronoun, row in ((male, 'его', rows[0]), (female, 'её', rows[1]), (male, 'их', rows[2])):
            source = (f"Это {male['name_ru']} и {female['name_ru']}. Это их {row['nom']}." if pronoun == 'их'
                      else f"Это {owner['name_ru']}. Это {pronoun} {row['nom']}.")
            value = f"{pronoun} {row['nom']}"
            alternatives = [f"{form} {row['nom']}" for form in ('его', 'её', 'их') if form != pronoun]
            whose = 'Чей' if row['nom'] in ('телефон', 'журнал') else 'Чья'
            _fact(plan, owner, 'owner', value, alternatives, f"{whose} это {row['nom']}?",
                f"Whose {row['en']} is this?", source, 'The possessive pronoun identifies the owner, not the person holding the item.',
                ('Их means that both named friends own this item.' if pronoun == 'их' else f"{pronoun.capitalize()} links this item to {owner['name_en']}."),
                ('«Их» указывает на обоих друзей.' if pronoun == 'их' else f"Владелец здесь — {owner['name_ru']}."),
                requirement=requirement, pattern=r'^ч(?:ей|ья|ьё|ьи)\b', rule='possessive-pronoun-reference',
                checks=_object_checks(row, 'nom'), alternative_checks=[_object_checks(row, 'nom')] * 2)
        plan['grammar_limits'].append('Possessive его/её/их is invariant; do not add н as in у него. Do not assess owner gender from the owned noun’s gender.')


def _description(row, color):
    adjective = _COLORS[color]['plur' if row['number'] == 'plur' else row['gender']]
    tags = ['nomn', row['number']] + ([row['gender']] if row['number'] == 'sing' else [])
    return f"{adjective} {row['noun']}", [_token(adjective, color, 'ADJF', *tags), _token(row['noun'], row['lemma'], 'NOUN', *tags)]


def _agreement(plan, rng, people):
    first, second = people[:2]
    if plan['family_id'] == 'agreement-find-clothes':
        garments = rng.sample(list(_CLOTHES), 3)
        owners = [first] * 3
        _scope(plan, 'identifying a friend’s clothes in a shared hallway',
            'Recognise the matching colour and garment before taking the right set.',
            f"Three different garments belong to {first['name_en']}; each has one stated colour.",
            ['Describe each garment in the nominative. Do not require accusative adjective endings after взять or искать.',
             'Use colour alternatives for the same garment. Newness, size and colour are not mutually exclusive alternatives.'])
    else:
        garment = rng.choice([row for row in _CLOTHES if row['number'] == 'sing'])
        plural = next(row for row in _CLOTHES if row['number'] == 'plur')
        garments, owners = [garment, garment, plural], [first, second, first]
        _scope(plan, 'separating two friends’ similar clothing sets',
            'Keep two similar garments with their owners, and identify the accompanying pair of boots.',
            f"{first['name_en']} and {second['name_en']} each have the same kind of garment in different colours; the boots belong to {first['name_en']}.",
            ['The first two garments have different owners and different colours. The plural boots are one pair, not two unrelated facts.',
             'Identify ownership in a supporting у + name frame. Only the nominative description is assessed.'])
    colors = rng.sample(list(_COLORS), 3)
    for row, owner, color in zip(garments, owners, colors):
        value, checks = _description(row, color)
        alternatives = [_description(row, alternative) for alternative in _COLORS if alternative != color]
        source = f"У {owner['genitive_ru']} {value}."
        _fact(plan, owner, 'description', value, [item[0] for item in alternatives],
            f"{row['question']} {row['noun']} у {owner['genitive_ru']}?",
            f"What are {owner['name_en']}’s boots like?" if row['number'] == 'plur' else f"What is {owner['name_en']}’s {row['en']} like?",
            source, 'The colour belongs to this named person’s garment, with the adjective agreeing in gender or plural number.',
            f"This describes {owner['name_en']}’s {_COLORS[color]['en']} {row['en']}.",
            f"Здесь дано описание: {value}.", requirement='a1.language.adjective-agreement',
            pattern=r'^как(?:ой|ая|ое|ие)\b', rule='nominative-adjective-agreement', checks=checks,
            alternative_checks=[item[1] for item in alternatives])
        _support(plan, f"у {owner['genitive_ru']}", f"{owner['name_en']} has / with {owner['name_en']}", 'A supplied owner frame; the assessed construction is the adjective description.')
    plan['grammar_limits'].extend(['Use nominative descriptions only, including neuter invariable пальто and plural ботинки.',
        'Синий follows its taught soft pattern: синий, синяя, синее, синие. Do not create синия or синие пальто for one coat.'])


def _present(plan, rng, people):
    _support(plan, 'по-русски', 'in Russian', 'The language of the activity is supplied before the person or verb-form check.')
    first, second, third = people[:3]
    candidates = [p['name_ru'] for p in people[:3]]
    requirement = 'a1.language.nominative-subject'
    if plan['family_id'] == 'present-individual-and-pair':
        _scope(plan, 'joining friends who are practising Russian in different ways',
            'Identify the person reading and the two friends who are talking together.',
            f"{first['name_en']} reads alone. {second['name_en']} and {third['name_en']} speak Russian together.",
            ['The reader is not one of the pair. The pair’s present-tense verb must be plural.',
             'Use only the taught читать/говорить present forms, with сейчас, вместе and по-русски as needed. Do not infer someone’s general ability from this activity.'])
        _fact(plan, first, 'person', first['name_ru'], candidates[1:], 'Кто сейчас читает?', 'Who is reading now?',
            f"{first['name_ru']} сейчас читает.", 'The named subject doing the reading, not a listener.',
            f"{first['name_en']} is the person reading now.", f"Сейчас читает {first['name_ru']}.",
            requirement=requirement, pattern=r'^кто\b', rule='named-nominative-subject',
            checks=[_token(first['name_ru'], first['name_ru'].lower(), 'NOUN', 'nomn')],
            alternative_checks=[[_token(p['name_ru'], p['name_ru'].lower(), 'NOUN', 'nomn')] for p in (second, third)],
            source_checks=[_token('читает', 'читать', 'VERB', 'pres', '3per', 'sing')])
        source = f"{second['name_ru']} и {third['name_ru']} говорят по-русски вместе."
        _fact(plan, second, 'activity', 'говорят', ['читают', 'не говорят'],
            'Что друзья делают вместе?', 'What are the friends doing together?', source,
            'The shared action of the named pair; no claim is made about habitual language ability.',
            'The two friends are speaking; говорят is the plural present form.', 'Два человека говорят; форма «говорят» относится к ним обоим.',
            requirement='a1.language.verb-conjugation', pattern=r'^что\b', rule='present-subject-agreement',
            checks=[_token('говорят', 'говорить', 'VERB', 'pres', '3per', 'plur')],
            alternative_checks=[[_token('читают', 'читать', 'VERB', 'pres', '3per', 'plur')], [_token('говорят', 'говорить', 'VERB', 'pres', '3per', 'plur')]])
        _fact(plan, third, 'person', third['name_ru'], [first['name_ru'], plan['meaning_plan']['writer']['name_ru']],
            f"Кто сейчас вместе с {second['instrumental_ru']}?", f"Who is with {second['name_en']} now?", source,
            'The other member of the named pair.', f"{third['name_en']} is the other person in this conversation.",
            f"Вместе говорят {second['name_ru']} и {third['name_ru']}.")
        _support(plan, f"вместе с {second['instrumental_ru']}", f"together with {second['name_en']}", 'Supplied question support; instrumental name forms are not assessed in this unit.')
        _support(plan, 'друзья', 'friends', 'Supplied group label; the passage identifies which two people are doing the activity together.')
    else:
        _scope(plan, 'taking turns reading while a friend speaks Russian',
            'Find out who reads first, who reads next, and who is speaking.',
            f"In this routine {first['name_en']} reads first, then {second['name_en']} reads. {third['name_en']} speaks Russian; the third person is not another reader.",
            ['Use present forms for the described sequence, not future perfective verbs. Sначала and потом label order explicitly.',
             'Do not invent a reason for the order, an audience or a fourth participant. Only читать and говорить are assessed verbs.'])
        for actor, marker, question, english in ((first, 'сначала', 'Кто читает сначала?', 'Who reads first?'),
                                                (second, 'потом', 'Кто читает потом?', 'Who reads next?'),
                                                (third, '', 'Кто говорит по-русски?', 'Who speaks Russian?')):
            speaking = actor == third
            verb = 'говорит' if speaking else 'читает'
            source = f"{actor['name_ru']} {verb} по-русски." if speaking else f"{marker.capitalize()} читает {actor['name_ru']}."
            alternatives = [p for p in people[:3] if p != actor]
            _fact(plan, actor, 'person', actor['name_ru'], [p['name_ru'] for p in alternatives], question, english, source,
                'The named subject of this stated action and sequence position.',
                f"{actor['name_en']} {'speaks Russian' if speaking else 'is the first reader' if marker == 'сначала' else 'reads next'}.",
                source, requirement=requirement, pattern=r'^кто\b', rule='named-nominative-subject',
                checks=[_token(actor['name_ru'], actor['name_ru'].lower(), 'NOUN', 'nomn')],
                alternative_checks=[[_token(p['name_ru'], p['name_ru'].lower(), 'NOUN', 'nomn')] for p in alternatives],
                source_checks=[_token(verb, 'говорить' if speaking else 'читать', 'VERB', 'pres', '3per', 'sing')])
        _support(plan, 'сначала', 'first', 'Supplied ordering word; this family does not test tense or aspect.')
        _support(plan, 'потом', 'then / next', 'Supplied ordering word, without a future-tense requirement.')


def _routine(plan, rng, people):
    actor = people[0]
    if plan['family_id'] == 'routine-meeting-plan':
        day, *other_days = rng.sample(list(_WEEKDAYS), 3)
        hour, *other_hours = rng.sample(list(_HOURS), 3)
        activities = [('читает', 'читать', 'reads'), ('пишет', 'писать', 'writes'), ('работает', 'работать', 'works')]
        action, *other_actions = rng.sample(activities, 3)
        _scope(plan, 'a friend sharing when a regular study session takes place',
            'Understand the day, the starting hour and the activity at one regular session.',
            f"{actor['name_en']} has one regular session on the stated weekday, at the stated hour, doing one activity.",
            ['Weekday and hour belong to the same session. Do not add a second timetable or a duration.',
             'Spell clock numbers out in both modes. These are whole hours only, not half-hours or spoken dates.'])
        req = 'a1.language.accusative-clock-weekday'
        _fact(plan, actor, 'time', day[1], [d[1] for d in other_days],
            f"В какой день у {actor['genitive_ru']} занятие?", f"On which day is {actor['name_en']}’s session?",
            f"У {actor['genitive_ru']} занятие {day[1]}.", 'The weekday of the one regular session.',
            'This is the day of the session; it does not give its hour.', 'Здесь назван день занятия.',
            requirement=req, pattern=r'^(?:в какой день|когда|во сколько)\b', rule='scheduled-weekday-hour',
            checks=[_token(day[1].split()[-1], day[0], 'NOUN', 'accs')],
            alternative_checks=[[_token(d[1].split()[-1], d[0], 'NOUN', 'accs')] for d in other_days])
        _fact(plan, actor, 'time', hour, other_hours,
            f"Во сколько у {actor['genitive_ru']} занятие?", f"At what time is {actor['name_en']}’s session?",
            f"У {actor['genitive_ru']} занятие {hour}.", 'The start hour of the same session.',
            'This is when the session starts, not how long it lasts.', 'Это время начала занятия, а не его длительность.',
            requirement=req, pattern=r'^(?:в какой день|когда|во сколько)\b', rule='scheduled-weekday-hour')
        _fact(plan, actor, 'activity', action[0], [a[0] for a in other_actions],
            f"Что {actor['name_ru']} делает на занятии?", f"What does {actor['name_en']} do during the session?",
            f"На занятии {actor['name_ru']} {action[0]}.", 'The stated activity at this session.',
            f"{actor['name_en']} {action[2]} at the session.", f"На занятии {actor['name_ru']} {action[0]}.",
            requirement='a1.language.verb-conjugation', pattern=r'^что\b', rule='present-subject-agreement',
            checks=[_token(action[0], action[1], 'VERB', 'pres', '3per', 'sing')],
            alternative_checks=[[_token(a[0], a[1], 'VERB', 'pres', '3per', 'sing')] for a in other_actions])
        _support(plan, 'занятие', 'session / class', 'The timetable has one session, not three unrelated events.')
        _support(plan, 'на занятии', 'during the session', 'Supplied location phrase; no extra case target is claimed.')
    else:
        suffix = 'а' if actor['gender'] == 'feminine' else ''
        verbs = rng.sample([('читать', 'читал', 'читает', 'read'), ('работать', 'работал', 'работает', 'work'),
                            ('отдыхать', 'отдыхал', 'отдыхает', 'rest')], 3)
        _scope(plan, 'a friend’s news about yesterday, today and tomorrow',
            'Keep a past activity, a current activity and a planned activity separate.',
            f"{actor['name_en']} did one activity yesterday, does a different one today, and plans a third tomorrow.",
            ['Use yesterday, today and tomorrow explicitly. A future imperfective activity is not a claim that a task will be completed.',
             'Past forms agree with the named person’s gender. Do not use completed perfective verbs or unmentioned start times.'])
        all_verbs = [('читать', 'читал', 'читает', 'read'), ('работать', 'работал', 'работает', 'work'), ('отдыхать', 'отдыхал', 'отдыхает', 'rest')]
        for index, marker in enumerate(('вчера', 'сегодня', 'завтра')):
            chosen = verbs[index]
            def form(v):
                return v[1] + suffix if index == 0 else v[2] if index == 1 else 'будет ' + v[0]
            def checks(v):
                return ([_token(v[1] + suffix, v[0], 'VERB', 'past', 'sing', 'femn' if suffix else 'masc')] if index == 0 else
                        [_token(v[2], v[0], 'VERB', 'pres', '3per', 'sing')] if index == 1 else
                        [_token('будет', 'быть', 'VERB', 'futr', '3per', 'sing'), _token(v[0], v[0], 'INFN')])
            value, others = form(chosen), [v for v in all_verbs if v != chosen]
            question = (f"Что {actor['name_ru']} делал{suffix} вчера?" if index == 0 else
                        f"Что {actor['name_ru']} делает сегодня?" if index == 1 else f"Что {actor['name_ru']} будет делать завтра?")
            english = f"What {'did' if index == 0 else 'does' if index == 1 else 'will'} {actor['name_en']} do {('yesterday', 'today', 'tomorrow')[index]}?"
            source = f"{marker.capitalize()} {actor['name_ru']} {value}."
            _fact(plan, actor, 'activity', value, [form(v) for v in others], question, english, source,
                f"The activity on {('the previous', 'the current', 'the next')[index]} day, not another point in the timeline.",
                f"The time word points to {('yesterday', 'today', 'tomorrow')[index]} and the verb matches it.",
                f"«{marker.capitalize()}» и форма глагола относятся к одному времени.",
                requirement='a1.language.verb-tense', pattern=r'^что\b', rule='explicit-activity-timeline',
                checks=checks(chosen), alternative_checks=[checks(v) for v in others])


def _possession(plan, rng, people):
    first, second, third = people[:3]
    first_item, second_item, third_item = rng.sample(list(_OBJECTS), 3)
    if plan['family_id'] == 'possession-borrow-missing-item':
        _scope(plan, 'finding someone who has an item a friend is missing',
            'Distinguish what a friend has, what is missing and who has the missing item.',
            f"{first['name_en']} has a {first_item['en']} but no {second_item['en']}; {second['name_en']} has a {second_item['en']}.",
            ['Having an item now does not establish permanent ownership. Do not say the item has already been borrowed.',
             'Keep the available object nominative after есть and the missing object genitive after нет.'])
        _fact(plan, first, 'item', first_item['nom'], [r['nom'] for r in (second_item, third_item)],
            f"Что есть у {first['genitive_ru']}?", f"What does {first['name_en']} have?",
            f"У {first['genitive_ru']} есть {first_item['nom']}.", 'The one available item.',
            f"{first['name_en']} has a {first_item['en']}; есть introduces it.", 'После «есть» названа доступная вещь.',
            requirement='a1.language.nominative-existence', pattern=r'^что\b', rule='existence-nominative',
            checks=_object_checks(first_item, 'nom'), alternative_checks=[_object_checks(r, 'nom') for r in (second_item, third_item)])
        _fact(plan, first, 'item', second_item['gen'], [r['gen'] for r in (first_item, third_item)],
            f"Чего нет у {first['genitive_ru']}?", f"What does {first['name_en']} not have?",
            f"У {first['genitive_ru']} нет {second_item['gen']}.", 'The missing item, not the available one.',
            f"{first['name_en']} does not have a {second_item['en']}; нет marks the absence.", 'После «нет» названа отсутствующая вещь.',
            requirement='a1.language.genitive-absence', pattern=r'^чего\b', rule='absence-genitive',
            checks=_object_checks(second_item, 'gen'), alternative_checks=[_object_checks(r, 'gen') for r in (first_item, third_item)])
        _fact(plan, second, 'owner', f"у {second['genitive_ru']}", [f"у {p['genitive_ru']}" for p in (first, third)],
            f"У кого есть {second_item['nom']}?", f"Who has a {second_item['en']}?",
            f"У {second['genitive_ru']} есть {second_item['nom']}.", 'The person with the needed item; borrowing has not happened.',
            f"{second['name_en']} has the item the first friend is missing.", f"Нужная вещь есть у {second['genitive_ru']}.")
    else:
        _scope(plan, 'returning an item that is with someone other than its owner',
            'Keep an item’s owner separate from the person who currently has it.',
            f"One {first_item['en']} belongs to {first['name_en']} but is with {second['name_en']}. Another {second_item['en']} belongs to {third['name_en']}.",
            ['The two items are different. The first item’s owner and current holder are different people.',
             'Do not treat у + a person as proof of ownership. The owner is stated by a genitive name after the item.'])
        for owner, item in ((first, first_item), (third, second_item)):
            alternatives = [p for p in people[:3] if p != owner]
            value = owner['genitive_ru']
            whose = 'Чья' if item['nom'] in ('книга', 'ручка', 'сумка') else 'Чей'
            _fact(plan, owner, 'owner', value, [p['genitive_ru'] for p in alternatives],
                f"{whose} это {item['nom']}?", f"Who owns this {item['en']}?", f"Это {item['nom']} {value}.",
                'The explicitly stated owner, regardless of who has the item now.',
                f"The {item['en']} belongs to {owner['name_en']}.", f"Это вещь {value}.",
                requirement='a1.language.genitive-possession', pattern=r'^ч(?:ей|ья|ьё|ьи)\b', rule='owner-genitive',
                checks=[_token(value, owner['name_ru'].lower(), 'NOUN', 'gent')],
                alternative_checks=[[_token(p['genitive_ru'], p['name_ru'].lower(), 'NOUN', 'gent')] for p in alternatives])
        _fact(plan, second, 'owner', f"у {second['genitive_ru']}", [f"у {p['genitive_ru']}" for p in (first, third)],
            f"У кого сейчас {first_item['nom']}?", f"Who has the {first_item['en']} now?",
            f"{first_item['nom'].capitalize()} {first['genitive_ru']} сейчас у {second['genitive_ru']}.",
            'The current holder of the first item, not necessarily its owner.',
            f"The item is with {second['name_en']}, while it belongs to {first['name_en']}.",
            f"Сейчас вещь у {second['genitive_ru']}, но её владелец — {first['name_ru']}.",
            requirement='a1.language.genitive-owner-u', pattern=r'^у кого\b', rule='possessor-u-genitive',
            checks=[_token(second['genitive_ru'], second['name_ru'].lower(), 'NOUN', 'gent')],
            alternative_checks=[[_token(p['genitive_ru'], p['name_ru'].lower(), 'NOUN', 'gent')] for p in (first, third)])


def _recipients(plan, rng, people):
    first, second = people[:2]
    objects = rng.sample([row for row in _OBJECTS if row['lemma'] in ('книга', 'журнал', 'ручка', 'билет')], 3)
    recipients = rng.sample(list(_RELATIVES), 3)
    _support(plan, 'вещь', 'item / thing', 'Question support that keeps the item’s identity out of the recipient question.')
    if plan['family_id'] == 'recipient-handover-and-call':
        _scope(plan, 'a friend passing on an item before making a separate call',
            'Understand the item handed over and distinguish its recipient from the person being called.',
            f"{first['name_en']} gives a {objects[0]['en']} to one relative or friend, then calls a different person.",
            ['The item recipient and call recipient are different. All relationships refer to the named actor’s own family or friends.',
             'A call does not transfer the object. Do not add a second item or claim a purchase.'])
        giving, item, called = first, objects[0], recipients[1]
        _object_fact(plan, giving, item, objects[1:], 'даёт', 'give', f"{giving['name_ru']} даёт {item['acc']} {recipients[0]['dat']}.")
        _recipient_fact(plan, giving, recipients[0], recipients[1:], f"даёт {item['acc']}", f"give the {item['en']} to",
                        f"{giving['name_ru']} даёт {item['acc']} {recipients[0]['dat']}.", 'The person receiving the item.')
        _recipient_fact(plan, first, called, [recipients[0], recipients[2]], 'звонит', 'call',
                        f"{first['name_ru']} звонит {called['dat']}.", 'The different person receiving the call.')
    else:
        _scope(plan, 'sorting out a purchase and an item given to someone else',
            'Keep the item being bought separate from the item already being given to another person.',
            f"{first['name_en']} buys a {objects[0]['en']}. {second['name_en']} gives a different item to one named relative or friend.",
            ['The buyer and giver are different people; the two items are different. Do not imply that the bought item is the gift.',
             'Do not add a price, quantity, reason for the purchase or a future handover.'])
        _object_fact(plan, first, objects[0], objects[1:], 'покупает', 'buy', f"{first['name_ru']} покупает {objects[0]['acc']}.")
        _object_fact(plan, second, objects[1], [objects[0], objects[2]], 'даёт', 'give',
                     f"{second['name_ru']} даёт {objects[1]['acc']} {recipients[0]['dat']}.")
        _recipient_fact(plan, second, recipients[0], recipients[1:], f"даёт {objects[1]['acc']}", f"give the {objects[1]['en']} to",
                        f"{second['name_ru']} даёт {objects[1]['acc']} {recipients[0]['dat']}.", 'The recipient of the given item, not the buyer.')


def _object_fact(plan, actor, item, others, verb, english, source):
    _fact(plan, actor, 'item', item['acc'], [row['acc'] for row in others], f"Что {actor['name_ru']} {verb}?",
        f"What does {actor['name_en']} {english}?", source, 'The direct object of this named person’s stated action.',
        f"This action concerns the {item['en']}.", f"Действие относится к этой вещи: {item['acc']}.",
        requirement='a1.language.accusative-object', pattern=r'^что\b', rule='inanimate-accusative-object',
        checks=_object_checks(item, 'acc'), alternative_checks=[_object_checks(row, 'acc') for row in others])


def _recipient_fact(plan, actor, person, others, verb, english, source, relation):
    question_action = 'даёт вещь' if verb.startswith('даёт ') else verb
    english_action = 'give the item to' if verb.startswith('даёт ') else english
    _fact(plan, actor, 'recipient', person['dat'], [row['dat'] for row in others], f"Кому {actor['name_ru']} {question_action}?",
        f"Who does {actor['name_en']} {english_action}?", source, relation,
        f"The recipient is {actor['name_en']}’s {person['en']}.", f"Здесь получатель назван формой «{person['dat']}».",
        requirement='a1.language.dative-recipient', pattern=r'^кому\b', rule='named-dative-recipient',
        checks=[_token(person['dat'], person['lemma'], 'NOUN', 'datv')],
        alternative_checks=[[_token(row['dat'], row['lemma'], 'NOUN', 'datv')] for row in others])


def _social(plan, rng, people):
    first, second, third = people[:3]
    if plan['family_id'] == 'social-names-and-repeat':
        male = next(p for p in people if p['gender'] == 'masculine')
        female = next(p for p in people if p['gender'] == 'feminine')
        _scope(plan, 'introducing two new classmates and asking for a detail again',
            'Learn the two classmates’ names and identify the detail one asks to hear again.',
            f"A new male classmate is {male['name_en']}; a new female classmate is {female['name_en']}. {female['name_en']} politely asks to hear one detail again.",
            ['Introduce each person with его/её зовут. The greeting does not prove a name or relationship by itself.',
             'The repetition request addresses a new adult contact as вы. It asks to hear information again, not to change it.',
             'Use a single narrator with short quoted phrases, not a dialogue requiring several synthetic voices.'])
        for actor, pronoun, noun, english in ((male, 'его', 'ученика', 'male classmate'), (female, 'её', 'ученицу', 'female classmate')):
            # Matching grammatical gender prevents the pronoun or role label
            # from giving away a name without reading/hearing the introduction.
            others = [_person(row) for row in rng.sample([row for row in _PEOPLE
                      if row[2] == actor['gender'] and row[0] != actor['name_ru']], 2)]
            source = f"Это {'новый ученик' if pronoun == 'его' else 'новая ученица'}. {pronoun.capitalize()} зовут {actor['name_ru']}."
            _fact(plan, actor, 'person', actor['name_ru'], [p['name_ru'] for p in others],
                f"Как зовут нового ученика?" if pronoun == 'его' else 'Как зовут новую ученицу?',
                f"What is the new {english}’s name?", source, 'The name of the person introduced by this naming construction.',
                f"{pronoun.capitalize()} зовут introduces {actor['name_en']} by name.", f"«{pronoun.capitalize()} зовут» называет имя: {actor['name_ru']}.",
                requirement='a1.language.accusative-name-pattern', pattern=r'^как зовут\b', rule='accusative-naming-person',
                checks=[_token(actor['name_ru'], actor['name_ru'].lower(), 'NOUN', 'nomn')],
                alternative_checks=[[_token(p['name_ru'], p['name_ru'].lower(), 'NOUN', 'nomn')] for p in others],
                source_checks=[_token(pronoun, 'он' if pronoun == 'его' else 'она', 'NPRO', 'accs'), _token('зовут', 'звать', 'VERB')])
        detail = rng.choice(('адрес', 'время', 'имя'))
        others = [word for word in ('адрес', 'время', 'имя') if word != detail]
        source = f"{female['name_ru']} просит: «Повторите {detail}, пожалуйста»."
        _fact(plan, female, 'request', detail, others,
            'Что новая ученица просит повторить?', 'What does the new female classmate ask to hear again?', source,
            'The detail requested again, not a changed time, changed name or new address.',
            'Повторите asks the other person to repeat this information.', '«Повторите» — просьба ещё раз сказать эту информацию.',
            requirement='a1.language.imperative', pattern=r'^что\b', rule='polite-repetition-request',
            checks=[_token(detail, detail, 'NOUN', 'accs')], alternative_checks=[[_token(word, word, 'NOUN', 'accs')] for word in others],
            source_checks=[_token('повторите', 'повторить', 'VERB', 'impr', 'plur')])
        _support(plan, 'новый ученик', 'new male student', 'Supplied role label for identifying the first introduction.')
        _support(plan, 'новая ученица', 'new female student', 'Supplied role label for identifying the second introduction.')
        _support(plan, 'просит', 'asks', 'A narrator reports the request without implying that it has been granted.')
    else:
        objects = rng.sample([row for row in _OBJECTS if row['lemma'] in ('ручка', 'книга', 'журнал', 'телефон')], 3)
        _scope(plan, 'friends checking permission before taking different items',
            'Identify the item each friend asks permission to take.',
            'Three friends each ask to take a different item; none of the requests has yet been answered.',
            ['Each name introduces a quoted Можно взять ...? request. Do not describe a completed action or grant permission.',
             'Keep speaker names beside their request. The three requests concern different items; no one asks for two items.',
             'Use one narrator reporting requests, not voice labels or an acted multi-speaker dialogue.'])
        for actor, item in zip((first, second, third), objects):
            others = [row for row in objects if row != item]
            source = f"{actor['name_ru']} спрашивает: «Можно взять {item['acc']}?»"
            _fact(plan, actor, 'item', item['acc'], [row['acc'] for row in others],
                f"Что {actor['name_ru']} хочет взять?", f"What does {actor['name_en']} want to take?", source,
                'The item in this person’s permission request. Permission has not yet been granted.',
                f"{actor['name_en']} asks to take the {item['en']}; the question does not mean they have taken it.",
                '«Можно взять…?» — вопрос о разрешении, а не сообщение о выполненном действии.',
                requirement='a1.language.impersonal-modal', pattern=r'^что\b', rule='permission-modal-infinitive',
                checks=_object_checks(item, 'acc'), alternative_checks=[_object_checks(row, 'acc') for row in others],
                source_checks=[_token('взять', 'взять', 'INFN')])
        _support(plan, 'спрашивает', 'asks a question', 'Supplied reporting verb; the permission request itself is assessed.')
        _support(plan, 'хочет взять', 'wants to take', 'Supplied question phrase for the requested action, not evidence that permission was granted.')


_BUILDERS = dict(zip(UNITS, (_personal, _agreement, _present, _routine, _possession, _recipients, _social)))


def build_plan(unit, seed, mode, recent_families=()):
    """Build a detached reproducible plan, or None for a different taught unit."""
    identity = unit.get('id')
    if identity not in UNITS:
        return None
    if unit.get('level') != 'A1' or mode not in ('reading', 'listening'):
        raise ValueError('These situation plans describe their taught A1 reading/listening scope.')
    if not isinstance(seed, str) or not seed.strip() or len(seed) > 120:
        raise ValueError('A language plan needs a bounded seed.')
    family = _family(identity, seed, recent_families)
    rng = random.Random(VERSION + ':words:' + identity + ':' + family + ':' + seed)
    # Both genders are needed for personal reference and name-pattern families.
    male = rng.choice([row for row in _PEOPLE if row[2] == 'masculine'])
    female = rng.choice([row for row in _PEOPLE if row[2] == 'feminine'])
    remaining = rng.sample([row for row in _PEOPLE if row not in (male, female)], 3)
    people = [_person(row) for row in [male, female, remaining[0]]]
    rng.shuffle(people)
    writer, addressee = [_person(row) for row in remaining[1:]]
    instrumental = {'Олег': 'Олегом', 'Дима': 'Димой', 'Иван': 'Иваном', 'Миша': 'Мишей',
                    'Анна': 'Анной', 'Нина': 'Ниной', 'Лена': 'Леной', 'Оля': 'Олей', 'Вера': 'Верой'}
    for person in people:
        person['instrumental_ru'] = instrumental[person['name_ru']]
    medium = 'a personal message' if mode == 'reading' else 'a personal voice message'
    plan = {'version': VERSION, 'construction_contract': 'exact-frames-v1', 'unit_id': identity, 'mode': mode,
        'family_id': family, 'recipe_id': family, 'medium': medium,
        'family_contract': {
            'seed_changes_en': 'People, role assignments and suitable checked lexical values vary after the family is chosen.',
            'exposure_identity_en': 'Changing names or prose does not create a different family.',
            'alternative_policy_en': 'All three answers use the same grammatical frame and refer to distinct supplied meanings.',
            'selection_en': 'Least encountered family, then least recent; history precedes lexical sampling.'},
        'supported_phrases': [], 'language_requirement_ids': [], 'checked_forms': [], 'answer_frames': [], 'contrast_rules': [],
        'supporting_language': ['Use the unit’s taught examples, with the explicitly supplied supporting phrases. A familiar lemma is not evidence of a familiar case or conjugation.'],
        'grammar_limits': ['Assess only the selected requirements; the whole unit is not certified by three comprehension questions.',
            'Keep the frozen meaning and grammatical forms. The checked source frames are language references, not prose to concatenate into a story.',
            'The writer may connect the facts naturally, but must keep references unambiguous and source spans sufficient to resolve each person.',
            'Use one speaker in listening. Do not introduce spoken dates, compound clock times, conditional clauses or participles.'],
        'extension_policy': {'checked_forms_are_examples': True,
            'lexical_sources': ['unit teaching', 'supplied familiar vocabulary', 'bounded new vocabulary'],
            'requirements': ['Use only this request’s frozen options for its assessed facts; expand the verified lexical reference in future plans rather than improvising an inflection.',
                             'Incidental new content words need contextual support and remain within the generation allowance.']},
        'meaning_plan': {'version': 'situation-meaning-v2', 'family_id': family, 'medium_en': medium,
            'writer': writer, 'addressee': addressee, 'participants': people,
            'speaker_relationship_en': 'One friend reports known everyday events to another friend.', 'facts': [],
            'constraints': ['The writer and addressee are not interchangeable with the named participants.',
                'The three facts serve one communicative purpose. Do not add further assessable events or explanations of why they happened.',
                'Questions ask about the stated person and relation. Do not expose an answer in a title or question.',
                'Do not concatenate the checked source sentences into an inventory; choose concise, connected prose.']}}
    _BUILDERS[identity](plan, rng, people)
    taught = {q.get('requirement_id') for q in unit.get('questions', [])}
    if not set(plan['language_requirement_ids']) <= taught:
        raise ValueError('The unit does not teach all selected language requirements.')
    # Cardinality and relation checks are cheap enough for every generated plan;
    # morphology is exhaustively exercised by validate_plan in the plan tests.
    _validate_shape(plan)
    return deepcopy(plan)


def _validate_shape(plan):
    if plan.get('unit_id') not in UNITS or plan.get('construction_contract') != 'exact-frames-v1':
        raise ValueError('Unknown personal/action language-plan contract.')
    facts = plan['meaning_plan']['facts']
    if [fact['id'] for fact in facts] != ['f1', 'f2', 'f3']:
        raise ValueError('A situation needs exactly three ordered facts.')
    if not 1 <= len(plan['language_requirement_ids']) <= 2:
        raise ValueError('A short situation has one or two selected language targets.')
    if {fact['requirement_id'] for fact in facts if fact['requirement_id']} != set(plan['language_requirement_ids']):
        raise ValueError('Each selected target needs an assessed fact.')
    for fact in facts:
        if len(fact['alternative_frames']) != 2 or len({fact['value_ru'], *fact['alternative_frames']}) != 3:
            raise ValueError('Answers must be three distinct, grammatically parallel meanings.')
        if not fact['checked_source_frame_ru'] or not fact['question_en'] or not fact['feedback']['caption_en']:
            raise ValueError('A fact needs a checked source, faithful question and authored feedback.')
        if fact['value_ru'].casefold() not in fact['checked_source_frame_ru'].casefold():
            raise ValueError('The reference source must contain its answer.')
        if fact['requirement_id']:
            frames = [frame for frame in plan['answer_frames'] if frame['role'] == fact['role']
                      and frame['requirement_id'] == fact['requirement_id'] and frame['form_key'] == fact['form_key']]
            if len(frames) != 1 or not re.search(frames[0]['question_pattern_ru'], fact['question_frame_ru'].casefold()):
                raise ValueError('A fact must use its one checked question frame.')
            inventory = {row[fact['form_key']] for row in plan['checked_forms'] if row['fact_id'] == fact['id']}
            if inventory != {fact['value_ru'], *fact['alternative_frames']}:
                raise ValueError('All three options need their own checked form records.')
    if len(plan['supported_phrases']) > 5:
        raise ValueError('Keep learner-facing support bounded.')


def validate_plan(plan):
    """Check the authored Russian form references, without pretending to grade prose.

Token checks require one morphological reading to satisfy all its stated tags.
Relation, negation and reference are also frozen explicitly; an analyser alone
cannot decide which person a pronoun denotes or who owns a borrowed object.
"""
    from utils.story_processing import get_morph
    _validate_shape(plan)
    records = [check for row in plan['checked_forms'] for check in row['grammatical_checks']]
    records += [check for fact in plan['meaning_plan']['facts'] for check in fact['source_checks']]
    for check in records:
        readings = get_morph().parse(check['surface_ru'])
        if not any(parsed.is_known and parsed.normal_form.casefold() == check['lemma'].casefold()
                   and set(check['tags']) <= set(parsed.tag.grammemes) for parsed in readings):
            raise ValueError(f"Invalid authored form: {check['surface_ru']} / {check['lemma']} / {check['tags']}")
    for fact in plan['meaning_plan']['facts']:
        source = fact['checked_source_frame_ru'].casefold()
        for check in fact['source_checks']:
            if not re.search(r'(?<!\w)' + re.escape(check['surface_ru'].casefold()) + r'(?!\w)', source):
                raise ValueError('A source construction check must occur in the reference sentence.')
        phrase = fact['value_ru'].casefold()
        requirement = fact['requirement_id']
        prefix = {
            'a1.language.nominative-existence': 'есть ',
            'a1.language.genitive-absence': 'нет ',
            'a1.language.impersonal-modal': 'можно взять ',
        }.get(requirement)
        if prefix and prefix + phrase not in source:
            raise ValueError('The reference sentence has lost the required governing construction.')
    # Do not silently accept the familiar Russian case trap in these units.
    for rule in plan['contrast_rules']:
        values = [row[rule['form_key']] for row in plan['checked_forms'] if rule['form_key'] in row]
        if rule['rule'] == 'personal-pronoun-dative' and not set(values) <= {'ему', 'ей', 'им'}:
            raise ValueError('Recipients need the supplied dative pronouns.')
        if rule['rule'] == 'possessor-u-genitive' and not all(value.startswith('у ') for value in values):
            raise ValueError('A current holder is identified by у plus genitive.')
        if rule['rule'] == 'scheduled-weekday-hour' and not all(re.match(r'^в(?:о)? ', value) for value in values):
            raise ValueError('These schedule answers are complete в/во phrases.')
        if rule['rule'] == 'scheduled-weekday-hour' and not set(values) <= {row[1] for row in _WEEKDAYS} | set(_HOURS):
            raise ValueError('The schedule needs an authored whole-hour or weekday frame.')
