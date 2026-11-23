"""Read the account balances from E-Hentai's exchange and perk pages.

The 2025 front site no longer shows a wallet bar, so the balances are spread
over subpages: the GP exchange lists Credits and the GP balance (as kGP), the
Hath exchange lists Credits and Hath, and the Hath Perks page states the Hath
balance. Only pages that are still missing a value are requested.
"""
import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup


BASE_URL = 'https://e-hentai.org/'
EXCHANGE_GP = 'exchange.php?t=gp'
EXCHANGE_HATH = 'exchange.php?t=hath'
HATH_PERKS = 'hathperks.php'

DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
)

# "Available: 98,169 Credits" / "Available: 1.5 kGP" / "Available: 50 Hath"
AVAILABLE_RE = re.compile(
    r'Available:\s*([\d,]+(?:\.\d+)?)\s*(kGP|GP|Credits|Hath)\b', re.IGNORECASE
)
# "You currently have 50 Hath."
CURRENT_HAVE_RE = re.compile(
    r'currently have\s*([\d,]+(?:\.\d+)?)\s*Hath\b', re.IGNORECASE
)


def _number(raw):
    value = float(raw.replace(',', ''))
    return int(value) if value.is_integer() else value


def _text(html):
    return BeautifulSoup(html, 'html.parser').get_text(separator=' ', strip=True)


def parse_available(html):
    """Return (gp, credits, hath) from the generic "Available:" lines."""
    gp = credits = hath = None
    for raw, unit in AVAILABLE_RE.findall(_text(html)):
        unit = unit.lower()
        if unit == 'credits' and credits is None:
            credits = _number(raw)
        elif unit == 'kgp' and gp is None:
            gp = _number(raw) * 1000
        elif unit == 'gp' and gp is None:
            gp = _number(raw)
        elif unit == 'hath' and hath is None:
            hath = _number(raw)
    return gp, credits, hath


def parse_current_hath(html):
    """Return the Hath balance from "You currently have N Hath."."""
    match = CURRENT_HAVE_RE.search(_text(html))
    return _number(match.group(1)) if match else None


def _snippets(html, limit=6):
    """Keep short text fragments that may explain a missing value."""
    found = []
    for sentence in re.split(r'(?<=[.!?])\s+|\s{2,}', _text(html)):
        if re.search(r'Available:|currently have|GP\b|Credits\b|Hath\b', sentence, re.IGNORECASE):
            found.append(sentence.strip()[:200])
        if len(found) >= limit:
            break
    return found


def _fetch_page(session, page, timeout):
    response = session.get(BASE_URL + page, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch(cookie='', proxy='', user_agent='', timeout=(10, 30)):
    """Fetch the balances; never raises, and reports failures in the result."""
    result = {
        'gp': None, 'credits': None, 'hath': None,
        'sources': {}, 'debug': [], 'error': None,
        'fetched_at': datetime.now().astimezone().isoformat(timespec='seconds'),
    }
    if not cookie:
        result['error'] = 'No cookie configured.'
        return result

    proxies = {'http': proxy, 'https': proxy} if proxy else {}
    headers = {
        'User-Agent': user_agent or DEFAULT_USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Cookie': cookie,
    }
    errors = []
    with requests.Session() as session:
        session.headers.update(headers)
        session.trust_env = False
        session.proxies.update(proxies)

        def load(page):
            try:
                return _fetch_page(session, page, timeout)
            except requests.exceptions.RequestException as exc:
                errors.append(f'{page}: {exc}')
                logging.warning('Balance page %s failed: %s', page, exc)
                return None

        html = load(EXCHANGE_GP)
        if html is not None:
            gp, credits, _ = parse_available(html)
            if gp is not None:
                result['gp'], result['sources']['gp'] = gp, EXCHANGE_GP
            if credits is not None:
                result['credits'], result['sources']['credits'] = credits, EXCHANGE_GP
            if gp is None or credits is None:
                result['debug'].extend(_snippets(html))

        html = load(HATH_PERKS)
        if html is not None:
            hath = parse_current_hath(html)
            if hath is not None:
                result['hath'], result['sources']['hath'] = hath, HATH_PERKS

        if result['credits'] is None or result['hath'] is None:
            html = load(EXCHANGE_HATH)
            if html is not None:
                _, credits, hath = parse_available(html)
                if result['credits'] is None and credits is not None:
                    result['credits'], result['sources']['credits'] = credits, EXCHANGE_HATH
                if result['hath'] is None and hath is not None:
                    result['hath'], result['sources']['hath'] = hath, EXCHANGE_HATH

    all_missing = result['gp'] is None and result['credits'] is None and result['hath'] is None
    if errors and all_missing:
        result['error'] = '; '.join(errors)
    elif all_missing:
        result['error'] = 'Could not read a balance from the account pages; the cookie may have expired.'
    return result
