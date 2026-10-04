"""Construction-led inputs for new situations, not a bank of finished stories.

The plan fixes what a learner should understand before a model chooses its
wording. Only these specified teaching scopes have plans here. Other units return
None; sharing an A1 label is not sufficient to infer their prerequisites.
"""
from copy import deepcopy
import random

VERSION = 'curriculum-language-plan-v5'

LOCATION = 'location-destination-v1'
CALENDAR = 'calendar-and-duration-v1'
TOPICS = 'talking-about-topics-v1'

_REQUIREMENTS = {
    LOCATION: ('a1.language.prepositional-location', 'a1.language.accusative-destination'),
    CALENDAR: ('a1.language.genitive-calendar-month', 'a1.language.accusative-duration'),
    TOPICS: ('a1.language.prepositional-topic',),
}

# IDs describe the communicative problem and survive cosmetic wording changes.
# Family choice precedes all names, places, dates and other lexical sampling.
_FAMILIES = {
    LOCATION: (
        {
            'id': 'location-find-before-moving',
            'setting': 'finding friends before one leaves for a next stop',
            'purpose': 'Help the addressee find either friend now and know where the first friend goes next.',
            'relationships': 'Two separate current locations; the first person has one next destination.',
            'seed_changes': 'Names and three distinct conventional places; which friend is moving.',
            'avoid': 'Do not make the next stop either current location, add a return journey or move the second friend.',
        },
        {
            'id': 'location-split-outing',
            'setting': 'friends going separate ways after spending time together',
            'purpose': 'Help the addressee decide which friend to accompany: say where both friends are now and where each goes next.',
            'relationships': 'One shared current location; two people go to different next destinations.',
            'seed_changes': 'Names, the shared starting place and two distinct destinations.',
            'avoid': 'Do not give either person a second stop or imply that the friends travel together to both destinations.',
        },
    ),
    CALENDAR: (
        {
            'id': 'calendar-completed-stay',
            'setting': 'news about a friend’s completed stay',
            'purpose': 'Help the addressee recall a friend’s visit: where the friend stayed, for how long, and its start date or another person who stayed there.',
            'relationships': 'One completed stay, its city and elapsed duration; reading adds its start date, listening adds a companion.',
            'seed_changes': 'Names, city and a plausible length of stay; written start date only in reading.',
            'avoid': 'Do not contrast overlapping geographic levels, add a second stay or calculate a duration from dates.',
            'duration_context': 'temporary-stay',
        },
        {
            'id': 'calendar-reading-period',
            'setting': 'friends recalling time spent reading a book',
            'purpose': 'Give the addressee the details of a reading activity before a book discussion: how long the friend read, where, and when reading began or who else read there.',
            'relationships': 'One book-reading activity, its venue and elapsed period; reading adds its start date, listening adds another reader.',
            'seed_changes': 'Names, a suitable reading venue and a plausible reading period; written start date only in reading.',
            'avoid': 'Use читал/читала, not прочитал/прочитала: no claim that the book was finished. Day/week may include breaks, not uninterrupted reading.',
            'duration_context': 'reading-period',
        },
    ),
    TOPICS: (
        {
            'id': 'topics-join-conversation',
            'setting': 'choosing a conversation to join',
            'purpose': 'Help the addressee join friends by naming their shared venue and the different subject each friend is discussing.',
            'relationships': 'Two speakers, one person-topic and one thing-topic, at a shared venue.',
            'seed_changes': 'Names, the person and thing being discussed, and a suitable shared venue.',
            'avoid': 'Each speaker has one topic; do not change subjects or confuse a person spoken about with the speaker.',
        },
        {
            'id': 'topics-thought-and-speech',
            'setting': 'a friend sharing a thought during a conversation',
            'purpose': 'Help the addressee respond to a friend: identify the person mentioned in conversation, the thought that the friend explicitly shares, and the friend’s current place.',
            'relationships': 'One friend mentions a person in conversation, explicitly shares a thought about a thing, and has one current location.',
            'seed_changes': 'The friend’s name, spoken person-topic, thought topic and current venue.',
            'avoid': 'Use the supplied direct-disclosure frame for the friend’s thought. Do not infer a thought from behaviour, expand this into a dialogue, or add another topic.',
        },
    ),
}


