from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from studio.app import StudioWindow
from studio.model import demo_project


def test_drag_and_resize_and_follow():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(demo_project())
    window.show()
    app.processEvents()
    timeline = window.timeline
    timeline.snap = False
    note = window.project.notes[0]
    rect = timeline.geometry_for(note)
    start = rect.center().toPoint()
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(timeline, start + QPoint(40, 0))
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=start + QPoint(40, 0))
    assert abs(note.time - 1.4) < .001
    window.undo()
    note = window.project.notes[0]
    assert note.time == 1
    rect = timeline.geometry_for(note)
    edge = QPoint(round(rect.right()), round(rect.center().y()))
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=edge)
    QTest.mouseMove(timeline, edge + QPoint(20, 0))
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=edge + QPoint(20, 0))
    assert abs(note.length - .85) < .001
    window.dirty = False
    window.close()


def test_inline_lyric_field_commits_with_undo():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(demo_project())
    window.show()
    app.processEvents()
    note = window.project.notes[0]
    field = window.timeline.lyric_fields[note.id]
    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, 'Hello')
    assert note.text == 'Hello'
    window.undo()
    assert window.project.notes[0].text == 'Sing'
    window.dirty = False
    window.close()
