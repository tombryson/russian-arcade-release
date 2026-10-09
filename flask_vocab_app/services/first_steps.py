"""A finite optional chapter with frozen teaching, answers and reward receipts."""
import json
from pathlib import Path

from flask import current_app

from repositories.learning_repository import LearningError, encoded, identifier, timestamp, transaction
from services.first_delivery import _completed_attempt, _owner
from services.intro_hints import hint_for
from services.progression import RULES, WELCOME_COINS, award, snapshot, unlock_worlds

LEGACY_VERSION = 'first-steps-v1'
DEFAULT_VERSION = 'first-steps-v2'
LEGACY_CHAPTER_ID = 'first-steps'
CHAPTER_ID = 'first-steps-v2'
LEGACY_LESSON_IDS = ('hello', 'bag', 'directions', 'help', 'set-off')
LESSON_IDS = ('hello', 'bag', 'introductions', 'gender', 'ownership')
CONTENT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'first_steps.json'
EDITIONS = {
    LEGACY_VERSION: {'chapter_id': LEGACY_CHAPTER_ID, 'lesson_ids': LEGACY_LESSON_IDS, 'path': CONTENT_PATH},
    DEFAULT_VERSION: {'chapter_id': CHAPTER_ID, 'lesson_ids': LESSON_IDS, 'path': CONTENT_PATH.with_name('first_steps_v2.json')},
}
HELLO = {'id': 'hello', 'position': 1, 'title': 'Hello, Barsik!',
         'description': 'Meet your guide and learn your first Russian word.',
         'version': 'first-delivery-v2', 'chapter_id': LEGACY_CHAPTER_ID,
         'vocabulary': [
             {'lemma': 'привет', 'form': 'Привет', 'pos': 'INTJ', 'sentence': 'Привет, Барсик!', 'translation': 'Hello, Barsik!', 'target_meaning': 'hello', 'grammar': {}},
             {'lemma': 'письмо', 'form': 'письмо', 'pos': 'NOUN', 'sentence': 'Это письмо.', 'translation': 'This is a letter.', 'target_meaning': 'a letter',
              'grammar': {'case': 'nomn', 'number': 'sing', 'gender': 'neut', 'animacy': 'inan'}},
             {'lemma': 'спасибо', 'form': 'Спасибо', 'pos': 'INTJ', 'sentence': 'Спасибо, Барсик!', 'translation': 'Thank you, Barsik!', 'target_meaning': 'thank you', 'grammar': {}},
         ]}


def resolve_version(version=None, lesson_id=None):
    if version is None:
        version = LEGACY_VERSION if lesson_id in set(LEGACY_LESSON_IDS) - set(LESSON_IDS) else DEFAULT_VERSION
    if not isinstance(version, str) or version not in EDITIONS:
        raise LearningError('invalid_version', 'Choose an available First steps edition.', 400)
    return version


def chapter_href(version):
    return '#first-steps?version=' + resolve_version(version)


def lesson_href(lesson_id, version):
    return '#first-delivery' if lesson_id == 'hello' else '#first-steps/' + lesson_id + '?version=' + resolve_version(version)


def chapter_content(version=DEFAULT_VERSION):
    version = resolve_version(version)
    edition = EDITIONS[version]
    content = json.loads(edition['path'].read_text(encoding='utf-8'))
    if (content['id'] != edition['chapter_id'] or content['version'] != version
            or tuple(lesson['id'] for lesson in content['lessons']) != edition['lesson_ids'][1:]):
        raise LearningError('chapter_unavailable', 'The first chapter is being prepared.', 503)
    return content


def _hello(conn, profile_id, guest_token):
    if profile_id:
        return conn.execute('SELECT * FROM first_delivery_attempts WHERE profile_id=?', (profile_id,)).fetchone()
    if guest_token:
        return conn.execute('SELECT * FROM first_delivery_attempts WHERE profile_id IS NULL AND guest_token=?', (guest_token,)).fetchone()
    return None


def _hello_complete(row):
    return bool(row and row['version'] == 'first-delivery-v2' and row['completed_at'] is not None)


