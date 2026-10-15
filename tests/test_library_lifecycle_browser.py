import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from tests.test_library_lifecycle import peers, song, package


def test_browser_edits_and_deletes_projects_and_dlc(peers):
    node = shutil.which('node')
    module = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'
    if not node or not module.exists():
        pytest.skip('Local Playwright runtime unavailable')
    _,remote,client = peers
    remote.add_project(song('Browser project'))
    identifier = package(remote)
    with remote.connect() as db:
        db.execute('UPDATE packages SET songs=? WHERE id=?',(json.dumps([
            dict(title='Pack song',artist='Pack artist',song_id=123)]),identifier))
        db.execute('INSERT INTO package_details VALUES (?,?,?,?)',(identifier,None,'unknown',''))
    environment = dict(os.environ,PLAYWRIGHT_MODULE=str(module),LIBRARY_URL=client.url)
    result = subprocess.run([node,str(Path(__file__).parent/'ui/library_lifecycle.cjs')],
        env=environment,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr
    assert remote.projects() == [] and remote.packages() == []