def _select_family(identity, seed, recent_families):
    """Prefer the least seen problem, then the one encountered longest ago.

History is newest first. Unknown or retired IDs cannot suppress a current
family. A separate seed chooses tied families before lexical sampling begins.
"""
    families = _FAMILIES[identity]
    known = {family['id'] for family in families}
    history = [value for value in recent_families if isinstance(value, str) and value in known]
    counts = {value: history.count(value) for value in known}
    def rank(family):
        value = family['id']
        return counts[value], -(history.index(value) if value in history else len(history))
    best = min(map(rank, families))
    candidates = [family for family in families if rank(family) == best]
    return random.Random(VERSION + ':family:' + identity + ':' + seed).choice(candidates)

# These are construction examples, not a permanent vocabulary whitelist.
# Names, events and prose remain generated. The lexical place reference records
# conventional prepositions, which cannot be inferred from noun morphology.
# Keep source lemmas with full governed phrases; bare endings are not meanings.
_PLACES = (
    {'lemma': 'школа', 'location': 'в школе', 'destination': 'в школу'},
    {'lemma': 'почта', 'location': 'на почте', 'destination': 'на почту'},
    {'lemma': 'парк', 'location': 'в парке', 'destination': 'в парк'},
    {'lemma': 'магазин', 'location': 'в магазине', 'destination': 'в магазин'},
    {'lemma': 'библиотека', 'location': 'в библиотеке', 'destination': 'в библиотеку'},
    {'lemma': 'кафе', 'location': 'в кафе', 'destination': 'в кафе'},
    {'lemma': 'банк', 'location': 'в банке', 'destination': 'в банк'},
    {'lemma': 'музей', 'location': 'в музее', 'destination': 'в музей'},
    {'lemma': 'театр', 'location': 'в театре', 'destination': 'в театр'},
    {'lemma': 'ресторан', 'location': 'в ресторане', 'destination': 'в ресторан'},
    {'lemma': 'аптека', 'location': 'в аптеке', 'destination': 'в аптеку'},
    {'lemma': 'больница', 'location': 'в больнице', 'destination': 'в больницу'},
    {'lemma': 'гостиница', 'location': 'в гостинице', 'destination': 'в гостиницу'},
    {'lemma': 'университет', 'location': 'в университете', 'destination': 'в университет'},
    {'lemma': 'вокзал', 'location': 'на вокзале', 'destination': 'на вокзал'},
    {'lemma': 'улица', 'location': 'на улице', 'destination': 'на улицу'},
    {'lemma': 'работа', 'location': 'на работе', 'destination': 'на работу'},
    {'lemma': 'остановка', 'location': 'на остановке', 'destination': 'на остановку'},
)
_DURATIONS = (
    {'lemma': 'минута', 'duration': 'одну минуту'},
    {'lemma': 'час', 'duration': 'час'},
    {'lemma': 'день', 'duration': 'день'},
    {'lemma': 'неделя', 'duration': 'неделю'},
    {'lemma': 'месяц', 'duration': 'месяц'},
)
_DURATION_CONTEXTS = {
    'temporary-stay': {
        'meaning_en': 'A temporary stay with someone or away from home; each alternative can reasonably describe this same stay.',
        'phrase_examples': ['день', 'неделю', 'месяц'],
    },
    'reading-period': {
        'meaning_en': 'Time spent reading a book, without claiming that the book was finished.',
        'phrase_examples': ['час', 'день', 'неделю'],
    },
}
_MONTHS = (
    ('январь', 'января'), ('февраль', 'февраля'), ('март', 'марта'),
    ('апрель', 'апреля'), ('май', 'мая'), ('июнь', 'июня'),
    ('июль', 'июля'), ('август', 'августа'), ('сентябрь', 'сентября'),
    ('октябрь', 'октября'), ('ноябрь', 'ноября'), ('декабрь', 'декабря'),
)
_ORDINALS = (
    'первого', 'второго', 'третьего', 'четвёртого', 'пятого', 'шестого',
    'седьмого', 'восьмого', 'девятого', 'десятого', 'одиннадцатого',
    'двенадцатого', 'тринадцатого', 'четырнадцатого', 'пятнадцатого',
    'шестнадцатого', 'семнадцатого', 'восемнадцатого', 'девятнадцатого',
    'двадцатого', 'двадцать первого', 'двадцать второго', 'двадцать третьего',
    'двадцать четвёртого', 'двадцать пятого', 'двадцать шестого',
    'двадцать седьмого', 'двадцать восьмого',
)
_TOPIC_FORMS = (
    {'lemma': 'мама', 'referent_kind': 'person', 'topic': 'о маме'},
    {'lemma': 'друг', 'referent_kind': 'person', 'topic': 'о друге'},
    {'lemma': 'Анна', 'referent_kind': 'person', 'topic': 'об Анне'},
    {'lemma': 'работа', 'referent_kind': 'thing', 'topic': 'о работе'},
    {'lemma': 'семья', 'referent_kind': 'thing', 'topic': 'о семье'},
    {'lemma': 'музыка', 'referent_kind': 'thing', 'topic': 'о музыке'},
    {'lemma': 'книга', 'referent_kind': 'thing', 'topic': 'о книге'},
    {'lemma': 'спорт', 'referent_kind': 'thing', 'topic': 'о спорте'},
    {'lemma': 'отдых', 'referent_kind': 'thing', 'topic': 'об отдыхе'},
)

