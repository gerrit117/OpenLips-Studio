import json
import struct

import pytest

from tools.extract_melody_markers import iter_melody_markers, parse_ixb_document
from tools.patch_lyrics_mapping import iter_lyric_markers_structural
from tools.write_template_chart import (
    Note,
    SongChart,
    TemplateWriteOptions,
    format_lyric_payload_comparison,
    format_lyric_payload_debug,
    format_summary,
    load_json_chart,
    write_template_chart,
    write_template_chart_files,
)


IXB_SCHEMA = (
    b'<ixb IsBigEndian="true" IsText="false" Platform="WIN32">'
    b"<Classes>"
    b'<Class Name="ixObject" Size="4"><Members></Members></Class>'
    b'<Class Name="ixReferencedObject" Base="1" Size="8"><Members>'
    b'<Member Name="m_uiReferenceCount" Offset="4"/>'
    b"</Members></Class>"
    b'<Class Name="ixSeqCode" Base="2" Size="20"><Members>'
    b'<Member Name="m_fTriggerTiming" Offset="8"/>'
    b'<Member Name="m_fLength" Offset="12"/>'
    b'<Member Name="m_iTrackIndex" Offset="16"/>'
    b"</Members></Class>"
    b'<Class Name="lpsMarker" Base="3" Size="24"><Members>'
    b'<Member Name="m_bTriggered" Offset="20"/>'
    b"</Members></Class>"
    b'<Class Name="lpsMelodyMarker" Base="4" Size="40"><Members>'
    b'<Member Name="m_Tone" Offset="24"/>'
    b'<Member Name="m_bTilt" Offset="32"/>'
    b'<Member Name="m_pLyricMarker" Offset="36"/>'
    b"</Members></Class>"
    b'<Class Name="ixVector&lt;lpsLyricWordData,1,ixAllocator&lt;lpsLyricWordData,1&gt;,ixIterator&lt;lpsLyricWordData&gt; &gt;" Size="16"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_reserve" Offset="4"/>'
    b'<Member Name="_size" Offset="8"/>'
    b'<Member Name="_allocator" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricMarker" Base="4" Size="64"><Members>'
    b'<Member Name="m_vecLyricWordData" Offset="28"/>'
    b'<Member Name="m_pMelodyMarker" Offset="24"/>'
    b'<Member Name="m_strFreeWord" Offset="44"/>'
    b'<Member Name="m_bEndOfWord" Offset="60"/>'
    b"</Members></Class>"
    b"</Classes><Objects>"
)


def melody_marker(time, length, raw_pitch=49, tone=6.0, octave=6):
    body = bytearray(40)
    struct.pack_into(">I", body, 4, 2)
    struct.pack_into(">ffIIfII", body, 8, time, length, raw_pitch, 0, tone, octave, 0)
    return b"\x28" + bytes(body)


def word_data(pointer, text_offset, text_length):
    body = bytearray(24)
    struct.pack_into(">I", body, 0, pointer)
    struct.pack_into(">I", body, 4, 0x280)
    struct.pack_into(">I", body, 8, 0x188FCD00)
    struct.pack_into(">I", body, 12, text_offset)
    struct.pack_into(">I", body, 16, text_length)
    struct.pack_into(">I", body, 20, 1)
    return bytes(body)


def lyric_marker(time, length, pointer, pitch=49, melody_pointer=0x2FA10000, end_word=1):
    body = bytearray(64)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">ffII", body, 8, time, length, pitch, 0)
    struct.pack_into(">I", body, 24, melody_pointer)
    struct.pack_into(">IIII", body, 28, pointer, 0x20, 1, 0xCDCDCDCD)
    struct.pack_into(">I", body, 60, end_word)
    return b"\x40" + bytes(body)


