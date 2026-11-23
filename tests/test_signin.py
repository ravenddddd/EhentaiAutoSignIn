import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from ehentai import signin


def response(html, set_cookies=()):
    headers = SimpleNamespace(getlist=lambda name: list(set_cookies))
    return SimpleNamespace(text=html, raw=SimpleNamespace(headers=headers))


@pytest.fixture
def settings(monkeypatch):
    values = {'E_COOKIE': 'ipb_member_id=1; event=111', 'E_PROXY': '', 'E_USER_AGENT': ''}
    monkeypatch.setattr(signin, 'setting', lambda name, default='': values.get(name, default))
    with patch.dict(os.environ, {}, clear=True):
        yield values


def test_cookie_update_persists(settings, monkeypatch):
    saved = []
    monkeypatch.setattr(signin, 'save_cookie', saved.append)
    monkeypatch.setattr(signin, 'request_page', lambda: response(
        '<div id="eventpane"><p>Reward</p></div>',
        ['event=new; Path=/', 'sk=abc; expires=Wed, 21 Oct 2037 07:28:00 GMT; Path=/'],
    ))
    outcome = signin.scrape()

    assert outcome['result'] == 'success'
    assert outcome['lines'] == ['Reward']
    assert saved == ['ipb_member_id=1; event=new; sk=abc']
    assert outcome['expires'] == [('sk', 'Wed, 21 Oct 2037 07:28:00 GMT')]
    assert signin.headers['Cookie'] == 'ipb_member_id=1; event=new; sk=abc'


def test_unchanged_cookie_is_not_written(settings, monkeypatch):
    saved = []
    monkeypatch.setattr(signin, 'save_cookie', saved.append)
    monkeypatch.setattr(signin, 'request_page', lambda: response(
        '<html></html>', ['event=111; Path=/'],
    ))
    signin.scrape()
    assert saved == []


@pytest.mark.parametrize(('html', 'expected'), [
    ('<html></html>', 'already'),
    ('<div id="eventpane">Random Encounter</div>', 'encounter'),
    ('<div id="eventpane"><p>Prize</p></div>', 'success'),
    ('<div id="eventpane"></div>', 'unknown'),
])
def test_scrape_results(html, expected, settings, monkeypatch):
    monkeypatch.setattr(signin, 'request_page', lambda: response(html))
    assert signin.scrape()['result'] == expected


@pytest.mark.parametrize('reward_html', [
    'You gain <strong>131</strong> EXP, <strong>397</strong> Credits!',
    'You gain<span>131</span><b>EXP</b>,<span>397</span><b>Credits</b>!',
])
def test_reward_text_keeps_spaces_around_inline_values(reward_html, settings, monkeypatch):
    html = (
        '<div id="eventpane"><p>It is the dawn of a new day!</p>'
        '<p>Reflecting on your journey so far, you find that you are a little wiser.</p>'
        f'<p>{reward_html}</p></div>'
    )
    monkeypatch.setattr(signin, 'request_page', lambda: response(html))
    outcome = signin.scrape()
    assert outcome['lines'][-1] == 'You gain 131 EXP, 397 Credits!'
    assert outcome['message'].startswith('Signed in.')


def test_request_errors_propagate(settings, monkeypatch):
    def fail():
        raise requests.ConnectionError('failed')

    monkeypatch.setattr(signin, 'request_page', fail)
    with pytest.raises(requests.ConnectionError):
        signin.scrape()


def test_missing_cookie_raises_not_configured(settings):
    settings['E_COOKIE'] = ''
    with pytest.raises(signin.NotConfigured):
        signin.scrape()
