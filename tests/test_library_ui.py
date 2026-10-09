"""Optional library workspace lifecycle, using isolated preferences."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from studio.app import StudioWindow
from studio.model import EditorNote, StudioProject, load_project


def test_library_toggle_preserves_files_and_reopens_snapshot(tmp_path, monkeypatch):
    state = {'library/enabled': False, 'library/root': str(tmp_path / 'library')}
    class Settings:
        def __init__(self, *_):
            pass
        def value(self, key, default=None, **kwargs):
            return state.get(key, default)
        def setValue(self, key, value):
            state[key] = value
    monkeypatch.setattr('studio.app.QSettings', Settings)
    monkeypatch.setattr('studio.library_page.QSettings', Settings)
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    try:
        from studio.i18n import tr
        tools = next(action.menu() for action in window.menuBar().actions() if action.text() == tr('Werkzeuge'))
        menus = {action.text(): action.menu() for action in tools.actions() if action.menu()}
        assert all(tr(key) in menus for key in ('tools.lyrics', 'tools.charts', 'tools.media', 'tools.library'))
        assert window.smart_pages_action in menus[tr('tools.lyrics')].actions()
        assert window.library_action in menus[tr('tools.library')].actions()
        assert any(action.text() == tr('download.youtube') for action in menus[tr('tools.media')].actions())
        assert window.library_page is None
        window.toggle_library(True)
        assert window.library_page is not None
        assert state['library/enabled'] is True
        path = window.library_page.library.root / 'library.sqlite3'
        assert path.is_file()
        window.toggle_library(False)
        assert window.library_page is None
        assert state['library/enabled'] is False
        assert path.is_file()
        window.toggle_library(True)
        assert window.library_page.library.root == path.parent
        local = window.library_page.local
        local.tabs.setCurrentWidget(local.packages)
        assert local.export_button.text() == tr('library.export_packages')
        assert any(button.text() == tr('usb.title') for button in local.buttons)
        local.tabs.setCurrentWidget(local.projects)
        assert local.export_button.text() == tr('library.export')
        identifier = window.library_page.library.add_project(StudioProject(
            title='Snapshot', artist='OpenLips', notes=[EditorNote(1, 1, 60, 'Test')]))
        snapshot = window.library_page.library.project_path(identifier)
        window.open_library_project(str(snapshot))
        assert window.path is None
        window.project.notes[0].pitch = 61
        assert load_project(snapshot).notes[0].pitch == 60
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
