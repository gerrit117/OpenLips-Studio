import time
from PySide6.QtWidgets import QApplication
from studio.community_page import CommunityPage
from studio.model import demo_project
from studio.i18n import set_language


def wait(page):
    end = time.monotonic() + 5
    while page.worker and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(.005)
    QApplication.processEvents()
    assert page.worker is None


class Client:
    def __init__(self):
        self.csrf = ''
        self.calls = []
    def login(self, username, password):
        self.calls.append(('login', username))
        return {'phase':'authenticated', 'username':username}
    def songs(self, query, sort, page, mine):
        self.calls.append(('songs', query, page, mine))
        return {'songs':[{'id':1, 'title':'Synthetic', 'artist':'Author', 'album':'Test',
                         'rating':4.5, 'votes':2, 'status':'published'}], 'page':1, 'pages':1, 'total':1}
    def request(self, path, fields=None):
        self.calls.append((path, fields))
        return {'id':1, 'title':'Synthetic', 'artist':'Author', 'album':'Test', 'rating':4.5,
                'votes':2, 'status':'published', 'description':'<script>not HTML</script>',
                'comments':[{'author':'Reader', 'text':'Good chart'}], 'own_rating':3}
    def logout(self):
        return {'phase':'signed_out'}
    def clear_session(self):
        self.csrf = ''


def test_native_signin_catalog_details_rating_logout():
    app = QApplication.instance() or QApplication([])
    set_language('en', persist=False)
    client = Client()
    page = CommunityPage(demo_project, client=client)
    assert not page.library.isEnabled()
    assert not client.calls
    page.username.setText('synthetic')
    page.password.setText('test-secret')
    page.login()
    wait(page)
    assert page.authenticated and page.library.isEnabled()
    assert not page.password.text()
    assert page.table.rowCount() == 1
    page.table.selectRow(0)
    wait(page)
    assert '<script>' in page.details.toPlainText()
    assert 'Good chart' in page.details.toPlainText()
    assert page.rating.currentData() == 3
    page.rating.setCurrentIndex(4)
    page.rate()
    wait(page)
    assert ('songs/1/rate/', {'value':5}) in client.calls
    page.logout()
    wait(page)
    assert not page.authenticated and page.table.rowCount() == 0
    page.close()


def test_community_tab_preserves_unsaved_editor_and_blocks_close_during_job():
    from studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(demo_project())
    before = window.project
    window.show_community()
    assert window.workspace_tabs.currentWidget() is window.community_page
    assert window.project is before and window.dirty
    window.dirty = False
    window.close()


def test_current_project_upload_is_media_free_and_does_not_change_editor(monkeypatch):
    import copy
    from pathlib import Path
    from tools.song_bundle import decode_bundle
    app = QApplication.instance() or QApplication([])
    project = demo_project()
    before = copy.deepcopy(project)
    client = Client()
    uploaded = []
    def upload(path, rights=False):
        bundle = decode_bundle(Path(path).read_bytes())
        assert rights and bundle.manifest['metadata']['title'] == project.title
        uploaded.append(Path(path))
        return {'song': {'id':1, 'status':'pending'}}
    client.upload = upload
    monkeypatch.setattr('studio.community_page.ProjectUploadDialog.exec', lambda _: 1)
    page = CommunityPage(lambda: project, client=client)
    page.authenticated = True
    page.upload_project()
    wait(page)
    assert uploaded and not uploaded[0].exists()
    assert project == before
    assert page.status.text()
    page.close()
