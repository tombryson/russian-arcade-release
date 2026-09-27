"""Public presentation milestones, with server-selected profile ownership."""
from flask import Blueprint, jsonify, request

from contracts.learning import fields
from repositories.learning_repository import LearningError
from services.onboarding import introduce_milestone, onboarding_state
from services.first_delivery import practice_command, read_practice, start_practice
from utils.household_access import access_policy, csrf_token


def create_onboarding_blueprint():
    bp = Blueprint('onboarding', __name__)

    @bp.app_context_processor
    def presentation_context():
        return {'onboarding_state': onboarding_state()}

    @bp.get('/api/v1/onboarding')
    @access_policy('public')
    def read():
        return jsonify(**onboarding_state(), csrf_token=csrf_token())

    @bp.post('/api/v1/onboarding')
    @access_policy('public')
    def introduce():
        if not request.is_json:
            raise LearningError('json_required', 'Send a JSON object for this operation.', 415)
        data = fields(request.get_json(silent=True), {'milestone'})
        return jsonify(**introduce_milestone(data['milestone']), csrf_token=csrf_token())

    @bp.get('/api/v1/onboarding/practice')
    @access_policy('public')
    def practice_read():
        return jsonify(**read_practice(), csrf_token=csrf_token())

    @bp.post('/api/v1/onboarding/practice/<operation>')
    @access_policy('public')
    def practice_write(operation):
        required = {'start': set(), 'learn': {'question_id'}, 'hint': {'question_id'}, 'answer': {'question_id', 'answer'},
                    'continue': {'question_id'}, 'complete': set()}
        if operation not in required:
            raise LearningError('not_found', 'This first-delivery action was not found.', 404)
        if not request.is_json:
            raise LearningError('json_required', 'Send a JSON object for this operation.', 415)
        data = fields(request.get_json(silent=True), required[operation], {'restart'} if operation == 'start' else set())
        result = start_practice(restart=data.get('restart', False)) if operation == 'start' else practice_command(operation, data)
        return jsonify(**result, csrf_token=csrf_token())

    return bp
