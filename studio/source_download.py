"""Inline workflow adapter for the existing isolated yt-dlp service."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from PySide6.QtCore import QObject, Signal, QStandardPaths
from studio.plugin_rpc import PluginRPC
from studio.plugin_process import relative_path


class SourceDownload(QObject):
    progress = Signal(str)
    ready = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.folder = None
        self.cancelled = False
        self.completed = False

    @property
    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def start(self, url, video=True, rights_confirmed=False):
        if self.busy:
            return
        from tools.youtube_download import youtube_url
        if not rights_confirmed:
            raise ValueError('Confirm download permission first')
        url = youtube_url(url)
        self.folder = tempfile.TemporaryDirectory(prefix='openlips-source-')
        self.root = Path(self.folder.name)
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        executable = root / 'download/OpenLipsDownload' / ('OpenLipsDownload.exe' if sys.platform == 'win32' else 'OpenLipsDownload')
        arguments = ['--serve', '--output', str(self.root)]
        if executable.is_file():
            command = [str(executable), *arguments]
        elif not getattr(sys, 'frozen', False):
            command = [sys.executable, '-m', 'tools.youtube_download', *arguments]
        else:
            self.folder.cleanup()
            raise ValueError('Download worker is missing from this installation')
        from studio.plugin_dialog import plugin_process_environment
        env = plugin_process_environment()
        self.cancelled = self.completed = False
        self.worker = PluginRPC(command, {key: env.value(key) for key in env.keys()}, self)
        self.worker.line.connect(self.receive)
        self.worker.failed.connect(self.fail)
        self.worker.finished.connect(self.cleanup)
        self.worker.start()
        self.worker.submit(dict(operation='youtube', url=url, video=video, rights_confirmed=True))

    def receive(self, line):
        if self.cancelled or self.completed:
            return
        try:
            value = json.loads(line.split(':', 1)[1])
            if 'progress' in value:
                self.progress.emit(str(value['progress'])[:2000])
            elif 'error' in value:
                self.fail(str(value['error']))
            elif 'result' in value:
                result = value['result']
                if result.get('type') != 'media':
                    raise ValueError('Unexpected download result')
                relative_path(result['path'])
                source = (self.root / result['path']).resolve(strict=True)
                source.relative_to(self.root.resolve())
                if not source.is_file() or source.stat().st_size > 8*1024**3:
                    raise ValueError('Invalid downloaded media')
                from studio.library_page import configured_library
                library = configured_library()
                base = Path(library) / 'media/imports' if library else Path(
                    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'imported-songs'
                target = base / uuid.uuid4().hex
                target.mkdir(parents=True)
                path = target / ('source' + source.suffix.lower())
                shutil.copy2(source, path)
                self.completed = True
                self.worker.requestInterruption()
                self.ready.emit(dict(path=str(path), video=bool(result['video']),
                    reference=result['reference'], metadata=result.get('metadata', {})))
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.fail(str(error))

    def fail(self, message):
        if self.cancelled or self.completed:
            return
        self.completed = True
        self.worker.requestInterruption()
        self.failed.emit(str(message)[:2000])

    def cancel(self):
        self.cancelled = True
        if self.worker:
            self.worker.requestInterruption()

    def cleanup(self):
        if self.folder:
            self.folder.cleanup()
            self.folder = None
        self.finished.emit()
