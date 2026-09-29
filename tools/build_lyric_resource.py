#!/usr/bin/env python3
"""Build a fresh IXB lyric ownership graph, tested in two OG song slots."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from tools.build_minimal_ixb_pair import (
        LYRIC_CLASSES, _frame_chunks, _join_ixb, _object, _payload,
    )
    from tools.walk_ixb_graph import Graph, GraphError
except ModuleNotFoundError:
    from build_minimal_ixb_pair import LYRIC_CLASSES, _frame_chunks, _join_ixb, _object, _payload
    from walk_ixb_graph import Graph, GraphError


ROOT = 0x05100000
ASSET_PACKAGE = 0x05100100
IMAGE = 0x05100200
NAME = 0x05100300
TYPE = 0x05100400
ASSETS = 0x05100500
EMPTY_SENTINEL = 0x05100600
ROOT_SENTINEL = 0x05100700
CHILD_NODE = 0x05100800
ROOT_NAME = 0x05100900
PACKAGE_NAME = 0x05100A00
TEXT = 0x12345678


def _schema(family: str) -> bytes:
    schema = ET.fromstring(LYRIC_CLASSES)
    if family == "og":
        for cls in schema:
            if cls.attrib["Name"] == "ixPackage":
                cls.set("Size", "52")
                members = cls.find("Members")
                for member in list(members):
                    if member.attrib["Name"] == "m_vecpLinkedPackages":
                        members.remove(member)
            elif cls.attrib["Name"] == "ixAssetPackage":
                cls.set("Size", "72")
                cls.find("Members/Member").set("Offset", "52")
    elif family != "later":
        raise ValueError("family must be og or later")
    return ET.tostring(schema, encoding="ascii", short_empty_elements=False)


def _package(name_key: int, name_length: int, parent: int, sentinel: int, count: int, *, family: str, assets: bool):
    base_size = 52 if family == "og" else 72
    body = bytearray(base_size + (20 if assets else 0))
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 8, parent, sentinel, count, 0)
    struct.pack_into(">IIII", body, 24, name_key, name_length, name_length, 0)
    struct.pack_into(">I", body, 40, 1)
    if assets:
        struct.pack_into(">IIII", body, base_size, ASSETS, 32, 1, 0)
    return _object("ixAssetPackage" if assets else "ixPackage", bytes(body),
                   key=ASSET_PACKAGE if assets else ROOT)


def build_lyric_ixb(name: str, payload: bytes, *, family: str = "og") -> bytes:
    """Emit a named package -> Text asset package -> RawFileImage resource.

    Corpus invariant: 59/59 plain lyrics have exactly one most-derived image,
    two package objects and three linked-list nodes. No template heap is used.
    """
    if not name or "\0" in name:
        raise ValueError("nonempty package name without embedded nulls required")
    name_bytes = name.encode("utf-8") + b"\0"
    image = bytearray(84)
    struct.pack_into(">I", image, 4, 1)
    struct.pack_into(">IIII", image, 8, NAME, len(name_bytes), len(name_bytes), 0)
    struct.pack_into(">I", image, 24, ASSET_PACKAGE)
    struct.pack_into(">I", image, 28, 0xFF)
    struct.pack_into(">IIII", image, 52, TEXT, len(payload), len(payload), 0)
    struct.pack_into(">IIII", image, 68, TYPE, 5, 5, 0)
    chunks = [
        _payload("name buffer", name_bytes, NAME),
        _payload("type buffer", b"Text\0", TYPE),
        # Character vectors own their buffers; equal strings must not alias.
        _payload("root name buffer", name_bytes, ROOT_NAME),
        _payload("package name buffer", b"Text\0", PACKAGE_NAME),
        _payload("visible text", payload, TEXT),
        _payload("asset references", struct.pack(">I", IMAGE) + bytes(31 * 4), ASSETS),
        _object("ixRawFileImage", bytes(image), key=IMAGE),
        _object("ixDblCnt<ixPackage *>", struct.pack(">III", 0, EMPTY_SENTINEL, EMPTY_SENTINEL), key=EMPTY_SENTINEL),
        _package(PACKAGE_NAME, 5, ROOT, EMPTY_SENTINEL, 0, family=family, assets=True),
        _object("ixDblCnt<ixPackage *>", struct.pack(">III", ASSET_PACKAGE, ROOT_SENTINEL, ROOT_SENTINEL), key=CHILD_NODE),
        _object("ixDblCnt<ixPackage *>", struct.pack(">III", 0, CHILD_NODE, CHILD_NODE), key=ROOT_SENTINEL),
        _package(ROOT_NAME, len(name_bytes), 0, ROOT_SENTINEL, 1, family=family, assets=False),
    ]
    classes = _schema(family)
    data, _ = _join_ixb(classes, _frame_chunks(classes, chunks), include_num_elements=True)
    validate_lyric_ownership(data)
    return data


def validate_lyric_ownership(data: bytes) -> dict:
    graph = Graph(data)
    image = graph.ref(IMAGE)
    root, package = graph.ref(ROOT), graph.ref(ASSET_PACKAGE)
    name_keys = [graph.u32(owner, graph.members(owner)[member]) for owner, member in
                 ((image, "m_strName"), (image, "m_strTypeName"),
                  (root, "m_strName"), (package, "m_strName"))]
    if len(set(name_keys)) != 4 or 0 in name_keys:
        raise GraphError("owning character vectors share/null their name buffers")
    _info, assets = graph.reference_vector(package, "m_vpAssets", "ixAsset")
    if [record.key for record in assets] != [IMAGE]:
        raise GraphError("Text package does not own the image")
    if graph.u32(image, 24) != ASSET_PACKAGE or graph.u32(package, 8) != ROOT:
        raise GraphError("ownership parent/back-reference mismatch")
    for owner, sentinel, count in ((root, ROOT_SENTINEL, 1), (package, EMPTY_SENTINEL, 0)):
        if graph.u32(owner, 12) != sentinel or graph.u32(owner, 16) != count:
            raise GraphError("package list header mismatch")
    if tuple(graph.u32(graph.ref(EMPTY_SENTINEL), i) for i in (0, 4, 8)) != (0, EMPTY_SENTINEL, EMPTY_SENTINEL):
        raise GraphError("invalid empty-list sentinel")
    if tuple(graph.u32(graph.ref(ROOT_SENTINEL), i) for i in (0, 4, 8)) != (0, CHILD_NODE, CHILD_NODE):
        raise GraphError("invalid root-list sentinel")
    if tuple(graph.u32(graph.ref(CHILD_NODE), i) for i in (0, 4, 8)) != (ASSET_PACKAGE, ROOT_SENTINEL, ROOT_SENTINEL):
        raise GraphError("invalid child-list links")
    for member in ("m_strName", "m_strTypeName", "m_vData"):
        info, buffer = graph.vector(image, member, 1)
        if buffer is None or buffer.size != info["reserve"] or info["size"] != info["reserve"]:
            raise GraphError("invalid image raw buffer")
    return graph.summary()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--payload-file", type=Path, required=True)
    parser.add_argument("--family", choices=("og", "later"), default="og")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = build_lyric_ixb(args.name, args.payload_file.read_bytes(), family=args.family)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("xb") as out:
        out.write(data)
    print(f"written={args.out} bytes={len(data)} records=12 family={args.family}")
    print("ownership=package -> Text asset package -> RawFileImage -> text raw record")
    print("list sentinels/references verified; OG runtime loading observed in ABC and Amazing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
