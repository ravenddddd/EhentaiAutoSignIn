from unittest.mock import Mock

import pytest

import main
from ehentai import config


def test_once_returns_zero_on_success(monkeypatch):
    monkeypatch.setattr('sys.argv', ['main.py', '--once'])
    monkeypatch.setattr(main, 'configure_file_logging', Mock())
    monkeypatch.setattr(main.runner, 'run_once', lambda trigger: {'result': 'success'})
    assert main.main() == 0


@pytest.mark.parametrize('result', ['error', 'unconfigured'])
def test_once_returns_one_on_failure(result, monkeypatch):
    monkeypatch.setattr('sys.argv', ['main.py', '--once'])
    monkeypatch.setattr(main, 'configure_file_logging', Mock())
    monkeypatch.setattr(main.runner, 'run_once', lambda trigger: {'result': result})
    assert main.main() == 1


def test_service_requires_a_web_password(monkeypatch):
    monkeypatch.setattr('sys.argv', ['main.py'])
    monkeypatch.setattr(main, 'configure_file_logging', Mock())
    monkeypatch.setattr(main, 'scheduled_times', lambda: ('00:30',))
    monkeypatch.setattr(config, 'setting', lambda name, default='': default)
    assert main.main() == 1


class FakeScheduler:
    def __init__(self):
        self.jobs = []
        self.next_run = None
        self._at = None

    def every(self):
        return self

    @property
    def day(self):
        return self

    def at(self, value):
        self._at = value
        return self

    def do(self, func, *args):
        self.jobs.append((self._at, func, args))
        return self

    def run_pending(self):
        raise KeyboardInterrupt


class ImmediateThread:
    def __init__(self, target=None, args=(), name=None, daemon=None):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


def test_service_starts_the_web_ui_and_scheduler(monkeypatch):
    server = Mock()
    scheduler = FakeScheduler()
    started = []
    monkeypatch.setattr('sys.argv', ['main.py'])
    monkeypatch.setattr(main, 'configure_file_logging', Mock())
    monkeypatch.setattr(main, 'scheduled_times', lambda: ('00:30', '12:30'))
    monkeypatch.setattr(
        config, 'setting',
        lambda name, default='': 'secret' if name == 'WEB_PASSWORD' else default,
    )
    monkeypatch.setattr(config, 'web_port', lambda: 18391)
    monkeypatch.setattr(main.web, 'serve', lambda port, password: server)
    monkeypatch.setattr(main.schedule, 'Scheduler', lambda: scheduler)
    monkeypatch.setattr(main.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(main.runner, 'run_once', lambda trigger: started.append(trigger))

    assert main.main() == 0
    assert started == ['startup']
    assert server.shutdown.called
    assert [job[0] for job in scheduler.jobs] == ['00:30', '12:30']
