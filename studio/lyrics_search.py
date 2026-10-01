"""Optional public LRCLIB lookup, performed only on explicit user request."""
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, Signal


def search_lyrics(title, artist):
    query = urlencode({'track_name': title, 'artist_name': artist})
    request = Request('https://lrclib.net/api/search?' + query,
                      headers={'User-Agent': 'OpenLips-Studio/0.1.0-beta'})
    with urlopen(request, timeout=15) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError('Lyrics search response too large')
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise ValueError('Unexpected lyrics search response')
    return [r for r in rows if isinstance(r, dict) and isinstance(r.get('plainLyrics'), str)][:30]


class LyricsSearch(QThread):
    results = Signal(list)
    failed = Signal(str)

    def __init__(self, title, artist, parent=None):
        super().__init__(parent)
        self.title, self.artist = title, artist

    def run(self):
        try:
            self.results.emit(search_lyrics(self.title, self.artist))
        except Exception as exc:
            self.failed.emit(str(exc))
