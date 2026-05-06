#!/usr/bin/env python3
"""Patch Lips lpsLyricMarker -> LyricWordData text mapping in-place."""

from __future__ import annotations

import argparse
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from tools.extract_melody_markers import (
        COMPRESSED_MAGICS,
        IxbClass,
        MelodyMarker,
        _f32be,
        _i32be,
        _inherited_members,
        _schema_file_class_codes,
        _u32be,
        describe_magic,
        iter_melody_markers_object_walker,
        parse_ixb_document,
    )
except ModuleNotFoundError:
    from extract_melody_markers import (
        COMPRESSED_MAGICS,
        IxbClass,
        MelodyMarker,
        _f32be,
        _i32be,
        _inherited_members,
        _schema_file_class_codes,
        _u32be,
        describe_magic,
        iter_melody_markers_object_walker,
        parse_ixb_document,
    )


LYRIC_REPEAT_COUNT = 10
WORD_DATA_TEXT_OFFSET = 12
WORD_DATA_TEXT_LENGTH = 16


@dataclass(frozen=True)
class LyricMarker:
    offset: int
    body_offset: int
    object_index: int
    chronological_index: int
    time: float
    length: float
    track_index: int
    melody_pointer: int
    word_data_pointer: int
    word_data_file_offset: int
    text_offset: int
    text_length: int
    end_of_word: int


@dataclass(frozen=True)
class _LyricCandidate:
    offset: int
    body_offset: int
    time: float
    length: float
    track_index: int
    melody_pointer: int
    word_data_pointer: int
    vector_field_offset: int
    end_of_word: int


@dataclass(frozen=True)
class LyricPatchSite:
    lyric_marker: LyricMarker
    new_text_offset: int
    new_text_length: int
    old_fragment: str | None
    new_fragment: str | None


@dataclass(frozen=True)
class LyricPatchResult:
    patched_data: bytes
    before_markers: list[LyricMarker]
    after_markers: list[LyricMarker]
    melody_markers_before: list[MelodyMarker]
    melody_markers_after: list[MelodyMarker]
    sites: list[LyricPatchSite]


def _class_by_name(classes: dict[int, IxbClass], name: str) -> IxbClass | None:
    return next((cls for cls in classes.values() if cls.name == name), None)


def _collect_pointer_occurrences(data: bytes, start: int, end: int, values: set[int]) -> dict[int, list[int]]:
    occurrences: dict[int, list[int]] = {value: [] for value in values}
    if not values:
        return occurrences
    for offset in range(start, max(start, end - 3)):
        value = _u32be(data, offset)
        if value in values:
            occurrences[value].append(offset)
    return occurrences


def _resolve_word_data_file_offset(
    occurrences_by_pointer: dict[int, list[int]],
    lyric_marker_offset: int,
    pointer_value: int,
) -> int | None:
    occurrences = occurrences_by_pointer.get(pointer_value, [])
    candidates = [offset for offset in occurrences if offset != lyric_marker_offset]
    if not candidates:
        return None
    before_marker = [offset for offset in candidates if offset < lyric_marker_offset]
    return max(before_marker) if before_marker else candidates[0]


def _extract_fragment(text: str | None, offset: int, length: int) -> str | None:
    if text is None:
        return None
    if offset < 0 or length < 0 or offset + length > len(text):
        return None
    return text[offset : offset + length]


def load_matching_lyric_text(chart_path: Path, explicit_lyric_path: Path | None = None) -> str | None:
    lyric_path = explicit_lyric_path or chart_path.with_name(f"{chart_path.stem}_Lyric{chart_path.suffix}")
    if not lyric_path.exists():
        return None
    data = lyric_path.read_bytes()
    marker = data.find(b"\xef\xbb\xbf")
    if marker < 0:
        return None
    return data[marker:].decode("utf-8", errors="replace")


