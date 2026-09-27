"""Original, versioned A1 diagnostic samples; never an examination or pass gate.

This module is pure content/contract construction. It does not create sessions,
grade learners, initialise providers, or treat a media hash as proof of listening.
The caller verifies the published audio bytes before binding a descriptor to a
task. Answer keys and transcripts are server content, not learner presentation.
"""
from copy import deepcopy
import re

from contracts.curriculum import CONTRACT_VERSION, freeze_task_contract, validate_task_contract
from services.curriculum_requirement_map import content_digest, requirement_index
from services.torfl_requirements import VERSION


BLUEPRINT_ID = 'a1-five-domain-pilot-v1'
DOMAIN_IDS = ('language_use', 'reading', 'listening', 'writing', 'speaking')
FORM_IDS = ('a', 'b')
_HASH = re.compile(r'[0-9a-f]{64}')
_MODES = dict(language_use='contextual_selection', reading='reading_selection',
              listening='listening_selection', writing='independent_writing',
              speaking='independent_speaking')
_DOMAIN_TITLES = {
    'language_use': ('Language use', 'Лексика и грамматика'),
    'reading': ('Reading', 'Чтение'),
    'listening': ('Listening', 'Аудирование'),
    'writing': ('Writing', 'Письмо'),
    'speaking': ('Speaking', 'Говорение'),
}
_TRANSCRIPTS = {
    'a': 'Привет, Оля! Это Антон. В субботу я не работаю. Давай встретимся в три часа в кафе рядом с парком. '
         'Я буду ждать тебя у входа. После кафе мы можем погулять в парке. Позвони мне вечером.',
    'b': 'Привет, Саша! Это Нина. Завтра у нас урок русского языка в десять часов. '
         'Встречаемся у библиотеки в половине десятого. Возьми тетрадь и ручку. '
         'После урока я иду домой, потому что ко мне придёт брат.',
}


def _item(identity, prompt, choices, answer, explanation, requirement_id):
    return {'id': identity, 'prompt': prompt,
            'choices': [{'id': chr(97 + i), 'text': text} for i, text in enumerate(choices)],
            'answer': answer, 'explanation': explanation, 'requirement_id': requirement_id}


def _base(domain, form_id, title, title_ru, prompt, prompt_ru, topic_id, hint):
    return {'domain': domain, 'form_id': form_id, 'title': title, 'title_ru': title_ru,
            'prompt': prompt, 'prompt_ru': prompt_ru,
            'format': domain if domain in ('writing', 'speaking') else 'choice_set',
            'topic_id': topic_id, 'hint': hint}


