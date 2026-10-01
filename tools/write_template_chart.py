#!/usr/bin/env python3
"""Template-based Lips chart writer for internal validation.

The JSON input accepted by this tool is a temporary debug format. The intended
long-term frontend is UltraStar TXT -> SongChart -> template writer.
"""

from __future__ import annotations

import argparse
import json
import math
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
    from tools.analyze_lyric_file import TEXT_COVERAGE_THRESHOLD, TextResource, select_text_resource
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
    from analyze_lyric_file import TEXT_COVERAGE_THRESHOLD, TextResource, select_text_resource
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
FLAT_PITCH_TEST_COUNT = 30
FLAT_PITCH_TEST_RAW_PITCH = 65


@dataclass(frozen=True)
class Note:
    time: float
    length: float
    pitch: int
    text: str
    end_word: bool = True
    line_break_after: bool = False
    page_break_time: float | None = None


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
    lyric_text_only: bool = False
    lyric_text_overwrite_only: bool = False
    lyric_worddata_only: bool = False
    lyric_marker_only: bool = False
    flat_pitch_test: bool = False
    disable_unused: bool = True


@dataclass(frozen=True)
class ByteDiffSummary:
    bytes_changed: int
    changed_ranges: list[tuple[int, int]]


@dataclass(frozen=True)
class LyricTextOverwriteInfo:
    range_start: int
    range_end: int
    original_range_length: int
    visible_range_start: int
    visible_range_end: int
    original_visible_length: int
    new_text_byte_length: int
    padding_byte: int
    visible_fill_byte: int
    prefix_char_length: int
    bom_preserved: bool
    trailing_padding_preserved: bool
    changed_only_detected_range: bool
    selected_by: str
    resource_index: int | None
    payload_length_offset: int
    payload_length_value: int
    coverage_markers_in_bounds: int | None = None
    coverage_total_markers: int | None = None
    coverage_ratio: float | None = None


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
class MelodyPreviewRow:
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
class LyricMappingValidation:
    object_index: int
    chronological_index: int
    offset: int
    expected_text: str
    resolved_text: str
    text_offset: int
    text_length: int
    match: bool
    warning: str


@dataclass(frozen=True)
class LyricFitContext:
    lyric_markers: list[LyricMarker]
    payload_capacity: int
    visible_capacity: int
    original_payload_chars: int
    trailing_padding_chars: int
    prefix: str
    line_break: str


@dataclass(frozen=True)
class TemplateWriteResult:
    chart_data: bytes
    lyric_data: bytes
    original_note_count: int
    notes_written: int
    trimmed_note_count: int
    last_surviving_lyric_fragment: str | None
    melody_count_before: int
    melody_count_after: int
    lyric_count_before: int
    lyric_count_after: int
    lyric_payload_bytes_used: int
    lyric_payload_capacity: int
    melody_changes: list[MelodyRecordChange]
    melody_preview: list[MelodyPreviewRow]
    lyric_changes: list[LyricRecordChange]
    lyric_mapping_validation: list[LyricMappingValidation]
    moved_unused_melody_count: int
    moved_unused_lyric_count: int
    chart_diff: ByteDiffSummary
    lyric_diff: ByteDiffSummary
    lyric_text_overwrite: LyricTextOverwriteInfo | None
    lyric_worddata_bounds_valid: bool
    string_length_fields_changed: bool
    pointer_looking_fields_changed: bool
    chart_only: bool = False
    lyric_only: bool = False
    lyric_text_only: bool = False
    lyric_text_overwrite_only: bool = False
    lyric_worddata_only: bool = False
    lyric_marker_only: bool = False
    flat_pitch_test: bool = False
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
                line_break_after=bool(raw_note.get("line_break_after", False)),
                page_break_time=(float(raw_note['page_break_time']) if raw_note.get('page_break_time') is not None else None),
            )
        except KeyError as exc:
            raise ValueError(f"note {index} missing required field {exc.args[0]}") from exc
        _validate_note(note, index)
        notes.append(note)
    if not notes:
        raise ValueError("chart contains no notes")
    return SongChart(notes=notes, title=payload.get("title"))


def _validate_note(note: Note, index: int) -> None:
    if note.page_break_time is not None and (not math.isfinite(note.page_break_time) or note.page_break_time < 0):
        raise ValueError(f'note {index} has invalid page switch time')
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


def _select_lyric_text_resource(
    lyric_data: bytes,
    lyric_markers: list[LyricMarker] | None = None,
) -> tuple[TextResource, str, int | None, int | None, int | None, float | None, int | None]:
    selection = select_text_resource(lyric_data, lyric_markers)
    if selection.resource is None:
        detail = ""
        if selection.coverage is not None:
            detail = f" best coverage was {selection.coverage.coverage_ratio:.1%}"
        raise ValueError(
            "could not select a visible lyric Text resource "
            f"(selected_by={selection.selected_by}, threshold={TEXT_COVERAGE_THRESHOLD:.0%}{detail})"
        )
    coverage_ratio = selection.coverage.coverage_ratio if selection.coverage is not None else None
    coverage_in_bounds = selection.coverage.markers_in_bounds if selection.coverage is not None else None
    coverage_total = selection.coverage.total_markers if selection.coverage is not None else None
    coverage_min_offset = selection.coverage.min_text_offset if selection.coverage is not None else None
    return (
        selection.resource,
        selection.selected_by,
        selection.resource_index,
        coverage_in_bounds,
        coverage_total,
        coverage_ratio,
        coverage_min_offset,
    )


