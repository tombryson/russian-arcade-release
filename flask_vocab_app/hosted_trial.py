"""Verified accounts and temporary guest demos in isolated hosted workspaces.

The public sample application remains usable without signing in. A verified
account gets a separate database, media directory and Flask session.
Provider credentials never pass through the browser or the identity database.
"""
from collections import OrderedDict
from contextlib import closing, contextmanager
from hashlib import sha256
import base64
import hmac
import json
import logging
import re
from pathlib import Path
import secrets
import shutil
import sqlite3
import threading
import time
from urllib.parse import urlencode, urlsplit

import requests
from hosted_account_page import ACCOUNT_PUBLIC_ASSETS
from hosted_demo_mount import DemoMount, demo_url, packaged_asset
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.wrappers import Request, Response
from werkzeug.utils import redirect
from werkzeug.wsgi import ClosingIterator

COOKIE = '__Host-russian-arcade-trial'
FLOW_COOKIE = '__Host-russian-arcade-oauth'
GUEST_COOKIE = '__Host-russian-arcade-demo'
SESSION_SECONDS = 7 * 24 * 3600
FLOW_SECONDS = 600
GUEST_SESSION_SECONDS = 24 * 3600
GUEST_STORAGE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_GUESTS = 32
DEFAULT_TENANT_STORAGE_BYTES = 100 * 1024 * 1024
MAX_STORAGE_CONFIG_BYTES = 64 * 1024
logger = logging.getLogger(__name__)


def safe_return_url(value):
    """Only absolute paths on this application are accepted after sign-in."""
    if (not isinstance(value, str) or not value.startswith('/') or value.startswith('//')
            or '\\' in value or any(ord(char) < 32 for char in value)
            or len(value) > 2000):
        return '/'
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or parts.path.startswith('/trial/'):
        return '/'
    if parts.path in ('/post', '/post/'):
        return parts._replace(path='/').geturl()
    return value


class TrialIdentityError(ValueError):
    pass


class GitHubIdentity:
    """OAuth authorization-code flow with PKCE; no repository scopes requested."""
    def __init__(self, client_id, client_secret, callback, *, http=requests):
        self.client_id, self.client_secret, self.callback = client_id, client_secret, callback
        self.http = http

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret)

    def authorization_url(self, state, verifier):
        challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        return 'https://github.com/login/oauth/authorize?' + urlencode({
            'client_id': self.client_id, 'redirect_uri': self.callback,
            'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
            'scope': '',
        })

    def verify(self, code, verifier):
        """Use the token once to identify its user, then discard it."""
        try:
            response = self.http.post('https://github.com/login/oauth/access_token',
                data={'client_id': self.client_id, 'client_secret': self.client_secret,
                      'redirect_uri': self.callback, 'code': code, 'code_verifier': verifier},
                headers={'Accept': 'application/json'}, timeout=15)
            response.raise_for_status()
            token = response.json().get('access_token')
            if not isinstance(token, str) or not token:
                raise TrialIdentityError('GitHub did not complete sign-in. Please try again.')
            response = self.http.get('https://api.github.com/user',
                headers={'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ' + token,
                         'X-GitHub-Api-Version': '2022-11-28'}, timeout=15)
            response.raise_for_status()
            user = response.json()
        except (requests.RequestException, ValueError, TypeError, AttributeError) as error:
            raise TrialIdentityError('GitHub sign-in is unavailable. Please try again.') from error
        if not isinstance(user, dict) or type(user.get('id')) is not int or user['id'] <= 0 or user.get('type') != 'User':
            raise TrialIdentityError('A personal GitHub account is required.')
        return 'github:' + str(user['id']), str(user.get('login') or 'Learner')[:60]


class GoogleIdentity:
    """Server-side OIDC code flow. Tokens are verified and never persisted."""
    def __init__(self, client_id, client_secret, callback, *, http=requests):
        self.client_id, self.client_secret, self.callback = client_id, client_secret, callback
        self.http = http

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret)

    def authorization_url(self, state, verifier, nonce):
        challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
            'client_id': self.client_id, 'redirect_uri': self.callback,
            'response_type': 'code', 'scope': 'openid profile',
            'state': state, 'nonce': nonce, 'code_challenge': challenge,
            'code_challenge_method': 'S256', 'prompt': 'select_account',
        })

    def verify(self, code, verifier, nonce):
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.id_token import verify_oauth2_token
        try:
            response = self.http.post('https://oauth2.googleapis.com/token',
                data={'grant_type': 'authorization_code', 'client_id': self.client_id,
                      'client_secret': self.client_secret, 'redirect_uri': self.callback,
                      'code': code, 'code_verifier': verifier}, timeout=15)
            response.raise_for_status()
            token = response.json().get('id_token')
            if not isinstance(token, str) or not token or len(token) > 16384:
                raise ValueError('Missing identity token')
            transport = GoogleRequest()
            # Bound certificate fetch time as well as the code exchange. The
            # library checks Google's signature, issuer, audience and lifetime.
            def bounded_request(*args, **kwargs):
                kwargs['timeout'] = 15
                return transport(*args, **kwargs)
            claims = verify_oauth2_token(token, bounded_request, audience=self.client_id)
            subject, returned_nonce = claims.get('sub'), claims.get('nonce')
            if (not isinstance(subject, str) or not valid_provider_identity('google', 'google:' + subject)
                    or not isinstance(returned_nonce, str) or not nonce
                    or not hmac.compare_digest(returned_nonce, nonce)
                    or claims.get('azp', self.client_id) != self.client_id):
                raise ValueError('Identity token does not match this sign-in')
            # Identity is the immutable subject, never an email address. A
            # matching email on another provider cannot join two workspaces.
            return 'google:' + subject, str(claims.get('name') or 'Learner')[:60]
        except (requests.RequestException, GoogleAuthError, ValueError, TypeError, KeyError, AttributeError) as error:
            raise TrialIdentityError('Google sign-in is unavailable. Please try again.') from error


