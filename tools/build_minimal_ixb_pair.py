#!/usr/bin/env python3
"""Build a tiny synthetic Lips IXB chart/lyric pair from scratch.

This is intentionally not a final custom-song writer. It creates the smallest
clean IXB candidate we can currently validate with the OpenLips structural
walkers: one package object, one lyric Text resource, and matching
MelodyMarker/LyricMarker/LyricWordData records.

Records use 12-byte big-endian headers and per-file schema indices. Passing
offline validation does not establish runtime/game acceptance.
"""

from __future__ import annotations

import argparse
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree as ET

try:
    from tools.analyze_lyric_file import find_text_resources
    from tools.extract_melody_markers import parse_ixb_document
    from tools.patch_melody_timing import _tone_octave_for_raw_pitch
    from tools.walk_ixb_graph import Graph, GraphError
except ModuleNotFoundError:
    from analyze_lyric_file import find_text_resources
    from extract_melody_markers import parse_ixb_document
    from patch_melody_timing import _tone_octave_for_raw_pitch
    from walk_ixb_graph import Graph, GraphError


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
CHART_POINTER = 0x05001000
CHART_SEQUENCE_VECTOR_POINTER = 0x05001100
EXTRA_SEQUENCE_VECTOR_POINTER = 0x05001200
TEMPO_MAP_POINTER = 0x05001300
MAIN_SEQUENCE_POINTER = 0x05001400
SEQ_CODE_VECTOR_POINTER = 0x05001500
LISTENER_VECTOR_POINTER = 0x05001600
MUSIC_INFO_POINTER = 0x05001700
MUSIC_INDEX_POINTER = 0x05001800

CHART_ROOT_LEVELS = (
    "chart-root-minimal",
    "chart-root-empty-sequence-vector",
    "chart-root-empty-seqcode-vector",
    "chart-root-one-seqcode",
    "chart-root-no-music-pointers",
    "chart-root-index-only",
    "chart-root-musicdata-only",
)
SYNTHETIC_LEVELS = ("bare", "tags", "lyric-ownership", "full-current", *CHART_ROOT_LEVELS)


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
    chart_emitted_offsets: tuple[tuple[str, int, int], ...] = ()
    lyric_emitted_offsets: tuple[tuple[str, int, int], ...] = ()


@dataclass(frozen=True)
class EmittedChunk:
    name: str
    tag: int | None
    data: bytes
    counts_as_element: bool = True
    key: int = 0

    @property
    def is_element(self) -> bool:
        return self.counts_as_element


@dataclass(frozen=True)
class ChartRootProfile:
    sequence_pointers: tuple[int, ...]
    seq_code_pointers: tuple[int, ...]
    index_pointer: int = MUSIC_INDEX_POINTER
    music_data_pointer: int = MUSIC_INFO_POINTER
    include_sequence_vector: bool = True
    include_seqcode_vector: bool = True
    include_music_info: bool = True
    include_music_index: bool = True


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
    b'<Class Name="lpsLyricWordData" Size="20"><Members>'
    b'<Member Name="m_uiUnknown0" Offset="0"/>'
    b'<Member Name="m_uiTextOffset" Offset="4"/>'
    b'<Member Name="m_uiTextLength" Offset="8"/>'
    b'<Member Name="m_uiUnknown12" Offset="12"/>'
    b'<Member Name="m_uiFlags" Offset="16"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricMarker" Base="4" Size="64"><Members>'
    b'<Member Name="m_pMelodyMarker" Offset="24"/>'
    b'<Member Name="m_vecLyricWordData" Offset="28"/>'
    b'<Member Name="m_strFreeWord" Offset="44"/>'
    b'<Member Name="m_bEndOfWord" Offset="60"/>'
    b"</Members></Class>"
    b'<Class Name="ixPackage" Base="2" Size="72"><Members></Members></Class>'
    b'<Class Name="ixVector&lt;lpsLyricWordData&gt;" Size="16"><Members>'
    b'<Member Name="_data" Offset="0"/>'
    b'<Member Name="_reserve" Offset="4"/>'
    b'<Member Name="_size" Offset="8"/>'
    b'<Member Name="_allocator" Offset="12"/>'
    b'</Members></Class>'
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
    b'<Class Name="lpsLyricWordData" Size="20"><Members>'
    b'<Member Name="m_uiUnknown0" Offset="0"/>'
    b'<Member Name="m_uiTextOffset" Offset="4"/>'
    b'<Member Name="m_uiTextLength" Offset="8"/>'
    b'<Member Name="m_uiUnknown12" Offset="12"/>'
    b'<Member Name="m_uiFlags" Offset="16"/>'
    b"</Members></Class>"
    b'<Class Name="lpsLyricMarker" Base="17" Size="64"><Members>'
    b'<Member Name="m_pMelodyMarker" Offset="24"/>'
    b'<Member Name="m_vecLyricWordData" Offset="28"/>'
    b'<Member Name="m_strFreeWord" Offset="44"/>'
    b'<Member Name="m_bEndOfWord" Offset="60"/>'
    b"</Members></Class>"
    b"</Classes>"
)


