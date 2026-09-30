import struct

import pytest

from tools.analyze_asf import HEADER, STREAM, VIDEO, inspect
from tools.normalize_og_asf import normalize


def synthetic_video(bits=0, codec=b'WVC1'):
    fmt = bytearray(51)
    struct.pack_into('<II', fmt, 0, 768, 432)
    struct.pack_into('<I', fmt, 11, 40)
    struct.pack_into('<H', fmt, 25, bits)
    fmt[27:31] = codec
    body = VIDEO + bytes(16) + struct.pack('<QIIHI', 0, len(fmt), 0, 2, 0) + fmt
    obj = STREAM + struct.pack('<Q', len(body) + 24) + body
    return HEADER + struct.pack('<QI', len(obj) + 30, 1) + b'\x01\x02' + obj + b'untouched synthetic packet data'


@pytest.mark.parametrize('bits', [0, 24])
def test_only_bitmap_field_changes_and_source_is_preserved(tmp_path, bits):
    source, output = tmp_path / 'input.wmv', tmp_path / 'output.wmv'
    original = synthetic_video(bits)
    source.write_bytes(original)
    result = normalize(source, output)
    patched = output.read_bytes()
    assert source.read_bytes() == original
    assert len(patched) == len(original)
    assert inspect(output)['streams'][0]['bitmap_bit_count'] == 24
    differences = [i for i, (a, b) in enumerate(zip(original, patched)) if a != b]
    assert differences == result['changed_offsets'] == ([result['field_offset']] if bits == 0 else [])
    assert result['encoded_packets_unchanged']
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('data', [synthetic_video(16), synthetic_video(codec=b'WMV2'), b'invalid'])
def test_rejects_unknown_formats_without_output(tmp_path, data):
    source, output = tmp_path / 'input.wmv', tmp_path / 'output.wmv'
    source.write_bytes(data)
    with pytest.raises(ValueError):
        normalize(source, output)
    assert source.read_bytes() == data
    assert not output.exists()


def test_never_overwrites_existing_files(tmp_path):
    source, output = tmp_path / 'input.wmv', tmp_path / 'output.wmv'
    source.write_bytes(synthetic_video())
    output.write_bytes(b'keep')
    for target in (source, output):
        with pytest.raises(ValueError):
            normalize(source, target)
    assert output.read_bytes() == b'keep'


def test_publication_failure_cleans_temporary_file(tmp_path, monkeypatch):
    source, output = tmp_path / 'input.wmv', tmp_path / 'output.wmv'
    data = synthetic_video()
    source.write_bytes(data)
    def fail_link(*args):
        raise OSError('simulated unsupported filesystem')
    monkeypatch.setattr('tools.normalize_og_asf.os.link', fail_link)
    with pytest.raises(OSError):
        normalize(source, output)
    assert source.read_bytes() == data
    assert not output.exists()
    assert not list(tmp_path.glob('*.tmp'))
