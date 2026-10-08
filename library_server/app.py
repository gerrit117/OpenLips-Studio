"""Private-network library UI using Studio's shared server and authoring APIs."""
import argparse
import os
from pathlib import Path
import signal
import threading

from studio.library import Library
from studio.server import handler_for, server_lock, serve
from studio.server_config import create_config, load_config, update_features

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def web_handler(library, config, manager, auth):
    Base = handler_for(library, config, manager, auth)
    assets = {'/': (ROOT / 'static/index.html', 'text/html; charset=utf-8'),
              '/app.css': (ROOT / 'static/app.css', 'text/css; charset=utf-8'),
              '/app.js': (ROOT / 'static/app.js', 'text/javascript; charset=utf-8'),
              '/lucide.js': (ROOT / 'static/lucide.min.js', 'text/javascript; charset=utf-8'),
              '/logo-light.png': (ROOT / 'static/logo-light.png', 'image/png'),
              '/logo-dark.png': (ROOT / 'static/logo-dark.png', 'image/png')}
    class Handler(Base):
        def do_GET(self):
            if self.path in assets:
                if not self.safe_request():
                    return
                path, content_type = assets[self.path]
                data = path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; media-src blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
                self.end_headers()
                self.wfile.write(data)
            else:
                super().do_GET()
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description='OpenLips Library (trusted LAN/VPN only)')
    parser.add_argument('--config', type=Path, default=Path('/data/server.json'))
    parser.add_argument('--library', type=Path, default=Path('/data/library'))
    parser.add_argument('--bind', default=os.environ.get('OPENLIPS_BIND', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('OPENLIPS_PORT', '8765')))
    parser.add_argument('--ftp-port', type=int, default=2121)
    parser.add_argument('--local-http-test', action='store_true', help='Restrict this development instance to localhost')
    parser.add_argument('--authenticated', action='store_true', help='Keep the legacy HTTPS/pairing mode')
    args = parser.parse_args(argv)
    if args.local_http_test and args.bind != '127.0.0.1':
        parser.error('HTTP development mode requires 127.0.0.1')
    if not args.config.exists():
        create_config(args.config, args.library, args.bind, args.port, args.ftp_port,
            tls=args.authenticated and not args.local_http_test, discovery=args.bind != '127.0.0.1', lan_open=not args.authenticated)
    config = load_config(args.config)
    if not args.authenticated and not config.get('lan_open'):
        update_features(args.config, tls=False, discovery=config['bind'] != '127.0.0.1', name=config['name'], lan_open=True)
        config = load_config(args.config)
    config['allow_browser'] = True
    config['encoding_enabled'] = False
    library = Library(config['library'])
    if os.name != 'nt':
        os.chmod(args.config.parent, 0o700)
    with server_lock(library.root):
        return serve(library, config, web_handler)


if __name__ == '__main__':
    raise SystemExit(main())