CHART_ROOT_CLASSES = (
    CHART_CLASSES[: -len(b"</Classes>")]
    + b'<Class Name="ixVector&lt;ixSequence *,1,ixAllocator&lt;ixSequence *,1&gt;,ixIterator&lt;ixSequence *&gt; &gt;" Size="16"><Members>'
    + b'<Member Name="_data" Offset="0"/>'
    + b'<Member Name="_reserve" Offset="4"/>'
    + b'<Member Name="_size" Offset="8"/>'
    + b'<Member Name="_allocator" Offset="12"/>'
    + b"</Members></Class>"
    + b'<Class Name="lpsMusicInfo" Base="2" Size="296"><Members>'
    + b'<Member Name="UintID" Offset="36"/>'
    + b'<Member Name="Title" Offset="40"/>'
    + b'<Member Name="Artist" Offset="56"/>'
    + b'<Member Name="Length" Offset="112"/>'
    + b'<Member Name="LyricUri" Offset="244"/>'
    + b"</Members></Class>"
    + b'<Class Name="lpsMusicIndex" Base="22" Size="608"><Members>'
    + b'<Member Name="ID" Offset="376"/>'
    + b'<Member Name="ChartUri" Offset="408"/>'
    + b'<Member Name="Source" Offset="472"/>'
    + b'<Member Name="ChartState" Offset="484"/>'
    + b"</Members></Class>"
    + b'<Class Name="ixPrototype" Base="13" Size="56"><Members></Members></Class>'
    + b'<Class Name="ixAgentPrototype" Base="24" Size="72"><Members>'
    + b'<Member Name="strStateName" Offset="56"/>'
    + b"</Members></Class>"
    + b'<Class Name="ixChart" Base="25" Size="108"><Members>'
    + b'<Member Name="m_vpSequence" Offset="72"/>'
    + b'<Member Name="m_vpExtraSequence" Offset="88"/>'
    + b'<Member Name="m_MusicStartOffset" Offset="104"/>'
    + b"</Members></Class>"
    + b'<Class Name="lpsChart" Base="26" Size="184"><Members>'
    + b'<Member Name="m_strNoiseMaker" Offset="108"/>'
    + b'<Member Name="m_strNoiseMakerForLS2" Offset="124"/>'
    + b'<Member Name="m_BaseCentOffset" Offset="140"/>'
    + b'<Member Name="m_pIndex" Offset="144"/>'
    + b'<Member Name="m_pMusicData" Offset="148"/>'
    + b'<Member Name="m_strAudioEffectPresetPath" Offset="152"/>'
    + b'<Member Name="m_strLyricPathCash" Offset="168"/>'
    + b"</Members></Class>"
    + b'<Class Name="ixVector&lt;ixSeqCode *,1,ixAllocator&lt;ixSeqCode *,1&gt;,ixIterator&lt;ixSeqCode *&gt; &gt;" Size="16"><Members>'
    + b'<Member Name="_data" Offset="0"/>'
    + b'<Member Name="_reserve" Offset="4"/>'
    + b'<Member Name="_size" Offset="8"/>'
    + b'<Member Name="_allocator" Offset="12"/>'
    + b"</Members></Class>"
    + b'<Class Name="ixSequence" Base="25" Size="104"><Members>'
    + b'<Member Name="m_vpSeqCode" Offset="72"/>'
    + b'<Member Name="m_vpListeners" Offset="88"/>'
    + b"</Members></Class>"
    + b'<Class Name="ixTempoMap" Base="29" Size="104"><Members></Members></Class>'
    + b"</Classes>"
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


def _object(name: str, body: bytes, *, key: int = 0) -> EmittedChunk:
    # Class indices are resolved from this file's schema during framing.
    return EmittedChunk(name=name, tag=1, data=body, key=key)


def _payload(name: str, data: bytes, key: int) -> EmittedChunk:
    return EmittedChunk(name=name, tag=None, data=data, key=key)


def _char_vector(name: str, pointer: int, text: str) -> EmittedChunk:
    raw = text.encode("utf-8")
    return _payload(name, raw, pointer)


def _asset_pointer_vector(pointer: int, asset_pointer: int) -> EmittedChunk:
    return _pointer_vector("ixVector<ixAsset *>", pointer, (asset_pointer,))


def _pointer_vector(name: str, pointer: int, pointers: Sequence[int], reserve: int = 0x20) -> EmittedChunk:
    capacity = max(reserve, len(pointers)) if pointers else 0
    body = b"".join(struct.pack(">I", value) for value in pointers)
    return _payload(name, body.ljust(capacity * 4, b"\0"), pointer)


def _package_pointer_vector(pointer: int) -> EmittedChunk:
    return _payload("ixVector<ixPackage *>", b"", pointer)


def _package_list(pointer: int) -> EmittedChunk:
    body = bytearray(12)
    struct.pack_into(">III", body, 0, pointer, 0, 0)
    return _object("ixList<ixPackage *>", bytes(body))


def _package_list_node(package_pointer: int) -> EmittedChunk:
    body = bytearray(12)
    struct.pack_into(">III", body, 0, package_pointer, 0, 0)
    return _object("ixDblCnt<ixPackage *>", bytes(body))


def _tree_node(package_pointer: int) -> EmittedChunk:
    body = bytearray(24)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">I", body, 8, package_pointer)
    struct.pack_into(">III", body, 12, PACKAGE_LIST_POINTER, 0, 0)
    return _object("ixTreeNode<ixPackage>", bytes(body))


