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
    from tools.patch_melody_timing import _tone_octave_for_raw_pitch
except ModuleNotFoundError:
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
    chart_num_elements: int
    lyric_num_elements: int
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


def _ixb_open(num_elements: int) -> bytes:
    return f'<ixb IsBigEndian="true" IsText="false" Platform="WIN32" NumOfElements="{num_elements}">'.encode("ascii")


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


def _melody_marker(note: MinimalNote, melody_pointer: int, lyric_pointer: int) -> EmittedChunk:
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
    return _object("lpsMelodyMarker", MELODY_MARKER_TAG, bytes(body))


def _lyric_marker(note: MinimalNote, word_data_pointer: int, melody_pointer: int) -> EmittedChunk:
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
    return _object("lpsLyricMarker", LYRIC_MARKER_TAG, bytes(body))


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


def _join_ixb(classes: bytes, chunks: Sequence[EmittedChunk]) -> tuple[bytes, int]:
    num_elements = sum(1 for chunk in chunks if chunk.is_element)
    data = b"".join([_ixb_open(num_elements), classes, b"<Objects>", *(chunk.data for chunk in chunks), b"</Objects></ixb>"])
    return data, num_elements


def _tag_summary(chunks: Sequence[EmittedChunk]) -> tuple[tuple[str, int], ...]:
    return tuple((chunk.name, chunk.tag) for chunk in chunks if chunk.tag is not None)


def build_minimal_ixb_pair(notes: Sequence[MinimalNote] = DEFAULT_NOTES) -> MinimalIxbPair:
    if not notes:
        raise ValueError("at least one note is required")
    normalized_notes = tuple(notes)
    lyric_text, text_offsets = _build_lyric_text(normalized_notes)
    lyric_payload = lyric_text.encode("utf-8")

    chart_chunks = [
        *_package_ownership_chunks(CHART_PACKAGE_NAME, packed_size=0, include_asset_vector=True),
        _asset_object(CHART_PACKAGE_NAME, ASSET_PACKAGE_POINTER),
    ]
    for index, note in enumerate(normalized_notes):
        word_data_pointer = 0x07160000 + index * 0x80
        melody_pointer = 0x2FA10000 + index * 0x80
        lyric_pointer = 0x2FA20000 + index * 0x80
        text_offset, text_length = text_offsets[index]
        chart_chunks.append(_word_data(word_data_pointer, text_offset, text_length))
        chart_chunks.append(_melody_marker(note, melody_pointer, lyric_pointer))
        chart_chunks.append(_lyric_marker(note, word_data_pointer, melody_pointer))
    chart_data, chart_num_elements = _join_ixb(CHART_CLASSES, chart_chunks)

    lyric_chunks = [
        *_package_ownership_chunks(LYRIC_PACKAGE_NAME, packed_size=len(lyric_payload), include_asset_vector=True),
        *_lyric_resource_chunks(len(lyric_payload)),
        _text_resource(lyric_payload),
    ]
    lyric_data, lyric_num_elements = _join_ixb(LYRIC_CLASSES, lyric_chunks)
    return MinimalIxbPair(
        chart_data=chart_data,
        lyric_data=lyric_data,
        lyric_text=lyric_text,
        notes=normalized_notes,
        text_offsets=text_offsets,
        chart_num_elements=chart_num_elements,
        lyric_num_elements=lyric_num_elements,
        chart_emitted_tags=_tag_summary(chart_chunks),
        lyric_emitted_tags=_tag_summary(lyric_chunks),
    )


def write_minimal_ixb_pair(out_dir: Path, stem: str, *, force: bool = False) -> tuple[Path, Path, MinimalIxbPair]:
    pair = build_minimal_ixb_pair()
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


def _format_summary(chart_path: Path, lyric_path: Path, pair: MinimalIxbPair) -> str:
    lines = [
        "minimal IXB pair written",
        f"  chart: {chart_path}",
        f"  lyric: {lyric_path}",
        f"  chart bytes: {len(pair.chart_data)}",
        f"  lyric bytes: {len(pair.lyric_data)}",
        f"  chart NumOfElements: {pair.chart_num_elements}",
        f"  lyric NumOfElements: {pair.lyric_num_elements}",
        f"  chart emitted tags: {_format_tag_counts(pair.chart_emitted_tags)}",
        f"  lyric emitted tags: {_format_tag_counts(pair.lyric_emitted_tags)}",
        "  chart marker tags: "
        + _format_named_tags(pair.chart_emitted_tags, ("lpsMelodyMarker", "lpsLyricMarker", "lpsLyricWordData")),
        "  package/asset/fileimage counts: "
        f"chart ixAssetPackage={sum(1 for name, _ in pair.chart_emitted_tags if name == 'ixAssetPackage')} "
        f"chart ixAsset={sum(1 for name, _ in pair.chart_emitted_tags if name == 'ixAsset')} "
        f"lyric ixAssetPackage={sum(1 for name, _ in pair.lyric_emitted_tags if name == 'ixAssetPackage')} "
        f"lyric ixAsset={sum(1 for name, _ in pair.lyric_emitted_tags if name == 'ixAsset')} "
        f"lyric ixFileImage={sum(1 for name, _ in pair.lyric_emitted_tags if name == 'ixFileImage')} "
        f"lyric ixRawFileImage={sum(1 for name, _ in pair.lyric_emitted_tags if name == 'ixRawFileImage')}",
        "  chart objects: 1 ixPackage, 1 ixAssetPackage, 1 ixAsset, "
        f"{len(pair.notes)} lpsMelodyMarker, {len(pair.notes)} lpsLyricMarker, {len(pair.notes)} lpsLyricWordData",
        "  lyric objects: 1 ixPackage, 1 ixAssetPackage, 1 ixAsset, 1 ixFileImage, 1 ixRawFileImage, 1 Text resource",
        "  ownership graph: ixPackage -> ixAssetPackage -> ixRawFileImage",
        f"  resource chain: ixRawFileImage.m_strTypeName='{TEXT_TYPE_NAME[:-1]}' "
        f"m_vData_ptr=0x{TEXT_PAYLOAD_POINTER:08X} payload_hash=0x{TEXT_RESOURCE_HASH:08X}",
        f"  lyric payload bytes: {len(pair.lyric_text.encode('utf-8'))}",
        "  notes:",
    ]
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
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    chart_path, lyric_path, pair = write_minimal_ixb_pair(args.out_dir, args.stem, force=args.force)
    print(_format_summary(chart_path, lyric_path, pair))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
