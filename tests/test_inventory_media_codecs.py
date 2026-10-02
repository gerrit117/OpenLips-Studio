import struct

import pytest

from tools.inventory_media_codecs import census, inspect_media


def riff(codec=0x161, form=b'XWMA'):
    fmt = struct.pack('<HHIIHHH', codec, 2, 48000, 24000, 1024, 16, 0)
    chunks = b'fmt ' + struct.pack('<I', len(fmt)) + fmt
    chunks += b'dpds' + struct.pack('<II', 4, 4096)
    chunks += b'data' + struct.pack('<I', 2) + b'\x00\x00'
    return b'RIFF' + struct.pack('<I', len(chunks) + 4) + form + chunks


@pytest.mark.parametrize('codec,name', [(0x161, 'WMA Standard'), (0x162, 'WMA Pro'), (0x166, 'XMA2')])
def test_riff_codec_not_guessed_from_extension(tmp_path, codec, name):
    path = tmp_path / 'sample.wmv'
    original = riff(codec)
    path.write_bytes(original)
    result = inspect_media(path)
    assert result['container'] == 'RIFF'
    assert result['form'] == 'XWMA'
    assert result['streams'][0]['codec'] == name
    assert path.read_bytes() == original


def test_invalid_chunk_is_reported_and_overlapping_roots_are_not_recounted(tmp_path):
    good = tmp_path / 'good.xWMA'
    good.write_bytes(riff())
    bad = tmp_path / 'bad.wma'
    malformed = bytearray(riff())
    struct.pack_into('<I', malformed, 16, 0x7fffffff)
    bad.write_bytes(malformed)
    report = census([('first', tmp_path), ('overlap', tmp_path)])
    assert report['file_count'] == 1
    assert len(report['failures']) == 1
    assert 'outside' in report['failures'][0]['error']


@pytest.mark.parametrize('data', [b'RIFF', riff()[:-1], b'unknown magic'])
def test_rejects_bad_container(tmp_path, data):
    path = tmp_path / 'bad.xwma'
    path.write_bytes(data)
    with pytest.raises(ValueError):
        inspect_media(path)
