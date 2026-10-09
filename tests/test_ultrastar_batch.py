from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import pytest

from studio.ultrastar_batch import discover_charts, load_chart
from studio.ultrastar_batch_dialog import UltraStarBatchDialog


def chart(folder, name='Test'):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + '.txt')
    path.write_text('#TITLE:Test\n#ARTIST:OpenLips\n#BPM:120\n#GAP:0\n: 0 4 0 Test\nE\n', encoding='utf-8')
    return path


def test_recursive_discovery_and_media_selection(tmp_path):
    path = chart(tmp_path / 'Artist/Song')
    for name in ('Test.mp4', 'Test.m4a', 'Test [CO].jpg', 'Test [BG].jpg'):
        (path.parent / name).write_bytes(b'synthetic')
    assert discover_charts(tmp_path) == [path]
    project = load_chart(path)
    assert Path(project.audio_path).name == 'Test.m4a'
    assert Path(project.video_path).name == 'Test.mp4'
    assert Path(project.cover_path).name == 'Test [CO].jpg'
    assert project.notes[0].pitch == 60


def test_ambiguous_media_is_not_guessed(tmp_path):
    path = chart(tmp_path)
    for name in ('First.mp3', 'Second.mp3', 'First.mp4', 'Second.mp4', 'First.jpg', 'Second.jpg'):
        (tmp_path / name).write_bytes(b'synthetic')
    project = load_chart(path)
    assert not project.audio_path
    assert not project.video_path
    assert not project.cover_path


def test_declared_media_wins_over_filename_fallback(tmp_path):
    path = chart(tmp_path)
    path.write_text(path.read_text().replace('#GAP:0', '#GAP:0\n#MP3:Chosen.mp3\n#COVER:Chosen.jpg'), encoding='utf-8')
    for name in ('Chosen.mp3', 'Test.mp3', 'Chosen.jpg', 'Test [CO].jpg'):
        (tmp_path / name).write_bytes(b'synthetic')
    project = load_chart(path)
    assert Path(project.audio_path).name == 'Chosen.mp3'
    assert Path(project.cover_path).name == 'Chosen.jpg'


def test_invalid_txt_does_not_modify_sources(tmp_path):
    path = tmp_path / 'invalid.txt'
    path.write_bytes(b'not an UltraStar chart')
    with pytest.raises(ValueError):
        load_chart(path)
    assert path.read_bytes() == b'not an UltraStar chart'


def test_batch_selection_and_pack_limit(tmp_path):
    app = QApplication.instance() or QApplication([])
    project = load_chart(chart(tmp_path))
    dialog = UltraStarBatchDialog()
    dialog.receive([(str(index), project) for index in range(17)], [])
    dialog.update_buttons()
    assert len(dialog.selected()) == 17
    assert dialog.open_button.isEnabled()
    assert not dialog.export_button.isEnabled()
    dialog.table.item(16, 0).setCheckState(Qt.CheckState.Unchecked)
    assert len(dialog.selected()) == 16
    assert dialog.export_button.isEnabled()
    dialog.reject()


def test_batch_project_destination_is_selected_and_cancel_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr('studio.library_page.configured_library', lambda: None)
    from studio.ultrastar_batch_dialog import QFileDialog
    app = QApplication.instance() or QApplication([])
    project = load_chart(chart(tmp_path / 'source'))
    dialog = UltraStarBatchDialog()
    dialog.receive([('source', project)], [])
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **kw: '')
    dialog.finish_import(False)
    assert dialog.batch_result is None
    assert not list(tmp_path.glob('OpenLips-*'))
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **kw: str(tmp_path))
    dialog.finish_import(False)
    saved = list(tmp_path.glob('OpenLips-*/*.olp'))
    assert len(saved) == 1
    assert saved[0].name == '0001.olp'
    assert dialog.batch_result[2] is False


def test_batch_uses_configured_library_without_a_folder_prompt(tmp_path, monkeypatch):
    root = tmp_path / 'chosen-library'
    monkeypatch.setattr('studio.library_page.configured_library', lambda: root)
    from studio.ultrastar_batch_dialog import QFileDialog
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **kw: pytest.fail('Fixed library prompted'))
    app = QApplication.instance() or QApplication([])
    dialog = UltraStarBatchDialog()
    project = load_chart(chart(tmp_path / 'source'))
    dialog.receive([('source', project)], [])
    dialog.finish_import(False)
    assert len(list((root / 'workspace').glob('*.olp'))) == 1
    assert dialog.batch_result[2] is False
