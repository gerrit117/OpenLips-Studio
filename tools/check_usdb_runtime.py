"""Packaging guard against shipping a stale native downloader protocol."""
import json
from pathlib import Path
import subprocess
import tempfile
import os


def check_runtime(executable):
    with tempfile.TemporaryDirectory(prefix='openlips-usdb-build-check-') as folder:
        result = subprocess.run([str(Path(executable).resolve()), '--serve', '--output',
            str(Path(folder) / 'output'), '--state', str(Path(folder) / 'state')],
            input=json.dumps({'operation': 'capabilities'}) + '\n', text=True,
            encoding='utf-8', errors='replace', capture_output=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        messages = [json.loads(line.split(':', 1)[1]) for line in result.stdout.splitlines()
                    if line.startswith('OPENLIPS_RPC:')]
        if (result.returncode or not messages or 'download_batch' not in
                messages[-1].get('result', {}).get('operations', [])):
            raise ValueError('Rebuild USDBWorker.spec: the bundled runtime does not support native batch imports')
        return messages[-1]['result']
