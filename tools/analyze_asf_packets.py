#!/usr/bin/env python3
"""Read-only fixed-packet ASF payload/fragment inventory, without decoding media."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct
from uuid import UUID

try:
    from tools.analyze_asf import inspect
except ModuleNotFoundError:
    from analyze_asf import inspect

DATA = UUID('75b22636-668e-11cf-a6d9-00aa0062ce6c').bytes_le


def packet_payloads(data):
    pos = 0

    def take(count):
        nonlocal pos
        if count < 0 or pos + count > len(data):
            raise ValueError('truncated ASF packet field')
        value = data[pos:pos + count]
        pos += count
        return value

    def variable(code):
        return int.from_bytes(take((0, 1, 2, 4)[code]), 'little')

    if not data:
        raise ValueError('empty packet')
    if data[0] & 0x80:
        correction = take(1)[0]
        if correction & 0x70:
            raise ValueError('unsupported error correction layout')
        take(correction & 0x0f)
    flags, properties = take(2)
    length = variable((flags >> 5) & 3) or len(data)
    variable((flags >> 1) & 3)
    padding = variable((flags >> 3) & 3)
    send_time = int.from_bytes(take(4), 'little')
    take(2)
    end = length - padding
    if end > len(data) or end < pos:
        raise ValueError('invalid packet length/padding')
    if flags & 1:
        payload_flags = take(1)[0]
        count, length_code = payload_flags & 0x3f, payload_flags >> 6
        if not length_code:
            raise ValueError('unsupported multiple payload length encoding')
    else:
        count, length_code = 1, 0
    rows = []
    for _ in range(count):
        stream = variable((properties >> 6) & 3)
        number = variable((properties >> 4) & 3)
        offset = variable((properties >> 2) & 3)
        replicated = take(variable(properties & 3))
        if pos > end:
            raise ValueError('payload header outside packet data')
        size = variable(length_code) if flags & 1 else end - pos
        if pos + size > end:
            raise ValueError('payload outside packet data')
        take(size)
        rows.append(dict(stream=stream & 0x7f, object_number=number,
                         offset=offset, bytes=size, replicated_length=len(replicated),
                         object_size=int.from_bytes(replicated[:4], 'little') if len(replicated) >= 8 else None,
                         timestamp_ms=int.from_bytes(replicated[4:8], 'little') if len(replicated) >= 8 else None,
                         extension_hex=replicated[8:].hex(), send_time_ms=send_time))
    if pos != end:
        raise ValueError('unconsumed packet data')
    return rows


def analyze(path):
    header = inspect(path)
    if header['min_packet'] != header['max_packet'] or not header['min_packet']:
        raise ValueError('only fixed-size packet files supported by this diagnostic')
    streams = defaultdict(list)
    with Path(path).open('rb') as source:
        source.seek(header['header_size'])
        data_header = source.read(50)
        if len(data_header) != 50 or data_header[:16] != DATA:
            raise ValueError('ASF Data object not directly after header')
        data_size = struct.unpack_from('<Q', data_header, 16)[0]
        count = struct.unpack_from('<Q', data_header, 40)[0]
        if count != header['packet_count'] or data_size != 50 + count * header['min_packet']:
            raise ValueError('Data object packet count/size mismatch')
        for index in range(count):
            packet = source.read(header['min_packet'])
            if len(packet) != header['min_packet']:
                raise ValueError(f'truncated packet {index}')
            for row in packet_payloads(packet):
                row['packet_index'] = index
                streams[row['stream']].append(row)
    result = []
    for stream, rows in streams.items():
        starts = [r for r in rows if r['offset'] == 0 and r['object_size'] is not None]
        issues, active, consumed = [], None, 0
        for r in rows:
            if r['object_size'] is None:
                continue
            if r['offset'] == 0:
                if active and consumed != active['object_size']:
                    issues.append(dict(packet=active['packet_index'], reason='incomplete object', consumed=consumed, size=active['object_size']))
                active, consumed = r, 0
            if not active or r['object_number'] != active['object_number'] or r['offset'] != consumed:
                issues.append(dict(packet=r['packet_index'], reason='fragment number/offset discontinuity'))
            consumed = r['offset'] + r['bytes']
        if active and consumed != active['object_size']:
            issues.append(dict(packet=active['packet_index'], reason='incomplete final object'))
        result.append(dict(stream=stream, payloads=len(rows), object_starts=len(starts),
                           unvalidated_payloads=sum(r['object_size'] is None for r in rows),
                           replicated_lengths=dict(Counter(r['replicated_length'] for r in rows)),
                           extensions=dict(Counter(r['extension_hex'] for r in rows)),
                           fragment_issue_count=len(issues), fragment_issues=issues[:20],
                           first=starts[:3], around_512=starts[509:515], last=starts[-1:] ))
    return dict(filename=str(path), packet_count=header['packet_count'], streams=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', type=Path, nargs='+')
    args = parser.parse_args()
    for path in args.files:
        print(json.dumps(analyze(path), indent=2))


if __name__ == '__main__':
    main()
