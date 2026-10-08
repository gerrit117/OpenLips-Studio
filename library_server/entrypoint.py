"""Prepare the dedicated Docker volume, then permanently drop root privileges."""
import os
from pathlib import Path
import stat
import sys


def prepare_storage(root, uid, gid):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('The data mount must not be a symbolic link')
    root.mkdir(parents=True, exist_ok=True)
    managed = root / 'library'
    if managed.is_symlink():
        raise ValueError('The library directory must not be a symbolic link')
    managed.mkdir(exist_ok=True)
    paths = [root, managed]
    for directory, dirs, files in os.walk(managed, followlinks=False):
        paths.extend(Path(directory) / name for name in dirs + files)
    for path in paths:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            continue
        if (info.st_uid, info.st_gid) != (uid, gid):
            os.chown(path, uid, gid)
        needed = 0o700 if stat.S_ISDIR(info.st_mode) else 0o600
        if info.st_mode & needed != needed:
            os.chmod(path, stat.S_IMODE(info.st_mode) | needed)


def main():
    try:
        uid = int(os.environ.get('PUID', '10001'))
        gid = int(os.environ.get('PGID', '10001'))
        if not 1 <= uid <= 2147483647 or not 1 <= gid <= 2147483647:
            raise ValueError('PUID and PGID must be positive non-root IDs')
        if os.getuid() == 0:
            prepare_storage('/data', uid, gid)
            os.setgroups([])
            os.setgid(gid)
            os.setuid(uid)
        os.umask(0o077)
        print(f'OpenLips storage ready; application UID/GID {os.getuid()}:{os.getgid()}', flush=True)
        os.execvp(sys.executable, [sys.executable, '-m', 'library_server.container_app', *sys.argv[1:]])
    except (OSError, ValueError) as error:
        print(f'Cannot prepare /data: {error}. Mount a dedicated writable appdata directory.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
