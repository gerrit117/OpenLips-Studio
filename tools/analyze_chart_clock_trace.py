#!/usr/bin/env python3
"""Summarize read-only native OG ChartPlayer traces; no game files are opened."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path


def read_trace(text: str) -> list[dict[str, str]]:
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        row = dict(token.split("=", 1) for token in line.split())
        required = {"host", "phase", "object", "clock", "started"}
        if not required <= row.keys():
            raise ValueError(f"line {number}: missing {sorted(required - row.keys())}")
        for key in ("host", "clock"):
            float(row[key])
        rows.append(row)
    return rows


def summarize(rows: list[dict[str, str]]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["object"]].append(row)
    result = []
    for obj, observations in groups.items():
        starts = [r for r in observations if r["phase"] == "1"]
        start_host = float(starts[-1]["host"]) if starts else None
        updates = [r for r in observations if r["phase"] == "2"
                   and (start_host is None or float(r["host"]) >= start_host)]
        entry = {"object": obj, "start_calls": sum(r["phase"] == "0" for r in observations),
                 "start_completions": len(starts), "updates": len(updates)}
        if updates:
            first, last = updates[0], updates[-1]
            wall = float(last["host"]) - float(first["host"])
            advance = float(last["clock"]) - float(first["clock"])
            entry.update(wall_seconds=wall, clock_first=float(first["clock"]),
                         clock_last=float(last["clock"]), clock_advance=advance,
                         status=("insufficient_observation" if wall < 5 else
                                 "stalled" if abs(advance) < 0.05 else "advancing"),
                         started_values=sorted({r["started"] for r in updates}),
                         audio_states=sorted({r.get("audio_state", "unknown") for r in updates}),
                         movie_states=sorted({r.get("movie_state", "unknown") for r in updates}))
        result.append(entry)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.traces:
        print(f"file={path.name}")
        for entry in summarize(read_trace(path.read_text(encoding="utf-8"))):
            print(" ".join(f"{key}={value}" for key, value in entry.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
