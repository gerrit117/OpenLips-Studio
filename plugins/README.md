# OpenLips Studio plugins

Plugins live separately from the Studio host. Native process plugins have their
own executable, dependencies and models in platform-specific **`.opl`** packages.
Studio does not install Python packages into itself or import their runtime code.

| Plugin | What it does | Requirements |
| --- | --- | --- |
| [Basic Pitch](basic_pitch/README.md) | Local audio-to-MIDI and editable melody draft, using Spotify's model | Matching platform `.opl`; isolated vocal audio recommended; no account or API key |
| [Example lyric mapping](example_lyrics/README.md) | Developer example assigning words from a text file to existing notes | Build its standalone executable on the target platform; not an AI model |

USDB search/import and the manual YouTube download are built into Studio. They
do not require installing an additional `.opl` plugin. The `usdb_downloader`
directory currently contains the bundled backend source, not a separate plugin
download for users.

Install the matching package using **Werkzeuge > Plugins > .opl installieren**,
then explicitly enable it. Plugins execute with your user permissions, not in a
security sandbox. Only use trusted code. Declared permissions are informational.

Basic Pitch packages: [Windows](https://github.com/gerrit117/OpenLips-Studio/releases/download/v0.4.6-beta.3/Basic-Pitch-0.4.0-2-windows-x64.opl),
[macOS Apple Silicon](https://github.com/gerrit117/OpenLips-Studio/releases/download/v0.4.6-beta.3/Basic-Pitch-0.4.0-2-macos-arm64.opl),
[macOS Intel](https://github.com/gerrit117/OpenLips-Studio/releases/download/v0.4.6-beta.3/Basic-Pitch-0.4.0-2-macos-x64.opl),
[Linux](https://github.com/gerrit117/OpenLips-Studio/releases/download/v0.4.6-beta.3/Basic-Pitch-0.4.0-2-linux-x64.opl).
These existing downloads remain available for compatibility; new Studio releases
list only the system installation files.

See [the plugin developer guide](../docs/studio_plugins.md) for the manifest,
process protocol, packaging, UI integration, trust model and extension limits.
Generated models/runtimes/packages belong in ignored build/output directories,
not in Git. Song projects use `.olp`, not `.opl`.
