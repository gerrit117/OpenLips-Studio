# AMD AI acceleration

## Scope

Studio's AI dialog offers Auto, CPU, AMD Radeon (ROCm), NVIDIA CUDA and Apple
Metal. On Windows, Auto detects an AMD display adapter and selects the isolated
AMD engine. The engine checks actual PyTorch GPU availability; unsupported GPUs
or runtime failures fall back to CPU. No driver changes are performed by Studio.

The Windows AMD companion uses Python 3.12, PyTorch 2.9.1 and AMD's official
ROCm 7.2.1 wheels. It is isolated from the normal AI engine and requires roughly
5 GB installed space before downloaded model weights. Frozen builds include
their interpreter; users do not need to install Python or select a runtime path.
The runtime downloader uses a distinct `windows-x64-amd` asset, validates its
checksum, rejects unsafe archive paths, and checks expanded disk requirements.

Demucs vocal separation and OpenAI Whisper transcription run on ROCm. PyTorch
exposes HIP GPUs through its `cuda` API, but reports and UI retain the AMD label.
SwiftF0 pitch extraction and optional lyric alignment remain CPU operations.
Whisper's unavailable Triton timing kernels also fall back to CPU implementations.

CTranslate2's CUDA backend is not an AMD backend. AMD transcription therefore
uses original OpenAI Whisper. CPU fallback inside the AMD engine also uses
PyTorch Whisper: mixing CTranslate2 and ROCm in the same Windows process caused
an OpenMP runtime conflict in testing. No unsafe duplicate-OpenMP override is used.
An unhandled native GPU process crash triggers at most one CPU retry; cancelling
an analysis never triggers a retry. Analysis output is temporary until accepted.

## Local verification, 2026-10-03

Hardware: Radeon RX 7900 XTX, Windows driver 32.0.31019.2002. Tests used local
user-provided audio, not committed media. No drivers or original files changed.

| Test | Result |
| --- | --- |
| HIP tensor allocation and reduction | Passed on RX 7900 XTX |
| 35-second audio, Demucs + Whisper tiny, explicit AMD | Passed, 29.485 s |
| 20-second audio, same models, Auto | Passed, AMD selected, 21.079 s |
| 20-second audio, explicit CPU in AMD environment | Passed, 99.484 s |
| Frozen standalone AMD engine, 20-second audio | Passed, 24.187 s; separation/transcription AMD |

These are smoke tests, not controlled performance or accuracy benchmarks. GPU
FP16 and CPU FP32 outputs can differ. Timings include different warm-up/cache
conditions. No claim is made that generated lyrics or notes need no correction.

Unsupported AMD cards, other drivers, Linux ROCm and Apple Metal were not tested
on hardware here. The downloadable AMD companion currently targets Windows x64.
An installed AMD adapter alone does not imply ROCm compatibility.

## Build and references

Install `requirements-ai-amd-windows.txt` in a separate Python 3.12 environment,
then build `AIWorker.spec`. Place its complete output alongside Studio under
`ai-amd/`, or package it with `tools/package_ai_runtime.py --flavor amd` for
automatic verified download. Keep the generated dependency license inventory.

- [AMD Windows PyTorch installation](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/windows/install-pytorch.html)
- [AMD Windows compatibility matrix](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/windows/windows_compatibility.html)
- [CTranslate2 hardware support](https://opennmt.net/CTranslate2/hardware_support.html)
- [OpenAI Whisper](https://github.com/openai/whisper)
