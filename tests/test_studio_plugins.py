import json
from pathlib import Path
import sys
import time

import pytest

from plugins.basic_pitch.engine import project_from_events, validate_options
from studio.plugin_process import load_process_plugin, platform_tag
from studio.model import StudioProject, EditorNote
from studio.plugins import ImportPlugin, discover_plugins, available_plugins, load_local_plugin

PLUGIN_SOURCE = Path(__file__).resolve().parents[1] / 'plugins/basic_pitch'


def plugin_settings(path):
    from PySide6.QtCore import QSettings
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    settings.setValue('plugins/folders', [str(PLUGIN_SOURCE)])
    settings.setValue('plugins/enabled', ['spotify-basic-pitch'])
    return settings


def qt_app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def wait_until(app, predicate, timeout=10):
    start = time.monotonic()
    while not predicate():
        app.processEvents()
        time.sleep(.01)
        assert time.monotonic() - start < timeout
    app.processEvents()


def test_basic_pitch_is_opt_in_without_loading_ml():
    assert available_plugins()[0] == []
    offers, errors = available_plugins([PLUGIN_SOURCE])
    assert offers[0].id == 'spotify-basic-pitch'
    plugins, errors = discover_plugins()
    assert plugins == []
    plugins, errors = discover_plugins(['spotify-basic-pitch'], [PLUGIN_SOURCE])
    assert not errors
    assert 'Spotify Audio Intelligence Lab' in plugins[0].author
    assert plugins[0].process_plugin
    assert 'basic_pitch' not in sys.modules


def test_options_and_monophonic_draft():
    assert validate_options({})['minimum_note_length'] == 127
    for options in ({'minimum_pitch': 84, 'maximum_pitch': 45}, {'onset_threshold': float('nan')},
                    {'minimum_note_length': 2.5}, {'frame_threshold': True}, {'melody_mode': 'unknown'}):
        with pytest.raises(ValueError):
            validate_options(options)
    project = project_from_events([(0, 2, 60, .2), (.5, 1, 72, .9)], 'original.wav')
    assert [(n.time, n.length, n.pitch) for n in project.notes] == [(0, .5, 60), (.5, .5, 72), (1, 1, 60)]
    assert all(not n.text for n in project.notes)
    assert len(project_from_events([(0, 2, 60, .2), (.5, 1, 72, .9)], 'original.wav', 'all').notes) == 2
    with pytest.raises(ValueError):
        project_from_events([(0, 1, float('nan'), .2)], 'original.wav')


def test_local_plugin_is_not_executed_until_enabled(tmp_path):
    folder = tmp_path / 'plugin'
    folder.mkdir()
    sentinel = folder / 'loaded'
    (folder / 'openlips-plugin.json').write_text(json.dumps({'id': 'example', 'module': 'plugin.py'}))
    (folder / 'plugin.py').write_text(
        'from pathlib import Path\nfrom studio.plugins import ImportPlugin\n'
        f'Path({str(sentinel)!r}).touch()\n'
        "def create_plugin():\n    return ImportPlugin('example', 'Example', ('.txt',), lambda path: None)\n")
    available_plugins([folder])
    discover_plugins([], [folder])
    assert not sentinel.exists()
    plugins, errors = discover_plugins(['example'], [folder])
    assert not errors and plugins[0].id == 'example'
    assert sentinel.exists()
    (folder / 'openlips-plugin.json').write_text(json.dumps({'id': 'escape', 'module': '../outside.py'}))
    with pytest.raises(ValueError):
        load_local_plugin(folder / 'openlips-plugin.json')


def test_plugin_api_and_worker_selection(tmp_path, monkeypatch):
    data = json.loads((PLUGIN_SOURCE / 'openlips-plugin.json').read_text(encoding='utf-8'))
    plugin = load_process_plugin(tmp_path, data)
    plugin.validate()
    with pytest.raises(ValueError):
        ImportPlugin('invalid', 'Bad', (), None, api_version=2).validate()
    with pytest.raises(FileNotFoundError):
        plugin.create_command('request', 'output')
    worker = tmp_path / data['entrypoints'][platform_tag()]
    worker.parent.mkdir(parents=True)
    worker.touch()
    assert plugin.create_command('request', 'output')[0] == str(worker)


