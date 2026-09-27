"""One durable first reading activity, with frozen answers and a welcome reward."""
import json
import hashlib

from flask import current_app, session

from repositories.learning_repository import LearningError, encoded, identifier, timestamp, transaction
from services.onboarding import onboarding_state
from services.progression import WELCOME_COINS, award_first_delivery, snapshot as progression_snapshot
from utils.household_access import access_id, csrf_token

GUEST_ATTEMPT_KEY = 'first_delivery_guest_token'
VERSION = 'first-delivery-v2'
# Published versions are immutable: saved first answers refer to these exact
# choice IDs, labels and feedback, including after an explicit lesson restart.
V1_QUESTIONS = (
    {'id': 'greeting', 'passage': 'Барсик пришёл к подруге.\n— Привет, Барсик!\n— Привет, Маша!',
     'prompt': 'What are Barsik and Masha doing?',
     'choices': ({'id': 'greeting', 'text': 'Saying hello'}, {'id': 'thanking', 'text': 'Saying thank you'}, {'id': 'leaving', 'text': 'Saying goodbye'}),
     'answer': 'greeting', 'hint': 'They both say «Привет». It is a greeting used when you meet someone.',
     'feedback': 'They are saying hello to each other. «Привет» means “hello”.'},
    {'id': 'letter', 'passage': 'У Барсика есть письмо.\nОн несёт его тебе.',
     'prompt': 'What is Barsik carrying?',
     'choices': ({'id': 'book', 'text': 'A book'}, {'id': 'letter', 'text': 'A letter'}, {'id': 'apple', 'text': 'An apple'}),
     'answer': 'letter', 'hint': 'Look for the word «письмо». It means a letter that you send.',
     'feedback': 'Barsik is carrying a letter to you. «Письмо» means “a letter”.'},
    {'id': 'thanks', 'passage': 'Маша показала Барсику дорогу.\n— Спасибо, Маша! — сказал Барсик.',
     'prompt': 'Why does Barsik say «Спасибо»?',
     'choices': ({'id': 'hello', 'text': 'He is greeting Masha'}, {'id': 'asking', 'text': 'He is asking for a letter'}, {'id': 'thanks', 'text': 'He is thanking Masha for showing him the way'}),
     'answer': 'thanks', 'hint': '«Спасибо» means “thank you”. Masha has just helped Barsik find his way.',
     'feedback': 'Barsik is thanking Masha for showing him the way. «Спасибо» means “thank you”.'},
)
WORD_CHOICES = ({'id': 'hello', 'text': 'Привет!'}, {'id': 'letter', 'text': 'письмо'}, {'id': 'thanks', 'text': 'Спасибо!'})
QUESTIONS = (
    {'id': 'word-hello', 'title': 'Say hello to Barsik.', 'passage': '',
     'lesson': {'word': 'Привет!', 'meaning': 'Hello!', 'explanation': 'Use «Привет!» to greet someone you know.'},
     'prompt': 'Say hello to Barsik.', 'choices': (WORD_CHOICES[1], WORD_CHOICES[0], WORD_CHOICES[2]),
     'answer': 'hello', 'hint': '«Привет!» is the greeting you just learned.',
     'feedback': '«Привет!» means “hello”. You can use it to greet Barsik.'},
    {'id': 'word-letter', 'title': 'A letter for you.', 'passage': '',
     'lesson': {'word': 'письмо', 'meaning': 'a letter', 'explanation': 'This is what Barsik is carrying for you.'},
     'prompt': 'Choose the Russian word for “a letter”.', 'choices': (WORD_CHOICES[1], WORD_CHOICES[2], WORD_CHOICES[0]),
     'answer': 'letter', 'hint': '«письмо» is the word for a letter.',
     'feedback': '«письмо» means “a letter”. This is what Barsik is carrying.'},
    {'id': 'word-thanks', 'title': 'Say thank you.', 'passage': '',
     'lesson': {'word': 'Спасибо!', 'meaning': 'Thank you!', 'explanation': 'Use «Спасибо!» when someone helps you.'},
     'prompt': 'Say thank you.', 'choices': WORD_CHOICES,
     'answer': 'thanks', 'hint': '«Спасибо!» is how you say thank you.',
     'feedback': '«Спасибо!» means “thank you”.'},
)
VERSIONS = {'first-delivery-v1': V1_QUESTIONS, VERSION: QUESTIONS}


