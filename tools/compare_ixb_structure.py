#!/usr/bin/env python3
"""Compare a real Lips IXB chart/lyric pair with a synthetic pair.

The report is intentionally semantic: class inventory, known marker/resource
counts, text coverage, and likely object graph gaps. It is not a raw byte diff.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from tools.analyze_lyric_file import find_text_resources, select_text_resource
    from tools.extract_melody_markers import (
        IxbClass,
        MelodyMarker,
        _schema_file_class_codes,
        describe_magic,
        find_fileio_header_candidates,
        iter_melody_markers,
        parse_ixb_document,
        probe_object_record_headers,
        validate_ixb_write_order,
    )
    from tools.patch_lyrics_mapping import LyricMarker, iter_lyric_markers_structural
except ModuleNotFoundError:
    from analyze_lyric_file import find_text_resources, select_text_resource
    from extract_melody_markers import (
        IxbClass,
        MelodyMarker,
        _schema_file_class_codes,
        describe_magic,
        find_fileio_header_candidates,
        iter_melody_markers,
        parse_ixb_document,
        probe_object_record_headers,
        validate_ixb_write_order,
    )
    from patch_lyrics_mapping import LyricMarker, iter_lyric_markers_structural


ROLE_CLASSES = {
    "package graph": (
        "ixTreeNode<ixPackage>",
        "ixPackage",
        "ixList<ixPackage",
        "ixVector<ixPackage",
        "ixDblCnt<ixPackage",
    ),
    "asset/resource graph": (
        "ixAssetPackage",
        "ixAsset",
        "ixFileImage",
        "ixRawFileImage",
        "ixVector<char",
        "ixVector<ixAsset",
    ),
    "chart roots/sequences": (
        "ixChart",
        "lpsChart",
        "ixSequence",
        "ixTempoMap",
        "lpsMusicInfo",
        "lpsMusicIndex",
        "ixSeq",
    ),
    "gameplay markers": (
        "lpsMelodyMarker",
        "lpsLyricMarker",
        "lpsLyricWordData",
        "lpsPhraseMarker",
        "lpsPageBreakMarker",
        "lpsHitMarker",
        "lpsShortEndMarker",
    ),
}


@dataclass(frozen=True)
class TextSelectionSummary:
    resource_count: int
    selected_by: str
    selected_index: int | None
    selected_payload_length: int | None
    coverage_in_bounds: int | None
    coverage_total: int | None
    coverage_ratio: float | None


@dataclass(frozen=True)
class IxbStructureSummary:
    label: str
    path: Path
    role: str
    size: int
    magic_kind: str
    num_elements: int | None
    is_big_endian: bool | None
    is_text: bool | None
    platform: str | None
    uri_count: int
    write_order_warnings: tuple[str, ...]
    object_record_candidate_count: int
    fileio_header_candidate_count: int
    objects_start: int | None
    objects_end: int | None
    classes_by_name: dict[str, IxbClass]
    melody_count: int
    lyric_count: int
    melody_prefix_counts: Counter[int]
    lyric_prefix_counts: Counter[int]
    duplicate_melody_times: int
    duplicate_lyric_times: int
    text_selection: TextSelectionSummary | None


def _classes_by_name(classes: Iterable[IxbClass]) -> dict[str, IxbClass]:
    return {cls.name: cls for cls in classes}


def _prefix_counts(data: bytes, markers: Iterable[MelodyMarker | LyricMarker]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for marker in markers:
        if 0 <= marker.offset < len(data):
            counts[data[marker.offset]] += 1
    return counts


def _duplicate_times(markers: Iterable[MelodyMarker | LyricMarker]) -> int:
    rounded = Counter(round(marker.time, 3) for marker in markers)
    return sum(1 for count in rounded.values() if count > 1)


def _text_selection_summary(data: bytes, lyric_markers: Sequence[LyricMarker] | None) -> TextSelectionSummary:
    resources = find_text_resources(data)
    selection = select_text_resource(data, lyric_markers)
    coverage = selection.coverage
    return TextSelectionSummary(
        resource_count=len(resources),
        selected_by=selection.selected_by,
        selected_index=selection.resource_index,
        selected_payload_length=selection.resource.payload_length if selection.resource else None,
        coverage_in_bounds=coverage.markers_in_bounds if coverage else None,
        coverage_total=coverage.total_markers if coverage else None,
        coverage_ratio=coverage.coverage_ratio if coverage else None,
    )


def summarize_ixb_file(
    path: Path,
    *,
    label: str,
    role: str,
    linked_chart_data: bytes | None = None,
) -> IxbStructureSummary:
    data = path.read_bytes()
    _, magic_kind = describe_magic(data)
    document = parse_ixb_document(data)
    classes_by_name = _classes_by_name(document.classes.values())
    melody = list(iter_melody_markers(data)) if role == "chart" else []
    lyrics = iter_lyric_markers_structural(data) if role == "chart" else []
    linked_lyrics = iter_lyric_markers_structural(linked_chart_data) if linked_chart_data else None
    text_selection = _text_selection_summary(data, linked_lyrics) if role == "lyric" else None
    return IxbStructureSummary(
        label=label,
        path=path,
        role=role,
        size=len(data),
        magic_kind=magic_kind,
        num_elements=document.num_elements,
        is_big_endian=document.is_big_endian,
        is_text=document.is_text,
        platform=document.platform,
        uri_count=len(document.uri_entries),
        write_order_warnings=tuple(validate_ixb_write_order(document)),
        object_record_candidate_count=len(probe_object_record_headers(data, document)),
        fileio_header_candidate_count=len(find_fileio_header_candidates(data)),
        objects_start=document.objects_start,
        objects_end=document.objects_end,
        classes_by_name=classes_by_name,
        melody_count=len(melody),
        lyric_count=len(lyrics),
        melody_prefix_counts=_prefix_counts(data, melody),
        lyric_prefix_counts=_prefix_counts(data, lyrics),
        duplicate_melody_times=_duplicate_times(melody),
        duplicate_lyric_times=_duplicate_times(lyrics),
        text_selection=text_selection,
    )


def _format_counter(counter: Counter[int]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"0x{value:02X}:{count}" for value, count in counter.most_common())


def _class_line(cls: IxbClass) -> str:
    return f"{cls.name} (index={cls.index}, size={cls.size}, base={cls.base})"


def _classes_matching(summary: IxbStructureSummary, patterns: Sequence[str]) -> list[IxbClass]:
    matched: list[IxbClass] = []
    for cls in summary.classes_by_name.values():
        if any(pattern in cls.name for pattern in patterns):
            matched.append(cls)
    return sorted(matched, key=lambda cls: cls.index)


def _missing_classes(real: IxbStructureSummary, synthetic: IxbStructureSummary) -> list[IxbClass]:
    missing = set(real.classes_by_name) - set(synthetic.classes_by_name)
    return sorted((real.classes_by_name[name] for name in missing), key=lambda cls: cls.index)


def _important_missing_by_role(real: IxbStructureSummary, synthetic: IxbStructureSummary) -> list[str]:
    lines: list[str] = []
    for role_name, patterns in ROLE_CLASSES.items():
        real_matches = _classes_matching(real, patterns)
        synth_matches = _classes_matching(synthetic, patterns)
        synth_names = {cls.name for cls in synth_matches}
        missing = [cls for cls in real_matches if cls.name not in synth_names]
        if missing:
            lines.append(f"  {role_name}: " + ", ".join(cls.name for cls in missing))
    return lines


def _marker_tag_observation(real: IxbStructureSummary, synthetic: IxbStructureSummary, marker: str) -> str:
    real_counts = real.melody_prefix_counts if marker == "MelodyMarker" else real.lyric_prefix_counts
    synth_counts = synthetic.melody_prefix_counts if marker == "MelodyMarker" else synthetic.lyric_prefix_counts
    return f"  {marker}: real tags [{_format_counter(real_counts)}], synthetic tags [{_format_counter(synth_counts)}]"


def _tag_expectations(summary: IxbStructureSummary, class_name: str) -> str | None:
    cls = summary.classes_by_name.get(class_name)
    if cls is None:
        return None
    codes = ", ".join(f"0x{code:02X}" for code in _schema_file_class_codes(cls))
    return f"{class_name}: index=0x{cls.index:02X}, size=0x{cls.size:02X}, accepted file tags={codes}"


def format_pair_comparison(
    real_chart: IxbStructureSummary,
    real_lyric: IxbStructureSummary,
    synthetic_chart: IxbStructureSummary,
    synthetic_lyric: IxbStructureSummary,
) -> str:
    lines: list[str] = [
        "# IXB Synthetic Pair Gap Report",
        "",
        "## Inputs",
        f"- real chart: {real_chart.path} ({real_chart.size} bytes, {real_chart.magic_kind})",
        f"- real lyric: {real_lyric.path} ({real_lyric.size} bytes, {real_lyric.magic_kind})",
        f"- synthetic chart: {synthetic_chart.path} ({synthetic_chart.size} bytes, {synthetic_chart.magic_kind})",
        f"- synthetic lyric: {synthetic_lyric.path} ({synthetic_lyric.size} bytes, {synthetic_lyric.magic_kind})",
        "",
        "## High-Signal Differences",
        f"- Real chart declares NumOfElements={real_chart.num_elements}; synthetic chart declares {synthetic_chart.num_elements}.",
        f"- Real lyric declares NumOfElements={real_lyric.num_elements}; synthetic lyric declares {synthetic_lyric.num_elements}.",
        f"- Real chart class inventory has {len(real_chart.classes_by_name)} classes; synthetic chart has {len(synthetic_chart.classes_by_name)}.",
        f"- Real lyric class inventory has {len(real_lyric.classes_by_name)} classes; synthetic lyric has {len(synthetic_lyric.classes_by_name)}.",
        f"- Real chart markers: {real_chart.melody_count} MelodyMarkers, {real_chart.lyric_count} LyricMarkers.",
        f"- Synthetic chart markers: {synthetic_chart.melody_count} MelodyMarkers, {synthetic_chart.lyric_count} LyricMarkers.",
        "",
        "## Writer-Oriented Metadata",
        _format_writer_metadata(real_chart),
        _format_writer_metadata(real_lyric),
        _format_writer_metadata(synthetic_chart),
        _format_writer_metadata(synthetic_lyric),
        "",
        "## Missing Classes By Role",
        "Chart:",
    ]
    lines.extend(_important_missing_by_role(real_chart, synthetic_chart) or ["  none"])
    lines.append("Lyric:")
    lines.extend(_important_missing_by_role(real_lyric, synthetic_lyric) or ["  none"])
    lines.extend(
        [
            "",
            "## Marker Record Tagging",
            _marker_tag_observation(real_chart, synthetic_chart, "MelodyMarker"),
            _marker_tag_observation(real_chart, synthetic_chart, "LyricMarker"),
        ]
    )
    for summary in (real_chart, synthetic_chart):
        for class_name in ("lpsMelodyMarker", "lpsLyricMarker"):
            expectation = _tag_expectations(summary, class_name)
            if expectation:
                lines.append(f"  {summary.label} {expectation}")
    lines.extend(
        [
            "",
            "## Lyric Text Resources",
            _format_text_selection("real lyric", real_lyric.text_selection),
            _format_text_selection("synthetic lyric", synthetic_lyric.text_selection),
            "",
            "## Duplicate/Mode Clues",
            f"- Real chart duplicate MelodyMarker time groups: {real_chart.duplicate_melody_times}",
            f"- Real chart duplicate LyricMarker time groups: {real_chart.duplicate_lyric_times}",
            f"- Synthetic chart duplicate MelodyMarker time groups: {synthetic_chart.duplicate_melody_times}",
            f"- Synthetic chart duplicate LyricMarker time groups: {synthetic_chart.duplicate_lyric_times}",
            "",
            "## Missing Exact Chart Classes",
            _format_class_list(_missing_classes(real_chart, synthetic_chart)),
            "",
            "## Missing Exact Lyric Classes",
            _format_class_list(_missing_classes(real_lyric, synthetic_lyric)),
            "",
            "## Current Interpretation",
            "- The synthetic lyric schema now matches the real package/asset/file-image class inventory when those classes are present.",
            "- The synthetic lyric resource chain is still minimal and uses synthetic pointer values; in-game validation must determine whether that ownership graph is sufficient.",
            "- The synthetic chart file has note and lyric marker records but not the real chart root/sequence metadata that tells Lips which sequences exist.",
            "- The real chart includes lpsChart/ixChart/ixSequence/ixTempoMap/music metadata plus phrase/page/hit/short-end marker families.",
            "- The synthetic package objects now carry names and asset vectors, but their pointers/lists are synthetic and may still be incomplete.",
            "- Real file-layout marker tags are now matched when synthetic tags report 0x28 for MelodyMarker and 0x40 for LyricMarker.",
            "",
            "## Minimum Next Structures To Model",
            "1. In-game test the current minimal ownership-chain pair before adding more chart structures.",
            "2. If it still crashes, add the smallest chart root layer: lpsChart/ixChart plus one ixSequence/ixTempoMap-style owner.",
            "3. Add ixVector<ixSeqCode *> and ixVector<lpsLyricWordData> ownership only when the loader still rejects the tiny pair.",
            "4. Defer full phrase/page/hit/short-end and mode/player duplicate reconstruction until the root/sequence layer is proven necessary.",
        ]
    )
    return "\n".join(lines)


def _format_writer_metadata(summary: IxbStructureSummary) -> str:
    warnings = "; ".join(summary.write_order_warnings) if summary.write_order_warnings else "none"
    return (
        f"- {summary.label}: IsBigEndian={summary.is_big_endian}, IsText={summary.is_text}, "
        f"Platform={summary.platform}, UriList entries={summary.uri_count}, "
        f"object-record candidates={summary.object_record_candidate_count}, "
        f"FileIO header candidates={summary.fileio_header_candidate_count}, "
        f"write-order warnings={warnings}"
    )


def _format_text_selection(label: str, selection: TextSelectionSummary | None) -> str:
    if selection is None:
        return f"- {label}: no lyric text selection"
    coverage = "none"
    if selection.coverage_in_bounds is not None and selection.coverage_total is not None and selection.coverage_ratio is not None:
        coverage = f"{selection.coverage_in_bounds}/{selection.coverage_total} ({selection.coverage_ratio:.1%})"
    return (
        f"- {label}: resources={selection.resource_count}, selected_by={selection.selected_by}, "
        f"selected_index={selection.selected_index}, selected_payload_length={selection.selected_payload_length}, coverage={coverage}"
    )


def _format_class_list(classes: Sequence[IxbClass]) -> str:
    if not classes:
        return "none"
    return "\n".join(f"- {_class_line(cls)}" for cls in classes)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-chart", type=Path, required=True)
    parser.add_argument("--real-lyric", type=Path, required=True)
    parser.add_argument("--synthetic-chart", type=Path, required=True)
    parser.add_argument("--synthetic-lyric", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    real_chart_data = args.real_chart.read_bytes()
    synthetic_chart_data = args.synthetic_chart.read_bytes()
    report = format_pair_comparison(
        summarize_ixb_file(args.real_chart, label="real chart", role="chart"),
        summarize_ixb_file(args.real_lyric, label="real lyric", role="lyric", linked_chart_data=real_chart_data),
        summarize_ixb_file(args.synthetic_chart, label="synthetic chart", role="chart"),
        summarize_ixb_file(
            args.synthetic_lyric,
            label="synthetic lyric",
            role="lyric",
            linked_chart_data=synthetic_chart_data,
        ),
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
