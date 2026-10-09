"""Synthetic library, read-only FTP, authenticated API and job regressions."""
import ftplib
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

from studio.library import Library
from studio.model import EditorNote, StudioProject, load_project
from studio.server import JobManager, handler_for, make_ftp, server_lock
from studio.server_config import create_config, load_config, local_bind, update_connection
from studio.xbox_transfer import copy_to_xbox, private_address
from tools.build_dlc import build_package, make_manifest, sha256, verify_stfs, xbox_path


def project(tmp_path):
    audio = tmp_path / 'voice.wav'
    audio.write_bytes(b'synthetic source, never executed')
    return StudioProject(title='Test song', artist='Test artist', audio_path=str(audio),
        notes=[EditorNote(1, .5, 60, 'Hello')])


def config(tmp_path):
    return dict(bind='127.0.0.1', port=8765, ftp_port=0, ftp_user='openlips',
                ftp_password='a' * 32, api_token='b' * 32, passive_ports=[50000, 50009])


def test_opt_in_library_preserves_media_and_versions(tmp_path):
    library = Library(tmp_path / 'library')
    p = project(tmp_path)
    original = Path(p.audio_path).read_bytes()
    identifier = library.add_project(p)
    duplicate = load_project(library.project_path(identifier))
    duplicate.notes[0].id = 'another-editor-uuid'
    assert library.add_project(duplicate) == identifier
    archived = load_project(library.project_path(identifier))
    assert Path(archived.audio_path).read_bytes() == original
    assert Path(p.audio_path).read_bytes() == original
    p.notes[0].pitch += 1
    assert library.add_project(p) != identifier
    assert len(library.projects()) == 2
    with pytest.raises(KeyError):
        library.project_path('../../secrets')
    assert not list((library.root / 'publish').iterdir())


def test_credentials_roundtrip_and_no_overwrite(tmp_path):
    path = tmp_path / 'server.json'
    generated = create_config(path, tmp_path / 'library')
    assert load_config(path)['api_token'] == generated['api_token']
    update_connection(path, '192.168.1.20', 8766, 2122)
    assert load_config(path)['api_token'] == generated['api_token']
    assert load_config(path)['bind'] == '192.168.1.20'
    with pytest.raises(ValueError):
        create_config(tmp_path / 'invalid.json', tmp_path / 'library', port=50000)
    assert not (tmp_path / 'invalid.json').exists()
    if os.name == 'nt':
        assert generated['api_token'] not in path.read_text()
        assert generated['ftp_password'] not in path.read_text()
    with pytest.raises(FileExistsError):
        create_config(path, tmp_path / 'other')
    for address in ('0.0.0.0', '8.8.8.8', '::', '169.254.1.1'):
        with pytest.raises(ValueError):
            local_bind(address)
    assert local_bind('192.168.1.20') == '192.168.1.20'
    with pytest.raises(OSError):
        with server_lock(tmp_path):
            with server_lock(tmp_path):
                pass


def test_ftp_target_must_be_local():
    assert private_address('127.0.0.1') == '127.0.0.1'
    with pytest.raises(ValueError):
        private_address('8.8.8.8')


def test_api_auth_no_paths_or_arbitrary_jobs(tmp_path):
    library = Library(tmp_path / 'library')
    identifier = library.add_project(project(tmp_path))
    settings = config(tmp_path)
    class Manager:
        def enqueue(self, request):
            return 'test-job'
    http = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(library, settings, Manager()))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f'http://127.0.0.1:{http.server_address[1]}'
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            opener.open(base + '/api/v1/library')
        assert error.value.code == 401
        request = urllib.request.Request(base + '/api/v1/library',
            headers={'Authorization': 'Bearer ' + settings['api_token']})
        with opener.open(request) as response:
            data = response.read()
        assert identifier.encode() in data
        assert str(tmp_path).encode() not in data
        for header in ({'Origin': 'http://evil.example'}, {'Host': 'evil.example'}):
            request = urllib.request.Request(base + '/api/v1/library',
                headers={'Authorization': 'Bearer ' + settings['api_token'], **header})
            with pytest.raises(urllib.error.HTTPError) as error:
                opener.open(request)
            assert error.value.code == 403
        request = urllib.request.Request(base + '/api/v1/jobs', data=b'x' * 8193,
            headers={'Authorization': 'Bearer ' + settings['api_token'], 'Content-Type': 'application/json'})
        with pytest.raises(urllib.error.HTTPError) as error:
            opener.open(request)
        assert error.value.code == 400
    finally:
        http.shutdown()
        http.server_close()
        thread.join(3)


