#!/usr/bin/env python3
"""Local-only corpus comparison for private Lips chart/lyric resources.

The tool deliberately emits sanitized identifiers instead of DB rows, song
titles, lyrics, or raw private paths. It reuses the existing IXB analyzers for
parsing and keeps object-record probes diagnostic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from tools.analyze_lyric_file import (
        _length_field_refs,
        _pointer_like_refs,
        compute_resource_coverages,
        find_text_resources,
        select_text_resource,
    )
    from tools.extract_melody_markers import (
        COMPRESSED_MAGICS,
        IxbDocument,
        describe_magic,
        find_fileio_header_candidates,
        iter_melody_markers_object_walker,
        parse_ixb_document,
        probe_object_record_headers,
        validate_ixb_write_order,
    )
    from tools.patch_lyrics_mapping import iter_lyric_markers_structural
except ModuleNotFoundError:
    from analyze_lyric_file import (
        _length_field_refs,
        _pointer_like_refs,
        compute_resource_coverages,
        find_text_resources,
        select_text_resource,
    )
    from extract_melody_markers import (
        COMPRESSED_MAGICS,
        IxbDocument,
        describe_magic,
        find_fileio_header_candidates,
        iter_melody_markers_object_walker,
        parse_ixb_document,
        probe_object_record_headers,
        validate_ixb_write_order,
    )
    from patch_lyrics_mapping import iter_lyric_markers_structural


PRIVATE_ROOT = Path("private/Lips")
DEFAULT_DB = PRIVATE_ROOT / "lps/MusicDB"
DEFAULT_OUTPUT = Path("private/outputs/corpus_comparison")


@dataclass(frozen=True)
class JoinedPair:
    pair_id: str
    row_number: int
    source: str
    chart_uri_hash: str
    lyric_uri_hash: str
    chart_path: Path | None
    lyric_path: Path | None
    family_label: str
    include_reason: str


@dataclass(frozen=True)
class SectionBounds:
    ixb_header_start: int | None
    ixb_header_end: int | None
    classes_open_start: int | None
    classes_open_end: int | None
    classes_close_start: int | None
    classes_close_end: int | None
    urilist_open_start: int | None
    urilist_open_end: int | None
    urilist_close_start: int | None
    urilist_close_end: int | None
    objects_open_start: int | None
    objects_open_end: int | None
    objects_close_start: int | None
    objects_close_end: int | None
    ixb_close_start: int | None
    ixb_close_end: int | None


@dataclass(frozen=True)
class RoundtripResult:
    pair_id: str
    role: str
    file_size: int
    byte_identical: bool
    mismatch_offset: int | None
    sha1_original: str
    sha1_roundtrip: str


def _sha_text(value: str | None) -> str:
    normalized = value or ""
    return hashlib.sha1(normalized.encode("utf-8", errors="replace")).hexdigest()[:12]


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _pair_id(chart_uri: str | None, lyric_uri: str | None) -> str:
    return hashlib.sha1(f"{chart_uri or ''}\n{lyric_uri or ''}".encode("utf-8", errors="replace")).hexdigest()[:12]


def _norm_uri_path(uri: str | None) -> Path | None:
    if not uri:
        return None
    cleaned = uri.replace("\\", "/")
    lowered = cleaned.lower()
    if lowered.startswith("game:/"):
        cleaned = cleaned[6:]
    elif lowered.startswith("game:"):
        cleaned = cleaned[5:]
    cleaned = cleaned.lstrip("/")
    if cleaned.lower().endswith(".ixb"):
        cleaned = cleaned[:-4] + ".X360"
    return PRIVATE_ROOT / cleaned


def _resolve_uri(uri: str | None) -> Path | None:
    candidate = _norm_uri_path(uri)
    if candidate is None:
        return None
    if candidate.exists():
        return candidate
    alternatives = []
    if candidate.suffix.lower() == ".x360":
        alternatives.append(candidate.with_suffix(".ixb"))
    else:
        alternatives.append(candidate.with_suffix(".X360"))
    for alt in alternatives:
        if alt.exists():
            return alt
    return candidate


def _family_label(path: Path | None, document: IxbDocument | None = None) -> str:
    parts = {part.lower() for part in path.parts} if path else set()
    class_names = {cls.name for cls in document.classes.values()} if document else set()
    if "ls2" in parts or any(name.startswith("lps2") or "lips2" in name.lower() for name in class_names):
        return "LS2"
    if "dlc" in parts or any("Gesture" in name or "Noisemaker" in name for name in class_names):
        return "DLC/later"
    if "lps" in parts:
        return "Lips 1-style"
    return "unknown"


def _uri_family(uri: str | None) -> str:
    normalized = (uri or "").replace("\\", "/").lower()
    if normalized.startswith("game:/lps/levels") or normalized.startswith("game:lps/levels"):
        return "Lips 1-style"
    if normalized.startswith("game:/ls2/levels") or normalized.startswith("game:ls2/levels"):
        return "LS2"
    if "dlc" in normalized:
        return "DLC/later"
    return "unknown"


def load_joined_pairs(db_path: Path, *, include_ls2: bool = False) -> list[JoinedPair]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute("select ChartUri, LyricUri from Music order by rowid").fetchall()
    pairs: list[JoinedPair] = []
    for index, row in enumerate(rows, start=1):
        chart_uri = row["ChartUri"]
        lyric_uri = row["LyricUri"]
        chart_path = _resolve_uri(chart_uri)
        lyric_path = _resolve_uri(lyric_uri)
        uri_family = _uri_family(chart_uri)
        include_reason = "included"
        if uri_family == "LS2" and not include_ls2:
            include_reason = "skipped_ls2_optional_later"
        elif uri_family == "DLC/later":
            include_reason = "skipped_dlc_not_inferred_from_lps_musicdb"
        elif uri_family != "Lips 1-style":
            include_reason = "skipped_not_lips1_disc_uri"
        pairs.append(
            JoinedPair(
                pair_id=_pair_id(chart_uri, lyric_uri),
                row_number=index,
                source="db",
                chart_uri_hash=_sha_text(chart_uri),
                lyric_uri_hash=_sha_text(lyric_uri),
                chart_path=chart_path if chart_path and chart_path.exists() else None,
                lyric_path=lyric_path if lyric_path and lyric_path.exists() else None,
                family_label=uri_family if uri_family != "unknown" else _family_label(chart_path),
                include_reason=include_reason,
            )
        )
    return pairs


def load_lips1_filesystem_pairs(root: Path = PRIVATE_ROOT / "lps/Levels") -> list[JoinedPair]:
    charts = [
        path
        for path in root.rglob("*.X360")
        if path.is_file() and not path.name.endswith("_Lyric.X360")
    ]
    pairs: list[JoinedPair] = []
    for index, chart_path in enumerate(sorted(charts), start=1):
        lyric_path = chart_path.with_name(f"{chart_path.stem}_Lyric{chart_path.suffix}")
        if not lyric_path.exists():
            continue
        rel_chart = chart_path.relative_to(PRIVATE_ROOT).as_posix()
        rel_lyric = lyric_path.relative_to(PRIVATE_ROOT).as_posix()
        pairs.append(
            JoinedPair(
                pair_id=_pair_id(rel_chart, rel_lyric),
                row_number=index,
                source="filesystem_lips1",
                chart_uri_hash=_sha_text(rel_chart),
                lyric_uri_hash=_sha_text(rel_lyric),
                chart_path=chart_path,
                lyric_path=lyric_path,
                family_label="Lips 1-style",
                include_reason="included_filesystem_lips1_not_db_join",
            )
        )
    return pairs


def _counter_to_dict(counter: Counter[Any]) -> dict[str, int]:
    return {str(key): value for key, value in sorted(counter.items(), key=lambda item: str(item[0]))}


def _class_inventory(document: IxbDocument) -> list[dict[str, Any]]:
    return [
        {
            "index": cls.index,
            "name": cls.name,
            "size": cls.size,
            "base": cls.base,
            "members": [{"name": name, "offset": offset} for name, offset in sorted(cls.members.items())],
        }
        for cls in sorted(document.classes.values(), key=lambda item: item.index)
    ]


def _class_names(document: IxbDocument) -> list[str]:
    return [cls.name for cls in sorted(document.classes.values(), key=lambda item: item.index)]


def _section_bounds(data: bytes) -> SectionBounds:
    def tag_range(tag: bytes) -> tuple[int | None, int | None]:
        start = data.find(tag)
        if start < 0:
            return None, None
        return start, start + len(tag)

    header_start = 0 if data.startswith(b"<ixb") else None
    header_end = None
    if header_start is not None:
        header_close = data.find(b">", header_start)
        header_end = header_close + 1 if header_close >= 0 else None

    return SectionBounds(
        ixb_header_start=header_start,
        ixb_header_end=header_end,
        classes_open_start=tag_range(b"<Classes>")[0],
        classes_open_end=tag_range(b"<Classes>")[1],
        classes_close_start=tag_range(b"</Classes>")[0],
        classes_close_end=tag_range(b"</Classes>")[1],
        urilist_open_start=tag_range(b"<UriList>")[0],
        urilist_open_end=tag_range(b"<UriList>")[1],
        urilist_close_start=tag_range(b"</UriList>")[0],
        urilist_close_end=tag_range(b"</UriList>")[1],
        objects_open_start=tag_range(b"<Objects>")[0],
        objects_open_end=tag_range(b"<Objects>")[1],
        objects_close_start=tag_range(b"</Objects>")[0],
        objects_close_end=tag_range(b"</Objects>")[1],
        ixb_close_start=tag_range(b"</ixb>")[0],
        ixb_close_end=tag_range(b"</ixb>")[1],
    )


def _object_section_metrics(data: bytes, document: IxbDocument) -> dict[str, Any]:
    if document.objects_start is None or document.objects_end is None:
        return {"start": None, "end": None, "length": None, "sha1": None}
    payload = data[document.objects_start : document.objects_end]
    return {
        "start": document.objects_start,
        "end": document.objects_end,
        "length": len(payload),
        "sha1": _sha_bytes(payload),
    }


def _text_resource_summary(data: bytes, chart_data: bytes | None) -> dict[str, Any]:
    resources = find_text_resources(data)
    lyric_markers = iter_lyric_markers_structural(chart_data) if chart_data else None
    coverages = compute_resource_coverages(resources, data, lyric_markers) if lyric_markers is not None else []
    selection = select_text_resource(data, lyric_markers)
    items = []
    for index, resource in enumerate(resources, start=1):
        pointer_refs = _pointer_like_refs(data, resource.payload_start, resource.payload_end)
        length_refs = _length_field_refs(data, resource.payload_length)
        coverage = coverages[index - 1] if index - 1 < len(coverages) else None
        items.append(
            {
                "index": index,
                "payload_start": resource.payload_start,
                "payload_end": resource.payload_end,
                "payload_length": resource.payload_length,
                "visible_length": resource.visible_length,
                "payload_hash_offset": resource.payload_hash_offset,
                "payload_hash": f"0x{resource.payload_hash:08X}",
                "payload_length_offset": resource.payload_length_offset,
                "padding_byte": resource.padding_byte,
                "printable_ratio": round(resource.printable_ratio, 3),
                "line_count": resource.line_count,
                "utf8_ok": resource.utf8_ok,
                "visible_candidate": resource.is_visible_lyric_candidate,
                "pointer_like_refs_into_payload_count": len(pointer_refs),
                "payload_length_value_refs_count": len(length_refs),
                "coverage_in_bounds": coverage.markers_in_bounds if coverage else None,
                "coverage_total": coverage.total_markers if coverage else None,
                "coverage_ratio": round(coverage.coverage_ratio, 4) if coverage else None,
            }
        )
    selected_index = selection.resource_index if selection.resource else None
    return {
        "resource_count": len(resources),
        "selected_by": selection.selected_by,
        "selected_index": selected_index,
        "coverage_ratio": round(selection.coverage.coverage_ratio, 4) if selection.coverage else None,
        "coverage_in_bounds": selection.coverage.markers_in_bounds if selection.coverage else None,
        "coverage_total": selection.coverage.total_markers if selection.coverage else None,
        "resources": items,
    }


def analyze_file(path: Path, role: str, linked_chart_data: bytes | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    magic, kind = describe_magic(data)
    result: dict[str, Any] = {
        "role": role,
        "size": len(data),
        "magic": magic,
        "kind": kind,
        "path_hash": _sha_text(str(path)),
    }
    if data[:4] in COMPRESSED_MAGICS:
        result["status"] = "compressed/unsupported"
        return result
    if not data.startswith(b"<ixb"):
        result["status"] = "unsupported/non-ixb"
        return result

    document = parse_ixb_document(data)
    family = _family_label(path, document)
    result.update(
        {
            "status": "plain-ixb",
            "family_label": family,
            "header": {
                "IsBigEndian": document.is_big_endian,
                "IsText": document.is_text,
                "Platform": document.platform,
                "NumOfElements": document.num_elements,
            },
            "class_count": len(document.classes),
            "class_names": _class_names(document),
            "class_inventory": _class_inventory(document),
            "uri_count": len(document.uri_entries),
            "write_order_warnings": validate_ixb_write_order(document),
            "section_bounds": asdict(_section_bounds(data)),
            "object_section": _object_section_metrics(data, document),
            "object_record_candidate_count": len(probe_object_record_headers(data, document)),
            "fileio_header_candidate_count": len(find_fileio_header_candidates(data)),
        }
    )
    if role == "chart":
        melody = list(iter_melody_markers_object_walker(data, document))
        lyrics = iter_lyric_markers_structural(data)
        result.update(
            {
                "marker_counts": {
                    "melody": len(melody),
                    "lyric": len(lyrics),
                },
                "marker_source_counts": _counter_to_dict(Counter(marker.source for marker in melody)),
                "lyric_track_index_counts": _counter_to_dict(Counter(marker.track_index for marker in lyrics)),
                "lyric_end_of_word_counts": _counter_to_dict(Counter(marker.end_of_word for marker in lyrics)),
                "lyric_worddata": {
                    "min_text_offset": min((marker.text_offset for marker in lyrics), default=None),
                    "max_text_end": max((marker.text_offset + marker.text_length for marker in lyrics), default=None),
                    "unique_worddata_offsets": len({marker.word_data_file_offset for marker in lyrics}),
                    "unique_worddata_pointers": len({marker.word_data_pointer for marker in lyrics}),
                },
            }
        )
    if role == "lyric":
        result["text_resources"] = _text_resource_summary(data, linked_chart_data)
    return result


def analyze_pair(pair: JoinedPair) -> dict[str, Any]:
    if pair.include_reason != "included":
        if pair.include_reason == "included_filesystem_lips1_not_db_join":
            pass
        else:
            return {
                "pair_id": pair.pair_id,
                "row_number": pair.row_number,
                "source": pair.source,
                "chart_uri_hash": pair.chart_uri_hash,
                "lyric_uri_hash": pair.lyric_uri_hash,
                "resolved": False,
                "family_label": pair.family_label,
                "include_reason": pair.include_reason,
                "chart": {"status": "skipped"},
                "lyric": {"status": "skipped"},
            }
    chart_data = pair.chart_path.read_bytes() if pair.chart_path and pair.chart_path.exists() else None
    chart = analyze_file(pair.chart_path, "chart") if pair.chart_path else {"status": "missing"}
    lyric = (
        analyze_file(pair.lyric_path, "lyric", linked_chart_data=chart_data)
        if pair.lyric_path
        else {"status": "missing"}
    )
    labels = {pair.family_label}
    if chart.get("family_label"):
        labels.add(chart["family_label"])
    if lyric.get("family_label"):
        labels.add(lyric["family_label"])
    label = "mixed" if len(labels - {"unknown"}) > 1 else next(iter(labels - {"unknown"}), pair.family_label)
    return {
        "pair_id": pair.pair_id,
        "row_number": pair.row_number,
        "source": pair.source,
        "chart_uri_hash": pair.chart_uri_hash,
        "lyric_uri_hash": pair.lyric_uri_hash,
        "resolved": bool(pair.chart_path and pair.lyric_path),
        "include_reason": pair.include_reason,
        "family_label": label,
        "chart": chart,
        "lyric": lyric,
    }


def _plain_pair_reports(pair_reports: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        report
        for report in pair_reports
        if report["chart"].get("status") == "plain-ixb" and report["lyric"].get("status") == "plain-ixb"
    ]


def _aggregate(pair_reports: list[dict[str, Any]]) -> dict[str, Any]:
    chart_status = Counter(report["chart"].get("status") for report in pair_reports)
    lyric_status = Counter(report["lyric"].get("status") for report in pair_reports)
    families = Counter(report["family_label"] for report in pair_reports)
    include_reasons = Counter(report.get("include_reason", "included") for report in pair_reports)
    sources = Counter(report.get("source", "unknown") for report in pair_reports)
    plain = _plain_pair_reports(pair_reports)
    header_attrs: dict[str, Counter[str]] = defaultdict(Counter)
    class_sets: Counter[str] = Counter()
    text_resource_counts: Counter[int] = Counter()
    coverage_buckets: Counter[str] = Counter()
    for report in plain:
        for role in ("chart", "lyric"):
            header = report[role].get("header", {})
            for key, value in header.items():
                header_attrs[f"{role}.{key}"][str(value)] += 1
        class_key = "|".join(report["chart"].get("class_names", []))
        class_sets[class_key] += 1
        text = report["lyric"].get("text_resources", {})
        text_resource_counts[text.get("resource_count", 0)] += 1
        ratio = text.get("coverage_ratio")
        if ratio is None:
            coverage_buckets["none"] += 1
        elif ratio >= 0.999:
            coverage_buckets["100%"] += 1
        elif ratio >= 0.9:
            coverage_buckets["90-99%"] += 1
        else:
            coverage_buckets["<90%"] += 1
    return {
        "pairs_total": len(pair_reports),
        "pairs_resolved": sum(1 for report in pair_reports if report["resolved"]),
        "plain_pairs": len(plain),
        "chart_status": _counter_to_dict(chart_status),
        "lyric_status": _counter_to_dict(lyric_status),
        "family_labels": _counter_to_dict(families),
        "include_reasons": _counter_to_dict(include_reasons),
        "sources": _counter_to_dict(sources),
        "header_attributes": {key: _counter_to_dict(value) for key, value in sorted(header_attrs.items())},
        "chart_class_inventory_variants": len(class_sets),
        "top_chart_class_inventory_counts": [
            {"count": count, "sha1": _sha_text(classes), "class_count": classes.count("|") + 1 if classes else 0}
            for classes, count in class_sets.most_common(10)
        ],
        "text_resource_counts": _counter_to_dict(text_resource_counts),
        "coverage_buckets": _counter_to_dict(coverage_buckets),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _format_private_summary(aggregate: dict[str, Any], reports: list[dict[str, Any]]) -> str:
    lines = [
        "# Private Corpus Comparison Summary",
        "",
        "Sanitized local report. Pair IDs and hashes are stable, but no DB rows, song titles, lyrics, or raw private paths are included.",
        "",
        f"- pairs_total: {aggregate['pairs_total']}",
        f"- pairs_resolved: {aggregate['pairs_resolved']}",
        f"- plain_pairs: {aggregate['plain_pairs']}",
        f"- chart_status: {aggregate['chart_status']}",
        f"- lyric_status: {aggregate['lyric_status']}",
        f"- family_labels: {aggregate['family_labels']}",
        f"- include_reasons: {aggregate['include_reasons']}",
        f"- sources: {aggregate['sources']}",
        f"- text_resource_counts: {aggregate['text_resource_counts']}",
        f"- coverage_buckets: {aggregate['coverage_buckets']}",
        "",
        "## Plain Pair Snapshot",
    ]
    for report in _plain_pair_reports(reports)[:20]:
        text = report["lyric"].get("text_resources", {})
        markers = report["chart"].get("marker_counts", {})
        lines.append(
            "- "
            f"pair={report['pair_id']} source={report.get('source')} family={report['family_label']} "
            f"classes(chart/lyric)={report['chart'].get('class_count')}/{report['lyric'].get('class_count')} "
            f"markers(melody/lyric)={markers.get('melody')}/{markers.get('lyric')} "
            f"text_resources={text.get('resource_count')} coverage={text.get('coverage_ratio')}"
        )
    return "\n".join(lines) + "\n"


def write_phase1_outputs(output_dir: Path, pair_reports: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate = _aggregate(pair_reports)
    _write_json(output_dir / "joined_pairs_sanitized.json", pair_reports)
    _write_json(output_dir / "corpus_aggregate.json", aggregate)
    (output_dir / "summary.md").write_text(_format_private_summary(aggregate, pair_reports), encoding="utf-8")
    return aggregate


def write_phase2_outputs(output_dir: Path, pair_reports: list[dict[str, Any]]) -> dict[str, Any]:
    section_reports = []
    for report in _plain_pair_reports(pair_reports):
        for role in ("chart", "lyric"):
            section_reports.append(
                {
                    "pair_id": report["pair_id"],
                    "role": role,
                    "family_label": report["family_label"],
                    "size": report[role]["size"],
                    "section_bounds": report[role]["section_bounds"],
                    "write_order_warnings": report[role]["write_order_warnings"],
                }
            )
    _write_json(output_dir / "section_boundaries.json", section_reports)
    warnings = Counter()
    for item in section_reports:
        if item["write_order_warnings"]:
            for warning in item["write_order_warnings"]:
                warnings[warning] += 1
        else:
            warnings["none"] += 1
    summary = {
        "plain_files_reported": len(section_reports),
        "write_order_warnings": _counter_to_dict(warnings),
    }
    _write_json(output_dir / "section_boundary_summary.json", summary)
    return summary


def _split_ixb_sections_noop(data: bytes) -> list[bytes]:
    """Split at writer-order tags and rejoin exact original byte slices."""
    tags = [b"<Classes>", b"</Classes>", b"<UriList>", b"</UriList>", b"<Objects>", b"</Objects>", b"</ixb>"]
    cut_points = {0, len(data)}
    header_end = data.find(b">")
    if data.startswith(b"<ixb") and header_end >= 0:
        cut_points.add(header_end + 1)
    for tag in tags:
        start = data.find(tag)
        if start >= 0:
            cut_points.add(start)
            cut_points.add(start + len(tag))
    ordered = sorted(cut_points)
    return [data[start:end] for start, end in zip(ordered, ordered[1:]) if start != end]


def run_roundtrip_probe(pair_reports: list[dict[str, Any]], pairs: list[JoinedPair]) -> RoundtripResult | None:
    candidates = [
        report
        for report in _plain_pair_reports(pair_reports)
        if report["lyric"].get("status") == "plain-ixb"
    ]
    if not candidates:
        return None
    selected = min(candidates, key=lambda report: report["lyric"]["size"])
    pair_id = selected["pair_id"]

    # Re-resolve by sanitized id from in-memory DB joins instead of storing raw
    # paths in reports.
    pair_by_id = {pair.pair_id: pair for pair in pairs}
    pair = pair_by_id[pair_id]
    if pair.lyric_path is None:
        return None
    data = pair.lyric_path.read_bytes()
    chunks = _split_ixb_sections_noop(data)
    roundtrip = b"".join(chunks)
    mismatch = None
    if data != roundtrip:
        for index, (left, right) in enumerate(zip(data, roundtrip)):
            if left != right:
                mismatch = index
                break
        if mismatch is None:
            mismatch = min(len(data), len(roundtrip))
    return RoundtripResult(
        pair_id=pair_id,
        role="lyric",
        file_size=len(data),
        byte_identical=data == roundtrip,
        mismatch_offset=mismatch,
        sha1_original=_sha_bytes(data),
        sha1_roundtrip=_sha_bytes(roundtrip),
    )


def write_phase3_outputs(
    output_dir: Path,
    pair_reports: list[dict[str, Any]],
    pairs: list[JoinedPair],
) -> RoundtripResult | None:
    result = run_roundtrip_probe(pair_reports, pairs)
    _write_json(output_dir / "roundtrip_noop_probe.json", asdict(result) if result else {"status": "no_plain_lyric"})
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-ls2", action="store_true", help="Include LS2 rows explicitly; off by default.")
    parser.add_argument(
        "--no-filesystem-lips1",
        action="store_true",
        help="Disable separate lps/Levels filesystem supplement.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    args.output.mkdir(parents=True, exist_ok=True)
    pairs = load_joined_pairs(args.db, include_ls2=args.include_ls2)
    if not args.no_filesystem_lips1:
        pairs = [*pairs, *load_lips1_filesystem_pairs()]
    if args.limit is not None:
        pairs = pairs[: args.limit]
    reports = [analyze_pair(pair) for pair in pairs]
    aggregate = write_phase1_outputs(args.output, reports)
    section_summary = write_phase2_outputs(args.output, reports)
    roundtrip = write_phase3_outputs(args.output, reports, pairs)
    print(f"pairs_total={aggregate['pairs_total']}")
    print(f"pairs_resolved={aggregate['pairs_resolved']}")
    print(f"plain_pairs={aggregate['plain_pairs']}")
    print(f"section_plain_files={section_summary['plain_files_reported']}")
    if roundtrip:
        print(f"roundtrip_pair={roundtrip.pair_id} byte_identical={roundtrip.byte_identical}")
    else:
        print("roundtrip_pair=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
