# Lips IXB/X360 format understanding status

Date: 2026-07-03

Sources used:

- Existing reader/analyzer code in `tools/`
- `docs/ghidra_findings.md`
- `docs/ghidra_xexloader_findings.md`
- `docs/script_semantics_findings.md`
- `docs/game_corpus_findings.md`
- Local private samples under `private/Lips/`
- Local private reports under `private/outputs/`

Privacy boundary: `private/Lips/` and `private/outputs/` are private inputs and
outputs. They must not be committed or pushed. This document only contains
structured summaries, not original game data, scripts, lyrics, or binary dumps.

## Executive status

We are no longer guessing about the broad shape of Lips song resources. The
project can reliably inspect many real plain-IXB `.X360` chart and lyric files,
extract melody/lyric marker summaries, identify lyric text payloads, and compare
real vs synthetic/template files at a useful structural level.

We do not yet have a complete from-scratch IXB writer specification. The safest
near-term strategy is template-preserving editing: keep the real package,
classes, object graph, header attributes, and most payload layout intact; rewrite
only fields we can validate by corpus comparison and roundtrip tests.

## 1. What Is Securely Understood

### IXB/X360 Structure

Facts:

- A large subset of Lips `.X360` song/chart/lyric files are plain IXB files that
  begin with `<ixb`.
- The local game corpus scan found 741 `.X360` files and 2 `.ixb` files.
- Of those 743 files, 311 are directly parseable plain IXB and 432 begin with
  `0F F5 12 ED`, identified by the existing reader as `LZXTDECODE compressed`.
- Plain IXB files combine XML-like metadata and binary object data in one stream.
  They are not pure XML.
- The generic IXB writer in the game emits metadata sections before raw object
  data.

Strongly supported write/read order:

1. Opening `<ixb ...>` header attributes.
2. `<Classes>`.
3. Repeated `<Class ...>` records.
4. Optional/empty `<Members>` sections with repeated `<Member ...>` records.
5. `</Classes>`.
6. `<UriList>` / `</UriList>` in the generic writer path.
7. `<Objects>`.
8. Binary object table/data.
9. `</Objects>`.
10. `</ixb>`.

Strong indication:

- Real samples in the current corpus have zero URI entries. The generic writer
  supports `UriList`, but actual parsed song resources here do not use it.

Risk:

- Compressed `.X360` files are only classified by outer magic today. Their inner
  IXB structure is not visible until decompressed.

### Header And Attributes

Facts:

- The current parser extracts top-level IXB attributes:
  `IsBigEndian`, `IsText`, `Platform`, and `NumOfElements`.
- Across 311 parsed plain IXB files from `private/Lips/`, all have
  `Platform="WIN32"` and `IsText="false"`.
- 308 parsed files have `IsBigEndian="true"`; 3 parsed standalone/non-song-ish
  files have `IsBigEndian="false"`.
- No parsed corpus file produced IXB write-order warnings with the current
  `validate_ixb_write_order` diagnostic.
- Ghidra confirms the writer-side token strings:
  `IsBigEndian`, `IsText`, `Platform`, `NumOfElements`, `Classes`, `Class`,
  `Members`, `Member`, `Offset`, `Base`, `Size`, `UriList`, `Uri`, `Key`,
  `Objects`.

Strong indications:

- `Platform` is metadata emitted by the generic serializer, not a simple "must
  equal console platform" flag. Real Xbox 360 corpus files can still say
  `WIN32`.
- `NumOfElements` is not merely the number of XML classes or visible marker
  records. Ghidra shows it is computed from writer context counters.

Hypotheses:

- `NumOfElements` probably counts a mix of object/block entries managed by the
  serializer context. Exact context fields are not mapped yet.
- In a template-preserving writer, preserving the template's `NumOfElements` is
  safer than recomputing it until object creation/deletion is fully modeled.

### Classes, Members, Objects

Facts:

