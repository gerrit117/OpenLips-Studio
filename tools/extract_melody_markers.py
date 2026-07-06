#!/usr/bin/env python3
"""Extract Lips lpsMelodyMarker-like records from .X360 chart files."""

from __future__ import annotations

import argparse
import csv
import math
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TextIO


PLAIN_IXB_MAGIC = b"<ixb"
COMPRESSED_MAGICS = {
    b"\x0f\xf5\x12\xed": "LZXTDECODE compressed",
    b"\x0f\xf5\x12\xee": "LZXNATIVE compressed",
}

RUNTIME_MELODY_VTABLE = 0x8200D8D0
FILE_MELODY_CLASS_HASH = 0x2404A1CD

TIME_RANGE = (0.0, 900.0)
LENGTH_RANGE = (0.02, 20.0)
RAW_PITCH_RANGE = (24, 84)
TONE_RANGE = (0.0, 11.0)
OCTAVE_RANGE = (1, 8)
TILT_RANGE = (0, 1)


@dataclass(frozen=True)
class MelodyMarker:
    offset: int
    time: float
    length: float
    raw_pitch: int
    tone: float
    octave: int
    tilt: int
    source: str = "scan"


@dataclass(frozen=True)
class MelodyLayout:
    name: str
    size: int
    time: int
    length: int
    raw_pitch: int
    tone: int
    octave: int
    tilt: int
    scan_prefix: int = 0
    step: int = 1
    class_index: int | None = None


@dataclass(frozen=True)
class IxbClass:
    index: int
    name: str
    size: int
    base: int | None
    members: dict[str, int]


@dataclass(frozen=True)
class IxbUriEntry:
    key: int
    uri: str
    offset: int


@dataclass(frozen=True)
class IxbDocument:
    classes: dict[int, IxbClass]
    is_big_endian: bool | None
    is_text: bool | None
    platform: str | None
    num_elements: int | None
    classes_start: int | None
    classes_end: int | None
    urilist_start: int | None
    urilist_end: int | None
    objects_start: int | None
    objects_end: int | None
    uri_entries: tuple[IxbUriEntry, ...]


@dataclass(frozen=True)
class IxbObjectRecordCandidate:
    offset: int
    zero: int
    value: int
    payload_size: int
    payload_start: int
    payload_end: int


@dataclass(frozen=True)
class FileIoHeaderCandidate:
    offset: int
    tag: bytes
    name: bytes
    version: int
    secondary: int


@dataclass
class DebugInfo:
    path: Path
    size: int
    magic: bytes
    kind: str
    role: str
    schema_found: bool
    melody_class: IxbClass | None
    scan_counts: Counter[str]
    rejection_counts: Counter[str]
    walker_steps: int = 0
    walker_resyncs: int = 0
    detection_mode: str = "unsupported/unknown"
    failure_reason: str | None = None


def _u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _u16be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _i32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">i", data, offset)[0]


def _f32be(data: bytes, offset: int) -> float:
    return struct.unpack_from(">f", data, offset)[0]


def _class_hash(name: str) -> int:
    """IXB object records carry a per-class 32-bit value; this matches known charts."""
    value = 0
    for byte in name.encode("utf-8"):
        value = (value * 33 + byte) & 0xFFFFFFFF
    return value


def describe_magic(data: bytes) -> tuple[str, str]:
    magic = data[:4]
    hex_magic = " ".join(f"{byte:02X}" for byte in magic)
    if magic == PLAIN_IXB_MAGIC:
        return hex_magic, "plain IXB"
    if magic in COMPRESSED_MAGICS:
        return hex_magic, COMPRESSED_MAGICS[magic]
    return hex_magic, "unknown"


def parse_ixb_classes(data: bytes) -> dict[int, IxbClass]:
    start = data.find(b"<Classes>")
    end = data.find(b"</Classes>")
    if start < 0 or end < 0:
        return {}

    fragment = data[start : end + len(b"</Classes>")].decode("utf-8", errors="strict")
    root = ET.fromstring(fragment)
    classes: dict[int, IxbClass] = {}
    for index, node in enumerate(root.findall("Class"), start=1):
        members = {
            member.attrib["Name"]: int(member.attrib["Offset"])
            for member in node.findall("./Members/Member")
            if "Name" in member.attrib and "Offset" in member.attrib
        }
        classes[index] = IxbClass(
            index=index,
            name=node.attrib.get("Name", ""),
            size=int(node.attrib.get("Size", "0")),
            base=int(node.attrib["Base"]) if "Base" in node.attrib else None,
            members=members,
        )
    return classes


