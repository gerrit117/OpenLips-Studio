"""Background media conversion; input files are never overwritten."""
import copy
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QPushButton, QFileDialog,
                               QDialogButtonBox, QComboBox, QPlainTextEdit, QWidget, QHBoxLayout, QLabel)
import qtawesome as qta
from studio.i18n import tr

from studio.media import prepare_media, native_encoder, ffmpeg_encoder


class MediaWorker(QThread):
    message = Signal(str)
    finished_output = Signal(str)
    failed = Signal(str)

    def __init__(self, project, values, parent):
        super().__init__(parent)
        self.project, self.values = copy.deepcopy(project), values

    def run(self):
        try:
            v = self.values
            output = prepare_media(self.project, v['output'], v['mode'], v['encoder'],
                                   v['ffmpeg'], self.message.emit)
            self.finished_output.emit(str(output))
        except Exception as exc:
            self.failed.emit(str(exc))


class MediaDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.worker = None
        self.setWindowTitle(tr('OG-Medien vorbereiten'))
        self.resize(680, 500)
        layout = QFormLayout(self)
        self.mode = QComboBox()
        self.mode.addItem(tr('Video mit eigener Tonspur'), 'video')
        self.mode.addItem(tr('Nur Audio'), 'audio')
        self.mode.addItem(tr('Audio mit statischem Covervideo'), 'cover-video')
        if not project.video_path:
            self.mode.setCurrentIndex(1)
        layout.addRow(tr('Quelle'), self.mode)
        self.fields = {}
        for key, label, value in [('output', tr('Neuer Ausgabeordner'), '')]:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(value)
            self.fields[key] = edit
            h.addWidget(edit, 1)
            button = QPushButton(qta.icon('fa5s.folder-open'), '')
            button.setToolTip(label + tr(' auswaehlen'))
            button.clicked.connect(lambda checked=False, k=key: self.choose(k))
            h.addWidget(button)
            layout.addRow(label, row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addRow(self.log)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr('Konvertieren'))
        self.buttons.accepted.connect(self.convert)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)
        if sys.platform != 'win32':
            self.log.setPlainText(tr('Die finale VC-1/WMA-Pro-Konvertierung benötigt derzeit Windows. '
                                 'Projekte, Imports und Bearbeitung funktionieren auch auf macOS und Linux. '
                                 'Speichere das Projekt als .olp und konvertiere die Medien unter Windows.'))
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        elif not native_encoder():
            self.log.setPlainText(tr('Der gebündelte OpenLips-Encoder fehlt. Bitte das vollständige Windows-Release entpacken.'))
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)

    def choose(self, key):
        if key == 'output':
            parent = QFileDialog.getExistingDirectory(self, tr('Uebergeordneten Ordner waehlen'))
            value = str(Path(parent) / 'prepared_media') if parent else ''
        else:
            value = QFileDialog.getOpenFileName(self, tr('Encoder waehlen'))[0]
        if value:
            self.fields[key].setText(value)

    def convert(self):
        values = {key: edit.text() for key, edit in self.fields.items()}
        values.update(encoder=native_encoder(), ffmpeg=ffmpeg_encoder())
        values['mode'] = self.mode.currentData()
        if not values['output'].strip():
            self.log.appendPlainText(tr('Bitte einen neuen Ausgabeordner angeben.'))
            return
        self.worker = MediaWorker(self.project, values, self)
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.finished_output.connect(lambda path: self.done_message(tr('Fertig: ') + path))
        self.worker.failed.connect(lambda error: self.done_message(tr('Fehler: ') + error))
        self.buttons.setEnabled(False)
        self.mode.setEnabled(False)
        self.worker.start()

    def done_message(self, message):
        self.log.appendPlainText(message)
        self.buttons.setEnabled(True)
        self.mode.setEnabled(True)

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
