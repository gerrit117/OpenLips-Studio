"""Adapters to existing validated OG authoring tools; never rebuild via templates."""
from pathlib import Path
import json
import os
import tempfile

from tools.write_template_chart import Note, SongChart, _validate_note
from tools.build_owned_chart import build_owned_pair


def export_community_song(project, path, *, duration, youtube=None, album='', genre='', language=''):
    from tools.song_bundle import encode_bundle
    from studio.media import write_cover
    chart = internal_chart(project)
    chart_bytes, lyric_bytes = build_owned_pair(chart, 'community_song', 'community_song.xWMA',
                                               bpm=project.bpm, song_duration=duration)
    with tempfile.TemporaryDirectory(prefix='openlips-cover-') as temp:
        cover = write_cover(project, Path(temp) / 'cover.jpg').read_bytes()
    data = encode_bundle(chart_bytes, lyric_bytes, cover,
                         metadata=dict(title=project.title, artist=project.artist, album=album,
                                       genre=genre, language=language, family='og'),
                         duration=duration, youtube=youtube, offset=project.reference_offset)
    path = Path(path)
    if path.suffix.lower() != '.ols':
        raise ValueError('Community export must end in .ols')
    # Exclusive creation never replaces an existing song or project.
    created = False
    try:
        try:
            with path.open('xb') as stream:
                created = True
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            if created:
                path.unlink(missing_ok=True)
            raise
    except FileExistsError:
        raise FileExistsError('Choose a new file; existing exports are not overwritten') from None
    return path


def internal_chart(project):
    project.validate()
    from studio.i18n import tr
    if any(not n.pitch_assigned for n in project.notes):
        raise ValueError(tr('timing.unassigned_export'))
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


def export_midi(project, path):
    import mido
    from studio.i18n import tr
    project.validate()
    if not project.notes or any(not n.pitch_assigned for n in project.notes):
        raise ValueError(tr('timing.unassigned_export'))
    path = Path(path)
    if path.suffix.lower() not in ('.mid','.midi'):
        raise ValueError('Choose a MIDI filename')
    tempo = mido.bpm2tempo(project.bpm)
    midi = mido.MidiFile(type=0,ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo',tempo=tempo,time=0))
    events = []
    for note in project.ordered():
        media_start = note.time+project.reference_offset
        if media_start<0:
            raise ValueError('Reference offset produces a negative MIDI onset')
        start = round(mido.second2tick(media_start,480,tempo))
        stop = max(start+1,round(mido.second2tick(media_start+note.length,480,tempo)))
        events.append((start,1,note.pitch))
        events.append((stop,0,note.pitch))
    previous = 0
    for tick,on,pitch in sorted(events):
        track.append(mido.Message('note_on' if on else 'note_off',note=pitch,
                                 velocity=90 if on else 0,time=tick-previous))
        previous = tick
    with path.open('xb') as stream:
        midi.save(file=stream)
    return path


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
