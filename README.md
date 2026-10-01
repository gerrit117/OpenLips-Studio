# OpenLips Studio

**0.1.1 Beta**: a native desktop song editor built on OpenLips' Xbox 360
IXB reverse-engineering tools. Windows, macOS and Linux use the same Python/Qt
sources. The accepted fresh writer targets original Lips (2008), not all LS2
or compressed chart variants.

## Desktop Editor

- MIDI import with track/channel selection and tempo-map conversion.
- UltraStar import preserving note text, timing, lengths, pitch and phrase times.
- Horizontal karaoke bars, editable syllables, pitch names and exact page timing.
- Note creation, dragging/resizing, word/phrase boundaries and undo/redo.
- Local audio/video reference playback, speed control and preview-only offset.
- Unfinished `.olp` projects: versioned JSON with external media references.
- Optional lyrics lookup, experimental syllable suggestions and importer plugins.
- Fresh template-free OG chart/lyric export and experimental DLC packaging.

## Run or Build

Bundled applications include Python; end users do not need to install it.
For source development, install Python 3.11+:

```sh
python -m pip install -e ".[dev]"
python -m studio
python -m pytest -q
python -m PyInstaller --noconfirm OpenLipsStudio.spec
```

Windows output: `dist/OpenLipsStudio/OpenLipsStudio.exe`. Keep its entire folder.
GitHub Actions builds target-native Windows x64, macOS Apple Silicon/Intel and
Linux x64 artifacts. Non-Windows availability is pending successful native CI;
this is not a claim of testing on every Linux distribution.

## Documentation

- [Editor guide](docs/studio.md) and [platform builds](docs/studio_platforms.md).
- [Page timing, projects and community direction](docs/studio_pages_and_community.md).
- [Beta validation](docs/studio_validation.md) and [changelog](CHANGELOG.md).
- [IXB structures](docs/structures.md), [strict graph reader](docs/og_ixb_reader.md).
- [Research / CLI reference](docs/research_overview.md).
- [Experimental DLC builder](docs/dlc_builder.md) and [discovery findings](docs/dlc_import_comparison.md).

## Scope and Rights

`studio/` is the app, `tools/` retains the existing importers/serializers/analyzers,
`tests/` contains synthetic fixtures, and `docs/` contains sanitized findings.
Private samples and generated media stay local and are not distributed.
Earlier Git history still requires a copyrighted-sample audit before the repo
is made public. Current cleanup does not rewrite history or delete local samples.

DLC discovery remains unresolved; structural STFS checks do not prove game
acceptance. Native media/STFS backends are separate and currently Windows-oriented.
Imported media/lyrics require appropriate rights. No community upload is automatic.

Source: GPL-3.0-or-later. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
