# OG IXB reader, sequential records, and live chart ownership

Research: 2026-09-28/29. This supersedes earlier assumptions that fixed marker
tag bytes and schema inventories establish a valid synthetic object graph.
No sample files, game bytes, decompiled game code, or raw memory are included.
The writer and synthetic builder were not changed in this investigation.

Follow-up: the builder's record framing has now been corrected separately;
see [synthetic_record_framing.md](synthetic_record_framing.md) for the changes,
22/22 offline-valid outputs and remaining runtime limitations.

## Executable and analysis repair

Original Lips 2008, title 4D530888, version 0.0.0.20, XEX SHA-256:
`95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9`.
Ghidra 12.1.3 with the supplied XEXLoaderWV extension; Xenia Canary based on
aee0871. Addresses below are specific to this executable, not the executable
from the older crash dumps with entry point 0x828dae18.

The verified save-helper family starts at 0x827df4d0, saves r14..r31 and r12,
and returns at 0x827df51c. Temporary callfixups model the actual stores and
remove false no-return flags and invented helper return values. Sixteen
existing entries, r14..r29, were fixed; r30/r31 had no function entry and were
explicitly skipped. Restore helpers, complete ABI recovery, and exact function
boundaries remain incomplete. All research runs used `-readOnly -noanalysis`.

Reproducible script: `tools/ghidra/StudyOgIxbReader.java`. It checks the XEX
hash and helper instructions before applying analysis changes. Example,
using an already imported private project:

```powershell
& "$Ghidra\support\analyzeHeadless.bat" "$Projects" LipsOG2008_Reader `
  -process default.xex -readOnly -noanalysis `
  -scriptPath tools/ghidra `
  -postScript StudyOgIxbReader.java private/outputs/og_reader_decompile.txt
```

The output contains generated decompiled game code and must remain private.

## Reader behavior

The binary IXB reader is at **0x82d98700**, identified through its header,
Classes, Members, UriList and Objects token handling. Related functions:

| Address | Observed operation | Confidence |
|---|---|---|
| 0x82d98700 | Parses metadata/schema and consumes binary object records | High |
| 0x82d979c8 | Copies/converts payload fields using class/member layout descriptors | High for operation, provisional signature |
| 0x82d97c28 | Resolves serialized references through an object-key table; queues unresolved references | High for operation, provisional member types |
| 0x82d98558 | Registers URI-resolved objects in the lookup table | Medium |

The reader consumes the following header, then the declared payload:

| Record-relative offset | Big-endian value |
|---:|---|
| +0 | 32-bit tag; schema class index = tag & 0xfff |
| +4 | 32-bit serialized object key |
| +8 | 32-bit length word; payload length = word & 0x7fffffff |
| +12 | Payload bytes |

Class indices are one-based, in embedded schema order. Index zero denotes raw
data. The next record begins immediately after the payload, with no alignment
rounding. Closing Objects is recognized only at a reached record boundary.
The remaining flag bits are retained but their complete meaning is unresolved.
Serialized keys are mapped to allocated objects during loading; they are not
runtime addresses. Forward references require fixups.

Melody-related records must be identified by schema inheritance. ABC's notes
are mostly `lpsPhraseMarker`, derived from `lpsMelodyMarker`, with class tag
37 (0x25), not a universal 0x28 tag. Other files assign different indices to
the same class. A class inventory also contains classes with zero instances.

## Corpus validation

All 119 available `.X360` files under `private/samples/` were attempted:
59 charts and 60 lyric files. Two compressed files, one chart and its lyric
partner, were reported unsupported. All **117 plain files** were consumed
sequentially with exact Objects boundaries and matching NumOfElements.
No scan, resynchronization, alignment guesses, or plausibility filtering were
used. Confidence is high within this corpus; compressed handling and other
unseen variants are not established.

The private file-by-file manifest, including SHA-256 values and complete
vector diagnostics, is `private/outputs/ixb_sequential_graph_20260929.json`.
Reproduce it with:

```powershell
python tools/walk_ixb_graph.py private/samples --json `
  > private/outputs/ixb_sequential_graph_20260929.json
```

The command writes only stdout; its exit status is nonzero when unsupported
files or graph errors are included. The two compressed files explain that
status in this run. This is a separate read-only diagnostic, not a replacement
for the existing writer or scanner.

Diagnostic object indices are zero-based positions in the whole Objects
section, including raw records; they are not the legacy marker-only indices.

| Observation | Frequency / count | Confidence |
|---|---:|---|
| Exact framing and header count | 117/117 plain files; 216,483 records | High |
| One instantiated chart root | 58/58 plain charts | High |
| Checked chart/sequence reference vectors | 1,893 vectors; 118,132 entries; zero unresolved nonnull targets | High |
| Melody-derived instances | 41,456 across 58 charts | High for inheritance, not all necessarily vocal notes |
| LyricMarker instances | 37,080 across 58 charts | High |
| Nonnull LyricMarker Melody references resolve to Melody-derived objects | 37,059/37,059 | High |
| Null LyricMarker Melody reference | 21 markers in 1/58 charts | Low for mode/semantic explanation |
| WordData raw buffer length = reserve * 20 bytes | 37,080/37,080 vectors | High within corpus |
| WordData vector size | 37,077 size-one vectors, 3 size-two vectors | High |
| lpsChart.m_pIndex serialized null | 58/58 roots | High |
| lpsChart.m_pMusicData serialized null | 16/16 schemas that declare it | High within applicable subset |
| lpsMusicInfo / lpsMusicIndex schema present | 58/58 charts each | High |
| lpsMusicInfo / lpsMusicIndex object instances | 0/58 charts each | High |