def _package_object(package_name: str, name_pointer: int, packed_size: int) -> EmittedChunk:
    raw_name_len = len(package_name.encode("utf-8")) + 1
    body = bytearray(72)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 24, name_pointer, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 40, 1)
    struct.pack_into(">I", body, 44, packed_size)
    struct.pack_into(">IIII", body, 52, PACKAGE_VECTOR_POINTER, 0, 0, 0)
    return _object("ixPackage", bytes(body))


def _bare_package_object(name: str) -> EmittedChunk:
    body = bytearray(72)
    struct.pack_into(">I", body, 4, 1)
    return _object(name, bytes(body))


def _asset_package_object(package_name: str, name_pointer: int, packed_size: int, asset_count: int) -> EmittedChunk:
    raw_name_len = len(package_name.encode("utf-8")) + 1
    body = bytearray(92)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 24, name_pointer, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 40, 1)
    struct.pack_into(">I", body, 44, packed_size)
    struct.pack_into(">IIII", body, 52, PACKAGE_VECTOR_POINTER, 0, 0, 0)
    asset_reserve = 0x20 if asset_count else 0
    struct.pack_into(">IIII", body, 72, ASSET_VECTOR_POINTER, asset_reserve, asset_count, 0)
    return _object("ixAssetPackage", bytes(body))


def _asset_object(asset_name: str, asset_package_pointer: int, *, name_pointer: int = ASSET_NAME_POINTER) -> EmittedChunk:
    raw_name_len = len(asset_name.encode("utf-8")) + 1
    body = bytearray(52)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 8, name_pointer, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 24, asset_package_pointer)
    struct.pack_into(">I", body, 28, 0xFFFFFFFF)
    struct.pack_into(">IIII", body, 36, TEXT_RESOURCE_HASH, 0, 0, 0)
    return _object("ixAsset", bytes(body))


def _file_image_object(asset_name: str, asset_package_pointer: int, payload_length: int) -> EmittedChunk:
    raw_name_len = len(asset_name.encode("utf-8")) + 1
    body = bytearray(68)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 8, ASSET_NAME_POINTER, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 24, asset_package_pointer)
    struct.pack_into(">I", body, 28, 0xFFFFFFFF)
    struct.pack_into(">IIII", body, 36, TEXT_RESOURCE_HASH, 0, 0, 0)
    struct.pack_into(">IIII", body, 52, TEXT_RESOURCE_HASH, payload_length, payload_length, 0)
    return _object("ixFileImage", bytes(body))


