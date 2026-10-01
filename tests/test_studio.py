from pathlib import Path

import mido
import pytest

from studio.model import (StudioProject, EditorNote, demo_project, pitch_name,
                          assign_lyrics, save_project, load_project)
from studio.importers import read_midi, project_from_midi
from studio.exporters import export_debug_json, export_owned_pair


def test_project_roundtrip(tmp_path):
    project = demo_project()
    project.audio_path = str(tmp_path / 'reference.wav')
    project.video_path = str(tmp_path / 'reference.mp4')
    project.reference_offset = 1.25
    save_project(project, tmp_path / 'demo.olp')
    result = load_project(tmp_path / 'demo.olp')
    assert result == project
    assert pitch_name(60) == 'C4'


def test_lyrics_and_stable_note_order():
    project = StudioProject(notes=[EditorNote(0, 1, 60), EditorNote(0, 1, 62), EditorNote(1, 1, 64)])
    assert project.ordered() == project.notes
    assert assign_lyrics(project, 'Hel|lo world', syllabify=True) == (3, 0)
    assert project.lyric_text() == 'Hello world'
    assert not project.notes[0].end_word
    assert project.notes[-1].line_break_after


def test_midi_tempo_map_and_channel_selection(tmp_path):
    midi = mido.MidiFile(ticks_per_beat=480)
    tempo = mido.MidiTrack()
    midi.tracks.append(tempo)
    tempo.extend([mido.MetaMessage('set_tempo', tempo=500000),
                  mido.MetaMessage('set_tempo', tempo=1000000, time=480)])
    notes = mido.MidiTrack()
    midi.tracks.append(notes)
    notes.extend([mido.MetaMessage('track_name', name='Voice'),
                  mido.Message('note_on', note=60, velocity=64, channel=0),
                  mido.Message('note_off', note=60, channel=0, time=960),
                  mido.Message('note_on', note=65, velocity=64, channel=1),
                  mido.Message('note_on', note=65, velocity=0, channel=1, time=480)])
    path = tmp_path / 'synthetic.mid'
    midi.save(path)
    imported = read_midi(path)
    assert len(imported.lanes) == 2
    assert imported.lanes[0].notes[0].length == pytest.approx(1.5)
    assert imported.lanes[1].notes[0].time == pytest.approx(1.5)
    assert imported.lanes[1].notes[0].length == pytest.approx(1)
    assert project_from_midi(path, imported, 0).bpm == 120


def test_invalid_project_and_midi(tmp_path):
    with pytest.raises(ValueError):
        StudioProject(notes=[EditorNote(0, 0, 60)]).validate()
    midi = mido.MidiFile(type=2)
    midi.tracks.append(mido.MidiTrack())
    path = tmp_path / 'async.mid'
    midi.save(path)
    with pytest.raises(ValueError, match='type 2'):
        read_midi(path)


def test_owned_export_without_template(tmp_path):
    project = demo_project()
    directory = export_owned_pair(project, tmp_path / 'pair', 'first_light', 'first_light.xWMA')
    assert (directory / 'first_light.X360').read_bytes().startswith(b'<ixb')
    assert (directory / 'first_light_Lyric.X360').read_bytes().startswith(b'<ixb')
    with pytest.raises(FileExistsError):
        export_owned_pair(project, directory, 'first_light', 'first_light.xWMA')
    export_debug_json(project, tmp_path / 'chart.json')
    with pytest.raises(FileExistsError):
        export_debug_json(project, tmp_path / 'chart.json')


def test_window_horizontal_follow_and_edit():
    from PySide6.QtWidgets import QApplication
    from studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    original = window.project.notes[0]
    window.select_note(original.id)
    window.pitch_edit.setValue(65)
    window.edit_note()
    assert window.project.notes[0].pitch == 65
    window.undo()
    assert window.project.notes[0].pitch == 60
    window.redo()
    assert window.project.notes[0].pitch == 65
    window.timeline.set_cursor(15)
    x1 = window.timeline.geometry_for(window.project.notes[0]).x()
    window.timeline.set_cursor(16)
    assert window.timeline.geometry_for(window.project.notes[0]).x() < x1
    assert window.timeline.origin > 0
    window.dirty = False
    window.close()


def test_ui_save_project_not_export(tmp_path):
    from PySide6.QtWidgets import QApplication
    from studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.path = tmp_path / 'unfinished.olp'
    window.project.notes[0].text = ''
    window.dirty = True
    assert window.save()
    assert not window.dirty
    restored = load_project(window.path)
    assert restored.notes[0].text == ''
    assert not list(tmp_path.glob('*.X360'))
    window.close()


def test_syllable_suggestion_changes_only_draft_and_is_undoable():
    from PySide6.QtWidgets import QApplication
    from studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.lyrics.setPlainText('beautiful melody')
    before = [(n.text, n.time, n.length) for n in window.project.notes]
    window.suggest_text()
    assert '|' in window.lyrics.toPlainText()
    assert [(n.text, n.time, n.length) for n in window.project.notes] == before
    window.undo()
    assert window.lyrics.toPlainText() == 'beautiful melody'
    window.dirty = False
    window.close()
