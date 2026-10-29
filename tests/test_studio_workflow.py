"""Media-first navigation and lyric editing use only synthetic project data."""
import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from studio.model import StudioProject, EditorNote, save_project, load_project
from studio.lyric_mapping import assign_word, lyric_links, tokens, note_words
from studio.lyric_document import word_payload, valid_payload, python_position, qt_position
from studio.song_analysis import key_from_chroma, MAJOR_PROFILE, MINOR_PROFILE


def sample():
    return StudioProject(title='Synthetic', draft_lyrics='one two one', notes=[
        EditorNote(1, .5, 60, 'one'), EditorNote(2, .5, 62, 'two'), EditorNote(3, .5, 64, 'one')])


@pytest.fixture
def window(tmp_path, monkeypatch):
    from studio.app import StudioWindow
    from studio.workflow import StudioWorkflow
    app = QApplication.instance() or QApplication([])
    old = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    monkeypatch.setattr(StudioWorkflow, 'analyze', lambda _: None)
    w = StudioWindow()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()
    app.processEvents()
    QSettings.setDefaultFormat(old)


def test_starts_with_source_without_a_project_file(window):
    assert window.workflow.current_step == 0
    assert window.path is None
    assert not window.project.notes and not window.dirty
    assert window.main_toolbar.isHidden()


def test_navigation_does_not_create_or_replace_projects(window):
    project = window.project
    for step in (1, 2, 3, 4, 0):
        window.workflow.go(step)
        assert window.project is project and window.path is None
        assert window.workflow.current_step == step
    assert not window.dirty


def test_expert_controls_are_collapsed_and_reversible(window):
    assert window.note_details.isHidden() and window.reference_controls.isHidden()
    window.expert_toggle.setChecked(True)
    assert not window.note_details.isHidden() and not window.reference_controls.isHidden()
    window.expert_toggle.setChecked(False)
    assert window.note_details.isHidden()


def test_source_kind_switch_exposes_inline_link_and_permission(window):
    flow = window.workflow
    flow.set_source_mode(True)
    assert flow.url_mode.isChecked() and not flow.rights.isHidden()
    flow.set_source_mode(False)
    assert flow.file_mode.isChecked() and flow.rights.isHidden()


def test_new_source_is_not_ignored_when_project_already_has_media(window, monkeypatch):
    window.project.audio_path = 'old.wav'
    flow = window.workflow
    flow.set_source_mode(True)
    flow.source_input.setText('https://www.youtube.com/watch?v=abcdefghijk')
    called = []
    monkeypatch.setattr(flow, 'acquire_source', lambda: called.append(True))
    flow.continue_source()
    assert called == [True]


def test_playback_highlights_playing_word_instead_of_old_selection(window):
    project = sample()
    window.replace_project(project)
    window.lyrics.highlight(project, project.notes[0].id, position=2.1)
    assert window.lyrics.last_highlight[1] == (4, 7)


def test_completed_download_starts_preparation_analysis_after_worker_exit(window, monkeypatch):
    from types import SimpleNamespace
    flow = window.workflow
    window.project.audio_path = 'downloaded.wav'
    flow.current_step = 1
    flow.download = SimpleNamespace(completed=True, busy=False)
    called = []
    monkeypatch.setattr(flow, 'analyze', lambda: called.append(True))
    flow.download_finished()
    assert called == [True]


def test_video_audio_check_can_cancel_without_replacing_project(window, monkeypatch, tmp_path):
    import studio.song_media_check
    media = tmp_path/'silent.mp4'
    media.write_bytes(b'synthetic')
    original = window.project
    monkeypatch.setattr(studio.song_media_check, 'ensure_song_audio', lambda *_: False)
    window.workflow.adopt_media(media)
    assert window.project is original and not window.dirty


def test_video_keeps_companion_audio_selected_during_source_check(window, monkeypatch, tmp_path):
    import studio.song_media_check
    media = tmp_path/'video.mp4'
    media.write_bytes(b'synthetic')
    def checked(project, parent):
        project.audio_path = str(tmp_path/'soundtrack.mp3')
        return True
    monkeypatch.setattr(studio.song_media_check, 'ensure_song_audio', checked)
    window.workflow.adopt_media(media)
    assert window.project.audio_path.endswith('soundtrack.mp3')
    assert window.project.video_path == str(media)
    assert window.workflow.current_step == 1


