"""Frozen relationship plans for seven taught A1 units.

These are semantic and inflection blocks, not completed passage templates. A
writer supplies the connected message after the people, event and answer key
are chosen. The linked language requirements describe comprehension evidence;
selecting an answer does not establish independent grammatical production.
"""
from copy import deepcopy
import random
import re

VERSION = 'curriculum-language-plan-v5'
UNITS = (
    'basic-motion-v1', 'numbers-quantities-v1', 'needs-company-v1',
    'action-aspect-v1', 'origins-and-destinations-v1', 'connected-messages-v1',
    'instrumental-activities-professions-v1',
)

_PEOPLE = (
    ('Олег', 'Oleg', 'Олега', 'Олегу', 'm'),
    ('Иван', 'Ivan', 'Ивана', 'Ивану', 'm'),
    ('Миша', 'Misha', 'Миши', 'Мише', 'm'),
    ('Анна', 'Anna', 'Анны', 'Анне', 'f'),
    ('Нина', 'Nina', 'Нины', 'Нине', 'f'),
    ('Лена', 'Lena', 'Лены', 'Лене', 'f'),
    ('Вера', 'Vera', 'Веры', 'Вере', 'f'),
)
_PLACES = (
    ('школа', 'в школе', 'в школу', 'из школы'),
    ('библиотека', 'в библиотеке', 'в библиотеку', 'из библиотеки'),
    ('магазин', 'в магазине', 'в магазин', 'из магазина'),
    ('почта', 'на почте', 'на почту', 'с почты'),
    ('музей', 'в музее', 'в музей', 'из музея'),
    ('аптека', 'в аптеке', 'в аптеку', 'из аптеки'),
    ('театр', 'в театре', 'в театр', 'из театра'),
)
_COMPANY = (
    ('брат', 'с братом', 'от брата', 'к брату'),
    ('сестра', 'с сестрой', 'от сестры', 'к сестре'),
    ('друг', 'с другом', 'от друга', 'к другу'),
    ('подруга', 'с подругой', 'от подруги', 'к подруге'),
)
_TRANSPORT = ('на автобусе', 'на поезде', 'на машине')
_ACTIVITIES = (('спорт', 'спортом'), ('музыка', 'музыкой'), ('русский язык', 'русским языком'))
_PROFESSIONS = (('врач', 'врачом'), ('учитель', 'учителем'), ('инженер', 'инженером'))
# Only these supplied simple-count paradigms are used. A familiar noun does not
# license automatic guessing of its counted plural or numeral agreement.
_COUNTS = (
    ('яблоко', ('одно яблоко', 'два яблока', 'три яблока', 'четыре яблока', 'пять яблок')),
    ('груша', ('одна груша', 'две груши', 'три груши', 'четыре груши', 'пять груш')),
    ('чашка', ('одна чашка', 'две чашки', 'три чашки', 'четыре чашки', 'пять чашек')),
    ('тарелка', ('одна тарелка', 'две тарелки', 'три тарелки', 'четыре тарелки', 'пять тарелок')),
    ('тетрадь', ('одна тетрадь', 'две тетради', 'три тетради', 'четыре тетради', 'пять тетрадей')),
    ('карандаш', ('один карандаш', 'два карандаша', 'три карандаша', 'четыре карандаша', 'пять карандашей')),
)
_FAMILIES = {
    UNITS[0]: (
        ('motion-changed-commute', 'explaining a change to the usual journey',
         'Keep the usual walking routine separate from today’s vehicle journey to the same destination.'),
        ('motion-connection-on-foot', 'finding a friend after a vehicle journey',
         'The first journey by vehicle has ended. The person is now walking from the station to a nearby destination.'),
    ),
    UNITS[1]: (
        ('quantities-preparing-a-table', 'checking what is ready for a shared snack',
         'Three stated quantities of different food or table items; no calculation or inferred number of guests.'),
        ('quantities-class-materials', 'finding the current lesson and checking its materials',
         'The position of the current lesson is distinct from the quantities of two school items.'),
    ),
    UNITS[2]: (
        ('needs-sharing-an-errand', 'arranging an errand while another friend has a different need',
         'One person needs to buy an item and goes with a companion; a second person needs to rest, work or telephone.'),
        ('company-tea-preferences', 'preparing tea for a friend and a companion',
         'A human companion and the different additions to two people’s tea are separate relationships.'),
    ),
    UNITS[3]: (
        ('aspect-letter-progress', 'checking which letter is ready to send',
         'One person wrote only part of a letter yesterday; another completed a letter. The first person promises a completed result tomorrow.'),
        ('aspect-reading-handover', 'passing on a letter after reading it',
         'One person has finished reading a letter; a second has not read it yet and plans to spend time reading tomorrow, without promising completion.'),
    ),
    UNITS[4]: (
        ('origins-errand-sequence', 'arranging where to meet during an errand',
         'A previous place, the immediate next stop and one later stop form a three-place route; none is the current stationary location.'),
        ('origins-family-visits', 'coordinating visits to relatives or friends',
         'The first person has left one person and is going to another; the second traveller has a separate origin.'),
    ),
    UNITS[5]: (
        ('messages-meeting-change', 'updating a meeting plan',
         'A stated reason explains a changed meeting time; the agreed venue is unchanged. Do not reverse cause and consequence.'),
        ('messages-call-after-activity', 'explaining when a friend can telephone',
         'A named activity is happening now and prevents a call; its end is the trigger for a stated telephone call.'),
    ),
    UNITS[6]: (
        ('instrumental-shared-interests', 'finding a friend to practise with',
         'Two people practise different activities; one also states a future profession. A hobby does not prove or cause a career.'),
        ('instrumental-now-and-future', 'introducing a working adult and a learner’s plans',
         'One person has a profession now; another plans the same profession for the future and names their current study activity.'),
    ),
}


def _family(identity, seed, recent):
    families = _FAMILIES[identity]
    known = {row[0] for row in families}
    history = [value for value in recent if isinstance(value, str) and value in known]
    def score(row):
        return history.count(row[0]), -(history.index(row[0]) if row[0] in history else len(history))
    best = min(map(score, families))
    return random.Random(f'{VERSION}:family:{identity}:{seed}').choice([f for f in families if score(f) == best])


def _person(row):
    name, english, genitive, dative, gender = row
    return {'name_ru': name, 'name_en': english, 'genitive_ru': genitive,
            'dative_ru': dative, 'gender': 'feminine' if gender == 'f' else 'masculine'}


def _support(plan, ru, en, scope):
    plan['supported_phrases'].append({'ru': ru, 'en': en, 'scope': scope})