def _raw_file_image_object(asset_name: str, asset_package_pointer: int, payload_length: int) -> EmittedChunk:
    raw_name_len = len(asset_name.encode("utf-8")) + 1
    type_name_len = len(TEXT_TYPE_NAME.encode("utf-8"))
    body = bytearray(84)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 8, ASSET_NAME_POINTER, raw_name_len, raw_name_len, 0)
    struct.pack_into(">I", body, 24, asset_package_pointer)
    struct.pack_into(">I", body, 28, 0xFFFFFFFF)
    struct.pack_into(">IIII", body, 36, TEXT_RESOURCE_HASH, 0, 0, 0)
    struct.pack_into(">IIII", body, 52, TEXT_RESOURCE_HASH, payload_length, payload_length, 0)
    struct.pack_into(">IIII", body, 68, TYPE_NAME_POINTER, type_name_len, type_name_len, 0)
    return _object("ixRawFileImage", bytes(body))


def _music_info_object() -> EmittedChunk:
    body = bytearray(296)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">I", body, 36, 1)
    struct.pack_into(">I", body, 112, 30)
    struct.pack_into(">I", body, 116, 0xFFFFFFFF)
    return _object("lpsMusicInfo", bytes(body))


def _music_index_object() -> EmittedChunk:
    body = bytearray(608)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">I", body, 36, 1)
    struct.pack_into(">I", body, 112, 30)
    struct.pack_into(">I", body, 116, 0xFFFFFFFF)
    struct.pack_into(">I", body, 376, 1)
    struct.pack_into(">I", body, 472, 1)
    struct.pack_into(">I", body, 484, 1)
    return _object("lpsMusicIndex", bytes(body))


def _lps_chart_object(
    sequence_count: int,
    *,
    index_pointer: int = MUSIC_INDEX_POINTER,
    music_data_pointer: int = MUSIC_INFO_POINTER,
) -> EmittedChunk:
    body = bytearray(184)
    struct.pack_into(">I", body, 4, 1)
    sequence_reserve = 0x20 if sequence_count else 0
    struct.pack_into(">IIII", body, 72, CHART_SEQUENCE_VECTOR_POINTER, sequence_reserve, sequence_count, 0)
    struct.pack_into(">IIII", body, 88, 0, 0, 0, 0)
    struct.pack_into(">f", body, 104, 0.0)
    struct.pack_into(">f", body, 140, 0.0)
    struct.pack_into(">I", body, 144, index_pointer)
    struct.pack_into(">I", body, 148, music_data_pointer)
    return _object("lpsChart", bytes(body))


def _ix_tempo_map_object() -> EmittedChunk:
    body = bytearray(104)
    struct.pack_into(">I", body, 4, 1)
    struct.pack_into(">IIII", body, 72, 0, 0, 0, 0)
    struct.pack_into(">IIII", body, 88, 0, 0, 0, 0)
    return _object("ixTempoMap", bytes(body))


def _ix_sequence_object(seq_code_count: int) -> EmittedChunk:
    body = bytearray(104)
    struct.pack_into(">I", body, 4, 1)
    seq_code_reserve = max(0x20, seq_code_count) if seq_code_count else 0
    struct.pack_into(">IIII", body, 72, SEQ_CODE_VECTOR_POINTER, seq_code_reserve, seq_code_count, 0)
    struct.pack_into(">IIII", body, 88, 0, 0, 0, 0)
    return _object("ixSequence", bytes(body))


def _word_data(pointer: int, text_offset: int, text_length: int) -> EmittedChunk:
    # Real buffers have reserve * 20 bytes; offset/length are element +4/+8.
    body = bytearray(0x20 * 20)
    struct.pack_into(">IIIII", body, 0, 0, text_offset, text_length, 0, 1)
    return _payload("lpsLyricWordData", bytes(body), pointer)


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
    return _object("lpsMelodyMarker", bytes(body), key=melody_pointer)


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
    return _object("lpsLyricMarker", bytes(body), key=melody_pointer + 0x10000)


def _text_resource(payload: bytes) -> list[EmittedChunk]:
    return [
        _payload("ixVector<char> type name", TEXT_TYPE_NAME.encode("utf-8"), TYPE_NAME_POINTER),
        _payload("Text resource", payload, TEXT_RESOURCE_HASH),
    ]


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
        _asset_object(LYRIC_ASSET_NAME, ASSET_PACKAGE_POINTER),
        _file_image_object(LYRIC_ASSET_NAME, ASSET_PACKAGE_POINTER, payload_length),
        _raw_file_image_object(LYRIC_ASSET_NAME, ASSET_PACKAGE_POINTER, payload_length),
    ]


