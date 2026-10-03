import copy
import pytest
from studio.model import EditorNote, StudioProject
from studio.lyric_pages import optimize_pages
from studio.exporters import internal_chart
from tools.build_owned_chart import owned_lyric_word_ends, owned_lyric_payload, phrase_page_starts
from tools.build_owned_chart import build_owned_pair
from tools.walk_ixb_graph import Graph


def test_split_long_line_without_changing_music_or_text():
    project = StudioProject(notes=[EditorNote(i, .5, 60, 'word') for i in range(8)])
    before = [(n.id, n.time, n.length, n.pitch, n.text, n.end_word) for n in project.notes]
    result = optimize_pages(project, max_chars=14, max_seconds=8)
    assert result['added_breaks'] == 2
    assert [n.line_break_after for n in project.notes] == [False, False, True, False, False, True, False, False]
    assert before == [(n.id, n.time, n.length, n.pitch, n.text, n.end_word) for n in project.notes]
    assert len(phrase_page_starts(internal_chart(project).notes)) == 3
    assert optimize_pages(project, max_chars=14, max_seconds=8)['added_breaks'] == 0


def test_corpus_defaults_split_sparse_long_page_without_lengthening_notes():
    project = StudioProject(notes=[EditorNote(i, .1, 60, 'word') for i in range(8)])
    before = [(n.time, n.length, n.pitch, n.text) for n in project.notes]
    result = optimize_pages(project)
    assert result['pages'] == 3
    assert before == [(n.time, n.length, n.pitch, n.text) for n in project.notes]
    assert optimize_pages(project)['added_breaks'] == 0


def test_optimizer_preserves_serialized_note_lengths_and_pitches():
    project = StudioProject(notes=[EditorNote(i, .12, 60 + i % 3, 'word') for i in range(12)])
    def values():
        chart, _ = build_owned_pair(internal_chart(project), 'Synthetic', 'Audio/Synthetic')
        graph = Graph(chart)
        return [(graph.melody_values(r)['time'], graph.melody_values(r)['length'],
                 graph.melody_values(r)['tone'], graph.melody_values(r)['octave'])
                for r in graph.records if graph.is_a(r, 'lpsMelodyMarker')]
    before = values()
    assert optimize_pages(project)['added_breaks'] > 0
    assert values() == before


def test_keep_melisma_and_manual_breaks_together():
    project = StudioProject(notes=[EditorNote(0, .5, 60, 'Long'),
        EditorNote(1, .5, 62, '~', end_word=False),
        EditorNote(2, .5, 64, '~', end_word=False, line_break_after=True, page_break_time=2.5),
        EditorNote(3, .5, 60, 'Next')])
    before = copy.deepcopy(project)
    result = optimize_pages(project, max_notes=2)
    assert result['oversized_words'] == 1
    assert project == before
    chart = internal_chart(project)
    _, placements = owned_lyric_payload(chart)
    assert owned_lyric_word_ends(chart, placements)[0] is True


def test_split_by_notes_and_duration_only_at_word_end():
    project = StudioProject(notes=[EditorNote(i, .8, 60, str(i)) for i in range(6)])
    result = optimize_pages(project, max_notes=2, max_seconds=2)
    assert result['pages'] == 3


@pytest.mark.parametrize('kwargs', [dict(max_chars=0), dict(max_notes=0), dict(max_seconds=float('nan'))])
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        optimize_pages(StudioProject(), **kwargs)
