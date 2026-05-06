import struct

import pytest

from tools.extract_melody_markers import RUNTIME_MELODY_VTABLE, iter_melody_markers
from tools.patch_melody_timing import (
    DEFAULT_TIMES,
    MUTE_FIRST_PHRASE_SHIFT_SECONDS,
    PITCH_DEMO_RAW_PITCH,
    PITCH_ZIGZAG_PATTERN,
    default_output_path,
    find_patch_sites,
    patch_file,
    patch_first_melody_timings,
    patch_mute_first_phrase_visual_test,
    patch_pitch_demo,
    patch_pitch_zigzag,
)


MELODY_CLASS_CODE = 0x28

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


def runtime_marker(time, length, raw_pitch=49, tone=6.0, octave=6, tilt=0):
    return struct.pack(
        ">IIffIIfII",
        RUNTIME_MELODY_VTABLE,
        2,
        time,
        length,
        raw_pitch,
        0x12345678,
        tone,
        octave,
        tilt,
    )


def file_marker(time, length, raw_pitch=49, tone=6.0, octave=6, tilt=0):
    body = bytearray(40)
    struct.pack_into(">I", body, 4, 2)
    struct.pack_into(">ffIIfII", body, 8, time, length, raw_pitch, 0x12345678, tone, octave, tilt)
    struct.pack_into(">I", body, 36, 0xDEADBEEF)
    return bytes([MELODY_CLASS_CODE]) + bytes(body)


def chart_with_markers(count=12, times=None, length_step=1.0):
    times = list(range(count)) if times is None else times
    markers = [file_marker(float(time), 0.25 + index * length_step) for index, time in enumerate(times[:count])]
    return IXB_SCHEMA + b"gap".join(markers) + b"</Objects></ixb>"


def test_patches_first_10_structural_markers_only_and_preserves_size_count_and_unknowns():
    original_times = [30.0, 20.0, 5.0, 11.0, 1.0, 9.0, 2.0, 8.0, 3.0, 7.0, 4.0, 6.0]
    original = chart_with_markers(times=original_times)

    result = patch_first_melody_timings(original)
    patched_markers = sorted(iter_melody_markers(result.patched_data), key=lambda marker: marker.offset)

    assert len(result.patched_data) == len(original)
    assert len(result.sites) == 10
    assert len(result.before_markers) == 12
    assert len(result.after_markers) == 12
    assert [site.original_time for site in result.sites] == pytest.approx(sorted(original_times)[:10])
    assert [site.chronological_index for site in result.sites] == list(range(1, 11))
    assert [site.object_order_index for site in result.sites] == [5, 7, 9, 11, 3, 12, 10, 8, 6, 4]
    assert [marker.time for marker in patched_markers] == pytest.approx(
        [30.0, 20.0, 24.0, 29.0, 20.0, 28.0, 21.0, 27.0, 22.0, 26.0, 23.0, 25.0]
    )
    assert [marker.length for marker in patched_markers] == pytest.approx(
        [0.25 + index for index in range(12)]
    )

    for site in result.sites:
        changed = set(range(site.time_offset, site.time_offset + 4))
        changed.update(range(site.length_offset, site.length_offset + 4))
        for index, (before, after) in enumerate(
            zip(original[site.offset : site.offset + 41], result.patched_data[site.offset : site.offset + 41])
        ):
            absolute_index = site.offset + index
            if absolute_index not in changed:
                assert after == before


def test_rejects_runtime_only_fallback_markers():
    data = b"".join(runtime_marker(float(index), 0.5) for index in range(10))

    assert find_patch_sites(data) == []
    with pytest.raises(ValueError, match="schema/object-walker"):
        patch_first_melody_timings(data)


def test_mute_first_phrase_visual_test_moves_first_20_chronological_markers_later():
    original_times = [
        50.0,
        2.0,
        40.0,
        1.0,
        30.0,
        3.0,
        20.0,
        4.0,
        10.0,
        5.0,
        9.0,
        6.0,
        8.0,
        7.0,
        60.0,
        70.0,
        80.0,
        90.0,
        100.0,
        110.0,
        120.0,
    ]
    original = chart_with_markers(count=len(original_times), times=original_times, length_step=0.1)

    result = patch_mute_first_phrase_visual_test(original)
    patched_markers = sorted(iter_melody_markers(result.patched_data), key=lambda marker: marker.offset)

    assert len(result.patched_data) == len(original)
    assert len(result.before_markers) == len(original_times)
    assert len(result.after_markers) == len(original_times)
    assert len(result.sites) == 20
    assert [site.chronological_index for site in result.sites] == list(range(1, 21))
    assert [site.new_time for site in result.sites] == pytest.approx(
        [site.original_time + MUTE_FIRST_PHRASE_SHIFT_SECONDS for site in result.sites]
    )
    expected_by_offset = original_times[:]
    for site in result.sites:
        expected_by_offset[site.object_order_index - 1] = site.original_time + MUTE_FIRST_PHRASE_SHIFT_SECONDS
    assert [marker.time for marker in patched_markers] == pytest.approx(expected_by_offset)
    assert [marker.length for marker in patched_markers] == pytest.approx(
        [0.25 + index * 0.1 for index in range(len(original_times))]
    )


