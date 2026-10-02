import struct

import pytest

from tools.analyze_asf import AUDIO, EXTENSION, EXTENDED_STREAM, STREAM, VIDEO, inspect
from tools.probe_asf_frame_metadata import build
from tests.test_analyze_asf import object_bytes, synthetic_asf


def fixture_bytes(duration=None):
    data = synthetic_asf()
    extension_data = b''
    if duration is not None:
        body = bytearray(64)
        struct.pack_into('<H', body, 48, 1)
        struct.pack_into('<Q', body, 52, duration)
        extension_data = object_bytes(EXTENDED_STREAM, body)
    payload = bytes(16) + struct.pack('<HI', 6, len(extension_data)) + extension_data
    extension = object_bytes(EXTENSION, payload)
    data = bytearray(data + extension)
    struct.pack_into('<Q', data, 16, len(data))
    struct.pack_into('<I', data, 24, 3)
    # Mark the fixture stream as video for this metadata-only test.
    pos = data.index(AUDIO)
    fmt = bytearray(51)
    struct.pack_into('<II', fmt, 0, 768, 432)
    struct.pack_into('<I', fmt, 11, 40)
    struct.pack_into('<H', fmt, 25, 24)
    fmt[27:31] = b'WVC1'
    old_size = struct.unpack_from('<Q', data, pos - 8)[0]
    stream = VIDEO + bytes(16) + struct.pack('<QIIHI', 0, len(fmt), 0, 1, 0) + fmt
    data[pos - 24:pos - 24 + old_size] = object_bytes(STREAM, stream)
    struct.pack_into('<Q', data, 16, len(data))
    struct.pack_into('<Q', data, 70, len(data) + 10)
    return bytes(data) + b'packets!!!'


def test_adds_only_video_duration_and_preserves_data(tmp_path):
    source, ref, out = (tmp_path / n for n in ('source.wmv', 'ref.wmv', 'out.wmv'))
    source.write_bytes(fixture_bytes())
    ref.write_bytes(fixture_bytes(333667))
    original = source.read_bytes()
    result = build(source, ref, out)
    assert result['encoded_data_unchanged']
    assert result['added_bytes'] == 88
    assert source.read_bytes() == original
    info = inspect(out)
    assert info['extended_streams'][0]['average_time_per_frame_100ns'] == 333667
    assert info['declared_file_size'] == out.stat().st_size
    assert out.read_bytes()[info['header_size']:] == b'packets!!!'
    with pytest.raises(ValueError, match='new separate'):
        build(source, ref, out)


@pytest.mark.parametrize('duration', [0, 10000001])
def test_refuses_invalid_duration(tmp_path, duration):
    source, ref, out = (tmp_path / n for n in ('s.wmv', 'r.wmv', 'o.wmv'))
    source.write_bytes(fixture_bytes())
    ref.write_bytes(fixture_bytes(duration))
    with pytest.raises(ValueError, match='valid video frame duration'):
        build(source, ref, out)
    assert not out.exists()


def test_rejects_extension_overrun(tmp_path):
    data = bytearray(fixture_bytes(333667))
    pos = data.index(EXTENSION)
    struct.pack_into('<I', data, pos + 42, 1000000)
    path = tmp_path / 'bad.wmv'
    path.write_bytes(data)
    with pytest.raises(ValueError, match='extension length mismatch'):
        inspect(path)