def _parse_bool_attr(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _parse_int_attr(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value, 10)
    except ValueError:
        return None


def _opening_ixb_attrs(data: bytes) -> dict[str, str]:
    end = data.find(b">")
    if end < 0 or not data.startswith(PLAIN_IXB_MAGIC):
        return {}
    fragment = data[: end + 1].decode("utf-8", errors="strict")
    try:
        node = ET.fromstring(fragment + "</ixb>")
    except ET.ParseError:
        return {}
    return dict(node.attrib)


def _range_after_tag(data: bytes, start_tag: bytes, end_tag: bytes) -> tuple[int | None, int | None]:
    start = data.find(start_tag)
    end = data.find(end_tag)
    if start < 0:
        range_start = None
    else:
        range_start = start + len(start_tag)
    if end < 0:
        range_end = None
    else:
        range_end = end
    return range_start, range_end


def parse_ixb_uri_list(data: bytes) -> tuple[IxbUriEntry, ...]:
    start = data.find(b"<UriList>")
    end = data.find(b"</UriList>")
    if start < 0 or end < 0:
        return ()
    fragment = data[start : end + len(b"</UriList>")].decode("utf-8", errors="strict")
    root = ET.fromstring(fragment)
    entries: list[IxbUriEntry] = []
    search_from = start
    for node in root.findall("Uri"):
        key = _parse_int_attr(node.attrib.get("Key"))
        uri = node.attrib.get("Uri")
        if key is None or uri is None:
            continue
        needle = f'<Uri Key="{key}"'.encode("utf-8")
        offset = data.find(needle, search_from, end)
        if offset < 0:
            offset = start
        else:
            search_from = offset + 1
        entries.append(IxbUriEntry(key=key, uri=uri, offset=offset))
    return tuple(entries)


def parse_ixb_document(data: bytes) -> IxbDocument:
    attrs = _opening_ixb_attrs(data)
    classes_start, classes_end = _range_after_tag(data, b"<Classes>", b"</Classes>")
    urilist_start, urilist_end = _range_after_tag(data, b"<UriList>", b"</UriList>")
    objects_start, objects_end = _range_after_tag(data, b"<Objects>", b"</Objects>")
    return IxbDocument(
        classes=parse_ixb_classes(data),
        is_big_endian=_parse_bool_attr(attrs.get("IsBigEndian")),
        is_text=_parse_bool_attr(attrs.get("IsText")),
        platform=attrs.get("Platform"),
        num_elements=_parse_int_attr(attrs.get("NumOfElements")),
        classes_start=classes_start,
        classes_end=classes_end,
        urilist_start=urilist_start,
        urilist_end=urilist_end,
        objects_start=objects_start,
        objects_end=objects_end,
        uri_entries=parse_ixb_uri_list(data),
    )


def validate_ixb_write_order(document: IxbDocument) -> list[str]:
    """Return writer-order diagnostics inspired by Ghidra observations, not a spec.

    XEXLoaderWV analysis shows the game's generic writer emitting header
    attributes, Classes, UriList, then Objects. Existing samples/tools may omit
    UriList, so diagnostics stay non-fatal.
    """
    warnings: list[str] = []
    if document.classes_start is None or document.classes_end is None:
        warnings.append("missing Classes section")
    elif document.classes_start > document.classes_end:
        warnings.append("Classes section has invalid bounds")

    if document.objects_start is None or document.objects_end is None:
        warnings.append("missing Objects section")
    elif document.objects_start > document.objects_end:
        warnings.append("Objects section has invalid bounds")

    if (
        document.classes_end is not None
        and document.objects_start is not None
        and document.classes_end > document.objects_start
    ):
        warnings.append("Classes section appears after Objects start")

    has_urilist = document.urilist_start is not None or document.urilist_end is not None
    if has_urilist:
        if document.urilist_start is None or document.urilist_end is None:
            warnings.append("incomplete UriList section")
        elif document.urilist_start > document.urilist_end:
            warnings.append("UriList section has invalid bounds")
        else:
            if document.classes_end is not None and document.classes_end > document.urilist_start:
                warnings.append("UriList appears before Classes close")
            if document.objects_start is not None and document.urilist_end > document.objects_start:
                warnings.append("UriList appears after Objects start")
    return warnings


def probe_object_record_headers(
    data: bytes,
    document: IxbDocument,
    *,
    max_payload_size: int = 0x400000,
) -> tuple[IxbObjectRecordCandidate, ...]:
    """Find possible object/payload records without changing parser behavior.

    XEXLoaderWV Ghidra notes show a writer helper emitting three 4-byte fields
    followed by payload bytes. The meaning of the middle field is still a
    hypothesis, so this remains diagnostic only.
    """
    if document.objects_start is None or document.objects_end is None:
        return ()
    candidates: list[IxbObjectRecordCandidate] = []
    start = document.objects_start
    end = document.objects_end
    for offset in range(start, max(start, end - 11)):
        zero = _u32be(data, offset)
        if zero != 0:
            continue
        value = _u32be(data, offset + 4)
        payload_size = _u32be(data, offset + 8)
        payload_start = offset + 12
        payload_end = payload_start + payload_size
        if payload_size <= 0 or payload_size > max_payload_size:
            continue
        if payload_end > end:
            continue
        candidates.append(
            IxbObjectRecordCandidate(
                offset=offset,
                zero=zero,
                value=value,
                payload_size=payload_size,
                payload_start=payload_start,
                payload_end=payload_end,
            )
        )
    return tuple(candidates)


def _is_header_ascii(value: bytes) -> bool:
    return all(0x20 <= byte <= 0x7E for byte in value)


def find_fileio_header_candidates(data: bytes) -> tuple[FileIoHeaderCandidate, ...]:
    """Find possible FileIO header objects from Ghidra-observed field offsets.

    The game validates a 4-byte tag at +0x10, 4-byte name at +0x14, a 16-bit
    version at +0x18, and another 16-bit field at +0x1a. This does not prove
    the structure is the outer .X360 header, so callers should present results
    as candidates only.
    """
    candidates: list[FileIoHeaderCandidate] = []
    for offset in range(0, max(0, len(data) - 0x1b)):
        tag = data[offset + 0x10 : offset + 0x14]
        name = data[offset + 0x14 : offset + 0x18]
        if not (_is_header_ascii(tag) and _is_header_ascii(name)):
            continue
        version = _u16be(data, offset + 0x18)
        secondary = _u16be(data, offset + 0x1A)
        if version > 0x1000 or secondary > 0x1000:
            continue
        candidates.append(
            FileIoHeaderCandidate(
                offset=offset,
                tag=tag,
                name=name,
                version=version,
                secondary=secondary,
            )
        )
    return tuple(candidates)


def _inherited_members(classes: dict[int, IxbClass], cls: IxbClass) -> dict[str, int]:
    merged: dict[str, int] = {}
    if cls.base and cls.base in classes:
        merged.update(_inherited_members(classes, classes[cls.base]))
    merged.update(cls.members)
    return merged


def _schema_file_class_codes(cls: IxbClass) -> list[int]:
    codes: list[int] = [cls.size & 0xFF, (cls.size + 8) & 0xFF]
    if cls.name == "lpsMelodyMarker":
        codes.append(FILE_MELODY_CLASS_HASH >> 24)
    codes.append(cls.index & 0xFF)
    return list(dict.fromkeys(codes))


def melody_layouts_from_schema(data: bytes, classes: dict[int, IxbClass] | None = None) -> list[MelodyLayout]:
    classes = parse_ixb_classes(data) if classes is None else classes
    melody_class = next((cls for cls in classes.values() if cls.name == "lpsMelodyMarker"), None)
    if not melody_class:
        return []

    members = _inherited_members(classes, melody_class)
    time_offset = members.get("m_fTriggerTiming", 8)
    length_offset = members.get("m_fLength", 12)
    raw_pitch_offset = members.get("m_iTrackIndex", 16)
    tone_offset = members.get("m_Tone", melody_class.members.get("m_Tone", 24))
    tilt_offset = members.get("m_bTilt", melody_class.members.get("m_bTilt", 32))
    size = melody_class.size

    file_layouts = [
        MelodyLayout(
            name=f"ixb-schema:{melody_class.name}:0x{class_code:02X}",
            size=size,
            time=time_offset,
            length=length_offset,
            raw_pitch=raw_pitch_offset,
            tone=tone_offset,
            octave=tone_offset + 4,
            tilt=tilt_offset,
            scan_prefix=1,
            step=1,
            class_index=class_code,
        )
        for class_code in _schema_file_class_codes(melody_class)
    ]
    return [
        *file_layouts,
        MelodyLayout(
            name=f"runtime-schema:{melody_class.name}",
            size=size,
            time=time_offset,
            length=length_offset,
            raw_pitch=raw_pitch_offset,
            tone=tone_offset,
            octave=tone_offset + 4,
            tilt=tilt_offset,
            scan_prefix=0,
            step=1,
            class_index=melody_class.index,
        ),
    ]


def fallback_layouts() -> list[MelodyLayout]:
    return [
        MelodyLayout("ixb-fallback-36", 36, 8, 12, 16, 24, 28, 32, scan_prefix=1, step=1, class_index=0x24),
        MelodyLayout("ixb-fallback-40", 40, 8, 12, 16, 24, 28, 32, scan_prefix=1, step=1, class_index=0x24),
        MelodyLayout("runtime-fallback", 36, 8, 12, 16, 24, 28, 32, scan_prefix=0, step=1),
    ]


def _rejection_reason(marker: MelodyMarker) -> str | None:
    if not all(math.isfinite(value) for value in (marker.time, marker.length, marker.tone)):
        return "non-finite float"
    if not (TIME_RANGE[0] <= marker.time <= TIME_RANGE[1]):
        return "time out of range"
    if not (LENGTH_RANGE[0] <= marker.length <= LENGTH_RANGE[1]):
        return "length out of range"
    if not (RAW_PITCH_RANGE[0] <= marker.raw_pitch <= RAW_PITCH_RANGE[1]):
        return "raw_pitch out of range"
    if not (TONE_RANGE[0] <= marker.tone <= TONE_RANGE[1]):
        return "tone out of range"
    if not (OCTAVE_RANGE[0] <= marker.octave <= OCTAVE_RANGE[1]):
        return "octave out of range"
    if not (TILT_RANGE[0] <= marker.tilt <= TILT_RANGE[1]):
        return "tilt out of range"
    return None


def _marker_at(data: bytes, offset: int, layout: MelodyLayout) -> MelodyMarker:
    base = offset + layout.scan_prefix
    return MelodyMarker(
        offset=offset,
        time=_f32be(data, base + layout.time),
        length=_f32be(data, base + layout.length),
        raw_pitch=_i32be(data, base + layout.raw_pitch),
        tone=_f32be(data, base + layout.tone),
        octave=_i32be(data, base + layout.octave),
        tilt=_i32be(data, base + layout.tilt),
        source=layout.name,
    )


def _candidate_offsets(data: bytes, layout: MelodyLayout) -> Iterable[int]:
    if layout.scan_prefix == 1:
        for offset in range(0, max(0, len(data) - layout.scan_prefix - layout.size + 1), layout.step):
            if layout.class_index is not None and data[offset] == layout.class_index:
                yield offset
        return

    for offset in range(0, max(0, len(data) - layout.size + 1), layout.step):
        if _u32be(data, offset) == RUNTIME_MELODY_VTABLE:
            yield offset


def _plausibility_offsets(data: bytes, layout: MelodyLayout) -> Iterable[int]:
    for offset in range(0, max(0, len(data) - layout.scan_prefix - layout.size + 1), layout.step):
        yield offset


def _collect_layout_markers(
    data: bytes,
    layout: MelodyLayout,
    offsets: Iterable[int],
    debug: DebugInfo | None = None,
    source: str = "fallback scan",
) -> list[MelodyMarker]:
    markers: list[MelodyMarker] = []
    seen_offsets: set[int] = set()
    for offset in offsets:
        marker = _marker_at(data, offset, layout)
        reason = _rejection_reason(marker)
        if reason:
            if debug:
                debug.rejection_counts[f"{layout.name}: {reason}"] += 1
            continue
        if offset in seen_offsets:
            continue
        seen_offsets.add(offset)
        markers.append(
            MelodyMarker(
                offset=marker.offset,
                time=marker.time,
                length=marker.length,
                raw_pitch=marker.raw_pitch,
                tone=marker.tone,
                octave=marker.octave,
                tilt=marker.tilt,
                source=source,
            )
        )
    if debug:
        debug.scan_counts[layout.name] += len(markers)
    return markers


def _best_marker_set(marker_sets: list[tuple[MelodyLayout, list[MelodyMarker]]]) -> list[MelodyMarker]:
    non_empty = [(layout, markers) for layout, markers in marker_sets if markers]
    if not non_empty:
        return []

    def score(item: tuple[MelodyLayout, list[MelodyMarker]]) -> tuple[int, int]:
        layout, markers = item
        file_record_bonus = 1 if layout.scan_prefix == 1 else 0
        return len(markers), file_record_bonus

    return max(non_empty, key=score)[1]


def _decode_from_body(data: bytes, object_offset: int, body_offset: int, layout: MelodyLayout) -> MelodyMarker:
    return MelodyMarker(
        offset=object_offset,
        time=_f32be(data, body_offset + layout.time),
        length=_f32be(data, body_offset + layout.length),
        raw_pitch=_i32be(data, body_offset + layout.raw_pitch),
        tone=_f32be(data, body_offset + layout.tone),
        octave=_i32be(data, body_offset + layout.octave),
        tilt=_i32be(data, body_offset + layout.tilt),
        source="schema/object-walker",
    )


def iter_object_records(data: bytes, document: IxbDocument, debug: DebugInfo | None = None) -> Iterable[tuple[int, int, IxbClass]]:
    """Walk the IXB object heap using one-byte class indices and schema sizes.

    Some observed heaps contain padding/null bytes or embedded payload areas. When the
    next byte is not a known class id, the walker advances one byte to resync; when it
    is known, it advances by the declared class size. This keeps the primary pass
    structural without assuming a single marker byte signature.
    """
    if document.objects_start is None or document.objects_end is None:
        return
    offset = document.objects_start
    end = document.objects_end
    while offset < end:
        class_index = data[offset]
        cls = document.classes.get(class_index)
        if not cls or cls.size <= 0 or offset + 1 + cls.size > end:
            if debug:
                debug.walker_resyncs += 1
            offset += 1
            continue
        if debug:
            debug.walker_steps += 1
        yield offset, offset + 1, cls
        offset += 1 + cls.size


def iter_melody_markers_object_walker(
    data: bytes,
    document: IxbDocument,
    debug: DebugInfo | None = None,
) -> Iterable[MelodyMarker]:
    melody_class = next((cls for cls in document.classes.values() if cls.name == "lpsMelodyMarker"), None)
    if not melody_class:
        return
    layouts = melody_layouts_from_schema(data, document.classes)
    if not layouts:
        return
    layout = next((item for item in layouts if item.name.startswith("ixb-schema:")), layouts[0])
    seen_offsets: set[int] = set()
    for object_offset, body_offset, cls in iter_object_records(data, document, debug):
        if cls.index != melody_class.index:
            continue
        marker = _decode_from_body(data, object_offset, body_offset, layout)
        reason = _rejection_reason(marker)
        if reason:
            if debug:
                debug.rejection_counts[f"schema/object-walker: {reason}"] += 1
            continue
        seen_offsets.add(object_offset)
        yield marker

    if document.objects_start is None or document.objects_end is None:
        return

    for layout in layouts:
        if layout.scan_prefix != 1 or layout.class_index is None:
            continue
        end = max(document.objects_start, document.objects_end - layout.scan_prefix - layout.size + 1)
        for offset in range(document.objects_start, end):
            if data[offset] != layout.class_index:
                continue
            marker = _decode_from_body(data, offset, offset + layout.scan_prefix, layout)
            reason = _rejection_reason(marker)
            if reason:
                if debug:
                    debug.rejection_counts[f"{layout.name}: {reason}"] += 1
                continue
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            if debug:
                debug.scan_counts[f"schema/object-walker:{layout.name}"] += 1
            yield marker


def iter_melody_markers(data: bytes, debug: DebugInfo | None = None) -> Iterable[MelodyMarker]:
    """Scan a blob for runtime and IXB-file MelodyMarker-like records."""
    document = parse_ixb_document(data)
    if document.classes and not any(cls.name == "lpsMelodyMarker" for cls in document.classes.values()):
        if debug:
            debug.detection_mode = "unsupported/unknown"
            debug.failure_reason = "IXB schema does not define lpsMelodyMarker"
        return
    walked = list(iter_melody_markers_object_walker(data, document, debug))
    layouts = melody_layouts_from_schema(data, document.classes) or fallback_layouts()
    candidate_sets = [
        (layout, _collect_layout_markers(data, layout, _candidate_offsets(data, layout), debug))
        for layout in layouts
    ]
    best_candidates = _best_marker_set(candidate_sets)
    if walked and (
        not best_candidates
        or len(walked) == len(best_candidates)
        or len(walked) >= max(10, len(best_candidates) // 2)
    ):
        if debug:
            debug.detection_mode = "schema/object-walker"
            debug.scan_counts["schema/object-walker"] += len(walked)
        yield from walked
        return

    if best_candidates:
        if debug:
            debug.detection_mode = "fallback scan"
        yield from best_candidates
        return

    plausibility_sets = [
        (
            layout,
            _collect_layout_markers(
                data,
                layout,
                _plausibility_offsets(data, layout),
                debug,
                source="fallback scan",
            ),
        )
        for layout in layouts
    ]
    best_plausibility = _best_marker_set(plausibility_sets)
    if best_plausibility:
        yield from best_plausibility
    if debug and best_plausibility:
        debug.detection_mode = "fallback scan"


def _new_debug_info(path: Path, data: bytes) -> DebugInfo:
    classes = parse_ixb_classes(data)
    melody_class = next((cls for cls in classes.values() if cls.name == "lpsMelodyMarker"), None)
    role = "lyric" if path.stem.endswith("_Lyric") else "chart"
    return DebugInfo(
        path=path,
        size=len(data),
        magic=data[:4],
        kind=describe_magic(data)[1],
        role=role,
        schema_found=bool(classes),
        melody_class=melody_class,
        scan_counts=Counter(),
        rejection_counts=Counter(),
    )


def detect_family(data: bytes, classes: dict[int, IxbClass] | None = None) -> str:
    classes = parse_ixb_classes(data) if classes is None else classes
    names = {cls.name for cls in classes.values()}
    melody_class = next((cls for cls in classes.values() if cls.name == "lpsMelodyMarker"), None)
    if not classes:
        return "unknown"
    if any(name.startswith("ls2") for name in names):
        return "Lips 2 / LS2"
    if "lpsHitMarker" in names or "lpsTimedNoisemakerMarker" in names:
        return "later-generation / DLC"
    if melody_class and melody_class.size >= 40:
        return "Lips 2/DLC-style chart"
    if melody_class and melody_class.size == 36:
        return "Lips 1-style chart"
    return "plain IXB Lips-family chart"


def extract_melody_markers(path: Path, debug: bool = False) -> tuple[list[MelodyMarker], DebugInfo | None]:
    data = path.read_bytes()
    debug_info = _new_debug_info(path, data) if debug else None
    magic = data[:4]
    if magic in COMPRESSED_MAGICS:
        if debug_info:
            debug_info.detection_mode = "unsupported/unknown"
            debug_info.failure_reason = f"{COMPRESSED_MAGICS[magic]} file must be decompressed before melody extraction"
        return [], debug_info
    markers = sorted(iter_melody_markers(data, debug_info), key=lambda marker: (marker.time, marker.offset))
    if debug_info and not markers:
        debug_info.detection_mode = "unsupported/unknown"
    return markers, debug_info


def write_csv(markers: Iterable[MelodyMarker], output: TextIO) -> None:
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["offset", "time", "length", "raw_pitch", "tone", "octave", "tilt"])
    for marker in markers:
        writer.writerow(
            [
                f"0x{marker.offset:08X}",
                f"{marker.time:.6f}",
                f"{marker.length:.6f}",
                marker.raw_pitch,
                f"{marker.tone:.6f}",
                marker.octave,
                marker.tilt,
            ]
        )


def inspect_chart(path: Path, debug: bool = False) -> tuple[list[str], list[MelodyMarker]]:
    data = path.read_bytes()
    magic_hex, kind = describe_magic(data)
    markers, debug_info = extract_melody_markers(path, debug=debug)
    classes = parse_ixb_classes(data)
    family = detect_family(data, classes)
    mode = markers[0].source if markers else (debug_info.detection_mode if debug_info else "unsupported/unknown")
    lines = [
        f"{path.name}",
        f"  size: {len(data)}",
        f"  magic: {magic_hex}",
        f"  kind: {kind}",
        f"  role: {'lyric' if path.stem.endswith('_Lyric') else 'chart'}",
        f"  family: {family}",
        f"  mode: {mode}",
        f"  candidates: {len(markers)}",
        f"  validation: {validation_summary(markers, debug_info, path, kind)}",
        "  first 5 candidates:",
    ]
    for marker in markers[:5]:
        lines.append(
            "    "
            f"offset=0x{marker.offset:08X}, "
            f"time={marker.time:.6f}, length={marker.length:.6f}, "
            f"raw_pitch={marker.raw_pitch}, tone={marker.tone:.6f}, "
            f"octave={marker.octave}, tilt={marker.tilt}"
        )
    if debug and debug_info:
        lines.extend(format_debug(debug_info, zero_only=bool(markers)))
    return lines, markers


def format_marker(marker: MelodyMarker | None) -> str:
    if marker is None:
        return "-"
    return (
        f"offset=0x{marker.offset:08X} "
        f"time={marker.time:.6f} length={marker.length:.6f} "
        f"raw_pitch={marker.raw_pitch} tone={marker.tone:.6f} "
        f"octave={marker.octave} tilt={marker.tilt}"
    )


def analyze_chart(path: Path, debug: bool = False) -> list[str]:
    data = path.read_bytes()
    magic_hex, kind = describe_magic(data)
    markers, debug_info = extract_melody_markers(path, debug=debug)
    classes = parse_ixb_classes(data)
    family = detect_family(data, classes)
    mode = markers[0].source if markers else (debug_info.detection_mode if debug_info else "unsupported/unknown")
    lines = [
        f"{path.name}",
        f"  magic: {magic_hex}",
        f"  kind: {kind}",
        f"  role: {'lyric' if path.stem.endswith('_Lyric') else 'chart'}",
        f"  family: {family}",
        f"  marker_count: {len(markers)}",
        f"  first_marker: {format_marker(markers[0] if markers else None)}",
        f"  last_marker: {format_marker(markers[-1] if markers else None)}",
        f"  parsing_mode: {mode}",
        f"  validation: {validation_summary(markers, debug_info, path, kind)}",
    ]
    if debug and debug_info:
        lines.extend(format_debug(debug_info))
    return lines


def validation_summary(markers: list[MelodyMarker], debug_info: DebugInfo | None, path: Path, kind: str) -> str:
    if path.stem.endswith("_Lyric"):
        return "skipped: lyric container, not a melody chart"
    if kind != "plain IXB":
        return f"unsupported: {kind}"
    if markers:
        source = markers[0].source
        if source == "schema/object-walker":
            return "ok: schema/object-walker"
        return "warning: fallback scan"
    if debug_info and debug_info.failure_reason:
        return f"unsupported: {debug_info.failure_reason}"
    if path.suffix.lower() != ".x360":
        return "unsupported: not an .X360 file"
    return "unsupported: no lpsMelodyMarker records found"


def format_debug(debug_info: DebugInfo, zero_only: bool = False) -> list[str]:
    if zero_only:
        return []
    lines = ["  debug:"]
    lines.append(f"    role: {debug_info.role}")
    lines.append(f"    schema_found: {debug_info.schema_found}")
    if debug_info.melody_class:
        cls = debug_info.melody_class
        lines.append(f"    melody_class: index={cls.index}, size={cls.size}, base={cls.base}")
    else:
        lines.append("    melody_class: not found")
    if debug_info.scan_counts:
        lines.append(f"    scan_counts: {dict(debug_info.scan_counts)}")
    lines.append(f"    walker_steps: {debug_info.walker_steps}")
    lines.append(f"    walker_resyncs: {debug_info.walker_resyncs}")
    lines.append(f"    detection_mode: {debug_info.detection_mode}")
    if debug_info.failure_reason:
        lines.append(f"    failure_reason: {debug_info.failure_reason}")
    if debug_info.rejection_counts:
        lines.append(f"    top_rejections: {dict(debug_info.rejection_counts.most_common(8))}")
    if debug_info.kind != "plain IXB":
        lines.append("    note: non-plain IXB files are not scanned until decompressed")
    return lines


def _chart_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(item for item in path.rglob("*.X360") if item.is_file())
    return [path]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan Lips .X360 chart files for lpsMelodyMarker-like records and export CSV."
    )
    parser.add_argument("chart", type=Path, help="Input .X360 chart file or directory")
    parser.add_argument("--out", type=Path, help="Output CSV file, or output directory in batch mode")
    parser.add_argument("--debug", action="store_true", help="Print schema and rejection details for zero-marker files")
    parser.add_argument("--inspect", action="store_true", help="Print per-file scan summary instead of CSV to stdout")
    parser.add_argument("--analyze", action="store_true", help="Print compact batch analysis: family, marker count, first/last, and mode")
    return parser.parse_args(argv)