- The parser reliably extracts `<Classes>` and each class's `Name`, `Size`,
  optional `Base`, and member `Offset` values.
- Existing analyzers use class inventory and member offsets to locate known
  marker payloads.
- Parsed chart resources contain class families such as `lpsMusicInfo`,
  `lpsMusicIndex`, `ixChart`, `lpsChart`, `ixSequence`, `ixSeqCode`,
  `ixTempoMap`, `ixSeqMarkerCode`, `lpsMelodyMarker`, `lpsLyricMarker`,
  `lpsPhraseMarker`, `lpsPageBreakMarker`, `lpsShortEndMarker`, and, in some
  files, `lpsHitMarker`, gesture/noisemaker classes, or LS2 classes.
- Parsed lyric resources mainly contain package/asset/file-image classes such as
  `ixPackage`, `ixAssetPackage`, `ixAsset`, `ixFileImage`, and
  `ixRawFileImage`.
- The existing object walker can extract melody markers from many real chart
  files by walking known one-byte class ids plus schema sizes, with fallback
  scanning only when needed.

Strong indications:

- Chart gameplay data is sequence/object-graph based. It is not just a flat note
  table.
- Lyric files are asset/resource containers carrying text payloads. The chart
  file carries the lyric marker timing and text offsets that point into the
  lyric text resource.

Hypotheses:

- The three 4-byte fields before object payloads observed in Ghidra are part of
  object/block serialization, but the exact semantic meaning of every field is
  still unresolved.

Risk:

- The current broad object-record probe is intentionally diagnostic. It must not
  become the primary parser until it is correlated with actual object boundaries.

### Endianness

Facts:

- PowerPC/Xbox code and existing parser logic treat numeric binary payload values
  as big-endian for song resources.
- Ghidra shows the serializer writer conditionally byte-swapping 16-bit and
  32-bit numeric fields when an endian flag is set.
- Existing marker extraction reads floats and integers from chart payloads as
  big-endian.
- Real parsed song resources overwhelmingly declare `IsBigEndian=true`.

Strong indication:

- `IsBigEndian` is not cosmetic. It controls actual numeric payload
  serialization.

Risk:

- String/XML metadata remains UTF-8/XML-like text. Endianness applies to binary
  payload fields, not to every byte in the file.

### DB, Script, And Semantic Layer

Facts:

- `private/Lips/lps/MusicDB` and `private/Lips/lps/GameContentDB` are SQLite
  databases without extensions.
- First-game `lps/MusicDB` has a single `Music` table with 40 rows.
- Writer-relevant `Music` fields include `ChartUri`, `LyricUri`, `AudioUri`,
  `VideoUri`, `AlbumJacketUri`, preview URIs, content IDs, content filenames,
  state flags, release/latest dates, leaderboard, locale, and fog fields.
- In the first-game DB, `ChartUri` and `LyricUri` use `.ixb` logical suffixes
  for all 40 rows.
- The same local corpus stores many actual resources as `.X360`.
- LS2 uses a split database shape: `MusicData`, `StageData`, `PreviewData`, and
  `DLCData`.
- Readable first-game Lua exists under `lps/Script`; LS2 scripts are mostly
  `.luaB`.
- `lps/Script/MusicDatabase.lua`, `SequenceTrackConfig.lua`, and
  `lps/Script/Chart/` are the highest-value semantic sources.

Strong indications:

- `.ixb` in DB rows is a logical resource identity; `.X360` is the platform
  package/container extension used on disk.
- First-game-style authoring should use the first-game `MusicDB.Music` model as
  the semantic target, not LS2's split table model.

Hypotheses:

- `SequenceTrackConfig.lua` is likely the best bridge from script semantics to
  `ixSequence` / `ixSeqCode` / marker classes, but it still needs field-level
  validation against bytes.

### Chart/Lyric Separation

Facts:

