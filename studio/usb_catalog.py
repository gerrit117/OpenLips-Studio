"""Read-only Xbox Content inventory and explicit, snapshot-checked package removal."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

from studio.package_metadata import package_metadata
from tools.install_dlc_usb import content_directory
from tools.build_dlc import TITLE_ID


@dataclass
class UsbPackage:
    path: Path
    title: str
    songs: list
    built: str | None
    precision: str
    content_id: str
    copied: float
    snapshot: tuple
    error: str = ''
    revision: str = 'unknown'
    local: str = 'none'


def _snapshot(path):
    stat = path.stat()
    with path.open('rb') as stream:
        header = stream.read(0xA000)
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, hashlib.sha256(header).hexdigest()


def song_key(songs):
    values = {(s['artist'].strip().casefold(), s['title'].strip().casefold()) for s in songs}
    return tuple(sorted(values)) if values and all(artist and title for artist, title in values) else ()


def _date(value, precision):
    if not value:
        return None
    try:
        date = datetime.fromisoformat(value)
        return (date.timestamp() if date.tzinfo else date, 'utc' if date.tzinfo else precision)
    except ValueError:
        return None


def compare_versions(entries, local=()):
    for entry in entries:
        key = song_key(entry.songs)
        if not key:
            continue
        group = [e for e in entries if song_key(e.songs) == key]
        dates = [_date(e.built, e.precision) for e in group]
        own = _date(entry.built, entry.precision)
        if len(group) > 1 and own and all(d and d[1] == own[1] for d in dates):
            newest = max(d[0] for d in dates)
            entry.revision = 'older' if own[0] < newest else 'latest'
        matches = [p for p in local if song_key(p['songs']) == key]
        if any(p.get('content_id') == entry.content_id and p['bytes'] == entry.snapshot[0] for p in matches):
            entry.local = 'same'
        elif matches:
            local_dates = [_date(p.get('built'), p.get('precision')) for p in matches]
            if own and all(d and d[1] == own[1] for d in local_dates):
                newest = max(d[0] for d in local_dates)
                entry.local = 'newer' if newest > own[0] else 'older' if newest < own[0] else 'different'
            else:
                entry.local = 'different'
    return entries


def _safe_child(path, parent):
    return not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)() and path.resolve().parent == parent.resolve()


def scan_usb(root, local=()):
    content = content_directory(root)
    entries = []
    for profile in content.iterdir():
        if not re.fullmatch('[0-9a-fA-F]{16}', profile.name) or not _safe_child(profile, content) or not profile.is_dir():
            continue
        for title in profile.iterdir():
            if title.name.upper() != f'{TITLE_ID:08X}' or not _safe_child(title, profile) or not title.is_dir():
                continue
            for kind in title.iterdir():
                if kind.name.upper() != '00000002' or not _safe_child(kind, title) or not kind.is_dir():
                    continue
                for path in kind.iterdir():
                    if not _safe_child(path, kind) or not path.is_file():
                        continue
                    with path.open('rb') as stream:
                        header = stream.read(0xA000)
                    if (len(header) < 0xA000 or header[:4] not in (b'LIVE', b'PIRS', b'CON ')
                            or int.from_bytes(header[0x360:0x364], 'big') != TITLE_ID
                            or int.from_bytes(header[0x344:0x348], 'big') != 2):
                        continue
                    snapshot = _snapshot(path)
                    fallback = header[0x411:0x511].decode('utf-16-be', errors='replace').split('\0', 1)[0]
                    try:
                        data = package_metadata(path, read_only=True)
                        entry = UsbPackage(path, data['title'], data['songs'], data['package_date'],
                            data['date_precision'], data['content_id'], path.stat().st_mtime, snapshot)
                    except (OSError, ValueError) as error:
                        entry = UsbPackage(path, fallback or path.name, [], None, 'unknown', '',
                                           path.stat().st_mtime, snapshot, str(error))
                    entries.append(entry)
    return compare_versions(entries, local)


def delete_package(root, entry):
    content = content_directory(root)
    relative = entry.path.relative_to(content)
    if (len(relative.parts) != 4 or not re.fullmatch('[0-9a-fA-F]{16}', relative.parts[0])
            or relative.parts[1].upper() != f'{TITLE_ID:08X}' or relative.parts[2] != '00000002'):
        raise ValueError('Only an inventoried Lips DLC package can be removed')
    parent = content
    for part in relative.parts:
        child = parent / part
        if not _safe_child(child, parent):
            raise ValueError('USB path changed or contains a link')
        parent = child
    if _snapshot(entry.path) != entry.snapshot:
        raise ValueError('USB package changed; refresh before removing it')
    entry.path.unlink()


def display_date(value):
    if not value:
        return '-'
    try:
        date = datetime.fromisoformat(value)
        return (date.astimezone() if date.tzinfo else date).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return '-'


def file_date(value):
    return display_date(datetime.fromtimestamp(value, timezone.utc).isoformat())
