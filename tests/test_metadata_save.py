import pytest
from PySide6.QtWidgets import QApplication

from studio.app import StudioWindow
from studio.model import StudioProject, load_project


@pytest.mark.parametrize('save_as', [False, True])
def test_save_commits_metadata_without_focus_change(tmp_path, monkeypatch, save_as):
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(StudioProject(title='Old title', artist='Old artist'))
    path = tmp_path / 'song.olp'
    monkeypatch.setattr('studio.library_page.configured_library', lambda: None)
    monkeypatch.setattr('studio.app.QFileDialog.getSaveFileName', lambda *args: (str(path), ''))
    if not save_as:
        window.path = path
    window.artist_edit.setText('Danny Vera')
    window.title_edit.setText('Rollercoaster')
    try:
        if save_as:
            window.save_as()
        else:
            assert window.save()
        saved = load_project(path)
        assert saved.artist == window.artist_edit.text() == 'Danny Vera'
        assert saved.title == window.title_edit.text() == 'Rollercoaster'
        assert not window.dirty
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
