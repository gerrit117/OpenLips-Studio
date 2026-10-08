"""Actual Linux Docker smoke test with synthetic data, no accounts or media."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

NAME = 'openlips-library-ci'
VOLUME = 'openlips-library-ci-data'
BASE = 'http://127.0.0.1:18765'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path, data=None, binary=False):
    body = None if data is None else json.dumps(data).encode()
    headers = {} if body is None else {'Content-Type': 'application/json'}
    request = urllib.request.Request(BASE + '/api/v1/' + path, data=body, headers=headers)
    with opener.open(request, timeout=10) as response:
        raw = response.read()
    return raw if binary else json.loads(raw)


def wait_for_server():
    for _ in range(60):
        try:
            value = api('status')
            assert value['auth_required'] is False and not value['encoding']
            return
        except OSError:
            time.sleep(1)
    raise AssertionError('Container did not start')


def job(project, kind):
    identifier = api('jobs', {'projects': [project], 'kind': kind})['id']
    for _ in range(90):
        value = api('jobs/' + identifier)
        if value['state'] == 'ready':
            catalog = api('library')
            artifact = next(a for a in catalog['artifacts'] if a['id'] == value['package_id'])
            raw = api('artifacts/' + artifact['id'], binary=True)
            assert hashlib.sha256(raw).hexdigest() == artifact['id']
            assert raw
            return
        assert value['state'] != 'failed', value
        time.sleep(1)
    raise AssertionError('Chart job timed out')


def main():
    subprocess.run(['docker', 'volume', 'create', VOLUME], check=True)
    try:
        subprocess.run(['docker', 'run', '-d', '--name', NAME, '-p', '127.0.0.1:18765:8765',
            '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=128m,mode=1777',
            '--security-opt', 'no-new-privileges:true',
            '-v', VOLUME + ':/library', 'openlips-library:test'], check=True)
        wait_for_server()
        subprocess.run(['docker', 'exec', NAME, 'python', '-m', 'library_server.health'], check=True)
        subprocess.run(['docker', 'exec', NAME, 'python', '-c',
            "import socket; s=socket.socket(); assert s.connect_ex(('127.0.0.1',2121)) != 0; s.close()"], check=True)
        identifier = api('identity')['server_id']
        assert api('identity')['auth_required'] is False
        with opener.open(BASE, timeout=10) as response:
            assert b'OpenLips Library' in response.read()
        text = '#TITLE:Container demo\n#ARTIST:OpenLips\n#BPM:120\n#GAP:0\n: 0 4 0 Hello\n: 4 4 4 world\n- 8\nE\n'
        project = api('import', {'name': 'demo.txt', 'data': base64.b64encode(text.encode()).decode()})['id']
        songs = api('library')['songs']
        assert len(songs) == 1 and songs[0]['project_id'] == project and songs[0]['kind'] == 'ultrastar'
        for kind in ('midi', 'lrc', 'chart'):
            job(project, kind)
        subprocess.run(['docker', 'restart', NAME], check=True)
        wait_for_server()
        assert api('identity')['server_id'] == identifier
        assert any(p['id'] == project for p in api('library')['projects'])
        assert len(api('library')['artifacts']) == 3
        print('PASS: Linux Docker startup, anonymous HTTP, TXT import, MIDI/LRC/OLS exports and persistence')
    finally:
        subprocess.run(['docker', 'logs', NAME], check=False)
        subprocess.run(['docker', 'rm', '-fv', NAME], check=False)
        subprocess.run(['docker', 'volume', 'rm', VOLUME], check=False)
    host_mount_smoke()


def host_mount_smoke():
    # Match Unraid: restrictive existing appdata and stale server.json.
    with tempfile.TemporaryDirectory(prefix='openlips-bind-ci-') as folder, \
            tempfile.TemporaryDirectory(prefix='openlips-appdata-ci-') as appdata:
        os.chmod(folder, 0o700)
        legacy = Path(appdata) / 'server.json'
        legacy.write_text('{"bind":"192.168.1.3","port":1,"tls_cert":"missing.pem"}')
        mount = str(Path(folder).resolve()) + ':/library'
        try:
            subprocess.run(['docker', 'run', '-d', '--name', NAME, '-p', '127.0.0.1:18765:8765',
                '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=128m,mode=1777',
                '--security-opt', 'no-new-privileges:true',
                '-e', 'PUID=99', '-e', 'PGID=100',
                '-v', mount, '-v', str(Path(appdata).resolve()) + ':/data', 'openlips-library:test'], check=True)
            wait_for_server()
            uid = subprocess.check_output(['docker', 'exec', NAME, 'python', '-c',
                "print(next(line.split()[1] for line in open('/proc/1/status') if line.startswith('Uid:')))"], text=True).strip()
            assert uid == '99', uid
            assert subprocess.check_output(['docker', 'exec', NAME, 'cat', '/data/server.json'], text=True).strip() == '{"bind":"192.168.1.3","port":1,"tls_cert":"missing.pem"}'
            subprocess.run(['docker', 'restart', NAME], check=True)
            wait_for_server()
            print('PASS: Bridge networking, non-root app, restrictive appdata repair and ignored stale config')
        finally:
            subprocess.run(['docker', 'logs', NAME], check=False)
            subprocess.run(['docker', 'rm', '-fv', NAME], check=False)
            # Only this generated CI directory; prepare it for TemporaryDirectory cleanup.
            subprocess.run(['docker', 'run', '--rm',
                '-v', mount, '--entrypoint', 'python', 'openlips-library:test', '-c',
                "import pathlib,shutil,os; [shutil.rmtree(p) if p.is_dir() else p.unlink() "
                "for p in pathlib.Path('/library').iterdir()]; os.chown('/library',"
                + str(os.getuid()) + ',' + str(os.getgid()) + ')'], check=True)


if __name__ == '__main__':
    main()
