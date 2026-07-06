# Ghidra XEXLoaderWV findings for Lips X360 / IXB writing

Date: 2026-07-03

Scope: original Xbox 360 `Default.xex`, imported with `XEXLoaderWV` and analyzed in Ghidra. This file supplements `docs/ghidra_findings.md` and focuses only on writer-relevant facts.

## XEXLoaderWV improvements over the previous import

Confirmed facts:

| Item | Previous `default.exe` import | XEXLoaderWV import |
| --- | --- | --- |
| Program name | `default.exe` | `Default.xex` |
| Loader/format | `Portable Executable (PE)` | `XEX Loader by Warranty Voider` |
| Language | `PowerPC:BE:32:default` | `PowerPC:BE:64:A2ALT-32addr` |
| Image base | `0x82000000` | `0x00000000` reported by metadata, with executable blocks still mapped at `0x82000600+` |
| Function count | `18406` | `24131` |
| Symbol count | `34630` | `94625` |
| Analysis status | analyzed | analyzed |

Segments are mostly the same executable layout, but `.text`, `.idata` and `.XBLD` end slightly earlier in the XEXLoaderWV import:

| Segment | Range |
| --- | --- |
| `.rdata` | `0x82000600` - `0x82190c5f` |
| `.pdata` | `0x82190e00` - `0x821d1caf` |
| `.text` | `0x821e0000` - `0x82b6966b` |
| `.data` | `0x82bd0000` - `0x82e93bdb` |
| `.XBMOVIE` | `0x82e93c00` - `0x82e93c07` |
| `.idata` | `0x82ea0000` - `0x82ea054d` |
| `.XBLD` | `0x82eb0000` - `0x82eb010f` |
| `.reloc` | `0x82eb0200` - `0x82f53157` |

Entry/export facts:

- Entry labels: `entry @ 0x828dae18`, `Function_828DAE18 @ 0x828dae18`, and program entry `0x00000000`.
- Export table reports `entry -> 0x828dae18` and `Function_828DAE18 -> 0x828dae18`.
- The MCP `/list_imports` endpoint still reports no imports.
- However, XEXLoaderWV did recover many kernel/XAM import stubs as named functions, including `NtCreateFile`, `NtOpenFile`, `NtReadFile`, `NtWriteFile`, `NtClose`, `NtQueryInformationFile`, `NtSetInformationFile`, `XamContentCreateEx`, `_snprintf`, `_vsnprintf` and `sprintf`.

Impact:

- XEXLoaderWV materially improves function/symbol recovery and gives usable Xbox runtime import-stub names.
- It does not automatically solve all function-boundary problems. Some serializer functions still have broken bodies because Ghidra treats tiny save/restore helper thunks as nonstandard prologues.

## New writer-relevant strings

Confirmed writer string table near `0x82061d68`:

| Address | String | Writer relevance |
| --- | --- | --- |
| `0x82061d68` | `.\Serialize\ixSerializerWriter.cpp` | Source marker for writer code. |
| `0x82061dc4` | `</ixb>` | Final IXB close tag. |
| `0x82061dcc` | `</Objects>` | Objects section close. |
| `0x82061dd8` | `<Objects>` | Objects section start. |
| `0x82061de4` | `</UriList>` | URI list close. |
| `0x82061df0` | `<Uri` | URI entry start. |
| `0x82061df8` | ` Key="%d"` | URI entry key field. |
| `0x82061e04` | ` Uri="%s"` | URI entry URI string field. |
| `0x82061e10` | `<UriList>` | URI list start. |
| `0x82061e1c` | `</Classes>` | Classes section close. |
| `0x82061e3c` | `<Class` | Class entry start. |
| `0x82061e44` | ` Name="%s"` | Class name attribute. |
| `0x82061e50` | `<Members>` | Member list start. |
| `0x82061e5c` | `<Member` | Member entry start. |
| `0x82061e64` | ` Offset="%d"` | Member offset attribute. |
| `0x82061e74` | ` Base="%d"` | Member base/type-related attribute. |
| `0x82061e80` | ` Size="%d"` | Member size attribute. |
| `0x82061e8c` | `</Members>` | Member list close. |
| `0x82061e98` | `</Class>` | Class entry close. |
| `0x82061ea4` | `/>` | Self-close marker. |
| `0x82061ea8` | `<Classes>` | Classes section start. |
| `0x82061eb8` | ` NumOfElements="%d"` | Top-level element count. |
| `0x82061ecc` | ` Platform="%s"` | Platform attribute. |
| `0x82061edc` | ` IsText="false"` | Binary IXB mode marker. |
| `0x82061eec` | ` IsBigEndian="%s"` | Endianness attribute. |

