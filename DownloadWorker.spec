"""Built-in yt-dlp worker, isolated from Studio UI and optional USDB plugin."""
from pathlib import Path
import sys
import deno
import imageio_ffmpeg
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []
for name in ('yt_dlp', 'yt_dlp_ejs'):
    data, binary, imports = collect_all(name)
    datas += data
    binaries += binary
    hiddenimports += imports
datas += copy_metadata('yt-dlp')
suffix = '.exe' if sys.platform == 'win32' else ''
binaries += [(deno.find_deno_bin(), 'bin'), (imageio_ffmpeg.get_ffmpeg_exe(), 'media')]
notices = Path('build/download-licenses')
if notices.is_dir():
    datas.append((str(notices), 'licenses'))
a = Analysis(['tools/youtube_download.py'], pathex=['.'], datas=datas,
    binaries=binaries, hiddenimports=hiddenimports,
    excludes=['PySide6', 'torch', 'tensorflow', 'numpy', 'scipy', 'matplotlib'], noarchive=False)
for index, entry in enumerate(a.binaries):
    if entry[1] == imageio_ffmpeg.get_ffmpeg_exe():
        a.binaries[index] = ('media/ffmpeg' + suffix, entry[1], 'BINARY')
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OpenLipsDownload', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='OpenLipsDownload')
