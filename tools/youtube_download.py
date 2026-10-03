"""Built-in media download service; no account secrets or browser cookies stored."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse, parse_qs


def youtube_url(value):
    value = value.strip()
    tag = re.search(r'(?:^|[,;\s])v=([A-Za-z0-9_-]{11})(?:$|[,;&\s])', value)
    if tag:
        value = tag[1]
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


def download(request, output, progress):
    if request.get('rights_confirmed') is not True:
        raise ValueError('Confirm download permission first')
    import yt_dlp
    from studio.media import ffmpeg_encoder
    url = youtube_url(request['url'])
    folder = Path(output) / 'media'
    folder.mkdir(exist_ok=True)
    video = bool(request.get('video', True))
    def update(data):
        if data['status'] == 'downloading':
            total = data.get('total_bytes') or data.get('total_bytes_estimate')
            percent = round(data.get('downloaded_bytes', 0) / total * 100) if total else 0
            progress(f'Download: {percent}%')
        elif data['status'] == 'finished':
            progress('Processing downloaded media')
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    deno = root / 'bin' / ('deno.exe' if os.name == 'nt' else 'deno')
    if not deno.is_file():
        import deno as deno_package
        deno = Path(deno_package.find_deno_bin())
    options = dict(outtmpl=str(folder / 'source.%(ext)s'), noplaylist=True,
        ffmpeg_location=ffmpeg_encoder(), quiet=True, no_warnings=True, noprogress=True,
        progress_hooks=[update], socket_timeout=30, js_runtimes={'deno': {'path': str(deno)}},
        format='bestvideo[height<=720]+bestaudio/best[height<=720]' if video else 'bestaudio/best',
        merge_output_format='mkv', max_filesize=8 * 1024 ** 3)
    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.extract_info(url, download=True)
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() not in
             ('.part', '.ytdl', '.json') and not re.search(r'\.f\d+\.', p.name)]
    if len(files) != 1:
        raise ValueError('Download did not produce one complete media file')
    return {'type': 'media', 'path': files[0].relative_to(output).as_posix(),
            'video': video, 'reference': url}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state')
    args = parser.parse_args()
    def emit(value):
        print('OPENLIPS_RPC:' + json.dumps(value, ensure_ascii=True), flush=True)
    for line in sys.stdin:
        try:
            if len(line) > 65536:
                raise ValueError('Request too large')
            request = json.loads(line)
            if request['operation'] != 'youtube':
                raise ValueError('Unsupported downloader operation')
            result = download(request, args.output, lambda message: emit({'progress': message}))
            emit({'result': result})
        except Exception as error:
            emit({'error': str(error)[:2000]})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
