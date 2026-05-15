# IXB Ownership Field Diff Notes

This note is a focused, read-only comparison of the ownership/container fields
that are most likely to cause the current synthetic lyric IXB hard crash.

Generated local report:

```powershell
py tools\compare_ownership_fields.py `
  --corpus-root private\samples `
  --real-lyric private\samples\lyrics\1234_Lyric.X360 `
  --synthetic-root private\outputs\minimal_ixb_variants `
  --stem 1234_Lyric.X360 `
  > private\outputs\minimal_ixb_variants\ownership_field_diff_after_fix.txt
```

The generated report is intentionally kept under `private/outputs` and should
not be committed.

## Corpus Summary

The current analysis scans all local lyric samples under `private/samples`.

- lyric samples analyzed: 60
- plain IXB samples: 59/60, confidence high
- canonical `ixRawFileImage` present: 59/60, confidence high
- `ixRawFileImage.data_ptr` equals a Text payload hash: 59/59 applicable files, confidence high
- `ixRawFileImage.data_reserve` and `data_size` equal the matched Text payload length: 59/59 applicable files, confidence high
- `ixRawFileImage` type reserve/size are `5/5`: 59/59 applicable files, confidence high
- every detected Text resource uses compact type header `pointer, length, inline Text\0`: 59/60 files, confidence high
- `ixAssetPackage` with an asset vector is present in 27/60 files, confidence low as a corpus-wide invariant

Observed distributions:

- Text resource count: `0:1`, `2:59`
- `ixAssetPackage.asset_vector_reserve`: `0:10`, `32:17`, `None:33`
- `ixAssetPackage.asset_vector_size`: `0:10`, `1:17`, `None:33`
- compact Text type header count per file: `0:1`, `2:59`

The full generated report lists every analyzed file path. The one sample with
zero detected Text resources is treated as unsupported for these ownership
rules rather than evidence against them.

Confidence levels:

- high: present in at least 90% of applicable samples
- medium: present in at least 50% of applicable samples
- low: present in less than 50% of applicable samples or only one/few files

## Controlled Variant Comparison

Synthetic variants compared:

- `bare`
- `tags`
- `lyric-ownership`
- `full-current`

Only `lyric-ownership` and `full-current` include the synthetic ownership
chain.

## Strongest Finding

Across the corpus, `ixRawFileImage.data_ptr` stores the Text resource payload
hash in 59/59 applicable files. The previous synthetic ownership chain used a
fake runtime pointer there.

Real canonical `ixRawFileImage`:

- tag: `0x54`
- offset: `0x000012BD`
- `asset_package_ptr = 0x0719D6C0`
- `data_ptr = 0x14BB2C10`
- `data_reserve = 1666`
- `data_size = 1666`
- `type_name_ptr = 0x099221E8`
- `type_reserve = 5`
- `type_size = 5`

That `data_ptr` value exactly matches Text resource 0's payload hash in the
real example:

- Text payload hash: `0x14BB2C10`
- Text payload length: `1666`

Fixed synthetic canonical `ixRawFileImage` in both `lyric-ownership` and
`full-current`:

- tag: `0x54`
- offset: `0x00000C25`
- `asset_package_ptr = 0x05000400`
- `data_ptr = 0x12345678`
- `data_reserve = 22`
- `data_size = 22`
- `type_name_ptr = 0x05000800`
- `type_reserve = 5`
- `type_size = 5`

The synthetic Text resource hash is `0x12345678`, and the fixed synthetic
`ixRawFileImage.data_ptr` now equals that hash. `data_reserve` and `data_size`
also equal the generated Text payload length.

Conclusion: the concrete hash-vs-fake-pointer mismatch is fixed for synthetic
lyric ownership serialization.

## Vector And Container Notes

No high-confidence synthetic ownership candidate currently shows
`count > 0` with a null pointer. Zero/null allocator-like fields also occur in
the real file, so zero allocator fields alone should not be treated as fatal.

The asset vector is not present as a strong corpus-wide invariant, but where
the real canonical `ixAssetPackage` asset vector is present, the common reserve
style is `32` with size `1`.

Real 1234 `ixAssetPackage` canonical asset vector:

- tag: `0x5C`
- offset: `0x00001335`
- `asset_vector_ptr = 0x071989C0`
- `asset_vector_reserve = 32`
- `asset_vector_size = 1`

Synthetic `ixAssetPackage` canonical asset vector:

- `asset_vector_ptr = 0x05000500`
- `asset_vector_reserve = 32`
- `asset_vector_size = 1`

This is not an obvious null/count violation, but it still differs from the
real pointer namespace.

The Text resource type-name header is now serialized in the compact form seen
across 59/60 local lyric files:

- pointer/hash-ish word
- 32-bit length (`5`)
- inline `Text\0`
- padding
- payload hash
- payload length

The synthetic builder no longer emits the Text type name as a runtime-style
standalone `_data/_reserve/_size/_allocator` vector.

## Variant Interpretation

- `bare`: no ownership chain, so no `ixRawFileImage` or `ixAssetPackage`
  mismatch is present.
- `tags`: marker tags and `NumOfElements` only; still no ownership chain.
- `lyric-ownership`: introduces the lyric ownership chain with fixed
  `ixRawFileImage.data_ptr = Text payload hash`.
- `full-current`: same fixed lyric ownership serialization as
  `lyric-ownership`.

This keeps the next Xbox test focused on whether the previous hard crash was
caused by the malformed lyric ownership serialization rather than marker tags
or object count alone.

## Next Safe Direction

Do not add more chart roots or sequence/controller structures yet. The next
Xbox test should compare the existing controlled variants after this fix:

- `bare`
- `tags`
- `lyric-ownership`
- `full-current`

If `lyric-ownership` no longer hard-crashes, the previous ownership-chain
pointer/hash mismatch was likely causal. If it still hard-crashes, keep
investigating the remaining ownership references before adding chart roots.
