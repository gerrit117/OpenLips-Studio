"""Read-only page statistics from owned IXB sequences and matched lyric resources."""
import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
from types import SimpleNamespace

from tools.walk_ixb_graph import Graph
from tools.analyze_song_variants import string_field
from tools.analyze_lyric_file import select_text_resource


def distribution(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    def percentile(q):
        index = (len(values) - 1) * q
        low, high = math.floor(index), math.ceil(index)
        return round(values[low] + (values[high] - values[low]) * (index - low), 4)
    return dict(count=len(values), min=values[0], max=values[-1],
                mean=round(statistics.mean(values), 4),
                **{f'p{q}': percentile(q / 100) for q in (10, 25, 50, 75, 90, 95, 99)})


def timing(graph, record, field='m_fTriggerTiming'):
    return struct.unpack_from('>f', graph.data, record.payload + graph.members(record)[field])[0]


def inspect_pair(chart, lyric):
    graph = Graph(chart.read_bytes())
    sequences = {}
    for record in graph.records:
        if graph.is_a(record, 'ixSequence'):
            name = string_field(graph, record, 'm_strName')
            _, codes = graph.reference_vector(record, 'm_vpSeqCode', 'ixSeqCode')
            sequences.setdefault(name, []).append(codes)
    sections = sequences.get('Section', [])
    if len(sections) != 1:
        raise ValueError('Expected one explicit Section sequence')
    page_codes = [code for code in sections[0] if graph.is_a(code, 'lpsPageBreakMarker')]
    cuts = sorted(set(timing(graph, code) for code in page_codes))
    if not cuts or any(not math.isfinite(t) for t in cuts):
        raise ValueError('No valid page timings')
    all_lyrics = [r for r in graph.records if graph.is_a(r, 'lpsLyricMarker')]
    coverage_markers, fragments = [], {}
    for marker in all_lyrics:
        info, buffer = graph.vector(marker, 'm_vecLyricWordData', 20)
        spans = []
        for index in range(info['size']):
            offset, length = graph.u32(buffer, index * 20 + 4), graph.u32(buffer, index * 20 + 8)
            spans.append((offset, length))
            coverage_markers.append(SimpleNamespace(text_offset=offset, text_length=length))
        fragments[marker.key] = spans
    raw = lyric.read_bytes()
    selection = select_text_resource(raw, coverage_markers)
    if not selection.resource:
        raise ValueError('No matching lyric Text resource')
    resource = selection.resource
    text = raw[resource.payload_start:resource.payload_end].decode('utf-8')
    tracks = []
    for name, groups in sequences.items():
        if name != 'Lyric' and not name.startswith('Lyric_Duet'):
            continue
        melody_name = name.replace('Lyric', 'Melody', 1)
        if len(groups) != 1 or len(sequences.get(melody_name, [])) != 1:
            continue
        melodies = [r for r in sequences[melody_name][0] if graph.is_a(r, 'lpsMelodyMarker')]
        lyrics = sorted((r for r in groups[0] if graph.is_a(r, 'lpsLyricMarker')),
                        key=lambda r: (timing(graph, r), r.index))
        if not melodies or not lyrics:
            continue
        # Include the pre-first-cut interval explicitly instead of discarding it.
        windows = [-math.inf] + cuts
        pages = [dict(cut=None if i == 0 else cuts[i - 1], notes=[], lyrics=[]) for i in range(len(windows))]
        for melody in melodies:
            pages[bisect_right(cuts, timing(graph, melody))]['notes'].append(melody)
        for marker in lyrics:
            pages[bisect_right(cuts, timing(graph, marker))]['lyrics'].append(marker)
        results, anomalies = [], Counter()
        melody_keys = {r.key for r in melodies}
        for marker in lyrics:
            linked_key = graph.u32(marker, graph.members(marker)['m_pMelodyMarker'])
            if not linked_key:
                anomalies['null_lyric_melody_link'] += 1
                continue
            linked = graph.ref(linked_key)
            if linked.key not in melody_keys:
                anomalies['lyric_link_outside_melody_sequence'] += 1
            if bisect_right(cuts, timing(graph, linked)) != bisect_right(cuts, timing(graph, marker)):
                anomalies['lyric_link_in_different_page'] += 1
        for index, page in enumerate(pages):
            if not page['lyrics']:
                continue
            parts, previous_span, offsets = [], None, []
            for marker in page['lyrics']:
                spans = fragments[marker.key]
                for span in spans:
                    offset, length = span
                    if offset + length > len(text):
                        anomalies['text_range_out_of_bounds'] += 1
                        continue
                    if span != previous_span:
                        parts.append(text[offset:offset + length])
                        offsets.append(span)
                    previous_span = span
                if graph.u32(marker, graph.members(marker)['m_bEndOfWord']):
                    parts.append(' ')
            visible = ' '.join(''.join(parts).strip('\ufeff\x00').split())
            if not visible:
                anomalies['empty_visible_page'] += 1
                continue
            if not page['notes']:
                anomalies['lyrics_without_matching_page_notes'] += 1
                continue
            starts = [timing(graph, note) for note in page['notes']]
            ends = [timing(graph, note) + timing(graph, note, 'm_fLength') for note in page['notes']]
            first, last = min(starts), max(ends)
            row = dict(index=index, characters=len(visible), words=len(visible.split()),
                       notes=len(page['notes']), lyric_markers=len(page['lyrics']),
                       note_span_seconds=last - first,
                       first_note=first, last_note_end=last, cut=page['cut'])
            durations = [timing(graph, note, 'm_fLength') for note in page['notes']]
            row['note_durations'] = durations
            row['shortest_note_seconds'] = min(durations)
            if last > first:
                row['shortest_note_span_fraction'] = min(durations) / (last - first)
            if page['cut'] is not None:
                row['lead_seconds'] = first - page['cut']
            if index + 1 < len(pages):
                row['next_cut'] = cuts[index]
                row['switch_after_note_end_seconds'] = cuts[index] - last
                if page['cut'] is not None:
                    row['page_interval_seconds'] = cuts[index] - page['cut']
                following = [r for p in pages[index + 1:] for r in p['notes']]
                if following:
                    row['gap_to_next_notes_seconds'] = min(timing(graph, r) for r in following) - last
            last_lyric = page['lyrics'][-1]
            row['last_lyric_end_word'] = bool(graph.u32(last_lyric, graph.members(last_lyric)['m_bEndOfWord']))
            if offsets:
                end = offsets[-1][0] + offsets[-1][1]
                tail = text[end:]
                whitespace = tail[:len(tail) - len(tail.lstrip())]
                row['resource_newline_after'] = '\n' in whitespace or '\r' in whitespace
                row['resource_word_separator_after'] = bool(whitespace)
            results.append(row)
        tracks.append(dict(name=name, pages=results, anomalies=dict(anomalies)))
    return dict(page_markers=len(page_codes), unique_page_timings=len(cuts),
                page_marker_track_indices=dict(Counter(str(graph.u32(code, graph.members(code)['m_iTrackIndex'])) for code in page_codes)),
                text_coverage=selection.coverage.coverage_ratio if selection.coverage else None,
                tracks=tracks)


def summarize(rows, duet=False):
    valid = [row for row in rows if row.get('status') == 'parsed']
    normal = [(row, track) for row in valid for track in row['tracks']
              if (track['name'].startswith('Lyric_Duet') if duet else track['name'] == 'Lyric')]
    pages = [page for _, track in normal for page in track['pages']]
    metrics = ('characters', 'words', 'notes', 'lyric_markers', 'note_span_seconds', 'lead_seconds',
               'switch_after_note_end_seconds', 'gap_to_next_notes_seconds',
               'shortest_note_seconds', 'shortest_note_span_fraction', 'page_interval_seconds')
    transitions = [p for p in pages if 'gap_to_next_notes_seconds' in p]
    durations = [length for p in pages for length in p['note_durations']]
    return dict(unique_pairs=len(rows), parsed=len(valid), normal_tracks=len(normal), nonempty_normal_pages=len(pages),
        note_duration_distribution=distribution(durations),
        short_note_occurrences={label: dict(notes=sum(length < limit for length in durations),
            tracks=sum(any(length < limit for p in t['pages'] for length in p['note_durations'])
                       for _, t in normal)) for label, limit in (('under_100ms', .1), ('under_150ms', .15))},
        transition_count=len(transitions),
        transition_occurrences={key: sum(predicate(p) for p in transitions)
            for key, predicate in (
                ('word_end', lambda p: p['last_lyric_end_word']),
                ('resource_newline', lambda p: p.get('resource_newline_after', False)),
                ('at_or_after_note_end', lambda p: p['switch_after_note_end_seconds'] >= -0.0001),
                ('within_100ms_after_note_end', lambda p: -.0001 <= p['switch_after_note_end_seconds'] <= .1))},
        anomalies={key: sum(t['anomalies'].get(key, 0) for _, t in normal)
                   for key in sorted({k for _, t in normal for k in t['anomalies']})},
        distributions={key: distribution([page[key] for page in pages if key in page]) for key in metrics},
        page_occurrences={key: sum(bool(page.get(key)) for page in pages)
                          for key in ('last_lyric_end_word', 'resource_newline_after', 'resource_word_separator_after')},
        file_occurrences={key: sum(any(bool(p.get(key)) for p in track['pages']) for _, track in normal)
                          for key in ('last_lyric_end_word', 'resource_newline_after', 'resource_word_separator_after')},
        thresholds={label: dict(pages=sum(predicate(p) for p in pages),
                               files=sum(any(predicate(p) for p in track['pages']) for _, track in normal))
                    for label, predicate in [('chars_over_30', lambda p: p['characters'] > 30),
                                              ('notes_over_8', lambda p: p['notes'] > 8),
                                              ('span_over_3', lambda p: p['note_span_seconds'] > 3),
                                              ('chars_over_42', lambda p: p['characters'] > 42),
                                              ('notes_over_16', lambda p: p['notes'] > 16),
                                              ('span_over_8', lambda p: p['note_span_seconds'] > 8)]})


def corpus(roots, lyric_root):
    rows, physical, used_lyrics = {}, [], set()
    sample_lyrics = {p.name.casefold(): p for p in lyric_root.rglob('*')
                     if p.suffix.lower() == '.x360' and p.stem.lower().endswith('_lyric')}
    for label, root in roots:
        for chart in sorted(p for p in root.rglob('*') if p.suffix.lower() == '.x360' and not p.stem.lower().endswith('_lyric')):
            name = chart.stem.removesuffix('_Cht') + '_Lyric' + chart.suffix
            lyric = chart.with_name(name)
            if not lyric.is_file():
                lyric = sample_lyrics.get(name.casefold())
            digest = hashlib.sha256(chart.read_bytes()).hexdigest()
            lyric_digest = hashlib.sha256(lyric.read_bytes()).hexdigest() if lyric and lyric.is_file() else None
            key = (digest, lyric_digest)
            copy = dict(corpus=label, chart=str(chart.resolve()), lyric=str(lyric.resolve()) if lyric else None)
            physical.append(copy)
            if lyric:
                used_lyrics.add(lyric.resolve())
            if key not in rows:
                row = dict(sha256=digest, lyric_sha256=lyric_digest, copies=[])
                try:
                    if not lyric:
                        raise ValueError('Missing matching lyric file')
                    row.update(inspect_pair(chart, lyric), status='parsed')
                except (ValueError, KeyError, OSError, struct.error) as error:
                    row.update(status='unsupported/error', error=str(error))
                rows[key] = row
            rows[key]['copies'].append(copy)
    result = list(rows.values())
    all_lyrics = set(p.resolve() for p in sample_lyrics.values())
    for _, root in roots:
        all_lyrics.update(p.resolve() for p in root.rglob('*')
                          if p.suffix.lower() == '.x360' and p.stem.lower().endswith('_lyric'))
    return dict(physical_chart_files=len(physical), physical_lyric_files=len(used_lyrics),
                available_lyric_files=len(all_lyrics),
                unpaired_lyric_files=sorted(str(p) for p in all_lyrics - used_lyrics),
                files_analyzed=physical, summary=summarize(result), duet_summary=summarize(result, duet=True),
                corpora={label: summarize([row for row in result if any(c['corpus'] == label for c in row['copies'])]) for label, _ in roots},
                pairs=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', action='append', required=True)
    parser.add_argument('--lyric-root', type=Path, default=Path('private/samples/lyrics'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output already exists')
    roots = [(label, Path(root)) for label, root in (value.split('=', 1) for value in args.corpus)]
    result = corpus(roots, args.lyric_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
