# Optional native AI runtime; build with requirements-ai.txt, not the GUI environment.
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
import imageio_ffmpeg

datas, binaries, imports = [], [], []
for package in ('swift_f0', 'demucs', 'faster_whisper', 'ctranslate2'):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    imports += h
binaries.append((imageio_ffmpeg.get_ffmpeg_exe(), 'media'))
datas += [('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')]
notices = Path('build/ai-licenses')
if notices.is_dir():
    datas.append((str(notices), 'licenses'))
a = Analysis(['tools/ai_worker_entry.py'], pathex=['.'], datas=datas, binaries=binaries,
             hiddenimports=imports + ['numpy.core.multiarray', 'numpy.core.numeric'],
             excludes=['PySide6', 'matplotlib', 'IPython', 'pytest'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OpenLipsAI', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='OpenLipsAI')
