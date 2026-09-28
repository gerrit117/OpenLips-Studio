# OG loader validation and analysis repair

2026-09-28; input and tooling identity: [og_ghidra_setup.md](og_ghidra_setup.md).
This investigation uses the supplied Ghidra 12.1.3 XEXLoaderWV extension.
The game XEX and saved Ghidra database were not changed. All subsequent Ghidra
runs used -readOnly -noanalysis; experimental analysis edits were discarded.

## What the plugin actually did

The log confirms XEXLoaderWV imported the XEX rather than a generic PE loader.
It processed encryption/compression, mapped sections, created .pdata functions
and named Xbox imports. Identical results across versions did not mean the
plugin was unused: the two loader source sets were identical. The plugin does
not automatically recover the IXB grammar or reliable types for every function.

## Decompression checks

A private Java audit rebuilt the XEX normal-compression block stream, checked
bounds and verified each SHA-1 against the digest stored in the chain.

| Check | Result |
|---|---|
| Compressed blocks | 102/102 SHA-1 checks passed |
| LZX chunks | 566 |
| Combined LZX input | 5,948,106 bytes |
| Declared image size | 18,546,688 bytes |
| Declared LZX window | 32,768 bytes |
| Explicit-size decode output | 18,546,688 bytes |
| Existing oversized-request decode output | 18,546,688 bytes |
| Outputs equal | Yes, byte-for-byte |
| Explicit decode equals loader PE image | Yes, byte-for-byte |
| Imported blocks within decoded image | 15/15 byte-identical |

The matched blocks include all of .text, .rdata, .pdata, .data, .idata, .XBLD,
.XBMOVIE and eight .embsec_ blocks. The .reloc block extends outside this
decoded image and was explicitly excluded from the comparison. Its mapping
remains to be checked; no claim of whole-program-image integrity is made.

The explicit-size decode did not produce the end-of-input warning. The two
oversized decode calls did. For this input the warning is explained by the
loader requesting compressed_size * 100 bytes: it returns all declared image
bytes before exhausting the stream. This is not evidence of truncated .text.

Limit: both decodes use the same LZX implementation. Input hash verification,
output-size checks and byte comparisons establish consistency and absence of
observed truncation, not independent proof of decoder correctness or signature
authenticity. A different decoder/Xenia comparison remains useful.

## Recovered anchors

The reader-style bare tokens are present despite missing exact source strings:

| Token | OG address |
|---|---|
| IsBigEndian | 0x821063d4 |
| NumOfElements | 0x821063e0 |
| UriList | 0x82106428 |
| Writer source-path string start | 0x821062a0 |
| Writer Objects opening token | 0x82106294 |
| m_vecLyricWordData | 0x820e0fe4 |

String presence is not a control-flow proof. A bounded lis/addi-or-ori scanner
found candidate references missing from Ghidra's reference table. It is only a
candidate generator: it does not fully model intervening register clobbers.
Manual instruction review is required before trusting each hit.

## Confirmed false no-return flags

Three save-register helper entries were marked no-return in the saved analysis:

- 0x827df4d0: saves r14 onward.
- 0x827df4e0: saves r18 onward.
- 0x827df504: saves r27 onward.

Instruction inspection shows straight-line register stores through r31, a store
of r12, and a shared blr at 0x827df51c. These entries return. Their no-return
classification truncated caller control flow in the decompiler.

A temporary experiment cleared these flags and CALL_RETURN flow overrides,
disassembled the affected caller ranges and assigned candidate bodies bounded
by neighboring .pdata start addresses. It recovered substantial pseudocode for:

| Candidate function | Temporary body range | Evidence / status |
|---|---|---|
| 0x82d9a388 | 0x82d9a388..0x82d9a7af | Writer-source reference; binary stream operations |
| 0x82d9a8c0 | 0x82d9a8c0..0x82d9b717 | References formatted header fields and Objects token; writer-side candidate |
| 0x82d78708 | 0x82d78708..0x82d7897f | WordData member-name reference; role unconfirmed |

Previously these candidates decompiled essentially as a call to a supposedly
non-returning helper. This is a concrete analysis-quality improvement, unlike
the Ghidra-version comparison.

This is not yet a complete ABI repair: generated pseudocode still treats the
save helper as returning a context value. That expression is a decompiler
artifact, not a proven helper return contract. Correct save/restore call-fixups,
register effects, signatures and exact function boundaries must be established
before interpreting recovered parameter names and struct offsets. The new
pseudocode is navigation evidence, not a specification to implement blindly.

## Next step

Build correct analysis handling for the verified save/restore helper family in
a separate research project or reproducible script. Then trace references to
the bare reader tokens and object-reference fixup code, using the recovered
writer as a comparison, not as a substitute for the reader. Validate individual
operations against Xenia before changing the chart writer.

Private reproducibility artifacts in xenia-research:
LipsLoaderAudit.java, LipsReaderAnchors.java and LipsRepairProbe.java under
ghidra-scripts; og-loader-validation.txt, og-reader-anchors.txt and
og-helper-repair.txt with their corresponding logs. No game bytes or generated
decompiled code are included in this report.
