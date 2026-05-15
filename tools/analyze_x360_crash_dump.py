#!/usr/bin/env python3
"""Analyze an Xbox 360 PE/XEX memory image around a crash address.

The X360Debugger dump used during development is a PE-like PowerPC image. This
tool does not need symbols: it maps virtual addresses to image-relative offsets,
uses the `.pdata` function table for function bounds, and prints a small
PowerPC disassembly window around the IAR.
"""

from __future__ import annotations

import argparse
import bisect
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class PeSection:
    name: str
    virtual_address: int
    virtual_size: int
    raw_pointer: int
    raw_size: int
    characteristics: int

    @property
    def virtual_end(self) -> int:
        return self.virtual_address + max(self.virtual_size, self.raw_size)


@dataclass(frozen=True)
class PeImage:
    path: Path
    data: bytes
    image_base: int
    entry_rva: int
    size_of_image: int
    sections: tuple[PeSection, ...]


@dataclass(frozen=True)
class PdataEntry:
    start_va: int
    end_va: int
    info: int
    file_offset: int


def _u16le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u32be(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def parse_pe_image(path: Path) -> PeImage:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"{path} does not start with an MZ header")
    pe_offset = _u32le(data, 0x3C)
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"{path} does not contain a PE signature at e_lfanew")
    coff = pe_offset + 4
    section_count = _u16le(data, coff + 2)
    optional_header_size = _u16le(data, coff + 16)
    optional = coff + 20
    magic = _u16le(data, optional)
    if magic != 0x10B:
        raise ValueError(f"unsupported PE optional-header magic 0x{magic:04X}")
    entry_rva = _u32le(data, optional + 16)
    image_base = _u32le(data, optional + 28)
    size_of_image = _u32le(data, optional + 56)
    section_table = optional + optional_header_size
    sections: list[PeSection] = []
    for index in range(section_count):
        offset = section_table + index * 40
        name = data[offset : offset + 8].split(b"\0")[0].decode("ascii", errors="replace")
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, offset + 8)
        characteristics = _u32le(data, offset + 36)
        sections.append(
            PeSection(
                name=name,
                virtual_address=virtual_address,
                virtual_size=virtual_size,
                raw_pointer=raw_pointer,
                raw_size=raw_size,
                characteristics=characteristics,
            )
        )
    return PeImage(
        path=path,
        data=data,
        image_base=image_base,
        entry_rva=entry_rva,
        size_of_image=size_of_image,
        sections=tuple(sections),
    )


def section_for_va(image: PeImage, address: int) -> PeSection | None:
    rva = address - image.image_base
    for section in image.sections:
        if section.virtual_address <= rva < section.virtual_end:
            return section
    return None


def flat_image_offset(image: PeImage, address: int) -> int | None:
    offset = address - image.image_base
    if 0 <= offset < len(image.data):
        return offset
    return None


def section_raw_offset(image: PeImage, address: int) -> int | None:
    section = section_for_va(image, address)
    if section is None:
        return None
    rva = address - image.image_base
    offset = section.raw_pointer + (rva - section.virtual_address)
    if 0 <= offset < len(image.data):
        return offset
    return None


def parse_pdata_entries(image: PeImage) -> list[PdataEntry]:
    pdata = next((section for section in image.sections if section.name == ".pdata"), None)
    if pdata is None:
        return []
    start = pdata.virtual_address
    end = min(len(image.data), pdata.virtual_address + pdata.virtual_size)
    raw_entries: list[tuple[int, int, int]] = []
    for offset in range(start, end - 7, 8):
        start_va = _u32be(image.data, offset)
        info = _u32be(image.data, offset + 4)
        if image.image_base <= start_va < image.image_base + image.size_of_image:
            raw_entries.append((start_va, info, offset))
    raw_entries.sort(key=lambda entry: entry[0])
    entries: list[PdataEntry] = []
    for index, (start_va, info, offset) in enumerate(raw_entries):
        end_va = raw_entries[index + 1][0] if index + 1 < len(raw_entries) else image.image_base + image.size_of_image
        entries.append(PdataEntry(start_va=start_va, end_va=end_va, info=info, file_offset=offset))
    return entries


