"""Native Studio views backed by an isolated downloader plugin over JSON pipes."""
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from PySide6.QtCore import QStandardPaths, Signal, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QCheckBox, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QWidget)

from studio.i18n import tr
from studio.plugin_dialog import plugin_process_environment
from studio.plugin_process import relative_path


class PluginDownloadDialog(QDialog):
    accepted_song = Signal(object)
    accepted_media = Signal(object)

    def __init__(self, plugin, view, project, parent=None, automatic=False):
        super().__init__(parent)
        self.plugin, self.view, self.project = plugin, view, project
        self.setWindowTitle(tr('download.youtube') if view == 'media-download' else tr('download.usdb'))
        self.resize(760, 530 if view == 'usdb-browser' else 260)
        self.folder = tempfile.TemporaryDirectory(prefix='openlips-download-')
        self.root = Path(self.folder.name)
        self.running, self.request = False, None
        self.songs, self.page = [], 0
        self.batch_result = None
        layout = QVBoxLayout(self)
        self.form = QFormLayout()
        self.username, self.password = QLineEdit(), QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.login = QPushButton(tr('download.login'))
        if view == 'usdb-browser':
            self.form.addRow(tr('download.username'), self.username)
            self.form.addRow(tr('download.password'), self.password)
            self.form.addRow(self.login)
            self.login.clicked.connect(lambda: self.send({'operation': 'login',
                'username': self.username.text(), 'password': self.password.text()}))
        self.query = QLineEdit(project.video_reference if view == 'media-download' else '')
        self.artist = QLineEdit()
        self.query.setMaxLength(8192)
        if view == 'usdb-browser':
            self.form.addRow(tr('Interpret'), self.artist)
        self.form.addRow(tr('download.url') if view == 'media-download' else tr('Titel'), self.query)
        layout.addLayout(self.form)
        self.search = QPushButton(tr('download.search'))
        self.previous, self.next = QPushButton(tr('download.previous')), QPushButton(tr('download.next'))
        self.table = QTableWidget(0, 3)
        if view == 'usdb-browser':
            row = QHBoxLayout()
            for button in (self.search, self.previous, self.next): row.addWidget(button)
            layout.addLayout(row)
            self.search.clicked.connect(lambda: self.find(0))
            self.previous.clicked.connect(lambda: self.find(max(0, self.page - 100)))
            self.next.clicked.connect(lambda: self.find(self.page + 100))
            self.query.returnPressed.connect(lambda: self.find(0))
            self.table.setHorizontalHeaderLabels([tr('Interpret'), tr('Titel'), tr('ui.language')])
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
            self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            layout.addWidget(self.table)
        self.export_pack = QCheckBox(tr('download.export_pack'))
        self.export_pack.setChecked(True)
        self.pack_name = QLineEdit('USDB Song Pack')
        if view == 'usdb-browser':
            layout.addWidget(self.export_pack)
            form = QFormLayout()
            form.addRow(tr('pack.name'), self.pack_name)
            layout.addLayout(form)
        self.video = QCheckBox(tr('Download video (max. 720p)'))
        self.video.setChecked(True)
        self.rights = QCheckBox(tr('I have the rights/permission to download the selected media'))
        layout.addWidget(self.video)
        layout.addWidget(self.rights)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.download = QPushButton(tr('download.start'))
        self.close_button = QPushButton(tr('Abbrechen'))
        row.addStretch()
        row.addWidget(self.download)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.download.clicked.connect(self.download_selected)
        self.close_button.clicked.connect(self.reject)
        state = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'plugin-state' / plugin.id
        state.mkdir(parents=True, exist_ok=True)
        command = plugin.create_command(self.root / 'unused.json', self.root)
        arguments = command if plugin.id == 'studio-youtube' else [command[0],
            '--serve', '--output', str(self.root), '--state', str(state)]
        from studio.plugin_rpc import PluginRPC
        env = plugin_process_environment()
        self.process = PluginRPC(arguments, {key: env.value(key) for key in env.keys()}, self)
        self.process.line.connect(self.read_line)
        self.process.failed.connect(self.failed)
        self.process.start()
        if automatic:
            self.rights.setChecked(True)
            QTimer.singleShot(0, self.download_selected)

    def send(self, request):
        if self.running:
            return
        self.request = request
        self.operation = request['operation']
        self.running = True
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText(tr('download.working'))
        self.set_controls(False)
        self.flush_request()

    def flush_request(self):
        if self.request:
            self.process.submit(self.request)
            self.request = None
            self.password.clear()

    def set_controls(self, enabled):
        for widget in (self.query, self.artist, self.username, self.password, self.login, self.search,
                       self.previous, self.next, self.download, self.video, self.rights, self.table):
            widget.setEnabled(enabled)

    def find(self, page):
        self.page = page
        self.send({'operation': 'search', 'query': self.query.text(), 'artist': self.artist.text(), 'offset': page})

    def download_selected(self):
        if not self.rights.isChecked():
            self.status.setText(tr('download.confirm_rights'))
            return
        request = {'operation': 'youtube' if self.view == 'media-download' else 'download',
                   'rights_confirmed': True, 'video': self.video.isChecked()}
        if self.view == 'media-download':
            request['url'] = self.query.text()
        else:
            rows = sorted({item.row() for item in self.table.selectedItems()})
            if not rows:
                self.status.setText(tr('download.select_song'))
                return
            if len(rows) > 16:
                self.status.setText(tr('pack.count_limit'))
                return
            request['operation'] = 'download_batch'
            request['song_ids'] = [self.songs[row]['id'] for row in rows]
        self.send(request)

    def read_line(self, line):
        try:
            value = json.loads(line.split(':', 1)[1])
            if 'progress' in value:
                self.status.setText(str(value['progress'])[:2000])
            elif 'error' in value:
                self.failed(value['error'])
            elif 'result' in value:
                self.receive(value['result'])
        except (ValueError, KeyError, OSError, TypeError, StopIteration) as error:
            self.failed(str(error))

    def failed(self, message):
        self.running = False
        self.request = None
        self.progress.hide()
        self.status.setText(str(message)[:2000])
        self.set_controls(True)

    def receive(self, result):
        self.running = False
        self.progress.hide()
        self.set_controls(True)
        if self.operation == 'login':
            self.status.setText(tr('download.signed_in', username=result['username']))
        elif self.operation == 'search':
            self.songs = result['songs']
            self.table.setRowCount(len(self.songs))
            for row, song in enumerate(self.songs):
                for column, key in enumerate(('artist', 'title', 'language')):
                    self.table.setItem(row, column, QTableWidgetItem(str(song[key])))
            self.previous.setEnabled(self.page > 0)
            self.next.setEnabled(result.get('has_more', False))
            self.status.setText(tr('download.results', count=result['total']))
        elif result.get('type') == 'songs':
            from studio.plugin_song_import import SongImport
            from studio.model import save_project
            projects = []
            paths = result['paths']
            if not isinstance(paths, list) or not 1 <= len(paths) <= 16:
                raise ValueError('Invalid batch result')
            for value in paths:
                relative_path(value)
                folder = (self.root / value).resolve(strict=True)
                folder.relative_to(self.root.resolve())
                project = SongImport(folder).adopt(self.media_root())
                media = project.video_path or project.audio_path or project.cover_path
                if media:
                    save_project(project, Path(media).parent / 'song.olp')
                projects.append(project)
            self.batch_result = (projects, self.pack_name.text().strip() or 'USDB Song Pack', self.export_pack.isChecked())
            self.accept()
        elif result.get('type') == 'song':
            from studio.plugin_song_import import SongImport
            song = SongImport(self.root).adopt(self.media_root())
            self.accepted_song.emit(song)
            self.accept()
        elif result.get('type') == 'media':
            relative_path(result['path'])
            source = (self.root / result['path']).resolve(strict=True)
            source.relative_to(self.root.resolve())
            if not source.is_file() or source.stat().st_size > 8 * 1024 ** 3:
                raise ValueError('Invalid downloaded media')
            target = self.media_root() / uuid.uuid4().hex
            target.mkdir(parents=True)
            destination = target / ('source' + source.suffix.lower())
            shutil.copy2(source, destination)
            self.accepted_media.emit(dict(path=str(destination), video=result['video'], reference=result['reference']))
            self.accept()

    def media_root(self):
        return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'imported-songs'

    def done(self, result):
        self.running = False
        self.process.stop()
        self.folder.cleanup()
        super().done(result)
