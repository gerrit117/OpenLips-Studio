"""Optional adapter for the existing experimental STFS backend."""
from pathlib import Path
import tempfile

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QPushButton,
                               QFileDialog, QDialogButtonBox, QMessageBox)

from studio.exporters import export_owned_pair


class PackageWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, project, values, parent):
        super().__init__(parent)
        self.project, self.values = project, values

    def run(self):
        try:
            from tools.build_dlc import make_manifest, build_package, asset_name
            v = self.values
            media = {key: Path(v[key]) for key in ('audio', 'preview_audio', 'jacket')}
            if v['video']:
                media['video'] = Path(v['video'])
            for path in media.values():
                if not path.is_file():
                    raise ValueError(f'Missing media file: {path}')
                asset_name(path.name)
            with tempfile.TemporaryDirectory(prefix='openlips-studio-') as temp:
                name = 'custom'
                pair = export_owned_pair(self.project, Path(temp) / 'pair', name,
                                          media['audio'].name,
                                          media.get('video').name if 'video' in media else None)
                files = {p.name: p for p in media.values()}
                if len(files) != len(media):
                    raise ValueError('Media basenames must be distinct')
                assets = {key: path.name for key, path in media.items()}
                for key, basename in [('chart', name + '.X360'), ('lyric', name + '_Lyric.X360')]:
                    assets[key] = basename
                    if basename in files:
                        raise ValueError('Media basename conflicts with chart')
                    files[basename] = pair / basename
                manifest = make_manifest(self.project.title, self.project.artist,
                                         int(v['id'], 0), self.project.duration + 2, assets)
                result = build_package(v['backend'], files, manifest, v['output'], self.project.title)
            self.completed.emit(f'{v["output"]}\nSHA256: {result["sha256"]}')
        except Exception as exc:
            self.failed.emit(str(exc))


class DlcDialog(QDialog):
    def __init__(self, project, parent):
        super().__init__(parent)
        self.setWindowTitle('DLC exportieren (experimentell)')
        self.resize(620, 380)
        self.project = project
        self.worker = None
        self.fields = {}
        layout = QFormLayout(self)
        self.id = QLineEdit('0x73000001')
        layout.addRow('Eigene freie Song-ID', self.id)
        for key, label in [('backend', 'STFS-Backend'), ('audio', 'Audio (xWMA)'),
                           ('preview_audio', 'Vorschau (xWMA)'), ('jacket', 'Cover (JPEG)'),
                           ('video', 'Video (optional)'), ('output', 'Ausgabepaket')]:
            edit = QLineEdit()
            self.fields[key] = edit
            button = QPushButton('...')
            button.setToolTip(label + ' auswaehlen')
            button.clicked.connect(lambda checked=False, k=key: self.choose(k))
            from PySide6.QtWidgets import QWidget, QHBoxLayout
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(edit, 1)
            h.addWidget(button)
            layout.addRow(label, row)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.build)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def choose(self, key):
        if key == 'output':
            path, _ = QFileDialog.getSaveFileName(self, 'Neues Paket', 'custom.LIVE', 'LIVE (*.LIVE)')
        else:
            path, _ = QFileDialog.getOpenFileName(self, key)
        if path:
            self.fields[key].setText(path)

    def build(self):
        import copy
        if QMessageBox.question(self, 'Experimenteller Export',
            'Der STFS-Container wird geprueft, die DLC-Erkennung im Spiel ist noch nicht bestaetigt. Fortfahren?') != QMessageBox.StandardButton.Yes:
            return
        values = {k: w.text() for k, w in self.fields.items()}
        values['id'] = self.id.text()
        self.worker = PackageWorker(copy.deepcopy(self.project), values, self)
        self.worker.completed.connect(self.success)
        self.worker.failed.connect(self.failure)
        self.buttons.setEnabled(False)
        self.worker.start()

    def success(self, result):
        QMessageBox.information(self, 'Paket validiert', result)
        self.buttons.setEnabled(True)

    def failure(self, message):
        QMessageBox.critical(self, 'Export fehlgeschlagen', message)
        self.buttons.setEnabled(True)

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
