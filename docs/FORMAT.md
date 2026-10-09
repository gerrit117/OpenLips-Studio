# Format Reference

Current authoring references:

- [OG runtime container, chart and resource structure](og_lips_runtime_format.md)
- [Owned chart/lyric writer](runtime_owned_builder.md)
- [Lyric resources and word mappings](lyric_x360_format.md)
- [Page breaks and native marker relationships](lyric_pages.md)
- [Page-layout policy](intelligent_page_breaks.md)
- [Community song `.ols` format](song_bundle.md)
- [DLC manifest and package structure](dlc_builder.md)
- [Song packs and USB storage](song_packs_usb.md)
- [Project/version storage](workspace_and_versions.de.md)

`.olp` projects use `openlips-studio-project`, schema 1. New optional fields
`album`, `genre`, `year`, `created_at`, `modified_at` remain backwards compatible.
Dates use ISO 8601 UTC. Old files fall back to their filesystem modification
time; that is not a recovered original creation time. Date fields do not define
library musical identity. Project saves and exports are separate operations.

New unsigned DLC headers contain `OpenLips Studio; created=<ISO UTC>; ...` in
the display-description field. The header SHA-1 is recomputed before canonical
naming. This does not alter the XML, chart, lyric or media bytes and is not a
Microsoft signature. Read-only USB inventory can read CON/PIRS and dual-copy
tables; the authoring/installation verifier still accepts only supported
unsigned LIVE packages. Inventory alone is not payload/signature validation.

Original-duration/native display comparisons remain ongoing research. Runtime
compatibility should not be inferred solely from structural round trips.
