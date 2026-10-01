"""Bounded .opl ZIP packages; inspection/installation never executes plugin code."""
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

MANIFEST = 'openlips-plugin.json'
MAX_BYTES = 16 * 1024 * 1024


def inspect_package(path):
    path = Path(path)
    if path.suffix.lower() != '.opl':
        raise ValueError('Plugin packages must use .opl (.olp is a song project)')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 256 or sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise ValueError('Plugin package exceeds 256 entries / 16 MiB')
        names = set()
        for entry in entries:
            name = PurePosixPath(entry.filename)
            if (not entry.filename or '\\' in entry.filename or name.is_absolute()
                    or any(part in ('..', '.') or ':' in part for part in name.parts)
                    or any(part.rstrip(' .') != part for part in name.parts)):
                raise ValueError('Unsafe plugin package path')
            if entry.filename.casefold() in names:
                raise ValueError('Duplicate plugin package path')
            names.add(entry.filename.casefold())
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode) or (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError('Plugin package may not contain links or special files')
        manifest = archive.getinfo(MANIFEST)
        if manifest.file_size > 65536:
            raise ValueError('Plugin manifest exceeds 64 KiB')
        data = json.loads(archive.read(MANIFEST).decode('utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+', data['id']):
            raise ValueError('Invalid plugin ID')
        if data['id'] in ('.', '..'):
            raise ValueError('Invalid plugin ID')
        if data.get('api_version', 1) != 1:
            raise ValueError('Unsupported plugin API')
        module = data.get('module', '')
        if not isinstance(module, str) or not module.endswith('.py') or module not in [entry.filename for entry in entries]:
            raise ValueError('Missing plugin Python module')
        return data


def install_package(path, destination):
    data = inspect_package(path)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / data['id']
    target.resolve().relative_to(destination)
    if target.exists():
        raise FileExistsError(f'Plugin already installed: {target.name}')
    # Extract into a fresh owned staging directory; never overwrite another plugin.
    with tempfile.TemporaryDirectory(prefix='.install-', dir=destination) as staging:
        staging = Path(staging)
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                output = staging / entry.filename
                output.resolve().relative_to(staging)
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, output.open('xb') as stream:
                    shutil.copyfileobj(source, stream)
        staging.rename(target)
    return target


def build_package(folder, output):
    folder, output = Path(folder), Path(output)
    if output.suffix.lower() != '.opl':
        raise ValueError('Plugin packages must use .opl')
    paths = sorted(folder.rglob('*'))
    if any(path.is_symlink() for path in paths):
        raise ValueError('Plugin source may not contain symlinks')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path, path.relative_to(folder).as_posix())
    inspect_package(output)
    return output
