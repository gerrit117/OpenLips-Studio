#!/usr/bin/env python3
"""Normalize the observed OG WVC1 bitmap bit-count declaration in a new copy.

This is not a transcoder or a general Xbox compatibility guarantee. The tested
Media Foundation output has biBitCount=0; 74/74 reference OG videos use 24.
Only this two-byte header field is writable; encoded packets stay untouched.
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import tempfile
from pathlib import Path

try:
    from tools.analyze_asf import inspect
except ModuleNotFoundError:
    from analyze_asf import inspect


def normalize(source: Path, output: Path) -> dict:
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise ValueError("output must be a new file, separate from input")
    original = inspect(source)
    videos = [s for s in original['streams'] if s.get('kind') == 'video']
    if len(videos) != 1 or videos[0]['fourcc'] != 'WVC1':
        raise ValueError("requires exactly one WVC1 video stream")
    video = videos[0]
    old_bits = video['bitmap_bit_count']
    if old_bits not in (0, 24):
        raise ValueError(f"unexpected bitmap bit count {old_bits}; refusing to guess")
    if not 40 <= video['bitmap_header_size'] <= len(bytes.fromhex(video['format_hex'])) - 11:
        raise ValueError("bitmap header size outside video format")
    offset = video['format_offset'] + 25
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=output.name + '.', suffix='.tmp', dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w+b') as destination, source.open('rb') as original_file:
            shutil.copyfileobj(original_file, destination)
            destination.seek(offset)
            destination.write(struct.pack('<H', 24))
            destination.flush()
            os.fsync(destination.fileno())
        changed = []
        with source.open('rb') as before, temporary.open('rb') as after:
            position = 0
            while True:
                a, b = before.read(1024 * 1024), after.read(1024 * 1024)
                if len(a) != len(b):
                    raise ValueError("file size changed during normalization")
                if not a:
                    break
                if a != b:
                    for i, (old, new) in enumerate(zip(a, b)):
                        if old != new:
                            if not offset <= position + i < offset + 2:
                                raise ValueError("unexpected change outside bitmap bit-count field")
                            changed.append(position + i)
                position += len(a)
        checked = inspect(temporary)
        if checked['file_size'] != original['file_size'] or any(
                s['bitmap_bit_count'] != 24 for s in checked['streams'] if s.get('kind') == 'video'):
            raise ValueError("normalized header validation failed")
        # Same-directory hard link publishes a complete file without clobbering
        # an output created concurrently. Unsupported filesystems fail safely.
        os.link(temporary, output)
        return dict(output=str(output), file_size=checked['file_size'],
                    field_offset=offset, old_bits=old_bits, new_bits=24,
                    changed_offsets=changed, outside_field_unchanged=True,
                    encoded_packets_unchanged=True)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(normalize(args.input, args.out))
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == '__main__':
    main()
