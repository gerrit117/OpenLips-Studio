import sqlite3

import pytest

from tools.analyze_catalog_scaling import audit, benchmark


def test_audit_is_read_only(tmp_path):
    path = tmp_path / 'catalog.db'
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE Music (Title, Artist, AudioState, ChartState)')
    connection.execute("INSERT INTO Music VALUES ('Synthetic', 'Test', 2, 2)")
    connection.commit()
    connection.close()
    original = path.read_bytes()
    report = audit(path)
    assert report['rows'] == 1
    assert report['indexes'] == []
    assert any('SCAN' in item[3] for item in report['query_plan'])
    assert path.read_bytes() == original


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        audit(path)
    assert not path.exists()


def test_other_generation_schema_is_reported_not_rewritten(tmp_path):
    path = tmp_path / 'later.db'
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE MusicData (ID)')
    connection.close()
    assert audit(path)['status'] == 'unsupported_schema'


def test_unreadable_database_is_reported_without_repair(tmp_path):
    path = tmp_path / 'invalid.db'
    data = b'not a database'
    path.write_bytes(data)
    assert audit(path)['status'] == 'unreadable'
    assert path.read_bytes() == data


@pytest.mark.parametrize('indexed', [False, True])
def test_synthetic_benchmark_keeps_all_songs(indexed):
    report = benchmark(600, indexed, repeats=2)
    assert report['returned'] == 600
    assert report['median_ms'] >= 0