- Chart `.X360` files contain melody marker and lyric marker structures.
- Lyric `_Lyric.X360` files contain visible text resources.
- `analyze_lyric_file.py` can select the visible lyric text resource and, when
  given the matching chart, validate it against chart `LyricWordData` coverage.
- A real private Lips-1 pair produced 100% chart-worddata coverage for the
  selected lyric payload in the local report.
- Current tools report melody counts, lyric marker counts, text-resource
  candidates, payload lengths, payload hashes, pointer-like references, and
  coverage.

Strong indications:

- The lyric file can be edited only in coordination with chart lyric markers if
  text lengths/offsets change.
- Replacing visible text while preserving resource layout is feasible for narrow
  cases; changing structure or adding/removing words requires chart marker
  updates.

## 2. What Is Realistically Possible Now

### Reader

Realistic now:

- Identify plain IXB vs compressed/unknown `.X360`.
- Parse top-level IXB metadata attributes.
- Parse class/member schemas.
- Locate object section bounds.
- Parse empty/present URI lists.
- Extract melody markers from supported plain-IXB charts.
- Extract structural lyric marker data from supported charts.
- Locate visible text resources in `_Lyric.X360`.
- Join chart lyric markers to lyric payload coverage when both files are
  provided.

Risks:

- Reader coverage stops at compressed files until decompression exists.
- Some supported charts may still require fallback scanning or richer object
  walking.

### Analyzer

Realistic now:

- Build reliable structural reports for real chart/lyric pairs.
- Compare real vs synthetic/template files by header metadata, class inventory,
  marker counts, text-resource selection, URI-list presence, and broad object
  diagnostics.
- Use private corpus reports to find common class inventories and variants.
- Identify whether a candidate file is Lips 1-style, later/DLC-ish, or LS2-ish
  by class inventory.

Risks:

- Analyzer output must keep distinguishing facts from diagnostic probes. Object
  candidate counts and FileIO-header candidates are useful clues, not proof.

### Template-Preserving Writer

Realistic now:

- Use a real chart/lyric pair as a template.
- Preserve header attributes, class/member metadata, object graph shape,
  resource names, package/asset layout, and most offsets.
- Patch constrained payload fields such as melody timing/pitch or existing lyric
  text ranges when lengths/padding allow.
- Emit modified files that keep the original IXB structure rather than
  rebuilding from scratch.

Strong recommendation:

- This should be the main writer direction first. It aligns with what is
  actually understood.

Risks:

- Growing/shrinking payloads can invalidate offsets, pointer-like references,
  length fields, hashes, object sizes, and possibly `NumOfElements`.
- Any edit that changes object count or class inventory moves from
  template-preserving into partial-rebuild territory.

### Minimal Song/Chart Edits

Realistic now:

- Patch existing marker fields where schema offsets are known and the file is
  plain IXB.
- Replace lyric text in place when the new payload fits the existing range and
  known length/hash fields are handled.
- Generate diagnostic reports before/after to confirm marker counts, text
  coverage, and IXB metadata remain stable.

Risk:

- In-place text edits can still break hashes or pointer/length references if not
  all related fields are updated.

### New Songs From Templates

Realistic with constraints:

- Generate a new song by choosing a close template and rewriting only supported
  marker/text/audio-reference content.
- Keep the original class inventory and object graph.
- Prefer first-game-style templates because they are simpler and better aligned
  with the current goal.

Not realistic yet:

- Arbitrary song generation with a completely new object graph, new sequence
  layout, new classes, and no template.

## 3. What Is Still Unclear

### Object-Record Semantics

Facts:

- Ghidra shows writer helpers that emit raw binary blocks and repeated 4-byte
  fields before payloads.
- Existing tools can walk many object heaps by class id and class size.

Unknown:

- Exact meaning of each per-object 4-byte field.
- Whether all object payload areas use the same record shape.
- How object ids, class ids, pointer-like values, and offsets relate.
- How `NumOfElements` maps to visible object records.

