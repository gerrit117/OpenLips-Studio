import copy
import pytest

from studio.lrc import parse_lrc, attach_lrc, read_lrc
from studio.model import StudioProject, EditorNote, save_project, load_project


def test_bom_metadata_precision_and_repeated_chorus():
    doc = parse_lrc('\ufeff[ar:Example]\n[ti:Test]\n[00:01.123][00:08.50]Hello\n[00:02]World')
    assert doc.metadata == {'ar': 'Example', 'ti': 'Test'}
    assert [(c.time, c.text) for c in doc.cues] == [(1.123, 'Hello'), (2, 'World'), (8.5, 'Hello')]


def test_late_offset_applied_once_and_negative_time_not_clamped():
    doc = parse_lrc('[00:00.100]Hello\n[offset:200]')
    assert doc.cues[0].time == -.1
    assert doc.warnings


def test_enhanced_words_repeated_with_relative_anchors():
    doc = parse_lrc('[00:10.00][00:20.00]<00:10.00>Hello <00:10.50>world<00:11.00>\n[offset:-250]')
    assert doc.cues[0].text == 'Hello world'
    assert [(w.time, w.text) for w in doc.cues[1].words] == [(20.25, 'Hello '), (20.75, 'world'), (21.25, '')]


def test_attach_and_roundtrip_preserve_all_notes(tmp_path):
    project = StudioProject(notes=[EditorNote(1, .5, 60, 'unchanged')])
    before = copy.deepcopy(project.notes)
    attach_lrc(project, parse_lrc('[offset:100]\n[00:02.123]New words'), 'local.lrc')
    assert project.notes == before
    path = tmp_path / 'test.olp'
    save_project(project, path)
    restored = load_project(path)
    assert restored.notes == before
    assert parse_lrc(restored.lyric_reference['raw']).cues[0].time == 2.023
    assert restored.draft_lyrics == 'New words'


@pytest.mark.parametrize('text', ['', 'plain text', '[offset:no]\n[00:01]Hi', '[00:01]Hi\x00', '[00:01]<00:99>Hi'])
def test_invalid_sources_refuse(text):
    with pytest.raises(ValueError):
        parse_lrc(text)


def test_project_invalid_reference_refuses():
    with pytest.raises(ValueError):
        StudioProject(lyric_reference={'format': 'lrc', 'raw': 4}).validate()


def test_file_bom_and_unicode(tmp_path):
    path = tmp_path / 'sample.lrc'
    path.write_text('[00:01.10]Grüße', encoding='utf-8-sig')
    assert read_lrc(path).cues[0].text == 'Grüße'


def test_warning_for_out_of_order_words():
    assert parse_lrc('[00:01]<00:02>a<00:01>b').warnings


def test_anchor_limit(monkeypatch):
    monkeypatch.setattr('studio.lrc.MAX_CUES', 1)
    with pytest.raises(ValueError, match='anchor limit'):
        parse_lrc('[00:01][00:02]Hello')


def test_old_project_without_reference_still_loads():
    payload = StudioProject().to_payload()
    del payload['lyric_reference']
    assert StudioProject.from_payload(payload).lyric_reference == {}


def test_gui_import_cancel_accept_undo_redo(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from studio.app import StudioWindow
    from studio.lrc_dialog import LrcDialog
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    original = copy.deepcopy(window.project)
    doc = parse_lrc('[00:01]Hello\n[00:02]world')
    monkeypatch.setattr(LrcDialog, 'exec', lambda self: LrcDialog.DialogCode.Rejected)
    window.accept_lrc(doc)
    assert window.project == original
    assert not window.history
    monkeypatch.setattr(LrcDialog, 'exec', lambda self: LrcDialog.DialogCode.Accepted)
    window.accept_lrc(doc)
    imported = copy.deepcopy(window.project)
    assert len(imported.notes) == 2
    assert all(not note.pitch_assigned for note in imported.notes)
    assert window.lyrics.toPlainText() == 'Hello\nworld'
    window.undo()
    assert window.project == original
    window.redo()
    assert window.project == imported
    window.dirty = False
    window.close()


def test_lrc_assigns_existing_notes_without_changing_music():
    from studio.lrc import assign_lrc_notes
    from studio.model import EditorNote
    project = StudioProject(notes=[EditorNote(1 + i, .8, 60 + i) for i in range(5)])
    original = [(n.id, n.time, n.length, n.pitch) for n in project.notes]
    doc = parse_lrc('[00:01]Hello world\n[00:05]Last')
    assert assign_lrc_notes(project, doc) == 5
    assert [n.text for n in project.notes] == ['Hello', '~', 'world', '~', 'Last']
    assert [(n.id, n.time, n.length, n.pitch) for n in project.notes] == original
    assert project.notes[3].line_break_after and project.notes[4].line_break_after


def test_enhanced_lrc_assignment_uses_word_anchors():
    from studio.lrc import assign_lrc_notes
    from studio.model import EditorNote
    project = StudioProject(notes=[EditorNote(2, 1, 60), EditorNote(6, 1, 62)])
    assign_lrc_notes(project, parse_lrc('[00:01]<00:01>First <00:05>second'))
    assert [n.text for n in project.notes] == ['First', 'second']


def test_lrc_rounding_gap_assigns_overlapping_note_only_once():
    from studio.lrc import assign_lrc_notes
    from studio.model import EditorNote
    project = StudioProject(notes=[EditorNote(53.650833, .197917, 56),
        EditorNote(53.850833, .197917, 56), EditorNote(60, .1, 60)])
    document = parse_lrc('[00:51.70]\n[00:53.66]Two words\n[00:55.00]\n[01:00.50]Later')
    assert assign_lrc_notes(project, document) == 2
    assert [n.text for n in project.notes] == ['Two', 'words', '']


def test_lrc_boundary_note_has_single_owner():
    from studio.lrc import assign_lrc_notes
    from studio.model import EditorNote
    project = StudioProject(notes=[EditorNote(1, .2, 60), EditorNote(1.99, .2, 61)])
    assert assign_lrc_notes(project, parse_lrc('[00:01]First\n[00:02]Second')) == 2
    assert [n.text for n in project.notes] == ['First', 'Second']


def test_lrc_assignment_gui_is_undoable(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from studio.app import StudioWindow
    from studio.lrc_dialog import LrcDialog
    from studio.model import EditorNote
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.project.notes = [EditorNote(1, 1, 60)]
    original = copy.deepcopy(window.project)
    monkeypatch.setattr(LrcDialog, 'exec', lambda self: LrcDialog.DialogCode.Accepted)
    window.accept_lrc(parse_lrc('[00:01]Hello'))
    assert window.project.notes[0].text == 'Hello'
    window.undo()
    assert window.project == original
    window.dirty = False
    window.close()
