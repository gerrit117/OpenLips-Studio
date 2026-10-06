import copy
import math

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QWizard

from studio.model import EditorNote, StudioProject, save_project, load_project
from studio.lrc import parse_lrc
from studio.lyric_timing import (text_units,timed_draft,lrc_draft,split_note,split_words,
                                 enhanced_lrc,write_lrc)
from studio.exporters import internal_chart,export_midi
from studio.page_policy import prepare_pages
from studio.timing_dialog import TimingDialog
from studio.song_wizard import SongWizard


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_word_and_explicit_syllable_units():
    units = text_units('Hel|lo world\nNext line','syllable')
    assert [(u.text,u.end_word,u.end_line) for u in units] == [
        ('Hel',False,False),('lo',True,False),('world',True,True),
        ('Next',True,False),('line',True,True)]
    assert [u.text for u in text_units('Hel|lo ~ world')] == ['Hello','world']


def test_timed_draft_keeps_pitches_unassigned_and_source_unchanged(tmp_path):
    original = StudioProject(title='Test')
    before = copy.deepcopy(original)
    p = timed_draft(original,[1,1.5,2],'Hel|lo world','syllable',end=2.8)
    assert original == before
    assert [n.text for n in p.notes] == ['Hel','lo','world']
    assert [n.length for n in p.notes] == [.5,.5,pytest.approx(.8)]
    assert all(not n.pitch_assigned for n in p.notes)
    with pytest.raises(ValueError):
        internal_chart(p)
    file = tmp_path/'draft.olp'
    save_project(p,file)
    assert load_project(file) == p
    p.notes[0].pitch_assigned = p.notes[1].pitch_assigned = p.notes[2].pitch_assigned = True
    assert len(internal_chart(p).notes) == 3


@pytest.mark.parametrize('times,end', [([],None),([-1],None),([math.nan],None),
    ([1,1],None),([2,1],None),([1],.5)])
def test_invalid_onsets(times,end):
    with pytest.raises(ValueError):
        timed_draft(StudioProject(),times,'hello',end=end)


def test_lrc_only_line_and_enhanced_blocks():
    source = StudioProject()
    plain = lrc_draft(source,parse_lrc('[00:01]Hello world\n[00:03]Next\n[00:04]'))
    assert [(n.time,n.length,n.text) for n in plain.notes] == [(1,2,'Hello world'),(3,1,'Next')]
    enhanced = lrc_draft(source,parse_lrc('[00:01]<00:01>Hel<00:01.5>lo <00:02>world <00:02.8>'))
    assert [(n.time,n.text,n.end_word) for n in enhanced.notes] == [(1,'Hel',False),(1.5,'lo',True),(2,'world',True)]
    assert enhanced.notes[-1].length == pytest.approx(.8)
    assert all(not n.pitch_assigned for n in enhanced.notes)
    assert source.notes == []


def test_bad_enhanced_order_and_offset_rejected():
    for text in ('[offset:2000]\n[00:01]word','[00:01]<00:02>a <00:01>b'):
        with pytest.raises(ValueError):
            lrc_draft(StudioProject(),parse_lrc(text))


def test_split_sustained_word_and_estimated_word_division():
    p = lrc_draft(StudioProject(),parse_lrc('[00:01]hello world\n[00:03]'))
    parts = split_words(p,p.notes[0].id)
    assert [(n.time,n.length,n.text) for n in parts] == [(1,1,'hello'),(2,1,'world')]
    parts[-1].line_break_after = True
    parts[-1].page_break_time = 3
    right = split_note(p,parts[-1].id,2.5)
    assert right.text == '~' and right.line_break_after and right.page_break_time == 3
    assert not parts[-1].end_word and not parts[-1].line_break_after
    assert not right.pitch_assigned


def test_lrc_export_audio_offset_and_exclusive_creation(tmp_path):
    p = timed_draft(StudioProject(reference_offset=.5),[1,1.5,2],'Hel|lo world','syllable',end=2.8)
    data = enhanced_lrc(p)
    parsed = parse_lrc(data)
    assert [w.time for w in parsed.cues[0].words] == [1.5,2,2.5,3.3]
    restored = lrc_draft(StudioProject(),parsed)
    assert [n.text for n in restored.notes] == ['Hel','lo','world']
    file = tmp_path/'timed.lrc'
    write_lrc(p,file)
    with pytest.raises(FileExistsError):
        write_lrc(p,file)


def test_lrc_continuations_not_printed_or_given_false_word_onsets():
    p = StudioProject(notes=[EditorNote(0,1,60,'hello',False),EditorNote(1,1,62,'~',True),
                             EditorNote(2,1,64,'world')])
    text = enhanced_lrc(p)
    assert '~' not in text and '<00:01.000>' not in text


