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
| Basic Pitch / model | Apache-2.0; Copyright 2022 Spotify AB; [repository, authors and license](https://github.com/spotify/basic-pitch) |
| ONNX Runtime | MIT; [repository](https://github.com/microsoft/onnxruntime) |
| SwiftF0 0.3.0 / bundled ONNX model | MIT; [repository and license](https://github.com/lars76/swift-f0) |
| Demucs 4.0.1 (optional engine) | MIT; Meta and contributors; [repository](https://github.com/facebookresearch/demucs) |
| Whisper / optional models | MIT; OpenAI; [repository and license](https://github.com/openai/whisper) |
| faster-whisper 1.2.1 | MIT; SYSTRAN and contributors; [repository](https://github.com/SYSTRAN/faster-whisper) |
| CTranslate2 | MIT; [repository](https://github.com/OpenNMT/CTranslate2) |
| PyTorch / TorchAudio | BSD-style licenses and dependency notices; [PyTorch](https://github.com/pytorch/pytorch), [TorchAudio](https://github.com/pytorch/audio) |
| imageio-ffmpeg | BSD-2-Clause wrapper; bundled FFmpeg binary has its own license/build configuration; [repository](https://github.com/imageio/imageio-ffmpeg) |
| USDB Syncer (development plugin) | GPL-3.0-only; Markus Böhning and contributors; [repository](https://github.com/bohning/usdb_syncer) |
| yt-dlp (USDB plugin) | Upstream source Unlicense; packaged dependency notices must also be preserved; [repository](https://github.com/yt-dlp/yt-dlp) |

The isolated Basic Pitch worker also uses NumPy, SciPy, Librosa, Pretty MIDI,
Mir Eval, Resampy, scikit-learn, Numba/LLVM, SoundFile/libsndfile, SoXR and their
dependencies. Each native build includes a `licenses/inventory.json` containing
the exact installed versions, plus license/notice files shipped by those packages.
The worker has its own inventory under `plugin-runtime/OpenLipsBasicPitch/licenses`.
Basic Pitch is credited to Spotify's Audio Intelligence Lab and its authors;
the plugin is an independent integration, not a Spotify service or endorsement.
Its model is distributed with the upstream Python package under its license.

The optional built-in AI workflow is independently implemented and inspired by
UltraSinger (rakuri255 and contributors) and UltraSinger Studio
(lazinessss999-dot and contributors), whose top-level projects declare MIT.
Their installers and bundled environments are not redistributed. The optional
AI engine has its own exact dependency inventory and notices. Larger Demucs
and Whisper weights download from their named upstream registries to a local
cache, not from arbitrary user-provided model code. No game songs, vocal stems,
lyrics or original game executables are included in any release artifact.

The optional native STFS backend is separate and uses Velocity/Botan; see
[backend documentation](docs/dlc_builder.md). It is not bundled in the desktop
artifact. No Xbox SDK components or game executables are distributed.

Before distributing binaries publicly, inventory the exact bundled dependency
versions and preserve their complete notices/font licenses and source-offer
requirements as applicable. This summary is not a substitute for those files.

The developing USDB plugin uses the upstream GUI and downloader in an isolated
process. Its dependency runtime and authenticated download flow are not yet
released/validated. Before publishing a native plugin, preserve upstream source,
licenses and notices, as well as the FFmpeg build's complete notices and source
requirements. Adding a Python package's license inventory alone is not enough
for the third-party FFmpeg executable contained in its wheel.