def _owner(conn):
    row = conn.execute(
        'SELECT p.id FROM household_access a JOIN learning_profiles p ON p.id=a.profile_id '
        'WHERE a.id=? AND a.expires_at>? AND p.archived=0 AND p.legacy_user_id IS NULL',
        (access_id(), timestamp()),
    ).fetchone()
    return (row['id'], None) if row else (None, session.get(GUEST_ATTEMPT_KEY))


def _read_attempt(conn, profile_id, guest_token):
    if profile_id:
        row = conn.execute('SELECT * FROM first_delivery_attempts WHERE profile_id=?', (profile_id,)).fetchone()
    elif guest_token:
        row = conn.execute('SELECT * FROM first_delivery_attempts WHERE profile_id IS NULL AND guest_token=?', (guest_token,)).fetchone()
    else:
        row = None
    if row and row['version'] not in VERSIONS:
        raise LearningError('activity_version_changed', 'Reload to open your saved first delivery.', 409)
    return row


def _serialize_attempt(row):
    questions = VERSIONS[row['version']]
    answers = json.loads(row['answers_json'])
    hints = json.loads(row['hints_json'])
    learned = json.loads(row['learned_json'])
    acknowledged = json.loads(row['acknowledged_json'])
    teaching = row['version'] == VERSION and len(learned) < len(questions)
    index = len(learned) if teaching else len(acknowledged)
    question = questions[index] if index < len(questions) else None
    phase = ('completed' if row['completed_at'] is not None else 'ready' if question is None
             else 'learn' if teaching else 'feedback' if question['id'] in answers else 'question')
    public_question = None
    if question:
        public_question = {key: question[key] for key in ('id', 'passage', 'prompt', 'choices')}
        public_question['title'] = question.get('title', question['prompt'])
        if phase == 'learn':
            public_question['lesson'] = question['lesson']
            public_question['choices'] = []
        if question['id'] in hints:
            public_question['hint'] = question['hint']
    public_answers = []
    for item in questions:
        saved = answers.get(item['id'])
        if saved:
            public_answers.append({
                'question_id': item['id'], 'answer': saved['answer'],
                'answer_text': next(choice['text'] for choice in item['choices'] if choice['id'] == saved['answer']),
                'correct': saved['correct'], 'correct_answer': next(choice['text'] for choice in item['choices'] if choice['id'] == item['answer']),
                'feedback': item['feedback'], 'hint_used': saved['hint_used'],
                'acknowledged': item['id'] in acknowledged,
            })
    return {'id': row['id'], 'version': row['version'], 'phase': phase, 'question_index': index, 'learned_count': len(learned), 'total_questions': len(questions),
            'question': public_question, 'answers': public_answers, 'completed_at': row['completed_at']}


def _previous_attempt(row):
    return json.loads(row['previous_attempt_json']) if row['previous_attempt_json'] else None


def _completed_attempt(row):
    # A guest's earned welcome receipt survives starting the revised lesson.
    # Claim the first completion's evidence, not later practice with the words.
    previous = _previous_attempt(row)
    if previous and previous['completed_at'] is not None:
        return previous
    return row if row['completed_at'] is not None else None