def _authored_forms():
    """Build the retained v1 source; future releases need a separate builder.

    Never revise this version in place: saved v1 sessions must remain valid when
    a later pilot version is added. Returned objects never mutate this source.
    """
    forms = {domain: [] for domain in DOMAIN_IDS}
    grammar = {
        'a': [
            ('location', 'Сейчас Анна читает книгу в ___.', ['библиотеку', 'библиотеке', 'библиотека'], 'b',
             'В библиотеке answers где? and uses the prepositional case.', 'prepositional-location'),
            ('object', 'На завтрак я ем ___.', ['каша', 'каше', 'кашу'], 'c',
             'Ем кашу names the direct object in the accusative case.', 'accusative-object'),
            ('absence', 'Сегодня у меня нет ___.', ['урока', 'урок', 'уроке'], 'a',
             'Нет урока expresses absence with the genitive case.', 'genitive-absence'),
            ('recipient', 'Я пишу письмо ___.', ['сестру', 'сестре', 'сестра'], 'b',
             'Письмо сестре identifies the recipient with the dative case.', 'dative-recipient'),
            ('agreement', 'Это моя ___ комната.', ['новое', 'новый', 'новая'], 'c',
             'Новая agrees with the feminine noun комната.', 'adjective-agreement'),
            ('verb', 'Каждый вечер мы ___ музыку.', ['слушаем', 'слушает', 'слушаешь'], 'a',
             'Мы takes the first-person plural form слушаем.', 'verb-conjugation'),
        ],
        'b': [
            ('location', 'Сейчас Игорь покупает хлеб в ___.', ['магазин', 'магазина', 'магазине'], 'c',
             'В магазине answers где? and uses the prepositional case.', 'prepositional-location'),
            ('object', 'Вечером я читаю ___.', ['книгу', 'книге', 'книга'], 'a',
             'Читаю книгу names the direct object in the accusative case.', 'accusative-object'),
            ('absence', 'На столе нет ___.', ['молоко', 'молока', 'молоку'], 'b',
             'Нет молока expresses absence with the genitive case.', 'genitive-absence'),
            ('recipient', 'Анна даёт билет ___.', ['братом', 'брата', 'брату'], 'c',
             'Даёт брату identifies the recipient with the dative case.', 'dative-recipient'),
            ('agreement', 'Это мой ___ стол.', ['старый', 'старая', 'старое'], 'a',
             'Старый agrees with the masculine noun стол.', 'adjective-agreement'),
            ('verb', 'Каждое утро ты ___ чай.', ['пью', 'пьёшь', 'пьёт'], 'b',
             'Ты takes the second-person singular form пьёшь.', 'verb-conjugation'),
        ],
    }
    for form_id, rows in grammar.items():
        task = _base('language_use', form_id, 'Everyday sentences', 'Повседневные фразы',
            'Choose the one word that completes each sentence.',
            'Выберите одно слово для каждого предложения.', 'daily_activities',
            'Look at who is acting and whether the phrase describes a place, an object or a person receiving something.')
        task['items'] = [_item(identity, prompt, choices, answer, explanation, 'a1.language.' + requirement)
                         for identity, prompt, choices, answer, explanation, requirement in rows]
        forms['language_use'].append(task)

    reading = {
        'a': (
            'A Saturday with a friend', 'Суббота с другом',
            'В субботу Марина не работает. Утром она завтракает дома. В одиннадцать часов Марина встречает друга '
            'Диму у музея. Они смотрят картины, а потом обедают в кафе. Дима идёт домой, а Марина покупает хлеб '
            'и молоко. Вечером она читает книгу.',
            [
                ('meeting', 'Где Марина встречает Диму?', ['У музея.', 'У кафе.', 'У магазина.'], 'a',
                 'The text says Марина встречает друга Диму у музея.', 'narrative-meaning'),
                ('sequence', 'Что Марина и Дима делают после музея?', ['Покупают хлеб.', 'Читают книгу.', 'Обедают в кафе.'], 'c',
                 'After looking at pictures, they have lunch in a café.', 'reference-and-sequence'),
                ('person', 'Кто покупает продукты?', ['Дима.', 'Марина.', 'Марина и Дима.'], 'b',
                 'Dima goes home; Marina buys bread and milk.', 'narrative-meaning'),
            ]),
        'b': (
            'A Sunday visit', 'Воскресный визит',
            'В воскресенье Павел едет к сестре Лене. Она живёт рядом с парком. Сначала Павел покупает цветы. '
            'В два часа он приходит к Лене. Они пьют чай и смотрят фотографии. Потом Лена идёт в парк, '
            'а Павел едет домой. Вечером он готовит ужин.',
            [
                ('meeting', 'Когда Павел приходит к Лене?', ['В три часа.', 'В два часа.', 'В один час.'], 'b',
                 'The text says В два часа он приходит к Лене.', 'narrative-meaning'),
                ('sequence', 'Что Павел делает до визита к Лене?', ['Готовит ужин.', 'Смотрит фотографии.', 'Покупает цветы.'], 'c',
                 'Сначала Павел покупает цветы places this before the visit.', 'reference-and-sequence'),
                ('person', 'Кто идёт в парк после чая?', ['Лена.', 'Павел.', 'Лена и Павел.'], 'a',
                 'Lena goes to the park while Pavel goes home.', 'narrative-meaning'),
            ]),
    }
    for form_id, (title, title_ru, passage, rows) in reading.items():
        task = _base('reading', form_id, title, title_ru,
            'Read the short account and choose one answer for each question.',
            'Прочитайте рассказ и выберите один ответ на каждый вопрос.', 'daily_activities',
            'Find the sentence about each question. Words such as потом and сначала show the order of events.')
        task['passage'] = passage
        task['items'] = [_item(identity, prompt, choices, answer, explanation, 'a1.reading.' + requirement)
                         for identity, prompt, choices, answer, explanation, requirement in rows]
        forms['reading'].append(task)

    listening = {
        'a': [
            ('time', 'Когда Антон хочет встретиться с Олей?', ['В воскресенье в три часа.', 'В субботу в три часа.', 'В субботу в пять часов.'], 'b',
             'Anton proposes meeting on Saturday at three.'),
            ('place', 'Где Антон будет ждать Олю?', ['У входа в кафе.', 'Дома.', 'В парке.'], 'a',
             'After naming the café, Anton says he will wait у входа.'),
            ('request', 'Что Антон просит Олю сделать вечером?', ['Купить кофе.', 'Прийти в парк.', 'Позвонить ему.'], 'c',
             'Anton ends with the request Позвони мне вечером.'),
        ],
        'b': [
            ('time', 'Когда Нина и Саша встречаются?', ['В десять часов.', 'В девять часов.', 'В половине десятого.'], 'c',
             'They meet at half past nine, before the ten o’clock lesson.'),
            ('place', 'Где Нина и Саша встречаются?', ['У библиотеки.', 'У дома Нины.', 'В кафе.'], 'a',
             'Nina says Встречаемся у библиотеки.'),
            ('request', 'Что Нина просит Сашу взять?', ['Книгу и билет.', 'Тетрадь и ручку.', 'Чай и хлеб.'], 'b',
             'Nina asks Саша to bring a notebook and pen.'),
        ],
    }
    for form_id, rows in listening.items():
        task = _base('listening', form_id, 'A voice message', 'Голосовое сообщение',
            'Listen to the message and choose one answer for each question. You may replay the recording.',
            'Послушайте сообщение и выберите один ответ на каждый вопрос. Запись можно прослушать ещё раз.',
            'daily_activities', 'Listen for the meeting time, meeting place and the final request.')
        task.update(transcript=_TRANSCRIPTS[form_id],
                    audio_url='/static/audio/course/assessment-pilot/a1-pilot-' + form_id + '-v1.mp3', audio=None)
        task['items'] = [_item(identity, prompt, choices, answer, explanation, 'a1.listening.short-message')
                         for identity, prompt, choices, answer, explanation in rows]
        forms['listening'].append(task)

    writing = {
        'a': ('Invite a friend to the park', 'Пригласите друга в парк',
              'Write a short message in Russian to a friend. Invite them to the park on a day you choose. '
              'Say when and where to meet, suggest one activity, and ask whether they can come.',
              'Напишите другу короткое сообщение по-русски. Пригласите его в парк в любой день. '
              'Напишите, когда и где вы встретитесь и что будете делать. Спросите, может ли друг прийти. '
              'Главное — понятное сообщение.'),
        'b': ('Invite a friend to dinner', 'Пригласите друга на ужин',
              'Write a short message in Russian to a friend. Invite them to your home for dinner on a day you choose. '
              'Say when and where to meet, name one food or drink, and ask whether they can come.',
              'Напишите другу короткое сообщение по-русски. Пригласите его к себе домой на ужин в любой день. '
              'Напишите, когда и где вы встретитесь и что будете есть или пить. Спросите, может ли друг прийти. '
              'Главное — понятное сообщение.'),
    }
    for form_id, (title, title_ru, prompt, prompt_ru) in writing.items():
        task = _base('writing', form_id, title, title_ru, prompt, prompt_ru, 'hobbies' if form_id == 'a' else 'home',
            'Use your own words. Check that the reader knows the invitation, meeting details and your question.')
        task.update(task=prompt_ru, task_en=prompt, required_words=[], target_words=30)
        forms['writing'].append(task)

    speaking = {
        'a': ('Introduce yourself to a classmate', 'Представьтесь однокласснику',
            'Record a short message in Russian for a new classmate. Introduce yourself: say your name, '
            'where you live, what you study or do for work, and one activity you enjoy. Use your own words. '
            'You may invent personal details.',
            'Запишите короткое сообщение по-русски для нового одноклассника. Представьтесь: скажите, как вас зовут, '
            'где вы живёте, что изучаете или где работаете и что любите делать. Говорите своими словами. '
            'Личные данные можно придумать.'),
        'b': ('Introduce yourself to a neighbour', 'Представьтесь соседу',
            'Record a short message in Russian for a new neighbour. Introduce yourself: say your name, '
            'where you are from, who you live with, and one activity you enjoy. Use your own words. '
            'You may invent personal details.',
            'Запишите короткое сообщение по-русски для нового соседа. Представьтесь: скажите, как вас зовут, '
            'откуда вы, с кем живёте и что любите делать. Говорите своими словами. '
            'Личные данные можно придумать.'),
    }
    for form_id, (title, title_ru, prompt, prompt_ru) in speaking.items():
        task = _base('speaking', form_id, title, title_ru, prompt, prompt_ru, 'greetings',
                     'Make one short original recording. Include the requested personal details in connected, understandable phrases.')
        identity = 'assessment-pilot-a1-speaking-' + form_id + '-v1'
        task['scenario'] = {
            'id': identity, 'seed': identity, 'scenario_id': 'assessment-pilot-recorded-message', 'scenario_version': 1,
            'target_level': 'A1', 'title': title, 'title_ru': title_ru,
            'description': prompt, 'description_ru': prompt_ru, 'mode': 'recorded_message',
            'goals': ['Introduce yourself with the requested personal details.'],
            'goals_ru': ['Представьтесь и сообщите нужные личные сведения.'],
            'goal_ids': ['objective-1'],
            'completion_criteria': ['The original learner audio contains a short connected introduction with the four requested personal details.'],
        }
        forms['speaking'].append(task)
    return forms


