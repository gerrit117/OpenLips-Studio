#!/usr/bin/env python3
"""Summarize Xenia log signals that matter for Lips runtime research."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


BUILD_RE = re.compile(r"Build:\s*(.+)")
TITLE_ID_RE = re.compile(r"Title ID:\s*([0-9A-Fa-f]{8})")
PE_NAME_RE = re.compile(r"XEX_HEADER_ORIGINAL_PE_NAME:\s*(.+)")
XMP_CALL_RE = re.compile(r"\b(XMP[A-Za-z0-9_]+)\(")
XMP_UNIMPLEMENTED_RE = re.compile(
    r"Unimplemented XMP message .*?msg=([0-9A-Fa-f]{8})"
)
DEVICE_CONTEXT_RE = re.compile(
    r"XamUserGetDeviceContext\(([0-9A-Fa-f]{8}),\s*"
    r"([0-9A-Fa-f]{8}),\s*([0-9A-Fa-f]{8})\(([0-9A-Fa-f]{8})\)\)"
)
MIC_REQUEST_RE = re.compile(
    r"MicDeviceRequest State:\s*([0-9A-Fa-f]{8})\s+"
    r"Action:\s*([0-9A-Fa-f]{4})\s+USER:\s*([0-9A-Fa-f]{8})"
)
CRASH_PC_RE = re.compile(r"\bPC:\s*0x([0-9A-Fa-f]+)")
REGISTER_RE = re.compile(r"\b(r(?:[12]?\d|3[01]))\s*=\s*([0-9A-Fa-f]{16})")
THREAD_NAME_RE = re.compile(r"SetThreadName\([^,]+,\s*([^\)]+)\)")
CONTENT_CALL_RE = re.compile(
    r"\b(Xam(?:Content|ShowDeviceSelector)[A-Za-z0-9_]+)\("
)


@dataclass
class Crash:
    line_number: int
    pc: str | None = None
    registers: dict[str, str] = field(default_factory=dict)


@dataclass
class LogAnalysis:
    build: str | None = None
    title_id: str | None = None
    original_pe_name: str | None = None
    line_count: int = 0
    xmp_calls: Counter[str] = field(default_factory=Counter)
    unimplemented_xmp: Counter[str] = field(default_factory=Counter)
    device_context_classes: Counter[int] = field(default_factory=Counter)
    device_context_users: Counter[int] = field(default_factory=Counter)
    mic_requests: Counter[tuple[int, int, int]] = field(default_factory=Counter)
    audio_capture_threads: Counter[str] = field(default_factory=Counter)
    content_calls: Counter[str] = field(default_factory=Counter)
    crashes: list[Crash] = field(default_factory=list)


def analyze_lines(lines: Iterable[str]) -> LogAnalysis:
    analysis = LogAnalysis()
    active_crash: Crash | None = None

    for line_number, line in enumerate(lines, 1):
        analysis.line_count = line_number

        if analysis.build is None and (match := BUILD_RE.search(line)):
            analysis.build = match.group(1).strip()
        if analysis.title_id is None and (match := TITLE_ID_RE.search(line)):
            analysis.title_id = match.group(1).upper()
        if analysis.original_pe_name is None and (match := PE_NAME_RE.search(line)):
            analysis.original_pe_name = match.group(1).strip()

        if match := XMP_CALL_RE.search(line):
            analysis.xmp_calls[match.group(1)] += 1
        if match := XMP_UNIMPLEMENTED_RE.search(line):
            analysis.unimplemented_xmp[match.group(1).upper()] += 1
        if match := DEVICE_CONTEXT_RE.search(line):
            analysis.device_context_users[int(match.group(1), 16)] += 1
            analysis.device_context_classes[int(match.group(2), 16)] += 1
        if match := MIC_REQUEST_RE.search(line):
            key = tuple(int(value, 16) for value in match.groups())
            analysis.mic_requests[key] += 1
        if match := THREAD_NAME_RE.search(line):
            name = match.group(1).strip()
            if name.startswith("AudioCapture"):
                analysis.audio_capture_threads[name] += 1
        if match := CONTENT_CALL_RE.search(line):
            analysis.content_calls[match.group(1)] += 1

        if "==== CRASH DUMP ====" in line:
            active_crash = Crash(line_number=line_number)
            analysis.crashes.append(active_crash)
            continue
        if active_crash is not None:
            if active_crash.pc is None and (match := CRASH_PC_RE.search(line)):
                active_crash.pc = f"0x{match.group(1).upper()}"
            if match := REGISTER_RE.search(line):
                active_crash.registers[match.group(1)] = f"0x{match.group(2).upper()}"

    return analysis


def analyze_log(path: Path) -> LogAnalysis:
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        return analyze_lines(stream)


def _format_counter(counter: Counter, empty: str = "none") -> str:
    if not counter:
        return empty
    return ", ".join(f"{key}={value}" for key, value in counter.most_common())


def format_report(analysis: LogAnalysis) -> str:
    lines = [
        "Xenia Lips runtime summary",
        f"build: {analysis.build or 'unknown'}",
        f"title_id: {analysis.title_id or 'unknown'}",
        f"original_pe_name: {analysis.original_pe_name or 'unknown'}",
        f"lines: {analysis.line_count}",
        f"xmp_calls: {_format_counter(analysis.xmp_calls)}",
        f"unimplemented_xmp: {_format_counter(analysis.unimplemented_xmp)}",
        "device_context_classes: "
        + _format_counter(
            Counter({f"0x{key:08X}": value for key, value in analysis.device_context_classes.items()})
        ),
        "device_context_users: "
        + _format_counter(Counter({str(key): value for key, value in analysis.device_context_users.items()})),
        f"audio_capture_threads: {_format_counter(analysis.audio_capture_threads)}",
        f"content_calls: {_format_counter(analysis.content_calls)}",
    ]

    if analysis.mic_requests:
        formatted = Counter(
            {
                f"state=0x{state:08X}/action=0x{action:04X}/user={user}": count
                for (state, action, user), count in analysis.mic_requests.items()
            }
        )
        lines.append(f"mic_requests: {_format_counter(formatted)}")
    else:
        lines.append("mic_requests: none")

    if analysis.crashes:
        for index, crash in enumerate(analysis.crashes, 1):
            registers = " ".join(
                f"{name}={value}"
                for name, value in crash.registers.items()
                if name in {"r1", "r3", "r4", "r5", "r6", "r7", "r8"}
            )
            lines.append(
                f"crash[{index}]: line={crash.line_number} pc={crash.pc or 'unknown'}"
                + (f" {registers}" if registers else "")
            )
    else:
        lines.append("crashes: none")

    observations: list[str] = []
    if analysis.unimplemented_xmp:
        observations.append(
            "This build still rejects XMP messages used during Lips startup; "
            "test a current Canary build before investigating microphone input."
        )
    if analysis.device_context_classes.get(4):
        observations.append(
            "The title is polling device class 4 (microphone); this alone does "
            "not prove that microphone support is the startup blocker."
        )
    if analysis.mic_requests:
        observations.append(
            "MicDeviceRequest is active; compare action/state counts before "
            "changing asynchronous completion behavior."
        )
    if not observations:
        observations.append("No known Lips-specific blocker was identified from these counters.")
    lines.extend(f"observation: {item}" for item in observations)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="Xenia log file to analyze")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.log.is_file():
        raise SystemExit(f"log file not found: {args.log}")
    print(format_report(analyze_log(args.log)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
