# Native builds must run on the target OS; do not cross-compile Qt bundles.
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules
import sys
from studio import DISPLAY_VERSION
from pathlib import Path

media_helper = Path('private/runtime/media/transcode_windows.exe')
media_binaries = [(str(media_helper), 'media')] if sys.platform == 'win32' and media_helper.is_file() else []
if sys.platform == 'win32':
    stfs = Path('private/runtime/dlc-backend-build/Release/openlips_stfs.exe')
    if not stfs.is_file():
        raise ValueError('Build the integrated STFS backend before packaging Windows Studio')
    media_binaries.append((str(stfs), 'media'))
    probe = Path(__import__('os').environ.get('OPENLIPS_FFPROBE', 'private/runtime/usdb-media/extracted/ffmpeg-8.1.2-essentials_build/bin/ffprobe.exe'))
    if not probe.is_file():
        raise ValueError('Missing bundled FFprobe')
    media_binaries.append((str(probe), 'media'))
import imageio_ffmpeg
ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
notices = Path('build/studio-licenses')
notice_data = [(str(notices), 'licenses')] if notices.is_dir() else []
download_root = Path(__import__('os').environ.get('OPENLIPS_DOWNLOAD_DIST', 'private/runtime/workers' if Path('private/runtime/workers/OpenLipsDownload').is_dir() else 'dist')) / 'OpenLipsDownload'
if not (download_root / ('OpenLipsDownload.exe' if sys.platform == 'win32' else 'OpenLipsDownload')).is_file():
    raise ValueError('Build DownloadWorker.spec before packaging Studio')
notice_data += [(str(path), 'download/OpenLipsDownload/' + str(path.parent.relative_to(download_root)))
                for path in download_root.rglob('*') if path.is_file()]
usdb_root = Path(__import__('os').environ.get('OPENLIPS_USDB_DIST', 'private/runtime/workers' if Path('private/runtime/workers/OpenLipsUSDB').is_dir() else 'dist')) / 'OpenLipsUSDB'
usdb_executable = usdb_root / ('OpenLipsUSDB.exe' if sys.platform == 'win32' else 'OpenLipsUSDB')
if not usdb_executable.is_file():
    raise ValueError('Build the integrated native USDB downloader before packaging Studio')
from tools.check_usdb_runtime import check_runtime
check_runtime(usdb_executable)
notice_data += [(str(path), 'usdb/OpenLipsUSDB/' + str(path.parent.relative_to(usdb_root)))
                for path in usdb_root.rglob('*') if path.is_file()]
icon = 'studio/assets/app-icon.ico' if sys.platform == 'win32' else None
asset_data = [(str(path), 'studio/assets') for path in Path('studio/assets').iterdir()
              if path.is_file() and path.suffix in ('.png', '.ico', '.icns', '.sh')]
ai_source_data = [(str(path), 'ai_backend/' + str(path.parent)) for path in map(Path, (
    'studio/__init__.py', 'studio/model.py', 'studio/lrc.py', 'studio/ai_chart.py', 'studio/ai_alignment.py',
    'tools/__init__.py', 'tools/create_ai_chart.py', 'tools/align_lyrics.py',
    'tools/ai_devices.py', 'tools/ai_transcription.py'))]

a = Analysis(['studio/launcher.py'], pathex=['.'],
             datas=collect_data_files('certifi') + collect_data_files('qtawesome') + collect_data_files('pyphen') + collect_data_files('swift_f0') + copy_metadata('swift-f0') +
                   [('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.')] + asset_data + notice_data + ai_source_data,
             binaries=media_binaries,
             hiddenimports=['mido', 'studio.dlc_dialog', 'studio.media_dialog', 'studio.plugins', 'studio.plugin_dialog', 'studio.plugin_smoke',
                            'studio.server', 'studio.server_job', 'pyftpdlib.authorizers', 'pyftpdlib.handlers', 'pyftpdlib.servers',
                            'studio.library_workspace', 'studio.remote_library', 'studio.library_security', 'studio.library_client'] + collect_submodules('zeroconf'),
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