def valid_provider_identity(provider, identity):
    if not isinstance(identity, str):
        return False
    if provider == 'github':
        return bool(re.fullmatch(r'github:[1-9][0-9]*', identity))
    if provider == 'google':
        subject = identity.removeprefix('google:')
        return identity.startswith('google:') and 1 <= len(subject) <= 255 and subject.isascii()
    return False


def tenant_settings(root, identity, *, secret, ledger_path, hostname):
    """Paths are derived exclusively from a verified or server-issued identity."""
    digest = sha256(identity.encode()).hexdigest()
    directory = Path(root).resolve() / 'tenants' / digest
    return {
        'HOSTED_AI_TRIAL': True, 'PUBLIC_DEMO': False,
        'AI_TRIAL_IDENTITY': identity, 'AI_TRIAL_LEDGER_PATH': str(Path(ledger_path).resolve()),
        'SECRET_KEY': hmac.new(secret.encode(), ('tenant:' + identity).encode(), 'sha256').hexdigest(),
        'DB_PATH': str(directory / 'vocab.db'), 'APP_MEDIA_DIR': str(directory / 'media'),
        'UPLOAD_FOLDER': str(directory / 'uploads'), 'WORD_POST_ASSET_DIR': str(directory / 'assets'),
        'ANKI_MEDIA_DIR': str(directory / 'anki-media'), 'SESSION_FILE_DIR': str(directory / 'sessions'),
        'SESSION_COOKIE_NAME': '__Host-ra-session-' + digest[:16],
        'SESSION_COOKIE_SECURE': True, 'SESSION_COOKIE_HTTPONLY': True, 'SESSION_COOKIE_SAMESITE': 'Lax',
        'WORD_POST_HOUSEHOLD_ENABLED': False, 'WORD_POST_ALLOWED_HOSTS': (hostname,),
        'GOOGLE_DRIVE_AUTO_AUTH': False, 'GOOGLE_DRIVE_FILE_ID': '',
        'GOOGLE_DRIVE_CREDENTIALS_FILE': str(directory / 'disabled-drive-credentials.json'),
        'GOOGLE_DRIVE_TOKEN_FILE': str(directory / 'disabled-drive-token.json'),
        'GOOGLE_DRIVE_CACHE_FILE': str(directory / 'disabled-drive-cache.txt'),
        'MAX_CONTENT_LENGTH': 12 * 1024 * 1024, 'LESSON_MAX_PAGES': 12,
    }


def is_guest_identity(identity):
    """Only server-generated opaque identities can enter guest lifecycle code."""
    return isinstance(identity, str) and bool(re.fullmatch(r'demo:[0-9a-f]{32}', identity))


def seed_trial_workspace(config, display_name):
    """Seed authored vocabulary and sample cards, never a personal DB snapshot."""
    from migrations import upgrade_database
    from repositories.learning_repository import transaction
    from services.sample_vocabulary import seed_sample_items, sample_needs_repair
    from services.learning_assets import LocalAssetStore
    from services.learning_content import ContentService
    from services.personal_learning import personal_access
    database = config['DB_PATH']
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    upgrade_database(database, backup=Path(database).is_file())
    with closing(sqlite3.connect(database)) as existing:
        needs_repair = sample_needs_repair(existing)
        if needs_repair:
            backup = str(database) + '.before-vocabulary-repair-' + secrets.token_hex(6) + '.bak'
            with closing(sqlite3.connect(backup)) as snapshot:
                existing.backup(snapshot)
    with transaction(database, write=True) as conn:
        seeded = conn.execute("SELECT 1 FROM learning_content_versions WHERE content_id='trial-sample' AND status='published'").fetchone()
        # Repair earlier sample vocabulary even when its published deck exists.
        # Card IDs, published content and review schedules remain unchanged.
        items = seed_sample_items(conn, 'trial-sample')
    if seeded:
        return
    credential = personal_access(database)
    content = ContentService(database, LocalAssetStore(config['WORD_POST_ASSET_DIR']))
    version = content.import_draft(dict(schema_version=2, id='trial-sample', kind='deck',
        title='First Russian words · sample cards', source='Authored sample content, no personal records.', items=items))
    content.publish(credential, version, 'Russian Arcade demo')
    with transaction(database, write=True) as conn:
        conn.execute("UPDATE learning_profiles SET display_name=? WHERE id='personal-learning'", (display_name,))
        conn.execute('DELETE FROM household_access')


def install_trial_session(app):
    """A hosted identity selects its own single profile, never local accounts."""
    from flask import jsonify, redirect as flask_redirect, request, session
    from services.personal_learning import PersonalSessions, PERSONAL_PROFILE
    sessions = PersonalSessions(app.config['DB_PATH'], lifetime=3600)

    def boundary():
        if request.blueprint == 'flashcards' or request.path in {
            '/sync', '/sync/preview', '/sync/history', '/sync_vocab', '/sanitize_vocab',
            '/apply_sanitization', '/edit_word', '/delete_word', '/add_word',
        } or request.args.get('source', 'db') != 'db':
            return jsonify(error={'code': 'local_tool', 'message': 'Drive and Anki tools run in a local installation.'}), 403
        if request.path in {'/post/profiles', '/post/household'}:
            return flask_redirect('/trial/account')
        if request.endpoint in {'user_sessions.create_profile', 'user_sessions.select_profile',
                                'user_sessions.actions', 'user_sessions.end'}:
            return jsonify(error={'code': 'hosted_identity',
                'message': 'Manage your signed-in account from the account menu.'}), 403
        state = sessions.state(session.get('personal_access_id'))
        if not state['profile'] or state['profile']['id'] != PERSONAL_PROFILE:
            session['personal_access_id'] = sessions.select(PERSONAL_PROFILE, session.get('personal_access_id'))
            session.permanent = True
    app.before_request_funcs.setdefault(None, []).insert(0, boundary)

    @app.after_request
    def trial_notice(response):
        if response.mimetype == 'text/html' and not response.direct_passthrough:
            body = response.get_data(as_text=True)
            if '</head>' in body and '</body>' in body:
                ai_message = ('The shared AI allowance is US$1 a day and US$20 a month. '
                              if app.config.get('AI_TRIAL_ENABLED') else
                              'AI generation is currently turned off. ')
                if app.config.get('HOSTED_GUEST_DEMO'):
                    notice = ('<details class="demo-notice"><summary>Demo</summary>'
                              '<p>Your demo progress lasts 24 hours. ' + ai_message +
                              '<a href="/trial/account">Demo and account options</a></p></details>')
                else:
                    notice = ('<details class="demo-notice"><summary>Your account</summary>'
                              '<p>Your practice is saved in your account. ' + ai_message +
                              '<a href="/trial/account">Account and sign out</a></p></details>')
                body = body.replace('</head>', '<link rel="stylesheet" href="/static/css/public_demo.css?v=2"></head>', 1)
                response.set_data(body.replace('</body>', notice + '</body>', 1))
        return response