# Nominative names suffice for the frozen relationships and questions. Do not
# invent a dative/addressee construction merely to fit a proper name into prose.
_PEOPLE = (
    {'name_ru': 'Олег', 'name_en': 'Oleg', 'gender': 'masculine'},
    {'name_ru': 'Дима', 'name_en': 'Dima', 'gender': 'masculine'},
    {'name_ru': 'Иван', 'name_en': 'Ivan', 'gender': 'masculine'},
    {'name_ru': 'Миша', 'name_en': 'Misha', 'gender': 'masculine'},
    {'name_ru': 'Анна', 'name_en': 'Anna', 'gender': 'feminine'},
    {'name_ru': 'Нина', 'name_en': 'Nina', 'gender': 'feminine'},
    {'name_ru': 'Лена', 'name_en': 'Lena', 'gender': 'feminine'},
    {'name_ru': 'Оля', 'name_en': 'Olya', 'gender': 'feminine'},
    {'name_ru': 'Вера', 'name_en': 'Vera', 'gender': 'feminine'},
)
# One geographic level only: a hotel can be in Moscow, so hotel/city options
# would not be mutually exclusive. These names use the same taught case frames.
_STAY_PLACES = (
    {'lemma': 'Москва', 'location': 'в Москве', 'destination': 'в Москву'},
    {'lemma': 'Петербург', 'location': 'в Петербурге', 'destination': 'в Петербург'},
    {'lemma': 'Тула', 'location': 'в Туле', 'destination': 'в Тулу'},
    {'lemma': 'Самара', 'location': 'в Самаре', 'destination': 'в Самару'},
    {'lemma': 'Омск', 'location': 'в Омске', 'destination': 'в Омск'},
    {'lemma': 'Минск', 'location': 'в Минске', 'destination': 'в Минск'},
)


def _fact(identity, role, subject, value, question, relation, alternatives):
    return {
        'id': identity, 'role': role, 'subject_name': subject['name_ru'],
        'subject_en': subject['name_en'], 'value_ru': value,
        'question_frame_ru': question, 'relation_en': relation,
        'alternative_frames': alternatives,
    }


