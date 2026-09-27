"""Browser appearance preferences shared by the Flask and native shells."""
from urllib.parse import unquote, urlsplit

from flask import Blueprint, current_app, redirect, request, session

from repositories.learning_repository import LearningError
from utils.household_access import access_policy
from utils.navigation import NAVIGATION_COOKIE, NAVIGATION_LAYOUTS, browser_navigation_layout


def _local_return_path(value):
    fallback = '/'
    if not isinstance(value, str) or not value.startswith('/'):
        return fallback
    decoded = unquote(value)
    if decoded.startswith('//') or '\\' in decoded or any(ord(char) < 32 for char in decoded):
        return fallback
    parts = urlsplit(decoded)
    if parts.scheme or parts.netloc:
        return fallback
    return value


def create_ui_preferences_blueprint():
    bp = Blueprint('ui_preferences', __name__)

    @bp.app_context_processor
    def navigation_preference():
        return {'navigation_layout': browser_navigation_layout()}

    @bp.after_request
    def private_preferences(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @bp.get('/appearance')
    @access_policy('public')
    def appearance():
        return redirect('/')

    @bp.post('/ui-navigation')
    @access_policy('public')
    def set_navigation():
        values = request.form.getlist('layout')
        if len(values) != 1 or values[0] not in NAVIGATION_LAYOUTS:
            raise LearningError('invalid_navigation', 'Choose top navigation or sidebar.', 400)
        session['ui_navigation'] = values[0]
        response = redirect(_local_return_path(request.form.get('next')), code=303)
        response.headers['Cache-Control'] = 'no-store'
        response.set_cookie(
            NAVIGATION_COOKIE, values[0], max_age=31536000, httponly=True,
            secure=current_app.config.get('SESSION_COOKIE_SECURE', False), samesite='Lax', path='/',
        )
        return response

    return bp
