"""Explicit owned original recording and review operations for lesson Speaking."""
from flask import Blueprint, jsonify, request, send_file
from repositories.learning_repository import LearningError
from utils.household_access import access_policy


def create_unit_exchange_blueprint(service):
    bp = Blueprint('unit_exchange', __name__, url_prefix='/api/v1/unit-exchanges')

    @bp.get('/<identity>')
    @access_policy('child')
    def read(identity):
        return jsonify(service.read(identity))

    @bp.post('/<identity>/turns/<turn_id>/listened')
    @access_policy('child')
    def listened(identity, turn_id):
        return jsonify(service.listened(identity, turn_id, request.get_json(silent=True)))

    @bp.post('/<identity>/turns/<turn_id>/recording')
    @access_policy('child')
    def recording(identity, turn_id):
        uploaded = request.files.get('audio')
        revision = request.form.get('expected_revision', '')
        if uploaded is None or not revision.isascii() or not revision.isdecimal():
            raise LearningError('invalid_input', 'Choose your original recording and current prompt.')
        try:
            result = service.record(identity, turn_id, uploaded.read(8 * 1024 * 1024 + 1),
                (uploaded.filename or '').rsplit('.', 1)[-1].lower(), request.form.get('submission_id'), int(revision))
        except LearningError:
            raise
        except ValueError as error:
            raise LearningError('invalid_audio', 'Use a playable recording between 0.2 and 60 seconds.') from error
        return jsonify(result)

    @bp.post('/<identity>/review')
    @access_policy('child')
    def review(identity):
        return jsonify(service.review(identity))

    @bp.get('/<identity>/turns/<turn_id>/audio')
    @access_policy('child')
    def original(identity, turn_id):
        response = send_file(service.original_audio(identity, turn_id), conditional=True)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @bp.get('/<identity>/turns/<turn_id>/prompt-audio')
    @access_policy('child')
    def prompt(identity, turn_id):
        response = send_file(service.prompt_audio(identity, turn_id), conditional=True)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @bp.get('/<identity>/closing-audio')
    @access_policy('child')
    def closing(identity):
        response = send_file(service.closing_audio(identity), conditional=True)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    return bp
