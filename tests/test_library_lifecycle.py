import hashlib
import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from studio.library import Library
from studio.library_client import LibraryClient
from studio.library_sync import sync_library
from studio.model import StudioProject, EditorNote, load_project, save_project
from studio.server import JobManager, handler_for
from studio.server_config import create_config


def song(title='Song'):
    return StudioProject(title=title, artist='Artist', notes=[EditorNote(1,1,60,'word')])


def package(library):
    data = b'synthetic package for deletion tests'
    identifier = hashlib.sha256(data).hexdigest()
    filename = 'A'*42
    (library.root/'publish'/filename).write_bytes(data)
    with library.connect() as db:
        db.execute('INSERT INTO packages VALUES (?,?,?,?,?,?)',
                   (identifier,filename,'Pack',len(data),json.dumps([]),time.time()))
    return identifier


@pytest.fixture
def peers(tmp_path):
    local, remote = Library(tmp_path/'local'),Library(tmp_path/'remote')
    config = create_config(tmp_path/'config.json',remote.root,lan_open=True)
    config['allow_browser'] = True
    manager = JobManager(remote,config)
    from library_server.app import web_handler
    http = ThreadingHTTPServer(('127.0.0.1',0),web_handler(remote,config,manager,None))
    thread = threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    client = LibraryClient(f'http://127.0.0.1:{http.server_address[1]}')
    yield local,remote,client
    http.shutdown()
    http.server_close()
    thread.join(5)
    manager.close()


@pytest.mark.parametrize('workspace',[False,True])
def test_saves_update_identity_and_save_as_can_fork(tmp_path,workspace):
    library = Library(tmp_path/'lib')
    path = library.draft_path(song()) if workspace else tmp_path/'external.olp'
    p = song()
    save_project(p,path)
    identifier = library.save_source(p,path)
    for pitch in (61,62,63):
        p.notes[0].pitch = pitch
        p.artist = 'Corrected artist'
        save_project(p,path)
        assert library.save_source(p,path) == identifier
    assert len(library.projects()) == 1
    assert load_project(library.project_path(identifier)).notes[0].pitch == 63
    copy_path = tmp_path/'copy.olp'
    save_project(p,copy_path)
    fork = library.save_source(p,copy_path,new_copy=True)
    assert fork != identifier and len(library.projects()) == 2


def test_project_delete_removes_drafts_exports_but_keeps_shared_and_external_files(tmp_path):
    library = Library(tmp_path/'lib')
    external = tmp_path/'original.olp'
    p = song()
    media = tmp_path/'source.wav'
    media.write_bytes(b'synthetic')
    p.audio_path = str(media)
    save_project(p,external)
    identifier = library.save_source(p,external)
    draft = library.draft_path(p)
    save_project(p,draft)
    assert library.save_source(p,draft) == identifier
    export = tmp_path/'chart.ols'
    export.write_bytes(b'generated export')
    artifact = library.add_artifact(export,'chart',identifier)
    artifact_path = library.artifact_path(artifact)
    retained = Path(load_project(library.project_path(identifier)).audio_path)
    library.remove_project(identifier)
    assert not draft.exists() and not artifact_path.exists()
    assert external.exists() and media.exists() and retained.exists()
    assert library.projects() == [] and library.artifacts() == []
    assert identifier in library.deleted('projects')


def test_sync_updates_existing_projects_in_both_directions(peers):
    local,remote,client = peers
    path = local.draft_path(song())
    p = song()
    save_project(p,path)
    identifier = local.save_source(p,path)
    assert not sync_library(local,client)['errors']
    peer = remote.projects()[0]['id']
    p.notes[0].pitch = 65
    save_project(p,path)
    local.save_source(p,path)
    result = sync_library(local,client)
    assert result['uploaded'] == 1 and not result['errors']
    assert len(local.projects()) == len(remote.projects()) == 1
    assert remote.projects()[0]['id'] == peer
    assert load_project(remote.project_path(peer)).notes[0].pitch == 65
    # The older workspace file must not undo a newer remote edit on the next sync.
    edited = load_project(remote.project_path(peer))
    edited.notes[0].pitch = 67
    save_project(edited,remote.project_path(peer))
    remote.refresh_project(remote.project_path(peer),edited)
    result = sync_library(local,client)
    assert result['downloaded'] == 1 and not result['errors']
    assert load_project(local.project_path(identifier)).notes[0].pitch == 67
    assert len(local.projects()) == len(remote.projects()) == 1
    again = sync_library(local,client)
    assert again['uploaded'] == again['downloaded'] == 0 and not again['errors']


@pytest.mark.parametrize('kind',['projects','packages'])
def test_local_deletions_are_not_resurrected_and_remote_deletion_is_opt_in(peers,kind):
    local,remote,client = peers
    if kind == 'projects':
        identifier = local.add_project(song())
        assert not sync_library(local,client)['errors']
        peer = remote.projects()[0]['id']
    else:
        identifier = package(local)
        peer = package(remote)
        server_id = client.request('GET','/api/v1/identity')['server_id']
        local.link_remote(server_id,kind,identifier,peer)
    unrelated = remote.add_project(song('Unrelated'))
    (local.remove_project if kind == 'projects' else local.remove_package)(identifier)
    result = sync_library(local,client)
    assert not result['errors']
    assert peer in {r['id'] for r in (remote.projects() if kind == 'projects' else remote.packages())}
    assert identifier not in {r['id'] for r in (local.projects() if kind == 'projects' else local.packages())}
    result = sync_library(local,client,propagate_deletions=True)
    assert result['deleted'] == 1 and not result['errors']
    assert peer not in {r['id'] for r in (remote.projects() if kind == 'projects' else remote.packages())}
    assert unrelated in {r['id'] for r in remote.projects()}
    assert sync_library(local,client,propagate_deletions=True)['deleted'] == 0


