"""Local, hash-guarded chart-only A/B test launcher. Never changes an ISO."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ensure_closed(executable):
    if os.name != 'nt':
        raise ValueError('This local Xenia test launcher targets Windows')
    result = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {executable.name}', '/FO', 'CSV', '/NH'],
                            capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if executable.name.casefold() in result.stdout.decode(errors='replace').casefold():
        raise ValueError('Close Xenia before switching test files')


def switch(config, mode='ai'):
    restore = mode == 'restore'
    root = Path(config['game_root']).resolve(strict=True)
    state = Path(config['state']).resolve()
    executable = Path(config['xenia']).resolve(strict=True)
    ensure_closed(executable)
    mappings = []
    for item in config['files']:
        target = (root / item['relative']).resolve(strict=True)
        target.relative_to(root)
        source = Path(item['source']).resolve(strict=not restore)
        mappings.append((target, source))
    if state.exists():
        saved = json.loads(state.read_text(encoding='utf-8'))
        if saved['root'] != str(root) or [r['target'] for r in saved['records']] != [str(t) for t, _ in mappings]:
            raise ValueError('Backup state belongs to another test')
        for row in saved['records']:
            if digest(Path(row['backup'])) != row['original_sha256']:
                raise ValueError('Backup hash mismatch')
            current = digest(Path(row['target']))
            if current not in (row['original_sha256'], row['patched_sha256'], row['baseline_sha256']):
                raise ValueError('Game files were changed outside this test; refusing overwrite')
    elif restore:
        return 'Nothing to restore'
    else:
        state.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for index, (target, source) in enumerate(mappings):
            backup = state.parent / f'original-{index}-{target.name}'
            with target.open('rb') as input, backup.open('xb') as output:
                shutil.copyfileobj(input, output)
            records.append(dict(target=str(target), backup=str(backup),
                                original_sha256=digest(target), patched_sha256=digest(source),
                                baseline=str(Path(config['files'][index]['baseline']).resolve(strict=True)),
                                baseline_sha256=digest(Path(config['files'][index]['baseline']))))
        saved = dict(root=str(root), records=records)
        with state.open('x', encoding='utf-8') as stream:
            json.dump(saved, stream, indent=2)
    try:
        for row, (target, source) in zip(saved['records'], mappings):
            source = Path(row['backup']) if restore else Path(row['baseline']) if mode == 'baseline' else source
            expected = row['original_sha256'] if restore else row['baseline_sha256'] if mode == 'baseline' else row['patched_sha256']
            if digest(source) != expected:
                raise ValueError('Test source changed after backup creation')
            temporary = target.with_name(target.name + '.openlips-test.tmp')
            with source.open('rb') as input, temporary.open('xb') as output:
                shutil.copyfileobj(input, output)
                output.flush()
                os.fsync(output.fileno())
            if digest(temporary) != expected:
                raise ValueError('Staged copy hash mismatch')
            os.replace(temporary, target)
            print(f'{target.name}: {expected}')
    except Exception:
        # A two-file publication cannot be atomic; restore both on failure.
        for row in saved['records']:
            if digest(Path(row['backup'])) == row['original_sha256']:
                shutil.copyfile(row['backup'], row['target'])
        raise
    return 'Pre-test files restored' if restore else 'Original baseline staged' if mode == 'baseline' else 'AI test pair staged'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('config', type=Path)
    p.add_argument('--mode', choices=('baseline', 'ai', 'restore', 'iso'), required=True)
    p.add_argument('--no-launch', action='store_true')
    args = p.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.mode in ('baseline', 'ai', 'restore'):
        print(switch(config, args.mode))
    if args.mode != 'restore' and not args.no_launch:
        executable = Path(config['xenia']).resolve(strict=True)
        ensure_closed(executable)
        game = Path(config['iso'] if args.mode == 'iso' else config['game_root']).resolve(strict=True)
        if args.mode != 'iso':
            game /= 'default.xex'
        # Modified loose files are visible only when booting the extracted XEX.
        subprocess.Popen([str(executable), str(game), *config.get('xenia_args', [])], cwd=executable.parent)


if __name__ == '__main__':
    main()
