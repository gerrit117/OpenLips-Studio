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

- A new song now appears under its own title/artist and loads from independent paths with a fresh offline profile. Existing profiles do not reimport the edited disc catalog, so DLC discovery is the intended installation route, not profile resets. See [registration and timing](docs/custom_song_registration.md). A constant `--note-offset` is available for controlled synchronization tests; durations remain source-exact.

- A fresh 770-note UltraStar chart and newly encoded VC-1/WMA Pro video now play in the isolated OG test slot and reach results. A one-byte ASF bitmap-header correction reproduces acceptance; audio was user-confirmed. Synchronization and independent catalog registration remain unfinished. See [controlled media tests](docs/custom_media_runtime_tests.md).

- A fully generated OG chart/lyric pair now has measured native clock progression, and a fresh six-note chart switches lyric/note pages without instrumentation. The earlier frozen-clock diagnosis was incorrect for this tested pair. Independent media/catalog registration remains unfinished; see [native clock comparison](docs/og_chart_clock_probe.md).

- The synthetic builder now writes complete big-endian record headers, schema-index tags and framed raw buffers. All 22 controlled outputs pass the strict reader; runtime acceptance is not yet verified. See [serialization correction](docs/synthetic_record_framing.md).

- A separate strict sequential reader (`tools/walk_ixb_graph.py`) consumes 117/117 local plain IXB samples with exact boundaries and object counts, resolves chart/sequence references, and traces ownership by serialized object key. See [OG IXB reader findings](docs/og_ixb_reader.md) for live ABC validation and the record-framing defect in the current synthetic builder.

- Plain IXB `.X360` files are parsed with header attributes, class/member inventories, URI list state, object section bounds, and writer-order diagnostics.
- Lips-1 chart files can be analyzed for melody markers, lyric markers, marker counts, timing, and text mapping coverage.
- Lips-1 lyric files can be analyzed for text resources, payload lengths, hash-like fields, pointer-like references, and chart-word coverage.
- Corpus comparison has been run locally against the private Lips game corpus. Public docs contain only sanitized summaries.
- Batch no-op roundtrip succeeded for 111/111 plain IXB lyric files and 111/111 plain IXB chart files using section split/rejoin with no object reserialization.
- A first private runtime-console test package has been prepared locally for a single 4-byte ASCII lyric payload edit, with analyzer before/after reports and rollback instructions.
- Ghidra findings document the likely IXB writer order and several writer-relevant serializer strings/functions, but unresolved fields are still treated as hypotheses.

## Recommended Direction

The fresh OG writer is now runtime-tested for the custom song above. Next work
is DLC discovery on existing profiles, followed by synchronization and media
preview/cover packaging. Preserve the accepted chart/media checkpoint while
testing each installation change separately. LS2/DLC runtime layout support
must not be inferred from OG acceptance.

For editing existing songs, retain the template-preserving path:

1. Keep real header attributes, class/member order, URI list, object graph shape, and unknown bytes intact.
2. Make one minimal same-size payload edit at a time.
3. Compare analyzer snapshots before/after.
4. Run a controlled runtime test.
5. Only then expand the supported edit surface.

Do not extend the from-scratch writer to other format families without their
own structural and runtime validation; compressed `.X360` authoring remains
outside the accepted plain OG path.

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
