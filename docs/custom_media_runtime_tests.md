# Custom media runtime tests

## Scope and rollback

## Working checkpoint: generated media accepted

The page-corrected 770-note fresh chart, generated lyric resource and generated
VC-1/WMA Pro 16-bit video played together in the isolated OG slot and reached
the Single Mode Results screen. The user confirmed the new song's audio.
Text and note pages advance, but synchronization is not yet verified. The
catalog still identifies the slot as the original song; this is not yet an
independent song registration, nor proof that every imported note rendered.

Controlled change: BITMAPINFOHEADER.biBitCount was changed from 0 to 24 in the
generated video. Exactly one byte at offset 397 differs; size 58290639 and all
compressed packets are unchanged. The failed and accepted runs use the same
chart/lyric pair. `tools/normalize_og_asf.py` reproduces the accepted file
byte-for-byte, SHA-256
`4291d86254e89f866445cd6a083799f5e870daa1fbe0dd540a8a0e530204ed47`.
It refuses existing outputs and unsupported format descriptions, validates
the change boundary, and publishes a new copy without overwriting its input.

74/74 untouched OG videos have biBitCount=24 (high confidence for this corpus).
The causal acceptance test is one generated song on OG in Xenia, not proof of
all Xbox hardware or later-game compatibility. Packet length, preroll and
Header Extension differences remain in the accepted file: matching those
fields to the reference was not necessary in this test.

The read-only native failure probe resolved the rejected resource to the full
song's `game:` asset stem, with request and override fields both zero. File
opening and initial reads succeeded. The one-field experiment isolates a
header compatibility issue here without blaming missing files or changing
the IXB graph.

The exact working chart, lyric, video, config, input JSON, runtime log, clock
trace and hashes are checkpointed privately. Do not regenerate or replace
this checkpoint during subsequent catalog/timing experiments.

### Supplied media research: agreement and limits

The user-supplied research note correctly separates ASF/WMV, RIFF/xWMA and
XMA/XMA2, and recommends corpus checks rather than guessed codec settings.
Its proposed work plan is background material, not project instructions.
Its general claim that full song audio is always a separate xWMA asset is
not established for our OG test: the accepted video itself contains WMA Pro
audio, while the OG corpus also has separate ASF `.wma` assets and xWMA
previews. Do not extrapolate this result to LS2/DLC playback paths.

The replacement UltraStar reference has GAP=15940 ms, 780 notes and a video
identifier matching the supplied official video; the earlier lyrics-video
reference had GAP=10180 ms and 770 notes. This is a new timing candidate, not
yet a measured synchronization fix.

The following failure sections retain the investigation history. Their
unresolved header hypotheses are superseded by the controlled result above.

OG Lips 2008, executable 0.0.0.20, isolated Amazing slot only. Original
extractions, ISO and supplied song media were not modified. After the failed
VC-1 test, the isolated chart, lyric and video were restored and hash-checked
against the backup. Generated copyrighted content remains private.

## Full UltraStar chart

The supplied full-length reference imports as 770 notes; none were trimmed.
The fresh chart has 770 phrase markers and 770 linked lyric markers, with
11 named tracks and 2488 framed records. It loaded over the original video,
displayed imported text and notes, progressed through multiple pages, and
reached results. This does not verify the entire imported duration: the
original video ends at about 191 seconds, before the last imported note.

Dense phrases exposed a page-boundary issue. The old fixed 0.8-second preroll
could start the next page before the previous phrase finished. The builder now
clamps that boundary to the preceding phrase end, without moving it beyond the
next phrase start. A synthetic overlap regression covers this rule. The updated
full chart was subsequently isolated from the media change: with the original
video it loads and displays successive imported pages, with a measured chart
clock of 43.092373 s at host trace time 47.945888 s. This verifies start and
early page progression, not all 770 notes or the complete song duration.

## Controlled failures

| Generated media | Result | Interpretation |
|---|---|---|
| PyAV WMV2 + WMA2, ASF | Disc Read Error at song start | Rejected; not a supported output claim |
| Windows Media Foundation VC-1 Advanced + WMA Pro, ASF | Disc Read Error at song start, user-confirmed | Matching codec names is insufficient |
| Same VC-1, explicitly 16-bit WMA Pro | Disc Read Error at song start, observed with native trace | Matching the audio extra data is insufficient |

The second file was independently decoded/probed: VC-1, 768x432, WMA Pro
48 kHz stereo at 192 kbit/s, approximately 263.309 seconds. It must **not** be
called Xbox-compatible based on that probe alone.

Concrete differences from the real file:

| Field | Original reference | Generated VC-1 test |
|---|---|---|
| WMA Pro decoded bit depth (codec extra data) | 16 | 24 |
| ASF min/max packet length | 16000/16000 | 8221/8221 |
| ASF preroll | 4000 ms | 3000 ms |
| VC-1 sequence header | Advanced profile | Advanced profile; different parameters |

These observations concern one working reference and one generated file, not
corpus-wide invariants. Confidence is high for the measured differences, low
for their causal relationship to rejection. Next controlled conversion selects
a 16-bit WMA Pro output type while retaining the video codec.

The installed SDK contains `xma2encode.exe` and `xwmaencode.exe` for audio.
Its video documentation recommends Windows Media Encoder 9. `XMedia2` is a
console playback API, not an installed desktop converter. SDK documentation
and binaries are private and are not included in this repository.

Native failure-site tracing is still needed if matching the audio type does
not fix the rejection. The current low-level log contains repeated unrelated
compression-information stubs and does not identify the failing media read.

### OG media corpus header inventory

