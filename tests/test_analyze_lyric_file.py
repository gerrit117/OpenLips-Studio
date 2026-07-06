import struct
from types import SimpleNamespace

from tools.analyze_lyric_file import analyze_lyric_file, find_text_resources, select_text_resource
from tools.extract_melody_markers import (
    find_fileio_header_candidates,
    parse_ixb_document,
    probe_object_record_headers,
    validate_ixb_write_order,
)


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


def lyric_ixb_with_resources(payloads: list[bytes]) -> bytes:
    return (
        b'<ixb IsBigEndian="true" IsText="false" Platform="WIN32">'
        b"<Classes></Classes><Objects>"
        + b"".join(text_resource(payload, payload_hash=0x1000 + index) for index, payload in enumerate(payloads))
        + b"</Objects></ixb>"
    )


def lyric_ixb_with_uri_list(payload: bytes) -> bytes:
    return (
        b'<ixb IsBigEndian="true" IsText="false" Platform="X360" NumOfElements="3">'
        b"<Classes></Classes>"
        b'<UriList><Uri Key="7" Uri="song/chart"/></UriList>'
        b"<Objects>"
        + text_resource(payload)
        + b"</Objects></ixb>"
    )


def test_parse_ixb_document_reports_header_attributes_and_uri_list():
    data = lyric_ixb_with_uri_list(b"First line\nSecond line\n")

    document = parse_ixb_document(data)

    assert document.is_big_endian is True
    assert document.is_text is False
    assert document.platform == "X360"
    assert document.num_elements == 3
    assert document.classes_start is not None
    assert document.classes_end is not None
    assert document.urilist_start is not None
    assert document.urilist_end is not None
    assert document.objects_start is not None
    assert document.objects_end is not None
    assert document.classes_end < document.urilist_start < document.urilist_end < document.objects_start
    assert len(document.uri_entries) == 1
    assert document.uri_entries[0].key == 7
    assert document.uri_entries[0].uri == "song/chart"
    assert validate_ixb_write_order(document) == []


def test_validate_ixb_write_order_allows_existing_files_without_uri_list():
    document = parse_ixb_document(lyric_ixb(b"First line\nSecond line\n"))

    assert document.urilist_start is None
    assert document.urilist_end is None
    assert document.uri_entries == ()
    assert validate_ixb_write_order(document) == []


def test_probe_object_record_headers_reports_diagnostic_candidates_only():
    payload = b"payload"
    record = struct.pack(">III", 0, 0x12345678, len(payload)) + payload
    data = (
        b'<ixb IsBigEndian="true" IsText="false" Platform="X360">'
        b"<Classes></Classes><Objects>"
        + record
        + b"</Objects></ixb>"
    )
    document = parse_ixb_document(data)

    candidates = probe_object_record_headers(data, document)

    assert len(candidates) == 1
    assert candidates[0].value == 0x12345678
    assert candidates[0].payload_size == len(payload)
    assert data[candidates[0].payload_start : candidates[0].payload_end] == payload


def test_find_fileio_header_candidates_reports_tag_name_version_secondary_layout():
    data = bytearray(b"\x00" * 0x40)
    data[0x10:0x14] = b"TAG1"
    data[0x14:0x18] = b"NAME"
    struct.pack_into(">HH", data, 0x18, 3, 4)

    candidates = find_fileio_header_candidates(bytes(data))

    assert any(
        candidate.offset == 0
        and candidate.tag == b"TAG1"
        and candidate.name == b"NAME"
        and candidate.version == 3
        and candidate.secondary == 4
        for candidate in candidates
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


def test_chart_worddata_coverage_selects_large_resource_when_heuristic_rejects_it():
    large_payload = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    small_payload = b"\x00\x01mostly-binary\x00\x02"
    data = lyric_ixb_with_resources([large_payload, small_payload])
    resources = find_text_resources(data)
    markers = [
        SimpleNamespace(text_offset=0, text_length=10),
        SimpleNamespace(text_offset=12, text_length=15),
        SimpleNamespace(text_offset=40, text_length=12),
    ]

    assert resources[0].is_visible_lyric_candidate is False
    selection = select_text_resource(data, markers)

    assert selection.resource == resources[0]
    assert selection.selected_by == "chart_worddata_coverage"
    assert selection.coverage is not None
    assert selection.coverage.markers_in_bounds == 3


def test_chart_worddata_coverage_does_not_select_low_coverage_binary_resource():
    large_payload = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    small_payload = b"\x00\x01mostly-binary\x00\x02"
    data = lyric_ixb_with_resources([large_payload, small_payload])
    resources = find_text_resources(data)
    markers = [
        SimpleNamespace(text_offset=0, text_length=10),
        SimpleNamespace(text_offset=12, text_length=15),
        SimpleNamespace(text_offset=40, text_length=12),
    ]

    selection = select_text_resource(data, markers)

    assert selection.resource != resources[1]
