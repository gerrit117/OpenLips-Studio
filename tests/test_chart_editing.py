import copy

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from studio.keys import key_info, key_pitches
from studio.lyric_timing import delete_notes, split_note, timed_draft
from studio.model import EditorNote, StudioProject, assign_lyrics, incomplete_notes
from studio.timeline import Timeline
from studio.timing_dialog import TimingDialog


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr('studio.tone_preview.TonePreview.play', lambda *args: None)
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('value,root,minor', [('G# maj', 8, False), ('Ab', 8, False),
    ('F#m', 6, True), ('Bb minor', 10, True), ('H Dur', 11, False), ('D moll', 2, True)])
def test_key_spellings(value, root, minor):
    info = key_info(value)
    assert (info['root'], info['minor']) == (root, minor)
    assert len(key_pitches(value)) == 7


def test_key_guides_do_not_confuse_scale_with_vocal_range():
    assert key_pitches('G# maj') == {8, 10, 0, 1, 3, 5, 7}
    assert key_pitches('Ab') == key_pitches('G#')
    assert key_pitches('Am') == {9, 11, 0, 2, 4, 5, 7}
    assert not key_pitches('') and key_info('not a key') is None


def test_timing_undo_seeks_to_removed_stamp_and_keeps_recording(app, monkeypatch):
    dialog = TimingDialog(StudioProject(draft_lyrics='hello world'))
    monkeypatch.setattr(dialog, 'tick', lambda: None)
    dialog.record.setChecked(True)
    dialog.timer.stop()
    for seconds in (1., 2.):
        dialog.position = seconds
        dialog.tap()
    dialog.position = 2.7
    dialog.undo()
    assert dialog.position == 2 and len(dialog.notes) == 1
    assert dialog.playing and dialog.record.isChecked()
    dialog.redo()
    assert dialog.position == 2 and len(dialog.notes) == 2
    dialog.reject()


def test_selected_word_and_time_correction_seek_with_offset(app):
    dialog = TimingDialog(StudioProject(reference_offset=.5))
    dialog.notes = timed_draft(StudioProject(), [1, 2], 'hello world', end=3).notes
    dialog.render()
    dialog.table.setCurrentCell(1, 0)
    assert dialog.position == 2
    dialog.table.item(1, 0).setText('2,250')
    assert dialog.notes[1].time == 2.25 and dialog.position == 2.25
    assert dialog.notes[0].length == 1.25 and dialog.notes[1].length == .75
    dialog.undo()
    assert dialog.notes[1].time == 2 and dialog.position == 2
    assert dialog.notes[0].length == dialog.notes[1].length == 1
    dialog.redo()
    assert dialog.notes[1].time == 2.25 and dialog.position == 2.25
    dialog.play_selected()
    assert dialog.playing and dialog.position == 2.25
    dialog.reject()


def test_invalid_manual_time_does_not_replace_timing(app):
    dialog = TimingDialog(StudioProject())
    dialog.notes = timed_draft(StudioProject(), [1, 2], 'hello world', end=3).notes
    dialog.render()
    before = copy.deepcopy(dialog.notes)
    dialog.table.item(1, 0).setText('.5')
    assert dialog.notes == before and not dialog.history
    dialog.reject()


@pytest.mark.parametrize('edge,delta,expected', [('left', .5, (1.5, 1.5)),
    ('left', -5, (.5, 2.5)), ('left', 10, (2.999, .001)),
    ('right', -.5, (1, 1.5)), ('right', 10, (1, 3))])
def test_resize_ends_keep_other_end_and_respect_neighbors(app, edge, delta, expected):
    timeline = Timeline()
    n = EditorNote(1, 2, 60, 'hello', pitch_assigned=False)
    project = StudioProject(notes=[EditorNote(0, .5, 62), n, EditorNote(4, 1, 62)])
    timeline.set_project(project)
    timeline.snap = False
    assert timeline.resized_values(n, 1, 2, delta, edge) == pytest.approx(expected)
    assert (n.time, n.length) == (1, 2)


