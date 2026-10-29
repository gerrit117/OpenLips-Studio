from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
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
    window.expert_toggle.setChecked(True)
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


def test_follow_survives_cursor_scroll_and_pause():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(demo_project())
    window.show()
    app.processEvents()
    window.seek(12)
    assert window.timeline.origin > 0
    assert window.follow_box.isChecked() and window.timeline.follow
    window.toggle_play()
    window.toggle_play()
    window.toggle_play()
    assert window.follow_box.isChecked() and window.timeline.follow
    window.toggle_play()
    window.scroll_to(1000)
    assert window.follow_box.isChecked() and window.timeline.follow
    event = QWheelEvent(QPointF(100,100), QPointF(100,100), QPoint(), QPoint(0,-120),
                       Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                       Qt.ScrollPhase.NoScrollPhase, False)
    window.timeline.wheelEvent(event)
    assert window.follow_box.isChecked() and window.timeline.follow
    window.toggle_play()
    assert window.timeline.follow
    window.toggle_play()
    window.follow_box.setChecked(False)
    window.toggle_play()
    assert not window.timeline.follow
    window.stop()
    window.dirty = False
    window.close()


def test_playback_keys_do_not_steal_spaces_from_text_or_page_recording():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(demo_project())
    window.show()
    app.processEvents()
    window.timeline.setFocus()
    QTest.keyClick(window.timeline, Qt.Key.Key_Space)
    assert window.playing
    QTest.keyClick(window.timeline, Qt.Key.Key_Space)
    assert not window.playing
    window.title_edit.setFocus()
    QTest.keyClick(window.title_edit, Qt.Key.Key_Space)
    assert not window.playing
    QTest.keyClick(window.title_edit, Qt.Key.Key_F5)
    assert window.playing
    QTest.keyClick(window.title_edit, Qt.Key.Key_F5)
    assert not window.playing
    window.record_pages_action.trigger()
    window.timeline.setFocus()
    QTest.keyClick(window.timeline, Qt.Key.Key_F5)
    assert window.playing and window.record_pages_action.isChecked()
    QTest.keyClick(window.timeline, Qt.Key.Key_F5)
    assert not window.playing and window.record_pages_action.isChecked()
    window.stop()
    window.dirty = False
    window.close()
