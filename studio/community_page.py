"""Native community workspace with serialized background network operations."""
import copy
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTextEdit, QCheckBox, QProgressBar,
    QFileDialog, QDialog, QDialogButtonBox, QDoubleSpinBox, QTabWidget)
import qtawesome as qta

from studio.community_client import CommunityClient, CommunityError, BASE_URL
from studio.i18n import tr


class CommunityJob(QThread):
    progress = Signal(int, int)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.operation(self.progress.emit)
        except Exception as error:
            self.error = error
        finally:
            self.operation = None


class ProjectUploadDialog(QDialog):
    def __init__(self, project, parent):
        super().__init__(parent)
        self.setWindowTitle(tr('community.upload_project'))
        self.resize(520, 350)
        form = QFormLayout(self)
        self.fields = {}
        for key, label in [('album','export.album'), ('genre','export.genre'),
                           ('language','export.language'), ('youtube','export.reference')]:
            field = QLineEdit(project.video_reference if key == 'youtube' else '')
            self.fields[key] = field
            form.addRow(tr(label), field)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(.001, 1800)
        self.duration.setDecimals(3)
        self.duration.setValue(max(project.duration + 2, .001))
        form.addRow(tr('export.duration'), self.duration)
        self.rights = QCheckBox(tr('community.rights'))
        self.rights.setStyleSheet('QCheckBox { spacing: 8px; }')
        form.addRow(self.rights)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('community.upload'))
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.rights.toggled.connect(buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class CommunityPage(QWidget):
    song_opened = Signal(str)

    def __init__(self, project_provider, parent=None, client=None):
        super().__init__(parent)
        self.client = client or CommunityClient()
        self.project_provider = project_provider
        self.worker = None
        self.authenticated = False
        self.phase = 'signed_out'
        self.page_number = 1
        self.pages = 1
        self.rows = []
        self.selected = None
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 12, 18, 12)
        account = QHBoxLayout()
        self.account_label = QLabel('OpenLips Community')
        account.addWidget(self.account_label, 1)
        self.logout_button = self.button('community.logout', 'fa5s.sign-out-alt', self.logout)
        account.addWidget(self.logout_button)
        root.addLayout(account)
        self.login_panel = QWidget()
        login = QFormLayout(self.login_panel)
        self.username = QLineEdit()
        self.username.setMaxLength(150)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setMaxLength(256)
        self.otp = QLineEdit()
        self.otp.setMaxLength(6)
        login.addRow(tr('download.username'), self.username)
        login.addRow(tr('download.password'), self.password)
        login.addRow(tr('community.otp'), self.otp)
        actions = QHBoxLayout()
        self.login_button = self.button('community.login', 'fa5s.sign-in-alt', self.login)
        actions.addWidget(self.login_button)
        self.register_button = self.button('community.register', 'fa5s.user-plus',
                                           lambda: QDesktopServices.openUrl(QUrl(BASE_URL+'/register/')))
        actions.addWidget(self.register_button)
        self.setup_button = self.button('community.setup', 'fa5s.external-link-alt',
                                        lambda: QDesktopServices.openUrl(QUrl(BASE_URL+'/account/')))
        actions.addWidget(self.setup_button)
        actions.addStretch()
        login.addRow(actions)
        self.password.returnPressed.connect(self.login)
        self.otp.returnPressed.connect(self.login)
        root.addWidget(self.login_panel)
        self.library = QTabWidget()
        root.addWidget(self.library, 1)
        browse = QWidget()
        layout = QVBoxLayout(browse)
        search = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('community.search'))
        search.addWidget(self.search, 1)
        self.sort = QComboBox()
        for key, label in [('artist','Artist'), ('title','Titel'), ('album','export.album'), ('rating','community.rating'), ('newest','community.newest')]:
            self.sort.addItem(tr(label), key)
        search.addWidget(self.sort)
        self.mine = QCheckBox(tr('community.mine'))
        search.addWidget(self.mine)
        search.addWidget(self.button('community.refresh', 'fa5s.sync-alt', self.reload))
        layout.addLayout(search)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr('Artist'), tr('Titel'), tr('export.album'), tr('community.rating'), tr('community.status')])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.select_song)
        layout.addWidget(self.table, 2)
        navigation = QHBoxLayout()
        self.previous_button = self.button('community.previous', 'fa5s.chevron-left', lambda: self.load_page(self.page_number-1))
        self.next_button = self.button('community.next', 'fa5s.chevron-right', lambda: self.load_page(self.page_number+1))
        self.page_label = QLabel()
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.page_label, 1)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)
        song_actions = QHBoxLayout()
        self.download_button = self.button('community.download', 'fa5s.download', self.download)
        song_actions.addWidget(self.download_button)
        self.rating = QComboBox()
        for number in range(1, 6):
            self.rating.addItem(qta.icon('fa5s.star', color='#d9b65f'), str(number), number)
        song_actions.addWidget(self.rating)
        self.rate_button = self.button('community.rate', 'fa5s.star', self.rate)
        song_actions.addWidget(self.rate_button)
        song_actions.addStretch()
        layout.addLayout(song_actions)
        self.library.addTab(browse, tr('community.songs'))
        upload = QWidget()
        upload_layout = QVBoxLayout(upload)
        self.upload_path = QLineEdit()
        self.upload_path.setReadOnly(True)
        file_row = QHBoxLayout()
        file_row.addWidget(self.upload_path, 1)
        file_row.addWidget(self.button('community.choose', 'fa5s.folder-open', self.choose_upload))
        upload_layout.addLayout(file_row)
        self.upload_info = QLabel()
        self.upload_info.setWordWrap(True)
        upload_layout.addWidget(self.upload_info)
        self.description = QTextEdit()
        self.description.setPlaceholderText(tr('community.description'))
        upload_layout.addWidget(self.description, 1)
        self.rights = QCheckBox(tr('community.rights'))
        upload_layout.addWidget(self.rights)
        upload_buttons = QHBoxLayout()
        self.upload_button = self.button('community.upload', 'fa5s.upload', self.upload_file)
        self.project_button = self.button('community.upload_project', 'fa5s.file-export', self.upload_project)
        upload_buttons.addWidget(self.upload_button)
        upload_buttons.addWidget(self.project_button)
        upload_buttons.addStretch()
        upload_layout.addLayout(upload_buttons)
        self.library.addTab(upload, tr('community.upload'))
        self.progress = QProgressBar()
        self.progress.hide()
        root.addWidget(self.progress)
        self.status = QLabel(tr('community.signin_notice'))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.status)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(400)
        self.search_timer.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda: self.search_timer.start())
        self.sort.currentIndexChanged.connect(self.reload)
        self.mine.toggled.connect(self.reload)
        self.update_controls()

    def button(self, label, icon, callback):
        button = QPushButton(qta.icon(icon, color='#cdd3d9'), tr(label))
        button.clicked.connect(callback)
        return button

    def update_controls(self):
        busy = self.worker is not None
        self.login_panel.setVisible(not self.authenticated)
        self.logout_button.setVisible(self.authenticated or self.phase != 'signed_out')
        self.logout_button.setEnabled(not busy)
        self.login_button.setEnabled(not busy)
        self.setup_button.setVisible(self.phase == 'mfa_setup_required')
        self.library.setEnabled(self.authenticated and not busy)
        self.previous_button.setEnabled(self.page_number > 1)
        self.next_button.setEnabled(self.page_number < self.pages)
        self.download_button.setEnabled(self.selected is not None)
        self.rate_button.setEnabled(self.selected is not None and self.selected.get('status') == 'published')

    def run_job(self, operation, callback):
        if self.worker:
            return
        job = CommunityJob(operation, self)
        self.worker = job
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText(tr('community.working'))
        job.progress.connect(self.show_progress)
        def finish():
            self.worker = None
            self.progress.hide()
            if job.error:
                self.failed(job.error)
            else:
                self.status.setText('')
                try:
                    callback(job.result)
                except Exception as error:
                    self.failed(error)
            job.deleteLater()
            self.update_controls()
        job.finished.connect(finish)
        self.update_controls()
        job.start()

    def show_progress(self, done, total):
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, done * 100 // total))

    def failed(self, error):
        code = error.code if isinstance(error, CommunityError) else ''
        key = 'community.error.' + code
        self.status.setText(tr(key) if tr(key) != key else str(error))
        if code in ('session_expired', 'login_required', 'access_denied', 'mfa_required'):
            self.authenticated = False
            self.rows = []
            self.table.setRowCount(0)
            self.details.clear()
            self.selected = None
            self.phase = 'mfa_required' if code == 'mfa_required' else 'signed_out'

    def login(self):
        if self.phase == 'mfa_required':
            code = self.otp.text().strip()
            self.otp.clear()
            self.run_job(lambda _: self.client.request('mfa/', {'code':code}), self.signed_in)
        else:
            username, password = self.username.text().strip(), self.password.text()
            self.password.clear()
            self.run_job(lambda _: self.client.login(username, password), self.signed_in)

    def signed_in(self, result):
        self.phase = result['phase']
        self.authenticated = self.phase == 'authenticated'
        if self.authenticated:
            self.account_label.setText('OpenLips Community · ' + result['username'])
            self.reload()
        else:
            self.status.setText(tr('community.' + self.phase))

    def logout(self):
        def leave(_):
            try:
                return self.client.logout()
            except CommunityError:
                return {'offline': True}
        self.run_job(leave, self.signed_out)

    def signed_out(self, _):
        self.authenticated = False
        self.phase = 'signed_out'
        self.account_label.setText('OpenLips Community')
        self.rows = []
        self.table.setRowCount(0)
        self.details.clear()
        self.selected = None
        self.status.setText(tr('community.signin_notice'))

    def reload(self, *_):
        self.load_page(1)

    def load_page(self, page):
        if not self.authenticated:
            return
        query, sort, mine = self.search.text(), self.sort.currentData(), self.mine.isChecked()
        self.run_job(lambda _: self.client.songs(query, sort, page, mine), self.show_songs)

    def show_songs(self, data):
        self.selected = None
        self.details.clear()
        self.rows = data['songs']
        self.page_number, self.pages = data['page'], data['pages']
        self.page_label.setText(f"{self.page_number} / {self.pages} · {data['total']} " + tr('community.songs'))
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for row, song in enumerate(self.rows):
            score = f"{song['rating']:.1f} ({song['votes']})" if song.get('rating') is not None else '—'
            for column, value in enumerate((song['artist'], song['title'], song['album'], score, tr('community.status.'+song['status']))):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.blockSignals(False)
        self.status.setText(tr('community.empty') if not self.rows else '')

    def select_song(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.rows):
            return
        self.selected = self.rows[row]
        song_id = self.selected['id']
        self.run_job(lambda _: self.client.request(f'songs/{song_id}/'), self.show_details)

    def show_details(self, song):
        self.selected = song
        text = f"{song['artist']} – {song['title']}\n{song.get('description', '')}\n"
        text += '\n'.join(f"{c['author']}: {c['text']}" for c in song.get('comments', []))
        self.details.setPlainText(text)
        if song.get('own_rating'):
            self.rating.setCurrentIndex(song['own_rating']-1)

    def rate(self):
        if self.selected:
            song_id, value = self.selected['id'], self.rating.currentData()
            self.run_job(lambda _: self.client.request(f'songs/{song_id}/rate/', {'value':value}), lambda _: self.reload())

    def download(self):
        if not self.selected:
            return
        song_id = self.selected['id']
        path, _ = QFileDialog.getSaveFileName(self, tr('community.download'), f'openlips-song-{song_id}.ols', 'OpenLips Song (*.ols)')
        if not path:
            return
        if not path.lower().endswith('.ols'):
            path += '.ols'
        self.run_job(lambda progress: self.client.download(song_id, path, progress), self.song_opened.emit)

    def choose_upload(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('community.choose'), '', 'OpenLips Song (*.ols)')
        if not path:
            return
        def inspect(_):
            from tools.song_bundle import MAX_BUNDLE, decode_bundle
            if Path(path).stat().st_size > MAX_BUNDLE:
                raise ValueError('Song exceeds the supported size')
            return decode_bundle(Path(path).read_bytes()).manifest['metadata']
        def ready(metadata):
            self.upload_path.setText(path)
            self.upload_info.setText(metadata['artist'] + ' – ' + metadata['title'])
            self.rights.setChecked(False)
        self.run_job(inspect, ready)

    def upload_file(self):
        path, rights, description = self.upload_path.text(), self.rights.isChecked(), self.description.toPlainText()
        if not path or not rights:
            self.status.setText(tr('community.error.rights_required'))
            return
        self.run_job(lambda _: self.client.upload(path, rights=rights, description=description), self.uploaded)

    def upload_project(self):
        project = copy.deepcopy(self.project_provider())
        dialog = ProjectUploadDialog(project, self)
        if not dialog.exec():
            return
        options = {key: field.text().strip() for key, field in dialog.fields.items()}
        duration = dialog.duration.value()
        def prepare(_):
            from studio.exporters import export_community_song
            with tempfile.TemporaryDirectory(prefix='openlips-community-') as folder:
                path = Path(folder) / 'song.ols'
                export_community_song(project, path, duration=duration, **options)
                return self.client.upload(path, rights=True)
        self.run_job(prepare, self.uploaded)

    def uploaded(self, result):
        self.status.setText(tr('community.uploaded'))
        self.rights.setChecked(False)