def template_chart(marker_count=6, text_offset_base=0):
    chunks = [IXB_SCHEMA]
    for index in range(marker_count):
        pointer = 0x07160000 + index * 0x80
        time = float(index + 1)
        chunks.append(word_data(pointer, text_offset_base + index * 3, 2))
        chunks.append(melody_marker(time, 0.25, raw_pitch=49))
        chunks.append(lyric_marker(time, 0.25, pointer, melody_pointer=0x2FA10000 + index * 0x80))
        chunks.append(b"gap")
    chunks.append(b"</Objects></ixb>")
    return b"".join(chunks)


def template_lyric(capacity=128):
    payload = b"\xef\xbb\xbf\r\nold old old old old\r\n"
    payload += b" " * (capacity - len(payload))
    return b"<ixb><Objects>" + text_resource(payload) + b"</Objects></ixb>"


def template_lyric_null_padded(capacity=128):
    payload = b"\xef\xbb\xbf\r\nold old old old old\r\n"
    payload += b"\x00" * (capacity - len(payload))
    return b"<ixb><Objects>" + text_resource(payload) + b"</Objects></ixb>"


def text_resource(payload: bytes, payload_hash=0x12345678):
    return b"\x00\x00\x00\x05Text\x00\x00\x00\x00" + struct.pack(">II", payload_hash, len(payload)) + payload


def template_lyric_with_resources(payloads):
    return b"<ixb><Objects>" + b"".join(text_resource(payload, 0x12345000 + index) for index, payload in enumerate(payloads)) + b"</Objects></ixb>"


def test_write_template_chart_patches_model_and_preserves_sizes_counts():
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(
        notes=[
            Note(10.0, 0.5, 60, "Hel", False),
            Note(10.5, 0.25, 62, "lo", True),
            Note(11.0, 0.75, 64, "world", True),
        ]
    )

    result = write_template_chart(chart_data, lyric_data, model)
    melody = sorted(iter_melody_markers(result.chart_data), key=lambda marker: marker.time)
    lyric = sorted(iter_lyric_markers_structural(result.chart_data), key=lambda marker: marker.time)

    assert len(result.chart_data) == len(chart_data)
    assert len(result.lyric_data) == len(lyric_data)
    assert result.melody_count_before == result.melody_count_after == 6
    assert result.lyric_count_before == result.lyric_count_after == 6
    assert result.notes_written == 3
    assert result.lyric_payload_bytes_used <= result.lyric_payload_capacity
    assert result.moved_unused_melody_count == 3
    assert result.moved_unused_lyric_count == 3
    assert len(result.melody_changes) == 6
    assert len(result.lyric_changes) == 6

    assert [(marker.time, marker.length, marker.raw_pitch) for marker in melody[:3]] == pytest.approx(
        [(10.0, 0.5, 60), (10.5, 0.25, 62), (11.0, 0.75, 64)]
    )
    assert [marker.time for marker in melody[3:]] == pytest.approx([898.98, 898.99, 899.0])
    assert [(marker.time, marker.length, marker.track_index, marker.end_of_word) for marker in lyric[:3]] == pytest.approx(
        [(10.0, 0.5, 60, 0), (10.5, 0.25, 62, 1), (11.0, 0.75, 64, 1)]
    )
    assert [marker.time for marker in lyric[3:]] == pytest.approx([898.98, 898.99, 899.0])
    assert b"Hello world\r\n" in result.lyric_data
    assert [marker.text_length for marker in lyric[:3]] == [3, 2, 5]
    assert result.lyric_text_overwrite is not None
    assert b"\x00" not in result.lyric_data[
        result.lyric_text_overwrite.visible_range_start : result.lyric_text_overwrite.visible_range_end
    ]
    assert result.lyric_text_overwrite.new_text_byte_length == len(b"Hello world\r\n")
    assert result.lyric_text_overwrite.changed_only_detected_range is True
    assert result.lyric_text_overwrite.selected_by == "chart_worddata_coverage"
    assert result.lyric_text_overwrite.coverage_markers_in_bounds == 6
    assert result.lyric_text_overwrite.coverage_total_markers == 6


