# X360 Synthetic Chart Crash Analysis

Crash context from the `full-current` synthetic pair test:

- exception code: `0xC0000005`
- IAR / crash address: `0x82AB3284`
- write target: `0x00000000`
- thread: `0xF9000000`
- stack pointer / GPR1: `0x30199850`
- observed variants:
  - `tags`: returns to song menu
  - `lyric-ownership`: returns to song menu
  - `full-current`: hard game crash

Local dump analyzed:

- `C:\Users\Gerrit\Desktop\dump.bin`
- size: `0x1110000` bytes
- PE/XEX-style PowerPC image
- image base: `0x82000000`
- entry RVA: `0x008DAE18`

Generated dump report:

```powershell
py tools\analyze_x360_crash_dump.py C:\Users\Gerrit\Desktop\dump.bin `
  --iar 0x82AB3284 `
  --sp 0x30199850 `
  --write-target 0x0 `
  > private\outputs\crash_dump_report.txt
```

The generated report is under `private/outputs` and should not be committed.

## Address Mapping

`0x82AB3284` maps into the main loaded game image. The image contains
`default.xex` strings and has the normal Xbox 360 executable image base:

- module/image base: `0x82000000`
- module-relative offset / RVA: `0x00AB3284`
- section: `.text`
- flat memory-image file offset: `0x00AB3284`
- PE section raw offset: `0x00AA5084`
- containing `.pdata` function: `0x82AB2DD8-0x82AB3548`
- function-relative offset: `0x4AC`
- `.pdata` unwind/info word: `0x40003704`

The bytes at the flat memory-image offset decode as valid PowerPC code. The PE
section raw offset does not show the live instruction stream, so this dump is
best treated as an already memory-mapped image.

## Code Around IAR

The crash site is inside a tight copy/fill-style routine, likely an optimized
runtime `memcpy` / `memmove` / vector-copy helper rather than a high-level chart
function.

Relevant disassembly:

```text
82AB3274: 80040004  lwz r0,4(r4)
82AB3278: 80E40008  lwz r7,8(r4)
82AB327C: 8104000C  lwz r8,12(r4)
82AB3280: 28060000  cmplwi cr0,r6,0
82AB3284: 90030004  stw r0,4(r3)  <-- IAR
82AB3288: 84040010  lwzu r0,16(r4)
82AB328C: 90E30008  stw r7,8(r3)
82AB3290: 9103000C  stw r8,12(r3)
82AB3294: 94030010  stwu r0,16(r3)
82AB3298: 4082FFD8  bne 0x82AB3270
```

The faulting instruction is:

```text
stw r0,4(r3)
```

Given the debugger write target `0x00000000`, the effective store address was
zero. For this exact instruction that implies `r3 + 4 == 0` in 32-bit effective
addressing, so `r3` was likely `0xFFFFFFFC`. That matches the observation that
many registers displayed `0xFFFFFFFFFFFFFFFF`.

Interpretation: the game likely passed an invalid destination pointer into a
copy/vector construction routine. The IAR itself is probably not the original
bad chart parser code; it is where the bad pointer finally became a write.

## Stack Inspection

The supplied dump does not include the stack address range:

- captured image range: `0x82000000-0x83110000`
- GPR1 / SP: `0x30199850`

So the stack window cannot be inspected from this file. To recover callers, a
separate memory read around `0x30199850` would be needed, for example
`0x30199750-0x30199A50`.

## Corpus Rule

This analysis uses all available local chart samples under
`private/samples/charts`, not only `1234`.

Sample count:

- chart samples analyzed: 59
- plain IXB charts: 58/59
- compressed/unsupported chart: 1/59

Files analyzed:

