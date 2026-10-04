"""Fly-only entry point. Local development continues to use app.create_app.

Supports a private installation or a public account sign-in site with
persistent personal accounts and separately enabled AI workspaces.
Local files and credentials are never published.
"""
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
from contextlib import closing

from werkzeug.wrappers import Request, Response
from werkzeug.middleware.proxy_fix import ProxyFix


class PrivateSite:
    """Protect HTML, APIs and every asset before Flask's profile middleware."""

    def __init__(self, application, username, password, database, hostname, public=False):
        self.application = application
        self.username = hashlib.sha256(username.encode()).digest()
        self.password = hashlib.sha256(password.encode()).digest()
        self.database = database
        self.hostname = hostname
        self.public = public

    def __call__(self, environ, start_response):
        request = Request(environ)
        if request.host != self.hostname:
            return Response('Unknown host', status=400)(environ, start_response)
        original_start_response = start_response

        def start_response(status, headers, exc_info=None):
            if request.is_secure:
                headers = [(key, value) for key, value in headers if key.lower() != 'strict-transport-security']
                headers.append(('Strict-Transport-Security', 'max-age=31536000'))
            return original_start_response(status, headers, exc_info)
        if request.path == '/healthz' and request.method in ('GET', 'HEAD'):
            try:
                uri = Path(self.database).resolve().as_uri() + '?mode=ro'
                with closing(sqlite3.connect(uri, uri=True, timeout=2)) as conn:
                    conn.execute('SELECT MAX(version) FROM schema_migrations').fetchone()
                response = Response('ok\n')
            except sqlite3.Error:
                response = Response('unavailable\n', status=503)
        else:
            credentials = request.authorization
            valid = self.public
            if credentials and credentials.type == 'basic':
                username = hashlib.sha256((credentials.username or '').encode()).digest()
                password = hashlib.sha256((credentials.password or '').encode()).digest()
                valid = hmac.compare_digest(username, self.username) & hmac.compare_digest(password, self.password)
            if valid:
                # Do not forward site credentials to application/provider code.
                environ.pop('HTTP_AUTHORIZATION', None)
                return self.application(environ, start_response)
            response = Response('Sign in to Russian Arcade.\n', status=401,
                                headers={'WWW-Authenticate': 'Basic realm="Russian Arcade", charset="UTF-8"'})
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response(environ, start_response)


def settings():
    """Validate before opening or migrating any database."""
    public = os.environ.get('PUBLIC_DEMO') == 'true'
    required = ('FLASK_SECRET_KEY', 'HOSTED_HOSTNAME', 'VOCAB_DB_PATH')
    if not public:
        required += ('HOSTED_ACCESS_USERNAME', 'HOSTED_ACCESS_PASSWORD')
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError('Hosted deployment requires session/access secrets, hostname and database path.')
    if len(os.environ['FLASK_SECRET_KEY']) < 32 or (not public and len(os.environ['HOSTED_ACCESS_PASSWORD']) < 24):
        raise RuntimeError('Use a generated session secret (32+ characters) and access password (24+ characters).')
    if not Path(os.environ['VOCAB_DB_PATH']).is_file():
        raise RuntimeError('Import a verified database snapshot onto the volume before starting the app.')
    return {key: os.environ[key] for key in required}


