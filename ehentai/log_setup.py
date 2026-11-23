"""Configure console logging and optional local rotating logs."""
from datetime import datetime, time as datetime_time, timedelta
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import time

from .config import ENV_PATH, read_env

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'


class RetainedRotatingFileHandler(RotatingFileHandler):
    """Rotate by size and date, and delete this program's expired backups."""

    def __init__(self, filename, max_bytes, retention_days):
        super().__init__(filename, maxBytes=max_bytes, backupCount=30, encoding='utf-8')
        self.retention_seconds = retention_days * 86400
        self.next_rollover = self.next_midnight()
        if (os.path.exists(self.baseFilename) and
                datetime.fromtimestamp(os.path.getmtime(self.baseFilename)).date() < datetime.now().date()):
            self.next_rollover = 0
        self.next_cleanup = 0
        self.cleanup_expired()

    @staticmethod
    def next_midnight():
        tomorrow = datetime.now().date() + timedelta(days=1)
        return datetime.combine(tomorrow, datetime_time.min).timestamp()

    def cleanup_expired(self):
        """Delete only this program's expired rotated files."""
        cutoff = time.time() - self.retention_seconds
        base = Path(self.baseFilename)
        for index in range(1, self.backupCount + 1):
            backup = base.with_name(f'{base.name}.{index}')
            try:
                if not backup.is_symlink() and backup.is_file() and backup.stat().st_mtime < cutoff:
                    backup.unlink()
            except FileNotFoundError:
                pass
        self.next_cleanup = time.time() + 3600

    def shouldRollover(self, record):
        # Rotate on the first write after midnight; otherwise use file size.
        if time.time() >= self.next_rollover and os.path.exists(self.baseFilename):
            if os.path.getsize(self.baseFilename) > 0:
                return True
        return super().shouldRollover(record)

    def doRollover(self):
        super().doRollover()
        self.next_rollover = self.next_midnight()
        self.cleanup_expired()

    def emit(self, record):
        if time.time() >= self.next_cleanup:
            try:
                self.cleanup_expired()
            except OSError:
                self.handleError(record)
        super().emit(record)


def configure_file_logging():
    """Enable file logging from .env; by default only the console is used."""
    keys = ('LOG_ENABLED', 'LOG_DIR', 'LOG_MAX_MB', 'LOG_RETENTION_DAYS')
    values = {key: os.getenv(key, '') for key in keys}
    errors = []
    # Parse only the logging keys so a bad setting elsewhere still gets logged.
    for key in keys:
        try:
            values.update(read_env(keys={key}))
        except ValueError as exc:
            errors.append(exc)
            values[key] = ''
    enabled = values['LOG_ENABLED'].strip().lower()
    if enabled in ('', 'false', '0', 'no', 'off'):
        if errors:
            raise errors[0]
        return
    if enabled not in ('true', '1', 'yes', 'on'):
        raise ValueError('LOG_ENABLED must be true or false.')

    def positive_integer(key, default):
        value = values[key].strip() or str(default)
        if not re.fullmatch(r'[0-9]+', value) or int(value) <= 0:
            errors.append(ValueError(f'{key} must be a positive integer.'))
            return default
        return int(value)

    max_mb = positive_integer('LOG_MAX_MB', 5)
    retention_days = positive_integer('LOG_RETENTION_DAYS', 30)
    default_directory = ENV_PATH.parent / 'logs'
    try:
        directory = Path(values['LOG_DIR'].strip() or 'logs').expanduser()
        if not directory.is_absolute():
            directory = ENV_PATH.parent / directory
        directory.mkdir(parents=True, exist_ok=True)
        handler = RetainedRotatingFileHandler(directory / 'ehentai.log', max_mb * 1024 * 1024, retention_days)
    except (OSError, ValueError) as exc:
        # When the configured directory is unusable, log to the default one.
        errors.append(exc)
        directory = default_directory
        directory.mkdir(parents=True, exist_ok=True)
        handler = RetainedRotatingFileHandler(directory / 'ehentai.log', max_mb * 1024 * 1024, retention_days)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(handler)
    logging.info('File logging enabled: %s', directory / 'ehentai.log')
    if errors:
        raise errors[0]
