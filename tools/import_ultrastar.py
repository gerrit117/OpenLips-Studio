#!/usr/bin/env python3
"""Import UltraStar TXT files into OpenLips' temporary JSON chart format."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ULTRASTAR_PITCH_TO_MIDI_OFFSET = 60
SUPPORTED_NOTE_TYPES = {":"}
GOLDEN_NOTE_TYPES = {"*"}
UNSUPPORTED_NOTE_TYPES = {"F": "freestyle", "R": "rap", "G": "rap golden"}
PHRASE_BREAK_TYPES = {"-"}


@dataclass(frozen=True)
class UltraStarNote:
    line_number: int
    note_type: str
    start_beat: int
    duration_beats: int
    ultrastar_pitch: int
    text: str
    end_word: bool
    line_break_after: bool = False
    page_break_beat: int | None = None

    @property
    def raw_pitch(self) -> int:
        return self.ultrastar_pitch + ULTRASTAR_PITCH_TO_MIDI_OFFSET


@dataclass(frozen=True)
class UltraStarChart:
    metadata: dict[str, str]
    notes: list[UltraStarNote]
    warnings: list[str]
    encoding: str
    ended: bool

    @property
    def title(self) -> str | None:
        return self.metadata.get("TITLE")

    @property
    def artist(self) -> str | None:
        return self.metadata.get("ARTIST")

    @property
    def bpm(self) -> float:
        value = self.metadata.get("BPM")
        if value is None:
            raise ValueError("UltraStar TXT is missing required #BPM metadata")
        try:
            bpm = float(value.replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"invalid #BPM value: {value!r}") from exc
        if bpm <= 0:
            raise ValueError(f"#BPM must be positive, got {bpm}")
        return bpm

    @property
    def gap_ms(self) -> float:
        value = self.metadata.get("GAP", "0")
        try:
            return float(value.replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"invalid #GAP value: {value!r}") from exc


def decode_ultrastar_text(data: bytes) -> tuple[str, str]:
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1") if data.startswith(b"\xef\xbb\xbf") else ("utf-8", "cp1252", "latin-1")
    for encoding in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def read_ultrastar_file(path: Path) -> tuple[str, str]:
    return decode_ultrastar_text(path.read_bytes())


def beat_to_seconds(beat: int | float, bpm: float, gap_ms: float) -> float:
    # UltraStar TXT beat units are quarter-beat ticks: beat 0 starts at GAP.
    return gap_ms / 1000.0 + (float(beat) * 60.0 / (bpm * 4.0))


def _set_previous_line_break(notes: list[UltraStarNote], beat: int | None = None) -> None:
    if not notes:
        return
    previous = notes[-1]
    notes[-1] = UltraStarNote(
        line_number=previous.line_number,
        note_type=previous.note_type,
        start_beat=previous.start_beat,
        duration_beats=previous.duration_beats,
        ultrastar_pitch=previous.ultrastar_pitch,
        text=previous.text,
        end_word=True,
        line_break_after=True,
        page_break_beat=beat,
    )


def _parse_note_line(line: str, line_number: int, warnings: list[str]) -> UltraStarNote | None:
    note_type = line[0]
    body = line[1:].lstrip()
    parts = body.split(maxsplit=3)
    if len(parts) < 4:
        warnings.append(f"line {line_number}: malformed {note_type!r} note ignored")
        return None
    try:
        start_beat = int(parts[0])
        duration_beats = int(parts[1])
        pitch = int(parts[2])
    except ValueError:
        warnings.append(f"line {line_number}: non-integer note timing/pitch ignored")
        return None
    raw_text = parts[3]
    text = raw_text.rstrip(" \t")
    end_word = text != raw_text
    if not text:
        warnings.append(f"line {line_number}: empty lyric text ignored")
        return None
    return UltraStarNote(
        line_number=line_number,
        note_type=note_type,
        start_beat=start_beat,
        duration_beats=duration_beats,
        ultrastar_pitch=pitch,
        text=text,
        end_word=end_word,
    )


def parse_ultrastar_text(text: str, encoding: str = "unknown") -> UltraStarChart:
    metadata: dict[str, str] = {}
    notes: list[UltraStarNote] = []
    warnings: list[str] = []
    ended = False
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue
        if line.startswith("#"):
            key, separator, value = line[1:].partition(":")
            if not separator:
                warnings.append(f"line {line_number}: malformed metadata ignored")
                continue
            metadata[key.strip().upper()] = value.strip()
            continue
        stripped = line.strip()
        if stripped == "E":
            ended = True
            break
        note_type = line[0]
        if note_type in PHRASE_BREAK_TYPES:
            parts = line[1:].split()
            try:
                beat = int(parts[0]) if parts else None
            except ValueError:
                beat = None
                warnings.append(f'line {line_number}: invalid phrase beat; automatic page timing retained')
            if len(parts) > 1 or metadata.get('RELATIVE', '').upper() in ('YES', 'TRUE', '1'):
                beat = None
                warnings.append(f'line {line_number}: relative/multi-value phrase timing unsupported; automatic page timing retained')
            _set_previous_line_break(notes, beat)
            continue
        if note_type == "*" and len(line[1:].split()) == 1:
            warnings.append(f"line {line_number}: '*' phrase marker treated as line break")
            _set_previous_line_break(notes)
            continue
        if note_type in GOLDEN_NOTE_TYPES:
            warnings.append(f"line {line_number}: golden note imported as a normal note")
            note = _parse_note_line(line, line_number, warnings)
            if note is not None:
                notes.append(note)
            continue
        if note_type in SUPPORTED_NOTE_TYPES:
            note = _parse_note_line(line, line_number, warnings)
            if note is not None:
                notes.append(note)
            continue
        if note_type in UNSUPPORTED_NOTE_TYPES:
            warnings.append(f"line {line_number}: {UNSUPPORTED_NOTE_TYPES[note_type]} note ignored")
            continue
        if stripped.startswith("P") and stripped[1:].isdigit():
            warnings.append(f"line {line_number}: player marker {stripped!r} ignored; importing following notes sequentially")
            continue
        warnings.append(f"line {line_number}: unsupported line ignored: {stripped[:40]!r}")

    chart = UltraStarChart(metadata=metadata, notes=notes, warnings=warnings, encoding=encoding, ended=ended)
    _ = chart.bpm
    _ = chart.gap_ms
    if "RELATIVE" in metadata and metadata["RELATIVE"].strip().upper() not in ("NO", "FALSE", "0"):
        chart.warnings.append("#RELATIVE is present; importer currently treats note beats as absolute")
    if not chart.title:
        chart.warnings.append("missing #TITLE metadata")
    if not chart.artist:
        chart.warnings.append("missing #ARTIST metadata")
    if not chart.ended:
        chart.warnings.append("missing E end marker")
    return chart


def parse_ultrastar_file(path: Path) -> UltraStarChart:
    text, encoding = read_ultrastar_file(path)
    return parse_ultrastar_text(text, encoding=encoding)


def chart_to_json_payload(chart: UltraStarChart) -> dict[str, Any]:
    bpm = chart.bpm
    gap_ms = chart.gap_ms
    notes: list[dict[str, Any]] = []
    for note in chart.notes:
        time = beat_to_seconds(note.start_beat, bpm, gap_ms)
        length = note.duration_beats * 60.0 / (bpm * 4.0)
        if note.raw_pitch < 24 or note.raw_pitch > 84:
            chart.warnings.append(
                f"line {note.line_number}: converted raw_pitch {note.raw_pitch} is outside OpenLips validation range 24..84"
            )
        notes.append(
            {
                "time": round(time, 6),
                "length": round(length, 6),
                "pitch": note.raw_pitch,
                "text": note.text,
                "end_word": note.end_word,
                "line_break_after": note.line_break_after,
                "source": {
                    "format": "UltraStar TXT",
                    "line": note.line_number,
                    "note_type": note.note_type,
                    "start_beat": note.start_beat,
                    "duration_beats": note.duration_beats,
                    "ultrastar_pitch": note.ultrastar_pitch,
                },
            }
        )
        if note.page_break_beat is not None:
            page_time = beat_to_seconds(note.page_break_beat, bpm, gap_ms)
            if page_time >= 0:
                notes[-1]['page_break_time'] = round(page_time, 6)
            else:
                chart.warnings.append(f'line {note.line_number}: negative page time omitted')
    return {
        "title": chart.title,
        "artist": chart.artist,
        "source_format": "UltraStar TXT",
        "metadata": chart.metadata,
        "timing": {
            "bpm": bpm,
            "gap_ms": gap_ms,
            "formula": "time_seconds = GAP_ms / 1000 + start_beat * 60 / (BPM * 4); length_seconds = duration_beats * 60 / (BPM * 4)",
            "pitch_formula": "raw_pitch = ultrastar_pitch + 60",
        },
        "warnings": chart.warnings,
        "notes": notes,
    }


def lyric_preview(notes: list[UltraStarNote], limit: int = 240) -> str:
    chunks: list[str] = []
    for note in notes:
        chunks.append(note.text)
        if note.line_break_after:
            chunks.append("\n")
        elif note.end_word:
            chunks.append(" ")
    preview = "".join(chunks).strip()
    if len(preview) > limit:
        preview = preview[: limit - 3] + "..."
    return preview.replace("\r", "\\r").replace("\n", "\\n")


def format_summary(chart: UltraStarChart, payload: dict[str, Any]) -> list[str]:
    notes = payload["notes"]
    lines = [
        "UltraStar import summary:",
        f"  title: {chart.title or ''}",
        f"  artist: {chart.artist or ''}",
        f"  encoding: {chart.encoding}",
        f"  BPM: {chart.bpm}",
        f"  GAP: {chart.gap_ms} ms",
        "  conversion_formula: time_seconds = GAP_ms / 1000 + start_beat * 60 / (BPM * 4)",
        "  length_formula: length_seconds = duration_beats * 60 / (BPM * 4)",
        "  pitch_formula: raw_pitch = ultrastar_pitch + 60",
        f"  note_count: {len(notes)}",
    ]
    if notes:
        first = notes[0]
        last = notes[-1]
        lines.append(
            "  first_note: "
            f"time={first['time']:.6f} length={first['length']:.6f} pitch={first['pitch']} text={first['text']!r}"
        )
        lines.append(
            "  last_note: "
            f"time={last['time']:.6f} length={last['length']:.6f} pitch={last['pitch']} text={last['text']!r}"
        )
    lines.append(f"  generated_lyric_preview: {lyric_preview(chart.notes)}")
    if notes:
        lines.append("  first_converted_timings:")
        for index, note in enumerate(notes[:8], start=1):
            source = note["source"]
            lines.append(
                "    "
                f"{index}: beat={source['start_beat']} duration={source['duration_beats']} "
                f"time={note['time']:.6f} length={note['length']:.6f} "
                f"pitch={note['pitch']} text={note['text']!r} end_word={note['end_word']} "
                f"line_break_after={note['line_break_after']}"
            )
    if chart.warnings:
        lines.append("  warnings:")
        for warning in chart.warnings:
            lines.append(f"    - {warning}")
    return lines


def write_json(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import UltraStar TXT into OpenLips temporary SongChart JSON.")
    parser.add_argument("input", type=Path, help="UltraStar TXT file")
    parser.add_argument("--out", type=Path, required=True, help="Output temporary SongChart JSON file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        chart = parse_ultrastar_file(args.input)
        payload = chart_to_json_payload(chart)
        write_json(payload, args.out)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("\n".join(format_summary(chart, payload)))
    print(f"  output: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