def test_midi_export_uses_assigned_pitches_and_same_media_clock(tmp_path):
    from studio.importers import read_midi
    p = timed_draft(StudioProject(reference_offset=.5),[1,2],'hello world',end=3)
    with pytest.raises(ValueError):
        export_midi(p,tmp_path/'missing.mid')
    for n,pitch in zip(p.notes,[60,64]):
        n.pitch,n.pitch_assigned = pitch,True
    file = tmp_path/'melody.mid'
    export_midi(p,file)
    imported = read_midi(file)
    assert [(n.time,n.pitch) for n in imported.lanes[0].notes] == [(1.5,60),(2.5,64)]
    with pytest.raises(FileExistsError):
        export_midi(p,file)


def test_automatic_page_copies_keep_music_and_manual_cuts():
    p = StudioProject(notes=[EditorNote(i*.4,.25,60,'word') for i in range(20)])
    before = copy.deepcopy(p)
    candidate = prepare_pages(p)
    assert p == before and candidate.page_layout_mode == 'automatic'
    assert any(n.line_break_after for n in candidate.notes)
    assert [(n.time,n.length,n.pitch,n.text,n.id) for n in p.notes] == [
        (n.time,n.length,n.pitch,n.text,n.id) for n in candidate.notes]
    p.page_layout_mode = 'manual'
    p.notes[1].line_break_after,p.notes[1].page_break_time = True,.7
    assert prepare_pages(p) == p


def test_legacy_project_defaults_to_assigned_pitches():
    p = StudioProject(notes=[EditorNote(1,1,60,'hello')]).to_payload()
    p.pop('page_layout_mode')
    p['notes'][0].pop('pitch_assigned')
    restored = StudioProject.from_payload(p)
    assert restored.notes[0].pitch_assigned and restored.page_layout_mode == 'source'


def test_song_pack_optimizes_owned_copies_and_preserves_manual_pages(tmp_path,monkeypatch):
    from studio.dlc_pack import build_projects_dlc
    from tools.walk_ixb_graph import Graph
    from tools.analyze_lyric_pages import timing
    audio=tmp_path/'audio.wav'
    audio.write_bytes(b'synthetic source')
    p=StudioProject(title='Automatic',artist='Test',audio_path=str(audio),
        notes=[EditorNote(i*.4,.25,60,'word') for i in range(20)])
    manual=copy.deepcopy(p)
    manual.title='Manual'
    manual.page_layout_mode='manual'
    manual.notes[0].line_break_after,manual.notes[0].page_break_time=True,.3
    before=copy.deepcopy([p,manual])
    def media(project,folder,report):
        folder.mkdir()
        data={}
        for name,suffix in [('audio','.xWMA'),('preview_audio','.xWMA'),('jacket','.jpg')]:
            file=folder/(name+suffix)
            file.write_bytes(b'synthetic media')
            data[name]=file
        return data,20
    captured={}
    def package(backend,files,*args,**kwargs):
        for name,path in files.items():
            if name.endswith('.X360') and '_Lyric' not in name:
                graph=Graph(path.read_bytes())
                captured[name]=[timing(graph,r) for r in graph.records if graph.is_a(r,'lpsPageBreakMarker')]
        return {'output_path':'synthetic package'}
    monkeypatch.setattr('studio.dlc_pack.bundled_tool',lambda name:'backend')
    monkeypatch.setattr('studio.dlc_pack.prepare_dlc_media',media)
    monkeypatch.setattr('studio.dlc_pack.build_package',package)
    build_projects_dlc([p,manual],tmp_path,pack_name='Test Pack')
    assert len(captured['song00.X360'])>2
    assert any(abs(cut-.3)<1e-6 for cut in captured['song01.X360'])
    assert [p,manual]==before


def test_lrc_wizard_needs_no_midi_and_returns_unpitched_draft(app,tmp_path,monkeypatch):
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:None)
    file = tmp_path/'lyrics.lrc'
    file.write_text('[ti:Test]\n[ar:Artist]\n[00:01]hello\n[00:02]world',encoding='utf-8')
    wizard = SongWizard()
    wizard.choices.setCurrentRow(wizard.modes.index('lrc'))
    wizard.show()
    app.processEvents()
    next_button = wizard.button(QWizard.WizardButton.NextButton)
    assert wizard.rect().contains(next_button.mapTo(wizard,next_button.rect().bottomRight()))
    wizard.next()
    wizard.rows['lrc'][0].setText(str(file))
    assert wizard.rows['chart'][1].isHidden()
    assert wizard.validateCurrentPage()
    assert wizard.project.title == 'Test' and wizard.project.artist == 'Artist'
    assert len(wizard.project.notes)==2 and not wizard.project.notes[0].pitch_assigned
    wizard.reject()


def test_timing_dialog_record_final_end_review_and_undo(app,monkeypatch):
    dialog = TimingDialog(StudioProject(draft_lyrics='hello world'))
    sounds=[]
    monkeypatch.setattr(dialog.click,'play',lambda *args:sounds.append(args))
    monkeypatch.setattr(dialog,'tick',lambda:None)
    dialog.record.setChecked(True)
    dialog.timer.stop()
    for seconds in (1,2):
        dialog.position=seconds
        dialog.tap()
    assert [n.text for n in dialog.notes] == ['hello','world']
    dialog.position=2.8
    dialog.tap()
    assert not dialog.record.isChecked() and dialog.notes[-1].length == pytest.approx(.8)
    assert len(sounds)==2
    dialog.undo()
    assert dialog.notes[-1].length == 2
    dialog.redo()
    assert dialog.notes[-1].length == pytest.approx(.8)
    dialog.accept()
    assert dialog.project.notes[-1].pitch_assigned is False
    assert not dialog.timer.isActive()