def test_job_validation_queue_limit_and_platform(tmp_path):
    library = Library(tmp_path / 'library')
    identifier = library.add_project(project(tmp_path))
    with patch.object(JobManager, 'run'):
        manager = JobManager(library)
        try:
            for request in ({'projects': ['../../secret']}, {'projects': [identifier], 'command': 'run'},
                            {'projects': [identifier, identifier]}, {'projects': [identifier], 'pack_name': 'wrong'}):
                with pytest.raises(ValueError):
                    manager.enqueue(request)
            with patch('studio.server.sys.platform', 'linux'), pytest.raises(ValueError, match='Windows'):
                manager.enqueue({'projects': [identifier]})
            with patch('studio.server.sys.platform', 'win32'):
                for _ in range(8):
                    manager.enqueue({'projects': [identifier]})
                with pytest.raises(ValueError, match='full'):
                    manager.enqueue({'projects': [identifier]})
        finally:
            manager.close()


@pytest.fixture
def native_package(tmp_path):
    from studio.dlc_media import bundled_tool
    backend = bundled_tool('openlips_stfs')
    if not backend:
        pytest.skip('Native STFS backend unavailable')
    names = dict(chart='test.X360', lyric='test_Lyric.X360', audio='test.xWMA',
                 jacket='test.jpg', preview_audio='preview.xWMA')
    files = {}
    for name in names.values():
        files[name] = tmp_path / name
        files[name].write_bytes(b'not real media; metadata-only fixture')
    output = tmp_path / 'source.LIVE'
    build_package(backend, files, make_manifest('Synthetic', 'OpenLips', 0x73000001, 20, names), output, 'Synthetic pack')
    return output


def test_native_metadata_library_and_cache(tmp_path, native_package):
    from studio.package_metadata import package_metadata
    metadata = package_metadata(native_package)
    assert metadata['title'] == 'Synthetic pack'
    assert metadata['songs'][0]['title'] == 'Synthetic'
    library = Library(tmp_path / 'library')
    identifier = library.add_project(project(tmp_path))
    package_id = library.add_package(native_package, [identifier])
    ready = [song for song in library.songs() if song['kind'] == 'dlc']
    assert len(ready) == 1 and ready[0]['title'] == 'Synthetic'
    assert ready[0]['artist'] == 'OpenLips' and ready[0]['package_id'] == package_id
    assert library.cached_package([identifier]) == package_id
    assert library.cached_package([identifier], 'wrong title') is None
    assert library.add_package(native_package, [identifier]) == package_id
    assert len(library.packages()) == 1
    assert sha256(library.package_path(package_id)) == sha256(native_package)
    assert not list((library.root / '.staging').iterdir())
    assert not (library.root / 'publish' / 'library.sqlite3').exists()
    assert library.cached_build([identifier], None, True) is None
    library.record_build(package_id, [identifier], None, True)
    assert library.cached_build([identifier], None, True) == package_id
    assert library.cached_build([identifier], None, False) is None


def test_real_ftp_push_hash_verify_and_read_only_pull(tmp_path, native_package):
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    from pyftpdlib.ioloop import IOLoop
    console = tmp_path / 'console'
    console.mkdir()
    authorizer = DummyAuthorizer()
    authorizer.add_user('xbox', 'secret', str(console), perm='elradfmw')
    class Handler(FTPHandler):
        pass
    Handler.authorizer = authorizer
    ftp = FTPServer(('127.0.0.1', 0), Handler, ioloop=IOLoop())
    thread = threading.Thread(target=lambda: ftp.serve_forever(timeout=.1, handle_exit=False), daemon=True)
    thread.start()
    values = dict(host='127.0.0.1', port=ftp.address[1], username='xbox', password='secret')
    events = []
    try:
        path = copy_to_xbox(native_package, values, lambda *event: events.append(event))
        installed = console / path
        assert installed.read_bytes() == native_package.read_bytes()
        assert {event[0] for event in events} == {'upload', 'verify'}
        assert not list(console.rglob('*.tmp'))
        with pytest.raises(FileExistsError):
            copy_to_xbox(native_package, values)
        assert installed.read_bytes() == native_package.read_bytes()
    finally:
        ftp.close_all()
        thread.join(3)
    library = Library(tmp_path / 'library')
    package_id = library.add_package(native_package)
    settings = config(tmp_path)
    ftp = make_ftp(library, settings)
    thread = threading.Thread(target=lambda: ftp.serve_forever(timeout=.1, handle_exit=False), daemon=True)
    thread.start()
    try:
        with ftplib.FTP() as client:
            client.connect('127.0.0.1', ftp.address[1], timeout=5)
            client.login(settings['ftp_user'], settings['ftp_password'])
            filenames = client.nlst()
            assert filenames == [library.package_path(package_id).name]
            chunks = []
            client.retrbinary('RETR ' + filenames[0], chunks.append)
            assert hashlib.sha256(b''.join(chunks)).hexdigest() == package_id
            for command in ('DELE ' + filenames[0], 'MKD malicious', 'CWD ..', 'RETR ../library.sqlite3'):
                if command == 'CWD ..':
                    client.sendcmd(command)
                    assert client.pwd() == '/'
                else:
                    with pytest.raises(ftplib.error_perm):
                        client.sendcmd(command)
    finally:
        ftp.close_all()
        thread.join(3)


