from studio.library import Library
from studio.model import StudioProject, load_project, save_project


def test_saved_metadata_refreshes_existing_entry_and_keeps_links(tmp_path):
    library = Library(tmp_path)
    identifier = library.add_project(StudioProject(title='Song', artist=''))
    library.link_remote('server', 'project', identifier, 'remote')
    with library.connect() as db:
        db.execute('INSERT INTO package_projects VALUES (?,?)', ('package', identifier))
    path = library.project_path(identifier)
    project = load_project(path)
    project.artist = 'Danny Vera'
    project.title = 'Rollercoaster'
    save_project(project, path)
    assert library.refresh_project(path, project)
    records = library.projects()
    assert len(records) == 1
    assert records[0]['id'] == identifier
    assert records[0]['artist'] == 'Danny Vera'
    assert records[0]['title'] == 'Rollercoaster'
    assert records[0]['packages'] == 1
    assert library.sync_links('server', 'project') == [(identifier, 'remote')]
    assert library.add_project(project) == identifier


def test_existing_stale_index_is_repaired_on_refresh(tmp_path):
    library = Library(tmp_path)
    identifier = library.add_project(StudioProject(title='Song', artist=''))
    path = library.project_path(identifier)
    project = load_project(path)
    project.artist = 'New artist'
    save_project(project, path)
    assert library.projects()[0]['artist'] == 'New artist'
    with library.connect() as db:
        assert db.execute('SELECT artist FROM projects WHERE id=?', (identifier,)).fetchone()[0] == 'New artist'


def test_identical_saved_versions_keep_their_ids(tmp_path):
    library = Library(tmp_path)
    first = library.add_project(StudioProject(title='Song', artist='Old'))
    second = library.add_project(StudioProject(title='Song', artist='New'))
    path = library.project_path(first)
    project = load_project(path)
    project.artist = 'New'
    save_project(project, path)
    assert library.refresh_project(path, project)
    assert {row['id'] for row in library.projects()} == {first, second}


def test_editor_save_updates_library_without_adding_version(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    library = Library(tmp_path)
    identifier = library.add_project(StudioProject(title='Song', artist=''))
    path = library.project_path(identifier)
    monkeypatch.setattr('studio.library_page.configured_library', lambda: tmp_path)
    window = StudioWindow()
    window.replace_project(load_project(path), path)
    window.artist_edit.setText('Danny Vera')
    try:
        assert window.save()
        records = library.projects()
        assert len(records) == 1
        assert records[0]['id'] == identifier
        assert records[0]['artist'] == 'Danny Vera'
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
