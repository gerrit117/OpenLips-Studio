#!/usr/bin/env python3
"""Patch the first lpsMelodyMarker timings in a Lips .X360 chart."""

from __future__ import annotations

import argparse
import os
import struct
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

try:
    from tools.extract_melody_markers import (
        COMPRESSED_MAGICS,
        MelodyMarker,
        melody_layouts_from_schema,
        parse_ixb_document,
        iter_melody_markers_object_walker,
    )
except ModuleNotFoundError:
    from extract_melody_markers import (
        COMPRESSED_MAGICS,
        MelodyMarker,
        melody_layouts_from_schema,
        parse_ixb_document,
        iter_melody_markers_object_walker,
    )


DEFAULT_TIMES = tuple(float(value) for value in range(20, 30))
MUTE_FIRST_PHRASE_COUNT = 20
MUTE_FIRST_PHRASE_SHIFT_SECONDS = 60.0
PITCH_DEMO_COUNT = 20
PITCH_DEMO_RAW_PITCH = 70
PITCH_ZIGZAG_COUNT = 30
PITCH_ZIGZAG_PATTERN = (45, 75)


@dataclass(frozen=True)
class PatchSite:
    offset: int
    object_order_index: int
    chronological_index: int
    time_offset: int
    length_offset: int
    raw_pitch_offset: int
    tone_offset: int
    octave_offset: int
    original_time: float
    length: float
    original_raw_pitch: int
    original_tone: float
    original_octave: int
    new_time: float | None = None
    new_raw_pitch: int | None = None
    new_tone: float | None = None
    new_octave: int | None = None


@dataclass(frozen=True)
class PatchResult:
    patched_data: bytes
    sites: list[PatchSite]
    before_markers: list[MelodyMarker]
    after_markers: list[MelodyMarker]


def _structural_markers(data: bytes) -> list[MelodyMarker]:
    document = parse_ixb_document(data)
    return sorted(iter_melody_markers_object_walker(data, document), key=lambda marker: marker.offset)


def _iter_patch_sites(data: bytes, markers: Iterable[MelodyMarker]) -> Iterable[PatchSite]:
    document = parse_ixb_document(data)
    layouts = melody_layouts_from_schema(data, document.classes)
    file_layouts = [layout for layout in layouts if layout.scan_prefix == 1 and layout.class_index is not None]
    if not file_layouts:
        raise ValueError("IXB schema does not define a patchable lpsMelodyMarker file layout")

    sorted_by_time = sorted(markers, key=lambda marker: (marker.time, marker.offset))
    chronological_indexes = {marker.offset: index for index, marker in enumerate(sorted_by_time, start=1)}
    for object_order_index, marker in enumerate(markers, start=1):
        layout = None
        for file_layout in file_layouts:
            if data[marker.offset] == file_layout.class_index:
                layout = file_layout
                break
        if layout is None:
            raise ValueError(f"schema/object-walker marker at 0x{marker.offset:08X} has no patchable file layout")
        base = marker.offset + layout.scan_prefix
        yield PatchSite(
            offset=marker.offset,
            object_order_index=object_order_index,
            chronological_index=chronological_indexes[marker.offset],
            time_offset=base + layout.time,
            length_offset=base + layout.length,
            raw_pitch_offset=base + layout.raw_pitch,
            tone_offset=base + layout.tone,
            octave_offset=base + layout.octave,
            original_time=marker.time,
            length=marker.length,
            original_raw_pitch=marker.raw_pitch,
            original_tone=marker.tone,
            original_octave=marker.octave,
        )


def find_patch_sites(data: bytes) -> list[PatchSite]:
    markers = _structural_markers(data)
    if not markers:
        return []
    return sorted(_iter_patch_sites(data, markers), key=lambda site: site.offset)