def iter_lyric_markers_structural(data: bytes) -> list[LyricMarker]:
    document = parse_ixb_document(data)
    lyric_class = _class_by_name(document.classes, "lpsLyricMarker")
    if not lyric_class or document.objects_start is None or document.objects_end is None:
        return []

    members = _inherited_members(document.classes, lyric_class)
    time_offset = members.get("m_fTriggerTiming", 8)
    length_offset = members.get("m_fLength", 12)
    track_offset = members.get("m_iTrackIndex", 16)
    melody_pointer_offset = members["m_pMelodyMarker"]
    vector_offset = members["m_vecLyricWordData"]
    end_of_word_offset = members.get("m_bEndOfWord", 60)
    class_codes = set(_schema_file_class_codes(lyric_class))

    candidates: list[_LyricCandidate] = []
    end = document.objects_end - 1 - lyric_class.size + 1
    for offset in range(document.objects_start, max(document.objects_start, end)):
        if data[offset] not in class_codes:
            continue
        body = offset + 1
        try:
            time = _f32be(data, body + time_offset)
            length = _f32be(data, body + length_offset)
            track_index = _i32be(data, body + track_offset)
            melody_pointer = _u32be(data, body + melody_pointer_offset)
            word_data_pointer = _u32be(data, body + vector_offset)
            vector_reserve = _u32be(data, body + vector_offset + 4)
            vector_size = _u32be(data, body + vector_offset + 8)
            end_of_word = _u32be(data, body + end_of_word_offset)
        except (struct.error, KeyError):
            continue
        if not (0.0 <= time <= 900.0 and 0.0 <= length <= 20.0):
            continue
        if not (0 < vector_size <= 8 and 0 < vector_reserve <= 0x1000):
            continue
        candidates.append(
            _LyricCandidate(
                offset=offset,
                body_offset=body,
                time=time,
                length=length,
                track_index=track_index,
                melody_pointer=melody_pointer,
                word_data_pointer=word_data_pointer,
                vector_field_offset=body + vector_offset,
                end_of_word=end_of_word,
            )
        )

    occurrences_by_pointer = _collect_pointer_occurrences(
        data,
        document.objects_start,
        document.objects_end,
        {candidate.word_data_pointer for candidate in candidates},
    )
    markers: list[LyricMarker] = []
    for candidate in candidates:
        word_data_file_offset = _resolve_word_data_file_offset(
            occurrences_by_pointer,
            candidate.vector_field_offset,
            candidate.word_data_pointer,
        )
        if word_data_file_offset is None or word_data_file_offset + WORD_DATA_TEXT_LENGTH + 4 > len(data):
            continue
        text_offset = _u32be(data, word_data_file_offset + WORD_DATA_TEXT_OFFSET)
        text_length = _u32be(data, word_data_file_offset + WORD_DATA_TEXT_LENGTH)
        if not (0 <= text_offset <= 0x100000 and 0 < text_length <= 0x1000):
            continue
        markers.append(
            LyricMarker(
                offset=candidate.offset,
                body_offset=candidate.body_offset,
                object_index=0,
                chronological_index=0,
                time=candidate.time,
                length=candidate.length,
                track_index=candidate.track_index,
                melody_pointer=candidate.melody_pointer,
                word_data_pointer=candidate.word_data_pointer,
                word_data_file_offset=word_data_file_offset,
                text_offset=text_offset,
                text_length=text_length,
                end_of_word=candidate.end_of_word,
            )
        )

    by_time = sorted(markers, key=lambda marker: (marker.time, marker.offset))
    chronological = {marker.offset: index for index, marker in enumerate(by_time, start=1)}
    by_offset = sorted(markers, key=lambda marker: marker.offset)
    object_order = {marker.offset: index for index, marker in enumerate(by_offset, start=1)}
    return [
        LyricMarker(
            offset=marker.offset,
            body_offset=marker.body_offset,
            object_index=object_order[marker.offset],
            chronological_index=chronological[marker.offset],
            time=marker.time,
            length=marker.length,
            track_index=marker.track_index,
            melody_pointer=marker.melody_pointer,
            word_data_pointer=marker.word_data_pointer,
            word_data_file_offset=marker.word_data_file_offset,
            text_offset=marker.text_offset,
            text_length=marker.text_length,
            end_of_word=marker.end_of_word,
        )
        for marker in by_offset
    ]


