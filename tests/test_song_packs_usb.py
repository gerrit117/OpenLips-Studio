"""Synthetic packs and USB storage only; never use attached physical drives."""
import copy
import hashlib
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from studio.dlc_pack import build_projects_dlc
from studio.model import EditorNote, StudioProject
from tools.build_dlc import make_pack_manifest, marketplace_filename, verify_stfs
from tools.install_dlc_usb import content_directory, install_package


def song(index, video=True):
    stem = f'song{index:02d}'
    assets = dict(chart=stem + '.X360', lyric=stem + '_Lyric.X360',
        audio=stem + '.xWMA', preview_audio=stem + '_prv.xWMA', jacket=stem + '.jpg')
    if video:
        assets['video'] = stem + '.wmv'
    return dict(title=f'Synthetic {index}', artist='Test & artist',
                uint_id=0x03000001 | (index << 28), duration=17, assets=assets)


def synthetic_package(path):
    data = bytearray(0xD000)
    data[:4] = b'LIVE'
    for offset, value in ((0x340, 0xAD0E), (0x344, 2), (0x360, 0x4D530888), (0x395, 1)):
        data[offset:offset + 4] = value.to_bytes(4, 'big')
    data[0x37B] = 1
    data[0xB000:0xB014] = hashlib.sha1(data[0xC000:]).digest()
    data[0x381:0x395] = hashlib.sha1(data[0xB000:0xC000]).digest()
    data[0x32C:0x340] = hashlib.sha1(data[0x344:0xB000]).digest()
    path.write_bytes(data)
    verify_stfs(path)
    return path


def test_pack_ids_asset_inventory_and_optional_video():
    songs = [song(0), song(1, False), song(2)]
    root = ET.fromstring(make_pack_manifest(songs, 0x03000001))
    indices = root.findall('MusicIndices/MusicIndex')
    assert len(indices) == 3
    assert len({s.findtext('UintID') for s in indices}) == 3
    assert {s.findtext('offerID') for s in indices} == {'3000001'}
    assert {s.findtext('ChartContentID') for s in indices} == {'4D53088803000001'}
    assert indices[1].findtext('VideoContentID') == '0'
    videos = root.findall('MusicVideos/MusicVideo')
    assert [v.findtext('ID') for v in videos] == ['4D53088803000001_000', '4D53088803000001_002']
    assert all(v.find('ChartID') is None for v in videos)
    assert indices[0].findtext('Artist') == 'Test & artist'
    assert ET.fromstring(make_pack_manifest([song(0, False), song(1, False)], 1)).find('MusicVideos') is None


def test_pack_duplicate_ids_and_assets_are_refused():
    with pytest.raises(ValueError, match='song ID'):
        make_pack_manifest([song(0), song(0)], 1)
    second = song(1)
    second['assets']['chart'] = 'SONG00.X360'
    with pytest.raises(ValueError, match='asset name'):
        make_pack_manifest([song(0), second], 1)


def test_pack_build_uses_distinct_media_and_matching_embedded_names(tmp_path):
    source = tmp_path / 'input.wav'
    source.write_bytes(b'synthetic source')
    projects = [StudioProject(title=f'Song {i}', artist='Test', audio_path=str(source),
        notes=[EditorNote(1, .5, 60, 'Hi')]) for i in range(2)]
    original = copy.deepcopy(projects)
    def prepare(project, directory, log):
        directory.mkdir()
        media = {}
        for key, filename in [('audio', 'song.xWMA'), ('preview_audio', 'preview.xWMA'), ('jacket', 'cover.jpg')]:
            media[key] = directory / filename
            media[key].write_bytes(key.encode())
        return media, 17
    def package(backend, files, manifest, output, display_name, **kwargs):
        from tools.walk_ixb_graph import Graph
        root = ET.fromstring(manifest)
        assert display_name == 'Test Song Pack'
        assert len(files) == 10
        for music in root.findall('MusicIndices/MusicIndex'):
            graph = Graph(files[music.findtext('ChartUri')].read_bytes())
            marker = next(r for r in graph.records if graph.is_a(r, 'ixAudioMarker'))
            info, raw = graph.vector(marker, 'm_strAudioName', 1)
            name = graph.data[raw.payload:raw.payload + info['size'] - 1].decode()
            assert name == Path(music.findtext('AudioUri')).stem
        return {'output_path': str(output / 'verified-package')}
    with patch('studio.dlc_pack.prepare_dlc_media', prepare), \
         patch('studio.dlc_pack.bundled_tool', return_value='backend'), \
         patch('studio.dlc_pack.build_package', package):
        assert build_projects_dlc(projects, tmp_path, pack_name='Test Song Pack')['output_path']
    assert projects == original
    assert source.read_bytes() == b'synthetic source'


