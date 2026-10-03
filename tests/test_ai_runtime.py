import io
import tarfile
import zipfile
import pytest

from studio.ai_runtime import choose_asset, choose_engine_asset, extract_checked, installed_engine


def test_missing_amd_asset_falls_back_to_cpu():
    cpu = 'OpenLips-AI-0.3.0-beta.1-windows-x64.zip'
    releases = [{'assets': [{'name': cpu}, {'name': cpu + '.sha256'}]}]
    target, selection = choose_engine_asset(releases, 'windows-x64', '.zip', 'amd')
    assert target == 'windows-x64'
    assert selection[1]['name'] == cpu
    with pytest.raises(ValueError):
        choose_engine_asset([], 'windows-x64', '.zip', 'amd')


def test_choose_matching_complete_release():
    name = 'OpenLips-AI-0.3.0-beta.1-windows-x64.zip'
    releases = [{'draft': False, 'assets': [{'name': name}, {'name': name + '.sha256'}]}]
    assert choose_asset(releases, 'windows-x64', '.zip')[0] == '0.3.0-beta.1'
    with pytest.raises(ValueError):
        choose_asset(releases, 'linux-x64', '.tar.gz')


def test_amd_release_is_distinct_from_cpu():
    cpu = 'OpenLips-AI-0.3.3-beta.1-windows-x64.zip'
    amd = 'OpenLips-AI-0.3.3-beta.1-windows-x64-amd.zip'
    releases = [{'assets': [{'name': name} for name in
                            (amd, amd + '.sha256', cpu, cpu + '.sha256')]}]
    assert choose_asset(releases, 'windows-x64', '.zip')[1]['name'] == cpu
    assert choose_asset(releases, 'windows-x64-amd', '.zip')[1]['name'] == amd


def test_installed_engines_keep_backends_separate(tmp_path):
    import os
    name = 'OpenLipsAI.exe' if os.name == 'nt' else 'OpenLipsAI'
    paths = {}
    for flavor, suffix in [('cpu', 'windows-x64'), ('amd', 'windows-x64-amd')]:
        path = tmp_path / ('0.3.3-beta.1-' + suffix) / 'ai' / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b'synthetic')
        paths[flavor] = str(path)
    assert installed_engine(tmp_path) == paths['cpu']
    assert installed_engine(tmp_path, flavor='amd') == paths['amd']


def test_extract_synthetic_runtime(tmp_path):
    archive = tmp_path / 'engine.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('ai/OpenLipsAI.exe', b'synthetic-executable')
    extract_checked(archive, tmp_path / 'ready')
    assert (tmp_path / 'ready/ai/OpenLipsAI.exe').read_bytes() == b'synthetic-executable'


@pytest.mark.parametrize('path', ['../escape', 'ai/../../escape', '/ai/escape', 'ai/C:escape', 'other/file'])
def test_archive_path_rejected(tmp_path, path):
    archive = tmp_path / 'engine.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr(path, b'bad')
    with pytest.raises(ValueError):
        extract_checked(archive, tmp_path / 'ready')


def test_tar_symlink_escape_rejected(tmp_path):
    archive = tmp_path / 'engine.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        link = tarfile.TarInfo('ai/escape')
        link.type = tarfile.SYMTYPE
        link.linkname = '../../escape'
        stream.addfile(link)
    with pytest.raises(ValueError):
        extract_checked(archive, tmp_path / 'ready')


def test_cancelled_install_leaves_no_executable(tmp_path):
    archive = tmp_path / 'engine.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('ai/OpenLipsAI.exe', b'synthetic')
    with pytest.raises(InterruptedError):
        extract_checked(archive, tmp_path / 'ready', lambda: True)
    assert not (tmp_path / 'ready/ai/OpenLipsAI.exe').exists()
