"""Lesson game audio: owned reads and explicit, CSRF-protected preparation."""
from flask import Blueprint, jsonify, request, send_file

from contracts.learning import fields
from repositories.learning_repository import LearningError
from utils.household_access import access_policy, csrf_token


def create_journey_game_media_blueprint(service):
    bp = Blueprint('journey_game_media', __name__, url_prefix='/api/v1/games/media')

    @bp.get('/<key>/status')
    @access_policy('public')
    def status(key):
        return jsonify(**service.status(key), csrf_token=csrf_token())

    @bp.post('/<key>/prepare')
    @access_policy('public')
    def prepare(key):
        if not request.is_json:
            raise LearningError('json_required', 'Send a JSON object for this operation.', 415)
        fields(request.get_json(silent=True), set())
        return jsonify(**service.prepare(key), csrf_token=csrf_token())

    @bp.get('/<key>')
    @access_policy('public')
    def asset(key):
        path, media_type = service.asset(key)
        # The global private response policy is no-store: switching local
        # profiles cannot serve an earlier owner's private card from HTTP cache.
        return send_file(path, mimetype=media_type, conditional=False, max_age=0)

    return bp