def _chart_root_profile(synthetic_level: str, seq_code_pointers: Sequence[int]) -> ChartRootProfile:
    full_seq_codes = tuple(seq_code_pointers)
    one_seq_code = full_seq_codes[:1]
    if synthetic_level == "chart-root-empty-sequence-vector":
        return ChartRootProfile(sequence_pointers=(), seq_code_pointers=(), include_seqcode_vector=False)
    if synthetic_level == "chart-root-empty-seqcode-vector":
        return ChartRootProfile(sequence_pointers=(MAIN_SEQUENCE_POINTER,), seq_code_pointers=())
    if synthetic_level == "chart-root-one-seqcode":
        return ChartRootProfile(sequence_pointers=(MAIN_SEQUENCE_POINTER,), seq_code_pointers=one_seq_code)
    if synthetic_level == "chart-root-no-music-pointers":
        return ChartRootProfile(
            sequence_pointers=(TEMPO_MAP_POINTER, MAIN_SEQUENCE_POINTER),
            seq_code_pointers=full_seq_codes,
            index_pointer=0,
            music_data_pointer=0,
        )
    if synthetic_level == "chart-root-index-only":
        return ChartRootProfile(
            sequence_pointers=(TEMPO_MAP_POINTER, MAIN_SEQUENCE_POINTER),
            seq_code_pointers=full_seq_codes,
            index_pointer=MUSIC_INDEX_POINTER,
            music_data_pointer=0,
        )
    if synthetic_level == "chart-root-musicdata-only":
        return ChartRootProfile(
            sequence_pointers=(TEMPO_MAP_POINTER, MAIN_SEQUENCE_POINTER),
            seq_code_pointers=full_seq_codes,
            index_pointer=0,
            music_data_pointer=MUSIC_INFO_POINTER,
        )
    return ChartRootProfile(
        sequence_pointers=(TEMPO_MAP_POINTER, MAIN_SEQUENCE_POINTER),
        seq_code_pointers=full_seq_codes,
        index_pointer=MUSIC_INDEX_POINTER,
        music_data_pointer=MUSIC_INFO_POINTER,
    )


def _chart_root_chunks(profile: ChartRootProfile) -> list[EmittedChunk]:
    chunks: list[EmittedChunk] = []
    if profile.include_sequence_vector:
        chunks.append(
            _pointer_vector(
                "ixVector<ixSequence *> chart sequences",
                CHART_SEQUENCE_VECTOR_POINTER,
                profile.sequence_pointers,
            )
        )
    if profile.include_seqcode_vector:
        chunks.append(
            _pointer_vector(
                "ixVector<ixSeqCode *> main sequence codes",
                SEQ_CODE_VECTOR_POINTER,
                profile.seq_code_pointers,
            )
        )
    if profile.include_music_info:
        chunks.append(_music_info_object())
    if profile.include_music_index:
        chunks.append(_music_index_object())
    chunks.append(
        _lps_chart_object(
            len(profile.sequence_pointers),
            index_pointer=profile.index_pointer,
            music_data_pointer=profile.music_data_pointer,
        )
    )
    if TEMPO_MAP_POINTER in profile.sequence_pointers:
        chunks.append(_ix_tempo_map_object())
    if MAIN_SEQUENCE_POINTER in profile.sequence_pointers:
        chunks.append(_ix_sequence_object(len(profile.seq_code_pointers)))
    return chunks


OBJECT_KEYS = {
    "ixTreeNode<ixPackage>": 0x05002000,
    "ixList<ixPackage *>": PACKAGE_LIST_POINTER,
    "ixDblCnt<ixPackage *>": 0x05002100,
    "ixPackage": PACKAGE_POINTER,
    "ixAssetPackage": ASSET_PACKAGE_POINTER,
    "ixAsset": ASSET_POINTER,
    "ixFileImage": 0x05002200,
    "ixRawFileImage": 0x05002300,
    "lpsChart": CHART_POINTER,
    "ixSequence": MAIN_SEQUENCE_POINTER,
    "ixTempoMap": TEMPO_MAP_POINTER,
    "lpsMusicInfo": MUSIC_INFO_POINTER,
    "lpsMusicIndex": MUSIC_INDEX_POINTER,
}


