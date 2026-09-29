# OpenLips

OpenLips is a reverse-engineering and tooling project for the Xbox 360 karaoke game *Lips*.

The goal is to understand the internal Lips file formats well enough to build safe tooling for custom song creation, chart inspection, lyric editing, and eventually UltraStar-to-Lips conversion.

## Project Goals

- Parse Lips `.X360` / IXB chart and lyric files.
- Extract melody, pitch, timing, marker, and lyric mapping data.
- Compare real chart/lyric pairs against synthetic/template output.
- Build template-preserving writers before attempting any from-scratch writer.
- Validate edits with byte-identical roundtrip tests and runtime checks.
- Convert UltraStar songs to Lips-compatible content once the file model is stable.

## Current Status

- A separate strict sequential reader (`tools/walk_ixb_graph.py`) consumes 117/117 local plain IXB samples with exact boundaries and object counts, resolves chart/sequence references, and traces ownership by serialized object key. See [OG IXB reader findings](docs/og_ixb_reader.md) for live ABC validation and the record-framing defect in the current synthetic builder.

- Plain IXB `.X360` files are parsed with header attributes, class/member inventories, URI list state, object section bounds, and writer-order diagnostics.
- Lips-1 chart files can be analyzed for melody markers, lyric markers, marker counts, timing, and text mapping coverage.
- Lips-1 lyric files can be analyzed for text resources, payload lengths, hash-like fields, pointer-like references, and chart-word coverage.
- Corpus comparison has been run locally against the private Lips game corpus. Public docs contain only sanitized summaries.
- Batch no-op roundtrip succeeded for 111/111 plain IXB lyric files and 111/111 plain IXB chart files using section split/rejoin with no object reserialization.
- A first private runtime-console test package has been prepared locally for a single 4-byte ASCII lyric payload edit, with analyzer before/after reports and rollback instructions.
- Ghidra findings document the likely IXB writer order and several writer-relevant serializer strings/functions, but unresolved fields are still treated as hypotheses.

## Recommended Direction

The safe path is template-preserving editing:

1. Keep real header attributes, class/member order, URI list, object graph shape, and unknown bytes intact.
2. Make one minimal same-size payload edit at a time.
3. Compare analyzer snapshots before/after.
4. Run a controlled runtime test.
5. Only then expand the supported edit surface.

Avoid a from-scratch writer until object-record semantics, padding, payload hashes, and compressed `.X360` handling are understood.

## Repository Structure

```text
docs/       Sanitized technical findings, format notes, plans, and runtime-test summaries
tools/      Parsers, analyzers, patchers, corpus comparison, and runtime-test preparation helpers
tests/      Unit tests for supported tooling behavior
private/    Local-only copyrighted/private game corpus and generated private reports; ignored by git
```

## Important Private Data Boundary

`private/` is intentionally ignored and must stay out of GitHub. It may contain copyrighted game files, local runtime-test copies, private reports with song titles/lyrics/paths, and machine-specific analysis output.

When moving to another machine, transfer `private/` separately by a private local method, for example an encrypted archive or external drive. Do not commit or push original game files, DLC, lyrics, audio, video, or extracted copyrighted assets.

## Legal Notice

This repository does not include copyrighted Lips assets, official Xbox 360 SDK binaries, original DLC files, audio, video, or game content.

OpenLips is intended for research, preservation, interoperability, and personal modding/tooling purposes only.
