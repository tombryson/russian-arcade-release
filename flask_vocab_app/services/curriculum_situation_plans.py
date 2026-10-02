"""Construction-led inputs for new situations, not a bank of finished stories.

The plan fixes what a learner should understand before a model chooses its
wording. Only these specified teaching scopes have plans here. Other units return
None; sharing an A1 label is not sufficient to infer their prerequisites.
"""
from copy import deepcopy
import random

VERSION = 'curriculum-language-plan-v3'

LOCATION = 'location-destination-v1'
CALENDAR = 'calendar-and-duration-v1'
TOPICS = 'talking-about-topics-v1'

_REQUIREMENTS = {
    LOCATION: ('a1.language.prepositional-location', 'a1.language.accusative-destination'),
    CALENDAR: ('a1.language.genitive-calendar-month', 'a1.language.accusative-duration'),
    TOPICS: ('a1.language.prepositional-topic',),
}

_RECIPES = {
    LOCATION: (
        ('find-a-friend', 'finding friends in the neighbourhood',
         'Tell the addressee where two friends are, so they can find them before one moves on.'),
        ('coordinate-two-people', 'meeting friends locally',
         'Help the addressee choose which friend to meet now, knowing one friend has a next stop.'),
        ('share-next-stop', 'a short local outing',
         'Pass on one friend’s next stop and another friend’s current location so the addressee can join them.'),
    ),
    CALENDAR: (
        ('report-a-visit', 'a friend’s completed visit',
         'Answer the addressee’s question about where a friend stayed, when the visit began and how long it lasted.'),
        ('share-travel-news', 'news about a friend’s stay',
         'Update the addressee about one friend’s recent stay: its place, starting date and length.'),
        ('remember-a-stay', 'remembering a shared friend’s trip',
         'Help the addressee recall the place, starting date and length of one friend’s stay.'),
    ),
    CALENDAR + ':listening': (
        ('report-a-stay', 'a friend’s completed stay',
         'Answer the addressee’s question about where a friend stayed, how long it lasted and who else was there.'),
        ('share-trip-news', 'news about friends away from home',
         'Tell the addressee about one friend’s stay and identify another friend who was at the same place.'),
        ('remember-a-visit', 'remembering a friend’s visit',
         'Help the addressee recall a friend’s stay: its place, length and one companion.'),
    ),
    TOPICS: (
        ('join-a-conversation', 'a conversation with friends',
         'Tell the addressee what two friends are each talking about and where they are, so the addressee can join them.'),
        ('find-an-interesting-conversation', 'friends sharing news',
         'Help the addressee find friends discussing a topic of interest by naming each speaker’s subject and the meeting place.'),
        ('share-conversation-news', 'a conversation during a break',
         'Invite the addressee into an existing conversation by explaining where the friends are and what each is talking about.'),
    ),
}

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
        'version': 'situation-meaning-v1',
        'writer': writer, 'addressee': addressee,
        'participants': [first, second],
        'context_en': plan['setting'], 'purpose_en': plan['purpose'],
        'timeline_en': '', 'facts': [],
        'constraints': [
            'Report these three facts about the named people; do not add other assessable events.',
            'The writer and addressee are not the people whose actions are being reported.',
            'Keep the subject’s name with each assessed fact. Connect clauses naturally; do not pad the message.',
            'Use names in questions, not ambiguous я, мы or она. A who-question must not contain its answer name.',
        ],
    }
    if plan['unit_id'] == LOCATION:
        here, next_stop, other_here = rng.sample(plan['checked_forms'], 3)
        locations = [row['location'] for row in (here, next_stop, other_here)]
        destinations = [row['destination'] for row in (here, next_stop, other_here)]
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
        venue, *venue_options = rng.sample(_STAY_PLACES, 3)
        meaning['venue_family'] = 'named-city'
        duration = rng.choice(plan['duration_context']['phrase_examples'])
        durations = [v for v in plan['duration_context']['phrase_examples'] if v != duration]
        past_live = 'жила' if first['gender'] == 'feminine' else 'жил'
        meaning['timeline_en'] = (
            f"One completed stay by {first['name_en']}. State its venue and elapsed duration. "
            'Do not add departure dates, later trips or another length of stay.')
        meaning['facts'] = [
            _fact('f1', 'duration', first, duration,
                  f"Как долго {first['name_ru']} там {past_live}?",
                  'The elapsed length of this one stay.', durations),
            _fact('f2', 'location', first, venue['location'],
                  f"Где {past_live} {first['name_ru']}?", 'The venue of the same stay.',
                  [row['location'] for row in venue_options]),
        ]
        if plan['mode'] == 'reading':
            dates = [row['date_written'] for row in plan['checked_forms'] if 'date_written' in row]
            arrived = 'приехала' if first['gender'] == 'feminine' else 'приехал'
            meaning['facts'].append(_fact('f3', 'date', first, dates[0],
                f"Когда {arrived} {first['name_ru']}?", 'The start date of this same stay.', dates[1:]))
            meaning['participants'] = [first]
            meaning['timeline_en'] += ' The written date is the arrival/start of that stay, not a second event.'
        else:
            meaning['facts'].append(_fact('f3', 'person', second, second['name_ru'],
                'Кто ещё там жил?', 'The one companion who also stayed at that venue.',
                [writer['name_ru'], addressee['name_ru']]))
            meaning['timeline_en'] += (
                f" {second['name_en']} was also there, but has no separate duration or departure. "
                'No calendar date is stated or assessed.')
        # Supporting venue comprehension does not claim a new language target.
        plan['extension_policy']['place_frames'] = list(_STAY_PLACES)
    else:
        people_topics = [row for row in plan['checked_forms'] if row['referent_kind'] == 'person']
        # Avoid turning a topic about a third person into an accidental self-reference.
        person_topic = rng.choice([row for row in people_topics
                                   if row['lemma'] not in {p['name_ru'] for p in (writer, addressee, first, second)}])
        thing_topics = [row for row in plan['checked_forms'] if row['referent_kind'] == 'thing']
        thing_topic = rng.choice(thing_topics)
        conversation_places = [row for row in _PLACES if row['lemma'] in ('кафе', 'парк', 'работа', 'библиотека')]
        venue, *venue_options = rng.sample(conversation_places, 3)
        meaning['timeline_en'] = (
            f"One present conversation at the same venue. {first['name_en']} talks about one person; "
            f"{second['name_en']} talks about one subject. Each speaker has exactly one topic, with no topic changes.")
        meaning['facts'] = [
            _fact('f1', 'topic_person', first, person_topic['topic'],
                  f"О ком говорит {first['name_ru']}?", 'This speaker’s sole topic, a person.',
                  [row['topic'] for row in people_topics if row != person_topic]),
            _fact('f2', 'topic_thing', second, thing_topic['topic'],
                  f"О чём говорит {second['name_ru']}?", 'This other speaker’s sole topic, a thing or subject.',
                  rng.sample([row['topic'] for row in thing_topics if row != thing_topic], 2)),
            _fact('f3', 'location', first, venue['location'],
                  f"Где сейчас {first['name_ru']}?", 'The place where both people are having this conversation.',
                  [row['location'] for row in venue_options]),
        ]
        plan['extension_policy']['place_frames'] = conversation_places
    return meaning


