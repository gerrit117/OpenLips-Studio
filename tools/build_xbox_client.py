"""Local native/desktop builds; SDK tools and generated assets stay private."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BEAR_REV = '7bea48e5e850ab4cafbe68d3765cdaba13a86d6f'
CJSON_REV = 'c859b25da02955fef659d658b8f324b5cde87be3'
MDNS_REV = 'a569c4759bd47e0f2a7bfc4d4c19620445782806'
STB_REV = '2c980bb59875b0d32144a71867fbdebb2f77cd20'


def assets(output, font):
    from PIL import Image, ImageDraw, ImageFont
    media = output / 'media'
    media.mkdir()
    typeface = ImageFont.truetype(str(font), 26)
    atlas = Image.new('RGBA', (1024, 640))
    painter = ImageDraw.Draw(atlas)
    metrics = []
    codes = list(range(32, 256)) + list(range(0x400, 0x500)) + [63] * 32
    for i, code in enumerate(codes):
        character = chr(code)
        painter.text(((i % 32) * 32, (i // 32) * 40 + 31), character,
                     font=typeface, fill='white', anchor='ls')
        metrics.append(round(typeface.getlength(character) * 64))
    (media / 'font.raw').write_bytes(struct.pack('>II', 1024, 640) + struct.pack('>512I', *metrics) + atlas.tobytes())
    for mode in ('dark', 'light'):
        with Image.open(ROOT / f'library_server/static/logo-{mode}.png') as logo:
            # Mechanical texture conversion; source branding remains unchanged.
            pixels = logo.convert('RGBA')
            pixels.thumbnail((768, 512), Image.Resampling.LANCZOS)
            (media / f'logo-{mode}.raw').write_bytes(struct.pack('>II', *pixels.size) + pixels.tobytes())


def build(output, sdk, dependencies, font, desktop=False, transport_only=False):
    output, sdk, dependencies, font = map(lambda p: Path(p).resolve(), (output, sdk, dependencies, font))
    if output.exists():
        raise FileExistsError(output)
    bear, cjson, mdns, stb = dependencies / 'bearssl', dependencies / 'cjson', dependencies / 'mdns', dependencies / 'stb'
    for folder, expected in ((bear, BEAR_REV), (cjson, CJSON_REV), (mdns, MDNS_REV), (stb, STB_REV)):
        revision = subprocess.check_output(['git', '-C', str(folder), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != expected:
            raise ValueError(f'Unexpected dependency revision: {folder.name}')
    output.mkdir(parents=True)
    objects, generated = output/'objects', output/'generated'
    objects.mkdir(); generated.mkdir()
    mdns_source = (mdns/'mdns.h').read_text(encoding='utf-8')
    includes = '#include <Winsock2.h>\n#include <Ws2tcpip.h>'
    if includes not in mdns_source:
        raise ValueError('Unexpected mDNS port header')
    mdns_source = mdns_source.replace(includes, '#ifdef _XBOX\n#include "mdns_xbox.h"\n#else\n' + includes + '\n#endif')
    (generated/'mdns.h').write_text(mdns_source, encoding='utf-8')
    env = os.environ.copy()
    if desktop:
        vc = Path('C:/Program Files (x86)/Microsoft Visual Studio 10.0/VC')
        windows = Path('C:/Program Files (x86)/Microsoft SDKs/Windows/v7.0A')
        binaries = vc/'bin'
        env['INCLUDE'] = os.pathsep.join(map(str, [vc/'include', windows/'Include', sdk/'include/xbox']))
        env['LIB'] = os.pathsep.join(map(str, [vc/'lib', windows/'Lib']))
        defines = ['/DOPENLIPS_HOST_TEST', '/DUNICODE', '/D_UNICODE']
        libraries = ['kernel32.lib', 'user32.lib', 'advapi32.lib', 'ws2_32.lib', 'd3d9.lib']
        shader = Path('C:/Program Files (x86)/Windows Kits/10/bin/10.0.26100.0/x86/fxc.exe')
    else:
        binaries = sdk/'bin/win32'
        env['INCLUDE'] = str(sdk/'include/xbox')
        env['LIB'] = str(sdk/'lib/xbox')
        defines = ['/D_XBOX', '/DXBOX']
        libraries = ['xapilib.lib', 'libcmt.lib', 'xboxkrnl.lib', 'd3d9.lib', 'xgraphics.lib', 'xnet.lib']
        shader = binaries/'fxc.exe'
    env['PATH'] = str(binaries) + os.pathsep + str(Path('C:/Program Files (x86)/Microsoft Visual Studio 10.0/Common7/IDE')) + os.pathsep + env.get('PATH', '')
    flags = ['/nologo', '/c', '/O2', '/MT', '/GR-', '/GS-', '/W3', '/D_CRT_SECURE_NO_WARNINGS',
             '/D_XBOX_CRT_DEPRECATE_INSECURE', '/DNDEBUG', '/DBR_USE_WIN32_RAND=0', '/DBR_USE_WIN32_TIME=0',
             '/DBR_USE_UNIX_TIME=0', '/DBR_USE_URANDOM=0', '/DBR_AES_X86NI=0', '/DBR_SSE2=0',
             '/DBR_POWER8=0', '/DBR_RDRAND=0', '/DBR_INT128=0', '/DCJSON_NESTING_LIMIT=64', '/Dinline=__inline'] + defines
    flags += ['/I'+str(bear/'inc'), '/I'+str(bear/'src'), '/I'+str(cjson), '/I'+str(stb),
              '/I'+str(ROOT/'xbox_client/src'), '/I'+str(generated), '/Fo'+str(objects)+os.sep]
    log = (output/'build.log').open('wb')
    def run(command):
        result = subprocess.run(list(map(str,command)), env=env, cwd=output,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log.write(result.stdout);log.flush()
        if result.returncode:
            print('\n'.join(result.stdout.decode(errors='replace').splitlines()[:45]))
            raise RuntimeError(f'Build tool failed ({result.returncode}); see {output / "build.log"}')
    try:
        sources = [bear/'src/hash/sha2small.c', *sorted((bear/'src/codec').glob('*32be.c')), cjson/'cJSON.c']
        if len({p.stem for p in sources}) != len(sources):
            raise ValueError('Duplicate object basenames')
        for begin in range(0,len(sources),20):
            run([binaries/'cl.exe',*flags,'/TC',*sources[begin:begin+20]])
        own = ['core.cpp','transport.cpp','discovery.cpp','transport_test.cpp'] if transport_only else ['core.cpp','transport.cpp','discovery.cpp','render.cpp','main.cpp']
        if not transport_only:
            for entry in ('vertex','pixel'):
                run([shader,'/nologo','/T', 'vs_3_0' if entry=='vertex' else 'ps_3_0', '/E',entry,
                    '/Fh',generated/f'render_{entry}.h','/Vn',f'render_{entry}',ROOT/'xbox_client/src/render.hlsl'])
        for name in own:
            source = generated/name
            source.write_bytes(b'\xef\xbb\xbf' + (ROOT/'xbox_client/src'/name).read_bytes())
            run([binaries/'cl.exe',*flags,source])
        response = generated/'objects.rsp'
        response.write_text('\n'.join('"'+str(p)+'"' for p in sorted(objects.glob('*.obj'))), encoding='utf-8')
        executable = output / ('transport-test.exe' if transport_only else 'OpenLipsXbox.exe')
        link = [binaries/'link.exe','/nologo','/out:'+str(executable),'@'+str(response),*libraries]
        if not desktop:
            link += ['/machine:PPCBE','/subsystem:xbox','/entry:mainCRTStartup','/base:0x82000000','/fixed:no','/XEX:NO']
        elif not transport_only:
            link += ['/subsystem:windows']
        run(link)
        if not desktop:
            if executable.read_bytes()[:2] != b'MZ':
                raise ValueError('The linker must emit a PE image, not an automatically generated development XEX')
            development = output/'sdk-development.xex'
            run([binaries/'imagexex.exe','/nologo','/in:'+str(output/'OpenLipsXbox.exe'),
                 '/out:'+str(development),'/titleid:0x4F4C5043'])
            from tools.inspect_xex_identity import identity
            if identity(development).get('title_id') != '4F4C5043':
                raise ValueError('Only our client image may be prepared for retail homebrew')
            xextool = dependencies/'xextool/msvc/build/x64/Release/XexTool.exe'
            if not xextool.is_file():
                raise ValueError('Build the private XexTool dependency before packaging a retail-console client')
            executable = output/'default.xex'
            run([xextool, '-m','r','-e','u','-c','u','-r','m','-o',executable,development])
        if not transport_only:
            assets(output,font)
        notices=output/'licenses';notices.mkdir()
        shutil.copyfile(bear/'LICENSE.txt',notices/'BearSSL.txt')
        shutil.copyfile(cjson/'LICENSE',notices/'cJSON.txt')
        shutil.copyfile(stb/'LICENSE',notices/'stb.txt')
        record={'binary':executable.name,'sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
            'bearssl_sha256':BEAR_REV,'cjson':CJSON_REV,'mdns':MDNS_REV,'stb':STB_REV,'hardware_verified':False,
            'desktop_preview':desktop,'source_sha256':{n:hashlib.sha256((ROOT/'xbox_client/src'/n).read_bytes()).hexdigest() for n in own}}
        (output/'build.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(executable)
        return executable
    finally:
        log.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sdk',default=os.environ.get('XEDK'))
    p.add_argument('--dependencies',type=Path,default=ROOT/'private/native-client-deps')
    p.add_argument('--font',type=Path,default=Path('C:/Windows/Fonts/segoeui.ttf'))
    p.add_argument('--desktop',action='store_true')
    p.add_argument('--transport-only',action='store_true')
    a=p.parse_args()
    build(a.output,a.sdk,a.dependencies,a.font,a.desktop,a.transport_only)
