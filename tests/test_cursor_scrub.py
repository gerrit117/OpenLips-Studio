import copy
import pytest
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from studio.app import StudioWindow
from studio.model import StudioProject, EditorNote


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    w = StudioWindow()
    w.replace_project(StudioProject(notes=[EditorNote(1,.5,60,'one'), EditorNote(8,.5,62,'two')]))
    w.show()
    app.processEvents()
    yield w
    w.dirty = False
    w.close()
    app.processEvents()


def move(timeline, point):
    QApplication.sendEvent(timeline, QMouseEvent(QEvent.Type.MouseMove, QPointF(point),
        QPointF(timeline.mapToGlobal(point)), Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


@pytest.mark.parametrize('playing', [False, True])
def test_cursor_drag_is_continuous_audible_and_restores_transport(window, monkeypatch, playing):
    t = window.timeline
    window.seek(1.13)
    t.scale = 100
    t.selected_ids = {window.project.notes[0].id}
    before = copy.deepcopy(window.project)
    plays, pauses = [], []
    window.project.audio_path = 'test.wav'
    before.audio_path = 'test.wav'
    monkeypatch.setattr(window.player,'play', lambda: plays.append(window.position))
    monkeypatch.setattr(window.player,'pause', lambda: pauses.append(window.position))
    if playing:
        window.toggle_play()
    origin = t.origin
    x = round(62+(window.position-origin)*t.scale)
    move(t,QPoint(x,27))
    assert QWidget.cursor(t).shape() == Qt.CursorShape.SizeHorCursor
    QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=QPoint(x,27))
    assert t.cursor_drag and not window.playing
    move(t,QPoint(x+37,27))
    expected = origin+(x+37-62)/t.scale
    assert window.position == pytest.approx(expected)
    assert t.origin == origin
    assert plays[-1] == pytest.approx(expected)
    QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=QPoint(x+37,27))
    assert not t.cursor_drag and window.playing == playing
    assert t.selected_ids == {window.project.notes[0].id}
    assert window.project == before
    assert pauses


def test_guided_review_cursor_preview_preserves_paused_state(monkeypatch):
    from studio.guided_review import GuidedReviewDialog
    app = QApplication.instance() or QApplication([])
    p = StudioProject(notes=[EditorNote(1,1,60,'one'), EditorNote(3,1,62,'two')])
    d = GuidedReviewDialog(p)
    heard = []
    monkeypatch.setattr(d.tones,'play',lambda *args: heard.append(args))
    d.mode.setCurrentIndex(d.mode.findData('notes'))
    d.begin_scrub()
    d.scrub_to(1.234)
    assert d.position == pytest.approx(1.234)
    assert heard[-1][0] == 60
    d.end_scrub()
    assert not d.playing
    d.reject()
    app.processEvents()
