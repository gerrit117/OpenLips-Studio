import copy
import json
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from studio.model import StudioProject, EditorNote
from studio.note_clipboard import capture, materialize, MIME


@pytest.fixture(autouse=True)
def clipboard_lifetime():
    app = QApplication.instance() or QApplication([])
    yield
    app.clipboard().clear()
    app.processEvents()


def project():
    return StudioProject(notes=[EditorNote(1,.4,60,'oh',False),
        EditorNote(1.4,.6,64,'~',True), EditorNote(3,.5,62,'again')])


def test_copy_preserves_pattern_and_is_independent():
    p = project()
    before = copy.deepcopy(p)
    data, selected = capture(p, {p.notes[1].id, p.notes[2].id})
    assert selected == {n.id for n in p.notes}
    notes = materialize(data, 10)
    assert [n.time for n in notes] == pytest.approx([10,10.4,12])
    assert [n.text for n in notes] == ['oh','~','again']
    assert [n.pitch for n in notes] == [60,64,62]
    assert all(n.id not in selected for n in notes)
    assert p == before
    second = materialize(data,20)
    assert not {n.id for n in notes} & {n.id for n in second}


def test_page_switches_move_and_terminal_target_is_removed():
    p = StudioProject(notes=[EditorNote(4,1,60,'a',line_break_after=True,page_break_time=5.5),
                             EditorNote(6,1,62,'b',line_break_after=True,page_break_time=8)])
    data, _ = capture(p,{n.id for n in p.notes})
    notes = materialize(data,10)
    assert notes[0].page_break_time == 11.5
    assert notes[-1].page_break_time is None


@pytest.mark.parametrize('payload',[b'{}',b'[]',b'not json',b'{"version":1,"notes":[]}',
    b'{"version":1,"notes":[{"time":-2,"length":1,"pitch":60}]}'])
def test_invalid_clipboard_is_rejected(payload):
    with pytest.raises(ValueError):
        materialize(payload,10)


def test_editor_shortcuts_paste_at_cursor_and_undo_without_text_collision():
    from studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(project())
    window.show()
    app.processEvents()
    window.timeline.selected_ids = {n.id for n in window.project.notes}
    window.timeline.choose_paste_mode = lambda notes: ('add', True)
    window.timeline.setFocus()
    QTest.keySequence(window.timeline,QKeySequence(QKeySequence.StandardKey.Copy))
    assert QApplication.clipboard().mimeData().hasFormat(MIME)
    window.seek(window.project.duration)
    QTest.keySequence(window.timeline,QKeySequence(QKeySequence.StandardKey.Paste))
    assert len(window.project.notes) == 6
    assert window.project.notes[3].time == 3.5
    assert len(window.timeline.selected_ids) == 3
    window.undo()
    assert len(window.project.notes) == 3
    window.redo()
    assert len(window.project.notes) == 6
    QApplication.clipboard().setText('Different title')
    window.title_edit.setFocus()
    window.title_edit.selectAll()
    QTest.keySequence(window.title_edit,QKeySequence(QKeySequence.StandardKey.Paste))
    assert window.title_edit.text() == 'Different title'
    assert len(window.project.notes) == 6
    window.dirty = False
    window.close()


def test_guided_review_paste_and_cancel_do_not_change_source():
    from studio.guided_review import GuidedReviewDialog
    app = QApplication.instance() or QApplication([])
    p = project()
    d = GuidedReviewDialog(p)
    d.timeline.selected_ids = {p.notes[0].id}
    d.timeline.copy_notes()
    d.timeline.paste_notes(2, mode='add')
    assert len(d.project.notes) == 5
    assert len(p.notes) == 3
    d.undo()
    assert len(d.project.notes) == 3
    d.reject()
