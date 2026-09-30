#!/usr/bin/env python3
"""Add a song to a new copy of the OG disc MusicDB, never to its input.

This registers paths only: it does not create media, modify a runtime cache,
or publish content. The OG 41-column schema is intentionally required.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path, PureWindowsPath


COLUMNS = tuple("UintID ID TitleID LeaderBoardID DiscIndex OwnerXuid Length Artist Title Genre Year Album Language Rating Source ChartUri AudioUri UYOMAudioUri LyricUri AlbumJacketUri VideoUri PreviewAudioUri PreviewVideoUri PreviewIconUri Color PreviewLyric AudioState ChartState VideoState ChartContentID VideoContentID Price ChartReleaseDate VideoReleaseDate ChartLatestDate VideoLatestDate bPaid ChartContentFilename VideoContentFilename bNewItem DeleteCheckFlag".split())


def register(source: Path, output: Path, *, title: str, artist: str,
             asset_stem: str, uint_id: int, song_id: str, year: str = "",
             genre: str = "Pop", preview_video: str = "",
             preview_audio: str = "", jacket: str = "") -> dict:
    source, output = source.resolve(), output.resolve()
    if source == output or output.exists():
        raise ValueError("output must be a new file, distinct from input")
    if not title.strip() or not artist.strip() or not song_id.strip():
        raise ValueError("title, artist and ID must be nonempty")
    if not 0 < uint_id <= 0xffffffff:
        raise ValueError("UintID must be a positive 32-bit integer")
    paths = [asset_stem, preview_video, preview_audio, jacket]
    for value in paths:
        if not value:
            continue
        path = PureWindowsPath(value)
        if path.root or path.drive or '..' in path.parts:
            raise ValueError("asset paths must be relative to lps, without parent traversal")
    stem = str(PureWindowsPath(asset_stem))
    if not stem or stem == '.':
        raise ValueError("asset stem must be nonempty")
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        actual = tuple(r[1] for r in original.execute('PRAGMA table_info(Music)'))
        if actual != COLUMNS:
            raise ValueError("unsupported Music schema; expected OG disc 41-column layout")
        before = original.execute('SELECT rowid,* FROM Music ORDER BY rowid').fetchall()
        if not before:
            raise ValueError("catalog must contain measured OG disc rows")
        identities = [(int(str(r[1]), 0), r[2]) for r in before]
        if any(number == uint_id or identifier == song_id for number, identifier in identities):
            raise ValueError("song ID or UintID already exists")
        # These values are common to all 40 measured OG disc rows. No song row
        # or template chart is cloned; the source catalog's unrelated rows stay intact.
        required = ('TitleID', 'DiscIndex', 'Source', 'AudioState', 'ChartState')
        for row in before:
            values = dict(zip(COLUMNS, row[1:]))
            if any(str(values[k]).lower() != str(v).lower() for k, v in zip(
                    required, ('0x4D530888', 3, 0, 2, 2))):
                raise ValueError("catalog is not the measured OG disc family")
        row = dict.fromkeys(COLUMNS, 0)
        row.update(UintID=f'0x{uint_id:08X}', ID=song_id, TitleID='0x4D530888',
                   LeaderBoardID=0, DiscIndex=3, Length='-', Artist=artist,
                   Title=title, Genre=genre, Year=year, Album='', Language='Intl',
                   ChartUri=stem+'.ixb', LyricUri=stem+'_Lyric.ixb',
                   AudioUri=stem, VideoUri=stem, UYOMAudioUri='',
                   AlbumJacketUri=('file://'+str(PureWindowsPath(jacket))) if jacket else '',
                   PreviewAudioUri=preview_audio, PreviewVideoUri=preview_video,
                   PreviewIconUri='', Color='', PreviewLyric='',
                   AudioState=2, ChartState=2, VideoState=2)
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=output.name+'.', suffix='.tmp', dir=output.parent)
        os.close(fd)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as copy:
                original.backup(copy)
                copy.execute('INSERT INTO Music ('+','.join(COLUMNS)+') VALUES ('+
                             ','.join('?' for _ in COLUMNS)+')', tuple(row[k] for k in COLUMNS))
                copy.commit()
                after = copy.execute('SELECT rowid,* FROM Music ORDER BY rowid').fetchall()
                if after[:-1] != before or len(after) != len(before)+1:
                    raise ValueError("original catalog rows changed")
                if copy.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                    raise ValueError("output catalog failed integrity check")
            with temporary.open('r+b') as handle:
                os.fsync(handle.fileno())
            os.link(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return dict(original_count=len(before), final_count=len(after),
                original_rows_unchanged=True, entry=row, output=str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--artist', required=True)
    parser.add_argument('--asset-stem', required=True)
    parser.add_argument('--uint-id', type=lambda v: int(v, 0), required=True)
    parser.add_argument('--song-id', required=True)
    parser.add_argument('--year', default='')
    parser.add_argument('--genre', default='Pop')
    parser.add_argument('--preview-video', default='')
    parser.add_argument('--preview-audio', default='')
    parser.add_argument('--jacket', default='')
    args = parser.parse_args()
    try:
        result = register(args.database, args.out, title=args.title, artist=args.artist,
                          asset_stem=args.asset_stem, uint_id=args.uint_id, song_id=args.song_id,
                          year=args.year, genre=args.genre, preview_video=args.preview_video,
                          preview_audio=args.preview_audio, jacket=args.jacket)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f'error: {exc}\n')
    import json
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
