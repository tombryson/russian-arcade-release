"""Mount the existing activity application at /demo without changing stored URLs.

Flask's SCRIPT_NAME handles url_for. The response adapter handles legacy root
URLs in templates and API presenters. Static assets and personal sign-in stay
shared at the origin; activity data and requests always use the mounted path.
"""
import json
import re
from pathlib import Path
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

from werkzeug.wrappers import Response


DEMO_PREFIX = '/demo'


def public_asset(path):
    if any(part in {'.', '..'} for part in path.split('/')) or '\\' in path:
        return False
    return ((path.startswith('/static/') and not path.startswith(('/static/media/', '/static/uploads/')))
            or path.startswith('/post/assets/'))


def packaged_asset(path):
    """Only files shipped with the app may bypass account storage routing."""
    if not public_asset(path):
        return False
    if path.startswith('/post/assets/'):
        return True  # The build blueprint validates its own immutable filenames.
    return (Path(__file__).parent / 'static' / path.removeprefix('/static/')).is_file()


def demo_url(value):
    if not isinstance(value, str) or not value.startswith('/') or value.startswith('//'):
        return value
    path = urlsplit(value).path
    if (path == DEMO_PREFIX or path.startswith(DEMO_PREFIX + '/')
            or public_asset(path)
            or path == '/trial/sign-out'
            or any(path == route or path.startswith(route + '/')
                   for route in ('/trial/sign-in', '/trial/callback', '/trial/connect'))):
        return value
    return DEMO_PREFIX + value


def response_urls(value, key=''):
    """Adapt URL fields only; never alter lesson text or submitted answers."""
    if isinstance(value, dict):
        return {name: response_urls(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [response_urls(item, key) for item in value]
    if isinstance(value, str) and (key in {'url', 'href', 'src', 'action', 'poster'}
                                   or key.endswith(('_url', '_href'))):
        return demo_url(value)
    return value


_ATTRIBUTE = re.compile(r'''(\s)([\w:-]+)(\s*=\s*)(["'])(.*?)\4''', re.DOTALL)


class DemoHTML(HTMLParser):
    """Preserve markup/scripts; adapt quoted URL attributes on actual tags."""
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        original = self.get_starttag_text()
        # A deliberate exit is the sole navigation back to the main site.
        if any(name == 'data-app-exit' for name, _ in attrs):
            self.parts.append(original)
            return
        def replace(match):
            gap, name, equals, quote, raw = match.groups()
            value = unescape(raw)
            url_attribute = name in {'href', 'src', 'action', 'formaction', 'poster', 'hx-get', 'hx-post',
                        'hx-put', 'hx-patch', 'hx-delete', 'hx-push-url', 'hx-replace-url',
                        'data-endpoint', 'data-lesson-poll', 'data-translation-audio'} or (
                            name.startswith('data-') and name.endswith(('-url', '-href')))
            json_attribute = name in {'data-navigation', 'data-onboarding'}
            if url_attribute or json_attribute:
                if json_attribute and value.startswith(('{', '[')):
                    try:
                        updated = json.dumps(response_urls(json.loads(value)), ensure_ascii=False)
                    except (ValueError, TypeError):
                        updated = value
                elif url_attribute:
                    updated = demo_url(value)
                else:
                    updated = value
                if updated != value:
                    return gap + name + equals + quote + escape(updated, quote=True) + quote
            return match.group(0)
        self.parts.append(_ATTRIBUTE.sub(replace, original))
        if tag == 'head':
            self.parts.append('<meta name="app-base-path" content="/demo">')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.parts.append('</' + tag + '>')

    def handle_data(self, data):
        self.parts.append(data)

    def handle_entityref(self, name):
        self.parts.append('&' + name + ';')

    def handle_charref(self, name):
        self.parts.append('&#' + name + ';')

    def handle_comment(self, data):
        self.parts.append('<!--' + data + '-->')

    def handle_decl(self, decl):
        self.parts.append('<!' + decl + '>')


class DemoMount:
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        mounted = dict(environ)
        mounted['SCRIPT_NAME'] = environ.get('SCRIPT_NAME', '') + DEMO_PREFIX
        mounted['PATH_INFO'] = environ['PATH_INFO'][len(DEMO_PREFIX):] or '/'
        mounted['russian_arcade.demo'] = True
        response = Response.from_app(self.application, mounted, buffered=False)
        for name in ('Location', 'HX-Redirect', 'HX-Push-Url', 'HX-Replace-Url', 'Content-Location'):
            if name in response.headers:
                response.headers[name] = demo_url(response.headers[name])
        if environ['REQUEST_METHOD'] != 'HEAD':
            if response.mimetype == 'text/html':
                parser = DemoHTML()
                parser.feed(response.get_data(as_text=True))
                parser.close()
                response.set_data(''.join(parser.parts))
            elif response.mimetype == 'application/json':
                payload = response.get_json(silent=True)
                if payload is not None:
                    response.set_data(json.dumps(response_urls(payload), ensure_ascii=False))
        return response(environ, start_response)
