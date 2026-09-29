# Original Lips: disc-to-runtime observations

Follow-up: [og_ixb_reader.md](og_ixb_reader.md) adds a strict sequential reader
and a complete live chart-to-sequence-to-marker trace for ABC. It also corrects
the apparent WordData file/runtime offset discrepancy below: the legacy file
resolver anchors at the header's key word, not at the payload start.

## Scope and evidence

Research session: 2026-09-22. Original Lips 2008, title 4D530888,
version 0.0.0.20, running in the locally instrumented Xenia Canary build
based on aee0871. ABC was started and gameplay with notes and lyrics was
visually verified. This is not a Number One Hits result and does not establish
why that game hangs. No game-memory writes, sample edits, or writer changes
were made. Guest execution was paused for read-only memory inspection.

The original ISO was inventoried directly using Xenia's XISO directory layout.
There are 40 song charts: 39 plain IXB and one compressed/unsupported chart
(Irreplaceable, magic 0ff512ed). All 40 were attempted. The existing parsers
provided schema and candidate information for 39; compressed data was not
interpreted. Of 32 charts also present at the matching local sample path, all
32 were byte-identical to the ISO; eight had no matching local file there.

This is an original-disc corpus, not evidence covering all DLC or LS2 files.
Live memory evidence covers one song and seven distinct note tuples only.
Private inventories and probes are in the local xenia-research directory:
inspect_og_disc.py, og-disc-inventory.json, probe_og_markers.py,
og-memory-markers.json and the og-format-20260921.log emulator log.
Do not commit the ISO, extracted assets, lyrics, or raw memory dumps.

## Disc-wide schema invariants

All offsets below are schema member offsets, not proven serialized body
offsets. Class declarations do not prove instantiated or required objects.

| Class / field | Observed schema | Frequency | Confidence |
|---|---|---|---|
| ixChart | size 92 | 39/39 readable charts | High within this disc |
| ixChart.m_vpSequence | offset 72 | 39/39 | High |
| ixChart.m_MusicStartOffset | offset 88 | 39/39 | High |
| lpsChart | size 148 | 39/39 | High |
| lpsChart.m_pIndex | offset 112 | 39/39 | High |
| lpsChart.m_strLyricPathCash | offset 132 | 39/39 | High |
| ixSequence | size 104 | 39/39 | High |
| ixSequence.m_vpSeqCode | offset 72 | 39/39 | High |
| ixSequence.m_vpListeners | offset 88 | 39/39 | High |
| ixTempoMap | size 104 | 39/39 | High |
| lpsMusicInfo | size 272 | 39/39 | High |
| lpsMusicIndex | size 536 | 39/39 | High |

In particular, offset 88 is NOT an extra-sequence vector in these ixChart
schemas. lpsChart.m_pIndex is NOT at 144, and these schemas do not declare
m_pMusicData at 148. Do not transplant the previously investigated later
layout into OG files. This does not invalidate those offsets for other builds.

The current family heuristic labels 11/39 plain charts from this original disc
as "later-generation / DLC" and 28/39 as "Lips 1-style chart". Therefore its
label is not a reliable generation identifier. All 39 readable pairs have two
candidate Text resources according to the existing resource finder; one
unsupported pair yields zero. These are detector results, not a complete
independent resource-table validation.

Files attempted (all .X360): No One; Stand By Me; Irreplaceable; Call Me;
With You; Yellow; Just Like Heaven; Personal Jesus; Survivor; White Flag;
Mercy; Hungry Like The Wolf; ABC; Virtual Insanity; Ring of Fire; Ruby;
Love at First Sight; Bleeding Love; Superstar; Makes Me Wonder;
Rome Wasn't Built in a Day; In Bloom; Young Folks;
Every Little Thing She Does Is; Another One Bites the Dust;
Fake Plastic Trees; Umbrella; Listen to Your Heart; I Wanna Be Sedated;
Love In a Trashcan; Amazing; Bust a Move; Boogie 2Nite; Song For Whoever;
An End Has a Start; Its Raining Men; Suddenly I See; Naive; I'm Gonna Be;
Put 'em High.

## ABC: provenance and candidate counts

The emulator log confirms loading chart and lyric from
game:\lps\Levels\Intl\J\Jackson 5\ABC\. Both ISO assets match the local
ABC sample files byte-for-byte.

| Asset | Bytes | SHA-256 |
|---|---:|---|
| ABC.X360 | 1011913 | 1ab7f47d31bfc63af38581bddcb6a3ae1a33c0c63311cf6db5cc289d6bdad704 |
| ABC_Lyric.X360 | 6808 | aaf2d3149514dd251635c3fba047b9671e1f57debd96955a75b84d24103b145c |

Chart NumOfElements is 5597. Existing tools report 1180 Melody candidates,
1150 Lyric candidates and 633 excess Melody timestamps after grouping equal
times. These are not independently validated counts of all live objects.
The current "object-walker" includes bytewise resynchronization and candidate
scanning, so its mode name must not be treated as proof of a complete graph.

## Live Melody and Lyric relationship

