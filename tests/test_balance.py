import requests

from ehentai import balance


GP_PAGE = (
    '<html><body>'
    '<div style="font-weight:bold">Available: 98,169 Credits</div>'
    '<div style="font-weight:bold">Available: 1.5 kGP</div>'
    '</body></html>'
)
HATH_PERKS_PAGE = '<html><body><p>You currently have 50 Hath.</p></body></html>'
HATH_PAGE = (
    '<html><body>'
    '<div>Available: 98,169 Credits</div>'
    '<div>Available: 50 Hath</div>'
    '</body></html>'
)


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []
        self.headers = {}
        self.proxies = {}
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, timeout):
        page = url.split('e-hentai.org/', 1)[1]
        if page not in self.pages:
            raise requests.ConnectionError(page)
        self.requested.append(page)
        return FakeResponse(self.pages[page])


def install_session(monkeypatch, pages):
    session = FakeSession(pages)
    monkeypatch.setattr(balance.requests, 'Session', lambda: session)
    return session


def test_parses_available_lines():
    gp, credits, hath = balance.parse_available(GP_PAGE)
    assert gp == 1500
    assert credits == 98169
    assert hath is None


def test_parses_current_hath():
    assert balance.parse_current_hath(HATH_PERKS_PAGE) == 50


def test_fetch_stops_after_two_pages(monkeypatch):
    session = install_session(monkeypatch, {
        balance.EXCHANGE_GP: GP_PAGE,
        balance.HATH_PERKS: HATH_PERKS_PAGE,
    })
    result = balance.fetch(cookie='event=1')
    assert result['gp'] == 1500
    assert result['credits'] == 98169
    assert result['hath'] == 50
    assert result['sources'] == {
        'gp': balance.EXCHANGE_GP,
        'credits': balance.EXCHANGE_GP,
        'hath': balance.HATH_PERKS,
    }
    assert session.requested == [balance.EXCHANGE_GP, balance.HATH_PERKS]
    assert result['error'] is None


def test_fetch_falls_back_to_the_hath_exchange(monkeypatch):
    session = install_session(monkeypatch, {
        balance.EXCHANGE_GP: '<div>Available: 1.5 kGP</div>',
        balance.HATH_PERKS: HATH_PERKS_PAGE,
        balance.EXCHANGE_HATH: HATH_PAGE,
    })
    result = balance.fetch(cookie='event=1')
    assert result['gp'] == 1500
    assert result['credits'] == 98169
    assert result['hath'] == 50
    assert result['sources']['credits'] == balance.EXCHANGE_HATH
    assert session.requested[-1] == balance.EXCHANGE_HATH


def test_fetch_without_a_cookie(monkeypatch):
    session = install_session(monkeypatch, {})
    result = balance.fetch(cookie='')
    assert result['error'] == 'No cookie configured.'
    assert session.requested == []


def test_fetch_reports_errors_when_every_page_fails(monkeypatch):
    session = install_session(monkeypatch, {})
    result = balance.fetch(cookie='event=1')
    assert 'exchange.php?t=gp' in result['error']
    assert len(session.requested) == 0


def test_missing_values_expose_debug_snippets(monkeypatch):
    install_session(monkeypatch, {
        balance.EXCHANGE_GP: '<div>Sign in to see your balance</div>',
        balance.HATH_PERKS: '<div>Log in</div>',
        balance.EXCHANGE_HATH: '<div>Log in</div>',
    })
    result = balance.fetch(cookie='event=1')
    assert result['gp'] is None
    assert result['credits'] is None
    assert result['hath'] is None