def test_chart_only_leaves_lyrics_unchanged():
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])
    before_lyrics = sorted(iter_lyric_markers_structural(chart_data), key=lambda marker: marker.offset)

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(chart_only=True))
    after_lyrics = sorted(iter_lyric_markers_structural(result.chart_data), key=lambda marker: marker.offset)
    melody = sorted(iter_melody_markers(result.chart_data), key=lambda marker: marker.time)

    assert result.lyric_data == lyric_data
    assert result.lyric_changes == []
    assert result.moved_unused_lyric_count == 0
    assert [(marker.time, marker.length, marker.track_index, marker.text_offset, marker.text_length) for marker in after_lyrics] == [
        (marker.time, marker.length, marker.track_index, marker.text_offset, marker.text_length) for marker in before_lyrics
    ]
    assert [(marker.time, marker.length, marker.raw_pitch) for marker in melody[:2]] == pytest.approx(
        [(10.0, 0.5, 60), (10.5, 0.25, 62)]
    )


def test_lyric_only_leaves_melody_markers_unchanged():
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])
    before_melody = sorted(iter_melody_markers(chart_data), key=lambda marker: marker.offset)

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_only=True))
    after_melody = sorted(iter_melody_markers(result.chart_data), key=lambda marker: marker.offset)
    lyric = sorted(iter_lyric_markers_structural(result.chart_data), key=lambda marker: marker.time)

    assert result.melody_changes == []
    assert result.moved_unused_melody_count == 0
    assert [(marker.time, marker.length, marker.raw_pitch, marker.tone, marker.octave) for marker in after_melody] == [
        (marker.time, marker.length, marker.raw_pitch, marker.tone, marker.octave) for marker in before_melody
    ]
    assert [(marker.time, marker.length, marker.track_index) for marker in lyric[:2]] == pytest.approx(
        [(10.0, 0.5, 60), (10.5, 0.25, 62)]
    )
    assert b"Hello\r\n" in result.lyric_data


def test_lyric_text_only_uses_safe_visible_range_overwrite():
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])
    visible_start = lyric_data.index(b"\xef\xbb\xbf")
    payload_end = visible_start + 128

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_text_only=True))

    assert result.chart_data == chart_data
    assert result.lyric_data != lyric_data
    assert b"Hello\r\n" in result.lyric_data
    assert result.lyric_data[payload_end:] == lyric_data[payload_end:]
    assert result.chart_diff.bytes_changed == 0
    assert result.lyric_diff.bytes_changed > 0
    assert result.lyric_text_overwrite is not None
    assert result.lyric_text_overwrite.range_start == visible_start
    assert result.lyric_text_overwrite.range_end == payload_end
    assert result.lyric_text_overwrite.original_range_length == 128
    assert result.lyric_text_overwrite.visible_range_end == visible_start + len(b"\xef\xbb\xbf\r\nold old old old old\r\n")
    assert result.lyric_text_overwrite.padding_byte == 0x20
    assert result.lyric_text_overwrite.visible_fill_byte == 0x20
    assert result.lyric_text_overwrite.trailing_padding_preserved is True
    assert result.lyric_text_overwrite.changed_only_detected_range is True
    assert result.melody_changes == []
    assert result.lyric_changes == []
    assert result.string_length_fields_changed is False
    assert result.pointer_looking_fields_changed is False


def test_lyric_text_overwrite_only_preserves_null_padding_style():
    chart_data = template_chart()
    lyric_data = template_lyric_null_padded()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])
    visible_start = lyric_data.index(b"\xef\xbb\xbf")
    payload_end = visible_start + 128

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_text_overwrite_only=True))

    assert result.chart_data == chart_data
    assert result.lyric_text_overwrite is not None
    assert result.lyric_text_overwrite.padding_byte == 0
    assert result.lyric_text_overwrite.range_start == visible_start
    assert result.lyric_text_overwrite.range_end == payload_end
    assert result.lyric_data[payload_end:] == lyric_data[payload_end:]
    replacement = result.lyric_data[visible_start:payload_end]
    original_visible_end = visible_start + len(b"\xef\xbb\xbf\r\nold old old old old\r\n")
    assert replacement.startswith(b"Hello\r\n")
    assert b"\x00" not in result.lyric_data[visible_start:original_visible_end]
    assert result.lyric_data[original_visible_end:payload_end] == lyric_data[original_visible_end:payload_end]
    assert result.lyric_text_overwrite.visible_fill_byte == 0x20
    assert result.lyric_text_overwrite.trailing_padding_preserved is True


