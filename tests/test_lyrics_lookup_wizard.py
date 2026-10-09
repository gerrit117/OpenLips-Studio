"""Wizard lyric acquisition does not need an existing song or network."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from studio.lyrics_lookup_dialog import LyricsLookupDialog
from studio.song_wizard import SongWizard


def application():
    return QApplication.instance() or QApplication([])


def test_wizard_offers_local_or_online_lrc_before_project(tmp_path, monkeypatch):
    app = application()
    path = tmp_path / 'timed.lrc'
    path.write_text('[ti:Example]\n[00:01.00]Hello\n[00:02.00]World', encoding='utf-8')
    wizard = SongWizard()
    wizard.restart()
    wizard.choices.setCurrentRow(wizard.modes.index('lrc'))
    assert not wizard.lrc_sources.isHidden() and wizard.project is None
    monkeypatch.setattr('studio.song_wizard.QFileDialog.getOpenFileName', lambda *a: (str(path), ''))
    wizard.choose_lrc_file()
    assert wizard.currentId() == 1
    assert wizard.rows['lrc'][0].text() == str(path)
    assert wizard.validateCurrentPage()
    assert wizard.project.title == 'Example'
    assert wizard.project.notes and all(not note.pitch_assigned for note in wizard.project.notes)
    wizard.close()
    app.processEvents()


def test_wizard_online_result_opens_files_step(tmp_path, monkeypatch):
    app = application()
    path = tmp_path / 'downloaded.lrc'
    class Lookup:
        def __init__(self, *_):
            self.lrc_path = path
        def exec(self):
            return True
    monkeypatch.setattr('studio.lyrics_lookup_dialog.LyricsLookupDialog', Lookup)
    wizard = SongWizard()
    wizard.restart()
    wizard.choices.setCurrentRow(wizard.modes.index('midi-lrc'))
    wizard.find_lrc_file()
    assert wizard.currentId() == 1 and wizard.rows['lrc'][0].text() == str(path)
    assert wizard.project is None
    wizard.close()
    app.processEvents()


def test_timed_lookup_preview_and_local_cache(tmp_path, monkeypatch):
    app = application()
    monkeypatch.setattr(QStandardPaths, 'writableLocation', lambda _: str(tmp_path))
    dialog = LyricsLookupDialog(title='Example', artist='Test')
    dialog.show_results([
        dict(trackName='Untimed', plainLyrics='No timestamps'),
        dict(trackName='Example', artistName='Test', duration=4,
             syncedLyrics='[00:01.00]Hello\n[00:02.00]World')])
    assert dialog.results.topLevelItemCount() == 1
    assert 'Hello' in dialog.preview.toPlainText()
    dialog.use_result()
    assert dialog.lrc_path.is_file()
    assert dialog.document.metadata == dict(ti='Example', ar='Test')
    assert dialog.document.cues[0].time == 1
    dialog.close()
    app.processEvents()
