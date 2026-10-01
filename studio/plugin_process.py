"""Declarative API-2 process plugins; no plugin Python is imported into Studio."""
from pathlib import Path, PurePosixPath
import platform
import re
import sys

from studio.plugins import ImportPlugin, PluginParameter

PROTOCOL_VERSION = 1


def platform_tag():
    system = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux' if sys.platform.startswith('linux') else sys.platform)
    machine = platform.machine().lower()
    architecture = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine, machine)
    return f'{system}-{architecture}'


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Unsafe plugin path: use relative POSIX paths')
    parts = value.split('/')
    if any(p in ('', '.', '..') or ':' in p or p.rstrip(' .') != p for p in parts):
        raise ValueError('Unsafe plugin path')
    if PurePosixPath(value).is_absolute():
        raise ValueError('Unsafe plugin path')
    return value


def validate_manifest(data):
    if not isinstance(data, dict) or not isinstance(data.get('id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-][a-zA-Z0-9_.-]{0,127}', data['id']):
        raise ValueError('Invalid plugin ID')
    if data['id'].rstrip(' .') != data['id']:
        raise ValueError('Invalid plugin ID')
    if data.get('api_version') != 2 or data.get('type') != 'process' or data.get('protocol') != PROTOCOL_VERSION:
        raise ValueError('Unsupported process plugin API/type/protocol')
    if data.get('result_type') != 'note-draft':
        raise ValueError('Unsupported plugin result type')
    for field in ('description', 'author', 'homepage'):
        if not isinstance(data.get(field, ''), str):
            raise ValueError('Plugin descriptive fields must be text')
    permissions = data.get('permissions', [])
    if not isinstance(permissions, list) or len(permissions) > 32 or not all(isinstance(x, str) and len(x) <= 100 for x in permissions):
        raise ValueError('Invalid plugin permissions')
    if not isinstance(data.get('label'), str) or not data['label']:
        raise ValueError('Missing plugin label')
    if not isinstance(data.get('version'), str) or not re.fullmatch(r'[a-zA-Z0-9_-][a-zA-Z0-9_.-]{0,63}', data['version']):
        raise ValueError('Invalid plugin version')
    entries = data.get('entrypoints')
    if not isinstance(entries, dict) or not entries:
        raise ValueError('Plugin needs platform entrypoints')
    for tag, executable in entries.items():
        if tag not in ('windows-x64', 'windows-arm64', 'linux-x64', 'linux-arm64', 'macos-x64', 'macos-arm64'):
            raise ValueError('Unsupported platform tag')
        relative_path(executable)
    extensions = data.get('extensions', [])
    if not isinstance(extensions, list) or not all(isinstance(x, str) and re.fullmatch(r'\.[a-zA-Z0-9]+', x) for x in extensions):
        raise ValueError('Invalid input extensions')
    parameters = data.get('parameters', [])
    if not isinstance(parameters, list) or len(parameters) > 64:
        raise ValueError('Invalid plugin parameters')
    keys = set()
    for parameter in parameters:
        if not isinstance(parameter, dict) or not isinstance(parameter.get('key'), str) or not re.fullmatch(r'[a-zA-Z0-9_]+', parameter['key']):
            raise ValueError('Invalid parameter key')
        if parameter['key'] in keys or not isinstance(parameter.get('label'), str):
            raise ValueError('Duplicate/invalid parameter')
        keys.add(parameter['key'])
        if parameter.get('kind') not in ('int', 'float', 'bool', 'choice', 'text'):
            raise ValueError('Unsupported parameter kind')
        if parameter['kind'] in ('int', 'float'):
            import math
            values = [parameter.get(k) for k in ('minimum', 'maximum', 'default')]
            if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in values):
                raise ValueError('Invalid numeric parameter')
            if not values[0] <= values[2] <= values[1]:
                raise ValueError('Parameter default outside bounds')
            if not -2147483647 <= values[0] <= values[1] <= 2147483647:
                raise ValueError('Parameter bounds exceed supported controls')
            if parameter['kind'] == 'int' and not all(isinstance(x, int) for x in values):
                raise ValueError('Integer parameter requires integer values')
        elif parameter['kind'] == 'choice':
            choices = parameter.get('choices')
            if not isinstance(choices, list) or not choices or not all(isinstance(x, list) and len(x) == 2 and isinstance(x[0], str) and isinstance(x[1], (str, int, float, bool)) for x in choices):
                raise ValueError('Invalid parameter choices')
            if parameter.get('default') not in [x[1] for x in choices]:
                raise ValueError('Invalid choice default')
        elif parameter['kind'] == 'bool' and not isinstance(parameter.get('default'), bool):
            raise ValueError('Invalid boolean default')
        elif parameter['kind'] == 'text' and not isinstance(parameter.get('default'), str):
            raise ValueError('Invalid text default')
    return data


def load_process_plugin(folder, data):
    data = validate_manifest(data)
    root = Path(folder).resolve()

    def command(request, output, python_override=''):
        executable = data['entrypoints'].get(platform_tag())
        if not executable:
            raise ValueError(f'Plugin does not support {platform_tag()}. Install the matching .opl package.')
        path = (root / executable).resolve(strict=True)
        path.relative_to(root)
        if not path.is_file():
            raise ValueError('Plugin runtime executable is missing')
        return [str(path), '--request', str(request), '--output', str(output)]

    parameters = tuple(PluginParameter(p['key'], p['label'], p['kind'], p['default'],
                                      p.get('minimum', 0), p.get('maximum', 1),
                                      tuple(tuple(c) for c in p.get('choices', [])))
                       for p in data.get('parameters', []))
    return ImportPlugin(data['id'], data['label'], tuple(data.get('extensions', [])), None,
                        description=data.get('description', ''), author=data.get('author', ''),
                        version=data['version'], homepage=data.get('homepage', ''),
                        parameters=parameters, create_command=command, process_plugin=True,
                        permissions=tuple(data.get('permissions', [])))
