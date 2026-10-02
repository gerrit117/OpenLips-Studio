# Song variants: corpus findings and LS2 follow-up

Snapshot: 2026-10-01. Read-only analysis; no game binaries or scripts are
distributed. Confidence below concerns the sampled corpus, not every release.

## Scope and reproducibility

Scanned every chart in local `private/samples/charts`, the re-extracted OG
backup's Levels tree, and the freshly extracted Number One Hits Levels tree.
There are **211 physical files, 130 distinct SHA-256 contents, 129 parsed plain
IXB charts and one distinct unsupported compressed chart**. The latter is
Irreplaceable, magic `0f f5 12 ed`, repeated across the three inventories.
No structural graph errors were reported for the 129 supported charts.

The private `song-variants-corpus.json` lists **every analyzed filename, hash,
corpus, schema, sequence and event**. Copies shared across corpora are not
independent evidence. Per-corpus denominators below exclude compressed input.

Reproduce with `python -m tools.analyze_song_variants --corpus local=private/samples/charts
--corpus OG=<backup-Levels> --corpus NOH=<extracted-Levels> --out <new-report.json>`.
The tool reads files only, resolves owned sequence vectors and distinguishes
actual objects from classes merely declared in XML.

| Observed structure | Local (58) | OG backup (39) | NoH extraction (111) | Confidence |
|---|---:|---:|---:|---|
| Actual lpsShortEndMarker | 58/58 | 39/39 | 111/111 | High: always present in supported corpus |
| Four named duet melody/lyric tracks | 31/58 | 18/39 | 44/111 | High: often present, not universal |
| Actual lpsTimedGestureMarker | 14/58 | 0/39 | 0/111 | Medium: later local subset only |
| Actual lpsTimedNoisemakerMarker | 11/58 | 0/39 | 0/111 | Medium: later local subset only |
| Actual lpsPlayerIdCode | 27/58 | not summarized here | not summarized here | Medium: optional local feature |
| lpsChart schema size 148 | 42/58 | 39/39 | 111/111 | High |
| lpsChart schema size 184 | 16/58 | 0/39 | 0/111 | High for existence; family attribution medium |

**The inspected NoH ISO is not evidence that all later charts use the 184-byte
layout.** It contains legacy-layout charts as well. Generation must be inferred
from schema/object fields, not an ISO name or one fixed marker signature.

## Native executable and Lua cross-check

NoH Default.xex SHA-256:
`5a3f0d7c104366ac5483db627efb7944004e5a6a33e502b9c9d359fbb0b170f8`.
Its entry is `0x828dae18`, .text begins `0x821e0000`; XEXLoaderWV imported
33,238 pdata symbols and Ghidra reported 33,302 functions. The loader still
emitted an LZX output-length warning and some instructions/functions remain
unresolved. Analysis success does not prove complete or perfect decompilation.

The native registration function at `0x82353168` references lpsChart,
lpsTimedGestureMarker and lpsTimedNoisemakerMarker class names. `_Cht.X360`
path construction is referenced by `0x82310948`. These addresses apply only
to the exact hash above. OG and NoH addresses must not be mixed.

Both inspected OG and NoH XEX headers report Title ID **4D530888**, with
different media IDs and versions. Do not equate shared identity with identical
executables. `tools/inspect_xex_identity.py` verifies headers without modifying
them. Raw disassembly and extracted Lua remain private.

## Quick actions

Later local charts contain a 44-byte timed gesture marker with
`m_TargetGestureIndex` at schema offset 40, and a 40-byte timed noisemaker
marker. These are real event objects, not guessed note tags. The source schema
must govern inherited fields and runtime/file tags.

NoH `Chart/ExciteMeter.lua` also drives gestures from score/excitement and routes
microphone actions. Thus **dynamic action prompts and authored timed events are
different mechanisms**. Adding a timed marker does not automatically reproduce
the entire prompt, scoring, animation and microphone workflow. Mic routing and
gesture enums still need controlled native tests; no QTE writer is enabled yet.

`lpsHitMarker` also has 44/48-byte layouts: its vowel field moves with the
layout. A common fixed offset across releases would be unsafe.

## Duet

Observed names are `Melody_Duet`, `Melody_Duet_P2`, `Lyric_Duet` and
`Lyric_Duet_P2`; script configuration includes player-1 aliases. The actual
owned code lists may differ, so these are not interchangeable copies.
`ChartPreview.lua` selects cooperative mode for duet and versus otherwise,
and separately enables players. Confidence: high for separate tracks, medium
for complete native routing/scoring until gameplay verification.

Implementation needs two editable voice/lyric tracks, per-player bindings,
correct shared/unison events and independent WordData mapping into the text
resource. Studio currently creates a single-voice draft; it must not advertise
that as a finished duet chart. Automatic separation of a lead from instruments
does not distinguish two singers inside the vocal stem.