def test_dialog_process_success_and_explicit_acceptance(tmp_path):
    from PySide6.QtCore import QSettings
    from studio.plugin_dialog import PluginDialog
    app = qt_app()
    settings = plugin_settings(tmp_path / 'settings.ini')
    dialog = PluginDialog(StudioProject(), settings=settings)
    result = StudioProject(notes=[EditorNote(1, .5, 65)])
    script = tmp_path / 'fake_worker.py'
    script.write_text('import pathlib,sys,json\n'
        f"pathlib.Path(sys.argv[1], 'result.json').write_text({json.dumps(result.to_payload())!r})\n"
        "print('OPENLIPS_PLUGIN:' + json.dumps({'message': 'Synthetic done'}), flush=True)\n")
    dialog.plugin = ImportPlugin('synthetic', 'Synthetic', ('.wav',), None,
        create_command=lambda request, output, python: [sys.executable, str(script), str(output)])
    source = tmp_path / 'synthetic.wav'
    source.write_bytes(b'synthetic')
    dialog.input.setText(str(source))
    received = []
    dialog.accepted_project.connect(received.append)
    dialog.run_plugin()
    wait_until(app, lambda: not dialog.busy())
    assert dialog.result.notes[0].pitch == 65
    assert dialog.preview.rowCount() == 1
    assert not received
    assert dialog.apply_button.isEnabled()
    dialog.apply_result()
    assert received[0].notes[0].pitch == 65
    assert dialog.temp is None


def test_process_cancellation_and_close_guard(tmp_path):
    from PySide6.QtCore import QSettings
    from studio.plugin_dialog import PluginDialog
    app = qt_app()
    settings = plugin_settings(tmp_path / 'settings.ini')
    dialog = PluginDialog(StudioProject(), settings=settings)
    dialog.plugin = ImportPlugin('slow', 'Slow', (), None,
        create_command=lambda *args: [sys.executable, '-c', 'import time; time.sleep(30)'])
    source = tmp_path / 'source.wav'
    source.touch()
    dialog.input.setText(str(source))
    dialog.show()
    dialog.run_plugin()
    wait_until(app, lambda: dialog.process.state().name == 'Running')
    dialog.reject()
    assert dialog.isVisible()
    assert not dialog.add_button.isEnabled()
    dialog.cancel()
    wait_until(app, lambda: not dialog.busy())
    assert dialog.result is None
    assert not dialog.apply_button.isEnabled()
    from studio.i18n import tr
    assert dialog.status.text() == tr('Analyse abgebrochen. Das Projekt wurde nicht geändert.')
    dialog.close()


def test_failed_runtime_does_not_change_project(tmp_path):
    from PySide6.QtCore import QSettings
    from studio.plugin_dialog import PluginDialog
    app = qt_app()
    settings = plugin_settings(tmp_path / 'settings.ini')
    project = StudioProject(notes=[EditorNote(0, 1, 60)])
    dialog = PluginDialog(project, settings=settings)
    source = tmp_path / 'source.wav'
    source.touch()
    dialog.input.setText(str(source))
    dialog.run_plugin()
    wait_until(app, lambda: not dialog.busy())
    assert project.notes[0].pitch == 60
    assert dialog.result is None
    assert dialog.run_button.isEnabled()
    dialog.close()


def test_plugin_note_application_is_undoable_and_preserves_metadata():
    from studio.app import StudioWindow
    app = qt_app()
    window = StudioWindow()
    original = window.project.to_payload()
    result = StudioProject(title='Analysis', notes=[EditorNote(1, .5, 70)])
    window.apply_plugin_notes(result)
    assert window.project.title == original['title']
    assert window.project.artist == original['artist']
    assert window.project.notes[0].pitch == 70
    window.undo()
    assert window.project.to_payload() == original
    assert not window.windowIcon().isNull()
    window.dirty = False
    window.close()


