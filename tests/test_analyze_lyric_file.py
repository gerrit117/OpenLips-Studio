import struct

from tools.analyze_lyric_file import analyze_lyric_file, find_text_resources


def text_resource(payload: bytes, payload_hash: int = 0x12345678) -> bytes:
    chunk = bytearray()
    chunk += struct.pack(">I", 5)
    chunk += b"Text\x00"
    chunk += b"\x00" * 4
    chunk += struct.pack(">I", payload_hash)
    chunk += struct.pack(">I", len(payload))
    chunk += payload
    return bytes(chunk)


def lyric_ixb(payload: bytes) -> bytes:
    return (
        b'<ixb IsBigEndian="true" IsText="false" Platform="WIN32">'
        b"<Classes></Classes><Objects>"
        + text_resource(payload)
        + b"\x01\x02\x03\x04"
        + text_resource(b"\x00\x01mostly-binary\x00\x02", payload_hash=0x87654321)
        + b"</Objects></ixb>"
    )


def test_find_text_resources_uses_embedded_payload_length_not_objects_tail():
    payload = b"\xef\xbb\xbf\r\nFirst line\r\nSecond line\r\n" + (b"\x00" * 8)
    data = lyric_ixb(payload)

    resources = find_text_resources(data)
    visible = [resource for resource in resources if resource.is_visible_lyric_candidate]

    assert len(resources) == 2
    assert len(visible) == 1
    assert visible[0].payload_length == len(payload)
    assert visible[0].visible_length == len(payload.rstrip(b"\x00"))
    assert visible[0].padding_byte == 0
    assert visible[0].payload_end < data.index(b"</Objects>")


def test_analyze_lyric_file_reports_visible_payload(tmp_path):
    path = tmp_path / "sample_Lyric.X360"
    path.write_bytes(lyric_ixb(b"\xef\xbb\xbf\r\nFirst line\r\nSecond line\r\n" + (b" " * 4)))

    lines = analyze_lyric_file(path)
    text = "\n".join(lines)

    assert "Text resources: 2" in text
    assert "candidate visible lyric payload ranges: 1" in text
    assert "visible lyrics appear: once" in text
    assert "payload_len_field=" in text