def test_lyric_text_overwrite_refuses_when_new_text_exceeds_visible_range():
    chart_data = template_chart()
    lyric_data = template_lyric(capacity=32)
    model = SongChart(notes=[Note(1.0, 0.5, 60, "this text is much too long for payload", True)])

    with pytest.raises(ValueError, match="original visible Text region"):
        write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_text_overwrite_only=True))


def test_lyric_text_preserves_bom_prefix_when_worddata_offsets_use_it():
    chart_data = template_chart(text_offset_base=3)
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])

    result = write_template_chart(chart_data, lyric_data, model)
    lyric = sorted(iter_lyric_markers_structural(result.chart_data), key=lambda marker: marker.time)

    assert b"\xef\xbb\xbf\r\nHello\r\n" in result.lyric_data
    assert [(marker.text_offset, marker.text_length) for marker in lyric[:2]] == [(3, 3), (6, 2)]
    assert result.lyric_text_overwrite is not None
    assert result.lyric_text_overwrite.prefix_char_length == 3
    assert result.lyric_text_overwrite.bom_preserved is True


def test_lyric_text_resource_selected_by_coverage_even_when_heuristic_rejects_it():
    chart_data = template_chart()
    broad_false_positive_prefix = b"\xef\xbb\xbf"
    visible_payload = broad_false_positive_prefix + b"A" * 125
    binary_payload = b"\x00\x01mostly-binary\x00\x02" + (b"\x00" * 64)
    lyric_data = template_lyric_with_resources([visible_payload, binary_payload])
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])
    selected_start = lyric_data.index(visible_payload)
    selected_end = selected_start + len(visible_payload)
    second_start = lyric_data.index(binary_payload)

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_text_overwrite_only=True))

    assert result.lyric_text_overwrite is not None
    assert result.lyric_text_overwrite.selected_by == "chart_worddata_coverage"
    assert result.lyric_text_overwrite.resource_index == 1
    assert result.lyric_text_overwrite.range_start == selected_start
    assert result.lyric_text_overwrite.range_end == selected_end
    assert result.lyric_data[:selected_start] == lyric_data[:selected_start]
    assert result.lyric_data[selected_end:] == lyric_data[selected_end:]
    assert result.lyric_data[second_start : second_start + len(binary_payload)] == binary_payload
    assert all(selected_start <= start and end <= selected_end for start, end in result.lyric_diff.changed_ranges)


def test_lyric_text_overwrite_does_not_select_broad_bom_to_objects_range():
    chart_data = template_chart()
    visible_payload = b"\xef\xbb\xbf" + (b"A" * 125)
    binary_payload = b"\x00\x01mostly-binary\x00\x02" + (b"\x00" * 64)
    lyric_data = template_lyric_with_resources([visible_payload, binary_payload])
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False)])
    selected_start = lyric_data.index(visible_payload)
    selected_end = selected_start + len(visible_payload)
    objects_end = lyric_data.index(b"</Objects>")

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_text_overwrite_only=True))

    assert result.lyric_text_overwrite is not None
    assert result.lyric_text_overwrite.range_start == selected_start
    assert result.lyric_text_overwrite.range_end == selected_end
    assert result.lyric_text_overwrite.range_end < objects_end
    assert result.lyric_data[selected_end:objects_end] == lyric_data[selected_end:objects_end]


