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

## Ghidra 12.1.3 supplied-plugin comparison

On the same date, the user supplied Ghidra 12.1.3 and a prebuilt XEXLoaderWV
extension with version=12.1.3 in extension.properties. It was installed without
modifying the supplied files, into the new installation's Ghidra/Extensions.
The previous LipsOG2008 database was preserved. The comparison uses a fresh
LipsOG2008_1213 project, the same input XEX, Java, 300-second analysis limit,
four-CPU limit and unchanged LipsInitialAudit.java export script.

Supplied XEXLoaderWV.jar SHA-256:
9363f04e6c600c4704660ee70a5924dadbd5db6ed0fe8c2ebdab4cc6a69bfa61.

All 20 Java source files in its bundled XEXLoaderWV-src.zip match the previously
built loader source byte-for-byte. This is source equivalence, not proof of
binary equivalence. The previous extension was built specifically for 12.1.4;
it was not this 12.1.3 prebuilt extension installed into the wrong version.

Both imports report the same 43,179 initial .pdata functions, 361 import thunks,
376 import references, LZX end-of-input warning, three invalid PNG candidates
and observed unresolved-instruction warnings. The supplied source retains the
same compressed-length * 100 decompression request. Version compatibility alone
does not eliminate these warnings.

Private comparison outputs: og-ghidra-1213-import.log and
og-ghidra-1213-audit.txt in xenia-research.

Both runs reached the 300-second automatic-analysis limit and saved their
projects successfully. Both audit exports are byte-identical, SHA-256:
1326ad3635b536148d39a9047ddec2008709a5cbddbc0feaa64991d24cc1b89f.
This includes 42,694 reported functions, block ranges, queried string/xref
results, the sampled vtable entries and five selected decompiled functions.
No improvement was observed in this bounded audit. This does not establish
equivalence of every function, full analysis completion, or import integrity.
Future work can use the supplied 12.1.3 combination; the next substantive task
is still import-byte validation and targeted reader/function-boundary analysis.
