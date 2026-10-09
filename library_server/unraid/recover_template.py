"""Reconstruct DockerMan XML from inspected OpenLips settings; emit XML only."""
import json
import os
import re
import shlex
import sys
from xml.etree import ElementTree as ET


def template(inspected):
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise ValueError('Inspect exactly one OpenLips container')
    container = inspected[0]
    name = container['Name'].lstrip('/')
    image = container['Config']['Image']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', name) or not image.startswith('ghcr.io/gerrit117/openlips-library:'):
        raise ValueError('This helper only supports the official OpenLips Library image')
    network = container['HostConfig']['NetworkMode']
    if network != 'bridge':
        raise ValueError('Expected bridge networking. Do not replace a custom network blindly')
    host = container['HostConfig']
    if host.get('Privileged') or container['Config'].get('Cmd'):
        raise ValueError('Privileged mode or custom command requires manual review')
    root = ET.Element('Container', version='2')
    for key, value in {'Name': name, 'Repository': image, 'Network': network, 'Privileged': 'false',
        'Registry': 'https://github.com/gerrit117/OpenLips-Studio/pkgs/container/openlips-library',
        'Support': 'https://github.com/gerrit117/OpenLips-Studio/issues',
        'Project': 'https://github.com/gerrit117/OpenLips-Studio',
        'Icon': 'https://raw.githubusercontent.com/gerrit117/OpenLips-Studio/main/library_server/static/logo-light.png',
        'Overview': 'Private LAN library. HTTP, no authentication or discovery.',
        'ExtraParams': '', 'PostArgs': ''}.items():
        ET.SubElement(root, key).text = value
    extra = []
    if host.get('ReadonlyRootfs'):
        extra.append('--read-only')
    for option in host.get('SecurityOpt') or []:
        extra.extend(['--security-opt', option])
    for destination, options in (host.get('Tmpfs') or {}).items():
        extra.extend(['--tmpfs', destination + ':' + options])
    for option in host.get('CapDrop') or []:
        extra.extend(['--cap-drop', option])
    for option in host.get('CapAdd') or []:
        extra.extend(['--cap-add', option])
    for setting, flag in [('Memory', '--memory'), ('PidsLimit', '--pids-limit'), ('NanoCpus', '--cpus')]:
        value = host.get(setting)
        if value and value > 0:
            extra.extend([flag, str(value / 1e9 if setting == 'NanoCpus' else value)])
    root.find('ExtraParams').text = ' '.join(shlex.quote(value) for value in extra)
    def config(label, target, value, kind, mode=''):
        ET.SubElement(root, 'Config', Name=label, Target=target, Default=value, Type=kind,
            Mode=mode, Display='always', Required='true', Mask='false', Description=label).text = value
    bindings = container['HostConfig'].get('PortBindings', {})
    web_port = None
    for target, entries in bindings.items():
        for entry in entries or []:
            port, protocol = target.split('/')
            if protocol != 'tcp' or port != '8765':
                raise ValueError('Unexpected mapped ports; review the template manually')
            host_port = entry['HostPort']
            if not str(host_port).isdigit():
                raise ValueError('Invalid mapped port')
            if entry.get('HostIp') not in ('', '0.0.0.0', '::'):
                raise ValueError('Host-IP-specific ports require manual review')
            config('Web port', port, host_port, 'Port', protocol)
            web_port = host_port
    if not web_port:
        raise ValueError('Missing published HTTP port')
    ET.SubElement(root, 'WebUI').text = 'http://[IP]:[PORT:8765]/'
    for mount in container.get('Mounts', []):
        if mount['Destination'] not in ('/data', '/library'):
            raise ValueError('Unexpected mount; review the template manually')
        if mount['Type'] != 'bind':
            raise ValueError('Use dedicated host folder mounts, not Docker-managed volumes')
        config('Song library' if mount['Destination'] == '/library' else 'Appdata',
               mount['Destination'], mount['Source'], 'Path', 'rw' if mount['RW'] else 'ro')
    for setting in container['Config'].get('Env', []):
        key, _, value = setting.partition('=')
        if key in ('PUID', 'PGID', 'OPENLIPS_PORT'):
            config(key, key, value, 'Variable')
        elif key.startswith('OPENLIPS_'):
            raise ValueError('Old OPENLIPS settings require manual review before template recovery')
    ET.indent(root)
    return ET.tostring(root, encoding='unicode', xml_declaration=True)


if __name__ == '__main__':
    try:
        inspected = json.loads(os.environ['OPENLIPS_INSPECT'])
        sys.stdout.write(template(inspected) + '\n')
    except (KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f'Template recovery stopped: {error}\n')
        raise SystemExit(1)
