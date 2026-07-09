#!/usr/bin/env python3
"""Prepare low-risk local runtime tests without editing private game files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
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
    from tools.corpus_comparison import (
        JoinedPair,
        _section_bounds,
        _split_ixb_sections_noop,
        _write_json,
        load_lips1_filesystem_pairs,
    )
    from tools.extract_melody_markers import (
        COMPRESSED_MAGICS,
        describe_magic,
        iter_melody_markers_object_walker,
        parse_ixb_document,
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
    from corpus_comparison import (
        JoinedPair,
        _section_bounds,
        _split_ixb_sections_noop,
        _write_json,
        load_lips1_filesystem_pairs,
    )
    from extract_melody_markers import (
        COMPRESSED_MAGICS,
        describe_magic,
        iter_melody_markers_object_walker,
        parse_ixb_document,
        validate_ixb_write_order,
    )
    from patch_lyrics_mapping import iter_lyric_markers_structural


DEFAULT_OUTPUT = Path("private/outputs/roundtrip_batch")
WORD_RE = re.compile(r"\b[A-Za-z]{4}\b")
SAME_LENGTH_REPLACEMENTS = {
    4: ["TEST", "NOTE", "SING", "WORD", "PLAY", "TONE", "LINE", "BEAT"],
}


@dataclass(frozen=True)
class BatchRoundtripItem:
    pair_id: str
    role: str
    size: int
    sha1_original: str
    sha1_roundtrip: str
    byte_identical: bool
    mismatch_offset: int | None
    mismatch_section: str | None
    status: str


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def _plain_ixb(path: Path) -> bool:
    data = path.read_bytes()
    return data.startswith(b"<ixb") and data[:4] not in COMPRESSED_MAGICS


def _first_mismatch(left: bytes, right: bytes) -> int | None:
    if left == right:
        return None
    for index, (left_byte, right_byte) in enumerate(zip(left, right)):
        if left_byte != right_byte:
            return index
    return min(len(left), len(right))


def _section_for_offset(data: bytes, offset: int | None) -> str | None:
    if offset is None:
        return None
    bounds = asdict(_section_bounds(data))
    ranges = [
        ("ixb_header", bounds["ixb_header_start"], bounds["ixb_header_end"]),
        ("classes_open_tag", bounds["classes_open_start"], bounds["classes_open_end"]),
        ("classes_body", bounds["classes_open_end"], bounds["classes_close_start"]),
        ("classes_close_tag", bounds["classes_close_start"], bounds["classes_close_end"]),
        ("urilist_open_tag", bounds["urilist_open_start"], bounds["urilist_open_end"]),
        ("urilist_body", bounds["urilist_open_end"], bounds["urilist_close_start"]),
        ("urilist_close_tag", bounds["urilist_close_start"], bounds["urilist_close_end"]),
        ("objects_open_tag", bounds["objects_open_start"], bounds["objects_open_end"]),
        ("objects_body", bounds["objects_open_end"], bounds["objects_close_start"]),
        ("objects_close_tag", bounds["objects_close_start"], bounds["objects_close_end"]),
        ("ixb_close_tag", bounds["ixb_close_start"], bounds["ixb_close_end"]),
    ]
    for name, start, end in ranges:
        if start is not None and end is not None and start <= offset < end:
            return name
    return "unknown"


def _roundtrip_one(pair_id: str, role: str, path: Path) -> BatchRoundtripItem:
    data = path.read_bytes()
    _, kind = describe_magic(data)
    if not data.startswith(b"<ixb"):
        return BatchRoundtripItem(pair_id, role, len(data), _sha_bytes(data), "", False, None, None, kind)
    document = parse_ixb_document(data)
    warnings = validate_ixb_write_order(document)
    if warnings:
        status = "plain-ixb/write-order-warning"
    else:
        status = "plain-ixb"
    roundtrip = b"".join(_split_ixb_sections_noop(data))
    mismatch = _first_mismatch(data, roundtrip)
    return BatchRoundtripItem(
        pair_id=pair_id,
        role=role,
        size=len(data),
        sha1_original=_sha_bytes(data),
        sha1_roundtrip=_sha_bytes(roundtrip),
        byte_identical=data == roundtrip,
        mismatch_offset=mismatch,
        mismatch_section=_section_for_offset(data, mismatch),
        status=status,
    )


def _plain_pairs() -> list[JoinedPair]:
    pairs = []
    for pair in load_lips1_filesystem_pairs():
        if pair.chart_path and pair.lyric_path and _plain_ixb(pair.chart_path) and _plain_ixb(pair.lyric_path):
            pairs.append(pair)
    return pairs


def run_batch_roundtrip(output_dir: Path) -> dict[str, Any]:
    pairs = _plain_pairs()
    lyric_items = [_roundtrip_one(pair.pair_id, "lyric", pair.lyric_path) for pair in pairs if pair.lyric_path]
    chart_items = [_roundtrip_one(pair.pair_id, "chart", pair.chart_path) for pair in pairs if pair.chart_path]
    summary = {
        "plain_pairs": len(pairs),
        "lyrics_total": len(lyric_items),
        "lyrics_byte_identical": sum(item.byte_identical for item in lyric_items),
        "charts_total": len(chart_items),
        "charts_byte_identical": sum(item.byte_identical for item in chart_items),
        "first_lyric_mismatch": next((asdict(item) for item in lyric_items if not item.byte_identical), None),
        "first_chart_mismatch": next((asdict(item) for item in chart_items if not item.byte_identical), None),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "batch_roundtrip_lyrics.json", [asdict(item) for item in lyric_items])
    _write_json(output_dir / "batch_roundtrip_charts.json", [asdict(item) for item in chart_items])
    _write_json(output_dir / "batch_roundtrip_summary.json", summary)
    return summary


def _decode_payload(data: bytes, payload_start: int, visible_end: int) -> str:
    return data[payload_start:visible_end].decode("utf-8", errors="replace")


def find_edit_candidates(output_dir: Path, *, limit: int = 40) -> dict[str, Any]:
    candidates_private: list[dict[str, Any]] = []
    candidates_public: list[dict[str, Any]] = []
    for pair in _plain_pairs():
        if pair.lyric_path is None or pair.chart_path is None:
            continue
        lyric_data = pair.lyric_path.read_bytes()
        chart_data = pair.chart_path.read_bytes()
        lyric_markers = iter_lyric_markers_structural(chart_data)
        resources = find_text_resources(lyric_data)
        selection = select_text_resource(lyric_data, lyric_markers)
        if selection.resource is None:
            continue
        resource = selection.resource
        text = _decode_payload(lyric_data, resource.payload_start, resource.visible_end)
        word_counts = Counter(match.group(0) for match in WORD_RE.finditer(text))
        payload_words = list(WORD_RE.finditer(text))
        pointer_refs = _pointer_like_refs(lyric_data, resource.payload_start, resource.payload_end)
        length_refs = _length_field_refs(lyric_data, resource.payload_length)
        field_offsets = {
            "payload_hash_offset": resource.payload_hash_offset,
            "payload_length_offset": resource.payload_length_offset,
            "payload_length_value_refs": length_refs,
            "pointer_like_refs_into_payload": pointer_refs,
        }
        for match in payload_words:
            word = match.group(0)
            if word_counts[word] != 1:
                continue
            if not word.isascii() or len(word) != 4:
                continue
            # Regex offsets are character offsets in the decoded UTF-8 string.
            # Runtime patches must use byte offsets in the original payload.
            byte_start = len(text[: match.start()].encode("utf-8"))
            byte_end = byte_start + len(word.encode("ascii"))
            absolute_start = resource.payload_start + byte_start
            absolute_end = resource.payload_start + byte_end
            nearby_offsets = [
                offset
                for offset in [resource.payload_hash_offset, resource.payload_length_offset, *length_refs, *pointer_refs]
                if abs(offset - absolute_start) <= 32 or absolute_start <= offset < absolute_end
            ]
            replacements = [item for item in SAME_LENGTH_REPLACEMENTS[4] if item.lower() != word.lower()]
            public_item = {
                "candidate_id": _sha_text(f"{pair.pair_id}:{absolute_start}:{word}"),
                "pair_id": pair.pair_id,
                "word_hash": _sha_text(word),
                "length": len(word),
                "replacement_examples": replacements[:4],
                "unique_in_selected_payload": True,
                "selected_resource_index": selection.resource_index,
                "coverage_ratio": round(selection.coverage.coverage_ratio, 4) if selection.coverage else None,
                "nearby_field_offsets_within_32_bytes": len(nearby_offsets),
                "payload_hash_field_in_same_resource": True,
                "payload_length_field_in_same_resource": True,
                "pointer_like_refs_into_payload_count": len(pointer_refs),
                "payload_length_value_refs_count": len(length_refs),
            }
            private_item = {
                **public_item,
                "original_word": word,
                "absolute_start": absolute_start,
                "absolute_end": absolute_end,
                "field_offsets": field_offsets,
            }
            candidates_public.append(public_item)
            candidates_private.append(private_item)
            if len(candidates_public) >= limit:
                break
        if len(candidates_public) >= limit:
            break
    summary = {
        "candidate_count": len(candidates_public),
        "public_candidates_are_redacted": True,
        "private_candidates_include_original_words": True,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "minimal_edit_candidates_sanitized.json", candidates_public)
    _write_json(output_dir / "minimal_edit_candidates_private.json", candidates_private)
    _write_json(output_dir / "minimal_edit_candidates_summary.json", summary)
    return {"summary": summary, "public": candidates_public}


def _class_names(document: Any) -> list[str]:
    return [cls.name for cls in sorted(document.classes.values(), key=lambda item: item.index)]


def _analysis_snapshot(chart_data: bytes, lyric_data: bytes) -> dict[str, Any]:
    chart_doc = parse_ixb_document(chart_data)
    lyric_doc = parse_ixb_document(lyric_data)
    melody = list(iter_melody_markers_object_walker(chart_data, chart_doc))
    lyric_markers = iter_lyric_markers_structural(chart_data)
    text_resources = find_text_resources(lyric_data)
    coverages = compute_resource_coverages(text_resources, lyric_data, lyric_markers)
    selection = select_text_resource(lyric_data, lyric_markers)
    return {
        "chart_header": {
            "IsBigEndian": chart_doc.is_big_endian,
            "IsText": chart_doc.is_text,
            "Platform": chart_doc.platform,
            "NumOfElements": chart_doc.num_elements,
        },
        "lyric_header": {
            "IsBigEndian": lyric_doc.is_big_endian,
            "IsText": lyric_doc.is_text,
            "Platform": lyric_doc.platform,
            "NumOfElements": lyric_doc.num_elements,
        },
        "chart_classes_sha1": _sha_text("|".join(_class_names(chart_doc))),
        "lyric_classes_sha1": _sha_text("|".join(_class_names(lyric_doc))),
        "chart_class_count": len(chart_doc.classes),
        "lyric_class_count": len(lyric_doc.classes),
        "marker_counts": {"melody": len(melody), "lyric": len(lyric_markers)},
        "selected_text_resource": {
            "selected_by": selection.selected_by,
            "selected_index": selection.resource_index if selection.resource else None,
            "coverage_ratio": round(selection.coverage.coverage_ratio, 4) if selection.coverage else None,
        },
        "text_resources": [
            {
                "index": index,
                "payload_length": resource.payload_length,
                "visible_length": resource.visible_length,
                "payload_hash": f"0x{resource.payload_hash:08X}",
                "payload_hash_offset": resource.payload_hash_offset,
                "payload_length_offset": resource.payload_length_offset,
                "pointer_like_refs_into_payload_count": len(
                    _pointer_like_refs(lyric_data, resource.payload_start, resource.payload_end)
                ),
                "payload_length_value_refs_count": len(_length_field_refs(lyric_data, resource.payload_length)),
                "coverage_ratio": round(coverages[index - 1].coverage_ratio, 4) if index - 1 < len(coverages) else None,
            }
            for index, resource in enumerate(text_resources, start=1)
        ],
    }


def _diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "chart_header",
        "lyric_header",
        "chart_classes_sha1",
        "lyric_classes_sha1",
        "chart_class_count",
        "lyric_class_count",
        "marker_counts",
        "selected_text_resource",
        "text_resources",
    ]
    return {key: {"before": before[key], "after": after[key]} for key in keys if before.get(key) != after.get(key)}


def run_validation_dry_run(output_dir: Path) -> dict[str, Any]:
    pairs = _plain_pairs()
    if not pairs:
        result = {"status": "no_plain_pairs"}
        _write_json(output_dir / "validation_dry_run.json", result)
        return result
    pair = min(pairs, key=lambda item: item.lyric_path.stat().st_size if item.lyric_path else 10**12)
    chart_data = pair.chart_path.read_bytes()
    lyric_data = pair.lyric_path.read_bytes()
    before = _analysis_snapshot(chart_data, lyric_data)
    after = _analysis_snapshot(chart_data, lyric_data)
    result = {
        "status": "ok",
        "pair_id": pair.pair_id,
        "copy_simulation": "same-bytes",
        "diff_count": len(_diff_snapshots(before, after)),
        "diffs": _diff_snapshots(before, after),
        "before": before,
        "after": after,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "validation_dry_run.json", result)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--candidate-limit", type=int, default=40)
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    batch = run_batch_roundtrip(args.output)
    candidates = find_edit_candidates(args.output, limit=args.candidate_limit)
    validation = run_validation_dry_run(args.output)
    print(f"roundtrip_lyrics={batch['lyrics_byte_identical']}/{batch['lyrics_total']}")
    print(f"roundtrip_charts={batch['charts_byte_identical']}/{batch['charts_total']}")
    print(f"edit_candidates={candidates['summary']['candidate_count']}")
    print(f"validation_dry_run={validation.get('status')} diff_count={validation.get('diff_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