def _rows(conn, profile_id, guest_token, chapter_id):
    if profile_id:
        rows = conn.execute('SELECT * FROM first_steps_attempts WHERE profile_id=? AND chapter_id=?', (profile_id, chapter_id)).fetchall()
    elif guest_token:
        rows = conn.execute('SELECT * FROM first_steps_attempts WHERE profile_id IS NULL AND guest_token=? AND chapter_id=?', (guest_token, chapter_id)).fetchall()
    else:
        rows = []
    return {row['lesson_id']: row for row in rows}


def completed_lessons(conn, profile_id, guest_token=None, *, version=None):
    """Owned frozen content; callers can request an edition or retained history.

    Games retain historical vocabulary. Chapter practice explicitly selects one
    edition so completion of the old bag never completes the revised chapter.
    """
    versions = [resolve_version(version)] if version is not None else list(EDITIONS)
    lessons = [dict(HELLO)] if _hello_complete(_hello(conn, profile_id, guest_token)) else []
    for selected in versions:
        lessons.extend(json.loads(row['content_json']) for row in _rows(conn, profile_id, guest_token, EDITIONS[selected]['chapter_id']).values()
                       if row['completed_at'] is not None)
    return sorted(lessons, key=lambda lesson: lesson['position'])


def _chapter(conn, profile_id, guest_token, content, version):
    edition = EDITIONS[version]
    rows = _rows(conn, profile_id, guest_token, edition['chapter_id'])
    hello = _hello(conn, profile_id, guest_token)
    lessons = []
    previous_complete = True
    for authored in (HELLO, *content['lessons']):
        lesson_id = authored['id']
        row = rows.get(lesson_id)
        lesson = json.loads(row['content_json']) if row else authored
        complete = _hello_complete(hello) if lesson_id == 'hello' else bool(row and row['completed_at'] is not None)
        active = bool(hello) if lesson_id == 'hello' else bool(row)
        status = 'completed' if complete else 'active' if active and previous_complete else 'available' if previous_complete else 'locked'
        lessons.append({key: lesson[key] for key in ('id', 'position', 'title', 'description')} |
                       {'status': status, 'href': lesson_href(lesson_id, version)})
        previous_complete = complete
    completed_count = sum(lesson['status'] == 'completed' for lesson in lessons)
    pending = 0
    if profile_id is None:
        pending = sum(RULES['activity_coins'] for row in rows.values() if row['completed_at'] is not None)
        if hello and _completed_attempt(hello) is not None:
            pending += WELCOME_COINS
    result = {'profile_id': profile_id, 'chapter_id': edition['chapter_id'], 'version': version, 'title': content['title'],
              'lessons': lessons, 'next_lesson': next((lesson for lesson in lessons if lesson['status'] in ('available', 'active')), None),
              'completed_count': completed_count, 'complete': completed_count == len(edition['lesson_ids']), 'pending_reward': pending}
    if version == LEGACY_VERSION:
        result['updated_chapter_href'] = chapter_href(DEFAULT_VERSION)
    else:
        previous = _rows(conn, profile_id, guest_token, LEGACY_CHAPTER_ID)
        if previous:
            result['previous_chapter'] = {'title': 'Earlier First steps', 'href': chapter_href(LEGACY_VERSION),
                                          'completed_count': sum(row['completed_at'] is not None for row in previous.values()) + int(_hello_complete(hello))}
    return result


def read_chapter(version=None):
    version = resolve_version(version)
    content = chapter_content(version)
    with transaction(current_app.config['DB_PATH']) as conn:
        return _chapter(conn, *_owner(conn), content, version)


def _available(chapter, lesson_id):
    lesson = next((lesson for lesson in chapter['lessons'] if lesson['id'] == lesson_id), None)
    if not lesson or lesson_id == 'hello':
        raise LearningError('not_found', 'Open your first words from the chapter overview.' if lesson_id == 'hello' else 'This lesson was not found.', 404)
    if lesson['status'] == 'locked':
        raise LearningError('lesson_locked', 'Finish the previous lesson before opening this one.', 409)
    return lesson


_BAG_LISTENING_PRESENTATION = 'bag-listening-sentences-v1'