def test_opl_roundtrip_installation_does_not_execute_code(tmp_path):
    from studio.plugin_package import build_package, install_package, inspect_package
    source = tmp_path / 'package'
    source.mkdir()
    (source / 'openlips-plugin.json').write_text(json.dumps({'id': 'example', 'module': 'plugin.py'}))
    (source / 'plugin.py').write_text("raise RuntimeError('must not execute during installation')")
    package = build_package(source, tmp_path / 'example.opl')
    assert inspect_package(package)['id'] == 'example'
    installed = install_package(package, tmp_path / 'plugins')
    assert (installed / 'plugin.py').read_text().startswith('raise')
    with pytest.raises(FileExistsError):
        install_package(package, tmp_path / 'plugins')
    assert package.exists()
    with pytest.raises(ValueError, match='.olp'):
        inspect_package(tmp_path / 'project.olp')


@pytest.mark.parametrize('unsafe', ['../outside.py', '/absolute.py', 'C:/outside.py', '..\\outside.py', 'space /bad.py'])
def test_opl_rejects_unsafe_paths(tmp_path, unsafe):
    import zipfile
    from studio.plugin_package import inspect_package
    path = tmp_path / 'bad.opl'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('openlips-plugin.json', json.dumps({'id': 'bad', 'module': 'plugin.py'}))
        archive.writestr('plugin.py', '')
        archive.writestr(unsafe, '')
    with pytest.raises(ValueError, match='Unsafe'):
        inspect_package(path)


def test_opl_rejects_symlinks_and_oversized_payload(tmp_path):
    import stat
    import zipfile
    from studio.plugin_package import inspect_package, LEGACY_MAX_BYTES
    path = tmp_path / 'link.opl'
    with zipfile.ZipFile(path, 'w') as archive:
        link = zipfile.ZipInfo('plugin.py')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, '../outside.py')
    with pytest.raises(ValueError):
        inspect_package(path)
    path = tmp_path / 'huge.opl'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('openlips-plugin.json', json.dumps({'id': 'huge', 'module': 'plugin.py'}))
        archive.writestr('plugin.py', '')
        archive.writestr('huge', b'0' * (LEGACY_MAX_BYTES + 1))
    with pytest.raises(ValueError, match='16 MiB'):
        inspect_package(path)


def test_platform_branding_assets_and_basic_pitch_package():
    from PIL import Image
    from studio.branding import asset
    with Image.open(asset('app-icon.ico')) as icon:
        assert (16, 16) in icon.info['sizes']
        assert (256, 256) in icon.info['sizes']
    with Image.open(asset('app-icon.icns')) as icon:
        assert icon.size == (1024, 1024)


def test_opl_ui_install_and_unlink_keep_original_files(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings, QStandardPaths
    from PySide6.QtWidgets import QFileDialog
    from studio.plugin_dialog import PluginDialog
    from studio.plugin_package import build_package
    app = qt_app()
    source = tmp_path / 'original'
    source.mkdir()
    (source / 'openlips-plugin.json').write_text(json.dumps({'id': 'installed-example', 'module': 'plugin.py'}))
    (source / 'plugin.py').write_text("raise RuntimeError('must not load when installed')")
    package = build_package(source, tmp_path / 'example.opl')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(package), ''))
    monkeypatch.setattr(QStandardPaths, 'writableLocation', lambda *args: str(tmp_path / 'app-data'))
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('plugins/enabled', ['installed-example'])
    dialog = PluginDialog(StudioProject(), settings=settings)
    dialog.install_opl()
    wait_until(app, lambda: not dialog.busy())
    assert dialog.offers[dialog.list.currentRow()].id == 'installed-example'
    assert not dialog.enable.isChecked()
    assert 'installed-example' not in dialog.enabled_ids
    installed = Path(dialog.folders[0])
    assert (installed / 'plugin.py').exists()
    dialog.remove_folder()
    assert not dialog.folders
    assert package.exists() and (installed / 'plugin.py').exists()
    dialog.close()