def _frame_chunks(classes: bytes, chunks: Sequence[EmittedChunk]) -> list[EmittedChunk]:
    schema = list(ET.fromstring(classes))
    framed = []
    keys = set()
    for chunk in chunks:
        key = chunk.key or OBJECT_KEYS[chunk.name]
        if not key or key in keys:
            raise ValueError(f"null/duplicate emitted key 0x{key:x}")
        keys.add(key)
        if chunk.tag is None:
            tag = 0
        else:
            matches = [(index, cls) for index, cls in enumerate(schema, 1)
                       if cls.attrib["Name"] == chunk.name
                       or cls.attrib["Name"].startswith(chunk.name[:-1] + ",")]
            if len(matches) != 1:
                raise ValueError(f"cannot resolve schema class for {chunk.name}")
            tag, cls = matches[0]
            if len(chunk.data) != int(cls.attrib["Size"]):
                raise ValueError(f"payload/schema size mismatch for {chunk.name}")
        header = struct.pack(">III", tag, key, len(chunk.data))
        framed.append(EmittedChunk(chunk.name, tag, header + chunk.data, key=key))
    return framed


def _validate_pair(chart_data: bytes, lyric_data: bytes, expected_notes: Sequence[MinimalNote]) -> None:
    chart, lyric = Graph(chart_data), Graph(lyric_data)
    for graph in (chart, lyric):
        errors = graph.summary()["graph_errors"]
        if errors:
            raise GraphError("generated graph failed validation: " + "; ".join(errors))
        for record in graph.records:
            if not record.class_index:
                continue
            for member in ("m_strName", "m_strTypeName", "m_vecpLinkedPackages", "m_vData", "m_vpAssets"):
                if member in graph.members(record):
                    element_size = 4 if member in ("m_vecpLinkedPackages", "m_vpAssets") else 1
                    info, buffer = graph.vector(record, member, element_size)
                    if buffer and buffer.size != info["reserve"] * element_size:
                        raise GraphError(f"reserve buffer length mismatch for {member}")
                    if member == "m_vpAssets":
                        graph.reference_vector(record, member, "ixAsset")
            if graph.is_a(record, "ixAsset"):
                package = graph.u32(record, graph.members(record)["m_pAssetPackage"])
                if package and not graph.is_a(graph.ref(package), "ixAssetPackage"):
                    raise GraphError("asset references a non-package object")
            if graph.is_a(record, "lpsMelodyMarker"):
                target = graph.ref(graph.u32(record, graph.members(record)["m_pLyricMarker"]))
                if not graph.is_a(target, "lpsLyricMarker"):
                    raise GraphError("melody references a non-lyric object")
    payload = lyric.ref(TEXT_RESOURCE_HASH)
    text = lyric_data[payload.payload:payload.payload + payload.size].decode("utf-8")
    markers = [r for r in chart.records if chart.is_a(r, "lpsLyricMarker")]
    if len(markers) != len(expected_notes):
        raise GraphError("lyric count does not match input notes")
    for marker, note in zip(markers, expected_notes, strict=True):
        info, buffer = chart.vector(marker, "m_vecLyricWordData", 20)
        if buffer is None or info["size"] != 1 or buffer.size != info["reserve"] * 20:
            raise GraphError("invalid WordData reserve/size/buffer")
        offset, length = chart.u32(buffer, 4), chart.u32(buffer, 8)
        if offset + length > len(text) or text[offset:offset + length] != note.text:
            raise GraphError("WordData fragment does not match generated lyric text")


def _join_ixb(classes: bytes, chunks: Sequence[EmittedChunk], *, include_num_elements: bool) -> tuple[bytes, int | None]:
    num_elements = sum(1 for chunk in chunks if chunk.is_element)
    declared_num_elements = num_elements if include_num_elements else None
    data = b"".join([_ixb_open(declared_num_elements), classes, b"<Objects>", *(chunk.data for chunk in chunks), b"</Objects></ixb>"])
    return data, declared_num_elements


def _chunk_offsets(
    classes: bytes,
    chunks: Sequence[EmittedChunk],
    *,
    include_num_elements: bool,
) -> tuple[tuple[str, int, int], ...]:
    num_elements = sum(1 for chunk in chunks if chunk.is_element)
    declared_num_elements = num_elements if include_num_elements else None
    cursor = len(_ixb_open(declared_num_elements)) + len(classes) + len(b"<Objects>")
    offsets: list[tuple[str, int, int]] = []
    for chunk in chunks:
        if chunk.tag is not None:
            offsets.append((chunk.name, chunk.tag, cursor))
        cursor += len(chunk.data)
    return tuple(offsets)


