# Chart Root Minimal Variant Report

This report records the corpus evidence behind the synthetic
`chart-root-minimal` variant in `tools/build_minimal_ixb_pair.py`.

The goal of this variant is intentionally narrow: keep the fixed lyric
ownership behavior unchanged, then add the smallest chart root and one sequence
owner around the existing tiny MelodyMarker/LyricMarker set. It is a diagnostic
variant, not a complete custom chart runtime reconstruction.

## Corpus Scope

Sample directory:

- `private/samples/charts`

Samples scanned:

- chart samples found: 59
- plain IXB charts parsed: 58/59
- unsupported/compressed chart: 1/59, `Irreplaceable.X360`

Confidence levels:

- high: present in at least 90% of applicable plain IXB samples
- medium: present in at least 50% of applicable plain IXB samples
- low: present in less than 50% of applicable plain IXB samples

## Required Class Inventory

Across the 58 supported plain IXB chart samples:

| Structure | Occurrence | Confidence |
| --- | ---: | --- |
| `ixChart` | 58/58 | high |
| `lpsChart` | 58/58 | high |
| `ixSequence` | 58/58 | high |
| `ixTempoMap` | 58/58 | high |
| `ixVector<ixSequence *>` | 58/58 | high |
| `ixVector<ixSeqCode *>` | 58/58 | high |
| `ixSeqCode` | 58/58 | high |
| `lpsMusicInfo` | 58/58 | high |
| `lpsMusicIndex` | 58/58 | high |
| `ixAssetPackage` | 58/58 | high |
| `ixAsset` | 58/58 | high |
| `ixFileImage` | 2/58 | low |
| `ixRawFileImage` | 0/58 | low for chart files |

Conclusion: chart root and sequence classes are corpus-wide chart requirements;
chart-side `ixRawFileImage` is not.

## Layout Families

The corpus has two `ixChart` / `lpsChart` layout families.

| Layout | Occurrence | Pattern | Confidence |
| --- | ---: | --- | --- |
| compact | 42/58 | `ixChart` size 92, `lpsChart` size 148 | medium |
| extended | 16/58 | `ixChart` size 108, `lpsChart` size 184 | low corpus-wide, high within this family |

Extended-layout examples include `1234.X360`, `Any Dream Will Do.X360`,
`Everything About You.X360`, `The Phantom Of The Opera.X360`, and other
DLC/later-style samples. The new synthetic variant deliberately follows this
extended layout because the current controlled testing has focused on `1234`
and the requested fields at offsets `144` and `148` only exist in this family.

## Relevant Field Evidence

| Field | Occurrence | Common offset/pattern | Confidence | Chosen synthetic value |
| --- | ---: | --- | --- | --- |
| `ixChart.m_vpSequence` | 58/58 | offset `72` | high | vector tuple `data=0x05001100 reserve=32 size=2 allocator=0` |
| `ixChart.m_vpExtraSequence` | 16/58 | offset `88` in extended layout only | low corpus-wide, high extended-family | empty vector tuple `0,0,0,0` |
| `ixSequence.m_vpSeqCode` | 58/58 | offset `72` | high | vector tuple `data=0x05001500 reserve=32 size=2*N allocator=0` |
| `ixSequence.m_vpListeners` | 58/58 | offset `88` | high | empty vector tuple `0,0,0,0` |
| `lpsChart.m_pIndex` | 42/58 compact at `112`; 16/58 extended at `144` | required in both families, offset differs | high required, medium offset split | `0x05001800 -> lpsMusicIndex` at extended offset `144` |
| `lpsChart.m_pMusicData` | 16/58 | offset `148` in extended layout only | low corpus-wide, high extended-family | `0x05001700 -> lpsMusicInfo` |
| `ixVector<ixSequence *>` fields | 58/58 | `_data=0`, `_reserve=4`, `_size=8`, `_allocator=12` | high | separate backing object with two entries |
| `ixVector<ixSeqCode *>` fields | 58/58 | `_data=0`, `_reserve=4`, `_size=8`, `_allocator=12` | high | separate backing object with Melody/Lyric marker entries |
| `lpsMusicInfo` | 42/58 size 272; 16/58 size 296 | size differs by family | high required, medium layout split | minimal extended-family size 296 |
| `lpsMusicIndex` | 42/58 size 536; 16/58 size 608 | size differs by family | high required, medium layout split | minimal extended-family size 608 |

The raw object field walker is still not trusted enough to infer exact runtime
pointer values from arbitrary samples. The high-confidence data here comes from
the parsed schema/class/member definitions across all plain chart samples.

## Isolation Variant Field Choices