def containing_pdata_entry(entries: Sequence[PdataEntry], address: int) -> PdataEntry | None:
    starts = [entry.start_va for entry in entries]
    index = bisect.bisect_right(starts, address) - 1
    if index < 0:
        return None
    entry = entries[index]
    if entry.start_va <= address < entry.end_va:
        return entry
    return None


def _sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def _spr_name(spr: int) -> str:
    return {1: "xer", 8: "lr", 9: "ctr"}.get(spr, str(spr))


def decode_ppc_instruction(insn: int, address: int) -> str:
    op = (insn >> 26) & 0x3F
    if insn == 0x4E800020:
        return "blr"
    if op in {14, 15}:
        rt = (insn >> 21) & 31
        ra = (insn >> 16) & 31
        imm = _sign_extend(insn & 0xFFFF, 16)
        return f"{'addi' if op == 14 else 'addis'} r{rt},r{ra},{imm}"
    if op in {32, 33, 34, 35, 36, 37, 38, 39, 40, 41}:
        names = {
            32: "lwz",
            33: "lwzu",
            34: "lbz",
            35: "lbzu",
            36: "stw",
            37: "stwu",
            38: "stb",
            39: "stbu",
            40: "lhz",
            41: "lhzu",
        }
        rt = (insn >> 21) & 31
        ra = (insn >> 16) & 31
        d = _sign_extend(insn & 0xFFFF, 16)
        return f"{names[op]} r{rt},{d}(r{ra})"
    if op in {10, 11}:
        bf = (insn >> 23) & 7
        l_bit = (insn >> 21) & 1
        ra = (insn >> 16) & 31
        value = insn & 0xFFFF
        if op == 11:
            value = _sign_extend(value, 16)
        return f"{'cmpl' if op == 10 else 'cmp'}{'d' if l_bit else 'w'}i cr{bf},r{ra},{value}"
    if op == 16:
        bo = (insn >> 21) & 31
        bi = (insn >> 16) & 31
        bd = _sign_extend(insn & 0xFFFC, 16)
        aa = (insn >> 1) & 1
        lk = insn & 1
        target = (bd if aa else address + bd) & 0xFFFFFFFF
        mnemonic = {
            (12, 2): "beq",
            (4, 2): "bne",
            (16, 0): "bdnz",
        }.get((bo, bi), f"bc bo={bo},bi={bi}")
        return f"{mnemonic} 0x{target:08X}{' lk' if lk else ''}"
    if op == 18:
        li = _sign_extend(insn & 0x03FFFFFC, 26)
        aa = (insn >> 1) & 1
        lk = insn & 1
        target = (li if aa else address + li) & 0xFFFFFFFF
        return f"b{'l' if lk else ''} 0x{target:08X}"
    if op == 19:
        xo = (insn >> 1) & 0x3FF
        if xo == 16:
            return "bclr"
        if xo == 528:
            return "bcctr"
    if op == 21:
        rs = (insn >> 21) & 31
        ra = (insn >> 16) & 31
        sh = (insn >> 11) & 31
        mb = (insn >> 6) & 31
        me = (insn >> 1) & 31
        return f"rlwinm r{ra},r{rs},{sh},{mb},{me}"
    if op == 31:
        xo = (insn >> 1) & 0x3FF
        rt = (insn >> 21) & 31
        ra = (insn >> 16) & 31
        rb = (insn >> 11) & 31
        if xo == 32:
            return f"cmplw cr0,r{ra},r{rb}"
        if xo == 40:
            return f"subf r{rt},r{ra},r{rb}"
        if xo == 266:
            return f"add r{rt},r{ra},r{rb}"
        if xo == 278:
            return f"dcbt r{ra},r{rb}"
        if xo == 246:
            return f"dcbz r{ra},r{rb}"
        if xo == 339:
            spr = ((insn >> 16) & 0x1F) | ((insn >> 6) & 0x3E0)
            return f"mf{_spr_name(spr)} r{rt}"
        if xo == 467:
            spr = ((insn >> 16) & 0x1F) | ((insn >> 6) & 0x3E0)
            return f"mt{_spr_name(spr)} r{rt}"
        return f"op31 xo={xo} r{rt},r{ra},r{rb}"
    if op == 58:
        rt = (insn >> 21) & 31
        ra = (insn >> 16) & 31
        d = _sign_extend(insn & 0xFFFC, 16)
        return f"ld r{rt},{d}(r{ra})"
    if op == 62:
        rs = (insn >> 21) & 31
        ra = (insn >> 16) & 31
        d = _sign_extend(insn & 0xFFFC, 16)
        return f"std r{rs},{d}(r{ra})"
    return f".long 0x{insn:08X}"


