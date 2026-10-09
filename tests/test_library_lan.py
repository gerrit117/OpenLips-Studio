"""Open home-network mode has no TLS, pairing or credentials."""
import ftplib
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading

import pytest

from studio.library import Library
from studio.library_client import LibraryClient
from studio.server import JobManager, handler_for, make_ftp
from studio.server_config import create_config, load_config, update_features


def test_lan_configuration_has_no_secrets_and_anonymous_ftp(tmp_path):
    library = Library(tmp_path/'library')
    cfg = create_config(tmp_path/'server.json',library.root,lan_open=True,tls=True)
    assert cfg['api_token']==cfg['ftp_password']==''
    assert 'tls_cert' not in cfg and 'secrets_dpapi' not in cfg and 'secrets' not in cfg
    cfg['ftp_port']=0
    ftp=make_ftp(library,cfg)
    thread=threading.Thread(target=lambda:ftp.serve_forever(timeout=.05,handle_exit=False),daemon=True)
    thread.start()
    try:
        with ftplib.FTP() as client:
            client.connect('127.0.0.1',ftp.socket.getsockname()[1],timeout=5)
            client.login()
            assert client.nlst()==[]
            with pytest.raises(ftplib.error_perm):
                client.mkd('not-allowed')
    finally:
        ftp.close_all();thread.join(5)


def test_anonymous_api_import_jobs_and_private_address_limits(tmp_path):
    library=Library(tmp_path/'library')
    cfg=create_config(tmp_path/'server.json',library.root,lan_open=True)
    manager=JobManager(library,cfg)
    http=ThreadingHTTPServer(('127.0.0.1',0),handler_for(library,cfg,manager))
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    client=LibraryClient(f'http://127.0.0.1:{http.server_address[1]}')
    try:
        assert client.request('GET','/api/v1/identity')['auth_required'] is False
        assert client.request('GET','/api/v1/status')['auth_required'] is False
        assert client.request('GET','/api/v1/library')['projects']==[]
        with pytest.raises(ValueError):
            client.request('POST','/api/v1/jobs',{'projects':['../../file']})
        with pytest.raises(ValueError):
            LibraryClient('http://8.8.8.8:8765')
    finally:
        http.shutdown();http.server_close();thread.join(5);manager.close()


def test_switch_to_lan_preserves_local_certificate_files(tmp_path):
    cfg=create_config(tmp_path/'server.json',tmp_path/'library',tls=True)
    cert=Path(cfg['tls_cert']);old=cert.read_bytes()
    update_features(tmp_path/'server.json',tls=False,discovery=True,name='Home library',lan_open=True)
    cfg=load_config(tmp_path/'server.json')
    assert cfg['lan_open'] and cfg['api_token']=='' and 'tls_cert' not in cfg
    assert cert.read_bytes()==old


def test_web_server_defaults_to_open_lan_and_migrates_old_config(tmp_path, monkeypatch):
    from library_server import app
    captured = []
    monkeypatch.setattr(app, 'serve', lambda library, config, handler: captured.append(config))
    path = tmp_path / 'server.json'
    arguments = ['--config', str(path), '--library', str(tmp_path / 'library'),
                 '--bind', '192.168.1.100']
    app.main(arguments)
    assert captured[-1]['lan_open'] and captured[-1]['discovery_enabled']
    assert captured[-1]['api_token'] == '' and 'tls_cert' not in captured[-1]
    legacy = tmp_path / 'legacy.json'
    create_config(legacy, tmp_path / 'legacy-library', bind='192.168.1.101', tls=True)
    # Existing configuration's bind, not the CLI's localhost default, controls discovery.
    app.main(['--config', str(legacy)])
    assert captured[-1]['lan_open'] and captured[-1]['discovery_enabled']
    assert captured[-1]['bind'] == '192.168.1.101'


def test_studio_auto_connects_one_open_library_without_pairing(tmp_path, monkeypatch):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from studio.remote_library import RemoteLibraryPage
    monkeypatch.setattr('studio.remote_library.load_profiles', lambda _: [])
    application = QApplication.instance() or QApplication([])
    page = RemoteLibraryPage(lambda: None)
    calls = []
    monkeypatch.setattr(page, 'prepare_pair', lambda: calls.append(page.url.text()))
    record = dict(server_id='1' * 32, name='Home library', host='192.168.1.100',
                  port=8765, tls=False, auth_required=False)
    try:
        page.discovered([record])
        QTest.qWait(200)
        assert calls == ['http://192.168.1.100:8765']
        paired = []
        monkeypatch.setattr(page, 'paired', lambda client, result: paired.append(result))
        page.open_lan(LibraryClient(calls[0]), dict(server_id=record['server_id'],
                                                  name=record['name'], auth_required=False))
        credentials = paired[0][1]
        assert credentials['api_token'] == ''
        assert credentials['ftp'] == dict(username='anonymous', password='')
    finally:
        page.close()
        application.processEvents()
