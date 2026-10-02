"""Read-only ASR comparison with matching IXB lyrics. Reports, not sample data, may be shared."""
import argparse
import json
from pathlib import Path
import struct
from types import SimpleNamespace

from studio.ai_chart import word_error_rate
from tools.analyze_lyric_file import select_text_resource
from tools.walk_ixb_graph import Graph
from tools.analyze_song_variants import string_field


def reference(chart, lyric):
    graph = Graph(chart.read_bytes())
    groups = []
    for sequence in graph.records:
        if not graph.is_a(sequence, 'ixSequence'):
            continue
        _, codes = graph.reference_vector(sequence, 'm_vpSeqCode', 'ixSeqCode')
        markers = []
        for record in codes:
            if not graph.is_a(record, 'lpsLyricMarker'):
                continue
            members = graph.members(record)
            info, buffer = graph.vector(record, 'm_vecLyricWordData', 20)
            for index in range(info['size']):
                markers.append(SimpleNamespace(
                    time=struct.unpack_from('>f', graph.data, record.payload + members['m_fTriggerTiming'])[0],
                    text_offset=graph.u32(buffer, index * 20 + 4),
                    text_length=graph.u32(buffer, index * 20 + 8),
                    end_of_word=graph.u32(record, members['m_bEndOfWord']),
                    object_index=record.index))
        if markers:
            groups.append((sequence.key, string_field(graph, sequence, 'm_strName'), markers))
    markers = [m for _, _, group in groups for m in group]
    data = lyric.read_bytes()
    selected = select_text_resource(data, markers)
    if not selected.resource:
        raise ValueError('No lyric Text resource selected by chart coverage')
    resource = selected.resource
    text = data[resource.payload_start:resource.payload_end].decode('utf-8', errors='replace')
    return groups, text, selected


def reference_words(chart, lyric, duration, sequence='Lyric'):
    groups, text, _ = reference(chart, lyric)
    matches = [group for _, name, group in groups if name == sequence]
    if len(matches) != 1:
        raise ValueError('Expected one explicit lyric sequence')
    seen, result, fragment, start = set(), [], '', None
    for marker in sorted(matches[0], key=lambda m: (m.time, m.object_index)):
        identity = (round(marker.time, 4), marker.text_offset, marker.text_length)
        if identity in seen or not 0 <= marker.time < duration:
            continue
        seen.add(identity)
        part = text[marker.text_offset:marker.text_offset + marker.text_length].strip('\ufeff\x00 \r\n')
        if '\ufffd' in part:
            raise ValueError('Reference contains non-UTF-8 bytes')
        if start is None:
            start = marker.time
        fragment += part
        if marker.end_of_word:
            if fragment:
                result.append(dict(time=start, text=fragment))
            fragment, start = '', None
    if fragment:
        result.append(dict(time=start, text=fragment))
    return result


def write_reference_lrc(chart, lyric, output, duration, window_words=6):
    words = reference_words(chart, lyric, duration)
    lines = []
    for index in range(0, len(words), window_words):
        group = words[index:index + window_words]
        milliseconds = round(group[0]['time'] * 1000)
        minute, remainder = divmod(milliseconds, 60000)
        second, fraction = divmod(remainder, 1000)
        lines.append(f'[{minute:02}:{second:02}.{fraction:03}]' + ' '.join(w['text'] for w in group))
    with output.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines) + '\n')
    return dict(words=len(words), windows=len(lines), source='structural normal-track reference; six-word test windows')


def compare(chart, lyric, analysis):
    groups, text, selected = reference(chart, lyric)
    report = json.loads(analysis.read_text(encoding='utf-8'))
    duration = report['duration']
    # Duplicate game-mode copies must not multiply the reference transcript.
    hypothesis = ' '.join(w['text'] for w in report['words'])
    comparisons = []
    for key, name, group in groups:
        seen, fragments = set(), []
        for marker in sorted(group, key=lambda m: (m.time, m.object_index)):
            identity = (round(marker.time, 4), marker.text_offset, marker.text_length)
            if identity in seen or not 0 <= marker.time < duration:
                continue
            seen.add(identity)
            fragment = text[marker.text_offset:marker.text_offset + marker.text_length].strip('\ufeff\x00 \r\n')
            if '\ufffd' in fragment:
                raise ValueError('Reference marker resolves into non-UTF-8 bytes')
            if fragment:
                fragments.append(fragment + (' ' if marker.end_of_word else ''))
        if fragments:
            comparisons.append(dict(sequence_key=f'0x{key:x}', sequence_name=name,
                                    **word_error_rate(''.join(fragments), hypothesis)))
    return dict(chart=chart.name, lyric=lyric.name, analysis=analysis.name,
                selected_by=selected.selected_by, coverage=selected.coverage.coverage_ratio,
                duration=duration, asr_model=report.get('asr_model'),
                separation=report['separation'], note_count=report['note_count'],
                elapsed_seconds=report['elapsed_seconds'],
                reference_mode='separate structural sequences; mode identity not assumed',
                sequence_comparisons=comparisons)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--chart', type=Path, required=True)
    p.add_argument('--lyric', type=Path, required=True)
    p.add_argument('--analysis', type=Path)
    p.add_argument('--out-lrc', type=Path)
    p.add_argument('--duration', type=float, default=60)
    args = p.parse_args()
    if args.out_lrc:
        print(json.dumps(write_reference_lrc(args.chart, args.lyric, args.out_lrc, args.duration)))
    elif args.analysis:
        print(json.dumps(compare(args.chart, args.lyric, args.analysis), indent=2))
    else:
        p.error('Use --analysis or --out-lrc')


if __name__ == '__main__':
    main()