def _frame(role, question, requirement, form_key):
    return {'role': role, 'question_ru': question,
            'requirement_id': requirement, 'form_key': form_key}


def _rule(requirement, rule, form_key, meaning):
    return {'requirement_id': requirement, 'rule': rule,
            'form_key': form_key, 'meaning_en': meaning}


def build_language_plan(unit, seed, mode):
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
        return None
    if unit.get('level') != 'A1':
        raise ValueError('This language plan only describes its taught A1 scope.')
    selected = list(_REQUIREMENTS[identity])
    if identity == CALENDAR and mode == 'listening':
        selected = ['a1.language.accusative-duration']
    taught = {question.get('requirement_id') for question in unit.get('questions', [])}
    if not set(selected) <= taught:
        raise ValueError('The unit does not teach all selected language requirements.')
    rng = random.Random(VERSION + ':' + identity + ':' + seed)
    recipes = _RECIPES[CALENDAR + ':listening' if identity == CALENDAR and mode == 'listening' else identity]
    recipe, setting, purpose = rng.choice(recipes)
    plan = {
        'version': VERSION, 'unit_id': identity, 'mode': mode,
        'recipe_id': recipe, 'setting': setting, 'purpose': purpose,
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
            'Keep each question about one named person and one stated point in the plan.',
            'Use complete в/на phrases in answers. All alternatives must fit the question grammatically.',
        ]
        plan['answer_frames'] = [_frame('location', 'Где?', where, 'location'),
                                 _frame('destination', 'Куда?', destination, 'destination')]
        plan['contrast_rules'] = [
            _rule(where, 'stationary-location', 'location', 'Where the person is now, not their next destination.'),
            _rule(destination, 'directed-destination', 'destination', 'Where the person is going, not movement within a place.'),
        ]
        plan['checked_forms'] = rng.sample(_PLACES, 6)
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
        scale = 'reading-period' if 'reading' in recipe else 'temporary-stay'
        plan['duration_context'] = {'id': scale, **_DURATION_CONTEXTS[scale]}
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
                'Spell duration words out naturally. Describe only one stay and one stated length of time.',
            ])
    else:
        topic = selected[0]
        plan['supporting_language'].append('Use the taught present forms of говорить, думать and рассказывать; nouns after о/об identify their topic.')
        plan['grammar_limits'] = [
            'Keep the person speaking separate from the person or thing spoken about.',
            'A topic is not a location: о работе and на работе express different relationships.',
            'Use О ком? for a person and О чём? for a thing or subject. Each answer includes о/об and the prepositional form.',
            'Use о or об according to the opening sound: об Анне, об отдыхе, but о языке. Do not infer the choice from the vowel letter alone.',
            'Do not require topic pronouns such as обо мне, reported speech or untaught tense forms.',
        ]
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