After the `chart-root-minimal` Xbox test still hard-crashed, but at a different
offset inside the same copy helper, the builder gained controlled isolation
variants. These do not add new chart classes. They reuse the same extended
layout and vary only the suspected vector sizes or music pointers.

The same corpus scan above guides these choices:

- `ixChart.m_vpSequence` exists in 58/58 plain chart schemas at offset `72`
- `ixSequence.m_vpSeqCode` exists in 58/58 plain chart schemas at offset `72`
- `ixSequence.m_vpListeners` exists in 58/58 plain chart schemas at offset `88`
- `lpsChart.m_pIndex` exists in 58/58, but its offset is layout-dependent
- `lpsChart.m_pMusicData` exists only in the extended family, 16/58

The variants intentionally keep the extended family because the current
synthetic test fixture and the crash report are based on the extended-layout
`1234` path.

| Variant | `ixChart.m_vpSequence` | `ixSequence.m_vpSeqCode` | Music pointers | Purpose |
| --- | --- | --- | --- | --- |
| `chart-root-minimal` | size `2`: tempo map + sequence | size `6`: all Melody/Lyric markers | index + music data | current crashing baseline |
| `chart-root-empty-sequence-vector` | size `0`, no sequence entries | omitted, no sequence owner | index + music data | test whether any sequence traversal triggers the crash |
| `chart-root-empty-seqcode-vector` | size `1`: one sequence | size `0` | index + music data | test whether seq-code traversal triggers the crash |
| `chart-root-one-seqcode` | size `1`: one sequence | size `1`: first MelodyMarker | index + music data | test whether one seq-code entry is already enough |
| `chart-root-no-music-pointers` | same as baseline | same as baseline | both null | test music pointer traversal as a trigger |
| `chart-root-index-only` | same as baseline | same as baseline | index only | split `lpsMusicIndex` from `lpsMusicInfo` |
| `chart-root-musicdata-only` | same as baseline | same as baseline | music data only | split `lpsMusicInfo` from `lpsMusicIndex` |

The music-pointer isolation variants still emit the minimal `lpsMusicInfo` and
`lpsMusicIndex` objects so the only intended behavioral difference is whether
`lpsChart` points at them. If all three music-pointer variants crash the same
way, construction of those minimal objects or vector traversal is more likely
than pointer traversal alone.

## Implemented Variant

`--synthetic-level chart-root-minimal` is based on the fixed
`lyric-ownership` behavior and does not change the lyric ownership chain.

Chart additions:

- one `lpsChart` object with extended-family `ixChart` base fields
- one `ixVector<ixSequence *>` backing object
- one minimal `ixTempoMap`
- one minimal `ixSequence`
- one `ixVector<ixSeqCode *>` backing object
- one minimal `lpsMusicInfo`
- one minimal `lpsMusicIndex`

The existing synthetic MelodyMarkers and LyricMarkers are inserted into the
sequence code vector in chronological object order:

- `lpsMelodyMarker[0]`
- `lpsLyricMarker[0]`
- `lpsMelodyMarker[1]`
- `lpsLyricMarker[1]`
- and so on

No duplicate mode, duet, short/full, phrase, page-break, hit-marker,
controller, audio-effect, or LED sequences are generated in this iteration.

## Generated Debug Output

The builder now prints, for every chart-root variant:

- chart root object offsets
- sequence object offsets
- backing vector object fields
- `ixChart.m_vpSequence`
- `ixChart.m_vpExtraSequence`
- `ixSequence.m_vpSeqCode`
- `ixSequence.m_vpListeners`
- `lpsChart.m_pIndex`
- `lpsChart.m_pMusicData`
- seq-code count inserted
- whether required synthetic references resolve to emitted objects

Example command:

```powershell
py tools\build_minimal_ixb_pair.py `
  --synthetic-level all `
  --out-dir private\outputs\minimal_ixb_variants `
  --stem 1234 `
  --force
```

Generated files remain under `private/outputs` and should not be committed.

## Next Xbox Test Interpretation

If `chart-root-minimal` changes behavior from hard crash to safe rejection or
deeper load progression, the crash is likely tied to missing chart root /
sequence ownership.

If it still hard-crashes, the next suspects are:

- the synthetic vector backing-object representation is still not matching the
  real file-layout representation closely enough
- `ixChart.m_vpSequence` may require a different entry set than just tempo map
  plus one sequence
- the extended-family `lpsMusicInfo` / `lpsMusicIndex` objects need more
  non-empty URI/string fields
- required controller/section/tempo marker objects may be mandatory even for a
  tiny playable chart

The compact 42/58 layout should be treated as a separate future variant rather
than folded into this minimal extended-family experiment.
