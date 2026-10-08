"""The simple container must work with port forwarding and stale host settings."""
from http.server import ThreadingHTTPServer
import json
import threading
from unittest.mock import patch
import urllib.error
import urllib.request

import pytest

from library_server.container_app import container_handler, local_authority, main, runtime_config
from studio.library import Library
from studio.server import JobManager


def test_old_configuration_does_not_override_container(tmp_path, monkeypatch):
    (tmp_path / 'server.json').write_text('{"bind":"192.168.1.99","tls_cert":"missing.pem"}')
    monkeypatch.setenv('OPENLIPS_BIND', '192.168.1.99')
    captured = []
    with patch('library_server.container_app.serve_http', side_effect=lambda lib, cfg: captured.append(cfg) or 0):
        assert main(['--library', str(tmp_path / 'library'), '--port', '9876']) == 0
        assert main(['--library', str(tmp_path / 'library'), '--port', '9876']) == 0
    assert captured[0]['bind'] == '0.0.0.0'
    assert captured[0]['port'] == 9876
    assert captured[0]['server_id'] == captured[1]['server_id']
    assert not captured[0]['discovery_enabled']
    assert captured[0]['ftp_port'] == 0
    assert 'tls_cert' not in captured[0]


@pytest.mark.parametrize('authority', ['192.168.1.3:9876', '127.0.0.1:8765', 'tower:8765', 'tower.local:8765'])
def test_private_forwarded_authorities(authority):
    assert local_authority(authority)


@pytest.mark.parametrize('authority', ['evil.example:8765', '8.8.8.8:8765', 'user@192.168.1.3', '127.0.0.1/path', '127.0.0.1:99999'])
def test_invalid_authorities(authority):
    assert not local_authority(authority)


def test_bridge_http_ui_and_cross_origin(tmp_path):
    library = Library(tmp_path / 'library')
    cfg = runtime_config(library, 8765)
    manager = JobManager(library, cfg)
    http = ThreadingHTTPServer(('127.0.0.1', 0), container_handler(library, cfg, manager))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f'http://127.0.0.1:{http.server_port}'
    try:
        for path in ('/', '/api/v1/status', '/api/v1/library'):
            req = urllib.request.Request(base + path, headers={'Host': '192.168.1.3:9876'})
            with opener.open(req) as response:
                assert response.status == 200
        req = urllib.request.Request(base + '/api/v1/status',
            headers={'Host': '192.168.1.3:9876', 'Origin': 'http://192.168.1.3:9876'})
        with opener.open(req) as response:
            assert json.load(response)['ftp_port'] == 0
        req = urllib.request.Request(base + '/api/v1/status',
            headers={'Host': '192.168.1.3:9876', 'Origin': 'http://unrelated.local'})
        with pytest.raises(urllib.error.HTTPError) as error:
            opener.open(req)
        assert error.value.code == 403
    finally:
        http.shutdown()
        http.server_close()
        thread.join(5)
        manager.close()
