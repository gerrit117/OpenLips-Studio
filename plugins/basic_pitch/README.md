# Basic Pitch process plugin

Spotify Audio Intelligence Lab's [Basic Pitch](https://github.com/spotify/basic-pitch)
turns audio into an editable note draft and MIDI. The OpenLips integration is
independent and not endorsed by Spotify.

## Install and use

Download the **Basic-Pitch-0.4.0-2-<platform>.opl** matching your Studio platform
from Releases. In Studio open **Werkzeuge > Plugins**, choose **.opl installieren**,
then enable Basic Pitch after the trust confirmation.

The package includes the model, Python, ONNX Runtime and scientific dependencies.
It runs offline without a Spotify account, API key or separate Python installation.
Nothing is installed into Studio's Python environment. Studio works without this
plugin installed. The older Studio 0.2.0 bundled adapter is not used by 0.2.1.

Choose WAV, FLAC, MP3, OGG or M4A audio. Adjust detection thresholds, minimum note
duration in milliseconds, MIDI pitch range and overlap filtering. Review the
preview, save the MIDI or explicitly accept the notes; acceptance is undoable.

Prefer isolated vocals. Basic Pitch is instrument-agnostic, not a vocal separator,
lyric transcription engine or tempo detector. Review note pitch, durations and
phrase boundaries. Absolute timestamps are retained; the editor grid defaults to
120 BPM. No audio is uploaded.

## Build on the target OS

Use isolated Python 3.11, not Studio's GUI environment:

```sh
python -m pip install -r tools/basic_pitch_requirements.txt
python -m pip install --no-deps basic-pitch==0.4.0
python plugins/basic_pitch/worker.py --self-test --output private/worker-source-smoke
python -m PyInstaller --noconfirm BasicPitchWorker.spec
python tools/collect_runtime_notices.py --out dist/OpenLipsBasicPitch/licenses
python -m tools.package_basic_pitch_plugin
```

Run from the repository root. Build separately on Windows x64, macOS Apple Silicon,
macOS Intel and Linux x64. CI tests installation of the actual `.opl` and inference
through the frozen GUI on all four targets. Native runtime symlinks and executable
permissions are preserved. No Apple Developer signing/notarization is supplied.

`engine.py` and `worker.py` are plugin code; neither imports Studio. The manifest
describes parameters and the native entrypoint. Studio only understands the
generic request/progress/result protocol.

## Credits and licenses

Basic Pitch and its model: Copyright 2022 Spotify AB, Apache-2.0. Integration code:
OpenLips, GPL-3.0-or-later. ONNX Runtime and scientific libraries retain their own
licenses; the package includes runtime version inventories and shipped notices.
The requirements choose ONNX rather than pulling in TensorFlow/CoreML. The Intel
macOS build pins Numba below 0.63 because newer versions dropped Intel-Mac wheels.
