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

Linux initially uses an Ubuntu 22.04/glibc build baseline to avoid unnecessarily
requiring a newer glibc. The complete portable folder is needed. It is intended
for modern glibc-based desktop distributions, not promised for every Linux:
Ubuntu/Debian/Fedora compatibility requires actual testing. Alpine/musl and ARM
Linux are not covered. Desktop X11/Wayland, OpenGL and audio runtime libraries
may still need installation through the distribution's package manager.
AppImage/Flatpak/DEB/RPM packaging is a follow-up, not another editor rewrite.

Native STFS and legacy media-conversion helpers remain separate Windows
backends. A portable editor is not proof that these backends work on macOS/Linux.
No unsigned Xbox content or copyrighted media is bundled in app artifacts.

References: [PyInstaller platform builds](https://pyinstaller.org/en/stable/usage.html),
[current GitHub runner targets](https://github.com/actions/runner-images),
[Qt Linux runtime requirements](https://doc.qt.io/qt-6/linux.html).
