# OpenLips

OpenLips is an open-source reverse engineering and tooling project for the Xbox 360 karaoke game *Lips*.

The goal is to understand the internal Lips file formats and build tools for custom song creation, chart editing, lyric editing, and eventually UltraStar-to-Lips conversion.

## Project Goals

- Parse Lips `.X360` chart files
- Extract melody, pitch, timing, and lyric mapping data
- Patch existing Lips song charts safely
- Build custom song tooling
- Convert UltraStar songs to Lips-compatible DLC data

## Current Status

- IXB container format identified
- MelodyMarker / pitch structures found and verified
- LyricMarker to MelodyMarker mapping identified
- Runtime gameplay structures partially understood
- Proof-of-concept lyric text modification confirmed working
- Writer / patcher development in progress

## Repository Structure

```text
docs/       Technical format documentation and structure notes
tools/      Parsers, extractors, patchers, and converters
research/   Reverse engineering notes, experiments, and findings
samples/    Local sample files, not intended for public distribution
dumps/      RAM dumps and analysis files, not intended for public distribution
```

## Legal Notice

This repository does not include copyrighted Lips assets, official Xbox 360 SDK binaries, original DLC files, audio, video, or game content.

OpenLips is intended for research, preservation, interoperability, and personal modding/tooling purposes only.
