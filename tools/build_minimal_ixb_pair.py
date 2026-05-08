#!/usr/bin/env python3
"""Build a tiny synthetic Lips IXB chart/lyric pair from scratch.

This is intentionally not a final custom-song writer. It creates the smallest
clean IXB candidate we can currently validate with the OpenLips structural
walkers: one package object, one lyric Text resource, and matching
MelodyMarker/LyricMarker/LyricWordData records.
"""

from __future__ import annotations

import argparse
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from tools.analyze_lyric_file import find_text_resources
    from tools.extract_melody_markers import _u32be, parse_ixb_document
    from tools.patch_melody_timing import _tone_octave_for_raw_pitch
except ModuleNotFoundError:
    from analyze_lyric_file import find_text_resources
    from extract_melody_markers import _u32be, parse_ixb_document
    from patch_melody_timing import _tone_octave_for_raw_pitch


PACKAGE_TREE_NODE_TAG = 0x03
PACKAGE_LIST_TAG = 0x05
CHAR_VECTOR_TAG = 0x06
PACKAGE_VECTOR_TAG = 0x07
PACKAGE_LIST_NODE_TAG = 0x08
ASSET_VECTOR_TAG = 0x09
ASSET_PACKAGE_TAG = 0x5C
ASSET_TAG = 0x34
FILE_IMAGE_TAG = 0x44
RAW_FILE_IMAGE_TAG = 0x54
WORD_DATA_TAG = 0x06
MELODY_MARKER_TAG = 0x28
LYRIC_MARKER_TAG = 0x40

TEXT_RESOURCE_HASH = 0x12345678
LYRIC_PREFIX = "\ufeff\r\n"
LYRIC_SUFFIX = "\r\n"

CHART_PACKAGE_NAME = "TinySynthetic"
LYRIC_PACKAGE_NAME = "TinySynthetic_Lyric"
LYRIC_ASSET_NAME = "TinySynthetic_Lyric"
TEXT_TYPE_NAME = "Text\0"

PACKAGE_POINTER = 0x05000000
PACKAGE_NAME_POINTER = 0x05000100
PACKAGE_LIST_POINTER = 0x05000200
PACKAGE_VECTOR_POINTER = 0x05000300
ASSET_PACKAGE_POINTER = 0x05000400
ASSET_VECTOR_POINTER = 0x05000500
ASSET_POINTER = 0x05000600
ASSET_NAME_POINTER = 0x05000700
TYPE_NAME_POINTER = 0x05000800
TEXT_PAYLOAD_POINTER = 0x05000900

SYNTHETIC_LEVELS = ("bare", "tags", "lyric-ownership", "full-current")


@dataclass(frozen=True)
class MinimalNote:
    time: float
    length: float
    raw_pitch: int
    text: str
    end_word: bool = True


@dataclass(frozen=True)
class MinimalIxbPair:
    chart_data: bytes
    lyric_data: bytes
    lyric_text: str
    notes: tuple[MinimalNote, ...]
    text_offsets: tuple[tuple[int, int], ...]
    synthetic_level: str
    chart_num_elements: int | None
    lyric_num_elements: int | None
    chart_emitted_tags: tuple[tuple[str, int], ...]
    lyric_emitted_tags: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class EmittedChunk:
    name: str
    tag: int | None
    data: bytes
    counts_as_element: bool = True

    @property
    def is_element(self) -> bool:
        return self.counts_as_element


DEFAULT_NOTES: tuple[MinimalNote, ...] = (
    MinimalNote(time=20.0, length=0.50, raw_pitch=65, text="Hi"),
    MinimalNote(time=21.0, length=0.50, raw_pitch=67, text="there"),
    MinimalNote(time=22.0, length=0.75, raw_pitch=69, text="Lips"),
)


def _ixb_open(num_elements: int | None) -> bytes:
    if num_elements is None:
        return b'<ixb IsBigEndian="true" IsText="false" Platform="WIN32">'
    return f'<ixb IsBigEndian="true" IsText="false" Platform="WIN32" NumOfElements="{num_elements}">'.encode("ascii")


BARE_CHART_CLASSES = (
    b"<Classes>"
    b'<Class Name="ixObject" Size="4"><Members></Members></Class>'
    b'<Class Name="ixReferencedObject" Base="1" Size="8"><Members>'
    b'<Member Name="m_uiReferenceCount" Offset="4"/>'
    b"</Members></Class>"
    b'<Class Name="ixSeqCode" Base="2" Size="20"><Members>'
    b'<Member Name="m_fTriggerTiming" Offset="8"/>'
    b'<Member Name="m_fLength" Offset="12"/>'
    b'<Member Name="m_iTrackIndex" Offset="16"/>'
    b"</Members></Class>"
    b'<Class Name="lpsMarker" Base="3" Size="24"><Members>'
    b'<Member Name="m_bTriggered" Offset="20"/>'
    b"</Members></Class>"
    b'<Class Name="lpsMelodyMarker" Base="4" Size="40"><Members>'
    b'<Member Name="m_Tone" Offset="24"/>'
    b'<Member Name="m_bTilt" Offset="32"/>'
    b'<Member Name="m_pLyricMarker" Offset="36"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricWordData" Size="24"><Members>'
    b'<Member Name="m_pText" Offset="0"/>'
    b'<Member Name="m_uiTextOffset" Offset="12"/>'
    b'<Member Name="m_uiTextLength" Offset="16"/>'
    b'<Member Name="m_uiFlags" Offset="20"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricMarker" Base="4" Size="64"><Members>'
    b'<Member Name="m_pMelodyMarker" Offset="24"/>'
    b'<Member Name="m_vecLyricWordData" Offset="28"/>'
    b'<Member Name="m_strFreeWord" Offset="44"/>'
    b'<Member Name="m_bEndOfWord" Offset="60"/>'
    b"</Members></Class>"
    b'<Class Name="ixPackage" Base="2" Size="72"><Members></Members></Class>'
    b"</Classes>"
)


