from tools.analyze_lyric_file import find_text_resources, select_text_resource
from tools.build_minimal_ixb_pair import (
    CHART_SEQUENCE_VECTOR_POINTER,
    MAIN_SEQUENCE_POINTER,
    MUSIC_INDEX_POINTER,
    MUSIC_INFO_POINTER,
    SEQ_CODE_VECTOR_POINTER,
    SYNTHETIC_LEVELS,
    build_minimal_ixb_pair,
    format_ownership_chain_compare,
)
from tools.extract_melody_markers import _u32be, iter_melody_markers_object_walker, parse_ixb_document
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
    assert pair.lyric_num_elements == 13
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


def test_synthetic_levels_isolate_marker_tags_and_ownership():
    expected = {
        "bare": {
            "chart_num": None,
            "lyric_num": None,
            "melody_tag": 0x05,
            "lyric_tag": 0x07,
            "chart_has_assets": False,
            "lyric_has_assets": False,
        },
        "tags": {
            "chart_num": 10,
            "lyric_num": 2,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": False,
            "lyric_has_assets": False,
        },
        "lyric-ownership": {
            "chart_num": 10,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": False,
            "lyric_has_assets": True,
        },
        "full-current": {
            "chart_num": 18,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": True,
            "lyric_has_assets": True,
            "chart_has_root": False,
        },
        "chart-root-minimal": {
            "chart_num": 25,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": True,
            "lyric_has_assets": True,
            "chart_has_root": True,
        },
        "chart-root-empty-sequence-vector": {
            "chart_num": 22,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": True,
            "lyric_has_assets": True,
            "chart_has_root": True,
            "chart_has_seqcode_vector": False,
        },
        "chart-root-empty-seqcode-vector": {
            "chart_num": 24,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": True,
            "lyric_has_assets": True,
            "chart_has_root": True,
        },
        "chart-root-one-seqcode": {
            "chart_num": 24,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": True,
            "lyric_has_assets": True,
            "chart_has_root": True,
        },
        "chart-root-no-music-pointers": {
            "chart_num": 25,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": True,
            "lyric_has_assets": True,
            "chart_has_root": True,
        },
        "chart-root-index-only": {
            "chart_num": 25,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": True,
            "lyric_has_assets": True,
            "chart_has_root": True,
        },
        "chart-root-musicdata-only": {
            "chart_num": 25,
            "lyric_num": 13,
            "melody_tag": 0x28,
            "lyric_tag": 0x40,
            "chart_has_assets": True,
            "lyric_has_assets": True,
            "chart_has_root": True,
        },
    }

    for level in SYNTHETIC_LEVELS:
        pair = build_minimal_ixb_pair(synthetic_level=level)
        chart_document = parse_ixb_document(pair.chart_data)
        lyric_document = parse_ixb_document(pair.lyric_data)
        chart_classes = {cls.name for cls in chart_document.classes.values()}
        lyric_classes = {cls.name for cls in lyric_document.classes.values()}
        melody = sorted(iter_melody_markers_object_walker(pair.chart_data, chart_document), key=lambda marker: marker.time)
        lyrics = sorted(iter_lyric_markers_structural(pair.chart_data), key=lambda marker: marker.time)
        config = expected[level]

        assert pair.chart_num_elements == config["chart_num"]
        assert pair.lyric_num_elements == config["lyric_num"]
        assert [tag for name, tag in pair.chart_emitted_tags if name == "lpsMelodyMarker"] == [
            config["melody_tag"]
        ] * len(pair.notes)
        assert [tag for name, tag in pair.chart_emitted_tags if name == "lpsLyricMarker"] == [
            config["lyric_tag"]
        ] * len(pair.notes)
        assert ("ixAssetPackage" in chart_classes) is config["chart_has_assets"]
        assert ("ixRawFileImage" in lyric_classes) is config["lyric_has_assets"]
        assert ("lpsChart" in chart_classes) is config.get("chart_has_root", False)
        if config.get("chart_has_root", False):
            assert {
                "ixChart",
                "lpsChart",
                "ixSequence",
                "ixTempoMap",
                "lpsMusicInfo",
                "lpsMusicIndex",
            } <= chart_classes
            assert any(name == "ixVector<ixSequence *> chart sequences" for name, _tag in pair.chart_emitted_tags)
            assert any(name == "ixVector<ixSeqCode *> main sequence codes" for name, _tag in pair.chart_emitted_tags) is config.get(
                "chart_has_seqcode_vector", True
            )
        assert len(melody) == len(pair.notes)
        assert len(lyrics) == len(pair.notes)


def _offset(pair, name):
    return next(offset for chunk_name, _tag, offset in pair.chart_emitted_offsets if chunk_name == name)