def test_edge_drag_cursor_resize_undo_and_delete(app):
    from studio.app import StudioWindow
    window = StudioWindow()
    n = EditorNote(1, 2, 60, 'hello', pitch_assigned=False)
    window.replace_project(StudioProject(notes=[n]))
    window.show()
    app.processEvents()
    timeline = window.timeline
    timeline.snap = False
    rect = timeline.geometry_for(n)
    left = QPoint(round(rect.left()), round(rect.center().y()))
    QTest.mouseMove(timeline, left)
    assert QWidget.cursor(timeline).shape() == Qt.CursorShape.SizeHorCursor
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=left)
    QTest.mouseMove(timeline, left + QPoint(50, 0))
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=left + QPoint(50, 0))
    assert (n.time, n.length) == pytest.approx((1.5, 1.5))
    assert not n.pitch_assigned and len(window.history) == 1
    window.undo()
    assert (window.project.notes[0].time, window.project.notes[0].length) == (1, 2)
    timeline.selected_id = window.project.notes[0].id
    timeline.selected_ids = {timeline.selected_id}
    QTest.keyClick(timeline, Qt.Key.Key_Delete)
    assert not window.project.notes
    window.undo()
    assert len(window.project.notes) == 1
    window.dirty = False
    window.close()


def test_melisma_uses_one_word_keeps_page_end_and_can_be_removed():
    n = EditorNote(1, 2, 60, 'hello', True, True, 3)
    p = StudioProject(notes=[n, EditorNote(4, 1, 62, 'world')])
    right = split_note(p, n.id, 2)
    right.pitch = 64
    assert not n.end_word and right.text == '~' and right.end_word
    delete_notes(p, {n.id})
    assert right.text == 'hello' and right.line_break_after and right.page_break_time == 3
    delete_notes(p, {right.id})
    assert [n.text for n in p.notes] == ['world']


def test_melisma_context_command_and_scale_picker_are_undoable(app):
    from studio.app import StudioWindow
    window = StudioWindow()
    note = EditorNote(1, 2, 60, 'hello', pitch_assigned=False)
    window.replace_project(StudioProject(notes=[note]))
    window.select_note(note.id)
    window.key_combo.setCurrentIndex(window.key_combo.findData('G#'))
    assert window.project.key_signature == 'G#'
    assert window.pitch_choices.isEnabled()
    assert all(window.pitch_choices.itemData(i) % 12 in key_pitches('G#')
               for i in range(window.pitch_choices.count()))
    window.choose_scale_pitch(window.pitch_choices.findData(60))
    assert window.project.notes[0].pitch_assigned
    window.timeline.add_melisma(note.id, 2)
    assert window.note().text == '~' and window.word_label.text() == 'hello'
    window.pitch_edit.setValue(63)
    window.edit_note()
    assert [n.pitch for n in window.project.ordered()] == [60, 63]
    window.undo()
    window.undo()
    assert len(window.project.notes) == 1 and window.project.notes[0].text == 'hello'
    window.undo()
    assert not window.project.notes[0].pitch_assigned
    window.undo()
    assert window.project.key_signature == ''
    window.dirty = False
    window.close()


def test_partial_text_anchor_preserves_prefix_music_and_manual_pages():
    p = StudioProject(page_layout_mode='manual', notes=[
        EditorNote(1, 1, 60, 'keep', line_break_after=True, page_break_time=2),
        EditorNote(2, 1, 60, 'wrong', False), EditorNote(3, 1, 62, '~', True, True, 4),
        EditorNote(4, 1, 64, 'wrong')])
    before = copy.deepcopy(p)
    text = 'unused hello world'
    assert assign_lyrics(p, text, 1, text_offset=text.index('hello')+2) == (2, 0)
    assert p.notes[0] == before.notes[0]
    assert [n.text for n in p.notes] == ['keep', 'hello', '~', 'world']
    assert [(n.time,n.length,n.pitch,n.line_break_after,n.page_break_time) for n in p.notes] == [
        (n.time,n.length,n.pitch,n.line_break_after,n.page_break_time) for n in before.notes]
    assert not p.notes[1].end_word and p.notes[2].end_word


