"""Remove SDK development encryption from our own plain/basic client image only."""
from pathlib import Path
import struct

from tools.inspect_xex_identity import identity

CLIENT_TITLE_ID = '4F4C5043'


def prepare(source, target):
    source, target = Path(source), Path(target)
    if identity(source).get('title_id') != CLIENT_TITLE_ID:
        raise ValueError('Only our OpenLips client image is accepted, never game files')
    if source.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Unexpected client image size')
    data = bytearray(source.read_bytes())
    offset, security, count = struct.unpack_from('>I4xII', data, 8)
    headers = dict(struct.unpack_from('>II', data, 24 + i * 8) for i in range(count))
    form = headers.get(0x3ff)
    if form is None or form + 8 > offset or security + 0x160 > offset or not 24 <= offset < len(data):
        raise ValueError('Invalid development-image headers')
    size, encrypted, compressed = struct.unpack_from('>IHH', data, form)
    if size < 8 or form + size > offset or encrypted != 1 or compressed not in (0, 1) or (len(data)-offset) % 16:
        raise ValueError('Only plain/basic SDK development images are accepted')
    if compressed == 1:
        if (size-8) % 8 or sum(struct.unpack_from('>I', data, form+i)[0] for i in range(8,size,8)) != len(data)-offset:
            raise ValueError('Invalid basic-image block table')
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    # The development format uses an all-zero wrapping key, not a retail key.
    unwrap = Cipher(algorithms.AES(bytes(16)), modes.CBC(bytes(16))).decryptor()
    key = unwrap.update(bytes(data[security+0x150:security+0x160])) + unwrap.finalize()
    decoder = Cipher(algorithms.AES(key), modes.CBC(bytes(16))).decryptor()
    image = decoder.update(bytes(data[offset:])) + decoder.finalize()
    if image[:2] != b'MZ' or len(image) < 64:
        raise ValueError('Input is not our SDK development image')
    pe = struct.unpack_from('<I', image, 0x3c)[0]
    if pe + 6 > len(image) or image[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H', image, pe+4)[0] != 0x1f2:
        raise ValueError('Expected a PowerPC big-endian executable')
    data[offset:] = image
    struct.pack_into('>H', data, form+4, 0)
    with target.open('xb') as stream:
        stream.write(data)
    # This is deliberately unsigned homebrew, not a Microsoft-signed retail title.
    return target
