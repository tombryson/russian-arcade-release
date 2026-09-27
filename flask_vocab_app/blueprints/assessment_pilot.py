"""Versioned, CSRF-protected diagnostic pilot lifecycle."""
from flask import Blueprint, jsonify, request, send_file, session
import wave

from repositories.learning_repository import LearningError
from services.speech_provider import SpeechError
from utils.household_access import access_id, access_policy


def create_assessment_pilot_blueprint(service):
    bp = Blueprint('assessment_pilot', __name__, url_prefix='/api/v1/assessment-pilot')

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise LearningError('invalid_input', 'Send a JSON object.')
        return value

    @bp.get('')
    @access_policy('child')
    def catalogue():
        return jsonify(service.catalogue(access_id()))

    @bp.post('/sessions')
    @access_policy('child')
    def start():
        return jsonify(service.start(access_id(), body(), 'ru' if session.get('ui_lang') == 'ru' else 'en'))

    @bp.get('/sessions/<sid>')
    @access_policy('child')
    def read(sid):
        return jsonify(service.read(access_id(), sid))

    @bp.post('/sessions/<sid>/components/<domain>/draft')
    @access_policy('child')
    def draft(sid, domain):
        return jsonify(service.draft(access_id(), sid, domain, body()))

    @bp.post('/sessions/<sid>/components/<domain>/support')
    @access_policy('child')
    def support(sid, domain):
        return jsonify(service.support(access_id(), sid, domain, body()))

    @bp.post('/sessions/<sid>/components/<domain>/attempts')
    @access_policy('child')
    def submit(sid, domain):
        try:
            if request.mimetype == 'multipart/form-data':
                uploaded = request.files.get('audio')
                revision = request.form.get('expected_revision', '')
                if uploaded is None or not revision.isascii() or not revision.isdecimal():
                    raise LearningError('invalid_input', 'Choose an original recording and the current form.')
                data = uploaded.read(8 * 1024 * 1024 + 1)
                extension = (uploaded.filename or '').rsplit('.', 1)[-1].lower()
                value = {'submission_id': request.form.get('submission_id'), 'component_id': request.form.get('component_id'), 'expected_revision': int(revision), 'response': {}}
                return jsonify(service.submit(access_id(), sid, domain, value, data=data, extension=extension))
            return jsonify(service.submit(access_id(), sid, domain, body()))
        except LearningError:
            raise
        except (SpeechError, ValueError, wave.Error, EOFError) as error:
            raise LearningError('invalid_audio', 'The original recording could not be saved. Use a playable clip between 0.2 and 90 seconds.') from error

    @bp.post('/sessions/<sid>/components/<domain>/review')
    @access_policy('child')
    def review(sid, domain):
        return jsonify(service.review(access_id(), sid, domain, body=body()))

    @bp.post('/sessions/<sid>/retry')
    @access_policy('child')
    def retry(sid):
        return jsonify(service.retry(access_id(), sid, body()))

    @bp.get('/sessions/<sid>/components/listening/audio')
    @access_policy('child')
    def listening_audio(sid):
        response = send_file(service.listening_audio(access_id(), sid), mimetype='audio/mpeg', conditional=True)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @bp.get('/sessions/<sid>/submissions/<submission_id>/audio')
    @access_policy('child')
    def original_audio(sid, submission_id):
        response = send_file(service.original_audio(access_id(), sid, submission_id), conditional=True)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    return bp