def create_hosted_app():
    values = settings()
    public = os.environ.get('PUBLIC_DEMO') == 'true'
    # PUBLIC_DEMO is the historical hosted security boundary, not permission
    # to open guest workspaces. The old sample experience now needs an opt-in.
    public_demo_enabled = public and os.environ.get('HOSTED_PUBLIC_DEMO_ENABLED') == 'true'
    from app import create_app
    overrides = {
        'SECRET_KEY': values['FLASK_SECRET_KEY'],
        'SESSION_COOKIE_SECURE': True,
        'WORD_POST_ALLOWED_HOSTS': (values['HOSTED_HOSTNAME'],),
        'WORD_POST_HOUSEHOLD_ENABLED': False,
        'HOSTED_ACCOUNTS_ENABLED': False,
        'HOSTED_TRIAL_AVAILABLE': False,
    }
    if public:
        overrides.update(OPENAI_API_KEY='', OPENROUTER_API_KEY='', ELEVENLABS_API_KEY='',
                         YANDEX_API_KEY='', GOOGLE_DRIVE_AUTO_AUTH=False, PUBLIC_DEMO=True,
                         MAX_CONTENT_LENGTH=16384)
    app = create_app(overrides)
    if public_demo_enabled:
        from public_demo import install_demo
        install_demo(app)
    application = app.wsgi_app
    ai_enabled = os.environ.get('AI_TRIAL_ENABLED') == 'true'
    guest_demo_enabled = public_demo_enabled and os.environ.get('HOSTED_GUEST_DEMO_ENABLED') == 'true'
    accounts_default = 'false' if guest_demo_enabled else os.environ.get('AI_TRIAL_ENABLED')
    accounts_enabled = os.environ.get('HOSTED_ACCOUNTS_ENABLED', accounts_default) == 'true'
    if public and (not public_demo_enabled or accounts_enabled or ai_enabled or guest_demo_enabled) and not os.environ.get('HOSTED_TRIAL_ROOT'):
        raise RuntimeError('Hosted accounts require HOSTED_TRIAL_ROOT on persistent storage.')
    if public and os.environ.get('HOSTED_TRIAL_ROOT'):
        from hosted_trial import HostedTrialDispatcher
        from services.ai_trial_budget import AITrialBudget
        root = Path(os.environ['HOSTED_TRIAL_ROOT']).resolve()
        ledger_path = root / 'ai-budget.sqlite3'
        oauth_configured = any(os.environ.get(provider + '_OAUTH_CLIENT_ID')
                               and os.environ.get(provider + '_OAUTH_CLIENT_SECRET')
                               for provider in ('GOOGLE', 'GITHUB'))
        app.config['HOSTED_ACCOUNTS_ENABLED'] = accounts_enabled and oauth_configured
        app.config['HOSTED_PUBLIC_DEMO_ENABLED'] = public_demo_enabled
        app.config['HOSTED_GUEST_DEMO_ENABLED'] = guest_demo_enabled
        app.config['HOSTED_TRIAL_AVAILABLE'] = ai_enabled and (guest_demo_enabled or app.config['HOSTED_ACCOUNTS_ENABLED'])
        if ai_enabled:
            required = ('DEMO_OPENAI_API_KEY', 'DEMO_ELEVENLABS_API_KEY', 'DEMO_OPENROUTER_API_KEY')
            if not (guest_demo_enabled or oauth_configured) or any(not os.environ.get(key) for key in required):
                raise RuntimeError('The whole-app AI trial needs dedicated demo provider keys and guest demo access or a configured sign-in provider.')
            # Initialization is an explicit administrative step. A missing volume
            # must never reset the spending allowance during a restart.
            with AITrialBudget(ledger_path, enabled=True)._transaction() as conn:
                conn.execute('SELECT halted FROM trial_control WHERE id=1').fetchone()
        if accounts_enabled and not oauth_configured:
            raise RuntimeError('Hosted accounts require Google or GitHub OAuth client ID and client secret.')
        trial_config = {
            'AI_TRIAL_ENABLED': ai_enabled,
            'OPENAI_API_KEY': os.environ.get('DEMO_OPENAI_API_KEY', '') if ai_enabled else '',
            'ELEVENLABS_API_KEY': os.environ.get('DEMO_ELEVENLABS_API_KEY', '') if ai_enabled else '',
            'OPENROUTER_API_KEY': os.environ.get('DEMO_OPENROUTER_API_KEY', '') if ai_enabled else '',
            'YANDEX_API_KEY': '',
        }
        application = HostedTrialDispatcher(application, create_app, root=root,
            ledger_path=ledger_path, secret=values['FLASK_SECRET_KEY'],
            hostname=values['HOSTED_HOSTNAME'], enabled=accounts_enabled, ai_enabled=ai_enabled, app_config=trial_config,
            guest_demo_enabled=guest_demo_enabled,
            public_preview_enabled=public_demo_enabled,
            client_id=os.environ.get('GITHUB_OAUTH_CLIENT_ID', ''),
            client_secret=os.environ.get('GITHUB_OAUTH_CLIENT_SECRET', ''),
            google_client_id=os.environ.get('GOOGLE_OAUTH_CLIENT_ID', ''),
            google_client_secret=os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', ''))
        app.extensions['hosted_trial'] = application
    app.wsgi_app = PrivateSite(application, values.get('HOSTED_ACCESS_USERNAME', ''),
                              values.get('HOSTED_ACCESS_PASSWORD', ''), values['VOCAB_DB_PATH'],
                              values['HOSTED_HOSTNAME'], public=public)
    # Fly terminates HTTPS; trust its protocol header, never forwarded host/IP.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0, x_port=0, x_prefix=0)
    return app


def main():
    if (os.environ.get('PUBLIC_DEMO') == 'true'
            and os.environ.get('HOSTED_PUBLIC_DEMO_ENABLED') == 'true'):
        from public_demo import prepare_demo
        prepare_demo()
    values = settings()
    from migrations import upgrade_database
    upgrade_database(values['VOCAB_DB_PATH'])  # Transactional, with pre-migration backup.
    if os.environ.get('AI_TRIAL_ENABLED') == 'true':
        recover_trial_voice_sessions(os.environ['HOSTED_TRIAL_ROOT'], os.environ.get('DEMO_OPENAI_API_KEY', ''))
    # One process owns in-process background jobs. Threads serve concurrent requests.
    os.execvp('gunicorn', ['gunicorn', '--bind', '0.0.0.0:8080', '--workers', '1',
                         '--worker-class', 'gthread', '--threads', '8', '--timeout', '300',
                         '--graceful-timeout', '110', '--error-logfile', '-',
                         'hosted:create_hosted_app()'])


def recover_trial_voice_sessions(root, api_key):
    """Hang up calls left by a process restart; retain their unconfirmed spend.

    A WebRTC connection can outlive the application server. Never interpret a
    restart as proof that provider billing stopped or restore its allowance.
    """
    from services.live_voice_provider import LiveVoiceProvider
    provider = LiveVoiceProvider({'OPENAI_API_KEY': api_key})
    for database in (Path(root) / 'tenants').glob('*/vocab.db'):
        with closing(sqlite3.connect(database, timeout=5)) as conn:
            rows = conn.execute("SELECT id,provider_id FROM live_conversation_sessions WHERE state IN ('connecting','live','ending')").fetchall()
            for sid, provider_id in rows:
                if provider_id:
                    provider.hangup(provider_id)
                conn.execute("UPDATE live_conversation_sessions SET state='interrupted',answer_sdp=NULL,error=? WHERE id=?",
                             ('The server restarted. Start a new conversation when you are ready.', sid))
            conn.commit()


if __name__ == '__main__':
    main()
