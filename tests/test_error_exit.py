import logging

import pytest

import main
from ehentai import config, log_setup


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    env_path = tmp_path / '.env'
    real = config.read_env
    monkeypatch.setattr(config, 'read_env', lambda **kwargs: real(env_path, **kwargs))
    monkeypatch.setattr(log_setup, 'read_env', lambda **kwargs: real(env_path, **kwargs))
    monkeypatch.setattr(log_setup, 'ENV_PATH', env_path)
    for key in (
        'E_COOKIE', 'E_SCHEDULE', 'E_PROXY', 'LOG_ENABLED', 'LOG_DIR',
        'LOG_MAX_MB', 'LOG_RETENTION_DAYS', 'WEB_PASSWORD', 'WEB_PORT',
    ):
        monkeypatch.delenv(key, raising=False)
    root = logging.getLogger()
    before = set(root.handlers)
    yield env_path
    for handler in set(root.handlers) - before:
        root.removeHandler(handler)
        handler.close()


def log_text(env_path):
    return (env_path.parent / 'logs' / 'ehentai.log').read_text(encoding='utf-8')


@pytest.mark.parametrize(('content', 'message'), [
    ("LOG_ENABLED='true'\nE_SCHEDULE='12:30,6:30'\n", 'E_SCHEDULE'),
    ("LOG_ENABLED='true'\nE_SCHEDULE='00:30'\n", 'WEB_PASSWORD'),
    ("LOG_ENABLED='true'\nLOG_MAX_MB='0'\nE_SCHEDULE='00:30'\n", 'LOG_MAX_MB'),
])
def test_startup_error_is_logged_without_a_traceback(isolated_config, monkeypatch, caplog, content, message):
    isolated_config.write_text(content, encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['main.py'])
    with caplog.at_level(logging.INFO):
        assert main.main() == 1
    text = log_text(isolated_config)
    assert message in text
    assert 'Traceback' not in text
    assert 'Traceback' not in caplog.text


def test_invalid_command_line_is_logged(isolated_config, monkeypatch, caplog):
    isolated_config.write_text("LOG_ENABLED='true'\n", encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['main.py', '--invalid'])
    with caplog.at_level(logging.INFO):
        assert main.main() == 1
    text = log_text(isolated_config)
    assert '--invalid' in text
    assert 'Traceback' not in text


def test_unavailable_log_directory_falls_back(isolated_config, monkeypatch, caplog):
    blocked = isolated_config.parent / 'not-a-directory'
    blocked.write_text('file', encoding='utf-8')
    isolated_config.write_text(
        "LOG_ENABLED='true'\nLOG_DIR='not-a-directory'\n", encoding='utf-8'
    )
    monkeypatch.setattr('sys.argv', ['main.py'])
    with caplog.at_level(logging.INFO):
        assert main.main() == 1
    assert 'Startup failed' in log_text(isolated_config)
