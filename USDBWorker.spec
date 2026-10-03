"""Standalone Syncer bridge; build in the isolated USDB Python environment."""
from pathlib import Path
import os
import sys
import deno
import subprocess
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

source = Path(os.environ['OPENLIPS_USDB_SOURCE']).resolve(strict=True)
revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
if revision != 'c8f9157bed4d45fc646e5d4c4450074ef0925aae':
    raise ValueError('USDB source must match the pinned upstream revision')
if not (source / 'src/usdb_syncer/gui/forms/MainWindow.py').is_file():
    raise ValueError('Run upstream generate_pyside_files.py before freezing')
sys.path.insert(0, str(source / 'src'))
datas, binaries, hiddenimports = [], [], []
for name in ('usdb_syncer', 'yt_dlp', 'yt_dlp_ejs', 'deno', 'keyring'):
    data, binary, imports = collect_all(name)
    datas += data
    binaries += binary
    hiddenimports += imports
media = Path(os.environ['OPENLIPS_USDB_MEDIA']).resolve(strict=True)
suffix = '.exe' if sys.platform == 'win32' else ''
for name in ('ffmpeg', 'ffprobe'):
    binary = media / (name + suffix)
    if not binary.is_file():
        raise ValueError('Missing bundled ' + name)
    binaries.append((str(binary), 'bin'))
binaries.append((deno.find_deno_bin(), 'bin'))
datas += copy_metadata('usdb_syncer') + copy_metadata('yt-dlp')
notices = Path('build/usdb-licenses')
if notices.is_dir():
    datas.append((str(notices), 'licenses'))
a = Analysis(['plugins/usdb_downloader/worker.py'], pathex=[str(source / 'src'), '.'],
             datas=datas, binaries=binaries, hiddenimports=hiddenimports,
             excludes=['torch', 'tensorflow', 'demucs', 'matplotlib', 'pytest'], noarchive=False)
if sys.platform == 'win32':
    # Use Windows' ICU shim, not an unrelated developer-tool DLL from PATH.
    a.binaries = [entry for entry in a.binaries
                  if entry[0].lower() != 'icuuc.dll' and
                  not (entry[0].lower().startswith('icudt') and 'poppler' in entry[1].lower())]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OpenLipsUSDB', console=True,
          icon='studio/assets/app-icon.ico' if sys.platform == 'win32' else None)
coll = COLLECT(exe, a.binaries, a.datas, name='OpenLipsUSDB')
