"""Synthetic HTTPS, pairing, portable import and inactive-backend integration."""
import base64
import io
import json
import socket
import ssl
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from studio.library import Library
from studio.library_client import LibraryClient, save_profiles, load_profiles
from studio.library_exchange import import_input, portable_project, FutureMediaBackend, FutureConsoleTransport
from studio.library_security import DeviceAuth
from studio.model import StudioProject, EditorNote, load_project
from studio.server import JobManager, handler_for, make_ftp
from studio.server_config import create_config
from tools.song_bundle import decode_bundle


TXT = b'#TITLE:Synthetic song\n#ARTIST:OpenLips\n#BPM:120\n#GAP:0\n: 0 4 0 Hello\n: 8 4 2 world\nE\n'


def test_portable_imports_drop_server_paths_and_lrc_has_no_invented_pitch(tmp_path):
    library = Library(tmp_path / 'library')
    p = StudioProject(title='Portable', artist='Author', audio_path='/etc/passwd',
                      cover_path='C:/Windows/secret', notes=[EditorNote(1,1,60,'Hello')])
    identifier = import_input(library, 'song.olp', json.dumps(p.to_payload()).encode())
    data = portable_project(library, identifier)
    assert not data['project']['audio_path'] and not data['project']['cover_path']
    assert data['media'] == {}
    identifier = import_input(library, 'song.lrc', b'[ti:Timed]\n[ar:OpenLips]\n[00:01.00]Hello\n[00:03.00]world\n')
    project = load_project(library.project_path(identifier))
    assert project.title == 'Timed'
    assert all(not note.pitch_assigned for note in project.notes)
    for name in ('../song.txt', 'song.exe', 'song.opl'):
        with pytest.raises(ValueError):
            import_input(library, name, TXT)


def test_pairing_is_one_time_revocable_and_credentials_are_not_broadcast(tmp_path):
    library = Library(tmp_path / 'library')
    config = create_config(tmp_path / 'server.json', library.root)
    auth = DeviceAuth(library, config)
    code = auth.begin_pairing()['code']
    result = auth.pair(code, 'Test PC')
    assert auth.valid(result['api_token'])
    with pytest.raises(ValueError):
        auth.pair(code, 'Other PC')
    with library.connect() as db:
        row = db.execute('SELECT * FROM devices').fetchone()
    assert result['api_token'] not in dict(row).values()
    assert result['ftp']['password'] not in row['ftp_secret']
    assert not any('secret' in key or 'token' in key for key in auth.devices()[0])
    auth.revoke(result['device_id'])
    assert not auth.valid(result['api_token'])
    code = auth.begin_pairing()['code']
    for _ in range(5):
        with pytest.raises(ValueError):
            auth.pair('invalid', 'Test')
    with pytest.raises(ValueError):
        auth.pair(code, 'Test')


def test_connection_profiles_roundtrip(tmp_path):
    path = tmp_path / 'connections.bin'
    profiles = [dict(url='https://127.0.0.1:8765', api_token='private-test-token', ftp={'password':'private-ftp'})]
    save_profiles(path, profiles)
    assert load_profiles(path) == profiles
    import os
    if os.name == 'nt':
        assert b'private-test-token' not in path.read_bytes()
    assert not LibraryClient('http://192.168.1.10:8765').tls
    with pytest.raises(ValueError):
        LibraryClient('http://8.8.8.8:8765')


