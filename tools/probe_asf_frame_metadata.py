"""Experimental ASF copy with reference frame-duration metadata; not a codec fix."""
import argparse
import os
from pathlib import Path
import shutil
import struct
import tempfile

from tools.analyze_asf import EXTENSION, EXTENDED_STREAM, FILE, inspect


def build(source, reference, output):
    source, reference, output = map(lambda p: Path(p).resolve(), (source, reference, output))
    if output.exists() or output in (source, reference):
        raise ValueError('output must be a new separate file')
    before, ref = inspect(source), inspect(reference)
    if before['extended_streams']:
        raise ValueError('probe requires missing extended stream metadata')
    ids = {s['number']: s.get('kind') for s in before['streams']}
    if ids != {s['number']: s.get('kind') for s in ref['streams']}:
        raise ValueError('reference stream IDs/types differ')
    video_ids = {n for n, kind in ids.items() if kind == 'video'}
    durations = {s['number']: s['average_time_per_frame_100ns'] for s in ref['extended_streams']
                 if s['number'] in video_ids}
    if len(video_ids) != 1 or set(durations) != video_ids or not all(0 < n <= 10000000 for n in durations.values()):
        raise ValueError('reference needs exactly one valid video frame duration')
    with source.open('rb') as f:
        header = bytearray(f.read(before['header_size']))
    positions, pos = [], 30
    for _ in range(before['header_objects']):
        size = struct.unpack_from('<Q', header, pos + 16)[0]
        positions.append((bytes(header[pos:pos + 16]), pos, size))
        pos += size
    extensions = [(p, size) for guid, p, size in positions if guid == EXTENSION]
    files = [p for guid, p, _ in positions if guid == FILE]
    if len(extensions) != 1 or len(files) != 1:
        raise ValueError('requires one header extension and one file properties object')
    ep, es = extensions[0]
    additions = bytearray()
    for number, duration in durations.items():
        body = bytearray(64)
        struct.pack_into('<I', body, 44, 2)  # Seekable, no payload extensions.
        struct.pack_into('<H', body, 48, number)
        struct.pack_into('<Q', body, 52, duration)
        additions += EXTENDED_STREAM + struct.pack('<Q', 88) + body
    delta = len(additions)
    struct.pack_into('<Q', header, 16, len(header) + delta)
    struct.pack_into('<Q', header, files[0] + 40, before['file_size'] + delta)
    struct.pack_into('<Q', header, ep + 16, es + delta)
    struct.pack_into('<I', header, ep + 42, es - 46 + delta)
    header[ep + es:ep + es] = additions
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=output.parent, prefix='.asf-frame-probe-')
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as dst, source.open('rb') as src:
            dst.write(header)
            src.seek(before['header_size'])
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        checked = inspect(temporary)
        if checked['file_size'] != before['file_size'] + delta:
            raise ValueError('size validation failed')
        # Preserve every byte after the header, including all compressed packets.
        with source.open('rb') as a, temporary.open('rb') as b:
            a.seek(before['header_size'])
            b.seek(checked['header_size'])
            while True:
                chunk = a.read(1024 * 1024)
                if b.read(len(chunk)) != chunk:
                    raise ValueError('data outside header changed')
                if not chunk:
                    break
        os.link(temporary, output)
        return dict(output=str(output), added_bytes=delta,
                    extended_streams=checked['extended_streams'], encoded_data_unchanged=True,
                    game_acceptance='not_tested')
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.input, args.reference, args.out))


if __name__ == '__main__':
    main()
