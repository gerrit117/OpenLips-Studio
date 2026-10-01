# Native builds must run on the target OS; do not cross-compile Qt bundles.
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
import sys
from studio import DISPLAY_VERSION
from pathlib import Path

media_helper = Path('private/runtime/og-framing-test/transcode_windows.exe')
media_binaries = [(str(media_helper), 'media')] if sys.platform == 'win32' and media_helper.is_file() else []
import imageio_ffmpeg
ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
notices = Path('build/studio-licenses')
notice_data = [(str(notices), 'licenses')] if notices.is_dir() else []
icon = 'studio/assets/app-icon.ico' if sys.platform == 'win32' else None
asset_data = [(str(path), 'studio/assets') for path in Path('studio/assets').iterdir()
              if path.is_file() and path.suffix in ('.png', '.ico', '.icns', '.sh')]
ai_source_data = [(str(path), 'ai_backend/' + str(path.parent)) for path in map(Path, (
    'studio/__init__.py', 'studio/model.py', 'studio/lrc.py', 'studio/ai_chart.py', 'studio/ai_alignment.py',
    'tools/__init__.py', 'tools/create_ai_chart.py', 'tools/align_lyrics.py'))]

a = Analysis(['studio/launcher.py'], pathex=['.'],
             datas=collect_data_files('qtawesome') + collect_data_files('pyphen') + collect_data_files('swift_f0') + copy_metadata('swift-f0') +
                   [('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')] + asset_data + notice_data + ai_source_data,
             binaries=media_binaries,
             hiddenimports=['mido', 'studio.dlc_dialog', 'studio.media_dialog', 'studio.plugins', 'studio.plugin_dialog', 'studio.plugin_smoke'],
             excludes=['PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore',
                       'torch', 'torchaudio', 'demucs', 'faster_whisper', 'ctranslate2', 'transformers'],
             noarchive=False)
a.binaries.append(('media/' + ('ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'), ffmpeg_binary, 'BINARY'))
# Qt 6.11 imports Windows' unversioned ICU shim. The developer PATH may
# contain an unrelated Poppler ICU with suffixed exports; never bundle it.
if sys.platform == 'win32':
    a.binaries = [entry for entry in a.binaries
                  if entry[0].lower() != 'icuuc.dll' and
                  not (entry[0].lower().startswith('icudt') and 'poppler' in entry[1].lower())]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='OpenLipsStudio', console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name='OpenLipsStudio')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='OpenLipsStudio.app',
                 icon='studio/assets/app-icon.icns',
                 bundle_identifier='org.openlips.studio',
                 info_plist={'CFBundleShortVersionString': DISPLAY_VERSION.split()[0],
                             'NSHighResolutionCapable': True})
