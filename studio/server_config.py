"""Per-user server configuration; Windows secrets use current-user DPAPI."""
import argparse
import base64
import ctypes
import ipaddress
import json
import os
from pathlib import Path
import secrets
import tempfile
import uuid

from studio.library import default_library_root


def crypt(data, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def local_bind(host):
    address = ipaddress.ip_address(host)
    if address.version != 4 or not (address.is_loopback or any(address in ipaddress.ip_network(net)
        for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))):
        raise ValueError('Bind to a specific IPv4 LAN/VPN address or 127.0.0.1, not 0.0.0.0')
    return str(address)


def default_lan_bind():
    import socket
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
        for value in sorted(addresses, key=lambda address: (not address.startswith('192.168.'), address)):
            try:
                if not ipaddress.ip_address(local_bind(value)).is_loopback:
                    return value
            except ValueError:
                continue
    except OSError:
        pass
    return '127.0.0.1'


def create_config(path, library, bind='127.0.0.1', port=8765, ftp_port=2121, *, tls=False, discovery=False, name='OpenLips Library', lan_open=False):
    local_bind(bind)
    if not all(1024 <= value <= 65535 for value in (port, ftp_port)) or port == ftp_port:
        raise ValueError('Use two distinct unprivileged ports')
    if any(50000 <= value <= 50009 for value in (port, ftp_port)):
        raise ValueError('Control ports must not overlap passive FTP ports 50000-50009')
    config = dict(schema=1, library=str(Path(library).resolve()), bind=bind,
                  port=port, ftp_port=ftp_port, ftp_user='openlips',
                  passive_ports=[50000, 50009], server_id=uuid.uuid4().hex,
                  name=name[:80], discovery_enabled=bool(discovery), lan_open=bool(lan_open))
    credentials = dict(api_token=secrets.token_urlsafe(32), ftp_password=secrets.token_urlsafe(24)) if not lan_open else {}
    if lan_open:
        config['ftp_user'] = 'anonymous'
    elif os.name == 'nt':
        config['secrets_dpapi'] = base64.b64encode(crypt(json.dumps(credentials).encode())).decode('ascii')
    else:
        config['secrets'] = credentials
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    if tls and not lan_open:
        from studio.library_security import create_certificate
        config['tls_cert'], config['tls_key'] = create_certificate(path.parent, bind)
    with path.open('x', encoding='utf-8') as stream:
        if os.name != 'nt':
            os.fchmod(stream.fileno(), 0o600)
        json.dump(config, stream, indent=2)
    return load_config(path)


def update_connection(path, bind, port, ftp_port):
    path = Path(path)
    current = load_config(path)
    local_bind(bind)
    if (not all(1024 <= value <= 65535 for value in (port, ftp_port)) or port == ftp_port
            or any(current['passive_ports'][0] <= value <= current['passive_ports'][1] for value in (port, ftp_port))):
        raise ValueError('Invalid or overlapping control ports')
    raw = json.loads(path.read_text(encoding='utf-8'))
    raw.update(bind=bind, port=port, ftp_port=ftp_port)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            if os.name != 'nt':
                os.fchmod(stream.fileno(), 0o600)
            json.dump(raw, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def update_features(path, *, tls, discovery, name, lan_open=False):
    path = Path(path)
    current = load_config(path)
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError('Use a library name of 1-80 characters')
    raw = json.loads(path.read_text(encoding='utf-8'))
    raw.update(name=name.strip(), discovery_enabled=bool(discovery), server_id=current['server_id'], lan_open=bool(lan_open))
    tls = bool(tls and not lan_open)
    if not lan_open and not raw.get('secrets_dpapi') and not raw.get('secrets'):
        credentials = dict(api_token=secrets.token_urlsafe(32), ftp_password=secrets.token_urlsafe(24))
        if os.name == 'nt':
            raw['secrets_dpapi'] = base64.b64encode(crypt(json.dumps(credentials).encode())).decode('ascii')
        else:
            raw['secrets'] = credentials
    raw['ftp_user'] = 'anonymous' if lan_open else 'openlips'
    if tls and not raw.get('tls_cert'):
        from studio.library_security import create_certificate
        cert, key = path.parent / 'library-cert.pem', path.parent / 'library-key.pem'
        if cert.is_file() and key.is_file():
            raw.update(tls_cert=str(cert), tls_key=str(key))
        else:
            raw['tls_cert'], raw['tls_key'] = create_certificate(path.parent, current['bind'])
    if not tls:
        raw.pop('tls_cert', None)
        raw.pop('tls_key', None)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            if os.name != 'nt':
                os.fchmod(stream.fileno(), 0o600)
            json.dump(raw, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def load_config(path):
    path = Path(path)
    if path.stat().st_size > 16384:
        raise ValueError('Server configuration too large')
    if os.name != 'nt' and path.stat().st_mode & 0o077:
        raise ValueError('Server configuration must have mode 0600')
    config = json.loads(path.read_text(encoding='utf-8'))
    if config.get('schema') != 1:
        raise ValueError('Unsupported server configuration')
    if not isinstance(config.get('lan_open', False), bool):
        raise ValueError('lan_open must be true or false')
    local_bind(config['bind'])
    if not all(isinstance(config[key], int) and 1024 <= config[key] <= 65535 for key in ('port', 'ftp_port')):
        raise ValueError('Invalid server ports')
    if config['port'] == config['ftp_port']:
        raise ValueError('API and FTP ports must differ')
    if config.get('lan_open'):
        config.update(api_token='', ftp_password='', ftp_user='anonymous')
        config.pop('tls_cert', None)
        config.pop('tls_key', None)
    elif os.name == 'nt':
        config.update(json.loads(crypt(base64.b64decode(config['secrets_dpapi'], validate=True), True)))
    else:
        config.update(config['secrets'])
    if not config.get('lan_open') and any(not isinstance(config.get(key), str) or len(config[key]) < 24
           for key in ('api_token', 'ftp_password')):
        raise ValueError('Missing strong server credentials')
    import hashlib
    config.setdefault('server_id', hashlib.sha256(config['api_token'].encode()).hexdigest()[:32])
    config.setdefault('name', 'OpenLips Library')
    if config.get('tls_cert'):
        from studio.library_security import certificate_fingerprint
        config['certificate_fingerprint'] = certificate_fingerprint(config['tls_cert'])
    start, end = config['passive_ports']
    if not 1024 <= start <= end <= 65535 or end - start > 100:
        raise ValueError('Invalid passive FTP ports')
    if any(start <= config[key] <= end for key in ('port', 'ftp_port')):
        raise ValueError('Passive ports overlap control ports')
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description='Initialize a local OpenLips worker (never overwrites credentials)')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--library', type=Path, default=default_library_root())
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--ftp-port', type=int, default=2121)
    parser.add_argument('--authenticated', action='store_true', help='Legacy authenticated mode instead of the default open LAN library')
    args = parser.parse_args(argv)
    create_config(args.config, args.library, args.bind, args.port, args.ftp_port,
                  lan_open=not args.authenticated, discovery=args.bind != '127.0.0.1')
    return 0