def test_blank_taps_then_text_preserve_timing(app,monkeypatch):
    dialog = TimingDialog(StudioProject())
    monkeypatch.setattr(dialog.click,'play',lambda *args:None)
    monkeypatch.setattr(dialog,'tick',lambda:None)
    dialog.record.setChecked(True)
    dialog.timer.stop()
    for seconds in (1,2):
        dialog.position=seconds
        dialog.tap()
    dialog.position=3
    dialog.record.setChecked(False)
    before = [(n.time,n.length) for n in dialog.notes]
    dialog.text.setPlainText('hello world')
    assert [n.text for n in dialog.notes] == ['hello','world']
    assert [(n.time,n.length) for n in dialog.notes] == before
    dialog.reject()


def test_editor_gray_draft_pitch_assignment_and_split_undo(app):
    from studio.app import StudioWindow
    window=StudioWindow()
    p = lrc_draft(StudioProject(),parse_lrc('[00:01]hello world\n[00:03]'))
    window.replace_project(p)
    window.select_note(p.notes[0].id)
    assert window.pitch_edit.value()==-1 and not window.tone_button.isEnabled()
    window.pitch_edit.setValue(60)
    window.pitch_edit.editingFinished.emit()
    assert window.project.notes[0].pitch_assigned
    window.timeline.split_selected(p.notes[0].id)
    assert len(window.project.notes)==2
    window.undo()
    assert len(window.project.notes)==1
    window.dirty=False
    window.close()


def test_pitch_edit_preserves_fractional_adjacent_note_times(app):
    from studio.app import StudioWindow
    window = StudioWindow()
    project = StudioProject(notes=[EditorNote(1/3,1/3,60,'hello'),
                                  EditorNote(2/3,1/3,62,'world')])
    window.replace_project(project)
    before = [(n.time,n.length) for n in project.notes]
    window.select_note(project.notes[0].id)
    window.pitch_edit.setValue(64)
    window.pitch_edit.editingFinished.emit()
    assert [(n.time,n.length) for n in window.project.notes] == before
    assert window.project.notes[0].pitch == 64
    window.dirty = False
    window.close()


def test_unpitched_merge_does_not_audition_placeholder_pitch(app):
    from studio.timeline import Timeline
    timeline = Timeline()
    project = timed_draft(StudioProject(),[1,2],'hello world',end=3)
    timeline.set_project(project)
    timeline.selected_ids = {n.id for n in project.notes}
    sounds = []
    timeline.pitch_preview.connect(sounds.append)
    timeline.merge_notes()
    assert len(project.notes) == 1 and not project.notes[0].pitch_assigned
    assert sounds == []


def test_timing_space_filter_and_text_entry(app,monkeypatch):
    dialog = TimingDialog(StudioProject(draft_lyrics='hello world'))
    monkeypatch.setattr(dialog.click,'play',lambda *args:None)
    monkeypatch.setattr(dialog,'tick',lambda:None)
    dialog.show()
    app.processEvents()
    dialog.record.setChecked(True)
    dialog.timer.stop()
    dialog.position = 1
    QTest.keyClick(dialog.play,Qt.Key.Key_Space)
    assert len(dialog.notes) == 1 and dialog.record.isChecked()
    dialog.position = 1.5
    dialog.record.setChecked(False)
    dialog.text.setFocus()
    QTest.keyClick(dialog.text,Qt.Key.Key_End)
    QTest.keyClick(dialog.text,Qt.Key.Key_Space)
    assert 'hello world ' == dialog.text.toPlainText()
    assert len(dialog.notes) == 1
    dialog.reject()


def test_review_ticks_reset_after_seek_and_speed_change(app,monkeypatch):
    dialog = TimingDialog(StudioProject())
    dialog.notes = timed_draft(StudioProject(),[1,2],'hello world',end=3).notes
    sounds = []
    monkeypatch.setattr(dialog.click,'play',lambda *args:sounds.append(args))
    now = [0.]
    monkeypatch.setattr('studio.timing_dialog.time.monotonic',lambda:now[0])
    dialog.toggle_play()
    dialog.timer.stop()
    now[0] = 1.1
    dialog.tick()
    dialog.tick()
    assert len(sounds) == 1
    dialog.seek(.5)
    dialog.change_speed('0.5x')
    now[0] += 1.2
    dialog.tick()
    assert len(sounds) == 2 and dialog.position == pytest.approx(1.1)
    dialog.hear_ticks.setChecked(False)
    now[0] += 2
    dialog.tick()
    assert len(sounds) == 2
    dialog.reject()
