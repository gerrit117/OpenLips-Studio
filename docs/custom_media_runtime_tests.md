# Custom media runtime tests

## Scope and rollback

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
full chart's runtime page behavior remains unverified because the media tests
below fail before gameplay.

## Controlled failures

| Generated media | Result | Interpretation |
|---|---|---|
| PyAV WMV2 + WMA2, ASF | Disc Read Error at song start | Rejected; not a supported output claim |
| Windows Media Foundation VC-1 Advanced + WMA Pro, ASF | Disc Read Error at song start, user-confirmed | Matching codec names is insufficient |

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

## Tools and sources

`tools/transcode_media_probe.py` is an intentionally experimental WMV2/WMA2
probe with synthetic tests. `tools/media/transcode_windows.cpp` uses native
Windows Media Foundation to generate VC-1/WMA Pro without an Xbox SDK dependency.
Both refuse existing outputs. Neither currently produces runtime-validated
Lips media. No song catalog entry has been inserted yet.

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
video subtype remains WVC1. Runtime acceptance is deliberately not claimed.