def _frame(plan, role, key, requirement, question, pattern, rule, meaning, values):
    """Inventory complete alternatives, rather than abstract endings."""
    frame = {'role': role, 'form_key': key, 'requirement_id': requirement,
             'question_ru': question, 'question_pattern_ru': pattern}
    if frame not in plan['answer_frames']:
        plan['answer_frames'].append(frame)
    for value in values:
        row = {key: value}
        if row not in plan['checked_forms']:
            plan['checked_forms'].append(row)
    if requirement:
        if requirement not in plan['language_requirement_ids']:
            plan['language_requirement_ids'].append(requirement)
        contrast = {'requirement_id': requirement, 'rule': rule,
                    'form_key': key, 'meaning_en': meaning}
        if contrast not in plan['contrast_rules']:
            plan['contrast_rules'].append(contrast)
    return key


def _hint_details(plan, person, role, key, requirement):
    """Short authored fragments for each relation; preserve personal names."""
    name, en = person['name_ru'], person['name_en']
    if role == 'activity':
        if requirement == 'a1.language.motion-basic-pairs':
            if plan['family_id'] == 'motion-changed-commute':
                return f'how {en} usually makes this journey', f'как обычно передвигается {name}'
            return f'how {en} travels after the station', f'как передвигается {name} после вокзала'
        if requirement == 'a1.language.dative-need':
            return f'what {en} needs to do', f'что нужно сделать {person["dative_ru"]}'
        if requirement == 'a1.language.verb-aspect':
            return f'what {en} did yesterday and whether the task was finished', f'что {name} делал{ "а" if person["gender"] == "feminine" else ""} вчера и было ли действие закончено'
        if requirement == 'a1.language.verb-tense':
            action = 'сделать' if plan['family_id'] == 'aspect-letter-progress' else 'делать'
            return f'what {en} plans to do tomorrow', f'что {name} планирует {action} завтра'
        if requirement == 'a1.language.instrumental-activity':
            return f'the activity {en} studies or practises', f'чем занимается {name}'
        if key == 'call_action':
            return f'who {en} plans to call afterwards', f'кому {name} позвонит потом'
        return f'how {en} is travelling', f'как передвигается {name}'
    if role == 'destination':
        return 'the destination of this part of the journey', 'куда человек направляется на этом этапе'
    if role == 'transport':
        return 'the stated vehicle for this part of the journey', 'на чём человек едет на этом этапе'
    if role == 'quantity':
        return 'the stated count of the items named in the question', 'сколько именно названных предметов есть у человека'
    if role == 'ordinal':
        return 'the position of the current lesson in the sequence', 'который урок идёт сейчас'
    if role == 'companion':
        return f'the person going with {en}', f'с кем идёт {name}'
    if role == 'ingredient':
        return f'the addition {en} wants in the tea', f'с чем {name} хочет чай'
    if role == 'origin':
        return f'where {en} is coming from', f'откуда идёт {name}'
    if role == 'person_destination':
        return f'the person {en} is going to visit', f'к кому идёт {name}'
    if role == 'reason':
        return (('the reason for moving the meeting to a later time', 'почему встречу переносят на более позднее время')
                if key == 'meeting_reason' else ('the reason the call has to wait', 'почему человек пока не звонит'))
    if role == 'time':
        return (('the new meeting time after the change', 'во сколько будет встреча после изменения')
                if key == 'meeting_time' else ('which activity must end before the call', 'какое дело должно закончиться перед звонком'))
    if role == 'location':
        return 'the place where the meeting will take place', 'где состоится встреча'
    if role == 'profession':
        return ((f'the profession {en} has now', f'кто {name} по профессии сейчас') if key == 'present_profession'
                else (f'the profession {en} plans to have', f'кем {name} планирует быть'))
    raise ValueError(f'No authored hint for {plan["family_id"]}: {role}')


def _fact(plan, person, role, key, requirement, question_ru, question_en,
          value, alternatives, source, relation, caption_en, caption_ru):
    detail_en, detail_ru = _hint_details(plan, person, role, key, requirement)
    fact = {
        'id': 'f' + str(len(plan['meaning_plan']['facts']) + 1),
        'role': role, 'form_key': key, 'requirement_id': requirement,
        'subject_name': person['name_ru'], 'subject_en': person['name_en'],
        'value_ru': value, 'alternative_frames': list(alternatives),
        'question_frame_ru': question_ru, 'question_en': question_en,
        'checked_source_frame_ru': source, 'relation_en': relation,
        'feedback': {'detail_en': detail_en, 'detail_ru': detail_ru,
                     'caption_en': caption_en, 'caption_ru': caption_ru},
    }
    plan['meaning_plan']['facts'].append(fact)
    return fact


def _destination(plan, person, place, others, *, later=False, requirement=None):
    values = [place[2], *(row[2] for row in others)]
    key = _frame(plan, 'destination', 'destination', requirement, 'Куда?', r'^куда\b',
                 'directed-destination', 'The stated next destination, not an origin or current location.', values)
    when = 'потом' if later else 'сейчас'
    _fact(plan, person, 'destination', key, requirement,
          f"Куда {when} идёт {person['name_ru']}?", f"Where is {person['name_en']} going {'afterwards' if later else 'now'}?",
          values[0], values[1:], f"{person['name_ru']} {'потом пойдёт' if later else 'сейчас идёт'} {values[0]}.",
          'The later stop.' if later else 'The current destination.',
          'This names the later stop.' if later else 'This names the destination of the current journey.',
          'Здесь названо следующее место.' if later else 'Здесь сказано, куда человек идёт сейчас.')


