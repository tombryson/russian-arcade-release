"""Authored starter games assembled from the learner's frozen lesson language.

This module does not translate lemmas, infer inflections, or call a provider.
Words, surface forms, sentences and their contextual translations travel
together from the saved lesson. The limited First steps vocabulary deliberately
produces a small first pack, rather than an invented broader curriculum.
"""
from copy import deepcopy
import hashlib
import random
import re

from repositories.learning_repository import LearningError

VERSION = 'journey-games-v2'
NEW_GAMES = (
    {'id': 'pairs', 'title': 'Postcard Pairs', 'lesson_id': 'bag', 'lesson_title': 'What’s in the bag?',
     'description': 'Match the Russian on each postcard to its picture.'},
    {'id': 'missing-stamp', 'title': 'Missing Stamp', 'lesson_id': 'bag', 'lesson_title': 'What’s in the bag?',
     'description': 'Put the missing Russian word back into each message.'},
    {'id': 'radio', 'title': 'Post Office Radio', 'lesson_id': 'directions', 'lesson_title': 'Which way?',
     'description': 'Listen to a short Russian radio programme, then answer four questions.'},
    {'id': 'mailbox-sort', 'title': 'Mailbox Sort', 'lesson_id': 'help', 'lesson_title': 'Ask for help',
     'description': 'Match Russian messages to their English meanings.'},
    {'id': 'letter-back', 'title': 'A Letter Back', 'lesson_id': 'help', 'lesson_title': 'Ask for help',
     'description': 'Listen to a message and rebuild it with word tiles.'},
    {'id': 'detective', 'title': 'Lost Parcel Detective', 'lesson_id': 'set-off', 'lesson_title': 'Ready to set off',
     'description': 'Use both clues to find the right delivery card.'},
)

PICTURES = {'письмо': ('letter', 'Letter'), 'сумка': ('bag', 'Bag'), 'карта': ('map', 'Map')}
DIRECTION_WORDS = {'прямо': 'straight', 'налево': 'left', 'направо': 'right'}
DIRECTION_LABELS = {'straight': 'straight ahead', 'left': 'left', 'right': 'right'}


