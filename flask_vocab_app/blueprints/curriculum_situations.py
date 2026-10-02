"""Thin routes for owned situation preparation; GET never calls a provider."""
from flask import Blueprint, jsonify, request, redirect, session
from contracts.learning import fields
from repositories.learning_repository import LearningError
from utils.household_access import access_id, access_policy
from utils.shell import render_page


def create_curriculum_situations_blueprint(service):
    bp = Blueprint('curriculum_situations', __name__)

    @bp.post('/curriculum/units/<unit_id>/situations')
    @access_policy('child')
    def start(unit_id):
        saved = service.start(access_id(), unit_id, request.form.get('mode'),
                              request.form.get('request_id'), request.form.get('profile_id'))
        return redirect(saved['url'] or '/curriculum/situations/' + saved['id'], code=303)

    @bp.get('/curriculum/situations/<sid>')
    @access_policy('child')
    def page(sid):
        saved = service.read(access_id(), sid)
        if saved['state'] == 'ready':
            return redirect(saved['url'], code=303)
        return render_page('curriculum_situation.html', active_page='curriculum', preparation=saved,
                           language='ru' if session.get('ui_lang') == 'ru' else 'en')

    @bp.get('/api/v1/curriculum/situations/<sid>')
    @access_policy('child')
    def read(sid):
        return jsonify(service.read(access_id(), sid))

    @bp.post('/api/v1/curriculum/situations/<sid>/prepare')
    @access_policy('child')
    def prepare(sid):
        body = fields(request.get_json(silent=True), {'retry'})
        if type(body['retry']) is not bool:
            raise LearningError('invalid_input', 'Choose whether to retry preparation.')
        return jsonify(service.advance(access_id(), sid, retry=body['retry']))

    return bp
