import struct

import pytest

from studio.importers import import_ultrastar
from studio.model import EditorNote, StudioProject
from studio.exporters import internal_chart
from tools.build_owned_chart import build_owned_pair, phrase_page_starts
from tools.walk_ixb_graph import Graph
from tools.write_template_chart import Note, SongChart


def test_explicit_page_time_emitted_and_does_not_retime_notes():
    chart = SongChart([Note(2, 1, 60, 'One', line_break_after=True, page_break_time=4.25),
                       Note(6, 2, 62, 'Two')])
    data, _ = build_owned_pair(chart, 'Demo', 'demo.xWMA', song_duration=12)
    graph = Graph(data)
    page_times = [struct.unpack_from('>f', data, r.payload + 8)[0]
                  for r in graph.records if graph.is_a(r, 'lpsPageBreakMarker')]
    assert page_times == pytest.approx([1.2, 4.25, 11])
    assert [struct.unpack_from('>f', data, r.payload + 8)[0]
            for r in graph.records if graph.is_a(r, 'lpsPhraseMarker')] == [2, 6]


def test_ultrastar_preserves_text_timings_and_numeric_break(tmp_path):
    path = tmp_path / 'synthetic.txt'
    path.write_text('#TITLE:Original\n#ARTIST:Test\n#BPM:120\n#GAP:1000\n: 0 4 0 Hel\n: 4 4 2 lo \n- 12\n: 16 8 4 world\nE\n', encoding='utf-8')
    project = import_ultrastar(path)
    assert [n.text for n in project.notes] == ['Hel', 'lo', 'world']
    assert [n.time for n in project.notes] == [1, 1.5, 3]
    assert [n.length for n in project.notes] == [.5, .5, 1]
    assert [n.pitch for n in project.notes] == [60, 62, 64]
    assert project.notes[1].page_break_time == 2.5
    assert project.notes[1].line_break_after
    assert internal_chart(project).notes[1].page_break_time == 2.5
    assert project.lyric_text() == 'Hello\nworld'


def test_invalid_page_and_duration_rejected():
    notes = [EditorNote(0, 1, 60, 'One', line_break_after=True, page_break_time=5),
             EditorNote(2, 1, 62, 'Two')]
    with pytest.raises(ValueError, match='next note'):
        phrase_page_starts(notes)
    notes[0].page_break_time = 1.5
    assert phrase_page_starts(notes) == [(None, 0), (0, 1.5)]
    notes[0].length = .75
    assert internal_chart(StudioProject(notes=notes)).notes[0].length == .75
