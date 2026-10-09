import zipfile
import pytest
from tools.package_ai_runtime import package
from tools.prepare_local_test_launchers import cmd_path


def test_ai_archive_excludes_samples_and_model_cache(tmp_path):
    engine = tmp_path / 'dist/OpenLipsAI'
    engine.mkdir(parents=True)
    (engine / 'OpenLipsAI.exe').write_bytes(b'synthetic-engine')
    (engine / 'small-model.onnx').write_bytes(b'synthetic-model')
    private = tmp_path / 'private'
    private.mkdir()
    (private / 'song.X360').write_bytes(b'do-not-package')
    archive = package('windows-2022', tmp_path / 'dist', tmp_path / 'release')
    with zipfile.ZipFile(archive) as stream:
        assert sorted(stream.namelist()) == ['ai/OpenLipsAI.exe', 'ai/small-model.onnx']
    assert archive.with_suffix('.zip.sha256').is_file()
    with pytest.raises(FileExistsError):
        package('windows-2022', tmp_path / 'dist', tmp_path / 'release')


def test_launcher_rejects_cmd_expansion(tmp_path):
    path = tmp_path / 'percent%name'
    path.touch()
    with pytest.raises(ValueError):
        cmd_path(path)


def test_amd_archive_uses_portable_stronger_compression(tmp_path):
    source = tmp_path / 'dist/OpenLipsAI'
    source.mkdir(parents=True)
    (source / 'OpenLipsAI.exe').write_bytes(b'synthetic engine' * 100)
    archive = package('windows-2022', tmp_path / 'dist', tmp_path / 'release', flavor='amd')
    with zipfile.ZipFile(archive) as stream:
        assert stream.getinfo('ai/OpenLipsAI.exe').compress_type == zipfile.ZIP_LZMA
        assert stream.read('ai/OpenLipsAI.exe') == b'synthetic engine' * 100
