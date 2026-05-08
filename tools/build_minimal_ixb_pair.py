#!/usr/bin/env python3
"""Build a tiny synthetic Lips IXB chart/lyric pair from scratch.

This is intentionally not a final custom-song writer. It creates the smallest
clean IXB candidate we can currently validate with the OpenLips structural
walkers: one package object, one lyric Text resource, and matching
MelodyMarker/LyricMarker/LyricWordData records.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from tools.patch_melody_timing import _tone_octave_for_raw_pitch
except ModuleNotFoundError:
    from patch_melody_timing import _tone_octave_for_raw_pitch


CHART_PACKAGE_CLASS_INDEX = 8
MELODY_CLASS_INDEX = 5
WORD_DATA_CLASS_INDEX = 6
LYRIC_CLASS_INDEX = 7
LYRIC_PACKAGE_CLASS_INDEX = 3

TEXT_RESOURCE_HASH = 0x12345678
LYRIC_PREFIX = "\ufeff\r\n"
LYRIC_SUFFIX = "\r\n"


@dataclass(frozen=True)
class MinimalNote:
    time: float
    length: float
    raw_pitch: int
    text: str
    end_word: bool = True


@dataclass(frozen=True)
class MinimalIxbPair:
    chart_data: bytes
    lyric_data: bytes
    lyric_text: str
    notes: tuple[MinimalNote, ...]
    text_offsets: tuple[tuple[int, int], ...]


DEFAULT_NOTES: tuple[MinimalNote, ...] = (
    MinimalNote(time=20.0, length=0.50, raw_pitch=65, text="Hi"),
    MinimalNote(time=21.0, length=0.50, raw_pitch=67, text="there"),
    MinimalNote(time=22.0, length=0.75, raw_pitch=69, text="Lips"),
)


CHART_SCHEMA = (
    b'<ixb IsBigEndian="true" IsText="false" Platform="WIN32">'
    b"<Classes>"
    b'<Class Name="ixObject" Size="4"><Members></Members></Class>'
    b'<Class Name="ixReferencedObject" Base="1" Size="8"><Members>'
    b'<Member Name="m_uiReferenceCount" Offset="4"/>'
    b"</Members></Class>"
    b'<Class Name="ixSeqCode" Base="2" Size="20"><Members>'
    b'<Member Name="m_fTriggerTiming" Offset="8"/>'
    b'<Member Name="m_fLength" Offset="12"/>'
    b'<Member Name="m_iTrackIndex" Offset="16"/>'
    b"</Members></Class>"
    b'<Class Name="lpsMarker" Base="3" Size="24"><Members>'
    b'<Member Name="m_bTriggered" Offset="20"/>'
    b"</Members></Class>"
    b'<Class Name="lpsMelodyMarker" Base="4" Size="40"><Members>'
    b'<Member Name="m_Tone" Offset="24"/>'
    b'<Member Name="m_bTilt" Offset="32"/>'
    b'<Member Name="m_pLyricMarker" Offset="36"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricWordData" Size="24"><Members>'
    b'<Member Name="m_pText" Offset="0"/>'
    b'<Member Name="m_uiTextOffset" Offset="12"/>'
    b'<Member Name="m_uiTextLength" Offset="16"/>'
    b'<Member Name="m_uiFlags" Offset="20"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricMarker" Base="4" Size="64"><Members>'
    b'<Member Name="m_pMelodyMarker" Offset="24"/>'
    b'<Member Name="m_vecLyricWordData" Offset="28"/>'
    b'<Member Name="m_strFreeWord" Offset="44"/>'
    b'<Member Name="m_bEndOfWord" Offset="60"/>'
    b"</Members></Class>"
    b'<Class Name="ixPackage" Base="2" Size="72"><Members></Members></Class>'
    b"</Classes><Objects>"
)


LYRIC_SCHEMA = (
    b'<ixb IsBigEndian="true" IsText="false" Platform="WIN32">'
    b"<Classes>"
    b'<Class Name="ixObject" Size="4"><Members></Members></Class>'
    b'<Class Name="ixReferencedObject" Base="1" Size="8"><Members>'
    b'<Member Name="m_uiReferenceCount" Offset="4"/>'
    b"</Members></Class>"
    b'<Class Name="ixPackage" Base="2" Size="72"><Members></Members></Class>'
    b"</Classes><Objects>"
)


def _object(class_index: int, body: bytes) -> bytes:
    if not 0 <= class_index <= 0xFF:
        raise ValueError(f"class index out of byte range: {class_index}")
    return bytes([class_index]) + body


def _package_object(class_index: int) -> bytes:
    body = bytearray(72)
    struct.pack_into(">I", body, 4, 1)
    return _object(class_index, bytes(body))


def _word_data(pointer: int, text_offset: int, text_length: int) -> bytes:
    body = bytearray(24)
    struct.pack_into(">I", body, 0, pointer)
    struct.pack_into(">I", body, 4, 0x280)
    struct.pack_into(">I", body, 8, 0x188FCD00)
    struct.pack_into(">I", body, 12, text_offset)
    struct.pack_into(">I", body, 16, text_length)
    struct.pack_into(">I", body, 20, 1)
    return _object(WORD_DATA_CLASS_INDEX, bytes(body))


def _melody_marker(note: MinimalNote, melody_pointer: int, lyric_pointer: int) -> bytes:
    tone, octave = _tone_octave_for_raw_pitch(note.raw_pitch)
    body = bytearray(40)
    struct.pack_into(">I", body, 4, 2)
    struct.pack_into(">f", body, 8, note.time)
    struct.pack_into(">f", body, 12, note.length)
    struct.pack_into(">I", body, 16, note.raw_pitch)
    struct.pack_into(">I", body, 20, 0)
    struct.pack_into(">f", body, 24, float(tone))
    struct.pack_into(">I", body, 28, int(octave))
    struct.pack_into(">I", body, 32, 0)
    struct.pack_into(">I", body, 36, lyric_pointer)
    return _object(MELODY_CLASS_INDEX, bytes(body))


def _lyric_marker(note: MinimalNote, word_data_pointer: int, melody_pointer: int) -> bytes:
    body = bytearray(64)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">f", body, 8, note.time)
    struct.pack_into(">f", body, 12, note.length)
    struct.pack_into(">I", body, 16, note.raw_pitch)
    struct.pack_into(">I", body, 20, 0)
    struct.pack_into(">I", body, 24, melody_pointer)
    struct.pack_into(">I", body, 28, word_data_pointer)
    struct.pack_into(">I", body, 32, 0x20)
    struct.pack_into(">I", body, 36, 1)
    struct.pack_into(">I", body, 40, 0xCDCDCDCD)
    struct.pack_into(">I", body, 60, 1 if note.end_word else 0)
    return _object(LYRIC_CLASS_INDEX, bytes(body))


def _text_resource(payload: bytes) -> bytes:
    return b"\x00\x00\x00\x05Text\x00\x00\x00\x00" + struct.pack(">II", TEXT_RESOURCE_HASH, len(payload)) + payload


def _build_lyric_text(notes: Sequence[MinimalNote]) -> tuple[str, tuple[tuple[int, int], ...]]:
    text_parts = [LYRIC_PREFIX]
    offsets: list[tuple[int, int]] = []
    current_offset = len(LYRIC_PREFIX)
    for index, note in enumerate(notes):
        if index:
            separator = "\r\n" if notes[index - 1].end_word else ""
            if separator:
                text_parts.append(separator)
                current_offset += len(separator)
        offsets.append((current_offset, len(note.text)))
        text_parts.append(note.text)
        current_offset += len(note.text)
    text_parts.append(LYRIC_SUFFIX)
    return "".join(text_parts), tuple(offsets)


def build_minimal_ixb_pair(notes: Sequence[MinimalNote] = DEFAULT_NOTES) -> MinimalIxbPair:
    if not notes:
        raise ValueError("at least one note is required")
    normalized_notes = tuple(notes)
    lyric_text, text_offsets = _build_lyric_text(normalized_notes)
    lyric_payload = lyric_text.encode("utf-8")

    chart_chunks = [CHART_SCHEMA, _package_object(CHART_PACKAGE_CLASS_INDEX)]
    for index, note in enumerate(normalized_notes):
        word_data_pointer = 0x07160000 + index * 0x80
        melody_pointer = 0x2FA10000 + index * 0x80
        lyric_pointer = 0x2FA20000 + index * 0x80
        text_offset, text_length = text_offsets[index]
        chart_chunks.append(_word_data(word_data_pointer, text_offset, text_length))
        chart_chunks.append(_melody_marker(note, melody_pointer, lyric_pointer))
        chart_chunks.append(_lyric_marker(note, word_data_pointer, melody_pointer))
    chart_chunks.append(b"</Objects></ixb>")

    lyric_data = b"".join(
        [
            LYRIC_SCHEMA,
            _package_object(LYRIC_PACKAGE_CLASS_INDEX),
            _text_resource(lyric_payload),
            b"</Objects></ixb>",
        ]
    )
    return MinimalIxbPair(
        chart_data=b"".join(chart_chunks),
        lyric_data=lyric_data,
        lyric_text=lyric_text,
        notes=normalized_notes,
        text_offsets=text_offsets,
    )


def write_minimal_ixb_pair(out_dir: Path, stem: str, *, force: bool = False) -> tuple[Path, Path, MinimalIxbPair]:
    pair = build_minimal_ixb_pair()
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_path = out_dir / f"{stem}.X360"
    lyric_path = out_dir / f"{stem}_Lyric.X360"
    for path in (chart_path, lyric_path):
        if path.exists() and not force:
            raise FileExistsError(f"{path} already exists; pass --force to overwrite")
    chart_path.write_bytes(pair.chart_data)
    lyric_path.write_bytes(pair.lyric_data)
    return chart_path, lyric_path, pair


def _format_summary(chart_path: Path, lyric_path: Path, pair: MinimalIxbPair) -> str:
    lines = [
        "minimal IXB pair written",
        f"  chart: {chart_path}",
        f"  lyric: {lyric_path}",
        f"  chart bytes: {len(pair.chart_data)}",
        f"  lyric bytes: {len(pair.lyric_data)}",
        "  chart objects: 1 ixPackage, "
        f"{len(pair.notes)} lpsMelodyMarker, {len(pair.notes)} lpsLyricMarker, {len(pair.notes)} lpsLyricWordData",
        "  lyric objects: 1 ixPackage, 1 Text resource",
        f"  lyric payload bytes: {len(pair.lyric_text.encode('utf-8'))}",
        "  notes:",
    ]
    for index, (note, (text_offset, text_length)) in enumerate(zip(pair.notes, pair.text_offsets, strict=True), start=1):
        tone, octave = _tone_octave_for_raw_pitch(note.raw_pitch)
        lines.append(
            "    "
            f"{index}: time={note.time:.3f} length={note.length:.3f} raw_pitch={note.raw_pitch} "
            f"tone={tone:.1f} octave={octave} text_offset={text_offset} text_length={text_length} text={note.text!r}"
        )
    lines.append("  note: this is a first standalone candidate; console/game acceptance may require more package metadata.")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("private/outputs/minimal_ixb"))
    parser.add_argument("--stem", default="TinySynthetic")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    chart_path, lyric_path, pair = write_minimal_ixb_pair(args.out_dir, args.stem, force=args.force)
    print(_format_summary(chart_path, lyric_path, pair))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