Eight distinct early time/length/raw-pitch patterns were searched in bounded
guest memory regions. Seven produced matches: 14 Melody-shaped objects and
seven Lyric-shaped objects. For each of these seven tuples, two Melody copies
were found at distinct physical backing addresses, plus one Lyric object.
The eighth pattern was not matched; this is not an exhaustive heap traversal.

Following each Lyric's pointer at +24 resolves to a Melody object with exactly
matching time, length and raw-pitch words (7/7). All seven WordData offset/length
pairs also match candidates in the original chart. Confidence is high for
these observed links, low for generalizing their ownership to specific modes.

| Live object field | Byte offset | Representation / observation |
|---|---:|---|
| Melody vtable | 0 | 0x820e1938 in this executable |
| Melody trigger | 8 | big-endian float32 |
| Melody length | 12 | big-endian float32 |
| Melody raw pitch | 16 | big-endian integer |
| Melody tone | 24 | big-endian float32 |
| Melody octave | 28 | big-endian integer |
| Melody tilt word | 32 | zero in these matches |
| Lyric vtable | 0 | 0x820e1100 in this executable |
| Lyric Melody pointer | 24 | relocated guest pointer |
| Lyric WordData vector | 28 | pointer, reserve, size, allocator slot |
| Lyric end-word word | 60 | 1 in these matches |

First linked Melody: time 2.817676544, length 0.158839464, raw pitch 59,
tone 8.0, octave 5. First Lyric points to guest 0xe94d2040. Its WordData
vector is pointer 0xea17a880, reserve 32, size 1. The first three words at
that vector data address are 0x188fcd00, 49, 2. Across seven vectors the first
word is constant; words at +4/+8 match file character offset/length pairs.
The meaning of the first word and total runtime element size remain unproven.
The probe read 20 bytes for inspection; bytes beyond the validated fields
must NOT be assumed to belong to the element.

| Time (s) | File candidates: character offset/length | Live pair |
|---:|---|---|
| 2.817677 | 33/2, 49/2 | 49/2 |
| 2.983422 | 36/4, 52/4 | 52/4 |
| 3.149168 | 41/3, 57/3 | 57/3 |
| 3.480659 | 45/3, 61/3 | 61/3 |
| 3.812150 | 98/4, 79/4 | 79/4 |
| 3.977896 | 102/3, 83/3 | 83/3 |
| 5.469607 | 17/2, 86/2 | 86/2 |

The file parser reads character fields at serialized record +12/+16, whereas
the live vector element exposes matching values at +4/+8. Do not copy a
runtime vector body into the file serializer. The first file Lyric candidates
have length 0.082872868 while the matched live Lyric length equals its linked
Melody length 0.158839464. This difference could involve loader processing or
candidate interpretation; determining the responsible code needs tracing.

The vector allocator slot is 0xcdcdcdcd in six observed Lyric objects and
0x60aa110b in one. A nonzero/uninitialized-looking slot alone is therefore
not proof of corruption: this song is running. Conversely, this observation
does not make arbitrary serialized allocator values safe.

Vtable addresses are executable-specific. The older documented Melody value
0x8200d8d0 must not be used as a universal runtime signature.

## Xenia address translation pitfall

ReadProcessMemory consumes host addresses, not Xbox addresses. This session's
virtual mapping base is 0x100000000. Xenia memory.h TranslateVirtual on Windows
adds another 0x1000 for guest addresses >= 0xe0000000:

    host = virtual_membase + guest + (guest >= 0xe0000000 ? 0x1000 : 0)

Thus guest 0xe94d2040 maps to host 0x1e94d3040, also accessible through
physical backing at 0x2094d3040. Omitting the bias initially returned unrelated
objects and falsely appeared to show invalid pointers; corrected reads validate
all seven links. Deduplicate aliases before counting runtime objects.

## Text and mode limitations

The detector reports ABC resource payloads [0x9dd,0x1899), length 3772, and
[0x1958,0x19ac), length 84. WordData bounds coverage is 1150/1150 versus 19/1150.
The first detected range contains 66 CRLF sequences, 362 NUL bytes and does
not decode as strict UTF-8. A 64-byte prefix is also present in guest backing
memory at host 0x207df89dd, consistent with a loaded file buffer. This is NOT
proof of the final runtime text representation or the range consumed by the
renderer. The resource finder itself still uses padding/printability choices.
Bounds coverage alone cannot establish correct semantic text resolution.

Multiple file groups and live copies are real observations, but Single/VS,
player, short/full, preload and runtime-copy explanations remain unseparated.
The backstage screen showed Multiplayer VS; that label is insufficient to
assign each object copy to a player. No claim of a solved text serializer or
minimal valid synthetic root graph follows from this session.

## Next controlled investigation

1. Trace owners of the validated live Melody/Lyric pointers back to sequence
   vectors, then chart roots; confirm vector units rather than guessing.
2. Trace resource lookup and the live WordData first word through the lyric
   renderer to establish its actual string encoding and indexing units.
3. Repeat the same bounded observations for another song and another mode.
4. Only then revise serialization. Keep file layouts, runtime layouts and
   executable-specific addresses separate in every report and test.

No synthetic structures were added in this investigation. The current evidence
supports a reproducible runtime comparison route, not a finished IXB writer.
