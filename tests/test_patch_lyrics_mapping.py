import struct

import pytest

from tools.patch_lyrics_mapping import (
    LYRIC_REPEAT_COUNT,
    WORD_DATA_TEXT_LENGTH,
    WORD_DATA_TEXT_OFFSET,
    default_output_path,
    iter_lyric_markers_structural,
    patch_file,
    patch_lyric_repeat_test,
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


def word_data(pointer, text_offset, text_length):
    body = bytearray(24)
    struct.pack_into(">I", body, 0, pointer)
    struct.pack_into(">I", body, 4, 0x280)
    struct.pack_into(">I", body, 8, 0x188FCD00)
    struct.pack_into(">I", body, 12, text_offset)
    struct.pack_into(">I", body, 16, text_length)
    struct.pack_into(">I", body, 20, 1)
    return bytes(body)


def lyric_marker(time, pointer, melody_pointer=0x2FA10000):
    body = bytearray(64)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">ffII", body, 8, time, 0.05, 60, 0)
    struct.pack_into(">I", body, 24, melody_pointer)
    struct.pack_into(">IIII", body, 28, pointer, 0x20, 1, 0xCDCDCDCD)
    struct.pack_into(">I", body, 60, 1)
    return b"\x40" + bytes(body)


def chart_with_lyric_markers(times):
    chunks = [IXB_SCHEMA]
    for index, time in enumerate(times):
        pointer = 0x07160000 + index * 0x80
        chunks.append(word_data(pointer, index * 3, 2))
        chunks.append(lyric_marker(float(time), pointer, melody_pointer=0x2FA10000 + index * 0x80))
        chunks.append(b"pad")
    chunks.append(b"</Objects></ixb>")
    return b"".join(chunks)


def test_lyric_repeat_test_repoints_first_10_chronological_word_data_only():
    times = [30, 1, 20, 2, 10, 3, 9, 4, 8, 5, 7, 6]
    original = chart_with_lyric_markers(times)
    lyric_text = "aa bb cc dd ee ff gg hh ii jj kk ll"

    result = patch_lyric_repeat_test(original, lyric_text=lyric_text)
    after = iter_lyric_markers_structural(result.patched_data)

    assert len(result.patched_data) == len(original)
    assert len(result.before_markers) == len(times)
    assert len(result.after_markers) == len(times)
    assert len(result.sites) == LYRIC_REPEAT_COUNT
    assert [site.lyric_marker.chronological_index for site in result.sites] == list(range(1, 11))

    source = result.sites[0].lyric_marker
    patched_offsets = {site.lyric_marker.offset for site in result.sites}
    for marker in after:
        if marker.offset in patched_offsets:
            assert marker.text_offset == source.text_offset
            assert marker.text_length == source.text_length
        else:
            assert marker.text_offset != source.text_offset or marker.text_length != source.text_length

    for site in result.sites:
        marker = site.lyric_marker
        changed = set(range(marker.word_data_file_offset + WORD_DATA_TEXT_OFFSET, marker.word_data_file_offset + WORD_DATA_TEXT_OFFSET + 4))
        changed.update(range(marker.word_data_file_offset + WORD_DATA_TEXT_LENGTH, marker.word_data_file_offset + WORD_DATA_TEXT_LENGTH + 4))
        for index, (before, patched) in enumerate(
            zip(
                original[marker.word_data_file_offset : marker.word_data_file_offset + 24],
                result.patched_data[marker.word_data_file_offset : marker.word_data_file_offset + 24],
            )
        ):
            absolute_index = marker.word_data_file_offset + index
            if absolute_index not in changed:
                assert patched == before


def test_requires_10_structural_lyric_markers():
    with pytest.raises(ValueError, match="need 10"):
        patch_lyric_repeat_test(chart_with_lyric_markers([1, 2, 3]))


def test_patch_file_writes_copy_and_preserves_original(tmp_path):
    source = tmp_path / "song.X360"
    lyric = tmp_path / "song_Lyric.X360"
    target = tmp_path / "song_lyric_repeat.X360"
    original = chart_with_lyric_markers(list(range(12)))
    source.write_bytes(original)
    lyric.write_bytes(b"<ixb><Objects>\xef\xbb\xbfaa bb cc dd ee ff gg hh ii jj kk ll</Objects></ixb>")

    result = patch_file(source, target, lyric_path=lyric)

    assert source.read_bytes() == original
    assert target.read_bytes() == result.patched_data
    assert target.exists()


def test_rejects_compressed_input(tmp_path):
    source = tmp_path / "compressed.X360"
    target = tmp_path / "patched.X360"
    source.write_bytes(b"\x0f\xf5\x12\xed" + b"compressed")

    with pytest.raises(ValueError, match="decompress"):
        patch_file(source, target)


def test_default_output_path():
    assert default_output_path(__import__("pathlib").Path("Song.X360")).name == "Song_lyric_repeat_test.X360"