def _question_presentation(version, item, saved=None):
    """Repair the original listening choices without relabelling past answers."""
    if saved and saved.get('presentation_version') != _BAG_LISTENING_PRESENTATION:
        return item
    original = {'map': 'карта', 'bag': 'сумка', 'letter': 'письмо'}
    if (version == DEFAULT_VERSION and item['id'] == 'bag-listen-object'
            and item.get('audio_text') == 'Это сумка.'
            and {choice['id']: choice['text'] for choice in item['choices']} == original):
        return {**item, 'prompt': 'Listen. Which sentence did you hear?',
                'feedback': 'This is a bag.',
                'choices': [{**choice, 'text': 'Это ' + choice['text'] + '.'} for choice in item['choices']]}
    return item


def _attempt(row):
    lesson = json.loads(row['content_json'])
    cards, questions = lesson['teaching'], lesson['questions']
    learned, acknowledged = json.loads(row['learned_json']), json.loads(row['acknowledged_json'])
    answers, hints = json.loads(row['answers_json']), json.loads(row['hints_json'])
    teaching_index, question_index = len(learned), len(acknowledged)
    phase = ('completed' if row['completed_at'] is not None else 'learn' if teaching_index < len(cards)
             else 'ready' if question_index == len(questions) else 'feedback' if questions[question_index]['id'] in answers else 'question')
    question = None
    if phase in ('question', 'feedback'):
        frozen = questions[question_index]
        item = _question_presentation(row['version'], frozen, answers.get(frozen['id']))
        question = {key: item[key] for key in ('id', 'prompt', 'passage', 'choices', 'visual', 'audio_url', 'choices_language') if key in item}
        hint = hint_for(row['version'], item['id'])
        question['hint_available'] = bool(hint)
        if hint and item['id'] in hints:
            question['hint'] = hint
        if phase == 'feedback':
            question.update({key: item[key] for key in ('audio_text', 'transcript') if key in item})
    public_answers = []
    for item in questions:
        saved = answers.get(item['id'])
        if saved:
            item = _question_presentation(row['version'], item, saved)
            public_answers.append({'question_id': item['id'], 'answer': saved['answer'],
                                   'answer_text': next(choice['text'] for choice in item['choices'] if choice['id'] == saved['answer']),
                                   'correct': saved['correct'], 'correct_answer': next(choice['text'] for choice in item['choices'] if choice['id'] == item['answer']),
                                   'feedback': item['feedback'], 'hint_used': saved['hint_used'], 'acknowledged': item['id'] in acknowledged})
    return {'id': row['id'], 'version': row['version'], 'phase': phase,
            'teaching_index': teaching_index, 'total_teaching': len(cards),
            'question_index': question_index, 'total_questions': len(questions),
            'teaching': cards[teaching_index] if phase == 'learn' else None, 'question': question,
            'answers': public_answers, 'completed_at': row['completed_at']}


def _lesson_state(conn, profile_id, guest_token, content, lesson_id, version, *, awarded_now=False):
    chapter = _chapter(conn, profile_id, guest_token, content, version)
    summary = _available(chapter, lesson_id)
    row = _rows(conn, profile_id, guest_token, EDITIONS[version]['chapter_id']).get(lesson_id)
    result = {'profile_id': profile_id, 'version': version, 'chapter_id': EDITIONS[version]['chapter_id'], 'lesson': {key: value for key, value in summary.items() if key != 'status'} | {'total_lessons': len(EDITIONS[version]['lesson_ids'])},
              'attempt': _attempt(row) if row else None, 'reward': None, 'teaching_cards': [], 'resolution': None,
              'next_lesson': chapter['next_lesson'], 'chapter_complete': chapter['complete'], 'pending_reward': chapter['pending_reward']}
    if version == LEGACY_VERSION:
        result['updated_chapter_href'] = chapter_href(DEFAULT_VERSION)
        if lesson_id in LESSON_IDS:
            result['updated_lesson_href'] = lesson_href(lesson_id, DEFAULT_VERSION)
    elif lesson_id in LEGACY_LESSON_IDS:
        previous = _rows(conn, profile_id, guest_token, LEGACY_CHAPTER_ID).get(lesson_id)
        if previous:
            result['previous_lesson'] = {'title': json.loads(previous['content_json'])['title'], 'href': lesson_href(lesson_id, LEGACY_VERSION)}
    if row and row['completed_at'] is not None:
        frozen = json.loads(row['content_json'])
        result['reward'] = {'amount': row['reward_amount'] if profile_id else RULES['activity_coins'],
                            'status': 'credited' if profile_id else 'pending', 'awarded_now': awarded_now}
        result['teaching_cards'] = frozen['teaching']
        result['resolution'] = frozen.get('resolution')
        if profile_id:
            result['progression'] = snapshot(conn, profile_id)
    return result


