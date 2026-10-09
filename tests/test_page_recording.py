import copy
import time

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolBar, QDialog, QLineEdit

from studio.app import StudioWindow
from studio.exporters import internal_chart
from studio.model import EditorNote, StudioProject, save_project, load_project
from studio.page_recording import plan_page_switch, apply_page_switch, clear_page_switches
from tools.build_owned_chart import build_owned_pair, phrase_page_starts
from tools.walk_ixb_graph import Graph
from tools.analyze_lyric_pages import timing


def example():
    return StudioProject(notes=[EditorNote(1, .4, 60, 'One'),
        EditorNote(2, .4, 62, 'two'), EditorNote(3, .4, 64, 'three')])


def musical_values(p):
    return [(n.id, n.time, n.length, n.pitch, n.text, n.end_word) for n in p.notes]


def test_exact_gap_time_and_round_trip(tmp_path):
    p = example()
    before = musical_values(p)
    switch = plan_page_switch(p, 1.8)
    assert switch.note_id == p.notes[0].id and switch.time == 1.8
    assert not switch.adjusted
    assert apply_page_switch(p, switch)
    assert not apply_page_switch(p, switch)
    assert musical_values(p) == before
    assert phrase_page_starts(internal_chart(p).notes)[1:] == [(0, 1.8)]
    chart, _ = build_owned_pair(internal_chart(p), 'Test', 'Audio/Test')
    graph = Graph(chart)
    cuts = [timing(graph, record) for record in graph.records
            if graph.is_a(record, 'lpsPageBreakMarker')]
    assert any(abs(cut - 1.8) < 1e-6 for cut in cuts)
    path = tmp_path / 'timed.olp'
    save_project(p, path)
    assert load_project(path) == p


def test_inside_word_snaps_to_nearest_safe_boundary():
    p = example()
    early = plan_page_switch(p, 1.2)
    assert early.time == 1.4 and early.adjusted
    late = plan_page_switch(p, 2.02)
    assert late.note_id == p.notes[0].id and late.time == 2.0


def test_no_first_empty_page_or_terminal_empty_page():
    p = example()
    assert plan_page_switch(p, .9) is None
    assert plan_page_switch(p, 3.4) is None
    assert plan_page_switch(StudioProject(), 1) is None
    assert plan_page_switch(StudioProject(notes=[p.notes[0]]), 1.1) is None


@pytest.mark.parametrize('seconds', [-1, float('inf'), float('nan')])
def test_invalid_time(seconds):
    with pytest.raises(ValueError):
        plan_page_switch(example(), seconds)


def test_melisma_syllables_and_overlaps_stay_together():
    p = StudioProject(notes=[EditorNote(0, .4, 60, 'Hel', False),
        EditorNote(.4, .4, 62, 'lo', True), EditorNote(.8, .7, 64, '~', False),
        EditorNote(2, .3, 60, 'next')])
    switch = plan_page_switch(p, .7)
    assert switch.note_id == p.notes[2].id and switch.time == 1.5
    p = StudioProject(notes=[EditorNote(0, 2, 60, 'one'),
        EditorNote(.5, 2, 62, 'two'), EditorNote(3, .3, 60, 'next')])
    switch = plan_page_switch(p, .7)
    assert switch.note_id == p.notes[1].id and switch.time == 2.5


def test_move_existing_cut_and_clear_without_changing_music():
    p = example()
    before = musical_values(p)
    apply_page_switch(p, plan_page_switch(p, 1.6))
    apply_page_switch(p, plan_page_switch(p, 1.8))
    apply_page_switch(p, plan_page_switch(p, 2.8))
    assert phrase_page_starts(internal_chart(p).notes)[1:] == [(0, 1.8), (1, 2.8)]
    assert clear_page_switches(p)
    assert not clear_page_switches(p)
    assert musical_values(p) == before


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    w = StudioWindow()
    w.replace_project(example())
    w.show()
    w.activateWindow()
    app.processEvents()
    yield w
    w.dirty = False
    w.close()


def test_toolbar_recording_and_undo(window):
    assert any(window.record_pages_action in bar.actions() for bar in window.findChildren(QToolBar))
    before = copy.deepcopy(window.project)
    window.record_pages_action.trigger()
    assert window.record_pages_action.isChecked()
    window.position = 1.8
    window.record_page_switch()
    after = copy.deepcopy(window.project)
    assert after.notes[0].page_break_time == 1.8 and window.dirty
    window.record_page_switch()
    assert len(window.history) == 1
    window.undo()
    assert window.project == before
    window.redo()
    assert window.project == after
    window.clear_lyric_pages()
    assert not any(n.line_break_after for n in window.project.notes)
    window.undo()
    assert window.project == after


def test_space_starts_then_records_while_playing_and_escape_finishes(window):
    window.record_pages_action.trigger()
    window.seek(1.8)
    QTest.keyClick(window.timeline, Qt.Key.Key_Space)
    assert window.playing and not window.history
    window.clock_start = time.monotonic() - 1.8
    QTest.keyClick(window.timeline, Qt.Key.Key_Space)
    assert window.playing and len(window.history) == 1
    assert 1.8 - 1e-6 <= window.project.notes[0].page_break_time < 1.9
    QTest.keyClick(window.timeline, Qt.Key.Key_Escape)
    assert not window.record_pages_action.isChecked()


def test_typing_spaces_and_auto_repeat_do_not_record(window):
    window.record_pages_action.trigger()
    window.title_edit.setFocus()
    QTest.keyClick(window.title_edit, Qt.Key.Key_Space)
    assert not window.playing
    window.timeline.setFocus()
    QApplication.instance().processEvents()
    history = len(window.history)
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, ' ', True)
    QApplication.sendEvent(window.timeline, event)
    assert not window.playing and len(window.history) == history
    window.title_edit.setFocus()
    QTest.keyClick(window.title_edit, Qt.Key.Key_Escape)
    assert not window.record_pages_action.isChecked()


def test_switching_project_or_workspace_disarms(window):
    window.record_pages_action.trigger()
    window.workspace_tabs.setCurrentWidget(window.community_page)
    assert not window.record_pages_action.isChecked() and not window.playing
    window.record_pages_action.trigger()
    window.replace_project(example())
    assert not window.record_pages_action.isChecked()


def test_modal_text_entry_and_modified_space_are_not_intercepted(window):
    window.record_pages_action.trigger()
    QTest.keyClick(window.timeline, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert not window.playing
    dialog = QDialog(window)
    dialog.setModal(True)
    field = QLineEdit(dialog)
    dialog.show()
    field.setFocus()
    QApplication.instance().processEvents()
    QTest.keyClick(field, Qt.Key.Key_Space)
    assert field.text() == ' ' and not window.playing
    dialog.close()


def test_close_stops_playback_timer(window):
    window.toggle_play()
    assert window.playing and window.timer.isActive()
    window.dirty = False
    window.close()
    assert not window.playing and not window.timer.isActive()