def test_pitch_demo_patches_first_20_chronological_markers_and_preserves_timing():
    original_times = [
        50.0,
        2.0,
        40.0,
        1.0,
        30.0,
        3.0,
        20.0,
        4.0,
        10.0,
        5.0,
        9.0,
        6.0,
        8.0,
        7.0,
        60.0,
        70.0,
        80.0,
        90.0,
        100.0,
        110.0,
        120.0,
    ]
    original = chart_with_markers(count=len(original_times), times=original_times, length_step=0.1)

    result = patch_pitch_demo(original)
    patched_markers = sorted(iter_melody_markers(result.patched_data), key=lambda marker: marker.offset)

    assert len(result.patched_data) == len(original)
    assert len(result.before_markers) == len(original_times)
    assert len(result.after_markers) == len(original_times)
    assert len(result.sites) == 20
    assert [site.chronological_index for site in result.sites] == list(range(1, 21))
    assert [marker.time for marker in patched_markers] == pytest.approx(original_times)
    assert [marker.length for marker in patched_markers] == pytest.approx(
        [0.25 + index * 0.1 for index in range(len(original_times))]
    )

    patched_offsets = {site.offset for site in result.sites}
    for marker in patched_markers:
        if marker.offset in patched_offsets:
            assert marker.raw_pitch == PITCH_DEMO_RAW_PITCH
            assert marker.tone == pytest.approx(9.0)
            assert marker.octave == 4
        else:
            assert marker.raw_pitch == 49
            assert marker.tone == pytest.approx(6.0)
            assert marker.octave == 6

    for site in result.sites:
        changed = set(range(site.raw_pitch_offset, site.raw_pitch_offset + 4))
        changed.update(range(site.tone_offset, site.tone_offset + 4))
        changed.update(range(site.octave_offset, site.octave_offset + 4))
        for index, (before, after) in enumerate(
            zip(original[site.offset : site.offset + 41], result.patched_data[site.offset : site.offset + 41])
        ):
            absolute_index = site.offset + index
            if absolute_index not in changed:
                assert after == before


def test_pitch_zigzag_raw_only_patches_raw_pitch_without_tone_octave():
    original_times = [float(value) for value in range(40, 0, -1)]
    original = chart_with_markers(count=len(original_times), times=original_times, length_step=0.1)

    result = patch_pitch_zigzag(original, update_tone_octave=False)
    patched_markers = sorted(iter_melody_markers(result.patched_data), key=lambda marker: marker.offset)

    assert len(result.patched_data) == len(original)
    assert len(result.before_markers) == len(original_times)
    assert len(result.after_markers) == len(original_times)
    assert len(result.sites) == 30
    assert [site.chronological_index for site in result.sites] == list(range(1, 31))
    assert [marker.time for marker in patched_markers] == pytest.approx(original_times)

    patched_offsets = {site.offset for site in result.sites}
    expected_by_chronology = {
        site.offset: PITCH_ZIGZAG_PATTERN[index % len(PITCH_ZIGZAG_PATTERN)]
        for index, site in enumerate(result.sites)
    }
    for marker in patched_markers:
        if marker.offset in patched_offsets:
            assert marker.raw_pitch == expected_by_chronology[marker.offset]
        else:
            assert marker.raw_pitch == 49
        assert marker.tone == pytest.approx(6.0)
        assert marker.octave == 6

    for site in result.sites:
        changed = set(range(site.raw_pitch_offset, site.raw_pitch_offset + 4))
        for index, (before, after) in enumerate(
            zip(original[site.offset : site.offset + 41], result.patched_data[site.offset : site.offset + 41])
        ):
            absolute_index = site.offset + index
            if absolute_index not in changed:
                assert after == before