Additional song/path strings confirmed in this import:

| Address | String | Notes |
| --- | --- | --- |
| `0x82011a18` | `%s\%s.X360` | Generic X360 path format, referenced near `0x82265a7c`. |
| `0x8201a090` | `_Cht.X360` | Chart filename suffix near `lpsChart`; referenced through the `0x822a3f70` chart setup path. |
| `0x820232c0` | `_Cht.X360` | Second chart filename suffix; referenced inside `Function_82310948`. |
| `0x8201a09c` | `lpsChart` | Chart class/type string used near chart X360 path creation. |
| `0x820232cc` | `lpsChart` | Second chart class/type string used inside `Function_82310948`. |
| `0x8200b378` | `%s_Lyric.ixb` | Still present, but no reliable xref found. |
| `0x8200b388` | `%s_Lyric` | Referenced near `0x822265b8`, `0x8222721c`, `0x8222730c` in this import. |

Reader strings remain consistent with the previous import:

- `0x820622cc`: `"ixSerializerReader::Load"`
- `0x820622e8`: `.\Serialize\ixSerializerReader.cpp`
- Reader token table includes `Class`, `Size`, `Base`, `UriList`, `Key`, `Objects`, `IsBigEndian`, `NumOfElements`, `Classes`, `Member`, `Members`, `Name`, `Offset`, `Uri`.

## Important writer functions and code regions

### `Function_82499F20`: formatted text/XML write helper

Confirmed facts:

- Address: `0x82499f20`
- Decompilation shows:
  - formats into global/temp buffer `0x82ccbf28` with max length `0x800`
  - scans to the terminating zero byte
  - calls the stream object's vtable slot `+0x38` with buffer and computed length
- This function is repeatedly called with XML/token strings from the IXB writer block.

Writer implication:

- XML-like IXB metadata text is emitted by formatting text fragments, not by a separate DOM writer.
- The exact token order in the writer block is relevant for reproducing game-compatible files.

### `FUN_82499fe8`: raw byte write helper

Confirmed facts:

- Address: `0x82499fe8`
- Calls the same stream object's vtable slot `+0x38`.
- Call sites pass explicit byte pointers and lengths.

Writer implication:

- Binary object data is written separately from the formatted XML metadata.
- The stream abstraction's `+0x38` slot is the common write sink for both formatted text and raw data.

### `Function_8249BE70`: binary object/block record writer

Confirmed facts:

- Address: `0x8249be70`
- Writes the following to the stream at `param_1 + 0x5c` using `FUN_82499fe8`:
  - 4 bytes: local zero value
  - 4 bytes: `param_2`
  - 4 bytes: `param_3`
  - `param_3` bytes: payload at `param_2`
- Increments a counter at `param_1 + 0x60`.
- Stores an offset/position-like value from the stream into a table at `param_1 + 0x4c`.

Hypothesis:

- This is an object-data or chunk writer. The observed binary record shape is strongly:
  - `u32 unknown_zero`
  - `u32 payload_offset_or_pointer_value`
  - `u32 payload_size`
  - `payload_size` bytes payload