def _motion(plan, rng, a, b):
    motion, transport = 'a1.language.motion-basic-pairs', 'a1.language.prepositional-transport'
    destination, *others = rng.sample([r for r in _PLACES if r[0] in ('школа', 'библиотека', 'музей', 'почта')], 3)
    vehicles = rng.sample(list(_TRANSPORT), 3)
    routine = plan['family_id'] == 'motion-changed-commute'
    name, en = a['name_ru'], a['name_en']
    _support(plan, 'обычно', 'usually', 'Keeps a routine separate from one journey under way.')
    if routine:
        value = 'ходит пешком'
        alternatives = ['ездит на автобусе', 'ездит на машине']
        key = _frame(plan, 'activity', 'motion_activity', motion, 'Как обычно?', r'^как\b',
                     'habit-versus-current-journey', 'The ordinary walking routine, distinct from today’s directed trip.', [value, *alternatives])
        _fact(plan, a, 'activity', key, motion, f'Как {name} обычно добирается туда?',
              f'How does {en} usually get there?', value, alternatives,
              f'{name} обычно {value}.', 'The usual routine, not today’s journey.',
              'Обычно describes the usual journey; today’s journey is different.', 'Обычно — это привычный путь, а не путь сегодня.')
        source = f'{name} сегодня едет {vehicles[0]}.'
        question, english = f'На чём {name} едет сегодня?', f'What transport is {en} using today?'
        _support(plan, 'добирается туда', 'gets there', 'Question support; туда refers only to the one named destination.')
        _support(plan, 'сегодня сильный дождь', 'it is raining heavily today', 'Optional reason for the change, not a fourth assessed fact.')
        plan['meaning_plan']['constraints'].append('Use ходит for the stated ordinary walking routine and едет for today’s journey under way. The source may use the supplied rain phrase to motivate the change, not an additional question.')
    else:
        value = 'идёт пешком'
        alternatives = ['едет на автобусе', 'едет на машине']
        key = _frame(plan, 'activity', 'motion_activity', motion, 'Как сейчас?', r'^как\b',
                     'current-directed-journey', 'The current walking leg after the first vehicle journey has ended.', [value, *alternatives])
        _fact(plan, a, 'activity', key, motion, f'Как {name} добирается туда после вокзала?',
              f'How is {en} getting there after the station?', value, alternatives,
              f'{name} сейчас {value}.', 'The second leg now, not the earlier vehicle journey.',
              'The vehicle journey has ended. This is the walking part after the station.', 'Поездка уже закончилась. Теперь человек идёт пешком.')
        past = 'ехала' if a['gender'] == 'feminine' else 'ехал'
        source = f'{name} сначала {past} {vehicles[0]}.'
        question, english = f'На чём {name} {past} сначала?', f'What transport did {en} use first?'
        _support(plan, f'сначала {past}', 'first travelled by vehicle', 'Past first leg; agree with the named person.')
        _support(plan, 'после вокзала', 'after the station', 'The second leg begins near the station, not an implausible long-distance walk.')
        plan['meaning_plan']['constraints'].append('The vehicle journey has ended at the station. The nearby final stop is reached on foot; do not imply that the person has already arrived there.')
    key = _frame(plan, 'transport', 'transport', transport, 'На чём?', r'^на чем\b',
                 'means-of-transport', 'На plus prepositional names the vehicle, not its destination.', vehicles)
    _fact(plan, a, 'transport', key, transport, question, english, vehicles[0], vehicles[1:], source,
          'The vehicle on the named journey leg.', 'This names the transport for this part of the journey.', 'Здесь назван транспорт на этой части пути.')
    # Destination is supporting comprehension; this unit does not assess the
    # destination case as an additional language requirement.
    _destination(plan, a, destination, others)
    f = plan['meaning_plan']['facts'][-1]
    # A destination question must not supply the walking/vehicle contrast that
    # another question asks the learner to hear. Направляется is neutral here.
    f['question_frame_ru'] = f"Куда {name} направляется {'сегодня' if routine else 'сейчас'}?"
    f['question_en'] = f"Where is {en} heading {'today' if routine else 'now'}?"
    f['feedback']['detail_ru'] = 'куда человек направляется'
    f['feedback']['detail_en'] = 'the destination of this journey'
    _support(plan, 'направляется', 'is heading', 'Question support; this verb does not reveal whether the person is walking or using transport.')
    if routine:
        f['checked_source_frame_ru'] = f'{name} сегодня едет {destination[2]}.'
    plan['grammar_limits'] += [
        'Do not treat every frequency expression as forcing ходить/ездить: the frozen event explicitly states an ordinary routine.',
        'Пешком is an adverb without a preposition. На автобусе/поезде/машине names transport; в автобусе would instead locate someone inside it.',
        'No inferred arrival, prefixed-verb paradigm or air-travel prerequisite is assessed.',
    ]


def _quantity(plan, rng, person, row, situation):
    lemma, inventory = row
    # The assessed fact must actually exhibit a counted genitive; one remains
    # a grammatical distractor, not false evidence of practising that case.
    chosen = rng.choice(inventory[1:])
    values = [chosen, *rng.sample([v for v in inventory if v != chosen], 2)]
    requirement = 'a1.language.genitive-quantity'
    key = _frame(plan, 'quantity', 'quantity_' + lemma, requirement, 'Сколько?', r'^сколько\b',
                 'simple-count', 'A stated quantity, with the counted noun form matched to the numeral.', values)
    plural = {'яблоко': 'яблок', 'груша': 'груш', 'чашка': 'чашек', 'тарелка': 'тарелок',
              'тетрадь': 'тетрадей', 'карандаш': 'карандашей'}[lemma]
    english = {'яблоко': 'apples', 'груша': 'pears', 'чашка': 'cups', 'тарелка': 'plates',
               'тетрадь': 'notebooks', 'карандаш': 'pencils'}[lemma]
    _fact(plan, person, 'quantity', key, requirement,
          f"Сколько {plural} у {person['genitive_ru']}?", f"How many {english} does {person['name_en']} have?",
          values[0], values[1:], f"У {person['genitive_ru']} {values[0]}.", situation,
          'Use the stated count for this item; do not add counts of different items.', 'Здесь указано количество именно этих предметов.')


def _numbers(plan, rng, a, b):
    if plan['family_id'] == 'quantities-preparing-a-table':
        # One fruit and two table items are a coherent preparation problem.
        selected = [rng.choice(_COUNTS[:2]), *_COUNTS[2:4]]
        for row in selected:
            _quantity(plan, rng, a, row, 'One of the three quantities available for this shared snack.')
        _support(plan, 'всё для чая', 'everything for tea', 'A shared purpose for the quantities, not a requirement to infer how many guests will attend.')
    else:
        ordinals = rng.sample(['первый урок', 'второй урок', 'третий урок'], 3)
        requirement = 'a1.language.cardinal-and-ordinal'
        key = _frame(plan, 'ordinal', 'lesson_ordinal', requirement, 'Который?', r'^который\b',
                     'ordinal-position', 'The position of the current lesson, not how many lessons there are.', ordinals)
        _fact(plan, a, 'ordinal', key, requirement, f"Который сейчас урок у {a['genitive_ru']}?",
              f"Which lesson in the sequence is {a['name_en']} in now?", ordinals[0], ordinals[1:],
              f"У {a['genitive_ru']} сейчас {ordinals[0]}.", 'The current lesson’s position, not the total number of lessons.',
              'This gives the position of the current lesson. It does not give the total.', 'Здесь указан порядок урока, а не количество уроков.')
        for row in _COUNTS[4:]:
            _quantity(plan, rng, a, row, 'The materials the learner has for this lesson.')
        _support(plan, 'который урок?', 'which lesson in the sequence?', 'This supplied question asks about order; сколько asks for a quantity.')
        _support(plan, 'третий урок', 'the third lesson', 'A checked extension of the taught ordinal agreement pattern, shown before practice.')
    plan['grammar_limits'] += [
        'Keep quantities in the simple nominative possession frame У ...; do not put одна груша into a купить accusative slot.',
        'Use only the supplied one-to-five counted noun paradigms. Do not infer case forms from an uninflected lemma.',
        'Do not require arithmetic, unstated totals, prices or spoken ordinal dates.',
    ]


def _companion(plan, person, rows):
    requirement = 'a1.language.instrumental-company'
    values = [r[1] for r in rows]
    key = _frame(plan, 'companion', 'companion', requirement, 'С кем?', r'^с кем\b',
                 'human-company', 'С plus instrumental identifies the human companion.', values)
    _fact(plan, person, 'companion', key, requirement, f"С кем идёт {person['name_ru']}?",
          f"Who is {person['name_en']} going with?", values[0], values[1:],
          f"{person['name_ru']} идёт {values[0]}.", 'The person going together, not an ingredient or someone visited.',
          'This names the companion travelling with the person.', 'Здесь сказано, с кем человек идёт вместе.')


