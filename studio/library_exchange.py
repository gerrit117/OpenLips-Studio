"""Portable library imports/exports; never trust client-supplied server paths."""
import base64
import json
from pathlib import Path
import tempfile

from studio.library import Library
from studio.model import StudioProject, load_project
from tools.build_dlc import sha256

INPUT_LIMIT = 16 * 1024 * 1024


def validate_media_header(path, field):
    with Path(path).open('rb') as stream:
        header = stream.read(16)
    asf = header.startswith(bytes.fromhex('3026b2758e66cf11a6d900aa0062ce6c'))
    mp4 = len(header) >= 12 and header[4:8] == b'ftyp'
    riff = header[:4] == b'RIFF' and header[8:12] in ((b'WAVE', b'xWMA', b'XWMA') if field == 'audio' else (b'AVI ',))
    audio = (header.startswith((b'ID3', b'fLaC', b'OggS')) or
             (len(header) >= 2 and header[0] == 255 and header[1] & 0xE0 == 0xE0))
    video = header.startswith(bytes.fromhex('1a45dfa3'))
    if not (asf or mp4 or riff or (audio if field == 'audio' else video)):
        raise ValueError('File does not have a recognized media container header')


def import_input(library, name, data, *, title='', artist=''):
    if (not isinstance(name, str) or len(name) > 256 or Path(name).name != name
            or any(c in name for c in '/\\\r\n\x00') or not isinstance(title, str) or not isinstance(artist, str)):
        raise ValueError('Invalid import metadata')
    extension = Path(name).suffix.lower()
    if extension not in ('.txt', '.lrc', '.mid', '.midi', '.ols', '.olp') or len(data) > INPUT_LIMIT:
        raise ValueError('Use TXT, LRC, MIDI, OLS or portable OLP up to 16 MiB')
    with tempfile.TemporaryDirectory(dir=library.root / '.staging', prefix='import-') as folder:
        path = Path(folder) / ('input' + extension)
        path.write_bytes(data)
        if extension == '.txt':
            from studio.importers import import_ultrastar
            project = import_ultrastar(path)
        elif extension in ('.mid', '.midi'):
            from studio.importers import read_midi, project_from_midi
            imported = read_midi(path)
            if len(imported.lanes) != 1:
                raise ValueError('Select/export one vocal MIDI lane in Studio before importing')
            project = project_from_midi(path, imported, 0)
        elif extension == '.lrc':
            from studio.lrc import read_lrc
            from studio.lyric_timing import lrc_draft
            document = read_lrc(path)
            project = lrc_draft(StudioProject(title=document.metadata.get('ti', Path(name).stem),
                artist=document.metadata.get('ar', '')), document, source='Library LRC')
        elif extension == '.ols':
            from studio.community_import import import_community
            project = import_community(path, storage_root=Path(folder) / 'cover')
        else:
            payload = json.loads(data)
            for field in ('audio_path', 'video_path', 'cover_path'):
                payload[field] = ''
            project = StudioProject.from_payload(payload)
        # TXT headers and JSON must never make the server read arbitrary media.
        project.audio_path = project.video_path = ''
        if extension != '.ols':
            project.cover_path = ''
        project.source = 'Library import'
        project.title = title.strip()[:256] or project.title
        project.artist = artist.strip()[:256] or project.artist
        if extension == '.lrc' and project.title == 'Neuer Song':
            project.title = Path(name).stem[:256]
        return library.add_project(project)


def media_path(library, identifier, field):
    if field not in ('audio', 'video', 'cover'):
        raise KeyError('Unknown media field')
    project = load_project(library.project_path(identifier))
    value = getattr(project, field + '_path')
    if not value:
        raise KeyError('No media stored')
    path = Path(value)
    if path.is_symlink() or path.resolve().parent != library.root / 'media' or not path.is_file():
        raise ValueError('Media is not a managed library asset')
    return path


def portable_project(library, identifier):
    project = load_project(library.project_path(identifier))
    payload = project.to_payload()
    media = {}
    for field in ('audio', 'video', 'cover'):
        payload[field + '_path'] = ''
        try:
            path = media_path(library, identifier, field)
        except KeyError:
            continue
        media[field] = dict(filename=path.name, bytes=path.stat().st_size,
                            sha256=path.stem if len(path.stem) == 64 else sha256(path))
    payload['source'] = 'Remote library'
    if payload.get('lyric_reference'):
        payload['lyric_reference']['source'] = 'Remote library'
    return dict(project=payload, media=media)


def chart_artifact(library, identifier, output, kind):
    from studio.model import load_project
    from studio.page_policy import prepare_pages
    project = prepare_pages(load_project(library.project_path(identifier)))
    if kind == 'chart':
        from studio.exporters import export_community_song
        from tools.song_bundle import youtube_reference
        try:
            reference = youtube_reference(project.video_reference) if project.video_reference else None
        except ValueError:
            reference = None
        return export_community_song(project, Path(output) / 'song.ols',
            duration=project.duration + 2, youtube=reference)
    if kind == 'midi':
        from studio.exporters import export_midi
        return export_midi(project, Path(output) / 'song.mid')
    if kind == 'lrc':
        from studio.lyric_timing import write_lrc
        path = Path(output) / 'song.lrc'
        write_lrc(project, path)
        return path
    raise ValueError('Unknown chart artifact')


class FutureMediaBackend:
    """Intentionally unavailable, regardless of environment flags."""
    enabled = False
    def transcode(self, project_id, profile):
        raise NotImplementedError('Portable media transcoding is not implemented or enabled')


class FutureConsoleTransport:
    """Future paired Xbox-agent protocol, not an active file transfer service."""
    enabled = False
    def transfer(self, package_id, device_id):
        raise NotImplementedError('Native Xbox agent transport is not implemented or enabled')