def _vector_fields(data, offset):
    body = offset + 1
    return tuple(_u32be(data, body + delta) for delta in (0, 4, 8, 12))


def _embedded_vector_fields(data, offset, relative_offset):
    body = offset + 1 + relative_offset
    return tuple(_u32be(data, body + delta) for delta in (0, 4, 8, 12))


def test_chart_root_isolation_variant_fields():
    empty_sequence = build_minimal_ixb_pair(synthetic_level="chart-root-empty-sequence-vector")
    lps_chart = _offset(empty_sequence, "lpsChart")
    sequence_vector = _offset(empty_sequence, "ixVector<ixSequence *> chart sequences")
    assert _vector_fields(empty_sequence.chart_data, sequence_vector) == (CHART_SEQUENCE_VECTOR_POINTER, 0, 0, 0)
    assert _embedded_vector_fields(empty_sequence.chart_data, lps_chart, 72) == (CHART_SEQUENCE_VECTOR_POINTER, 0, 0, 0)
    assert not any(name == "ixSequence" for name, _tag in empty_sequence.chart_emitted_tags)

    empty_seqcode = build_minimal_ixb_pair(synthetic_level="chart-root-empty-seqcode-vector")
    lps_chart = _offset(empty_seqcode, "lpsChart")
    sequence = _offset(empty_seqcode, "ixSequence")
    sequence_vector = _offset(empty_seqcode, "ixVector<ixSequence *> chart sequences")
    seqcode_vector = _offset(empty_seqcode, "ixVector<ixSeqCode *> main sequence codes")
    assert _vector_fields(empty_seqcode.chart_data, sequence_vector) == (CHART_SEQUENCE_VECTOR_POINTER, 0x20, 1, 0)
    assert _u32be(empty_seqcode.chart_data, sequence_vector + 1 + 16) == MAIN_SEQUENCE_POINTER
    assert _embedded_vector_fields(empty_seqcode.chart_data, lps_chart, 72) == (CHART_SEQUENCE_VECTOR_POINTER, 0x20, 1, 0)
    assert _vector_fields(empty_seqcode.chart_data, seqcode_vector) == (SEQ_CODE_VECTOR_POINTER, 0, 0, 0)
    assert _embedded_vector_fields(empty_seqcode.chart_data, sequence, 72) == (SEQ_CODE_VECTOR_POINTER, 0, 0, 0)

    one_seqcode = build_minimal_ixb_pair(synthetic_level="chart-root-one-seqcode")
    sequence = _offset(one_seqcode, "ixSequence")
    seqcode_vector = _offset(one_seqcode, "ixVector<ixSeqCode *> main sequence codes")
    assert _vector_fields(one_seqcode.chart_data, seqcode_vector) == (SEQ_CODE_VECTOR_POINTER, 0x20, 1, 0)
    assert _embedded_vector_fields(one_seqcode.chart_data, sequence, 72) == (SEQ_CODE_VECTOR_POINTER, 0x20, 1, 0)

    no_music = build_minimal_ixb_pair(synthetic_level="chart-root-no-music-pointers")
    lps_chart = _offset(no_music, "lpsChart")
    assert _u32be(no_music.chart_data, lps_chart + 1 + 144) == 0
    assert _u32be(no_music.chart_data, lps_chart + 1 + 148) == 0

    index_only = build_minimal_ixb_pair(synthetic_level="chart-root-index-only")
    lps_chart = _offset(index_only, "lpsChart")
    assert _u32be(index_only.chart_data, lps_chart + 1 + 144) == MUSIC_INDEX_POINTER
    assert _u32be(index_only.chart_data, lps_chart + 1 + 148) == 0

    musicdata_only = build_minimal_ixb_pair(synthetic_level="chart-root-musicdata-only")
    lps_chart = _offset(musicdata_only, "lpsChart")
    assert _u32be(musicdata_only.chart_data, lps_chart + 1 + 144) == 0
    assert _u32be(musicdata_only.chart_data, lps_chart + 1 + 148) == MUSIC_INFO_POINTER


def test_ownership_chain_compare_reports_real_and_synthetic_fields(tmp_path):
    real_pair = build_minimal_ixb_pair(synthetic_level="lyric-ownership")
    synthetic_pair = build_minimal_ixb_pair(synthetic_level="tags")
    real_lyric_path = tmp_path / "real_Lyric.X360"
    real_lyric_path.write_bytes(real_pair.lyric_data)

    report = format_ownership_chain_compare(real_lyric_path, synthetic_pair.lyric_data, synthetic_pair.synthetic_level)

    assert "ownership-chain comparison" in report
    assert "synthetic level: tags" in report
    assert "real resources:" in report
    assert "synthetic resources:" in report
    assert "ixRawFileImage" in report