def _public_state(conn, profile_id, row, *, awarded_now=False):
    result = {'profile_id': profile_id, 'attempt': None, 'previous_attempt': None, 'pending_reward': 0, 'reward': None, 'teaching_cards': []}
    if not row:
        return result
    result['attempt'] = _serialize_attempt(row)
    if row['version'] == 'first-delivery-v2' and row['completed_at'] is not None:
        result['teaching_cards'] = [{'id': question['id'], 'title': question['title'], **question['lesson']}
                                    for question in VERSIONS['first-delivery-v2']]
    previous = _previous_attempt(row)
    if previous:
        # Only presentation fields leave the server; never return raw archive
        # JSON, owner credentials or the guest token stored in that snapshot.
        result['previous_attempt'] = _serialize_attempt(previous)
    if _completed_attempt(row) is not None:
        result['reward'] = {'amount': WELCOME_COINS, 'status': 'credited' if profile_id else 'pending', 'awarded_now': awarded_now}
        if profile_id:
            result['progression'] = progression_snapshot(conn, profile_id)
        else:
            result['pending_reward'] = WELCOME_COINS
    return result


def read_practice():
    with transaction(current_app.config['DB_PATH']) as conn:
        profile_id, guest_token = _owner(conn)
        return _public_state(conn, profile_id, _read_attempt(conn, profile_id, guest_token))


def _require_introduction():
    state = onboarding_state()
    if not state['coins_introduced'] or not state['progress_introduced']:
        raise LearningError('introduction_required', 'Meet Lingo coins and your progress before starting the first delivery.', 409)
    return state


