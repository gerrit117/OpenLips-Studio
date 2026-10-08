#!/usr/bin/env python3
"""Build and verify an unsigned OG Lips LIVE/STFS DLC; optionally upload via FTP.

The native STFS backend is built separately; see docs/dlc_builder.md.
This tool packages prepared assets without changing their bytes or chart timing.
"""
from __future__ import annotations

import argparse
import ftplib
import getpass
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import uuid
import math
import mmap
from xml.etree import ElementTree as ET

TITLE_ID = 0x4D530888
BLOCK = 4096
# Conservative native-backend ceiling, not a Lips or STFS format limit.
MAX_ASSET_BYTES = 2 * 1024 ** 3 - 32 * 1024 ** 2


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def marketplace_filename(package):
    """Use the observed Lips DLC convention: header content ID + literal 4D.

    The suffix is corpus-derived, not asserted to be universal across Xbox titles.
    Call after the final rehash; a whole-file digest or Song ID is not this ID.
    """
    with Path(package).open('rb') as stream:
        header = stream.read(0x364)
    if (len(header) != 0x364 or header[:4] != b'LIVE'
            or int.from_bytes(header[0x344:0x348], 'big') != 2
            or int.from_bytes(header[0x360:0x364], 'big') != TITLE_ID):
        raise ValueError('expected a Lips LIVE marketplace header')
    content_id = header[0x32C:0x340]
    if not any(content_id):
        raise ValueError('missing STFS header content ID')
    return content_id.hex().upper() + '4D'


def verify_stfs(path):
    """Verify single-copy level 0/1/2 trees without loading the package into RAM."""
    with Path(path).open('rb') as stream:
        if os.fstat(stream.fileno()).st_size < 0xA000:
            raise ValueError('expected unsigned LIVE STFS')
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return _verify_stfs_data(data)


