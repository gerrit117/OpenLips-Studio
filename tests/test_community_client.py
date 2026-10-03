import io
import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest
from studio.community_client import CommunityClient, CommunityError, MAX_BUNDLE
from studio.exporters import export_community_song
from studio.model import demo_project


@pytest.fixture(autouse=True)
def application():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


class Response(io.BytesIO):
    def __init__(self, body, content_type='application/json', length=None):
        super().__init__(body)
        self.headers = Message()
        self.headers['Content-Type'] = content_type
        self.headers['Content-Length'] = str(len(body) if length is None else length)


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_origin_and_redirects_never_forward_credentials():
    from studio.community_client import NoRedirects
    for origin in ('http://openlips.org', 'https://attacker.invalid', 'https://openlips.org:444',
                   'https://user:password@openlips.org', 'https://openlips.org/path'):
        with pytest.raises(ValueError):
            CommunityClient(origin)
    with pytest.raises(CommunityError):
        NoRedirects().redirect_request(None, None, 302, '', {}, 'https://attacker.invalid')


def test_login_rotates_csrf_and_does_not_persist_password():
    client = CommunityClient()
    opener = Opener(Response(b'{"csrf_token":"initial"}'),
                    Response(b'{"csrf_token":"rotated","phase":"authenticated"}'))
    client.opener = opener
    assert client.login('synthetic', 'test-secret')['phase'] == 'authenticated'
    assert client.csrf == 'rotated'
    assert opener.calls[1].get_header('X-csrftoken') == 'initial'
    assert opener.calls[1].get_header('Origin') == 'https://openlips.org'
    assert 'password' not in client.__dict__
    client.clear_session()
    assert not client.csrf and not list(client.cookies)
    for path in ('/other', '../other', 'https://other.invalid'):
        with pytest.raises(ValueError):
            client.request(path)


def test_bounded_responses_and_errors():
    client = CommunityClient()
    client.opener = Opener(Response(b'<html>maintenance</html>', 'text/html'),
                           Response(b'', length=MAX_BUNDLE + 1), Response(b'[]'))
    for code in ('api_unavailable', 'too_large', 'invalid_response'):
        with pytest.raises(CommunityError) as failure:
            client.request('session/')
        assert failure.value.code == code
    client.opener = Opener(HTTPError('https://openlips.org', 503, '', {},
                                   io.BytesIO(b'{"error":"maintenance","message":"Maintenance"}')))
    with pytest.raises(CommunityError) as failure:
        client.request('songs/')
    assert failure.value.code == 'maintenance'


def test_upload_and_download_checked_bundle_and_no_overwrite(tmp_path):
    client = CommunityClient()
    client.csrf = 'synthetic'
    path = tmp_path / 'original.ols'
    project = demo_project()
    export_community_song(project, path, duration=project.duration + 2)
    body = path.read_bytes()
    client.opener = Opener(Response(b'{"song":{"id":1}}'),
                           Response(body, 'application/octet-stream'))
    with pytest.raises(CommunityError):
        client.upload(path)
    assert client.upload(path, rights=True)['song']['id'] == 1
    request = client.opener.calls[0]
    assert b'filename="song.ols"' in request.data and body in request.data
    target = tmp_path / 'download.ols'
    progress = []
    assert client.download(1, target, lambda *v: progress.append(v)) == str(target)
    assert target.read_bytes() == body
    assert progress
    with pytest.raises(FileExistsError):
        client.download(1, target)
    client.opener = Opener(Response(b'not a bundle', 'application/octet-stream'))
    rejected = tmp_path / 'rejected.ols'
    with pytest.raises(ValueError):
        client.download(2, rejected)
    assert not rejected.exists()


def test_logout_discards_local_session_even_if_server_is_unreachable():
    client = CommunityClient()
    client.csrf = 'synthetic'
    client.opener = Opener(TimeoutError())
    with pytest.raises(CommunityError):
        client.logout()
    assert not client.csrf


def test_downloaded_song_restores_notes_melisma_pages_tempo_and_offset(tmp_path, monkeypatch):
    from studio.community_import import import_community
    from studio.model import StudioProject, EditorNote
    monkeypatch.setattr('studio.community_import.QStandardPaths.writableLocation', lambda _: str(tmp_path))
    project = StudioProject(title='Synthetic', artist='Original Author', bpm=144,
                            reference_offset=.25, notes=[
        EditorNote(2, .5, 60, 'Hello', False),
        EditorNote(2.5, .5, 64, '~', True, True, 3.2),
        EditorNote(4, .75, 67, 'world', True, True)])
    path = tmp_path / 'synthetic.ols'
    export_community_song(project, path, duration=6)
    restored = import_community(path)
    assert len(restored.notes) == 3
    assert [n.pitch for n in restored.notes] == [60, 64, 67]
    assert [n.text for n in restored.notes] == ['Hello', '~', 'world']
    assert [n.end_word for n in restored.notes] == [False, True, True]
    assert restored.notes[1].line_break_after
    assert restored.notes[1].page_break_time == pytest.approx(3.2)
    assert restored.bpm == 144 and restored.reference_offset == .25
    assert restored.notes[2].length == pytest.approx(.75)
