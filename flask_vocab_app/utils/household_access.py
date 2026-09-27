"""Local profile sessions and opt-in household access across every study route."""
import secrets
from hashlib import sha256
import re
import sqlite3
from urllib.parse import urlsplit

from flask import abort, current_app, has_request_context, jsonify, redirect, render_template, request, session

from repositories.learning_repository import LearningError, require_access, timestamp, transaction


def access_policy(role):
    def decorate(view):
        view.household_policy = role
        return view
    return decorate


def access_id():
    return session.get('household_access_id' if current_app.config['WORD_POST_HOUSEHOLD_ENABLED'] else 'personal_access_id')


def active_profile_id(conn=None):
    """Resolve the selected browser identity, including for legacy repositories."""
    if conn is None:
        with transaction(current_app.config['DB_PATH']) as connection:
            return active_profile_id(connection)
    factory = conn.row_factory
    try:
        conn.row_factory = sqlite3.Row
        return require_access(conn, access_id(), timestamp())['id']
    finally:
        conn.row_factory = factory


def user_session_profile():
    if not has_request_context() or current_app.config['WORD_POST_HOUSEHOLD_ENABLED'] or not access_id():
        return None
    try:
        with transaction(current_app.config['DB_PATH']) as conn:
            profile = require_access(conn, access_id(), timestamp())
            return {field: profile[field] for field in ('id', 'display_name', 'avatar', 'study_timezone')}
    except (LearningError, sqlite3.OperationalError):
        return None


def user_session_scope():
    """Distinguish hosted accounts whose local profile IDs can be identical."""
    if current_app.config.get('HOSTED_AI_TRIAL'):
        identity = current_app.config['AI_TRIAL_IDENTITY']
        return 'hosted:' + sha256(identity.encode()).hexdigest()
    return 'preview' if current_app.config.get('PUBLIC_DEMO') else 'local'


def csrf_token():
    if 'household_csrf' not in session:
        session['household_csrf'] = secrets.token_urlsafe(32)
    return session['household_csrf']


