"""Install verified Lips packages into mounted Content storage, never raw disks."""
import ctypes
import os
from pathlib import Path
import shutil
import tempfile

from tools.build_dlc import TITLE_ID, marketplace_filename, sha256, verify_stfs


def content_directory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Select an existing mounted drive root')
    root = root.resolve()
    legacy = next((p for p in root.iterdir() if p.name.casefold() == 'xbox360'), None)
    if legacy and legacy.is_dir() and any(p.name.casefold().startswith('data000') for p in legacy.iterdir()):
        raise ValueError('Legacy Xbox360/Data000 storage is not supported; no files were changed')
    candidates = [p for p in root.iterdir() if p.name.casefold() == 'content']
    if (len(candidates) != 1 or not candidates[0].is_dir() or candidates[0].is_symlink()
            or not candidates[0].resolve().is_relative_to(root)):
        raise ValueError('This drive has no supported Xbox Content folder')
    return candidates[0]


def _publish_no_replace(source, target):
    if os.name == 'nt':
        os.rename(source, target)  # Windows rename refuses an existing destination.
    elif os.sys.platform == 'linux':
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(target))
    elif os.sys.platform == 'darwin':
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(os.fsencode(source), os.fsencode(target), 4):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(target))
    else:
        raise ValueError('Safe no-overwrite publication is unavailable on this platform')


def install_package(package, root, progress=lambda copied, total: None):
    package = Path(package)
    verified = verify_stfs(package)
    filename = marketplace_filename(package)
    content = content_directory(root)
    target_dir = content
    for part in ('0000000000000000', f'{TITLE_ID:08X}', '00000002'):
        matches = [p for p in target_dir.iterdir() if p.name.casefold() == part.casefold()]
        if len(matches) > 1:
            raise ValueError('Ambiguous Xbox Content path')
        child = matches[0] if matches else target_dir / part
        if child.is_symlink() or (child.exists() and not child.is_dir()):
            raise ValueError('Unsafe Xbox Content path')
        if not child.resolve().is_relative_to(content.resolve()):
            raise ValueError('Xbox Content path leaves the selected drive')
        child.mkdir(exist_ok=True)
        target_dir = child
    if any(p.name.casefold() == filename.casefold() for p in target_dir.iterdir()):
        raise FileExistsError('This package is already installed; existing files are not overwritten')
    if shutil.disk_usage(target_dir).free < verified['bytes'] + 1024 * 1024:
        raise ValueError('Not enough free space on the selected drive')
    fd, temporary = tempfile.mkstemp(prefix='.openlips-', suffix='.tmp', dir=target_dir)
    temporary = Path(temporary)
    try:
        copied = 0
        with os.fdopen(fd, 'wb') as output, package.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                output.write(block)
                copied += len(block)
                progress(copied, verified['bytes'])
            output.flush()
            os.fsync(output.fileno())
        if sha256(temporary) != verified['sha256']:
            raise ValueError('USB read-back verification failed')
        target = target_dir / filename
        if any(p.name.casefold() == filename.casefold() for p in target_dir.iterdir()):
            raise FileExistsError('Package appeared during transfer; not overwritten')
        _publish_no_replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)