def test_mac_app_worker_uses_intact_resources_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    contents = tmp_path / 'separate-plugin'
    monkeypatch.setattr(sys, '_MEIPASS', str(contents / 'Frameworks'), raising=False)
    monkeypatch.setattr(sys, 'executable', str(contents / 'MacOS/OpenLipsStudio'))
    data = json.loads((PLUGIN_SOURCE / 'openlips-plugin.json').read_text(encoding='utf-8'))
    import platform
    monkeypatch.setattr(platform, 'machine', lambda: 'arm64')
    worker = contents / data['entrypoints']['macos-arm64']
    worker.parent.mkdir(parents=True)
    worker.touch()
    assert load_process_plugin(contents, data).create_command('request', 'output')[0] == str(worker)


def test_frozen_worker_environment_is_isolated(monkeypatch):
    from studio.plugin_dialog import plugin_process_environment
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setenv('DYLD_LIBRARY_PATH', '/gui/libraries')
    monkeypatch.setenv('PYTHONHOME', '/gui/python')
    monkeypatch.setenv('LD_LIBRARY_PATH', '/gui/libraries:/system')
    monkeypatch.setenv('LD_LIBRARY_PATH_ORIG', '/system')
    environment = plugin_process_environment()
    assert environment.value('PYINSTALLER_RESET_ENVIRONMENT') == '1'
    assert not environment.contains('DYLD_LIBRARY_PATH')
    assert not environment.contains('PYTHONHOME')
    assert environment.value('LD_LIBRARY_PATH') == '/system'


def process_package(tmp_path, extra=None):
    import zipfile
    import stat
    manifest = json.loads((PLUGIN_SOURCE / 'openlips-plugin.json').read_text(encoding='utf-8'))
    manifest['entrypoints'] = {platform_tag(): 'runtime/worker.exe' if sys.platform == 'win32' else 'runtime/worker'}
    if extra:
        manifest.update(extra)
    archive = tmp_path / 'process.opl'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr('openlips-plugin.json', json.dumps(manifest))
        worker = zipfile.ZipInfo(next(iter(manifest['entrypoints'].values())))
        worker.create_system = 3
        worker.external_attr = (stat.S_IFREG | 0o755) << 16
        stream.writestr(worker, b'synthetic-native-executable')
    return archive, manifest