BARE_LYRIC_CLASSES = (
    b"<Classes>"
    b'<Class Name="ixObject" Size="4"><Members></Members></Class>'
    b'<Class Name="ixReferencedObject" Base="1" Size="8"><Members>'
    b'<Member Name="m_uiReferenceCount" Offset="4"/>'
    b"</Members></Class>"
    b'<Class Name="ixPackage" Base="2" Size="72"><Members></Members></Class>'
    b"</Classes>"
)


CHART_CLASSES = (
    b"<Classes>"
    b'<Class Name="ixObject" Size="4"><Members></Members></Class>'
    b'<Class Name="ixReferencedObject" Base="1" Size="8"><Members>'
    b'<Member Name="m_uiReferenceCount" Offset="4"/>'
    b"</Members></Class>"
    b'<Class Name="ixTreeNode&lt;ixPackage&gt;" Base="2" Size="24"><Members>'
    b'<Member Name="m_pParent" Offset="8"/>'
    b'<Member Name="m_lstpChildren" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="ixPackage" Base="3" Size="72"><Members>'
    b'<Member Name="m_strName" Offset="24"/>'
    b'<Member Name="m_bIsLoaded" Offset="40"/>'
    b'<Member Name="m_uiPackedSize" Offset="44"/>'
    b'<Member Name="m_vecpLinkedPackages" Offset="52"/>'
    b"</Members></Class>"
    b'<Class Name="ixList&lt;ixPackage *,ixAllocator&lt;ixDblCnt&lt;ixPackage *&gt;,1&gt; &gt;" Size="12"><Members>'
    b'<Member Name="_root" Offset="0"/>'
    b'<Member Name="_size" Offset="4"/>'
    b'<Member Name="_allocator" Offset="8"/>'
    b"</Members></Class>"
    b'<Class Name="ixVector&lt;char,1,ixAllocator&lt;char,1&gt;,ixIterator&lt;char&gt; &gt;" Size="16"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_reserve" Offset="4"/>'
    b'<Member Name="_size" Offset="8"/>'
    b'<Member Name="_allocator" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="ixVector&lt;ixPackage *,1,ixAllocator&lt;ixPackage *,1&gt;,ixIterator&lt;ixPackage *&gt; &gt;" Size="16"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_reserve" Offset="4"/>'
    b'<Member Name="_size" Offset="8"/>'
    b'<Member Name="_allocator" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="ixDblCnt&lt;ixPackage *&gt;" Size="12"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_tail" Offset="4"/>'
    b'<Member Name="_head" Offset="8"/>'
    b"</Members></Class>"
    b'<Class Name="ixVector&lt;ixAsset *,1,ixAllocator&lt;ixAsset *,1&gt;,ixIterator&lt;ixAsset *&gt; &gt;" Size="16"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_reserve" Offset="4"/>'
    b'<Member Name="_size" Offset="8"/>'
    b'<Member Name="_allocator" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="ixAssetPackage" Base="4" Size="92"><Members>'
    b'<Member Name="m_vpAssets" Offset="72"/>'
    b"</Members></Class>"
    b'<Class Name="ixMxColor4Base&lt;unsigned char,unsigned int&gt;" Size="4"><Members></Members></Class>'
    b'<Class Name="ixMxCharColor4" Base="11" Size="4"><Members></Members></Class>'
    b'<Class Name="ixAsset" Base="2" Size="52"><Members>'
    b'<Member Name="m_strName" Offset="8"/>'
    b'<Member Name="m_pAssetPackage" Offset="24"/>'
    b'<Member Name="m_UserColor" Offset="28"/>'
    b'<Member Name="m_aHash" Offset="36"/>'
    b"</Members></Class>"
    b'<Class Name="ixFileImage" Base="13" Size="68"><Members>'
    b'<Member Name="m_vData" Offset="52"/>'
    b"</Members></Class>"
    b'<Class Name="ixRawFileImage" Base="14" Size="84"><Members>'
    b'<Member Name="m_strTypeName" Offset="68"/>'
    b"</Members></Class>"
    b'<Class Name="ixSeqCode" Base="2" Size="20"><Members>'
    b'<Member Name="m_fTriggerTiming" Offset="8"/>'
    b'<Member Name="m_fLength" Offset="12"/>'
    b'<Member Name="m_iTrackIndex" Offset="16"/>'
    b"</Members></Class>"
    b'<Class Name="lpsMarker" Base="16" Size="24"><Members>'
    b'<Member Name="m_bTriggered" Offset="20"/>'
    b"</Members></Class>"
    b'<Class Name="lpsMelodyMarker" Base="17" Size="40"><Members>'
    b'<Member Name="m_Tone" Offset="24"/>'
    b'<Member Name="m_bTilt" Offset="32"/>'
    b'<Member Name="m_pLyricMarker" Offset="36"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricWordData" Size="24"><Members>'
    b'<Member Name="m_pText" Offset="0"/>'
    b'<Member Name="m_uiTextOffset" Offset="12"/>'
    b'<Member Name="m_uiTextLength" Offset="16"/>'
    b'<Member Name="m_uiFlags" Offset="20"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricMarker" Base="17" Size="64"><Members>'
    b'<Member Name="m_pMelodyMarker" Offset="24"/>'
    b'<Member Name="m_vecLyricWordData" Offset="28"/>'
    b'<Member Name="m_strFreeWord" Offset="44"/>'
    b'<Member Name="m_bEndOfWord" Offset="60"/>'
    b"</Members></Class>"
    b"</Classes>"
)


