"""Headless plugin service; Studio owns the UI, upstream owns USDB downloads."""
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse, parse_qs


def youtube_url(value):
    value = value.strip()
    if value.startswith('v='):
        value = value[2:].split(',')[0].split('&')[0]
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        return 'https://www.youtube.com/watch?v=' + value
    parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.hostname not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
        raise ValueError('Enter a YouTube URL or video ID')
    video_id = parsed.path.strip('/') if parsed.hostname == 'youtu.be' else parse_qs(parsed.query).get('v', [''])[0]
    if not video_id and parsed.path.startswith(('/shorts/', '/embed/')):
        video_id = parsed.path.split('/')[2]
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise ValueError('Invalid YouTube video ID')
    return 'https://www.youtube.com/watch?v=' + video_id


class Service:
    def __init__(self, output, state, progress):
        from PySide6.QtCore import QCoreApplication
        self.app = QCoreApplication.instance() or QCoreApplication([])
        from worker import configure
        from usdb_syncer import db, utils
        configure(state)
        utils.AppPaths.make_dirs()
        db.connect(utils.AppPaths.db)
        self.output, self.progress = Path(output), progress
        self.songs = {}
        self.user = None

    def handle(self, request):
        from usdb_syncer import usdb_scraper as scraper
        operation = request['operation']
        if operation == 'login':
            import requests
            session = requests.Session()
            if not scraper.login_to_usdb(session, request['username'], request['password']):
                session.close()
                raise ValueError('USDB login failed')
            user = scraper.get_logged_in_usdb_user(session)
            if not user:
                session.close()
                raise ValueError('USDB did not confirm the login')
            scraper.SessionManager.reset_session()
            scraper.SessionManager._session = session
            scraper.SessionManager._user = user
            self.user = user
            return {'username': user.name}
        if operation == 'search':
            if not self.user:
                raise ValueError('Sign in to USDB first')
            offset = max(0, int(request.get('offset', 0)))
            self.progress('Searching USDB')
            page = scraper.get_usdb_page('index.php', scraper.RequestMethod.POST,
                params={'link': 'list'}, session=scraper.SessionManager.session(),
                payload={'order': 'interpret', 'ud': 'asc', 'limit': '100', 'details': '1',
                         'start': str(offset), 'interpret': request.get('artist', ''),
                         'title': request.get('query', ''), 'newsearch': '1'})
            matches = list(scraper._parse_songs_from_songlist(page))
            self.songs.update({int(s.song_id): s for s in matches})
            return {'total': offset + len(matches), 'has_more': len(matches) == 100,
                    'songs': [dict(id=int(s.song_id), artist=s.artist,
                    title=s.title, language=s.language) for s in matches]}
        if operation in ('download', 'download_batch', 'youtube') and request.get('rights_confirmed') is not True:
            raise ValueError('Confirm download permission first')
        if operation == 'download_batch':
            ids = request.get('song_ids', [])
            if not isinstance(ids, list) or not 1 <= len(ids) <= 16 or len(set(ids)) != len(ids):
                raise ValueError('Select between 1 and 16 different songs per pack')
            base = self.output
            paths = []
            try:
                for index, song_id in enumerate(ids):
                    self.progress(f'Downloading song {index + 1}/{len(ids)}')
                    self.output = base / f'item-{index:03d}'
                    self.output.mkdir()
                    self.handle(dict(operation='download', song_id=song_id,
                        rights_confirmed=True, video=request.get('video', True)))
                    paths.append(self.output.relative_to(base).as_posix())
            finally:
                self.output = base
            return {'type': 'songs', 'paths': paths}
        if operation == 'download':
            from usdb_syncer import download_options, settings
            from usdb_syncer.song_loader import _SongLoader
            from worker import export_song
            if not self.user or not self.songs:
                raise ValueError('Search USDB before downloading')
            song = self.songs.get(int(request['song_id']))
            if not song:
                raise ValueError('Song not found in loaded catalogue')
            settings.set_video(bool(request.get('video', True)), temp=True)
            settings.set_audio(True, temp=True)
            settings.set_cover(True, temp=True)
            song.upsert()
            loader = _SongLoader(song, download_options.download_options())
            self.progress('Downloading song and media')
            song = loader._run_inner()
            self.app.processEvents()
            export_song(song, self.output)
            return {'type': 'song'}
        if operation == 'youtube':
            return self.download_youtube(request)
        raise ValueError('Unsupported plugin operation')

    def download_youtube(self, request):
        import yt_dlp
        from usdb_syncer import settings
        url = youtube_url(request['url'])
        folder = self.output / 'media'
        folder.mkdir(exist_ok=True)
        video = bool(request.get('video', True))
        def progress(data):
            if data['status'] == 'downloading':
                total = data.get('total_bytes') or data.get('total_bytes_estimate')
                percent = round(data.get('downloaded_bytes', 0) / total * 100) if total else 0
                self.progress(f'Download: {percent}%')
            elif data['status'] == 'finished':
                self.progress('Processing downloaded media')
        options = dict(outtmpl=str(folder / 'source.%(ext)s'), noplaylist=True,
            ffmpeg_location=settings.get_ffmpeg_dir(), quiet=True, no_warnings=True, noprogress=True,
            progress_hooks=[progress], socket_timeout=30,
            format='bestvideo[height<=720]+bestaudio/best[height<=720]' if video else 'bestaudio/best',
            merge_output_format='mkv', max_filesize=8 * 1024 ** 3)
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.extract_info(url, download=True)
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() not in
                 ('.part', '.ytdl', '.json') and not re.search(r'\.f\d+\.', p.name)]
        if len(files) != 1:
            raise ValueError('Download did not produce one complete media file')
        return {'type': 'media', 'path': files[0].relative_to(self.output).as_posix(),
                'video': video, 'reference': url}


def serve(output, state):
    def emit(value):
        print('OPENLIPS_RPC:' + json.dumps(value, ensure_ascii=True), flush=True)
    service = Service(output, state, lambda message: emit({'progress': message}))
    for line in sys.stdin:
        try:
            if len(line) > 65536:
                raise ValueError('Request too large')
            request = json.loads(line)
            result = service.handle(request)
            emit({'result': result})
        except Exception as error:
            # Never echo requests: they may contain account passwords.
            emit({'error': (str(error) or type(error).__name__)[:2000]})
