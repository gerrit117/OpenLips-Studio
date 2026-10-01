# Integrated AI chart creation: source review and proposal

Research snapshot, 2026-10-01. This document proposes a built-in, optional
Studio feature, not a new plugin. No AI runtime was installed or executed,
and no third-party code or model was incorporated in this pass.

## Reviewed projects

[UltraSinger](https://github.com/rakuri255/UltraSinger) provides an existing
music-to-chart pipeline. Source reviewed: device detection, vocal separation,
Whisper transcription/alignment, pitch tracking, hyphenation, dependency
manifest and license. The current code uses Demucs, WhisperX and SwiftF0;
older descriptions of its CREPE pipeline should not be treated as current.

[UltraSinger Studio](https://github.com/lazinessss999-dot/UltraSinger_studio-v1.0)
adds a browser interface, installation helpers, presets, external lyrics and
LRC handling. At review time the repository tree contains README, changelog,
license and a source ZIP, rather than independently browsable application
modules. The ZIP was inspected locally without extracting or executing its
installer or bundled virtual environment. Reviewed sources include
`web/lyrics_finder.py`, `web/pipeline_launcher.py` and the vendored lyrics parser.
Its Windows-oriented installation is not a ready cross-platform Studio backend.

Both top-level projects declare MIT licenses:
[UltraSinger license](https://github.com/rakuri255/UltraSinger/blob/main/LICENSE),
[Studio license](https://github.com/lazinessss999-dot/UltraSinger_studio-v1.0/blob/main/LICENSE).
Reuse can be considered with retained notices and attribution. This does not
license every dependency, model weight or retrieved lyric. Audit these
separately before distribution; retain upstream authors' credits in About,
third-party notices and documentation. Do not redistribute the bundled venv.

## Recommendation

Implement a native Studio workflow using small backend adapters, rather than
embedding the foreign web app or importing its full CLI into the Qt process:

1. Select reference audio/video and optional existing vocal stem.
2. Select lyric source: user text, local LRC, consent-based LRCLIB lookup,
   or transcription. Preserve supplied text instead of replacing it with ASR.
3. Separate vocals if needed; skip when a usable isolated stem is supplied.
4. Transcribe only if lyrics are missing. Align known words inside trusted
   line windows; transcription and forced alignment are different operations.
5. Extract voiced F0 and segment musical notes. Combine word/phoneme timing
   with note boundaries, including one syllable held across multiple pitches.
6. Present a preview with uncertain words, octave jumps and very short notes
   flagged. Accept into the existing editor as one undoable operation.
7. Save to `.olp`; export through the existing Lips writer and media pipeline.

Use a built-in feature with a separately managed worker process/runtime:
integrated UI does not require putting Torch/native inference libraries in the
main GUI interpreter. This also accommodates the reviewed upstream manifest's
Python `>=3.12,<3.14` requirement without breaking the current local 3.14 tools.
Workers need versioned structured results, cancellation, progress, resource
limits and no silent edits to an existing project.

The editor already supplies notes, timing, lyrics, phrase breaks, media preview,
undo and projects. Add an analysis dialog and review overlay, not another editor.
Suggested controls: Fast/Balanced/Quality presets; advanced per-stage model,
language, device, batch/chunk size and precision; separation toggle; pitch range;
minimum-note/merge settings; optional key quantization; model-cache management.

## Models and limitations

| Stage | Initial recommendation | Alternatives and cautions |
|---|---|---|
| Separation | Demucs `htdemucs`, optional | Fine-tuned variant for quality; BS-RoFormer/MelBand-RoFormer candidates need song benchmarks, licensing and memory review |
| ASR | Whisper small/base for modest hardware; large-v3 option | faster-whisper for CUDA/CPU; whisper.cpp for broader acceleration; bigger is not automatically better for sung words |
| Alignment | Language-specific WhisperX alignment | CPU fallback; verify singing/elongated vowels; don't silently invent timings for dropped words |
| Pitch | SwiftF0 CPU-first | torchcrepe comparison backend; RMVPE candidate after code/weight/license review; Basic Pitch remains useful for MIDI but isn't the sole vocal F0 method |
| Note segmentation | Stable F0 segments plus aligned syllables | Gate unvoiced/instrumental frames, smooth vibrato, preserve real pitch changes and repeated-note articulation |

SwiftF0's [current upstream API](https://github.com/lars76/swift-f0)
includes note segmentation, a 16 ms frame period and a small ONNX model.
Its published benchmark is not our accuracy measurement on Lips songs.
Use actual returned timestamps, not an assumed hop duration. The reviewed
UltraSinger adapter uses an older constructor/call style and describes the
256/16000 hop as approximately 62.5 ms: that arithmetic would be **16 ms**
(62.5 frames/second), so do not carry that comment into Studio. Pin and test
backend versions instead of assuming the adapter matches current SwiftF0.

Another portability/security concern: the reviewed Whisper module temporarily
monkey-patches `torch.load` to force `weights_only=False`. Do not copy a global
override into Studio. Only load trusted, pinned model artifacts; isolate any
necessary compatibility behavior. No arbitrary remote-code-enabled models.

Do not enable forced key quantization by default without review: chromatic notes
and modulations are real music, not necessarily detector errors. Dictionary
hyphenation alone does not locate sung syllables. Uniform word division and
silently interpolated alignment failures must be labelled estimates.

## Hardware acceleration and fallback

Acceleration is chosen **per stage**, not with one CUDA/CPU switch. Upstream
UltraSinger's device detector checks CUDA only, so unchanged it does not exploit
Apple Metal or AMD/Intel GPU backends. CPU remains the baseline for every stage.

| System/hardware | Practical candidates | Limits |
|---|---|---|
| Windows/Linux NVIDIA | faster-whisper/CTranslate2 CUDA; Torch CUDA for supported stages | Probe actual driver, compute capability and precision; legacy GPUs need compatible builds |
| macOS Apple Silicon | whisper.cpp Metal/Core ML; Torch MPS for compatible separation/alignment stages | CTranslate2 CUDA cannot become Metal by passing `mps`; test each adapter's operators |
| Windows/Linux AMD/Intel | whisper.cpp Vulkan; appropriate ROCm or other tested providers | Not universal GPU support for the full pipeline; model/backend/build specific |
| Any supported system | CPU/int8 ASR where supported; SwiftF0 CPU; chunked separation/alignment | Slower heavy stages; disclose time/memory estimates and avoid promising real time |

References: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[whisper.cpp backends](https://github.com/ggml-org/whisper.cpp),
[WhisperX](https://github.com/m-bain/whisperX),
[ONNX Runtime providers](https://onnxruntime.ai/docs/execution-providers/).
Availability of a provider is not proof a particular model runs on it.

Probe with a small actual inference, not just GPU enumeration. On allocation
failure, release the failed worker, lower batch/chunk size or model size, then
offer CPU fallback without losing the project. Report the actual backend used.
Process stages sequentially and unload large models to reduce peak memory.
CPU/GPU selection mainly affects execution; do not promise higher quality simply
because a GPU is present.

## LRC integration

Studio already performs explicit-consent LRCLIB searches, but currently consumes
plain lyrics; it does **not yet** import or retain synchronized LRC cues.
Use synchronized lyrics as a first-class input, not as disposable plain text.

- Support UTF-8/BOM, line timestamps, metadata, repeated timestamps and `[offset:]`.
  Preserve repeated chorus occurrences. Timestamp offsets are separate from
  media offsets; document their sign and apply exactly once.
- Support enhanced per-word `<mm:ss.xx>` cues where present. Preserve source
  precision and distinguish supplied starts from inferred ends.
- Plain LRC supplies line start times, not exact word/syllable durations or
  pitch. It can skip text recognition, but usually **not word alignment**.
- Enhanced LRC can supply word anchors, but still lacks sung F0, reliable
  note ends, phoneme segmentation and melisma mapping.
- Retain original cues/source provenance in the project. Map them to existing
  notes, or combine with new pitch analysis; never create invented pitches
  silently. Line/phrase cues suggest breaks but are not automatically optimal
  Lips page-switch times.
- Validate the recording/version: radio edit, video intro, remix and live lyrics
  can differ. Show matches and uncovered sections before accepting.
- LRCLIB lookup should match artist/title, duration and version, let users choose
  a result and record attribution. Public access is not a grant to redistribute
  copyrighted lyrics. Keep local files/manual input working offline.

The fork's LRC helpers are a useful reference, not a normative universal LRC
specification. Its heuristic/fallback interpolation needs review before adoption.

## Intermediate format

For the initial compatibility experiment, existing UltraSinger TXT output can
pass through our existing UltraStar importer. That is a fast way to benchmark
real songs without rewriting its full pipeline.

For the integrated feature, use **analysis data -> StudioProject/internal
SongChart -> Lips**. Preserve absolute seconds, confidence, original lyric cues,
phrase information and pitch contours. Do not force analysis through beat-grid
TXT: it can quantize timing and lose uncertainty/provenance. UltraStar TXT and
MIDI should remain optional interchange/export formats, not required hops.

## Scoring

Lips computes the player's score during gameplay. Read-only OG Lua inspection
shows the score display reading `GetChartGrader(...):GetTotalScore()`, and
history querying `GetTotalScoreWithStars()`, `GetTotalPossibleScore()` and
`GetPossibleMarkerScore()`. Diagnostics query live pitch distance, pitch-perfect
multiplier, hit combo and vibrato combo. No original scripts are distributed.

Charts provide the reference notes, durations and gameplay events that the
grader evaluates; they do not contain a pre-awarded score for a player's future
performance. Chart structure/bonuses can influence possible points. The exact
native formula and complete marker weighting have **not** been established, nor
has microphone scoring of a custom chart been exhaustively validated.

UltraStar similarly computes scores at runtime. Its TXT note types/durations
affect scoring (e.g. golden versus freestyle), not a fixed earned point number
per line. See the [format specification](https://usdx.eu/format/) and
[USDX score code](https://github.com/UltraStar-Deluxe/USDX/blob/master/src/base/USingScores.pas).
Do not copy UltraSinger's UltraStar score estimate into Lips as an authoritative
score: the games have different rules. Studio can offer reference-pitch and
chart-quality checks before implementing a separately validated Lips estimator.

## Delivery order

1. LRC parsing/cue persistence and user-text alignment workflow.
2. Isolated CPU-first SwiftF0 analysis, note segmentation and editable preview.
3. Optional separation and selectable transcription/alignment runtimes.
4. Hardware-specific validated builds, presets and recovery tests.
5. End-to-end new-chart gameplay and microphone-scoring checks.

This is an integration recommendation, not an implemented AI assistant or LRC
import release. It is independent of the MPEG-4 gameplay acceptance experiment.
