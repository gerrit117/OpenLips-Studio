from pathlib import Path
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
from studio.model import StudioProject


@pytest.fixture
def app():
    application = QApplication.instance() or QApplication([])
    yield application
    application.processEvents()


def test_local_project_delete_button_and_confirmation(app,tmp_path,monkeypatch):
    from studio.library_page import LibraryPage
    page = LibraryPage(lambda: StudioProject(),root=tmp_path)
    identifier = page.library.add_project(StudioProject(title='Delete me'))
    page.refresh()
    item = page.projects.topLevelItem(0)
    item.setSelected(True)
    assert page.command_buttons['library.delete'].isEnabled()
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.StandardButton.No)
    page.delete_selected()
    assert page.library.projects()
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.StandardButton.Yes)
    page.delete_selected()
    assert page.worker.wait(5000)
    app.processEvents()
    assert page.library.projects() == []
    assert identifier in page.library.deleted('projects')
    page.close()


def test_remote_deletion_policy_defaults_off_and_is_per_connection(app,tmp_path,monkeypatch):
    import studio.remote_library as module
    settings = QSettings(str(tmp_path/'settings.ini'),QSettings.Format.IniFormat)
    monkeypatch.setattr(module,'QSettings',lambda *args: settings)
    monkeypatch.setattr(module,'load_profiles',lambda path: [
        dict(name='One',server_id='a'*32),dict(name='Two',server_id='b'*32)])
    page = module.RemoteLibraryPage(lambda: StudioProject())
    assert not page.delete_remote.isChecked()
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.StandardButton.Yes)
    page.delete_remote.setChecked(True)
    assert settings.value('library/delete_remote/'+'a'*32,False,type=bool)
    page.connections.setCurrentIndex(1)
    assert not page.delete_remote.isChecked()
    page.connections.setCurrentIndex(0)
    assert page.delete_remote.isChecked()
    page.close()


def test_save_queue_coalesces_busy_saves_without_new_entries(app,tmp_path,monkeypatch):
    from studio.app import StudioWindow
    from studio.library import Library
    from studio.model import load_project
    from types import SimpleNamespace
    monkeypatch.setattr('studio.library_page.configured_library',lambda: tmp_path)
    window = StudioWindow()
    busy = [True]
    worker = SimpleNamespace(isRunning=lambda: busy[0])
    local = SimpleNamespace(task=lambda callback: callback(lambda message: None))
    window.library_page = SimpleNamespace(worker=worker,local=local)
    window.replace_project(StudioProject(title='Song'))
    window.path = tmp_path/'workspace'/'song.olp'
    try:
        for artist in ('One','Two','Three'):
            window.artist_edit.setText(artist)
            assert window.save()
        assert len(window.library_save_queue) == 1
        busy[0] = False
        window.flush_library_saves()
        library = Library(tmp_path)
        assert len(library.projects()) == 1
        assert library.projects()[0]['artist'] == 'Three'
        assert load_project(window.path).artist == 'Three'
    finally:
        window.dirty = False
        window.close()


def test_delete_waits_for_background_sync_in_top_level_window(app,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QWidget
    from studio.library_page import LibraryPage
    owner = QWidget()
    owner.library_busy = lambda: True
    stack = QWidget(owner)
    page = LibraryPage(lambda: StudioProject(),stack,root=tmp_path)
    page.library.add_project(StudioProject(title='Keep while syncing'))
    page.refresh()
    page.projects.topLevelItem(0).setSelected(True)
    assert page.is_busy()
    assert not page.command_buttons['library.delete'].isEnabled()
    monkeypatch.setattr(QMessageBox,'question',lambda *args: pytest.fail('Busy delete must not ask or run'))
    page.delete_selected()
    assert len(page.library.projects()) == 1
    owner.close()
