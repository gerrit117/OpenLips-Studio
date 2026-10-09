"""Native local batch import, sharing the existing Song Pack export workflow."""
from pathlib import Path
import uuid

from PySide6.QtCore import QThread, Signal, Qt, QStandardPaths
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QLineEdit,
    QProgressBar, QMessageBox, QComboBox)
import qtawesome as qta

from studio.i18n import tr
from studio.model import save_project
from studio.ultrastar_batch import discover_charts, load_chart, MAX_BATCH


class BatchReader(QThread):
    progress = Signal(int, int)
    loaded = Signal(object, object)

    def __init__(self, paths, parent):
        super().__init__(parent)
        self.paths = paths

    def run(self):
        songs, errors = [], []
        for index, path in enumerate(self.paths):
            if self.isInterruptionRequested():
                return
            try:
                songs.append((str(Path(path).resolve()), load_chart(path)))
            except Exception as error:
                errors.append(f'{Path(path).name}: {error}')
            self.progress.emit(index + 1, len(self.paths))
        self.loaded.emit(songs, errors)


class UltraStarBatchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('batch.title'))
        self.resize(780, 520)
        self.worker, self.batch_result = None, None
        self.entries, self.paths = [], set()
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.files = QPushButton(qta.icon('fa5s.file-import', color='#cdd3d9'), tr('batch.files'))
        self.folder = QPushButton(qta.icon('fa5s.folder-open', color='#cdd3d9'), tr('batch.folder'))
        row.addWidget(self.files)
        row.addWidget(self.folder)
        layout.addLayout(row)
        self.files.clicked.connect(self.pick_files)
        self.folder.clicked.connect(self.pick_folder)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr('Titel'), tr('Interpret'), tr('batch.media'), tr('batch.cover')])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.name = QLineEdit('Song Pack')
        self.name.setPlaceholderText(tr('pack.name'))
        layout.addWidget(self.name)
        self.export_mode = QComboBox()
        self.export_mode.addItem(tr('pack.title'), 'pack')
        self.export_mode.addItem(tr('batch.singles'), 'singles')
        self.export_mode.currentIndexChanged.connect(self.update_buttons)
        layout.addWidget(self.export_mode)
        row = QHBoxLayout()
        self.open_button = QPushButton(tr('batch.open'))
        self.export_button = QPushButton(tr('pack.title'))
        close = QPushButton(tr('Abbrechen'))
        row.addWidget(self.open_button)
        row.addWidget(self.export_button)
        row.addWidget(close)
        layout.addLayout(row)
        self.open_button.clicked.connect(lambda: self.finish_import(False))
        self.export_button.clicked.connect(lambda: self.finish_import(True))
        close.clicked.connect(self.reject)
        self.table.itemChanged.connect(self.update_buttons)
        self.update_buttons()

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('batch.files'), '', 'UltraStar (*.txt)')
        self.read(paths)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr('batch.folder'))
        if folder:
            try:
                self.read(discover_charts(folder))
            except Exception as error:
                self.status.setText(str(error))

    def read(self, paths):
        paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        paths = [path for path in paths if path not in self.paths]
        if not paths:
            return
        if len(paths) + len(self.entries) > MAX_BATCH:
            self.status.setText(tr('batch.limit', count=MAX_BATCH))
            return
        self.worker = BatchReader(paths, self)
        self.worker.progress.connect(lambda value, total: (self.progress.setRange(0, total), self.progress.setValue(value)))
        self.worker.loaded.connect(self.receive)
        self.worker.finished.connect(self.update_buttons)
        self.progress.show()
        self.files.setEnabled(False)
        self.folder.setEnabled(False)
        self.open_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.worker.start()

    def receive(self, songs, errors):
        self.table.blockSignals(True)
        for path, project in songs:
            self.paths.add(path)
            self.entries.append(project)
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [project.title, project.artist,
                      tr('batch.video') if project.video_path else tr('batch.audio') if project.audio_path else tr('batch.missing'),
                      tr('batch.present') if project.cover_path else tr('batch.missing')]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.progress.hide()
        self.status.setText(tr('batch.loaded', count=len(self.entries), errors=len(errors)) +
                            ('\n' + '\n'.join(errors[:5]) if errors else ''))

    def selected(self):
        return [project for row, project in enumerate(self.entries)
                if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]

    def update_buttons(self):
        busy = bool(self.worker and self.worker.isRunning())
        count = len(self.selected())
        self.files.setEnabled(not busy)
        self.folder.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self.export_mode.setEnabled(not busy)
        singles = self.export_mode.currentData() == 'singles'
        self.name.setVisible(not singles)
        self.open_button.setEnabled(not busy and count > 0)
        self.export_button.setText(tr('batch.singles') if singles else tr('pack.title'))
        self.export_button.setEnabled(not busy and count > 0 and (singles or count <= 16))
        self.export_button.setToolTip(tr('pack.count_limit') if not singles and count > 16 else '')

    def finish_import(self, export):
        projects = self.selected()
        if not projects:
            return
        singles = export and self.export_mode.currentData() == 'singles'
        if export and not singles and len(projects) > 16:
            self.status.setText(tr('pack.count_limit'))
            return
        from studio.library_page import configured_library
        library_root = configured_library()
        if library_root:
            from studio.library import Library
            root = Library(library_root).root / 'workspace'
        elif export:
            root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'batch-imports' / uuid.uuid4().hex
        else:
            destination = QFileDialog.getExistingDirectory(self, tr('batch.destination'))
            if not destination:
                return
            root = Path(destination) / ('OpenLips-' + uuid.uuid4().hex[:12])
        try:
            root.mkdir(parents=True, exist_ok=True)
            for index, project in enumerate(projects):
                path = Library(library_root).draft_path(project) if library_root else root / f'{index + 1:04d}.olp'
                save_project(project, path)
        except Exception as error:
            QMessageBox.warning(self, tr('batch.title'), str(error))
            return
        self.batch_result = (projects, self.name.text().strip() or 'Song Pack', 'singles' if singles else export)
        self.accept()

    def done(self, result):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()
        super().done(result)
