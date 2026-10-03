import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from studio.model import StudioProject, EditorNote, merge_selection
from studio.app import StudioWindow


def chart():
    return StudioProject(notes=[EditorNote(1, .2, 60, 'Roller', False),
        EditorNote(1.25, .15, 60, '~', False), EditorNote(1.45, .5, 60, 'coaster', True)])


def test_reference_volume_independent_of_note_tones():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    tone_volume = window.tones.volume
    window.reference_volume.setValue(20)
    assert window.audio.volume() == pytest.approx(.2)
    assert window.video_audio.volume() == pytest.approx(.2)
    assert window.tones.volume == tone_volume
    window.reference_mute.setChecked(True)
    assert window.audio.isMuted() and window.video_audio.isMuted()
    window.configure_media()
    assert window.audio.isMuted() and window.video_audio.isMuted()
    window.reference_mute.setChecked(False)
    assert not window.video_audio.isMuted()
    window.project.audio_path = 'separate.mp3'
    window.configure_media()
    assert window.video_audio.isMuted() and not window.audio.isMuted()
    window.reference_volume.setValue(0)
    assert window.audio.volume() == 0
    assert window.tones.volume == tone_volume
    window.close()


def test_merge_same_pitch_and_fragments():
    project = chart()
    result = merge_selection(project, [n.id for n in project.notes])
    assert len(project.notes) == 1
    assert result.time == 1 and result.length == pytest.approx(.95)
    assert result.pitch == 60 and result.text == 'Rollercoaster'
    assert result.end_word


@pytest.mark.parametrize('invalid', ['pitch', 'gap', 'page'])
def test_invalid_merge_preserves_project(invalid):
    project = chart()
    ids = [n.id for n in project.notes]
    if invalid == 'pitch':
        project.notes[1].pitch = 61
    elif invalid == 'gap':
        ids.pop(1)
    else:
        project.notes[0].line_break_after = True
    before = project.to_payload()
    with pytest.raises(ValueError):
        merge_selection(project, ids)
    assert project.to_payload() == before


def test_ctrl_selection_keyboard_and_merge_undo(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(chart())
    monkeypatch.setattr(window.tones, 'play', lambda *args: None)
    window.show()
    app.processEvents()
    timeline = window.timeline
    timeline.scale = 300
    notes = window.project.notes
    for index, note in enumerate(notes):
        QTest.mouseClick(timeline, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier if index else Qt.KeyboardModifier.NoModifier,
            pos=timeline.geometry_for(note).center().toPoint())
    assert timeline.selected_ids == {n.id for n in notes}
    QTest.keyClick(timeline, Qt.Key.Key_Up)
    assert {n.pitch for n in window.project.notes} == {61}
    window.undo()
    assert {n.pitch for n in window.project.notes} == {60}
    timeline.selected_ids = {n.id for n in window.project.notes}
    timeline.merge_notes()
    assert len(window.project.notes) == 1
    assert window.project.notes[0].text == 'Rollercoaster'
    window.undo()
    assert len(window.project.notes) == 3
    window.redo()
    assert len(window.project.notes) == 1
    window.dirty = False
    window.close()