def _criterion(task, identity, requirement_id, expectation, maximum=2):
    requirement = requirement_index()[requirement_id]
    if requirement['domain'] != task['domain'] or requirement['response_mode'] != _MODES[task['domain']]:
        raise ValueError('Pilot criterion must preserve its native requirement domain and response mode.')
    return {'id': identity, 'target_id': 'pilot.a1.' + task['domain'] + '.' + task['form_id'] + '.' + identity,
            'requirement_id': requirement_id, 'response_mode': _MODES[task['domain']],
            'evidence_scope': 'reference', 'expectation': expectation, 'max_score': maximum,
            'source_refs': deepcopy(requirement['source_refs'])}


def _criteria(task):
    if task['format'] == 'choice_set':
        return [_criterion(task, item['id'], item['requirement_id'],
            'Select the single answer to this original item from the supplied choices: ' + item['prompt'], 1)
            for item in task['items']]
    if task['domain'] == 'writing':
        return [
            _criterion(task, 'message-purpose', 'a1.writing.personal-message',
                'In the original learner text, address a friend, make the requested invitation and ask whether they can come. '
                'Accept natural short alternatives, with or without a greeting. Do not require a model phrase or exact word count.'),
            _criterion(task, 'message-details', 'a1.writing.personal-message',
                'In the original learner text, supply a comprehensible day, meeting time, meeting place and the requested activity, food or drink. '
                'Accept invented but coherent details and language errors that do not obscure these details. Do not infer omitted information.'),
        ]
    return [
        _criterion(task, 'personal-information', 'a1.speaking.personal-information',
            'In the original learner audio, give a short connected introduction with the four personal details requested by the prompt. '
            'Accept invented details, short phrases and natural alternatives. Assess only independent recorded production; '
            'do not claim evidence of dialogue, answering a partner, requests or interaction repair. Captions are not evidence.'),
        _criterion(task, 'intelligibility', 'a1.speaking.intelligibility',
            'Judge whether the original Russian words and short phrases can be understood from the learner audio itself. '
            'Accept a foreign accent. Do not infer pronunciation from captions or repaired text; unclear or absent audio is insufficient evidence.'),
    ]


