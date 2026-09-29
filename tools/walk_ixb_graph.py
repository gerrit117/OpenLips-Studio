#!/usr/bin/env python3
"""Read-only, sequential IXB record and chart ownership diagnostics.

OG reader 0x82D98700 reads tag/key/length then exactly length & 0x7fffffff
bytes. The low 12 tag bits select a one-based schema class; zero is raw data.
No alignment, byte-pattern scanning, or resynchronization is performed here.
Addresses are specific to the executable documented in docs/og_ixb_reader.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from xml.etree.ElementTree import ParseError

try:
    from tools.extract_melody_markers import IxbDocument, parse_ixb_document
except ModuleNotFoundError:
    from extract_melody_markers import IxbDocument, parse_ixb_document


class GraphError(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    index: int
    offset: int
    tag: int
    key: int
    length_word: int

    @property
    def class_index(self) -> int:
        return self.tag & 0xfff

    @property
    def size(self) -> int:
        return self.length_word & 0x7fffffff

    @property
    def payload(self) -> int:
        return self.offset + 12


class Graph:
    def __init__(self, data: bytes):
        if not data.startswith(b"<ixb"):
            raise GraphError(f"unsupported magic {data[:4].hex()}: plain IXB required")
        self.data = data
        try:
            self.document: IxbDocument = parse_ixb_document(data)
        except (ValueError, ParseError) as exc:
            raise GraphError(f"invalid IXB schema/header: {exc}") from exc
        doc = self.document
        if doc.is_big_endian is not True or doc.is_text is not False:
            raise GraphError("only binary big-endian IXB is supported")
        if doc.objects_start is None:
            raise GraphError("missing Objects section")
        self.records: list[Record] = []
        self.by_key: dict[int, Record] = {}
        pos = doc.objects_start
        # A text search for </Objects> can incorrectly stop inside raw data.
        # Recognize it only at a boundary reached by consuming a whole record.
        while not data.startswith(b"</Objects>", pos):
            if len(data) - pos < 12:
                raise GraphError(f"truncated record header at 0x{pos:x}")
            tag, key, size = struct.unpack_from(">III", data, pos)
            record = Record(len(self.records), pos, tag, key, size)
            if record.class_index and record.class_index not in doc.classes:
                raise GraphError(f"unknown class {record.class_index} at 0x{pos:x}")
            if record.payload + record.size > len(data):
                raise GraphError(f"record at 0x{pos:x} exceeds file boundary")
            if key == 0 or key in self.by_key:
                raise GraphError(f"null/duplicate object key 0x{key:x} at 0x{pos:x}")
            self.records.append(record)
            self.by_key[key] = record
            pos = record.payload + record.size
        self.document = replace(doc, objects_end=pos)
        if doc.num_elements is None or len(self.records) != doc.num_elements:
            raise GraphError(f"NumOfElements mismatch: header={doc.num_elements}, walked={len(self.records)}")

    def lineage(self, record: Record):
        index = record.class_index
        seen = set()
        while index:
            if index in seen or index not in self.document.classes:
                raise GraphError(f"invalid schema inheritance at class {index}")
            seen.add(index)
            cls = self.document.classes[index]
            yield cls
            index = cls.base

    def is_a(self, record: Record, name: str) -> bool:
        return any(cls.name == name for cls in self.lineage(record))

    def members(self, record: Record) -> dict[str, int]:
        result = {}
        for cls in reversed(list(self.lineage(record))):
            result.update(cls.members)
        return result

    def u32(self, record: Record, offset: int) -> int:
        if offset < 0 or offset + 4 > record.size:
            raise GraphError(f"field +0x{offset:x} outside record 0x{record.key:x}")
        return struct.unpack_from(">I", self.data, record.payload + offset)[0]

    def ref(self, key: int) -> Record:
        try:
            return self.by_key[key]
        except KeyError:
            raise GraphError(f"unresolved serialized object key 0x{key:x}") from None

    def vector(self, record: Record, member: str, element_size: int = 4) -> tuple[dict, Record | None]:
        offset = self.members(record)[member]
        # These four offsets are checked against the embedded vector schemas.
        schemas = [c for c in self.document.classes.values() if c.name.startswith("ixVector<")]
        if not schemas or any(any(c.members.get(n) != o for n, o in
                (("_data", 0), ("_reserve", 4), ("_size", 8), ("_allocator", 12))) for c in schemas):
            raise GraphError("unsupported vector schema layout")
        key, reserve, size, allocator = (self.u32(record, offset + i * 4) for i in range(4))
        info = dict(owner_key=record.key, member=member, offset=offset, data_key=key,
                    reserve=reserve, size=size, allocator=allocator)
        if size > reserve:
            raise GraphError(f"vector size exceeds reserve: {info}")
        target = self.ref(key) if key else None
        if size and target is None:
            raise GraphError(f"nonempty vector with null data key: {info}")
        if target is not None and (target.class_index != 0 or size * element_size > target.size):
            raise GraphError(f"vector buffer type/length mismatch: {info}")
        return info, target

    def reference_vector(self, record: Record, member: str, expected: str) -> tuple[dict, list[Record]]:
        info, buffer = self.vector(record, member)
        targets = [self.ref(self.u32(buffer, i * 4)) for i in range(info["size"])]
        if any(not self.is_a(target, expected) for target in targets):
            raise GraphError(f"vector {member} contains a non-{expected} object")
        return info, targets

    def describe(self, record: Record) -> dict:
        return dict(object_index=record.index, offset=record.offset, payload_start=record.payload,
                    tag=record.tag, class_index=record.class_index, key=record.key,
                    payload_length=record.size, length_word=record.length_word,
                    class_name=next(self.lineage(record)).name if record.class_index else "<raw>")

    def melody_values(self, record: Record) -> dict:
        members = self.members(record)
        def float_field(offset: int) -> float:
            return struct.unpack(">f", struct.pack(">I", self.u32(record, offset)))[0]
        tone = members["m_Tone"]
        return dict(**self.describe(record), time=float_field(members["m_fTriggerTiming"]),
                    length=float_field(members["m_fLength"]),
                    track_index=struct.unpack(">i", struct.pack(">I", self.u32(record, members["m_iTrackIndex"])))[0],
                    tone=float_field(tone), octave=self.u32(record, tone + 4),
                    tilt=self.u32(record, members["m_bTilt"]))

    def trace(self, key: int, summary: dict) -> dict:
        record = self.ref(key)
        paths = []
        for edge in summary["vectors"]:
            if key not in edge["target_keys"]:
                continue
            owner = self.ref(edge["owner_key"])
            path = [dict(**self.describe(owner), member=edge["member"],
                         buffer_key=edge["data_key"], entry_index=edge["target_keys"].index(key)),
                    self.describe(record)]
            paths.append(path)
            for parent in summary["vectors"]:
                if owner.key in parent["target_keys"]:
                    paths.append([dict(**self.describe(self.ref(parent["owner_key"])),
                        member=parent["member"], buffer_key=parent["data_key"],
                        entry_index=parent["target_keys"].index(owner.key))] + path)
        return dict(record=self.describe(record), ownership_paths=paths)

    def summary(self) -> dict:
        inventory = Counter(next(self.lineage(r)).name if r.class_index else "<raw>" for r in self.records)
        charts = [r for r in self.records if self.is_a(r, "ixChart")]
        sequences = [r for r in self.records if self.is_a(r, "ixSequence")]
        melodies = [r for r in self.records if self.is_a(r, "lpsMelodyMarker")]
        lyrics = [r for r in self.records if self.is_a(r, "lpsLyricMarker")]
        edges, errors = [], []
        for owner, member, expected in [(r, n, "ixSequence") for r in charts
                for n in ("m_vpSequence", "m_vpExtraSequence") if n in self.members(r)] + [
                (r, "m_vpSeqCode", "ixSeqCode") for r in sequences]:
            try:
                info, targets = self.reference_vector(owner, member, expected)
                info["target_keys"] = [r.key for r in targets]
                info["target_classes"] = dict(Counter(next(self.lineage(r)).name for r in targets))
                edges.append(info)
            except (GraphError, KeyError) as exc:
                errors.append(f"0x{owner.key:x}.{member}: {exc}")
        lyric_links = 0
        null_lyric_links = []
        for lyric in lyrics:
            try:
                key = self.u32(lyric, self.members(lyric)["m_pMelodyMarker"])
                if not key:
                    null_lyric_links.append(lyric.key)
                    continue
                target = self.ref(key)
                if not self.is_a(target, "lpsMelodyMarker"):
                    raise GraphError("lyric reference is not a MelodyMarker")
                lyric_links += 1
            except (GraphError, KeyError) as exc:
                errors.append(f"lyric 0x{lyric.key:x}: {exc}")
        melody_values = sorted((self.melody_values(r) for r in melodies), key=lambda m: (m["time"], m["object_index"]))
        return dict(records=len(self.records), num_elements=self.document.num_elements,
                    classes=dict(inventory), charts=len(charts), sequences=len(sequences),
                    melodies=len(melodies), lyrics=len(lyrics), resolved_lyric_links=lyric_links,
                    null_lyric_links=null_lyric_links, vectors=edges, graph_errors=errors,
                    first_melody_by_time=melody_values[0] if melody_values else None,
                    last_melody_by_time=melody_values[-1] if melody_values else None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true", help="emit detailed JSON to stdout (no files written)")
    parser.add_argument("--trace-key", type=lambda text: int(text, 0),
                        help="show chart/sequence ownership paths to one serialized object key (single file only)")
    args = parser.parse_args()
    if args.trace_key is not None and args.path.is_dir():
        parser.error("--trace-key requires a single file")
    files = sorted(p for p in args.path.rglob("*") if p.suffix.lower() == ".x360") if args.path.is_dir() else [args.path]
    results = []
    for path in files:
        data = None
        try:
            data = path.read_bytes()
            graph = Graph(data)
            summary = graph.summary()
            result = dict(file=str(path), status="parsed", mode="sequential-schema-reader",
                          magic=data[:4].hex(),
                          sha256=hashlib.sha256(data).hexdigest(), **summary)
            if args.trace_key is not None:
                result["trace"] = graph.trace(args.trace_key, summary)
        except (ValueError, OSError, struct.error, KeyError) as exc:
            result = dict(file=str(path), status="unsupported/error", mode="unsupported/unknown",
                          magic=data[:4].hex() if data is not None else None, error=str(exc))
        results.append(result)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['file']}: {r['status']} " + (f"records={r['records']}/{r['num_elements']} "
                  f"melodies={r['melodies']} lyrics={r['lyrics']} graph_errors={len(r['graph_errors'])}"
                  if r['status'] == "parsed" else r['error']))
            for error in r.get("graph_errors", []):
                print(f"  ERROR: {error}")
            if r.get("null_lyric_links"):
                print(f"  null_lyric_melody_references={len(r['null_lyric_links'])} (reported exception)")
            if "trace" in r:
                print(json.dumps(r["trace"], indent=2))
        print(f"files={len(results)} parsed={sum(r['status'] == 'parsed' for r in results)}")
    return 0 if results and all(r["status"] == "parsed" and not r["graph_errors"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
