"""Same-origin native reviewer; all writes use household authorization and CSRF."""
from flask import Blueprint, abort, current_app, jsonify, request

from utils.household_access import access_id, access_policy


def create_native_review_blueprint(review):
    bp=Blueprint('native_review',__name__)

    @bp.before_request
    def enabled():
        if not current_app.config['NATIVE_FLASHCARDS_ENABLED']:
            abort(404)

    def body():
        from repositories.learning_repository import LearningError
        if not request.is_json:
            raise LearningError('json_required','Send a JSON object for this action.',415)
        value=request.get_json(silent=True)
        if not isinstance(value,dict):
            raise LearningError('invalid_input','Send a JSON object for this action.')
        return value

    @bp.get('/api/v1/flashcards')
    @access_policy('child')
    def overview():
        return jsonify(review.overview(access_id(),request.args.to_dict()))

    @bp.post('/api/v1/review-sessions')
    @access_policy('child')
    def start():
        return jsonify(review.start(access_id(),body())),201

    @bp.get('/api/v1/review-sessions/<session_id>')
    @access_policy('child')
    def read(session_id):
        return jsonify(review.read(access_id(),session_id))

    @bp.post('/api/v1/review-sessions/<session_id>/<operation>')
    @access_policy('child')
    def command(session_id,operation):
        return jsonify(review.command(access_id(),session_id,operation,body()))

    @bp.post('/api/v1/flashcards/<card_id>/suspension')
    @access_policy('child')
    def suspension(card_id):
        return jsonify(review.suspend(access_id(),card_id,body()))

    @bp.get('/api/v1/flashcards/<card_id>/history')
    @access_policy('child')
    def history(card_id):
        return jsonify(review.history(access_id(),card_id))

    return bp
