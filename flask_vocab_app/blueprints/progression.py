"""Shared level preference, participation wallet and permanent story stops."""
from flask import Blueprint, jsonify, request
from contracts.learning import fields
from repositories.learning_repository import LearningError, require_access, timestamp, transaction
from services.progression import LEVELS, snapshot, journey_read, journey_answer
from services.course_progression import (course_snapshot, checkpoint_start, checkpoint_read,
                                        checkpoint_answer, checkpoint_support, checkpoint_listened,
                                        checkpoint_draft, switch_release)
from services.course_targets import practice_start, practice_get, practice_action
from services.course_followups import writing_followup, capture_vocabulary
from utils.household_access import access_id, access_policy, csrf_token


def create_progression_blueprint(db_path):
    bp = Blueprint('progression', __name__, url_prefix='/api/v1')

    def body(required, optional=()):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise LearningError('invalid_input','Send a JSON object.')
        fields(data, required, optional)
        return data

    def course_profile(conn):
        profile = require_access(conn, access_id(), timestamp())
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='course_enrolments'").fetchone():
            raise LearningError('course_unavailable', 'The course is temporarily unavailable.', 503)
        return profile

    @bp.get('/progression')
    @access_policy('child')
    def read():
        with transaction(db_path) as conn:
            profile = require_access(conn,access_id(),timestamp())
            return jsonify(snapshot(conn,profile['id']) | {'csrf_token':csrf_token()})

    @bp.post('/progression/preferences')
    @access_policy('child')
    def preferences():
        data = body({'level'})
        if data['level'] not in [level['id'] for level in LEVELS]:
            raise LearningError('invalid_level','Choose A1, A2, B1 or B2.')
        with transaction(db_path,write=True) as conn:
            profile = require_access(conn,access_id(),timestamp())
            conn.execute('INSERT INTO progression_preferences(profile_id,preferred_level) VALUES (?,?) ON CONFLICT(profile_id) DO UPDATE SET preferred_level=excluded.preferred_level',(profile['id'],data['level']))
            return jsonify(snapshot(conn,profile['id']))

    @bp.get('/journey/<world_id>')
    @access_policy('child')
    def world(world_id):
        with transaction(db_path) as conn:
            profile = require_access(conn,access_id(),timestamp())
            return jsonify(journey_read(conn,profile['id'],world_id))

    @bp.post('/journey/<world_id>/answer')
    @access_policy('child')
    def answer(world_id):
        data = body({'answer','submission_id'})
        with transaction(db_path,write=True) as conn:
            profile = require_access(conn,access_id(),timestamp())
            return jsonify(journey_answer(conn,profile['id'],world_id,data['answer'],data['submission_id']))

    @bp.get('/course')
    @access_policy('child')
    def course():
        if (set(request.args) - {'release_id', 'band'}
                or any(len(request.args.getlist(name)) != 1 for name in request.args)):
            raise LearningError('invalid_input', 'Choose one course release and level.')
        with transaction(db_path) as conn:
            profile = course_profile(conn)
            return jsonify(course_snapshot(conn, profile['id'], release_id=request.args.get('release_id'),
                                           band=request.args.get('band')) | {'csrf_token': csrf_token()})

    @bp.post('/course/chapters/<chapter_id>/checkpoint')
    @access_policy('child')
    def start_checkpoint(chapter_id):
        data = body({'request_id'}, {'challenge', 'release_id'})
        if 'release_id' in data and not isinstance(data['release_id'], str):
            raise LearningError('invalid_input', 'Course release must be a saved release ID.')
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(checkpoint_start(conn, profile['id'], chapter_id, data['request_id'],
                                            data.get('challenge', False), release_id=data.get('release_id')))

    @bp.get('/course/checkpoints/<attempt_id>')
    @access_policy('child')
    def read_checkpoint(attempt_id):
        with transaction(db_path) as conn:
            profile = course_profile(conn)
            return jsonify(checkpoint_read(conn, profile['id'], attempt_id))

    @bp.post('/course/checkpoints/<attempt_id>/answer')
    @access_policy('child')
    def answer_checkpoint(attempt_id):
        data = body({'answers', 'submission_id'})
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(checkpoint_answer(conn, profile['id'], attempt_id, data['answers'], data['submission_id']))

    @bp.post('/course/checkpoints/<attempt_id>/support')
    @access_policy('child')
    def support_checkpoint(attempt_id):
        data = body({'kind'}, {'question_id'})
        if 'question_id' in data and not isinstance(data['question_id'], str):
            raise LearningError('invalid_input', 'Question ID must name an existing checkpoint question.')
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(checkpoint_support(conn, profile['id'], attempt_id, data['kind'], data.get('question_id')))

    @bp.post('/course/checkpoints/<attempt_id>/listened')
    @access_policy('child')
    def listened_checkpoint(attempt_id):
        body(set())
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(checkpoint_listened(conn, profile['id'], attempt_id))

    @bp.post('/course/releases/<release_id>/switch')
    @access_policy('child')
    def change_course(release_id):
        data = body({'request_id', 'from_release_id'})
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(switch_release(conn, profile['id'], release_id, data['from_release_id'], data['request_id']))

    @bp.post('/course/checkpoints/<attempt_id>/draft')
    @access_policy('child')
    def save_checkpoint_draft(attempt_id):
        data = body({'answers', 'revision'})
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(checkpoint_draft(conn, profile['id'], attempt_id, data['answers'], data['revision']))

    @bp.post('/course/checkpoints/<attempt_id>/writing')
    @access_policy('child')
    def write_reply(attempt_id):
        data = body({'request_id'})
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(writing_followup(conn, profile['id'], attempt_id, data['request_id']))

    @bp.post('/course/checkpoints/<attempt_id>/vocabulary')
    @access_policy('child')
    def keep_word(attempt_id):
        data = body({'word', 'request_id'}, {'lemma', 'pos'})
        with transaction(db_path) as conn:
            profile = course_profile(conn)
        return jsonify(capture_vocabulary(db_path, profile['id'], attempt_id, data['word'], data['request_id'], data.get('lemma'), data.get('pos')))

    @bp.post('/course/chapters/<section_id>/practice')
    @access_policy('child')
    def start_preparation(section_id):
        data = body({'request_id'}, {'release_id'})
        if 'release_id' in data and not isinstance(data['release_id'], str):
            raise LearningError('invalid_input', 'Course release must be a saved release ID.')
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(practice_start(conn, profile['id'], section_id, data['request_id'],
                                          release_id=data.get('release_id'), enrol=True))

    @bp.get('/course/practice/<attempt_id>')
    @access_policy('child')
    def read_preparation(attempt_id):
        with transaction(db_path) as conn:
            profile = course_profile(conn)
            return jsonify(practice_get(conn, profile['id'], attempt_id))

    @bp.post('/course/practice/<attempt_id>/<action>')
    @access_policy('child')
    def act_preparation(attempt_id, action):
        required = {'request_id', 'item_id'} | ({'choice_id'} if action == 'answer' else set())
        data = body(required)
        with transaction(db_path, write=True) as conn:
            profile = course_profile(conn)
            return jsonify(practice_action(conn, profile['id'], attempt_id, action, data, data['request_id']))

    return bp
