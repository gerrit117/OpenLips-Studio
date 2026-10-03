# Optional native AI runtime; build with requirements-ai.txt, not the GUI environment.
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
import imageio_ffmpeg
import importlib.util
import importlib.metadata

datas, binaries, imports = [], [], []
for package in ('swift_f0', 'demucs', 'faster_whisper', 'ctranslate2', 'whisper'):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    imports += h
binaries.append((imageio_ffmpeg.get_ffmpeg_exe(), 'media'))
if importlib.util.find_spec('rocm_sdk'):
    for package in ('rocm_sdk', 'rocm_sdk_core', 'rocm_sdk_libraries_custom',
                    '_rocm_sdk_core', '_rocm_sdk_libraries_custom'):
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        imports += h
    from PyInstaller.utils.hooks import copy_metadata
    for distribution in ('rocm', 'rocm-sdk-core', 'rocm-sdk-libraries-custom'):
        datas += copy_metadata(distribution)
datas += [('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')]
notices = Path('build/amd-ai-licenses' if importlib.util.find_spec('rocm_sdk') else 'build/ai-licenses')
if notices.is_dir():
    datas.append((str(notices), 'licenses'))
a = Analysis(['tools/ai_worker_entry.py'], pathex=['.'], datas=datas, binaries=binaries,
             hiddenimports=imports + ['numpy.core.multiarray', 'numpy.core.numeric'],
             excludes=['PySide6', 'matplotlib', 'IPython', 'pytest'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OpenLipsAI', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='OpenLipsAI')