## Full and short

Every supported chart contains a short-end marker. `LpsUtilities.lua` passes
the session's short-mode choice into the chart player before initialization.
`Chart/ShortMode.lua` receives approach/end/extended callbacks; minigame scripts
query page counts with short-mode enabled. This strongly supports a runtime
early-end/extend mechanism on the same full song, **not necessarily a second
physically shortened media file** (medium confidence). Exact end-marker dispatch,
fade handling, extension threshold and grading need native tests.

The 2026-10-02 binding audit resolved the missing native references by tracking
PowerPC address construction across a reused nonvolatile base register. Raw
pointer scans and adjacent lis/addi scans alone did not find these bindings.
For the exact NoH hash above, `SetShortModeEnabled` is bound through site
`0x8240d04c` to Lua wrapper `0x8239f490`, which calls native setter
`0x8225a010`. The setter writes a 32-bit state at **runtime object +0x27c**.
`GetShortModeEnabled` is bound at `0x8240d060` to wrapper `0x8239f508`, which
calls getter `0x8225a018` reading the same field. Confidence: high for this
single executable's static binding, unverified across other executable versions.
This is a chart-player runtime state, **not an IXB serialized field offset**.

The `BeginShortModeApproach` and `ShortModeExtended` bindings were also resolved
at `0x8240ca3c` / `0x8240ca54`. Their accessor wrappers address runtime event
containers at **+0x10c / +0x11c**; companion wrappers route listener registration
to those same containers. Confidence: medium for event-container semantics from
static code plus Lua usage, not a proven complete media-stop/fade implementation.
The event dispatch/threshold consumers still need targeted runtime comparison.

`tools/ghidra/StudyVariantBindings.java` reproduces this bounded, hash-guarded
audit in a read-only headless project. It distinguishes candidate constant
references from established bindings, uses pseudo-disassembly for undefined
regions, and limits decompilation. The large binding region is not fully defined
as a function in the existing analysis. A save-register helper is also marked
non-returning by Ghidra despite decoded instructions after its call, truncating
one binding helper's decompilation. Raw C output alone is therefore insufficient;
the documented setter/getter mappings were cross-checked against instructions.
Game-derived exports remain private. This method has not established all QTE
enums, duet routing or final short-mode behavior.

An additional cross-corpus check found **exactly one short-end object in each
of 129/129 distinct supported charts**, always owned by the **Section** sequence
(129/129). Its trigger ranges from 70.526 to 224.805 seconds. Confidence is high
for this ownership invariant. Put an eventual generated short endpoint in
Section, not in a guessed Conductor track or a separately chopped note heap.
Its timestamp alone does not establish how the media fade/extend logic works.

The 139 timed gesture objects across the fourteen distinct local charts use
target indices 1, 2, 3, 5, 7, 8, 9, 10 and 12 (index 5 occurs in 78 objects).
These are occurrence counts, **not** verified gesture names or universal enums.
ExciteMeter's dynamic icon indexing and mic modes do not prove that this authored
target-index field uses the same enum; native dispatch must confirm it first.

The later ixChart base is 108 bytes with sequence/extra-sequence vectors at
72/88 and music-start offset 104; the older base is 92 bytes with music-start
offset 88. Later lpsChart stores index/music data at 144/148. Shared member
names must be resolved structurally. Do not transfer byte offsets blindly.

## Previews and overview metadata

Menu `QueueMenu.lua` asks MusicIndex for a distinct preview-video URI and has
a fallback when it is empty; `ChartPreview.lua` starts the chart at a supplied
start offset. Overview media binding therefore is not simply the full-song
filename reused everywhere. Existing database research identifies preview
audio/video/icon fields and preview time windows. Correct export needs matching
URIs, valid encoded preview assets and timing from the same recording.

The new AI A/B test intentionally leaves the original media, cover, previews
and database unchanged. It tests newly generated chart/lyric ownership, not new
catalog registration. Preview lyric/page synchronization for a newly registered
song remains a separate acceptance test; it has not been declared solved here.

## Personal edition: deferred, not a shipped feature

Logos, background music, UI fonts and catalog selection require separate asset
and save-cache tests. Changing Title ID can break DLC discovery, profile storage,
title updates and achievements. Keeping 4D530888 is the safer first experiment
for existing Lips DLC compatibility, not a guarantee. A custom title ID with
compatible DLC requires verified remapping/patches, not just a name change.
Any future personal-edition script must consume the user's original files;
neither game data nor patched XEX binaries should be published.

Next: inspect native short/gesture consumers on the exact executable, then test
one event and one mode at a time. The 600-DLC baseline remains scheduled for the
user's next test session; this analysis makes no performance-fix claim.
