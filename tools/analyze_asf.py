#!/usr/bin/env python3
"""Read-only ASF header inventory; no media decoding or file modifications."""
import argparse
import json
import struct
from collections import Counter
from pathlib import Path
from uuid import UUID


HEADER = UUID('75b22630-668e-11cf-a6d9-00aa0062ce6c').bytes_le
FILE = UUID('8cabdca1-a947-11cf-8ee4-00c00c205365').bytes_le
STREAM = UUID('b7dc0791-a9b7-11cf-8ee6-00c00c205365').bytes_le
AUDIO = UUID('f8699e40-5b4d-11cf-a8fd-00805f5c442b').bytes_le
VIDEO = UUID('bc19efc0-5b4d-11cf-a8fd-00805f5c442b').bytes_le


def inspect(path):
    path = Path(path)
    with path.open('rb') as source:
        prefix = source.read(30)
        if len(prefix) != 30 or prefix[:16] != HEADER:
            raise ValueError('not an ASF header')
        header_size, count = struct.unpack_from('<QI', prefix, 16)
        if header_size < 30 or header_size > min(path.stat().st_size, 16 * 1024 * 1024):
            raise ValueError('invalid or oversized ASF header')
        data = prefix + source.read(header_size - 30)
    result = dict(filename=str(path), file_size=path.stat().st_size,
                  header_size=header_size, header_objects=count, streams=[], objects=[])
    pos = 30
    for _ in range(count):
        if pos + 24 > len(data):
            raise ValueError('truncated ASF object')
        guid, size = data[pos:pos + 16], struct.unpack_from('<Q', data, pos + 16)[0]
        if size < 24 or pos + size > len(data):
            raise ValueError('ASF object outside header')
        payload = data[pos + 24:pos + size]
        result['objects'].append(str(UUID(bytes_le=guid)))
        if guid == FILE:
            if len(payload) < 80:
                raise ValueError('truncated file properties')
            values = struct.unpack_from('<6Q4I', payload, 16)
            result.update(zip(('declared_file_size', 'creation_time', 'packet_count',
                               'play_duration_100ns', 'send_duration_100ns', 'preroll_ms',
                               'flags', 'min_packet', 'max_packet', 'max_bitrate'), values))
        elif guid == STREAM:
            if len(payload) < 54:
                raise ValueError('truncated stream properties')
            length, error_length, flags = struct.unpack_from('<IIH', payload, 40)
            if 54 + length + error_length > len(payload):
                raise ValueError('stream format outside object')
            fmt = payload[54:54 + length]
            stream = dict(number=flags & 0x7f, encrypted=bool(flags & 0x8000),
                          type=str(UUID(bytes_le=payload[:16])), format_hex=fmt.hex())
            if payload[:16] == AUDIO:
                if len(fmt) < 16:
                    raise ValueError('truncated WAVEFORMAT')
                fields = struct.unpack_from('<HHIIHH', fmt)
                stream.update(kind='audio', **dict(zip(('codec_tag', 'channels', 'rate',
                                      'avg_bytes_per_sec', 'block_align', 'bits'), fields)))
            elif payload[:16] == VIDEO:
                if len(fmt) < 51:
                    raise ValueError('truncated video format')
                stream.update(kind='video', width=struct.unpack_from('<I', fmt)[0],
                              height=struct.unpack_from('<I', fmt, 4)[0],
                              fourcc=fmt[27:31].decode('ascii', errors='replace'))
            result['streams'].append(stream)
        pos += size
    if pos != len(data):
        raise ValueError('ASF header count/size mismatch')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args()
    files = sorted(p for p in args.path.rglob('*') if p.suffix.lower() in ('.wmv', '.wma')) if args.path.is_dir() else [args.path]
    rows, failures = [], []
    for path in files:
        try:
            rows.append(inspect(path))
        except (OSError, ValueError, struct.error) as error:
            failures.append(dict(filename=str(path), error=str(error)))
    if args.summary:
        patterns = Counter((r.get('min_packet'), r.get('max_packet'), r.get('preroll_ms'),
                            tuple((s.get('kind'), s.get('codec_tag'), s.get('bits'), s.get('fourcc'))
                                  for s in r['streams'])) for r in rows)
        print(json.dumps(dict(analyzed=len(rows), failures=failures,
                         files=[r['filename'] for r in rows],
                         patterns=[dict(pattern=p, count=n) for p, n in patterns.most_common()]), indent=2))
    else:
        print(json.dumps(dict(files=rows, failures=failures), indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