def test_syllable_anchor_starts_with_whole_selected_syllable():
    p = StudioProject(notes=[EditorNote(i, .5, 60) for i in range(3)])
    text = 'prefix Hel|lo world'
    assert assign_lyrics(p, text, 1, True, text_offset=text.index('lo')) == (2, 0)
    assert [n.text for n in p.notes] == ['', 'lo', 'world']


def test_assign_from_marked_text_handles_qt_unicode_positions_and_undo(app):
    from PySide6.QtGui import QTextCursor
    from studio.app import StudioWindow
    window = StudioWindow()
    text = 'Intro \U0001f600 line\nNew words'
    p = StudioProject(draft_lyrics=text, notes=[EditorNote(i, .5, 60, 'old') for i in range(4)])
    window.replace_project(p)
    window.select_note(p.notes[2].id)
    qt_position = len(text[:text.index('New')].encode('utf-16-le'))//2
    cursor = window.lyrics.textCursor()
    cursor.setPosition(qt_position)
    cursor.setPosition(qt_position+3, QTextCursor.MoveMode.KeepAnchor)
    window.lyrics.setTextCursor(cursor)
    window.assign_button.click()
    assert [n.text for n in window.project.notes] == ['old', 'old', 'New', 'words']
    window.undo()
    assert [n.text for n in window.project.notes] == ['old']*4
    window.dirty = False
    window.close()


def test_incomplete_notes_identify_all_missing_text_and_pitch_by_time():
    first = EditorNote(1, .5, 60, ' ')
    later = EditorNote(5, .5, 60, 'word', pitch_assigned=False)
    p = StudioProject(notes=[later, first, EditorNote(3, .5, 62, '~')])
    assert incomplete_notes(p) == [(1, first, ('missing_text',)), (3, later, ('missing_pitch',))]
    assert incomplete_notes(p, require_text=False) == [(3, later, ('missing_pitch',))]
    assert incomplete_notes(p, require_pitch=False) == [(1, first, ('missing_text',))]


def test_review_jump_finds_note_318_and_export_is_stopped_before_destination(app, monkeypatch):
    from studio.app import StudioWindow
    from studio.chart_review import ChartReviewDialog
    from PySide6.QtWidgets import QFileDialog
    window = StudioWindow()
    p = StudioProject(notes=[EditorNote(i, .5, 60, 'word') for i in range(320)])
    p.notes[317].text = ''
    p.notes[319].text = '  '
    window.replace_project(p)
    window.timeline.follow = False
    def choose(dialog):
        assert dialog.table.topLevelItemCount() == 2
        assert dialog.table.topLevelItem(0).text(1) == '318'
        assert dialog.table.topLevelItem(0).text(2) == '05:17.000'
        dialog.accept()
        return 1
    monkeypatch.setattr(ChartReviewDialog, 'exec', choose)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_: pytest.fail('Destination before validation'))
    window.export_json()
    assert window.note().id == p.notes[317].id
    assert window.position == 317 and window.timeline.origin < 317
    assert window.screens.currentIndex() == 1
    window.dirty = False
    window.close()


def test_song_pack_review_can_open_other_project_without_losing_changes(app, monkeypatch):
    from studio.app import StudioWindow
    window = StudioWindow()
    window.replace_project(StudioProject(notes=[EditorNote(1, .5, 60, 'keep')]))
    window.dirty = True
    other = StudioProject(title='Other', notes=[EditorNote(10, .5, 60)])
    before = copy.deepcopy(window.project)
    monkeypatch.setattr(window, 'confirm_discard', lambda: False)
    assert not window.show_chart_note(other, other.notes[0].id)
    assert window.project == before
    monkeypatch.setattr(window, 'confirm_discard', lambda: True)
    assert window.show_chart_note(other, other.notes[0].id)
    assert window.note().id == other.notes[0].id and window.position == 10
    window.dirty = False
    window.close()
