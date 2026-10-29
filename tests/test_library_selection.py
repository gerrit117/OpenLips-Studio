from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QTreeWidget, QMenu

from studio.model import StudioProject


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def remote(app, tmp_path, monkeypatch):
    import studio.remote_library as module
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    monkeypatch.setattr(module, 'QSettings', lambda *args: settings)
    monkeypatch.setattr(module, 'default_library_root', lambda: tmp_path / 'Library')
    page = module.RemoteLibraryPage(lambda: StudioProject())
    page.scanned = True
    page.sync_timer.stop()
    yield page
    if page.worker:
        page.worker.wait(5000)
        app.processEvents()
    page.close()


def test_local_delete_button_removes_multiple_selected_entries(app, tmp_path, monkeypatch):
    from studio.library_page import LibraryPage
    page = LibraryPage(lambda: StudioProject(), root=tmp_path)
    for title in ('One', 'Two', 'Three'):
        page.library.add_project(StudioProject(title=title))
    page.refresh()
    for i in (0, 1):
        page.projects.topLevelItem(i).setSelected(True)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    QTest.mouseClick(page.command_buttons['library.delete'], Qt.MouseButton.LeftButton)
    assert page.worker is not None
    assert page.worker.wait(5000)
    app.processEvents()
    assert len(page.library.projects()) == 1
    assert len(page.library.deleted('projects')) == 2
    page.close()


def test_remote_delete_uses_selection_not_current_row(remote, monkeypatch):
    remote.received({'projects': [dict(id=str(i), title=str(i)) for i in range(3)]})
    assert remote.tree.selectionMode() == QTreeWidget.SelectionMode.ExtendedSelection
    remote.tree.topLevelItem(0).setSelected(True)
    remote.tree.topLevelItem(1).setSelected(True)
    assert remote.tree.currentItem() is None
    calls = []
    def request(method, endpoint):
        calls.append((method, endpoint))
        return {} if method == 'GET' else {'removed': True}
    remote.client = SimpleNamespace(request=request)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(remote, 'task', lambda work, done, **kwargs: done(work()))
    remote.actions[-1].click()
    assert calls == [('DELETE', '/api/v1/projects/0'), ('DELETE', '/api/v1/projects/1'),
                     ('GET', '/api/v1/library')]


def test_remote_delete_skips_artifact_already_removed_with_project(remote, monkeypatch):
    remote.received({'projects': [dict(id='a', title='A')], 'artifacts': [
        dict(id='b', project_id='a', filename='chart.ols', kind='chart')]})
    remote.tree.selectAll()
    calls = []
    remote.client = SimpleNamespace(request=lambda method, endpoint: calls.append((method, endpoint)) or {})
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(remote, 'task', lambda work, done, **kwargs: done(work()))
    remote.delete_selected()
    assert calls == [('DELETE', '/api/v1/projects/a'), ('GET', '/api/v1/library')]


def test_remote_delete_reports_partial_failure_and_refreshes(remote, monkeypatch):
    remote.received({'projects': [dict(id=str(i), title=str(i)) for i in range(2)]})
    remote.tree.selectAll()
    calls, warnings = [], []
    def request(method, endpoint):
        calls.append(endpoint)
        if endpoint.endswith('/0'):
            raise ValueError('Permission denied')
        return {}
    remote.client = SimpleNamespace(request=request)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    monkeypatch.setattr(remote, 'task', lambda work, done, **kwargs: done(work()))
    remote.delete_selected()
    assert len(calls) == 3
    assert warnings and 'Permission denied' in remote.status.text()


def test_remote_context_menu_keeps_multiple_selection(remote, monkeypatch):
    remote.received({'projects': [dict(id=str(i), title=str(i)) for i in range(3)]})
    remote.resize(900, 700)
    remote.show()
    QApplication.processEvents()
    remote.tree.topLevelItem(0).setSelected(True)
    remote.tree.topLevelItem(1).setSelected(True)
    QTimer.singleShot(0, lambda: QApplication.activePopupWidget().close())
    remote.context_menu(remote.tree.visualItemRect(remote.tree.topLevelItem(1)).center())
    assert len(remote.tree.selectedItems()) == 2


def test_named_connections_survive_reopening_and_restore_last_address(remote, monkeypatch):
    import studio.remote_library as module
    from studio.library_client import LibraryClient
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args: ('Unraid', True))
    monkeypatch.setattr(remote, 'task', lambda work, done, **kwargs: done(work()))
    monkeypatch.setattr(LibraryClient, 'request', lambda *args: dict(
        server_id='a' * 32, name='Library', auth_required=False))
    remote.url.setText('http://192.168.1.3:8765')
    remote.save_button.click()
    assert remote.profiles[0]['name'] == 'Unraid'
    # A second connection must not hide the first one or reset the last choice.
    client = LibraryClient('http://192.168.1.20:8765')
    remote.paired(client, (dict(name='PC'), dict(server_id='b' * 32, api_token='', ftp={})))
    remote.connections.setCurrentIndex(0)
    monkeypatch.setattr(remote, 'refresh', lambda: None)
    remote.connect_saved()
    reopened = module.RemoteLibraryPage(lambda: StudioProject())
    reopened.scanned = True
    reopened.sync_timer.stop()
    assert reopened.connections.count() == 2
    assert reopened.connections.currentText() == 'Unraid'
    assert reopened.url.text() == 'http://192.168.1.3:8765'
    reopened.connections.setCurrentIndex(1)
    assert reopened.url.text() == 'http://192.168.1.20:8765'
    reopened.close()