def test_lyric_worddata_only_changes_only_worddata_offsets_and_lengths():
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])
    before_lyric = sorted(iter_lyric_markers_structural(chart_data), key=lambda marker: marker.offset)

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_worddata_only=True))
    after_lyric = sorted(iter_lyric_markers_structural(result.chart_data), key=lambda marker: marker.offset)
    after_melody = sorted(iter_melody_markers(result.chart_data), key=lambda marker: marker.offset)
    before_melody = sorted(iter_melody_markers(chart_data), key=lambda marker: marker.offset)

    assert result.lyric_data == lyric_data
    assert result.melody_changes == []
    assert result.chart_diff.bytes_changed > 0
    assert result.lyric_diff.bytes_changed == 0
    assert [(marker.time, marker.length, marker.track_index, marker.end_of_word) for marker in after_lyric] == [
        (marker.time, marker.length, marker.track_index, marker.end_of_word) for marker in before_lyric
    ]
    assert [(marker.time, marker.length, marker.raw_pitch) for marker in after_melody] == [
        (marker.time, marker.length, marker.raw_pitch) for marker in before_melody
    ]
    assert [(marker.text_offset, marker.text_length) for marker in after_lyric[:2]] == [(3, 3), (6, 2)]
    assert [(marker.text_offset, marker.text_length) for marker in after_lyric[2:]] == [
        (marker.text_offset, marker.text_length) for marker in before_lyric[2:]
    ]
    assert result.string_length_fields_changed is True
    assert result.pointer_looking_fields_changed is False


def test_lyric_marker_only_changes_only_lyric_marker_fields():
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])
    before_lyric = sorted(iter_lyric_markers_structural(chart_data), key=lambda marker: marker.offset)
    before_melody = sorted(iter_melody_markers(chart_data), key=lambda marker: marker.offset)

    result = write_template_chart(
        chart_data,
        lyric_data,
        model,
        TemplateWriteOptions(lyric_marker_only=True),
    )
    after_lyric = sorted(iter_lyric_markers_structural(result.chart_data), key=lambda marker: marker.offset)
    after_melody = sorted(iter_melody_markers(result.chart_data), key=lambda marker: marker.offset)

    assert result.lyric_data == lyric_data
    assert result.melody_changes == []
    assert result.moved_unused_lyric_count == 0
    assert [(marker.time, marker.length, marker.raw_pitch) for marker in after_melody] == [
        (marker.time, marker.length, marker.raw_pitch) for marker in before_melody
    ]
    assert [(marker.text_offset, marker.text_length, marker.melody_pointer, marker.word_data_pointer) for marker in after_lyric] == [
        (marker.text_offset, marker.text_length, marker.melody_pointer, marker.word_data_pointer) for marker in before_lyric
    ]
    assert [(marker.time, marker.length, marker.track_index, marker.end_of_word) for marker in after_lyric[:2]] == pytest.approx(
        [(10.0, 0.5, 60, 0), (10.5, 0.25, 62, 1)]
    )
    assert [(marker.time, marker.length, marker.track_index, marker.end_of_word) for marker in after_lyric[2:]] == pytest.approx(
        [(marker.time, marker.length, marker.track_index, marker.end_of_word) for marker in before_lyric[2:]]
    )
    assert result.string_length_fields_changed is False
    assert result.pointer_looking_fields_changed is False


def test_summary_reports_diff_validation_fields(tmp_path):
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False)])

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_worddata_only=True))
    summary = "\n".join(format_summary(result, tmp_path / "out.X360", tmp_path / "out_Lyric.X360"))

    assert "mode: lyric-worddata-only" in summary
    assert "chart_bytes_changed:" in summary
    assert "lyric_bytes_changed: 0" in summary
    assert "lyric_worddata_offset_length_bounds: ok" in summary
    assert "string_length_fields_changed: yes" in summary
    assert "pointer_looking_fields_changed: no" in summary


