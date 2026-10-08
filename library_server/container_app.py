"""Single-port Docker library; old network settings never override its defaults."""
import argparse
from http.server import ThreadingHTTPServer
import ipaddress
import os
from pathlib import Path
import re
import signal
import threading
import uuid
from urllib.parse import urlsplit

from library_server.app import web_handler
from studio.library import Library
from studio.server import JobManager, server_lock


def runtime_config(library, port):
    with library.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS container_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO container_settings VALUES (?, ?)', ('server_id', uuid.uuid4().hex))
        identifier = db.execute("SELECT value FROM container_settings WHERE key='server_id'").fetchone()[0]
    return dict(bind='0.0.0.0', port=port, server_id=identifier,
                name=os.environ.get('OPENLIPS_NAME', 'OpenLips Library')[:80],
                lan_open=True, allow_browser=True, encoding_enabled=False,
                discovery_enabled=False, api_token='', ftp_password='', ftp_user='',
                ftp_port=0, passive_ports=[])


def local_authority(authority):
    try:
        parsed = urlsplit('http://' + authority)
        host = parsed.hostname
        if not host or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return False
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return False
        try:
            address = ipaddress.ip_address(host)
            return address.is_private or address.is_loopback
        except ValueError:
            return bool(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.local)?', host))
    except ValueError:
        return False


def container_handler(library, config, manager):
    Base = web_handler(library, config, manager, None)

    class Handler(Base):
        def safe_request(self):
            authority = self.headers.get('Host', '')
            origin = self.headers.get('Origin')
            if (not local_authority(authority) or self.headers.get('Transfer-Encoding')
                    or (origin and origin != 'http://' + authority)):
                self.reply(403, {'error': 'Use the library LAN address; cross-origin requests are not allowed'})
                return False
            return True

    return Handler


def serve_http(library, config):
    manager = JobManager(library, config)
    previous = None
    try:
        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def __init__(self, *args):
                self.slots = threading.BoundedSemaphore(16)
                super().__init__(*args)

            def process_request(self, request, address):
                if not self.slots.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request, address)
                except Exception:
                    self.slots.release()
                    raise

            def process_request_thread(self, request, address):
                try:
                    super().process_request_thread(request, address)
                finally:
                    self.slots.release()

        with Server(('0.0.0.0', config['port']), container_handler(library, config, manager)) as http:
            if threading.current_thread() is threading.main_thread():
                previous = signal.signal(signal.SIGTERM,
                    lambda *_: threading.Thread(target=http.shutdown, daemon=True).start())
            print(f"OpenLips Library: HTTP port {config['port']}; no FTP, discovery, TLS or login", flush=True)
            http.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        manager.close()
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=Path('/data/library'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('OPENLIPS_PORT', '8765')))
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error('Use a port between 1024 and 65535')
    try:
        library = Library(args.library)
        config = runtime_config(library, args.port)
        with server_lock(library.root):
            return serve_http(library, config)
    except (OSError, ValueError) as error:
        parser.exit(1, f'OpenLips Library could not start: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