def _need(plan, person, actions):
    requirement = 'a1.language.dative-need'
    key = _frame(plan, 'activity', 'needed_action', requirement, 'Что нужно сделать?', r'^что\b',
                 'dative-need-infinitive', 'The dative person needs to do the stated infinitive action.', actions)
    _fact(plan, person, 'activity', key, requirement, f"Что нужно сделать {person['dative_ru']}?",
          f"What does {person['name_en']} need to do?", actions[0], actions[1:],
          f"{person['dative_ru']} нужно {actions[0]}.", 'This person’s need, not the companion’s action.',
          'Нужно refers to the named person and the action they need to do.', 'Нужно относится к названному человеку и его действию.')


def _needs(plan, rng, a, b):
    company = rng.sample(list(_COMPANY), 3)
    if plan['family_id'] == 'needs-sharing-an-errand':
        actions = rng.sample(['купить хлеб', 'купить чай', 'купить молоко'], 3)
        _need(plan, a, actions)
        _companion(plan, a, company)
        other = rng.sample(['отдохнуть', 'работать', 'позвонить маме'], 3)
        _need(plan, b, other)
        gloss = {'отдохнуть': 'rest', 'работать': 'work', 'позвонить маме': 'call their mother'}[other[0]]
        _support(plan, other[0], gloss, 'The other person has this one different need, not another errand or companion.')
        plan['meaning_plan']['constraints'].append('The second person is not the first person’s companion. The relative in the companion phrase belongs to the named traveller; make this clear without adding another person’s actions.')
    else:
        _companion(plan, a, company)
        # Distinct single additions, all natural with tea. Do not substitute
        # cheese just because it also has an instrumental form.
        ingredients = rng.sample(['с молоком', 'с лимоном', 'с сахаром'], 3)
        requirement = 'a1.language.instrumental-ingredient'
        for person, rotation in ((a, ingredients), (b, ingredients[1:] + ingredients[:1])):
            key = _frame(plan, 'ingredient', 'tea_ingredient', requirement, 'С чем?', r'^с чем\b',
                         'food-accompaniment', 'С plus instrumental names a stated addition to tea, not a person.', rotation)
            _fact(plan, person, 'ingredient', key, requirement, f"С чем {person['name_ru']} хочет чай?",
                  f"What does {person['name_en']} want in their tea?", rotation[0], rotation[1:],
                  f"{person['name_ru']} хочет чай {rotation[0]}.", 'The one addition this person requests for their own tea.',
                  'This is the addition to this person’s tea, not the other person’s preference.', 'Это добавка в чай этого человека.')
        glosses = {'с молоком': 'tea with milk', 'с лимоном': 'tea with lemon', 'с сахаром': 'tea with sugar'}
        for ingredient in ingredients[:2]:
            _support(plan, 'чай ' + ingredient, glosses[ingredient], 'A checked natural tea addition; each gloss matches this phrase only.')
        plan['meaning_plan']['constraints'].append('Each tea has one stated addition; do not mention any other additions or imply one drink belongs to both people. The named second person is the host; the unnamed relative accompanies the visitor.')
    plan['grammar_limits'] += [
        'Do not conflate the person who needs an action with its object or companion.',
        'A companion takes с + instrumental; a drink addition uses that case with a different meaning. Choices for one question all name the same kind of relation.',
        'Age, impersonal cold/hot states and short adjectives are not assessed by these two families.',
    ]


def _aspect(plan, rng, a, b):
    aspect, tense = 'a1.language.verb-aspect', 'a1.language.verb-tense'
    writing = plan['family_id'] == 'aspect-letter-progress'
    for index, person in enumerate((a, b)):
        female = person['gender'] == 'feminine'
        suffix = 'а' if female else ''
        if writing:
            inventory = [f'писал{suffix} письмо, но не закончил{suffix}', f'написал{suffix} письмо до конца', f'ещё не писал{suffix} письмо']
            chosen = inventory[index]
        else:
            inventory = [f'прочитал{suffix} письмо до конца', f'ещё не читал{suffix} письмо', f'читал{suffix} письмо, но не закончил{suffix}']
            chosen = inventory[index]
        alternatives = [v for v in inventory if v != chosen]
        key = _frame(plan, 'activity', 'past_letter_' + person['name_ru'], aspect, 'Что делал?', r'^что\b',
                     'activity-versus-result', 'Explicit completion, explicit non-completion and no prior activity are separate claims.', inventory)
        verb = 'делала' if female else 'делал'
        _fact(plan, person, 'activity', key, aspect, f"Что {person['name_ru']} {verb} вчера?",
              f"What did {person['name_en']} do yesterday?", chosen, alternatives,
              f"{person['name_ru']} вчера {chosen}.", 'The explicitly stated status of yesterday’s letter activity.',
              'The message explicitly states whether the letter was finished. An imperfective verb alone would not settle that.',
              'В сообщении прямо сказано, закончено ли действие. Одного глагола несовершенного вида для этого недостаточно.')
    person = a if writing else b
    # Do not contrast a promised completed writing with merely writing: the
    # completed event entails the activity. Options instead identify distinct
    # outcomes (or distinct activities) within the one announced future plan.
    future = (['напишет письмо до конца', 'прочитает книгу до конца', 'сделает задание'] if writing
              else ['будет читать письмо', 'будет писать письмо', 'будет делать задание'])
    # No completion is inferred from an imperfective future promise.
    key = _frame(plan, 'activity', 'future_letter', tense, 'Что будет делать?', r'^что\b',
                 'future-activity-or-result', 'A stated future activity or promised result, not an event already completed.', future)
    fact = _fact(plan, person, 'activity', key, tense,
          f"Что {person['name_ru']} {'сделает' if writing else 'будет делать'} завтра?",
          f"What will {person['name_en']} do tomorrow?", future[0], future[1:],
          f"{person['name_ru']} завтра {future[0]}.", 'Tomorrow’s explicit plan; completion is promised only by the perfective result.',
          'This is the plan for tomorrow. Only a stated completed result means the whole letter will be finished.',
          'Это план на завтра. Будет читать или будет писать само по себе не обещает закончить всё письмо.')
    fact['option_events'] = [
        {'phrase_ru': phrase, 'action_lemma': action, 'object_lemma': obj,
         'time': 'future', 'completion': 'promised' if writing else 'unspecified'}
        for phrase, action, obj in zip(future, ('писать', 'читать', 'делать') if writing else ('читать', 'писать', 'делать'),
                                      ('письмо', 'книга', 'задание') if writing else ('письмо', 'письмо', 'задание'))
    ]
    plan['meaning_plan']['constraints'].append(
        'There is exactly one announced future plan in this message. Do not mention any of the alternative future tasks. '
        'Every option names a different action/object event; none is simply the activity entailed by another option’s completed result.')
    _support(plan, 'до конца', 'to the end', 'Completion is explicit; the imperfective alone does not mean unfinished.')
    plan['meaning_plan']['constraints'].append(
        'Use yesterday for both past facts and tomorrow for the future fact. The future does not contradict yesterday’s result. '
        + ('The first person resumes their own unfinished letter; the second has a different completed letter.' if writing else 'The two people refer to the same letter; the second person has not read it yet. Reading tomorrow does not promise finishing it.'))
    plan['grammar_limits'] += [
        'Do not equate an imperfective past with non-completion: use the explicit supplied не закончил or ещё не читал boundary.',
        'Keep all past alternatives in the past and all future alternatives in the future; tense must not reveal the answer by itself.',
        'No general prefix rule, participle, passive or untaught perfective/imperfective pair is required.',
    ]