- `private/samples/charts/1234.X360` [plain IXB]
- `private/samples/charts/99 Luftballons.X360` [plain IXB]
- `private/samples/charts/ABC.X360` [plain IXB]
- `private/samples/charts/Amazing.X360` [plain IXB]
- `private/samples/charts/Another One Bites the Dust.X360` [plain IXB]
- `private/samples/charts/Any Dream Will Do.X360` [plain IXB]
- `private/samples/charts/Bad Moon Rising.X360` [plain IXB]
- `private/samples/charts/Bleeding Love.X360` [plain IXB]
- `private/samples/charts/Bust a Move.X360` [plain IXB]
- `private/samples/charts/Call Me.X360` [plain IXB]
- `private/samples/charts/Complicated.X360` [plain IXB]
- `private/samples/charts/Every Little Thing She Does Is.X360` [plain IXB]
- `private/samples/charts/Everything About You.X360` [plain IXB]
- `private/samples/charts/Fake Plastic Trees.X360` [plain IXB]
- `private/samples/charts/Hard Habit To Break.X360` [plain IXB]
- `private/samples/charts/Hard To Say I'm Sorry.X360` [plain IXB]
- `private/samples/charts/Hit Me With Your Best.X360` [plain IXB]
- `private/samples/charts/Hungry Like The Wolf.X360` [plain IXB]
- `private/samples/charts/I Don't Wanna Live.X360` [plain IXB]
- `private/samples/charts/I Don't Want To Wait.X360` [plain IXB]
- `private/samples/charts/I Wanna Be Sedated.X360` [plain IXB]
- `private/samples/charts/In Bloom.X360` [plain IXB]
- `private/samples/charts/Irreplaceable.X360` [LZXTDECODE compressed]
- `private/samples/charts/Island in the Sun.X360` [plain IXB]
- `private/samples/charts/Just Like Heaven.X360` [plain IXB]
- `private/samples/charts/Kasebrot.X360` [plain IXB]
- `private/samples/charts/Let's Get It Started.X360` [plain IXB]
- `private/samples/charts/Let's Groove.X360` [plain IXB]
- `private/samples/charts/Listen to Your Heart.X360` [plain IXB]
- `private/samples/charts/Love at First Sight.X360` [plain IXB]
- `private/samples/charts/Love In a Trashcan.X360` [plain IXB]
- `private/samples/charts/Love Song.X360` [plain IXB]
- `private/samples/charts/Makes Me Wonder.X360` [plain IXB]
- `private/samples/charts/Mercy.X360` [plain IXB]
- `private/samples/charts/No One.X360` [plain IXB]
- `private/samples/charts/Personal Jesus.X360` [plain IXB]
- `private/samples/charts/Relax.X360` [plain IXB]
- `private/samples/charts/Ring of Fire.X360` [plain IXB]
- `private/samples/charts/Rome Wasn't Built in a Day.X360` [plain IXB]
- `private/samples/charts/Ruby.X360` [plain IXB]
- `private/samples/charts/So Soll Es Bleiben.X360` [plain IXB]
- `private/samples/charts/SoakUpTheSun.X360` [plain IXB]
- `private/samples/charts/Stand By Me.X360` [plain IXB]
- `private/samples/charts/Superstar.X360` [plain IXB]
- `private/samples/charts/Survivor.X360` [plain IXB]
- `private/samples/charts/Sweet Home Alabama.X360` [plain IXB]
- `private/samples/charts/Take On Me.X360` [plain IXB]
- `private/samples/charts/The Look Of Love.X360` [plain IXB]
- `private/samples/charts/The Phantom Of The Opera.X360` [plain IXB]
- `private/samples/charts/The Sign.X360` [plain IXB]
- `private/samples/charts/Umbrella.X360` [plain IXB]
- `private/samples/charts/Virtual Insanity.X360` [plain IXB]
- `private/samples/charts/Walk Like an Egyptian.X360` [plain IXB]
- `private/samples/charts/White Flag.X360` [plain IXB]
- `private/samples/charts/With You.X360` [plain IXB]
- `private/samples/charts/Yellow.X360` [plain IXB]
- `private/samples/charts/You're Beautiful.X360` [plain IXB]
- `private/samples/charts/You've Lost That Lovin.X360` [plain IXB]
- `private/samples/charts/Young Folks.X360` [plain IXB]

## Chart Root / Sequence Corpus

Across the 58 supported plain IXB chart samples:

