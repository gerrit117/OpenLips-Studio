import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from studio.model import StudioProject, EditorNote
from studio.guided_review import GuidedReviewDialog, review_draft, review_lines
from studio.lrc import attach_lrc, parse_lrc


def project():
    p = StudioProject(notes=[EditorNote(1, .5, 60, 'Hello'), EditorNote(2, .5, 60, 'world'),
                             EditorNote(4, 1, 64, 'Again')])
    attach_lrc(p, parse_lrc('[00:01.00]Hello world\n[00:04.00]Again'), 'test')
    return p


def dialog(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('studio.tone_preview.TonePreview.play', lambda *args: None)
    p = project()
    d = GuidedReviewDialog(p)
    d.show()
    app.processEvents()
    return app, p, d


def test_lyric_anchors_remain_original():
    assert review_lines(project()) == [(1, 4, 'Hello world'), (4, 5, 'Again')]


def test_pitch_keys_and_cancel_do_not_change_original(monkeypatch):
    app, p, d = dialog(monkeypatch)
    note = d.view.notes[0]
    d.timeline.selected_id = note.id
    d.timeline.selected_ids = {note.id}
    QTest.keyClick(d.timeline, Qt.Key.Key_Up)
    assert d.project.notes[0].pitch == 61 and p.notes[0].pitch == 60
    d.undo()
    assert d.project.notes[0].pitch == 60
    d.redo()
    assert d.project.notes[0].pitch == 61
    d.reject()
    assert p.notes[0].pitch == 60


def test_merge_and_delete_update_full_draft_not_other_lines(monkeypatch):
    app, p, d = dialog(monkeypatch)
    d.timeline.selected_ids = {n.id for n in d.view.notes}
    d.timeline.merge_notes()
    assert len(d.project.notes) == 2
    assert d.project.notes[0].text == 'Hello world'
    assert d.project.notes[1].text == 'Again'
    d.timeline.delete_selected()
    assert [n.text for n in d.project.notes] == ['Again']
    d.undo()
    assert len(d.project.notes) == 2
    d.navigate(1)
    assert d.lyric.text() == 'Again'
    d.accept()


def test_loop_and_playback_modes(monkeypatch):
    app, p, d = dialog(monkeypatch)
    d.playing = True
    d.clock_position = d.end
    d.clock = __import__('time').monotonic()
    d.tick()
    assert d.position == .8 and d.playing
    d.loop.setChecked(False)
    d.clock_position = d.end
    d.tick()
    assert not d.playing
    d.mode.setCurrentIndex(d.mode.findData('notes'))
    assert d.audio.isMuted()
    d.reject()


def test_basic_pitch_draft_keeps_supplied_word_anchors():
    ref = StudioProject(key_signature='G# major')
    attach_lrc(ref, parse_lrc('[00:01.00]<00:01.00>Hello <00:02.00>world'), 'test')
    draft = StudioProject(notes=[EditorNote(1, 2, 60)])
    reviewed = review_draft(draft, ref)
    assert [(n.time, n.text) for n in reviewed.notes] == [(1, 'Hello'), (2, 'world')]
    assert reviewed.key_signature == ref.key_signature
    assert draft.notes[0].text == ''


def test_plain_lrc_does_not_invent_word_timestamps():
    ref = project()
    draft = StudioProject(notes=[EditorNote(1, .5, 60), EditorNote(2, .5, 62)])
    reviewed = review_draft(draft, ref)
    assert reviewed.notes[0].text == 'Hello world'
    assert reviewed.notes[1].text == ''
    assert any('no word anchors' in w for w in reviewed.warnings)


def test_word_alignment_routes_amd_to_cpu_engine(tmp_path, monkeypatch):
    from studio.ai_dialog import AiChartDialog
    from PySide6.QtCore import QSettings
    app = QApplication.instance() or QApplication([])
    cpu = tmp_path / 'cpu' / 'OpenLipsAI.exe'
    cpu.parent.mkdir()
    cpu.write_bytes(b'placeholder')
    amd = tmp_path / 'runtime-amd' / 'OpenLipsAI.exe'
    amd.parent.mkdir()
    amd.write_bytes(b'placeholder')
    media = tmp_path / 'voice.wav'
    media.write_bytes(b'placeholder')
    monkeypatch.setattr('studio.ai_runtime.has_amd_gpu', lambda: True)
    monkeypatch.setattr('studio.ai_runtime.installed_engine', lambda *a, **k: str(cpu))
    monkeypatch.setattr('studio.ai_runtime.amd_engine', lambda: (_ for _ in ()).throw(AssertionError('AMD worker selected')))
    monkeypatch.setattr('studio.ai_dialog.ffmpeg_encoder', lambda: 'ffmpeg')
    monkeypatch.setattr('studio.media_source.analysis_audio_source', lambda *a: str(media))
    monkeypatch.setattr(QSettings, 'setValue', lambda *a: None)
    calls = []
    monkeypatch.setattr('studio.ai_dialog.QProcess.start', lambda self, program, args: calls.append((program, args)))
    d = AiChartDialog(project())
    d.input.setText(str(media))
    d.runtime.setText(str(amd))
    d.device.setCurrentIndex(d.device.findData('amd'))
    d.align_lrc.setChecked(True)
    d.start()
    assert calls[0][0] == str(cpu)
    assert calls[0][1][calls[0][1].index('--device') + 1] == 'cpu'
    assert '--align-lrc' in calls[0][1]
    d.reject()
