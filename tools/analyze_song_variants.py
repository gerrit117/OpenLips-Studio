"""Read-only corpus inventory of sequence ownership, duet, short and action markers."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

from tools.walk_ixb_graph import Graph, GraphError


def string_field(graph, record, member):
    info, buffer = graph.vector(record, member, 1)
    return graph.data[buffer.payload:buffer.payload + info['size']].rstrip(b'\0').decode('utf-8') if buffer else ''


def inspect_chart(path):
    data = path.read_bytes()
    row = dict(file=str(path), size=len(data), magic=data[:4].hex(), sha256=hashlib.sha256(data).hexdigest())
    try:
        g = Graph(data)
        inventory = Counter(next(g.lineage(r)).name for r in g.records if r.class_index)
        sequences, events = [], []
        for record in g.records:
            if not g.is_a(record, 'ixSequence'):
                continue
            fields = g.members(record)
            name = string_field(g, record, 'm_strName') if 'm_strName' in fields else ''
            info, codes = g.reference_vector(record, 'm_vpSeqCode', 'ixSeqCode')
            classes = Counter(next(g.lineage(c)).name for c in codes)
            times = [struct.unpack_from('>f', data, c.payload + g.members(c)['m_fTriggerTiming'])[0]
                     for c in codes if 'm_fTriggerTiming' in g.members(c)]
            sequences.append(dict(name=name, key=record.key, size=info['size'], reserve=info['reserve'],
                                  classes=dict(classes), first_time=min(times) if times else None,
                                  last_time=max(times) if times else None))
            for code in codes:
                cls = next(g.lineage(code)).name
                if any(term in cls.lower() for term in ('short', 'gesture', 'action', 'call', 'unison', 'star', 'sectionpattern')):
                    fields = g.members(code)
                    events.append(dict(sequence=name, class_name=cls, key=code.key,
                        fields={name: dict(offset=off, u32=g.u32(code, off))
                                for name, off in fields.items() if off + 4 <= code.size}))
        row.update(status='parsed', records=len(g.records), classes=dict(inventory),
                   schema={c.name: dict(size=c.size, members=c.members) for c in g.document.classes.values()},
                   sequences=sequences, events=events, graph_errors=g.summary()['graph_errors'])
    except (ValueError, KeyError, OSError, struct.error, UnicodeError) as exc:
        row.update(status='unsupported/error', error=str(exc))
    return row


def corpus(roots):
    by_hash, files = {}, []
    for label, root in roots:
        for path in sorted(root.rglob('*')):
            if path.suffix.lower() != '.x360' or path.stem.lower().endswith('_lyric'):
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest not in by_hash:
                by_hash[digest] = inspect_chart(path)
                by_hash[digest]['copies'] = []
            by_hash[digest]['copies'].append(dict(corpus=label, file=str(path)))
            files.append(dict(corpus=label, file=str(path), sha256=digest))
    rows = list(by_hash.values())
    summaries = {}
    for label, _ in roots:
        selected = [r for r in rows if any(c['corpus'] == label for c in r['copies'])]
        parsed = [r for r in selected if r['status'] == 'parsed']
        class_frequency, track_frequency, layout = Counter(), Counter(), defaultdict(Counter)
        for row in parsed:
            class_frequency.update(row['classes'].keys())
            track_frequency.update({s['name'] for s in row['sequences']})
            for cls, fields in row['schema'].items():
                if cls in ('lpsChart', 'ixChart', 'ixSequence', 'lpsShortEndMarker', 'lpsMelodyMarker', 'lpsLyricMarker'):
                    layout[cls][json.dumps(fields, sort_keys=True)] += 1
        summaries[label] = dict(unique_files=len(selected), parsed=len(parsed), unsupported=len(selected) - len(parsed),
            class_occurrence=dict(class_frequency), sequence_name_occurrence=dict(track_frequency),
            schema_layouts={name: [dict(count=n, layout=json.loads(key)) for key, n in values.most_common()]
                           for name, values in layout.items()})
    return dict(physical_files=len(files), unique_files=len(rows), files_analyzed=files, corpora=summaries, charts=rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', action='append', required=True, help='label=directory (repeatable)')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    roots = [(label, Path(path)) for label, path in (v.split('=', 1) for v in args.corpus)]
    if args.out.exists():
        p.error('Output already exists')
    result = corpus(roots)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps(result['corpora'], indent=2))


if __name__ == '__main__':
    main()
