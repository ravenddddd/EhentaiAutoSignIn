import os
from unittest.mock import patch

import pytest

from ehentai import config


def test_setting_prefers_the_env_file(monkeypatch, tmp_path):
    path = tmp_path / '.env'
    path.write_text("E_PROXY='http://from-file'\n", encoding='utf-8')
    real = config.read_env
    monkeypatch.setattr(config, 'read_env', lambda **kwargs: real(path, **kwargs))
    with patch.dict(os.environ, {'E_PROXY': 'http://from-env'}, clear=True):
        assert config.setting('E_PROXY') == 'http://from-file'


def test_setting_falls_back_to_the_environment(monkeypatch, tmp_path):
    path = tmp_path / '.env'
    path.write_text('', encoding='utf-8')
    real = config.read_env
    monkeypatch.setattr(config, 'read_env', lambda **kwargs: real(path, **kwargs))
    with patch.dict(os.environ, {'E_USER_AGENT': 'agent/1'}, clear=True):
        assert config.setting('E_USER_AGENT') == 'agent/1'
        assert config.setting('E_PROXY', 'fallback') == 'fallback'


def test_web_port_default(monkeypatch):
    monkeypatch.setattr(config, 'read_env', lambda **kwargs: {})
    with patch.dict(os.environ, {}, clear=True):
        assert config.web_port() == 18391


@pytest.mark.parametrize('value', ['0', '65536', 'abc', '80.5', '-1'])
def test_web_port_validation(value, monkeypatch):
    monkeypatch.setattr(config, 'read_env', lambda **kwargs: {'WEB_PORT': value})
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match='WEB_PORT'):
            config.web_port()


@pytest.mark.parametrize(('env_value', 'file_values', 'expected'), [
    (None, {}, ('00:30', '06:30', '12:30', '18:30')),
    ('01:15', {'E_SCHEDULE': ' 08:00, 20:30 '}, ('08:00', '20:30')),
    ('01:15', {'E_SCHEDULE': ''}, ('00:30', '06:30', '12:30', '18:30')),
    ('01:15', {}, ('01:15',)),
    (None, {'E_SCHEDULE': '00:30,6:30,12:30,18:30'}, ('00:30', '06:30', '12:30', '18:30')),
    (None, {'E_SCHEDULE': '00:30,6:30,11:11,12:30,18:30'}, ('00:30', '06:30', '11:11', '12:30', '18:30')),
    (None, {'E_SCHEDULE': '6:30,06:30,12:30,6:30'}, ('06:30', '12:30')),
])
def test_schedule_parsing(env_value, file_values, expected, monkeypatch):
    monkeypatch.setattr(config, 'read_env', lambda **kwargs: file_values)
    env = {} if env_value is None else {'E_SCHEDULE': env_value}
    with patch.dict(os.environ, env, clear=True):
        assert config.scheduled_times() == expected


@pytest.mark.parametrize('value', ['24:00', '12:60', '08:00,', '12:30,6:30', '6:30,12:30,11:11'])
def test_invalid_times_are_rejected(value, monkeypatch):
    monkeypatch.setattr(config, 'read_env', lambda **kwargs: {'E_SCHEDULE': value})
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match='E_SCHEDULE'):
            config.scheduled_times()


def test_save_cookie_keeps_comments_and_other_settings(tmp_path):
    path = tmp_path / '.env'
    path.write_text(
        '# keep comment\n'
        "E_COOKIE='ipb_member_id=123; event=old; other=value'\n"
        "E_SCHEDULE='00:30'\n",
        encoding='utf-8',
    )
    config.save_cookie('ipb_member_id=123; event=new; other=value; sk=abc', path)

    text = path.read_text(encoding='utf-8')
    assert '# keep comment' in text
    assert "E_SCHEDULE='00:30'" in text
    assert '"ipb_member_id=123; event=new; other=value; sk=abc"' in text


def test_save_cookie_appends_when_missing(tmp_path):
    path = tmp_path / '.env'
    path.write_text("E_SCHEDULE='00:30'", encoding='utf-8')
    config.save_cookie('event=111', path)
    assert config.read_env(path)['E_COOKIE'] == 'event=111'
    assert config.read_env(path)['E_SCHEDULE'] == '00:30'


@pytest.mark.parametrize('content', [
    "E_COOKIE='unterminated\n",
    'NOT A VALID LINE\n',
])
def test_read_env_reports_the_line(content, tmp_path):
    path = tmp_path / '.env'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError, match='line'):
        config.read_env(path)
