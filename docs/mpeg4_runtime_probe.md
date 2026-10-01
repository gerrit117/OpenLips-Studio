# OG Lips ASF runtime probes

## Scope

Measured on 2026-10-01 using the local OG Lips 0.0.0.20 executable
(`95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9`)
and an instrumented Xenia Canary based on
`aee0871dd7a783de7ec61dfbd5e9985977093025`.
Only the Amazing full-video test asset was swapped. Its chart, separate WMA
asset and preview video were not changed. The backup game directory was not
modified. These observations are not real-console or LS2 validation.

## Confirmed container failure

The initial FFmpeg probes mapped video before audio. In ASF this assigned
video stream ID 1 and audio stream ID 2. The working reference has the reverse
assignment: **audio 1, video 2**.

The native video initialization at `0x824B1E90` calls `0x824BD1A0` with
`r4=2`. The latter checks that the requested stream descriptor has type 2
(video), and returns 4 when it is missing or has the wrong type. The caller
then returns `0x8000FFFF`, eventually presented as Disc Read Error.

Both the old MP4S probe and the old WVC1/WMA Pro remux control failed this
way, before reaching the video FourCC selector. The control's encoded audio
and video packets were unchanged. Opens and initial 131072-byte reads
succeeded. Thus these failures were not evidence that the video codecs were
unsupported, nor evidence of a missing file or a different audio bitstream.

Preserving audio ID 1/video ID 2 makes the WVC1 remux control load gameplay.
The requested stream query and decoder setup now return zero. This paired
control is strong evidence for the stream-ID cause of the original rejection.

The existing local corpus inventory contains **137/137 video-containing
files** with audio ID 1/video ID 2: 107 under the OG backup, 20 under
Songdateien and 10 elsewhere. This counts files, not deduplicated songs;
copies may occur. Confidence is high for the inspected corpus, not a claim
about every Lips release.

Both experimental builders now preserve and verify reference stream IDs.
They refuse non-contiguous/two-stream layouts rather than silently renumbering
them. Synthetic tests cover ordering, invalid IDs and atomic refusal when
the generated IDs differ. Production Studio encoding is unchanged.

## Corrected probes

All MPEG-4 probes retain ASF and the reference WMA Pro encoded packets.
They are not MP4/H.264/AAC files. All fully decode with FFmpeg, which is
not a test of Microsoft's decoder or Lips playback behavior.

| Probe | Stream query | Native video setup | Observed gameplay |
|---|---|---|---|
| Old WVC1 remux, inverted IDs | 4 | `8000FFFF`, before selector | Disc Read Error |
| Old MP4S, inverted IDs | 4 | `8000FFFF`, before selector | Disc Read Error |
| Corrected WVC1 remux | 0 | 0 | Video, lyrics and notes load |
| Corrected MP4S | 0 | `80600005` then `8000FFFF` | Disc Read Error |
| Corrected MP43 | 0 | 0 | Notes/lyrics advance; video appears frozen |
| Corrected WVC1/WMA Standard | 0 | 0; audio setup also 0 | Notes/lyrics advance; video appears frozen |
| Original WVC1/WMA Pro | 0 | 0 | Animated video; notes/lyrics advance; results reached |
| WVC1 remux + video duration metadata | 0 | 0 | Brief scene changes, later frozen; black Loading/EOF |
| MP43 + video duration metadata | 0 | 0; 29.97 fps handoff | Notes/lyrics advance; later image unchanged |

For corrected MP4S, the selector at `0x824FBE28` sees `MP4S`; the core at
`0x8252D3C8` receives `MP4S` and dimensions 768x432. At `0x824FBE20`,
the return is `0x80600005`, with LR `0x824FBDE0`.
Bounded instruction inspection places that return after the additional
`0x82508DF0` setup/input-parsing path and its error conversion, rather than
the stream query or initial FourCC selection. That path fetches compressed
input and invokes further parsing. The exact rejected bitstream feature has
not been measured; do not label this as global MPEG-4 incompatibility.

Corrected MP43 reaches the same selector with `MP43` and exits video setup
with zero. The chart clock advances past 86 seconds and the lyric/note
display changes. However, two separated gameplay observations show the
same background frame. **Loading is not proof of animated video playback.**
Do not expose MP43 as a verified production codec on this evidence.
Later MP43 observations reached a black Loading screen and reads beyond EOF
(`C0000011`); a clean results transition was not observed.

The WMA Standard test keeps the original WVC1 compressed video packets and
changes audio to `wmav2` (`0x161`, stereo 48 kHz, 192 kbit/s). Audio initialization
at `0x824B307C` returns zero and the chart advances past 29 seconds, but the
video remains on its first frame. Audible audio was not independently verified.
This means the frozen frame cannot yet be attributed specifically to MP43.
Under exactly the same instrumented emulator, the unmodified original advances
through different video scenes and reaches Single Mode Results.

## Frame-duration metadata control

An additional read-only inventory of 127 video-containing files under the OG
backup and Songdateien found video Extended Stream Properties with
`Average Time Per Frame = 333667` (100 ns units) in **127/127** files, no parse
failures. Copies may occur; this is a file count, not unique songs. The corrected
FFmpeg remux and MP43 probes have no Extended Stream Properties objects.
The original Amazing also contains an audio extended stream, which is not
copied by the isolated video-duration probe.

