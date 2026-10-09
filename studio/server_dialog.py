"""Explicit server setup/launch without automatic firewall or startup changes."""
from pathlib import Path
import sys

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QHBoxLayout,
    QLineEdit, QSpinBox, QLabel, QPushButton, QTextEdit, QCheckBox)

from studio.i18n import tr
from studio.server_config import create_config, load_config, update_connection, update_features, default_lan_bind


class ServerDialog(QDialog):
    def __init__(self, parent, library_root):
        super().__init__(parent)
        self.setWindowTitle(tr('server.title'))
        self.resize(640, 470)
        self.root = Path(library_root)
        self.config_path = self.root / 'server.json'
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.errorOccurred.connect(lambda _: self.status.setText(self.process.errorString()))
        self.process.finished.connect(self.stopped)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.bind = QLineEdit(default_lan_bind())
        self.name = QLineEdit('OpenLips Library')
        self.name.setMaxLength(80)
        self.tls = QCheckBox(tr('server.tls'))
        self.tls.setChecked(False)
        self.lan = QCheckBox(tr('server.lan_open'))
        self.lan.setChecked(True)
        self.lan.toggled.connect(self.lan_controls)
        self.discovery = QCheckBox(tr('server.discovery'))
        self.discovery.setChecked(True)
        self.port = QSpinBox()
        self.ftp = QSpinBox()
        for box, value in ((self.port, 8765), (self.ftp, 2121)):
            box.setRange(1024, 65535)
            box.setValue(value)
        for key, widget in [('server.bind', self.bind), ('server.api_port', self.port), ('server.ftp_port', self.ftp)]:
            form.addRow(tr(key), widget)
        form.addRow(tr('server.name'), self.name)
        form.addRow(self.lan)
        form.addRow(self.tls)
        form.addRow(self.discovery)
        layout.addLayout(form)
        self.status = QLabel(tr('server.notice'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        row = QHBoxLayout()
        self.setup = QPushButton(tr('server.setup'))
        self.setup.clicked.connect(self.configure)
        self.start = QPushButton(tr('server.start'))
        self.start.clicked.connect(self.launch)
        self.stop = QPushButton(tr('server.stop'))
        self.stop.clicked.connect(self.stop_server)
        self.credentials = QPushButton(tr('server.credentials'))
        self.credentials.clicked.connect(self.show_credentials)
        self.pair_button = QPushButton(tr('remote.pair'))
        self.pair_button.clicked.connect(self.pair_device)
        for button in (self.setup, self.start, self.stop, self.credentials, self.pair_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.update_controls()
        if self.config_path.exists():
            try:
                config = load_config(self.config_path)
                self.bind.setText(config['bind'])
                self.port.setValue(config['port'])
                self.ftp.setValue(config['ftp_port'])
                self.name.setText(config['name'])
                self.tls.setChecked(bool(config.get('tls_cert')))
                self.discovery.setChecked(bool(config.get('discovery_enabled')))
                self.lan.setChecked(True)
            except Exception as error:
                self.status.setText(str(error))
        self.lan_controls()

    def lan_controls(self, *_):
        opened = self.lan.isChecked()
        self.tls.setVisible(not opened)
        self.pair_button.setVisible(not opened)
        if opened:
            self.tls.setChecked(False)

    def update_controls(self):
        running = self.process.state() != QProcess.ProcessState.NotRunning
        exists = self.config_path.exists()
        self.setup.setText(tr('server.save') if exists else tr('server.setup'))
        self.setup.setEnabled(not running)
        self.start.setEnabled(exists and not running)
        self.stop.setEnabled(running)
        self.credentials.setEnabled(exists)
        self.pair_button.setEnabled(running)
        for widget in (self.bind, self.port, self.ftp, self.name, self.tls, self.discovery, self.lan):
            widget.setEnabled(not running)

    def configure(self):
        try:
            from studio.server import server_lock
            with server_lock(self.root):
                if self.config_path.exists():
                    update_connection(self.config_path, self.bind.text().strip(), self.port.value(), self.ftp.value())
                    update_features(self.config_path, tls=self.tls.isChecked(), discovery=self.discovery.isChecked(), name=self.name.text(), lan_open=self.lan.isChecked())
                else:
                    create_config(self.config_path, self.root, self.bind.text().strip(), self.port.value(), self.ftp.value(),
                                  tls=self.tls.isChecked(), discovery=self.discovery.isChecked(), name=self.name.text(), lan_open=self.lan.isChecked())
            self.status.setText(tr('server.configured', path=str(self.config_path)))
        except Exception as error:
            self.status.setText(str(error))
        self.update_controls()

    def launch(self):
        try:
            if self.lan.isChecked() and not load_config(self.config_path).get('lan_open'):
                self.configure()
            load_config(self.config_path)
            self.output.clear()
            arguments = ['--server', '--config', str(self.config_path)]
            if not getattr(sys, 'frozen', False):
                arguments = ['-m', 'studio', *arguments]
            self.process.start(sys.executable, arguments)
            self.status.setText(tr('server.notice'))
            self.update_controls()
        except Exception as error:
            self.status.setText(str(error))

    def read_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.output.insertPlainText(data[-8192:])
        if self.output.document().blockCount() > 300:
            self.output.setPlainText(self.output.toPlainText()[-8192:])

    def stop_server(self):
        try:
            config = load_config(self.config_path)
            self.owner_client(config).request('POST', '/api/v1/shutdown', {})
            self.stop.setEnabled(False)
            QTimer.singleShot(20000, self.force_stop)
        except Exception as error:
            self.status.setText(str(error))

    def owner_client(self, config):
        from studio.library_client import LibraryClient
        return LibraryClient(f"{'https' if config.get('tls_cert') else 'http'}://{config['bind']}:{config['port']}",
                             config['api_token'], config.get('certificate_fingerprint', ''))

    def pair_device(self):
        try:
            config = load_config(self.config_path)
            result = self.owner_client(config).request('POST', '/api/v1/pairing', {})
            self.status.setText(tr('server.pair_code', code=result['code'],
                fingerprint=config.get('certificate_fingerprint', 'localhost')))
        except Exception as error:
            self.status.setText(str(error))

    def force_stop(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def stopped(self, code, *_):
        self.status.setText(tr('server.failed', path=str(self.root / 'headless.log')) if code else tr('server.stopped'))
        self.update_controls()

    def show_credentials(self):
        try:
            config = load_config(self.config_path)
            dialog = QDialog(self)
            dialog.setWindowTitle(tr('server.credentials'))
            layout = QVBoxLayout(dialog)
            text = QTextEdit()
            text.setReadOnly(True)
            if config.get('lan_open'):
                text.setPlainText(f"http://{config['bind']}:{config['port']}\nFTP: {config['bind']}:{config['ftp_port']}\n{tr('server.lan_open')}")
                layout.addWidget(text)
                dialog.resize(650, 180)
                dialog.exec()
                return
            text.setPlainText(f"API: {'https' if config.get('tls_cert') else 'http'}://{config['bind']}:{config['port']}/api/v1/\n"
                f"Bearer: {config['api_token']}\nFTP: {config['bind']}:{config['ftp_port']}\n"
                f"User: {config['ftp_user']}\nPassword: {config['ftp_password']}\nPassive: 50000-50009\n"
                f"SHA-256: {config.get('certificate_fingerprint', '')}")
            layout.addWidget(text)
            dialog.resize(650, 220)
            dialog.exec()
        except Exception as error:
            self.status.setText(str(error))

    def reject(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            super().reject()
        else:
            self.status.setText(tr('server.stop_first'))

    def closeEvent(self, event):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            super().closeEvent(event)
        else:
            self.status.setText(tr('server.stop_first'))
            event.ignore()