Risk:

- A from-scratch writer will likely fail until this is mapped.

### Alignment And Padding

Facts:

- The writer emits raw bytes and many 4-byte numeric fields.
- Lyric text resources can include trailing null/space padding.

Unknown:

- Exact padding/alignment rule after every object payload.
- Whether rules differ between text resources, sequence data, package graph
  objects, and compressed outputs.

Risk:

- Incorrect padding can shift object boundaries and break later references.

### Compressed LZXTDECODE Files

Facts:

- 432 scanned `.X360` files start with the LZXTDECODE magic.
- Existing tools identify them and stop before structural parsing.
- Ghidra/XEXLoaderWV found decompression-related strings/functions, including
  `XctdDecompression` and `LDIDestroyDecompression`.

Unknown:

- Exact command/tool/API path we will use locally to decompress and recompress.
- Whether recompression is necessary for target deployment, or whether plain IXB
  is accepted in the relevant content path.

Risk:

- Treating compressed files as parseable IXB will produce false conclusions.

### Checksums And Hashes

Facts:

- Lyric text resources have payload-hash-like fields that current analyzers
  report.
- Ghidra did not yet identify a clear song/package checksum or SHA path.

Unknown:

- Exact hash algorithm and scope for lyric text payload hashes.
- Whether the game validates hashes strictly at load time or uses them for
  caching/resource identity.
- Whether STFS/package-level checks are relevant for our local workflow.

Risk:

- Text edits may appear structurally correct but fail at runtime if hashes are
  stale.

### Quick Actions, Gestures, Noisemakers

Facts:

- Scripts and class inventory contain gesture/noisemaker vocabulary.
- Some parsed charts include `lpsTimedGestureMarker`,
  `lpsTimedNoisemakerMarker`, LS2 LED classes, and later/DLC marker classes.
- Lua term scan found `Quick`, but only as weak semantic evidence.

Unknown:

- Which exact classes/fields represent quick actions.
- Whether quick actions are required for first-game-style song files.
- How gestures/noisemakers connect to sequence tracks and gameplay systems.

Risk:

- Removing or ignoring these structures in later/DLC-style files could break
  songs that rely on them.

### Full Writer From Scratch

Facts:

- We know the generic IXB section order and many token names.
- We know many class/member schemas from real files.
- We know endianness behavior is real and important.

Unknown:

- Complete object graph construction rules.
- Object id/reference conventions.
- Class table generation from runtime types.
- Exact `NumOfElements` computation.
- Padding/alignment.
- Hashes/checksums.
- Compression/recompression.

Risk:

- A from-scratch writer is currently high-risk and likely to create files that
  parse superficially but fail in-game.

## 4. How To Resolve Open Points Without Trial-And-Error

### Corpus Comparison

Use the existing analyzers against many real pairs and compare only structured
features:

- Header attributes.
- Class/member inventories.
- Object section bounds.
- Marker counts.
- Text resource counts and coverage.
- Payload length/hash fields.
- Pointer-like references into payloads.
- Family labels: Lips 1-style, later/DLC, LS2.

Goal:

- Identify stable invariants and variant-specific fields before writing them.

### Roundtrip Tests

Build roundtrip stages:

1. Parse a real plain-IXB file and re-emit an identical byte stream for metadata
   sections only.
2. Preserve binary object bytes exactly and verify full-file byte identity.
3. Change one known-safe scalar field and verify only expected bytes change.
4. Run analyzer before/after and compare semantic invariants.
5. Only then test in-game.

Goal:

- Separate serializer correctness from gameplay/content correctness.

### Template Preservation

Keep the writer conservative:

- Preserve class order.
- Preserve member order.
- Preserve object graph size and count.
- Preserve `Platform`, `IsBigEndian`, `IsText`, and existing `NumOfElements`.
- Preserve absent `UriList` where templates omit it.
- Preserve unknown payload bytes.