The [FFmpeg ASF muxer source](https://www.ffmpeg.org/doxygen/trunk/asfenc_8c_source.html)
conditionally emits extended stream properties with language metadata and
writes zero for average frame time. This explains a container difference,
not yet its causal role in Lips.

`tools/analyze_asf.py` now reads bounded Header Extension children and reports
video/audio frame durations with exact field offsets.
`tools/probe_asf_frame_metadata.py` adds one minimal video Extended Stream
Properties object using the matching reference duration. It refuses existing
outputs, mismatched stream IDs/types, existing extended stream objects and
invalid durations. It updates header/file lengths, copies all post-header bytes
unchanged and validates them before atomic publication. This is an experimental
metadata control, not a production codec repair or a complete reference-header
reconstruction. Synthetic tests cover bounds, immutable inputs and unchanged
compressed data.

The WVC1 remux with this minimal metadata object initializes successfully and
changes background scenes briefly, but later separated observations at chart
times beyond 58 and 86 seconds show the same frame. It eventually enters black
Loading while the IO trace repeatedly reads beyond EOF (`C0000011`). Thus this
metadata-only addition is **not sufficient** for sustained playback or cleanup.
The original completed normally under the same instrumentation. Do not report
the brief initial changes as a fixed video pipeline.

Static inspection of `0x824BD1A0` shows a nonzero extended-stream frame duration
converted into a floating frame rate, propagated by `0x824B1E90` into
`0x824AF788`. The latest read-only register trace additionally logs floating
registers at that handoff and both present/missing-duration paths. The original
extended video stream also advertises one payload extension; the minimal probe
does not reproduce it. Payload timing/extension interpretation remains an open
question, not a confirmed explanation of the freeze.

The MP43 metadata probe reaches `0x824BD2DC` with duration 333667 and
`f13=29.969999313354492`; at `0x824B209C`, `f1` carries that same frame rate
into the video handoff. The selector receives `MP43` and setup returns zero.
This directly confirms the new metadata is consumed, rather than merely present
in the file. Separated gameplay observations still show the same background
while the chart advances past 86 seconds, so this addition does not fix MP43
playback either. FFmpeg fully decodes both metadata probes without errors.

## Read-only instrumentation

`tools/ghidra/StudyOgCodecProbeSites.java` requires the exact executable hash,
uses `.pdata` boundaries and writes private instruction exports. Run using
Ghidra 12.1.3 `analyzeHeadless -process default.xex -readOnly -noanalysis`.
No game instructions are included in this report or committed exports.

`tools/xenia/og_codec_register_trace.patch` is a **cumulative alternative**
CPU instrumentation patch, including the earlier clock probes. Do not apply
it on top of overlapping clock/failure CPU patches. The optional trace is
enabled with `--lips_codec_trace_path`; it captures bounded register snapshots
and guarded descriptor reads, without guest writes or forced success results.
It is address-specific: only enable it for the executable hash above.
The patch itself does not perform automatic executable hash verification.
The existing media-IO instrumentation is separate.

`tools/xenia/mic_request_quiet.patch` changes an unconditional microphone
request log from error to debug level. This prevents multi-gigabyte log spam
at log level 0; it does not change the guest API return value or input state.

Private artifacts:

- `private/outputs/amazing-mpeg4-streamids-20261001/`: corrected video probes.
- `private/outputs/amazing-audio-streamids-20261001/`: corrected audio probes.
- `private/outputs/{remux,mp4s,mp43}-fixed-native-registers-20261001.txt`:
  native snapshots; similarly named IO logs and clock traces.
- `private/outputs/{original,remux-frame,mp43-frame}-native-registers-20261001.txt`:
  original and metadata-control snapshots, similarly named IO/clock traces.
- `private/outputs/asf-frame-metadata-{og,songdateien}-corpus-20261001.json`:
  read-only inventory summaries including file lists and frame-duration counts.

Generated preparation reports deliberately say `game_acceptance=not_tested`:
they describe the builder stage. This report records the subsequent runtime
observations without pretending that preparation alone validates playback.

## Remaining gates

The next controlled comparison should trace compressed-payload dispatch,
per-frame decode results and presentation timestamps for original versus remux.
The current snapshots cover initialization, not that delivery loop. Isolate
the MP4S setup/input-parser rejection separately. MP42 with corrected IDs has
not yet had a runtime test. No codec is promoted on partial initialization.
Audio and video do not need to be the same codec; preserving container
stream references is a separate requirement. A complete portable pipeline
needs both video and audio acceptance, advancing video, chart synchronization,
end-of-song/cleanup and real-console testing. No game decoder has been patched.

Checkpoint: Python suite 282 passed, 3 skipped, 11 subtests passed. The updated
Xenia trace builds successfully; both instrumentation patches pass reverse-apply
checks against the tested source. Media, binaries and raw game-code/log exports
remain private. Xenia was closed and the Amazing full video restored byte-for-byte
to the original after these tests; chart, audio and preview were left unchanged.