def _lyric_payload_text(lyric_data: bytes, lyric_markers: list[LyricMarker] | None = None) -> str:
    resource, _, _, _, _, _, _ = _select_lyric_text_resource(lyric_data, lyric_markers)
    return lyric_data[resource.payload_start : resource.payload_end].decode("utf-8", errors="replace")


def _existing_lyric_payload_stats(
    lyric_data: bytes,
    lyric_markers: list[LyricMarker] | None = None,
) -> tuple[int, int]:
    resource, _, _, _, _, _, _ = _select_lyric_text_resource(lyric_data, lyric_markers)
    return resource.visible_length, resource.payload_length


def _build_lyric_placements_without_writing(
    template_lyric_data: bytes,
    chart: SongChart,
    lyric_markers: list[LyricMarker] | None = None,
) -> dict[int, TextPlacement]:
    _, capacity = _existing_lyric_payload_stats(template_lyric_data, lyric_markers)
    _, placements = _build_lyric_payload(chart, capacity)
    return placements


def _validate_options(options: TemplateWriteOptions) -> None:
    isolated_modes = [
        options.chart_only,
        options.lyric_only,
        options.lyric_text_only,
        options.lyric_text_overwrite_only,
        options.lyric_worddata_only,
        options.lyric_marker_only,
        options.flat_pitch_test,
    ]
    if sum(1 for enabled in isolated_modes if enabled) > 1:
        raise ValueError(
            "--chart-only, --lyric-only, --lyric-text-only, --lyric-text-overwrite-only, "
            "--lyric-worddata-only, --lyric-marker-only, and --flat-pitch-test cannot be combined"
        )


def _patch_melody_enabled(options: TemplateWriteOptions) -> bool:
    return not (
        options.lyric_only
        or options.lyric_text_only
        or options.lyric_text_overwrite_only
        or options.lyric_worddata_only
        or options.lyric_marker_only
    )


def _patch_lyric_text_enabled(options: TemplateWriteOptions) -> bool:
    return not (options.chart_only or options.lyric_worddata_only or options.lyric_marker_only or options.flat_pitch_test)


def _patch_lyric_marker_fields_enabled(options: TemplateWriteOptions) -> bool:
    return not (
        options.chart_only
        or options.lyric_text_only
        or options.lyric_text_overwrite_only
        or options.lyric_worddata_only
        or options.flat_pitch_test
    )


def _patch_worddata_enabled(options: TemplateWriteOptions) -> bool:
    return not (
        options.chart_only
        or options.lyric_text_only
        or options.lyric_text_overwrite_only
        or options.lyric_marker_only
        or options.flat_pitch_test
    )


def _mode_name(options: TemplateWriteOptions) -> str:
    if options.chart_only:
        return "chart-only"
    if options.lyric_only:
        return "lyric-only"
    if options.lyric_text_only:
        return "lyric-text-only"
    if options.lyric_text_overwrite_only:
        return "lyric-text-overwrite-only"
    if options.lyric_worddata_only:
        return "lyric-worddata-only"
    if options.lyric_marker_only:
        return "lyric-marker-only"
    if options.flat_pitch_test:
        return "flat-pitch-test"
    return "full"


def _validate_lyric_word_bounds(lyric_markers: list[LyricMarker], lyric_data: bytes) -> None:
    payload = _lyric_payload_text(lyric_data, lyric_markers)
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


def _warning_for_resolved_text(expected: str, resolved: str, in_bounds: bool) -> str:
    if not in_bounds:
        return "out-of-bounds"
    if resolved == "":
        return "empty"
    if resolved.strip(" \t\r\n\x00") == "":
        return "spaces-or-padding"
    if "\x00" in resolved:
        return "contains-padding"
    if resolved != expected:
        return "wrong-fragment"
    return "no"


def _lyric_mapping_validation_rows(
    patched_lyric_data: bytes,
    lyric_markers: list[LyricMarker],
    chart: SongChart,
    lyric_changes: list[LyricRecordChange],
) -> list[LyricMappingValidation]:
    relevant_changes = [
        change
        for change in lyric_changes
        if change.action in ("note", "worddata") and 1 <= change.chronological_index <= len(chart.notes)
    ]
    if not relevant_changes:
        return []
    payload = _lyric_payload_text(patched_lyric_data, lyric_markers)
    rows: list[LyricMappingValidation] = []
    for change in sorted(relevant_changes, key=lambda item: item.chronological_index):
        expected = chart.notes[change.chronological_index - 1].text
        text_end = change.new_text_offset + change.new_text_length
        in_bounds = change.new_text_offset >= 0 and change.new_text_length >= 0 and text_end <= len(payload)
        resolved = payload[change.new_text_offset:text_end] if in_bounds else ""
        warning = _warning_for_resolved_text(expected, resolved, in_bounds)
        rows.append(
            LyricMappingValidation(
                object_index=change.object_index,
                chronological_index=change.chronological_index,
                offset=change.offset,
                expected_text=expected,
                resolved_text=resolved,
                text_offset=change.new_text_offset,
                text_length=change.new_text_length,
                match=resolved == expected and warning == "no",
                warning=warning,
            )
        )
    return rows


def _byte_diff_summary(before: bytes, after: bytes) -> ByteDiffSummary:
    if len(before) != len(after):
        raise ValueError("cannot summarize byte diff for differently sized data")
    ranges: list[tuple[int, int]] = []
    bytes_changed = 0
    range_start: int | None = None
    for index, (old_byte, new_byte) in enumerate(zip(before, after)):
        if old_byte == new_byte:
            if range_start is not None:
                ranges.append((range_start, index))
                range_start = None
            continue
        bytes_changed += 1
        if range_start is None:
            range_start = index
    if range_start is not None:
        ranges.append((range_start, len(before)))
    return ByteDiffSummary(bytes_changed=bytes_changed, changed_ranges=ranges)


