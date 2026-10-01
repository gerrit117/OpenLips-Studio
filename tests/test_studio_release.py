import hashlib
import os
import tarfile
import zipfile

import pytest

from tools.package_studio_release import package


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
