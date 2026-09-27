"""Local profile selection and browser-session lifecycle."""
from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session

from blueprints.word_post import BuildUnavailable, build_assets
from contracts.learning import fields
from repositories.learning_repository import LearningError, require_access, timestamp, transaction
from services.onboarding import onboarding_state
from services.personal_learning import PersonalSessions
from services.skill_progress import snapshot as skill_snapshot
from utils.household_access import access_id, access_policy, csrf_token, user_session_scope
from utils.navigation import browser_navigation_layout
from utils.course_context import selected_course_progress


def personal_sessions():
    return PersonalSessions(current_app.config['DB_PATH'],
                            lifetime=current_app.permanent_session_lifetime.total_seconds())


def selected_skill_progress():
    """Read only the introduced skills for this browser's selected profile."""
    introduced = onboarding_state()
    if not introduced['profile_id'] or not introduced['progress_introduced']:
        return None
    try:
        with transaction(current_app.config['DB_PATH']) as conn:
            profile = require_access(conn, access_id(), timestamp(), profile_id=introduced['profile_id'])
            return {'profile_id': profile['id'], 'display_name': profile['display_name'],
                    **skill_snapshot(conn, profile['id'])}
    except LearningError as error:
        if error.code in {'locked', 'profile_changed'}:
            return None
        raise


def create_user_sessions_blueprint():
    bp = Blueprint('user_sessions', __name__)

    @bp.before_request
    def personal_only():
        if current_app.config['WORD_POST_HOUSEHOLD_ENABLED']:
            abort(404)

    def state():
        return personal_sessions().state(access_id()) | {'csrf_token': csrf_token(), 'session_scope': user_session_scope()}

    def body(required, optional=()):
        if not request.is_json:
            raise LearningError('json_required', 'Send a JSON object for this operation.', 415)
        return fields(request.get_json(silent=True), required, optional)

    def replace_session(credential=None):
        language = session.get('ui_lang')
        navigation = browser_navigation_layout()
        session.clear()
        if language in {'en', 'ru'}:
            session['ui_lang'] = language
        session['ui_navigation'] = navigation
        if credential:
            session['personal_access_id'] = credential
        session.permanent = True
        csrf_token()
        current_app.session_interface.regenerate(session)

    def create(data):
        from services.onboarding import GUEST_ONBOARDING_KEY, onboarding_state
        from services.first_delivery import GUEST_ATTEMPT_KEY
        is_guest = onboarding_state()['profile_id'] is None
        guest = session.get(GUEST_ONBOARDING_KEY) if is_guest else None
        guest_practice = session.get(GUEST_ATTEMPT_KEY) if is_guest else None
        credential = personal_sessions().create(
            data.get('display_name'), data.get('study_timezone') or current_app.config['PERSONAL_STUDY_TIMEZONE'],
            data.get('avatar') or 'cat', access_id(), guest_onboarding=guest, guest_practice_token=guest_practice)
        replace_session(credential)

    def select(profile_id):
        replace_session(personal_sessions().select(profile_id, access_id()))

    def logout():
        personal_sessions().logout(access_id())
        replace_session()

    @bp.get('/api/v1/user-session')
    @access_policy('public')
    def read():
        return jsonify(state())

    @bp.post('/api/v1/user-session/profiles')
    @access_policy('public')
    def create_profile():
        create(body({'display_name'}, {'study_timezone', 'avatar'}))
        return jsonify(state()), 201

    @bp.post('/api/v1/user-session/select')
    @access_policy('public')
    def select_profile():
        select(body({'profile_id'})['profile_id'])
        return jsonify(state())

    @bp.post('/api/v1/user-session/logout')
    @access_policy('public')
    def end():
        body(set())
        logout()
        return jsonify(state())

    @bp.patch('/api/v1/user-session/profile')
    @access_policy('public')
    def rename_profile():
        personal_sessions().rename(access_id(), body({'display_name'})['display_name'])
        return jsonify(state())

    def render_picker(**context):
        try:
            assets = build_assets(current_app.config['WORD_POST_DIST_DIR'])
        except BuildUnavailable:
            assets = {'styles': []}
        return render_template('user_sessions.html', state=state(), assets=assets,
                               profile_course_progress=selected_course_progress(),
                               profile_skill_progress=selected_skill_progress(), **context)

    @bp.get('/post/profiles')
    @access_policy('public')
    def page():
        return render_picker()

    @bp.post('/post/profiles/actions')
    @access_policy('public')
    def actions():
        action = request.form.get('action')
        try:
            if action == 'create':
                create(request.form)
            elif action == 'select':
                select(request.form.get('profile_id'))
            elif action == 'logout':
                logout()
                return redirect('/post/profiles')
            elif action == 'rename':
                personal_sessions().rename(access_id(), request.form.get('display_name'))
            else:
                raise LearningError('invalid_action', 'Choose a supported profile action.')
        except LearningError as error:
            return render_picker(error=str(error), form_name=request.form.get('display_name', '')), error.status
        return redirect('/#home')

    return bp