def test_summary_reports_safe_text_overwrite_fields(tmp_path):
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False)])

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_text_overwrite_only=True))
    summary = "\n".join(format_summary(result, tmp_path / "out.X360", tmp_path / "out_Lyric.X360"))

    assert "mode: lyric-text-overwrite-only" in summary
    assert "selected_by: chart_worddata_coverage" in summary
    assert "selected_text_resource_index: 1" in summary
    assert "coverage: 6/6" in summary
    assert "payload_length_field:" in summary
    assert "payload_range:" in summary
    assert "payload_length:" in summary
    assert "visible_text_range:" in summary
    assert "visible_fill_byte: 0x20" in summary
    assert "trailing_padding_preserved: yes" in summary
    assert "chart_output_differs:" in summary
    assert "melody_preview_first10_chronological:" in summary
    assert "lyric_worddata_mapping_validation:" not in summary
    assert "new_text_byte_length:" in summary
    assert "padding_byte: 0x20" in summary
    assert "changed_only_selected_payload: yes" in summary
    assert "metadata_fields_changed: no" in summary


def test_summary_reports_lyric_worddata_mapping_validation(tmp_path):
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])

    result = write_template_chart(chart_data, lyric_data, model)
    summary = "\n".join(format_summary(result, tmp_path / "out.X360", tmp_path / "out_Lyric.X360"))

    assert [(row.expected_text, row.resolved_text, row.match, row.warning) for row in result.lyric_mapping_validation] == [
        ("Hel", "Hel", True, "no"),
        ("lo", "lo", True, "no"),
    ]
    assert "lyric_worddata_mapping_validation:" in summary
    assert "expected='Hel' resolved='Hel' match=yes warning=no" in summary
    assert "expected='lo' resolved='lo' match=yes warning=no" in summary


def test_worddata_mapping_validation_warns_for_wrong_or_padding_fragments(tmp_path):
    chart_data = template_chart()
    lyric_data = template_lyric_null_padded()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_worddata_only=True))
    summary = "\n".join(format_summary(result, tmp_path / "out.X360", tmp_path / "out_Lyric.X360"))

    assert result.lyric_mapping_validation
    assert any(row.warning != "no" for row in result.lyric_mapping_validation)
    assert "warning=wrong-fragment" in summary or "warning=spaces-or-padding" in summary


def test_flat_pitch_test_patches_first_30_chronological_melodies_only(tmp_path):
    chart_data = template_chart(marker_count=35)
    lyric_data = template_lyric(capacity=160)
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False)])
    before = sorted(iter_melody_markers(chart_data), key=lambda marker: (marker.time, marker.offset))

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(flat_pitch_test=True))
    after = sorted(iter_melody_markers(result.chart_data), key=lambda marker: (marker.time, marker.offset))
    summary = "\n".join(format_summary(result, tmp_path / "out.X360", tmp_path / "out_Lyric.X360"))

    assert result.lyric_data == lyric_data
    assert result.notes_written == 0
    assert result.melody_count_before == result.melody_count_after == 35
    assert result.lyric_count_before == result.lyric_count_after == 35
    assert len(result.melody_changes) == 30
    assert all(change.action == "flat-pitch-test" for change in result.melody_changes)
    assert result.lyric_changes == []
    assert result.moved_unused_melody_count == 0
    for old_marker, new_marker in zip(before[:30], after[:30]):
        assert new_marker.time == pytest.approx(old_marker.time)
        assert new_marker.length == pytest.approx(old_marker.length)
        assert new_marker.raw_pitch == 65
        assert new_marker.tone == pytest.approx(2.0)
        assert new_marker.octave == 5
    for old_marker, new_marker in zip(before[30:], after[30:]):
        assert (new_marker.time, new_marker.length, new_marker.raw_pitch, new_marker.tone, new_marker.octave) == pytest.approx(
            (old_marker.time, old_marker.length, old_marker.raw_pitch, old_marker.tone, old_marker.octave)
        )
    assert "mode: flat-pitch-test" in summary
    assert "mode_flat_pitch_test: yes" in summary
    assert summary.count("flat-pitch-test: object_index=") == 30
    assert "raw_pitch 49->65 tone 6.000000->2.000000 octave 6->5" in summary