`tools/analyze_asf.py` read all 114 ASF `.wmv`/`.wma` files under the untouched
OG backup's `lps/Levels` tree: 40 audio files and 74 full/preview videos, zero
parse failures. Its summary includes the full file list in private local output.
All 114/114 audio streams use WMA Pro (0x162), 16-bit; all 74/74 video streams
use WVC1. These are high-confidence observations for this OG corpus only.

| Packet length / preroll / streams | Occurrence |
|---|---:|
| 8223 / 1451 ms / audio | 40/114 |
| 8223 / 3000 ms / audio+video | 37/114 |
| 16000 / 4000 ms / audio+video | 36/114 |
| 16000 / 3000 ms / audio+video | 1/114 |

Thus neither 16000-byte packets nor 4000-ms preroll is universal. Do not blindly
copy Amazing's packet settings into all outputs. The generated 16-bit candidate
now matches the original audio codec extra data exactly, but requires a runtime
test. `tools/xenia/og_disc_error_trace.patch` adds bounded read-only backchain
logging at the existing fatal dirty-disc call; it does not suppress the error
or modify guest memory.

### Native failure call investigation

The 16-bit test reaches XamShowDirtyDiscErrorUI with LR=0x8280FF38, SP=0x7027FE70.
In the exact OG XEX, 0x8280FF28 is the wrapper calling that fatal UI. This does
not establish a codec error: two small tail-call callbacks can enter it.
Instruction-level reference search identifies callbacks 0x82BC4D38 and
0x82D07948. Their addresses are passed by functions containing 0x82BCA344 and
0x82D07B44, respectively. The latter handles file-operation dispatch including
case 0x10 that schedules a fatal callback; the former schedules a fatal thread
after initialization fails. The active origin is not yet distinguished.

The generic .pdata grouping merges these tiny leaf callbacks with preceding
functions, so a decompiled containing function can omit the actual tail call.
The comparison therefore checks raw PowerPC branch instructions as well as
decompilation. `StudyOgCodeReferences.java` is read-only and executable-hash
guarded. Its address-pair matches are candidates, not proof of execution.

The initial bounded stack logger found a valid backchain but no nonzero saved
LR values at its assumed frame+8 slot. That slot is not a verified Xenon unwind
rule; do not interpret the zeros as damaged game stack.

### Controlled IO and callback-origin result

With the same page-corrected chart/lyric pair, swapping only the full video
produces these results:

| Video | Result |
|---|---|
| Untouched original | Gameplay starts; notes, imported lyrics and pages advance |
| Generated 16-bit VC-1/WMA Pro | Disc Read Error before gameplay |

`og_media_io_trace.patch` logs file opens and first/failed/short ASF reads before
asynchronous status is changed to pending. The generated full video opens twice
with status 0 and returns the complete first 131072 bytes both times, status 0.
No failed or short full-video NtReadFile is logged before the fatal error.
Short reads of the untouched preview at its end return status 0 and are not
evidence of a read failure. Missing optional jackets and LS2 preview paths
also occur during menu navigation; do not conflate them with this failure.

The fatal thread's start address is **0x82D07948**, distinguishing the active
file-operation callback from the alternative initialization callback
0x82BC4D38. Static reference analysis follows case 0x10 in 0x82D07A30 via
0x82D0DAE8, with the fatal request at 0x82D10C40. The preceding code checks a
resolved `game:` path and an existing request/override condition. This is a
general resource-failure path, not a decoder error code. A read-only probe at
0x82D10C30 captures r28 (resolved path), r31 (owner), owner+0x0c (request), and
owner+0x10 (override), without skipping the fatal call.

High confidence: path opening succeeds, initial reads succeed, this chart
starts with original media, and the fatal callback origin is measured.
Unresolved: the first failing media validation/initialization function, its
return value, and the specific incompatible field or bitstream property.
This does **not** prove an encoder or codec defect, nor exclude other guest
resource/container requirements or an emulator implementation gap.

A further read-only corpus check covers all 74 original OG WMV files:
74/74 have BITMAPINFOHEADER.biBitCount=24; the generated VC-1 file has 0.
All 74 contain the ASF Header Extension object; the generated file lacks it
and includes a differently organized header inventory. These are measured
high-confidence corpus differences, **low-confidence causal hypotheses**.
Do not change encoder settings solely on this evidence.

## Tools and sources

`tools/transcode_media_probe.py` is an intentionally experimental WMV2/WMA2
probe with synthetic tests. `tools/media/transcode_windows.cpp` uses native
Windows Media Foundation to generate VC-1/WMA Pro without an Xbox SDK dependency.
Both refuse existing outputs. The native converter followed by
`normalize_og_asf.py` now produces runtime-tested OG media for the checkpoint
above. The WMV2/WMA2 probe remains rejected. No new catalog entry is validated yet.

Windows API references: [Media Foundation encoders](https://learn.microsoft.com/en-us/windows/win32/medfound/windows-media-encoders),
[transcode profiles](https://learn.microsoft.com/en-us/windows/win32/api/mfidl/nf-mfidl-mfcreatetranscodeprofile).

Build the native probe from a Visual Studio x64 developer terminal with Windows
SDK headers/libraries available. Put compiler artifacts in a private directory:

```text
cl /EHsc /std:c++17 tools/media/transcode_windows.cpp /Fo:private/transcode_windows.obj /Fe:private/transcode_windows.exe
private/transcode_windows.exe input.mp4 private/new-output.wmv
python tools/analyze_asf.py private/original-game/lps/Levels --summary
```

The converter publishes only a new file after the media session completes;
failed partial output is cleaned up. It selects 48 kHz stereo 192 kbit/s
16-bit WMA Pro explicitly rather than the first enumerated type. The selected
video subtype remains WVC1. Apply the bounded bitmap-header normalizer to a
new copy before testing the output; codec names alone do not establish acceptance.
