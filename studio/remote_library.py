"""Studio workspace for automatically discovered home-network libraries."""
import copy
import json
from pathlib import Path
import re
import socket

from PySide6.QtCore import Qt, Signal, QTimer, QSettings
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit,
    QPushButton, QLabel, QTreeWidget, QTreeWidgetItem, QInputDialog, QMessageBox, QFileDialog, QCheckBox, QMenu)
import qtawesome as qta

from studio.i18n import tr
from studio.library import default_library_root
from studio.library_page import LibraryTask
from studio.library_client import LibraryClient, load_profiles, save_profiles
from studio.model import StudioProject, save_project


class RemoteLibraryPage(QWidget):
    project_opened = Signal(str)
    community_upload_requested = Signal(object)
    def __init__(self, project_getter, parent=None, *, library_getter=None):
        super().__init__(parent)
        self.get_project = project_getter
        self.get_library = library_getter
        self.worker = self.client = None
        self.scanned = False
        self.profile_path = default_library_root().parent / 'library-connections.bin'
        self.profiles = load_profiles(self.profile_path)
        self.catalog = {}
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.connections = QComboBox()
        for profile in self.profiles:
            self.connections.addItem(profile['name'], profile)
        row.addWidget(self.connections, 1)
        self.connect_button = QPushButton(qta.icon('fa5s.link', color='#cdd3d9'), tr('remote.connect'))
        self.connect_button.clicked.connect(self.connect_saved)
        row.addWidget(self.connect_button)
        self.discover_button = QPushButton(qta.icon('fa5s.broadcast-tower', color='#cdd3d9'), tr('remote.discover'))
        self.discover_button.clicked.connect(self.discover)
        row.addWidget(self.discover_button)
        layout.addLayout(row)
        self.found = QComboBox()
        self.found.currentIndexChanged.connect(self.pick_found)
        layout.addWidget(self.found)
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText('http://192.168.1.100:8765')
        row.addWidget(self.url, 1)
        self.pair_button = QPushButton(tr('remote.connect'))
        self.pair_button.clicked.connect(self.prepare_pair)
        row.addWidget(self.pair_button)
        layout.addLayout(row)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('library.search'))
        self.search.textChanged.connect(self.filter)
        layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr('Artist'), tr('Titel'), tr('remote.type')])
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_project())
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context_menu)
        layout.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.actions = []
        for index, (key, icon, callback) in enumerate([('remote.refresh', 'fa5s.sync-alt', self.refresh),
                                    ('library.open', 'fa5s.folder-open', self.open_project),
                                    ('remote.upload', 'fa5s.upload', self.upload_current),
                                    ('remote.upload_dlc', 'fa5s.box', self.upload_packages),
                                    ('remote.chart', 'fa5s.file-export', self.export_chart),
                                    ('xbox.title', 'fa5s.upload', self.copy_package)]):
            if index == 3:
                layout.addLayout(row)
                row = QHBoxLayout()
            button = QPushButton(qta.icon(icon, color='#cdd3d9'), tr(key))
            button.clicked.connect(callback)
            row.addWidget(button)
            self.actions.append(button)
        layout.addLayout(row)
        sync_row = QHBoxLayout()
        self.sync_button = QPushButton(qta.icon('fa5s.sync-alt', color='#cdd3d9'), tr('remote.sync'))
        self.sync_button.clicked.connect(self.synchronize)
        sync_row.addWidget(self.sync_button)
        self.auto_sync = QCheckBox(tr('remote.auto_sync'))
        self.auto_sync.setChecked(QSettings('OpenLips', 'OpenLips Studio').value('library/auto_sync', False, type=bool))
        self.auto_sync.toggled.connect(lambda value: QSettings('OpenLips', 'OpenLips Studio').setValue('library/auto_sync', value))
        sync_row.addWidget(self.auto_sync)
        sync_row.addStretch()
        layout.addLayout(sync_row)
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(60000)
        self.sync_timer.timeout.connect(self.auto_synchronize)
        self.sync_timer.start()
        self.status = QLabel(tr('remote.ready'))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.controls = [self.connections, self.connect_button, self.discover_button, self.found, self.url, self.pair_button, self.sync_button, *self.actions]

    def context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item or self.worker and self.worker.isRunning():
            return
        self.tree.setCurrentItem(item)
        kind, record = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        if kind == 'projects':
            menu.addAction(tr('library.open'), self.open_project)
            menu.addAction(tr('remote.chart'), self.export_chart)
            menu.addAction(tr('library.community_upload'), self.upload_selected_community)
        elif kind == 'packages':
            menu.addAction(tr('xbox.title'), self.copy_package)
        else:
            menu.addAction(tr('library.open'), self.open_project)
        menu.addSeparator()
        menu.addAction(tr('remote.sync'), self.synchronize)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def upload_selected_community(self):
        record = self.selected('projects')
        if record and self.client:
            from studio.model import load_project
            self.task(lambda: self.download_project(record['id']),
                      lambda path: self.community_upload_requested.emit(load_project(path)))

    def task(self, callback, result, *, progress=False):
        if self.worker and self.worker.isRunning():
            return
        self.worker = LibraryTask(callback if progress else lambda report: callback(), self)
        self.worker.progress.connect(self.status.setText)
        self.worker.completed.connect(result)
        self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(lambda: [widget.setEnabled(True) for widget in self.controls])
        for widget in self.controls:
            widget.setEnabled(False)
        self.status.setText(tr('remote.working'))
        self.worker.start()

    def discover(self):
        from studio.library_discovery import discover
        self.task(discover, self.discovered)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.scanned:
            self.scanned = True
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self.connect_saved if self.profiles else self.discover)

    def discovered(self, results):
        self.found.clear()
        for result in results:
            self.found.addItem(f"{result['name']}  ({result['host']}:{result['port']})", result)
        self.status.setText(tr('remote.found', count=len(results)))
        if len(results) == 1 and not results[0].get('auth_required', True):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self.prepare_pair)

    def pick_found(self):
        record = self.found.currentData()
        if record:
            self.url.setText(f"{'https' if record['tls'] else 'http'}://{record['host']}:{record['port']}")
            self.pair_button.setText(tr('remote.connect') if not record.get('auth_required', True) else tr('remote.pair'))

    def prepare_pair(self):
        try:
            client = LibraryClient(self.url.text().strip())
        except Exception as error:
            self.status.setText(str(error))
            return
        if not client.tls:
            self.task(lambda: client.request('GET', '/api/v1/identity'), lambda value: self.open_lan(client, value))
            return
        self.task(lambda: client.connect(inspect=True) if client.tls else '', lambda fingerprint: self.finish_pair(client, fingerprint))

    def open_lan(self, client, identity):
        if identity.get('auth_required', True):
            self.status.setText(tr('remote.trust'))
            return
        credentials = dict(server_id=identity['server_id'], api_token='', ftp=dict(username='anonymous', password=''))
        self.paired(client, (identity, credentials))

    def finish_pair(self, client, fingerprint):
        if QMessageBox.question(self, tr('remote.trust'), tr('remote.fingerprint', fingerprint=fingerprint or 'localhost'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        code, ok = QInputDialog.getText(self, tr('remote.pair'), tr('remote.code'))
        if not ok:
            return
        client.fingerprint = fingerprint
        self.task(lambda: (client.request('GET', '/api/v1/identity'),
            client.request('POST', '/api/v1/pair', {'code': code, 'name': socket.gethostname()[:80]})),
            lambda result: self.paired(client, result))

    def paired(self, client, result):
        identity, credentials = result
        profile = dict(name=identity['name'], url=client.url, fingerprint=client.fingerprint, **credentials)
        self.profiles = [p for p in self.profiles if p['server_id'] != profile['server_id']] + [profile]
        save_profiles(self.profile_path, self.profiles)
        self.connections.clear()
        for item in self.profiles:
            self.connections.addItem(item['name'], item)
        self.connections.setCurrentIndex(self.connections.count()-1)
        self.client = LibraryClient(profile['url'], profile['api_token'], profile['fingerprint'])
        self.status.setText(tr('remote.connected') if not profile['api_token'] else tr('remote.paired'))
        # The worker's completion signal arrives before QThread.finished.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self.refresh)

    def connect_saved(self):
        profile = self.connections.currentData()
        if profile:
            self.client = LibraryClient(profile['url'], profile['api_token'], profile['fingerprint'])
            self.refresh()
        elif self.url.text().strip():
            self.prepare_pair()

    def refresh(self):
        if self.client:
            self.task(lambda: self.client.request('GET', '/api/v1/library'), self.received)

    def received(self, catalog):
        self.catalog = catalog
        self.tree.clear()
        project_names = {p['id']: p for p in catalog.get('projects', [])}
        for kind in ('projects', 'packages', 'artifacts'):
            for record in catalog.get(kind, []):
                if kind == 'artifacts':
                    source = project_names.get(record['project_id'], {})
                    label, artist, category = source.get('title', record['filename']), source.get('artist', ''), record['kind']
                else:
                    label, artist = record['title'], record.get('artist', '')
                    category = tr('library.projects') if kind == 'projects' else 'DLC'
                item = QTreeWidgetItem([artist, label, category])
                item.setData(0, Qt.ItemDataRole.UserRole, (kind, record))
                self.tree.addTopLevelItem(item)
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(1)
        self.filter()
        self.status.setText(tr('remote.connected'))

    def filter(self):
        query = self.search.text().casefold()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            item.setHidden(query not in (item.text(0)+' '+item.text(1)).casefold())

    def selected(self, kind):
        item = self.tree.currentItem()
        if item:
            selected_kind, record = item.data(0, Qt.ItemDataRole.UserRole)
            if selected_kind == kind:
                return record
        return None

    def open_project(self):
        record = self.selected('projects')
        if not self.client:
            return
        if record:
            self.task(lambda: self.download_project(record['id']), lambda path: self.project_opened.emit(str(path)))
        elif record := self.selected('artifacts'):
            self.task(lambda: self.download_artifact(record),
                lambda path: self.project_opened.emit(str(path)) if Path(path).suffix == '.olp' else self.status.setText(str(path)))

    def download_artifact(self, record):
        if not re.fullmatch(r'[a-f0-9]{64}\.(ols|mid|lrc)', record['filename']):
            raise ValueError('Unsafe remote artifact filename')
        folder = default_library_root().parent / 'remote-downloads'
        path = folder / record['filename']
        self.client.request('GET', '/api/v1/artifacts/' + record['id'], target=path,
            expected_hash=record['id'], expected_bytes=record['bytes'])
        if path.suffix == '.ols':
            from studio.community_import import import_community
            project = import_community(path, storage_root=folder / 'covers')
            output = path.with_suffix('.olp')
            save_project(project, output)
            return output
        return path

    def download_project(self, identifier):
        if not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('Invalid remote project ID')
        data = self.client.request('GET', '/api/v1/projects/' + identifier)
        payload = data['project']
        for field in ('audio_path', 'video_path', 'cover_path'):
            payload[field] = ''
        project = StudioProject.from_payload(payload)
        folder = default_library_root().parent / 'remote-downloads'
        for field, media in data['media'].items():
            if field not in ('audio', 'video', 'cover') or not re.fullmatch(r'[a-f0-9]{64}\.[a-z0-9]{1,16}', media['filename']):
                raise ValueError('Unsafe remote media filename')
            path = folder / media['filename']
            self.client.request('GET', f'/api/v1/projects/{identifier}/media/{field}', target=path,
                expected_hash=media['sha256'], expected_bytes=media['bytes'])
            setattr(project, field + '_path', str(path))
        path = folder / (identifier + '.olp')
        save_project(project, path)
        return path

    def upload_current(self):
        if not self.client:
            return
        project = copy.deepcopy(self.get_project())
        client = self.client
        def upload(progress):
            from studio.library_sync import upload_project
            upload_project(client, project, progress)
            return self.client.request('GET', '/api/v1/library')
        self.task(upload, self.received, progress=True)

    def upload_packages(self):
        if not self.client:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, tr('remote.upload_dlc'))
        if not paths:
            return
        client, library = self.client, self.get_library() if self.get_library else None
        def upload(progress):
            errors = []
            for path in paths:
                try:
                    from tools.build_dlc import verify_stfs
                    expected = verify_stfs(path)['sha256']
                    if library:
                        expected = library.add_package(path, progress=progress)
                    result = client.upload_file('/api/v1/packages', path, progress=progress)
                    if result['id'] != expected:
                        raise ValueError('Uploaded DLC checksum does not match')
                except Exception as error:
                    errors.append(f'{Path(path).name}: {error}')
            return client.request('GET', '/api/v1/library'), errors
        def done(result):
            self.received(result[0])
            self.status.setText('\n'.join(result[1]) if result[1] else tr('library.saved'))
        self.task(upload, done, progress=True)

    def auto_synchronize(self):
        if self.auto_sync.isChecked() and self.client:
            self.synchronize()

    def synchronize(self):
        if not self.client or not self.get_library or (self.worker and self.worker.isRunning()):
            return
        parent = self.parent()
        if hasattr(parent, 'local') and parent.local.worker and parent.local.worker.isRunning():
            return
        client, library = self.client, self.get_library()
        def sync(progress):
            from studio.library_sync import sync_library
            result = sync_library(library, client, progress)
            return client.request('GET', '/api/v1/library'), result
        def done(value):
            catalog, result = value
            self.received(catalog)
            if hasattr(parent, 'local'):
                parent.local.refresh()
            self.status.setText(tr('remote.synced', **result) +
                ('\n' + '\n'.join(result['errors'][:20]) if result['errors'] else ''))
        self.task(sync, done, progress=True)

    def export_chart(self):
        record = self.selected('projects')
        if record and self.client:
            self.task(lambda: self.client.request('POST', '/api/v1/jobs', {'projects': [record['id']], 'kind': 'chart'}),
                lambda result: self.status.setText(tr('remote.job', id=result['id'][:8])))

    def copy_package(self):
        record = self.selected('packages')
        if not record or not self.client:
            return
        if not re.fullmatch('[A-Fa-f0-9]{42}', record['filename']):
            self.status.setText('Invalid remote package filename')
            return
        path = default_library_root().parent / 'remote-downloads' / record['filename']
        self.task(lambda: self.client.request('GET', '/api/v1/packages/'+record['id'], target=path,
                expected_hash=record['id'], expected_bytes=record['bytes']), self.package_ready)

    def package_ready(self, path):
        from studio.xbox_dialog import XboxDialog
        XboxDialog(self, path).exec()