def _audio_descriptor(value, url):
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'url', 'sha256', 'size_bytes', 'duration_ms'}
            or value['url'] != url or not isinstance(value['sha256'], str) or not _HASH.fullmatch(value['sha256'])
            or type(value['size_bytes']) is not int or not 0 < value['size_bytes'] <= 32 * 1024 * 1024
            or type(value['duration_ms']) is not int or not 0 < value['duration_ms'] <= 120000):
        raise ValueError('Pilot listening audio requires its exact published URL, hash, size and bounded duration.')
    return deepcopy(value)


def freeze_task(task, *, audio=None):
    """Freeze exact authored content, optionally binding caller-verified media.

    A supplied audio descriptor is shape/identity checked here; the caller must
    verify the file bytes and transcript binding. Re-freezing cannot authorize
    arbitrary questions, answer keys, instructions or scenario changes.
    """
    if not isinstance(task, dict) or task.get('domain') not in DOMAIN_IDS or task.get('form_id') not in FORM_IDS:
        raise ValueError('Unknown pilot domain or form.')
    expected = _authored_forms()[task['domain']][FORM_IDS.index(task['form_id'])]
    candidate = {key: deepcopy(value) for key, value in task.items() if key != 'contract'}
    if task['domain'] == 'listening':
        saved_audio = _audio_descriptor(candidate.get('audio'), expected['audio_url'])
        candidate['audio'] = None
        bound_audio = _audio_descriptor(audio, expected['audio_url']) if audio is not None else saved_audio
    elif audio is not None:
        raise ValueError('Only listening tasks can bind source audio.')
    if content_digest(candidate) != content_digest(expected):
        raise ValueError('Published pilot content changed; create a new version instead.')
    if task['domain'] == 'listening':
        candidate['audio'] = bound_audio
    support = {'allowed': ['hint', 'translation', 'model_answer'],
               'independence_breakers': ['hint', 'translation', 'model_answer']}
    if task['domain'] == 'listening':
        support = {'allowed': ['hint', 'translation', 'model_answer', 'transcript', 'audio_replay'],
                   'independence_breakers': ['hint', 'translation', 'model_answer', 'transcript']}
    contract = freeze_task_contract({
        'schema_version': 1, 'contract_version': CONTRACT_VERSION, 'reference_version': VERSION,
        'task_id': BLUEPRINT_ID + ':' + task['domain'] + ':' + task['form_id'],
        'activity': task['domain'] if task['domain'] in ('writing', 'speaking') else 'assessment_pilot',
        'content_version': BLUEPRINT_ID, 'level': 'A1', 'topic_ids': [task['topic_id']],
        'purpose': 'diagnostic', 'content': candidate, 'rubric_version': 'a1-pilot-native-criteria-v1',
        'support': support, 'criteria': _criteria(candidate),
    })
    return {**candidate, 'contract': contract}


