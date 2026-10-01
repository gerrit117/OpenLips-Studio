import hashlib
import os
import tarfile
import zipfile

import pytest

from tools.package_studio_release import package
from tools.bundle_plugin_runtime import bundle


def test_windows_release_contains_only_app_and_checksum(tmp_path):
    app = tmp_path / 'dist/OpenLipsStudio'
    app.mkdir(parents=True)
    (app / 'OpenLipsStudio.exe').write_bytes(b'synthetic-executable')
    (tmp_path / 'private').mkdir()
    (tmp_path / 'private/sample.X360').write_bytes(b'private')
    archive = package('windows-2022', tmp_path / 'dist', tmp_path / 'release')
    with zipfile.ZipFile(archive) as stream:
        assert stream.namelist() == ['OpenLipsStudio/OpenLipsStudio.exe']
    checksum = archive.with_suffix('.zip.sha256').read_text()
    assert checksum.startswith(hashlib.sha256(archive.read_bytes()).hexdigest())
    with pytest.raises(FileExistsError):
        package('windows-2022', tmp_path / 'dist', tmp_path / 'release')


def test_worker_bundle_is_an_intact_separate_runtime(tmp_path):
    import sys
    worker = tmp_path / 'worker'
    worker.mkdir()
    name = 'OpenLipsBasicPitch.exe' if sys.platform == 'win32' else 'OpenLipsBasicPitch'
    (worker / name).write_bytes(b'original-worker')
    (worker / '_internal').mkdir()
    (worker / '_internal/python-library').write_bytes(b'worker-python-not-gui-python')
    app = tmp_path / 'OpenLipsStudio'
    app.mkdir()
    result = bundle(worker, app, sign=False)
    assert (result / name).read_bytes() == b'original-worker'
    assert (result / '_internal/python-library').read_bytes() == b'worker-python-not-gui-python'
    (worker / '_internal/python-library').write_bytes(b'updated-worker')
    bundle(worker, app, sign=False)
    assert (result / '_internal/python-library').read_bytes() == b'updated-worker'
    mac_app = tmp_path / 'OpenLipsStudio.app'
    mac_app.mkdir()
    result = bundle(worker, mac_app, sign=False)
    assert result.parent.parent == mac_app / 'Contents/Frameworks'


@pytest.mark.skipif(os.name == 'nt', reason='Unix permission/symlink semantics')
def test_linux_release_preserves_executable_and_symlinks(tmp_path):
    app = tmp_path / 'dist/OpenLipsStudio'
    app.mkdir(parents=True)
    executable = app / 'OpenLipsStudio'
    executable.write_bytes(b'#!/bin/sh\n')
    executable.chmod(0o755)
    (app / 'link').symlink_to('OpenLipsStudio')
    archive = package('ubuntu-22.04', tmp_path / 'dist', tmp_path / 'release')
    with tarfile.open(archive) as stream:
        assert stream.getmember('OpenLipsStudio/OpenLipsStudio').mode & 0o111 == 0o111
        assert stream.getmember('OpenLipsStudio/link').issym()
    (app / 'outside').symlink_to(tmp_path / 'private')
    (tmp_path / 'private').touch()
    with pytest.raises(ValueError):
        package('ubuntu-22.04', tmp_path / 'dist', tmp_path / 'release2')