def audio_clue(text):
    return {'text': text, 'audio_key': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def _unavailable():
    raise LearningError('game_content_unavailable', 'This saved lesson does not contain the language needed for this game.', 409)


class LessonLanguage:
    """Resolve stable lesson identities while retaining their exact saved text."""
    def __init__(self, lesson):
        self.lessons = {item['id']: item for item in lesson.get('related_lessons', [])}
        self.lessons[lesson['id']] = lesson
        self.refs = {}
        self.media_texts = set()

    def vocabulary(self, lesson_id, lemma):
        lesson = self.lessons.get(lesson_id)
        found = next((item for item in (lesson or {}).get('vocabulary', []) if item['lemma'] == lemma), None)
        if not found or any(not isinstance(found.get(field), str) or not found[field]
                            for field in ('lemma', 'form', 'sentence', 'translation')):
            _unavailable()
        self.refs[(lesson_id, lemma, found['sentence'])] = {'lesson_id': lesson_id, 'lesson_version': lesson.get('version'), **deepcopy(found)}
        return deepcopy(found)

    def teaching(self, lesson_id, card_id):
        lesson = self.lessons.get(lesson_id)
        found = next((item for item in (lesson or {}).get('teaching', []) if item['id'] == card_id), None)
        if not found or not found.get('word') or not found.get('meaning'):
            _unavailable()
        return {'sentence': found['word'], 'translation': found['meaning']}

    def answer_phrase(self, lesson_id, question_id):
        lesson = self.lessons.get(lesson_id)
        question = next((item for item in (lesson or {}).get('questions', []) if item['id'] == question_id), None)
        answer = next((choice['text'] for choice in (question or {}).get('choices', [])
                       if choice['id'] == question['answer']), None)
        if not answer:
            _unavailable()
        return answer

    def audio(self, text):
        self.media_texts.add(text)
        return audio_clue(text)


def _bag_words(language):
    return [language.vocabulary('bag', lemma) for lemma in PICTURES]


def _round(game, position, prompt, *, expected, hint, feedback, **fields):
    return {'id': f'{game}-{position + 1}', 'mechanic': game, 'prompt': prompt,
            'clues': [], 'max_choices': len(expected), 'expected_answer': expected,
            'hint': hint, 'feedback': feedback, **fields}


def _pairs(language, rng):
    words = _bag_words(language)
    rounds = []
    for position in range(3):
        selected = rng.sample(words, 2 if position == 0 else 3)
        pictures = rng.sample(selected, len(selected))
        left = [{'id': f'text-{index}', **language.audio(word['sentence'])} for index, word in enumerate(selected)]
        right = [{'id': f'picture-{index}', 'visual': PICTURES[word['lemma']][0], 'label': PICTURES[word['lemma']][1]}
                 for index, word in enumerate(pictures)]
        expected = [f'text-{index}:picture-{next(i for i, picture in enumerate(pictures) if picture["lemma"] == word["lemma"])}'
                    for index, word in enumerate(selected)]
        rounds.append(_round('pairs', position, 'Match each Russian postcard to its picture.',
                             expected=sorted(expected), left=left, right=right,
                             hint=' '.join(f'«{word["sentence"]}» — {word["translation"]}' for word in selected),
                             feedback=' '.join(f'«{word["sentence"]}» — {word["translation"]}' for word in selected)))
    return rounds


def cloze_sentence(sentence, form):
    """Remove the exact taught surface form, including its case or conjugation."""
    word_character = r'[\w\u0300-\u036f]'
    matches = list(re.finditer(r'(?<!' + word_character + ')' + re.escape(form) + r'(?!' + word_character + ')', sentence, flags=re.IGNORECASE))
    if len(matches) != 1:
        _unavailable()
    match = matches[0]
    return sentence[:match.start()] + '[[blank]]' + sentence[match.end():]


def _missing_stamp(language, rng):
    words = _bag_words(language)
    rounds = []
    for position, target in enumerate(rng.sample(words, len(words))):
        options = rng.sample(words, len(words))
        choices = [{'id': f'word-{index}', 'text': word['form']} for index, word in enumerate(options)]
        answer = next(choice['id'] for choice, word in zip(choices, options) if word['lemma'] == target['lemma'])
        rounds.append(_round('missing-stamp', position, 'Put the missing word back into the message.',
                             expected=[answer], choices=choices,
                             sentence=cloze_sentence(target['sentence'], target['form']),
                             translation=target['translation'], visual=PICTURES[target['lemma']][0],
                             answer_audio=[language.audio(target['sentence'])],
                             hint=f'The missing word is «{target["form"]}». Use the form from this sentence.',
                             feedback=f'«{target["sentence"]}» — {target["translation"]}'))
    return rounds


def _radio(language, rng):
    words = [language.vocabulary('directions', lemma) for lemma in DIRECTION_WORDS]
    rounds = []
    for position, target in enumerate(rng.sample(words, len(words))):
        options = rng.sample(list(DIRECTION_LABELS), 3)
        rounds.append(_round('radio', position, 'Listen, then choose the arrow for Barsik.',
                             expected=[DIRECTION_WORDS[target['lemma']]],
                             clues=[language.audio(target['sentence'])], audio_required=True,
                             choices=[{'id': move, 'visual': move, 'label': DIRECTION_LABELS[move].capitalize()} for move in options],
                             hint=f'«{target["sentence"]}» — {target["translation"]}',
                             feedback=f'«{target["sentence"]}» — {target["translation"]}'))
    return rounds


def _mailbox_sort(language, rng):
    words = rng.sample(_bag_words(language), 3)
    directions = rng.sample([language.vocabulary('directions', lemma) for lemma in DIRECTION_WORDS], 3)
    requests = [language.vocabulary('help', 'рынок'), language.vocabulary('help', 'показать')]
    bins = [{'id': 'name', 'label': 'Name a thing', 'description': 'Say what something is.'},
            {'id': 'direction', 'label': 'Give directions', 'description': 'Say which way to go.'},
            {'id': 'help', 'label': 'Ask for help', 'description': 'Ask where something is or ask someone to show you.'}]
    rounds = []
    for position in range(3):
        request = requests[position % len(requests)]
        entries = [(words[position], 'name'), (directions[position], 'direction'), (request, 'help')]
        rng.shuffle(entries)
        sentences = [{'id': f'note-{index}', **language.audio(word['sentence'])} for index, (word, _) in enumerate(entries)]
        expected = sorted(f'note-{index}:{category}' for index, (_, category) in enumerate(entries))
        rounds.append(_round('mailbox-sort', position, 'Put each message in the right mailbox.',
                             expected=expected, sentences=sentences, bins=rng.sample(bins, len(bins)),
                             hint=' '.join(f'«{word["sentence"]}» — {word["translation"]}' for word, _ in entries),
                             feedback=' '.join(f'«{word["sentence"]}» — {word["translation"]}' for word, _ in entries)))
    return rounds


def _letter_back(language, rng):
    greeting = language.teaching('help', 'help-greet')
    where = language.vocabulary('help', 'рынок')
    show = language.vocabulary('help', 'показать')
    thanks = {'sentence': language.answer_phrase('help', 'help-say-thanks'), 'translation': 'Thank you!'}
    informal = language.vocabulary('hello', 'привет')
    map_word = language.vocabulary('bag', 'карта')
    messages = [
        ('Greet the clerk politely, then ask where the market is.', [greeting, where]),
        ('Ask the clerk to show you the way, then say thank you.', [show, thanks]),
        ('Greet Barsik by name, then tell him this is a map.', [informal, map_word]),
    ]
    pool = {word['sentence']: word for word in (greeting, where, show, thanks, informal, map_word)}
    rounds = []
    for position, (goal, target) in enumerate(rng.sample(messages, len(messages))):
        target_text = [word['sentence'] for word in target]
        distractors = rng.sample([word for text, word in pool.items() if text not in target_text], 2)
        options = rng.sample([*target, *distractors], 4)
        tiles = [{'id': f'phrase-{index}', 'text': word['sentence']} for index, word in enumerate(options)]
        expected = [next(tile['id'] for tile in tiles if tile['text'] == text) for text in target_text]
        rounds.append(_round('letter-back', position, goal, expected=expected, tiles=tiles,
                             answer_audio=[language.audio(word['sentence']) for word in target],
                             hint='Choose two phrases. ' + ' Then '.join(word['translation'].rstrip('.') for word in target),
                             feedback=' '.join(target_text) + ' — ' + ' '.join(word['translation'] for word in target)))
    return rounds


def _detective(language, rng):
    objects = rng.sample(_bag_words(language), 3)
    # Sample all three to keep the visible seeded layout stable, but only
    # record the two sentences actually used. The third round uses the saved
    # two-step instruction; its unused single direction must not create a card.
    direction_lemmas = rng.sample(list(DIRECTION_WORDS), 3)
    directions = [language.vocabulary('directions', lemma) for lemma in direction_lemmas[:2]]
    sequence = language.vocabulary('set-off', 'потом')
    rounds = []
    for position, target in enumerate(objects):
        direction = directions[position] if position < 2 else sequence
        route = [DIRECTION_WORDS[direction['lemma']]] if position < 2 else ['straight', 'left']
        other_route = [rng.choice([move for move in DIRECTION_LABELS if move != route[0]])] if position < 2 else ['left', 'straight']
        other_object = objects[(position + 1) % len(objects)]
        # Each clue alone matches two cards. Only their intersection identifies
        # one card: neither colour nor answer wording gives it away.
        combinations = [(word, path) for word in (target, other_object) for path in (route, other_route)]
        rng.shuffle(combinations)
        destinations = []
        expected = None
        for index, (word, path) in enumerate(combinations):
            card_id = f'delivery-{index}'
            visual, label = PICTURES[word['lemma']]
            destinations.append({'id': card_id, 'visual': visual, 'route': list(path),
                                 'label': label + ': ' + ', then '.join(DIRECTION_LABELS[move] for move in path)})
            if word['lemma'] == target['lemma'] and path == route:
                expected = card_id
        rounds.append(_round('detective', position, 'Find the delivery card that matches both clues.',
                             expected=[expected], destinations=destinations,
                             clues=[language.audio(target['sentence']), language.audio(direction['sentence'])],
                             hint=target['translation'] + ' ' + direction['translation'],
                             feedback=f'«{target["sentence"]}» — {target["translation"]} «{direction["sentence"]}» — {direction["translation"]} Both clues belong to the same card.'))
    return rounds


BUILDERS = {'pairs': _pairs, 'missing-stamp': _missing_stamp, 'radio': _radio,
            'mailbox-sort': _mailbox_sort, 'letter-back': _letter_back, 'detective': _detective}


def build_content(game, lesson, seed):
    builder = BUILDERS.get(game['id'])
    if builder is None or lesson['id'] != game['lesson_id']:
        _unavailable()
    language = LessonLanguage(lesson)
    rounds = builder(language, random.Random(seed))
    return {'version': VERSION, 'lesson_version': lesson['version'], 'title': game['title'],
            'source': {'lesson_id': lesson['id'], 'title': lesson['title'], 'href': '#first-steps/' + lesson['id']},
            'rounds': rounds, 'vocabulary_refs': list(language.refs.values()),
            'media_texts': sorted(language.media_texts)}
