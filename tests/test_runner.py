from unittest.mock import Mock

import pytest

from ehentai import runner, signin


@pytest.fixture
def recorded(monkeypatch):
    records = []
    monkeypatch.setattr(runner.store, 'append', records.append)
    monkeypatch.setattr(runner, '_fetch_balance', lambda: {
        'gp': 1, 'credits': 2, 'hath': 3, 'sources': {}, 'error': None,
    })
    return records


def success():
    return {'result': 'success', 'message': 'Signed in.', 'lines': ['x'], 'expires': []}


def test_records_a_successful_run(recorded, monkeypatch):
    monkeypatch.setattr(runner.signin, 'scrape', success)
    record = runner.run_once('manual')
    assert record['result'] == 'success'
    assert record['trigger'] == 'manual'
    assert record['balance']['gp'] == 1
    assert record['duration'] >= 0
    assert recorded == [record]


def test_records_an_error_and_still_reads_balances(recorded, monkeypatch):
    def fail():
        raise RuntimeError('boom')

    monkeypatch.setattr(runner.signin, 'scrape', fail)
    record = runner.run_once('scheduled')
    assert record['result'] == 'error'
    assert record['message'] == 'RuntimeError: boom'
    assert record['balance']['gp'] == 1


def test_unconfigured_skips_the_balance(recorded, monkeypatch):
    def missing():
        raise signin.NotConfigured('No cookie')

    monkeypatch.setattr(runner.signin, 'scrape', missing)
    fetch = Mock()
    monkeypatch.setattr(runner, '_fetch_balance', fetch)
    record = runner.run_once('cli')
    assert record['result'] == 'unconfigured'
    fetch.assert_not_called()
    assert recorded == [record]


def test_a_store_failure_still_releases_the_lock(monkeypatch):
    monkeypatch.setattr(runner.store, 'append', Mock(side_effect=RuntimeError('disk')))
    monkeypatch.setattr(runner.signin, 'scrape', success)
    monkeypatch.setattr(runner, '_fetch_balance', lambda: {})
    assert runner.run_once('manual')['result'] == 'success'
    assert not runner._lock.locked()


def test_a_second_run_is_skipped_while_locked(recorded, monkeypatch):
    runner._lock.acquire()
    try:
        assert runner.run_once('manual') is None
    finally:
        runner._lock.release()
    assert recorded == []
