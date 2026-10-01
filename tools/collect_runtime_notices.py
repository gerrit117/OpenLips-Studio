"""Inventory exact installed versions and copy their shipped license/notice files."""
import argparse
from importlib.metadata import distributions
import json
from pathlib import Path
import shutil


def collect(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    inventory = []
    for distribution in sorted(distributions(), key=lambda d: d.metadata.get('Name', '').lower()):
        name = distribution.metadata.get('Name', 'unknown')
        records = []
        for file in distribution.files or ():
            if any(word in file.name.lower() for word in ('license', 'notice', 'copyright', 'copying')):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    relative = Path(name) / str(file).replace('..', '_parent_')
                    target = output / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    records.append(relative.as_posix())
        inventory.append({'name': name, 'version': distribution.version,
                          'license': distribution.metadata.get('License-Expression') or distribution.metadata.get('License', ''),
                          'notice_files': records})
    (output / 'inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    return len(inventory)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(f'{collect(args.out)} dependency versions inventoried')
