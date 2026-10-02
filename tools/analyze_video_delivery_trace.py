#!/usr/bin/env python3
"""Summarize bounded read-only OG video delivery probes; never open game files."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def summarize(text):
    groups = defaultdict(list)
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        row = dict(token.split('=', 1) for token in line.split())
        if 'site' not in row:
            raise ValueError(f'line {number}: missing site')
        if row['site'] == '824B1DC8':
            groups[(row['owner'], row['demux'])].append(row)
    result = []
    for (owner, demux), rows in groups.items():
        readable = [(r, (int(r['time_hi'], 16) << 32) | int(r['time_lo'], 16))
                    for r in rows if r.get('time_hi') not in (None, 'unreadable')
                    and r.get('time_lo') not in (None, 'unreadable')]
        timestamps = [time for _, time in readable]
        result.append(dict(owner=owner, demux=demux, observations=len(rows),
                           last_hit=int(rows[-1]['hit']),
                           timestamp_first_ms=timestamps[0] if timestamps else None,
                           timestamp_last_ms=timestamps[-1] if timestamps else None,
                           timestamp_unique=len(set(timestamps)),
                           consecutive_timestamp_deltas_ms=dict(Counter(
                               b - a for (previous, a), (current, b) in zip(readable, readable[1:])
                               if int(current['hit']) == int(previous['hit']) + 1)),
                           timestamp_regressions=sum(b < a for a, b in zip(timestamps, timestamps[1:])),
                           sampled_frame_hashes=len({r['frame_sample_hash'] for r in rows if 'frame_sample_hash' in r}),
                           delivery_statuses=dict(Counter(r.get('delivery_status', 'not_captured') for r in rows)),
                           written_bytes=dict(Counter(r['written'] for r in rows)),
                           eof_values=dict(Counter(r['eof'] for r in rows))))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces', type=Path, nargs='+')
    args = parser.parse_args()
    for path in args.traces:
        print(json.dumps(dict(file=path.name, objects=summarize(path.read_text(encoding='utf-8'))), indent=2))


if __name__ == '__main__':
    main()