def read_lesson(lesson_id, version=None):
    version = resolve_version(version, lesson_id)
    content = chapter_content(version)
    with transaction(current_app.config['DB_PATH']) as conn:
        return _lesson_state(conn, *_owner(conn), content, lesson_id, version)


def _credit(conn, profile_id, row, now):
    lesson = json.loads(row['content_json'])
    amount = award(conn, profile_id, activity='first_steps', content_key=f'{row["chapter_id"]}:{row["lesson_id"]}:{row["version"]}',
                   source_key=row['id'], title=lesson['title'], target_level='A1', now=now,
                   evidence={'basis': 'guided_intro_practice' if row['version'] == DEFAULT_VERSION else 'first_unassisted_answers', 'lesson_id': row['lesson_id']})
    conn.execute('UPDATE first_steps_attempts SET reward_amount=? WHERE id=?', (amount, row['id']))
    if row['chapter_id'] == LEGACY_CHAPTER_ID and row['lesson_id'] == 'set-off':
        # This lesson teaches and checks the clerk's direction to the market.
        # Its own saved receipt establishes the same story stop; old scene
        # answers and earlier checkpoint timestamps remain untouched.
        conn.execute('INSERT INTO journey_progress(profile_id,world_id,unlocked_at,visited_at,completed_at) VALUES (?,?,?,?,?) '
                     'ON CONFLICT(profile_id,world_id) DO UPDATE SET unlocked_at=COALESCE(journey_progress.unlocked_at,excluded.unlocked_at),'
                     'visited_at=COALESCE(journey_progress.visited_at,excluded.visited_at),completed_at=COALESCE(journey_progress.completed_at,excluded.completed_at)',
                     (profile_id, 'post-office', now, now, now))
        unlock_worlds(conn, profile_id, now)
    return amount


