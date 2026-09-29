import struct

import pytest

from tools.analyze_lyric_file import find_text_resources
from tools.build_minimal_ixb_pair import (
    CHART_ROOT_LEVELS, MAIN_SEQUENCE_POINTER, MUSIC_INDEX_POINTER,
    MUSIC_INFO_POINTER, SYNTHETIC_LEVELS, TEXT_RESOURCE_HASH, MinimalNote,
    build_minimal_ixb_pair, format_ownership_chain_compare, write_minimal_ixb_pair,
)
from tools.walk_ixb_graph import Graph, GraphError


@pytest.mark.parametrize("level", SYNTHETIC_LEVELS)
def test_all_levels_use_exact_framing_schema_tags_and_resolvable_links(level):
    pair = build_minimal_ixb_pair(synthetic_level=level)
    for data, declared, offsets in (
        (pair.chart_data, pair.chart_num_elements, pair.chart_emitted_offsets),
        (pair.lyric_data, pair.lyric_num_elements, pair.lyric_emitted_offsets),
    ):
        graph = Graph(data)
        assert len(graph.records) == declared == len(offsets)
        assert not graph.summary()["graph_errors"]
        cursor = graph.document.objects_start
        for record, (name, tag, offset) in zip(graph.records, offsets, strict=True):
            assert offset == record.offset == cursor
            assert struct.unpack_from(">III", data, offset) == (tag, record.key, record.size)
            if tag:
                assert record.size == graph.document.classes[tag].size
            else:
                assert record.size >= 0
            if tag:
                assert next(graph.lineage(record)).name == name or name.startswith("ixList<") or name.startswith("ixDblCnt<")
            cursor = record.payload + record.size
        assert cursor == graph.document.objects_end
        assert data[cursor:] == b"</Objects></ixb>"
    chart = Graph(pair.chart_data)
    summary = chart.summary()
    assert summary["melodies"] == summary["lyrics"] == summary["resolved_lyric_links"] == 3
    assert summary["charts"] == int(level in CHART_ROOT_LEVELS)
    melody = [r for r in chart.records if chart.is_a(r, "lpsMelodyMarker")]
    assert [(chart.melody_values(r)["time"], chart.melody_values(r)["length"],
             chart.melody_values(r)["track_index"]) for r in melody] == [
        (n.time, n.length, n.raw_pitch) for n in pair.notes]


@pytest.mark.parametrize("level", SYNTHETIC_LEVELS)
def test_raw_buffers_and_lyric_ranges(level):
    pair = build_minimal_ixb_pair(synthetic_level=level)
    chart, lyric = Graph(pair.chart_data), Graph(pair.lyric_data)
    resource = lyric.ref(TEXT_RESOURCE_HASH)
    assert resource.class_index == 0
    text = lyric.data[resource.payload:resource.payload + resource.size].decode("utf-8")
    assert text == pair.lyric_text
    resources = find_text_resources(pair.lyric_data)
    assert len(resources) == 1
    assert (resources[0].payload_start, resources[0].payload_length) == (resource.payload, resource.size)
    for record, note in zip((r for r in chart.records if chart.is_a(r, "lpsLyricMarker")), pair.notes, strict=True):
        info, buffer = chart.vector(record, "m_vecLyricWordData", element_size=20)
        assert buffer.class_index == 0
        assert info["size"] == 1
        assert buffer.size == info["reserve"] * 20
        offset, length = chart.u32(buffer, 4), chart.u32(buffer, 8)
        assert text[offset:offset + length] == note.text
    for image in (r for r in lyric.records if lyric.is_a(r, "ixFileImage")):
        assert lyric.u32(image, 52) == TEXT_RESOURCE_HASH
        assert lyric.u32(image, 56) == lyric.u32(image, 60) == resource.size
    for graph in (chart, lyric):
        for record in graph.records:
            for name in ("m_strName", "m_strTypeName"):
                if name not in graph.members(record):
                    continue
                info, buffer = graph.vector(record, name, 1)
                if buffer:
                    assert buffer.size == info["reserve"] == info["size"]
                    assert graph.data[buffer.payload + info["size"] - 1] == 0