LYRIC_CLASSES = (
    b"<Classes>"
    b'<Class Name="ixObject" Size="4"><Members></Members></Class>'
    b'<Class Name="ixReferencedObject" Base="1" Size="8"><Members>'
    b'<Member Name="m_uiReferenceCount" Offset="4"/>'
    b"</Members></Class>"
    b'<Class Name="ixTreeNode&lt;ixPackage&gt;" Base="2" Size="24"><Members>'
    b'<Member Name="m_pParent" Offset="8"/>'
    b'<Member Name="m_lstpChildren" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="ixPackage" Base="3" Size="72"><Members>'
    b'<Member Name="m_strName" Offset="24"/>'
    b'<Member Name="m_bIsLoaded" Offset="40"/>'
    b'<Member Name="m_uiPackedSize" Offset="44"/>'
    b'<Member Name="m_vecpLinkedPackages" Offset="52"/>'
    b"</Members></Class>"
    b'<Class Name="ixList&lt;ixPackage *,ixAllocator&lt;ixDblCnt&lt;ixPackage *&gt;,1&gt; &gt;" Size="12"><Members>'
    b'<Member Name="_root" Offset="0"/>'
    b'<Member Name="_size" Offset="4"/>'
    b'<Member Name="_allocator" Offset="8"/>'
    b"</Members></Class>"
    b'<Class Name="ixVector&lt;char,1,ixAllocator&lt;char,1&gt;,ixIterator&lt;char&gt; &gt;" Size="16"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_reserve" Offset="4"/>'
    b'<Member Name="_size" Offset="8"/>'
    b'<Member Name="_allocator" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="ixVector&lt;ixPackage *,1,ixAllocator&lt;ixPackage *,1&gt;,ixIterator&lt;ixPackage *&gt; &gt;" Size="16"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_reserve" Offset="4"/>'
    b'<Member Name="_size" Offset="8"/>'
    b'<Member Name="_allocator" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="ixDblCnt&lt;ixPackage *&gt;" Size="12"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_tail" Offset="4"/>'
    b'<Member Name="_head" Offset="8"/>'
    b"</Members></Class>"
    b'<Class Name="ixVector&lt;ixAsset *,1,ixAllocator&lt;ixAsset *,1&gt;,ixIterator&lt;ixAsset *&gt; &gt;" Size="16"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_reserve" Offset="4"/>'
    b'<Member Name="_size" Offset="8"/>'
    b'<Member Name="_allocator" Offset="12"/>'
    b"</Members></Class>"
    b'<Class Name="ixAssetPackage" Base="4" Size="92"><Members>'
    b'<Member Name="m_vpAssets" Offset="72"/>'
    b"</Members></Class>"
    b'<Class Name="ixMxColor4Base&lt;unsigned char,unsigned int&gt;" Size="4"><Members></Members></Class>'
    b'<Class Name="ixMxCharColor4" Base="11" Size="4"><Members></Members></Class>'
    b'<Class Name="ixAsset" Base="2" Size="52"><Members>'
    b'<Member Name="m_strName" Offset="8"/>'
    b'<Member Name="m_pAssetPackage" Offset="24"/>'
    b'<Member Name="m_UserColor" Offset="28"/>'
    b'<Member Name="m_aHash" Offset="36"/>'
    b"</Members></Class>"
    b'<Class Name="ixFileImage" Base="13" Size="68"><Members>'
    b'<Member Name="m_vData" Offset="52"/>'
    b"</Members></Class>"
    b'<Class Name="ixRawFileImage" Base="14" Size="84"><Members>'
    b'<Member Name="m_strTypeName" Offset="68"/>'
    b"</Members></Class>"
    b"</Classes>"
)


def _object(name: str, tag: int, body: bytes) -> EmittedChunk:
    if not 0 <= tag <= 0xFF:
        raise ValueError(f"object tag out of byte range: {tag}")
    return EmittedChunk(name=name, tag=tag, data=bytes([tag]) + body)


def _payload(name: str, data: bytes) -> EmittedChunk:
    return EmittedChunk(name=name, tag=None, data=data)


def _vector_body(pointer: int, reserve: int, size: int, allocator: int = 0) -> bytearray:
    body = bytearray(16)
    struct.pack_into(">IIII", body, 0, pointer, reserve, size, allocator)
    return body


def _char_vector(name: str, pointer: int, text: str) -> EmittedChunk:
    raw = text.encode("utf-8")
    body = _vector_body(pointer, len(raw), len(raw))
    return _object(name, CHAR_VECTOR_TAG, bytes(body) + raw)


def _asset_pointer_vector(pointer: int, asset_pointer: int) -> EmittedChunk:
    body = _vector_body(pointer, 1, 1)
    return _object("ixVector<ixAsset *>", ASSET_VECTOR_TAG, bytes(body) + struct.pack(">I", asset_pointer))


def _package_pointer_vector(pointer: int) -> EmittedChunk:
    body = _vector_body(pointer, 0, 0)
    return _object("ixVector<ixPackage *>", PACKAGE_VECTOR_TAG, bytes(body))


def _package_list(pointer: int) -> EmittedChunk:
    body = bytearray(12)
    struct.pack_into(">III", body, 0, pointer, 0, 0)
    return _object("ixList<ixPackage *>", PACKAGE_LIST_TAG, bytes(body))


def _package_list_node(package_pointer: int) -> EmittedChunk:
    body = bytearray(12)
    struct.pack_into(">III", body, 0, package_pointer, 0, 0)
    return _object("ixDblCnt<ixPackage *>", PACKAGE_LIST_NODE_TAG, bytes(body))


def _tree_node(package_pointer: int) -> EmittedChunk:
    body = bytearray(24)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">I", body, 8, package_pointer)
    struct.pack_into(">III", body, 12, PACKAGE_LIST_POINTER, 0, 0)
    return _object("ixTreeNode<ixPackage>", PACKAGE_TREE_NODE_TAG, bytes(body))


def _package_object(package_name: str, name_pointer: int, packed_size: int) -> EmittedChunk:
    raw_name_len = len(package_name.encode("utf-8"))
    body = bytearray(72)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 24, name_pointer, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 40, 1)
    struct.pack_into(">I", body, 44, packed_size)
    struct.pack_into(">IIII", body, 52, PACKAGE_VECTOR_POINTER, 0, 0, 0)
    return _object("ixPackage", 0x48, bytes(body))


def _bare_package_object(name: str, tag: int) -> EmittedChunk:
    body = bytearray(72)
    struct.pack_into(">I", body, 4, 1)
    return _object(name, tag, bytes(body))


def _asset_package_object(package_name: str, name_pointer: int, packed_size: int, asset_count: int) -> EmittedChunk:
    raw_name_len = len(package_name.encode("utf-8"))
    body = bytearray(92)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 24, name_pointer, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 40, 1)
    struct.pack_into(">I", body, 44, packed_size)
    struct.pack_into(">IIII", body, 52, PACKAGE_VECTOR_POINTER, 0, 0, 0)
    struct.pack_into(">IIII", body, 72, ASSET_VECTOR_POINTER, asset_count, asset_count, 0)
    return _object("ixAssetPackage", ASSET_PACKAGE_TAG, bytes(body))