- The exact meaning of `param_2` is not proven from this function alone. It may be an offset, pointer, or object identifier depending on the caller.

### `Function_8249BF28`: endian conversion before binary writing

Confirmed facts:

- Address: `0x8249bf28`
- Iterates fields/members recursively.
- Checks a flag at `context + 0x74`.
- When that flag is nonzero, it byte-swaps:
  - scalar 32-bit values for many field type IDs
  - scalar 16-bit values for some field type IDs
  - arrays of 16-bit values
  - arrays of 32-bit values
- Recurses for nested/compound field type `0x1a`.

Writer implication:

- Endianness is not cosmetic. The writer actively mutates serialized field bytes when the context endian flag is set.
- Python writer must treat numeric payload fields as big-endian for X360-compatible binary object data.

### IXB writer region around `0x8249c840` to `0x8249d504`

Confirmed facts from disassembly and string-load scan:

- Writer source string `.\Serialize\ixSerializerWriter.cpp` is referenced near:
  - `0x8249c45c`
  - `0x8249d1f4`
- Top-level header/attributes are emitted near `0x8249c898` to `0x8249c944`:
  - unknown token at `0x82061f00`
  - `IsBigEndian="%s"` at `0x8249c8d8`
  - `IsText="false"` at `0x8249c8e8`
  - `Platform="%s"` at `0x8249c8fc`
  - `NumOfElements="%d"` at `0x8249c918`
  - an additional literal at `0x82061eb4`, probably closing/opening syntax adjacent to `<Classes>`
  - `<Classes>` at `0x8249c940`
- The element count passed to `NumOfElements` is computed as:
  - `*(context + 0x60) + *(context + 0x24)`
  - The context field meanings are not proven, but both are counts used by the writer.
- Class/member metadata generation begins after `<Classes>`:
  - builds a temporary list of class-like records from context data
  - writes `<Class`
  - writes `Name="%s"`
  - conditionally writes `Base`, `Size` and member data
  - writes `<Members>`
  - writes repeated `<Member ... Offset/Base/Size ... />` records
  - writes `</Members>`
  - writes `</Class>`
- The class/member token setup at `0x8249cb3c` to `0x8249cbb0` loads:
  - `</Class>`
  - `</Members>`
  - ` Size="%d"`
  - ` Base="%d"`
  - ` Offset="%d"`
  - `<Member`
  - `<Members>`
  - ` Name="%s"`
  - `<Class`
  - XML escape fragments near `0x82061e28` / `0x82061e34`
- After all classes are written:
  - `</Classes>` at `0x8249d06c`
  - `<UriList>` at `0x8249d07c`
  - repeated URI entries:
    - `<Uri`
    - ` Key="%d"`
    - ` Uri="%s"`
    - a close/self-close fragment from stack/local state
  - `</UriList>` at `0x8249d110`
  - `<Objects>` at `0x8249d120`
- Binary object table/data writing happens after `<Objects>`:
  - calls `FUN_82499fe8` at `0x8249d138` with stream, pointer and size from context stack values
  - loops over object entries at `context + 0x1c` / `context + 0x24`
  - writes three 4-byte values per object before object payload:
    - value from lookup table or object record
    - object/class size-like value from `object + 0x40`
    - object id/key-like value
  - when context flag `+0x74` is nonzero, each of those 4-byte values is byte-swapped before writing
  - writes the raw object payload with `FUN_82499fe8`
- Final close sequence:
  - `</Objects>` at `0x8249d4f0`
  - `</ixb>` at `0x8249d500`

Hypothesis:

- Context `+0x74` is the big-endian output flag. This is supported by the repeated conditional byte swaps and the earlier `IsBigEndian` attribute emission, but the exact struct name is not known.
- Context `+0x24` appears to be object/class count used in loops.
- Context `+0x60` appears to be an emitted object/block count maintained by `Function_8249BE70`.

## Header validation fields

Confirmed functions in XEXLoaderWV import:

