"""Optional supported practice; never changes a first answer or its rewards."""
import json
import re

from repositories.learning_repository import LearningError, encoded, identifier, timestamp

OPERATIONS = {'retry', 'review', 'practice_answer', 'practice_continue', 'practice_exit', 'practice_hint', 'practice_transcript'}


def command(conn, row, operation, data):
    from services.journey_games import assess_answer, normalise_answer, movement_path
    content = json.loads(row['content_json'])
    answers = json.loads(row['answers_json'])
    acknowledged = json.loads(row['acknowledged_json'])
    support = json.loads(row['support_json'])
    rounds = {item['id']: item for item in content['rounds']}
    practice = support.get('_practice', {})
    now = timestamp()
    if operation == 'review':
        if row['completed_at'] is None:
            raise LearningError('game_incomplete', 'Finish the game before reviewing missed items.', 409)
        queue = [key for key, item in rounds.items() if not assess_answer(item, answers[key]['answer'])['correct']]
        if not queue:
            return
        if not practice.get('active'):
            practice = {'active': True, 'mode': 'review', 'queue': queue, 'index': 0}
    elif operation == 'retry':
        key = data['round_id']
        current = list(rounds)[len(acknowledged)] if len(acknowledged) < len(rounds) else None
        if row['completed_at'] is not None or key != current or key not in answers:
            raise LearningError('wrong_round', 'Retry the current checked question.', 409)
        if assess_answer(rounds[key], answers[key]['answer'])['correct']:
            raise LearningError('already_correct', 'This answer was correct. Continue to the next question.', 409)
        if not practice.get('active'):
            practice = {'active': True, 'mode': 'correction', 'queue': [key], 'index': 0}
    elif operation == 'practice_exit':
        practice['active'] = False
    else:
        if not practice.get('active'):
            raise LearningError('practice_finished', 'This review has finished.', 409)
        key = practice['queue'][practice['index']]
        if data['round_id'] != key:
            raise LearningError('wrong_round', 'Continue with the current practice question.', 409)
        if operation in ('practice_hint', 'practice_transcript'):
            practice['hint' if operation == 'practice_hint' else 'transcript'] = True
        elif operation == 'practice_answer':
            request_id = data['request_id']
            if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id):
                raise LearningError('invalid_request', 'Try checking the answer again.')
            answer = normalise_answer(rounds[key], data['answer'], row['game_id'])
            prior = conn.execute('SELECT round_id,answer_json FROM journey_game_corrections WHERE session_id=? AND request_id=?',
                                 (row['id'], request_id)).fetchone()
            if prior:
                if prior['round_id'] != key or json.loads(prior['answer_json']) != answer:
                    raise LearningError('idempotency_conflict', 'This check already has a different answer.', 409)
                return
            if practice.get('answer') is not None:
                raise LearningError('practice_checked', 'Continue after checking this answer.', 409)
            if row['game_id'] == 'directions':
                movement_path(rounds[key]['board'], answer)
            conn.execute('INSERT INTO journey_game_corrections VALUES (?,?,?,?,?,?)',
                         (identifier(), row['id'], key, request_id, encoded(answer), now))
            practice['answer'] = answer
        elif operation == 'practice_continue':
            # Continuing without an answer is an explicit skip, not evidence.
            for field in ('answer', 'hint', 'transcript'):
                practice.pop(field, None)
            practice['index'] += 1
            if practice['index'] == len(practice['queue']):
                practice['active'] = False
                if practice['mode'] == 'correction' and key not in acknowledged:
                    acknowledged.append(key)
    support['_practice'] = practice
    conn.execute('UPDATE journey_game_sessions SET support_json=?,acknowledged_json=?,updated_at=? WHERE id=?',
                 (encoded(support), encoded(acknowledged), now, row['id']))
