"""Download the project's native AI engine, verify it and install atomically."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.request
from urllib.parse import urlparse
import zipfile
import subprocess
from functools import lru_cache

from PySide6.QtCore import QThread, Signal, QStandardPaths

RELEASES = 'https://api.github.com/repos/gerrit117/OpenLips-Studio/releases'
MAX_DOWNLOAD = 4 * 1024 ** 3
MAX_EXPANDED = 12 * 1024 ** 3


def runtime_platform():
    import sys
    machine = platform.machine().lower()
    if sys.platform == 'win32' and machine in ('amd64', 'x86_64'):
        return 'windows-x64', '.zip'
    if sys.platform == 'darwin':
        return ('macos-arm64' if machine in ('arm64', 'aarch64') else 'macos-x64'), '.tar.gz'
    if sys.platform == 'linux' and machine in ('amd64', 'x86_64'):
        return 'linux-x64', '.tar.gz'
    raise ValueError('No AI engine build is available for this platform')


def cache_root():
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'ai-engines'


def installed_engine(root=None, flavor='cpu'):
    root = Path(root) if root else cache_root()
    name = 'OpenLipsAI.exe' if os.name == 'nt' else 'OpenLipsAI'
    candidates = sorted(root.glob('*/ai/' + name), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = [p for p in candidates if ('-amd' in p.parent.parent.name) == (flavor == 'amd')]
    return str(candidates[0]) if candidates else ''


@lru_cache(maxsize=1)
def has_amd_gpu():
    if os.name != 'nt':
        return False
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
            '(Get-CimInstance Win32_VideoController).Name'], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.returncode == 0 and b'AMD' in result.stdout.upper()
    except (OSError, subprocess.TimeoutExpired):
        return False


def amd_engine():
    import sys
    packaged = Path(sys.executable).parent / 'ai-amd' / 'OpenLipsAI.exe'
    if packaged.is_file():
        return str(packaged)
    cached = installed_engine(flavor='amd')
    if cached:
        return cached
    if not getattr(sys, 'frozen', False):
        local = Path(__file__).resolve().parents[1] / 'private/runtime/ai-amd-env/Scripts/python.exe'
        if local.is_file():
            return str(local)
    return ''


def open_url(url):
    parts = urlparse(url)
    if parts.scheme != 'https' or parts.hostname not in ('api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
        raise ValueError('Unexpected AI download URL')
    response = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'OpenLips-Studio'}), timeout=30)
    final = urlparse(response.url)
    if final.scheme != 'https' or final.hostname not in ('api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
        response.close()
        raise ValueError('Unexpected AI download redirect')
    return response


def choose_asset(releases, target, extension):
    pattern = re.compile(r'OpenLips-AI-([0-9]+\.[0-9]+\.[0-9]+(?:-beta\.[0-9]+)?)-' + re.escape(target + extension) + r'$')
    for release in releases:
        if release.get('draft'):
            continue
        assets = {a['name']: a for a in release.get('assets', [])}
        for name, asset in assets.items():
            match = pattern.fullmatch(name)
            if match and name + '.sha256' in assets:
                return match[1], asset, assets[name + '.sha256']
    raise ValueError('No complete AI engine release is currently available for this platform')


def choose_engine_asset(releases, target, extension, flavor):
    if flavor == 'amd':
        if target != 'windows-x64':
            raise ValueError('The downloadable AMD runtime is currently Windows-only')
        try:
            return target + '-amd', choose_asset(releases, target + '-amd', extension)
        except ValueError:
            pass
    return target, choose_asset(releases, target, extension)


def extract_checked(archive, destination, cancelled=lambda: False):
    destination = Path(destination)
    entries, links, total = [], [], 0
    zipped = zipfile.is_zipfile(archive)
    package = zipfile.ZipFile(archive) if zipped else tarfile.open(archive, 'r:gz')
    with package:
        members = package.infolist() if zipped else package.getmembers()
        if len(members) > 100000:
            raise ValueError('Too many AI engine files')
        seen = set()
        for member in members:
            name = member.filename if zipped else member.name
            path = PurePosixPath(name)
            if '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'ai':
                raise ValueError('Unsafe AI engine archive path')
            if name.rstrip('/').casefold() in seen:
                raise ValueError('Duplicate AI engine archive path')
            seen.add(name.rstrip('/').casefold())
            mode = member.external_attr >> 16 if zipped else member.mode
            directory = member.is_dir() if zipped else member.isdir()
            link = stat.S_ISLNK(mode) if zipped else member.issym()
            regular = stat.S_IFMT(mode) in (0, stat.S_IFREG) if zipped else member.isfile()
            if not directory and not link and not regular:
                raise ValueError('Unsupported AI engine archive entry')
            size = member.file_size if zipped else member.size
            total += size
            if total > MAX_EXPANDED:
                raise ValueError('AI engine exceeds expanded size limit')
            if link:
                target = package.read(member).decode('utf-8') if zipped else member.linkname
                if '\\' in target or ':' in target or PurePosixPath(target).is_absolute():
                    raise ValueError('Unsafe AI engine symlink')
                output = destination / name
                (output.parent / target).resolve().relative_to(destination.resolve())
                links.append((output, target))
            else:
                entries.append((member, destination / name, directory, mode))
        existing = destination
        while not existing.exists():
            existing = existing.parent
        if shutil.disk_usage(existing).free < total + 512 * 1024 * 1024:
            raise ValueError('Not enough free disk space to extract the AI engine')
        for member, output, directory, mode in entries:
            if cancelled():
                raise InterruptedError('AI engine download cancelled')
            if directory:
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            source = package.open(member) if zipped else package.extractfile(member)
            with source, output.open('xb') as stream:
                while chunk := source.read(1024 * 1024):
                    if cancelled():
                        raise InterruptedError('AI engine download cancelled')
                    stream.write(chunk)
            output.chmod(0o755 if mode & 0o111 else 0o644)
        for output, target in links:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.symlink_to(target)
        for output, _ in links:
            output.resolve(strict=True).relative_to(destination.resolve())


class EngineDownload(QThread):
    progress = Signal(int, str)
    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None, flavor='cpu'):
        super().__init__(parent)
        self.flavor = flavor
        self.actual_flavor = flavor

    def run(self):
        try:
            target, extension = runtime_platform()
            with open_url(RELEASES + '?per_page=20') as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('Release metadata exceeds size limit')
            target, selection = choose_engine_asset(json.loads(raw), target, extension, self.flavor)
            version, asset, checksum = selection
            self.actual_flavor = 'amd' if target.endswith('-amd') else 'cpu'
            if self.actual_flavor != self.flavor:
                cached = installed_engine(flavor='cpu')
                if cached:
                    self.ready.emit(cached)
                    return
            size = asset.get('size', 0)
            if not 0 < size <= MAX_DOWNLOAD:
                raise ValueError('Invalid AI engine download size')
            with open_url(checksum['browser_download_url']) as response:
                line = response.read(4097).decode('ascii').strip()
            match = re.fullmatch(r'([a-fA-F0-9]{64})\s+' + re.escape(asset['name']), line)
            if not match:
                raise ValueError('Invalid AI engine checksum file')
            root = cache_root()
            root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(root).free < size * 3 + 512 * 1024 * 1024:
                raise ValueError('Not enough free disk space for the AI engine')
            with tempfile.TemporaryDirectory(prefix='.download-', dir=root) as temporary:
                folder = Path(temporary)
                archive = folder / ('engine' + extension)
                digest, received = hashlib.sha256(), 0
                with open_url(asset['browser_download_url']) as response, archive.open('xb') as stream:
                    while chunk := response.read(1024 * 1024):
                        if self.isInterruptionRequested():
                            raise InterruptedError('AI engine download cancelled')
                        received += len(chunk)
                        if received > size:
                            raise ValueError('AI engine download exceeds declared size')
                        digest.update(chunk)
                        stream.write(chunk)
                        self.progress.emit(round(received / size * 100), f'{received // (1024 * 1024)} / {size // (1024 * 1024)} MB')
                if received != size or digest.hexdigest() != match[1].lower():
                    raise ValueError('AI engine checksum mismatch')
                self.progress.emit(100, 'Installing AI engine')
                stage = folder / 'ready'
                stage.mkdir()
                extract_checked(archive, stage, self.isInterruptionRequested)
                executable = stage / 'ai' / ('OpenLipsAI.exe' if os.name == 'nt' else 'OpenLipsAI')
                if not executable.is_file():
                    raise ValueError('AI engine executable is missing')
                destination = root / (version + '-' + target)
                if destination.exists():
                    raise FileExistsError('AI engine installation already exists')
                stage.rename(destination)
                self.ready.emit(str(destination / 'ai' / executable.name))
        except Exception as error:
            self.failed.emit(str(error))
