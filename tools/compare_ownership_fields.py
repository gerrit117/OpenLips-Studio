#!/usr/bin/env python3
"""Focused IXB ownership-container comparison.

This is a read-only forensic tool for comparing a known-working lyric IXB file
against a synthetic lyric IXB file. It intentionally looks only at the runtime
ownership/container area that can make Lips dereference bad fields:

* ixVector<char>
* ixVector<ixAsset *>
* ixList<ixPackage *>
* ixDblCnt<ixPackage *> wrappers
* ixPackage / ixAssetPackage / ixAsset / ixFileImage / ixRawFileImage fields

The scan is field-oriented rather than a full object graph walk because the
current synthetic files are precisely testing whether the serialized
file-layout tags and container fields match what the game expects.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from tools.analyze_lyric_file import TextResource, find_text_resources
    from tools.extract_melody_markers import _u32be, describe_magic, parse_ixb_document
except ModuleNotFoundError:
    from analyze_lyric_file import TextResource, find_text_resources
    from extract_melody_markers import _u32be, describe_magic, parse_ixb_document


OWNERSHIP_TAGS = {
    0x03: ("ixTreeNode<ixPackage>",),
    0x05: ("ixList<ixPackage *>",),
    0x06: ("ixVector<char>",),
    0x07: ("ixVector<ixPackage *>",),
    0x08: ("ixDblCnt<ixPackage *>",),
    0x09: ("ixVector<ixAsset *>",),
    0x34: ("ixAsset",),
    0x44: ("ixFileImage",),
    0x48: ("ixPackage",),
    0x54: ("ixRawFileImage",),
    0x5C: ("ixAssetPackage",),
}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    rel_offset: int
    role: str = "value"


@dataclass(frozen=True)
class RecordDef:
    kind: str
    tag: int
    min_size: int
    fields: tuple[FieldSpec, ...]


@dataclass(frozen=True)
class FieldValue:
    name: str
    abs_offset: int
    value: int
    role: str
    classification: str
    ref_count: int


@dataclass(frozen=True)
class OwnershipRecord:
    kind: str
    tag: int
    offset: int
    score: int
    fields: tuple[FieldValue, ...]
    preview_at_8: str
    preview_at_16: str
    issues: tuple[str, ...]

    def get(self, name: str) -> int | None:
        for field in self.fields:
            if field.name == name:
                return field.value
        return None


@dataclass(frozen=True)
class FileOwnershipAnalysis:
    path: Path
    data: bytes
    magic_description: str
    objects_start: int | None
    objects_end: int | None
    class_names: tuple[str, ...]
    text_resources: tuple[TextResource, ...]
    records_by_kind: dict[str, tuple[OwnershipRecord, ...]]


RECORD_DEFS: tuple[RecordDef, ...] = (
    RecordDef(
        "ixTreeNode<ixPackage>",
        0x03,
        24,
        (
            FieldSpec("parent_ptr", 8, "ptr"),
            FieldSpec("children_list_ptr", 12, "ptr"),
        ),
    ),
    RecordDef(
        "ixList<ixPackage *>",
        0x05,
        12,
        (
            FieldSpec("root_ptr", 0, "ptr"),
            FieldSpec("size", 4, "count"),
            FieldSpec("allocator_ptr", 8, "ptr"),
        ),
    ),
    RecordDef(
        "ixVector<char>",
        0x06,
        16,
        (
            FieldSpec("data_begin_ptr", 0, "ptr"),
            FieldSpec("reserve_or_end", 4, "count"),
            FieldSpec("size_or_capacity", 8, "count"),
            FieldSpec("allocator_or_inline", 12, "ptr"),
        ),
    ),
    RecordDef(
        "ixVector<ixPackage *>",
        0x07,
        16,
        (
            FieldSpec("data_begin_ptr", 0, "ptr"),
            FieldSpec("reserve_or_end", 4, "count"),
            FieldSpec("size_or_capacity", 8, "count"),
            FieldSpec("allocator_ptr", 12, "ptr"),
        ),
    ),
    RecordDef(
        "ixDblCnt<ixPackage *>",
        0x08,
        12,
        (
            FieldSpec("data_ptr", 0, "ptr"),
            FieldSpec("tail_ptr", 4, "ptr"),
            FieldSpec("head_ptr", 8, "ptr"),
        ),
    ),
    RecordDef(
        "ixVector<ixAsset *>",
        0x09,
        16,
        (
            FieldSpec("data_begin_ptr", 0, "ptr"),
            FieldSpec("reserve_or_end", 4, "count"),
            FieldSpec("size_or_capacity", 8, "count"),
            FieldSpec("allocator_ptr", 12, "ptr"),
        ),
    ),
    RecordDef(
        "ixAsset",
        0x34,
        52,
        (
            FieldSpec("name_data_ptr", 8, "ptr"),
            FieldSpec("name_reserve", 12, "count"),
            FieldSpec("name_size", 16, "count"),
            FieldSpec("asset_package_ptr", 24, "ptr"),
            FieldSpec("user_color", 28),
            FieldSpec("hash", 36, "hash"),
        ),
    ),
    RecordDef(
        "ixFileImage",
        0x44,
        68,
        (
            FieldSpec("name_data_ptr", 8, "ptr"),
            FieldSpec("name_reserve", 12, "count"),
            FieldSpec("name_size", 16, "count"),
            FieldSpec("asset_package_ptr", 24, "ptr"),
            FieldSpec("hash", 36, "hash"),
            FieldSpec("data_ptr", 52, "ptr"),
            FieldSpec("data_reserve", 56, "count"),
            FieldSpec("data_size", 60, "count"),
        ),
    ),
    RecordDef(
        "ixPackage",
        0x48,
        72,
        (
            FieldSpec("parent_ptr", 8, "ptr"),
            FieldSpec("children_list_ptr", 12, "ptr"),
            FieldSpec("name_data_ptr", 24, "ptr"),
            FieldSpec("name_reserve", 28, "count"),
            FieldSpec("name_size", 32, "count"),
            FieldSpec("is_loaded", 40),
            FieldSpec("packed_size", 44, "count"),
            FieldSpec("linked_packages_ptr", 52, "ptr"),
            FieldSpec("linked_packages_reserve", 56, "count"),
            FieldSpec("linked_packages_size", 60, "count"),
        ),
    ),
    RecordDef(
        "ixRawFileImage",
        0x54,
        84,
        (
            FieldSpec("name_data_ptr", 8, "ptr"),
            FieldSpec("name_reserve", 12, "count"),
            FieldSpec("name_size", 16, "count"),
            FieldSpec("asset_package_ptr", 24, "ptr"),
            FieldSpec("hash", 36, "hash"),
            FieldSpec("data_ptr", 52, "ptr"),
            FieldSpec("data_reserve", 56, "count"),
            FieldSpec("data_size", 60, "count"),
            FieldSpec("type_name_ptr", 68, "ptr"),
            FieldSpec("type_reserve", 72, "count"),
            FieldSpec("type_size", 76, "count"),
        ),
    ),
    RecordDef(
        "ixAssetPackage",
        0x5C,
        92,
        (
            FieldSpec("parent_ptr", 8, "ptr"),
            FieldSpec("children_list_ptr", 12, "ptr"),
            FieldSpec("name_data_ptr", 24, "ptr"),
            FieldSpec("name_reserve", 28, "count"),
            FieldSpec("name_size", 32, "count"),
            FieldSpec("linked_packages_ptr", 52, "ptr"),
            FieldSpec("linked_packages_reserve", 56, "count"),
            FieldSpec("linked_packages_size", 60, "count"),
            FieldSpec("asset_vector_ptr", 72, "ptr"),
            FieldSpec("asset_vector_reserve", 76, "count"),
            FieldSpec("asset_vector_size", 80, "count"),
        ),
    ),
)


def _iter_tag_offsets(data: bytes, tag: int) -> Iterable[int]:
    start = 0
    needle = bytes((tag,))
    while True:
        offset = data.find(needle, start)
        if offset < 0:
            return
        yield offset
        start = offset + 1


def _safe_u32(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    return _u32be(data, offset)


def _count_u32_refs(data: bytes, value: int) -> int:
    if value < 0 or value > 0xFFFFFFFF:
        return 0
    return data.count(struct.pack(">I", value))


def _ascii_preview(data: bytes, offset: int, length: int = 32) -> str:
    chunk = data[offset : min(len(data), offset + length)]
    out = []
    for byte in chunk:
        if byte == 0:
            out.append("\\0")
        elif byte in (0x0A, 0x0D, 0x09):
            out.append(chr(byte).encode("unicode_escape").decode("ascii"))
        elif 0x20 <= byte <= 0x7E:
            out.append(chr(byte))
        else:
            out.append(f"\\x{byte:02X}")
    return "".join(out)


def _classify_value(value: int, role: str, data: bytes, text_resources: Sequence[TextResource]) -> str:
    if value == 0:
        return "null"
    for index, resource in enumerate(text_resources):
        if value == resource.payload_hash:
            return f"text_payload_hash[{index}]"
        if value == resource.payload_start:
            return f"text_payload_start[{index}]"
        if value == resource.payload_end:
            return f"text_payload_end[{index}]"
        if value == resource.payload_length:
            return f"text_payload_length[{index}]"
    if 0 <= value < len(data):
        return "file_offset"
    if role == "count":
        return "count_or_capacity"
    if 0x01000000 <= value <= 0x9FFFFFFF:
        return "runtime_ptr_or_hash"
    return "external_or_unknown"


def _score_record(record_def: RecordDef, values: dict[str, int], data: bytes, offset: int, text_resources: Sequence[TextResource]) -> int:
    score = 0
    text_lengths = {resource.payload_length for resource in text_resources}

    def sane_count(name: str, max_value: int = 0x200000) -> bool:
        value = values.get(name)
        return value is not None and 0 <= value <= max_value

    if record_def.kind == "ixVector<char>":
        if sane_count("reserve_or_end", len(data) + 0x10000):
            score += 1
        if sane_count("size_or_capacity", len(data) + 0x10000):
            score += 1
        preview_8 = data[offset + 1 + 8 : offset + 1 + 24]
        preview_16 = data[offset + 1 + 16 : offset + 1 + 40]
        if _mostly_printable(preview_8) or _mostly_printable(preview_16):
            score += 3
        if values.get("size_or_capacity") in text_lengths:
            score += 2
    elif record_def.kind in {"ixVector<ixAsset *>", "ixVector<ixPackage *>"}:
        reserve = values.get("reserve_or_end", 0)
        size = values.get("size_or_capacity", 0)
        if 0 <= size <= reserve <= 0x10000:
            score += 3
        elif 0 <= size <= 0x10000 and 0 <= reserve <= len(data) + 0x10000:
            score += 1
    elif record_def.kind == "ixList<ixPackage *>":
        if sane_count("size", 0x10000):
            score += 2
        if values.get("size", 0) == 0 or values.get("root_ptr", 0) != 0:
            score += 1
    elif record_def.kind == "ixDblCnt<ixPackage *>":
        nonzero = sum(1 for name in ("data_ptr", "tail_ptr", "head_ptr") if values.get(name, 0) != 0)
        score += 1 + nonzero
    elif record_def.kind == "ixRawFileImage":
        if 0 <= values.get("name_size", 0) <= values.get("name_reserve", 0) <= 0x10000:
            score += 2
        if values.get("data_size") in text_lengths:
            score += 4
        if values.get("data_size") == values.get("data_reserve") and sane_count("data_size"):
            score += 2
        if values.get("type_size") == 5:
            score += 3
    elif record_def.kind == "ixFileImage":
        if values.get("data_size") in text_lengths:
            score += 3
        if values.get("data_size") == values.get("data_reserve") and sane_count("data_size"):
            score += 2
    elif record_def.kind == "ixAssetPackage":
        asset_size = values.get("asset_vector_size", 0)
        asset_reserve = values.get("asset_vector_reserve", 0)
        if 0 <= asset_size <= asset_reserve <= 0x10000:
            score += 4
        if 0 <= values.get("name_size", 0) <= values.get("name_reserve", 0) <= 0x10000:
            score += 2
    elif record_def.kind in {"ixAsset", "ixPackage", "ixTreeNode<ixPackage>"}:
        if 0 <= values.get("name_size", 0) <= values.get("name_reserve", 0) <= 0x10000:
            score += 2
        if sane_count("linked_packages_size", 0x10000):
            score += 1
    return score


def _mostly_printable(chunk: bytes) -> bool:
    if not chunk:
        return False
    printable = sum(1 for byte in chunk if byte in (0x09, 0x0A, 0x0D) or 0x20 <= byte <= 0x7E)
    return printable >= max(4, len(chunk) // 2)


def _record_issues(record_def: RecordDef, values: dict[str, int], text_resources: Sequence[TextResource]) -> tuple[str, ...]:
    issues: list[str] = []

    def add_if_count_with_null_pointer(size_name: str, ptr_name: str) -> None:
        if values.get(size_name, 0) > 0 and values.get(ptr_name, 0) == 0:
            issues.append(f"{size_name}>0 with {ptr_name}=NULL")

    if record_def.kind == "ixVector<char>":
        # The real file layout appears to inline string bytes in places where
        # the runtime schema names reserve/size/allocator fields. Treat these
        # as decoded observations, not invariant failures.
        pass
    elif record_def.kind in {"ixVector<ixAsset *>", "ixVector<ixPackage *>"}:
        add_if_count_with_null_pointer("size_or_capacity", "data_begin_ptr")
        reserve = values.get("reserve_or_end", 0)
        size = values.get("size_or_capacity", 0)
        if 0 <= reserve <= 0x10000 and size > reserve:
            issues.append("size_or_capacity greater than reserve_or_end")
    elif record_def.kind == "ixList<ixPackage *>":
        add_if_count_with_null_pointer("size", "root_ptr")
    elif record_def.kind == "ixAssetPackage":
        add_if_count_with_null_pointer("asset_vector_size", "asset_vector_ptr")
        add_if_count_with_null_pointer("linked_packages_size", "linked_packages_ptr")
        if values.get("asset_vector_size", 0) > values.get("asset_vector_reserve", 0):
            issues.append("asset_vector_size greater than asset_vector_reserve")
    elif record_def.kind == "ixPackage":
        add_if_count_with_null_pointer("linked_packages_size", "linked_packages_ptr")
    elif record_def.kind == "ixRawFileImage":
        text_lengths = {resource.payload_length for resource in text_resources}
        text_hashes = {resource.payload_hash for resource in text_resources}
        if values.get("data_size") in text_lengths and values.get("data_ptr") not in text_hashes:
            issues.append("data_size matches a Text payload but data_ptr is not that payload hash")
        if values.get("data_size", 0) > values.get("data_reserve", 0):
            issues.append("data_size greater than data_reserve")
    elif record_def.kind == "ixFileImage":
        if values.get("data_size", 0) > values.get("data_reserve", 0):
            issues.append("data_size greater than data_reserve")
    return tuple(issues)


def _decode_record(record_def: RecordDef, data: bytes, offset: int, text_resources: Sequence[TextResource]) -> OwnershipRecord | None:
    if offset + 1 + record_def.min_size > len(data):
        return None
    raw_values: dict[str, int] = {}
    fields: list[FieldValue] = []
    for field in record_def.fields:
        abs_offset = offset + 1 + field.rel_offset
        value = _safe_u32(data, abs_offset)
        if value is None:
            return None
        raw_values[field.name] = value
        fields.append(
            FieldValue(
                name=field.name,
                abs_offset=abs_offset,
                value=value,
                role=field.role,
                classification=_classify_value(value, field.role, data, text_resources),
                ref_count=_count_u32_refs(data, value),
            )
        )

    score = _score_record(record_def, raw_values, data, offset, text_resources)
    if score <= 0:
        return None
    return OwnershipRecord(
        kind=record_def.kind,
        tag=record_def.tag,
        offset=offset,
        score=score,
        fields=tuple(fields),
        preview_at_8=_ascii_preview(data, offset + 1 + 8),
        preview_at_16=_ascii_preview(data, offset + 1 + 16),
        issues=_record_issues(record_def, raw_values, text_resources),
    )


def analyze_ownership_fields(path: Path) -> FileOwnershipAnalysis:
    data = path.read_bytes()
    magic_hex, kind = describe_magic(data)
    document = parse_ixb_document(data)
    class_names = tuple(ixb_class.name for _, ixb_class in sorted(document.classes.items()))
    text_resources = tuple(find_text_resources(data))
    records_by_kind: dict[str, list[OwnershipRecord]] = {}

    for record_def in RECORD_DEFS:
        records: list[OwnershipRecord] = []
        for offset in _iter_tag_offsets(data, record_def.tag):
            record = _decode_record(record_def, data, offset, text_resources)
            if record is None:
                continue
            records.append(record)
        records.sort(key=lambda item: (-item.score, item.offset))
        records_by_kind[record_def.kind] = records[:12]

    return FileOwnershipAnalysis(
        path=path,
        data=data,
        magic_description=f"{magic_hex} ({kind})",
        objects_start=document.objects_start,
        objects_end=document.objects_end,
        class_names=class_names,
        text_resources=text_resources,
        records_by_kind={kind: tuple(records) for kind, records in records_by_kind.items()},
    )


def _hex(value: int | None) -> str:
    return "None" if value is None else f"0x{value:08X}"


def _range_text(start: int | None, end: int | None) -> str:
    if start is None or end is None:
        return "unknown"
    return f"0x{start:08X}-0x{end:08X}"


def _text_resource_lines(analysis: FileOwnershipAnalysis) -> list[str]:
    lines: list[str] = []
    if not analysis.text_resources:
        return ["  Text resources: none detected"]
    lines.append("  Text resources:")
    for index, resource in enumerate(analysis.text_resources):
        lines.append(
            "    "
            f"[{index}] payload=0x{resource.payload_start:08X}-0x{resource.payload_end:08X} "
            f"len={resource.payload_length} hash=0x{resource.payload_hash:08X} "
            f"length_field=0x{resource.payload_length_offset:08X}"
        )
    return lines


def _canonical_raw_file_image(analysis: FileOwnershipAnalysis) -> OwnershipRecord | None:
    text_lengths = {resource.payload_length for resource in analysis.text_resources}
    for record in analysis.records_by_kind.get("ixRawFileImage", ()):
        if record.get("data_size") in text_lengths and record.get("type_size") == 5:
            return record
    records = analysis.records_by_kind.get("ixRawFileImage", ())
    return records[0] if records else None


def _canonical_asset_package(analysis: FileOwnershipAnalysis) -> OwnershipRecord | None:
    for record in analysis.records_by_kind.get("ixAssetPackage", ()):
        if (record.get("asset_vector_size") or 0) > 0:
            return record
    records = analysis.records_by_kind.get("ixAssetPackage", ())
    return records[0] if records else None


def _field_line(record: OwnershipRecord, prefix: str = "      ") -> list[str]:
    lines = [
        f"{prefix}{record.kind} tag=0x{record.tag:02X} offset=0x{record.offset:08X} score={record.score}",
        f"{prefix}  preview@+8:  {record.preview_at_8}",
        f"{prefix}  preview@+16: {record.preview_at_16}",
    ]
    for field in record.fields:
        lines.append(
            f"{prefix}  {field.name}@0x{field.abs_offset:08X}="
            f"{_hex(field.value)} {field.classification} refs={field.ref_count}"
        )
    if record.issues:
        for issue in record.issues:
            lines.append(f"{prefix}  ISSUE: {issue}")
    return lines


def _issue_lines(label: str, analysis: FileOwnershipAnalysis) -> list[str]:
    lines = [f"{label} invariant issues:"]
    any_issue = False
    canonical_raw = _canonical_raw_file_image(analysis)
    canonical_asset_package = _canonical_asset_package(analysis)
    for kind, records in analysis.records_by_kind.items():
        for record in records:
            high_confidence = record in (canonical_raw, canonical_asset_package) or record.score >= 5
            if not high_confidence:
                continue
            for issue in record.issues:
                lines.append(f"  {kind} at 0x{record.offset:08X}: {issue}")
                any_issue = True
    if not any_issue:
        lines.append("  none found in scored ownership candidates")
    return lines


def _high_signal_findings(real: FileOwnershipAnalysis, synthetic: FileOwnershipAnalysis) -> list[str]:
    lines = ["High-signal ownership differences:"]
    real_raw = _canonical_raw_file_image(real)
    synthetic_raw = _canonical_raw_file_image(synthetic)
    if real_raw and synthetic_raw:
        real_data_ptr = real_raw.get("data_ptr")
        synthetic_data_ptr = synthetic_raw.get("data_ptr")
        real_hashes = {resource.payload_hash for resource in real.text_resources}
        synthetic_hashes = {resource.payload_hash for resource in synthetic.text_resources}
        lines.append(
            "  ixRawFileImage.data_ptr: "
            f"real={_hex(real_data_ptr)} synthetic={_hex(synthetic_data_ptr)}"
        )
        if real_data_ptr in real_hashes and synthetic_data_ptr not in synthetic_hashes:
            lines.append(
                "  SUSPECT: real RawFileImage data_ptr equals the Text payload hash, "
                "but synthetic data_ptr is a fake pointer instead of the synthetic Text payload hash."
            )
        lines.append(
            "  ixRawFileImage data size/reserve: "
            f"real={real_raw.get('data_size')}/{real_raw.get('data_reserve')} "
            f"synthetic={synthetic_raw.get('data_size')}/{synthetic_raw.get('data_reserve')}"
        )
        lines.append(
            "  ixRawFileImage type vector: "
            f"real size={real_raw.get('type_size')} reserve={real_raw.get('type_reserve')} "
            f"synthetic size={synthetic_raw.get('type_size')} reserve={synthetic_raw.get('type_reserve')}"
        )
    else:
        lines.append("  ixRawFileImage canonical candidate missing on one side")

    real_asset_pkg = _canonical_asset_package(real)
    synthetic_asset_pkg = _canonical_asset_package(synthetic)
    if real_asset_pkg and synthetic_asset_pkg:
        lines.append(
            "  ixAssetPackage asset vector: "
            f"real ptr={_hex(real_asset_pkg.get('asset_vector_ptr'))} "
            f"reserve={real_asset_pkg.get('asset_vector_reserve')} size={real_asset_pkg.get('asset_vector_size')} | "
            f"synthetic ptr={_hex(synthetic_asset_pkg.get('asset_vector_ptr'))} "
            f"reserve={synthetic_asset_pkg.get('asset_vector_reserve')} size={synthetic_asset_pkg.get('asset_vector_size')}"
        )
        if (synthetic_asset_pkg.get("asset_vector_size") or 0) > 0 and synthetic_asset_pkg.get("asset_vector_ptr") == 0:
            lines.append("  SUSPECT: synthetic asset vector has non-zero size with NULL pointer.")
    else:
        lines.append("  ixAssetPackage canonical candidate missing on one side")

    real_char = real.records_by_kind.get("ixVector<char>", ())
    synthetic_char = synthetic.records_by_kind.get("ixVector<char>", ())
    if real_char and synthetic_char:
        lines.append(
            "  ixVector<char> preview pattern: "
            f"real first preview@+8={real_char[0].preview_at_8!r}; "
            f"synthetic first preview@+8={synthetic_char[0].preview_at_8!r}"
        )
        if "\\0" in synthetic_char[0].preview_at_8 and "\\0" not in real_char[0].preview_at_8[:16]:
            lines.append(
                "  SUSPECT: synthetic char vector carries runtime-style size/allocator words "
                "before inline text, while the real file-layout candidate starts with text bytes sooner."
            )
    return lines


def _summary_counts(analysis: FileOwnershipAnalysis) -> str:
    parts = []
    for record_def in RECORD_DEFS:
        count = len(analysis.records_by_kind.get(record_def.kind, ()))
        if count:
            parts.append(f"{record_def.kind}={count}")
    return ", ".join(parts) if parts else "none"


def format_ownership_diff_report(real: FileOwnershipAnalysis, synthetic: FileOwnershipAnalysis, synthetic_label: str = "synthetic") -> str:
    lines: list[str] = [
        "# Focused IXB Ownership Field Diff",
        "",
        "This report is read-only. It does not propose or emit new structures.",
        "Generic candidate scans can catch tag-like bytes inside string data; the canonical records and high-signal findings are the actionable section.",
        "",
        f"Real lyric: {real.path}",
        f"  size={len(real.data)} magic={real.magic_description} objects={_range_text(real.objects_start, real.objects_end)}",
        f"  ownership candidate counts: {_summary_counts(real)}",
        *_text_resource_lines(real),
        "",
        f"{synthetic_label}: {synthetic.path}",
        f"  size={len(synthetic.data)} magic={synthetic.magic_description} objects={_range_text(synthetic.objects_start, synthetic.objects_end)}",
        f"  ownership candidate counts: {_summary_counts(synthetic)}",
        *_text_resource_lines(synthetic),
        "",
        *_high_signal_findings(real, synthetic),
        "",
        *_issue_lines("Real", real),
        "",
        *_issue_lines(synthetic_label, synthetic),
        "",
        "Canonical raw file image records:",
    ]

    real_raw = _canonical_raw_file_image(real)
    synthetic_raw = _canonical_raw_file_image(synthetic)
    if real_raw:
        lines.extend(_field_line(real_raw, "  real "))
    else:
        lines.append("  real none")
    if synthetic_raw:
        lines.extend(_field_line(synthetic_raw, f"  {synthetic_label} "))
    else:
        lines.append(f"  {synthetic_label} none")

    lines.append("")
    lines.append("Canonical asset package records:")
    real_asset_pkg = _canonical_asset_package(real)
    synthetic_asset_pkg = _canonical_asset_package(synthetic)
    if real_asset_pkg:
        lines.extend(_field_line(real_asset_pkg, "  real "))
    else:
        lines.append("  real none")
    if synthetic_asset_pkg:
        lines.extend(_field_line(synthetic_asset_pkg, f"  {synthetic_label} "))
    else:
        lines.append(f"  {synthetic_label} none")

    lines.append("")
    lines.append("Top scored ownership/container candidates by kind:")
    for record_def in RECORD_DEFS:
        kind = record_def.kind
        lines.append(f"  {kind}:")
        real_records = real.records_by_kind.get(kind, ())[:4]
        synthetic_records = synthetic.records_by_kind.get(kind, ())[:4]
        if real_records:
            lines.append("    real:")
            for record in real_records:
                lines.extend(_field_line(record, "      "))
        else:
            lines.append("    real: none")
        if synthetic_records:
            lines.append(f"    {synthetic_label}:")
            for record in synthetic_records:
                lines.extend(_field_line(record, "      "))
        else:
            lines.append(f"    {synthetic_label}: none")

    return "\n".join(lines) + "\n"


def _synthetic_inputs_from_args(args: argparse.Namespace) -> list[tuple[str, Path]]:
    inputs: list[tuple[str, Path]] = []
    if args.synthetic_root:
        for child in sorted(args.synthetic_root.iterdir()):
            if not child.is_dir():
                continue
            lyric = child / args.stem
            if lyric.exists():
                inputs.append((child.name, lyric))
    for index, lyric in enumerate(args.synthetic_lyric or []):
        label = args.label[index] if args.label and index < len(args.label) else lyric.stem
        inputs.append((label, lyric))
    return inputs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-lyric", type=Path, required=True, help="Known-working *_Lyric.X360 file.")
    parser.add_argument(
        "--synthetic-lyric",
        type=Path,
        action="append",
        help="Synthetic *_Lyric.X360 file. May be passed multiple times.",
    )
    parser.add_argument("--label", action="append", help="Label for a --synthetic-lyric input.")
    parser.add_argument(
        "--synthetic-root",
        type=Path,
        help="Directory containing variant subdirectories with the lyric filename from --stem.",
    )
    parser.add_argument("--stem", default="1234_Lyric.X360", help="Lyric filename under --synthetic-root.")
    args = parser.parse_args(argv)

    synthetic_inputs = _synthetic_inputs_from_args(args)
    if not synthetic_inputs:
        parser.error("provide --synthetic-lyric or --synthetic-root")

    real = analyze_ownership_fields(args.real_lyric)
    for index, (label, path) in enumerate(synthetic_inputs):
        if index:
            print("\n" + "=" * 80 + "\n")
        synthetic = analyze_ownership_fields(path)
        print(format_ownership_diff_report(real, synthetic, label), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