def _tag_summary(chunks: Sequence[EmittedChunk]) -> tuple[tuple[str, int], ...]:
    return tuple((chunk.name, chunk.tag) for chunk in chunks if chunk.tag is not None)


def _level_flags(synthetic_level: str) -> tuple[bool, bool, bool, bool]:
    if synthetic_level not in SYNTHETIC_LEVELS:
        raise ValueError(f"unknown synthetic level {synthetic_level!r}; choose one of {', '.join(SYNTHETIC_LEVELS)}")
    # Even the bare ownership variant needs the reader's element count.
    include_num_elements = True
    include_chart_root = synthetic_level in CHART_ROOT_LEVELS
    include_chart_ownership = synthetic_level == "full-current" or include_chart_root
    include_lyric_ownership = synthetic_level in {"lyric-ownership", "full-current"} or include_chart_root
    return include_num_elements, include_chart_ownership, include_lyric_ownership, include_chart_root


def build_minimal_ixb_pair(
    notes: Sequence[MinimalNote] = DEFAULT_NOTES,
    *,
    synthetic_level: str = "full-current",
) -> MinimalIxbPair:
    if not notes:
        raise ValueError("at least one note is required")
    (
        include_num_elements,
        include_chart_ownership,
        include_lyric_ownership,
        include_chart_root,
    ) = _level_flags(synthetic_level)
    normalized_notes = tuple(notes)
    lyric_text, text_offsets = _build_lyric_text(normalized_notes)
    lyric_payload = lyric_text.encode("utf-8")
    marker_pointers = tuple(
        (
            0x07160000 + index * 0x80,
            0x2FA10000 + index * 0x80,
            0x2FA20000 + index * 0x80,
        )
        for index, _note in enumerate(normalized_notes)
    )
    seq_code_pointers = tuple(pointer for _word_pointer, melody_pointer, lyric_pointer in marker_pointers for pointer in (melody_pointer, lyric_pointer))

    if include_chart_ownership:
        chart_classes = CHART_ROOT_CLASSES if include_chart_root else CHART_CLASSES
        chart_chunks = [
            *_package_ownership_chunks(CHART_PACKAGE_NAME, packed_size=0, include_asset_vector=True),
            _asset_object(CHART_PACKAGE_NAME, ASSET_PACKAGE_POINTER, name_pointer=PACKAGE_NAME_POINTER),
        ]
        if include_chart_root:
            chart_chunks.extend(_chart_root_chunks(_chart_root_profile(synthetic_level, seq_code_pointers)))
    else:
        chart_classes = BARE_CHART_CLASSES
        chart_chunks = [_bare_package_object("ixPackage")]
    for index, note in enumerate(normalized_notes):
        word_data_pointer, melody_pointer, lyric_pointer = marker_pointers[index]
        text_offset, text_length = text_offsets[index]
        chart_chunks.append(_word_data(word_data_pointer, text_offset, text_length))
        chart_chunks.append(_melody_marker(note, melody_pointer, lyric_pointer))
        chart_chunks.append(_lyric_marker(note, word_data_pointer, melody_pointer))
    chart_chunks = _frame_chunks(chart_classes, chart_chunks)
    chart_data, chart_num_elements = _join_ixb(chart_classes, chart_chunks, include_num_elements=include_num_elements)

    if include_lyric_ownership:
        lyric_classes = LYRIC_CLASSES
        lyric_chunks = [
            *_package_ownership_chunks(LYRIC_PACKAGE_NAME, packed_size=len(lyric_payload), include_asset_vector=True),
            *_lyric_resource_chunks(len(lyric_payload)),
            *_text_resource(lyric_payload),
        ]
    else:
        lyric_classes = BARE_LYRIC_CLASSES
        lyric_chunks = [
            _bare_package_object("ixPackage"),
            *_text_resource(lyric_payload),
        ]
    lyric_chunks = _frame_chunks(lyric_classes, lyric_chunks)
    lyric_data, lyric_num_elements = _join_ixb(lyric_classes, lyric_chunks, include_num_elements=include_num_elements)
    _validate_pair(chart_data, lyric_data, normalized_notes)
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
        chart_emitted_offsets=_chunk_offsets(chart_classes, chart_chunks, include_num_elements=include_num_elements),
        lyric_emitted_offsets=_chunk_offsets(lyric_classes, lyric_chunks, include_num_elements=include_num_elements),
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


