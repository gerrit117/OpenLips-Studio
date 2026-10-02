"""Native sharing bundles, using only tiny generated charts and solid-color covers."""
import io
import unittest
from PIL import Image
from tools.build_owned_chart import build_owned_pair
from tools.write_template_chart import Note, SongChart
from tools.song_bundle import encode_bundle, decode_bundle, youtube_reference


class SongBundleTests(unittest.TestCase):
    def bundle(self, **overrides):
        chart, lyric = build_owned_pair(SongChart([Note(2, .5, 60, "Hello"), Note(3, 1, 65, "world")]), "Synthetic", "Audio/Synthetic")
        cover = io.BytesIO()
        Image.new("RGB", (256, 256), "#228877").save(cover, format="JPEG")
        options = {"metadata": {"title": "Synthetic", "artist": "Original Author", "album": "", "genre": "", "language": "English", "family": "og"}, "duration": 4}
        options.update(overrides)
        return chart, lyric, encode_bundle(chart, lyric, cover.getvalue(), **options)

    def test_roundtrip_preserves_native_bytes(self):
        chart, lyric, raw = self.bundle(youtube="https://youtu.be/abcdefghijk")
        parsed = decode_bundle(raw)
        self.assertEqual((parsed.chart, parsed.lyric), (chart, lyric))
        self.assertEqual(parsed.validation["coverage"], 100)
        self.assertEqual(parsed.manifest["media"]["reference_video"], "https://www.youtube.com/watch?v=abcdefghijk")

    def test_manifest_hash_corruption_rejected(self):
        _, _, data = self.bundle()
        bad = bytearray(data)
        bad[20] ^= 1
        with self.assertRaises(ValueError):
            decode_bundle(bad)

    def test_plain_zip_is_not_a_bundle(self):
        with self.assertRaises(ValueError):
            decode_bundle(b"PK\x03\x04not a song")

    def test_duration_required_without_reference(self):
        with self.assertRaises(ValueError):
            self.bundle(duration=None)

    def test_reference_url_is_not_an_arbitrary_fetch_target(self):
        for value in ("javascript:alert(1)", "https://youtube.com.evil.invalid/watch?v=abcdefghijk", "http://youtu.be/abcdefghijk", "https://user:pass@youtube.com/watch?v=abcdefghijk"):
            with self.assertRaises(ValueError):
                youtube_reference(value)


if __name__ == "__main__":
    unittest.main()
