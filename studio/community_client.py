"""Bounded HTTPS community transport. Sessions live only in memory."""
from http.cookiejar import CookieJar
import json
from pathlib import Path
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request

from tools.song_bundle import MAX_BUNDLE, decode_bundle

BASE_URL = 'https://openlips.org'
API = '/api/studio/v1/'
MAX_JSON = 1024 * 1024


class CommunityError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CommunityError('redirect', 'The community endpoint redirected unexpectedly.')


class CommunityClient:
    def __init__(self, base_url=BASE_URL, *, allow_local_test=False):
        parsed = urlparse(base_url)
        local = allow_local_test and parsed.hostname in ('127.0.0.1', 'localhost')
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('Invalid community origin')
        if not local and (parsed.scheme != 'https' or parsed.hostname != 'openlips.org' or parsed.port not in (None, 443)):
            raise ValueError('Only the official HTTPS community endpoint is supported')
        self.base_url = base_url.rstrip('/')
        self.cookies = CookieJar()
        self.opener = build_opener(NoRedirects(), HTTPCookieProcessor(self.cookies))
        self.csrf = ''

    def clear_session(self):
        self.cookies.clear()
        self.csrf = ''

    def request(self, path, fields=None, *, raw=False, payload=None, content_type=None, progress=None):
        if path.startswith('/') or '..' in path or '://' in path:
            raise ValueError('Invalid API path')
        headers = {'Accept': 'application/octet-stream' if raw else 'application/json',
                   'User-Agent': 'OpenLips-Studio', 'Origin': self.base_url,
                   'Referer': self.base_url + '/'}
        data = payload
        if fields is not None:
            data = urlencode(fields).encode('utf-8')
            content_type = 'application/x-www-form-urlencoded'
        if data is not None:
            if not self.csrf:
                raise CommunityError('login_required', 'Sign in to OpenLips.')
            headers['X-CSRFToken'] = self.csrf
            headers['Content-Type'] = content_type
        request = Request(self.base_url + API + path, data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                limit = MAX_BUNDLE if raw else MAX_JSON
                declared = int(response.headers.get('Content-Length', '0'))
                if declared > limit:
                    raise CommunityError('too_large', 'The server response exceeds the supported size.')
                if not raw and response.headers.get_content_type() != 'application/json':
                    raise CommunityError('api_unavailable', 'The community API is not available yet.')
                parts, total = [], 0
                while chunk := response.read(min(65536, limit + 1 - total)):
                    parts.append(chunk)
                    total += len(chunk)
                    if total > limit:
                        raise CommunityError('too_large', 'The server response exceeds the supported size.')
                    if progress:
                        progress(total, declared)
                body = b''.join(parts)
        except HTTPError as exc:
            try:
                result = json.loads(exc.read(MAX_JSON + 1))
                code = result.get('error', 'request_failed')
                message = result.get('message', 'The community request failed.')
            except (ValueError, AttributeError):
                code = {401:'login_required', 403:'access_denied', 404:'api_unavailable', 429:'rate_limited', 503:'maintenance'}.get(exc.code, 'request_failed')
                message = 'The community request failed.'
            raise CommunityError(str(code)[:80], str(message)[:500]) from None
        except (URLError, TimeoutError, OSError):
            raise CommunityError('connection_failed', 'Could not connect to the community. Check your connection and try again.') from None
        if raw:
            return body
        try:
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError()
        except ValueError:
            raise CommunityError('invalid_response', 'The community returned an invalid response.') from None
        if isinstance(result.get('csrf_token'), str):
            self.csrf = result['csrf_token']
        return result

    def login(self, username, password):
        self.request('session/')
        return self.request('login/', {'username': username, 'password': password})

    def logout(self):
        try:
            return self.request('logout/', {})
        finally:
            self.clear_session()

    def songs(self, query='', sort='artist', page=1, mine=False):
        return self.request('songs/?' + urlencode({'q': query, 'sort': sort, 'page': page, 'mine': '1' if mine else '0'}))

    def upload(self, path, *, rights=False, description=''):
        if not rights:
            raise CommunityError('rights_required', 'Confirm you may share all included content.')
        path = Path(path)
        if path.suffix.lower() != '.ols' or path.stat().st_size > MAX_BUNDLE:
            raise CommunityError('invalid_bundle', 'Choose a supported .ols song.')
        body = path.read_bytes()
        decode_bundle(body)
        boundary = 'OpenLips' + secrets.token_hex(24)
        payload = b''
        for name, value in (('rights', '1'), ('description', description)):
            payload += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode('utf-8')
        payload += (f'--{boundary}\r\nContent-Disposition: form-data; name="archive"; filename="song.ols"\r\nContent-Type: application/octet-stream\r\n\r\n').encode('ascii')
        payload += body + f'\r\n--{boundary}--\r\n'.encode('ascii')
        return self.request('upload/', payload=payload, content_type='multipart/form-data; boundary=' + boundary)

    def download(self, song_id, destination, progress=None):
        if not isinstance(song_id, int) or song_id <= 0:
            raise ValueError('Invalid song ID')
        destination = Path(destination)
        if destination.suffix.lower() != '.ols':
            raise ValueError('Downloads must use .ols')
        if destination.exists():
            raise FileExistsError('Choose a new file; existing songs are not overwritten')
        body = self.request(f'songs/{song_id}/download/', raw=True, progress=progress)
        decode_bundle(body)
        created = False
        try:
            with destination.open('xb') as stream:
                created = True
                stream.write(body)
        except Exception:
            if created:
                destination.unlink(missing_ok=True)
            raise
        return str(destination)
