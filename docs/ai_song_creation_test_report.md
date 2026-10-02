# AI chart creation: test report

Date: 2026-10-01. Version: 0.3.0 Beta. Local recordings and generated song
projects remain private; no copyrighted fixtures are committed.

## Implemented

- Built-in Tools -> Create chart from audio (AI), not a plugin.
- Local SwiftF0 pitch detection and segmentation, using its bundled 135,090-byte
  ONNX model. Main Studio does not import Torch/Demucs/Whisper.
- Optional independent Demucs htdemucs / faster-whisper engine, with tiny,
  base, small, medium and large-v3 model choices. Larger models download/cache
  on demand; no separate Python is needed for a native engine package.
- CPU baseline; per-stage CUDA/MPS probing and RuntimeError CPU retries.
  Actual GPU execution is **not tested on this machine**. Radeon does not imply
  CUDA support; SwiftF0 and Metal ASR use CPU.
- LRC anchors or ASR word estimates, explicit whole-line/melisma warnings,
  background progress/cancel, review, accept, undo and `.olp` persistence.
- One-note-per-word exportable draft, or detailed pitch contour for editing.
  Neither option is a claim of automatic phonetic syllabification.
- Optional EN/DE Wav2Vec2 CTC word alignment inside existing LRC windows,
  preserving supplied text and refusing unsupported token mappings.
- Windows installer recipe and native macOS DMG recipe, plus portable Linux.

## Actual song benchmarks

Hardware: Ryzen 7 5800X3D, 64 GB RAM, Radeon RX 7900 XTX; **CPU used**.
Audio came from the re-extracted known-original OG backup. Demucs used shifts=0;
Whisper int8 CPU and English language; SwiftF0 supplied measured pitch spans.
Wall times below exclude first model downloads and are not portable guarantees.

| Input / duration | Stages | Notes before optional word simplification | Time | Normal-track word error rate |
|---|---|---:|---:|---:|
| Amazing / first 60 s | mixed audio, SwiftF0 only | 101 | 0.437 s | Not applicable |
| Amazing / first 60 s | htdemucs + Whisper base + SwiftF0 | 117 | 36.453 s | 73.1% |
| Amazing / first 60 s | htdemucs + Whisper small + SwiftF0 | 127 | 36.625 s | 47.3% |
| Amazing / full 190.774 s | htdemucs + Whisper small + SwiftF0 | 437 | 88.125 s | 46.3% |
| ABC / first 60 s | htdemucs + Whisper small + SwiftF0, word layout | 132 | 56.063 s | 62.4% |

Reference text is resolved structurally from the lyric resource selected by
WordData coverage, and compared separately per sequence. Duplicate duet lyrics
are **not** concatenated into the single-player reference. WER lowercases and
ignores punctuation; syllable splits, backing vocals and arrangement differences
can still influence it. This small benchmark is not an accuracy leaderboard.

**The recognition is not reliable enough to accept unreviewed.** Small improved
over base on this example but both omit/substitute sung words. Known lyrics/LRC
are a sensible fallback. Pitch-only mix detection can follow instruments;
separation is recommended, but no vocal-pitch accuracy percentage is established
without manual or ground-truth note alignment. Accurate automatic syllable
alignment remains open. Experimental CTC word alignment was then tested against
93 known Amazing words in sixteen six-word windows: all 93 texts survived, but
median absolute start-time difference from the original chart was **0.506 s**,
with a **4.054 s** maximum. This is not sufficient to declare accurate automatic
singing timing. Preserving supplied text is not ASR accuracy: WER against a
forced transcript would be meaningless. The English alignment model is roughly
360 MiB and downloads on demand.

## Automated and frozen tests

The synthetic regression suite exercises overlap rejection, word boundaries,
melismas, LRC clipping, WER, project round trips, GUI acceptance/cancellation/undo,
and real isolated inference on original generated tones (220 / 293.6648 Hz).
The frozen Studio worker also recovered MIDI pitches 57 and 62 without external
Python or model downloads. Packaging failures (missing distribution metadata
and NumPy compatibility modules used by serialized Demucs models) were caught
by inference smoke tests and fixed; successful compilation alone is insufficient.
The standalone frozen engine also performed actual Amazing vocal separation,
Whisper-small transcription and pitch analysis (first 60 seconds, 42.015 s,
33 simplified word notes), verifying usable native runtime dependencies.

Read-only corpus analysis covers 211 physical charts / 130 distinct contents;
129 plain IXB charts parse without graph errors. See [LS2 findings](ls2_song_variants.md).
All four native CI targets and the download publication completed successfully;
see [release verification](studio_release_verification_030.md) for exact checks.
These native smoke tests do not replace physical Xbox or full gameplay tests.

Local suite: **328 passed, 6 skipped, 11 subtests passed**. The skips are
explicit platform/optional-integration checks, not passing results. The private
new Amazing chart structurally contains 773/773 parsed objects, 220 MelodyMarkers,
220 LyricMarkers and zero graph errors. The baseline/AI/restore cycle was actually
executed without launching the emulator, and both original file hashes were
restored exactly. No sample or media file was left modified.

## Prepared local gameplay test

The new private Amazing pair is generated from the complete AI analysis with
**220 word notes** and the original **190.774-second** media duration. Chart and
lyric heaps are newly serialized; no template heap is copied. Audio/video,
database, cover and previews are deliberately untouched, so timing/content can
be judged against the original recording in the existing Amazing slot.

The Desktop `OpenLips Tests` folder contains:

1. `01-Original-Amazing.cmd`: install the known-original chart/lyrics and launch
   the extracted game. Select Amazing and note baseline timing/page behavior.
2. `02-AI-Amazing.cmd`: install the new AI pair and launch the same game.
   Check whether notes/lyrics advance throughout the song, obvious wrong words,
   octave errors, note lengths, page changes and end behavior.
3. `03-Dateien-wiederherstellen.cmd`: restore exactly the pre-test chart/lyrics.
4. `04-Original-ISO.cmd`: launch the untouched OG ISO, with no loose-file edits.
5. `05-Number-One-Hits-ISO.cmd`: boot NoH for comparison only. The previously
   observed loading stall is **not claimed fixed**.
6. `06-KI-Chart-in-Studio.cmd`: open the editable AI result in the new Studio.

**Close Xenia before switching files.** The launcher creates hash-checked backups,
refuses unexpected manual edits, and rolls back both targets on a failed switch.
It never changes an ISO. Patched loose files require booting the extracted XEX;
booting the original ISO cannot see them. Restoring returns to the exact state
before the first test, which may already differ from the original baseline.

## What the user still needs to check

- In-game start, complete playback, page timing and microphone scoring of this
  newly generated AI pair. Structural validation is not in-game acceptance.
- Listen to lyric/pitch mistakes; try known enhanced LRC from the same recording.
  Compare editor reference offset separately from exported chart-time shifts.
- Windows wizard install/uninstall and project association on a normal account.
- macOS DMG drag/install, Intel/Apple Silicon startup, Linux desktop integration,
  native optional engine and hardware-specific acceleration.
- NoH loading, timed actions, duet/player routing, short-mode end/extension,
  newly registered overview media, and the separate 600-DLC baseline.

Do not upload original recordings, game Lua, XEX files or lyric dumps with bug
reports. Report version, selected models/device, logs and a synthetic reproduction.
