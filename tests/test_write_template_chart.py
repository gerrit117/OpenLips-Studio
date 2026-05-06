import json
import struct

import pytest

from tools.extract_melody_markers import iter_melody_markers, parse_ixb_document
from tools.patch_lyrics_mapping import iter_lyric_markers_structural
from tools.write_template_chart import (
    Note,
    SongChart,
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


def template_chart(marker_count=6):
    chunks = [IXB_SCHEMA]
    for index in range(marker_count):
        pointer = 0x07160000 + index * 0x80
        time = float(index + 1)
        chunks.append(word_data(pointer, index * 3, 2))
        chunks.append(melody_marker(time, 0.25, raw_pitch=49))
        chunks.append(lyric_marker(time, 0.25, pointer, melody_pointer=0x2FA10000 + index * 0x80))
        chunks.append(b"gap")
    chunks.append(b"</Objects></ixb>")
    return b"".join(chunks)


def template_lyric(capacity=128):
    payload = b"\xef\xbb\xbf\r\nold old old\r\n"
    payload += b" " * (capacity - len(payload))
    return b"<ixb><Objects>" + payload + b"</Objects></ixb>"


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

    assert [(marker.time, marker.length, marker.raw_pitch) for marker in melody[:3]] == pytest.approx(
        [(10.0, 0.5, 60), (10.5, 0.25, 62), (11.0, 0.75, 64)]
    )
    assert [marker.time for marker in melody[3:]] == pytest.approx([898.98, 898.99, 899.0])
    assert [(marker.time, marker.length, marker.track_index, marker.end_of_word) for marker in lyric[:3]] == pytest.approx(
        [(10.0, 0.5, 60, 0), (10.5, 0.25, 62, 1), (11.0, 0.75, 64, 1)]
    )
    assert [marker.time for marker in lyric[3:]] == pytest.approx([898.98, 898.99, 899.0])
    assert b"\xef\xbb\xbf\r\nHello world\r\n" in result.lyric_data
    assert [marker.text_length for marker in lyric[:3]] == [3, 2, 5]


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

    with pytest.raises(ValueError, match="template has only"):
        write_template_chart(chart_data, lyric_data, model)


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
