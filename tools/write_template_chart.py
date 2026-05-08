#!/usr/bin/env python3
"""Template-based Lips chart writer for internal validation.

The JSON input accepted by this tool is a temporary debug format. The intended
long-term frontend is UltraStar TXT -> SongChart -> template writer.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from tools.extract_melody_markers import (
        COMPRESSED_MAGICS,
        MelodyMarker,
        describe_magic,
        iter_melody_markers_object_walker,
        parse_ixb_document,
    )
    from tools.patch_lyrics_mapping import (
        LyricMarker,
        WORD_DATA_TEXT_LENGTH,
        WORD_DATA_TEXT_OFFSET,
        iter_lyric_markers_structural,
    )
    from tools.patch_melody_timing import _iter_patch_sites, _structural_markers, _tone_octave_for_raw_pitch
except ModuleNotFoundError:
    from extract_melody_markers import (
        COMPRESSED_MAGICS,
        MelodyMarker,
        describe_magic,
        iter_melody_markers_object_walker,
        parse_ixb_document,
    )
    from patch_lyrics_mapping import (
        LyricMarker,
        WORD_DATA_TEXT_LENGTH,
        WORD_DATA_TEXT_OFFSET,
        iter_lyric_markers_structural,
    )
    from patch_melody_timing import _iter_patch_sites, _structural_markers, _tone_octave_for_raw_pitch


UNUSED_MARKER_START_TIME = 899.0
UNUSED_MARKER_STEP = 0.01
MIN_UNUSED_LENGTH = 0.02


@dataclass(frozen=True)
class Note:
    time: float
    length: float
    pitch: int
    text: str
    end_word: bool = True


Syllable = Note


@dataclass(frozen=True)
class SongChart:
    notes: list[Note]
    title: str | None = None


@dataclass(frozen=True)
class TextPlacement:
    offset: int
    length: int


@dataclass(frozen=True)
class TemplateWriteOptions:
    chart_only: bool = False
    lyric_only: bool = False
    disable_unused: bool = True


@dataclass(frozen=True)
class MelodyRecordChange:
    action: str
    object_index: int
    chronological_index: int
    offset: int
    old_time: float
    new_time: float
    old_length: float
    new_length: float
    old_raw_pitch: int
    new_raw_pitch: int
    old_tone: float
    new_tone: float
    old_octave: int
    new_octave: int


@dataclass(frozen=True)
class LyricRecordChange:
    action: str
    object_index: int
    chronological_index: int
    offset: int
    melody_pointer: int
    old_time: float
    new_time: float
    old_length: float
    new_length: float
    old_track_index: int
    new_track_index: int
    old_end_word: int
    new_end_word: int
    old_text_offset: int
    new_text_offset: int
    old_text_length: int
    new_text_length: int


@dataclass(frozen=True)
class TemplateWriteResult:
    chart_data: bytes
    lyric_data: bytes
    notes_written: int
    melody_count_before: int
    melody_count_after: int
    lyric_count_before: int
    lyric_count_after: int
    lyric_payload_bytes_used: int
    lyric_payload_capacity: int
    melody_changes: list[MelodyRecordChange]
    lyric_changes: list[LyricRecordChange]
    moved_unused_melody_count: int
    moved_unused_lyric_count: int
    chart_only: bool = False
    lyric_only: bool = False
    disable_unused: bool = True


def load_json_chart(path: Path) -> SongChart:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_notes = payload.get("notes", payload.get("syllables"))
    if not isinstance(raw_notes, list):
        raise ValueError("JSON chart must contain a notes or syllables list")
    notes: list[Note] = []
    for index, raw_note in enumerate(raw_notes, start=1):
        try:
            note = Note(
                time=float(raw_note["time"]),
                length=float(raw_note["length"]),
                pitch=int(raw_note["pitch"]),
                text=str(raw_note["text"]),
                end_word=bool(raw_note.get("end_word", True)),
            )
        except KeyError as exc:
            raise ValueError(f"note {index} missing required field {exc.args[0]}") from exc
        _validate_note(note, index)
        notes.append(note)
    if not notes:
        raise ValueError("chart contains no notes")
    return SongChart(notes=notes, title=payload.get("title"))


def _validate_note(note: Note, index: int) -> None:
    if note.time < 0 or note.time > 899:
        raise ValueError(f"note {index} time must be between 0 and 899 seconds")
    if note.length <= 0 or note.length > 20:
        raise ValueError(f"note {index} length must be > 0 and <= 20 seconds")
    if note.pitch < 24 or note.pitch > 84:
        raise ValueError(f"note {index} pitch must be in the supported vocal range 24..84")
    if not note.text:
        raise ValueError(f"note {index} text must not be empty")


def _chronological_melody_sites(chart_data: bytes):
    melody_markers = _structural_markers(chart_data)
    sites = list(_iter_patch_sites(chart_data, melody_markers))
    return sorted(sites, key=lambda site: (site.original_time, site.offset))


def _chronological_lyrics(chart_data: bytes) -> list[LyricMarker]:
    return sorted(iter_lyric_markers_structural(chart_data), key=lambda marker: (marker.time, marker.offset))


def _lyric_payload_byte_bounds(lyric_data: bytes) -> tuple[int, int]:
    payload_start = lyric_data.find(b"\xef\xbb\xbf")
    payload_end = lyric_data.find(b"</Objects>", payload_start)
    if payload_start < 0 or payload_end < 0:
        raise ValueError("lyric template does not contain a UTF-8 BOM text payload inside <Objects>")
    return payload_start, payload_end


def _lyric_payload_text(lyric_data: bytes) -> str:
    payload_start, payload_end = _lyric_payload_byte_bounds(lyric_data)
    return lyric_data[payload_start:payload_end].decode("utf-8", errors="replace")


def _existing_lyric_payload_stats(lyric_data: bytes) -> tuple[int, int]:
    payload_start, payload_end = _lyric_payload_byte_bounds(lyric_data)
    payload = lyric_data[payload_start:payload_end]
    return len(payload.rstrip(b" ")), len(payload)


def _validate_options(options: TemplateWriteOptions) -> None:
    if options.chart_only and options.lyric_only:
        raise ValueError("--chart-only and --lyric-only cannot be used together")


def _validate_lyric_word_bounds(lyric_markers: list[LyricMarker], lyric_data: bytes) -> None:
    payload = _lyric_payload_text(lyric_data)
    for marker in lyric_markers:
        if marker.text_offset < 0 or marker.text_length < 0 or marker.text_offset + marker.text_length > len(payload):
            raise ValueError(
                "LyricWordData text range is outside lyric payload: "
                f"offset=0x{marker.offset:08X} text={marker.text_offset}/{marker.text_length} payload_chars={len(payload)}"
            )


def _validate_patched_lyric_links(
    melody_markers: list[MelodyMarker],
    lyric_markers: list[LyricMarker],
    lyric_changes: list[LyricRecordChange],
) -> None:
    by_offset = {marker.offset: marker for marker in lyric_markers}
    for change in lyric_changes:
        marker = by_offset.get(change.offset)
        if marker is None:
            raise ValueError(f"patched LyricMarker at 0x{change.offset:08X} disappeared after writing")
        if marker.melody_pointer == 0:
            raise ValueError(f"patched LyricMarker at 0x{change.offset:08X} has a null MelodyMarker pointer")
        if marker.melody_pointer != change.melody_pointer:
            raise ValueError(f"patched LyricMarker at 0x{change.offset:08X} changed its MelodyMarker pointer")
        if marker.chronological_index > len(melody_markers):
            raise ValueError(
                "patched LyricMarker has no corresponding chronological MelodyMarker: "
                f"lyric_index={marker.chronological_index} melody_count={len(melody_markers)}"
            )


def _unused_time(index: int) -> float:
    return UNUSED_MARKER_START_TIME - index * UNUSED_MARKER_STEP


def _build_lyric_payload(chart: SongChart, capacity: int) -> tuple[bytes, dict[int, TextPlacement]]:
    text = "\ufeff\r\n"
    placements: dict[int, TextPlacement] = {}
    for index, note in enumerate(chart.notes):
        offset = len(text)
        text += note.text
        placements[index] = TextPlacement(offset=offset, length=len(note.text))
        if note.end_word:
            text += " "
    payload = text.rstrip() + "\r\n"
    encoded = payload.encode("utf-8")
    if len(encoded) > capacity:
        raise ValueError(f"new lyric text needs {len(encoded)} bytes but template has only {capacity}")
    return encoded + (b" " * (capacity - len(encoded))), placements


def patch_lyric_file_text(template_lyric_data: bytes, chart: SongChart) -> tuple[bytes, dict[int, TextPlacement], int, int]:
    payload_start, payload_end = _lyric_payload_byte_bounds(template_lyric_data)
    capacity = payload_end - payload_start
    payload, placements = _build_lyric_payload(chart, capacity)
    patched = bytearray(template_lyric_data)
    patched[payload_start:payload_end] = payload
    if len(patched) != len(template_lyric_data):
        raise ValueError("lyric file size changed unexpectedly")
    return bytes(patched), placements, len(payload.rstrip(b" ")), capacity


def patch_chart_from_model(
    template_chart_data: bytes,
    chart: SongChart,
    placements: dict[int, TextPlacement],
    options: TemplateWriteOptions = TemplateWriteOptions(),
) -> tuple[bytes, list[MelodyRecordChange], list[LyricRecordChange]]:
    _validate_options(options)
    patch_melody = not options.lyric_only
    patch_lyrics = not options.chart_only
    melody_sites = _chronological_melody_sites(template_chart_data)
    lyric_markers = _chronological_lyrics(template_chart_data)
    if patch_melody and len(chart.notes) > len(melody_sites):
        raise ValueError(f"chart has {len(chart.notes)} notes but template has only {len(melody_sites)} MelodyMarkers")
    if patch_lyrics and len(chart.notes) > len(lyric_markers):
        raise ValueError(f"chart has {len(chart.notes)} notes but template has only {len(lyric_markers)} LyricMarkers")

    patched = bytearray(template_chart_data)
    melody_changes: list[MelodyRecordChange] = []
    lyric_changes: list[LyricRecordChange] = []
    if patch_melody:
        for index, note in enumerate(chart.notes):
            melody_site = melody_sites[index]
            tone, octave = _tone_octave_for_raw_pitch(note.pitch)
            struct.pack_into(">f", patched, melody_site.time_offset, note.time)
            struct.pack_into(">f", patched, melody_site.length_offset, note.length)
            struct.pack_into(">i", patched, melody_site.raw_pitch_offset, note.pitch)
            struct.pack_into(">f", patched, melody_site.tone_offset, tone)
            struct.pack_into(">i", patched, melody_site.octave_offset, octave)
            melody_changes.append(
                MelodyRecordChange(
                    action="note",
                    object_index=melody_site.object_order_index,
                    chronological_index=melody_site.chronological_index,
                    offset=melody_site.offset,
                    old_time=melody_site.original_time,
                    new_time=note.time,
                    old_length=melody_site.length,
                    new_length=note.length,
                    old_raw_pitch=melody_site.original_raw_pitch,
                    new_raw_pitch=note.pitch,
                    old_tone=melody_site.original_tone,
                    new_tone=tone,
                    old_octave=melody_site.original_octave,
                    new_octave=octave,
                )
            )

    if patch_lyrics:
        for index, note in enumerate(chart.notes):
            lyric_marker = lyric_markers[index]
            placement = placements[index]
            new_end_word = 1 if note.end_word else 0
            struct.pack_into(">f", patched, lyric_marker.body_offset + 8, note.time)
            struct.pack_into(">f", patched, lyric_marker.body_offset + 12, note.length)
            struct.pack_into(">i", patched, lyric_marker.body_offset + 16, note.pitch)
            struct.pack_into(">I", patched, lyric_marker.body_offset + 60, new_end_word)
            struct.pack_into(">I", patched, lyric_marker.word_data_file_offset + WORD_DATA_TEXT_OFFSET, placement.offset)
            struct.pack_into(">I", patched, lyric_marker.word_data_file_offset + WORD_DATA_TEXT_LENGTH, placement.length)
            lyric_changes.append(
                LyricRecordChange(
                    action="note",
                    object_index=lyric_marker.object_index,
                    chronological_index=lyric_marker.chronological_index,
                    offset=lyric_marker.offset,
                    melody_pointer=lyric_marker.melody_pointer,
                    old_time=lyric_marker.time,
                    new_time=note.time,
                    old_length=lyric_marker.length,
                    new_length=note.length,
                    old_track_index=lyric_marker.track_index,
                    new_track_index=note.pitch,
                    old_end_word=lyric_marker.end_of_word,
                    new_end_word=new_end_word,
                    old_text_offset=lyric_marker.text_offset,
                    new_text_offset=placement.offset,
                    old_text_length=lyric_marker.text_length,
                    new_text_length=placement.length,
                )
            )

    if options.disable_unused:
        if patch_melody:
            for unused_index, melody_site in enumerate(melody_sites[len(chart.notes) :]):
                new_time = _unused_time(unused_index)
                new_length = max(MIN_UNUSED_LENGTH, min(melody_site.length, 1.0))
                struct.pack_into(">f", patched, melody_site.time_offset, new_time)
                struct.pack_into(">f", patched, melody_site.length_offset, new_length)
                melody_changes.append(
                    MelodyRecordChange(
                        action="disable-unused",
                        object_index=melody_site.object_order_index,
                        chronological_index=melody_site.chronological_index,
                        offset=melody_site.offset,
                        old_time=melody_site.original_time,
                        new_time=new_time,
                        old_length=melody_site.length,
                        new_length=new_length,
                        old_raw_pitch=melody_site.original_raw_pitch,
                        new_raw_pitch=melody_site.original_raw_pitch,
                        old_tone=melody_site.original_tone,
                        new_tone=melody_site.original_tone,
                        old_octave=melody_site.original_octave,
                        new_octave=melody_site.original_octave,
                    )
                )

        if patch_lyrics:
            for unused_index, lyric_marker in enumerate(lyric_markers[len(chart.notes) :]):
                new_time = _unused_time(unused_index)
                struct.pack_into(">f", patched, lyric_marker.body_offset + 8, new_time)
                struct.pack_into(">f", patched, lyric_marker.body_offset + 12, MIN_UNUSED_LENGTH)
                lyric_changes.append(
                    LyricRecordChange(
                        action="disable-unused",
                        object_index=lyric_marker.object_index,
                        chronological_index=lyric_marker.chronological_index,
                        offset=lyric_marker.offset,
                        melody_pointer=lyric_marker.melody_pointer,
                        old_time=lyric_marker.time,
                        new_time=new_time,
                        old_length=lyric_marker.length,
                        new_length=MIN_UNUSED_LENGTH,
                        old_track_index=lyric_marker.track_index,
                        new_track_index=lyric_marker.track_index,
                        old_end_word=lyric_marker.end_of_word,
                        new_end_word=lyric_marker.end_of_word,
                        old_text_offset=lyric_marker.text_offset,
                        new_text_offset=lyric_marker.text_offset,
                        old_text_length=lyric_marker.text_length,
                        new_text_length=lyric_marker.text_length,
                    )
                )

    if len(patched) != len(template_chart_data):
        raise ValueError("chart file size changed unexpectedly")
    return bytes(patched), melody_changes, lyric_changes


def write_template_chart(
    template_chart_data: bytes,
    template_lyric_data: bytes,
    chart: SongChart,
    options: TemplateWriteOptions = TemplateWriteOptions(),
) -> TemplateWriteResult:
    _validate_options(options)
    for index, note in enumerate(chart.notes, start=1):
        _validate_note(note, index)
    if template_chart_data[:4] in COMPRESSED_MAGICS:
        _, kind = describe_magic(template_chart_data)
        raise ValueError(f"chart template is {kind}; decompress it before writing")
    if template_lyric_data[:4] in COMPRESSED_MAGICS:
        _, kind = describe_magic(template_lyric_data)
        raise ValueError(f"lyric template is {kind}; decompress it before writing")

    melody_before = sorted(
        iter_melody_markers_object_walker(template_chart_data, parse_ixb_document(template_chart_data)),
        key=lambda marker: marker.offset,
    )
    lyric_before = iter_lyric_markers_structural(template_chart_data)
    if options.chart_only:
        patched_lyric = template_lyric_data
        placements: dict[int, TextPlacement] = {}
        lyric_bytes_used, lyric_capacity = _existing_lyric_payload_stats(template_lyric_data)
    else:
        patched_lyric, placements, lyric_bytes_used, lyric_capacity = patch_lyric_file_text(template_lyric_data, chart)
    patched_chart, melody_changes, lyric_changes = patch_chart_from_model(template_chart_data, chart, placements, options)
    melody_after = sorted(
        iter_melody_markers_object_walker(patched_chart, parse_ixb_document(patched_chart)),
        key=lambda marker: marker.offset,
    )
    lyric_after = iter_lyric_markers_structural(patched_chart)
    if len(melody_before) != len(melody_after):
        raise ValueError(f"MelodyMarker count changed from {len(melody_before)} to {len(melody_after)}")
    if len(lyric_before) != len(lyric_after):
        raise ValueError(f"LyricMarker count changed from {len(lyric_before)} to {len(lyric_after)}")
    if len(patched_chart) != len(template_chart_data):
        raise ValueError("chart file size changed unexpectedly")
    if len(patched_lyric) != len(template_lyric_data):
        raise ValueError("lyric file size changed unexpectedly")
    _validate_lyric_word_bounds(lyric_after, patched_lyric)
    _validate_patched_lyric_links(melody_after, lyric_after, lyric_changes)
    return TemplateWriteResult(
        chart_data=patched_chart,
        lyric_data=patched_lyric,
        notes_written=len(chart.notes),
        melody_count_before=len(melody_before),
        melody_count_after=len(melody_after),
        lyric_count_before=len(lyric_before),
        lyric_count_after=len(lyric_after),
        lyric_payload_bytes_used=lyric_bytes_used,
        lyric_payload_capacity=lyric_capacity,
        melody_changes=melody_changes,
        lyric_changes=lyric_changes,
        moved_unused_melody_count=sum(1 for change in melody_changes if change.action == "disable-unused"),
        moved_unused_lyric_count=sum(1 for change in lyric_changes if change.action == "disable-unused"),
        chart_only=options.chart_only,
        lyric_only=options.lyric_only,
        disable_unused=options.disable_unused,
    )


def _default_outputs(chart_template: Path) -> tuple[Path, Path]:
    return (
        chart_template.with_name(f"{chart_template.stem}_custom_template{chart_template.suffix}"),
        chart_template.with_name(f"{chart_template.stem}_custom_template_Lyric{chart_template.suffix}"),
    )


def _write_output_rollback_safe(output_path: Path, data: bytes, force: bool = False) -> None:
    if output_path.exists() and not force:
        raise ValueError(f"{output_path} already exists; pass --force to overwrite it")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f"{output_path.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()
    try:
        temp_path.write_bytes(data)
        os.replace(temp_path, output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def write_template_chart_files(
    chart_template: Path,
    lyric_template: Path,
    json_chart: Path,
    out_chart: Path | None = None,
    out_lyric: Path | None = None,
    force: bool = False,
    options: TemplateWriteOptions = TemplateWriteOptions(),
) -> TemplateWriteResult:
    _validate_options(options)
    default_chart, default_lyric = _default_outputs(chart_template)
    out_chart = out_chart or default_chart
    out_lyric = out_lyric or default_lyric
    if chart_template.resolve() == out_chart.resolve():
        raise ValueError("refusing to overwrite the chart template")
    if lyric_template.resolve() == out_lyric.resolve():
        raise ValueError("refusing to overwrite the lyric template")
    chart = load_json_chart(json_chart)
    result = write_template_chart(chart_template.read_bytes(), lyric_template.read_bytes(), chart, options)
    _write_output_rollback_safe(out_chart, result.chart_data, force=force)
    _write_output_rollback_safe(out_lyric, result.lyric_data, force=force)
    return result


def _format_bool(value: bool) -> str:
    return "yes" if value else "no"


def format_summary(result: TemplateWriteResult, out_chart: Path, out_lyric: Path) -> list[str]:
    lines = [
        "template chart write summary:",
        f"  chart_output: {out_chart}",
        f"  lyric_output: {out_lyric}",
        f"  mode_chart_only: {_format_bool(result.chart_only)}",
        f"  mode_lyric_only: {_format_bool(result.lyric_only)}",
        f"  disable_unused: {_format_bool(result.disable_unused)}",
        f"  notes_written: {result.notes_written}",
        f"  melody_marker_count: {result.melody_count_before} -> {result.melody_count_after}",
        f"  lyric_marker_count: {result.lyric_count_before} -> {result.lyric_count_after}",
        f"  lyric_payload_bytes: {result.lyric_payload_bytes_used}/{result.lyric_payload_capacity}",
        f"  moved_unused_melody_markers: {result.moved_unused_melody_count}",
        f"  moved_unused_lyric_markers: {result.moved_unused_lyric_count}",
        f"  melody_records_changed: {len(result.melody_changes)}",
        f"  lyric_records_changed: {len(result.lyric_changes)}",
        "  input_format: temporary JSON debug format; UltraStar TXT remains the target frontend",
    ]
    if result.melody_changes:
        lines.append("  melody_changes:")
        for change in result.melody_changes:
            lines.append(
                "    "
                f"{change.action}: object_index={change.object_index} "
                f"chronological_index={change.chronological_index} "
                f"offset=0x{change.offset:08X} "
                f"time {change.old_time:.6f}->{change.new_time:.6f} "
                f"length {change.old_length:.6f}->{change.new_length:.6f} "
                f"raw_pitch {change.old_raw_pitch}->{change.new_raw_pitch}"
            )
    if result.lyric_changes:
        lines.append("  lyric_changes:")
        for change in result.lyric_changes:
            lines.append(
                "    "
                f"{change.action}: object_index={change.object_index} "
                f"chronological_index={change.chronological_index} "
                f"offset=0x{change.offset:08X} "
                f"melody_ptr=0x{change.melody_pointer:08X} "
                f"time {change.old_time:.6f}->{change.new_time:.6f} "
                f"length {change.old_length:.6f}->{change.new_length:.6f} "
                f"track {change.old_track_index}->{change.new_track_index} "
                f"end_word {change.old_end_word}->{change.new_end_word} "
                f"text {change.old_text_offset}/{change.old_text_length}->{change.new_text_offset}/{change.new_text_length}"
            )
    return lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Template-based Lips chart writer using temporary JSON debug input.")
    parser.add_argument("json_chart", type=Path, help="Temporary JSON chart model")
    parser.add_argument("--template-chart", type=Path, required=True, help="Template chart .X360")
    parser.add_argument("--template-lyric", type=Path, required=True, help="Template _Lyric.X360")
    parser.add_argument("--out-chart", type=Path, help="Output chart .X360")
    parser.add_argument("--out-lyric", type=Path, help="Output _Lyric.X360")
    parser.add_argument("--chart-only", action="store_true", help="Patch only MelodyMarkers; leave lyric data unchanged")
    parser.add_argument(
        "--lyric-only",
        action="store_true",
        help="Patch lyric text and LyricMarker/LyricWordData records only; leave MelodyMarkers unchanged",
    )
    parser.add_argument(
        "--no-disable-unused",
        action="store_true",
        help="Do not move unused MelodyMarkers or LyricMarkers later in the template",
    )
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing outputs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    default_chart, default_lyric = _default_outputs(args.template_chart)
    out_chart = args.out_chart or default_chart
    out_lyric = args.out_lyric or default_lyric
    options = TemplateWriteOptions(
        chart_only=args.chart_only,
        lyric_only=args.lyric_only,
        disable_unused=not args.no_disable_unused,
    )
    try:
        result = write_template_chart_files(
            args.template_chart,
            args.template_lyric,
            args.json_chart,
            out_chart=out_chart,
            out_lyric=out_lyric,
            force=args.force,
            options=options,
        )
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("\n".join(format_summary(result, out_chart, out_lyric)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
