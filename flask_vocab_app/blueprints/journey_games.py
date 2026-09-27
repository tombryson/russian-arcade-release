"""Public guest play, scoped to a learner or the current introductory session."""
from flask import Blueprint, jsonify, request, send_file

from contracts.learning import fields
from repositories.learning_repository import LearningError
from services.journey_games import game_image, prepare_session, read_catalogue, read_session, session_command, start_game, purchase_game
from utils.household_access import access_policy, csrf_token


def create_journey_games_blueprint():
    bp = Blueprint('journey_games', __name__, url_prefix='/api/v1/games')

    def body(required, optional=None):
        if not request.is_json:
            raise LearningError('json_required', 'Send a JSON object for this operation.', 415)
        return fields(request.get_json(silent=True), required, optional or set())

    @bp.get('')
    @access_policy('public')
    def catalogue():
        return jsonify(**read_catalogue(), csrf_token=csrf_token())

    @bp.post('/<game_id>/purchase')
    @access_policy('public')
    def purchase(game_id):
        data = body({'request_id', 'expected_price'})
        return jsonify(**purchase_game(game_id, data['request_id'], data['expected_price']), csrf_token=csrf_token())

    @bp.post('/<game_id>/start')
    @access_policy('public')
    def start(game_id):
        data = body({'request_id'}, {'options', 'new_game'})
        if 'new_game' in data and type(data['new_game']) is not bool:
            raise LearningError('invalid_options', 'Choose whether to start a new game.')
        return jsonify(**start_game(game_id, data['request_id'], data.get('options'), new_game=data.get('new_game', False)), csrf_token=csrf_token())

    @bp.post('/sessions/<session_id>/prepare')
    @access_policy('public')
    def prepare(session_id):
        data = body(set(), {'retry'})
        if 'retry' in data and type(data['retry']) is not bool:
            raise LearningError('invalid_options', 'Choose whether to retry preparation.')
        return jsonify(**prepare_session(session_id, retry=data.get('retry', False)), csrf_token=csrf_token())

    @bp.get('/sessions/<session_id>/assets/<asset_id>')
    @access_policy('public')
    def image(session_id, asset_id):
        path, media_type = game_image(session_id, asset_id)
        result = send_file(path, mimetype=media_type, conditional=True)
        result.headers['Cache-Control'] = 'private, no-store'
        result.headers['X-Content-Type-Options'] = 'nosniff'
        return result

    @bp.get('/sessions/<session_id>')
    @access_policy('public')
    def read(session_id):
        return jsonify(**read_session(session_id), csrf_token=csrf_token())

    @bp.get('/sessions/<session_id>/words')
    @access_policy('public')
    def word_details(session_id):
        from services.journey_games import game_word
        return jsonify(**game_word(session_id, request.args.get('word')), csrf_token=csrf_token())

    @bp.post('/sessions/<session_id>/words')
    @access_policy('public')
    def add_word(session_id):
        from services.journey_games import game_word
        data = body({'word', 'lemma'}, {'pos'})
        return jsonify(**game_word(session_id, data['word'], lemma=data['lemma'], pos=data.get('pos')), csrf_token=csrf_token())

    @bp.post('/sessions/<session_id>/<operation>')
    @access_policy('public')
    def command(session_id, operation):
        required = {'quiz': set(), 'hint': {'round_id'}, 'listen': {'round_id', 'audio_key'}, 'transcript': {'round_id'},
                    'practice_hint': {'round_id'}, 'practice_transcript': {'round_id'}, 'retry': {'round_id'}, 'review': set(), 'practice_exit': set(),
                    'practice_answer': {'round_id', 'answer', 'request_id'}, 'practice_continue': {'round_id'},
                    'answer': {'round_id', 'answer'}, 'continue': {'round_id'}, 'complete': set()}
        if operation not in required:
            raise LearningError('not_found', 'This game action was not found.', 404)
        return jsonify(**session_command(session_id, operation, body(required[operation])), csrf_token=csrf_token())

    @bp.post('/sessions/<session_id>/route-command')
    @access_policy('public')
    def route_command(session_id):
        from services.route_delivery import command
        return jsonify(**command(session_id, body({'request_id', 'revision', 'action', 'payload'})), csrf_token=csrf_token())

    return bp
