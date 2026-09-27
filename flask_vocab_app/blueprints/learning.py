"""Household controls and the first persistent learning API."""
import sqlite3

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, session

from blueprints.word_post import build_assets, BuildUnavailable
from contracts.learning import fields, key
from repositories.learning_repository import LearningError, require_access, timestamp, transaction
from services.onboarding import GUEST_ONBOARDING_KEY, onboarding_state
from utils.household_access import access_id, access_policy, csrf_token
from utils.navigation import browser_navigation_layout
from utils.course_context import selected_course_progress


def create_learning_blueprint(household, content, learning, store):
    bp = Blueprint('learning', __name__)

    def clear_access_session():
        language = session.get('ui_lang')
        navigation = browser_navigation_layout()
        session.clear()
        if language in {'en', 'ru'}:
            session['ui_lang'] = language
        session['ui_navigation'] = navigation

    def body(required, optional=()):
        if not request.is_json:
            raise LearningError('json_required', 'Send a JSON object for this operation.', 415)
        return fields(request.get_json(silent=True), required, optional)

    @bp.after_request
    def policy(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @bp.get('/post/household', endpoint='household')
    @access_policy('public')
    def household_page():
        enabled = current_app.config['WORD_POST_HOUSEHOLD_ENABLED']
        if not enabled:
            return redirect('/post/profiles')
        try:
            state = household.state(access_id()) if enabled else {'configured': False, 'adult': False}
        except sqlite3.OperationalError:
            state = {'configured': False, 'adult': False}
        versions = content.list_for_adult(access_id()) if state['adult'] else []
        selected = None
        if state['adult'] and request.args.get('version'):
            selected = content.inspect(access_id(), request.args['version'])
        try:
            assets = build_assets(current_app.config['WORD_POST_DIST_DIR'])
        except BuildUnavailable:
            assets = {'styles': []}
        from blueprints.user_sessions import selected_skill_progress
        return render_template('household.html', state=state, versions=versions, selected=selected, assets=assets,
                               profile_course_progress=selected_course_progress(),
                               profile_skill_progress=selected_skill_progress())

    @bp.get('/api/v1/household')
    @access_policy('public')
    def state():
        if not current_app.config['WORD_POST_HOUSEHOLD_ENABLED']:
            from blueprints.user_sessions import personal_sessions
            return jsonify(**personal_sessions().state(access_id()), configured=True, adult=False,
                           csrf_token=csrf_token())
        try:
            result = household.state(access_id())
        except sqlite3.OperationalError as error:
            raise LearningError('migration_required', 'Run db-upgrade before household setup.', 503) from error
        return jsonify(**result, csrf_token=csrf_token())

    def unlock(pin):
        credential = household.unlock(pin, access_id())
        clear_access_session()
        session['household_access_id'] = credential
        current_app.session_interface.regenerate(session)
        csrf_token()

    @bp.post('/api/v1/household/unlock')
    @access_policy('public')
    def api_unlock():
        data = body({'pin'})
        unlock(data['pin'])
        return jsonify(**household.state(access_id()), csrf_token=csrf_token())

    @bp.post('/api/v1/household/lock')
    @access_policy('public')
    def api_lock():
        body(set())
        household.lock(access_id())
        clear_access_session()
        return jsonify(locked=True, csrf_token=csrf_token())

    @bp.post('/api/v1/grownups/profiles')
    @access_policy('adult')
    def profile_create():
        data = body({'display_name','study_timezone'}, {'avatar'})
        guest = session.get(GUEST_ONBOARDING_KEY) if onboarding_state()['profile_id'] is None else None
        profile_id = household.create_profile(access_id(), data['display_name'], data['study_timezone'], data.get('avatar', 'letter'), guest_onboarding=guest)
        session.pop(GUEST_ONBOARDING_KEY, None)
        return jsonify(id=profile_id), 201

    @bp.post('/api/v1/grownups/profiles/<profile_id>/select')
    @access_policy('adult')
    def profile_select(profile_id):
        body(set())
        household.select_profile(access_id(), profile_id)
        session.pop(GUEST_ONBOARDING_KEY, None)
        return jsonify(**household.state(access_id()))

    @bp.post('/api/v1/grownups/profiles/<profile_id>/archive')
    @access_policy('adult')
    def profile_archive(profile_id):
        body(set())
        household.archive_profile(access_id(), profile_id)
        return jsonify(archived=True)

    @bp.get('/api/v1/grownups/content/<version_id>')
    @access_policy('adult')
    def inspect_content(version_id):
        return jsonify(content.inspect(access_id(), version_id))

    @bp.post('/api/v1/grownups/content/<version_id>/publish')
    @access_policy('adult')
    def publish_content(version_id):
        data = body({'reviewer','approved'})
        if data['approved'] is not True:
            raise LearningError('approval_required', 'Review this content and explicitly approve it before publishing.')
        content.publish(access_id(), version_id, data['reviewer'])
        return jsonify(published=True)

    @bp.post('/api/v1/grownups/content/<version_id>/withdraw')
    @access_policy('adult')
    def withdraw_content(version_id):
        body(set())
        content.withdraw(access_id(), version_id)
        return jsonify(withdrawn=True)

    @bp.get('/api/v1/post')
    @access_policy('child')
    def post():
        return jsonify(learning.home(access_id()))

    @bp.get('/api/v1/word-pocket')
    @access_policy('child')
    def pocket():
        return jsonify(learning.progress(access_id()))

    @bp.post('/api/v1/learning-sessions')
    @access_policy('child')
    def start_session():
        return jsonify(learning.start(access_id(), body({'profile_id','version_id','submission_id'}))), 201

    @bp.get('/api/v1/learning-sessions/<session_id>')
    @access_policy('child')
    def read_session(session_id):
        return jsonify(learning.read(access_id(), session_id))

    @bp.post('/api/v1/learning-sessions/<session_id>/attempts')
    @access_policy('child')
    def attempt(session_id):
        return jsonify(learning.command(access_id(), session_id, 'answer', body({'submission_id','expected_revision','item_id','answer'})))

    @bp.post('/api/v1/learning-sessions/<session_id>/help')
    @access_policy('child')
    def help_item(session_id):
        return jsonify(learning.command(access_id(), session_id, 'help', body({'submission_id','expected_revision','item_id'})))

    @bp.post('/api/v1/learning-sessions/<session_id>/listened')
    @access_policy('child')
    def listened_item(session_id):
        return jsonify(learning.command(access_id(), session_id, 'listened', body({'submission_id','expected_revision','item_id'})))

    @bp.post('/api/v1/learning-sessions/<session_id>/transcript')
    @access_policy('child')
    def transcript_item(session_id):
        return jsonify(learning.command(access_id(), session_id, 'transcript', body({'submission_id','expected_revision','item_id'})))

    @bp.get('/api/v1/assets/<asset_id>')
    @access_policy('public')
    def asset(asset_id):
        key(asset_id)
        with transaction(current_app.config['DB_PATH']) as conn:
            try:
                require_access(conn, access_id(), timestamp(), adult=True)
                adult = True
            except LearningError:
                require_access(conn, access_id(), timestamp())
                adult = False
            row = conn.execute('SELECT * FROM learning_assets WHERE id=?', (asset_id,)).fetchone()
            published = conn.execute("SELECT 1 FROM learning_content_assets a JOIN learning_content_versions v ON a.version_id=v.id WHERE a.asset_id=? AND v.status='published'", (asset_id,)).fetchone()
            if not row or (not adult and not published):
                raise LearningError('not_found', 'This asset is not available.', 404)
            path = store.path(row['storage_key'])
            if not path.is_file():
                raise LearningError('asset_missing', 'This media is unavailable.', 404)
            return send_file(path, mimetype=row['media_type'], conditional=False, max_age=0)

    @bp.post('/post/household/actions')
    @access_policy('public')
    def form_action():
        action = request.form.get('action')
        if action == 'unlock':
            unlock(request.form.get('pin'))
        elif action == 'lock':
            household.lock(access_id())
            clear_access_session()
        elif action == 'create-profile':
            guest = session.get(GUEST_ONBOARDING_KEY) if onboarding_state()['profile_id'] is None else None
            household.create_profile(access_id(), request.form.get('name'), request.form.get('timezone'), request.form.get('avatar', 'letter'), guest_onboarding=guest)
            session.pop(GUEST_ONBOARDING_KEY, None)
        elif action == 'select-profile':
            household.select_profile(access_id(), request.form.get('profile_id'))
            session.pop(GUEST_ONBOARDING_KEY, None)
            return redirect('/')
        elif action == 'archive-profile':
            household.archive_profile(access_id(), request.form.get('profile_id'))
        elif action == 'publish':
            if request.form.get('approved') != 'yes':
                raise LearningError('approval_required', 'Review the pack and confirm approval first.')
            content.publish(access_id(), request.form.get('version_id'), request.form.get('reviewer'))
        elif action == 'withdraw':
            content.withdraw(access_id(), request.form.get('version_id'))
        else:
            raise LearningError('invalid_action', 'Choose a supported household action.')
        return redirect('/post/household')

    return bp
