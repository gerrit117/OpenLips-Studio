# Third-party Components

OpenLips Studio source is GPL-3.0-or-later. See LICENSE. Songs, game files,
private samples and user-imported media are not licensed by this project.

The desktop application uses these separately licensed dependencies:

| Component | License / source |
| --- | --- |
| PySide6 / Qt | LGPLv3/GPLv3/commercial alternatives; [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html) |
| Mido | MIT; [repository](https://github.com/mido/mido) |
| Pyphen | GPL/LGPL/MPL alternatives; dictionaries have their own notices; [repository](https://github.com/Kozea/Pyphen) |
| QtAwesome | MIT; bundled icon fonts have their own licenses; [repository](https://github.com/spyder-ide/qtawesome) |
| PyInstaller bootloader | GPL with bootloader exception; [license](https://pyinstaller.org/en/stable/license.html) |
| Python | PSF license; [license](https://docs.python.org/3/license.html) |

The optional native STFS backend is separate and uses Velocity/Botan; see
[backend documentation](docs/dlc_builder.md). It is not bundled in the desktop
artifact. No Xbox SDK components or game executables are distributed.

Before distributing binaries publicly, inventory the exact bundled dependency
versions and preserve their complete notices/font licenses and source-offer
requirements as applicable. This summary is not a substitute for those files.