Goal:

- Reduce the unknown surface area to the fields being intentionally changed.

### Targeted Ghidra Analysis

Use Ghidra only for concrete questions:

- What exactly is the lyric writer/load path around `%s_Lyric`?
- What does the object-record field at position 1/2/3 mean in the caller?
- Which function computes or validates text payload hashes?
- Where are decompressed bytes handed to `ixSerializerReader::Load`?
- Which code path consumes `lpsTimedGestureMarker` or quick-action-like data?

Goal:

- Avoid broad reverse-engineering wandering. Each Ghidra pass should answer one
  writer-blocking question.

### DB Joiner: MusicDB To Chart/Lyric Samples

Build a local-only DB joiner:

- Read `private/Lips/lps/MusicDB`.
- Resolve `ChartUri` and `LyricUri` to local chart/lyric sample paths.
- Feed pairs into the existing analyzers.
- Emit sanitized local reports under `private/outputs/`.

Do not commit:

- Song titles, artists, lyrics, or raw DB row dumps.

Goal:

- Tie semantic DB fields to actual IXB/X360 structures without exposing private
  data.

### Decompression Step For LZXTDECODE

Add a documented local decompression workflow before analyzing compressed files:

- Detect compressed magic.
- Decompress into ignored `private/outputs/...`.
- Run existing plain-IXB analyzers on decompressed bytes.
- Keep original compressed files untouched.
- Treat recompression as a separate later problem.

Goal:

- Bring 432 currently opaque corpus files into the same structured comparison
  pipeline.

## 5. Recommended Roadmap

### Next Three Small Steps

1. Add a local-only MusicDB joiner/report runner.
   It should map first-game `ChartUri`/`LyricUri` to private files and run
   existing analyzers, outputting only sanitized summaries under
   `private/outputs/`.

2. Add a strict IXB section-boundary report.
   For each plain-IXB sample, record exact offsets for opening header,
   `<Classes>`, `</Classes>`, optional `UriList`, `<Objects>`, `</Objects>`,
   and `</ixb>`. This directly tests the Ghidra-derived writer order.

3. Add one byte-preserving roundtrip test for metadata parsing.
   Start with a small lyric file: parse header/classes/objects boundaries and
   assert that a no-op roundtrip preserves bytes exactly before allowing any
   writer edits.

### Medium-Term Steps

- Implement a template-preserving lyric text editor with full before/after
  analyzer comparison.
- Implement a template-preserving chart marker editor for known fields only.
- Map object-record fields by correlating Ghidra writer call sites with real
  object boundaries from corpus files.
- Identify and implement text payload hash calculation, if runtime tests prove
  it is required.
- Add decompression support or a documented external decompression step for
  `LZXTDECODE`.
- Extend family-specific profiles: Lips 1-style first, later/DLC second, LS2
  third.

### Explicitly Not Recommended

- Do not build a new parallel parser from scratch.
- Do not force `Platform="X360"` just because files are for Xbox 360.
- Do not write `UriList` entries unless a template or proven target file needs
  them.
- Do not use the object-record probe as a real object parser yet.
- Do not generate a full song from scratch before byte-stable template
  roundtrips work.
- Do not remove quick-action, gesture, noisemaker, LED, or LS2-ish structures
  from real templates merely because we do not understand them yet.
- Do not commit anything from `private/Lips/` or `private/outputs/`.

## Final Assessment

The project is in a solid analyzer/template-editing phase, not yet in a
from-scratch authoring phase.

The most reliable path is:

1. Keep reading more real samples with the existing tools.
2. Preserve real structure wherever possible.
3. Make small, measurable edits.
4. Prove every writer assumption with corpus comparison, roundtrip tests, and
   targeted Ghidra checks.

That path should get us to usable custom songs much faster than trying to invent
a clean-room IXB writer before the object graph, padding, hashes, and compression
rules are actually proven.
