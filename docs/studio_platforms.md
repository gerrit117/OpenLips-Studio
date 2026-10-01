# Desktop distributions

The editor, MIDI/UltraStar import, projects and fresh OG IXB writer share the
same Python/Qt sources across platforms. A frozen release includes Python,
Qt, dependencies and dictionaries: end users do not install Python separately.
Source checkout/development does require Python 3.11+.

From 0.2.1 Beta, Basic Pitch is distributed separately as a platform-specific
`.opl` containing its independent Python 3.11 / ONNX runtime and model. Studio
works without it installed; no extra user Python installation is required for
either download. The actual plugin package is installed and tested through the
frozen GUI before release. See the [plugin guide](studio_plugins.md).
On Linux install the desktop icon using
`sh _internal/studio/assets/install-desktop-entry.sh` from the Studio directory.

Native builds are required; PyInstaller is not a cross-compiler. The build
matrix produces Windows x64, macOS Apple Silicon, macOS Intel and Linux x64
artifacts. macOS gets an `.app` bundle plus the portable build directory.
Artifacts include smoke-test output; success is reported only after the jobs
actually complete. Apple signing/notarization remains pending. Version 0.3.0 adds
a Windows per-user Inno Setup wizard and native macOS DMG with an Applications
shortcut; neither requires users to install Python. Linux retains the portable
archive and desktop-entry installer.
Run `36818350412` completed successfully on all four native targets for 0.1.1 Beta.
From 0.1.3 Beta, successful main-branch builds publish versioned prereleases
with all four native archives and SHA-256 checksums. Windows/macOS use ZIP;
Linux uses tar.gz to preserve executable permissions. All matrix jobs must pass
before publishing. An existing version tag from another commit is not overwritten:
code changes require an app version bump. Same-commit retries may replace assets.
Downloads live under [GitHub Releases](https://github.com/gerrit117/OpenLips-Studio/releases).
The repository remains private; this workflow does not change its visibility.

Linux initially uses an Ubuntu 22.04/glibc build baseline to avoid unnecessarily
requiring a newer glibc. The complete portable folder is needed. It is intended
for modern glibc-based desktop distributions, not promised for every Linux:
Ubuntu/Debian/Fedora compatibility requires actual testing. Alpine/musl and ARM
Linux are not covered. Desktop X11/Wayland, OpenGL and audio runtime libraries
may still need installation through the distribution's package manager.
The Linux CI baseline installs `libegl1`, `libgl1`, `libopengl0`, `libxcb-cursor0`,
`libxkbcommon-x11-0` and `libpulse0`. Package names can differ on other distributions.
AppImage/Flatpak/DEB/RPM packaging is a follow-up, not another editor rewrite.

The Windows application bundles its native OG media encoder. Native STFS remains
a separate backend; optional cover-video preparation requires FFmpeg. Final OG
media encoding is refused on macOS/Linux; see [media scope](studio_media.md).
On those systems, game export needs already-compatible media: OG uses the
tested ASF/WVC1/WMA Pro profile, while experimental DLC packaging requires
RIFF/XWMA full audio and preview. Editor reference playback is not a codec
conversion. See [exact profiles and preparation](studio_media.md#already-compatible-media-on-macos-and-linux).
A portable editor is not proof that these backends work on macOS/Linux.
No unsigned Xbox content or copyrighted media is bundled in app artifacts.

## Optional built-in AI engine

SwiftF0's small model is bundled with Studio. Heavy stages use the separate
OpenLips-AI archive, not an `.opl` plugin. Extract it and select OpenLipsAI in
Tools -> Create chart from audio (AI). Placing its `ai` folder beside the Windows
Studio executable enables automatic discovery. Larger named models download
on first use to `~/.cache/openlips/ai`; audio is processed locally.

Optional developer installation uses Python 3.11 and `requirements-ai.txt`.
Windows/Linux release engines use Torch 2.8 CPU wheels. macOS Intel pins the
last supported Torch 2.2.2 Intel wheel and NumPy <2; Apple Silicon uses Torch
2.8. Studio excludes these heavy dependencies. Actual GPU acceleration
requires compatible runtime builds/drivers; CPU is the tested baseline.
See [tests and limitations](ai_song_creation_test_report.md).

References: [PyInstaller platform builds](https://pyinstaller.org/en/stable/usage.html),
[current GitHub runner targets](https://github.com/actions/runner-images),
[Qt Linux runtime requirements](https://doc.qt.io/qt-6/linux.html).
