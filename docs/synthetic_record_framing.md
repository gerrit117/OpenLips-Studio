# Synthetic IXB record framing correction

Follow-up to [og_ixb_reader.md](og_ixb_reader.md), 2026-09-29.
This iteration fixes serialization only. It does not add chart roots, sequences,
controllers, mode groups, or gameplay logic beyond the existing build variants.

## Evidence and scope

All 119 local chart/lyric samples were considered; 117 plain IXB files were
read sequentially, and two compressed files remain unsupported. Across 216,483
records, every header is three big-endian u32 words: tag, object key, length.
All typed records use the embedded schema index, not the object's byte size.
Raw records use class index zero. No alignment rounding is performed.
These observations occur in 117/117 supported samples: high corpus confidence.
All 2,255 nonnull name/type-name buffers across those 117 files have exactly
reserve bytes and include the null terminator in the used size (high confidence).
Two raw records have the length flag set; the flag semantics remain unresolved.
The synthetic writer emits unflagged lengths, the common observed convention.

Previously the builder wrote a single tag byte followed by an object body.
It also mixed unframed data and runtime-style vector wrappers into Objects.
The strict reader rejected 22/22 generated files at the first record.

## Implemented correction

- Resolve typed record tags from each generated file's own class order.
  Hardcoded 0x28/0x40 tags are removed: they are not universal class IDs.
- Write complete 12-byte big-endian headers and unique nonzero object keys.
- Write string buffers, reference-vector buffers, WordData buffers, Text type
  name and Text payload as separately framed raw records.
- Include string terminators in name-vector reserve/size, matching 2,255/2,255
  corpus buffers rather than leaving the terminator outside the declared size.
- Reference-vector raw buffers contain only entries and reserved space, not a
  second data/reserve/size/allocator wrapper. Owner fields retain that wrapper.
- WordData buffers use the observed 20-byte element layout; offset/length are
  element +4/+8. Reserve 32 is backed by 640 bytes, with one used element.
- The Text payload key remains 0x12345678. FileImage/RawFileImage data fields
  reference that record; data reserve/size still equal its payload byte length.
- Give existing ownership objects distinct keys, and fix the chart asset name
  reference to the already emitted chart package-name buffer.
- Include NumOfElements for every level, including bare, counting raw records.
- Validate framing, counts, known references, selected vector reserves and
  generated lyric fragments before writing output files.
- Replace the builder's byte-scan debug summaries with strict schema diagnostics.

Package/list/allocator semantics and chart root relationships are not newly
reconstructed here. Existing sequence/music-pointer isolation choices remain.
One vector schema declaration is added to bare charts to describe their already
existing embedded WordData vector; it does not create a new runtime object.

## Variant compatibility

All old level names are retained, but outputs are intentionally not byte
compatible with their invalid predecessors. `bare` and `tags` now produce
identical files: both must use correct framing, count metadata and schema tags.
They remain available as aliases for the same no-ownership baseline. To repeat
old crash comparisons, retain the original private outputs separately.

| Level | Chart records | Lyric records | Strict graph errors |
|---|---:|---:|---:|
| bare | 10 | 3 | 0 |
| tags | 10 | 3 | 0 |
| lyric-ownership | 10 | 14 | 0 |
| full-current | 18 | 14 | 0 |
| chart-root-minimal | 25 | 14 | 0 |
| chart-root-empty-sequence-vector | 22 | 14 | 0 |
| chart-root-empty-seqcode-vector | 24 | 14 | 0 |
| chart-root-one-seqcode | 24 | 14 | 0 |
| chart-root-no-music-pointers | 25 | 14 | 0 |
| chart-root-index-only | 25 | 14 | 0 |
| chart-root-musicdata-only | 25 | 14 | 0 |

Counts use the default three synthetic notes. The lyric count increases by one
because the Text type name and payload are now two real records, not an inline
compound blob. Each pair resolves three lyric-to-melody links and the expected
three text fragments. All 22 generated files pass exact sequential traversal.
Confidence: high for offline framing; **runtime acceptance remains untested**.

## Reproduce

```powershell
python tools/build_minimal_ixb_pair.py --synthetic-level all `
  --out-dir private/outputs/record_framing_v2 --stem TinySynthetic
python tools/walk_ixb_graph.py private/outputs/record_framing_v2
python -m pytest -q
```

Outputs remain private and ignored. No real sample data is copied, rewritten,
or committed. Existing destination files are refused unless --force is given.
Older comparison tools can still label payload-length low bytes as marker
prefixes; those heuristic counts must not be read as actual emitted class tags.
Use the builder's sequential diagnostics and walk_ixb_graph for this iteration.

## Next Runtime Test

Re-test the corrected no-chart-ownership baseline and existing chart isolation
levels in the known-working test package. Do not infer game acceptance from
offline checks. Remaining candidates include incomplete member type metadata,
list sentinel semantics, allocator conventions, asset-to-chart ownership and
controller/prototype relationships. Those are hypotheses, not established
required fixes. Capture the new loader path before adding more structures.