@pytest.mark.parametrize("level,count,sequences", [
    ("chart-root-minimal", 6, 2),
    ("chart-root-empty-sequence-vector", None, 0),
    ("chart-root-empty-seqcode-vector", 0, 1),
    ("chart-root-one-seqcode", 1, 1),
    ("chart-root-no-music-pointers", 6, 2),
    ("chart-root-index-only", 6, 2),
    ("chart-root-musicdata-only", 6, 2),
])
def test_isolation_variants_keep_their_graph(level, count, sequences):
    graph = Graph(build_minimal_ixb_pair(synthetic_level=level).chart_data)
    root = next(r for r in graph.records if graph.is_a(r, "lpsChart"))
    info, targets = graph.reference_vector(root, "m_vpSequence", "ixSequence")
    assert info["size"] == len(targets) == sequences
    if count is not None:
        owner = graph.ref(MAIN_SEQUENCE_POINTER)
        info, codes = graph.reference_vector(owner, "m_vpSeqCode", "ixSeqCode")
        assert info["size"] == len(codes) == count
        if count == 1:
            assert graph.is_a(codes[0], "lpsMelodyMarker")
    else:
        assert MAIN_SEQUENCE_POINTER not in graph.by_key
    index = 0 if level in ("chart-root-no-music-pointers", "chart-root-musicdata-only") else MUSIC_INDEX_POINTER
    music = 0 if level in ("chart-root-no-music-pointers", "chart-root-index-only") else MUSIC_INFO_POINTER
    assert graph.u32(root, 144) == index
    assert graph.u32(root, 148) == music


def test_large_sequence_has_consistent_capacity():
    notes = tuple(MinimalNote(20.0 + i, 0.5, 65, "Hi") for i in range(40))
    graph = Graph(build_minimal_ixb_pair(notes, synthetic_level="chart-root-minimal").chart_data)
    info, codes = graph.reference_vector(graph.ref(MAIN_SEQUENCE_POINTER), "m_vpSeqCode", "ixSeqCode")
    assert info["size"] == info["reserve"] == len(codes) == 80


def test_deterministic_output_and_no_overwrite(tmp_path):
    first = build_minimal_ixb_pair()
    assert first == build_minimal_ixb_pair()
    chart, lyric, _ = write_minimal_ixb_pair(tmp_path, "Tiny")
    with pytest.raises(FileExistsError):
        write_minimal_ixb_pair(tmp_path, "Tiny")
    assert chart.read_bytes() == first.chart_data
    assert lyric.read_bytes() == first.lyric_data


def test_truncated_or_wrong_framing_is_rejected():
    data = build_minimal_ixb_pair().chart_data
    first = Graph(data).records[0]
    broken = data[:first.offset] + data[first.offset + 11:]
    with pytest.raises(GraphError):
        Graph(broken)


def test_raw_text_can_contain_objects_closing_token_without_resynchronization():
    notes = (MinimalNote(20.0, 0.5, 65, "Hi </Objects> there"),)
    pair = build_minimal_ixb_pair(notes)
    graph = Graph(pair.lyric_data)
    payload = graph.ref(TEXT_RESOURCE_HASH)
    assert b"</Objects>" in graph.data[payload.payload:payload.payload + payload.size]
    assert graph.data[graph.document.objects_end:] == b"</Objects></ixb>"


def test_ownership_comparison_uses_structural_records(tmp_path):
    pair = build_minimal_ixb_pair(synthetic_level="lyric-ownership")
    path = tmp_path / "real_Lyric.X360"
    path.write_bytes(pair.lyric_data)
    report = format_ownership_chain_compare(path, pair.lyric_data, "lyric-ownership")
    assert "ixRawFileImage" in report
    assert "sequential" in report
    assert "data_ptr=0x12345678" in report