def _build_meaning_plan(plan, rng):
    """Choose the people and event before prose; a writer cannot change the key.

Three facts are enough for a short purposeful message. The distractors are
grammatically possible answers about that event, not wrong Russian or random
objects. Their pools are lexical references that can grow, not finished stories.
"""
    writer, addressee, first, second = rng.sample(_PEOPLE, 4)
    meaning = {
        'version': 'situation-meaning-v2', 'family_id': plan['family_id'],
        'medium_en': plan['medium'],
        'speaker_relationship_en': 'The writer reports known information about friends to another friend.',
        'writer': writer, 'addressee': addressee,
        'participants': [first, second],
        'context_en': plan['setting'], 'purpose_en': plan['purpose'],
        'timeline_en': '', 'facts': [],
        'constraints': [
            'Report these three facts about the named people; do not add other assessable events.',
            'The writer and addressee are not the people whose actions are being reported.',
            'Identify each subject within the source span; use clear pronouns to connect related clauses and avoid repeated names.',
            'Use names in questions, not ambiguous я, мы or она. A who-question must not contain its answer name.',
            *plan['family_contract']['implausible_combinations'],
        ],
    }
    if plan['unit_id'] == LOCATION:
        here, next_stop, other_here = rng.sample(plan['checked_forms'], 3)
        locations = [row['location'] for row in (here, next_stop, other_here)]
        destinations = [row['destination'] for row in (here, next_stop, other_here)]
        if plan['family_id'] == 'location-split-outing':
            meaning['timeline_en'] = (
                f"Now {first['name_en']} and {second['name_en']} are together at one place. "
                'Then each goes to a different next stop. There is no second leg of either route.')
            meaning['facts'] = [
                _fact('f1', 'location', first, here['location'],
                      f"Где сейчас {first['name_ru']} и {second['name_ru']}?",
                      'The shared current place before the friends go separate ways.', locations[1:]),
                _fact('f2', 'destination', first, next_stop['destination'],
                      f"Куда потом идёт {first['name_ru']}?", 'The first person’s only next destination.',
                      [destinations[0], destinations[2]]),
                _fact('f3', 'destination', second, other_here['destination'],
                      f"Куда потом идёт {second['name_ru']}?", 'The second person’s different next destination.',
                      destinations[:2]),
            ]
        else:
            meaning['timeline_en'] = (
                f"Now {first['name_en']} is at one place and {second['name_en']} is at another. "
                f"Then {first['name_en']} goes to exactly one next stop. No subsequent stop or shared movement is specified.")
            meaning['facts'] = [
                _fact('f1', 'location', first, here['location'],
                      f"Где сейчас {first['name_ru']}?", 'Current location, before any movement.', locations[1:]),
                _fact('f2', 'destination', first, next_stop['destination'],
                      f"Куда потом идёт {first['name_ru']}?", 'The only next destination.', [destinations[0], destinations[2]]),
                _fact('f3', 'location', second, other_here['location'],
                      f"Где сейчас {second['name_ru']}?", 'The other person’s current location.', locations[:2]),
            ]
    elif plan['unit_id'] == CALENDAR:
        reading_activity = plan['family_id'] == 'calendar-reading-period'
        venues = ([row for row in _PLACES if row['lemma'] in ('библиотека', 'кафе', 'парк')]
                  if reading_activity else list(_STAY_PLACES))
        duration = rng.choice(plan['duration_context']['phrase_examples'])
        if reading_activity and duration in ('день', 'неделю'):
            # Extended reading belongs indoors; a written winter date should
            # not accidentally imply an entire day reading in a park.
            indoors = [row for row in venues if row['lemma'] in (
                ('библиотека',) if duration == 'неделю' else ('библиотека', 'кафе'))]
            venue = rng.choice(indoors)
            venue_options = rng.sample([row for row in venues if row != venue], 2)
        else:
            venue, *venue_options = rng.sample(venues, 3)
        meaning['venue_family'] = 'reading-venue' if reading_activity else 'named-city'
        durations = [v for v in plan['duration_context']['phrase_examples'] if v != duration]
        female = first['gender'] == 'feminine'
        past_verb = ('читала' if female else 'читал') if reading_activity else ('была' if female else 'был')
        activity = 'reading activity' if reading_activity else 'stay'
        meaning['timeline_en'] = (
            f"One {activity} by {first['name_en']}. State its venue and elapsed duration. "
            'Do not add a later activity or another length of time.')
        if reading_activity:
            meaning['timeline_en'] += ' Reading may include breaks; no completion of the book or finish date is stated.'
        else:
            meaning['timeline_en'] += ' This is a completed stay; do not add a departure date.'
        meaning['facts'] = [
            _fact('f1', 'duration', first, duration,
                  f"Как долго {first['name_ru']} {past_verb} книгу?" if reading_activity else f"Как долго {first['name_ru']} там {past_verb}?",
                  f'The elapsed period of this one {activity}.', durations),
            _fact('f2', 'location', first, venue['location'],
                  f"Где {first['name_ru']} {past_verb}?", f'The venue of the same {activity}.',
                  [row['location'] for row in venue_options]),
        ]
        if plan['mode'] == 'reading':
            dates = [row['date_written'] for row in plan['checked_forms'] if 'date_written' in row]
            started = ('начала читать' if female else 'начал читать') if reading_activity else ('приехала' if female else 'приехал')
            meaning['facts'].append(_fact('f3', 'date', first, dates[0],
                f"Когда {first['name_ru']} {started}?", f'The start date of this same {activity}.', dates[1:]))
            meaning['participants'] = [first]
            meaning['timeline_en'] += f' The written date is the start of that {activity}, not a second event.'
        else:
            meaning['facts'].append(_fact('f3', 'person', second, second['name_ru'],
                'Кто ещё там читал?' if reading_activity else 'Кто ещё там был?',
                'The one other reader at that venue.' if reading_activity else 'The one companion who also stayed at that venue.',
                [writer['name_ru'], addressee['name_ru']]))
            meaning['timeline_en'] += (
                f" {second['name_en']} also {'read' if reading_activity else 'stayed'} there, but has no separate duration. "
                'No calendar date is stated or assessed.')
        # Supporting venue comprehension does not claim a new language target.
        plan['extension_policy']['place_frames'] = venues
    else:
        people_topics = [row for row in plan['checked_forms'] if row['referent_kind'] == 'person']
        # Avoid turning a topic about a third person into an accidental self-reference.
        person_topic = rng.choice([row for row in people_topics
                                   if row['lemma'] not in {p['name_ru'] for p in (writer, addressee, first, second)}])
        thing_topics = [row for row in plan['checked_forms'] if row['referent_kind'] == 'thing']
        thing_topic = rng.choice(thing_topics)
        conversation_places = [row for row in _PLACES if row['lemma'] in ('кафе', 'парк', 'библиотека')]
        venue, *venue_options = rng.sample(conversation_places, 3)
        thought_and_speech = plan['family_id'] == 'topics-thought-and-speech'
        if thought_and_speech:
            second = first
            meaning['participants'] = [first]
        topic_verb = 'думает' if thought_and_speech else 'говорит'
        meaning['timeline_en'] = (
            f"One present conversation at the same venue. {first['name_en']} talks about one person; "
            f"{second['name_en']} talks about one subject. Each speaker has exactly one topic, with no topic changes.")
        meaning['facts'] = [
            _fact('f1', 'topic_person', first, person_topic['topic'],
                  f"О ком говорит {first['name_ru']}?",
                  'The person mentioned as a conversation subject.' if thought_and_speech else 'This speaker’s sole topic, a person.',
                  [row['topic'] for row in people_topics if row != person_topic]),
            _fact('f2', 'topic_thing', second, thing_topic['topic'],
                  f"О чём {topic_verb} {second['name_ru']}?",
                  'The thought the friend explicitly discloses.' if thought_and_speech else 'This other speaker’s sole topic, a thing or subject.',
                  rng.sample([row['topic'] for row in thing_topics if row != thing_topic], 2)),
            _fact('f3', 'location', first, venue['location'],
                  f"Где сейчас {first['name_ru']}?", 'The friend’s current place.' if thought_and_speech else 'The place where both people are having this conversation.',
                  [row['location'] for row in venue_options]),
        ]
        if thought_and_speech:
            meaning['timeline_en'] = (
                f"{first['name_en']} is now at one place, mentions one person in conversation and explicitly shares a thought about one thing. "
                'The friend tells the writer their thought in the supplied direct-disclosure frame. '
                'The thought is known from that statement, not inferred by the writer. '
                'The disclosure is evidence for the thought, not a fourth assessed fact.')
        plan['extension_policy']['place_frames'] = conversation_places
    _add_checked_feedback(plan, meaning)
    return meaning


