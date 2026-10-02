"""Package only the optional frozen AI engine, never model caches or song data."""
import argparse
from pathlib import Path
import hashlib
import tarfile
import zipfile
from tools.package_studio_release import TARGETS, release_version


def package(target, dist=Path('dist'), output=Path('release_assets')):
    label = TARGETS[target]
    source = Path(dist) / 'OpenLipsAI'
    if not (source / ('OpenLipsAI.exe' if label.startswith('windows') else 'OpenLipsAI')).is_file():
        raise ValueError('Build the native AI engine first')
    output.mkdir(parents=True, exist_ok=True)
    extension = '.tar.gz' if not label.startswith('windows') else '.zip'
    archive = output / f'OpenLips-AI-{release_version()}-{label}{extension}'
    if archive.exists():
        raise FileExistsError(archive)
    for path in source.rglob('*'):
        if path.is_symlink():
            path.resolve(strict=True).relative_to(source.resolve())
    if extension == '.zip':
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as stream:
            for path in sorted(source.rglob('*')):
                stream.write(path, Path('ai') / path.relative_to(source))
    else:
        with tarfile.open(archive, 'x:gz', dereference=False) as stream:
            stream.add(source, arcname='ai')
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.with_suffix(archive.suffix + '.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=TARGETS, required=True)
    args = parser.parse_args()
    print(package(args.target))
