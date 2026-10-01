"""USDB Syncer hook bridge. Uses upstream login/search/downloader, not a scraper fork."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

UPSTREAM_COMMIT = 'c8f9157bed4d45fc646e5d4c4450074ef0925aae'


def report(message):
    print('OPENLIPS_PLUGIN:' + json.dumps({'message': message}), flush=True)


def export_song(song, output):
    """Snapshot the selected local song; never alter the Syncer library or headers."""
    output = Path(output).resolve()
    assets = output / 'song'
    if assets.exists():
        raise ValueError('A song has already been exported for this job')
    txt = song.txt_path()
    if not txt or not Path(txt).is_file():
        raise ValueError('Download the selected song TXT before sending it to Studio')
    sources = {'chart': Path(txt)}
    for field in ('audio', 'video', 'cover'):
        value = getattr(song, field + '_path')()
        if value and Path(value).is_file():
            sources[field] = Path(value)
    if sum(p.stat().st_size for p in sources.values()) > 8 * 1024 * 1024 * 1024:
        raise ValueError('Selected song exceeds 8 GiB')
    assets.mkdir(parents=True)
    result = dict(format='openlips-plugin-song', schema_version=1)
    try:
        for field, source in sources.items():
            name = field + source.suffix.lower()
            shutil.copy2(source, assets / name)
            result[field] = 'song/' + name
        temporary = output / 'result.json.tmp'
        temporary.write_text(json.dumps(result), encoding='utf-8')
        temporary.replace(output / 'result.json')
    except Exception:
        shutil.rmtree(assets)
        raise
    report('Selected song ready for Studio preview')
    return result


def configure(state, video=True):
    from PySide6.QtCore import QSettings
    from usdb_syncer import settings, utils
    state = Path(state).resolve()
    state.mkdir(parents=True, exist_ok=True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(state / 'settings'))
    # Isolate Syncer internals from a separately installed upstream application.
    for field in ('log', 'db', 'addons', 'licenses', 'fonts', 'license_hash', 'song_list', 'profile'):
        original = getattr(utils.AppPaths, field)
        setattr(utils.AppPaths, field, state / original.name)
    utils.AppPaths.shared = None
    settings.SYSTEM_USDB = 'OpenLips USDB Plugin/USDB'
    settings.set_song_dir(state / 'songs', temp=True)
    (state / 'songs').mkdir(exist_ok=True)
    settings.set_video(video, temp=True)
    settings.set_video_resolution(settings.VideoResolution.P720, temp=True)
    settings.set_audio_separation(False, temp=True)
    settings.set_webserver_auto_start(False, temp=True)
    settings.set_discord_allowed(False, temp=True)
    binaries = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'bin'
    if binaries.is_dir():
        os.environ['PATH'] = str(binaries) + os.pathsep + os.environ.get('PATH', '')
        settings.set_ffmpeg_dir(str(binaries), temp=True)


def attach(window, output):
    from PySide6 import QtWidgets
    from PySide6.QtCore import QTimer
    from usdb_syncer.song_loader import DownloadManager

    def send():
        selected = list(window.table.selected_songs())
        if len(selected) != 1:
            QtWidgets.QMessageBox.information(window, 'OpenLips Studio', 'Select exactly one downloaded song.')
            return
        if DownloadManager._jobs:
            QtWidgets.QMessageBox.information(window, 'OpenLips Studio', 'Wait for all downloads to finish before sending a song.')
            return
        try:
            export_song(selected[0], output)
            window.close()
        except Exception as error:
            QtWidgets.QMessageBox.warning(window, 'OpenLips Studio', str(error))

    action = window.menu_tools.addAction('Send selected song to OpenLips Studio', send)
    window.toolBar.addAction(action) if hasattr(window, 'toolBar') else None
    timer = QTimer(window)
    def cancel_if_requested():
        if (Path(output) / 'cancel.request').exists():
            timer.stop()
            # Upstream closeEvent aborts DownloadManager and waits for child cleanup.
            window.close()
    timer.timeout.connect(cancel_if_requested)
    timer.start(250)
    window.openlips_cancel_timer = timer
    return action


def launch(request, output):
    if request.get('protocol') != 1:
        raise ValueError('Unsupported plugin protocol')
    options = request.get('options', {})
    if options.get('rights_confirmed') is not True:
        raise ValueError('Confirm that you have the rights/permission to download the selected media.')
    from usdb_syncer import gui
    configure(request['state_dir'], bool(options.get('video', True)))
    from usdb_syncer.gui import hooks
    callback = lambda window: attach(window, output)
    hooks.MainWindowDidLoad.subscribe(callback)
    report('USDB Syncer opening. Sign in, download/select one song, then Tools > Send selected song to OpenLips Studio.')
    sys.argv = [sys.argv[0]]
    try:
        gui.main()
    finally:
        hooks.MainWindowDidLoad.unsubscribe(callback)
    if not (Path(output) / 'result.json').exists():
        raise ValueError('USDB Syncer closed without sending a song. The Studio project was not changed.')


def self_test(output):
    """Offline integration fixture: real upstream SongTxt/meta tags, original own words."""
    from usdb_syncer.meta_tags import MetaTags
    from usdb_syncer.logger import logger
    import yt_dlp
    import deno
    from PySide6 import QtWidgets
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    configure(output / 'state')
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    fixture = output / 'fixture.txt'
    fixture.write_text('#TITLE:OpenLips Fixture\n#ARTIST:OpenLips\n#BPM:120\n#GAP:0\n: 0 4 0 Hel\n: 4 4 2 lo \n- 8\nE\n', encoding='utf-8')
    from usdb_syncer.song_txt import SongTxt
    assert SongTxt.parse(fixture.read_text(encoding='utf-8'), logger)
    assert MetaTags.parse('v=ABCDEFGHIJK', logger).video
    class FixtureSong:
        def txt_path(self): return fixture
        def audio_path(self): return None
        def video_path(self): return None
        def cover_path(self): return None
    export_song(FixtureSong(), output)
    print('Offline USDB/yt-dlp/Qt bridge test passed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test(args.output)
        else:
            if not args.request or args.request.stat().st_size > 64 * 1024 * 1024:
                raise ValueError('Missing or oversized request')
            launch(json.loads(args.request.read_text(encoding='utf-8')), args.output)
        return 0
    except Exception as error:
        report(str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
