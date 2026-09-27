"""Signalling, saved audio and review for the separate live conversation activity."""
from flask import Blueprint, jsonify, request, send_file
from repositories.learning_repository import LearningError
from utils.household_access import access_id, access_policy


def create_live_conversation_blueprint(service):
    bp = Blueprint('live_conversation', __name__, url_prefix='/api/v1/live-conversations')

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise LearningError('invalid_input','Send a JSON object.')
        return value

    @bp.get('/options')
    @access_policy('child')
    def options():
        return jsonify(service.options(access_id(), request.args.get('exclude_seed'), request.args.get('scenario_id','cafe'),request.args.get('level')))

    @bp.get('/scenarios')
    @access_policy('child')
    def scenarios():
        return jsonify(service.scenarios(access_id(),request.args.get('level')))

    @bp.post('')
    @access_policy('child')
    def start():
        return jsonify(service.start(access_id(),body())),201

    @bp.get('/<sid>')
    @access_policy('child')
    def read(sid):
        return jsonify(service.read(access_id(),sid))

    @bp.post('/<sid>/connect')
    @access_policy('child')
    def connect(sid):
        return jsonify(service.connect(access_id(),sid,body()))

    @bp.post('/<sid>/heartbeat')
    @access_policy('child')
    def heartbeat(sid):
        return jsonify(service.heartbeat(access_id(),sid))

    @bp.post('/<sid>/finish')
    @access_policy('child')
    def finish(sid):
        return jsonify(service.finish(access_id(),sid))

    @bp.post('/<sid>/review')
    @access_policy('child')
    def review(sid):
        return jsonify(service.review(access_id(),sid)),202

    @bp.get('/<sid>/recordings/<rid>')
    @access_policy('child')
    def audio(sid,rid):
        return send_file(service.audio(access_id(),sid,rid), mimetype='audio/wav',conditional=True)

    @bp.post('/<sid>/recordings/<rid>/retry')
    @access_policy('child')
    def retry(sid,rid):
        return jsonify(service.retry(access_id(),sid,rid)),202

    @bp.post('/<sid>/delete')
    @access_policy('child')
    def delete(sid):
        return jsonify(service.delete(access_id(),sid))

    return bp
