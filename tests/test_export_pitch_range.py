import pytest

from studio.model import StudioProject, EditorNote
from studio.exporters import internal_chart
from tools.build_owned_chart import build_owned_pair
from tools.walk_ixb_graph import Graph
import struct
from tools.write_template_chart import Note, _validate_note


@pytest.mark.parametrize('pitch', [0, 23, 24, 84, 85, 88, 90, 127])
def test_export_preserves_full_midi_range(pitch):
    project = StudioProject(notes=[EditorNote(1, 1, pitch, 'Test')])
    chart = internal_chart(project)
    assert chart.notes[0].pitch == pitch
    data, _ = build_owned_pair(chart, 'pitch_test', 'pitch_test.xWMA')
    graph = Graph(data)
    marker = next(r for r in graph.records if graph.is_a(r, 'lpsPhraseMarker'))
    raw, tone, octave = struct.unpack_from('>i4xfI', data, marker.payload + 16)
    assert raw == 127 - pitch
    assert tone + 12 * octave == pitch


@pytest.mark.parametrize('pitch', [-1, 128])
def test_export_rejects_invalid_midi(pitch):
    with pytest.raises(ValueError, match='0..127'):
        _validate_note(Note(1, 1, pitch, 'Test', True), 1)
