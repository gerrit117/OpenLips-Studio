"""Downloader handoff is isolated from network and user-library data."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from studio.source_download import SourceDownload


@pytest.fixture
def downloader(tmp_path, monkeypatch):
    from studio import library_page
    monkeypatch.setattr(library_page, 'configured_library', lambda: str(tmp_path/'library'))
    adapter = SourceDownload()
    adapter.root = tmp_path/'temporary'
    adapter.root.mkdir()
    adapter.worker = SimpleNamespace(requestInterruption=lambda: None)
    return adapter


def message(result):
    return 'OPENLIPS_RPC:' + json.dumps({'result': result})


def test_adopt_download_keeps_media_after_temporary_folder_is_removed(downloader):
    source = downloader.root/'source.mkv'
    source.write_bytes(b'synthetic media')
    ready = []
    downloader.ready.connect(ready.append)
    downloader.receive(message(dict(type='media', path=source.name, video=True,
        reference='https://www.youtube.com/watch?v=abcdefghijk', metadata={'artist': 'Synthetic'})))
    assert len(ready) == 1
    assert Path(ready[0]['path']).read_bytes() == b'synthetic media'
    assert not Path(ready[0]['path']).is_relative_to(downloader.root)
    assert ready[0]['metadata']['artist'] == 'Synthetic'


def test_cancelled_download_cannot_adopt_a_late_result(downloader):
    ready = []
    downloader.ready.connect(ready.append)
    downloader.cancel()
    downloader.receive(message(dict(type='media', path='missing.wav')))
    assert ready == []


def test_worker_cannot_handoff_an_external_path(downloader):
    failed = []
    downloader.failed.connect(failed.append)
    downloader.receive(message(dict(type='media', path='../outside.wav')))
    assert failed and downloader.completed


def test_permission_is_required_before_starting_worker():
    adapter = SourceDownload()
    with pytest.raises(ValueError, match='permission'):
        adapter.start('abcdefghijk', rights_confirmed=False)
    assert adapter.worker is None and adapter.folder is None
