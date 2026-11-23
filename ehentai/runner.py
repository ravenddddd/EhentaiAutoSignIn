"""Run one check-in, collect the balances and persist the result."""
import logging
import threading
import time
from datetime import datetime

from . import balance, config, signin, store


_lock = threading.Lock()


def is_running():
    """True while a check-in is in progress."""
    return _lock.locked()


def _iso(timestamp):
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec='seconds')


def _fetch_balance():
    try:
        return balance.fetch(
            cookie=config.setting('E_COOKIE'),
            proxy=config.setting('E_PROXY'),
            user_agent=config.setting('E_USER_AGENT'),
        )
    except Exception as exc:
        logging.warning('Failed to read balances: %s', exc)
        return {'error': f'{type(exc).__name__}: {exc}'}


def run_once(trigger='scheduled'):
    """Run one check-in and store the record; None when a run is in progress."""
    if not _lock.acquire(blocking=False):
        logging.info('A check-in is already running; skipped the %s trigger.', trigger)
        return None

    started = time.time()
    record = {
        'ts': _iso(started),
        'trigger': trigger,
        'result': 'error',
        'message': '',
        'lines': [],
        'expires': [],
        'balance': {},
        'duration': 0,
    }
    try:
        outcome = signin.scrape()
        record.update(
            result=outcome['result'],
            message=outcome['message'],
            lines=outcome['lines'],
            expires=outcome['expires'],
        )
        logging.info(outcome['message'])
    except signin.NotConfigured as exc:
        record.update(result='unconfigured', message=str(exc))
        logging.warning('%s', exc)
    except Exception as exc:
        record.update(result='error', message=f'{type(exc).__name__}: {exc}')
        logging.error('Check-in failed: %s', record['message'])
    finally:
        try:
            if record['result'] != 'unconfigured':
                record['balance'] = _fetch_balance()
            record['duration'] = round(time.time() - started, 2)
            store.append(record)
        except Exception as exc:
            logging.error('Failed to store the run: %s', exc)
        finally:
            _lock.release()
    return record
