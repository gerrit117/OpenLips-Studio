"""Read only XEX2 optional-header identity; no decryption, patching or execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def identity(path):
    data = path.read_bytes()
    if data[:4] != b'XEX2' or len(data) < 24:
        raise ValueError('Not XEX2')
    count = struct.unpack_from('>I', data, 20)[0]
    if count > 1024 or 24 + count * 8 > len(data):
        raise ValueError('Invalid optional header table')
    headers = dict(struct.unpack_from('>II', data, 24 + i * 8) for i in range(count))
    result = dict(file=str(path), size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  optional_headers={f'0x{k:x}': f'0x{v:x}' for k, v in headers.items()})
    offset = headers.get(0x40006)
    if offset is not None:
        if offset + 24 > len(data):
            raise ValueError('Execution identity out of bounds')
        media, version, base, title = struct.unpack_from('>4I', data, offset)
        result.update(title_id=f'{title:08X}', media_id=f'{media:08X}', version=f'{version:08X}', base_version=f'{base:08X}')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('files', type=Path, nargs='+')
    print(json.dumps([identity(path) for path in p.parse_args().files], indent=2))
