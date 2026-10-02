"""Bounded instrumental rules for activities and singular future professions.

All constructions and lexical targets are taught in the paired unit. These
rules practise two functions; they do not establish independent case control.
"""

ACTIVITIES = (
    ('спорт', 'sport', 'спортом', ('спорт', 'спорта', 'спорту')),
    ('музыка', 'music', 'музыкой', ('музыка', 'музыку', 'музыке')),
    ('русский язык', 'Russian language', 'русским языком',
     ('русский язык', 'русского языка', 'русскому языку')),
)
ACTIVITY_SUBJECTS = (
    ('Я', 'занимаюсь'), ('Ты', 'занимаешься'), ('Он', 'занимается'),
    ('Она', 'занимается'), ('Мы', 'занимаемся'), ('Вы', 'занимаетесь'),
    ('Они', 'занимаются'),
)
PROFESSIONS = (
    ('врач', 'doctor', 'врачом', ('врач', 'врача', 'врачу')),
    ('учитель', 'teacher', 'учителем', ('учитель', 'учителя', 'учителю')),
    ('инженер', 'engineer', 'инженером', ('инженер', 'инженера', 'инженеру')),
)
# Plural professional predicates would require врачами/учителями and another
# teaching step. The present unit deliberately limits this rule to singular.
FUTURE_SUBJECTS = (('Я', 'буду'), ('Ты', 'будешь'), ('Он', 'будет'), ('Она', 'будет'))


def build_question(rng):
    # Runtime import avoids a second implementation of the frozen question
    # contract while permitting registration in curriculum_generation.BUILDERS.
    from services.curriculum_generation import _question
    if rng.choice((True, False)):
        subject, verb = rng.choice(ACTIVITY_SUBJECTS)
        lemma, gloss, answer, distractors = rng.choice(ACTIVITIES)
        return _question(
            'instrumental-activity', 'instrumental-activity',
            f'{subject} {verb} [...].', answer, [answer, *distractors],
            f'{lemma} — {gloss}',
            'Заниматься takes the activity in the instrumental, without с. '
            + ('Both words change in русским языком.' if lemma == 'русский язык'
               else f'The activity form is {answer}.'),
            'Название занятия после заниматься — в творительном падеже, без с: ' + answer + '.',
            semantic=('activity', subject, lemma),
            accepted=[answer, 'музыкою'] if lemma == 'музыка' else [answer],
            meaning_ru='Назовите занятие: ' + lemma + '.',
        )
    subject, verb = rng.choice(FUTURE_SUBJECTS)
    lemma, gloss, answer, distractors = rng.choice(PROFESSIONS)
    return _question(
        'instrumental-profession', 'instrumental-profession',
        f'{subject} {verb} [...].', answer, [answer, *distractors],
        f'{lemma} — {gloss}; name a future profession.',
        'Use the taught future-profession pattern: ' + verb + ' ' + answer + '.',
        'Будущая профессия в изученной конструкции: ' + verb + ' ' + answer + '.',
        semantic=('profession', subject, lemma),
        meaning_ru='Назовите будущую профессию: ' + lemma + '.',
    )