def disassemble_window(image: PeImage, center_address: int, before: int = 0x80, after: int = 0x80) -> list[str]:
    start = center_address - before
    end = center_address + after
    lines: list[str] = []
    for address in range(start, end + 1, 4):
        offset = flat_image_offset(image, address)
        if offset is None or offset + 4 > len(image.data):
            continue
        insn = _u32be(image.data, offset)
        marker = "  <-- IAR" if address == center_address else ""
        lines.append(f"{address:08X}: {insn:08X}  {decode_ppc_instruction(insn, address)}{marker}")
    return lines


def hexdump_address(image: PeImage, address: int, length: int = 0x100) -> list[str]:
    offset = flat_image_offset(image, address)
    if offset is None:
        return [f"address 0x{address:08X} is outside captured image range 0x{image.image_base:08X}-0x{image.image_base + len(image.data):08X}"]
    lines: list[str] = []
    for delta in range(0, length, 16):
        current = offset + delta
        chunk = image.data[current : current + 16]
        virtual = image.image_base + current
        hex_bytes = " ".join(f"{byte:02X}" for byte in chunk)
        ascii_text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{virtual:08X}: {hex_bytes:<47}  {ascii_text}")
    return lines


def format_report(image: PeImage, iar: int, stack_pointer: int | None, write_target: int | None) -> str:
    rva = iar - image.image_base
    section = section_for_va(image, iar)
    flat_offset = flat_image_offset(image, iar)
    raw_offset = section_raw_offset(image, iar)
    pdata_entries = parse_pdata_entries(image)
    function = containing_pdata_entry(pdata_entries, iar)
    lines = [
        "# X360 Crash Dump Address Report",
        "",
        f"Dump: {image.path}",
        f"Image base: 0x{image.image_base:08X}",
        f"Image size in header: 0x{image.size_of_image:X}",
        f"Captured bytes: 0x{len(image.data):X}",
        f"Entry RVA: 0x{image.entry_rva:08X}",
        "",
        "## Crash Address Mapping",
        "",
        f"IAR: 0x{iar:08X}",
        f"Module-relative offset/RVA: 0x{rva:08X}",
        f"Section: {section.name if section else 'unknown'}",
        f"Flat image offset used for memory-dump code bytes: 0x{flat_offset:08X}" if flat_offset is not None else "Flat image offset: outside dump",
        f"PE section raw offset: 0x{raw_offset:08X}" if raw_offset is not None else "PE section raw offset: unavailable",
    ]
    if function:
        lines.extend(
            [
                f"Containing `.pdata` function: 0x{function.start_va:08X}-0x{function.end_va:08X}",
                f"Function-relative offset: 0x{iar - function.start_va:X}",
                f"`.pdata` entry file offset: 0x{function.file_offset:08X}",
                f"`.pdata` unwind/info word: 0x{function.info:08X}",
            ]
        )
    if write_target is not None:
        lines.append(f"Debugger write target: 0x{write_target:08X}")
    lines.extend(["", "## Disassembly Around IAR", ""])
    lines.extend(f"    {line}" for line in disassemble_window(image, iar))
    lines.extend(["", "## Stack Window", ""])
    if stack_pointer is None:
        lines.append("No stack pointer supplied.")
    else:
        lines.append(f"GPR1/SP: 0x{stack_pointer:08X}")
        lines.extend(f"    {line}" for line in hexdump_address(image, stack_pointer, 0x100))
    return "\n".join(lines) + "\n"


def parse_int(value: str) -> int:
    return int(value, 0)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--iar", type=parse_int, required=True)
    parser.add_argument("--sp", type=parse_int)
    parser.add_argument("--write-target", type=parse_int)
    args = parser.parse_args(argv)
    image = parse_pe_image(args.dump)
    print(format_report(image, args.iar, args.sp, args.write_target), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
