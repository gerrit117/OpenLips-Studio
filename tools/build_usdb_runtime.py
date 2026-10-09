"""Build the pinned native USDB bridge in its own Python environment."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

UPSTREAM = 'https://github.com/bohning/usdb_syncer.git'
REVISION = 'c8f9157bed4d45fc646e5d4c4450074ef0925aae'


def build(root=Path('.')):
    root = Path(root).resolve()
    source = root / 'private/runtime/usdb-source'
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        subprocess.run(['git', 'clone', UPSTREAM, str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'checkout', REVISION], check=True)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('USDB checkout does not match the pinned revision')
    environment = root / 'private/runtime/usdb-build-env'
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', 'PySide6>=6.8,<7', 'pyinstaller>=6,<7',
                    'deno==2.9.7', 'yt-dlp[default]==2026.8.19'], check=True)
    subprocess.run([str(python), 'src/tools/generate_pyside_files.py'], cwd=source, check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', str(source)], check=True)
    media = root / 'private/runtime/usdb-tools'
    media.mkdir(exist_ok=True)
    for name in ('ffmpeg', 'ffprobe'):
        suffix = '.exe' if os.name == 'nt' else ''
        if os.name == 'nt':
            binary = root / 'private/runtime/usdb-media/extracted/ffmpeg-8.1.2-essentials_build/bin' / (name + suffix)
        else:
            found = shutil.which(name)
            if not found:
                raise ValueError('Install native FFmpeg and FFprobe before building USDB')
            binary = Path(found).resolve(strict=True)
        shutil.copy2(binary, media / (name + suffix))
    subprocess.run([str(python), '-m', 'tools.collect_runtime_notices', '--out', 'build/usdb-licenses'],
                   cwd=root, check=True)
    notices = root / 'build/usdb-licenses/upstream'
    notices.mkdir(parents=True, exist_ok=True)
    for name in ('LICENSE', 'NOTICE.txt'):
        shutil.copy2(source / name, notices / name)
    shutil.copytree(source / 'licenses', notices / 'licenses', dirs_exist_ok=True)
    env = dict(os.environ, OPENLIPS_USDB_SOURCE=str(source), OPENLIPS_USDB_MEDIA=str(media))
    subprocess.run([str(python), '-m', 'PyInstaller', '--noconfirm', 'USDBWorker.spec'], cwd=root, env=env, check=True)
    from tools.check_usdb_runtime import check_runtime
    executable = root / 'dist/OpenLipsUSDB' / ('OpenLipsUSDB.exe' if os.name == 'nt' else 'OpenLipsUSDB')
    check_runtime(executable)
    return executable


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    print(build(parser.parse_args().root))
