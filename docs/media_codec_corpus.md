# Media codec corpus and native parser investigation

Read-only investigation, 2026-10-01. No media, executable, profile or saved
Ghidra project was patched. The working Windows encoder remains unchanged.

## Samples

`tools/inventory_media_codecs.py` inspected **591 media paths, zero failures**:

| Root | Files |
|---|---:|
| Untouched OG backup, complete lps tree | 521 |
| Songdateien archive | 46 |
| Loose Lips/lps (Airplanes) | 4 |
| Four previously extracted original DLC packages, six songs | 20 |
| Repository private/samples (charts/lyrics only) | 0 media |

Full filenames and distributions are recorded privately in
`private/outputs/media-codec-corpus-final-20261001.json`. Counts are **paths, not
independent assets**: some archive and extracted files duplicate one another.
Custom-generated files, the edited active game extraction, renamed `.wmv.bak`
intros and media still inside unextracted ISO/STFS files were excluded. Later
coverage consists of available disc/DLC samples, not a complete NoH inventory.

| Format | Occurrence | Confidence |
|---|---:|---|
| RIFF/XWMA, WMA Standard 0x0161 | 76/76 xWMA files | High within available corpus |
| ASF audio, WMA Pro 0x0162 | 182/182 ASF audio streams | High within available corpus |
| WVC1 video | 115/137 video streams | High measured frequency |
| WMV3 video | 22/137 video streams | High measured frequency |
| RIFF/WAVE, XMA2 0x0166 | 333/333 XMA2 files | High; primarily effects |

WMA Standard is not limited to previews: **6/6 full-song audio assets** in the
four original extracted DLC packages use it. Full Ey DJ, Hamma and Airplanes
audio also uses it. Their movies contain WMV3 with embedded WMA Pro instead.
OG full audio in ASF and its movie audio use WMA Pro; its 40 xWMA previews use
WMA Standard. Different containers use different paths.

All 76 xWMA files have `fmt ` -> `dpds` -> `data`, 18-byte format descriptions,
cbSize=0, 48 kHz stereo and 16-bit output. All decoded-size tables are
nondecreasing with one entry per encoded data block. Block alignment is 8192
in 74/76 and 1008 in 2/76 paths (Ey DJ/Hamma `_prvcl` variants). This is a rare
preview-specific pattern, not a general full-song setting. Do not hard-code 8192.

## Native OG evidence

Ghidra 12.1.3, supplied XEXLoaderWV, existing LipsOG2008_Reader project, headless
`-readOnly -noanalysis`. Executable SHA-256:
`95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9`.
Addresses are specific to this OG build, not NoH/title updates.

`StudyOgMediaCodecs.java` exports symbols, string references and PPC tag
comparisons. `StudyOgIxbReader.java` repairs save-helper analysis in a discarded
transaction for bounded decompilation. Assembly/pseudocode stays private.

| Address | Finding | Confidence |
|---|---|---|
| 0x82AD19A8 | Opens a RIFF reader, locates fmt/data/dpds chunks, accepts WAVE or XWMA form identifiers | High parser evidence |
| 0x82AD1758 | Reads and byte-swaps WAVEFORMAT; explicitly handles PCM, WMA Standard/Pro, XMA2 and extensible format, rejects other direct tags | High for this parser, not a global playback whitelist |
| 0x82AD16D0 | Reads and byte-swaps cumulative dpds entries | High table handling evidence |
| 0x82D85F58 | Audio loading uses that RIFF parser and a shared 0x161/0x162 branch to load packet-size data | Medium-high; exact object types remain provisional |
| 0x8265C6E0 | Describes WMAStd/WMAPro and other tags | Diagnostic only, not proof of playback |
| 0x824D5310, 0x8267C080 | Converts/validates audio format families | Medium; not all branches proven reachable for songs |
| 0x826601A8 | Calls imported XMACreateContext at 0x82DE45AC | High XMA kernel-service evidence |
| 0x82421108 | References ixXMVPlayer_MainLoop for engine movie control | High observation; name does not make ASF into XMV |

XAudio render-driver imports establish console audio output, not a WMA decoder
API. No named XMedia/XMV decoder import was recovered in this bounded survey.
Native media/format routines are present in the XEX, consistent with linked
SDK/engine libraries plus kernel services (medium attribution confidence).
Do not conclude that every codec is game-authored, or that no system component
is involved. XMA contexts are not evidence that WMA uses XMA hardware.

.pdata can merge leaf functions and VMX128 instructions truncate some
decompilation. The XMA function at 0x82660158 has unsupported p-code. A small
predicate at 0x82D85DF0 is visible in assembly but omitted from its containing
function's pseudocode. Raw comparisons were checked, not just decompiled output.

## Conversion implications

The all-WMA-Pro assumption is wrong for DLC audio. A portable **audio-only
RIFF/xWMA backend** is now a strong candidate. It needs correct encoded blocks
and cumulative decoded-size/seek tables; renaming regular WMA is not enough.
FFmpeg's [xWMA implementation](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/xwma.c)
distinguishes WMAv2 and WMA Pro and synthesizes codec-specific extra data.
[Microsoft documents](https://learn.microsoft.com/en-us/windows/win32/api/xaudio2/ns-xaudio2-xaudio2_buffer_wma)
the decoded packet-size table and Xbox byte swapping.

PCM is accepted by the examined RIFF parser, but that does not prove that song
registration, streaming or memory limits permit PCM as a complete replacement.
It is a separate candidate, not a released backend.

This does not solve new portable video encoding: original movies use WVC1 or
WMV3, not the WMV2 output of the rejected earlier experiment. WMA Standard in
RIFF also does not prove it works inside an ASF movie.

Next tests: original movie baseline, copied-packet remux control, then unchanged
VC-1 with WMA Standard. `build_media_codec_tests.py` prepares new copies and
verifies video packet hashes. Independently test correctly authored xWMA with
seeking on the separate audio path, initially without optional video.

No fresh gameplay test completed: automated short keyboard presses did not
reliably leave the title screen and the user is away. Probes were not installed
into game files. Do not enable unverified output in Studio or replace the proven
Windows backend on static evidence alone.