def patch_lyric_repeat_test(data: bytes, lyric_text: str | None = None) -> LyricPatchResult:
    before_markers = iter_lyric_markers_structural(data)
    if len(before_markers) < LYRIC_REPEAT_COUNT:
        raise ValueError(f"found {len(before_markers)} structural LyricMarkers, need {LYRIC_REPEAT_COUNT}")

    chronological = sorted(before_markers, key=lambda marker: (marker.time, marker.offset))
    selected = chronological[:LYRIC_REPEAT_COUNT]
    source = selected[0]
    patched = bytearray(data)
    sites: list[LyricPatchSite] = []
    for marker in selected:
        struct.pack_into(">I", patched, marker.word_data_file_offset + WORD_DATA_TEXT_OFFSET, source.text_offset)
        struct.pack_into(">I", patched, marker.word_data_file_offset + WORD_DATA_TEXT_LENGTH, source.text_length)
        sites.append(
            LyricPatchSite(
                lyric_marker=marker,
                new_text_offset=source.text_offset,
                new_text_length=source.text_length,
                old_fragment=_extract_fragment(lyric_text, marker.text_offset, marker.text_length),
                new_fragment=_extract_fragment(lyric_text, source.text_offset, source.text_length),
            )
        )

    patched_data = bytes(patched)
    after_markers = iter_lyric_markers_structural(patched_data)
    before_melody = sorted(iter_melody_markers_object_walker(data, parse_ixb_document(data)), key=lambda marker: marker.offset)
    after_melody = sorted(
        iter_melody_markers_object_walker(patched_data, parse_ixb_document(patched_data)),
        key=lambda marker: marker.offset,
    )
    if len(patched_data) != len(data):
        raise ValueError("file size changed unexpectedly")
    if len(before_markers) != len(after_markers):
        raise ValueError(f"LyricMarker count changed from {len(before_markers)} to {len(after_markers)}")
    if len(before_melody) != len(after_melody):
        raise ValueError(f"MelodyMarker count changed from {len(before_melody)} to {len(after_melody)}")
    return LyricPatchResult(patched_data, before_markers, after_markers, before_melody, after_melody, sites)


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_lyric_repeat_test{input_path.suffix}")


def write_output_rollback_safe(output_path: Path, data: bytes, force: bool = False) -> None:
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


def patch_file(
    input_path: Path,
    output_path: Path,
    lyric_path: Path | None = None,
    force: bool = False,
) -> LyricPatchResult:
    data = input_path.read_bytes()
    _, kind = describe_magic(data)
    if data[:4] in COMPRESSED_MAGICS:
        raise ValueError(f"{input_path} is {kind}; decompress it before patching")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("refusing to modify the original file in place; choose a different output path")
    lyric_text = load_matching_lyric_text(input_path, lyric_path)
    result = patch_lyric_repeat_test(data, lyric_text)
    write_output_rollback_safe(output_path, result.patched_data, force=force)
    return result


def format_summary(result: LyricPatchResult, output_path: Path) -> list[str]:
    lines = [
        "before/after validation:",
        f"  output: {output_path}",
        f"  file_size: {len(result.patched_data)} bytes",
        f"  lyric_marker_count_before: {len(result.before_markers)}",
        f"  lyric_marker_count_after: {len(result.after_markers)}",
        f"  melody_marker_count_before: {len(result.melody_markers_before)}",
        f"  melody_marker_count_after: {len(result.melody_markers_after)}",
        "patch summary:",
        f"  patched_records: {len(result.sites)}",
        "  patched_fields: LyricWordData character offset, character length",
        "  mode: schema/object-walker",
        "  demo_mode: lyric-repeat-test",
    ]
    for site in result.sites:
        marker = site.lyric_marker
        old_fragment = repr(site.old_fragment) if site.old_fragment is not None else "<unavailable>"
        new_fragment = repr(site.new_fragment) if site.new_fragment is not None else "<unavailable>"
        lines.append(
            f"  lyric_index={marker.object_index} "
            f"chronological_index={marker.chronological_index} "
            f"offset=0x{marker.offset:08X} "
            f"time={marker.time:.6f} "
            f"melody_ptr=0x{marker.melody_pointer:08X} "
            f"word_data=0x{marker.word_data_file_offset:08X} "
            f"text {marker.text_offset}/{marker.text_length} -> {site.new_text_offset}/{site.new_text_length} "
            f"old_fragment={old_fragment} new_fragment={new_fragment}"
        )
    return lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patch Lips LyricMarker/LyricWordData mappings.")
    parser.add_argument("input", type=Path, help="Input Lips chart .X360 file")
    parser.add_argument("output", type=Path, nargs="?", help="Patched output .X360 chart file")
    parser.add_argument("--out", type=Path, help="Patched output .X360 chart file")
    parser.add_argument("--lyric", type=Path, help="Matching *_Lyric.X360 file for debug text fragments")
    parser.add_argument("--lyric-repeat-test", action="store_true", help="Repeat the first existing lyric fragment on the first 10 chronological LyricMarkers")
    parser.add_argument("--force", action="store_true", help="Allow overwriting an existing output file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.lyric_repeat_test:
        print("error: choose --lyric-repeat-test", file=sys.stderr)
        return 2
    output_path = args.out or args.output or default_output_path(args.input)
    try:
        result = patch_file(args.input, output_path, lyric_path=args.lyric, force=args.force)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("\n".join(format_summary(result, output_path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
