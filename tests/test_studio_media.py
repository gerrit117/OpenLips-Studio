from pathlib import Path
import sys

import pytest
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtWidgets import QApplication

from studio.model import demo_project, save_project, load_project
from studio import media


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_cover_and_project_roundtrip(tmp_path, app):
    project = demo_project()
    cover = media.write_cover(project, tmp_path / 'cover.jpg')
    reader = QImageReader(str(cover))
    assert bytes(reader.format()) == b'jpeg'
    assert reader.size().width() == reader.size().height() == 256
    with pytest.raises(FileExistsError):
        media.write_cover(project, cover)
    project.cover_path = str(cover)
    save_project(project, tmp_path / 'song.olp')
    assert load_project(tmp_path / 'song.olp') == project


def test_cover_source_preserved_and_invalid_rejected(tmp_path, app):
    source = QImage(80, 40, QImage.Format.Format_RGB32)
    source.fill(0xffaabbcc)
    path = tmp_path / 'source.png'
    assert source.save(str(path))
    original = path.read_bytes()
    project = demo_project()
    project.cover_path = str(path)
    media.write_cover(project, tmp_path / 'out.jpg')
    assert path.read_bytes() == original
    project.cover_path = str(tmp_path / 'absent.png')
    with pytest.raises(ValueError, match='decoded'):
        media.cover_image(project)


def test_video_uses_video_audio_not_separate_reference(tmp_path, monkeypatch, app):
    project = demo_project()
    project.audio_path = str(tmp_path / 'other.wav')
    project.video_path = str(tmp_path / 'input.mp4')
    Path(project.video_path).write_bytes(b'synthetic-input')
    encoder = tmp_path / 'helper.exe'
    encoder.touch()
    calls = []
    monkeypatch.setattr(sys, 'platform', 'win32')
    def fake_run(args, log):
        calls.append(args)
        Path(args[2]).write_bytes(b'encoded')
    monkeypatch.setattr(media, 'run_encoder', fake_run)
    monkeypatch.setattr(media, 'validate_og_media', lambda path, video: {'streams': [], 'file_size': 7})
    monkeypatch.setattr(media, 'normalize', lambda source, dest: Path(dest).write_bytes(b'normalized'))
    directory = media.prepare_media(project, tmp_path / 'output', 'video', encoder)
    assert Path(calls[0][1]) == Path(project.video_path)
    assert calls[0][-1] == '--audio-only'
    assert Path(calls[1][1]) == Path(project.video_path)
    assert (directory / 'cover.jpg').exists()
    assert Path(project.video_path).read_bytes() == b'synthetic-input'
    with pytest.raises(FileExistsError):
        media.prepare_media(project, directory, 'video', encoder)


def test_failed_encoding_never_publishes_partial_folder(tmp_path, monkeypatch, app):
    project = demo_project()
    project.audio_path = str(tmp_path / 'input.wav')
    Path(project.audio_path).touch()
    encoder = tmp_path / 'helper.exe'
    encoder.touch()
    monkeypatch.setattr(sys, 'platform', 'win32')
    def fail(*args):
        raise ValueError('synthetic failure')
    monkeypatch.setattr(media, 'run_encoder', fail)
    with pytest.raises(ValueError, match='synthetic failure'):
        media.prepare_media(project, tmp_path / 'output', 'audio', encoder)
    assert not (tmp_path / 'output').exists()


def test_video_cap_and_codec_validation(monkeypatch):
    data = {'streams': [dict(kind='audio', codec_tag=0x162, rate=48000, channels=2, bits=16),
                        dict(kind='video', fourcc='WVC1', bitmap_bit_count=24, width=768, height=432)]}
    monkeypatch.setattr(media, 'inspect', lambda path: data)
    media.validate_og_media('unused', True)
    data['streams'][1]['height'] = 1080
    with pytest.raises(ValueError, match='1280x720'):
        media.validate_og_media('unused', True)
    data['streams'].pop()
    media.validate_og_media('unused', False)
    data['streams'][0]['codec_tag'] = 0x161
    with pytest.raises(ValueError, match='WMA Pro'):
        media.validate_og_media('unused', False)


def test_shift_updates_note_and_page_times_and_undo(monkeypatch, app):
    from studio.app import StudioWindow, QInputDialog
    window = StudioWindow()
    window.project.notes[0].page_break_time = 2
    original = window.project.notes[0].time
    monkeypatch.setattr(QInputDialog, 'getDouble', lambda *args: (1.5, True))
    window.shift_all_notes()
    assert window.project.notes[0].time == original + 1.5
    assert window.project.notes[0].page_break_time == 3.5
    window.undo()
    assert window.project.notes[0].time == original
    window.dirty = False
    window.close()
