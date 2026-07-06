# Lips 1 Target Profile

This note summarizes the current local sample comparison for choosing a
Lips-1-style output format as the first custom chart writer target.

## Local Sample Families

Available chart samples under `private/samples` currently split into two
families:

| Family | Samples | `ixChart` | `lpsChart` | `lpsMelodyMarker` | `lpsPhraseMarker` | Music metadata |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Lips 1 / compact | `99 Luftballons`, `You've Lost That Lovin` | 92 | 148 | 36 | 36 | `lpsMusicInfo` 272, `lpsMusicIndex` 536 |
| Later / LS2 extended | `Any Dream Will Do`, `Everything About You`, `I Don't Want To Wait`, `The Phantom Of The Opera` | 108 | 184 | 40 | 40 | `lpsMusicInfo` 296, `lpsMusicIndex` 608, plus `ls2MusicData` |

The compact family is the better first writer target because it has fewer
runtime-facing fields and no LS2-specific music data layer.

## Compact Chart Shape

Common compact classes observed in the two Lips-1-style chart examples:

- `ixChart` with `m_vpSequence` at offset `72` and `m_MusicStartOffset` at
  offset `88`
- `lpsChart` with `m_strNoiseMaker`, `m_BaseCentOffset`, `m_pIndex`,
  `m_strAudioEffectPresetPath`, and `m_strLyricPathCash`
- `ixSequence`, `ixTempoMap`, `ixVector<ixSequence *>`, and
  `ixVector<ixSeqCode *>`
- `lpsMelodyMarker`, `lpsLyricMarker`, `lpsPhraseMarker`,
  `lpsPageBreakMarker`, and `lpsShortEndMarker`
- LED/audio sequence classes: `lpsLedMasterSequence`, `lpsLedSequence`,
  `lpsLedMarker`, `lpsLedLoopMarker`, `lpsLedLoopSequence`,
  `ixAudioEffectSequence`, and `ixAudioMarker`

The compact samples do not define the LS2-only marker/data classes listed
below.

## Later / LS2 Additions To Exclude Initially

The later-family charts add or commonly use:

- `ls2MusicData`
- `ls2DbRecord`
- `lpsTimedGestureMarker`
- `lpsTimedNoisemakerMarker`
- `lpsHitMarker`
- `ixChart.m_vpExtraSequence`
- `lpsChart.m_strNoiseMakerForLS2`
- `lpsChart.m_pMusicData`
- extra fields in `lpsMusicInfo`, `lpsMusicIndex`, and
  `lpsLedMasterSequence`

These are the strongest current candidates for the "quick action" / later-game
behavior layer. They should be parsed and reported, but excluded from the first
from-scratch writer profile.

## Lyric Files

The matching lyric samples are consistent:

- each supported matching lyric file has two `Text` resources
- the visible lyric resource is selected correctly by chart
  `LyricWordData` coverage
- the smaller second `Text` resource has low coverage and should not be used as
  visible lyric text

For the first writer, keep the current rule: choose the `_Lyric.X360` text
resource by `LyricWordData` coverage, then write only inside that real payload
boundary.

## Recommended Next Work

1. Add a chart-family analyzer that reports compact vs LS2 layout, class sizes,
   LS2-only classes, and counts of phrase/page/short/hit/gesture/noisemaker
   markers.
2. Use `99 Luftballons` and `You've Lost That Lovin` as the initial compact
   profile corpus.
3. Implement a compact-only synthetic variant instead of extending the current
   LS2-style `chart-root-minimal` path.
4. Generate a compact chart root with no LS2 `m_vpExtraSequence`, no
   `m_pMusicData`, no `ls2MusicData`, no timed gestures, and no timed
   noisemakers.
5. Add only the minimum gameplay structures first: chart root, one tempo map,
   one vocal sequence, melody/lyric/phrase/page/short-end markers, and lyric
   word data.
6. Treat LED/audio/noisemaker content as optional decoration until the vocal
   chart loads and plays.

The key rule: do not mix compact and extended fields in one synthetic file.
The first writer should deliberately target the compact Lips-1 family.