def _add_checked_feedback(plan, meaning):
    """Feedback follows the frozen event, including reading and reported thought."""
    activity = plan['family_id'] == 'calendar-reading-period'
    calendar = plan['unit_id'] == CALENDAR
    people = {person['name_ru']: person for person in meaning['participants']}
    for fact in meaning['facts']:
        name, english, role = fact['subject_name'], fact['subject_en'], fact['role']
        female = people[name]['gender'] == 'feminine'
        past = ('читала' if female else 'читал') if activity else ('была' if female else 'был')
        started = ('начала читать' if female else 'начал читать') if activity else ('приехала' if female else 'приехал')
        thought = role == 'topic_thing' and plan['family_id'] == 'topics-thought-and-speech'
        details = {
            'location': (f'where {english} is now', f'где сейчас {name}',
                         'This gives the current location.', 'Здесь сказано, где человек сейчас.'),
            'destination': (f'where {english} goes next', f'куда потом идёт {name}',
                            'This gives the next stop.', 'Здесь сказано, куда человек идёт потом.'),
            'duration': (f'how long {english} read' if activity else f'how long {english} stayed',
                         f'сколько времени {name} {past}',
                         'This gives the period spent reading; it does not say the book was finished.' if activity else 'This tells how long the stay lasted.',
                         'Здесь сказано, сколько времени человек читал.' if activity else 'Здесь сказано, сколько времени это длилось.'),
            'date': (f'the day when {english} began reading' if activity else f'the day when {english} arrived',
                     f'какого числа {name} {started}',
                     'This gives the start date of reading.' if activity else 'This gives the arrival date.',
                     'Здесь названа дата начала чтения.' if activity else 'Здесь названа дата приезда.'),
            'topic_person': (f'who {english} is talking about', f'о ком говорит {name}',
                             'This tells who the speaker is talking about.', 'Здесь сказано, о ком говорит человек.'),
            'topic_thing': (f'what {english} is thinking about' if thought else f'what {english} is talking about',
                            f"о чём {'думает' if thought else 'говорит'} {name}",
                            'This reports the thought the friend has shared.' if thought else 'This tells what the speaker is talking about.',
                            'Здесь сказано, о чём человек думает.' if thought else 'Здесь сказано, о чём говорит человек.'),
            'person': ('the other reader’s name' if activity else 'the other person’s name',
                       'имя ещё одного человека',
                       'This names the other person who read there.' if activity else 'This names the other person who stayed there.',
                       'Здесь назван ещё один человек, который там читал.' if activity else 'Здесь назван ещё один человек, который там был.'),
        }
        values = details[role]
        if role == 'location' and calendar:
            values = (f"where {english} {'read' if activity else 'stayed'}", f'где {name} {past}',
                      'This gives the place of reading.' if activity else 'This gives the place of the stay.',
                      'Здесь сказано, где человек читал.' if activity else 'Здесь сказано, где человек был.')
        fact['feedback'] = dict(zip(('detail_en', 'detail_ru', 'caption_en', 'caption_ru'), values))

