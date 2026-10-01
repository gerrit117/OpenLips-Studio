import struct
import pytest

from tools.analyze_asf_packets import packet_payloads


def test_single_payload_and_extension():
    replicated = struct.pack('<IIH', 3, 4000, 33)
    data = b'\x82\x00\x00\x00\x5d' + struct.pack('<IH', 0, 33)
    data += b'\x82\x01' + struct.pack('<I', 0) + bytes([len(replicated)]) + replicated + b'abc'
    row = packet_payloads(data)[0]
    assert row['stream'] == 2
    assert row['object_size'] == 3
    assert row['timestamp_ms'] == 4000
    assert row['extension_hex'] == '2100'
    assert row['bytes'] == 3


def test_truncated_packet_refuses():
    with pytest.raises(ValueError, match='truncated'):
        packet_payloads(b'\x82')


def test_multiple_payloads_with_padding():
    header = b'\x09\x5d\x04' + struct.pack('<IH', 0, 33) + b'\x42'
    def payload(stream, text):
        replicated = struct.pack('<II', len(text), 4000)
        return bytes([stream, 1]) + struct.pack('<I', 0) + b'\x08' + replicated + bytes([len(text)]) + text
    rows = packet_payloads(header + payload(1, b'abc') + payload(2, b'defg') + bytes(4))
    assert [(r['stream'], r['bytes']) for r in rows] == [(1, 3), (2, 4)]


def test_payload_cannot_overlap_padding():
    data = b'\x09\x5d\x08' + struct.pack('<IH', 0, 33) + b'\x41'
    data += b'\x02\x01' + struct.pack('<I', 0) + b'\x08' + struct.pack('<II', 3, 4000) + b'\x03abc'
    with pytest.raises(ValueError, match='outside packet data'):
        packet_payloads(data)
