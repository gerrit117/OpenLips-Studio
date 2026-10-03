"""Package the separately frozen USDB bridge as an installable native .opl."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from studio.plugin_package import build_package
from studio.plugin_process import platform_tag


def package(worker=Path('dist/OpenLipsUSDB'), output=Path('release_assets')):
    root = Path(__file__).resolve().parents[1]
    source = root / 'plugins/usdb_downloader'
    manifest = json.loads((source / 'openlips-plugin.json').read_text(encoding='utf-8'))
    tag = platform_tag()
    manifest['entrypoints'] = {tag: manifest['entrypoints'][tag]}
    worker = Path(worker).resolve(strict=True)
    for path in worker.rglob('*'):
        if path.is_symlink():
            path.resolve(strict=True).relative_to(worker)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"USDB-Downloader-{manifest['version']}-{tag}.opl"
    with tempfile.TemporaryDirectory(prefix='openlips-usdb-package-') as temporary:
        stage = Path(temporary)
        (stage / 'openlips-plugin.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        shutil.copytree(worker, stage / 'runtime/OpenLipsUSDB', symlinks=True)
        for name in ('README.md', 'worker.py', 'service.py'):
            shutil.copy2(source / name, stage / name)
        shutil.copy2(root / 'LICENSE', stage / 'LICENSE')
        shutil.copy2(root / 'THIRD_PARTY_NOTICES.md', stage / 'THIRD_PARTY_NOTICES.md')
        build_package(stage, archive)
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.with_suffix('.opl.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, default=Path('dist/OpenLipsUSDB'))
    parser.add_argument('--out', type=Path, default=Path('release_assets'))
    args = parser.parse_args()
    print(package(args.worker, args.out))
