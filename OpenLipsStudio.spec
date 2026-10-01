# Native builds must run on the target OS; do not cross-compile Qt bundles.
from PyInstaller.utils.hooks import collect_data_files
import sys

a = Analysis(['studio/launcher.py'], pathex=['.'],
             datas=collect_data_files('qtawesome') + collect_data_files('pyphen') +
                   [('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')],
             hiddenimports=['mido', 'studio.dlc_dialog', 'studio.plugins'],
             excludes=['PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore'],
             noarchive=False)
# Qt 6.11 imports Windows' unversioned ICU shim. The developer PATH may
# contain an unrelated Poppler ICU with suffixed exports; never bundle it.
if sys.platform == 'win32':
    a.binaries = [entry for entry in a.binaries
                  if entry[0].lower() != 'icuuc.dll' and
                  not (entry[0].lower().startswith('icudt') and 'poppler' in entry[1].lower())]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name='OpenLipsStudio', console=False)
coll = COLLECT(exe, a.binaries, a.datas, name='OpenLipsStudio')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='OpenLipsStudio.app',
                 bundle_identifier='org.openlips.studio',
                 info_plist={'CFBundleShortVersionString': '0.1.0',
                             'NSHighResolutionCapable': True})
