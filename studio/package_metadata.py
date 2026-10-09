"""Bounded Lips STFS metadata reader (LIVE, plus read-only CON/PIRS inventory).

This is not a Microsoft signature verifier. Publication still requires the
full unsigned-package integrity check in tools.build_dlc.
"""
import hashlib
from datetime import datetime
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from tools.build_dlc import TITLE_ID

BLOCK = 4096


def package_metadata(path, *, read_only=False):
    with Path(path).open('rb') as stream:
        def read(offset, size):
            stream.seek(offset)
            value = stream.read(size)
            if len(value) != size:
                raise ValueError('Truncated STFS metadata')
            return value

        header = read(0, 0xA000)
        if (header[:4] not in ((b'LIVE', b'PIRS', b'CON ') if read_only else (b'LIVE',))
                or (not read_only and header[0x37B] != 1)
                or int.from_bytes(header[0x344:0x348], 'big') != 2
                or int.from_bytes(header[0x360:0x364], 'big') != TITLE_ID):
            raise ValueError('Only single-copy Lips LIVE packages are supported')
        base = (int.from_bytes(header[0x340:0x344], 'big') + 4095) & ~4095
        if not 0xA000 <= base <= 0x10000:
            raise ValueError('Invalid STFS header size')
        header = read(0, base)
        if hashlib.sha1(header[0x344:base]).digest() != header[0x32C:0x340]:
            raise ValueError('Invalid STFS header')
        count = int.from_bytes(header[0x395:0x399], 'big')
        if not 0 < count <= 170 ** 3:
            raise ValueError('Invalid STFS block count')
        separation = header[0x37B]
        copies = 1 << ((~separation) & 1)
        step0, step1 = (171, 29071) if copies == 1 else (172, 29242)
        level = 0 if count <= 170 else 1 if count <= 170**2 else 2
        top = 0 if level == 0 else step0 if level == 1 else step1
        top += (separation & 2) >> 1

        def block(number):
            if not 0 <= number < count:
                raise ValueError('STFS block outside package')
            physical = number + copies * ((number + 170) // 170)
            if number >= 170:
                physical += copies * ((number + 170 ** 2) // 170 ** 2)
            if number >= 170 ** 2:
                physical += copies
            return read(base + physical * BLOCK, BLOCK)

        def next_block(number):
            group = number // 170
            table = 0 if group == 0 else group * step0 + copies * (group // 170 + 1 + (group >= 170))
            if level == 0:
                table += (separation & 2) >> 1
            elif level == 1:
                table += bool(read(base + top * BLOCK + group * 24 + 20, 1)[0] & 0x40)
            else:
                parent = number // 170**2
                level1 = step0 if parent == 0 else copies + parent * step1
                level1 += bool(read(base + top * BLOCK + parent * 24 + 20, 1)[0] & 0x40)
                table += bool(read(base + level1 * BLOCK + group % 170 * 24 + 20, 1)[0] & 0x40)
            return int.from_bytes(read(base + table * BLOCK + number % 170 * 24 + 21, 3), 'big')

        def chain(start, size):
            if not 0 < size <= 2 * 1024 * 1024:
                raise ValueError('STFS metadata exceeds 2 MiB limit')
            result, seen = bytearray(), set()
            while len(result) < size:
                if start in seen:
                    raise ValueError('Cyclic STFS chain')
                seen.add(start)
                result.extend(block(start)[:min(BLOCK, size - len(result))])
                if len(result) < size:
                    start = next_block(start)
            return bytes(result)

        table_size = int.from_bytes(header[0x37C:0x37E], 'little') * BLOCK
        table_start = int.from_bytes(header[0x37E:0x381], 'little')
        table = chain(table_start, table_size)
        manifests, manifest_dates, manifest_stamps = [], [], []
        for offset in range(0, len(table), 64):
            entry = table[offset:offset + 64]
            length = entry[0x28] & 0x3F
            if not length:
                continue
            if length > 40:
                raise ValueError('Invalid STFS filename length')
            if entry[:length].lower() == b'dlc.xml':
                if entry[0x28] & 0x80 or entry[0x32:0x34] != b'\xff\xff':
                    raise ValueError('DLC.xml must be a root file')
                manifests.append(chain(int.from_bytes(entry[0x2F:0x32], 'little'),
                    int.from_bytes(entry[0x34:0x38], 'big')))
                stamp = int.from_bytes(entry[0x38:0x3C], 'big')
                manifest_stamps.append(stamp)
                try:
                    manifest_dates.append(datetime(1980 + (stamp >> 25), (stamp >> 21) & 15,
                        (stamp >> 16) & 31, (stamp >> 11) & 31, (stamp >> 5) & 63, (stamp & 31)*2))
                except ValueError:
                    manifest_dates.append(None)
        if len(manifests) != 1 or any(token in manifests[0].upper() for token in (b'<!DOCTYPE', b'<!ENTITY')):
            raise ValueError('Expected one DLC.xml without DTD/entity declarations')
        try:
            root = ET.fromstring(manifests[0])
        except ET.ParseError as error:
            raise ValueError('Invalid DLC.xml') from error
        entries = root.findall('MusicIndices/MusicIndex')
        if root.tag != 'DLCContents' or not 1 <= len(entries) <= 1024:
            raise ValueError('Invalid Lips music manifest')
        songs = []
        for item in entries:
            songs.append({key: (item.findtext(tag) or '')[:1024] for key, tag in
                [('artist', 'Artist'), ('title', 'Title'), ('song_id', 'UintID'),
                 ('content_id', 'ChartContentID'), ('chart', 'ChartUri'), ('lyric', 'LyricUri')]})
        display = header[0x411:0x511].decode('utf-16-be', errors='replace').split('\0', 1)[0]
        description = header[0xD11:0xE11].decode('utf-16-be', errors='replace').split('\0', 1)[0]
        date, precision = manifest_dates[0], 'second'
        if description.startswith('OpenLips custom song; unsigned research package'):
            # Legacy Velocity writes raw seconds into the FAT seconds/2 field.
            # Its minute is usable, but sub-minute ordering is not recoverable.
            stamp = manifest_stamps[0]
            try:
                date = datetime(1980+(stamp >> 25), (stamp >> 21)&15, (stamp >> 16)&31,
                                (stamp >> 11)&31, (stamp >> 5)&63)
            except ValueError:
                date = None
            precision = 'minute'
        created = re.search(r'OpenLips Studio; created=([^;]+);', description)
        if created:
            try:
                candidate = datetime.fromisoformat(created[1])
                if candidate.tzinfo is not None:
                    date, precision = candidate, 'utc'
            except ValueError:
                pass
        return dict(title_id=f'{TITLE_ID:08X}', content_id=header[0x32C:0x340].hex().upper(),
                    title=display, songs=songs, package_date=date.isoformat() if date else None,
                    date_precision=precision)