def test_process_plugin_large_runtime_and_native_permissions(tmp_path):
    import os
    import zipfile
    from studio.plugin_package import install_package, LEGACY_MAX_BYTES
    archive, manifest = process_package(tmp_path)
    with zipfile.ZipFile(archive, 'a', compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr('runtime/model', b'x' * (LEGACY_MAX_BYTES + 1))
    installed = install_package(archive, tmp_path / 'installed')
    assert installed.name == 'spotify-basic-pitch-0.4.0-2'
    worker = installed / manifest['entrypoints'][platform_tag()]
    assert worker.read_bytes() == b'synthetic-native-executable'
    if os.name != 'nt':
        assert os.access(worker, os.X_OK)
    assert load_local_plugin(installed / 'openlips-plugin.json').create_command('r', 'o')[0] == str(worker)


def test_process_plugin_rejects_wrong_platform_and_unknown_api(tmp_path):
    from studio.plugin_package import inspect_package
    tag = 'linux-arm64' if platform_tag() != 'linux-arm64' else 'windows-arm64'
    archive, _ = process_package(tmp_path, {'entrypoints': {tag: 'runtime/worker'}})
    with pytest.raises(ValueError, match='does not support'):
        inspect_package(archive)
    archive, _ = process_package(tmp_path, {'protocol': 999})
    with pytest.raises(ValueError, match='Unsupported'):
        inspect_package(archive)


@pytest.mark.parametrize('name', ['CON.py', 'runtime/aux.txt', 'runtime/../escape', 'runtime//worker', 'runtime/worker.'])
def test_process_plugin_rejects_portably_unsafe_names(tmp_path, name):
    import zipfile
    from studio.plugin_package import inspect_package
    archive, _ = process_package(tmp_path)
    with zipfile.ZipFile(archive, 'a') as stream:
        stream.writestr(name, 'bad')
    with pytest.raises(ValueError):
        inspect_package(archive)


def test_process_install_rolls_back_on_corrupt_runtime(tmp_path):
    import zipfile
    from studio.plugin_package import install_package
    archive, manifest = process_package(tmp_path)
    with zipfile.ZipFile(archive, 'a') as stream:
        stream.writestr(manifest['entrypoints'][platform_tag()] + '/data', b'file-parent-conflict')
    with pytest.raises(OSError):
        install_package(archive, tmp_path / 'installed')
    assert list((tmp_path / 'installed').iterdir()) == []


@pytest.mark.skipif(sys.platform == 'win32', reason='Unix symlink/execute semantics')
def test_native_package_preserves_internal_links_and_rejects_escaping_links(tmp_path):
    import stat
    import zipfile
    from studio.plugin_package import install_package, inspect_package
    archive, manifest = process_package(tmp_path)
    with zipfile.ZipFile(archive, 'a') as stream:
        stream.writestr('runtime/library-real', b'original-library')
        link = zipfile.ZipInfo('runtime/library')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        stream.writestr(link, 'library-real')
    installed = install_package(archive, tmp_path / 'installed')
    assert (installed / 'runtime/library').is_symlink()
    assert (installed / 'runtime/library').read_bytes() == b'original-library'
    with zipfile.ZipFile(archive, 'a') as stream:
        link = zipfile.ZipInfo('escape')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        stream.writestr(link, '../outside')
    with pytest.raises(ValueError, match='escapes'):
        inspect_package(archive)


def test_independent_lyric_worker_preserves_chart_fields(tmp_path):
    from plugins.example_lyrics.worker import run
    project = StudioProject(notes=[EditorNote(2, .7, 62, line_break_after=True), EditorNote(1, .5, 60)])
    source = tmp_path / 'words.txt'
    source.write_text('Hello world', encoding='utf-8')
    before = project.to_payload()
    result = run({'protocol': 1, 'input': str(source), 'options': {}, 'project': before}, tmp_path / 'output')
    resolved = StudioProject.from_payload(result)
    assert [n.text for n in resolved.ordered()] == ['Hello', 'world']
    assert [(n.id, n.time, n.length, n.pitch, n.line_break_after) for n in resolved.notes] == [
        (n.id, n.time, n.length, n.pitch, n.line_break_after) for n in project.notes]
    assert project.to_payload() == before


def test_studio_does_not_import_or_bundle_basic_pitch():
    root = Path(__file__).resolve().parents[1]
    assert not (root / 'studio/basic_pitch_plugin.py').exists()
    assert not (root / 'studio/basic_pitch_worker.py').exists()
    spec = (root / 'OpenLipsStudio.spec').read_text()
    assert 'OpenLipsBasicPitch' not in spec
    for path in (PLUGIN_SOURCE / 'engine.py', PLUGIN_SOURCE / 'worker.py'):
        assert 'from studio' not in path.read_text(encoding='utf-8')


def test_linking_new_folder_does_not_reuse_id_trust(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QFileDialog
    from studio.plugin_dialog import PluginDialog
    app = qt_app()
    (tmp_path / 'openlips-plugin.json').write_text(json.dumps({'id': 'remembered', 'module': 'plugin.py'}))
    (tmp_path / 'plugin.py').write_text("raise RuntimeError('must not execute when linked')")
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('plugins/enabled', ['remembered'])
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path))
    dialog = PluginDialog(StudioProject(), settings=settings)
    dialog.add_folder()
    assert dialog.plugin is None and not dialog.enable.isChecked()
    assert not dialog.enabled_ids
    dialog.close()