| Function | Address | Confirmed behavior |
| --- | --- | --- |
| `Function_82491C28` | `0x82491c28` | Compares 4 bytes at `param_1 + 0x10` with expected tag string. Mismatch returns `0x82000101`. |
| `Function_82491CD0` | `0x82491cd0` | Compares 4 bytes at `param_1 + 0x14` with expected name string. Mismatch returns `0x82000102`. |
| `Function_82491D68` | `0x82491d68` | Reads 16-bit value at `param_1 + 0x18`; returns `0x82000103` if stored version is greater than expected version. |

Additional confirmed accessors in the same region:

- `0x82491c08`: returns `param_1 + 0x10`
- `0x82491c10`: copies 4 bytes into `param_1 + 0x10`
- `0x82491cb0`: returns `param_1 + 0x10` in the disassembly window, but is adjacent to the name field area and needs re-checking before use
- `0x82491cb8`: copies 4 bytes into `param_1 + 0x14`
- `0x82491d58`: reads 16-bit value at `param_1 + 0x18`
- `0x82491d60`: writes 16-bit value at `param_1 + 0x18`
- `0x82491dc8`: reads 16-bit value at `param_1 + 0x1a`
- `0x82491dd0`: writes 16-bit value at `param_1 + 0x1a`
- `0x82491dd8`: compares 16-bit value at `param_1 + 0x1a` against expected value and returns `0x82000104` on mismatch

Writer implication:

- A related binary header object has at least:
  - `+0x10`: 4-byte tag
  - `+0x14`: 4-byte name
  - `+0x18`: 16-bit version
  - `+0x1a`: 16-bit secondary version/flags field
- This header is proven as an engine FileIO validation object, but it is still not proven as the outer `.X360` file header.

## Path and chart/lyric creation paths

Confirmed facts:

- Generic X360 path format `%s\%s.X360` at `0x82011a18` is referenced near `0x82265a7c`.
- `_Cht.X360` and `lpsChart` are used in two chart setup paths:
  - `Function_822A3F70`
  - `Function_82310948`
- Decompilation of `Function_822A3F70` shows a chart object/resource being created with:
  - `_Cht.X360`
  - `lpsChart`
  - a generated/derived path component
  - object allocation sizes `0x5c` and `0x48`
- `%s_Lyric` is referenced near `0x822265b8`, `0x8222721c`, `0x8222730c`.
- `%s_Lyric.ixb` exists but still has no reliable code xref.

Hypothesis:

- Chart resources are stronger writer targets than lyric resources at this point, because `_Cht.X360` and `lpsChart` have confirmed code paths and object creation calls.
- Lyric creation likely has a similar path, but the exact function boundaries around the lyric references still need cleanup.

## I/O and decompression layer

Confirmed facts:

- XEXLoaderWV recovers named kernel/XAM stubs:
  - `NtCreateFile`
  - `NtOpenFile`
  - `NtReadFile`
  - `NtWriteFile`
  - `NtClose`
  - `XamContentCreateEx`
  - `LDIDestroyDecompression`
- Callers of `NtWriteFile` include:
  - `Function_828DBBB0`
  - `Function_828DC570`
  - `Function_828EEBA0`
- `Function_828F33D8` references `XctdDecompression` and appears to participate in compressed file/open handling.
- The IXB serializer writer itself does not call these kernel stubs directly in the recovered call graph. It writes through a stream abstraction.

Writer implication:

- For Python writer work, the serializer byte layout should be implemented first.
- Reproducing the game runtime's stream/file abstraction is not necessary unless we later need package/container installation behavior.

## Vermutete IXB/X360 write order

Strongly supported by writer disassembly:

1. Emit IXB opening/header text containing:
   - `IsBigEndian="%s"`
   - `IsText="false"`
   - `Platform="%s"`
   - `NumOfElements="%d"`
