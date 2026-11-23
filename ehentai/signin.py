"""Visit the E-Hentai news page, handle the check-in result and the Cookie."""
import http.cookies
import logging
import os
import re
import time

import requests
from bs4 import BeautifulSoup

from .config import save_cookie, setting


URL = 'https://e-hentai.org/news.php'
headers = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,'
        'image/avif,image/webp,image/apng,*/*;q=0.8,'
        'application/signed-exchange;v=b3;q=0.7'
    ),
    'Upgrade-Insecure-Requests': '1',
    'Cookie': '',
}
proxies = {}
COOKIE_FIELDS = ('ipb_member_id', 'ipb_pass_hash', 'sk', 'hath_perks', 'nw', 'event')


class NotConfigured(ValueError):
    """Raised when no E-Hentai cookie has been configured yet."""


def mask_cookie(cookie):
    """Hide cookie values in logs and on the Web page."""
    result = []

    for item in cookie.split(';'):
        item = item.strip()

        if '=' not in item:
            result.append(item)
            continue

        key, value = item.split('=', 1)

        if len(value) > 8:
            value = value[:3] + '*' * (len(value) - 6) + value[-3:]
        elif value:
            value = value[0] + '*' * (len(value) - 1)

        result.append(f'{key}={value}')

    return '; '.join(result)


def init_config():
    """Reload the request settings before every run."""
    proxy = setting('E_PROXY')
    cookie = setting('E_COOKIE')
    user_agent = setting('E_USER_AGENT')

    if not cookie:
        raise NotConfigured('No cookie configured. Set E_COOKIE in .env or through the Web UI.')
    proxies.clear()
    if proxy:
        proxies.update(http=proxy, https=proxy)
        logging.info('Proxy configured.')
    headers['Cookie'] = cookie
    logging.info('Using cookie: %s', mask_cookie(cookie))
    if user_agent:
        headers['User-Agent'] = user_agent
    os.environ['E_COOKIE'] = cookie


def parse_set_cookie(raw_headers):
    """Extract cookie values and expiry dates from the response headers."""
    cookies = {}
    expires = []

    for raw in raw_headers:
        parsed = http.cookies.SimpleCookie()
        parsed.load(raw)

        for key, value in parsed.items():
            cookies[key] = value.value

            if value['expires']:
                expires.append((key, value['expires']))

    return cookies, expires


def update_cookie(new_cookies, expires):
    """Merge the supported Cookie fields and persist them when they change."""
    old_cookie = os.getenv('E_COOKIE', '')
    current = {}

    for item in old_cookie.split(';'):
        if '=' in item:
            key, value = item.strip().split('=', 1)
            current[key] = value

    updated = False

    for field in COOKIE_FIELDS:
        if field in new_cookies and current.get(field) != new_cookies[field]:
            current[field] = new_cookies[field]
            updated = True

    if not updated:
        logging.info('Local cookie is up to date.')
        return

    new_cookie = '; '.join(f'{k}={v}' for k, v in current.items())
    save_cookie(new_cookie)
    os.environ['E_COOKIE'] = new_cookie
    headers['Cookie'] = new_cookie

    logging.info('Updated E_COOKIE in .env: %s', mask_cookie(new_cookie))


def do_request(session=None):
    client = session or requests

    response = client.get(
        URL,
        headers=headers,
        proxies=proxies,
        timeout=(10, 30)
    )

    response.raise_for_status()
    return response


def request_page():
    """Request the page with the default TLS settings, retrying up to twice."""
    last_error = None
    for attempt in range(1, 4):
        logging.info('Fetching page, attempt %s/3', attempt)
        try:
            return do_request()
        except requests.exceptions.RequestException as exc:
            last_error = exc
        if attempt < 3:
            time.sleep(2)
    raise last_error


def scrape():
    """Perform one check-in and return the parsed outcome."""
    init_config()

    response = request_page()

    set_cookies = response.raw.headers.getlist('Set-Cookie')
    expires = []
    if set_cookies:
        new_cookies, expires = parse_set_cookie(set_cookies)
        update_cookie(new_cookies, expires)
    else:
        logging.info('No Set-Cookie header; the current cookie is still valid.')

    # news.php's eventpane holds the reward or a Random Encounter.
    soup = BeautifulSoup(response.text, 'html.parser')
    event_pane = soup.find('div', id='eventpane')

    if not event_pane:
        return {
            'result': 'already',
            'message': 'Already signed in for today.',
            'lines': [],
            'expires': expires,
        }

    event_text = event_pane.get_text(
        separator=' ',
        strip=True
    ).lower()

    if 'encounter' in event_text:
        return {
            'result': 'encounter',
            'message': 'Random Encounter. Handle it manually or wait for the event to end.',
            'lines': [],
            'expires': expires,
        }

    # Inline tags may split text and numbers; no extra space before punctuation.
    lines = [
        re.sub(r'\s+([,.;:!?])', r'\1', p.get_text(' ', strip=True))
        for p in event_pane.find_all('p')
    ]

    if lines:
        return {
            'result': 'success',
            'message': 'Signed in.\n' + '\n'.join(lines),
            'lines': lines,
            'expires': expires,
        }

    return {
        'result': 'unknown',
        'message': 'Unrecognized check-in response.',
        'lines': [],
        'expires': expires,
    }
