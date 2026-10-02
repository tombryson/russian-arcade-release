"""New g1 rules for calendar dates, duration and the subject of a conversation.

These rules own bounded teaching lexicons, not a translation field on lemmas.
Morphology is realized through the same analyser as the existing rules. A date
or character change does not make a previously answered case contrast unseen.
"""

MONTHS = (
    ('январь', 'January'), ('февраль', 'February'), ('март', 'March'),
    ('апрель', 'April'), ('май', 'May'), ('июнь', 'June'),
    ('июль', 'July'), ('август', 'August'), ('сентябрь', 'September'),
    ('октябрь', 'October'), ('ноябрь', 'November'), ('декабрь', 'December'),
)
# Contexts describe elapsed time, rather than a deadline (за), waiting time
# (через), intended stay (на), or recurring rate (в). Do not interchange them.
DURATIONS = (
    ('Урок начался в десять и закончился в одиннадцать. Урок длился',
     'час', 'one hour', 'один час'),
    ('Я начал читать в два часа и закончил в три. Я читал',
     'час', 'one hour', 'один час'),
    ('Я начал ждать в 14:00. Автобус пришёл в 14:01. Я ждал',
     'минута', 'one minute', 'одну минуту'),
    ('Я начал отдыхать в понедельник утром и закончил во вторник утром. Я отдыхал',
     'день', 'one day', 'один день'),
    ('Я приехал в понедельник и уехал в следующий понедельник. Я жил в гостинице',
     'неделя', 'one week', 'одну неделю'),
    ('Я приехал первого марта и уехал первого апреля. Я жил в Москве',
     'месяц', 'one month', 'один месяц'),
)
TOPICS = (
    ('мама', 'mother', 'о'), ('друг', 'male friend', 'о'),
    ('семья', 'family', 'о'), ('работа', 'work', 'о'),
    ('книга', 'book', 'о'), ('музыка', 'music', 'о'),
    ('спорт', 'sport', 'о'), ('отдых', 'rest or a holiday', 'об'),
)
TOPIC_VERBS = (
    ('Я', 'говорю'), ('Мы', 'говорим'), ('Ты', 'думаешь'),
    ('Она', 'думает'), ('Вы', 'рассказываете'), ('Они', 'рассказывают'),
)


def time_question(rng):
    from services.curriculum_generation import _question, inflect, noun_choices
    if rng.choice((True, False)):
        lemma, gloss = rng.choice(MONTHS)
        # All months contain these dates. Avoid impossible 30/31 February.
        day = rng.randint(1, 28)
        event = rng.choice(('Урок будет', 'Встреча будет', 'Концерт будет'))
        answer = inflect(lemma, 'sing gent')
        return _question(
            'calendar-month', 'genitive-calendar-month',
            f'{event} {day} [...].', answer, noun_choices(lemma, answer),
            f'{lemma} — {gloss}. Complete the calendar date.',
            'After the day number in a date, the month takes the genitive: ' + answer + '.',
            'После числа в дате месяц ставится в родительном падеже: ' + answer + '.',
            semantic=('calendar-month', lemma),
            meaning_ru=f'{lemma}. Дополните календарную дату.',
        )
    context, lemma, gloss, explicit = rng.choice(DURATIONS)
    answer = inflect(lemma, 'sing accs')
    # These are different time meanings, not invented malformed Russian.
    choices = [answer, 'в два часа', 'первого марта', 'через неделю']
    return _question(
        'elapsed-duration', 'accusative-duration', context + ' [...].',
        answer, choices,
        f'Say how long the activity lasted: {gloss}. Give the duration, not the start time. Use the time word without a preposition.',
        'A completed stretch of time uses a duration phrase without a preposition: '
        + answer + '. В два часа is a clock time; первого марта is a date; через неделю means a week later.',
        'Продолжительность — без предлога: ' + answer
        + '. В два часа — время, первого марта — дата, через неделю — позже.',
        semantic=('elapsed-duration', lemma), accepted=[answer, explicit],
        meaning_ru='Слово: ' + lemma + '. Укажите продолжительность без предлога, а не время начала.',
    )


def topic_question(rng):
    from services.curriculum_generation import _question, inflect, noun_choices
    lemma, gloss, prep = rng.choice(TOPICS)
    subject, verb = rng.choice(TOPIC_VERBS)
    answer = inflect(lemma, 'sing loct')
    return _question(
        'topic-about', 'prepositional-topic', f'{subject} {verb} {prep} [...].',
        answer, noun_choices(lemma, answer),
        f'{lemma} — {gloss}. Name one topic being discussed or thought about.',
        'About a topic uses о + prepositional: ' + prep + ' ' + answer + '.'
        + (' Use об before the vowel sound at the start of отдых.' if prep == 'об' else ''),
        'Тема речи или мысли: о + предложный падеж — ' + prep + ' ' + answer + '.',
        semantic=('topic-about', lemma),
        meaning_ru=f'{lemma}. Назовите одну тему речи или мысли.',
    )
