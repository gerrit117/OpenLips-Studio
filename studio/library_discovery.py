"""Opt-in mDNS presence. Advertisements contain no passwords, paths or songs."""
import ipaddress
import socket
import threading
import time

SERVICE = '_openlips._tcp.local.'


def announcement(config):
    from zeroconf import Zeroconf, ServiceInfo, IPVersion
    address = ipaddress.ip_address(config['bind'])
    if address.is_loopback or not config.get('discovery_enabled'):
        return None
    properties = dict(id=config['server_id'], name=config.get('name', 'OpenLips Library'),
        protocol='1', tls='1' if config.get('tls_cert') else '0',
        fingerprint=config.get('certificate_fingerprint', ''), auth='0' if config.get('lan_open') else '1')
    service = ServiceInfo(SERVICE, config['server_id'] + '.' + SERVICE,
        addresses=[socket.inet_aton(str(address))], port=config['port'],
        properties=properties, server='openlips-' + config['server_id'] + '.local.')
    zeroconf = Zeroconf(interfaces=[str(address)], ip_version=IPVersion.V4Only)
    try:
        zeroconf.register_service(service)
    except Exception:
        zeroconf.close()
        raise
    return zeroconf, service


def stop_announcement(value):
    if value:
        zeroconf, service = value
        try:
            zeroconf.unregister_service(service)
        finally:
            zeroconf.close()


def discover(seconds=3):
    from zeroconf import Zeroconf, ServiceBrowser, IPVersion
    found, lock = {}, threading.Lock()
    class Listener:
        def add_service(self, zc, kind, name):
            info = zc.get_service_info(kind, name, timeout=1000)
            if not info:
                return
            props = {k.decode('ascii', errors='ignore'): v.decode('utf-8', errors='replace')
                     for k, v in info.properties.items() if isinstance(v, bytes)}
            if props.get('protocol') != '1' or len(props.get('id', '')) != 32:
                return
            for host in info.parsed_addresses():
                address = ipaddress.ip_address(host)
                if address.version != 4 or not any(address in ipaddress.ip_network(net)
                    for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
                    continue
                with lock:
                    found[props['id']] = dict(server_id=props['id'], name=props.get('name', 'OpenLips Library')[:80],
                        host=host, port=info.port, tls=props.get('tls') == '1', fingerprint=props.get('fingerprint', ''), auth_required=props.get('auth', '1')!='0')
        update_service = add_service
        def remove_service(self, zc, kind, name):
            pass
    zc = Zeroconf(ip_version=IPVersion.V4Only)
    browser = ServiceBrowser(zc, SERVICE, Listener())
    try:
        time.sleep(max(.1, min(seconds, 10)))
        with lock:
            return list(found.values())
    finally:
        browser.cancel()
        zc.close()
