"""Build our own local Xbox probe using an already-installed official SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from tools.inspect_xex_identity import identity


ROOT = Path(__file__).resolve().parents[1]


def build(sdk, output, font):
    sdk, output, font = Path(sdk).resolve(strict=True), Path(output).resolve(), Path(font).resolve(strict=True)
    if os.name != 'nt':
        raise ValueError('This probe build uses the installed Windows SDK tools')
    if font.suffix.lower() != '.ttf':
        raise ValueError('Supply a TTF font you are allowed to use; no SDK assets are copied')
    if output.exists():
        raise FileExistsError(output)
    binpath = sdk / 'bin/win32'
    for tool in ('cl.exe', 'link.exe', 'imagexex.exe'):
        if not (binpath / tool).is_file():
            raise FileNotFoundError(binpath / tool)
    output.mkdir(parents=True)
    env = os.environ.copy()
    env['PATH'] = str(binpath) + os.pathsep + env.get('PATH', '')
    env['INCLUDE'] = str(sdk / 'include/xbox')
    env['LIB'] = str(sdk / 'lib/xbox')
    source = ROOT / 'xbox_client/probe/main.cpp'
    obj, pe, xex = output/'probe.obj', output/'probe.exe', output/'default.xex'
    commands = [
        [str(binpath/'cl.exe'), '/nologo', '/c', '/O2', '/MT', '/GR-', '/GS-', '/W4',
         '/D_XBOX', '/DXBOX', '/DNDEBUG', '/Fo'+str(obj), str(source)],
        [str(binpath/'link.exe'), '/nologo', '/machine:PPCBE', '/subsystem:xbox',
         '/entry:mainCRTStartup', '/base:0x82000000', '/fixed', '/out:'+str(pe), str(obj),
         'xapilib.lib', 'libcmt.lib', 'xboxkrnl.lib', 'd3d9.lib', 'd3dx9.lib',
         'xgraphics.lib', 'xuirun.lib', 'xuirender.lib', 'xmcore.lib', 'xaudio2.lib'],
        [str(binpath/'imagexex.exe'), '/nologo', '/in:'+str(pe), '/out:'+str(xex),
         '/titleid:0x4F4C5052'],
    ]
    with (output/'build.log').open('wb') as log:
        for command in commands:
            result = subprocess.run(command, cwd=output, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(result.stdout)
            log.flush()
            print(result.stdout.decode(errors='replace'))
            result.check_returncode()
    data = identity(xex)
    if data.get('title_id') != '4F4C5052':
        raise ValueError('Generated XEX has an unexpected execution identity')
    media = output/'media'
    media.mkdir()
    shutil.copyfile(font, media/'client.ttf')
    data['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    data['font_sha256'] = hashlib.sha256(font.read_bytes()).hexdigest()
    data['hardware_verified'] = False
    (output/'verification.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(xex)
    return xex


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', default=os.environ.get('XEDK'))
    parser.add_argument('--output', type=Path, default=ROOT/'private/xbox-client-probe-20261007')
    parser.add_argument('--font', type=Path, required=True)
    args = parser.parse_args()
    if not args.sdk:
        parser.error('Set XEDK or pass --sdk for your existing installation')
    build(args.sdk, args.output, args.font)