def blueprint():
    """Return independent frozen authored forms; source audio starts unbound."""
    return {
        'id': BLUEPRINT_ID, 'schema_version': 1, 'level': 'A1',
        'title': 'A1 five-domain diagnostic pilot', 'title_ru': 'Пробная диагностика A1: пять разделов',
        'limitations': [
            'Original application-authored diagnostic samples, not official TORFL items or a proficiency certificate.',
            'Each form samples a few A1 requirements; it does not establish full A1 coverage, mastery or readiness for an examination.',
            'Forms A and B have not been calibrated or shown to be equivalent in difficulty. No pass mark or progression gate is defined.',
            'Keep help, transcript and model-answer use visible. Supported attempts remain useful practice, not independent evidence.',
            'Listening requires the verified recording. Speaking requires original learner audio; missing or unclear audio remains unscored.',
            'The pilot has not been calibrated for proficiency decisions.',
        ],
        'domains': [{'id': domain, 'title': _DOMAIN_TITLES[domain][0], 'title_ru': _DOMAIN_TITLES[domain][1]}
                    for domain in DOMAIN_IDS],
        'forms': {domain: [freeze_task(task) for task in tasks] for domain, tasks in _authored_forms().items()},
    }


def validate_blueprint(payload):
    """Reject changed authored content, omitted forms and rehashed substitutions."""
    expected = blueprint()
    if not isinstance(payload, dict) or set(payload) != set(expected):
        raise ValueError('Pilot blueprint contains missing or unsupported fields.')
    if any(content_digest(payload[key]) != content_digest(value) for key, value in expected.items() if key != 'forms'):
        raise ValueError('Pilot blueprint identity, scope or domain list changed.')
    forms = payload['forms']
    if not isinstance(forms, dict) or set(forms) != set(DOMAIN_IDS):
        raise ValueError('Pilot requires exactly the five authored domains.')
    for domain in DOMAIN_IDS:
        if not isinstance(forms[domain], list) or len(forms[domain]) != len(FORM_IDS):
            raise ValueError('Pilot requires both authored forms in each domain.')
        for index, task in enumerate(forms[domain]):
            if not isinstance(task, dict) or task.get('domain') != domain or task.get('form_id') != FORM_IDS[index]:
                raise ValueError('Pilot forms are missing, duplicated or in the wrong domain.')
            validate_task_contract(task.get('contract'))
            frozen = freeze_task(task)
            if task != frozen:
                raise ValueError('Pilot task contract does not match its exact authored content.')
    return deepcopy(payload)