def _verify_stfs_data(data):
    if len(data) < 0xA000 or data[:4] != b'LIVE':
        raise ValueError('expected unsigned LIVE STFS')
    if any(data[4:0x104]):
        raise ValueError('unexpected signature: this builder only emits unsigned LIVE')
    content_type = int.from_bytes(data[0x344:0x348], 'big')
    title_id = int.from_bytes(data[0x360:0x364], 'big')
    if content_type != 2 or title_id != TITLE_ID:
        raise ValueError('not an OG Lips marketplace content package')
    header_end = (int.from_bytes(data[0x340:0x344], 'big') + 4095) & ~4095
    if header_end < 0xA000 or header_end > len(data):
        raise ValueError('invalid header size')
    if hashlib.sha1(data[0x344:header_end]).digest() != data[0x32C:0x340]:
        raise ValueError('STFS header hash mismatch')
    # Bit zero selects single-copy hash tables; bit one is the active copy.
    if data[0x37B] != 1:
        raise ValueError('only single-copy hash tables supported by this validator')
    count = int.from_bytes(data[0x395:0x399], 'big')
    if not 0 < count <= 170 ** 3:
        raise ValueError('invalid STFS block count')
    level = 2 if count > 170 ** 2 else 1 if count > 170 else 0
    top = header_end + (0x718F if level == 2 else 171 if level == 1 else 0) * BLOCK

    def block_at(offset):
        value = data[offset:offset + BLOCK]
        if len(value) != BLOCK:
            raise ValueError(f'truncated STFS block at {offset:#x}')
        return value

    if hashlib.sha1(block_at(top)).digest() != data[0x381:0x395]:
        raise ValueError('STFS top table hash mismatch')
    groups = (count + 169) // 170
    if level == 2:
        for parent in range((groups + 169) // 170):
            position = header_end + (171 if parent == 0 else 1 + parent * 0x718F) * BLOCK
            expected = data[top + parent * 24:top + parent * 24 + 20]
            if hashlib.sha1(block_at(position)).digest() != expected:
                raise ValueError(f'STFS level 1 table hash mismatch: group {parent}')
    for group in range(groups):
        physical_table = (0 if group == 0 else
            group * 171 + group // 170 + 1 + (1 if group >= 170 else 0))
        table_offset = header_end + physical_table * BLOCK
        table = block_at(table_offset)
        if count > 170:
            parent = group // 170
            parent_position = (header_end + (171 if parent == 0 else 1 + parent * 0x718F) * BLOCK)
            entry = parent_position + (group % 170) * 24
            if hashlib.sha1(table).digest() != data[entry:entry + 20]:
                raise ValueError(f'STFS level 0 table hash mismatch: group {group}')
        for index in range(min(170, count - group * 170)):
            number = group * 170 + index
            physical = number + (number + 170) // 170
            if number >= 170:
                physical += (number + 170 ** 2) // (170 ** 2)
            if number >= 170 ** 2:
                physical += 1
            if hashlib.sha1(block_at(header_end + physical * BLOCK)).digest() != table[index * 24:index * 24 + 20]:
                raise ValueError(f'STFS data hash mismatch: block {number}')
    digest = hashlib.sha256()
    for offset in range(0, len(data), 1024 * 1024):
        digest.update(data[offset:offset + 1024 * 1024])
    return dict(title_id=title_id, allocated_blocks=count, hash_groups=groups,
                hash_level=level, bytes=len(data), sha256=digest.hexdigest())


def asset_name(name):
    if not name or len(name) > 40 or name in ('.', '..') or any(
            ord(c) < 32 or ord(c) > 126 or c in '/\\:' for c in name):
        raise ValueError('asset names must be flat ASCII names of 1-40 bytes')
    return name


def make_manifest(title, artist, uint_id, duration, assets, *, preview_lyric=''):
    if not 0 < uint_id <= 0xFFFFFFFF:
        raise ValueError('UintID must be an unused positive 32-bit ID')
    if not title.strip() or not artist.strip() or not math.isfinite(duration) or not 0 < duration < 86400:
        raise ValueError('title, artist and positive duration are required')
    content_id = f'{TITLE_ID:08X}{uint_id:08X}'
    root = ET.Element('DLCContents')
    music = ET.SubElement(ET.SubElement(root, 'MusicIndices'), 'MusicIndex')
    fields = dict(Artist=artist, Title=title, Genre='Pop', Year='2026',
                  Language='EN', Album='', Length=str(round(duration)), Rating='0',
                  LeaderBoardID='0', ChartUri=assets['chart'], AudioUri=assets['audio'],
                  LyricUri=assets['lyric'], AlbumJacketUri=assets['jacket'],
                  PreviewAudioUri=assets['preview_audio'], offerID=f'{uint_id:X}',
                  UintID=f'0x{uint_id:08X}', ChartContentID=content_id,
                  VideoContentID=content_id if 'video' in assets else '0', PreviewLyric=preview_lyric)
    for key, value in fields.items():
        ET.SubElement(music, key).text = value
    if 'video' in assets:
        video = ET.SubElement(ET.SubElement(root, 'MusicVideos'), 'MusicVideo')
        for key, value in dict(Artist=artist, Title=title, Genre='Pop', Year='2026',
                              Album='', VideoUri=assets['video'],
                              PreviewAudioUri=assets['preview_audio'],
                              VideoContentID=content_id, ChartID=content_id + '_00').items():
            ET.SubElement(video, key).text = value
        if 'preview_video' in assets:
            ET.SubElement(video, 'PreviewVideoUri').text = assets['preview_video']
    ET.SubElement(root, 'LicenseBits', ValidBits='3').text = '0x7'
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def build_package(backend, files, manifest, output, display_name, *, canonical_name=False):
    if len(display_name.encode('utf-16-be')) > 254:
        raise ValueError('STFS display name must fit in 127 UTF-16 code units')
    output = Path(output).resolve()
    if not str(output).isascii():
        raise ValueError('the current native backend requires an ASCII output directory/path')
    if canonical_name and not output.is_dir():
        raise ValueError('automatic package naming requires an existing output directory')
    if not canonical_name and output.exists():
        raise FileExistsError(f'refusing to overwrite {output}')
    directory = output if canonical_name else output.parent
    directory.mkdir(parents=True, exist_ok=True)
    if sum(Path(p).stat().st_size for p in files.values()) > MAX_ASSET_BYTES:
        raise ValueError('native backend limit: 2016 MiB total assets')
    folded = [asset_name(n).casefold() for n in files]
    if len(set(folded)) != len(folded) or 'dlc.xml' in folded:
        raise ValueError('duplicate or reserved asset filename')
    with tempfile.TemporaryDirectory(prefix='openlips-dlc-', dir=directory) as temp:
        temp = Path(temp)
        staging = temp / 'assets'
        staging.mkdir()
        for name, path in files.items():
            if not Path(path).is_file():
                raise ValueError(f'asset is not a file: {path}')
            shutil.copyfile(path, staging / name)
        (staging / 'DLC.xml').write_bytes(manifest)
        package = temp / 'package.LIVE'
        subprocess.run([str(Path(backend).resolve()), 'build', str(staging), str(package),
                        f'{TITLE_ID:08X}', display_name], check=True, timeout=600)
        result = verify_stfs(package)
        extracted = temp / 'roundtrip'
        subprocess.run([str(Path(backend).resolve()), 'extract', str(package), str(extracted)],
                       check=True, timeout=600)
        expected = {p.name: sha256(p) for p in staging.iterdir()}
        actual = {p.name: sha256(p) for p in extracted.iterdir() if p.is_file()}
        if actual != expected or any(not p.is_file() for p in extracted.iterdir()):
            raise ValueError('STFS extraction inventory/content differs from staging')
        if canonical_name:
            output = directory / marketplace_filename(package)
        with package.open('r+b') as stream:
            os.fsync(stream.fileno())
        # Same-volume hard link publishes atomically and refuses an existing name.
        os.link(package, output)
    result['output_path'] = str(output)
    return result


def make_pack_manifest(songs, pack_id):
    """Multiple indices share the package offer/content ID, not the song ID."""
    if not songs or not 0 < pack_id <= 0xFFFFFFFF:
        raise ValueError('a song pack needs songs and a positive package ID')
    root = ET.Element('DLCContents')
    indices = ET.SubElement(root, 'MusicIndices')
    videos = ET.SubElement(root, 'MusicVideos')
    ids, names = set(), set()
    content_id = f'{TITLE_ID:08X}{pack_id:08X}'
    for index, song in enumerate(songs):
        if song['uint_id'] in ids:
            raise ValueError('duplicate song ID in pack')
        ids.add(song['uint_id'])
        for name in song['assets'].values():
            folded = asset_name(name).casefold()
            if folded in names:
                raise ValueError('duplicate asset name in pack')
            names.add(folded)
        single = ET.fromstring(make_manifest(song['title'], song['artist'],
            song['uint_id'], song['duration'], song['assets'],
            preview_lyric=song.get('preview_lyric', '')))
        music = single.find('MusicIndices/MusicIndex')
        music.find('offerID').text = f'{pack_id:X}'
        music.find('ChartContentID').text = content_id
        music.find('VideoContentID').text = content_id if 'video' in song['assets'] else '0'
        indices.append(music)
        video = single.find('MusicVideos/MusicVideo')
        if video is not None:
            video.find('VideoContentID').text = content_id
            video.remove(video.find('ChartID'))
            ET.SubElement(video, 'ID').text = f'{content_id}_{index:03d}'
            videos.append(video)
    if not len(videos):
        root.remove(videos)
    ET.SubElement(root, 'LicenseBits', ValidBits='3').text = '0x7'
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def xbox_path(package, root='Hdd1/Content'):
    root = root.replace('\\', '/')
    if not root.strip('/') or any(c in root for c in '\r\n\x00') or '..' in PurePosixPath(root).parts:
        raise ValueError('unsafe FTP content root')
    name = Path(package).name
    if (not name or len(name) > 255 or name in ('.', '..') or any(
            ord(c) < 32 or ord(c) > 126 or c in '/\\:' for c in name)):
        raise ValueError('unsafe FTP package filename')
    return f"{root.rstrip('/')}/0000000000000000/{TITLE_ID:08X}/00000002/{name}"


def upload_package(ftp, package, remote, *, progress=None, cancelled=lambda: False, cleanup=None):
    """Upload new content using a unique temporary name, verify, then rename."""
    checked = verify_stfs(package)
    if any(c in remote for c in '\r\n') or '..' in PurePosixPath(remote).parts:
        raise ValueError('unsafe FTP path')
    parent, name = remote.rsplit('/', 1)
    ftp.cwd('/')
    for part in PurePosixPath(parent).parts:
        if part == '/':
            continue
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            ftp.mkd(part)
            ftp.cwd(part)
    if name.casefold() in {PurePosixPath(p).name.casefold() for p in ftp.nlst()}:
        raise FileExistsError('remote package already exists; not overwritten')
    # Keep incomplete files outside the content-type directory enumerated by Lips.
    destination = '/' + parent.strip('/') + '/' + name
    staging = '/' + parent.strip('/').rsplit('/', 1)[0] + '/.openlips-transfer'
    try:
        ftp.cwd(staging)
    except ftplib.error_perm:
        ftp.mkd(staging)
        ftp.cwd(staging)
    temporary = '.openlips-' + uuid.uuid4().hex + '.tmp'
    total = Path(package).stat().st_size
    sent, received = 0, 0

    def notify(phase, done):
        if cancelled():
            raise InterruptedError('Transfer cancelled; no DLC installed')
        if progress:
            progress(phase, done, total)

    def uploaded(chunk):
        nonlocal sent
        sent += len(chunk)
        notify('upload', sent)

    digest = hashlib.sha256()

    def downloaded(chunk):
        nonlocal received
        received += len(chunk)
        if received > total:
            raise ValueError('FTP read-back size mismatch')
        digest.update(chunk)
        notify('verify', received)

    try:
        notify('upload', 0)
        with Path(package).open('rb') as stream:
            ftp.storbinary('STOR ' + temporary, stream, blocksize=65536, callback=uploaded)
        ftp.retrbinary('RETR ' + temporary, downloaded, blocksize=65536)
        if received != total or digest.hexdigest() != checked['sha256']:
            raise ValueError('FTP read-back hash mismatch')
        ftp.cwd('/' + parent.strip('/'))
        if name.casefold() in {PurePosixPath(p).name.casefold() for p in ftp.nlst()}:
            raise FileExistsError('remote target appeared during upload')
        notify('verify', total)
        ftp.rename(staging + '/' + temporary, destination)
    except Exception:
        try:
            if cleanup:
                ftp.close()
                cleanup(staging + '/' + temporary)
            else:
                ftp.delete(staging + '/' + temporary)
        except ftplib.all_errors:
            pass
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', type=Path, default=Path(os.environ.get(
        'OPENLIPS_STFS_BACKEND', 'private/runtime/dlc-backend-build/Release/openlips_stfs.exe')))
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--chart', type=Path, help='already generated chart, packaged byte-identically')
    source.add_argument('--ultrastar', type=Path, help='generate a fresh OG pair, then package it')
    p.add_argument('--lyric', type=Path, help='required with --chart')
    p.add_argument('--name', default='CustomSong', help='fresh chart basename for --ultrastar')
    p.add_argument('--audio', type=Path, required=True, help='prepared xWMA, not MP3')
    p.add_argument('--preview-audio', type=Path, required=True)
    p.add_argument('--jacket', type=Path, required=True)
    p.add_argument('--video', type=Path)
    p.add_argument('--preview-video', type=Path, help='prepared menu preview WMV, optional with --video')
    p.add_argument('--title', required=True)
    p.add_argument('--artist', required=True)
    p.add_argument('--uint-id', type=lambda s: int(s, 0), required=True)
    p.add_argument('--duration', type=float, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ftp-host')
    p.add_argument('--ftp-port', type=int, default=21)
    p.add_argument('--ftp-user', default='xbox')
    p.add_argument('--ftp-root', default='Hdd1/Content')
    p.add_argument('--ftp-tls', action='store_true')
    p.add_argument('--upload', action='store_true', help='explicitly enable transfer; otherwise path preview only')
    a = p.parse_args(argv)
    if a.upload and not a.ftp_host:
        p.error('--upload requires --ftp-host')
    if a.chart and not a.lyric:
        p.error('--chart requires --lyric')
    if a.preview_video and not a.video:
        p.error('--preview-video requires --video')
    if a.ultrastar and a.lyric:
        p.error('--lyric cannot be combined with --ultrastar')
    # Keep generated charts private and alive until the container is verified.
    with tempfile.TemporaryDirectory(prefix='openlips-chart-') as generated:
        if a.ultrastar:
            try:
                from tools.import_ultrastar import parse_ultrastar_file, chart_to_json_payload
                from tools.build_owned_chart import build_owned_pair
                from tools.write_template_chart import Note, SongChart, _validate_note
            except ModuleNotFoundError:
                from import_ultrastar import parse_ultrastar_file, chart_to_json_payload
                from build_owned_chart import build_owned_pair
                from write_template_chart import Note, SongChart, _validate_note
            source_chart = parse_ultrastar_file(a.ultrastar)
            payload = chart_to_json_payload(source_chart)
            notes = [Note(**{k: n[k] for k in ('time', 'length', 'pitch', 'text',
                                               'end_word', 'line_break_after')}) for n in payload['notes']]
            for i, note in enumerate(notes, 1):
                _validate_note(note, i)
            name = asset_name(a.name)
            asset_name(name + '_Lyric.X360')
            chart, lyric = build_owned_pair(SongChart(notes, source_chart.title), name,
                                           a.audio.stem, bpm=source_chart.bpm,
                                           movie_name=a.video.stem if a.video else None,
                                           song_duration=a.duration)
            a.chart = Path(generated) / (name + '.X360')
            a.lyric = Path(generated) / (name + '_Lyric.X360')
            a.chart.write_bytes(chart)
            a.lyric.write_bytes(lyric)
            print(f'fresh UltraStar chart: notes={len(notes)} BPM={source_chart.bpm} GAP_ms={source_chart.gap_ms}')
            for warning in source_chart.warnings:
                print('WARNING: ' + warning)
        return package_cli(a, p)


def package_cli(a, p):
    assets = {key: getattr(a, key) for key in ('chart', 'lyric', 'audio', 'preview_audio', 'jacket', 'video', 'preview_video')
              if getattr(a, key) is not None}
    for key in ('chart', 'lyric'):
        with assets[key].open('rb') as stream:
            if stream.read(4) != b'<ixb':
                p.error(f'{key} must be a plain IXB file')
    for key in ('audio', 'preview_audio'):
        with assets[key].open('rb') as stream:
            header = stream.read(12)
            if header[:4] != b'RIFF' or header[8:12] != b'XWMA':
                p.error(f'{key} must be encoded RIFF/XWMA; conversion is not performed here')
    names = {key: asset_name(path.name) for key, path in assets.items()}
    if len(set(n.casefold() for n in names.values())) != len(names):
        p.error('asset basenames must be unique')
    manifest = make_manifest(a.title, a.artist, a.uint_id, a.duration, names)
    result = build_package(a.backend, {names[k]: v for k, v in assets.items()}, manifest, a.out, a.title)
    print(f'unsigned LIVE DLC: {a.out.resolve()}')
    print(f'hashes=verified roundtrip=byte-identical blocks={result["allocated_blocks"]} sha256={result["sha256"]}')
    remote = xbox_path(a.out, a.ftp_root)
    print(f'FTP destination (preview): {remote}')
    print('Retail signature absent; Xenia/modified console required. In-game DLC validation still required.')
    if a.upload:
        password = os.environ.get('OPENLIPS_FTP_PASSWORD') or getpass.getpass('Xbox FTP password: ')
        cls = ftplib.FTP_TLS if a.ftp_tls else ftplib.FTP
        if not a.ftp_tls:
            print('WARNING: plain FTP transmits credentials and content unencrypted; use a trusted LAN.')
        with cls(timeout=30) as ftp:
            ftp.connect(a.ftp_host, a.ftp_port)
            ftp.login(a.ftp_user, password)
            if a.ftp_tls:
                ftp.prot_p()
            upload_package(ftp, a.out, remote)
        print('FTP upload verified by SHA-256 read-back; published new package.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError, ftplib.Error) as error:
        raise SystemExit(f'DLC build/upload failed: {error}')
