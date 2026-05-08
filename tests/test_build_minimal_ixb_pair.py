from tools.analyze_lyric_file import find_text_resources, select_text_resource
from tools.build_minimal_ixb_pair import build_minimal_ixb_pair
from tools.extract_melody_markers import iter_melody_markers_object_walker, parse_ixb_document
from tools.patch_lyrics_mapping import iter_lyric_markers_structural


def test_minimal_ixb_pair_is_structurally_walkable():
    pair = build_minimal_ixb_pair()
    chart_document = parse_ixb_document(pair.chart_data)
    lyric_document = parse_ixb_document(pair.lyric_data)

    assert pair.chart_data.startswith(b"<ixb")
    assert pair.lyric_data.startswith(b"<ixb")
    assert [cls.name for cls in chart_document.classes.values() if cls.name == "ixPackage"] == ["ixPackage"]
    assert [cls.name for cls in lyric_document.classes.values() if cls.name == "ixPackage"] == ["ixPackage"]

    chart_class_names = {cls.name for cls in chart_document.classes.values()}
    lyric_class_names = {cls.name for cls in lyric_document.classes.values()}
    assert {"ixAssetPackage", "ixAsset", "ixFileImage", "ixRawFileImage"} <= chart_class_names
    assert {"ixAssetPackage", "ixAsset", "ixFileImage", "ixRawFileImage"} <= lyric_class_names
    assert pair.chart_num_elements == 18
    assert pair.lyric_num_elements == 14
    assert [tag for name, tag in pair.chart_emitted_tags if name == "lpsMelodyMarker"] == [0x28] * len(pair.notes)
    assert [tag for name, tag in pair.chart_emitted_tags if name == "lpsLyricMarker"] == [0x40] * len(pair.notes)
    assert [tag for name, tag in pair.lyric_emitted_tags if name == "ixRawFileImage"] == [0x54]

    melody = sorted(iter_melody_markers_object_walker(pair.chart_data, chart_document), key=lambda marker: marker.time)
    lyrics = sorted(iter_lyric_markers_structural(pair.chart_data), key=lambda marker: marker.time)
    assert len(melody) == len(pair.notes)
    assert len(lyrics) == len(pair.notes)
    assert [(marker.time, marker.length, marker.raw_pitch) for marker in melody] == [
        (note.time, note.length, note.raw_pitch) for note in pair.notes
    ]
    assert [(marker.time, marker.length, marker.track_index) for marker in lyrics] == [
        (note.time, note.length, note.raw_pitch) for note in pair.notes
    ]


def test_minimal_ixb_pair_has_one_text_resource_resolved_by_worddata_coverage():
    pair = build_minimal_ixb_pair()
    lyric_markers = iter_lyric_markers_structural(pair.chart_data)
    resources = find_text_resources(pair.lyric_data)
    selection = select_text_resource(pair.lyric_data, lyric_markers)

    assert len(resources) == 1
    assert selection.resource == resources[0]
    assert selection.selected_by == "chart_worddata_coverage"
    assert selection.coverage is not None
    assert selection.coverage.markers_in_bounds == len(pair.notes)
    assert selection.coverage.markers_out_of_bounds == 0

    decoded_payload = pair.lyric_data[resources[0].payload_start : resources[0].payload_end].decode("utf-8")
    assert decoded_payload == pair.lyric_text
    resolved = [decoded_payload[offset : offset + length] for offset, length in pair.text_offsets]
    assert resolved == [note.text for note in pair.notes]
