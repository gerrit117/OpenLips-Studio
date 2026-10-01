"""Generate private Windows test launchers; leave all game files untouched."""
import argparse
import json
from pathlib import Path
import shutil


def cmd_path(path):
    value = str(Path(path).resolve(strict=True))
    if any(c in value for c in ('%', '"', '\r', '\n')):
        raise ValueError('Unsupported character in CMD path')
    return '"' + value + '"'


def prepare(repo, output, game, baseline, pair, xenia, iso, noh_iso, python):
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    relative = Path('lps/Levels/Intl/S/Seal/Amazing')
    config = dict(game_root=str(game.resolve(strict=True)), xenia=str(xenia.resolve(strict=True)),
                  iso=str(iso.resolve(strict=True)), state=str((output / 'backups/state.json').resolve()),
                  xenia_args=['--break_on_start=false', '--keyboard_mode=1', '--hid=keyboard',
                              '--keybind_a=0x0D', '--keybind_start=0x0D', '--keybind_dpad_left=A',
                              '--keybind_dpad_right=D', '--log_level=2'],
                  files=[dict(relative=str(relative / name), source=str((pair / name).resolve(strict=True)),
                              baseline=str((baseline / relative / name).resolve(strict=True)))
                         for name in ('Amazing.X360', 'Amazing_Lyric.X360')])
    path = output / 'amazing-test.json'
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    commands = [('01-Original-Amazing.cmd', 'baseline'), ('02-AI-Amazing.cmd', 'ai'),
                ('03-Dateien-wiederherstellen.cmd', 'restore'), ('04-Original-ISO.cmd', 'iso')]
    for filename, mode in commands:
        text = ('@echo off\r\nsetlocal\r\nchcp 65001 >nul\r\n'
                f'pushd {cmd_path(repo)}\r\n'
                f'{cmd_path(python)} -m tools.run_xenia_test {cmd_path(path)} --mode {mode}\r\n'
                'if errorlevel 1 echo Test konnte nicht gestartet werden. Bitte die Meldung oben beachten.\r\n'
                'popd\r\npause\r\n')
        (output / filename).write_text(text, encoding='utf-8', newline='')
    for filename, command in [
            ('05-Number-One-Hits-ISO.cmd', f'start "Lips Number One Hits" {cmd_path(xenia)} {cmd_path(noh_iso)} ' + ' '.join(config['xenia_args'])),
            ('06-KI-Chart-in-Studio.cmd', f'start "OpenLips Studio" {cmd_path(repo / "dist/OpenLipsStudio/OpenLipsStudio.exe")} --project {cmd_path(pair / "reviewed-draft.olp")}')]:
        (output / filename).write_text('@echo off\r\n' + command + '\r\n', encoding='utf-8', newline='')
    return path


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'out', 'game', 'baseline', 'pair', 'xenia', 'iso', 'noh-iso', 'python'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    print(prepare(a.repo, a.out, a.game, a.baseline, a.pair, a.xenia, a.iso, a.noh_iso, a.python))
