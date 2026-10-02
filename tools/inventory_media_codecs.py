"""Read-only codec census across game media roots; extensions are not codecs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from tools.analyze_asf import HEADER, inspect as inspect_asf

EXTENSIONS = {'.wmv', '.wma', '.xwma', '.xma', '.xma2', '.xmv', '.wav'}
CODECS = {0x161: 'WMA Standard', 0x162: 'WMA Pro', 0x160: 'WMA v1',
          0x165: 'XMA', 0x166: 'XMA2', 1: 'PCM'}


def inspect_riff(path):
    with Path(path).open('rb') as stream:
        prefix = stream.read(12)
        if len(prefix) != 12 or prefix[:4] != b'RIFF':
            raise ValueError('not RIFF')
        end = struct.unpack_from('<I', prefix, 4)[0] + 8
        if end > Path(path).stat().st_size or end < 12:
            raise ValueError('invalid RIFF size')
        result = dict(container='RIFF', form=prefix[8:12].decode('ascii', 'replace'),
                      streams=[], chunks=[])
        pos = 12
        while pos < end:
            if pos + 8 > end:
                raise ValueError('truncated RIFF chunk header')
            stream.seek(pos)
            header = stream.read(8)
            tag, length = header[:4], struct.unpack_from('<I', header, 4)[0]
            next_pos = pos + 8 + length + (length & 1)
            if next_pos > end:
                raise ValueError('RIFF chunk outside declared range')
            result['chunks'].append(dict(tag=tag.decode('ascii', 'replace'), size=length, payload_offset=pos + 8))
            if tag == b'fmt ':
                if length < 16:
                    raise ValueError('truncated WAVEFORMAT')
                fmt = stream.read(min(length, 4096))
                fields = struct.unpack_from('<HHIIHH', fmt)
                audio = dict(kind='audio', **dict(zip(('codec_tag', 'channels', 'rate',
                             'avg_bytes_per_sec', 'block_align', 'bits'), fields)))
                audio['codec'] = CODECS.get(fields[0], f'unknown 0x{fields[0]:04x}')
                audio['format_length'] = length
                if length >= 18:
                    audio['extra_size'] = struct.unpack_from('<H', fmt, 16)[0]
                result['streams'].append(audio)
            elif tag == b'dpds':
                if length % 4 or length > 4 * 1024 * 1024:
                    raise ValueError('invalid or oversized dpds table')
                entries = [item[0] for item in struct.iter_unpack('<I', stream.read(length))]
                result['dpds'] = dict(count=len(entries), last_decoded_bytes=entries[-1] if entries else 0,
                                      nondecreasing=all(a <= b for a, b in zip(entries, entries[1:])))
            pos = next_pos
        if not result['streams']:
            raise ValueError('RIFF has no fmt chunk')
        return result


def inspect_media(path):
    with Path(path).open('rb') as stream:
        magic = stream.read(16)
    if magic == HEADER:
        row = inspect_asf(path)
        row['container'] = 'ASF'
        for stream in row['streams']:
            if stream.get('kind') == 'audio':
                stream['codec'] = CODECS.get(stream['codec_tag'], 'unknown')
    elif magic[:4] == b'RIFF':
        row = inspect_riff(path)
    else:
        raise ValueError(f'unsupported container magic={magic.hex()}')
    row.update(filename=str(path), file_size=path.stat().st_size, magic=magic.hex())
    return row


def census(roots):
    rows, failures, seen = [], [], set()
    for label, root in roots:
        root = Path(root).resolve(strict=True)
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                row = inspect_media(path)
                row['group'] = label
                row['relative_path'] = str(path.relative_to(root))
                rows.append(row)
            except (OSError, ValueError, struct.error) as error:
                failures.append(dict(group=label, filename=str(path), error=str(error)))
    patterns = Counter()
    for row in rows:
        for stream in row['streams']:
            patterns[(row['group'], row['container'], stream.get('kind'),
                      stream.get('codec'), stream.get('fourcc'), stream.get('rate'),
                      stream.get('channels'), stream.get('bits'),
                      stream.get('width'), stream.get('height'))] += 1
    return dict(files=rows, failures=failures, file_count=len(rows),
                patterns=[dict(pattern=p, count=n) for p, n in sorted(patterns.items(), key=lambda x: str(x[0]))],
                caveat='Path counts, not unique assets. Copies in different roots may repeat. Corpus usage does not prove decoder acceptance.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', required=True, metavar='LABEL=PATH')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    roots = []
    for entry in args.root:
        label, separator, path = entry.partition('=')
        if not separator or not label or not path:
            parser.error('--root requires LABEL=PATH')
        roots.append((label, path))
    report = census(roots)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