def install_household_policy(app):
    @app.context_processor
    def security_context():
        return {'household_enabled': app.config['WORD_POST_HOUSEHOLD_ENABLED'], 'csrf_token': csrf_token,
                'user_session_profile': user_session_profile(), 'user_session_scope': user_session_scope()}

    @app.errorhandler(LearningError)
    def learning_error(error):
        if request.path.startswith('/api/'):
            return jsonify(error={'code': error.code, 'message': str(error), **error.details}), error.status
        from blueprints.word_post import BuildUnavailable, build_assets
        try:
            assets = build_assets(app.config['WORD_POST_DIST_DIR'])
        except BuildUnavailable:
            assets = {'styles': []}
        return render_template('learning_error.html', message=str(error), assets=assets), error.status

    @app.before_request
    def household_boundary():
        enabled = app.config['WORD_POST_HOUSEHOLD_ENABLED']
        if enabled and request.blueprint == 'user_sessions':
            abort(404)
        if not enabled and request.blueprint == 'learning' and request.endpoint not in {
            'learning.household', 'learning.state', 'learning.post', 'learning.pocket', 'learning.asset',
            'learning.start_session', 'learning.read_session', 'learning.attempt', 'learning.help_item',
            'learning.listened_item', 'learning.transcript_item',
        }:
            abort(404)
        if enabled and (len(app.config.get('SECRET_KEY') or '') < 32 or app.config['SECRET_KEY'] == 'dev-secret-key-change-me'):
            raise LearningError('configuration_required', 'Set a private FLASK_SECRET_KEY of at least 32 characters before enabling household mode.', 503)
        if urlsplit(request.host_url).hostname not in app.config['WORD_POST_ALLOWED_HOSTS']:
            raise LearningError('invalid_host', 'This local app currently runs on this computer only.', 400)
        expected_scope = request.headers.get('X-Account-Scope')
        if expected_scope is not None and expected_scope != user_session_scope():
            raise LearningError('account_changed', 'Your account changed in another tab. Reload this page to continue.', 409)
        view = app.view_functions.get(request.endpoint)
        role = getattr(view, 'household_policy', 'adult')
        if request.endpoint in {'word_post.home','word_post.assets','word_post.licenses'}:
            role = 'public'
        if request.endpoint == 'static':
            filename = request.view_args.get('filename', '')
            if filename.startswith(('css/','js/')) or re.fullmatch(r'audio/deliveries/[0-9a-f]{24}\.mp3', filename) or filename in {
                'audio/course/curriculum/location-destination-listening-v1/shop-now.mp3',
                'audio/course/curriculum/location-destination-listening-v1/after-pharmacy.mp3',
                'audio/course/curriculum/location-destination-listening-v1/inside-museum.mp3',
                'images/barsik-running-v1.webp', 'images/barsik-progress-run-v1.webp', 'images/favicon.svg',
                'images/favicon.ico', 'images/apple-touch-icon.png',
                'images/scene-builder/cat-v1.webp', 'images/scene-builder/table-v1.webp',
                'images/scene-builder/book-v1.webp', 'images/scene-builder/book-upright-v1.webp', 'images/scene-builder/walking-v1.webp',
                'images/scene-builder/taxi-v1.webp',
                'images/scene-builder/walking-away-v1.webp', 'images/scene-builder/taxi-moving-v1.webp',
                'images/scene-builder/taxi-away-v1.webp', 'images/scene-builder/doorway-inside-v1.webp',
                'images/scene-builder/courtyard-in-v1.webp', 'images/scene-builder/courtyard-out-v1.webp',
            }:
                role = 'public'
        # Unknown routes retain their normal 404/405 behavior without creating a session.
        if view is None:
            return
        # Two legacy GET endpoints invoke providers/write capture state. Their
        # compatibility clients must send the same token as ordinary writes.
        unsafe = request.method not in ('GET','HEAD','OPTIONS') or request.path in ('/sentence/generate','/sync_vocab')
        if unsafe:
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                raise LearningError('csrf_failed', 'Open this form from this application and try again.', 403)
            if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise LearningError('csrf_failed', 'Open this form from this application and try again.', 403)
            provided = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
            expected = session.get('household_csrf')
            if not isinstance(provided, str) or not expected or not secrets.compare_digest(provided, expected):
                raise LearningError('csrf_failed', 'This form expired. Reload before trying again.', 403)
        # Bind an open page to the identity it originally rendered. A stale tab
        # must not accept another profile's data or write as that profile even
        # if a background response has refreshed its CSRF token.
        page_profile = request.headers.get('X-Profile-ID')
        if page_profile is not None and (unsafe or role != 'public' or request.endpoint in {'learning.asset', 'onboarding.practice_read', 'first_steps.chapter', 'first_steps.lesson', 'journey_games.catalogue', 'journey_games.read', 'journey_game_media.status', 'journey_game_media.asset', 'curriculum.index'}):
            with transaction(app.config['DB_PATH']) as conn:
                selected = conn.execute(
                    'SELECT p.id FROM household_access a JOIN learning_profiles p ON p.id=a.profile_id '
                    'WHERE a.id=? AND a.expires_at>? AND p.archived=0 AND p.legacy_user_id IS NULL',
                    (access_id(), timestamp()),
                ).fetchone()
            if page_profile != (selected['id'] if selected else ''):
                raise LearningError('profile_changed', 'Your profile changed. Reopen this page before continuing.', 409)
        if role == 'public' and (enabled or not access_id()):
            return
        try:
            with transaction(app.config['DB_PATH'], write=not enabled) as conn:
                now = timestamp()
                require_access(conn, access_id(), now, adult=enabled and role == 'adult')
                if not enabled:
                    expiry = now + int(app.permanent_session_lifetime.total_seconds())
                    conn.execute('UPDATE household_access SET adult_until=?,expires_at=? WHERE id=?',
                                 (expiry, expiry, access_id()))
                    session.permanent = True
        except sqlite3.OperationalError as error:
            raise LearningError('migration_required', 'Run db-upgrade before using saved learning profiles.', 503) from error
        except LearningError:
            if not enabled and role == 'public':
                session.pop('personal_access_id', None)
                return
            if request.method == 'GET' and not request.path.startswith('/api/'):
                return redirect('/post/household' if enabled else '/post/profiles')
            raise

    @app.after_request
    def private_response_policy(response):
        if request.endpoint not in {'word_post.assets','word_post.licenses','static'}:
            response.headers['Cache-Control'] = 'private, no-store' if request.endpoint in {'assessment_pilot.listening_audio', 'assessment_pilot.original_audio'} else 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        return response
