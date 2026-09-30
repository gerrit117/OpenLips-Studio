import struct

import pytest

from tools.analyze_asf import AUDIO, FILE, HEADER, STREAM, VIDEO, inspect


def object_bytes(guid, payload):
    return guid + struct.pack('<Q', len(payload) + 24) + payload


def synthetic_asf():
    properties = bytes(16) + struct.pack('<6Q4I', 254, 0, 1, 10000000, 10000000, 3000, 2, 16000, 16000, 192000)
    wave = struct.pack('<HHIIHHH', 0x162, 2, 48000, 24000, 8192, 16, 0)
    stream = AUDIO + bytes(16) + struct.pack('<QIIHI', 0, len(wave), 0, 1, 0) + wave
    children = object_bytes(FILE, properties) + object_bytes(STREAM, stream)
    return HEADER + struct.pack('<QI', len(children) + 30, 2) + b'\x01\x02' + children


def test_reads_little_endian_asf_header_without_modifying_file(tmp_path):
    path = tmp_path / 'synthetic.wma'
    data = synthetic_asf()
    path.write_bytes(data)
    result = inspect(path)
    assert path.read_bytes() == data
    assert result['min_packet'] == result['max_packet'] == 16000
    assert result['preroll_ms'] == 3000
    assert result['streams'][0]['bits'] == 16
    assert result['streams'][0]['codec_tag'] == 0x162
    assert result['streams'][0]['rate'] == 48000


@pytest.mark.parametrize('data', [b'bad', synthetic_asf()[:-1],
                               HEADER + struct.pack('<QI', 29, 0) + b'\x01\x02'])
def test_rejects_invalid_headers(tmp_path, data):
    path = tmp_path / 'bad.wmv'
    path.write_bytes(data)
    with pytest.raises(ValueError):
        inspect(path)


def test_rejects_object_length_outside_header(tmp_path):
    data = bytearray(synthetic_asf())
    struct.pack_into('<Q', data, 46, len(data) * 2)
    path = tmp_path / 'bad.wmv'
    path.write_bytes(data)
    with pytest.raises(ValueError, match='outside header'):
        inspect(path)


@pytest.mark.parametrize('bits', [0, 24])
def test_reports_video_bitmap_bits_and_exact_format_offset(tmp_path, bits):
    fmt = bytearray(51)
    struct.pack_into('<II', fmt, 0, 768, 432)
    struct.pack_into('<I', fmt, 11, 40)
    struct.pack_into('<H', fmt, 25, bits)
    fmt[27:31] = b'WVC1'
    stream = VIDEO + bytes(16) + struct.pack('<QIIHI', 0, len(fmt), 0, 2, 0) + fmt
    child = object_bytes(STREAM, stream)
    data = HEADER + struct.pack('<QI', len(child) + 30, 1) + b'\x01\x02' + child
    path = tmp_path / 'video.wmv'
    path.write_bytes(data)
    result = inspect(path)['streams'][0]
    assert result['bitmap_bit_count'] == bits
    assert result['bitmap_header_size'] == 40
    assert data[result['format_offset']:result['format_offset'] + len(fmt)] == fmt
    assert path.read_bytes() == data
