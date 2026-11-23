"""Read local configuration, persist the Cookie and parse the schedule."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile


DEFAULT_SCHEDULE = ('00:30', '06:30', '12:30', '18:30')
DEFAULT_WEB_PORT = '18391'


def application_dir():
    """Prefer the data directory, then the source or executable directory."""
    data_dir = os.getenv('EHENTAI_DATA_DIR', '').strip()
    if data_dir:
        return Path(data_dir).expanduser().resolve()
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ENV_PATH = application_dir() / '.env'


def read_env(path=ENV_PATH, *, keys=None):
    """Read .env; with keys, only parse the requested settings for early logging."""
    values = {}
    if not path.exists():
        return values
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, separator, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if keys is not None and key not in keys:
            continue
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            raise ValueError(f'.env line {number} is malformed')
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f'.env line {number} has an invalid quoted value') from exc
            if not isinstance(value, str):
                raise ValueError(f'.env line {number} must be a string')
        elif value.startswith("'"):
            if not value.endswith("'") or len(value) < 2:
                raise ValueError(f'.env line {number} has an unterminated quoted value')
            value = value[1:-1]
        values[key] = value
    return values


def setting(name, default=''):
    """Return one setting; the .env value wins over the process environment."""
    values = {name: os.getenv(name, '')}
    values.update(read_env(keys={name}))
    return values[name].strip() or default


def web_port():
    """Return the Web UI port, defaulting to a quiet, uncommon port."""
    value = setting('WEB_PORT', DEFAULT_WEB_PORT)
    if not re.fullmatch(r'[0-9]{1,5}', value) or not 0 < int(value) < 65536:
        raise ValueError('WEB_PORT must be an integer between 1 and 65535.')
    return int(value)


def save_cookie(cookie, path=ENV_PATH):
    """Atomically replace E_COOKIE in .env, keeping comments and other settings."""
    lines = path.read_text(encoding='utf-8-sig').splitlines(keepends=True) if path.exists() else []
    replacement = 'E_COOKIE=' + json.dumps(cookie, ensure_ascii=False) + '\n'
    found = False
    for index, line in enumerate(lines):
        if re.match(r'^\s*(?:export\s+)?E_COOKIE\s*=', line):
            lines[index] = replacement
            found = True
    if not found:
        if lines and not lines[-1].endswith(('\n', '\r')):
            lines[-1] += '\n'
        lines.append(replacement)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.writelines(lines)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def scheduled_times():
    """Read the daily local run times, defaulting to four runs per day."""
    value = setting('E_SCHEDULE')
    if not value.strip():
        return DEFAULT_SCHEDULE

    times = []
    seen = set()
    for item in value.split(','):
        item = item.strip()
        if not re.fullmatch(r'(?:[0-9]|[01][0-9]|2[0-3]):[0-5][0-9]', item):
            raise ValueError('E_SCHEDULE must be comma-separated 24-hour times, e.g. 00:30,6:30.')
        hour, minute = item.split(':')
        normalized = f'{int(hour):02d}:{minute}'
        if normalized in seen:
            continue
        if times and normalized < times[-1]:
            raise ValueError('E_SCHEDULE times must be in ascending order.')
        seen.add(normalized)
        times.append(normalized)
    return tuple(times)
