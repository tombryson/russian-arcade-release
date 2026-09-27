"""Explicit guided-dialogue commands and owned, cached speech playback."""
from flask import Blueprint, jsonify, request, send_file
from contracts.learning import fields
from utils.household_access import access_id, access_policy


def create_step_conversation_blueprint(service):
    bp = Blueprint('step_conversation', __name__, url_prefix='/api/v1/step-conversations')

    def body(required, optional=()):
        return fields(request.get_json(silent=True), required, optional)

    @bp.get('/options')
    @access_policy('child')
    def options():
        return jsonify(service.options(access_id(), request.args.get('exclude_seed'),
                                       request.args.get('scenario_id', 'cafe'), request.args.get('level')))

    @bp.get('/history')
    @access_policy('child')
    def history():
        return jsonify(service.history(access_id()))

    @bp.post('')
    @access_policy('child')
    def start():
        return jsonify(service.start(access_id(), body({'submission_id'},
            {'scenario_id', 'scenario_seed', 'target_level', 'language'}))), 201

    @bp.get('/<sid>')
    @access_policy('child')
    def read(sid):
        return jsonify(service.read(access_id(), sid))

    @bp.post('/<sid>/answer')
    @access_policy('child')
    def answer(sid):
        return jsonify(service.answer(access_id(), sid, body({'submission_id', 'turn_id', 'option_id'})))

    @bp.post('/<sid>/hint')
    @access_policy('child')
    def hint(sid):
        return jsonify(service.hint(access_id(), sid, body({'turn_id'})))

    @bp.post('/<sid>/next')
    @access_policy('child')
    def next_turn(sid):
        return jsonify(service.next(access_id(), sid, body({'turn_id'})))

    @bp.post('/<sid>/retry')
    @access_policy('child')
    def retry(sid):
        body(set())
        return jsonify(service.retry(access_id(), sid))

    @bp.post('/<sid>/audio')
    @access_policy('child')
    def prepare_audio(sid):
        return jsonify(service.prepare_audio(access_id(), sid, body({'turn_id', 'kind'})))

    @bp.get('/<sid>/audio/<tid>/<kind>')
    @access_policy('child')
    def audio(sid, tid, kind):
        return send_file(service.audio(access_id(), sid, tid, kind), mimetype='audio/mpeg', conditional=True)

    return bp
