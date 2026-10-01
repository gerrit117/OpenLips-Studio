# Desktop distributions

The editor, MIDI/UltraStar import, projects and fresh OG IXB writer share the
same Python/Qt sources across platforms. A frozen release includes Python,
Qt, dependencies and dictionaries: end users do not install Python separately.
Source checkout/development does require Python 3.11+.

Native builds are required; PyInstaller is not a cross-compiler. The build
matrix produces Windows x64, macOS Apple Silicon, macOS Intel and Linux x64
artifacts. macOS gets an `.app` bundle plus the portable build directory.
Artifacts include smoke-test output; success is reported only after the jobs
actually complete. Apple signing/notarization and installers remain pending.
Run `36818350412` completed successfully on all four native targets for 0.1.1 Beta.

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
A portable editor is not proof that these backends work on macOS/Linux.
No unsigned Xbox content or copyrighted media is bundled in app artifacts.

References: [PyInstaller platform builds](https://pyinstaller.org/en/stable/usage.html),
[current GitHub runner targets](https://github.com/actions/runner-images),
[Qt Linux runtime requirements](https://doc.qt.io/qt-6/linux.html).
