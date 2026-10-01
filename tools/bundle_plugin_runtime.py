"""Copy the finished worker intact; never re-analyze it under the GUI's Python."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def bundle(worker, application, sign=True):
    worker, application = Path(worker).resolve(), Path(application).resolve()
    if not worker.is_dir() or not application.is_dir():
        raise ValueError('Build the worker and desktop app before bundling')
    executable = worker / ('OpenLipsBasicPitch.exe' if sys.platform == 'win32' else 'OpenLipsBasicPitch')
    if not executable.is_file():
        raise ValueError('Missing worker executable')
    for path in worker.rglob('*'):
        if path.is_symlink():
            path.resolve(strict=True).relative_to(worker)
    # A worker contains both native code and data/metadata. Frameworks makes
    # codesign misidentify .dist-info directories as malformed nested bundles.
    base = application / ('Contents/Resources' if application.suffix == '.app' else '_internal')
    target = base / 'plugin-runtime/OpenLipsBasicPitch'
    target.resolve().relative_to(application)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.worker-', dir=target.parent) as temporary:
        staging = Path(temporary) / 'runtime'
        shutil.copytree(worker, staging, symlinks=True)
        if target.exists():
            # Only the verified generated worker directory, never arbitrary app/user paths.
            target.resolve().relative_to(application)
            shutil.rmtree(target)
        staging.rename(target)
    if sys.platform == 'darwin' and application.suffix == '.app' and sign:
        # Adding nested code changes the existing ad-hoc bundle signature.
        subprocess.run(['codesign', '--force', '--sign', '-', str(application)], check=True)
    return target
