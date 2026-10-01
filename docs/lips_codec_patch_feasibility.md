# Alternative decoder feasibility in Lips

Read-only investigation, 2026-10-01. No game, media, profile, production
encoder or saved Ghidra project was changed. This is an optional game-modification
research track, not a new format accepted by the stock-game builder.

## Result

Xbox 360 software decoder ports exist. An additional decoder inside Lips is
technically plausible, but not implemented or runtime-verified here. More
importantly, the OG executable contains a video selector for additional legacy
formats beyond the WVC1/WMV3 assets observed in the corpus. Test those formats
with controlled inputs before committing to a new H.264 decoder port.

Changing a filename or adding a FourCC case alone does not implement a decoder.
Dashboard playback support also does not establish support inside a title.

## Scope and confidence

- Native analysis: **one OG 2008 executable**, SHA-256
  `95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9`.
  Addresses below are virtual addresses for this image only.
- Media evidence: **591 available paths**, with duplicate copies, from the
  [corpus census](media_codec_corpus.md). All 137 video streams observed are
  WVC1 (115) or WMV3 (22). No corpus file proves H.264 or WMV2 gameplay support.
- Tooling: Ghidra 12.1.3/XEXLoaderWV, read-only project processing, bounded
  function reconstruction using `.pdata`, existing save-GPR analysis fixups.
- Local SDK inspection: XMedia2 headers, sample entry points and library symbol
  inventory. This is a newer SDK than OG; it does not establish exact ABI identity.
- High confidence: selector constants and construction calls in this image.
  Medium: inferred decoder roles from construction/vtables/library symbols.
  Low/unverified: additional format gameplay acceptance and real-console speed.
- No equivalent native survey of NoH/LS2 was performed in this pass. Do not
  transfer addresses or decoder assumptions to those titles.

## Native movie path

| Address | Observation |
|---|---|
| `0x82420768` | Engine movie opening; player stored at object `+0x58` |
| `0x82421108` | Movie start/state handling; `ixXMVPlayer_MainLoop` worker |
| `0x824AA740` | Player factory; selects file/memory/user-I/O input |
| `0x824AA268` | Builds stream, decoder, renderer and player pipeline |
| `0x824B2478` | Candidate video decoder constructor; vtable `0x82008698` |
| `0x824B39E0` | Candidate audio decoder constructor; vtable `0x820087D0` |
| `0x824B23B8` | Video vtable `+0x44`: retains input and initializes context |
| `0x824BCBC8` | Creates decoder context via `0x824C5D90`/`0x824BC368` |
| `0x824B1E90` | Initializes stream/decoder information through `0x824BCC48` |
| `0x824FBE28` | Video format predicate and decoder callback-table selection |
| `0x824FBAD8` | Selected decoder creation; metadata/extradata/context setup |
| `0x82508B58` | WMV-family core initialization; calls `0x82507E00` |

The construction and input-connect paths are traced. The last indirect
dispatch from that path to `0x824FBE28` is **not yet proven**: Ghidra did not
recover a direct reference to the selector, though its own callback reference
to `0x824FBAD8` is recovered. Treat this as strong decoder-code evidence,
not a completed runtime call trace. One further bounded export encountered a
function-creation failure after exporting `0x824BCC48`; no conclusions are
drawn from the unexported callbacks.

### Exact selector behavior

At `0x824FBE28`, stream type must be `2`. The format description starts at
input `+8`; its width/height are at `+8`/`+0xC`, bit depth at `+0x12` must
be nonzero, and the FourCC is at `+0x14`. Observed accepted constants:

| Family | FourCC cases |
|---|---|
| Windows Media | `WVC1`, `WMVA`, `WMV3`, `WMV2`, `WMV1` |
| Additional WMV variants | `WVP2`, `WMVP`, `WMVR` |
| Legacy MPEG-4 variants | `MP4S`, `MP43`, `MP42` |

The default returns `0x80500003`. Accepted cases populate decoder callbacks;
the creation callback invokes an actual decoder initializer, not just a
diagnostic label. Initialization treats WVC1 specially and checks codec-specific
data for some formats. Header validity still matters.

**H.264/AVC is not one of these cases.** This does not prove that every byte of
the executable lacks an H.264 decoder. `MP4S`/`MP43`/`MP42` are not H.264;
MPEG-4 Part 2 and AVC/Part 10 must not be conflated.