def _asset_object(asset_name: str, asset_package_pointer: int) -> EmittedChunk:
    raw_name_len = len(asset_name.encode("utf-8"))
    body = bytearray(52)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 8, ASSET_NAME_POINTER, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 24, asset_package_pointer)
    struct.pack_into(">I", body, 28, 0xFFFFFFFF)
    struct.pack_into(">IIII", body, 36, TEXT_RESOURCE_HASH, 0, 0, 0)
    return _object("ixAsset", ASSET_TAG, bytes(body))


def _file_image_object(asset_name: str, asset_package_pointer: int, payload_length: int) -> EmittedChunk:
    raw_name_len = len(asset_name.encode("utf-8"))
    body = bytearray(68)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 8, ASSET_NAME_POINTER, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 24, asset_package_pointer)
    struct.pack_into(">I", body, 28, 0xFFFFFFFF)
    struct.pack_into(">IIII", body, 36, TEXT_RESOURCE_HASH, 0, 0, 0)
    struct.pack_into(">IIII", body, 52, TEXT_PAYLOAD_POINTER, payload_length, payload_length, 0)
    return _object("ixFileImage", FILE_IMAGE_TAG, bytes(body))


def _raw_file_image_object(asset_name: str, asset_package_pointer: int, payload_length: int) -> EmittedChunk:
    raw_name_len = len(asset_name.encode("utf-8"))
    type_name_len = len(TEXT_TYPE_NAME.encode("utf-8"))
    body = bytearray(84)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 8, ASSET_NAME_POINTER, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 24, asset_package_pointer)
    struct.pack_into(">I", body, 28, 0xFFFFFFFF)
    struct.pack_into(">IIII", body, 36, TEXT_RESOURCE_HASH, 0, 0, 0)
    struct.pack_into(">IIII", body, 52, TEXT_PAYLOAD_POINTER, payload_length, payload_length, 0)
    struct.pack_into(">IIII", body, 68, TYPE_NAME_POINTER, type_name_len, type_name_len, 0)
    return _object("ixRawFileImage", RAW_FILE_IMAGE_TAG, bytes(body))


def _word_data(pointer: int, text_offset: int, text_length: int) -> EmittedChunk:
    body = bytearray(24)
    struct.pack_into(">I", body, 0, pointer)
    struct.pack_into(">I", body, 4, 0x280)
    struct.pack_into(">I", body, 8, 0x188FCD00)
    struct.pack_into(">I", body, 12, text_offset)
    struct.pack_into(">I", body, 16, text_length)
    struct.pack_into(">I", body, 20, 1)
    return _object("lpsLyricWordData", WORD_DATA_TAG, bytes(body))


def _melody_marker(note: MinimalNote, melody_pointer: int, lyric_pointer: int, tag: int = MELODY_MARKER_TAG) -> EmittedChunk:
    tone, octave = _tone_octave_for_raw_pitch(note.raw_pitch)
    body = bytearray(40)
    struct.pack_into(">I", body, 4, 2)
    struct.pack_into(">f", body, 8, note.time)
    struct.pack_into(">f", body, 12, note.length)
    struct.pack_into(">I", body, 16, note.raw_pitch)
    struct.pack_into(">I", body, 20, 0)
    struct.pack_into(">f", body, 24, float(tone))
    struct.pack_into(">I", body, 28, int(octave))
    struct.pack_into(">I", body, 32, 0)
    struct.pack_into(">I", body, 36, lyric_pointer)
    return _object("lpsMelodyMarker", tag, bytes(body))


def _lyric_marker(note: MinimalNote, word_data_pointer: int, melody_pointer: int, tag: int = LYRIC_MARKER_TAG) -> EmittedChunk:
    body = bytearray(64)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">f", body, 8, note.time)
    struct.pack_into(">f", body, 12, note.length)
    struct.pack_into(">I", body, 16, note.raw_pitch)
    struct.pack_into(">I", body, 20, 0)
    struct.pack_into(">I", body, 24, melody_pointer)
    struct.pack_into(">I", body, 28, word_data_pointer)
    struct.pack_into(">I", body, 32, 0x20)
    struct.pack_into(">I", body, 36, 1)
    struct.pack_into(">I", body, 40, 0xCDCDCDCD)
    struct.pack_into(">I", body, 60, 1 if note.end_word else 0)
    return _object("lpsLyricMarker", tag, bytes(body))


def _text_resource(payload: bytes) -> EmittedChunk:
    data = b"\x00\x00\x00\x05Text\x00\x00\x00\x00" + struct.pack(">II", TEXT_RESOURCE_HASH, len(payload)) + payload
    return _payload("Text resource", data)


def _build_lyric_text(notes: Sequence[MinimalNote]) -> tuple[str, tuple[tuple[int, int], ...]]:
    text_parts = [LYRIC_PREFIX]
    offsets: list[tuple[int, int]] = []
    current_offset = len(LYRIC_PREFIX)
    for index, note in enumerate(notes):
        if index:
            separator = "\r\n" if notes[index - 1].end_word else ""
            if separator:
                text_parts.append(separator)
                current_offset += len(separator)
        offsets.append((current_offset, len(note.text)))
        text_parts.append(note.text)
        current_offset += len(note.text)
    text_parts.append(LYRIC_SUFFIX)
    return "".join(text_parts), tuple(offsets)


def _package_ownership_chunks(package_name: str, packed_size: int, *, include_asset_vector: bool) -> list[EmittedChunk]:
    chunks = [
        _char_vector("ixVector<char> package name", PACKAGE_NAME_POINTER, package_name + "\0"),
        _package_pointer_vector(PACKAGE_VECTOR_POINTER),
        _package_list(PACKAGE_LIST_POINTER),
        _tree_node(PACKAGE_POINTER),
        _package_list_node(PACKAGE_POINTER),
        _package_object(package_name, PACKAGE_NAME_POINTER, packed_size),
    ]
    if include_asset_vector:
        chunks.insert(1, _asset_pointer_vector(ASSET_VECTOR_POINTER, ASSET_POINTER))
        chunks.append(_asset_package_object(package_name, PACKAGE_NAME_POINTER, packed_size, asset_count=1))
    return chunks