def start_practice(*, restart=False):
    if type(restart) is not bool:
        raise LearningError('invalid_restart', 'Choose whether to start the revised lesson.')
    state = _require_introduction()
    if state['profile_id'] is None and not session.get(GUEST_ATTEMPT_KEY):
        # The established CSRF token is server-generated and rotated on identity
        # changes. Derivation makes simultaneous first starts use one owner;
        # this token is kept only in the server session, never accepted as input.
        session[GUEST_ATTEMPT_KEY] = hashlib.sha256(('first-delivery:' + csrf_token()).encode()).hexdigest()
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile_id, guest_token = _owner(conn)
        if profile_id != state['profile_id']:
            raise LearningError('profile_changed', 'Your profile changed. Reopen this page before continuing.', 409)
        row = _read_attempt(conn, profile_id, guest_token)
        if row:
            if restart and row['version'] != VERSION:
                now = timestamp()
                conn.execute('UPDATE first_delivery_attempts SET previous_attempt_json=?,version=?,answers_json=?,hints_json=?,learned_json=?,acknowledged_json=?,completed_at=NULL,updated_at=? WHERE id=?',
                             (encoded(dict(row)), VERSION, '{}', '[]', '[]', '[]', now, row['id']))
                row = _read_attempt(conn, profile_id, guest_token)
            return _public_state(conn, profile_id, row)
        now = timestamp()
        conn.execute('INSERT INTO first_delivery_attempts(id,profile_id,guest_token,version,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                     (identifier(), profile_id, guest_token, VERSION, now, now))
        return _public_state(conn, profile_id, _read_attempt(conn, profile_id, guest_token))


def practice_command(operation, data):
    _require_introduction()
    with transaction(current_app.config['DB_PATH'], write=True) as conn:
        profile_id, guest_token = _owner(conn)
        row = _read_attempt(conn, profile_id, guest_token)
        if not row:
            raise LearningError('practice_not_started', 'Start your first delivery before continuing.', 409)
        if operation == 'complete' and row['completed_at'] is not None:
            return _public_state(conn, profile_id, row)
        questions = VERSIONS[row['version']]
        question_ids = tuple(question['id'] for question in questions)
        answers = json.loads(row['answers_json'])
        hints = json.loads(row['hints_json'])
        learned = json.loads(row['learned_json'])
        acknowledged = json.loads(row['acknowledged_json'])
        now = timestamp()
        awarded_now = False
        if operation == 'complete':
            if acknowledged != list(question_ids):
                raise LearningError('feedback_required', 'Answer each question and continue after its feedback before finishing.', 409)
            conn.execute('UPDATE first_delivery_attempts SET completed_at=?,updated_at=? WHERE id=?', (now, now, row['id']))
            if profile_id:
                finished = _completed_attempt(_read_attempt(conn, profile_id, guest_token))
                awarded_now = bool(award_first_delivery(conn, profile_id, finished['id'], json.loads(finished['answers_json']), now=now, content_version=finished['version']))
        else:
            question_id = data['question_id']
            if not isinstance(question_id, str) or question_id not in question_ids:
                raise LearningError('invalid_question', 'Choose a question from this first delivery.')
            question = questions[question_ids.index(question_id)]
            saved = answers.get(question_id)
            if operation == 'answer' and saved:
                if data['answer'] != saved['answer']:
                    raise LearningError('answer_already_saved', 'Your first answer is saved. Continue after the feedback.', 409)
                return _public_state(conn, profile_id, row)
            if operation == 'hint' and question_id in hints:
                return _public_state(conn, profile_id, row)
            if operation == 'continue' and question_id in acknowledged:
                return _public_state(conn, profile_id, row)
            if operation == 'learn' and question_id in learned:
                return _public_state(conn, profile_id, row)
            cursor = len(learned) if operation == 'learn' else len(acknowledged)
            if row['completed_at'] is not None or cursor >= len(questions) or question_id != question_ids[cursor]:
                raise LearningError('wrong_question', 'Continue with the current question in your first delivery.', 409)
            if row['version'] == VERSION and len(learned) < len(questions) and operation != 'learn':
                raise LearningError('lesson_required', 'Meet the three Russian words before trying to remember them.', 409)
            if operation == 'learn':
                if 'lesson' not in question:
                    raise LearningError('lesson_unavailable', 'Start the revised lesson to learn your first words.', 409)
                learned.append(question_id)
            elif operation == 'hint':
                if saved:
                    raise LearningError('answer_already_saved', 'Your first answer is saved. Read its feedback before continuing.', 409)
                hints.append(question_id)
            elif operation == 'answer':
                if not isinstance(data['answer'], str) or data['answer'] not in [choice['id'] for choice in question['choices']]:
                    raise LearningError('invalid_answer', 'Choose one of the available answers.')
                answers[question_id] = {'answer': data['answer'], 'correct': data['answer'] == question['answer'],
                                        'hint_used': question_id in hints, 'answered_at': now}
            elif operation == 'continue':
                if not saved:
                    raise LearningError('answer_required', 'Answer this question before continuing.', 409)
                acknowledged.append(question_id)
            else:
                raise LearningError('invalid_action', 'Choose a supported first-delivery action.')
            conn.execute('UPDATE first_delivery_attempts SET answers_json=?,hints_json=?,learned_json=?,acknowledged_json=?,updated_at=? WHERE id=?',
                         (encoded(answers), encoded(hints), encoded(learned), encoded(acknowledged), now, row['id']))
        return _public_state(conn, profile_id, _read_attempt(conn, profile_id, guest_token), awarded_now=awarded_now)


def claim_guest_practice(conn, profile_id, guest_token, *, now=None):
    """Called only inside creation of a new personal profile, never selection."""
    if not isinstance(guest_token, str) or not guest_token:
        return
    row = _read_attempt(conn, None, guest_token)
    if not row:
        return
    now = timestamp() if now is None else now
    conn.execute('UPDATE first_delivery_attempts SET profile_id=?,guest_token=NULL,updated_at=? WHERE id=? AND profile_id IS NULL',
                 (profile_id, now, row['id']))
    completed = _completed_attempt(row)
    if completed is not None:
        award_first_delivery(conn, profile_id, completed['id'], json.loads(completed['answers_json']), now=now, content_version=completed['version'])
    from services.first_steps import claim_guest_lessons
    claim_guest_lessons(conn, profile_id, guest_token, now=now)
    from services.journey_games import claim_guest_games, sync_unlocks
    claim_guest_games(conn, profile_id, guest_token, now=now)
    sync_unlocks(conn, profile_id, None, now=now)
