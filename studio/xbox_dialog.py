"""Studio's package-to-console FTP workflow."""
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout)
import qtawesome as qta

from studio.i18n import tr
from studio.xbox_transfer import connection, copy_to_xbox


class TransferWorker(QThread):
    progress = Signal(str, int)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, settings, package, parent):
        super().__init__(parent)
        self.settings, self.package = settings, package

    def run(self):
        try:
            if self.package:
                path = copy_to_xbox(self.package, self.settings,
                    lambda phase, done, total: self.progress.emit(phase,
                        min(99, (0 if phase == 'upload' else 50) + done * 50 // max(1, total))),
                    self.isInterruptionRequested)
                self.completed.emit(tr('xbox.saved', path=path))
            else:
                with connection(self.settings['host'], self.settings['port'],
                                self.settings['username'], self.settings['password'], self.settings['tls']) as ftp:
                    ftp.pwd()
                self.completed.emit(tr('xbox.connected'))
        except Exception as error:
            message = str(error)
            password = self.settings['password']
            self.failed.emit(message.replace(password, '***') if password else message)
        finally:
            self.settings['password'] = ''


class XboxDialog(QDialog):
    def __init__(self, parent=None, package=None):
        super().__init__(parent)
        self.worker = None
        self.setWindowTitle(tr('xbox.title'))
        self.resize(610, 400)
        settings = QSettings('OpenLips', 'OpenLips Studio')
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.package = QLineEdit(str(package or ''))
        pick = QPushButton(qta.icon('fa5s.folder-open', color='#cdd3d9'), '')
        pick.setToolTip(tr('usb.choose_package'))
        pick.clicked.connect(self.choose)
        row = QHBoxLayout()
        row.addWidget(self.package)
        row.addWidget(pick)
        form.addRow(tr('xbox.package'), row)
        self.host = QLineEdit(str(settings.value('xbox/host', '')))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(settings.value('xbox/port', 21)))
        self.user = QLineEdit(str(settings.value('xbox/username', 'xbox')))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.root = QLineEdit(str(settings.value('xbox/root', 'Hdd1/Content')))
        self.tls = QCheckBox('FTPS (TLS)')
        self.tls.setChecked(settings.value('xbox/tls', False, type=bool))
        for key, widget in [('xbox.host', self.host), ('xbox.port', self.port),
                            ('xbox.user', self.user), ('xbox.password', self.password),
                            ('xbox.root', self.root)]:
            form.addRow(tr(key), widget)
        form.addRow(self.tls)
        layout.addLayout(form)
        notice = QLabel(tr('xbox.notice'))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.test = QPushButton(tr('xbox.test'))
        self.test.clicked.connect(lambda: self.start(False))
        self.copy = QPushButton(qta.icon('fa5s.upload', color='#cdd3d9'), tr('xbox.copy'))
        self.copy.clicked.connect(lambda: self.start(True))
        self.cancel = QPushButton(tr('Abbrechen'))
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_transfer)
        for button in (self.test, self.copy, self.cancel):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.controls = [self.package, pick, self.host, self.port, self.user,
                         self.password, self.root, self.tls, self.test, self.copy]

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('usb.choose_package'))
        if path:
            self.package.setText(path)

    def start(self, upload):
        if self.worker and self.worker.isRunning():
            return
        if upload and not Path(self.package.text()).is_file():
            self.status.setText(tr('usb.choose_package'))
            return
        values = dict(host=self.host.text().strip(), port=self.port.value(),
            username=self.user.text(), password=self.password.text(),
            root=self.root.text().strip(), tls=self.tls.isChecked())
        settings = QSettings('OpenLips', 'OpenLips Studio')
        for key in ('host', 'port', 'username', 'root', 'tls'):
            settings.setValue('xbox/' + key, values[key])
        self.worker = TransferWorker(values, self.package.text() if upload else None, self)
        self.worker.progress.connect(lambda phase, value: (
            self.status.setText(tr('xbox.' + phase)), self.progress.setValue(value)))
        self.worker.completed.connect(lambda message: self.result(message, True))
        self.worker.failed.connect(lambda message: self.result(message, False))
        for widget in self.controls:
            widget.setEnabled(False)
        self.cancel.setEnabled(upload)
        self.progress.setValue(0)
        self.status.setText(tr('xbox.connecting'))
        self.worker.start()

    def result(self, message, success):
        self.status.setText(message)
        self.progress.setValue(100 if success else 0)
        for widget in self.controls:
            widget.setEnabled(True)
        self.cancel.setEnabled(False)

    def cancel_transfer(self):
        if self.worker:
            self.worker.requestInterruption()
        self.cancel.setEnabled(False)

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            self.password.clear()
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            self.password.clear()
            super().closeEvent(event)