class HostedTrialDispatcher:
    """Route accounts and temporary demo browsers to their own workspaces."""
    def __init__(self, public_application, app_factory, *, root, ledger_path, secret, hostname,
                 client_id='', client_secret='', app_config=None, enabled=False, ai_enabled=None,
                 max_tenants=100, max_cached_apps=8, identity_provider=None,
                 google_client_id='', google_client_secret='', identity_providers=None,
                 budget=None, seed=seed_trial_workspace, clock=time.time,
                 guest_demo_enabled=False, max_guests=DEFAULT_MAX_GUESTS):
        self.public_application, self.app_factory = public_application, app_factory
        self.root, self.ledger_path = Path(root).resolve(), Path(ledger_path).resolve()
        self.secret, self.hostname, self.enabled = secret, hostname, enabled
        self.config = dict(app_config or {})
        # Existing callers enabled authentication and paid AI together. New
        # callers can enable persistent accounts while keeping providers off.
        self.ai_enabled = bool(self.config.get('AI_TRIAL_ENABLED', enabled)) if ai_enabled is None else bool(ai_enabled)
        self.config['AI_TRIAL_ENABLED'] = self.ai_enabled
        self.max_tenants, self.max_cached_apps = max_tenants, max_cached_apps
        self.guest_demo_enabled, self.max_guests = bool(guest_demo_enabled), max_guests
        self.last_guest_cleanup = 0
        self.clock, self.seed = clock, seed
        self.providers = {
            'google': GoogleIdentity(google_client_id, google_client_secret, 'https://' + hostname + '/trial/callback/google'),
            'github': identity_provider or GitHubIdentity(client_id, client_secret, 'https://' + hostname + '/trial/callback'),
        }
        self.providers.update(identity_providers or {})
        if set(self.providers) - {'google', 'github'}:
            raise ValueError('Unsupported sign-in provider.')
        self.signer = URLSafeTimedSerializer(secret, salt='russian-arcade-hosted-trial-v1')
        self.guest_signer = URLSafeTimedSerializer(secret, salt='russian-arcade-guest-demo-v1')
        self.csrf_signer = URLSafeTimedSerializer(secret, salt='russian-arcade-hosted-trial-signout-v1')
        self.link_signer = URLSafeTimedSerializer(secret, salt='russian-arcade-hosted-link-v1')
        if max_tenants < 1 or max_cached_apps < 1 or max_guests < 1:
            raise ValueError('Positive tenant and application limits are required.')
        self.cache, self.lock = OrderedDict(), threading.RLock()
        self.inflight, self.storage_reserved = {}, {}
        if budget is None:
            from services.ai_trial_budget import AITrialBudget
            budget = AITrialBudget(self.ledger_path, enabled=self.ai_enabled)
        self.budget = budget
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.registry = self.root / 'identities.sqlite3'
        with self._db() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS identities(identity TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, identity TEXT NOT NULL REFERENCES identities(identity), expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS oauth_flows(state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, verifier TEXT NOT NULL, next_url TEXT NOT NULL, expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_limits(bucket INTEGER PRIMARY KEY, attempts INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS request_limits(identity TEXT NOT NULL, kind TEXT NOT NULL, bucket INTEGER NOT NULL, attempts INTEGER NOT NULL, PRIMARY KEY(identity,kind,bucket));
                CREATE TABLE IF NOT EXISTS guest_sessions(token_hash TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS guest_admissions(kind TEXT NOT NULL, bucket INTEGER NOT NULL, attempts INTEGER NOT NULL, PRIMARY KEY(kind,bucket));
            ''')
            # executescript commits the initial transaction; serialize additive
            # migrations before checking columns to avoid concurrent ALTERs.
            conn.execute('BEGIN IMMEDIATE')
            # Additive migration: identities remain canonical workspace keys.
            # Existing GitHub sessions, tenant paths and spend are untouched.
            columns = {row['name'] for row in conn.execute('PRAGMA table_info(oauth_flows)')}
            for name, definition in (
                    ('provider', "TEXT NOT NULL DEFAULT 'github'"),
                    ('nonce', "TEXT NOT NULL DEFAULT ''"),
                    ('purpose', "TEXT NOT NULL DEFAULT 'sign-in'"),
                    ('session_hash', "TEXT NOT NULL DEFAULT ''")):
                if name not in columns:
                    conn.execute(f'ALTER TABLE oauth_flows ADD COLUMN {name} {definition}')
            conn.execute('''CREATE TABLE IF NOT EXISTS identity_aliases(
                provider_identity TEXT PRIMARY KEY,
                provider TEXT NOT NULL CHECK(provider IN ('github','google')),
                identity TEXT NOT NULL REFERENCES identities(identity),
                created_at INTEGER NOT NULL,
                UNIQUE(identity,provider))''')
            conn.execute('''INSERT OR IGNORE INTO identity_aliases(provider_identity,provider,identity,created_at)
                SELECT identity,'github',identity,created_at FROM identities WHERE identity LIKE 'github:%' ''')

    @property
    def provider(self):
        """Retain the legacy injectable GitHub provider for callers/tests."""
        return self.providers['github']

    @provider.setter
    def provider(self, value):
        self.providers['github'] = value

    def _provider_options(self, next_url='/'):
        if not self.enabled:
            return []
        return [{'id': key, 'name': {'google': 'Google', 'github': 'GitHub'}[key],
                 'sign_in_url': '/trial/sign-in/' + key + ('?' + urlencode({'next': next_url}) if next_url != '/' else '')}
                for key, provider in self.providers.items() if provider.configured]

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.registry, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _session(self, request):
        value = request.cookies.get(COOKIE)
        if not value:
            return None
        try:
            token = self.signer.loads(value, max_age=SESSION_SECONDS)
            if not isinstance(token, str):
                return None
        except (BadSignature, SignatureExpired):
            return None
        with self._db() as conn:
            row = conn.execute('SELECT s.token_hash,s.identity,i.display_name FROM sessions s JOIN identities i USING(identity) WHERE token_hash=? AND expires_at>?',
                               (sha256(token.encode()).hexdigest(), int(self.clock()))).fetchone()
        return dict(row) if row else None

    def _guest_session(self, request):
        if not self.guest_demo_enabled:
            return None
        try:
            token = self.guest_signer.loads(request.cookies.get(GUEST_COOKIE, ''), max_age=GUEST_SESSION_SECONDS)
            if not isinstance(token, str):
                return None
        except (BadSignature, SignatureExpired):
            return None
        with self._db() as conn:
            row = conn.execute('SELECT * FROM guest_sessions WHERE token_hash=? AND expires_at>?',
                (sha256(token.encode()).hexdigest(), int(self.clock()))).fetchone()
        if not row or not is_guest_identity(row['identity']):
            return None
        return {**dict(row), 'display_name': 'Demo'}

    def _cleanup_guests(self, *, force=False):
        """Remove expired guest files only; never erase spend or personal accounts.

        The same lock protects request admission, app eviction and background
        workers. A long recording or generation keeps its workspace until idle.
        No filesystem path supplied by a visitor participates in cleanup.
        """
        now = int(self.clock())
        with self.lock:
            if not force and now - self.last_guest_cleanup < 60:
                return
            self.last_guest_cleanup = now
            with self._db() as conn:
                rows = conn.execute('SELECT identity FROM guest_sessions WHERE expires_at<=?', (now,)).fetchall()
                for row in rows:
                    identity = row['identity']
                    if not is_guest_identity(identity):
                        continue
                    if (conn.execute('SELECT 1 FROM identities WHERE identity=?', (identity,)).fetchone()
                            or conn.execute('SELECT 1 FROM identity_aliases WHERE identity=?', (identity,)).fetchone()):
                        continue
                    app = self.cache.get(identity)
                    if self.inflight.get(identity, 0) or (app and self._busy(identity, app)):
                        continue
                    parent = self.root / 'tenants'
                    directory = parent / sha256(identity.encode()).hexdigest()
                    # Refuse redirected roots; rmtree itself does not follow
                    # symlinks inside a genuine generated guest directory.
                    if parent.is_symlink() or directory.is_symlink() or directory.resolve().parent != parent.resolve():
                        continue
                    if app:
                        for executor in app.extensions.get('trial_executors', []):
                            executor.shutdown(wait=False, cancel_futures=False)
                        self.cache.pop(identity, None)
                    if directory.exists():
                        shutil.rmtree(directory)
                    conn.execute('DELETE FROM guest_sessions WHERE identity=?', (identity,))
                    conn.execute('DELETE FROM request_limits WHERE identity=?', (identity,))
                    self.inflight.pop(identity, None)
                    self.storage_reserved.pop(identity, None)

    def _demo(self, request, account, guest):
        if not self.guest_demo_enabled:
            return self._response(Response('Not found', status=404))
        if request.method not in ('GET', 'HEAD'):
            return self._response(Response('Method not allowed', status=405, headers={'Allow': 'GET, HEAD'}))
        # Demo and personal accounts coexist. The URL selects the workspace;
        # entering the demo never signs out or modifies a personal account.
        next_url = demo_url(safe_return_url(request.args.get('next')))
        if next_url == '/demo':
            next_url = '/demo/'
        if request.method == 'HEAD' and request.environ.get('russian_arcade.demo'):
            return self._response(Response(status=200))
        if guest or request.method == 'HEAD':
            return self._response(redirect(next_url))
        purpose = (request.headers.get('Sec-Purpose', '') + request.headers.get('Purpose', '')).lower()
        if ('prefetch' in purpose or request.headers.get('Sec-Fetch-Dest') not in (None, 'document')
                or request.headers.get('Origin') not in (None, 'https://' + self.hostname)):
            return self._response(Response(status=204))
        now = int(self.clock())
        token, identity = secrets.token_urlsafe(40), 'demo:' + secrets.token_hex(16)
        with self.lock:
            self._cleanup_guests(force=True)
            with self._db() as conn:
                for kind, period, maximum in (('minute', 60, 12), ('hour', 3600, 30), ('day', 86400, 100)):
                    bucket = now // period
                    conn.execute('DELETE FROM guest_admissions WHERE kind=? AND bucket<?', (kind, bucket))
                    conn.execute('INSERT INTO guest_admissions VALUES (?,?,1) ON CONFLICT(kind,bucket) DO UPDATE SET attempts=attempts+1',
                                 (kind, bucket))
                    if conn.execute('SELECT attempts FROM guest_admissions WHERE kind=? AND bucket=?', (kind, bucket)).fetchone()[0] > maximum:
                        response = self._page('Please try again shortly', 'The demo has had a lot of visitors. You can still explore the sample activities.', 429)
                        response.headers['Retry-After'] = str(period - now % period)
                        return response
                if (conn.execute('SELECT COUNT(*) FROM guest_sessions').fetchone()[0] >= self.max_guests
                        or shutil.disk_usage(self.root).free < 256 * 1024 * 1024 + GUEST_STORAGE_BYTES):
                    return self._page('The demo is busy', 'Please try again later. Sample activities are still available.', 503)
                conn.execute('INSERT INTO guest_sessions VALUES (?,?,?,?)',
                    (sha256(token.encode()).hexdigest(), identity, now, now + GUEST_SESSION_SECONDS))
        response = self._response(redirect(next_url))
        response.set_cookie(GUEST_COOKIE, self.guest_signer.dumps(token), max_age=GUEST_SESSION_SECONDS,
                            httponly=True, secure=True, samesite='Lax', path='/')
        return response

    def _response(self, response):
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    def _json(self, value, status=200):
        return self._response(Response(json.dumps(value), status=status, content_type='application/json'))

    def _maintenance(self, identity):
        """Only an operator-owned marker can pause a verified workspace."""
        digest = sha256(identity.encode()).hexdigest()
        return (self.root / 'operator' / 'maintenance' / digest).exists()

    def _maintenance_response(self, request, account):
        message = 'Your saved practice is temporarily unavailable while we update your workspace. Please try again shortly.'
        if (request.path.startswith('/api/') or request.is_json
                or request.accept_mimetypes.best == 'application/json'):
            response = self._json({'error': {'code': 'workspace_maintenance', 'message': message}}, 503)
        else:
            response = self._page('Your workspace is being updated', message, 503, account=account)
        response.headers['Retry-After'] = '60'
        return response

    def _storage_limit(self, identity):
        """Read operator overrides; malformed or absent values keep the default.

        This path is outside tenant uploads and never comes from request data.
        Read on admission so an atomic operator update needs no app restart.
        """
        if is_guest_identity(identity):
            return GUEST_STORAGE_BYTES
        try:
            with (self.root / 'operator' / 'storage-limits.json').open('rb') as source:
                raw = source.read(MAX_STORAGE_CONFIG_BYTES + 1)
            if len(raw) > MAX_STORAGE_CONFIG_BYTES:
                return DEFAULT_TENANT_STORAGE_BYTES
            limits = json.loads(raw)
            value = limits.get(sha256(identity.encode()).hexdigest()) if isinstance(limits, dict) else None
            if type(value) is int and value > 0:
                return value
        except (OSError, ValueError, UnicodeError):
            pass
        return DEFAULT_TENANT_STORAGE_BYTES

    def _page(self, title, message, status=200, *, account=None, next_url='/', allowance_message='', demo_active=False):
        from hosted_account_page import render_account_page
        connected = []
        if account:
            with self._db() as conn:
                connected = [row[0] for row in conn.execute(
                    'SELECT provider FROM identity_aliases WHERE identity=?', (account['identity'],))]
        body = render_account_page(title, message, providers=self._provider_options(next_url),
            account={'display_name': account['display_name']} if account else None,
            csrf_token=self.csrf_signer.dumps(account['token_hash']) if account else '',
            link_csrf_token=self.link_signer.dumps(account['token_hash']) if account else '',
            connected_providers=connected, next_url=next_url, allowance_message=allowance_message,
            demo_enabled=self.guest_demo_enabled, demo_active=demo_active)
        return self._response(Response(body, status=status, content_type='text/html; charset=utf-8'))

    def _begin(self, request, provider_name='github', *, account=None):
        provider = self.providers.get(provider_name)
        if not self.enabled or not provider or not provider.configured:
            return self._page('Sign-in unavailable', 'This sign-in option is not available. You can still explore the sample activities.', 503)
        state, browser, verifier, nonce = (secrets.token_urlsafe(size) for size in (32, 32, 48, 32))
        now = int(self.clock())
        with self._db() as conn:
            bucket = now // 60
            conn.execute('DELETE FROM auth_limits WHERE bucket<?', (bucket - 1,))
            conn.execute('INSERT INTO auth_limits(bucket,attempts) VALUES (?,1) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1', (bucket,))
            if conn.execute('SELECT attempts FROM auth_limits WHERE bucket=?', (bucket,)).fetchone()[0] > 30:
                return self._page('Please wait', 'Too many sign-in attempts. Please try again in a minute.', 429)
            conn.execute('DELETE FROM oauth_flows WHERE expires_at<=?', (now,))
            conn.execute('''INSERT INTO oauth_flows
                (state_hash,browser_hash,verifier,next_url,expires_at,provider,nonce,purpose,session_hash)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (sha256(state.encode()).hexdigest(), sha256(browser.encode()).hexdigest(), verifier,
                 '/trial/account' if account else safe_return_url(request.args.get('next')),
                 now + FLOW_SECONDS, provider_name, nonce, 'connect' if account else 'sign-in',
                 account['token_hash'] if account else ''))
        url = (provider.authorization_url(state, verifier, nonce) if provider_name == 'google'
               else provider.authorization_url(state, verifier))
        response = self._response(redirect(url))
        response.set_cookie(FLOW_COOKIE, browser, max_age=FLOW_SECONDS, httponly=True, secure=True, samesite='Lax', path='/')
        return response

    def _valid_action(self, request, account, signer):
        valid_origin = (request.headers.get('Origin') in (None, 'https://' + self.hostname)
                        and request.headers.get('Sec-Fetch-Site') != 'cross-site')
        try:
            token = signer.loads(request.form.get('csrf_token', ''), max_age=3600)
        except (BadSignature, SignatureExpired):
            token = None
        return bool(valid_origin and account and token == account['token_hash'])

    def _callback(self, request, provider_name='github'):
        provider = self.providers.get(provider_name)
        state, browser, code = request.args.get('state', ''), request.cookies.get(FLOW_COOKIE, ''), request.args.get('code', '')
        if (not self.enabled or not provider or not provider.configured or not state or not browser
                or len(state) > 128 or len(browser) > 128 or len(code) > 2048):
            return self._page('Sign-in not completed', 'Please start sign-in again.', 400)
        with self._db() as conn:
            flow = conn.execute('SELECT * FROM oauth_flows WHERE state_hash=? AND expires_at>?',
                                (sha256(state.encode()).hexdigest(), int(self.clock()))).fetchone()
            if (not flow or flow['provider'] != provider_name
                    or not hmac.compare_digest(flow['browser_hash'], sha256(browser.encode()).hexdigest())):
                return self._page('Sign-in expired', 'Please start sign-in again.', 400)
            conn.execute('DELETE FROM oauth_flows WHERE state_hash=?', (flow['state_hash'],))
        if request.args.get('error') or not code:
            response = self._page('Sign-in cancelled', 'You can try again or continue exploring Russian Arcade.', 400)
            response.delete_cookie(FLOW_COOKIE, secure=True, httponly=True, samesite='Lax', path='/')
            return response
        previous_session = self._session(request)
        account = previous_session if flow['purpose'] == 'connect' else None
        if flow['purpose'] == 'connect' and (not account or account['token_hash'] != flow['session_hash']):
            return self._page('Connection expired', 'Sign in to your account and connect this sign-in option again.', 403)
        try:
            external_identity, name = (provider.verify(code, flow['verifier'], flow['nonce'])
                if provider_name == 'google' else provider.verify(code, flow['verifier']))
            if not valid_provider_identity(provider_name, external_identity):
                raise TrialIdentityError('A verified provider identity is required.')
            now = int(self.clock())
            with self._db() as conn:
                alias = conn.execute('SELECT identity FROM identity_aliases WHERE provider_identity=?',
                                     (external_identity,)).fetchone()
                if account:
                    # Recheck after the network call under the write lock. A
                    # sign-out during provider verification revokes this flow.
                    active = conn.execute('SELECT identity FROM sessions WHERE token_hash=? AND expires_at>?',
                                          (flow['session_hash'], now)).fetchone()
                    if not active or active['identity'] != account['identity']:
                        return self._page('Connection expired', 'Sign in to your account and connect this sign-in option again.', 403)
                    identity = account['identity']
                    existing_provider = conn.execute('SELECT provider_identity FROM identity_aliases WHERE identity=? AND provider=?',
                                                      (identity, provider_name)).fetchone()
                    if ((alias and alias['identity'] != identity)
                            or (existing_provider and existing_provider['provider_identity'] != external_identity)):
                        return self._page('Account already connected',
                            'This sign-in option is already connected to an account. Your saved practice has not changed.', 409)
                elif alias:
                    identity = alias['identity']
                else:
                    if conn.execute('SELECT COUNT(*) FROM identities').fetchone()[0] >= self.max_tenants:
                        return self._page('Demo capacity reached', 'The demo is full for now. Sample activities are still available.', 503)
                    # Keep existing GitHub keys byte-for-byte. Hash new Google
                    # subjects to bound workspace and budget identifier length.
                    identity = external_identity if provider_name == 'github' else 'google:' + sha256(external_identity.encode()).hexdigest()
                    conn.execute('INSERT INTO identities VALUES (?,?,?)', (identity, name[:60], now))
                if not alias:
                    conn.execute('INSERT INTO identity_aliases VALUES (?,?,?,?)',
                                 (external_identity, provider_name, identity, now))
                # A second provider must not overwrite the original account's
                # display name or construct a new workspace/spending identity.
                name = conn.execute('SELECT display_name FROM identities WHERE identity=?', (identity,)).fetchone()[0]
            if account:
                response = self._response(redirect('/trial/account'))
                response.delete_cookie(FLOW_COOKIE, secure=True, httponly=True, samesite='Lax', path='/')
                return response
            if not self._maintenance(identity):
                self._application(identity, name)
        except (TrialIdentityError, ValueError):
            return self._page('Sign-in not completed', 'Your personal workspace could not be opened. Please try again later.', 503)
        token = secrets.token_urlsafe(40)
        with self._db() as conn:
            conn.execute('DELETE FROM sessions WHERE expires_at<=?', (int(self.clock()),))
            if previous_session:
                conn.execute('DELETE FROM sessions WHERE token_hash=?', (previous_session['token_hash'],))
                conn.execute('DELETE FROM oauth_flows WHERE session_hash=?', (previous_session['token_hash'],))
            conn.execute('INSERT INTO sessions VALUES (?,?,?)',
                         (sha256(token.encode()).hexdigest(), identity, int(self.clock()) + SESSION_SECONDS))
        response = self._response(redirect(flow['next_url']))
        response.set_cookie(COOKIE, self.signer.dumps(token), max_age=SESSION_SECONDS, httponly=True, secure=True, samesite='Lax', path='/')
        response.delete_cookie(FLOW_COOKIE, secure=True, httponly=True, samesite='Lax', path='/')
        return response

    def _busy(self, identity, app):
        if self.inflight.get(identity, 0) or app.extensions.get('trial_futures'):
            return True
        learning = app.extensions.get('learning', {})
        lessons, live = learning.get('lessons'), learning.get('live_conversation')
        return bool((lessons and lessons._active) or (live and live.connections)
                    or (live and live.reviews and live.reviews.running))

    def _track_executors(self, app):
        pending = app.extensions['trial_futures'] = set()
        executors = app.extensions['trial_executors'] = []
        learning = app.extensions.get('learning', {})
        live = learning.get('live_conversation')
        for service in (live, live.reviews if live else None, learning.get('conversation')):
            if service is None:
                continue
            executor = service.executor
            executors.append(executor)
            submit = executor.submit
            def tracked_submit(*args, _submit=submit, **kwargs):
                with self.lock:
                    future = _submit(*args, **kwargs)
                    pending.add(future)
                def finished(completed):
                    with self.lock:
                        pending.discard(completed)
                future.add_done_callback(finished)
                return future
            executor.submit = tracked_submit

    def _admit(self, identity, request):
        """Bound cheap requests and disk growth before reaching application code."""
        now = int(self.clock())
        mutation = request.method not in ('GET', 'HEAD', 'OPTIONS') or request.path == '/sentence/generate'
        with self._db() as conn:
            conn.execute('DELETE FROM request_limits WHERE bucket<? AND kind!=?', (now // 60 - 1, 'daily-writes'))
            conn.execute("DELETE FROM request_limits WHERE kind='daily-writes' AND bucket<?", (now // 86400 - 1,))
            guest = is_guest_identity(identity)
            limits = [(identity, 'requests', now // 60, 180 if guest else 1200)]
            if mutation:
                limits += [(identity, 'writes', now // 60, 30 if guest else 180),
                           (identity, 'daily-writes', now // 86400, 300 if guest else 5000)]
            if guest:
                limits += [('guest-global', 'requests', now // 60, 1200)]
                if mutation:
                    limits += [('guest-global', 'writes', now // 60, 180),
                               ('guest-global', 'daily-writes', now // 86400, 1000)]
            for rate_identity, kind, bucket, maximum in limits:
                conn.execute('INSERT INTO request_limits VALUES (?,?,?,1) ON CONFLICT(identity,kind,bucket) DO UPDATE SET attempts=attempts+1',
                             (rate_identity, kind, bucket))
                count = conn.execute('SELECT attempts FROM request_limits WHERE identity=? AND kind=? AND bucket=?',
                                     (rate_identity, kind, bucket)).fetchone()[0]
                if count > maximum:
                    return self._json({'error': {'code': 'rate_limited', 'message': 'Please pause for a moment before trying again.'}}, 429), 0
        if not mutation:
            return None, 0
        length = request.content_length or 0
        if length > 12 * 1024 * 1024:
            return self._json({'error': {'code': 'upload_limit', 'message': 'Choose a file smaller than 12 MB.'}}, 413), 0
        # Let callers finish a call or remove data even when storage is full.
        if request.path.endswith(('/delete', '/finish')) or request.method == 'DELETE':
            return None, 0
        directory = self.root / 'tenants' / sha256(identity.encode()).hexdigest()
        occupied = sum(path.stat().st_size for path in directory.rglob('*') if path.is_file() and not path.is_symlink())
        reservation = max(length, 1024 * 1024)
        reserved = self.storage_reserved.get(identity, 0)
        limit = self._storage_limit(identity)
        if occupied + reserved + reservation > limit:
            logger.warning('Workspace storage admission denied: occupied=%d reserved=%d requested=%d limit=%d',
                           occupied, reserved, reservation, limit)
            message = ('This demo has reached its storage limit. Saved activities remain available.' if guest
                       else 'Your account has reached its storage limit. Saved activities remain available.')
            return self._json({'error': {'code': 'storage_limit', 'message': message}}, 507), 0
        free = shutil.disk_usage(self.root).free
        if free - reservation < 256 * 1024 * 1024:
            logger.warning('Server storage admission denied: free=%d requested=%d reserve=%d',
                           free, reservation, 256 * 1024 * 1024)
            response = self._json({'error': {'code': 'server_storage_low',
                'message': 'We couldn’t save this just now. Please try again shortly.'}}, 507)
            response.headers['Retry-After'] = '30'
            return response, 0
        self.storage_reserved[identity] = self.storage_reserved.get(identity, 0) + reservation
        return None, reservation

    def _application(self, identity, name):
        with self.lock:
            if identity in self.cache:
                self.cache.move_to_end(identity)
                return self.cache[identity]
            if self.ai_enabled:
                # This identity came from the verified callback or a valid
                # persisted server-side session. Provision it on first access
                # after AI activation too, without another sign-in. INSERT OR
                # IGNORE preserves existing denials and spending history.
                try:
                    self.budget.authorize_identity(identity)
                except ValueError as error:
                    raise TrialIdentityError('AI activation is temporarily unavailable.') from error
            if len(self.cache) >= self.max_cached_apps:
                idle = next(((key, value) for key, value in self.cache.items() if not self._busy(key, value)), None)
                if idle is None:
                    raise TrialIdentityError('The demo is busy. Please try again shortly.')
                key, old = idle
                self.cache.pop(key)
                for executor in old.extensions.get('trial_executors', []):
                    executor.shutdown(wait=False, cancel_futures=False)
            config = dict(self.config)
            # Security and storage boundaries always override caller defaults.
            config.update(tenant_settings(self.root, identity, secret=self.secret,
                                         ledger_path=self.ledger_path, hostname=self.hostname))
            config['HOSTED_GUEST_DEMO'] = is_guest_identity(identity)
            config['HOSTED_GUEST_DEMO_ENABLED'] = self.guest_demo_enabled
            config['HOSTED_ACCOUNTS_ENABLED'] = bool(self._provider_options())
            self.seed(config, name)
            app = self.app_factory(config)
            install_trial_session(app)
            self._track_executors(app)
            self.cache[identity] = app
            return app

    def __call__(self, environ, start_response):
        if environ.get('PATH_INFO', '').startswith('/demo/'):
            return DemoMount(self._dispatch)(environ, start_response)
        return self._dispatch(environ, start_response)

    def _dispatch(self, environ, start_response):
        request = Request(environ)
        if request.host != self.hostname:
            return self._response(Response('Unknown host', status=400))(environ, start_response)
        # Sign-in and recovery pages must render even while a learner's
        # workspace is paused. Only these packaged public files bypass it.
        if request.method in ('GET', 'HEAD') and (request.path in ACCOUNT_PUBLIC_ASSETS
                or self.guest_demo_enabled and packaged_asset(request.path)):
            return self.public_application(environ, start_response)
        try:
            demo_area = bool(environ.get('russian_arcade.demo'))
            account = None if demo_area else self._session(request)
            if self.guest_demo_enabled:
                self._cleanup_guests()
            guest = self._guest_session(request) if demo_area or request.path == '/demo' else None
            if demo_area and not self.guest_demo_enabled:
                response = self._response(Response('Not found', status=404))
            elif request.path == '/demo' or (demo_area and request.path == '/' and (not guest or 'next' in request.args)):
                response = self._demo(request, account, guest)
            elif demo_area and request.path.startswith(('/trial/sign-in', '/trial/callback', '/trial/connect', '/trial/sign-out')):
                # Provider authentication always belongs to the main site.
                response = self._response(Response('Not found', status=404))
            elif request.path == '/trial/status' and request.method == 'GET':
                response = self._json({'authenticated': bool(account), 'enabled': self.enabled,
                    'demo': bool(guest), 'demo_enabled': self.guest_demo_enabled,
                    'demo_url': '/demo/' if self.guest_demo_enabled else '',
                    'configured': any(provider.configured for provider in self.providers.values()),
                    'providers': self._provider_options(), 'ai_enabled': self.ai_enabled,
                    'display_name': account['display_name'] if account else 'Demo' if guest else None,
                    'sign_in_url': '/trial/sign-in', 'account_url': '/trial/account'})
            elif request.path == '/trial/account' and request.method == 'GET':
                if account:
                    ai_message = ('Your AI demo allowance is US$1 per day and US$2 in total. '
                                  'All visitors share US$1 per day and US$10 in total. Saved practice remains available when an allowance is used.'
                                  if self.ai_enabled else
                                  'AI generation is currently turned off. Your saved practice remains available.')
                    response = self._page('Your account',
                        'Your practice and uploads stay in this account.',
                        account=account, allowance_message=ai_message)
                elif guest:
                    response = self._page('Demo',
                        'Your demo expires after 24 hours. Sign in to open your personal account.'
                        if self._provider_options() else 'Your demo expires after 24 hours.',
                        demo_active=True, allowance_message=(
                            'Everyone shares a limited AI allowance. Sample activities remain available when it runs out.'
                            if self.ai_enabled else 'AI generation is currently turned off. Sample activities remain available.'))
                elif self._provider_options():
                    response = self._page('Sign in', '', next_url=safe_return_url(request.args.get('next')))
                else:
                    response = self._page('Public preview',
                        'You are using a temporary demo profile. Personal sign-in is not enabled on this site yet. You can try the sample activities here, or use the full app in a local installation.')
            elif request.path == '/trial/sign-in' and request.method == 'GET':
                if account:
                    response = self._response(redirect('/trial/account'))
                elif self._provider_options():
                    response = self._page('Sign in', '', next_url=safe_return_url(request.args.get('next')))
                else:
                    response = self._page('Sign-in unavailable', 'Personal sign-in is not enabled on this site yet. You can still explore the sample activities.', 503)
            elif request.path in {'/trial/sign-in/google', '/trial/sign-in/github'} and request.method == 'GET':
                response = self._begin(request, request.path.rsplit('/', 1)[1])
            elif request.path == '/trial/callback' and request.method == 'GET':
                response = self._callback(request)
            elif request.path == '/trial/callback/google' and request.method == 'GET':
                response = self._callback(request, 'google')
            elif request.path in {'/trial/connect/google', '/trial/connect/github'} and request.method == 'POST':
                if not self._valid_action(request, account, self.link_signer):
                    response = self._page('Connection expired', 'Open your account and try again.', 403)
                else:
                    response = self._begin(request, request.path.rsplit('/', 1)[1], account=account)
            elif request.path == '/trial/sign-out' and request.method == 'POST':
                if not self._valid_action(request, account, self.csrf_signer):
                    response = self._page('Sign-out expired', 'Open your account and try again.', 403)
                else:
                    with self._db() as conn:
                        conn.execute('DELETE FROM sessions WHERE token_hash=?', (account['token_hash'],))
                        conn.execute('DELETE FROM oauth_flows WHERE session_hash=?', (account['token_hash'],))
                    response = self._response(redirect('/'))
                    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='Lax', path='/')
                    response.delete_cookie(FLOW_COOKIE, secure=True, httponly=True, samesite='Lax', path='/')
            elif request.path.startswith('/trial/'):
                response = self._response(Response('Not found', status=404))
            elif demo_area and not guest:
                if request.path.startswith('/api/') or request.method not in ('GET', 'HEAD'):
                    response = self._json({'error': {'code': 'demo_expired',
                        'message': 'Open the demo to start a new session.', 'demo_url': '/demo/'}}, 401)
                else:
                    response = self._response(redirect('/demo?' + urlencode({'next': request.full_path.rstrip('?')})))
            elif account or guest:
                workspace = account or guest
                identity = workspace['identity']
                with self.lock:
                    if guest and guest['expires_at'] <= int(self.clock()):
                        return self._json({'error': {'code': 'demo_expired',
                            'message': 'Your demo has expired. Open the demo again to start fresh.',
                            'demo_url': '/demo'}}, 401)(environ, start_response)
                    if self._maintenance(identity):
                        return self._maintenance_response(request, account)(environ, start_response)
                    app = self._application(identity, workspace['display_name'])
                    rejected, reserved = self._admit(identity, request)
                    if rejected is not None:
                        return rejected(environ, start_response)
                    self.inflight[identity] = self.inflight.get(identity, 0) + 1
                def release():
                    with self.lock:
                        self.inflight[identity] -= 1
                        self.storage_reserved[identity] = self.storage_reserved.get(identity, 0) - reserved
                try:
                    result = app(environ, start_response)
                except BaseException:
                    release()
                    raise
                return ClosingIterator(result, release)
            else:
                if self.guest_demo_enabled:
                    # The main site is the personal-account entry. Anonymous
                    # visitors enter the explicit /demo/ area to try activities.
                    if request.method in ('GET', 'HEAD') and not request.path.startswith('/api/'):
                        response = self._page('Russian Arcade' if request.path == '/' else 'Sign in',
                            'Learn and practise Russian.' if request.path == '/' else '',
                            next_url=safe_return_url(request.full_path.rstrip('?')))
                    else:
                        response = self._json({'error': {'code': 'sign_in_required',
                            'message': 'Sign in or open the demo to continue.',
                            'sign_in_url': '/trial/sign-in', 'demo_url': '/demo/'}}, 401)
                    return response(environ, start_response)
                return self.public_application(environ, start_response)
        except (sqlite3.Error, OSError, TrialIdentityError):
            response = self._page('Demo temporarily unavailable', 'Please try again shortly.', 503)
        return response(environ, start_response)