def _string_length_fields_changed(before: list[LyricMarker], after: list[LyricMarker]) -> bool:
    after_by_offset = {marker.offset: marker for marker in after}
    return any(
        marker.offset in after_by_offset and marker.text_length != after_by_offset[marker.offset].text_length
        for marker in before
    )


def _pointer_looking_fields_changed(before: list[LyricMarker], after: list[LyricMarker]) -> bool:
    after_by_offset = {marker.offset: marker for marker in after}
    for marker in before:
        after_marker = after_by_offset.get(marker.offset)
        if after_marker is None:
            return True
        if marker.melody_pointer != after_marker.melody_pointer:
            return True
        if marker.word_data_pointer != after_marker.word_data_pointer:
            return True
    return False


def _unused_time(index: int) -> float:
    return UNUSED_MARKER_START_TIME - index * UNUSED_MARKER_STEP


def _decode_resource_text(data: bytes) -> tuple[str, bool]:
    try:
        return data.decode("utf-8"), True
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), False


def _neutral_prefix(prefix: str) -> str:
    return "".join(char if char in "\ufeff\r\n\t" else " " for char in prefix)


def _prefix_from_template(resource: TextResource, lyric_data: bytes, coverage_min_offset: int | None) -> str:
    visible_raw = lyric_data[resource.payload_start : resource.visible_end]
    visible_text, _ = _decode_resource_text(visible_raw)
    if coverage_min_offset is not None and 0 <= coverage_min_offset <= len(visible_text):
        return _neutral_prefix(visible_text[:coverage_min_offset])
    if visible_text.startswith("\ufeff\r\n"):
        return "\ufeff\r\n"
    if visible_text.startswith("\ufeff\n"):
        return "\ufeff\n"
    if visible_text.startswith("\ufeff"):
        return "\ufeff"
    index = 0
    while index < len(visible_text) and visible_text[index] in "\r\n\t ":
        index += 1
    return _neutral_prefix(visible_text[:index])


def _line_break_from_template(resource: TextResource, lyric_data: bytes) -> str:
    visible_raw = lyric_data[resource.payload_start : resource.visible_end]
    visible_text, _ = _decode_resource_text(visible_raw)
    if "\r\n" in visible_text:
        return "\r\n"
    if "\n" in visible_text:
        return "\n"
    if "\r" in visible_text:
        return "\r"
    return "\r\n"


def _build_visible_lyric_text(
    chart: SongChart,
    prefix: str = "\ufeff\r\n",
    line_break: str = "\r\n",
) -> tuple[str, dict[int, TextPlacement]]:
    text = prefix
    placements: dict[int, TextPlacement] = {}
    for index, note in enumerate(chart.notes):
        offset = len(text)
        text += note.text
        placements[index] = TextPlacement(offset=offset, length=len(note.text))
        if note.line_break_after:
            text += line_break
        elif note.end_word:
            text += " "
    payload = text.rstrip(" ") + line_break
    return payload, placements


def _build_visible_lyric_payload(chart: SongChart) -> tuple[bytes, dict[int, TextPlacement]]:
    payload, placements = _build_visible_lyric_text(chart)
    encoded = payload.encode("utf-8")
    return encoded, placements


def _build_lyric_payload(chart: SongChart, capacity: int) -> tuple[bytes, dict[int, TextPlacement]]:
    encoded, placements = _build_visible_lyric_payload(chart)
    if len(encoded) > capacity:
        raise ValueError(f"new lyric text needs {len(encoded)} bytes but template has only {capacity}")
    return encoded + (b" " * (capacity - len(encoded))), placements


def patch_lyric_file_text(
    template_lyric_data: bytes,
    chart: SongChart,
    lyric_markers: list[LyricMarker] | None = None,
) -> tuple[bytes, dict[int, TextPlacement], int, int, LyricTextOverwriteInfo]:
    (
        resource,
        selected_by,
        resource_index,
        coverage_in_bounds,
        coverage_total,
        coverage_ratio,
        coverage_min_offset,
    ) = _select_lyric_text_resource(template_lyric_data, lyric_markers)
    payload_start = resource.payload_start
    payload_end = resource.payload_end
    visible_start = resource.payload_start
    visible_end = resource.visible_end
    padding_byte = resource.padding_byte if resource.padding_byte is not None else 0x20
    visible_fill_byte = 0x20
    payload_capacity = resource.payload_length
    visible_capacity = max(0, visible_end - visible_start)
    prefix = _prefix_from_template(resource, template_lyric_data, coverage_min_offset)
    line_break = _line_break_from_template(resource, template_lyric_data)
    visible_text, placements = _build_visible_lyric_text(chart, prefix=prefix, line_break=line_break)
    payload = visible_text.encode("utf-8")
    if len(payload) > visible_capacity:
        raise ValueError(
            f"new lyric text needs {len(payload)} bytes but original visible Text region has only {visible_capacity}"
        )
    patched = bytearray(template_lyric_data)
    original_trailing_padding = template_lyric_data[visible_end:payload_end]
    visible_replacement = payload + bytes([visible_fill_byte]) * (visible_capacity - len(payload))
    replacement = visible_replacement + original_trailing_padding
    if len(replacement) != payload_capacity:
        raise ValueError("generated lyric replacement does not match selected Text resource payload length")
    patched[payload_start:payload_end] = replacement
    if len(patched) != len(template_lyric_data):
        raise ValueError("lyric file size changed unexpectedly")
    changed_ranges = _byte_diff_summary(template_lyric_data, bytes(patched)).changed_ranges
    changed_only_detected_range = all(payload_start <= start and end <= payload_end for start, end in changed_ranges)
    return (
        bytes(patched),
        placements,
        len(payload),
        payload_capacity,
        LyricTextOverwriteInfo(
            range_start=payload_start,
            range_end=payload_end,
            original_range_length=payload_capacity,
            visible_range_start=visible_start,
            visible_range_end=visible_end,
            original_visible_length=visible_capacity,
            new_text_byte_length=len(payload),
            padding_byte=padding_byte,
            visible_fill_byte=visible_fill_byte,
            prefix_char_length=len(prefix),
            bom_preserved=prefix.startswith("\ufeff") == template_lyric_data[payload_start:payload_start + 3].startswith(b"\xef\xbb\xbf"),
            trailing_padding_preserved=patched[visible_end:payload_end] == template_lyric_data[visible_end:payload_end],
            changed_only_detected_range=changed_only_detected_range,
            selected_by=selected_by,
            resource_index=resource_index,
            payload_length_offset=resource.payload_length_offset,
            payload_length_value=resource.payload_length,
            coverage_markers_in_bounds=coverage_in_bounds,
            coverage_total_markers=coverage_total,
            coverage_ratio=coverage_ratio,
        ),
    )


