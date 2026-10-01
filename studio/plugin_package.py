"""Atomic .opl installation, including bounded native runtimes and internal links."""
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

MANIFEST = 'openlips-plugin.json'
MAX_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 50000
LEGACY_MAX_BYTES = 16 * 1024 * 1024
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def safe_path(value):
    from studio.plugin_process import relative_path
    value = relative_path(value)
    if any(part.split('.')[0].upper() in RESERVED or any(c in part for c in '<>"|?*') or any(ord(c) < 32 for c in part)
           for part in value.split('/')):
        raise ValueError('Unsafe plugin package path')
    return value


def _inspect(archive):
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_BYTES:
        raise ValueError('Plugin package exceeds 50000 entries / 2 GiB')
    names, links, files = set(), {}, {}
    for entry in entries:
        name = safe_path(entry.filename.rstrip('/') if entry.is_dir() else entry.filename)
        if name.casefold() in names:
            raise ValueError('Duplicate plugin package path')
        names.add(name.casefold())
        mode = entry.external_attr >> 16
        if entry.flag_bits & 1:
            raise ValueError('Encrypted plugin entries are unsupported')
        if stat.S_ISLNK(mode):
            if entry.file_size > 4096:
                raise ValueError('Oversized plugin link')
            target = archive.read(entry).decode('utf-8')
            if not target or '\\' in target or ':' in target or PurePosixPath(target).is_absolute():
                raise ValueError('Unsafe plugin link')
            parts = list(PurePosixPath(name).parent.parts)
            for part in target.split('/'):
                if part == '..':
                    if not parts:
                        raise ValueError('Plugin link escapes package')
                    parts.pop()
                elif part not in ('', '.'):
                    parts.append(part)
            safe_path('/'.join(parts))
            links[name] = target
        elif mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ValueError('Plugin package contains special files')
        files[name] = entry
    link_names = {name.casefold() for name in links}
    for name in files:
        if any(str(parent).casefold() in link_names for parent in PurePosixPath(name).parents):
            raise ValueError('Plugin entries may not be nested below links')
    manifest = files.get(MANIFEST)
    if manifest is None or manifest.file_size > 65536 or MANIFEST in links:
        raise ValueError('Missing or oversized plugin manifest')
    data = json.loads(archive.read(manifest).decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Invalid plugin manifest')
    if data.get('api_version', 1) == 2:
        from studio.plugin_process import validate_manifest, platform_tag
        validate_manifest(data)
        executable = data['entrypoints'].get(platform_tag())
        if not executable:
            raise ValueError(f'Plugin does not support {platform_tag()}')
        if executable not in files or executable in links or files[executable].is_dir():
            raise ValueError('Missing plugin runtime executable')
    else:
        if links:
            raise ValueError('Legacy plugins may not contain links')
        if len(entries) > 256 or sum(e.file_size for e in entries) > LEGACY_MAX_BYTES:
            raise ValueError('Legacy plugin exceeds 256 entries / 16 MiB')
        if data.get('api_version', 1) != 1:
            raise ValueError('Unsupported plugin API')
        if not isinstance(data.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-][a-zA-Z0-9_.-]{0,127}', data['id']):
            raise ValueError('Invalid plugin ID')
        if data.get('module') not in files or not str(data['module']).endswith('.py'):
            raise ValueError('Missing plugin Python module')
    safe_path(data['id'])
    return data, files, links


def inspect_package(path):
    path = Path(path)
    if path.suffix.lower() != '.opl':
        raise ValueError('Plugin packages must use .opl (.olp is a song project)')
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Compressed plugin package exceeds 2 GiB')
    with zipfile.ZipFile(path) as archive:
        return _inspect(archive)[0]


def install_package(path, destination):
    path = Path(path)
    if path.suffix.lower() != '.opl' or path.stat().st_size > MAX_BYTES:
        raise ValueError('Expected a .opl package up to 2 GiB')
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    # Validate and extract the same open archive rather than reopening after inspection.
    with zipfile.ZipFile(path) as archive:
        data, entries, links = _inspect(archive)
        version = '-' + data['version'] if data.get('api_version') == 2 else ''
        target = destination / (data['id'] + version)
        target.resolve().relative_to(destination)
        if target.exists():
            raise FileExistsError(f'Plugin already installed: {target.name}')
        with tempfile.TemporaryDirectory(prefix='.install-', dir=destination) as temporary:
            staging = Path(temporary) / 'plugin'
            staging.mkdir()
            for name, entry in entries.items():
                if entry.is_dir() or name in links:
                    continue
                output = staging / name
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, output.open('xb') as stream:
                    shutil.copyfileobj(source, stream)
                output.chmod(0o755 if (entry.external_attr >> 16) & 0o111 else 0o644)
            for name, target_path in links.items():
                output = staging / name
                output.parent.mkdir(parents=True, exist_ok=True)
                output.symlink_to(target_path)
            for name in links:
                (staging / name).resolve(strict=True).relative_to(staging.resolve())
            if data.get('api_version') == 2:
                from studio.plugin_process import platform_tag
                executable = staging / data['entrypoints'][platform_tag()]
                if os.name != 'nt' and not os.access(executable, os.X_OK):
                    raise ValueError('Plugin runtime is not executable')
            staging.rename(target)
    return target


def build_package(folder, output):
    folder, output = Path(folder).resolve(), Path(output)
    if output.suffix.lower() != '.opl':
        raise ValueError('Plugin packages must use .opl')
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.opl', dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob('*')):
                if '__pycache__' in path.parts:
                    continue
                name = path.relative_to(folder).as_posix()
                if path.is_symlink():
                    path.resolve(strict=True).relative_to(folder)
                    entry = zipfile.ZipInfo(name)
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(entry, path.readlink().as_posix())
                elif path.is_file():
                    archive.write(path, name)
        inspect_package(temporary)
        os.link(temporary, output)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return output
