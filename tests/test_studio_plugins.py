import json
from pathlib import Path
import sys
import time

import pytest

from studio.basic_pitch_plugin import (create_plugin, project_from_events,
                                        validate_options, worker_command)
from studio.model import StudioProject, EditorNote
from studio.plugins import ImportPlugin, discover_plugins, available_plugins, load_local_plugin


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
    offers, errors = available_plugins()
    assert offers[0].id == 'spotify-basic-pitch'
    plugins, errors = discover_plugins()
    assert plugins == []
    plugins, errors = discover_plugins(['spotify-basic-pitch'])
    assert not errors
    assert plugins[0].author == 'Spotify Audio Intelligence Lab'
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
    plugin = create_plugin()
    plugin.validate()
    with pytest.raises(ValueError):
        ImportPlugin('invalid', 'Bad', (), None, api_version=2).validate()
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    with pytest.raises(ValueError, match='runtime is missing'):
        worker_command('request', 'output')
    name = 'OpenLipsBasicPitch.exe' if sys.platform == 'win32' else 'OpenLipsBasicPitch'
    worker = tmp_path / 'plugin-runtime/OpenLipsBasicPitch' / name
    worker.parent.mkdir(parents=True)
    worker.touch()
    assert worker_command('request', 'output')[0] == str(worker)
    with pytest.raises(ValueError, match='unsupported custom Python'):
        worker_command('request', 'output', 'custom-python')
    monkeypatch.setattr(sys, 'frozen', False)
    assert worker_command('request', 'output', 'custom-python')[0] == 'custom-python'


def test_dialog_process_success_and_explicit_acceptance(tmp_path):
    from PySide6.QtCore import QSettings
    from studio.plugin_dialog import PluginDialog
    app = qt_app()
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('plugins/enabled', ['spotify-basic-pitch'])
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
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('plugins/enabled', ['spotify-basic-pitch'])
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
    assert 'abgebrochen' in dialog.status.text()
    dialog.close()


def test_failed_runtime_does_not_change_project(tmp_path):
    from PySide6.QtCore import QSettings
    from studio.plugin_dialog import PluginDialog
    app = qt_app()
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('plugins/enabled', ['spotify-basic-pitch'])
    project = StudioProject(notes=[EditorNote(0, 1, 60)])
    dialog = PluginDialog(project, settings=settings)
    source = tmp_path / 'source.wav'
    source.touch()
    dialog.input.setText(str(source))
    dialog.runtime.setText(str(tmp_path / 'missing-python'))
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
    from studio.plugin_package import inspect_package, MAX_BYTES
    path = tmp_path / 'link.opl'
    with zipfile.ZipFile(path, 'w') as archive:
        link = zipfile.ZipInfo('plugin.py')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, '../outside.py')
    with pytest.raises(ValueError, match='links'):
        inspect_package(path)
    path = tmp_path / 'huge.opl'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('huge', b'0' * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match='16 MiB'):
        inspect_package(path)


def test_platform_branding_assets_and_basic_pitch_package():
    from PIL import Image
    from studio.branding import asset
    from studio.plugin_package import inspect_package
    assert inspect_package(asset('basic-pitch.opl'))['id'] == create_plugin().id
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
    dialog = PluginDialog(StudioProject(), settings=QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    dialog.install_opl()
    assert dialog.offers[dialog.list.currentRow()].id == 'installed-example'
    assert not dialog.enable.isChecked()
    installed = Path(dialog.folders[0])
    assert (installed / 'plugin.py').exists()
    dialog.remove_folder()
    assert not dialog.folders
    assert package.exists() and (installed / 'plugin.py').exists()
    dialog.close()


def test_mac_app_worker_uses_intact_resources_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    contents = tmp_path / 'OpenLipsStudio.app/Contents'
    monkeypatch.setattr(sys, '_MEIPASS', str(contents / 'Frameworks'), raising=False)
    monkeypatch.setattr(sys, 'executable', str(contents / 'MacOS/OpenLipsStudio'))
    worker = contents / 'Resources/plugin-runtime/OpenLipsBasicPitch/OpenLipsBasicPitch'
    worker.parent.mkdir(parents=True)
    worker.touch()
    assert worker_command('request', 'output')[0] == str(worker)
