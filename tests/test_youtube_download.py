import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools.youtube_download import youtube_url, download
from studio.plugin_process import validate_manifest, load_process_plugin


@pytest.mark.parametrize('source', [
    'ABCDEFGHIJK', 'v=ABCDEFGHIJK', 'v=ABCDEFGHIJK,a=ABCDEFGHIJK',
    'https://youtu.be/ABCDEFGHIJK', 'https://www.youtube.com/watch?v=ABCDEFGHIJK&t=15',
    'https://www.youtube.com/shorts/ABCDEFGHIJK',
])
def test_reference_video_forms(source):
    assert youtube_url(source) == 'https://www.youtube.com/watch?v=ABCDEFGHIJK'


@pytest.mark.parametrize('source', ['video.mp4', 'file:///video',
    'https://evil.test/watch?v=ABCDEFGHIJK', 'https://youtube.com.evil.test/watch?v=ABCDEFGHIJK',
    'https://www.youtube.com/playlist?list=ABCDEFGHIJK'])
def test_unsafe_or_non_video_reference_rejected(source):
    with pytest.raises(ValueError):
        youtube_url(source)


def test_download_requires_permission_before_network(tmp_path):
    with pytest.raises(ValueError, match='permission'):
        download({'url': 'ABCDEFGHIJK'}, tmp_path, Mock())


def test_download_uses_bundled_tools_and_no_playlist(tmp_path, monkeypatch):
    import yt_dlp
    import deno
    from tools import youtube_download
    monkeypatch.setattr('studio.media.ffmpeg_encoder', lambda: 'bundled/ffmpeg.exe')
    monkeypatch.setattr(deno, 'find_deno_bin', lambda: 'bundled/deno.exe')
    options = {}
    class Downloader:
        def __init__(self, values): options.update(values)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            (tmp_path / 'media/source.mkv').write_bytes(b'synthetic-media')
            options['progress_hooks'][0]({'status': 'finished'})
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', Downloader)
    result = youtube_download.download({'url': 'ABCDEFGHIJK', 'rights_confirmed': True}, tmp_path, Mock())
    assert result['path'] == 'media/source.mkv'
    assert options['noplaylist'] is True
    assert '[height<=720]' in options['format']
    assert options['ffmpeg_location'] == 'bundled/ffmpeg.exe'
    assert options['js_runtimes']['deno']['path']


def test_ui_contributions_are_validated_and_not_executed():
    path = Path(__file__).resolve().parents[1] / 'plugins/usdb_downloader/openlips-plugin.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    plugin = load_process_plugin(path.parent, manifest)
    assert [a['view'] for a in plugin.ui_actions] == ['usdb-browser', 'media-download']
    manifest['ui_actions'][0]['view'] = 'arbitrary-python'
    with pytest.raises(ValueError, match='UI action'):
        validate_manifest(manifest)
