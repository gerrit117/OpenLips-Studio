"""Early soundtrack selection uses synthetic paths, never user media."""
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from studio.model import StudioProject
from studio.song_media_check import ensure_song_audio


@pytest.fixture
def media_ui(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('studio.song_media_check.bundled_tool', lambda name: 'probe')
    question = Mock(return_value=QMessageBox.StandardButton.Yes)
    picker = Mock(return_value=('soundtrack.mp3', ''))
    warning = Mock()
    monkeypatch.setattr('studio.song_media_check.QMessageBox.question', question)
    monkeypatch.setattr('studio.song_media_check.QFileDialog.getOpenFileName', picker)
    monkeypatch.setattr('studio.song_media_check.QMessageBox.warning', warning)
    monkeypatch.setattr('studio.song_media_check.media_streams', lambda path, probe: {'audio'})
    def missing(project, probe):
        raise ValueError('No soundtrack')
    monkeypatch.setattr('studio.song_media_check.resolve_audio_source', missing)
    return app, question, picker, warning


def test_silent_video_prompts_and_attaches_audio(media_ui):
    _, question, picker, warning = media_ui
    project = StudioProject(video_path='silent.mp4')
    assert ensure_song_audio(project)
    assert project.audio_path == 'soundtrack.mp3'
    question.assert_called_once()
    picker.assert_called_once()
    warning.assert_not_called()


def test_cancel_audio_selection_keeps_wizard_open(media_ui):
    media_ui[2].return_value = ('', '')
    project = StudioProject(video_path='silent.mp4')
    assert not ensure_song_audio(project)
    assert project.audio_path == ''


def test_audio_can_be_added_later(media_ui):
    media_ui[1].return_value = QMessageBox.StandardButton.No
    project = StudioProject(video_path='silent.mp4')
    assert ensure_song_audio(project)
    assert project.audio_path == ''
    media_ui[2].assert_not_called()


def test_selected_silent_file_is_rejected(media_ui, monkeypatch):
    monkeypatch.setattr('studio.song_media_check.media_streams', lambda path, probe: {'video'})
    project = StudioProject(video_path='silent.mp4')
    assert not ensure_song_audio(project)
    assert project.audio_path == ''
    media_ui[3].assert_called_once()


@pytest.mark.parametrize('source', ['movie.mp4', 'movie.m4a'])
def test_existing_soundtrack_needs_no_prompt(media_ui, monkeypatch, source):
    monkeypatch.setattr('studio.song_media_check.resolve_audio_source', lambda project, probe: source)
    project = StudioProject(video_path='movie.mp4')
    assert ensure_song_audio(project)
    assert project.audio_path == ('' if source.endswith('.mp4') else source)
    media_ui[1].assert_not_called()


def test_audio_only_project_needs_no_video_check(media_ui):
    assert ensure_song_audio(StudioProject(audio_path='song.mp3'))
    media_ui[1].assert_not_called()
