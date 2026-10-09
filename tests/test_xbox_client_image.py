"""Synthetic client-only SDK image preparation; no game or SDK fixtures."""
import struct

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from tools.prepare_xbox_client_image import prepare


def image(tmp_path, title=0x4F4C5043):
    data = bytearray(0x400)
    struct.pack_into('>4s5I', data, 0, b'XEX2', 1, 0x400, 0, 0x100, 2)
    struct.pack_into('>4I', data, 24, 0x40006, 0x40, 0x3ff, 0x80)
    struct.pack_into('>4I8x', data, 0x40, 0, 0, 0, title)
    struct.pack_into('>IHH', data, 0x80, 8, 1, 0)
    key = bytes(range(16))
    encoder = Cipher(algorithms.AES(bytes(16)), modes.CBC(bytes(16))).encryptor()
    data[0x250:0x260] = encoder.update(key) + encoder.finalize()
    pe = bytearray(128)
    pe[:2] = b'MZ'
    struct.pack_into('<I', pe, 0x3c, 0x40)
    struct.pack_into('<4sH', pe, 0x40, b'PE\0\0', 0x1f2)
    encoder = Cipher(algorithms.AES(key), modes.CBC(bytes(16))).encryptor()
    data.extend(encoder.update(bytes(pe)) + encoder.finalize())
    source = tmp_path / 'synthetic.xex'
    source.write_bytes(data)
    return source, bytes(data), bytes(pe)


def test_own_image_preparation_preserves_source_and_refuses_overwrite(tmp_path):
    source, original, pe = image(tmp_path)
    target = tmp_path / 'default.xex'
    prepare(source, target)
    assert source.read_bytes() == original
    result = target.read_bytes()
    assert result[0x400:] == pe
    assert struct.unpack_from('>H', result, 0x84)[0] == 0
    with pytest.raises(FileExistsError):
        prepare(source, target)


def test_other_title_and_truncated_payload_are_rejected(tmp_path):
    source, original, _ = image(tmp_path, title=0x12345678)
    target = tmp_path / 'output.xex'
    with pytest.raises(ValueError, match='Only our OpenLips'):
        prepare(source, target)
    assert not target.exists() and source.read_bytes() == original
    source, original, _ = image(tmp_path)
    source.write_bytes(original[:-1])
    with pytest.raises(ValueError):
        prepare(source, target)
    assert not target.exists()
