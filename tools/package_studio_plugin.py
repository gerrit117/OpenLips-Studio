"""Build a portable .opl plugin package, not an .olp song project."""
import argparse
from pathlib import Path

from studio.plugin_package import build_package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(build_package(args.folder, args.out))
