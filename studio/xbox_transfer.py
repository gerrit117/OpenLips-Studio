"""Explicit, verified LAN transfers; credentials are never persisted."""
import ftplib
import ipaddress
import socket
import ssl
from contextlib import contextmanager

from tools.build_dlc import upload_package, xbox_path


def private_address(host):
    if not host or any(c.isspace() for c in host) or len(host) > 253:
        raise ValueError('Enter a LAN address or hostname')
    addresses = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    for family, _, _, _, endpoint in addresses:
        address = ipaddress.ip_address(endpoint[0].split('%')[0])
        allowed = address.is_loopback or (
            address.version == 4 and any(address in ipaddress.ip_network(net)
                for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))
        if allowed:
            return str(address)
    raise ValueError('Xbox transfers require a trusted IPv4 LAN/VPN or localhost')


@contextmanager
def connection(host, port, username, password, tls=False):
    if not 1 <= port <= 65535 or any(c in username + password for c in '\r\n\x00'):
        raise ValueError('Invalid FTP settings')
    address = private_address(host)
    client = ftplib.FTP_TLS(context=ssl.create_default_context(), timeout=30) if tls else ftplib.FTP(timeout=30)
    try:
        # Resolve once and connect to the checked address, not a second DNS result.
        client.connect(address, port)
        if tls:
            client.host = host  # TLS checks the configured hostname/certificate.
        client.login(username, password)
        if tls:
            client.prot_p()
        client.set_pasv(True)
        yield client
    finally:
        client.close()


def copy_to_xbox(package, settings, progress=None, cancelled=lambda: False):
    remote = xbox_path(package, settings.get('root', 'Hdd1/Content'))
    def cleanup(path):
        # A callback cancellation can leave the control channel out of sync.
        # Remove only our exact staging filename through a fresh connection.
        with connection(settings['host'], settings['port'], settings['username'],
                        settings['password'], settings.get('tls', False)) as client:
            client.delete(path)
    with connection(settings['host'], settings['port'], settings['username'],
                    settings['password'], settings.get('tls', False)) as ftp:
        upload_package(ftp, package, remote, progress=progress, cancelled=cancelled, cleanup=cleanup)
    return remote
