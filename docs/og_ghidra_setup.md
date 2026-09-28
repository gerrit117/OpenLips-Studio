# OG Lips Ghidra baseline

Date: 2026-09-28. Setup and initial import, not a verified IXB loader specification.

## Input identity

- Original input: extracted OG Lips 2008 default.xex, left unchanged.
- Size: 6,074,368 bytes.
- SHA-256: 95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9.
- XEX2 execution header: title 4D530888, version/base version 0x14 (0.0.0.20).
- Entry: 0x828108c0; image base: 0x82000000.
- Imported .text: 0x82190000, size 0x00c54c3c.

The earlier July report has entry 0x828dae18 and .text at 0x821e0000.
It is a different executable layout. Its addresses must not be carried across
without re-identification; this comparison does not identify the older title
edition by itself. Title/version match the recent OG runtime session, but
full binary equivalence to its loaded memory has not yet been established.

## Toolchain

- Ghidra 12.1.4 PUBLIC, supplied locally.
- Temurin JDK 21.0.11.
- XEXLoaderWV source: https://github.com/zeroKilo/XEXLoaderWV
- Loader commit: 4bcf58da4caa5260644fc19f5eef5ccde3b7ff46.
- Built successfully against this Ghidra installation with Gradle 9.3.1.
- Gradle distribution SHA-256 checked against the publisher's checksum.
- Loader installed only into this Ghidra installation's Ghidra/Extensions.
- Selected language: PowerPC:BE:64:A2ALT-32addr (loader default).
- No PDB requested, no title-update patch applied.

The private project is xenia-research/ghidra-projects/LipsOG2008.
The original game files and other Ghidra projects were not modified.
Private automation is ghidra-scripts/LipsInitialAudit.java; output is
og-ghidra-initial-audit.txt and og-ghidra-import.log in xenia-research.
Logs, generated decompilation and Ghidra databases stay outside this repository.

Reproducible initial command, with paths supplied locally:

```text
analyzeHeadless <projects> LipsOG2008 -import <OG/default.xex>
  -analysisTimeoutPerFile 300 -max-cpu 4
  -scriptPath <scripts> -postScript LipsInitialAudit.java <private-report>
  -log <private-log>
```

The timeout bounds automatic analysis only. It is not proof that all functions
have been analyzed. Post-analysis exports are limited to 24 selected functions,
with a 30-second decompiler limit per function.

## Import caveats

The loader reports 43,179 .pdata functions and 361 named import thunks
(376 import references). Counts reflect loader output, not manual validation.

The loader reports "out of input bytes" during LZX decompression but continues.
Source inspection shows the normal-compression path calls an overload that
requests compressed-input-length * 100 output bytes, catches decompression
exceptions and returns bytes produced so far. Therefore the warning may be an
over-request rather than damaged input, but import completeness remains unproven.
Check decompressed length and/or compare code regions against an independent
decoder or Xenia before drawing conclusions from absent or unusual bytes.

Automatic analysis also reports invalid PNG candidates and unresolved PowerPC
p-code constructors in some functions. These warnings are not evidence of a
bad song file. A successful project save does not resolve those limitations.

## Initial run result

Import and project save succeeded. Automatic analysis hit the explicit
300-second limit, so the project is partially analyzed, not fully analyzed.
The audit script completed and exported five selected functions as pseudocode.
The function manager reports 42,694 functions after this pass, distinct from
the loader's initial .pdata count.

Recovered candidate anchors:

- lpsMelodyMarker string at 0x820f1f80, with references at 0x82cbde80
  and 0x82c8e8d4.
- lpsLyricMarker string at 0x820f2ae8, referenced at 0x82cbe860.
- Both class strings are referenced within Function_82CBD668. Its role is
  not yet established; a shared string table consumer is not proof of a loader.
- ixSerializerWriter.cpp at 0x821062ac.
- Known live Melody vtable 0x820e1938 begins with function 0x821dd5d0.
- Known live Lyric vtable 0x820e1100 begins with function 0x821d72c0.

The exact reader strings searched (ixSerializerReader::Load and
ixSerializerReader.cpp) were not found in imported initialized blocks. This
does not prove absence of a reader, especially before import completeness is
checked. Some nonzero vtable targets have no recognized function at their
entry; the audit's `null` function labels do not mean null pointer values.

## Next narrow questions

1. Validate imported bytes and function boundaries at the IXB reader.
2. Re-identify reader source strings and call sites in this exact build.
3. Follow a real MelodyMarker through deserialization, reference fixups and
   insertion into its owning sequence vector.
4. Confirm those operations using the existing working OG Xenia session method.

Do not transplant runtime vector layouts into the file writer or add synthetic
chart structures based on this initial import alone.