def test_no_disable_unused_preserves_unused_marker_times():
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(disable_unused=False))
    melody_by_offset = sorted(iter_melody_markers(result.chart_data), key=lambda marker: marker.offset)
    lyric_by_offset = sorted(iter_lyric_markers_structural(result.chart_data), key=lambda marker: marker.offset)

    assert result.moved_unused_melody_count == 0
    assert result.moved_unused_lyric_count == 0
    assert [marker.time for marker in melody_by_offset[2:]] == pytest.approx([3.0, 4.0, 5.0, 6.0])
    assert [marker.time for marker in lyric_by_offset[2:]] == pytest.approx([3.0, 4.0, 5.0, 6.0])


def test_chart_only_and_lyric_only_are_mutually_exclusive():
    chart_data = template_chart()
    lyric_data = template_lyric()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False)])

    with pytest.raises(ValueError, match="cannot be combined"):
        write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(chart_only=True, lyric_only=True))


def test_json_loader_is_temporary_debug_input(tmp_path):
    path = tmp_path / "chart.json"
    path.write_text(
        json.dumps(
            {
                "title": "Debug",
                "notes": [
                    {"time": 1.0, "length": 0.5, "pitch": 60, "text": "A", "end_word": True}
                ],
            }
        ),
        encoding="utf-8",
    )

    chart = load_json_chart(path)

    assert chart.title == "Debug"
    assert chart.notes == [Note(1.0, 0.5, 60, "A", True)]


def test_rejects_lyric_text_that_does_not_fit():
    chart_data = template_chart()
    lyric_data = template_lyric(capacity=16)
    model = SongChart(notes=[Note(1.0, 0.5, 60, "this text is much too long", True)])

    with pytest.raises(ValueError, match="original visible Text region"):
        write_template_chart(chart_data, lyric_data, model)


def test_lyric_payload_debug_and_comparison_report_generated_bytes():
    chart_data = template_chart(text_offset_base=3)
    lyric_data = template_lyric_null_padded()
    model = SongChart(notes=[Note(10.0, 0.5, 60, "Hel", False), Note(10.5, 0.25, 62, "lo", True)])

    result = write_template_chart(chart_data, lyric_data, model, TemplateWriteOptions(lyric_text_overwrite_only=True))
    debug = "\n".join(format_lyric_payload_debug(lyric_data, result))
    comparison = "\n".join(format_lyric_payload_comparison(lyric_data, result, preview_bytes=32))

    assert "generated_payload_hex:" in debug
    assert "EF BB BF 0D 0A 48 65 6C" in debug
    assert "generated_visible_text_escaped:" in debug
    assert "\\ufeff\\r\\nHello\\r\\n" in debug
    assert "original_visible_preview:" in comparison
    assert "generated_visible_preview:" in comparison
    assert "first_32_bytes_before_hex:" in comparison
    assert "first_32_bytes_after_hex:" in comparison


def test_write_template_chart_files_outputs_copies(tmp_path):
    chart_template = tmp_path / "template.X360"
    lyric_template = tmp_path / "template_Lyric.X360"
    json_chart = tmp_path / "chart.json"
    out_chart = tmp_path / "out.X360"
    out_lyric = tmp_path / "out_Lyric.X360"
    chart_data = template_chart()
    lyric_data = template_lyric()
    chart_template.write_bytes(chart_data)
    lyric_template.write_bytes(lyric_data)
    json_chart.write_text(
        json.dumps({"notes": [{"time": 1.0, "length": 0.5, "pitch": 60, "text": "A"}]}),
        encoding="utf-8",
    )

    result = write_template_chart_files(chart_template, lyric_template, json_chart, out_chart, out_lyric)

    assert chart_template.read_bytes() == chart_data
    assert lyric_template.read_bytes() == lyric_data
    assert out_chart.read_bytes() == result.chart_data
    assert out_lyric.read_bytes() == result.lyric_data
