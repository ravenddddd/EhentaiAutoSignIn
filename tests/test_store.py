import json

import pytest

from ehentai import config, store


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ENV_PATH', tmp_path / '.env')
    return tmp_path


def test_append_and_read_newest_first(data_dir):
    store.append({'ts': '2026-01-01T00:30:00', 'result': 'already'})
    store.append({'ts': '2026-01-02T00:30:00', 'result': 'success'})

    records = store.read()
    assert [record['result'] for record in records] == ['success', 'already']
    assert store.latest()['result'] == 'success'


def test_read_limit(data_dir):
    for index in range(5):
        store.append({'index': index})
    assert [record['index'] for record in store.read(2)] == [4, 3]


def test_empty_history(data_dir):
    assert store.read() == []
    assert store.latest() is None


def test_corrupt_lines_are_skipped(data_dir, caplog):
    path = data_dir / 'runs.jsonl'
    path.write_text(
        json.dumps({'ok': 1}) + '\nnot json\n' + json.dumps({'ok': 2}) + '\n',
        encoding='utf-8',
    )
    with caplog.at_level('WARNING'):
        records = store.read()
    assert [record['ok'] for record in records] == [2, 1]
    assert 'line 2' in caplog.text