def _origins(plan, rng, a, b):
    origin_req = 'a1.language.genitive-origin'
    if plan['family_id'] == 'origins-errand-sequence':
        rows = rng.sample(list(_PLACES), 3)
        origins = [r[3] for r in rows]
        key = _frame(plan, 'origin', 'place_origin', origin_req, 'Откуда?', r'^откуда\b',
                     'place-origin', 'Из pairs with в and с with на in these checked place phrases.', origins)
        _fact(plan, a, 'origin', key, origin_req, f"Откуда идёт {a['name_ru']}?",
              f"Where is {a['name_en']} coming from?", origins[0], origins[1:],
              f"{a['name_ru']} идёт {origins[0]}.", 'The place already left, not the next stop.',
              'This names the starting point, which is different from either later stop.', 'Это исходное место, а не место назначения.')
        destination_req = 'a1.language.accusative-destination'
        _destination(plan, a, rows[1], [rows[0], rows[2]], requirement=destination_req)
        _destination(plan, a, rows[2], rows[:2], later=True, requirement=destination_req)
        _support(plan, 'сначала', 'first', 'The immediate next stop.')
        _support(plan, 'потом', 'afterwards', 'The later stop.')
    else:
        rows = rng.sample(list(_COMPANY), 3)
        origins = [r[2] for r in rows]
        key = _frame(plan, 'origin', 'person_origin', origin_req, 'Откуда?', r'^откуда\b',
                     'person-origin', 'От plus genitive identifies a person whose place has been left.', origins)
        for person, values in ((a, origins), (b, origins[2:] + origins[:2])):
            _fact(plan, person, 'origin', key, origin_req, f"Откуда идёт {person['name_ru']}?",
                  f"Whose place is {person['name_en']} coming from?", values[0], values[1:],
                  f"{person['name_ru']} идёт {values[0]}.", 'The person already visited, not a companion or next visit.',
                  'От names the person whose place has already been left.', 'От указывает, от кого человек уже ушёл.')
        requirement = 'a1.language.dative-person-destination'
        values = [rows[1][3], rows[0][3], rows[2][3]]
        key = _frame(plan, 'person_destination', 'person_destination', requirement, 'К кому?', r'^к кому\b',
                     'person-destination', 'К plus dative identifies the person being visited next.', values)
        _fact(plan, a, 'person_destination', key, requirement, f"К кому сейчас идёт {a['name_ru']}?",
              f"Who is {a['name_en']} going to visit now?", values[0], values[1:],
              f"{a['name_ru']} сейчас идёт {values[0]}.", 'The first person’s next visit, not the person already visited.',
              'К names the person being visited next; от names the person already left.', 'К — к кому идут; от — от кого уже ушли.')
        glosses = {'от брата': 'from their brother’s place', 'от сестры': 'from their sister’s place',
                   'от друга': 'from a male friend’s place', 'от подруги': 'from a female friend’s place'}
        for origin in (origins[0], origins[2]):
            _support(plan, origin, glosses[origin], 'A checked person-origin; the person visited is not a travelling companion.')
    plan['grammar_limits'] += [
        'Keep origin, destination and current location distinct. Being on a route does not mean arrival.',
        'Use conventional из/в and с/на place pairs; do not infer prepositions from noun endings.',
        'For person visits use от + genitive and к + dative; never replace them with companion с + instrumental.',
    ]