def patch_first_melody_timings(
    data: bytes,
    times: Iterable[float] = DEFAULT_TIMES,
) -> PatchResult:
    new_times = list(times)
    before_markers = _structural_markers(data)
    if not before_markers:
        raise ValueError("no schema/object-walker lpsMelodyMarker records found")
    all_sites = list(_iter_patch_sites(data, before_markers))
    sites = sorted(all_sites, key=lambda site: (site.original_time, site.offset))
    if len(sites) < len(new_times):
        raise ValueError(f"found {len(sites)} schema/object-walker MelodyMarker records, need {len(new_times)}")
    selected_sites = [
        replace(site, new_time=new_time)
        for site, new_time in zip(sites, new_times)
    ]

    patched = bytearray(data)
    for site in selected_sites:
        if site.new_time is None:
            raise ValueError("internal error: patch site missing new time")
        struct.pack_into(">f", patched, site.time_offset, site.new_time)
        struct.pack_into(">f", patched, site.length_offset, site.length)

    patched_data = bytes(patched)
    after_markers = _structural_markers(patched_data)
    if len(before_markers) != len(after_markers):
        raise ValueError(f"object count changed from {len(before_markers)} to {len(after_markers)}")
    if len(patched_data) != len(data):
        raise ValueError("file size changed unexpectedly")
    return PatchResult(patched_data, selected_sites, before_markers, after_markers)


def patch_mute_first_phrase_visual_test(data: bytes) -> PatchResult:
    before_markers = _structural_markers(data)
    if not before_markers:
        raise ValueError("no schema/object-walker lpsMelodyMarker records found")
    sites = sorted(_iter_patch_sites(data, before_markers), key=lambda site: (site.original_time, site.offset))
    if len(sites) < MUTE_FIRST_PHRASE_COUNT:
        raise ValueError(
            f"found {len(sites)} schema/object-walker MelodyMarker records, need {MUTE_FIRST_PHRASE_COUNT}"
        )
    new_times = [
        site.original_time + MUTE_FIRST_PHRASE_SHIFT_SECONDS
        for site in sites[:MUTE_FIRST_PHRASE_COUNT]
    ]
    return patch_first_melody_timings(data, new_times)


