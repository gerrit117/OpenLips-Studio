import json
from http.server import ThreadingHTTPServer
import threading
import zipfile

import pytest
from PIL import Image

from studio.library import Library
from studio.library_bundle import import_bundle, write_bundle
from studio.library_client import LibraryClient
from studio.library_sync import sync_library
from studio.model import StudioProject, EditorNote, load_project, save_project
from studio.server import JobManager, handler_for
from studio.server_config import create_config


def song(title='Local'):
    return StudioProject(title=title, artist='OpenLips', video_reference='abcdefghijk',
        notes=[EditorNote(1, 1, 60, 'Hello')])


def test_atomic_bundle_preserves_reference_and_has_no_partial_projects(tmp_path):
    library = Library(tmp_path / 'library')
    project = song()
    cover = tmp_path / 'cover.png'
    Image.new('RGB', (32, 32), 'teal').save(cover)
    audio = tmp_path / 'audio.mp3'
    audio.write_bytes(b'ID3' + b'synthetic' * 100)
    project.cover_path, project.audio_path = str(cover), str(audio)
    bundle = tmp_path / 'song.zip'
    write_bundle(project, bundle)
    identifier = import_bundle(library, bundle)
    assert len(library.projects()) == 1
    copy = load_project(library.project_path(identifier))
    assert copy.video_reference == 'abcdefghijk'
    assert open(copy.audio_path, 'rb').read() == audio.read_bytes()
    assert library.add_project(project) == identifier
    assert import_bundle(library, bundle) == identifier


def test_bundle_rejects_paths_and_executable_media(tmp_path):
    library = Library(tmp_path / 'library')
    for name, content in [('../cover.png', b'x'), ('audio.mp3', b'MZ executable')]:
        bundle = tmp_path / 'bad.zip'
        with zipfile.ZipFile(bundle, 'w') as archive:
            archive.writestr('project.json', json.dumps(song().to_payload()))
            archive.writestr(name, content)
        with pytest.raises(ValueError):
            import_bundle(library, bundle)
    assert library.projects() == []


def test_real_bidirectional_sync_is_idempotent_and_recovers_new_versions(tmp_path):
    local, remote = Library(tmp_path / 'local'), Library(tmp_path / 'remote')
    save_project(song(), local.draft_path(song()))
    remote.add_project(song('Remote'))
    config = create_config(tmp_path / 'config.json', remote.root, lan_open=True)
    manager = JobManager(remote, config)
    http = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(remote, config, manager))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    client = LibraryClient(f'http://127.0.0.1:{http.server_address[1]}')
    try:
        result = sync_library(local, client)
        assert not result['errors'], result
        assert result['uploaded'] == result['downloaded'] == 1
        assert len(local.projects()) == len(remote.projects()) == 2
        result = sync_library(local, client)
        assert result['uploaded'] == result['downloaded'] == 0 and not result['errors']
        assert len(local.projects()) == len(remote.projects()) == 2
        revised = song()
        revised.notes[0].pitch = 62
        local.add_project(revised)
        result = sync_library(local, client)
        assert result['uploaded'] == 1 and not result['errors']
        assert len(remote.projects()) == 3
        # Removing an entry remotely never removes the local version.
        identifier = next(r['id'] for r in remote.projects() if r['title'] == 'Remote')
        remote.remove_project(identifier)
        result = sync_library(local, client)
        assert not result['errors']
        assert len(local.projects()) == len(remote.projects()) == 3
    finally:
        http.shutdown()
        http.server_close()
        thread.join(5)
        manager.close()
