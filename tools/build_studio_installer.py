"""Native Windows wizard / macOS drag-to-Applications image from a frozen app."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from tools.package_studio_release import release_version, TARGETS


def build(target, dist=Path('dist'), output=Path('release_assets'), compiler=None):
    label = TARGETS[target]
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = f'OpenLips-Studio-{release_version()}-{label}'
    if label == 'windows-x64':
        if sys.platform != 'win32':
            raise ValueError('Build the Windows installer on Windows')
        compiler = compiler or shutil.which('ISCC')
        if not compiler:
            installed = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Inno Setup 6/ISCC.exe'
            compiler = str(installed) if installed.is_file() else None
        if not compiler:
            raise ValueError('Inno Setup 6 compiler not installed')
        archive = output / (name + '-setup.exe')
        if archive.exists():
            raise FileExistsError(archive)
        source = (Path(dist) / 'OpenLipsStudio').resolve()
        if not (source / 'OpenLipsStudio.exe').is_file():
            raise ValueError('Frozen Windows app is missing')
        subprocess.run([compiler, '/Qp', f'/DAppVersion={release_version()}', f'/DSourceDir={source}',
                        f'/DOutputDir={output}', str(Path('packaging/windows/studio.iss').resolve())], check=True)
    elif label.startswith('macos-'):
        if sys.platform != 'darwin':
            raise ValueError('Build DMG images on macOS')
        archive = output / (name + '.dmg')
        if archive.exists():
            raise FileExistsError(archive)
        source = Path(dist) / 'OpenLipsStudio.app'
        if not source.is_dir():
            raise ValueError('Frozen macOS app is missing')
        with tempfile.TemporaryDirectory(prefix='openlips-dmg-') as temporary:
            staging = Path(temporary)
            subprocess.run(['ditto', str(source), str(staging / source.name)], check=True)
            (staging / 'Applications').symlink_to('/Applications', target_is_directory=True)
            subprocess.run(['hdiutil', 'create', '-volname', 'OpenLips Studio', '-srcfolder',
                            str(staging), '-format', 'UDZO', str(archive)], check=True)
    else:
        return None  # Linux keeps its portable archive and desktop-entry installer.
    if not archive.is_file():
        raise ValueError('Installer command produced no output')
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.with_suffix(archive.suffix + '.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    return archive


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', choices=TARGETS, required=True)
    p.add_argument('--compiler')
    args = p.parse_args()
    print(build(args.target, compiler=args.compiler))