def _tone_octave_for_raw_pitch(raw_pitch: int) -> tuple[float, int]:
    return float((55 - raw_pitch) % 12), 6 + ((55 - raw_pitch) // 12)


def patch_pitch_demo(data: bytes, raw_pitch: int = PITCH_DEMO_RAW_PITCH) -> PatchResult:
    before_markers = _structural_markers(data)
    if not before_markers:
        raise ValueError("no schema/object-walker lpsMelodyMarker records found")
    sites = sorted(_iter_patch_sites(data, before_markers), key=lambda site: (site.original_time, site.offset))
    if len(sites) < PITCH_DEMO_COUNT:
        raise ValueError(f"found {len(sites)} schema/object-walker MelodyMarker records, need {PITCH_DEMO_COUNT}")

    tone, octave = _tone_octave_for_raw_pitch(raw_pitch)
    selected_sites = [
        replace(site, new_raw_pitch=raw_pitch, new_tone=tone, new_octave=octave)
        for site in sites[:PITCH_DEMO_COUNT]
    ]

    patched = bytearray(data)
    for site in selected_sites:
        if site.new_raw_pitch is None or site.new_tone is None or site.new_octave is None:
            raise ValueError("internal error: patch site missing new pitch")
        struct.pack_into(">i", patched, site.raw_pitch_offset, site.new_raw_pitch)
        struct.pack_into(">f", patched, site.tone_offset, site.new_tone)
        struct.pack_into(">i", patched, site.octave_offset, site.new_octave)

    patched_data = bytes(patched)
    after_markers = _structural_markers(patched_data)
    if len(before_markers) != len(after_markers):
        raise ValueError(f"object count changed from {len(before_markers)} to {len(after_markers)}")
    if len(patched_data) != len(data):
        raise ValueError("file size changed unexpectedly")
    return PatchResult(patched_data, selected_sites, before_markers, after_markers)


def patch_pitch_zigzag(data: bytes, update_tone_octave: bool) -> PatchResult:
    before_markers = _structural_markers(data)
    if not before_markers:
        raise ValueError("no schema/object-walker lpsMelodyMarker records found")
    sites = sorted(_iter_patch_sites(data, before_markers), key=lambda site: (site.original_time, site.offset))
    if len(sites) < PITCH_ZIGZAG_COUNT:
        raise ValueError(f"found {len(sites)} schema/object-walker MelodyMarker records, need {PITCH_ZIGZAG_COUNT}")

    selected_sites: list[PatchSite] = []
    for index, site in enumerate(sites[:PITCH_ZIGZAG_COUNT]):
        raw_pitch = PITCH_ZIGZAG_PATTERN[index % len(PITCH_ZIGZAG_PATTERN)]
        if update_tone_octave:
            tone, octave = _tone_octave_for_raw_pitch(raw_pitch)
        else:
            tone, octave = site.original_tone, site.original_octave
        selected_sites.append(replace(site, new_raw_pitch=raw_pitch, new_tone=tone, new_octave=octave))

    patched = bytearray(data)
    for site in selected_sites:
        if site.new_raw_pitch is None or site.new_tone is None or site.new_octave is None:
            raise ValueError("internal error: patch site missing new pitch")
        struct.pack_into(">i", patched, site.raw_pitch_offset, site.new_raw_pitch)
        if update_tone_octave:
            struct.pack_into(">f", patched, site.tone_offset, site.new_tone)
            struct.pack_into(">i", patched, site.octave_offset, site.new_octave)

    patched_data = bytes(patched)
    after_markers = _structural_markers(patched_data)
    if len(before_markers) != len(after_markers):
        raise ValueError(f"object count changed from {len(before_markers)} to {len(after_markers)}")
    if len(patched_data) != len(data):
        raise ValueError("file size changed unexpectedly")
    return PatchResult(patched_data, selected_sites, before_markers, after_markers)


def default_output_path(input_path: Path, mode: str = "patch-demo") -> Path:
    suffixes = {
        "mute-first-phrase-visual-test": "mute_first_phrase_visual_test",
        "pitch-demo": "pitch_demo",
        "pitch-zigzag-raw-only": "pitch_zigzag_raw_only",
        "pitch-zigzag-full": "pitch_zigzag_full",
    }
    suffix = suffixes.get(mode, "patched_demo")
    return input_path.with_name(f"{input_path.stem}_{suffix}{input_path.suffix}")


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


def patch_file(input_path: Path, output_path: Path, force: bool = False, mode: str = "patch-demo") -> PatchResult:
    data = input_path.read_bytes()
    magic = data[:4]
    if magic in COMPRESSED_MAGICS:
        raise ValueError(f"{input_path} is {COMPRESSED_MAGICS[magic]}; decompress it before patching")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("refusing to modify the original file in place; choose a different output path")

    if mode == "mute-first-phrase-visual-test":
        result = patch_mute_first_phrase_visual_test(data)
    elif mode == "pitch-demo":
        result = patch_pitch_demo(data)
    elif mode == "pitch-zigzag-raw-only":
        result = patch_pitch_zigzag(data, update_tone_octave=False)
    elif mode == "pitch-zigzag-full":
        result = patch_pitch_zigzag(data, update_tone_octave=True)
    else:
        result = patch_first_melody_timings(data)
    write_output_rollback_safe(output_path, result.patched_data, force=force)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch the first 10 Lips lpsMelodyMarker records to times 20.0 through 29.0."
    )
    parser.add_argument("input", type=Path, help="Input Lips .X360 chart file")
    parser.add_argument("output", type=Path, nargs="?", help="Patched output .X360 chart file")
    parser.add_argument("--out", type=Path, help="Patched output .X360 chart file")
    parser.add_argument("--patch-demo", action="store_true", help="Patch the first 10 MelodyMarkers to 20.0 through 29.0")
    parser.add_argument(
        "--mute-first-phrase-visual-test",
        action="store_true",
        help="Move the first 20 chronological MelodyMarkers 60 seconds later",
    )
    parser.add_argument(
        "--pitch-demo",
        action="store_true",
        help="Set raw_pitch to 70 for the first 20 chronological MelodyMarkers",
    )
    parser.add_argument(
        "--pitch-zigzag-raw-only",
        action="store_true",
        help="Alternate raw_pitch 45/75 for the first 30 chronological MelodyMarkers without touching tone/octave",
    )
    parser.add_argument(
        "--pitch-zigzag-full",
        action="store_true",
        help="Alternate raw_pitch 45/75 for the first 30 chronological MelodyMarkers and update tone/octave",
    )
    parser.add_argument("--force", action="store_true", help="Allow overwriting an existing output file")
    return parser.parse_args(argv)


