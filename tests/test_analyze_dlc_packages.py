"""Synthetic-only read-only DLC comparison tests."""
import tempfile
from pathlib import Path
import unittest
from tools.analyze_dlc_packages import header_info, manifest_info


class ComparisonTests(unittest.TestCase):
    def test_header_fields_and_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            header = bytearray(0x400)
            header[:4] = b'LIVE'
            header[0x32C:0x340] = b'\x12' * 20
            header[0x340:0x344] = (0xAD0E).to_bytes(4, 'big')
            header[0x360:0x364] = (0x4D530888).to_bytes(4, 'big')
            header[0x22C:0x234] = b'\xff' * 8
            header[0x234:0x238] = (7).to_bytes(4, 'big')
            header[0x238:0x23C] = (1).to_bytes(4, 'big')
            path = Path(temp) / ('12' * 20 + '4D')
            path.write_bytes(header)
            result = header_info(path)
            self.assertEqual(result['title_id'], '4D530888')
            self.assertTrue(result['filename_hex42'])
            self.assertTrue(result['filename_header_hash_prefix'])
            self.assertEqual(result['licenses'][0]['bits'], 7)
            self.assertEqual(path.read_bytes(), header)

    def test_manifest_bom_and_case_insensitive_uri_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = b'\xef\xbb\xbf<DLCContents><MusicIndices><MusicIndex><AudioUri>TEST.xWMA</AudioUri><LyricUri>missing.X360</LyricUri></MusicIndex></MusicIndices></DLCContents>'
            (root / 'DLC.xml').write_bytes(raw)
            (root / 'test.xWMA').write_bytes(b'synthetic')
            result = manifest_info(root)
            self.assertTrue(result['utf8_bom'])
            self.assertEqual(result['missing_uri_files'], [dict(field='LyricUri', value='missing.X360')])
            self.assertEqual((root / 'DLC.xml').read_bytes(), raw)

    def test_short_or_unknown_header_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'unknown'
            path.write_bytes(b'not a package')
            with self.assertRaises(ValueError):
                header_info(path)


if __name__ == '__main__':
    unittest.main()
