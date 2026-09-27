"""Russian Arcade entry and shared production asset boundary.

Learner state is fetched through the protected learning API. Existing Flask
activities share the design tokens without sharing Preact DOM ownership.
"""
import json
from pathlib import Path
import re

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_from_directory

from utils.household_access import access_policy


class BuildUnavailable(ValueError):
    pass


def build_assets(dist, entry_key='src/main.tsx'):
    """Resolve a Vite entry and imported styles; accept only local built files."""
    root = Path(dist).resolve()
    try:
        manifest = json.loads((root / '.vite/manifest.json').read_text())
        if not isinstance(manifest, dict):
            raise BuildUnavailable('Invalid manifest')
        entry = manifest[entry_key]
        styles, seen = [], set()

        def asset(value, extension):
            if not isinstance(value, str) or not re.fullmatch(r'assets/[A-Za-z0-9_.-]+', value):
                raise BuildUnavailable('Invalid asset path')
            path = (root / value).resolve()
            if not path.is_relative_to(root / 'assets') or path.suffix != extension or not path.is_file():
                raise BuildUnavailable('Missing or invalid asset')
            return value.removeprefix('assets/')

        def visit(key):
            if key in seen:
                return
            seen.add(key)
            chunk = manifest[key]
            asset(chunk['file'], '.js')
            css, imports = chunk.get('css', []), chunk.get('imports', [])
            if not isinstance(css, list) or not isinstance(imports, list):
                raise BuildUnavailable('Invalid chunk dependencies')
            for value in css:
                filename = asset(value, '.css')
                if filename not in styles:
                    styles.append(filename)
            for imported in imports:
                if not isinstance(imported, str):
                    raise BuildUnavailable('Invalid imported chunk')
                visit(imported)

        visit(entry_key)
        return {'script': asset(entry['file'], '.js'), 'styles': styles}
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        raise BuildUnavailable('Word Post build is unavailable') from error


def create_word_post_blueprint():
    blueprint = Blueprint('word_post', __name__)

    @blueprint.app_context_processor
    def shared_design():
        def arcade_styles():
            if not current_app.config['WORD_POST_ENABLED']:
                return []
            try:
                return build_assets(current_app.config['WORD_POST_DIST_DIR'], 'src/legacy.ts')['styles']
            except BuildUnavailable:
                return []
        return {'arcade_styles': arcade_styles}

    @blueprint.before_request
    def enabled():
        if not current_app.config['WORD_POST_ENABLED']:
            abort(404)

    @blueprint.after_request
    def response_policy(response):
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; font-src 'self'; connect-src 'self'; "
            "media-src 'self' blob:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-store'
        return response

    def page(view):
        try:
            assets = build_assets(current_app.config['WORD_POST_DIST_DIR'])
        except BuildUnavailable:
            current_app.logger.warning('Word Post build missing or invalid; rebuild the UI package')
            return render_template('word_post_unavailable.html'), 503
        from services.course_releases import default_release_id
        return render_template('word_post.html', view=view, assets=assets, default_course_release=default_release_id())

    @blueprint.get('/')
    def home():
        return page('app')

    @blueprint.get('/post')
    @blueprint.get('/post/')
    @access_policy('public')
    def legacy_home():
        # A Location without a fragment preserves the browser's existing hash
        # route. Keep the raw query too, including previews and shared filters.
        query = request.query_string.decode('latin-1')
        return redirect('/' + ('?' + query if query else ''), code=308)

    @blueprint.get('/post/catalogue')
    def catalogue():
        if not current_app.config['WORD_POST_CATALOGUE_ENABLED']:
            abort(404)
        return page('catalogue')

    @blueprint.get('/post/assets/<path:filename>')
    def assets(filename):
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*', filename):
            abort(404)
        directory = Path(current_app.config['WORD_POST_DIST_DIR']).resolve() / 'assets'
        path = (directory / filename).resolve()
        if not path.is_relative_to(directory) or path.suffix not in {'.js', '.css', '.woff2', '.woff', '.webp', '.png', '.jpg', '.svg'}:
            abort(404)
        response = send_from_directory(directory, filename, max_age=31536000)
        response.cache_control.immutable = True
        return response

    @blueprint.get('/post/licenses/<filename>')
    def licenses(filename):
        if filename not in {'golos-text-OFL.txt', 'unbounded-OFL.txt'}:
            abort(404)
        return send_from_directory(Path(current_app.config['WORD_POST_DIST_DIR']) / 'licenses', filename)

    return blueprint
