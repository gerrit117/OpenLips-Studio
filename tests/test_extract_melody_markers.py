import csv
import io
import struct

import pytest

from tools.extract_melody_markers import (
    RUNTIME_MELODY_VTABLE,
    MelodyMarker,
    describe_magic,
    extract_melody_markers,
    iter_melody_markers,
    parse_ixb_classes,
    write_csv,
)


MELODY_CLASS_INDEX = 5

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
    b"</Classes><Objects>"
)


def runtime_marker(time, length, raw_pitch, tone, octave, tilt):
    return struct.pack(
        ">IIffIIfII",
        RUNTIME_MELODY_VTABLE,
        2,
        time,
        length,
        raw_pitch,
        0,
        tone,
        octave,
        tilt,
    )


def file_marker(time, length, raw_pitch, tone, octave, tilt):
    body = bytearray(40)
    struct.pack_into(">I", body, 4, 2)
    struct.pack_into(">ffIIfII", body, 8, time, length, raw_pitch, 0, tone, octave, tilt)
    return bytes([MELODY_CLASS_INDEX]) + bytes(body)


def test_scans_schema_file_markers_big_endian_and_sorts_by_time():
    data = (
        IXB_SCHEMA
        + file_marker(9.22779, 0.178106, 47, 8.0, 6, 0)
        + b"between"
        + file_marker(8.856088, 0.363957, 49, 6.0, 6, 0)
        + b"</Objects></ixb>"
    )

    markers = list(iter_melody_markers(data))
    sorted_markers = sorted(markers, key=lambda marker: (marker.time, marker.offset))

    assert len(markers) == 2
    assert sorted_markers[0].raw_pitch == 49
    assert sorted_markers[0].time == pytest.approx(8.856088)
    assert sorted_markers[0].tone == pytest.approx(6.0)
    assert sorted_markers[1].raw_pitch == 47
    assert {marker.source for marker in markers} == {"schema/object-walker"}


def test_scans_runtime_markers():
    data = b"padding" + runtime_marker(8.856088, 0.363957, 49, 6.0, 6, 0)

    markers = list(iter_melody_markers(data))

    assert len(markers) == 1
    assert markers[0].offset == len(b"padding")
    assert markers[0].octave == 6


def test_extract_returns_debug_for_compressed_chart_files(tmp_path):
    chart = tmp_path / "compressed.X360"
    chart.write_bytes(b"\x0f\xf5\x12\xed" + b"compressed")

    markers, debug = extract_melody_markers(chart, debug=True)

    assert markers == []
    assert debug is not None
    assert debug.kind == "LZXTDECODE compressed"


def test_parses_ixb_schema_classes():
    classes = parse_ixb_classes(IXB_SCHEMA)

    melody = next(cls for cls in classes.values() if cls.name == "lpsMelodyMarker")
    assert melody.size == 40
    assert melody.members["m_Tone"] == 24


def test_schema_without_melody_class_does_not_fallback_scan():
    data = (
        b'<ixb IsBigEndian="true" IsText="false" Platform="WIN32">'
        b"<Classes>"
        b'<Class Name="ixObject" Size="4"><Members></Members></Class>'
        b"</Classes><Objects>"
        + runtime_marker(8.856088, 0.363957, 49, 6.0, 6, 0)
        + b"</Objects></ixb>"
    )

    assert list(iter_melody_markers(data)) == []


def test_describes_magic():
    assert describe_magic(b"<ixb...") == ("3C 69 78 62", "plain IXB")
    assert describe_magic(b"\x0f\xf5\x12\xee...")[1] == "LZXNATIVE compressed"


def test_writes_required_csv_columns():
    output = io.StringIO()
    write_csv(
        [MelodyMarker(offset=16, time=1.25, length=0.5, raw_pitch=60, tone=0.0, octave=5, tilt=1)],
        output,
    )

    rows = list(csv.DictReader(io.StringIO(output.getvalue())))

    assert rows == [
        {
            "offset": "0x00000010",
            "time": "1.250000",
            "length": "0.500000",
            "raw_pitch": "60",
            "tone": "0.000000",
            "octave": "5",
            "tilt": "1",
        }
    ]
