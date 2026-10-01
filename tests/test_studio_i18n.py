import copy

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from studio.i18n import language, set_language, tr, CATALOG


@pytest.fixture(autouse=True)
def restore_language():
    previous = language()
    yield
    set_language(previous, persist=False)


def test_catalog_languages_and_placeholders():
    from string import Formatter
    for english, german in CATALOG.values():
        assert english and german
        fields = lambda value: {key for _, key, _, _ in Formatter().parse(value) if key is not None}
        assert fields(english) == fields(german)
    set_language('en', persist=False)
    assert tr('Projekt oeffnen') == 'Open project'
    set_language('de', persist=False)
    assert tr('Projekt oeffnen') == 'Projekt öffnen'
    with pytest.raises(ValueError):
        set_language('fr', persist=False)


def test_language_switch_preserves_project_and_history(monkeypatch):
    from studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('studio.app.set_language', lambda value: set_language(value, persist=False))
    set_language('de', persist=False)
    window = StudioWindow()
    before = copy.deepcopy(window.project)
    window.snapshot()
    window.change_language('en')
    assert window.menuBar().actions()[0].text() == 'File'
    assert window.project == before
    assert len(window.history) == 1
    window.change_language('de')
    assert window.menuBar().actions()[0].text() == 'Datei'
    assert window.project == before
    window.dirty = False
    window.close()


def test_media_paths_not_required_and_macos_limit_explained(monkeypatch):
    from studio.media_dialog import MediaDialog
    from studio.model import demo_project
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('studio.media_dialog.sys.platform', 'darwin')
    set_language('en', persist=False)
    dialog = MediaDialog(demo_project())
    assert set(dialog.fields) == {'output'}
    assert 'requires Windows' in dialog.log.toPlainText()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
    dialog.close()