def _format_ownership_scan(label: str, data: bytes, *, limit: int = 4) -> list[str]:
    graph = Graph(data)
    lines = [f"  {label} ownership/vector fields (sequential schema reader):"]
    counts = Counter()
    ownership = {"ixPackage", "ixAssetPackage", "ixAsset", "ixFileImage",
                 "ixRawFileImage", "ixTreeNode<ixPackage>"}
    for record in graph.records:
        if not record.class_index:
            continue
        cls = next(graph.lineage(record))
        if cls.name not in ownership and not cls.name.startswith(("ixList<", "ixDblCnt<")):
            continue
        counts[cls.name] += 1
        if counts[cls.name] > limit:
            continue
        lines.append(f"    {cls.name} tag=0x{record.tag:X} key=0x{record.key:08X} "
                     f"header=0x{record.offset:08X} payload=0x{record.payload:08X}")
        for name, offset in sorted(graph.members(record).items(), key=lambda item: item[1]):
            value = graph.u32(record, offset)
            lines.append(f"      {name} +{offset}: 0x{value:08X}")
            if name in ("m_strName", "m_strTypeName", "m_vecpLinkedPackages", "m_vData", "m_vpAssets"):
                info, buffer = graph.vector(record, name, 4 if name in ("m_vecpLinkedPackages", "m_vpAssets") else 1)
                lines.append(f"        reserve={info['reserve']} size={info['size']} "
                             f"allocator=0x{info['allocator']:08X} "
                             f"raw_buffer_bytes={buffer.size if buffer else 0}")
        if graph.is_a(record, "ixFileImage"):
            ptr, reserve, size = (graph.u32(record, o) for o in (52, 56, 60))
            target = graph.by_key.get(ptr)
            lines.append(f"      data_ptr=0x{ptr:08X} data_reserve={reserve} data_size={size} "
                         f"resource_resolved={'yes' if target and target.class_index == 0 else 'no'}")
    return lines


def _format_chart_root_debug(pair: MinimalIxbPair) -> list[str]:
    graph = Graph(pair.chart_data)
    summary = graph.summary()
    lines = ["  chart root debug (sequential schema reader):"]
    for record in graph.records:
        if not graph.is_a(record, "ixChart") and not graph.is_a(record, "ixSequence"):
            continue
        lines.append(f"    {next(graph.lineage(record)).name}: "
                     f"header=0x{record.offset:08X} payload=0x{record.payload:08X} key=0x{record.key:08X}")
        for name in ("m_pIndex", "m_pMusicData"):
            if name in graph.members(record):
                value = graph.u32(record, graph.members(record)[name])
                status = "null (intentional)" if not value else (
                    next(graph.lineage(graph.ref(value))).name)
                lines.append(f"      {name}=0x{value:08X} -> {status}")
        if graph.is_a(record, "ixSequence"):
            info, _buffer = graph.vector(record, "m_vpListeners")
            lines.append(f"      m_vpListeners: key=0x{info['data_key']:08X} "
                         f"reserve={info['reserve']} size={info['size']}")
    for vector in summary["vectors"]:
        lines.append(f"    {vector['member']} owner=0x{vector['owner_key']:08X}: "
                     f"data=0x{vector['data_key']:08X} reserve={vector['reserve']} "
                     f"size={vector['size']} allocator=0x{vector['allocator']:08X}")
        lines.append("      resolved entries: " + (
            ", ".join(f"0x{key:08X}" for key in vector["target_keys"]) or "empty"))
    lines.append(f"    records={summary['records']}/{summary['num_elements']} "
                 f"melodies={summary['melodies']} lyrics={summary['lyrics']} "
                 f"resolved_lyric_links={summary['resolved_lyric_links']} "
                 f"graph_errors={len(summary['graph_errors'])}")
    lines.append("    runtime/game acceptance: NOT VERIFIED")
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
        "  serialization: 12-byte BE tag/key/length headers; schema-index tags; no record alignment",
        "  validation: sequential records/counts, references, reserve buffers and lyric fragments passed",
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
    lines.extend(_format_chart_root_debug(pair))
    lines.append(
        "  resource chain note: ownership variants reference the Text raw record by its serialized resource key."
    )
    lines.append(
        f"  synthetic Text constants: type_name='{TEXT_TYPE_NAME[:-1]}' "
        f"raw_file_image_data_ref=0x{TEXT_RESOURCE_HASH:08X} payload_hash=0x{TEXT_RESOURCE_HASH:08X} "
        f"legacy_fake_payload_ptr=0x{TEXT_PAYLOAD_POINTER:08X}"
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