def _frame(role, question, requirement, form_key):
    return {'role': role, 'question_ru': question,
            'requirement_id': requirement, 'form_key': form_key}


def _rule(requirement, rule, form_key, meaning):
    return {'requirement_id': requirement, 'rule': rule,
            'form_key': form_key, 'meaning_en': meaning}


def build_language_plan(unit, seed, mode, *, recent_families=()):
    """Return a detached, reproducible plan for a supported taught unit.

Mode changes are deliberate: written dates are taught in the calendar unit;
recognising all spoken ordinal dates is not. Listening therefore uses its
duration target only. No plan is a new access gate or a proficiency judgement.
"""
    if mode not in ('reading', 'listening'):
        raise ValueError('Choose reading or listening for a language plan.')
    if not isinstance(seed, str) or not seed.strip() or len(seed) > 120:
        raise ValueError('A language plan needs a bounded seed.')
    identity = unit.get('id')
    if identity == 'location-destination-v2':
        identity = LOCATION
    if identity not in _REQUIREMENTS:
        from services.curriculum_situation_plans_personal import build_plan as personal
        from services.curriculum_situation_plans_relations import build_plan as relations
        return personal(unit, seed, mode, recent_families) or relations(unit, seed, mode, recent_families)
    if unit.get('level') != 'A1':
        raise ValueError('This language plan only describes its taught A1 scope.')
    selected = list(_REQUIREMENTS[identity])
    if identity == CALENDAR and mode == 'listening':
        selected = ['a1.language.accusative-duration']
    taught = {question.get('requirement_id') for question in unit.get('questions', [])}
    if not set(selected) <= taught:
        raise ValueError('The unit does not teach all selected language requirements.')
    family = _select_family(identity, seed, recent_families)
    rng = random.Random(VERSION + ':words:' + identity + ':' + family['id'] + ':' + seed)
    plan = {
        'version': VERSION, 'unit_id': identity, 'mode': mode,
        'family_id': family['id'], 'recipe_id': family['id'],
        'setting': family['setting'], 'purpose': family['purpose'],
        'medium': 'a personal message' if mode == 'reading' else 'a personal voice message',
        'family_contract': {
            'relationships_en': family['relationships'],
            'seed_changes_en': family['seed_changes'],
            'implausible_combinations': [family['avoid']],
            'exposure_identity_en': 'The family remains the same after changes to names, nouns, dates or wording.',
            'question_purpose_en': family['purpose'],
            'alternative_policy_en': 'Each answer has two grammatical alternatives within the same meaning relation and event scale.',
            'selection_en': 'Least encountered family, then least recent; history precedes lexical sampling.',
        },
        'supported_phrases': [],
        'language_requirement_ids': selected,
        'supporting_language': [
            'Use short clauses and familiar connecting words; make every personal reference explicit.',
            'The unit examples are language inputs, not evidence that the learner already knows every form.',
        ],
        'grammar_limits': [], 'answer_frames': [], 'contrast_rules': [], 'checked_forms': [],
        'extension_policy': {
            'checked_forms_are_examples': True,
            'lexical_sources': ['unit teaching', 'supplied familiar vocabulary', 'bounded new vocabulary'],
            'requirements': [
                'Apply a taught construction to additional suitable nouns; do not confuse a new noun with a new grammatical requirement.',
                'Validate the inflected form, lexical sense and required preposition before accepting it.',
                'Keep unfamiliar content vocabulary within the request allowance and provide its contextual support.',
                'A noun in the vocabulary store does not establish that its whole paradigm or a new construction has been taught.',
            ],
        },
    }
    if identity == LOCATION:
        where, destination = selected
        plan['supporting_language'].append('Use the taught present forms of быть/implied location and идти, with сейчас and потом.')
        plan['grammar_limits'] = [
            'Contrast a current position with a destination; do not infer destination from movement alone.',
            'Do not require origins, prefixed motion verbs, transport or directions with untaught case frames.',
            'Keep each question about one stated relation at one point in the plan; name both friends when asking about their shared current place.',
            'Use complete в/на phrases in answers. All alternatives must fit the question grammatically.',
        ]
        plan['answer_frames'] = [_frame('location', 'Где?', where, 'location'),
                                 _frame('destination', 'Куда?', destination, 'destination')]
        plan['contrast_rules'] = [
            _rule(where, 'stationary-location', 'location', 'Where the person is now, not their next destination.'),
            _rule(destination, 'directed-destination', 'destination', 'Where the person is going, not movement within a place.'),
        ]
        # Work is a relation to an activity and a street can contain a stop.
        # Neither is a mutually exclusive alternative to a concrete venue.
        discrete_places = [row for row in _PLACES if row['lemma'] not in ('работа', 'улица')]
        plan['checked_forms'] = rng.sample(discrete_places, 6)
        plan['extension_policy']['place_frames'] = list(_PLACES)
        plan['extension_policy']['place_rule'] = (
            'Use a conventional location/destination pair from this lexical reference or another supplied, verified source. '
            'Do not choose в/на from morphology alone. Regular singular -е locations and taught accusative patterns '
            'can use further common places. A supported invariable noun such as кафе is valid, but its identical '
            'forms require explicit location/destination context; do not score an ending contrast there.')
    elif identity == CALENDAR:
        duration = 'a1.language.accusative-duration'
        plan['supporting_language'].append('Use the taught activities and elapsed-time verbs in the unit examples, including ждал and длился.')
        plan['grammar_limits'] = [
            'Use stated elapsed durations, not arithmetic on start and finish times.',
            'Как долго? and Сколько времени? take a duration phrase without в or через.',
            'Use three plausible lengths of time for duration options; never mix dates, places and durations.',
            'Keep every option plausible for the same activity. Do not contrast a minute with a month for an ordinary lesson.',
            'Use bare single-unit durations or the taught один/одну + noun; further counts require a supplied, taught numeral-and-noun pattern.',
        ]
        plan['answer_frames'] = [_frame('duration', 'Как долго?', duration, 'duration')]
        plan['contrast_rules'] = [_rule(duration, 'elapsed-duration', 'duration',
            'The length of an activity, not when it starts or how long until it starts.')]
        plan['checked_forms'] = rng.sample(_DURATIONS, len(_DURATIONS))
        scale = family['duration_context']
        plan['duration_context'] = {'id': scale, **_DURATION_CONTEXTS[scale]}
        if scale == 'reading-period':
            plan['supported_phrases'].append({
                'ru': 'читал книгу / читала книгу', 'en': 'read a book for a period; completion is not asserted',
                'scope': 'The supplied accusative object книгу supports the taught reading verb; it is not an extra assessed construction.',
            })
            plan['grammar_limits'].append(
                'For this reading activity use читал/читала книгу. An hour, day or week is an elapsed reading period, possibly with breaks. Do not claim completion.')
            if mode == 'reading':
                plan['supported_phrases'].append({
                    'ru': 'начал читать книгу / начала читать книгу', 'en': 'began reading a book',
                    'scope': 'A supplied supporting phrase to anchor the written start date; not an independently assessed aspect or infinitive target.',
                })
                plan['grammar_limits'].append(
                    'Use the supplied начал/начала читать книгу frame for the start date. The date marks the beginning of the same reading period, not its end.')
        plan['extension_policy']['duration_rule'] = {
            'bare_singular': True, 'optional_one': ['один', 'одну'],
            'counts_above_one_require_taught_pattern': True,
            'counted_forms_are_not_implied_by_familiar_lemmas': True,
        }
        if mode == 'reading':
            date = 'a1.language.genitive-calendar-month'
            plan['answer_frames'].insert(0, _frame('date', 'Когда?', date, 'date_written'))
            plan['contrast_rules'].insert(0, _rule(date, 'calendar-date', 'date_written',
                'A calendar day and genitive month, without a preceding в.'))
            month, genitive = rng.choice(_MONTHS)
            plan['checked_forms'].extend({'lemma': month, 'date_written': f'{day} {genitive}',
                'date_spoken': f'{_ORDINALS[day - 1]} {genitive}'} for day in rng.sample(range(1, 29), 3))
            plan['grammar_limits'].append('Show dates with written day numbers; the date_spoken form is reference metadata, not a task for this lesson.')
        else:
            plan['grammar_limits'].extend([
                'Do not include calendar dates or test spoken ordinal numbers; this unit teaches their written form only.',
                'A start time may be incidental only when its expression occurs in the teaching; do not assess clock-time recognition.',
                'Spell duration words out naturally. Describe only one activity or stay and one stated length of time.',
            ])
    else:
        topic = selected[0]
        plan['supporting_language'].append('Use the taught present forms of говорить, думать and рассказывать; nouns after о/об identify their topic.')
        plan['grammar_limits'] = [
            'Keep the person speaking separate from the person or thing spoken about.',
            'A topic is not a location: о работе and на работе express different relationships.',
            'Use О ком? for a person and О чём? for a thing or subject. Each answer includes о/об and the prepositional form.',
            'Use о or об according to the opening sound: об Анне, об отдыхе, but о языке. Do not infer the choice from the vowel letter alone.',
            'Do not require topic pronouns such as обо мне, unsupported reported speech or untaught tense forms.',
        ]
        if family['id'] == 'topics-thought-and-speech':
            plan['supported_phrases'].append({
                'ru': 'Я думаю',
                'en': 'I am thinking',
                'scope': 'Support this bounded direct-disclosure frame; substitute the frozen name and thing-topic. The quote conveys the thought fact, not another event.',
            })
            plan['supported_phrases'].append({
                'ru': 'добавляет', 'en': 'adds',
                'scope': 'An optional reporting verb for the explicitly disclosed thought after the separate conversation topic.',
            })
            plan['grammar_limits'].append(
                'Make the thought credible with a named-speaker direct disclosure «Я думаю ...». '
                'The supplied добавляет can introduce it after the separate conversation topic without repeating говорит. '
                'Use the frozen name as the quote’s speaker and the frozen thought-topic. '
                'This bounded direct quote is allowed; no guessed thoughts, indirect speech or extra dialogue.')
        plan['answer_frames'] = [_frame('topic_person', 'О ком?', topic, 'topic'),
                                 _frame('topic_thing', 'О чём?', topic, 'topic')]
        plan['contrast_rules'] = [_rule(topic, 'conversation-topic', 'topic',
            'The subject of speaking, thinking or telling, not the speaker or their location.')]
        plan['checked_forms'] = rng.sample(_TOPIC_FORMS, len(_TOPIC_FORMS))
        plan['extension_policy']['topic_rule'] = (
            'Additional supported person or topic nouns may use the taught singular prepositional -е construction. '
            'Check the full о/об phrase and its person/topic meaning. Require evidence for proper-name readings; '
            'do not substitute pronoun constructions such as обо мне or unfamiliar declension patterns.')
    plan['meaning_plan'] = _build_meaning_plan(plan, rng)
    return deepcopy(plan)
