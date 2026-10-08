"""Ready packages are songs even if no editable project was archived."""
import json

from studio.library import Library
from studio.model import EditorNote, StudioProject


def seed_package(library, songs):
    with library.connect() as db:
        db.execute('INSERT INTO packages VALUES (?,?,?,?,?,?)',
            ('a' * 64, 'B' * 40 + '4D', 'Synthetic pack', 1024, json.dumps(songs), 0))


def test_package_only_collection_lists_each_song(tmp_path):
    library = Library(tmp_path / 'library')
    seed_package(library, [dict(artist='Artist Z', title='Second', song_id='1'),
                           dict(artist='Artist A', title='First', song_id='2')])
    assert library.projects() == []
    songs = library.songs()
    assert [s['title'] for s in songs] == ['First', 'Second']
    assert len({s['key'] for s in songs}) == 2
    assert all(s['kind'] == 'dlc' and s['song_count'] == 2 for s in songs)
    assert all(s['package_id'] == 'a' * 64 and s['filename'] == 'B' * 40 + '4D' for s in songs)
    assert len(library.packages()) == 1


def test_source_labels_and_legacy_project_compatibility(tmp_path):
    library = Library(tmp_path / 'library')
    for index, (source, kind) in enumerate([('Library OLS', 'community'),
            ('UltraStar TXT', 'ultrastar'), ('MIDI / vocals / Kanal 1', 'midi'),
            ('Library LRC', 'lrc'), ('Handmade', 'project')]):
        project = StudioProject(title=f'Song {index}', artist='OpenLips', source=source,
            notes=[EditorNote(1, .5, 60, 'Hello')])
        identifier = library.add_project(project)
        assert next(s for s in library.songs() if s['project_id'] == identifier)['kind'] == kind
    with library.connect() as db:
        db.execute('DELETE FROM project_types')
    assert all(s['kind'] == 'project' for s in library.songs())


def test_removing_project_keeps_ready_dlc_visible(tmp_path):
    library = Library(tmp_path / 'library')
    identifier = library.add_project(StudioProject(title='Draft', artist='OpenLips',
        notes=[EditorNote(1, .5, 60, 'Hello')]))
    seed_package(library, [dict(artist='OpenLips', title='Ready', song_id='1')])
    library.remove_project(identifier)
    assert [s['title'] for s in library.songs()] == ['Ready']
    with library.connect() as db:
        assert db.execute('SELECT count(*) FROM project_types').fetchone()[0] == 0
