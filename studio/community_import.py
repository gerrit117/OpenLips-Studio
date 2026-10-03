"""Read a checked native community song into editable project notes."""
from pathlib import Path
import tempfile
import os
from PySide6.QtCore import QStandardPaths
from studio.model import StudioProject, EditorNote
from tools.song_bundle import decode_bundle, MAX_BUNDLE
from tools.walk_ixb_graph import Graph


def import_community(path):
    path = Path(path)
    if path.stat().st_size > MAX_BUNDLE:
        raise ValueError('Community song exceeds the supported size')
    bundle = decode_bundle(path.read_bytes())
    chart, lyric = Graph(bundle.chart), Graph(bundle.lyric)
    # Validation already requires complete coverage; select the matching owned
    # Text buffer rather than a printable run or guessed BOM range.
    resources = []
    for record in lyric.records:
        if lyric.is_a(record, 'ixRawFileImage'):
            info, buffer = lyric.vector(record, 'm_vData', 1)
            type_info, type_buffer = lyric.vector(record, 'm_strTypeName', 1)
            if type_buffer and bundle.lyric[type_buffer.payload:type_buffer.payload + type_info['size']].rstrip(b'\0') == b'Text' and buffer:
                resources.append(bundle.lyric[buffer.payload:buffer.payload + info['size']].decode('utf-8'))
    mappings = {}
    for record in chart.records:
        if chart.is_a(record, 'lpsLyricMarker'):
            members = chart.members(record)
            info, buffer = chart.vector(record, 'm_vecLyricWordData', 20)
            ranges = [(chart.u32(buffer, i * 20 + 4), chart.u32(buffer, i * 20 + 8)) for i in range(info['size'])]
            mappings[chart.u32(record, members['m_pMelodyMarker'])] = (ranges, bool(chart.u32(record, members['m_bEndOfWord'])))
    text = next((text for text in sorted(resources, key=len, reverse=True)
                 if all(start + size <= len(text) for ranges, _ in mappings.values() for start, size in ranges)), None)
    if text is None:
        raise ValueError('Could not resolve community lyrics')
    notes = []
    for record in chart.records:
        if chart.is_a(record, 'lpsMelodyMarker') and not chart.is_a(record, 'lpsPhraseMarker'):
            values = chart.melody_values(record)
            ranges, end_word = mappings.get(record.key, ([], True))
            notes.append(EditorNote(values['time'], values['length'], values['track_index'],
                                    ''.join(text[start:start + size] for start, size in ranges), end_word))
    metadata = bundle.manifest['metadata']
    project = StudioProject(title=metadata['title'], artist=metadata['artist'], notes=notes,
                            source='OpenLips Song', video_reference=bundle.manifest['media']['reference_video'] or '')
    project.validate()
    root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'community-imports'
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='song-', dir=root))
    (folder / 'cover.jpg').write_bytes(bundle.cover)
    project.cover_path = str(folder / 'cover.jpg')
    return project