This changes the interpretation of the earlier WMV2/WMA2 disc-read failure:
it cannot establish absence of a WMV2 decoder. Audio, ASF/container details,
bitmap metadata or a different dispatch path may have caused rejection.
The successful WVC1/WMA Pro file and its header normalization remain the baseline.

## Actual Xbox 360 port precedents

### ffplay360: closest execution environment

The historical [ffplay360 source](https://github.com/CodeAsm/ffplay360) contains
an [Xbox360 Visual Studio/XDK project](https://github.com/CodeAsm/ffplay360/blob/master/main/main.vcproj),
with Xbox compiler/linker tools and D3D9/XAudio2 dependencies. Its
[configuration](https://github.com/CodeAsm/ffplay360/blob/master/config.h)
enables PowerPC/big-endian Xbox code, H.264/AAC decoding and MOV demuxing.

The [worker source](https://github.com/CodeAsm/ffplay360/blob/master/main/thread.cpp)
calls FFmpeg packet reading/video decoding and manages Xbox threads.
[Display code](https://github.com/CodeAsm/ffplay360/blob/master/main/display.cpp)
creates Y/U/V textures; [audio code](https://github.com/CodeAsm/ffplay360/blob/master/main/audio.cpp)
feeds 16-bit PCM to XAudio2. These are useful examples of the required adapters,
not proof of sustained 720p decoding while Lips renders and scores vocals.

It is an old standalone player, not an in-game codec plugin. Launching it as
another title would replace Lips, so that is not a solution. Do not copy the
repository wholesale: it includes SDK-derived ATG/Common material and compiled
binaries. Audit individual licenses and dependencies before any reuse; none
were incorporated or executed here. Historical compatibility glue also needs
review, rather than assuming modern FFmpeg can be built unchanged.

### XMPlayer: independent free-toolchain precedent

[XMPlayer](https://github.com/LibXenonProject/xmplayer) ports MPlayer/FFmpeg
using LibXenon. Its [Makefile](https://github.com/LibXenonProject/xmplayer/blob/master/Makefile)
links avcodec/avformat/swscale; its
[configuration](https://github.com/LibXenonProject/xmplayer/blob/master/mplayer/config.h)
enables H.264 decoding. The [README](https://github.com/LibXenonProject/xmplayer/blob/master/README)
describes launching through XeLL and records historical stability/sync limitations.

[LibXenon](https://github.com/Free60Project/libxenon) provides a bare-metal
homebrew environment and toolchain. That demonstrates software decoding on
the hardware, but its ELF/runtime cannot be dropped into a retail XEX as-is.
Do not confuse Xbox 360 LibXenon with original-Xbox nxdk.

## XDK findings and integration requirements

The locally installed SDK exposes XMedia2 player creation, frame retrieval,
rendering, playback status, pause and seek. Its I420 frame format describes
**decoded pixels**, not an H.264 compressed-input capability. The examined
header has no public arbitrary-codec registration switch.

Library symbols include WMV/WMA decoder and channel/rendering classes. H.264
DXVA mode identifiers alone are not decoder code or evidence of a usable
hardware accelerator/API in Lips. Do not infer support from those identifiers.

A new decoder requires PowerPC/big-endian compilation, allocator and thread
adapters, file/demux I/O, decoded frame transfer, and an ABI-compatible bridge
to the game. Preserve the existing D3D device and audio engine; do not blindly
reuse a standalone player's device creation. The bridge must support ownership,
cleanup, pause/resume, seek, timestamps, end-of-stream, errors and frame dropping.
Audio must remain synchronized with chart/scoring time and microphone processing.

Using an appropriately licensed existing XDK privately is a practical route
for an XEX proof of concept; no SDK download or redistribution is part of this
project. An alternative free-toolchain path still needs the title ABI bridge.
Publish original patch source/tooling, not game or SDK binaries. Running a
modified title needs an execution environment that permits it; this is not a
promise of an installable modification on an unmodified retail console.

An emulator-only host decoding hook is another possibility, but would not
solve playback on a real Xbox. It must remain clearly separate.

## Next controlled gates

### MPEG-4 follow-up, 2026-10-01

Bounded analysis continued into `0x82507E00` -> `0x8252D3C8`. The latter
explicitly maps FourCCs to decoder state at context `+0x3C90`: `MP4S` -> `0`,
`MP42` -> `2`, `MP43` -> `3`, `WMV1` -> `4`, `WMV2` -> `5`, `WMV3` -> `6`,
and `WMVA` -> `7`, with lowercase aliases. Unknown cases return `6` on that
path. This strengthens the evidence beyond a superficial FourCC whitelist;
it still does not establish successful ASF demux, initialization or playback.
The final live indirect call from the factory to the selector remains untraced.
The input setup path reaches the generic callback-selection loop at
`0x824C6508`. Its three-entry table at `0x82EC7D9C` resolves through cells to
`0x824E4970`, `0x824E3628` and `0x824E1EB8`. Those functions select further
callback tables based on input/options; they are not a direct recovered call
to the video selector. The survey now exports these static registry entries
privately so a later runtime trace can distinguish container selection from
codec initialization.

`tools/build_mpeg4_codec_tests.py` now generates an original copy, remux control
and three separate candidates using FFmpeg's real matching encoders:

| Variant | Encoder | Actual output FourCC | Container/audio |
|---|---|---|---|
| Control | video copy | WVC1 | ASF / original WMA Pro packets |
| MPEG-4 Part 2 | mpeg4 | MP4S | ASF / original WMA Pro packets |
| Microsoft MPEG-4 v3 | msmpeg4 | MP43 | ASF / original WMA Pro packets |
| Microsoft MPEG-4 v2 | msmpeg4v2 | MP42 | ASF / original WMA Pro packets |

These are **not MP4 container files, H.264 or AAC**. FFmpeg's
[codec-tag table](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/riff.c)
confirms the bitstream/tag pairings. The tool preserves source dimensions/rate,
uses YUV420p, no B-frames and a modest video bitrate. It verifies actual ASF
tags, nonzero bitmap bit count, unchanged encoded audio hashes and full FFmpeg
decoding. The remux control additionally requires unchanged video packet hashes.
Outputs publish only after all validation succeeds and never replace inputs.

The full Amazing reference was processed successfully locally: all four
generated files fully decode with FFmpeg, with unchanged WMA Pro packet hashes.
The latest verified files remain private under
`private/outputs/amazing-mpeg4-tests-verified-20261001/`.
**No candidate was installed or tested in Lips in this pass.** FFmpeg decoding
does not test Microsoft's decoder constraints or Lips clock integration.

Reproduce with a legally available working reference:

```powershell
py -m tools.build_mpeg4_codec_tests Amazing.wmv --out private/outputs/mpeg4-tests
```

Test original -> remux control -> each video candidate with the same chart,
profile and audio assets. If remux fails, investigate ASF metadata before
attributing the failure to a video decoder. Keep this separate from WMA Standard
testing; a successful video-only experiment still leaves the audio encoding
requirement for an entirely cross-platform production pipeline unresolved.

1. Recover or runtime-trace the final indirect selector dispatch. Record decoder
   creation errors before changing any game code.
2. Keep WVC1 video packets unchanged and test WMA Standard separately against
   the existing remuxed WMA Pro control. Prepared files are not yet gameplay-tested.
3. Test a short WMV2 clip with baseline container/bitmap metadata and unchanged
   supported audio, independently of step 2. Then consider exact supported
   legacy MPEG-4 tags. A FourCC must describe the real bitstream, not disguise it.
4. If no stock-game path works, first compile a small decoder harness with
   synthetic test media. Audit licensing, output checksums and memory use.
5. Only then integrate a small H.264 software-decoder experiment: 320x180 or
   432p, modest frame rate, 8-bit YUV420 and initially no B-frames. This is a
   proposed test profile, not confirmed support. Benchmark on real hardware
   with the game running before considering 720p.
6. Require a complete song, seek/pause/cleanup and chart-sync validation before
   exposing an optional patched-game export mode in Studio.

No decoder patch or additional stock-game codec acceptance is claimed by this
report. Mac/Linux warnings remain accurate until a path passes these gates.

## Reproduction and private artifacts

`tools/ghidra/StudyOgVideoCodecRoutes.java` is a hash-guarded candidate survey
for this OG image. Run it with `analyzeHeadless`, `-readOnly -noanalysis` and a
private output path; use `StudyOgIxbReader.java` for the bounded addresses above.
The survey checks tags and adjacent PPC constant construction, not all possible
instructions or dispatch tables. Negative results are not absence proofs.

Raw decompilation, vtable dumps and SDK symbol output remain under ignored
`private/outputs/`; only original analysis tooling and this sanitized report
are committed. The new survey compiled and ran successfully in Ghidra 12.1.3.
