import copy

from PySide6.QtWidgets import QApplication, QToolBar

from studio.app import StudioWindow
from studio.model import EditorNote, StudioProject
from studio.smart_pages import intelligent_pages, plan_pages, word_units, boundary_cost
from studio.importers import import_ultrastar
from tools.build_owned_chart import build_owned_pair
from studio.exporters import internal_chart


def project(words, starts=None):
    return StudioProject(notes=[EditorNote(t, .25, 60, word)
                               for t, word in zip(starts or [i * .4 for i in range(len(words))], words)])


def musical_values(p):
    return [(n.id, n.time, n.length, n.pitch, n.text, n.end_word) for n in p.notes]


def test_import_keeps_original_breaks_until_action(tmp_path):
    source = tmp_path / 'song.txt'
    source.write_text('#TITLE:Test\n#ARTIST:Test\n#BPM:120\n#GAP:1000\n: 0 4 0 One \n- 6\n: 8 4 2 two \nE\n')
    p = import_ultrastar(source)
    before = copy.deepcopy(p)
    assert p.notes[0].line_break_after
    assert p.notes[0].page_break_time == 1.75
    plan_pages(p)
    assert p == before


def test_pause_is_preferred_and_music_is_unchanged():
    p = project(['Here', 'we', 'go', 'back', 'home', 'again'], [0, .4, .8, 2.2, 2.6, 3])
    before = musical_values(p)
    result = intelligent_pages(p)
    assert p.notes[2].line_break_after
    assert result['pages'] == 2
    assert musical_values(p) == before
    assert not intelligent_pages(p)['changed']
    build_owned_pair(internal_chart(p), 'Test', 'Audio/Test')


def test_sentence_and_link_word_hints_are_soft_and_meaningful():
    p = project(['the', 'home.', 'word'], [0, .4, .8])
    units = word_units(p.ordered())
    assert boundary_cost(units[0], units[1]) > boundary_cost(units[1], units[2])
    p = project(['We', 'go', 'home.', 'Now', 'come', 'back'], [0, .3, .6, 1, 1.3, 1.6])
    intelligent_pages(p)
    assert p.notes[2].line_break_after


def test_melisma_and_syllables_are_not_cut_even_with_old_break_inside():
    p = StudioProject(notes=[EditorNote(0, .5, 60, 'Hel', False, True),
        EditorNote(.6, .5, 62, 'lo', True), EditorNote(1.2, 2, 64, '~', False),
        EditorNote(4, .5, 60, 'next')])
    before = musical_values(p)
    units = word_units(p.ordered())
    assert [len(u['notes']) for u in units] == [3, 1]
    intelligent_pages(p)
    assert not p.notes[0].line_break_after and not p.notes[1].line_break_after
    assert musical_values(p) == before


def test_oversized_group_and_empty_project():
    p = StudioProject(notes=[EditorNote(0, 5, 60, 'long'), EditorNote(5, 3, 62, '~', False)])
    assert intelligent_pages(p)['oversized_words'] == 1
    assert not p.notes[0].line_break_after
    assert intelligent_pages(StudioProject())['pages'] == 0


def test_overlap_is_not_separated():
    p = StudioProject(notes=[EditorNote(0, 2, 60, 'one'), EditorNote(.5, 2, 62, 'two')])
    intelligent_pages(p)
    assert not p.notes[0].line_break_after


def test_toolbar_action_and_undo_redo():
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    assert not window.smart_pages_action.isEnabled()
    window.replace_project(project(['Here', 'we', 'go', 'back', 'home', 'again'], [0, .4, .8, 2.2, 2.6, 3]))
    before = copy.deepcopy(window.project)
    assert window.smart_pages_action.isEnabled()
    assert any(window.smart_pages_action in bar.actions() for bar in window.findChildren(QToolBar))
    window.smart_pages_action.trigger()
    after = copy.deepcopy(window.project)
    assert after != before
    assert len(window.history) == 1
    window.undo()
    assert window.project == before
    window.redo()
    assert window.project == after
    window.intelligent_lyric_pages()
    assert len(window.history) == 1
    window.dirty = False
    window.close()
