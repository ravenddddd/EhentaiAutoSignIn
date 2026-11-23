"""Serve a small single-user Web UI for the check-in history and the cookie."""
import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import __version__, config, runner, signin, store


STATIC_DIR = Path(__file__).resolve().parent / 'static'
STATIC_FILES = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
}
SECURITY_HEADERS = {
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ),
}
SESSION_COOKIE = 'ehentai_session'
SESSION_TTL = 30 * 86400
MAX_BODY = 64 * 1024
CSRF_HEADER = 'X-Requested-With'
CSRF_VALUE = 'ehentai-signin'
REQUIRED_COOKIE_FIELDS = ('ipb_member_id', 'ipb_pass_hash', 'event')
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT = 60
MANUAL_COOLDOWN = 30

_failures = {}
_manual_last = 0.0
_state_lock = threading.Lock()


class ApiError(Exception):
    """An error that maps directly onto an HTTP response."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def derive_key(password):
    return hashlib.sha256(b'ehentai-signin-session:' + password.encode('utf-8')).digest()


def issue_token(key, now=None):
    issued = int(now if now is not None else time.time())
    signature = hmac.new(key, str(issued).encode('ascii'), hashlib.sha256).hexdigest()
    return f'{issued}.{signature}'


def token_valid(key, token, now=None):
    if not token or '.' not in token:
        return False
    issued, _, signature = token.partition('.')
    if not issued.isdigit():
        return False
    expected = hmac.new(key, issued.encode('ascii'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    return int(issued) + SESSION_TTL > int(now if now is not None else time.time())


def normalize_cookie(raw):
    """Validate a pasted Cookie header and return it in a canonical form."""
    if not isinstance(raw, str):
        raise ApiError(400, 'The cookie must be a string.')
    value = raw.strip()
    if not value:
        raise ApiError(400, 'The cookie is empty.')
    if len(value) > 8192:
        raise ApiError(400, 'The cookie is too long.')
    fields = {}
    for item in value.split(';'):
        item = item.strip()
        if not item:
            continue
        if '=' not in item:
            raise ApiError(400, f'Malformed cookie segment: {item[:20]}')
        name, _, field_value = item.partition('=')
        fields[name.strip()] = field_value.strip()
    missing = [name for name in REQUIRED_COOKIE_FIELDS if not fields.get(name)]
    if missing:
        raise ApiError(400, 'The cookie is missing required fields: ' + ', '.join(missing))
    return '; '.join(f'{name}={field_value}' for name, field_value in fields.items())


def next_run(times, now=None):
    """Return the next scheduled local time as an ISO string."""
    if not times:
        return None
    current = now if now is not None else datetime.now()
    for value in times:
        hour, minute = (int(part) for part in value.split(':'))
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > current:
            return candidate.isoformat(timespec='minutes')
    hour, minute = (int(part) for part in times[0].split(':'))
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return (candidate + timedelta(days=1)).isoformat(timespec='minutes')


def state_payload():
    """Everything the page needs, without any secret value."""
    runs = store.read(30)
    latest = runs[0] if runs else None
    cookie = config.setting('E_COOKIE')
    try:
        schedule = list(config.scheduled_times())
        schedule_error = None
    except ValueError as exc:
        schedule, schedule_error = [], str(exc)
    return {
        'version': __version__,
        'configured': bool(cookie),
        'cookie': {
            'masked': signin.mask_cookie(cookie) if cookie else '',
            'expires': (latest or {}).get('expires', []),
        },
        'balance': (latest or {}).get('balance', {}),
        'balance_at': (latest or {}).get('ts'),
        'runs': runs,
        'running': runner.is_running(),
        'schedule': schedule,
        'schedule_error': schedule_error,
        'next_run': next_run(schedule),
        'proxy_configured': bool(config.setting('E_PROXY')),
        'server_time': datetime.now().astimezone().isoformat(timespec='seconds'),
    }


def make_handler(password):
    key = derive_key(password)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'ehentai-signin'
        sys_version = ''
        protocol_version = 'HTTP/1.1'

        # -- plumbing ---------------------------------------------------
        def log_message(self, fmt, *args):
            logging.debug('web %s - %s', self.address_string(), fmt % args)

        def _headers(self):
            return SECURITY_HEADERS

        def _send(self, status, body, content_type='application/json; charset=utf-8', extra=None):
            data = body if isinstance(body, bytes) else body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            for name, value in self._headers().items():
                self.send_header(name, value)
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)

        def _json(self, status, payload, extra=None):
            self._send(status, json.dumps(payload, ensure_ascii=False), extra=extra)

        def _error(self, status, message):
            self._json(status, {'error': message})

        def _session(self):
            jar = {}
            for part in self.headers.get('Cookie', '').split(';'):
                if '=' in part:
                    name, _, value = part.strip().partition('=')
                    jar[name] = value
            return jar.get(SESSION_COOKIE)

        def _authenticated(self):
            return token_valid(key, self._session())

        def _check_csrf(self):
            if self.headers.get(CSRF_HEADER) != CSRF_VALUE:
                raise ApiError(403, 'Missing or invalid request header.')

        def _read_json(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if length <= 0:
                return {}
            if length > MAX_BODY:
                raise ApiError(413, 'Request body too large.')
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ApiError(400, 'Request body is not valid JSON.') from None
            if not isinstance(data, dict):
                raise ApiError(400, 'Request body must be a JSON object.')
            return data

        def _require_auth(self):
            if not self._authenticated():
                raise ApiError(401, 'Sign in first.')

        # -- routes -----------------------------------------------------
        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path in STATIC_FILES:
                    name, content_type = STATIC_FILES[path]
                    self._send(200, (STATIC_DIR / name).read_bytes(), content_type)
                elif path == '/api/state':
                    if not self._authenticated():
                        self._json(200, {'authenticated': False, 'version': __version__})
                    else:
                        payload = state_payload()
                        payload['authenticated'] = True
                        self._json(200, payload)
                else:
                    self._error(404, 'Not found.')
            except Exception as exc:  # never leak a traceback to the browser
                logging.exception('Web request failed: %s', exc)
                self._error(500, 'Internal error.')

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                self._check_csrf()
                body = self._read_json()
                if path == '/api/login':
                    self._login(body)
                elif path == '/api/logout':
                    self._json(200, {'ok': True}, extra={
                        'Set-Cookie': f'{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'
                    })
                elif path == '/api/cookie':
                    self._require_auth()
                    self._save_cookie(body)
                elif path == '/api/run':
                    self._require_auth()
                    self._run()
                else:
                    self._error(404, 'Not found.')
            except ApiError as exc:
                self._error(exc.status, exc.message)
            except Exception as exc:
                logging.exception('Web request failed: %s', exc)
                self._error(500, 'Internal error.')

        # -- handlers ---------------------------------------------------
        def _login(self, body):
            address = self.client_address[0]
            with _state_lock:
                count, until = _failures.get(address, (0, 0))
                if until > time.time():
                    raise ApiError(429, 'Too many attempts. Wait a minute and try again.')
            if not hmac.compare_digest(str(body.get('password', '')).encode('utf-8'),
                                       password.encode('utf-8')):
                with _state_lock:
                    count += 1
                    until = time.time() + LOGIN_LOCKOUT if count >= LOGIN_MAX_FAILURES else 0
                    _failures[address] = (count, until)
                logging.warning('Failed Web login from %s', address)
                raise ApiError(401, 'Wrong password.')
            with _state_lock:
                _failures.pop(address, None)
            cookie = (
                f'{SESSION_COOKIE}={issue_token(key)}; Path=/; Max-Age={SESSION_TTL}; '
                'HttpOnly; SameSite=Strict'
            )
            self._json(200, {'ok': True}, extra={'Set-Cookie': cookie})

        def _save_cookie(self, body):
            value = normalize_cookie(body.get('cookie', ''))
            config.save_cookie(value)
            self._json(200, {'ok': True, 'cookie': signin.mask_cookie(value)})

        def _run(self):
            global _manual_last
            with _state_lock:
                now = time.time()
                if _manual_last and now - _manual_last < MANUAL_COOLDOWN:
                    raise ApiError(429, 'A manual check-in just ran. Wait a moment.')
                _manual_last = now
            if runner.is_running():
                raise ApiError(409, 'A check-in is already running.')
            thread = threading.Thread(
                target=runner.run_once, args=('manual',), name='manual-run', daemon=True
            )
            thread.start()
            self._json(202, {'started': True})

    return Handler


def serve(port, password, host='0.0.0.0'):
    """Start the Web server on a daemon thread and return the server object."""
    server = ThreadingHTTPServer((host, port), make_handler(password))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name='web', daemon=True).start()
    return server