def test_transfer_cancellation_never_publishes(tmp_path, native_package):
    from tests.test_build_dlc import FakeFTP
    from tools.build_dlc import upload_package
    ftp = FakeFTP()
    with pytest.raises(InterruptedError):
        upload_package(ftp, native_package, xbox_path(native_package), cancelled=lambda: True)
    assert not ftp.files


def test_finished_dlc_upload_sync_download_and_copy(tmp_path, native_package):
    from studio.library_sync import sync_library, copy_packages
    from studio.library_client import LibraryClient
    local, remote = Library(tmp_path / 'local'), Library(tmp_path / 'remote')
    identifier = local.add_package(native_package)
    settings = create_config(tmp_path / 'sync.json', remote.root, lan_open=True)
    manager = JobManager(remote, settings)
    http = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(remote, settings, manager))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    client = LibraryClient(f'http://127.0.0.1:{http.server_address[1]}')
    try:
        result = sync_library(local, client)
        assert not result['errors'] and result['uploaded'] == 1
        assert remote.package_path(identifier).read_bytes() == native_package.read_bytes()
        result = sync_library(local, client)
        assert result['uploaded'] == result['downloaded'] == 0
        second = Library(tmp_path / 'second')
        result = sync_library(second, client)
        assert not result['errors'] and result['downloaded'] == 1
        assert second.package_path(identifier).read_bytes() == native_package.read_bytes()
        outputs = copy_packages(second, [identifier], tmp_path / 'copies')
        assert outputs[0].read_bytes() == native_package.read_bytes()
        assert copy_packages(second, [identifier], tmp_path / 'copies') == outputs
        outputs[0].write_bytes(b'User file')
        with pytest.raises(FileExistsError):
            copy_packages(second, [identifier], tmp_path / 'copies')
        assert outputs[0].read_bytes() == b'User file'
    finally:
        http.shutdown()
        http.server_close()
        thread.join(5)
        manager.close()


def test_export_archives_only_when_enabled(tmp_path, native_package, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from studio.dlc_dialog import PackageWorker
    app = QApplication.instance() or QApplication([])
    root = tmp_path / 'library'
    monkeypatch.setattr('studio.library_page.configured_library', lambda: root)
    monkeypatch.setattr('studio.dlc_pack.build_projects_dlc', lambda *args, **kwargs: {'output_path': str(native_package)})
    worker = PackageWorker(project(tmp_path), str(tmp_path), None)
    errors, completed = [], []
    worker.archive_warning.connect(errors.append)
    worker.completed.connect(completed.append)
    worker.run()
    assert not errors
    assert completed == [str(native_package)]
    library = Library(root)
    assert len(library.projects()) == 1
    assert len(library.packages()) == 1
    disabled_root = tmp_path / 'disabled'
    monkeypatch.setattr('studio.library_page.configured_library', lambda: None)
    worker = PackageWorker(project(tmp_path), str(tmp_path), None)
    worker.run()
    assert not disabled_root.exists()


@pytest.mark.skipif(os.environ.get('OPENLIPS_TEST_NATIVE_DLC') != '1', reason='Explicit native encoder integration test')
def test_headless_build_subprocess_and_cached_reuse(tmp_path):
    from studio.media import ffmpeg_encoder
    import subprocess
    source = tmp_path / 'synthetic.mp4'
    subprocess.run([ffmpeg_encoder(), '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
        'testsrc2=size=320x180:rate=24:duration=17', '-f', 'lavfi', '-i',
        'sine=frequency=440:sample_rate=48000:duration=17', '-c:v', 'libx264',
        '-c:a', 'aac', str(source)], stdin=subprocess.DEVNULL, check=True, capture_output=True, timeout=60)
    original = sha256(source)
    library = Library(tmp_path / 'library')
    identifier = library.add_project(StudioProject(title='Headless test', artist='OpenLips',
        video_path=str(source), notes=[EditorNote(1, .5, 60, 'Hello'), EditorNote(2, 1, 64, 'world')]))
    manager = JobManager(library)
    try:
        job = manager.enqueue({'projects': [identifier]})
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            with library.connect() as db:
                row = db.execute('SELECT * FROM jobs WHERE id=?', (job,)).fetchone()
            if row['state'] in ('ready', 'failed'):
                break
            time.sleep(.1)
        assert row['state'] == 'ready', (dict(row), (library.root / ('worker-' + job + '.log')).read_text(errors='replace'))
        package_id = row['package_id']
        assert verify_stfs(library.package_path(package_id))['sha256'] == package_id
        assert sha256(source) == original
        next_job = manager.enqueue({'projects': [identifier]})
        with library.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (next_job,)).fetchone()
        assert row['state'] == 'ready'
        assert row['package_id'] == package_id
        assert len(library.packages()) == 1
    finally:
        manager.close()
