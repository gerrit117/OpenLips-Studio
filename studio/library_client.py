"""Anonymous LAN HTTP, optional legacy HTTPS and saved library connections."""
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
from pathlib import Path
import ssl
import tempfile
from urllib.parse import urlsplit

from studio.xbox_transfer import private_address


class LibraryClient:
    def __init__(self, url, token='', fingerprint=''):
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('Use a plain library HTTP(S) address without credentials or path')
        self.host, self.address = parsed.hostname, private_address(parsed.hostname)
        self.port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        self.tls, self.token, self.fingerprint = parsed.scheme == 'https', token, fingerprint.lower()
        self.url = f'{parsed.scheme}://{self.host}:{self.port}'

    def connect(self, inspect=False):
        if self.tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            connection = http.client.HTTPSConnection(self.address, self.port, timeout=30, context=context)
        else:
            connection = http.client.HTTPConnection(self.address, self.port, timeout=30)
        connection.connect()
        if self.tls:
            actual = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
            if inspect:
                connection.close()
                return actual
            # Certificate verification is by an explicitly trusted SHA-256 pin,
            # before sending any token, pairing code or file content.
            if len(self.fingerprint) != 64 or not hmac.compare_digest(actual, self.fingerprint):
                connection.close()
                raise ValueError('Library certificate changed or was not trusted')
        return connection

    def request(self, method, endpoint, data=None, *, target=None, expected_hash=None, expected_bytes=None):
        if not endpoint.startswith('/api/v1/') or any(c in endpoint for c in '\r\n'):
            raise ValueError('Invalid API endpoint')
        if target and expected_hash:
            cached = Path(target)
            if cached.is_file() and not cached.is_symlink() and (expected_bytes is None or cached.stat().st_size == expected_bytes):
                from tools.build_dlc import sha256
                if sha256(cached) == expected_hash:
                    return cached
        connection = self.connect()
        try:
            headers = {'Host': f'{self.address}:{self.port}'}
            if self.token:
                headers['Authorization'] = 'Bearer ' + self.token
            body = None if data is None else json.dumps(data, allow_nan=False).encode()
            if body is not None:
                headers['Content-Type'] = 'application/json'
            connection.request(method, endpoint, body, headers)
            response = connection.getresponse()
            if response.status >= 400:
                error = response.read(8192)
                try:
                    message = json.loads(error).get('error', 'Library request failed')
                except (ValueError, AttributeError):
                    message = 'Library request failed'
                raise ValueError(f'{response.status}: {message}')
            if target:
                target = Path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                size = int(response.getheader('Content-Length', '-1'))
                if not 0 <= size <= 8 * 1024 ** 3 or (expected_bytes is not None and size != expected_bytes):
                    raise ValueError('Invalid download size')
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                        temporary = Path(stream.name)
                        digest, received = hashlib.sha256(), 0
                        while chunk := response.read(65536):
                            received += len(chunk)
                            if received > size:
                                raise ValueError('Download too large')
                            digest.update(chunk)
                            stream.write(chunk)
                    if received != size or (expected_hash and digest.hexdigest() != expected_hash):
                        raise ValueError('Download integrity check failed')
                    try:
                        os.link(temporary, target)
                    except FileExistsError:
                        from tools.build_dlc import sha256
                        if sha256(target) != digest.hexdigest():
                            raise ValueError('Existing download differs; not overwritten')
                    return target
                finally:
                    if temporary:
                        temporary.unlink(missing_ok=True)
            raw = response.read(64 * 1024 * 1024 + 1)
            if len(raw) > 64 * 1024 * 1024:
                raise ValueError('Library response too large')
            return json.loads(raw)
        finally:
            connection.close()

    def upload_media(self, identifier, field, path):
        return self.upload_file(f'/api/v1/projects/{identifier}/media/{field}', path)

    def upload_file(self, endpoint, path):
        if not endpoint.startswith('/api/v1/') or any(c in endpoint for c in '\r\n'):
            raise ValueError('Invalid API endpoint')
        path = Path(path)
        connection = self.connect()
        try:
            with path.open('rb') as stream:
                connection.request('POST', endpoint, stream,
                    headers={'Host': f'{self.address}:{self.port}', 'Authorization': 'Bearer ' + self.token,
                        'Content-Length': str(path.stat().st_size), 'Content-Type': 'application/octet-stream',
                        'X-File-Name': 'media' + path.suffix.lower()})
                response = connection.getresponse()
                result = json.loads(response.read(8192))
                if response.status >= 400:
                    raise ValueError(result.get('error', 'Upload failed'))
                return result
        finally:
            connection.close()


def save_profiles(path, profiles):
    from studio.server_config import crypt
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(profiles, allow_nan=False).encode()
    if os.name == 'nt':
        raw = crypt(raw)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            if os.name != 'nt':
                os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def load_profiles(path):
    from studio.server_config import crypt
    path = Path(path)
    if not path.exists():
        return []
    if path.stat().st_size > 1024 * 1024 or (os.name != 'nt' and path.stat().st_mode & 0o077):
        raise ValueError('Unsafe library profile file')
    raw = path.read_bytes()
    if os.name == 'nt':
        raw = crypt(raw, True)
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError('Invalid library profiles')
    return value
