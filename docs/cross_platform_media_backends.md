# Cross-platform media encoder research

Research date: 2026-10-01. No game files or accepted media checkpoints changed.

## Required output, not just a filename

The accepted OG path currently uses WVC1/VC-1 Advanced video and 16-bit stereo
48 kHz WMA Pro in ASF, followed by the bounded ASF normalization already used
by Studio. A `.wmv` extension does not establish compatibility. The historical
WMV2/WMA2 experiment produced a disc-read error; see
[the runtime test log](custom_media_runtime_tests.md#controlled-failures).
ASF authoring and DLC RIFF/xWMA authoring remain different tasks.

The current helper calls Windows Media Foundation APIs, including
`MFCreateTranscodeTopology` and `MFTranscodeGetAudioOutputAvailableTypes`.
It is not a portable encoder merely because its frontend is Python.

## Candidates

| Candidate | Evidence | Remaining gap | Assessment |
|---|---|---|---|
| FFmpeg | Current codec registry lists VC-1/WMV3/WMA Pro decoders, but no corresponding encoders; WMA1/2 and WMV1/2 encoders exist | Cannot produce the accepted codec pair | Bundle for preprocessing, not a final OG backend |
| MainConcept VC-1 / Transcoding SDK | Vendor documents VC-1 encoding, ASF muxing and a low-level API for Windows, Intel macOS and Linux; VC-1 package includes a WMA encoder | Public material says WMA, not specifically our WMA Pro profile. Current OS/architecture support, Apple Silicon, costs and redistribution need written confirmation | Strongest documented native candidate, not yet validated |
| WMAEncodeRS | Maintainer explicitly documents Windows 10/11 and Microsoft runtime; supports WMA Pro and RIFF/xWMA | Still Windows-only; no video encoder | Useful audio reference, not a portable replacement |
| Historical Intel IPP/UMC samples | Intel forum documents a Linux VC-1 encoder command in 2010 | No current maintained, redistributable, all-platform WMA Pro + VC-1 backend established; modern ARM support unknown | Historical lead, low confidence |
| Wine / CrossOver | Could theoretically host Windows encoding code | No tested codec availability or output compatibility on macOS/Linux. Windows DLL redistribution cannot be assumed | Experimental only; do not advertise as supported |
| User-controlled Windows encoding worker / VM | Reuses the accepted helper and normalizer instead of inventing a codec | Requires Windows somewhere, explicit connection/authentication and implementation; Windows ARM codec availability needs testing | Pragmatic fallback, not genuinely native on all platforms |

No free, maintained, fully native encoder pair for all four Studio targets was
verified in this investigation. This is a finding about the investigated
options, not proof that no implementation can exist.

## Proposed next verification

1. Request a MainConcept evaluation and confirmation of **WMA Pro 0x0162**,
   48 kHz stereo / 16-bit / 192 kbit/s, WVC1 Advanced and ASF output for each
   target, specifically macOS ARM64. Do not purchase or redistribute anything
   based on generic WMA claims.
2. Encode the same owned short synthetic input with each candidate.
3. Run Studio's existing codec/container validation and bounded normalization.
4. Compare headers/packet layout with the accepted checkpoint and test the
   generated asset in Xenia and on the original system. Do not equate successful
   desktop decoding with game compatibility.
5. Keep an optional proprietary encoder external to the GPL app, using a
   documented process boundary, and review its distribution terms separately.

Until a backend passes these checks, keep Windows encoding operational and
explain the limitation before conversion on macOS/Linux. Bundling FFmpeg
removes a path-selection burden, not the missing codec implementation.

## Primary sources

- [FFmpeg codec registry](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/allcodecs.c)
- [Microsoft Windows Media encoders](https://learn.microsoft.com/en-us/windows/win32/medfound/windows-media-encoders)
- [MainConcept VC-1](https://www.mainconcept.com/vc-1)
- [MainConcept VC-1 datasheet](https://www.mainconcept.com/hubfs/PDFs/Datasheets/VC1_SDK_DATASHEET.pdf?hsLang=en)
- [MainConcept Transcoding SDK](https://www.mainconcept.com/transcoding-sdk)
- [MainConcept Audio SDK](https://www.mainconcept.com/audio)
- [WMAEncodeRS source and platform requirements](https://github.com/MSIVST/WMAEncodeRS)
- [Historical Intel Linux VC-1 encoding discussion](https://community.intel.com/t5/Intel-Integrated-Performance/Why-VC-1-encoding-so-slow-comparing-to-H264-encoding/m-p/887252)

Vendor availability and licensing are research observations only. No SDK was
installed or purchased, no Windows DLLs were copied into a public artifact,
and no media was uploaded to a third-party encoder.