- `ixChart`: present in 58/58, confidence high
- `lpsChart`: present in 58/58, confidence high
- `ixSequence`: present in 58/58, confidence high
- `ixTempoMap`: present in 58/58, confidence high
- `ixVector<ixSequence *>`: present in 58/58, confidence high
- `ixVector<ixSeqCode *>`: present in 58/58, confidence high
- `ixSeqCode`: present in 58/58, confidence high
- `lpsMusicInfo`: present in 58/58, confidence high
- `lpsMusicIndex`: present in 58/58, confidence high
- `ixAssetPackage`: present in 58/58, confidence high
- `ixAsset`: present in 58/58, confidence high
- `ixFileImage`: present in 2/58, confidence low
- `ixRawFileImage`: not observed as a chart-class invariant

Therefore, chart root and sequence classes are not sample-specific. They are
high-confidence corpus-wide requirements for plain chart files.

## Variant Difference

`tags` and `lyric-ownership` both use the minimal chart form:

- chart contains loose `lpsLyricWordData`
- chart contains loose `lpsMelodyMarker`
- chart contains loose `lpsLyricMarker`
- no chart package/asset ownership
- no `ixChart` / `lpsChart`
- no `ixSequence`
- no `ixTempoMap`
- no `lpsMusicInfo` / `lpsMusicIndex`

`full-current` adds chart-side package/resource ownership:

- `ixTreeNode<ixPackage>`
- `ixPackage`
- `ixList<ixPackage *>`
- `ixVector<char>`
- `ixVector<ixPackage *>`
- `ixDblCnt<ixPackage *>`
- `ixVector<ixAsset *>`
- `ixAssetPackage`
- `ixAsset`

But `full-current` still lacks all high-confidence chart roots/sequences:

- no `ixChart`
- no `lpsChart`
- no `ixSequence`
- no `ixTempoMap`
- no `ixVector<ixSequence *>`
- no `ixVector<ixSeqCode *>`
- no `lpsMusicInfo`
- no `lpsMusicIndex`

This lines up with the observed behavior:

- without chart ownership, the game appears to reject the tiny chart safely
- with chart ownership, the game appears to traverse deeper into chart asset
  loading
- once traversal reaches expected chart root/sequence data, the synthetic object
  graph supplies no valid destination/vector/root object, leading to an invalid
  pointer passed into the copy routine at `0x82AB3284`

## Likely Bad Pointer Class

The crash is a null-address write inside a copy helper, so the most likely
high-level cause is a malformed destination container or missing owner object,
not lyric text or melody marker data.

Most suspicious chart-side fields:

- `ixChart.m_vpSequence` at offset `72`
- `ixChart.m_vpExtraSequence` at offset `88`
- `ixSequence.m_vpSeqCode` at offset `72`
- `ixSequence.m_vpListeners` at offset `88`
- `lpsChart.m_pIndex` at offset `144`
- `lpsChart.m_pMusicData` at offset `148`
- `ixVector<ixSequence *>` begin/reserve/size/capacity fields
- `ixVector<ixSeqCode *>` begin/reserve/size/capacity fields

Current synthetic `full-current` cannot populate those fields because it does
not emit those classes or owner objects yet.

## Next Minimal Fix Proposal

Do not change lyric ownership yet. The lyric-ownership variant now returns to
the menu, and the hard crash only appears when chart-side ownership is added.

Next minimal runtime step:

1. Add a new controlled variant, for example `chart-root-minimal`, rather than
   modifying all existing variants.
2. Keep the fixed lyric ownership exactly as-is.
3. Add the smallest chart root layer:
   - one `lpsChart`
   - its `ixChart` base fields
   - one valid `ixVector<ixSequence *>`
   - one minimal `ixTempoMap`
   - one minimal playable `ixSequence`
   - one valid `ixVector<ixSeqCode *>`
4. Put the existing MelodyMarkers and LyricMarkers into the sequence's
   `ixVector<ixSeqCode *>` rather than leaving them only as loose heap objects.
5. Add minimal `lpsMusicInfo` and `lpsMusicIndex`, or explicitly set
   `lpsChart.m_pIndex` and `lpsChart.m_pMusicData` to a real-file-compatible
   safe value after checking corpus pointer behavior.
6. Keep phrase/page/hit/short-end markers out of this iteration unless the game
   still rejects the root/sequence variant.

The key test is whether adding a valid chart root and sequence vector changes
the `full-current` behavior from hard crash back to safe rejection or load
progression.
