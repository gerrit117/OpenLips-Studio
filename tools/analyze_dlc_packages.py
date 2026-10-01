#!/usr/bin/env python3
"""Read-only comparison of STFS headers and already extracted DLC manifests."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET


def header_info(path):
    with Path(path).open('rb') as stream:
        header = stream.read(0x400)
    if len(header) != 0x400 or header[:4] not in (b'LIVE', b'PIRS', b'CON '):
        raise ValueError(f'not an STFS header: {path}')
    def integer(offset, size=4):
        return int.from_bytes(header[offset:offset + size], 'big')
    licenses = []
    for offset in range(0x22C, 0x32C, 16):
        record = header[offset:offset + 16]
        if any(record):
            licenses.append(dict(id=record[:8].hex(), bits=integer(offset + 8),
                                 flags=integer(offset + 12)))
    return dict(filename=Path(path).name, file_bytes=Path(path).stat().st_size,
                filename_length=len(Path(path).name),
                filename_hex42=bool(re.fullmatch('[0-9a-fA-F]{42}', Path(path).name)),
                filename_header_hash_prefix=Path(path).name[:40].lower() == header[0x32C:0x340].hex(),
                header_sha1=header[0x32C:0x340].hex(),
                magic=header[:4].decode('ascii'), header_size=integer(0x340),
                content_type=integer(0x344), metadata_version=integer(0x348),
                content_size=integer(0x34C, 8), media_id=integer(0x354),
                version=integer(0x358), base_version=integer(0x35C),
                title_id=f'{integer(0x360):08X}', platform=header[0x364],
                executable_type=header[0x365], disc_number=header[0x366],
                discs_in_set=header[0x367], savegame_id=integer(0x368),
                profile_id=header[0x371:0x379].hex(),
                volume_flags=header[0x37B], licenses=licenses)


def manifest_info(directory):
    directory = Path(directory)
    raw = (directory / 'DLC.xml').read_bytes()
    root = ET.fromstring(raw)
    files = {p.name.casefold(): p.name for p in directory.iterdir() if p.is_file()}
    entries = {}
    missing = []
    for group, element in [('music', 'MusicIndices/MusicIndex'),
                           ('video', 'MusicVideos/MusicVideo')]:
        entries[group] = []
        for node in root.findall(element):
            fields = {child.tag: child.text or '' for child in node}
            entries[group].append(fields)
            for key, value in fields.items():
                if key.endswith('Uri') and value and value.casefold() not in files:
                    missing.append(dict(field=key, value=value))
    charts = []
    try:
        from tools.walk_ixb_graph import Graph
    except ModuleNotFoundError:
        from walk_ixb_graph import Graph
    for node in entries['music']:
        actual = files.get(node.get('ChartUri', '').casefold())
        if not actual:
            continue
        data = (directory / actual).read_bytes()
        chart = dict(filename=actual, bytes=len(data), magic=data[:4].hex())
        try:
            graph = Graph(data)
            chart['class_sizes'] = {c.name: c.size for c in graph.document.classes.values()
                                    if c.name in ('lpsChart', 'ixChart', 'ixSequence', 'lpsMelodyMarker')}
            chart['melodies'] = sum(graph.is_a(r, 'lpsMelodyMarker') for r in graph.records if r.class_index)
            chart['objects'] = len(graph.records)
        except ValueError as error:
            chart['structural_error'] = str(error)
        charts.append(chart)
    return dict(xml_bytes=len(raw), utf8_bom=raw.startswith(b'\xef\xbb\xbf'),
                root=root.tag, files=sorted(files.values()),
                license_bits=root.findtext('LicenseBits'),
                license_attributes=dict(root.find('LicenseBits').attrib) if root.find('LicenseBits') is not None else {},
                entries=entries, missing_uri_files=missing, charts=charts)


def compare(originals, extracted, custom, custom_extracted):
    references = [dict(header=header_info(p), manifest=manifest_info(extracted / p.name))
                  for p in sorted(originals.iterdir()) if p.is_file()]
    fields = Counter()
    music_count = 0
    for package in references:
        for entry in package['manifest']['entries']['music']:
            fields.update(entry.keys())
            music_count += 1
    return dict(sample_count=len(references), music_entry_count=music_count,
                music_field_occurrence=dict(sorted(fields.items())),
                originals=references,
                custom=dict(header=header_info(custom), manifest=manifest_info(custom_extracted)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--originals', type=Path, required=True)
    p.add_argument('--extracted', type=Path, required=True)
    p.add_argument('--custom', type=Path, required=True)
    p.add_argument('--custom-extracted', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(compare(args.originals, args.extracted, args.custom, args.custom_extracted),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
