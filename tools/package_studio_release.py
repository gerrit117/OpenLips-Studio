"""Package only the frozen application, preserving Unix modes and app symlinks."""
import argparse
import hashlib
from pathlib import Path
import stat
import tarfile
import zipfile

from packaging.version import Version
from studio import __version__

TARGETS = {'windows-2022': 'windows-x64', 'macos-14': 'macos-arm64',
           'macos-15-intel': 'macos-x64', 'ubuntu-22.04': 'linux-x64'}


def release_version():
    version = Version(__version__)
    suffix = f'-beta.{version.pre[1]}' if version.pre and version.pre[0] == 'b' else ''
    if version.pre and version.pre[0] != 'b':
        raise ValueError('Unsupported prerelease type')
    return version.base_version + suffix


def package(target, dist=Path('dist'), output=Path('release_assets')):
    label = TARGETS[target]
    source = Path(dist) / ('OpenLipsStudio.app' if label.startswith('macos') else 'OpenLipsStudio')
    if not source.is_dir():
        raise ValueError(f'Missing frozen application: {source}')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted(path for path in source.rglob('*')
                   if path.relative_to(source).parts[0] not in ('ai', 'ai-amd'))
    for path in paths:
        if path.is_symlink():
            path.resolve(strict=True).relative_to(source.resolve())
    extension = '.tar.gz' if label.startswith('linux') else '.zip'
    archive = output / f'OpenLips-Studio-{release_version()}-{label}{extension}'
    if archive.exists():
        raise FileExistsError(archive)
    if extension == '.tar.gz':
        with tarfile.open(archive, 'w:gz', dereference=False) as stream:
            stream.add(source, arcname=source.name,
                       filter=lambda entry: None if any(entry.name == source.name + '/' + name or
                           entry.name.startswith(source.name + '/' + name + '/')
                           for name in ('ai', 'ai-amd')) else entry)
    else:
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as stream:
            for path in paths:
                name = path.relative_to(source.parent).as_posix()
                if path.is_symlink():
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    stream.writestr(info, path.readlink().as_posix())
                else:
                    stream.write(path, name)
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.with_suffix(archive.suffix + '.sha256').write_text(
        f'{digest}  {archive.name}\n', encoding='ascii')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, choices=TARGETS)
    args = parser.parse_args()
    print(package(args.target))


if __name__ == '__main__':
    main()
