"""Personal conversation practice and private recording playback."""
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file
from repositories.learning_repository import LearningError
from utils.household_access import access_id, access_policy


def create_conversation_blueprint(service):
    bp = Blueprint('conversation', __name__, url_prefix='/api/v1/conversations')

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise LearningError('invalid_input', 'Send a JSON object.')
        return value

    @bp.get('/options')
    @access_policy('child')
    def options():
        return jsonify(service.options(access_id()))

    @bp.post('')
    @access_policy('child')
    def start():
        return jsonify(service.start(access_id(), body())), 201

    @bp.get('/<sid>')
    @access_policy('child')
    def read(sid):
        return jsonify(service.read(access_id(), sid))

    @bp.post('/<sid>/turns')
    @access_policy('child')
    def submit(sid):
        audio = request.files.get('audio')
        if audio is None:
            raise LearningError('invalid_audio', 'Add a microphone recording or an audio file.')
        extension = Path(audio.filename or '').suffix.lower().lstrip('.')
        return jsonify(service.submit(access_id(), sid, request.form,
                                      audio.read(8 * 1024 * 1024 + 1), extension)), 202

    @bp.post('/<sid>/turns/<tid>/retry')
    @access_policy('child')
    def retry(sid, tid):
        return jsonify(service.retry(access_id(), sid, tid)), 202

    @bp.post('/<sid>/greeting')
    @access_policy('child')
    def greeting(sid):
        return jsonify(service.greeting(access_id(), sid))

    @bp.get('/<sid>/greeting/audio')
    @access_policy('child')
    def greeting_audio(sid):
        service.read(access_id(), sid)
        path = service.root / (sid + '-greeting.mp3')
        if not path.is_file():
            raise LearningError('not_found', 'Greeting audio is not ready.', 404)
        return send_file(path, mimetype='audio/mpeg', conditional=True)

    @bp.get('/<sid>/turns/<tid>/audio/<kind>')
    @access_policy('child')
    def audio(sid, tid, kind):
        return send_file(service.audio(access_id(), sid, tid, kind), conditional=True)

    @bp.post('/<sid>/finish')
    @access_policy('child')
    def finish(sid):
        return jsonify(service.finish(access_id(), sid))

    @bp.post('/<sid>/delete')
    @access_policy('child')
    def delete(sid):
        return jsonify(service.delete(access_id(), sid))

    return bp