def test_https_api_pairing_import_chart_job_and_revoke(tmp_path):
    library = Library(tmp_path / 'library')
    config = create_config(tmp_path / 'server.json', library.root, tls=True)
    config['ftp_port'] = 0
    config['encoding_enabled'] = False
    ftp = make_ftp(library, config)
    auth = DeviceAuth(library, config, ftp.handler.authorizer)
    manager = JobManager(library, config)
    http = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(library, config, manager, auth))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(config['tls_cert'], config['tls_key'])
    http.socket = context.wrap_socket(http.socket, server_side=True, do_handshake_on_connect=False)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    url = f'https://127.0.0.1:{http.server_address[1]}'
    owner = LibraryClient(url, config['api_token'], config['certificate_fingerprint'])
    try:
        status = owner.request('GET', '/api/v1/status')
        assert status['chart_conversion'] and not status['encoding']
        assert not status['portable_transcode'] and not status['native_xbox_transport']
        with pytest.raises(ValueError, match='certificate'):
            LibraryClient(url, config['api_token'], '0'*64).request('GET', '/api/v1/library')
        code = owner.request('POST', '/api/v1/pairing', {})['code']
        client = LibraryClient(url, fingerprint=config['certificate_fingerprint'])
        result = client.request('POST', '/api/v1/pair', {'code':code,'name':'Studio test'})
        client.token = result['api_token']
        assert ftp.handler.authorizer.has_user(result['ftp']['username'])
        imported = client.request('POST', '/api/v1/import', {'name':'song.txt','data':base64.b64encode(TXT).decode()})['id']
        assert portable_project(library, imported)['project']['title'] == 'Synthetic song'
        cover=tmp_path/'cover.png'
        Image.new('RGB',(64,64),'#38618c').save(cover)
        imported=client.upload_media(imported,'cover',cover)['id']
        portable=client.request('GET','/api/v1/projects/'+imported)
        assert portable['media']['cover']['bytes']==cover.stat().st_size
        assert str(tmp_path) not in json.dumps(portable)
        lyrics=base64.b64encode(b'[00:00.00]Hello\n[00:01.00]world\n').decode()
        imported=client.request('POST','/api/v1/projects/'+imported+'/lyrics',{'data':lyrics})['id']
        assert load_project(library.project_path(imported)).lyric_reference['format']=='lrc'
        invalid=tmp_path/'not-media.mp3';invalid.write_bytes(b'MZ this is not audio')
        with pytest.raises(ValueError,match='recognized'):
            client.upload_media(imported,'audio',invalid)
        with pytest.raises(ValueError, match='501'):
            client.request('POST', '/api/v1/transcode', {})
        with pytest.raises(ValueError, match='403'):
            client.request('DELETE', '/api/v1/projects/' + imported)
        job = client.request('POST', '/api/v1/jobs', {'projects':[imported], 'kind':'chart'})['id']
        deadline = time.monotonic()+45
        while time.monotonic()<deadline:
            state = client.request('GET', '/api/v1/jobs/' + job)
            if state['state'] in ('ready','failed'):
                break
            time.sleep(.1)
        assert state['state']=='ready', dict(state)
        artifact = library.artifact_path(state['package_id'])
        assert decode_bundle(artifact.read_bytes()).manifest['metadata']['title'] == 'Synthetic song'
        copy = tmp_path / 'downloaded.ols'
        client.request('GET', '/api/v1/artifacts/'+state['package_id'], target=copy,
                       expected_hash=state['package_id'], expected_bytes=artifact.stat().st_size)
        assert copy.read_bytes()==artifact.read_bytes()
        with patch.object(client, 'connect', side_effect=AssertionError('Cache must not redownload')):
            assert client.request('GET', '/api/v1/artifacts/'+state['package_id'], target=copy,
                expected_hash=state['package_id'], expected_bytes=artifact.stat().st_size)==copy
        owner.request('DELETE', '/api/v1/devices/'+result['device_id'])
        with pytest.raises(ValueError, match='401'):
            client.request('GET', '/api/v1/library')
        assert not ftp.handler.authorizer.has_user(result['ftp']['username'])
    finally:
        http.shutdown(); http.server_close(); thread.join(3)
        manager.close(); ftp.close_all()


def test_media_header_and_disabled_backends(tmp_path):
    from studio.library_exchange import validate_media_header
    path = tmp_path / 'renamed.mp3'
    path.write_bytes(b'MZ executable')
    with pytest.raises(ValueError):
        validate_media_header(path, 'audio')
    assert not FutureMediaBackend.enabled and not FutureConsoleTransport.enabled
    with pytest.raises(NotImplementedError):
        FutureMediaBackend().transcode('id','profile')
    with pytest.raises(NotImplementedError):
        FutureConsoleTransport().transfer('id','console')


def test_discovery_advertises_no_credentials(tmp_path):
    from studio.library_discovery import announcement, stop_announcement
    config = create_config(tmp_path/'server.json', tmp_path/'library', bind='192.168.1.10', tls=True, discovery=True)
    with patch('zeroconf.Zeroconf') as implementation:
        advertised = announcement(config)
        info = implementation.return_value.register_service.call_args.args[0]
        text = repr(info.properties)
        assert config['api_token'] not in text and config['ftp_password'] not in text
        assert str(tmp_path) not in text
        assert info.properties[b'protocol'] == b'1'
        assert info.properties[b'fingerprint'].decode() == config['certificate_fingerprint']
        stop_announcement(advertised)
        implementation.return_value.close.assert_called_once()
