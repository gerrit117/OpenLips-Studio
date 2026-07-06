#!/usr/bin/env python3
"""Read-only diagnostics for Lips *_Lyric.X360 IXB files.

This tool intentionally does not patch or rewrite anything. It tries to map the
raw lyric text resources before the template writer learns to edit them again.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from tools.extract_melody_markers import (
        COMPRESSED_MAGICS,
        _u32be,
        describe_magic,
        find_fileio_header_candidates,
        iter_melody_markers_object_walker,
        parse_ixb_document,
        probe_object_record_headers,
        validate_ixb_write_order,
    )
    from tools.patch_lyrics_mapping import iter_lyric_markers_structural
except ModuleNotFoundError:
    from extract_melody_markers import (
        COMPRESSED_MAGICS,
        _u32be,
        describe_magic,
        find_fileio_header_candidates,
        iter_melody_markers_object_walker,
        parse_ixb_document,
        probe_object_record_headers,
        validate_ixb_write_order,
    )
    from patch_lyrics_mapping import iter_lyric_markers_structural


MIN_TEXT_RUN = 8
PREVIEW_LIMIT = 90
TEXT_COVERAGE_THRESHOLD = 0.90


@dataclass(frozen=True)
class TextRun:
    start: int
    end: int
    encoding: str
    printable_ratio: float
    line_count: int
    preview: str


@dataclass(frozen=True)
class TextResource:
    type_name: str
    type_name_offset: int
    type_length_offset: int
    type_length: int
    payload_hash_offset: int
    payload_hash: int
    payload_length_offset: int
    payload_start: int
    payload_end: int
    payload_length: int
    visible_end: int
    padding_byte: int | None
    printable_ratio: float
    line_count: int
    utf8_ok: bool
    preview: str

    @property
    def visible_length(self) -> int:
        return self.visible_end - self.payload_start

    @property
    def is_visible_lyric_candidate(self) -> bool:
        return self.utf8_ok and self.printable_ratio >= 0.75 and self.line_count >= 2 and self.visible_length >= 16


@dataclass(frozen=True)
class ChartLyricCoverage:
    resource: TextResource
    decoded_chars: int
    markers_in_bounds: int
    markers_out_of_bounds: int
    min_text_offset: int | None
    max_text_end: int | None

    @property
    def total_markers(self) -> int:
        return self.markers_in_bounds + self.markers_out_of_bounds

    @property
    def coverage_ratio(self) -> float:
        return self.markers_in_bounds / self.total_markers if self.total_markers else 0.0


@dataclass(frozen=True)
class TextResourceSelection:
    resource: TextResource | None
    selected_by: str
    resource_index: int | None = None
    coverage: ChartLyricCoverage | None = None
    threshold: float = TEXT_COVERAGE_THRESHOLD


def _safe_preview(text: str, limit: int = PREVIEW_LIMIT) -> str:
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= limit:
        preview = text
    else:
        preview = text[: limit - 3] + "..."
    return preview.encode("ascii", errors="backslashreplace").decode("ascii")


def _decode_utf8(data: bytes) -> tuple[str, bool]:
    try:
        return data.decode("utf-8"), True
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), False


def _printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(1 for char in text if char.isprintable() or char in "\r\n\t\ufeff")
    return printable / len(text)


def _trim_padding(data: bytes) -> tuple[int, int | None]:
    visible_end = len(data)
    while visible_end > 0 and data[visible_end - 1] in (0x00, 0x20):
        visible_end -= 1
    padding = data[visible_end:]
    if not padding:
        return visible_end, None
    null_count = padding.count(0)
    space_count = padding.count(0x20)
    return visible_end, 0 if null_count > space_count else 0x20


def find_text_runs(data: bytes) -> list[TextRun]:
    runs: list[TextRun] = []
    start: int | None = None
    for index, value in enumerate(data + b"\x00"):
        is_textish = value in (0x09, 0x0A, 0x0D) or 0x20 <= value <= 0x7E or value >= 0x80
        if is_textish:
            if start is None:
                start = index
            continue
        if start is None:
            continue
        end = index
        if end - start >= MIN_TEXT_RUN:
            raw = data[start:end]
            text, utf8_ok = _decode_utf8(raw)
            ratio = _printable_ratio(text)
            if ratio >= 0.65:
                runs.append(
                    TextRun(
                        start=start,
                        end=end,
                        encoding="utf-8" if utf8_ok else "utf-8-replace",
                        printable_ratio=ratio,
                        line_count=text.count("\n"),
                        preview=_safe_preview(text),
                    )
                )
        start = None
    return runs


def _find_all(data: bytes, needle: bytes) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = data.find(needle, start)
        if offset < 0:
            return offsets
        offsets.append(offset)
        start = offset + 1


def find_text_resources(data: bytes) -> list[TextResource]:
    resources: list[TextResource] = []
    seen: set[tuple[int, int]] = set()
    for type_offset in _find_all(data, b"Text\x00"):
        if type_offset < 4:
            continue
        type_length_offset = type_offset - 4
        type_length = _u32be(data, type_length_offset)
        if type_length != 5:
            continue
        candidates: list[TextResource] = []
        for pad_count in range(0, 9):
            payload_hash_offset = type_offset + type_length + pad_count
            payload_length_offset = payload_hash_offset + 4
            payload_start = payload_length_offset + 4
            if payload_start > len(data):
                continue
            payload_length = _u32be(data, payload_length_offset)
            payload_end = payload_start + payload_length
            if payload_length <= 0 or payload_end > len(data):
                continue
            payload = data[payload_start:payload_end]
            text, utf8_ok = _decode_utf8(payload)
            ratio = _printable_ratio(text)
            line_count = text.count("\n")
            key = (payload_start, payload_end)
            if key in seen:
                continue
            visible_len, padding_byte = _trim_padding(payload)
            candidates.append(
                TextResource(
                    type_name="Text",
                    type_name_offset=type_offset,
                    type_length_offset=type_length_offset,
                    type_length=type_length,
                    payload_hash_offset=payload_hash_offset,
                    payload_hash=_u32be(data, payload_hash_offset),
                    payload_length_offset=payload_length_offset,
                    payload_start=payload_start,
                    payload_end=payload_end,
                    payload_length=payload_length,
                    visible_end=payload_start + visible_len,
                    padding_byte=padding_byte,
                    printable_ratio=ratio,
                    line_count=line_count,
                    utf8_ok=utf8_ok,
                    preview=_safe_preview(text),
                )
            )
        if not candidates:
            continue
        candidates.sort(
            key=lambda resource: (
                resource.is_visible_lyric_candidate,
                resource.line_count,
                resource.printable_ratio,
                resource.visible_length,
            ),
            reverse=True,
        )
        selected = candidates[0]
        seen.add((selected.payload_start, selected.payload_end))
        resources.append(selected)
    return sorted(resources, key=lambda resource: resource.payload_start)


def _pointer_like_refs(data: bytes, start: int, end: int) -> list[int]:
    refs: list[int] = []
    for offset in range(0, max(0, len(data) - 3)):
        value = _u32be(data, offset)
        if start <= value < end:
            refs.append(offset)
    return refs


def _length_field_refs(data: bytes, length: int) -> list[int]:
    refs: list[int] = []
    for offset in range(0, max(0, len(data) - 3)):
        if _u32be(data, offset) == length:
            refs.append(offset)
    return refs


def _duplicate_resources(data: bytes, resources: list[TextResource]) -> dict[str, list[TextResource]]:
    groups: dict[str, list[TextResource]] = defaultdict(list)
    for resource in resources:
        payload = data[resource.payload_start : resource.visible_end]
        digest = hashlib.sha1(payload).hexdigest()
        groups[digest].append(resource)
    return {digest: group for digest, group in groups.items() if len(group) > 1}


def coverage_for_resource(resource: TextResource, lyric_data: bytes, lyric_markers: Sequence[object]) -> ChartLyricCoverage:
    decoded = lyric_data[resource.payload_start : resource.payload_end].decode("utf-8", errors="replace")
    decoded_chars = len(decoded)
    text_offsets = [marker.text_offset for marker in lyric_markers if hasattr(marker, "text_offset")]
    text_ends = [
        marker.text_offset + marker.text_length
        for marker in lyric_markers
        if hasattr(marker, "text_offset") and hasattr(marker, "text_length")
    ]
    in_bounds = sum(
        1
        for marker in lyric_markers
        if 0 <= marker.text_offset <= marker.text_offset + marker.text_length <= decoded_chars
    )
    out_of_bounds = len(lyric_markers) - in_bounds
    return ChartLyricCoverage(
        resource=resource,
        decoded_chars=decoded_chars,
        markers_in_bounds=in_bounds,
        markers_out_of_bounds=out_of_bounds,
        min_text_offset=min(text_offsets) if text_offsets else None,
        max_text_end=max(text_ends) if text_ends else None,
    )


def compute_resource_coverages(
    resources: Sequence[TextResource],
    lyric_data: bytes,
    lyric_markers: Sequence[object],
) -> list[ChartLyricCoverage]:
    return [coverage_for_resource(resource, lyric_data, lyric_markers) for resource in resources]


def select_text_resource(
    lyric_data: bytes,
    lyric_markers: Sequence[object] | None = None,
    threshold: float = TEXT_COVERAGE_THRESHOLD,
) -> TextResourceSelection:
    resources = find_text_resources(lyric_data)
    if lyric_markers is not None:
        coverages = compute_resource_coverages(resources, lyric_data, lyric_markers)
        if coverages:
            best_index, best = max(
                enumerate(coverages, start=1),
                key=lambda item: (item[1].markers_in_bounds, item[1].resource.payload_length),
            )
            if best.total_markers and best.coverage_ratio >= threshold:
                return TextResourceSelection(
                    resource=best.resource,
                    selected_by="chart_worddata_coverage",
                    resource_index=best_index,
                    coverage=best,
                    threshold=threshold,
                )
            return TextResourceSelection(
                resource=None,
                selected_by="chart_worddata_coverage_below_threshold",
                resource_index=best_index,
                coverage=best,
                threshold=threshold,
            )

    candidates = [resource for resource in resources if resource.is_visible_lyric_candidate]
    if candidates:
        candidates.sort(key=lambda item: (item.line_count, item.printable_ratio, item.visible_length), reverse=True)
        return TextResourceSelection(
            resource=candidates[0],
            selected_by="heuristic",
            resource_index=resources.index(candidates[0]) + 1,
            threshold=threshold,
        )
    return TextResourceSelection(resource=None, selected_by="unsupported/unknown", threshold=threshold)


def analyze_chart(chart_path: Path, resources: list[TextResource], lyric_data: bytes) -> tuple[list[str], list[ChartLyricCoverage]]:
    data = chart_path.read_bytes()
    document = parse_ixb_document(data)
    melody = sorted(iter_melody_markers_object_walker(data, document), key=lambda marker: marker.offset)
    lyrics = iter_lyric_markers_structural(data)
    lines: list[str] = [
        "chart analysis:",
        f"  path: {chart_path}",
        f"  file_size: {len(data)}",
        f"  MelodyMarker count: {len(melody)}",
        f"  LyricMarker count: {len(lyrics)}",
    ]

    rounded_times = Counter(round(marker.time, 3) for marker in lyrics if math.isfinite(marker.time))
    duplicate_times = [(time, count) for time, count in rounded_times.items() if count > 1]
    duplicate_times.sort(key=lambda item: (-item[1], item[0]))
    lines.append(f"  duplicate_time_groups: {len(duplicate_times)}")
    if duplicate_times:
        preview = ", ".join(f"{time:.3f}s x{count}" for time, count in duplicate_times[:12])
        lines.append(f"  duplicate_time_group_preview: {preview}")

    track_counts = Counter(marker.track_index for marker in lyrics)
    lines.append(f"  track_index_values: {len(track_counts)}")
    if track_counts:
        preview = ", ".join(f"{value}:{count}" for value, count in track_counts.most_common(20))
        lines.append(f"  track_index_distribution: {preview}")

    end_word_counts = Counter(marker.end_of_word for marker in lyrics)
    lines.append(
        "  end_of_word_distribution: "
        + (", ".join(f"{value}:{count}" for value, count in sorted(end_word_counts.items())) if end_word_counts else "none")
    )

    text_offsets = [marker.text_offset for marker in lyrics]
    text_ends = [marker.text_offset + marker.text_length for marker in lyrics]
    if text_offsets and text_ends:
        lines.append(f"  LyricWordData text offset span: {min(text_offsets)}..{max(text_ends)} chars")
        repeated_offsets = sum(1 for count in Counter(text_offsets).values() if count > 1)
        lines.append(f"  repeated LyricWordData offsets: {repeated_offsets}")
    else:
        lines.append("  LyricWordData text offset span: none")

    coverages = compute_resource_coverages(resources, lyric_data, lyrics)
    for resource, coverage in zip(resources, coverages):
        lines.append(
            "  resource coverage: "
            f"payload=0x{resource.payload_start:08X}-0x{resource.payload_end - 1:08X} "
            f"decoded_chars={coverage.decoded_chars} markers_in_bounds={coverage.markers_in_bounds}/{len(lyrics)} "
            f"markers_out_of_bounds={coverage.markers_out_of_bounds} "
            f"coverage={coverage.coverage_ratio:.1%}"
        )

    selection = select_text_resource(lyric_data, lyrics)
    if selection.resource is None:
        detail = ""
        if selection.coverage is not None:
            detail = f" best_coverage={selection.coverage.coverage_ratio:.1%}"
        lines.append(f"  selected_text_resource: none selected_by={selection.selected_by}{detail}")
    else:
        detail = ""
        if selection.coverage is not None:
            detail = (
                f" coverage={selection.coverage.markers_in_bounds}/{selection.coverage.total_markers}"
                f" ({selection.coverage.coverage_ratio:.1%})"
            )
        lines.append(
            "  selected_text_resource: "
            f"payload=0x{selection.resource.payload_start:08X}-0x{selection.resource.payload_end - 1:08X} "
            f"resource_index={selection.resource_index} "
            f"selected_by={selection.selected_by}{detail}"
        )

    possible_groups: list[str] = []
    if duplicate_times and len(duplicate_times) > max(3, len(lyrics) // 20):
        possible_groups.append("many duplicate LyricMarker times")
    if track_counts and len(track_counts) > 2:
        possible_groups.append("many track_index values; field appears pitch-like in known charts")
    if coverages and any(coverage.markers_out_of_bounds for coverage in coverages):
        possible_groups.append("some LyricWordData offsets do not map into candidate text resources")
    lines.append("  possible mode/player grouping clues: " + ("; ".join(possible_groups) if possible_groups else "none obvious"))
    return lines, coverages


def analyze_lyric_file(lyric_path: Path, chart_path: Path | None = None) -> list[str]:
    data = lyric_path.read_bytes()
    magic, kind = describe_magic(data)
    lines = [
        "lyric file analysis:",
        f"  path: {lyric_path}",
        f"  file_size: {len(data)}",
        f"  magic: {magic} ({kind})",
    ]
    if data[:4] in COMPRESSED_MAGICS:
        lines.append("  status: compressed/unsupported for structural text diagnostics")
        return lines

    document = parse_ixb_document(data)
    write_order_warnings = validate_ixb_write_order(document)
    lines.extend(
        [
            (
                "  IXB header: "
                f"IsBigEndian={document.is_big_endian} IsText={document.is_text} "
                f"Platform={document.platform} NumOfElements={document.num_elements}"
            ),
            f"  objects_range: {document.objects_start}..{document.objects_end}",
            f"  UriList entries: {len(document.uri_entries)}",
            (
                "  write_order_warnings: "
                + ("; ".join(write_order_warnings) if write_order_warnings else "none")
            ),
            f"  object_record_candidates: {len(probe_object_record_headers(data, document))}",
            f"  FileIO_header_candidates: {len(find_fileio_header_candidates(data))}",
            f"  IXB classes present: {len(document.classes)}",
        ]
    )
    for cls in sorted(document.classes.values(), key=lambda item: item.index):
        lines.append(f"    class {cls.index}: {cls.name} size={cls.size}")

    text_runs = find_text_runs(data)
    lines.append(f"  ASCII/UTF-8 text ranges: {len(text_runs)}")
    for run in text_runs:
        lines.append(
            f"    0x{run.start:08X}-0x{run.end - 1:08X} len={run.end - run.start} "
            f"encoding={run.encoding} printable={run.printable_ratio:.2f} lines={run.line_count} "
            f"preview={run.preview!r}"
        )

    resources = find_text_resources(data)
    visible_candidates = [resource for resource in resources if resource.is_visible_lyric_candidate]
    lines.append(f"  Text resources: {len(resources)}")
    for resource in resources:
        pointer_refs = _pointer_like_refs(data, resource.payload_start, resource.payload_end)
        length_refs = _length_field_refs(data, resource.payload_length)
        lines.append(
            f"    payload=0x{resource.payload_start:08X}-0x{resource.payload_end - 1:08X} "
            f"len={resource.payload_length} visible_len={resource.visible_length} "
            f"type_len_field=0x{resource.type_length_offset:08X} payload_len_field=0x{resource.payload_length_offset:08X} "
            f"hash=0x{resource.payload_hash:08X}@0x{resource.payload_hash_offset:08X} "
            f"padding={'none' if resource.padding_byte is None else f'0x{resource.padding_byte:02X}'} "
            f"printable={resource.printable_ratio:.2f} lines={resource.line_count} "
            f"visible_candidate={'yes' if resource.is_visible_lyric_candidate else 'no'}"
        )
        lines.append(f"      preview={resource.preview!r}")
        lines.append(
            f"      pointer_like_refs_into_payload={len(pointer_refs)} "
            f"({', '.join(f'0x{offset:08X}' for offset in pointer_refs[:8]) if pointer_refs else 'none'})"
        )
        lines.append(
            f"      payload_length_value_refs={len(length_refs)} "
            f"({', '.join(f'0x{offset:08X}' for offset in length_refs[:8]) if length_refs else 'none'})"
        )

    duplicates = _duplicate_resources(data, visible_candidates)
    lines.append(f"  candidate visible lyric payload ranges: {len(visible_candidates)}")
    lines.append(f"  visible lyrics appear: {'multiple times' if len(visible_candidates) > 1 else 'once' if visible_candidates else 'not found'}")
    lines.append(f"  duplicate visible text regions: {len(duplicates)}")
    for digest, group in duplicates.items():
        ranges = ", ".join(f"0x{item.payload_start:08X}-0x{item.visible_end - 1:08X}" for item in group)
        lines.append(f"    sha1={digest[:12]} count={len(group)} ranges={ranges}")

    if chart_path is not None:
        chart_lines, _ = analyze_chart(chart_path, resources, data)
        lines.extend(chart_lines)
    else:
        selection = select_text_resource(data)
        if selection.resource is None:
            lines.append(f"  selected_text_resource: none selected_by={selection.selected_by}")
        else:
            lines.append(
                "  selected_text_resource: "
                f"payload=0x{selection.resource.payload_start:08X}-0x{selection.resource.payload_end - 1:08X} "
                f"resource_index={selection.resource_index} "
                f"selected_by={selection.selected_by}"
            )
    return lines


def _matching_pairs(lyrics_dir: Path, charts_dir: Path) -> list[tuple[str, Path, Path]]:
    charts = {path.stem: path for path in charts_dir.glob("*.X360") if not path.name.endswith("_Lyric.X360")}
    lyrics = {
        path.name[: -len("_Lyric.X360")]: path
        for path in lyrics_dir.glob("*_Lyric.X360")
    }
    return sorted((name, charts[name], lyrics[name]) for name in charts.keys() & lyrics.keys())


def batch_summary(lyrics_dir: Path, charts_dir: Path) -> list[str]:
    pairs = _matching_pairs(lyrics_dir, charts_dir)
    lines = [
        f"matching_pairs: {len(pairs)}",
        (
            "filename | text_resources | payload_lengths | WordData coverage per resource | "
            "visible_candidate | proposed_by_coverage | conflict"
        ),
        "-" * 140,
    ]
    supported_ok = True
    for name, chart_path, lyric_path in pairs:
        lyric_data = lyric_path.read_bytes()
        if lyric_data[:4] in COMPRESSED_MAGICS:
            lines.append(f"{name} | compressed/unsupported | [] | none | none | none | unsupported")
            continue
        resources = find_text_resources(lyric_data)
        chart_data = chart_path.read_bytes()
        lyric_markers = iter_lyric_markers_structural(chart_data)
        coverages = compute_resource_coverages(resources, lyric_data, lyric_markers)
        selection = select_text_resource(lyric_data, lyric_markers)
        heuristic = [index for index, resource in enumerate(resources, start=1) if resource.is_visible_lyric_candidate]
        selected_index = None
        if selection.resource is not None:
            selected_index = next(
                (index for index, resource in enumerate(resources, start=1) if resource == selection.resource),
                None,
            )
        if selection.resource is None or selection.selected_by != "chart_worddata_coverage":
            supported_ok = False
        conflict = bool(selected_index and (not heuristic or selected_index not in heuristic))
        payloads = ", ".join(str(resource.payload_length) for resource in resources)
        coverage_text = ", ".join(
            f"R{index}:{coverage.markers_in_bounds}/{coverage.total_markers}({coverage.coverage_ratio:.1%})"
            for index, coverage in enumerate(coverages, start=1)
        )
        if selection.resource is None:
            proposed = f"none({selection.selected_by})"
        else:
            ratio = selection.coverage.coverage_ratio if selection.coverage else 0.0
            proposed = f"R{selected_index}({selection.selected_by}, {ratio:.1%})"
        lines.append(
            f"{name} | {len(resources)} | [{payloads}] | {coverage_text or 'none'} | "
            f"{heuristic or 'none'} | {proposed} | {'yes' if conflict else 'no'}"
        )
    lines.append(f"highest_worddata_coverage_selects_supported_plain_pairs: {'yes' if supported_ok else 'no'}")
    return lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Lips *_Lyric.X360 text resources without modifying files.")
    parser.add_argument("lyric_file", type=Path, nargs="?", help="Input *_Lyric.X360 file")
    parser.add_argument("--chart", type=Path, help="Matching chart .X360 file")
    parser.add_argument("--batch", type=Path, help="Directory containing *_Lyric.X360 files")
    parser.add_argument("--charts", type=Path, help="Directory containing matching chart .X360 files for --batch")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.batch:
            if args.charts is None:
                print("error: --batch requires --charts", file=sys.stderr)
                return 2
            lines = batch_summary(args.batch, args.charts)
        else:
            if args.lyric_file is None:
                print("error: lyric_file is required unless --batch is used", file=sys.stderr)
                return 2
            lines = analyze_lyric_file(args.lyric_file, args.chart)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