def test_missing_files_do_not_become_remote_deletions(peers):
    local,remote,client = peers
    identifier = local.add_project(song())
    sync_library(local,client)
    local.project_path(identifier).unlink()
    result = sync_library(local,client,propagate_deletions=True)
    assert result['deleted'] == 0 and len(remote.projects()) == 1


def test_failed_delete_remains_pending_for_retry(peers,monkeypatch):
    local,remote,client = peers
    identifier = local.add_project(song())
    sync_library(local,client)
    local.remove_project(identifier)
    request = client.request
    def fail(method,*args,**kwargs):
        if method == 'DELETE':
            raise OSError('offline')
        return request(method,*args,**kwargs)
    monkeypatch.setattr(client,'request',fail)
    result = sync_library(local,client,propagate_deletions=True)
    assert result['errors'] and not local.projects() and len(remote.projects()) == 1
    monkeypatch.setattr(client,'request',request)
    assert sync_library(local,client,propagate_deletions=True)['deleted'] == 1


def test_remote_delete_api_removes_artifacts_and_packages(peers,tmp_path):
    _,remote,client = peers
    identifier = remote.add_project(song())
    path = tmp_path/'lyrics.lrc'
    path.write_text('[00:01]word')
    artifact = remote.add_artifact(path,'lrc',identifier)
    stored = remote.artifact_path(artifact)
    client.request('DELETE','/api/v1/artifacts/'+artifact)
    assert not stored.exists()
    dlc = package(remote)
    stored = remote.package_path(dlc)
    client.request('DELETE','/api/v1/packages/'+dlc)
    assert not stored.exists() and remote.packages() == []


def test_sync_reports_conflicting_edits_without_overwriting(peers):
    local,remote,client = peers
    identifier = local.add_project(song())
    sync_library(local,client)
    peer = remote.projects()[0]['id']
    for library,key,pitch in ((remote,peer,65),(local,identifier,67)):
        path = library.project_path(key)
        p = load_project(path)
        p.notes[0].pitch = pitch
        save_project(p,path)
        library.refresh_project(path,p)
    result = sync_library(local,client)
    assert result['errors']
    assert load_project(local.project_path(identifier)).notes[0].pitch == 67
    assert load_project(remote.project_path(peer)).notes[0].pitch == 65


def test_project_changes_invalidate_linked_package_reuse(tmp_path):
    library = Library(tmp_path/'lib')
    identifier = library.add_project(song())
    dlc = package(library)
    with library.connect() as db:
        db.execute('INSERT INTO package_revisions VALUES (?,?,?)',(dlc,identifier,library.revision(identifier)))
    assert library.package_is_current(dlc,[identifier])
    path = library.project_path(identifier)
    p = load_project(path)
    p.notes[0].pitch = 65
    save_project(p,path)
    library.refresh_project(path,p)
    assert not library.package_is_current(dlc,[identifier])


def test_deleting_one_local_copy_keeps_remote_copy_linked_to_another(peers):
    local,remote,client = peers
    first = local.add_project(song())
    second = local.add_project(song(),force_new=True)
    assert not sync_library(local,client)['errors']
    assert len(remote.projects()) == 1
    peer = remote.projects()[0]['id']
    local.remove_project(first)
    result = sync_library(local,client,propagate_deletions=True)
    assert not result['errors'] and result['deleted'] == 0
    assert {row['id'] for row in remote.projects()} == {peer}
    assert {row['id'] for row in local.projects()} == {second}


def test_editing_a_saved_copy_does_not_overwrite_other_copy_during_sync(peers):
    local,remote,client = peers
    first = local.add_project(song())
    second = local.add_project(song(),force_new=True)
    assert not sync_library(local,client)['errors']
    path = local.project_path(second)
    p = load_project(path)
    p.notes[0].pitch = 67
    save_project(p,path)
    local.refresh_project(path,p)
    result = sync_library(local,client)
    assert not result['errors']
    assert len(remote.projects()) == 2
    assert load_project(local.project_path(first)).notes[0].pitch == 60
    assert load_project(local.project_path(second)).notes[0].pitch == 67
    assert not sync_library(local,client)['errors']
    assert load_project(local.project_path(first)).notes[0].pitch == 60


def test_legacy_workspace_binding_uses_existing_content_before_edit(tmp_path):
    library = Library(tmp_path/'lib')
    p = song()
    identifier = library.add_project(p)
    path = library.draft_path(p)
    save_project(p,path)
    assert library.bind_source(load_project(path),path) == identifier
    p.notes[0].pitch = 67
    save_project(p,path)
    assert library.save_source(p,path) == identifier
    assert len(library.projects()) == 1


def test_legacy_binding_does_not_guess_from_song_title(tmp_path):
    library = Library(tmp_path/'lib')
    p = song()
    library.add_project(p)
    p.notes[0].pitch = 67
    path = library.draft_path(p)
    save_project(p,path)
    assert library.bind_source(p,path) is None


def test_web_metadata_edits_sync_into_existing_local_project(peers):
    local,remote,client = peers
    identifier = local.add_project(song())
    sync_library(local,client)
    peer = remote.projects()[0]['id']
    result = client.request('POST','/api/v1/projects/'+peer,{'artist':'Corrected artist'})
    assert result['id'] == peer
    result = sync_library(local,client)
    assert not result['errors'] and result['downloaded'] == 1
    assert local.projects()[0]['id'] == identifier
    assert load_project(local.project_path(identifier)).artist == 'Corrected artist'