def patch_chart_from_model(
    template_chart_data: bytes,
    chart: SongChart,
    placements: dict[int, TextPlacement],
    options: TemplateWriteOptions = TemplateWriteOptions(),
) -> tuple[bytes, list[MelodyRecordChange], list[LyricRecordChange]]:
    _validate_options(options)
    patch_melody = _patch_melody_enabled(options)
    patch_lyric_marker_fields = _patch_lyric_marker_fields_enabled(options)
    patch_worddata = _patch_worddata_enabled(options)
    patch_any_chart_lyrics = patch_lyric_marker_fields or patch_worddata
    melody_sites = _chronological_melody_sites(template_chart_data)
    lyric_markers = _chronological_lyrics(template_chart_data)
    patched = bytearray(template_chart_data)
    melody_changes: list[MelodyRecordChange] = []
    lyric_changes: list[LyricRecordChange] = []
    if options.flat_pitch_test:
        if len(melody_sites) < FLAT_PITCH_TEST_COUNT:
            raise ValueError(
                f"--flat-pitch-test needs at least {FLAT_PITCH_TEST_COUNT} MelodyMarkers; found {len(melody_sites)}"
            )
        tone, octave = _tone_octave_for_raw_pitch(FLAT_PITCH_TEST_RAW_PITCH)
        for melody_site in melody_sites[:FLAT_PITCH_TEST_COUNT]:
            struct.pack_into(">i", patched, melody_site.raw_pitch_offset, FLAT_PITCH_TEST_RAW_PITCH)
            struct.pack_into(">f", patched, melody_site.tone_offset, tone)
            struct.pack_into(">i", patched, melody_site.octave_offset, octave)
            melody_changes.append(
                MelodyRecordChange(
                    action="flat-pitch-test",
                    object_index=melody_site.object_order_index,
                    chronological_index=melody_site.chronological_index,
                    offset=melody_site.offset,
                    old_time=melody_site.original_time,
                    new_time=melody_site.original_time,
                    old_length=melody_site.length,
                    new_length=melody_site.length,
                    old_raw_pitch=melody_site.original_raw_pitch,
                    new_raw_pitch=FLAT_PITCH_TEST_RAW_PITCH,
                    old_tone=melody_site.original_tone,
                    new_tone=tone,
                    old_octave=melody_site.original_octave,
                    new_octave=octave,
                )
            )
        if len(patched) != len(template_chart_data):
            raise ValueError("chart file size changed unexpectedly")
        return bytes(patched), melody_changes, lyric_changes

    if patch_melody and len(chart.notes) > len(melody_sites):
        raise ValueError(f"chart has {len(chart.notes)} notes but template has only {len(melody_sites)} MelodyMarkers")
    if patch_any_chart_lyrics and len(chart.notes) > len(lyric_markers):
        raise ValueError(f"chart has {len(chart.notes)} notes but template has only {len(lyric_markers)} LyricMarkers")

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

    if patch_any_chart_lyrics:
        for index, note in enumerate(chart.notes):
            lyric_marker = lyric_markers[index]
            placement = placements[index] if patch_worddata else TextPlacement(lyric_marker.text_offset, lyric_marker.text_length)
            new_end_word = 1 if note.end_word else 0
            if patch_lyric_marker_fields:
                struct.pack_into(">f", patched, lyric_marker.body_offset + 8, note.time)
                struct.pack_into(">f", patched, lyric_marker.body_offset + 12, note.length)
                struct.pack_into(">i", patched, lyric_marker.body_offset + 16, note.pitch)
                struct.pack_into(">I", patched, lyric_marker.body_offset + 60, new_end_word)
            if patch_worddata:
                struct.pack_into(">I", patched, lyric_marker.word_data_file_offset + WORD_DATA_TEXT_OFFSET, placement.offset)
                struct.pack_into(">I", patched, lyric_marker.word_data_file_offset + WORD_DATA_TEXT_LENGTH, placement.length)
            lyric_changes.append(
                LyricRecordChange(
                    action="note"
                    if patch_lyric_marker_fields and patch_worddata
                    else "lyric-marker"
                    if patch_lyric_marker_fields
                    else "worddata",
                    object_index=lyric_marker.object_index,
                    chronological_index=lyric_marker.chronological_index,
                    offset=lyric_marker.offset,
                    melody_pointer=lyric_marker.melody_pointer,
                    old_time=lyric_marker.time,
                    new_time=note.time if patch_lyric_marker_fields else lyric_marker.time,
                    old_length=lyric_marker.length,
                    new_length=note.length if patch_lyric_marker_fields else lyric_marker.length,
                    old_track_index=lyric_marker.track_index,
                    new_track_index=note.pitch if patch_lyric_marker_fields else lyric_marker.track_index,
                    old_end_word=lyric_marker.end_of_word,
                    new_end_word=new_end_word if patch_lyric_marker_fields else lyric_marker.end_of_word,
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

        if patch_lyric_marker_fields and not options.lyric_marker_only:
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


def _melody_preview_rows(before: list[MelodyMarker], after: list[MelodyMarker], limit: int = 10) -> list[MelodyPreviewRow]:
    after_by_offset = {marker.offset: marker for marker in after}
    rows: list[MelodyPreviewRow] = []
    for chronological_index, marker in enumerate(sorted(before, key=lambda item: (item.time, item.offset))[:limit], start=1):
        after_marker = after_by_offset.get(marker.offset, marker)
        rows.append(
            MelodyPreviewRow(
                chronological_index=chronological_index,
                offset=marker.offset,
                old_time=marker.time,
                new_time=after_marker.time,
                old_length=marker.length,
                new_length=after_marker.length,
                old_raw_pitch=marker.raw_pitch,
                new_raw_pitch=after_marker.raw_pitch,
                old_tone=marker.tone,
                new_tone=after_marker.tone,
                old_octave=marker.octave,
                new_octave=after_marker.octave,
            )
        )
    return rows


def _is_tail_trim_retryable_error(exc: ValueError) -> bool:
    message = str(exc)
    return (
        "new lyric text needs" in message
        or "LyricWordData text range is outside lyric payload" in message
    )


def _chart_with_tail_trim(chart: SongChart, note_count: int) -> SongChart:
    return SongChart(notes=list(chart.notes[:note_count]), title=chart.title)


def _build_lyric_fit_context(
    template_chart_data: bytes,
    template_lyric_data: bytes,
    lyric_markers: list[LyricMarker] | None = None,
) -> LyricFitContext:
    lyric_markers = lyric_markers or _chronological_lyrics(template_chart_data)
    resource, _, _, _, _, _, coverage_min_offset = _select_lyric_text_resource(template_lyric_data, lyric_markers)
    payload = template_lyric_data[resource.payload_start : resource.payload_end]
    trailing_padding = template_lyric_data[resource.visible_end : resource.payload_end]
    return LyricFitContext(
        lyric_markers=lyric_markers,
        payload_capacity=resource.payload_length,
        visible_capacity=max(0, resource.visible_end - resource.payload_start),
        original_payload_chars=len(payload.decode("utf-8", errors="replace")),
        trailing_padding_chars=len(trailing_padding.decode("utf-8", errors="replace")),
        prefix=_prefix_from_template(resource, template_lyric_data, coverage_min_offset),
        line_break=_line_break_from_template(resource, template_lyric_data),
    )


def _generated_lyric_ranges_fit_with_context(
    context: LyricFitContext,
    chart: SongChart,
    options: TemplateWriteOptions,
) -> bool:
    if not (_patch_lyric_text_enabled(options) or _patch_worddata_enabled(options)):
        return True
    try:
        if _patch_lyric_text_enabled(options):
            visible_text, placements = _build_visible_lyric_text(chart, prefix=context.prefix, line_break=context.line_break)
            encoded_length = len(visible_text.encode("utf-8"))
            if encoded_length > context.visible_capacity:
                return False
            payload_chars = len(visible_text) + (context.visible_capacity - encoded_length) + context.trailing_padding_chars
        else:
            payload_chars = context.original_payload_chars
            placements = (
                _build_lyric_payload(chart, context.payload_capacity)[1]
                if _patch_worddata_enabled(options)
                else {}
            )
    except ValueError:
        return False

    patch_worddata = _patch_worddata_enabled(options)
    for index, marker in enumerate(context.lyric_markers):
        if patch_worddata and index < len(chart.notes):
            placement = placements[index]
            text_offset = placement.offset
            text_length = placement.length
        else:
            text_offset = marker.text_offset
            text_length = marker.text_length
        if text_offset < 0 or text_length < 0 or text_offset + text_length > payload_chars:
            return False
    return True


def _find_lyric_safe_note_count(
    template_chart_data: bytes,
    template_lyric_data: bytes,
    chart: SongChart,
    options: TemplateWriteOptions,
) -> int:
    if options.flat_pitch_test:
        return len(chart.notes)
    context = _build_lyric_fit_context(template_chart_data, template_lyric_data)
    note_count = len(chart.notes)
    while note_count > 0:
        candidate = _chart_with_tail_trim(chart, note_count)
        if _generated_lyric_ranges_fit_with_context(context, candidate, options):
            return note_count
        note_count -= 1
    return 0


def write_template_chart(
    template_chart_data: bytes,
    template_lyric_data: bytes,
    chart: SongChart,
    options: TemplateWriteOptions = TemplateWriteOptions(),
) -> TemplateWriteResult:
    _validate_options(options)
    for index, note in enumerate(chart.notes, start=1):
        _validate_note(note, index)
    original_note_count = len(chart.notes)
    if template_chart_data[:4] in COMPRESSED_MAGICS or template_lyric_data[:4] in COMPRESSED_MAGICS:
        working_note_count = original_note_count
    else:
        working_note_count = _find_lyric_safe_note_count(template_chart_data, template_lyric_data, chart, options)
    while True:
        working_chart = _chart_with_tail_trim(chart, working_note_count)
        try:
            return _write_template_chart_once(
                template_chart_data,
                template_lyric_data,
                working_chart,
                options,
                original_note_count=original_note_count,
                trimmed_note_count=original_note_count - working_note_count,
            )
        except ValueError as exc:
            if options.flat_pitch_test or not _is_tail_trim_retryable_error(exc) or working_note_count == 0:
                raise
            working_note_count -= 1


def _write_template_chart_once(
    template_chart_data: bytes,
    template_lyric_data: bytes,
    chart: SongChart,
    options: TemplateWriteOptions,
    original_note_count: int,
    trimmed_note_count: int,
) -> TemplateWriteResult:
    _validate_options(options)
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
    lyric_text_overwrite: LyricTextOverwriteInfo | None = None
    if _patch_lyric_text_enabled(options):
        patched_lyric, placements, lyric_bytes_used, lyric_capacity, lyric_text_overwrite = patch_lyric_file_text(
            template_lyric_data,
            chart,
            lyric_before,
        )
    else:
        patched_lyric = template_lyric_data
        lyric_bytes_used, lyric_capacity = _existing_lyric_payload_stats(template_lyric_data, lyric_before)
        placements = (
            _build_lyric_placements_without_writing(template_lyric_data, chart, lyric_before)
            if _patch_worddata_enabled(options)
            else {}
        )
    patched_chart, melody_changes, lyric_changes = patch_chart_from_model(template_chart_data, chart, placements, options)
    melody_after = sorted(
        iter_melody_markers_object_walker(patched_chart, parse_ixb_document(patched_chart)),
        key=lambda marker: marker.offset,
    )
    lyric_after = lyric_before if options.flat_pitch_test else iter_lyric_markers_structural(patched_chart)
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
    lyric_mapping_validation = _lyric_mapping_validation_rows(patched_lyric, lyric_after, chart, lyric_changes)
    chart_diff = _byte_diff_summary(template_chart_data, patched_chart)
    lyric_diff = _byte_diff_summary(template_lyric_data, patched_lyric)
    return TemplateWriteResult(
        chart_data=patched_chart,
        lyric_data=patched_lyric,
        original_note_count=original_note_count,
        notes_written=0 if options.flat_pitch_test else len(chart.notes),
        trimmed_note_count=trimmed_note_count,
        last_surviving_lyric_fragment=chart.notes[-1].text if chart.notes else None,
        melody_count_before=len(melody_before),
        melody_count_after=len(melody_after),
        lyric_count_before=len(lyric_before),
        lyric_count_after=len(lyric_after),
        lyric_payload_bytes_used=lyric_bytes_used,
        lyric_payload_capacity=lyric_capacity,
        melody_changes=melody_changes,
        melody_preview=_melody_preview_rows(melody_before, melody_after),
        lyric_changes=lyric_changes,
        lyric_mapping_validation=lyric_mapping_validation,
        moved_unused_melody_count=sum(1 for change in melody_changes if change.action == "disable-unused"),
        moved_unused_lyric_count=sum(1 for change in lyric_changes if change.action == "disable-unused"),
        chart_diff=chart_diff,
        lyric_diff=lyric_diff,
        lyric_text_overwrite=lyric_text_overwrite,
        lyric_worddata_bounds_valid=True,
        string_length_fields_changed=_string_length_fields_changed(lyric_before, lyric_after),
        pointer_looking_fields_changed=_pointer_looking_fields_changed(lyric_before, lyric_after),
        chart_only=options.chart_only,
        lyric_only=options.lyric_only,
        lyric_text_only=options.lyric_text_only,
        lyric_text_overwrite_only=options.lyric_text_overwrite_only,
        lyric_worddata_only=options.lyric_worddata_only,
        lyric_marker_only=options.lyric_marker_only,
        flat_pitch_test=options.flat_pitch_test,
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
    json_chart: Path | None,
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
    if json_chart is None:
        if not options.flat_pitch_test:
            raise ValueError("JSON chart is required unless --flat-pitch-test is used")
        chart = SongChart(notes=[])
    else:
        chart = load_json_chart(json_chart)
    result = write_template_chart(chart_template.read_bytes(), lyric_template.read_bytes(), chart, options)
    _write_output_rollback_safe(out_chart, result.chart_data, force=force)
    _write_output_rollback_safe(out_lyric, result.lyric_data, force=force)
    return result


def _format_bool(value: bool) -> str:
    return "yes" if value else "no"


def _format_ranges(ranges: list[tuple[int, int]], limit: int = 12) -> str:
    if not ranges:
        return "none"
    visible = [f"0x{start:08X}-0x{end - 1:08X}" for start, end in ranges[:limit]]
    if len(ranges) > limit:
        visible.append(f"... +{len(ranges) - limit} more")
    return ", ".join(visible)


def _hex_dump(data: bytes, width: int = 16) -> list[str]:
    lines: list[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hex_bytes = " ".join(f"{value:02X}" for value in chunk)
        ascii_bytes = "".join(chr(value) if 0x20 <= value <= 0x7E else "." for value in chunk)
        lines.append(f"    {offset:08X}  {hex_bytes:<{width * 3 - 1}}  {ascii_bytes}")
    if not lines:
        lines.append("    <empty>")
    return lines


def _escaped_utf8(data: bytes, limit: int | None = None) -> str:
    text = data.decode("utf-8", errors="replace")
    if limit is not None and len(text) > limit:
        text = text[: limit - 3] + "..."
    return text.encode("unicode_escape", errors="backslashreplace").decode("ascii")


def _escaped_text(text: str, limit: int = 80) -> str:
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text.encode("unicode_escape", errors="backslashreplace").decode("ascii")


def format_lyric_payload_debug(original_lyric_data: bytes, result: TemplateWriteResult) -> list[str]:
    info = result.lyric_text_overwrite
    if info is None:
        return ["lyric payload debug: unavailable because lyric text was not rewritten"]
    generated_payload = result.lyric_data[info.range_start : info.range_end]
    generated_visible = result.lyric_data[info.visible_range_start : info.visible_range_end]
    lines = [
        "lyric payload debug:",
        f"  selected_payload_range: 0x{info.range_start:08X}-0x{info.range_end - 1:08X}",
        f"  generated_payload_length: {len(generated_payload)}",
        "  generated_payload_hex:",
    ]
    lines.extend(_hex_dump(generated_payload))
    lines.extend(
        [
            f"  generated_payload_decoded_utf8_preview: {_escaped_utf8(generated_payload, limit=512)}",
            f"  generated_visible_text_escaped: {_escaped_utf8(generated_visible)}",
        ]
    )
    return lines


def format_lyric_payload_comparison(
    original_lyric_data: bytes,
    result: TemplateWriteResult,
    preview_bytes: int = 256,
) -> list[str]:
    info = result.lyric_text_overwrite
    if info is None:
        return ["lyric payload comparison: unavailable because lyric text was not rewritten"]
    original_visible = original_lyric_data[info.visible_range_start : info.visible_range_end]
    generated_visible = result.lyric_data[info.visible_range_start : info.visible_range_end]
    original_prefix = original_lyric_data[info.range_start : min(info.range_end, info.range_start + preview_bytes)]
    generated_prefix = result.lyric_data[info.range_start : min(info.range_end, info.range_start + preview_bytes)]
    lines = [
        "lyric payload comparison:",
        f"  original_visible_preview: {_escaped_utf8(original_visible, limit=512)}",
        f"  generated_visible_preview: {_escaped_utf8(generated_visible, limit=512)}",
        f"  first_{preview_bytes}_bytes_before_hex:",
    ]
    lines.extend(_hex_dump(original_prefix))
    lines.append(f"  first_{preview_bytes}_bytes_after_hex:")
    lines.extend(_hex_dump(generated_prefix))
    return lines


def format_summary(result: TemplateWriteResult, out_chart: Path, out_lyric: Path) -> list[str]:
    lines = [
        "template chart write summary:",
        f"  chart_output: {out_chart}",
        f"  lyric_output: {out_lyric}",
        f"  mode: {_mode_name(result)}",
        f"  mode_chart_only: {_format_bool(result.chart_only)}",
        f"  mode_lyric_only: {_format_bool(result.lyric_only)}",
        f"  mode_lyric_text_only: {_format_bool(result.lyric_text_only)}",
        f"  mode_lyric_text_overwrite_only: {_format_bool(result.lyric_text_overwrite_only)}",
        f"  mode_lyric_worddata_only: {_format_bool(result.lyric_worddata_only)}",
        f"  mode_lyric_marker_only: {_format_bool(result.lyric_marker_only)}",
        f"  mode_flat_pitch_test: {_format_bool(result.flat_pitch_test)}",
        f"  disable_unused: {_format_bool(result.disable_unused)}",
        f"  original_note_count: {result.original_note_count}",
        f"  trimmed_note_count: {result.trimmed_note_count}",
        f"  final_note_count: {result.notes_written}",
        f"  final_payload_usage: {result.lyric_payload_bytes_used}/{result.lyric_payload_capacity} bytes",
        f"  last_surviving_lyric_fragment: {'' if result.last_surviving_lyric_fragment is None else _escaped_text(result.last_surviving_lyric_fragment)!r}",
        f"  notes_written: {result.notes_written}",
        f"  melody_marker_count: {result.melody_count_before} -> {result.melody_count_after}",
        f"  lyric_marker_count: {result.lyric_count_before} -> {result.lyric_count_after}",
        f"  lyric_payload_bytes: {result.lyric_payload_bytes_used}/{result.lyric_payload_capacity}",
        f"  chart_output_differs: {_format_bool(result.chart_diff.bytes_changed > 0)}",
        f"  chart_bytes_changed: {result.chart_diff.bytes_changed}",
        f"  lyric_bytes_changed: {result.lyric_diff.bytes_changed}",
        f"  chart_changed_ranges: {_format_ranges(result.chart_diff.changed_ranges)}",
        f"  lyric_changed_ranges: {_format_ranges(result.lyric_diff.changed_ranges)}",
        f"  lyric_worddata_offset_length_bounds: {'ok' if result.lyric_worddata_bounds_valid else 'failed'}",
        f"  string_length_fields_changed: {_format_bool(result.string_length_fields_changed)}",
        f"  pointer_looking_fields_changed: {_format_bool(result.pointer_looking_fields_changed)}",
        f"  moved_unused_melody_markers: {result.moved_unused_melody_count}",
        f"  moved_unused_lyric_markers: {result.moved_unused_lyric_count}",
        f"  melody_records_changed: {len(result.melody_changes)}",
        f"  lyric_records_changed: {len(result.lyric_changes)}",
        "  input_format: temporary JSON debug format; UltraStar TXT remains the target frontend",
    ]
    if result.lyric_text_overwrite is not None:
        overwrite = result.lyric_text_overwrite
        lines.extend(
            [
                "  lyric_text_overwrite:",
                f"    selected_by: {overwrite.selected_by}",
                f"    selected_text_resource_index: {overwrite.resource_index}",
                f"    coverage: {'n/a' if overwrite.coverage_markers_in_bounds is None or overwrite.coverage_total_markers is None else f'{overwrite.coverage_markers_in_bounds}/{overwrite.coverage_total_markers}'}",
                f"    coverage_ratio: {'n/a' if overwrite.coverage_ratio is None else f'{overwrite.coverage_ratio:.1%}'}",
                f"    payload_length_field: 0x{overwrite.payload_length_offset:08X}={overwrite.payload_length_value}",
                f"    payload_range: 0x{overwrite.range_start:08X}-0x{overwrite.range_end - 1:08X}",
                f"    payload_length: {overwrite.original_range_length}",
                f"    visible_text_range: 0x{overwrite.visible_range_start:08X}-0x{overwrite.visible_range_end - 1:08X}",
                f"    visible_text_length: {overwrite.original_visible_length}",
                f"    new_text_byte_length: {overwrite.new_text_byte_length}",
                f"    padding_byte: 0x{overwrite.padding_byte:02X}",
                f"    visible_fill_byte: 0x{overwrite.visible_fill_byte:02X}",
                f"    prefix_char_length: {overwrite.prefix_char_length}",
                f"    bom_preserved: {_format_bool(overwrite.bom_preserved)}",
                f"    trailing_padding_preserved: {_format_bool(overwrite.trailing_padding_preserved)}",
                f"    changed_only_selected_payload: {_format_bool(overwrite.changed_only_detected_range)}",
                "    metadata_fields_changed: no",
            ]
        )
        if overwrite.selected_by == "heuristic":
            lines.append(
                "    warning: no chart LyricWordData coverage was available; selected lyric text by heuristic fallback"
            )
    if result.melody_preview:
        lines.append("  melody_preview_first10_chronological:")
        for row in result.melody_preview:
            lines.append(
                "    "
                f"chronological_index={row.chronological_index} "
                f"offset=0x{row.offset:08X} "
                f"time {row.old_time:.6f}->{row.new_time:.6f} "
                f"length {row.old_length:.6f}->{row.new_length:.6f} "
                f"raw_pitch {row.old_raw_pitch}->{row.new_raw_pitch} "
                f"tone {row.old_tone:.6f}->{row.new_tone:.6f} "
                f"octave {row.old_octave}->{row.new_octave}"
            )
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
                f" tone {change.old_tone:.6f}->{change.new_tone:.6f}"
                f" octave {change.old_octave}->{change.new_octave}"
            )
    if result.lyric_mapping_validation:
        lines.append("  lyric_worddata_mapping_validation:")
        for row in result.lyric_mapping_validation:
            lines.append(
                "    "
                f"chronological_index={row.chronological_index} "
                f"object_index={row.object_index} "
                f"offset=0x{row.offset:08X} "
                f"text={row.text_offset}/{row.text_length} "
                f"expected={_escaped_text(row.expected_text)!r} "
                f"resolved={_escaped_text(row.resolved_text)!r} "
                f"match={_format_bool(row.match)} "
                f"warning={row.warning}"
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
    parser.add_argument("json_chart", nargs="?", type=Path, help="Temporary JSON chart model")
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
        "--lyric-text-only",
        action="store_true",
        help="Legacy alias for safe visible-text overwrite; leave chart records unchanged",
    )
    parser.add_argument(
        "--lyric-text-overwrite-only",
        action="store_true",
        help="Overwrite only the existing visible _Lyric.X360 text byte range; leave chart records unchanged",
    )
    parser.add_argument(
        "--lyric-worddata-only",
        action="store_true",
        help="Patch only LyricWordData text offsets/lengths; leave lyric text, MelodyMarkers, and LyricMarkers unchanged",
    )
    parser.add_argument(
        "--lyric-marker-only",
        action="store_true",
        help="Patch only LyricMarker timing/length/track/end-word fields; leave lyric text, WordData, and MelodyMarkers unchanged",
    )
    parser.add_argument(
        "--flat-pitch-test",
        action="store_true",
        help=(
            "Patch only the first 30 chronological MelodyMarkers to raw_pitch 65, "
            "updating tone/octave while preserving timing and length"
        ),
    )
    parser.add_argument(
        "--no-disable-unused",
        action="store_true",
        help="Do not move unused MelodyMarkers or LyricMarkers later in the template",
    )
    parser.add_argument(
        "--debug-lyric-payload",
        action="store_true",
        help="Dump the generated selected lyric Text payload as hex, UTF-8 preview, and escaped text",
    )
    parser.add_argument(
        "--compare-lyric-payload",
        action="store_true",
        help="Print original/generated visible lyric payload previews and first bytes before/after",
    )
    parser.add_argument(
        "--payload-preview-bytes",
        type=int,
        default=256,
        help="Number of first selected-payload bytes to show in --compare-lyric-payload",
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
        lyric_text_only=args.lyric_text_only,
        lyric_text_overwrite_only=args.lyric_text_overwrite_only,
        lyric_worddata_only=args.lyric_worddata_only,
        lyric_marker_only=args.lyric_marker_only,
        flat_pitch_test=args.flat_pitch_test,
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
    if args.debug_lyric_payload or args.compare_lyric_payload:
        original_lyric_data = args.template_lyric.read_bytes()
        if args.debug_lyric_payload:
            print("\n".join(format_lyric_payload_debug(original_lyric_data, result)))
        if args.compare_lyric_payload:
            print(
                "\n".join(
                    format_lyric_payload_comparison(
                        original_lyric_data,
                        result,
                        preview_bytes=args.payload_preview_bytes,
                    )
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