2. Emit `<Classes>`.
3. For each class:
   - emit `<Class`
   - emit `Name="%s"`
   - emit class attributes such as `Base` and `Size` where applicable
   - emit `<Members>`
   - for each member emit `<Member Offset="%d" Base="%d" Size="%d" ... />`
   - emit `</Members>`
   - emit `</Class>`
4. Emit `</Classes>`.
5. Emit `<UriList>`.
6. For each URI entry:
   - emit `<Uri`
   - emit `Key="%d"`
   - emit `Uri="%s"`
   - close the entry
7. Emit `</UriList>`.
8. Emit `<Objects>`.
9. Emit raw object table/data:
   - an initial raw block from context stack values
   - repeated per-object records, with 4-byte fields byte-swapped when big-endian flag is set
   - raw object payload bytes
10. Emit `</Objects>`.
11. Emit `</ixb>`.

Still uncertain:

- The exact opening token before `IsBigEndian` is at/near `0x82061f00` and was not decoded in this pass.
- The exact close token at `0x82061eb4` used before `<Classes>` should be read and matched against real sample bytes.
- Alignment/padding is not yet proven. The writer clearly writes multiple 4-byte values and uses 4-byte raw writes, but no explicit padding string or simple alignment constant was confirmed.

## Hard facts for Python writer implementation

- Metadata text must include the writer token names exactly as recovered:
  - `IsBigEndian`
  - `IsText`
  - `Platform`
  - `NumOfElements`
  - `Classes`
  - `Class`
  - `Name`
  - `Members`
  - `Member`
  - `Offset`
  - `Base`
  - `Size`
  - `UriList`
  - `Uri`
  - `Key`
  - `Objects`
- X360 writer should emit binary numeric object data big-endian.
- `NumOfElements` is a sum of two writer context counters, not just one visible list length.
- Object records include 4-byte fields before raw object payload. At least one helper writes:
  - `u32 0`
  - `u32 param_2`
  - `u32 param_3`
  - `param_3` bytes payload
- The class/member section is written before `UriList`; `UriList` is written before `Objects`.
- The XML-like metadata and binary data share the same stream, so the file is not pure XML.

## Open questions

- What exact bytes/string form open the IXB document before `IsBigEndian`?
- What exact bytes/string at `0x82061eb4` are emitted between `NumOfElements` and `<Classes>`?
- Which real sample offset corresponds to the transition from metadata text to binary object data?
- Which context fields map to class count, object count, URI count and emitted object block count?
- Is the FileIO header at `+0x10/+0x14/+0x18/+0x1a` present in outer `.X360` files, nested IXB objects, or both?
- What is the alignment/padding rule after raw object payloads? No hard rule was confirmed in code yet.
- Can the lyric writer path be recovered as cleanly as the chart path?

## Next concrete Python steps

1. Add a writer-focused scanner that locates the exact opening IXB text, `<Classes>`, `</Classes>`, `<UriList>`, `<Objects>`, `</Objects>` and `</ixb>` offsets in every private sample.
2. For each sample, split the file into:
   - pre-`<Classes>` header text
   - classes/member metadata
   - URI list metadata
   - object metadata boundary
   - binary object payload area
3. Add a strict metadata parser for:
   - `NumOfElements`
   - `IsBigEndian`
   - `Platform`
   - class `Name`
   - member `Offset`, `Base`, `Size`
   - URI `Key`, `Uri`
4. Implement a minimal binary writer that preserves existing class/member/URI metadata and rewrites only object payload bytes first.
5. Treat all numeric object fields as big-endian for X360 output until a counterexample is found.
6. Add a probe for the FileIO header layout in real samples:
   - find candidate 4-byte tag and name fields
   - validate nearby 16-bit version and secondary field
   - compare against the error-code functions at `0x82491c28`, `0x82491cd0`, `0x82491d68`, `0x82491dd8`
7. Only after the existing sample round-trip is byte-stable, implement new Lips 1 compact song generation using the profile from `docs/lips1_target_profile.md`.

