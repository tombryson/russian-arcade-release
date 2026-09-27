"""Owned chapter progress with public guest access and CSRF-protected writes."""
from flask import Blueprint, jsonify, request

from contracts.learning import fields
from repositories.learning_repository import LearningError
from services.first_steps import lesson_command, read_chapter, read_lesson
from utils.household_access import access_policy, csrf_token


def create_first_steps_blueprint():
    bp = Blueprint('first_steps', __name__, url_prefix='/api/v1/first-steps')

    @bp.get('')
    @access_policy('public')
    def chapter():
        return jsonify(**read_chapter(), csrf_token=csrf_token())

    @bp.get('/<lesson_id>')
    @access_policy('public')
    def lesson(lesson_id):
        return jsonify(**read_lesson(lesson_id), csrf_token=csrf_token())

    @bp.post('/<lesson_id>/<operation>')
    @access_policy('public')
    def command(lesson_id, operation):
        required = {'start': set(), 'learn': {'teaching_id'}, 'hint': {'question_id'},
                    'answer': {'question_id', 'answer'}, 'continue': {'question_id'}, 'complete': set()}
        if operation not in required:
            raise LearningError('not_found', 'This lesson action was not found.', 404)
        if not request.is_json:
            raise LearningError('json_required', 'Send a JSON object for this operation.', 415)
        data = fields(request.get_json(silent=True), required[operation])
        return jsonify(**lesson_command(lesson_id, operation, data), csrf_token=csrf_token())

    return bp
