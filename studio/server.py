"""Opt-in LAN worker API and read-only package FTP server, not a public web app."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
import ssl
import base64
from contextlib import contextmanager

from studio.library import Library
from studio.server_config import load_config


@contextmanager
def server_lock(root):
    with (root / 'server.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'1')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def stop_worker(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
    else:
        import signal
        os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=10)


def worker_command(library, job):
    arguments = ['--library', str(library), '--job', job]
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--server-job', *arguments]
    return [sys.executable, '-m', 'studio.server_job', *arguments]


class JobManager:
    def __init__(self, library, config=None):
        self.library = library
        self.encoding_enabled = (config or {}).get('encoding_enabled', sys.platform == 'win32')
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.process = None
        with library.connect() as db:
            db.execute("UPDATE jobs SET state='failed',progress='Worker stopped before completion' WHERE state IN ('queued','running')")
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def enqueue(self, request):
        if not isinstance(request, dict) or set(request) - {'projects', 'pack_name', 'kind'}:
            raise ValueError('Expected projects and optional pack_name')
        ids = request.get('projects')
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 16
                or any(not isinstance(value, str) or len(value) != 32 for value in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError('Use 1-16 distinct registered project IDs')
        name = request.get('pack_name')
        kind = request.get('kind', 'dlc')
        if kind not in ('dlc', 'chart', 'midi', 'lrc') or (kind != 'dlc' and (len(ids) != 1 or name is not None)):
            raise ValueError('Use one project for chart, MIDI or LRC export')
        if len(ids) > 1 and (not isinstance(name, str) or not name.strip() or len(name.encode('utf-16-be')) > 254):
            raise ValueError('A song pack needs a name of at most 127 UTF-16 code units')
        if len(ids) == 1 and name is not None:
            raise ValueError('pack_name is only valid for multi-song packages')
        for identifier in ids:
            self.library.project_path(identifier)
        with self.lock, self.library.connect() as db:
            if db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0] >= 8:
                raise ValueError('Job queue is full')
            identifier = uuid.uuid4().hex
            cached = self.library.cached_build(ids, name, True) if kind == 'dlc' else None
            if kind == 'dlc' and not cached and (sys.platform != 'win32' or not self.encoding_enabled):
                raise ValueError('Encoding currently requires Windows; library and prepared packages work on all platforms')
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?)',
                (identifier, json.dumps(request), 'ready' if cached else 'queued',
                 'Ready (cached)' if cached else 'Queued', cached, time.time()))
        return identifier

    def run(self):
        while not self.stop_event.wait(.25):
            with self.library.connect() as db:
                row = db.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
                if row:
                    db.execute("UPDATE jobs SET state='running',progress='Preparing' WHERE id=?", (row['id'],))
            if not row:
                continue
            try:
                log = self.library.root / ('worker-' + row['id'] + '.log')
                with log.open('wb') as output:
                    self.process = subprocess.Popen(worker_command(self.library.root, row['id']),
                        stdout=output, stderr=output, stdin=subprocess.DEVNULL,
                        start_new_session=os.name != 'nt',
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    while self.process.poll() is None:
                        if self.stop_event.wait(.25):
                            stop_worker(self.process)
                            break
            except Exception:
                pass
            finally:
                self.process = None
                with self.library.connect() as db:
                    db.execute("UPDATE jobs SET state='failed',progress='Build interrupted or failed; see local log' WHERE id=? AND state='running'", (row['id'],))

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=20)


def handler_for(library, config, manager, auth=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'OpenLips'

        def setup(self):
            super().setup()
            self.connection.settimeout(10)
            if isinstance(self.connection, ssl.SSLSocket):
                self.connection.do_handshake()

        def log_message(self, format, *args):
            pass

        def reply(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def safe_request(self):
            self.connection.settimeout(10)
            origin = self.headers.get('Origin')
            scheme = 'https' if config.get('tls_cert') else 'http'
            if (self.headers.get('Transfer-Encoding') or (origin and (
                    not config.get('allow_browser') or origin != scheme + '://' + self.headers.get('Host', '')))):
                self.reply(403, {'error': 'Browser/cross-origin requests are not allowed'})
                return False
            expected = f"{config['bind']}:{self.server.server_address[1]}"
            if self.headers.get('Host') not in (expected, f"localhost:{self.server.server_address[1]}" if config['bind'] == '127.0.0.1' else expected):
                self.reply(403, {'error': 'Invalid Host'})
                return False
            return True

        def token(self):
            return self.headers.get('Authorization', '').removeprefix('Bearer ')

        def master(self):
            return bool(config.get('lan_open')) or hmac.compare_digest(self.token().encode(), config['api_token'].encode())

        def authorized(self):
            if not self.safe_request():
                return False
            if config.get('lan_open'):
                return True
            if not (auth.valid(self.token()) if auth else self.master()):
                self.reply(401, {'error': 'Authentication required'})
                return False
            return True

        def do_GET(self):
            if self.path == '/api/v1/identity':
                if self.safe_request():
                    self.reply(200, dict(server_id=config.get('server_id', ''), name=config.get('name', 'OpenLips Library'),
                        protocol=1, fingerprint=config.get('certificate_fingerprint', ''), auth_required=not config.get('lan_open', False),
                        pairing=bool(auth and (config.get('tls_cert') or config['bind'] == '127.0.0.1'))))
                return
            if not self.authorized():
                return
            if self.path == '/api/v1/library':
                self.reply(200, {'projects': library.projects(), 'packages': library.packages(), 'artifacts': library.artifacts(), 'songs': library.songs()})
            elif self.path == '/api/v1/status':
                self.reply(200, dict(protocol=1, auth_required=not config.get('lan_open', False), encoding=sys.platform == 'win32' and config.get('encoding_enabled', True),
                    chart_conversion=True, portable_transcode=False, native_xbox_transport=False,
                    ftp_port=config['ftp_port'], ftp_user=config['ftp_user'],
                    passive_ports=config['passive_ports']))
            elif self.path == '/api/v1/devices' and auth and self.master():
                self.reply(200, {'devices': auth.devices()})
            elif self.path.startswith('/api/v1/projects/'):
                from studio.library_exchange import portable_project, media_path
                parts = self.path.removeprefix('/api/v1/projects/').split('/')
                try:
                    if len(parts) == 1:
                        self.reply(200, portable_project(library, parts[0]))
                    elif len(parts) == 3 and parts[1] == 'media':
                        self.reply_file(media_path(library, parts[0], parts[2]))
                    else:
                        self.reply(404, {'error': 'Unknown resource'})
                except (KeyError, ValueError, OSError):
                    self.reply(404, {'error': 'Project or media unavailable'})
            elif self.path.startswith('/api/v1/artifacts/') or self.path.startswith('/api/v1/packages/'):
                try:
                    identifier = self.path.rsplit('/', 1)[1]
                    path = library.artifact_path(identifier) if '/artifacts/' in self.path else library.package_path(identifier)
                    self.reply_file(path)
                except (KeyError, ValueError, OSError):
                    self.reply(404, {'error': 'Output unavailable'})
            elif self.path.startswith('/api/v1/jobs/'):
                identifier = self.path.removeprefix('/api/v1/jobs/')
                with library.connect() as db:
                    row = db.execute('SELECT id,state,progress,package_id,created FROM jobs WHERE id=?', (identifier,)).fetchone()
                self.reply(200 if row else 404, dict(row) if row else {'error': 'Unknown job'})
            elif self.path == '/api/v1/jobs':
                with library.connect() as db:
                    rows = db.execute('SELECT id,state,progress,package_id,created,request FROM jobs ORDER BY created DESC LIMIT 100').fetchall()
                titles = {p['id']: p['title'] for p in library.projects()}
                records = []
                for row in rows:
                    item = dict(row)
                    request = json.loads(item.pop('request'))
                    item['kind'] = request.get('kind', 'dlc')
                    item['title'] = request.get('pack_name') or titles.get(request['projects'][0], 'Project')
                    records.append(item)
                self.reply(200, {'jobs': records})
            else:
                self.reply(404, {'error': 'Unknown endpoint'})

        def do_POST(self):
            if self.path == '/api/v1/pair':
                if not self.safe_request():
                    return
                if not auth or (not config.get('tls_cert') and config['bind'] != '127.0.0.1'):
                    self.reply(403, {'error': 'Pairing requires TLS or localhost'})
                    return
                try:
                    request = self.json_body()
                    result = auth.pair(request.get('code'), request.get('name'))
                    result.update(server_id=config['server_id'], ftp_port=config['ftp_port'])
                    self.reply(200, result)
                except (ValueError, KeyError, TypeError, UnicodeError):
                    self.reply(400, {'error': 'Pairing unavailable, invalid or expired'})
                return
            if not self.authorized():
                return
            if self.path == '/api/v1/pairing' and auth and self.master():
                if not config.get('tls_cert') and config['bind'] != '127.0.0.1':
                    self.reply(403, {'error': 'Enable HTTPS before remote pairing'})
                    return
                self.reply(200, auth.begin_pairing())
                return
            if self.path in ('/api/v1/transcode', '/api/v1/console-transfer'):
                self.reply(501, {'error': 'Backend prepared but deliberately disabled'})
                return
            if self.path == '/api/v1/import':
                try:
                    request = self.json_body(24 * 1024 * 1024)
                    if set(request) - {'name', 'data', 'title', 'artist'}:
                        raise ValueError('Unsupported import fields')
                    from studio.library_exchange import import_input
                    identifier = import_input(library, request['name'], base64.b64decode(request['data'], validate=True),
                        title=request.get('title', ''), artist=request.get('artist', ''))
                    self.reply(201, {'id': identifier})
                except (ValueError, KeyError, TypeError, UnicodeError) as error:
                    self.reply(400, {'error': str(error)[:500]})
                return
            if self.path == '/api/v1/project-bundles':
                try:
                    import tempfile
                    import zipfile
                    from studio.library_bundle import BUNDLE_LIMIT, import_bundle
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= BUNDLE_LIMIT:
                        raise ValueError('Invalid project bundle size')
                    with tempfile.TemporaryDirectory(dir=library.root / '.staging') as folder:
                        path = Path(folder) / 'project.zip'
                        with path.open('xb') as stream:
                            remaining = length
                            while remaining:
                                chunk = self.rfile.read(min(65536, remaining))
                                if not chunk:
                                    raise ValueError('Incomplete project bundle upload')
                                stream.write(chunk)
                                remaining -= len(chunk)
                        identifier = import_bundle(library, path)
                    self.reply(201, {'id': identifier})
                except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
                    self.reply(400, {'error': str(error)[:500]})
                return
            if self.path == '/api/v1/packages':
                try:
                    import tempfile
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 2 * 1024 ** 3:
                        raise ValueError('Invalid DLC upload size')
                    with tempfile.TemporaryDirectory(dir=library.root / '.staging') as folder:
                        path = Path(folder) / 'package.LIVE'
                        with path.open('xb') as stream:
                            remaining = length
                            while remaining:
                                chunk = self.rfile.read(min(65536, remaining))
                                if not chunk:
                                    raise ValueError('Incomplete DLC upload')
                                stream.write(chunk)
                                remaining -= len(chunk)
                        identifier = library.add_package(path)
                    self.reply(201, {'id': identifier})
                except (ValueError, OSError) as error:
                    self.reply(400, {'error': str(error)[:500]})
                return
            if self.path.startswith('/api/v1/projects/'):
                parts = self.path.removeprefix('/api/v1/projects/').split('/')
                try:
                    from studio.model import load_project
                    project = load_project(library.project_path(parts[0]))
                    if len(parts) == 1:
                        request = self.json_body()
                        if not request or set(request) - {'title', 'artist'} or any(
                                not isinstance(value, str) or not value.strip() or len(value) > 256 for value in request.values()):
                            raise ValueError('Use nonempty title/artist up to 256 characters')
                        for key, value in request.items():
                            setattr(project, key, value.strip())
                    elif len(parts) == 2 and parts[1] == 'lyrics':
                        request = self.json_body(4 * 1024 * 1024)
                        from studio.lrc import parse_lrc, assign_lrc_notes, attach_lrc
                        raw = base64.b64decode(request.get('data', ''), validate=True).decode('utf-8-sig')
                        document = parse_lrc(raw)
                        if not project.notes:
                            raise ValueError('Add MIDI/chart notes before assigning LRC')
                        attach_lrc(project, document, 'Library LRC')
                        if not assign_lrc_notes(project, document):
                            raise ValueError('No LRC anchors overlap the existing chart notes')
                    elif len(parts) == 3 and parts[1] == 'media':
                        import tempfile
                        field = parts[2]
                        extension = Path(self.headers.get('X-File-Name', '')).suffix.lower()
                        allowed = {'audio': {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma', '.xwma'},
                                   'video': {'.mp4', '.mkv', '.webm', '.mov', '.avi', '.wmv'},
                                   'cover': {'.png', '.jpg', '.jpeg', '.webp'}}
                        length = int(self.headers.get('Content-Length', '0'))
                        limit = 8 * 1024 * 1024 if field == 'cover' else 2 * 1024 ** 3
                        if extension not in allowed.get(field, set()) or not 0 < length <= limit:
                            raise ValueError('Unsupported media type or size')
                        with tempfile.TemporaryDirectory(dir=library.root / '.staging') as folder:
                            path = Path(folder) / ('media' + extension)
                            with path.open('xb') as stream:
                                remaining = length
                                while remaining:
                                    chunk = self.rfile.read(min(65536, remaining))
                                    if not chunk:
                                        raise ValueError('Incomplete media upload')
                                    stream.write(chunk)
                                    remaining -= len(chunk)
                            if field == 'cover':
                                from PIL import Image
                                with Image.open(path) as image:
                                    if image.width * image.height > 16 * 1024 ** 2 or image.format not in ('PNG', 'JPEG', 'WEBP'):
                                        raise ValueError('Cover image is too large or unsupported')
                                    image.verify()
                            else:
                                # Stored, not executed or automatically transcoded. Decoding
                                # and codec validation remain the consuming worker's job.
                                from studio.library_exchange import validate_media_header
                                validate_media_header(path, field)
                            setattr(project, field + '_path', str(path))
                            identifier = library.add_project(project)
                        self.reply(201, {'id': identifier})
                        return
                    else:
                        raise ValueError('Unknown project action')
                    self.reply(201, {'id': library.add_project(project)})
                except (ValueError, KeyError, OSError, UnicodeError) as error:
                    self.reply(400, {'error': str(error)[:500]})
                return
            if self.path == '/api/v1/shutdown':
                if not self.master():
                    self.reply(403, {'error': 'Owner access required'})
                    return
                self.reply(202, {'state': 'stopping'})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path != '/api/v1/jobs':
                self.reply(404, {'error': 'Unknown endpoint'})
                return
            try:
                identifier = manager.enqueue(self.json_body())
                self.reply(202, {'id': identifier})
            except (ValueError, KeyError, UnicodeError) as error:
                self.reply(400, {'error': str(error)})

        def json_body(self, limit=8192):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= limit or self.headers.get_content_type() != 'application/json':
                raise ValueError('Invalid JSON body size or content type')
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Incomplete request')
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError('Expected a JSON object')
            return value

        def reply_file(self, path):
            with path.open('rb') as stream:
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(path.stat().st_size))
                self.send_header('Content-Disposition', 'attachment; filename="' + path.name + '"')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                while chunk := stream.read(65536):
                    self.wfile.write(chunk)

        def do_DELETE(self):
            if not self.authorized():
                return
            if not self.master():
                self.reply(403, {'error': 'Owner access required'})
                return
            try:
                if self.path.startswith('/api/v1/devices/') and auth:
                    auth.revoke(self.path.rsplit('/', 1)[1])
                elif self.path.startswith('/api/v1/projects/'):
                    identifier = self.path.rsplit('/', 1)[1]
                    with library.connect() as db:
                        if db.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running')").fetchone():
                            raise ValueError('Wait for active jobs before removing a project')
                    library.remove_project(identifier)
                else:
                    self.reply(404, {'error': 'Unknown endpoint'})
                    return
                self.reply(200, {'removed': True})
            except (KeyError, ValueError) as error:
                self.reply(400, {'error': str(error)})
    return Handler


def make_ftp(library, config):
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    from pyftpdlib.ioloop import IOLoop

    authorizer = DummyAuthorizer()
    if config.get('lan_open'):
        authorizer.add_anonymous(str(library.root / 'publish'), perm='elr')
    else:
        authorizer.add_user(config['ftp_user'], config['ftp_password'], str(library.root / 'publish'), perm='elr')

    class Handler(FTPHandler):
        banner = 'OpenLips package library'
        timeout = 60
        max_login_attempts = 3
        passive_ports = range(config['passive_ports'][0], config['passive_ports'][1] + 1)
        permit_foreign_addresses = False
        permit_privileged_ports = False
        auth_failed_timeout = 2
    Handler.authorizer = authorizer
    server = FTPServer((config['bind'], config['ftp_port']), Handler, ioloop=IOLoop())
    server.max_cons = 8
    server.max_cons_per_ip = 4
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--authenticated', action='store_true', help='Preserve the legacy authenticated configuration')
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if not args.authenticated and not config.get('lan_open'):
        from studio.server_config import update_features
        update_features(args.config, tls=False, discovery=True, name=config['name'], lan_open=True)
        config = load_config(args.config)
    library = Library(config['library'])
    with server_lock(library.root):
        return serve(library, config)


def serve(library, config, handler_factory=handler_for):
    # Fail before starting jobs if dependencies or ports are unavailable.
    ftp = make_ftp(library, config)
    from studio.library_security import DeviceAuth
    from studio.library_discovery import announcement, stop_announcement
    auth = None if config.get('lan_open') else DeviceAuth(library, config, ftp.handler.authorizer)
    manager = JobManager(library, config)
    http = None
    advertised = None
    previous_sigterm = None
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

            def handle_error(self, request, client_address):
                if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError, ssl.SSLError)):
                    return
                super().handle_error(request, client_address)

        http = Server((config['bind'], config['port']), handler_factory(library, config, manager, auth))
        if config.get('tls_cert'):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(config['tls_cert'], config['tls_key'])
            http.socket = context.wrap_socket(http.socket, server_side=True, do_handshake_on_connect=False)
        http.daemon_threads = True
        if threading.current_thread() is threading.main_thread():
            import signal
            previous_sigterm = signal.signal(signal.SIGTERM,
                lambda *_: threading.Thread(target=http.shutdown, daemon=True).start())
        thread = threading.Thread(target=lambda: ftp.serve_forever(timeout=.25, handle_exit=False), daemon=True)
        thread.start()
        try:
            advertised = announcement(config)
        except Exception as error:
            print(f'Discovery unavailable: {type(error).__name__}', flush=True)
        if sys.stdout:
            print(f"OpenLips worker: {config['bind']}:{config['port']} (FTP {config['ftp_port']})", flush=True)
        http.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        if http:
            http.server_close()
        manager.close()
        ftp.close_all()
        stop_announcement(advertised)
        if previous_sigterm is not None:
            import signal
            signal.signal(signal.SIGTERM, previous_sigterm)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