def _connected(plan, rng, a, b):
    requirement = 'a1.language.time-and-reason-clauses'
    name, en = a['name_ru'], a['name_en']
    if plan['family_id'] == 'messages-meeting-change':
        reasons = rng.sample(['потому что ещё работает', 'потому что автобус опаздывает', 'потому что ещё на уроке'], 3)
        key = _frame(plan, 'reason', 'meeting_reason', requirement, 'Почему?', r'^почему\b',
                     'explicit-cause', 'The reason causes the delay; it is not the new meeting time.', reasons)
        _fact(plan, a, 'reason', key, requirement, f'Почему {name} предлагает встретиться позже?',
              f'Why does {en} suggest meeting later?', reasons[0], reasons[1:],
              f'{name} предлагает встретиться позже, {reasons[0]}.', 'The explicit reason for the changed time.',
              'Потому что introduces the reason for the change.', 'Потому что объясняет причину изменения.')
        hours = rng.sample(['в пять', 'в шесть', 'в семь'], 3)
        # Earlier proposed time is unassessed background. New time is later.
        hours.sort(key=lambda x: ['в пять', 'в шесть', 'в семь'].index(x))
        corrected = hours[1:][rng.randrange(2)]
        alternatives = [v for v in hours if v != corrected]
        key = _frame(plan, 'time', 'meeting_time', None, 'Во сколько?', r'^во сколько\b',
                     'stated-time', 'The revised time, not the cancelled time.', [corrected, *alternatives])
        _fact(plan, a, 'time', key, None, f'Во сколько {name} предлагает встретиться теперь?',
              f'What time does {en} now suggest meeting?', corrected, alternatives,
              f'{name} предлагает встретиться {corrected}.', 'The new time; the earlier five o’clock proposal is no longer current.',
              'Use the new proposal after the change.', 'Выберите новое время после изменения.')
        venues = rng.sample([r for r in _PLACES if r[0] in ('парк', 'библиотека', 'театр', 'музей')], 3)
        values = [r[1] for r in venues]
        key = _frame(plan, 'location', 'meeting_location', None, 'Где?', r'^где\b',
                     'meeting-venue', 'The agreed meeting venue, which stays unchanged.', values)
        _fact(plan, a, 'location', key, None, f'Где {name} предлагает встретиться?',
              f'Where does {en} suggest meeting?', values[0], values[1:],
              f'{name} предлагает встретиться {values[0]}.', 'The unchanged meeting place.',
              'Only the time changes; this is still the agreed place.', 'Меняется только время. Место встречи остаётся прежним.')
        _support(plan, 'предлагает встретиться позже', 'suggests meeting later', 'Supports the practical message’s purpose; the reason remains explicit.')
        _support(plan, 'предлагает встретиться', 'suggests meeting', 'Supports a subsequent proposal naming the new time or venue without repeating позже.')
        _support(plan, 'автобус опаздывает', 'the bus is late', 'One possible explicit cause, not a required inferred cause.')
        _support(plan, corrected, {'в шесть': 'at six', 'в семь': 'at seven'}[corrected], 'The clock-time phrase supports the changed plan; no new time inflection is assessed.')
        plan['meaning_plan']['constraints'].append(f'The previous plan was в пять; the final agreed time is {corrected}. Do not change the venue, add another appointment or make the new time earlier than the cancelled time.')
    else:
        # These are different causal/time relationships, not a renamed meeting.
        activities = rng.sample([
            ('урок', 'когда урок закончится', 'потому что сейчас урок'),
            ('работа', 'когда работа закончится', 'потому что сейчас работает'),
            ('встреча', 'когда встреча закончится', 'потому что сейчас на встрече'),
        ], 3)
        times = [r[1] for r in activities]
        key = _frame(plan, 'time', 'call_trigger', requirement, 'Когда?', r'^когда\b',
                     'end-before-call', 'The end of the named activity triggers the later call.', times)
        _fact(plan, a, 'time', key, requirement, f'Когда {name} позвонит?', f'When will {en} call?',
              times[0], times[1:], f'{name} позвонит, {times[0]}.', 'The call happens after this activity ends, not while it is happening.',
              'The activity ends first; the telephone call follows.', 'Сначала заканчивается занятие, потом человек звонит.')
        reasons = [r[2] for r in activities]
        key = _frame(plan, 'reason', 'call_reason', requirement, 'Почему?', r'^почему\b',
                     'explicit-cause', 'The current activity explains why the call waits.', reasons)
        _fact(plan, a, 'reason', key, requirement, f'Почему {name} не звонит сейчас?', f'Why is {en} not calling now?',
              reasons[0], reasons[1:], f'{name} не звонит сейчас, {reasons[0]}.', 'The stated reason for waiting; it must match the call trigger.',
              'The current activity is the reason the person cannot call yet.', 'Сейчас человек занят этим делом и поэтому пока не звонит.')
        actions = rng.sample(['позвонит маме', 'позвонит брату', 'позвонит сестре'], 3)
        key = _frame(plan, 'activity', 'call_action', None, 'Что сделает?', r'^что\b',
                     'planned-call', 'The stated next action, with the correct recipient.', actions)
        _fact(plan, a, 'activity', key, None, f'Что {name} сделает потом?', f'What will {en} do afterwards?',
              actions[0], actions[1:], f'{name} потом {actions[0]}.', 'The stated telephone action and its recipient.',
              'This identifies the person they will telephone after the activity.', 'Здесь сказано, кому человек позвонит потом.')
        trigger_glosses = {'когда урок закончится': 'when the lesson ends', 'когда работа закончится': 'when work ends', 'когда встреча закончится': 'when the meeting ends'}
        _support(plan, times[0], trigger_glosses[times[0]], 'The supplied finite trigger is the end of this one activity.')
        call_glosses = {'позвонит маме': 'will call their mother', 'позвонит брату': 'will call their brother', 'позвонит сестре': 'will call their sister'}
        _support(plan, actions[0], call_glosses[actions[0]], 'The supported telephone recipient is not a separate dative production target.')
        plan['meaning_plan']['constraints'].append('The same activity must be both the current obstacle and the later end-trigger. Do not turn the temporal clause into a cause, or invent an unrelated reason for not calling.')
    plan['grammar_limits'] += [
        'A потому что clause gives a cause; a когда clause locates the following action in time. Do not interchange their meanings.',
        'No inferred motives, conditional hypotheticals or pronouns with two plausible antecedents.',
        'These families do not claim mastery of reported speech, negation paradigms or every coordination pattern in the unit.',
    ]


def _instrumental(plan, rng, a, b):
    activities = rng.sample(list(_ACTIVITIES), 3)
    professions = rng.sample(list(_PROFESSIONS), 3)
    current_future = plan['family_id'] == 'instrumental-now-and-future'
    if current_future:
        values = [r[0] for r in professions]
        key = _frame(plan, 'profession', 'present_profession', None, 'Кто по профессии?', r'^кто\b',
                     'current-profession', 'A current profession without future быть.', values)
        _fact(plan, a, 'profession', key, None, f"Кто {a['name_ru']} по профессии сейчас?",
              f"What is {a['name_en']}’s profession now?", values[0], values[1:],
              f"{a['name_ru']} сейчас {values[0]}.", 'The adult’s actual current profession.',
              'This person has the profession now; the other person is talking about the future.', 'Это профессия сейчас, а не план на будущее.')
        _support(plan, 'кто по профессии?', 'what is their profession?', 'Question support for the current-profession comparison.')
    for person, rows in ((b, activities),) if current_future else ((a, activities), (b, activities[1:] + activities[:1])):
        values = [r[1] for r in rows]
        requirement = 'a1.language.instrumental-activity'
        key = _frame(plan, 'activity', 'instrumental_activity', requirement, 'Чем занимается?', r'^чем\b',
                     'activity-instrumental', 'Заниматься governs the activity in the instrumental, without с.', values)
        _fact(plan, person, 'activity', key, requirement, f"Чем занимается {person['name_ru']}?",
              f"What does {person['name_en']} study or practise?", values[0], values[1:],
              f"{person['name_ru']} занимается {values[0]}.", 'The activity, not a person accompanying them or a job.',
              'The activity follows занимается directly, without с.', 'Название занятия стоит после занимается без предлога с.')
    person = b if current_future else a
    values = [r[1] for r in professions]
    requirement = 'a1.language.instrumental-profession'
    key = _frame(plan, 'profession', 'future_profession', requirement, 'Кем будет?', r'^кем\b',
                 'future-profession-instrumental', 'The supplied future быть frame governs the profession in the instrumental.', values)
    _fact(plan, person, 'profession', key, requirement, f"Кем {person['name_ru']} будет в будущем?",
          f"What profession does {person['name_en']} plan to have in the future?", values[0], values[1:],
          f"{person['name_ru']} говорит: «В будущем я буду {values[0]}».", 'The person’s own stated future profession; this is a plan, not a certified prediction.',
          'Буду + the profession describes this person’s future plan.', 'Буду с названием профессии описывает план на будущее.')
    _support(plan, 'в будущем', 'in the future', 'Frame the person’s profession as their stated plan, not a narrator’s certainty about their future.')
    plan['grammar_limits'] += [
        'An activity after заниматься is instrumental without с; с учителем would be company, not the activity or profession.',
        'Врач and инженер can name a woman’s profession. Do not invent feminine professional nouns or mismatch future быть with grammatical gender.',
        'Do not turn an interest in music or sport into a reason the person must choose a particular profession.',
    ]