def test_oversize_pack_refuses_publication_and_leaves_sources_unchanged(tmp_path):
    source = tmp_path / 'source.wav'
    source.write_bytes(b'source')
    project = StudioProject(title='Test', artist='Test', audio_path=str(source),
        notes=[EditorNote(1, .5, 60, 'Hi')])
    def prepare(project, directory, log):
        directory.mkdir()
        media = {}
        for key in ('audio', 'preview_audio', 'jacket'):
            path = directory / (key + '.dat')
            path.write_bytes(b'synthetic')
            media[key] = path
        return media, 17
    with patch('studio.dlc_pack.prepare_dlc_media', prepare), \
         patch('studio.dlc_pack.bundled_tool', return_value='backend'), \
         patch('studio.dlc_pack.MAX_ASSET_BYTES', 1), \
         patch('studio.dlc_pack.build_package') as publish:
        with pytest.raises(ValueError, match='2016 MiB'):
            build_projects_dlc([project, project], tmp_path, pack_name='Large Pack')
        publish.assert_not_called()
    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == b'source'


def test_verified_usb_copy_no_overwrite_and_source_preserved(tmp_path):
    source = synthetic_package(tmp_path / 'custom.LIVE')
    root = tmp_path / 'usb'
    root.mkdir()
    (root / 'Content').mkdir()
    progress = []
    target = install_package(source, root, lambda n, total: progress.append((n, total)))
    assert target.relative_to(root).parts[:4] == ('Content', '0000000000000000', '4D530888', '00000002')
    assert target.name == marketplace_filename(source)
    assert target.read_bytes() == source.read_bytes()
    assert progress[-1] == (source.stat().st_size, source.stat().st_size)
    with pytest.raises(FileExistsError):
        install_package(source, root)
    assert not list(target.parent.glob('.openlips-*'))


def test_usb_corrupt_package_no_space_and_failed_readback(tmp_path):
    source = synthetic_package(tmp_path / 'custom.LIVE')
    root = tmp_path / 'usb'
    root.mkdir()
    (root / 'Content').mkdir()
    with patch('tools.install_dlc_usb.shutil.disk_usage') as usage:
        usage.return_value.free = 0
        with pytest.raises(ValueError, match='free space'):
            install_package(source, root)
    with patch('tools.install_dlc_usb.sha256', return_value='incorrect'):
        with pytest.raises(ValueError, match='read-back'):
            install_package(source, root)
    assert not list(root.rglob('.openlips-*'))
    assert not list(root.rglob('*4D'))
    source.write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        install_package(source, root)


def test_legacy_usb_and_missing_content_are_not_written(tmp_path):
    with pytest.raises(ValueError, match='Content'):
        content_directory(tmp_path)
    legacy = tmp_path / 'Xbox360'
    legacy.mkdir()
    (legacy / 'Data0000').write_bytes(b'preserve this')
    with pytest.raises(ValueError, match='Legacy'):
        content_directory(tmp_path)
    assert (legacy / 'Data0000').read_bytes() == b'preserve this'


def test_atomic_usb_publication_refuses_racing_destination(tmp_path):
    from tools.install_dlc_usb import _publish_no_replace
    source, target = tmp_path / 'temporary', tmp_path / 'installed'
    source.write_bytes(b'new')
    target.write_bytes(b'existing')
    with pytest.raises(OSError):
        _publish_no_replace(source, target)
    assert target.read_bytes() == b'existing'
    assert source.read_bytes() == b'new'


def test_only_writable_content_volumes_are_offered(tmp_path):
    from studio.usb_dialog import xbox_volumes
    (tmp_path / 'Content').mkdir()
    class Volume:
        def __init__(self, fs, read_only=False):
            self.fs, self.read_only = fs, read_only
        def isValid(self): return True
        def isReady(self): return True
        def isReadOnly(self): return self.read_only
        def rootPath(self): return str(tmp_path)
        def fileSystemType(self): return self.fs
    good = Volume(b'FAT32')
    with patch('studio.usb_dialog.QStorageInfo.mountedVolumes',
               return_value=[Volume(b'NTFS'), Volume(b'FAT32', True), good]):
        assert xbox_volumes() == [good]


def test_pack_and_usb_dialogs_start_without_an_attached_drive():
    from PySide6.QtWidgets import QApplication
    from studio.dlc_dialog import SongPackDialog
    from studio.usb_dialog import UsbDialog
    app = QApplication.instance() or QApplication([])
    project = StudioProject(title='Test', artist='Test', notes=[EditorNote(1, 1, 60, 'Hi')])
    pack = SongPackDialog(project)
    assert pack.songs.count() == 1
    pack.build()
    assert pack.worker is None
    pack.name.setText('Synthetic Pack')
    pack.build()
    assert pack.worker is None
    pack.songs.setCurrentRow(0)
    pack.remove_project()
    assert not pack.projects
    with patch('studio.usb_dialog.xbox_volumes', return_value=[]):
        usb = UsbDialog()
        assert not usb.copy_button.isEnabled()
    pack.close()
    usb.close()