def format_validation(result: PatchResult, output_path: Path, mode: str) -> list[str]:
    pitch_modes = {"pitch-demo", "pitch-zigzag-raw-only", "pitch-zigzag-full"}
    if mode == "pitch-zigzag-raw-only":
        patched_fields = "raw_pitch"
    elif mode in pitch_modes:
        patched_fields = "raw_pitch, tone, octave"
    else:
        patched_fields = "trigger timing, length"
    lines = [
        "before/after validation:",
        f"  output: {output_path}",
        f"  file_size: {len(result.patched_data)} bytes",
        f"  marker_count_before: {len(result.before_markers)}",
        f"  marker_count_after: {len(result.after_markers)}",
        "patch summary:",
        f"  patched_records: {len(result.sites)}",
        f"  patched_fields: {patched_fields}",
        "  mode: schema/object-walker",
        f"  demo_mode: {mode}",
    ]
    for site in result.sites:
        prefix = (
            f"  object_index={site.object_order_index} "
            f"chronological_index={site.chronological_index} "
            f"offset=0x{site.offset:08X} "
        )
        if mode in pitch_modes:
            if site.new_raw_pitch is None or site.new_tone is None or site.new_octave is None:
                raise ValueError("internal error: patch site missing new pitch")
            lines.append(
                prefix
                + f"old_time={site.original_time:.6f} "
                + f"raw_pitch {site.original_raw_pitch} -> {site.new_raw_pitch} "
                + f"tone {site.original_tone:.6f} -> {site.new_tone:.6f} "
                + f"octave {site.original_octave} -> {site.new_octave}"
            )
        else:
            if site.new_time is None:
                raise ValueError("internal error: patch site missing new time")
            lines.append(
                prefix
                + f"old_time={site.original_time:.6f} new_time={site.new_time:.6f} "
                + f"length preserved {site.length:.6f}"
            )
    return lines


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    selected_modes = [
        args.patch_demo,
        args.mute_first_phrase_visual_test,
        args.pitch_demo,
        args.pitch_zigzag_raw_only,
        args.pitch_zigzag_full,
    ]
    if sum(1 for selected in selected_modes if selected) != 1:
        print(
            "error: choose exactly one mode: --patch-demo, --mute-first-phrase-visual-test, "
            "--pitch-demo, --pitch-zigzag-raw-only, or --pitch-zigzag-full",
            file=sys.stderr,
        )
        return 2
    if args.mute_first_phrase_visual_test:
        mode = "mute-first-phrase-visual-test"
    elif args.pitch_demo:
        mode = "pitch-demo"
    elif args.pitch_zigzag_raw_only:
        mode = "pitch-zigzag-raw-only"
    elif args.pitch_zigzag_full:
        mode = "pitch-zigzag-full"
    else:
        mode = "patch-demo"
    output_path = args.out or args.output or default_output_path(args.input, mode=mode)
    try:
        result = patch_file(args.input, output_path, force=args.force, mode=mode)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print("\n".join(format_validation(result, output_path, mode)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
