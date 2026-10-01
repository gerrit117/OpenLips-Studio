"""Adapters to existing validated OG authoring tools; never rebuild via templates."""
from pathlib import Path
import json
import os
import tempfile

from tools.write_template_chart import Note, SongChart, _validate_note
from tools.build_owned_chart import build_owned_pair


def internal_chart(project):
    project.validate()
    notes = [Note(n.time, n.length, n.pitch, n.text, n.end_word, n.line_break_after, n.page_break_time)
             for n in project.ordered()]
    if not notes:
        raise ValueError('No notes to export')
    for index, note in enumerate(notes, 1):
        _validate_note(note, index)
        if not note.text.strip():
            raise ValueError(f'Note {index} has no lyric fragment')
    return SongChart(notes, project.title)


def export_debug_json(project, path):
    chart = internal_chart(project)
    from dataclasses import asdict
    path = Path(path)
    data = json.dumps(dict(title=chart.title, artist=project.artist, bpm=project.bpm,
                           notes=[asdict(n) for n in chart.notes]), ensure_ascii=False,
                      indent=2, allow_nan=False).encode('utf-8')
    with path.open('xb') as stream:
        stream.write(data)


def export_owned_pair(project, directory, name, audio_name, movie_name=None, duration=None):
    if not name or Path(name).name != name or any(c in name for c in '/\\:'):
        raise ValueError('Chart name must be a basename')
    chart = internal_chart(project)
    chart_bytes, lyric_bytes = build_owned_pair(chart, name, audio_name, bpm=project.bpm,
                                               movie_name=movie_name,
                                               song_duration=duration or project.duration + 2)
    directory = Path(directory).resolve()
    if directory.exists():
        raise FileExistsError('Choose a new output directory; existing files are never overwritten')
    directory.parent.mkdir(parents=True, exist_ok=True)
    # Publishing the whole prepared directory avoids a half-written pair.
    with tempfile.TemporaryDirectory(prefix='.openlips-export-', dir=directory.parent) as temp:
        ready = Path(temp) / 'ready'
        ready.mkdir()
        (ready / (name + '.X360')).write_bytes(chart_bytes)
        (ready / (name + '_Lyric.X360')).write_bytes(lyric_bytes)
        if directory.exists():
            raise FileExistsError('Output appeared during export')
        os.rename(ready, directory)
    return directory