_BUILDERS = dict(zip(UNITS, (_motion, _numbers, _needs, _aspect, _origins, _connected, _instrumental)))


def build_plan(unit, seed, mode, recent_families=()):
    """Build one reproducible, detached plan after selecting its problem family."""
    if mode not in ('reading', 'listening'):
        raise ValueError('Choose reading or listening for a language plan.')
    if not isinstance(seed, str) or not seed.strip() or len(seed) > 120:
        raise ValueError('A language plan needs a bounded seed.')
    identity = unit.get('id')
    if identity not in _BUILDERS:
        return None
    if unit.get('level') != 'A1':
        raise ValueError('This language plan only describes its taught A1 scope.')
    family, setting, relation = _family(identity, seed, recent_families)
    rng = random.Random(f'{VERSION}:words:{identity}:{family}:{seed}')
    writer, addressee, a, b = map(_person, rng.sample(list(_PEOPLE), 4))
    medium = 'a personal message' if mode == 'reading' else 'a personal voice message'
    purpose = setting[0].upper() + setting[1:] + '.'
    plan = {
        'version': VERSION, 'construction_contract': 'exact-frames-v1',
        'unit_id': identity, 'mode': mode, 'family_id': family, 'recipe_id': family,
        'setting': setting, 'purpose': purpose, 'medium': medium,
        'family_contract': {
            'relationships_en': relation,
            'seed_changes_en': 'People, conventional lexical frames and applicable event values are sampled after the event family.',
            'implausible_combinations': ['Keep the frozen three facts and their timeline. Do not invent an extra destination, owner, result or cause.'],
            'exposure_identity_en': 'Cosmetic changes to words or names do not make a different family.',
            'question_purpose_en': purpose,
            'alternative_policy_en': 'Three grammatical options express the same question relation; they differ in the reported fact, not grammatical correctness.',
            'selection_en': 'Least encountered family, then least recent; history precedes lexical sampling.',
        },
        'language_requirement_ids': [], 'answer_frames': [], 'contrast_rules': [],
        'checked_forms': [], 'supported_phrases': [],
        'supporting_language': [
            'Use the unit teaching, supplied phrase support and the learner vocabulary as separate sources; a known lemma does not imply knowledge of all its forms.',
            'The checked source frames constrain meaning and government. Connect them naturally rather than concatenating a three-item fact list.',
            'Grammar links identify reading/listening recognition, not independent grammatical production.',
        ],
        'grammar_limits': [],
        'extension_policy': {
            'checked_forms_are_examples': True,
            'lexical_sources': ['unit teaching', 'supplied familiar vocabulary', 'bounded new vocabulary'],
            'requirements': [
                'Keep the chosen assessed facts fixed. New contextual words may enrich the message within the vocabulary allowance, not change its key.',
                'Only add nouns to governed slots using an independently verified complete inflected phrase.',
                'No answer may depend on unsupported unfamiliar vocabulary or a newly invented grammatical prerequisite.',
            ],
        },
        'meaning_plan': {
            'version': 'situation-meaning-v2', 'family_id': family, 'medium_en': medium,
            'writer': writer, 'addressee': addressee, 'participants': [a, b],
            'speaker_relationship_en': 'One friend relays directly known news about the named people to another friend.',
            'context_en': setting, 'purpose_en': purpose, 'timeline_en': relation, 'facts': [],
            'constraints': [
                'Make one useful message with these three facts. Do not add a fourth assessed fact or recycle a complete stock passage.',
                'Writer and addressee are separate from the named participants; make changes of subject explicit.',
                'Use the supplied question frames without ambiguous pronouns. One source sentence per sentence entry.',
                'A source-frame example is a linguistic reference, not an instruction to repeat that sentence mechanically.',
            ],
        },
    }
    _BUILDERS[identity](plan, rng, a, b)
    used_people = {fact['subject_name'] for fact in plan['meaning_plan']['facts']}
    plan['meaning_plan']['participants'] = [p for p in (a, b) if p['name_ru'] in used_people]
    taught = {q.get('requirement_id') for q in unit.get('questions', [])}
    if not set(plan['language_requirement_ids']) <= taught:
        raise ValueError('The unit does not teach all selected language requirements.')
    validate_plan(plan)
    return deepcopy(plan)


def validate_plan(plan):
    """Reject malformed authored relationships before asking a model for prose.

The inventories below are deliberately checked lexical paradigms. General
morphology is not used to guess conventional prepositions or pedagogical scope.
"""
    if plan.get('unit_id') not in UNITS or plan.get('construction_contract') != 'exact-frames-v1':
        raise ValueError('Unknown relational language-plan contract.')
    facts = plan.get('meaning_plan', {}).get('facts', [])
    if len(facts) != 3 or [f['id'] for f in facts] != ['f1', 'f2', 'f3']:
        raise ValueError('A relational plan needs exactly three frozen facts.')
    requirements = plan['language_requirement_ids']
    if not 1 <= len(requirements) <= 2:
        raise ValueError('A family assesses one or two taught constructions.')
    if {f['requirement_id'] for f in facts if f['requirement_id']} != set(requirements):
        raise ValueError('Every selected language requirement needs a frozen assessed fact.')
    participants = {p['name_ru'] for p in plan['meaning_plan']['participants']}
    outsider = {plan['meaning_plan'][role]['name_ru'] for role in ('writer', 'addressee')}
    if participants & outsider:
        raise ValueError('Writer, addressee and assessed participants must be distinct.')
    for fact in facts:
        values = [fact['value_ru'], *fact['alternative_frames']]
        if len(values) != 3 or len(set(values)) != 3:
            raise ValueError('Each fact needs three distinct grammatical alternatives.')
        frames = [f for f in plan['answer_frames'] if f['role'] == fact['role']
                  and f['form_key'] == fact['form_key'] and f['requirement_id'] == fact['requirement_id']]
        if len(frames) != 1 or not re.search(frames[0]['question_pattern_ru'], fact['question_frame_ru'].lower().replace('ё', 'е')):
            raise ValueError('The question must fit its authored semantic frame.')
        known = {row[fact['form_key']] for row in plan['checked_forms'] if fact['form_key'] in row}
        if not set(values) <= known:
            raise ValueError('Every answer must occur in its checked phrase inventory.')
        if fact['subject_name'] not in participants:
            raise ValueError('The fact needs an identified participant.')
        if not fact['question_en'] or not fact['checked_source_frame_ru'] or not all(fact['feedback'].values()):
            raise ValueError('Facts need a faithful question, source-frame reference and contextual feedback.')
        key = fact['form_key']
        if key.startswith('quantity_'):
            lemma = key.removeprefix('quantity_')
            if not set(values) <= set(dict(_COUNTS)[lemma]):
                raise ValueError('Counted forms must follow the checked noun paradigm.')
        elif key == 'transport' and not set(values) <= set(_TRANSPORT):
            raise ValueError('Transport needs a conventional на + prepositional phrase.')
        elif key in ('companion', 'person_origin', 'person_destination'):
            index = {'companion': 1, 'person_origin': 2, 'person_destination': 3}[key]
            if not set(values) <= {row[index] for row in _COMPANY}:
                raise ValueError('A person relation has the wrong case or preposition.')
        elif key in ('destination', 'place_origin', 'meeting_location'):
            index = {'destination': 2, 'place_origin': 3, 'meeting_location': 1}[key]
            if not set(values) <= {row[index] for row in _PLACES}:
                raise ValueError('A place relation has the wrong conventional frame.')
        elif key == 'instrumental_activity' and not set(values) <= {r[1] for r in _ACTIVITIES}:
            raise ValueError('Activities take their checked instrumental without с.')
        elif key in ('present_profession', 'future_profession'):
            index = 0 if key == 'present_profession' else 1
            if not set(values) <= {r[index] for r in _PROFESSIONS}:
                raise ValueError('The current and future profession frames differ.')
        _validate_finite_frames(plan, fact, values)
    _validate_event(plan)
    if len(plan['supported_phrases']) > 5:
        raise ValueError('A plan cannot add more than five supported phrases.')