def test_changing_preparation_tempo_preserves_note_times(window):
    window.replace_project(sample())
    flow = window.workflow
    flow.go(1)
    before = [(n.time, n.length, n.pitch) for n in window.project.notes]
    flow.bpm.setValue(133)
    flow.offset.setValue(.15)
    flow.commit_preparation()
    assert window.project.bpm == 133 and window.project.beat_offset == .15
    assert [(n.time, n.length, n.pitch) for n in window.project.notes] == before
    assert flow.current_step == 1


def test_draft_text_is_shared_between_setup_and_editor(window):
    window.workflow.go(2)
    window.workflow.text_input.setPlainText('hello world')
    assert window.lyrics.toPlainText() == window.project.draft_lyrics == 'hello world'
    assert window.workflow.current_step == 2 and window.dirty
    window.undo()
    assert window.lyrics.toPlainText() == ''


def test_empty_lyric_grid_draft_is_explicitly_unpitched(window):
    window.workflow.go(2)
    window.workflow.text_input.setPlainText('one two three')
    window.workflow.grid_draft()
    assert len(window.project.notes) == 3
    assert all(not n.pitch_assigned for n in window.project.notes)
    assert window.workflow.current_step == 3


def test_lrc_import_in_lyrics_step_does_not_open_nested_review(window):
    from studio.lrc import parse_lrc
    window.workflow.go(2)
    window.accept_lrc(parse_lrc('[00:01.00]first\n[00:03.00]second'))
    assert window.workflow.current_step == 2
    assert len(window.project.notes) == 2
    assert not window.project.notes[0].pitch_assigned
    assert window.lyrics.toPlainText() == 'first\nsecond'


def test_word_click_assigns_only_selected_note_and_can_undo(window):
    project = sample()
    project.notes[1].text = ''
    window.replace_project(project)
    window.select_note(project.notes[1].id)
    window.assign_lyric_word(4, 7)
    assert [n.text for n in window.project.notes] == ['one', 'two', 'one']
    window.undo()
    assert window.project.notes[1].text == ''


def test_repeated_words_keep_their_occurrence_after_swap(tmp_path):
    project = sample()
    before = [(n.time, n.length, n.pitch) for n in project.notes]
    assign_word(project, 8, 11, {project.notes[1].id})
    assert [n.text for n in project.notes] == ['one', 'one', 'two']
    assert lyric_links(project)[project.notes[1].id] == (8, 11)
    assert lyric_links(project)[project.notes[2].id] == (4, 7)
    assert [(n.time, n.length, n.pitch) for n in project.notes] == before
    path = tmp_path/'draft.olp'
    save_project(project, path)
    assert lyric_links(load_project(path)) == lyric_links(project)


def test_empty_notes_are_not_combined_into_one_word():
    project = sample()
    for note in project.notes:
        note.text = ''
    assert len(note_words(project.notes)) == 3
    assign_word(project, 0, 3, {project.notes[1].id})
    assert [n.text for n in project.notes] == ['', 'one', '']


def test_word_can_span_multiple_pitches_without_duplicate_text():
    project = sample()
    assign_word(project, 0, 3, {n.id for n in project.notes[:2]})
    assert [n.text for n in project.notes[:2]] == ['one', '~']
    assert not project.notes[0].end_word and project.notes[1].end_word


def test_word_cannot_cross_page_boundary_or_nonconsecutive_selection():
    project = sample()
    before = copy.deepcopy(project)
    with pytest.raises(ValueError):
        assign_word(project, 0, 3, {project.notes[0].id, project.notes[2].id})
    assert project == before
    project.notes[0].line_break_after = True
    with pytest.raises(ValueError):
        assign_word(project, 0, 3, {project.notes[0].id, project.notes[1].id})


def test_utf16_word_positions_and_stale_drag_validation():
    text = '😀 one two'
    for position in range(len(text)+1):
        assert python_position(text, qt_position(text, position)) == position
    payload = word_payload(text, 2, 5)
    assert valid_payload(payload, text)
    assert not valid_payload(payload, '😀 one changed')
    assert not valid_payload(dict(start=-1, end=2), text)


@pytest.mark.parametrize('minor', [False, True])
@pytest.mark.parametrize('root', range(12))
def test_key_profiles_are_recognized_in_all_transpositions(root, minor):
    import numpy as np
    names = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
    assert key_from_chroma(np.roll(MINOR_PROFILE if minor else MAJOR_PROFILE, root)) == names[root]+('m' if minor else '')


def test_key_detection_declines_silence_or_invalid_chroma():
    assert key_from_chroma([0]*12) == ''
    assert key_from_chroma([float('nan')]*12) == ''
    assert key_from_chroma([1, 2]) == ''
