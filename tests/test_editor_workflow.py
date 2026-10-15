import copy
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from studio.app import StudioWindow
from studio.model import EditorNote, StudioProject
from studio.note_editing import conflicts, duplicate_ids, lyric_shift_plan, passage_destination


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    w = StudioWindow()
    w.replace_project(StudioProject(notes=[EditorNote(1,.2,60,'one'),
        EditorNote(2,.2,62,'two'), EditorNote(3,.2,64,'three')]))
    w.show()
    app.processEvents()
    yield w
    w.dirty = False
    w.close()
    app.clipboard().clear()
    app.processEvents()


def test_select_cell_does_not_seek_and_creates_smallest_note(window):
    from studio.beat_grid import step
    t = window.timeline
    position = window.position
    point = QPoint(90,60)
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,pos=point)
    assert window.position == position
    assert t.target is not None
    expected = t.target
    QTest.mouseDClick(t,Qt.MouseButton.LeftButton,pos=point)
    n = window.note()
    assert (n.time,n.pitch) == (expected[0],expected[2])
    assert n.length == pytest.approx(step(window.project))
    assert window.position == position
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=QPoint(150,60))
    assert window.position != position


def test_ctrl_endpoint_selects_whole_range(window):
    t = window.timeline
    notes = window.project.ordered()
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,pos=t.geometry_for(notes[0]).center().toPoint())
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,
                    pos=t.geometry_for(notes[-1]).center().toPoint())
    assert t.selected_ids == {n.id for n in notes}


def test_paste_cancel_replace_and_undo(window):
    t = window.timeline
    t.selected_ids = {window.project.notes[0].id}
    t.copy_notes()
    before = copy.deepcopy(window.project)
    t.choose_paste_mode = lambda notes: None
    t.paste_notes(2)
    assert window.project == before
    t.paste_notes(2,mode='replace')
    assert len(window.project.notes) == 3
    assert window.project.ordered()[1].text == 'one'
    window.undo()
    assert window.project.notes == before.notes


def test_lyrics_swap_without_changing_notes(window):
    p = window.project
    timing = [(n.time,n.length,n.pitch) for n in p.notes]
    plan = lyric_shift_plan(p,p.notes[0].id,1)
    for note,text,end_word in plan:
        note.text,note.end_word = text,end_word
    assert [n.text for n in p.notes] == ['two','one','three']
    assert [(n.time,n.length,n.pitch) for n in p.notes] == timing
    with pytest.raises(ValueError,match='no_room'):
        lyric_shift_plan(p,p.notes[0].id,1,suffix=True)
    p.notes[-1].text = ''
    for note,text,end_word in lyric_shift_plan(p,p.notes[0].id,1,suffix=True):
        note.text,note.end_word = text,end_word
    assert [n.text for n in p.notes] == ['','two','one']


@pytest.mark.parametrize('include_text', [False, True])
def test_paste_content_choice_preserves_timing_and_source(window, include_text):
    t = window.timeline
    source = copy.deepcopy(window.project.notes)
    t.selected_ids = {n.id for n in source}
    t.copy_notes()
    t.choose_paste_mode = lambda notes: ('add', include_text)
    t.paste_notes(5)
    inserted = window.project.notes[3:]
    assert [n.time for n in inserted] == [5,6,7]
    assert [n.length for n in inserted] == [n.length for n in source]
    assert [n.pitch for n in inserted] == [n.pitch for n in source]
    assert [n.text for n in inserted] == ([n.text for n in source] if include_text else ['','',''])
    assert window.project.notes[:3] == source
    window.undo()
    assert window.project.notes == source


def test_conflicts_and_safe_duplicate_removal():
    a,b,c = EditorNote(1,1,60,''),EditorNote(1,1,60,'hello'),EditorNote(1,1,60,'different')
    d = EditorNote(2,1,60,'next')
    p = StudioProject(notes=[a,b,c,d])
    assert set(conflicts(p)) == {a.id,b.id,c.id}
    assert duplicate_ids(p) == {a.id}
    before = copy.deepcopy(p)
    inserted = [EditorNote(1,.2,65,'new')]
    assert len(passage_destination(p,inserted,'add')) == 5
    assert len(passage_destination(p,inserted,'replace')) == 2
    assert p == before


def test_paste_dialog_exposes_text_choice(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    def choose(box):
        assert box.checkBox().isChecked()
        box.checkBox().setChecked(False)
        box.buttons()[0].click()
        return 0
    monkeypatch.setattr(QMessageBox, 'exec', choose)
    assert window.timeline.choose_paste_mode(window.project.notes) == ('replace', False)
