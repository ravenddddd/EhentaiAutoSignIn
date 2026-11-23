"""Append-only sign-in history stored as JSON Lines beside .env."""
import json
import logging
import os
import threading

from . import config


_lock = threading.Lock()


def path():
    """Return the history file path, next to .env in the data directory."""
    return config.ENV_PATH.parent / 'runs.jsonl'


def append(record):
    """Append one run record; each line is a complete JSON object."""
    with _lock:
        target = path()
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with open(target, 'a', encoding='utf-8', newline='\n') as output:
            output.write(line + '\n')
            output.flush()
            os.fsync(output.fileno())


def read(limit=30):
    """Return the newest `limit` records, newest first."""
    target = path()
    if not target.exists():
        return []
    records = []
    with _lock:
        with open(target, encoding='utf-8') as source:
            for number, line in enumerate(source, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logging.warning('runs.jsonl line %s is not valid JSON; skipped.', number)
    return list(reversed(records[-limit:]))


def latest():
    """Return the most recent record, or None."""
    records = read(1)
    return records[0] if records else None