Two root layouts occur: 42/58 have lpsChart size 148 and m_pIndex at 112;
16/58 have the later layout, m_pIndex at 144, m_pMusicData at 148, and
m_vpExtraSequence at 88. Both expose m_vpSequence at 72. The schema, not a
fixed generation label, determines which fields exist. ExtraSequence is absent
in the first layout; +88 there is MusicStartOffset.

Vector schemas describe data/reserve/size/allocator at +0/+4/+8/+12. Reference
vector data keys point to separate raw records whose used entries are 32-bit
object keys. Empty vectors may retain a nonnull buffer and nonzero reserve.
Allocator slots contain multiple patterns, including 0xcdcdcdcd; treating
these bytes as mandatory live allocator pointers is unsupported.

The old raw-pitch name at marker +16 is an API alias: the schema names that
field `m_iTrackIndex`. Tone is a separate eight-byte value, fIdx and octave.
The old pitch formula agrees for 41,410/41,456 Melody-derived instances, so it
is not a universal semantic rule for every derived marker class. Existing
patcher behavior was left unchanged pending class-specific investigation.

## Live ABC graph

ABC gameplay was visually verified on 2026-09-29 and paused in Xenia for
read-only process-memory inspection. The chart's strict walk gives 5,597
records, 1,180 Melody-derived instances and 1,150 LyricMarkers.

Two complete sequence buffers, 381 and 321 entries, matched file object order
and time/length/+16 fields for every entry. Following buffer references at
sequence +72 identified their owning sequences, then the chart's vector at
+72 identified the root with reserve 32 and size 15.

One concrete chain in this paused run:

| Role | Serialized object key | Runtime guest address |
|---|---:|---:|
| lpsChart | 0x31635560 | 0xe9b65b40 |
| Chart sequence buffer | 0x41232160 | 0xe98bdf80 |
| Sequence at chart entry 6 | 0x41231ae0 | 0xe98be780 |
| SeqCode buffer, 381 entries | 0x14817e78 | 0xea8b7000 |
| First lpsPhraseMarker | 0x413fd0e0 | 0xe94b6800 |

The first marker is record 4022, header offset 0x9b825, payload offset 0x9b831,
time 2.817676544 and length 0.158839464. These guest addresses are allocation
results, not constants for serialization. The chart and sequence vtables in
this executable are 0x820df848 and 0x821085d8.

```powershell
python tools/walk_ixb_graph.py private/samples/charts/ABC.X360 `
  --trace-key 0x413fd0e0 --json
```

Following all 15 root entries confirms matching vector size/reserve for
15/15 sequences, 2,542 SeqCode references, and zero unreadable referenced
objects. The comparison matches time/+16 for 2,477 entries and length for
2,057. Differences occur in tempo-related records and one phrase/lyric group;
they must not be interpreted as corrupt pointers merely because they differ
from disk.

All 1,150 live lyric WordData used payloads match the raw-record payload bytes
from disk, including the inferred 20-byte element layout. Of the lyric Melody
links, 1,131 match file Melody time/length/+16; 19 target altered hit markers.
One group of 466 LyricMarkers has changed length, and all 466 lengths equal
their current linked Melody lengths. Other lyric groups retain file lengths.
Specific Single/VS/Duet/short/full assignments remain unresolved.

ABC's serialized m_pIndex is zero, but the live root points to 0xeb040080,
an object with vtable 0x820ec860. Together with zero disk instances across the
corpus, this supports runtime construction of the index, not a requirement to
serialize an lpsMusicIndex object. The exact construction call path remains
to be traced.

The legacy WordData resolver anchors at the object-key word, header +4.
Its relative +12/+16 character fields are therefore payload +4/+8. The earlier
file/runtime offset discrepancy was an anchor discrepancy, not evidence that
the loader moves those fields within the element.

The local live probe is `xenia-research/probe_og_sequence_graph.py`; derived
results are `og-live-sequence-full-20260929.json`. They remain local. Reads
were bounded to Xenia's 512 MiB physical backing view; overlapping chunks
were deduplicated for object hits. No memory writes or synthetic asset loads
were performed. This live evidence covers one song and one gameplay session.

## Concrete synthetic-builder failure

`build_minimal_ixb_pair.py::_object` currently emits `bytes([tag]) + body`, and
`_join_ixb` concatenates those chunks directly. Raw vector/name data is also
emitted outside the required record framing. This is incompatible with the
observed 12-byte record header.

All 11 current controlled levels were generated in memory, then their chart
and lyric bytes were passed to the strict walker: **22/22 outputs fail at the
first record**. No synthetic outputs were written or run on the console.

For full-current's lyric, the first twelve bytes would be interpreted as:

- tag 0x06050001, class index 1;
- object key zero;
- length 0x1454696e, far beyond the generated file.

This proves invalid serialization before ownership-field analysis even begins.
It plausibly explains allocation/copy failure, but the old crash dumps do not
prove that precise call path. A changed copy-helper crash address alone does
not prove successful chart-root traversal. Earlier claims that missing roots
or malformed allocator slots were the confirmed cause must be downgraded.

The next controlled implementation should first emit proper tag/key/length
records, select tags by its own schema order, emit vector buffers as raw
records, count all records correctly, and validate every nonnull reference.
It should keep serialized index/music pointers null as observed and avoid
adding further classes until framing passes. Game acceptance of a minimal
graph, resource semantics, and mode requirements still require testing.
