"""Versioned Russian exercise rules, realized before a learner sees a task.

The seed identifies an immutable instance, not an answer shuffle. Version g1
owns its lexicon and rules: change this version when changing their meaning.
No provider, lexical-store write or proficiency award is needed to practise.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import random

from contracts.learning import validate_pack
from services.curriculum_instrumental_generation import build_question as _instrumental
from utils.story_processing import get_morph

PREFIX = 'curriculum-unit:g1:'
PLACES = (
    ('школа', 'school', 'в'), ('библиотека', 'library', 'в'),
    ('магазин', 'shop', 'в'), ('музей', 'museum', 'в'),
    ('парк', 'park', 'в'), ('театр', 'theatre', 'в'),
    ('почта', 'post office', 'на'), ('работа', 'work', 'на'),
)
OBJECTS = (
    ('книга', 'book'), ('карта', 'map'), ('письмо', 'letter'),
    ('журнал', 'magazine'), ('сумка', 'bag'), ('тетрадь', 'notebook'),
    ('билет', 'ticket'), ('ручка', 'pen'),
)
PEOPLE = ('мама', 'папа', 'брат', 'сестра', 'друг', 'подруга')
PEOPLE_GLOSSES = dict(zip(PEOPLE, ('mother', 'father', 'brother', 'sister', 'male friend', 'female friend')))
SUBJECTS = (('Я', '1per', 'sing'), ('Ты', '2per', 'sing'),
            ('Он', '3per', 'sing'), ('Она', '3per', 'sing'),
            ('Мы', '1per', 'plur'), ('Вы', '2per', 'plur'), ('Они', '3per', 'plur'))
WEEKDAYS = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')


@lru_cache(maxsize=1024)
def inflect(lemma, features, pos='NOUN'):
    for parsed in get_morph().parse(lemma):
        if parsed.normal_form == lemma and parsed.tag.POS == pos:
            value = parsed.inflect(frozenset(features.split()))
            if value is not None:
                return value.word
    raise ValueError('No checked realization for ' + lemma + ': ' + features)


def noun_choices(lemma, answer):
    return list(dict.fromkeys([answer] + [inflect(lemma, 'sing ' + case)
        for case in ('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct')]))[:4]


def _question(rule, requirement, sentence, answer, choices, meaning, explanation, explanation_ru,
              *, semantic=None, accepted=None, meaning_ru=None):
    if sentence.count('[...]') != 1 or answer not in choices or len(set(choices)) < 2:
        raise ValueError('A rule must produce a visible gap and distinct answers.')
    signature = hashlib.sha256(repr((rule, semantic or sentence, answer)).encode()).hexdigest()[:20]
    return {'id': 'q-' + signature, 'rule': rule, 'semantic': signature,
            'requirement_id': 'a1.language.' + requirement, 'sentence': sentence,
            'answer_text': answer, 'options': list(dict.fromkeys(choices)),
            'meaning': meaning, 'meaning_ru': meaning_ru or meaning.split(' — ')[0].split(' / ')[-1], 'explanation': explanation, 'explanation_ru': explanation_ru,
            'accepted_answers': accepted or ([answer, answer[:-2] + 'ою'] if rule == 'company' and answer.endswith('ой') else [answer])}


def _location(rng):
    place, english, prep = rng.choice(PLACES)
    destination = rng.choice((True, False))
    subject, person, number = rng.choice(SUBJECTS)
    verb = inflect('идти', 'pres ' + person + ' ' + number, 'INFN') if destination else 'сейчас'
    answer = inflect(place, 'sing ' + ('accs' if destination else 'loct'))
    cue = 'Say where the journey is heading. Refer to one place.' if destination else 'Describe where someone is already located. Refer to one place.'
    cue_ru = 'Назовите одно место, куда направляются.' if destination else 'Назовите одно место, где уже находятся.'
    return _question('destination' if destination else 'location',
        'accusative-destination' if destination else 'prepositional-location',
        f'{subject} {verb} {prep} [...].', answer, noun_choices(place, answer), f'{place} — {english}. {cue}',
        'A destination uses the accusative after в or на.' if destination else 'A location uses the prepositional case after в or на.',
        'Направление: в или на + винительный падеж.' if destination else 'Место: в или на + предложный падеж.',
        meaning_ru=f'{place}. {cue_ru}')


def _possession(rng):
    noun, gloss = rng.choice(OBJECTS)
    owner = rng.choice(('меня', 'тебя', 'него', 'неё', 'нас', 'вас', 'них'))
    absent = rng.choice((False, True))
    answer = inflect(noun, 'sing gent') if absent else noun
    return _question('absence' if absent else 'existence', 'genitive-absence' if absent else 'nominative-existence',
        f'У {owner} {"нет" if absent else "есть"} [...].', answer, noun_choices(noun, answer), f'{noun} — {gloss}. Refer to one item.',
        'After нет, put the missing thing in the genitive.' if absent else 'After есть, name the thing in the nominative.',
        'После нет — родительный падеж.' if absent else 'После есть — именительный падеж.',
        meaning_ru=f'{noun}. Речь об одном предмете.')


def _recipient(rng):
    noun, gloss = rng.choice(OBJECTS)
    person = rng.choice(PEOPLE)
    if rng.choice((True, False)):
        answer = inflect(person, 'sing datv')
        obj = inflect(noun, 'sing accs')
        return _question('recipient', 'dative-recipient', f'Я даю {obj} [...].', answer,
            noun_choices(person, answer), f'{person} — {PEOPLE_GLOSSES[person]}. Name the person receiving the item.',
            'The person receiving something takes the dative.', 'Получатель: кому? Дательный падеж.',
            meaning_ru=f'{person}. Назовите получателя предмета.')
    answer = inflect(noun, 'sing accs')
    return _question('object', 'accusative-object', f'Я даю [...] {inflect(person, "sing datv")}.', answer,
        noun_choices(noun, answer), f'{noun} — {gloss}. Refer to one item.',
        'The thing being given is the direct object, in the accusative.', 'Предмет: что? Винительный падеж.',
        meaning_ru=f'{noun}. Речь об одном предмете.')


def _present(rng):
    subject, person, number = rng.choice(SUBJECTS)
    lemma = rng.choice(('читать', 'говорить'))
    complement = rng.choice(('по-русски', 'по-английски')) if lemma == 'говорить' else rng.choice(('книгу', 'письмо', 'журнал'))
    answer = inflect(lemma, 'pres ' + person + ' ' + number, 'INFN')
    choices = list(dict.fromkeys(inflect(lemma, 'pres ' + p + ' ' + n, 'INFN') for _, p, n in SUBJECTS))
    return _question('present-person', 'verb-conjugation', f'{subject} [...] {complement}.', answer,
        [answer] + [x for x in choices if x != answer][:3], lemma,
        f'{subject} determines the person and number of the present-tense verb.',
        f'Форма глагола зависит от подлежащего «{subject}».')


def _time(rng):
    day = rng.choice(WEEKDAYS)
    action = rng.choice(('я работаю', 'у нас урок', 'мы идём в музей', 'я читаю дома'))
    answer = inflect(day, 'sing accs')
    return _question('weekday', 'accusative-clock-weekday', f'В [...] {action}.', answer,
        noun_choices(day, answer), day + '. Describe a single occasion.',
        'Use в + accusative to say on which day something happens.', 'День события: в + винительный падеж.',
        meaning_ru=day + '. Речь об одном дне.')


def _agreement(rng):
    noun, gloss = rng.choice(OBJECTS)
    adjective = rng.choice(('новый', 'старый', 'большой', 'маленький'))
    plural = rng.choice((True, False))
    gender = next(p.tag.gender for p in get_morph().parse(noun) if p.normal_form == noun and p.tag.POS == 'NOUN')
    tags = 'plur nomn' if plural else 'sing nomn ' + gender
    answer = inflect(adjective, tags, 'ADJF')
    choices = [inflect(adjective, 'sing nomn ' + g, 'ADJF') for g in ('masc', 'femn', 'neut')]
    choices.append(inflect(adjective, 'plur nomn', 'ADJF'))
    surface = inflect(noun, 'plur nomn') if plural else noun
    return _question('adjective-agreement', 'adjective-agreement', f'Это [...] {surface}.', answer,
        choices, f'{adjective} — {dict(новый="new", старый="old", большой="big", маленький="small")[adjective]}; {noun} — {gloss}',
        'Match the adjective to the noun’s gender and number.', 'Прилагательное согласуется с существительным в роде и числе.')


def _reference(rng):
    pronoun, target = rng.choice((('я', 'меня'), ('ты', 'тебя'), ('он', 'его'), ('она', 'её'), ('мы', 'нас'), ('вы', 'вас'), ('они', 'их')))
    verb = rng.choice(('видеть', 'знать', 'понимать'))
    subject, person = ('Он', '3per') if pronoun in ('я', 'мы') else ('Я', '1per')
    verb = inflect(verb, 'pres sing ' + person, 'INFN')
    return _question('object-pronoun', 'personal-pronoun-cases', f'{subject} {verb} [...].', target,
        [target, pronoun, {'я':'мне','ты':'тебе','он':'ему','она':'ей','мы':'нам','вы':'вам','они':'им'}[pronoun]],
        f'Use the pronoun {pronoun}.',
        'The pronoun is the direct object. Use its accusative form.', 'Местоимение — прямое дополнение: винительный падеж.', meaning_ru=f'Используйте местоимение {pronoun}.')


def _motion(rng):
    subject, person, number = rng.choice(SUBJECTS)
    vehicle = rng.choice((False, True))
    # Explicit outward AND return trips disambiguate ходить/ездить. Merely
    # saying "every day" does not rule out идти/ехать on the outward leg.
    repeated = rng.choice((False, True))
    lemma = ('ездить' if repeated else 'ехать') if vehicle else ('ходить' if repeated else 'идти')
    place, _, prep = rng.choice(PLACES)
    where = prep + ' ' + inflect(place, 'sing accs')
    if repeated:
        context = 'Туда и обратно, много раз.'
        english = 'Repeated journeys there and back.'
    else:
        context = 'По дороге туда, прямо сейчас.'
        english = 'On the outward journey, right now.'
    mode = 'на автобусе' if vehicle else 'пешком'
    answer = inflect(lemma, 'pres ' + person + ' ' + number, 'INFN')
    choices = [inflect(v, 'pres ' + person + ' ' + number, 'INFN') for v in ('идти', 'ходить', 'ехать', 'ездить')]
    return _question('motion-mode-direction', 'motion-basic-pairs', f'{context}\n{subject} [...] {where} {mode}.', answer,
        choices, english,
        ('Vehicle travel uses ехать/ездить. ' if vehicle else 'Walking uses идти/ходить. ') +
        ('Here there are repeated journeys in both directions.' if repeated else 'Here the journey is in progress in one direction.'),
        ('Транспорт: ехать/ездить. ' if vehicle else 'Пешком: идти/ходить. ') +
        ('Здесь повторяются поездки туда и обратно.' if repeated else 'Здесь движение сейчас в одном направлении.'), meaning_ru=context)


def _quantity(rng):
    noun, gloss = rng.choice(OBJECTS)
    number = rng.choice((2, 3, 4, 5, 6, 7, 8, 9, 10))
    answer = inflect(noun, ('sing' if number < 5 else 'plur') + ' gent')
    choices = list(dict.fromkeys([answer, noun, inflect(noun, 'plur nomn'), inflect(noun, 'sing datv'), inflect(noun, 'sing gent')]))[:4]
    return _question('quantity', 'genitive-quantity', f'У меня {number} [...].', answer, choices, f'{noun} — {gloss}',
        'After 2–4 use genitive singular; after 5–10 use genitive plural.',
        'После 2–4 — родительный единственного числа; после 5–10 — родительный множественного числа.')


def _social(rng):
    lemma, informal, polite = rng.choice((('читать','читай','читайте'), ('говорить','говори','говорите'),
        ('слушать','слушай','слушайте'), ('повторять','повторяй','повторяйте'), ('писать','пиши','пишите')))
    formal = rng.choice((False, True))
    answer = polite if formal else informal
    context = 'Обращение на вы.' if formal else 'Обращение к другу на ты.'
    return _question('polite-instruction', 'imperative', f'{context}\n[...], пожалуйста.', answer, [informal, polite], lemma,
        'Use the -те form when addressing someone as вы.' if formal else 'Use the singular informal form when addressing a friend as ты.',
        'При обращении на вы используйте форму с -те.' if formal else 'При обращении на ты используйте форму единственного числа.')


def _company(rng):
    person = rng.choice(PEOPLE)
    action = rng.choice(('Я говорю', 'Я гуляю', 'Я иду в парк', 'Я работаю'))
    answer = inflect(person, 'sing ablt')
    return _question('company', 'instrumental-company', f'{action} с [...].', answer,
        noun_choices(person, answer), f'{person} — {PEOPLE_GLOSSES[person]}. Name one companion.',
        'With a person uses с + instrumental.', 'Совместное действие: с кем? С + творительный падеж.',
        meaning_ru=f'{person}. Назовите одного спутника.')


def _aspect(rng):
    impf, perf, obj = rng.choice((('читать', 'прочитать', 'книгу'), ('писать', 'написать', 'письмо'),
                                ('делать', 'сделать', 'задание')))
    complete = rng.choice((False, True))
    subject, gender = rng.choice((('Он', 'masc'), ('Она', 'femn')))
    imperfect = inflect(impf, 'past sing ' + gender, 'INFN')
    perfect = inflect(perf, 'past sing ' + gender, 'INFN')
    # Name the requested viewpoint explicitly; imperfective past can describe
    # a completed event in general-factual contexts and is not inherently wrong.
    wording = 'Подчеркните завершённый результат.' if complete else 'Покажите процесс: работа ещё не закончена.'
    answer = perfect if complete else imperfect
    return _question('aspect-viewpoint', 'verb-aspect', f'{wording}\n{subject} [...] {obj}.', answer,
        [imperfect, perfect], 'Emphasise the completed result.' if complete else 'Describe the unfinished activity.',
        'Perfective foregrounds the completed result; imperfective presents the activity.',
        'Совершенный вид подчёркивает результат; несовершенный — процесс.', meaning_ru=wording)


def _origin(rng):
    place, gloss, prep = rng.choice(PLACES)
    origin = 'из' if prep == 'в' else 'с'
    subject, person, number = rng.choice(SUBJECTS)
    answer = inflect(place, 'sing gent')
    return _question('origin', 'genitive-origin',
        f'{subject} {inflect("идти", "pres " + person + " " + number, "INFN")} {origin} [...].',
        answer, noun_choices(place, answer), f'{place} — {gloss}. Say where the journey started. Refer to one place.',
        'Where from uses из or с + genitive. Pair в with из and на with с.',
        'Откуда: из или с + родительный падеж. В — из, на — с.',
        meaning_ru=f'{place}. Назовите одно место, откуда начался путь.')


def _connected(rng):
    name = rng.choice(('Анна', 'Нина', 'Вера', 'Оля'))
    reason = rng.choice((True, False))
    if reason:
        before, after = rng.choice((('осталась дома', 'заболела'), ('взяла зонт', 'начался дождь'),
            ('купила хлеб', 'дома нет хлеба'), ('пошла в магазин', 'нужен хлеб'),
            ('открыла окно', 'в комнате жарко'), ('закрыла окно', 'на улице холодно'),
            ('позвонила маме', 'хотела поговорить'), ('поехала на автобусе', 'школа далеко'),
            ('пошла в библиотеку', 'нужна книга'), ('написала другу', 'хотела пригласить его в гости')))
        sentence, answer, cue = f'{name} {before}, [...] {after}.', 'потому что', 'Give the reason.'
        ru = 'Укажите причину.'
    else:
        before, after = rng.choice((('пришла домой', 'позвонила маме'), ('закончила работу', 'пошла домой'),
            ('прочитала письмо', 'написала ответ'), ('купила билет', 'пошла на вокзал'),
            ('приготовила чай', 'позвала маму'), ('позавтракала', 'пошла в школу'),
            ('купила продукты', 'приготовила обед'), ('вернулась с работы', 'открыла письмо')))
        sentence, answer, cue = f'Сначала {name} {before}, а [...] {after}.', 'потом', 'What happened next?'
        ru = 'Что было потом?'
    return _question('reason' if reason else 'sequence', 'time-and-reason-clauses', sentence,
        answer, ['потому что', 'потом', 'или'], cue,
        'Потому что introduces a reason; сначала … потом orders events.',
        'Потому что вводит причину; сначала … потом показывает порядок событий.',
        semantic=(before, after, answer), meaning_ru=ru)


BUILDERS = {
    'location-destination-v1': _location, 'possession-absence-v1': _possession,
    'objects-recipients-v1': _recipient, 'present-actions-v1': _present,
    'time-routine-v1': _time, 'noun-adjective-agreement-v1': _agreement,
    'personal-reference-v1': _reference, 'basic-motion-v1': _motion,
    'numbers-quantities-v1': _quantity, 'social-exchanges-v1': _social,
    'needs-company-v1': _company, 'action-aspect-v1': _aspect,
    'origins-and-destinations-v1': _origin, 'connected-messages-v1': _connected,
    'instrumental-activities-professions-v1': _instrumental,
}


def build(unit_id, seed, stage='practice'):
    """Return a deterministic pack and its question contracts, without writes.

    The caller chooses a seed against exposure history. A finite rule space can
    eventually repeat; revision is not proof of fresh transfer.
    """
    from services.curriculum_units import get_unit
    if unit_id not in BUILDERS or stage not in ('practice', 'forms'):
        raise ValueError('Unsupported generative lesson stage.')
    rng = random.Random(seed)
    unit = deepcopy(get_unit(unit_id))
    candidates = {}
    for _ in range(160):
        q = BUILDERS[unit_id](rng)
        candidates.setdefault(q['semantic'], q)
    values = list(candidates.values())
    rng.shuffle(values)
    # Include each taught function before filling the set. Random selection
    # alone can omit one side of a contrast, such as location/destination.
    selected, covered = [], set()
    for q in values:
        if q['rule'] not in covered:
            selected.append(q)
            covered.add(q['rule'])
    if len(selected) > 6:
        raise ValueError('Split the lesson before adding more practice functions.')
    selected_ids = {q['id'] for q in selected}
    selected.extend(q for q in values if q['id'] not in selected_ids)
    selected = selected[:6]
    rng.shuffle(selected)
    if len(selected) < 4:
        raise ValueError('The grammar rule has insufficient distinct situations.')
    items, questions = [], []
    for q in selected:
        forms = stage == 'forms'
        options = q['options'][:]
        rng.shuffle(options)
        choices = [{'id': f'option-{i}', 'text': text} for i, text in enumerate(options)]
        prompt = q['sentence'] + '\n' + q['meaning']
        item = {'id': q['id'], 'type': 'controlled_text' if forms else 'choice',
                'prompt': prompt, 'hint': q['explanation']}
        if forms:
            item.update(answer=q['answer_text'], accepted_answers=q['accepted_answers'])
        else:
            item.update(choices=choices, answer=next(c['id'] for c in choices if c['text'] == q['answer_text']))
        items.append(item)
        questions.append({**q, 'prompt': prompt, 'expectation': 'Use the taught construction in this stated context.',
                          'hint_ru': q['explanation_ru'], 'prompt_ru': q['sentence'] + '\n' + q['meaning_ru']})
    identity = PREFIX + unit_id + ':' + ('f' if stage == 'forms' else 'p') + ':' + seed
    pack = {'schema_version': 1, 'id': identity, 'kind': 'activity', 'title': unit['title'],
            'source': 'Rule-generated Russian practice; g1; ' + unit_id, 'items': items}
    validate_pack(pack)
    return pack, unit, questions


def decode(pack):
    if not pack['id'].startswith(PREFIX):
        return None
    rest = pack['id'][len(PREFIX):].split(':')
    if len(rest) != 3 or rest[0] not in BUILDERS or rest[1] not in ('p', 'f'):
        raise ValueError('Unknown generated practice version.')
    return rest[0], rest[2], 'forms' if rest[1] == 'f' else 'practice'
