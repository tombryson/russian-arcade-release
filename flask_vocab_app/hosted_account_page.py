"""Render hosted sign-in without starting a learner application or JavaScript."""
from pathlib import Path
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape


_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / 'templates'),
    autoescape=select_autoescape(['html']),
)
_PROVIDERS = {'google': 'Google', 'github': 'GitHub'}
ACCOUNT_PUBLIC_ASSETS = frozenset({
    '/static/css/account.css', '/static/images/favicon.svg',
    '/static/images/account/google-g.png',
    '/static/fonts/golos-text-latin-400-normal.woff2',
    '/static/fonts/golos-text-latin-500-normal.woff2',
    '/static/fonts/unbounded-latin-500-normal.woff2',
    '/static/fonts/google-sans-latin-500-normal.woff2',
})


def render_account_page(title, message='', *, providers=(), account=None,
                        csrf_token='', link_csrf_token='', connected_providers=(),
                        allowance_message='', next_url='/', demo_active=False, demo_enabled=False):
    """Return escaped HTML; authentication and CSRF validation live in the dispatcher.

    Only configured providers are offered for sign-in or linking. Provider IDs
    and local routes are fixed here; no provider response can inject a URL.
    """
    if (not isinstance(next_url, str) or not next_url.startswith('/')
            or next_url.startswith('//') or '\\' in next_url
            or any(ord(char) < 32 for char in next_url)):
        next_url = '/'
    available = {row['id'] for row in providers if isinstance(row, dict)
                 and row.get('id') in _PROVIDERS}
    connected = {value for value in connected_providers if value in _PROVIDERS}
    query = '?' + urlencode({'next': next_url}) if next_url != '/' else ''
    methods = [
        {'id': identity, 'name': name, 'configured': identity in available,
         'connected': identity in connected,
         'sign_in_url': f'/trial/sign-in/{identity}{query}'}
        for identity, name in _PROVIDERS.items()
        if identity in available or account and identity in connected
    ]
    name = str(account['display_name']) if account else ''
    return _templates.get_template('account.html').render(
        title=title, message=message, methods=methods, account_name=name,
        authenticated=account is not None, avatar=name[:1].upper(),
        csrf_token=csrf_token, link_csrf_token=link_csrf_token,
        allowance_message=allowance_message, next_url=next_url,
        existing_github_notice=not account and available == {'google', 'github'},
        demo_active=bool(demo_active and not account),
        demo_enabled=bool(demo_enabled and not account),
        demo_url='/demo/' + query,
    )
