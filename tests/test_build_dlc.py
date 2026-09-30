"""Synthetic DLC metadata, integrity and FTP tests; no game/song fixtures."""
import hashlib
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from tools.build_dlc import (asset_name, build_package, make_manifest,
                             upload_package, verify_stfs, xbox_path)


class FakeFTP:
    def __init__(self):
        self.files = {}
        self.corrupt = False

    def cwd(self, path):
        pass

    def nlst(self):
        return list(self.files)

    def storbinary(self, command, stream):
        self.files[command[5:]] = stream.read()

    def retrbinary(self, command, callback):
        callback(b'corrupted' if self.corrupt else self.files[command[5:]])

    def rename(self, old, new):
        self.files[new] = self.files.pop(old)

    def delete(self, name):
        self.files.pop(name, None)


class DLC(unittest.TestCase):
    def test_independent_hash_validation_and_damage(self):
        # One synthetic allocated block and its hash table, no real game data.
        data = bytearray(0xD000)
        data[:4] = b'LIVE'
        data[0x340:0x344] = (0xAD0E).to_bytes(4, 'big')
        data[0x344:0x348] = (2).to_bytes(4, 'big')
        data[0x360:0x364] = (0x4D530888).to_bytes(4, 'big')
        data[0x37B] = 1
        data[0x395:0x399] = (1).to_bytes(4, 'big')
        data[0xB000:0xB014] = hashlib.sha1(data[0xC000:0xD000]).digest()
        data[0x381:0x395] = hashlib.sha1(data[0xB000:0xC000]).digest()
        data[0x32C:0x340] = hashlib.sha1(data[0x344:0xB000]).digest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.LIVE'
            path.write_bytes(data)
            self.assertEqual(verify_stfs(path)['allocated_blocks'], 1)
            for offset in (0x350, 0xB000, 0xC000):
                damaged = bytearray(data)
                damaged[offset] ^= 1
                path.write_bytes(damaged)
                with self.assertRaises(ValueError):
                    verify_stfs(path)

    def test_manifest_escaped_and_identity(self):
        names = dict(chart='s.X360', lyric='s_Lyric.X360', audio='s.xWMA',
                     preview_audio='s_prv.xWMA', jacket='s.jpg', video='s.wmv')
        root = ET.fromstring(make_manifest('Test & <Song>', 'Artist', 0xCCF9001, 12, names))
        music = root.find('MusicIndices/MusicIndex')
        self.assertEqual(music.findtext('Title'), 'Test & <Song>')
        self.assertEqual(music.findtext('ChartContentID'), '4D5308880CCF9001')
        self.assertEqual(root.findtext('MusicVideos/MusicVideo/ChartID'), '4D5308880CCF9001_00')

    def test_path_and_names(self):
        self.assertEqual(xbox_path('test.LIVE'),
                         'Hdd1/Content/0000000000000000/4D530888/00000002/test.LIVE')
        for name in ('../bad', 'bad\r\n', 'x' * 41, '\u00e4', '..'):
            with self.assertRaises(ValueError):
                asset_name(name)
        with self.assertRaises(ValueError):
            xbox_path('test.LIVE', '../Content')

    def test_refuses_overwrite_before_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'existing.LIVE'
            target.write_bytes(b'existing')
            with self.assertRaises(FileExistsError):
                build_package('absent.exe', {}, b'', target, 'Test')
            self.assertEqual(target.read_bytes(), b'existing')

    def test_failed_backend_leaves_no_output_or_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.dat'
            source.write_bytes(b'synthetic source')
            output = root / 'failed.LIVE'
            with patch('tools.build_dlc.subprocess.run',
                       side_effect=subprocess.CalledProcessError(1, 'backend')):
                with self.assertRaises(subprocess.CalledProcessError):
                    build_package('missing.exe', {'source.dat': source}, b'<DLCContents/>', output, 'Test')
            self.assertFalse(output.exists())
            self.assertEqual(list(root.iterdir()), [source])
            self.assertEqual(source.read_bytes(), b'synthetic source')

    def test_upload_and_corruption_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'test.LIVE'
            source.write_bytes(b'synthetic')
            ftp = FakeFTP()
            with patch('tools.build_dlc.verify_stfs'):
                upload_package(ftp, source, xbox_path(source))
                self.assertEqual(ftp.files, {'test.LIVE': b'synthetic'})
                with self.assertRaises(FileExistsError):
                    upload_package(ftp, source, xbox_path(source))
                ftp = FakeFTP()
                ftp.corrupt = True
                with self.assertRaises(ValueError):
                    upload_package(ftp, source, xbox_path(source))
                self.assertEqual(ftp.files, {})

    @unittest.skipUnless(os.environ.get('OPENLIPS_STFS_BACKEND'), 'native backend not configured')
    def test_native_roundtrip_hash_boundaries(self):
        backend = os.environ['OPENLIPS_STFS_BACKEND']
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for size in (1, 167 * 4096, 168 * 4096, 169 * 4096,
                         170 * 4096, 171 * 4096, 1024 * 1024):
                source = tmp / 'synthetic.dat'
                source.write_bytes(b'S' * size)
                package = tmp / f'{size}.LIVE'
                report = build_package(backend, {'synthetic.dat': source}, b'<DLCContents/>', package, 'Test \u00e4')
                self.assertEqual(report['allocated_blocks'], 2 + (size + 4095) // 4096)
                self.assertEqual(report['sha256'], hashlib.sha256(package.read_bytes()).hexdigest())
                original = package.read_bytes()
                corrupt = bytearray(original)
                corrupt[-1] ^= 1
                package.write_bytes(corrupt)
                with self.assertRaises(ValueError):
                    verify_stfs(package)
                package.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
