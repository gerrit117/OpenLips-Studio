"""Synthetic removable-storage fixtures; no physical USB writes or game data."""
from datetime import datetime
import hashlib
from pathlib import Path
import pytest

from studio.usb_catalog import scan_usb, delete_package, compare_versions, UsbPackage
from studio.package_metadata import package_metadata
from tools.build_dlc import stamp_package_creation, verify_stfs, make_manifest, make_pack_manifest
from studio.model import StudioProject, EditorNote, load_project, save_project, project_status
from studio.library import Library


def package(path, *, copies=1, magic=b'LIVE'):
    base = 0xB000
    data = bytearray(base + (copies + 2) * 4096)
    data[:4] = magic
    for offset, value in ((0x340, 0xAD0E), (0x344, 2), (0x360, 0x4D530888), (0x395, 2)):
        data[offset:offset + 4] = value.to_bytes(4, 'big')
    data[0x37B] = 1 if copies == 1 else 0
    data[0x37C:0x37E] = (1).to_bytes(2, 'little')
    display = 'Test pack'.encode('utf-16-be')
    data[0x411:0x411+len(display)] = display
    table = base + copies * 4096
    data[table:table+7] = b'DLC.xml'
    data[table+0x28] = 7
    data[table+0x2F:table+0x32] = (1).to_bytes(3, 'little')
    data[table+0x32:table+0x34] = b'\xff\xff'
    xml = b'<DLCContents><MusicIndices><MusicIndex><Artist>Test</Artist><Title>Song</Title></MusicIndex></MusicIndices></DLCContents>'
    data[table+0x34:table+0x38] = len(xml).to_bytes(4, 'big')
    stamp = ((2026-1980)<<25) | (10<<21) | (9<<16) | (12<<11) | (5<<5) | 15
    data[table+0x38:table+0x3C] = stamp.to_bytes(4, 'big')
    data[table+4096:table+4096+len(xml)] = xml
    for index in range(2):
        data[base+index*24:base+index*24+20] = hashlib.sha1(data[table+index*4096:table+(index+1)*4096]).digest()
    data[0x381:0x395] = hashlib.sha1(data[base:base+4096]).digest()
    data[0x32C:0x340] = hashlib.sha1(data[0x344:base]).digest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def usb_path(root, name='ABC'):
    return root / 'Content/0000000000000000/4D530888/00000002' / name


def test_embedded_utc_date_does_not_change_assets(tmp_path):
    path = package(tmp_path/'test')
    before = path.read_bytes()[0xB000:]
    stamp_package_creation(path)
    verify_stfs(path)
    metadata = package_metadata(path)
    assert metadata['date_precision'] == 'utc'
    assert datetime.fromisoformat(metadata['package_date']).tzinfo
    assert path.read_bytes()[0xB000:] == before
    assert metadata['songs'][0]['title'] == 'Song'


def test_read_only_two_copy_con_and_pirs(tmp_path):
    for magic in (b'CON ', b'PIRS'):
        path = package(tmp_path/magic.decode().strip(), copies=2, magic=magic)
        assert package_metadata(path, read_only=True)['songs'][0]['artist'] == 'Test'
        with pytest.raises(ValueError):
            package_metadata(path)
        with pytest.raises(ValueError):
            stamp_package_creation(path)


def test_usb_inventory_and_snapshot_checked_delete(tmp_path):
    root = tmp_path/'usb'
    path = package(usb_path(root))
    ignored = package(root/'Content/0000000000000000/12345678/00000002/other')
    entries = scan_usb(root)
    assert len(entries) == 1 and entries[0].title == 'Test pack'
    assert entries[0].songs[0]['title'] == 'Song'
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='changed'):
        delete_package(root, entries[0])
    delete_package(root, scan_usb(root)[0])
    assert not path.exists() and ignored.exists()


def test_unreadable_manifest_remains_visible(tmp_path):
    path = package(usb_path(tmp_path/'usb'))
    data = bytearray(path.read_bytes())
    data[0xD000] = 0
    path.write_bytes(data)
    entries = scan_usb(tmp_path/'usb')
    assert entries[0].error and entries[0].title == 'Test pack'


def entry(date, content_id):
    return UsbPackage(Path(content_id), 'Pack', [dict(artist='Test', title='Song')],
        date, 'utc', content_id, 0, (1024,0,0,''))


def test_local_and_usb_versions_do_not_guess_unknown_dates():
    old = entry('2026-10-09T10:00:00+00:00', 'old')
    new = entry('2026-10-09T11:00:00+00:00', 'new')
    local = dict(songs=old.songs, built=new.built, precision='utc', content_id='new', bytes=1024)
    compare_versions([old, new], [local])
    assert old.local == 'newer' and old.revision == 'older'
    assert new.local == 'same' and new.revision == 'latest'
    unknown = entry(None, 'unknown')
    compare_versions([unknown], [local])
    assert unknown.local == 'different' and unknown.revision == 'unknown'


def test_project_dates_status_and_deduplication(tmp_path):
    project = StudioProject(title='Song', artist='Test', notes=[EditorNote(1,1,60,'Hello')], genre='Rock',year='1990')
    path = tmp_path/'song.olp'
    save_project(project, path)
    created = project.created_at
    library = Library(tmp_path/'library')
    identifier = library.add_project(project)
    save_project(project, path)
    assert project.created_at == created
    assert library.add_project(project) == identifier
    assert load_project(path).year == '1990'
    assert library.projects()[0]['status'] == 'needs_media'
    project.notes[0].text = ''
    assert project_status(project) == 'draft'
    assert library.add_project(project) != identifier
    assert '2026-' in library.draft_path(project).name


def test_ultrastar_metadata_and_dlc_manifest(tmp_path):
    from studio.importers import import_ultrastar
    path = tmp_path/'song.txt'
    path.write_text('#TITLE:Song\n#ARTIST:Test\n#BPM:120\n#GAP:0\n#GENRE:Rock\n#YEAR:1990\n#ALBUM:Album\n: 0 4 0 Hi\nE\n')
    project = import_ultrastar(path)
    assert (project.genre, project.year, project.album) == ('Rock','1990','Album')
    assets = dict(chart='chart', audio='audio', lyric='lyric', jacket='cover', preview_audio='preview')
    single = dict(title='Song',artist='Test',uint_id=1,duration=15,assets=assets,
                  genre=project.genre,year=project.year,album=project.album)
    from xml.etree import ElementTree as ET
    manifest = ET.fromstring(make_pack_manifest([single, dict(single, uint_id=2, assets={k:'second'+v for k,v in assets.items()})], 1))
    assert all(s.findtext('Year') == '1990' for s in manifest.findall('MusicIndices/MusicIndex'))
    assert ET.fromstring(make_manifest('Song','Test',1,15,assets)).findtext('MusicIndices/MusicIndex/Genre') == ''
