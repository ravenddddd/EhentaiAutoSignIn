import http.client
import json

import pytest

from ehentai import web


CSRF = {web.CSRF_HEADER: web.CSRF_VALUE}


def test_token_roundtrip():
    key = web.derive_key('secret')
    token = web.issue_token(key, now=1000)
    assert web.token_valid(key, token, now=1001)
    assert not web.token_valid(key, 'garbage')
    assert not web.token_valid(key, token, now=1000 + web.SESSION_TTL + 1)
    assert not web.token_valid(web.derive_key('other'), token, now=1001)


def test_normalize_cookie():
    value = web.normalize_cookie(
        '  ipb_member_id=1;  ipb_pass_hash=abc ;event=111; sk=xyz  '
    )
    assert value == 'ipb_member_id=1; ipb_pass_hash=abc; event=111; sk=xyz'


@pytest.mark.parametrize('value', [
    '', 'not-a-cookie', 'ipb_member_id=1; ipb_pass_hash=abc',
])
def test_normalize_cookie_rejects_bad_values(value):
    with pytest.raises(web.ApiError):
        web.normalize_cookie(value)


def test_next_run_wraps_to_tomorrow():
    from datetime import datetime

    now = datetime(2026, 1, 1, 23, 0)
    assert web.next_run(['00:30', '06:30'], now=now) == '2026-01-02T00:30'
    assert web.next_run([], now=now) is None


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(web, '_failures', {})
    monkeypatch.setattr(web, '_manual_last', 0.0)
    monkeypatch.setattr(web.config, 'setting', lambda name, default='': {
        'E_COOKIE': 'ipb_member_id=1; ipb_pass_hash=abc; event=111',
        'E_PROXY': '',
        'E_SCHEDULE': '00:30',
    }.get(name, default))
    monkeypatch.setattr(web.store, 'read', lambda limit=30: [])
    monkeypatch.setattr(web.runner, 'is_running', lambda: False)
    httpd = web.serve(0, 'secret')
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def call(httpd, method, path, body=None, headers=None, cookie=None):
    connection = http.client.HTTPConnection(
        '127.0.0.1', httpd.server_address[1], timeout=5
    )
    request_headers = dict(headers or {})
    payload = None
    if body is not None:
        payload = json.dumps(body).encode('utf-8')
        request_headers['Content-Type'] = 'application/json'
    if cookie:
        request_headers['Cookie'] = cookie
    connection.request(method, path, body=payload, headers=request_headers)
    response = connection.getresponse()
    data = response.read()
    out = dict(response.getheaders())
    connection.close()
    return response.status, out, data


def login(httpd):
    status, headers, _ = call(
        httpd, 'POST', '/api/login', {'password': 'secret'}, CSRF
    )
    assert status == 200
    return headers['Set-Cookie'].split(';', 1)[0]


def test_state_is_hidden_before_login(server):
    status, headers, data = call(server, 'GET', '/api/state')
    assert status == 200
    assert json.loads(data)['authenticated'] is False
    assert headers['X-Content-Type-Options'] == 'nosniff'


def test_login_rejects_a_wrong_password(server):
    status, _, _ = call(server, 'POST', '/api/login', {'password': 'nope'}, CSRF)
    assert status == 401


def test_post_requires_the_csrf_header(server):
    status, _, _ = call(server, 'POST', '/api/login', {'password': 'secret'})
    assert status == 403


def test_state_is_visible_after_login(server):
    session = login(server)
    status, _, data = call(server, 'GET', '/api/state', cookie=session)
    payload = json.loads(data)
    assert status == 200
    assert payload['authenticated'] is True
    assert payload['configured'] is True
    assert payload['runs'] == []
    assert payload['schedule'] == ['00:30']


def test_cookie_validation_over_http(server, monkeypatch):
    saved = []
    monkeypatch.setattr(web.config, 'save_cookie', saved.append)
    session = login(server)

    status, _, _ = call(
        server, 'POST', '/api/cookie', {'cookie': 'broken'}, CSRF, session
    )
    assert status == 400
    assert saved == []

    good = 'ipb_member_id=1; ipb_pass_hash=abc; event=111'
    status, _, _ = call(server, 'POST', '/api/cookie', {'cookie': good}, CSRF, session)
    assert status == 200
    assert saved == [good]


def test_private_routes_require_a_session(server):
    status, _, _ = call(server, 'POST', '/api/run', {}, CSRF)
    assert status == 401


def test_index_is_served(server):
    status, headers, data = call(server, 'GET', '/')
    assert status == 200
    assert headers['Content-Type'].startswith('text/html')
    assert b'E-Hentai Check-in' in data
