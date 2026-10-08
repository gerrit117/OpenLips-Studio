"""Actual Linux Docker smoke test with synthetic data, no accounts or media."""
import base64
import hashlib
import json
import subprocess
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
        subprocess.run(['docker', 'run', '-d', '--name', NAME, '--network', 'host',
            '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid,size=128m,mode=1777',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '-e', 'OPENLIPS_BIND=127.0.0.1', '-e', 'OPENLIPS_PORT=18765',
            '-v', VOLUME + ':/data', 'openlips-library:test'], check=True)
        wait_for_server()
        assert api('identity')['auth_required'] is False
        with opener.open(BASE, timeout=10) as response:
            assert b'OpenLips Library' in response.read()
        text = '#TITLE:Container demo\n#ARTIST:OpenLips\n#BPM:120\n#GAP:0\n: 0 4 0 Hello\n: 4 4 4 world\n- 8\nE\n'
        project = api('import', {'name': 'demo.txt', 'data': base64.b64encode(text.encode()).decode()})['id']
        for kind in ('midi', 'lrc', 'chart'):
            job(project, kind)
        subprocess.run(['docker', 'restart', NAME], check=True)
        wait_for_server()
        assert any(p['id'] == project for p in api('library')['projects'])
        assert len(api('library')['artifacts']) == 3
        print('PASS: Linux Docker startup, anonymous HTTP, TXT import, MIDI/LRC/OLS exports and persistence')
    finally:
        subprocess.run(['docker', 'logs', NAME], check=False)
        subprocess.run(['docker', 'rm', '-f', NAME], check=False)
        subprocess.run(['docker', 'volume', 'rm', VOLUME], check=False)


if __name__ == '__main__':
    main()