def _output_path(input_path: Path, out: Path | None, batch: bool) -> Path | None:
    if out is None:
        return None
    if batch:
        return out / f"{input_path.stem}.csv"
    return out


def _batch_summary(records: list[tuple[Path, list[MelodyMarker], str]]) -> list[str]:
    roles = Counter("lyric" if path.stem.endswith("_Lyric") else "chart" for path, _, _ in records)
    kinds = Counter(kind for _, _, kind in records)
    chart_records = [(path, markers, kind) for path, markers, kind in records if not path.stem.endswith("_Lyric")]
    modes = Counter(markers[0].source if markers else "unsupported/unknown" for _, markers, _ in chart_records)
    unsupported_charts = [path.name for path, markers, _ in chart_records if not markers]
    lines = [
        "Batch summary",
        f"  files: {len(records)}",
        f"  charts: {roles['chart']}",
        f"  lyrics: {roles['lyric']}",
        f"  plain_ixb: {kinds['plain IXB']}",
        f"  compressed_or_unknown: {sum(count for kind, count in kinds.items() if kind != 'plain IXB')}",
        f"  schema_object_walker_charts: {modes['schema/object-walker']}",
        f"  fallback_scan_charts: {modes['fallback scan']}",
        f"  unsupported_charts: {modes['unsupported/unknown']}",
    ]
    if unsupported_charts:
        lines.append(f"  unsupported_chart_files: {', '.join(unsupported_charts)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        paths = _chart_paths(args.chart)
        if not paths:
            print(f"error: no .X360 files found in {args.chart}", file=sys.stderr)
            return 1

        batch = args.chart.is_dir()
        if args.out and batch:
            args.out.mkdir(parents=True, exist_ok=True)

        batch_records: list[tuple[Path, list[MelodyMarker], str]] = []
        for path in paths:
            if args.analyze:
                print("\n".join(analyze_chart(path, debug=args.debug)))
                markers, _ = extract_melody_markers(path, debug=False)
            elif args.inspect or batch:
                lines, markers = inspect_chart(path, debug=args.debug)
                print("\n".join(lines))
            else:
                markers, debug_info = extract_melody_markers(path, debug=args.debug)

            output_path = _output_path(path, args.out, batch)
            _, kind = describe_magic(path.read_bytes())
            if batch and (args.analyze or args.inspect):
                batch_records.append((path, markers, kind))
            if output_path and markers:
                with output_path.open("w", encoding="utf-8", newline="") as handle:
                    write_csv(markers, handle)
            elif not args.inspect and not args.analyze and not batch:
                write_csv(markers, sys.stdout)
                if args.debug and debug_info:
                    print("\n".join(format_debug(debug_info)), file=sys.stderr)
        if batch_records:
            print("\n".join(_batch_summary(batch_records)))
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, ET.ParseError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
