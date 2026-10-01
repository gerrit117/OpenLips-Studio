"""Build with the isolated Python 3.11 environment, before the GUI bundle."""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
import sys

datas = collect_data_files('basic_pitch') + copy_metadata('basic-pitch')
for package in ('numpy', 'librosa', 'mir_eval', 'onnxruntime', 'pretty_midi', 'resampy',
                'scikit-learn', 'scipy', 'soundfile', 'numba', 'llvmlite', 'soxr', 'mido'):
    datas += copy_metadata(package)
a = Analysis(['plugins/basic_pitch/worker.py'], pathex=['.'], datas=datas,
             hiddenimports=collect_submodules('librosa') + ['onnxruntime', 'basic_pitch.inference'],
             excludes=['PySide6', 'qtawesome', 'tensorflow', 'coremltools', 'tflite_runtime',
                       'matplotlib', 'IPython', 'pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OpenLipsBasicPitch', console=True,
          icon='studio/assets/app-icon.ico' if sys.platform == 'win32' else None)
coll = COLLECT(exe, a.binaries, a.datas, name='OpenLipsBasicPitch')
