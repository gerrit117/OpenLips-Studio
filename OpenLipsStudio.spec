# Native builds must run on the target OS; do not cross-compile Qt bundles.
from PyInstaller.utils.hooks import collect_data_files
import sys
from studio import DISPLAY_VERSION
from pathlib import Path
from tools.bundle_plugin_runtime import bundle

media_helper = Path('private/runtime/og-framing-test/transcode_windows.exe')
media_binaries = [(str(media_helper), 'media')] if sys.platform == 'win32' and media_helper.is_file() else []
worker = Path('dist/OpenLipsBasicPitch')
icon = 'studio/assets/app-icon.ico' if sys.platform == 'win32' else None

a = Analysis(['studio/launcher.py'], pathex=['.'],
             datas=collect_data_files('qtawesome') + collect_data_files('pyphen') +
                   [('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.'), ('studio/assets', 'studio/assets')],
             binaries=media_binaries,
             hiddenimports=['mido', 'studio.dlc_dialog', 'studio.media_dialog', 'studio.plugins', 'studio.plugin_dialog', 'studio.plugin_smoke'],
             excludes=['PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'imageio_ffmpeg'],
             noarchive=False)
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
if worker.is_dir():
    bundle(worker, Path('dist/OpenLipsStudio'))
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='OpenLipsStudio.app',
                 icon='studio/assets/app-icon.icns',
                 bundle_identifier='org.openlips.studio',
                 info_plist={'CFBundleShortVersionString': DISPLAY_VERSION.split()[0],
                             'NSHighResolutionCapable': True})
    if worker.is_dir():
        bundle(worker, Path('dist/OpenLipsStudio.app'))