def test_pitch_zigzag_full_patches_raw_pitch_tone_and_octave():
    original_times = [float(value) for value in range(40, 0, -1)]
    original = chart_with_markers(count=len(original_times), times=original_times, length_step=0.1)

    result = patch_pitch_zigzag(original, update_tone_octave=True)
    patched_markers = sorted(iter_melody_markers(result.patched_data), key=lambda marker: marker.offset)

    assert len(result.patched_data) == len(original)
    assert len(result.before_markers) == len(original_times)
    assert len(result.after_markers) == len(original_times)
    assert len(result.sites) == 30

    expected_by_chronology = {
        site.offset: PITCH_ZIGZAG_PATTERN[index % len(PITCH_ZIGZAG_PATTERN)]
        for index, site in enumerate(result.sites)
    }
    for marker in patched_markers:
        if marker.offset not in expected_by_chronology:
            assert marker.raw_pitch == 49
            assert marker.tone == pytest.approx(6.0)
            assert marker.octave == 6
        elif expected_by_chronology[marker.offset] == 45:
            assert marker.raw_pitch == 45
            assert marker.tone == pytest.approx(10.0)
            assert marker.octave == 6
        else:
            assert marker.raw_pitch == 75
            assert marker.tone == pytest.approx(4.0)
            assert marker.octave == 4

    for site in result.sites:
        changed = set(range(site.raw_pitch_offset, site.raw_pitch_offset + 4))
        changed.update(range(site.tone_offset, site.tone_offset + 4))
        changed.update(range(site.octave_offset, site.octave_offset + 4))
        for index, (before, after) in enumerate(
            zip(original[site.offset : site.offset + 41], result.patched_data[site.offset : site.offset + 41])
        ):
            absolute_index = site.offset + index
            if absolute_index not in changed:
                assert after == before


def test_requires_at_least_10_structural_markers():
    with pytest.raises(ValueError, match="need 10"):
        patch_first_melody_timings(chart_with_markers(1))


def test_rejects_compressed_input(tmp_path):
    source = tmp_path / "compressed.X360"
    target = tmp_path / "patched.X360"
    source.write_bytes(b"\x0f\xf5\x12\xee" + b"compressed")

    with pytest.raises(ValueError, match="decompress"):
        patch_file(source, target)


def test_patch_file_writes_copy_and_preserves_original(tmp_path):
    source = tmp_path / "song.X360"
    target = tmp_path / "song_patched.X360"
    original = chart_with_markers()
    source.write_bytes(original)

    result = patch_file(source, target)

    assert source.read_bytes() == original
    assert target.read_bytes() == result.patched_data
    assert target.exists()


def test_patch_file_supports_mute_first_phrase_mode(tmp_path):
    source = tmp_path / "song.X360"
    target = tmp_path / "song_muted.X360"
    source.write_bytes(chart_with_markers(count=21, length_step=0.1))

    result = patch_file(source, target, mode="mute-first-phrase-visual-test")

    assert source.read_bytes() != target.read_bytes()
    assert target.read_bytes() == result.patched_data
    assert len(result.sites) == 20


def test_patch_file_supports_pitch_demo_mode(tmp_path):
    source = tmp_path / "song.X360"
    target = tmp_path / "song_pitch.X360"
    source.write_bytes(chart_with_markers(count=21, length_step=0.1))

    result = patch_file(source, target, mode="pitch-demo")

    assert source.read_bytes() != target.read_bytes()
    assert target.read_bytes() == result.patched_data
    assert len(result.sites) == 20


@pytest.mark.parametrize(
    ("mode", "target_name"),
    [
        ("pitch-zigzag-raw-only", "song_zigzag_raw.X360"),
        ("pitch-zigzag-full", "song_zigzag_full.X360"),
    ],
)
def test_patch_file_supports_pitch_zigzag_modes(tmp_path, mode, target_name):
    source = tmp_path / "song.X360"
    target = tmp_path / target_name
    source.write_bytes(chart_with_markers(count=31, length_step=0.1))

    result = patch_file(source, target, mode=mode)

    assert source.read_bytes() != target.read_bytes()
    assert target.read_bytes() == result.patched_data
    assert len(result.sites) == 30


def test_refuses_to_overwrite_output_without_force(tmp_path):
    source = tmp_path / "song.X360"
    target = tmp_path / "song_patched.X360"
    source.write_bytes(chart_with_markers())
    target.write_bytes(b"existing")

    with pytest.raises(ValueError, match="already exists"):
        patch_file(source, target)


def test_default_output_path_uses_patched_demo_suffix():
    assert default_output_path(__import__("pathlib").Path("Song.X360")).name == "Song_patched_demo.X360"
    assert (
        default_output_path(
            __import__("pathlib").Path("Song.X360"),
            mode="mute-first-phrase-visual-test",
        ).name
        == "Song_mute_first_phrase_visual_test.X360"
    )
    assert default_output_path(__import__("pathlib").Path("Song.X360"), mode="pitch-demo").name == "Song_pitch_demo.X360"
    assert (
        default_output_path(__import__("pathlib").Path("Song.X360"), mode="pitch-zigzag-raw-only").name
        == "Song_pitch_zigzag_raw_only.X360"
    )
    assert (
        default_output_path(__import__("pathlib").Path("Song.X360"), mode="pitch-zigzag-full").name
        == "Song_pitch_zigzag_full.X360"
    )