def _validate_finite_frames(plan, fact, values):
    person = next(p for p in plan['meaning_plan']['participants'] if p['name_ru'] == fact['subject_name'])
    key, source, value = fact['form_key'], fact['checked_source_frame_ru'], fact['value_ru']
    finite = {
        'motion_activity': {'ходит пешком', 'идёт пешком', 'ездит на автобусе', 'ездит на машине', 'едет на автобусе', 'едет на машине'},
        'needed_action': {'купить хлеб', 'купить чай', 'купить молоко', 'отдохнуть', 'работать', 'позвонить маме'},
        'lesson_ordinal': {'первый урок', 'второй урок', 'третий урок'},
        'tea_ingredient': {'с молоком', 'с лимоном', 'с сахаром'},
        'future_letter': {'напишет письмо до конца', 'прочитает книгу до конца', 'сделает задание', 'будет читать письмо', 'будет писать письмо', 'будет делать задание'},
        'meeting_time': {'в пять', 'в шесть', 'в семь'},
        'meeting_reason': {'потому что ещё работает', 'потому что автобус опаздывает', 'потому что ещё на уроке'},
        'call_trigger': {'когда урок закончится', 'когда работа закончится', 'когда встреча закончится'},
        'call_reason': {'потому что сейчас урок', 'потому что сейчас работает', 'потому что сейчас на встрече'},
        'call_action': {'позвонит маме', 'позвонит брату', 'позвонит сестре'},
    }
    if key.startswith('past_letter_'):
        suffix = 'а' if person['gender'] == 'feminine' else ''
        allowed = {f'писал{suffix} письмо, но не закончил{suffix}', f'написал{suffix} письмо до конца', f'ещё не писал{suffix} письмо',
                   f'прочитал{suffix} письмо до конца', f'ещё не читал{suffix} письмо', f'читал{suffix} письмо, но не закончил{suffix}'}
    else:
        allowed = finite.get(key)
    if allowed is not None and not set(values) <= allowed:
        raise ValueError('The finite or lexical frame does not match its checked meaning and agreement.')
    if value not in source:
        raise ValueError('The source-frame reference must express the frozen value.')
    if key == 'needed_action' and source != f"{person['dative_ru']} нужно {value}.":
        raise ValueError('A need is assigned to the person in the dative, not the nominative.')
    if key.startswith('quantity_') and source != f"У {person['genitive_ru']} {value}.":
        raise ValueError('The counting frame uses possession, not an unlicensed accusative object.')
    if key == 'instrumental_activity' and source != f"{person['name_ru']} занимается {value}.":
        raise ValueError('The activity follows занимается without с.')
    if key == 'future_profession' and source != f"{person['name_ru']} говорит: «В будущем я буду {value}».":
        raise ValueError('The future profession must be the person’s stated plan.')
    if key.startswith('past_letter_') and source != f"{person['name_ru']} вчера {value}.":
        raise ValueError('Past activity and its explicit result must keep the same named actor.')


def _validate_event(plan):
    facts = plan['meaning_plan']['facts']
    family = plan['family_id']
    if family.startswith('aspect-'):
        future = facts[2]
        events = future.get('option_events', [])
        if len(events) != 3 or len({(row['action_lemma'], row['object_lemma']) for row in events}) != 3:
            raise ValueError('Future options must express distinct events, not a completed result and its entailed activity.')
        if [row['phrase_ru'] for row in events] != [future['value_ru'], *future['alternative_frames']]:
            raise ValueError('The future event claims must match the actual options.')
        expected = 'promised' if family == 'aspect-letter-progress' else 'unspecified'
        if any(row['time'] != 'future' or row['completion'] != expected for row in events):
            raise ValueError('Future alternatives must share their temporal and completion scope.')
    if family == 'messages-call-after-activity':
        trigger, reason, _ = facts
        matching = {
            'когда урок закончится': 'потому что сейчас урок',
            'когда работа закончится': 'потому что сейчас работает',
            'когда встреча закончится': 'потому что сейчас на встрече',
        }
        if matching.get(trigger['value_ru']) != reason['value_ru']:
            raise ValueError('The call trigger and the reason for waiting must name the same activity.')
    elif family == 'origins-errand-sequence':
        origin, next_stop, later_stop = facts
        identities = {r[3]: r[0] for r in _PLACES}
        destinations = {r[2]: r[0] for r in _PLACES}
        places = [identities[origin['value_ru']], destinations[next_stop['value_ru']], destinations[later_stop['value_ru']]]
        if len(set(places)) != 3:
            raise ValueError('The route must separate the place left and its two later stops.')
    elif family == 'aspect-letter-progress':
        if 'но не закончил' not in facts[0]['value_ru'] or not facts[1]['value_ru'].startswith(('написал', 'написала')):
            raise ValueError('The letters must have explicitly different completion states.')
        if facts[2]['subject_name'] != facts[0]['subject_name'] or facts[2]['value_ru'] != 'напишет письмо до конца':
            raise ValueError('The unfinished letter’s writer promises tomorrow’s result.')
    elif family == 'aspect-reading-handover':
        if not facts[0]['value_ru'].startswith(('прочитал', 'прочитала')) or not facts[1]['value_ru'].startswith('ещё не читал'):
            raise ValueError('The first person has finished reading; the next reader has not read it yet.')
        if facts[2]['subject_name'] != facts[1]['subject_name'] or facts[2]['value_ru'] != 'будет читать письмо':
            raise ValueError('The next reader promises reading, without a promised completed result.')
    elif family == 'company-tea-preferences' and facts[1]['value_ru'] == facts[2]['value_ru']:
        raise ValueError('The two tea requests must retain their different additions.')
    elif family == 'messages-meeting-change' and facts[1]['value_ru'] == 'в пять':
        raise ValueError('The revised meeting time must follow the cancelled time.')