def lesson_command(lesson_id, operation, data, version=None):
    version = resolve_version(version, lesson_id)
    chapter_id = EDITIONS[version]['chapter_id']
    content = chapter_content(version)
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile_id, guest_token = _owner(conn)
        chapter = _chapter(conn, profile_id, guest_token, content, version)
        _available(chapter, lesson_id)
        row = _rows(conn, profile_id, guest_token, EDITIONS[version]['chapter_id']).get(lesson_id)
        now = timestamp()
        if operation == 'start':
            if row is None:
                lesson = next(lesson for lesson in content['lessons'] if lesson['id'] == lesson_id) | {'chapter_id': chapter_id, 'version': version}
                conn.execute('INSERT INTO first_steps_attempts(id,profile_id,guest_token,chapter_id,lesson_id,version,content_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                             (identifier(), profile_id, guest_token, chapter_id, lesson_id, version, encoded(lesson), now, now))
            return _lesson_state(conn, profile_id, guest_token, content, lesson_id, version)
        if row is None:
            raise LearningError('lesson_not_started', 'Start this lesson before continuing.', 409)
        if row['completed_at'] is not None:
            # Completed lessons are read-only; replaying commands cannot reset
            # first answers, add observations or create a fresh daily claim.
            return _lesson_state(conn, profile_id, guest_token, content, lesson_id, version)
        lesson = json.loads(row['content_json'])
        cards, questions = lesson['teaching'], lesson['questions']
        learned, acknowledged = json.loads(row['learned_json']), json.loads(row['acknowledged_json'])
        answers, hints = json.loads(row['answers_json']), json.loads(row['hints_json'])
        awarded_now = False
        if operation == 'complete':
            if len(learned) != len(cards) or acknowledged != [question['id'] for question in questions]:
                raise LearningError('feedback_required', 'Finish each question and continue after its feedback before completing the lesson.', 409)
            conn.execute('UPDATE first_steps_attempts SET completed_at=?,updated_at=? WHERE id=?', (now, now, row['id']))
            if profile_id:
                completed = _rows(conn, profile_id, guest_token, chapter_id)[lesson_id]
                awarded_now = bool(_credit(conn, profile_id, completed, now))
        elif operation == 'learn':
            teaching_id = data['teaching_id']
            if not isinstance(teaching_id, str) or teaching_id not in [card['id'] for card in cards]:
                raise LearningError('invalid_teaching', 'Choose a word from this lesson.')
            if teaching_id in learned:
                return _lesson_state(conn, profile_id, guest_token, content, lesson_id, version)
            if len(learned) >= len(cards) or teaching_id != cards[len(learned)]['id']:
                raise LearningError('wrong_teaching', 'Continue with the current teaching card.', 409)
            learned.append(teaching_id)
        else:
            question_id = data['question_id']
            question = next((question for question in questions if question['id'] == question_id), None) if isinstance(question_id, str) else None
            if question is None:
                raise LearningError('invalid_question', 'Choose a question from this lesson.')
            if len(learned) != len(cards):
                raise LearningError('lesson_required', 'Meet the words before trying to remember them.', 409)
            saved = answers.get(question_id)
            if operation == 'answer' and saved:
                if data['answer'] != saved['answer']:
                    raise LearningError('answer_already_saved', 'Your first answer is saved. Continue after the feedback.', 409)
                return _lesson_state(conn, profile_id, guest_token, content, lesson_id, version)
            if operation in ('hint', 'review') and not hint_for(row['version'], question_id):
                raise LearningError('hint_unavailable', 'Try an answer to see its explanation.', 409)
            if (operation in ('hint', 'review') and question_id in hints) or (operation == 'continue' and question_id in acknowledged):
                return _lesson_state(conn, profile_id, guest_token, content, lesson_id, version)
            if len(acknowledged) >= len(questions) or question_id != questions[len(acknowledged)]['id']:
                raise LearningError('wrong_question', 'Continue with the current question.', 409)
            if operation in ('hint', 'review'):
                if saved:
                    raise LearningError('answer_already_saved', 'Your first answer is saved. Read its feedback before continuing.', 409)
                hints.append(question_id)
            elif operation == 'answer':
                if not isinstance(data['answer'], str) or data['answer'] not in [choice['id'] for choice in question['choices']]:
                    raise LearningError('invalid_answer', 'Choose one of the available answers.')
                answers[question_id] = {'answer': data['answer'], 'correct': data['answer'] == question['answer'],
                                        'hint_used': question_id in hints, 'answered_at': now}
                if _question_presentation(row['version'], question) != question:
                    # Remember which labels were shown for this new response;
                    # older responses still display their frozen noun labels.
                    answers[question_id]['presentation_version'] = _BAG_LISTENING_PRESENTATION
            elif operation == 'continue':
                if saved is None:
                    raise LearningError('answer_required', 'Answer this question before continuing.', 409)
                acknowledged.append(question_id)
        if operation != 'complete':
            conn.execute('UPDATE first_steps_attempts SET learned_json=?,answers_json=?,hints_json=?,acknowledged_json=?,updated_at=? WHERE id=?',
                         (encoded(learned), encoded(answers), encoded(hints), encoded(acknowledged), now, row['id']))
        return _lesson_state(conn, profile_id, guest_token, content, lesson_id, version, awarded_now=awarded_now)


def claim_guest_lessons(conn, profile_id, guest_token, *, now=None):
    """Transfer only during new personal profile creation, after lesson one."""
    now = timestamp() if now is None else now
    for edition in EDITIONS.values():
        rows = _rows(conn, None, guest_token, edition['chapter_id'])
        for lesson_id in edition['lesson_ids'][1:]:
            row = rows.get(lesson_id)
            if row is None:
                continue
            conn.execute('UPDATE first_steps_attempts SET profile_id=?,guest_token=NULL,updated_at=? WHERE id=? AND profile_id IS NULL',
                         (profile_id, now, row['id']))
            if row['completed_at'] is not None:
                _credit(conn, profile_id, row, now)