def _lyric_resource_chunks(payload_length: int) -> list[EmittedChunk]:
    return [
        _char_vector("ixVector<char> asset name", ASSET_NAME_POINTER, LYRIC_ASSET_NAME + "\0"),
        _char_vector("ixVector<char> raw type name", TYPE_NAME_POINTER, TEXT_TYPE_NAME),
        _asset_object(LYRIC_ASSET_NAME, ASSET_PACKAGE_POINTER),
        _file_image_object(LYRIC_ASSET_NAME, ASSET_PACKAGE_POINTER, payload_length),
        _raw_file_image_object(LYRIC_ASSET_NAME, ASSET_PACKAGE_POINTER, payload_length),
    ]


def _join_ixb(classes: bytes, chunks: Sequence[EmittedChunk], *, include_num_elements: bool) -> tuple[bytes, int | None]:
    num_elements = sum(1 for chunk in chunks if chunk.is_element)
    declared_num_elements = num_elements if include_num_elements else None
    data = b"".join([_ixb_open(declared_num_elements), classes, b"<Objects>", *(chunk.data for chunk in chunks), b"</Objects></ixb>"])
    return data, declared_num_elements


def _tag_summary(chunks: Sequence[EmittedChunk]) -> tuple[tuple[str, int], ...]:
    return tuple((chunk.name, chunk.tag) for chunk in chunks if chunk.tag is not None)


def _level_flags(synthetic_level: str) -> tuple[bool, bool, bool, bool]:
    if synthetic_level not in SYNTHETIC_LEVELS:
        raise ValueError(f"unknown synthetic level {synthetic_level!r}; choose one of {', '.join(SYNTHETIC_LEVELS)}")
    use_real_marker_tags = synthetic_level != "bare"
    include_num_elements = synthetic_level != "bare"
    include_chart_ownership = synthetic_level == "full-current"
    include_lyric_ownership = synthetic_level in {"lyric-ownership", "full-current"}
    return use_real_marker_tags, include_num_elements, include_chart_ownership, include_lyric_ownership


def build_minimal_ixb_pair(
    notes: Sequence[MinimalNote] = DEFAULT_NOTES,
    *,
    synthetic_level: str = "full-current",
) -> MinimalIxbPair:
    if not notes:
        raise ValueError("at least one note is required")
    use_real_marker_tags, include_num_elements, include_chart_ownership, include_lyric_ownership = _level_flags(synthetic_level)
    normalized_notes = tuple(notes)
    lyric_text, text_offsets = _build_lyric_text(normalized_notes)
    lyric_payload = lyric_text.encode("utf-8")

    if include_chart_ownership:
        chart_classes = CHART_CLASSES
        chart_chunks = [
            *_package_ownership_chunks(CHART_PACKAGE_NAME, packed_size=0, include_asset_vector=True),
            _asset_object(CHART_PACKAGE_NAME, ASSET_PACKAGE_POINTER),
        ]
    else:
        chart_classes = BARE_CHART_CLASSES
        chart_chunks = [_bare_package_object("ixPackage", 0x08)]
    melody_tag = MELODY_MARKER_TAG if use_real_marker_tags else 0x05
    lyric_tag = LYRIC_MARKER_TAG if use_real_marker_tags else 0x07
    for index, note in enumerate(normalized_notes):
        word_data_pointer = 0x07160000 + index * 0x80
        melody_pointer = 0x2FA10000 + index * 0x80
        lyric_pointer = 0x2FA20000 + index * 0x80
        text_offset, text_length = text_offsets[index]
        chart_chunks.append(_word_data(word_data_pointer, text_offset, text_length))
        chart_chunks.append(_melody_marker(note, melody_pointer, lyric_pointer, tag=melody_tag))
        chart_chunks.append(_lyric_marker(note, word_data_pointer, melody_pointer, tag=lyric_tag))
    chart_data, chart_num_elements = _join_ixb(chart_classes, chart_chunks, include_num_elements=include_num_elements)

    if include_lyric_ownership:
        lyric_classes = LYRIC_CLASSES
        lyric_chunks = [
            *_package_ownership_chunks(LYRIC_PACKAGE_NAME, packed_size=len(lyric_payload), include_asset_vector=True),
            *_lyric_resource_chunks(len(lyric_payload)),
            _text_resource(lyric_payload),
        ]
    else:
        lyric_classes = BARE_LYRIC_CLASSES
        lyric_chunks = [
            _bare_package_object("ixPackage", 0x03),
            _text_resource(lyric_payload),
        ]
    lyric_data, lyric_num_elements = _join_ixb(lyric_classes, lyric_chunks, include_num_elements=include_num_elements)
    return MinimalIxbPair(
        chart_data=chart_data,
        lyric_data=lyric_data,
        lyric_text=lyric_text,
        notes=normalized_notes,
        text_offsets=text_offsets,
        synthetic_level=synthetic_level,
        chart_num_elements=chart_num_elements,
        lyric_num_elements=lyric_num_elements,
        chart_emitted_tags=_tag_summary(chart_chunks),
        lyric_emitted_tags=_tag_summary(lyric_chunks),
    )


def write_minimal_ixb_pair(
    out_dir: Path,
    stem: str,
    *,
    synthetic_level: str = "full-current",
    force: bool = False,
) -> tuple[Path, Path, MinimalIxbPair]:
    pair = build_minimal_ixb_pair(synthetic_level=synthetic_level)
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_path = out_dir / f"{stem}.X360"
    lyric_path = out_dir / f"{stem}_Lyric.X360"
    for path in (chart_path, lyric_path):
        if path.exists() and not force:
            raise FileExistsError(f"{path} already exists; pass --force to overwrite")
    chart_path.write_bytes(pair.chart_data)
    lyric_path.write_bytes(pair.lyric_data)
    return chart_path, lyric_path, pair


def _format_tag_counts(tags: Sequence[tuple[str, int]]) -> str:
    counts = Counter(tag for _, tag in tags)
    return ", ".join(f"0x{tag:02X}:{count}" for tag, count in sorted(counts.items())) or "none"


