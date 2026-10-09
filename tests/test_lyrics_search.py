"""LRC searches retain HTTPS verification in packaged installations."""
import io
import json
import ssl

import certifi
import pytest

from studio import lyrics_search


def test_search_adds_bundled_ca_to_system_trust(monkeypatch):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    loaded = []
    original = context.load_verify_locations

    def load(**kwargs):
        loaded.append(kwargs['cafile'])
        original(**kwargs)

    monkeypatch.setattr(lyrics_search.ssl, 'create_default_context', lambda: context)
    monkeypatch.setattr(context, 'load_verify_locations', load)

    def open_request(request, *, timeout, context):
        assert request.full_url.startswith('https://lrclib.net/api/search?')
        assert 'track_name=A%26B' in request.full_url
        assert timeout == 15
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname
        assert context.cert_store_stats()['x509_ca'] > 0
        return io.BytesIO(json.dumps([
            {'syncedLyrics': '[00:01.00]Hello'}, {'id': 2}]).encode())

    monkeypatch.setattr(lyrics_search, 'urlopen', open_request)
    assert lyrics_search.search_lyrics('A&B', 'Artist') == [
        {'syncedLyrics': '[00:01.00]Hello'}]
    assert loaded == [certifi.where()]


def test_invalid_certificate_is_not_retried_without_verification(monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(kwargs['context'])
        raise ssl.SSLCertVerificationError('invalid certificate')

    monkeypatch.setattr(lyrics_search, 'urlopen', fail)
    with pytest.raises(ssl.SSLCertVerificationError):
        lyrics_search.search_lyrics('Example', 'Artist')
    assert len(calls) == 1
    assert calls[0].verify_mode == ssl.CERT_REQUIRED
    assert calls[0].check_hostname


def test_search_response_limit_is_preserved(monkeypatch):
    monkeypatch.setattr(lyrics_search, 'urlopen', lambda *a, **k:
                        io.BytesIO(b' ' * (2 * 1024 * 1024 + 1)))
    with pytest.raises(ValueError, match='too large'):
        lyrics_search.search_lyrics('Example', 'Artist')