def _format_named_tags(tags: Sequence[tuple[str, int]], names: Sequence[str]) -> str:
    selected = [(name, tag) for name, tag in tags if name in names]
    return ", ".join(f"{name}=0x{tag:02X}" for name, tag in selected) or "none"


def _class_inventory(data: bytes) -> str:
    document = parse_ixb_document(data)
    names = [f"{cls.index}:{cls.name}" for cls in document.classes.values()]
    return ", ".join(names) or "none"


def _tag_count(tags: Sequence[tuple[str, int]], name: str) -> int:
    return sum(1 for tag_name, _ in tags if tag_name == name)


def _safe_u32(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    return _u32be(data, offset)


def _hex_or_none(value: int | None) -> str:
    return "n/a" if value is None else f"0x{value:08X}"


def _int_or_none(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def _ascii_preview(data: bytes, limit: int = 28) -> str:
    preview = data[:limit]
    return "".join(chr(byte) if 32 <= byte < 127 else "." for byte in preview)


def _ownership_offsets(data: bytes, tag: int, limit: int = 12) -> list[int]:
    document = parse_ixb_document(data)
    start = document.objects_start or 0
    end = document.objects_end or len(data)
    offsets: list[int] = []
    cursor = start
    while cursor < end:
        offset = data.find(bytes([tag]), cursor, end)
        if offset < 0:
            return offsets
        if _ownership_candidate_is_plausible(data, offset, tag):
            offsets.append(offset)
            if len(offsets) >= limit:
                return offsets
        cursor = offset + 1
    return offsets


def _ownership_candidate_is_plausible(data: bytes, offset: int, tag: int) -> bool:
    body = offset + 1
    if tag == CHAR_VECTOR_TAG:
        possible_offset_or_capacity = _safe_u32(data, body + 4)
        return possible_offset_or_capacity is not None and possible_offset_or_capacity <= len(data) + 0x1000
    if tag in {PACKAGE_VECTOR_TAG, ASSET_VECTOR_TAG}:
        reserve = _safe_u32(data, body + 4)
        size = _safe_u32(data, body + 8)
        return reserve is not None and size is not None and reserve <= 0x1000 and size <= 0x1000
    if tag == PACKAGE_LIST_TAG:
        size = _safe_u32(data, body + 4)
        return size is not None and size <= 0x1000
    if tag == PACKAGE_LIST_NODE_TAG:
        return _safe_u32(data, body) is not None
    if tag == PACKAGE_TREE_NODE_TAG:
        return _safe_u32(data, body + 12) is not None
    if tag in {0x48, ASSET_PACKAGE_TAG}:
        name_reserve = _safe_u32(data, body + 28)
        name_size = _safe_u32(data, body + 32)
        linked_reserve = _safe_u32(data, body + 56)
        linked_size = _safe_u32(data, body + 60)
        if None in {name_reserve, name_size, linked_reserve, linked_size}:
            return False
        if name_reserve > 0x10000 or name_size > 0x10000 or linked_reserve > 0x1000 or linked_size > 0x1000:
            return False
        if tag == ASSET_PACKAGE_TAG:
            asset_reserve = _safe_u32(data, body + 76)
            asset_size = _safe_u32(data, body + 80)
            return asset_reserve is not None and asset_size is not None and asset_reserve <= 0x1000 and asset_size <= 0x1000
        return True
    if tag in {ASSET_TAG, FILE_IMAGE_TAG, RAW_FILE_IMAGE_TAG}:
        name_reserve = _safe_u32(data, body + 12)
        name_size = _safe_u32(data, body + 16)
        if name_reserve is None or name_size is None or name_reserve > 0x10000 or name_size > 0x10000:
            return False
        if tag in {FILE_IMAGE_TAG, RAW_FILE_IMAGE_TAG}:
            data_reserve = _safe_u32(data, body + 56)
            data_size = _safe_u32(data, body + 60)
            if data_reserve is None or data_size is None or data_reserve > 0x200000 or data_size > 0x200000:
                return False
        if tag == RAW_FILE_IMAGE_TAG:
            type_reserve = _safe_u32(data, body + 72)
            type_size = _safe_u32(data, body + 76)
            if type_reserve is None or type_size is None or type_reserve > 0x10000 or type_size > 0x10000:
                return False
        return True
    return True


def _ownership_fields(data: bytes, offset: int, tag: int) -> tuple[str, list[str]]:
    body = offset + 1
    zero_pointer_fields: list[str] = []

    def field(name: str, rel: int, *, pointer_like: bool = True) -> tuple[str, int | None]:
        value = _safe_u32(data, body + rel)
        if pointer_like and value == 0:
            zero_pointer_fields.append(name)
        return name, value

    if tag == CHAR_VECTOR_TAG:
        ptr_name, ptr = field("data_ptr", 0)
        length_name, length = field("file_len_or_reserve", 4, pointer_like=False)
        vector_size_name, vector_size = field("vector_size_view", 8, pointer_like=False)
        allocator_name, allocator = field("allocator_view", 12)
        preview_start = body + 8
        preview_len = min(length or 0, 32)
        preview = _ascii_preview(data[preview_start : preview_start + preview_len])
        text = (
            f"{ptr_name}={_hex_or_none(ptr)} {length_name}={_int_or_none(length)} "
            f"{vector_size_name}={_int_or_none(vector_size)} {allocator_name}={_hex_or_none(allocator)} "
            f"inline_preview='{preview}'"
        )
        return text, zero_pointer_fields
    if tag in {PACKAGE_VECTOR_TAG, ASSET_VECTOR_TAG}:
        data_name, data_ptr = field("data_ptr", 0)
        reserve_name, reserve = field("reserve", 4, pointer_like=False)
        size_name, size = field("size", 8, pointer_like=False)
        allocator_name, allocator = field("allocator", 12)
        text = (
            f"{data_name}={_hex_or_none(data_ptr)} {reserve_name}={_int_or_none(reserve)} "
            f"{size_name}={_int_or_none(size)} {allocator_name}={_hex_or_none(allocator)}"
        )
        return text, zero_pointer_fields
    if tag == PACKAGE_LIST_TAG:
        root_name, root = field("root", 0)
        size_name, size = field("size", 4, pointer_like=False)
        allocator_name, allocator = field("allocator", 8)
        return f"{root_name}={_hex_or_none(root)} {size_name}={_int_or_none(size)} {allocator_name}={_hex_or_none(allocator)}", zero_pointer_fields
    if tag == PACKAGE_LIST_NODE_TAG:
        data_name, data_ptr = field("data", 0)
        tail_name, tail = field("tail", 4)
        head_name, head = field("head", 8)
        return f"{data_name}={_hex_or_none(data_ptr)} {tail_name}={_hex_or_none(tail)} {head_name}={_hex_or_none(head)}", zero_pointer_fields
    if tag == PACKAGE_TREE_NODE_TAG:
        parent_name, parent = field("parent", 8)
        children_name, children = field("children_list", 12)
        return f"{parent_name}={_hex_or_none(parent)} {children_name}={_hex_or_none(children)}", zero_pointer_fields
    if tag in {0x48, ASSET_PACKAGE_TAG}:
        name_name, name_ptr = field("name_ptr", 24)
        name_reserve_name, name_reserve = field("name_reserve", 28, pointer_like=False)
        name_size_name, name_size = field("name_size", 32, pointer_like=False)
        linked_name, linked = field("linked_packages_ptr", 52)
        linked_reserve_name, linked_reserve = field("linked_reserve", 56, pointer_like=False)
        linked_size_name, linked_size = field("linked_size", 60, pointer_like=False)
        text = (
            f"{name_name}={_hex_or_none(name_ptr)} {name_reserve_name}={_int_or_none(name_reserve)} "
            f"{name_size_name}={_int_or_none(name_size)} {linked_name}={_hex_or_none(linked)} "
            f"{linked_reserve_name}={_int_or_none(linked_reserve)} {linked_size_name}={_int_or_none(linked_size)}"
        )
        if tag == ASSET_PACKAGE_TAG:
            assets_name, assets = field("asset_vector_ptr", 72)
            assets_reserve_name, assets_reserve = field("asset_reserve", 76, pointer_like=False)
            assets_size_name, assets_size = field("asset_size", 80, pointer_like=False)
            text += (
                f" {assets_name}={_hex_or_none(assets)} {assets_reserve_name}={_int_or_none(assets_reserve)} "
                f"{assets_size_name}={_int_or_none(assets_size)}"
            )
        return text, zero_pointer_fields
    if tag in {ASSET_TAG, FILE_IMAGE_TAG, RAW_FILE_IMAGE_TAG}:
        name_name, name_ptr = field("name_ptr", 8)
        name_reserve_name, name_reserve = field("name_reserve", 12, pointer_like=False)
        name_size_name, name_size = field("name_size", 16, pointer_like=False)
        package_name, package = field("asset_package_ptr", 24)
        hash_name, asset_hash = field("hash", 36, pointer_like=False)
        text = (
            f"{name_name}={_hex_or_none(name_ptr)} {name_reserve_name}={_int_or_none(name_reserve)} "
            f"{name_size_name}={_int_or_none(name_size)} {package_name}={_hex_or_none(package)} "
            f"{hash_name}={_hex_or_none(asset_hash)}"
        )
        if tag in {FILE_IMAGE_TAG, RAW_FILE_IMAGE_TAG}:
            data_name, data_ptr = field("data_ptr", 52)
            data_reserve_name, data_reserve = field("data_reserve", 56, pointer_like=False)
            data_size_name, data_size = field("data_size", 60, pointer_like=False)
            text += (
                f" {data_name}={_hex_or_none(data_ptr)} {data_reserve_name}={_int_or_none(data_reserve)} "
                f"{data_size_name}={_int_or_none(data_size)}"
            )
        if tag == RAW_FILE_IMAGE_TAG:
            type_name, type_ptr = field("type_name_ptr", 68)
            type_reserve_name, type_reserve = field("type_reserve", 72, pointer_like=False)
            type_size_name, type_size = field("type_size", 76, pointer_like=False)
            text += (
                f" {type_name}={_hex_or_none(type_ptr)} {type_reserve_name}={_int_or_none(type_reserve)} "
                f"{type_size_name}={_int_or_none(type_size)}"
            )
        return text, zero_pointer_fields
    return "no ownership-field decoder", zero_pointer_fields


OWNERSHIP_SCAN_TAGS = (
    ("ixTreeNode<ixPackage>", PACKAGE_TREE_NODE_TAG),
    ("ixList<ixPackage *>", PACKAGE_LIST_TAG),
    ("ixVector<char>", CHAR_VECTOR_TAG),
    ("ixVector<ixPackage *>", PACKAGE_VECTOR_TAG),
    ("ixDblCnt<ixPackage *>", PACKAGE_LIST_NODE_TAG),
    ("ixVector<ixAsset *>", ASSET_VECTOR_TAG),
    ("ixPackage", 0x48),
    ("ixAssetPackage", ASSET_PACKAGE_TAG),
    ("ixAsset", ASSET_TAG),
    ("ixFileImage", FILE_IMAGE_TAG),
    ("ixRawFileImage", RAW_FILE_IMAGE_TAG),
)


def _format_ownership_scan(label: str, data: bytes, *, limit: int = 4) -> list[str]:
    lines = [f"  {label} ownership/vector field scan:"]
    class_names = {cls.name for cls in parse_ixb_document(data).classes.values()}
    if not any(name in class_names for name in ("ixTreeNode<ixPackage>", "ixAssetPackage", "ixRawFileImage")):
        lines.append("    skipped: rich ownership classes are not present in this variant")
        lines.append("    zero/null pointer-like fields: not scanned")
        return lines
    any_offsets = False
    zero_fields: list[str] = []
    for name, tag in OWNERSHIP_SCAN_TAGS:
        offsets = _ownership_offsets(data, tag, limit=limit)
        if not offsets:
            continue
        any_offsets = True
        lines.append(f"    {name} tag=0x{tag:02X} candidates={len(offsets)}")
        for offset in offsets[:limit]:
            fields, zeros = _ownership_fields(data, offset, tag)
            zero_fields.extend(f"{name}@0x{offset:08X}:{zero}" for zero in zeros)
            lines.append(f"      0x{offset:08X}: {fields}")
    if not any_offsets:
        lines.append("    none")
    lines.append("    zero/null pointer-like fields: " + (", ".join(zero_fields[:24]) if zero_fields else "none"))
    return lines


def _format_resource_chain(data: bytes) -> str:
    resources = find_text_resources(data)
    if not resources:
        return "no Text resources"
    return "; ".join(
        f"Text[{index}] payload=0x{resource.payload_start:08X}-0x{resource.payload_end:08X} "
        f"len={resource.payload_length} hash=0x{resource.payload_hash:08X}"
        for index, resource in enumerate(resources, start=1)
    )


def format_ownership_chain_compare(real_lyric_path: Path, synthetic_lyric_data: bytes, synthetic_label: str) -> str:
    real_data = real_lyric_path.read_bytes()
    lines = [
        "ownership-chain comparison:",
        f"  real lyric: {real_lyric_path}",
        f"  synthetic level: {synthetic_label}",
        f"  real resources: {_format_resource_chain(real_data)}",
        f"  synthetic resources: {_format_resource_chain(synthetic_lyric_data)}",
    ]
    lines.extend(_format_ownership_scan("real lyric", real_data, limit=6))
    lines.extend(_format_ownership_scan("synthetic lyric", synthetic_lyric_data, limit=6))
    return "\n".join(lines)


def _format_summary(chart_path: Path, lyric_path: Path, pair: MinimalIxbPair) -> str:
    lines = [
        "minimal IXB pair written",
        f"  synthetic_level: {pair.synthetic_level}",
        f"  chart: {chart_path}",
        f"  lyric: {lyric_path}",
        f"  chart bytes: {len(pair.chart_data)}",
        f"  lyric bytes: {len(pair.lyric_data)}",
        f"  chart NumOfElements: {pair.chart_num_elements}",
        f"  lyric NumOfElements: {pair.lyric_num_elements}",
        f"  chart emitted tags: {_format_tag_counts(pair.chart_emitted_tags)}",
        f"  lyric emitted tags: {_format_tag_counts(pair.lyric_emitted_tags)}",
        f"  chart class inventory: {_class_inventory(pair.chart_data)}",
        f"  lyric class inventory: {_class_inventory(pair.lyric_data)}",
        "  chart marker tags: "
        + _format_named_tags(pair.chart_emitted_tags, ("lpsMelodyMarker", "lpsLyricMarker", "lpsLyricWordData")),
        "  package/asset/fileimage counts: "
        f"chart ixPackage={_tag_count(pair.chart_emitted_tags, 'ixPackage')} "
        f"chart ixAssetPackage={_tag_count(pair.chart_emitted_tags, 'ixAssetPackage')} "
        f"chart ixAsset={_tag_count(pair.chart_emitted_tags, 'ixAsset')} "
        f"chart ixFileImage={_tag_count(pair.chart_emitted_tags, 'ixFileImage')} "
        f"chart ixRawFileImage={_tag_count(pair.chart_emitted_tags, 'ixRawFileImage')} "
        f"lyric ixPackage={_tag_count(pair.lyric_emitted_tags, 'ixPackage')} "
        f"lyric ixAssetPackage={_tag_count(pair.lyric_emitted_tags, 'ixAssetPackage')} "
        f"lyric ixAsset={_tag_count(pair.lyric_emitted_tags, 'ixAsset')} "
        f"lyric ixFileImage={_tag_count(pair.lyric_emitted_tags, 'ixFileImage')} "
        f"lyric ixRawFileImage={_tag_count(pair.lyric_emitted_tags, 'ixRawFileImage')}",
        f"  resource chain: {_format_resource_chain(pair.lyric_data)}",
        f"  lyric payload bytes: {len(pair.lyric_text.encode('utf-8'))}",
        "  ownership graph summary:",
    ]
    lines.extend(_format_ownership_scan("chart", pair.chart_data))
    lines.extend(_format_ownership_scan("lyric", pair.lyric_data))
    lines.append(
        "  resource chain note: ixRawFileImage should point to the Text payload only in lyric-ownership/full-current variants."
    )
    lines.append(
        f"  synthetic Text constants: type_name='{TEXT_TYPE_NAME[:-1]}' m_vData_ptr=0x{TEXT_PAYLOAD_POINTER:08X} "
        f"payload_hash=0x{TEXT_RESOURCE_HASH:08X}"
    )
    lines.append(
        "  notes:",
    )
    for index, (note, (text_offset, text_length)) in enumerate(zip(pair.notes, pair.text_offsets, strict=True), start=1):
        tone, octave = _tone_octave_for_raw_pitch(note.raw_pitch)
        lines.append(
            "    "
            f"{index}: time={note.time:.3f} length={note.length:.3f} raw_pitch={note.raw_pitch} "
            f"tone={tone:.1f} octave={octave} text_offset={text_offset} text_length={text_length} text={note.text!r}"
        )
    lines.append("  note: this is a first standalone candidate; console/game acceptance may require more package metadata.")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("private/outputs/minimal_ixb"))
    parser.add_argument("--stem", default="TinySynthetic")
    parser.add_argument(
        "--synthetic-level",
        choices=(*SYNTHETIC_LEVELS, "all"),
        default="full-current",
        help="Build one controlled synthetic variant, or all variants in per-level subdirectories.",
    )
    parser.add_argument(
        "--compare-real-lyric",
        type=Path,
        help="Print an ownership-chain tag/field comparison against a known-good real *_Lyric.X360 file.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    levels = SYNTHETIC_LEVELS if args.synthetic_level == "all" else (args.synthetic_level,)
    for level_index, level in enumerate(levels):
        target_dir = args.out_dir / level if args.synthetic_level == "all" else args.out_dir
        chart_path, lyric_path, pair = write_minimal_ixb_pair(
            target_dir,
            args.stem,
            synthetic_level=level,
            force=args.force,
        )
        if level_index:
            print()
        print(_format_summary(chart_path, lyric_path, pair))
        if args.compare_real_lyric:
            print(format_ownership_chain_compare(args.compare_real_lyric, pair.lyric_data, level))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
