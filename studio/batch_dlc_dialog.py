"""Sequential single-song DLC export with one destination and a batch summary."""
import copy
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QFileDialog, QPlainTextEdit

from studio.i18n import tr


class SingleDlcWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(object, object)

    def __init__(self, projects, directory, parent=None):
        super().__init__(parent)
        self.projects = copy.deepcopy(projects)
        self.directory = Path(directory)
        from studio.library_page import configured_library
        self.library_root = configured_library()

    def run(self):
        from studio.dlc_pack import build_projects_dlc
        outputs, errors = [], []
        for index, project in enumerate(self.projects):
            if self.isInterruptionRequested():
                break
            label = f'{project.artist} - {project.title}'
            def report(message):
                if self.isInterruptionRequested():
                    raise InterruptedError('Cancelled')
                self.progress.emit(index, f'{index + 1}/{len(self.projects)}: {label}\n{message}')
            try:
                report('')
                result = build_projects_dlc([project], self.directory, report, optimize_pages=True)
                outputs.append(result['output_path'])
                if self.library_root:
                    try:
                        from studio.library import Library
                        library = Library(self.library_root)
                        identifier = library.add_project(project)
                        package = library.add_package(result['output_path'], [identifier])
                        library.record_build(package, [identifier], None, True)
                    except Exception as error:
                        errors.append(tr('library.archive_failed', error=f'{label}: {error}'))
            except InterruptedError:
                break
            except Exception as error:
                errors.append(f'{label}: {error}')
            self.progress.emit(index + 1, label)
        self.completed.emit(outputs, errors)


class SingleDlcBatchDialog(QDialog):
    def __init__(self, projects, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('batch.singles'))
        self.resize(620, 240)
        self.projects, self.worker = projects, None
        self.output_paths = []
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(projects))
        layout.addWidget(self.progress)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setVisible(False)
        layout.addWidget(self.errors)
        self.button = QPushButton(tr('export.dlc_save'))
        self.button.clicked.connect(self.start_or_cancel)
        layout.addWidget(self.button)

    def start_or_cancel(self):
        if self.worker:
            if self.worker.isRunning():
                self.worker.requestInterruption()
                self.button.setEnabled(False)
                self.status.setText(tr('batch.stopping'))
            else:
                self.accept()
            return
        from studio.library_setup import export_directory
        directory = export_directory() or QFileDialog.getExistingDirectory(self, tr('export.dlc_directory'))
        if not directory:
            return
        self.worker = SingleDlcWorker(self.projects, directory, self)
        self.worker.progress.connect(lambda value, message: (self.progress.setValue(value), self.status.setText(message)))
        self.worker.completed.connect(self.finished_batch)
        self.worker.finished.connect(lambda: self.button.setEnabled(True))
        self.button.setText(tr('Abbrechen'))
        self.worker.start()

    def finished_batch(self, outputs, errors):
        self.output_paths = outputs
        self.status.setText(tr('batch.exported', count=len(outputs), errors=len(errors)))
        self.errors.setPlainText('\n'.join(errors))
        self.errors.setVisible(bool(errors))
        self.button.setText(tr('batch.close'))

    def done(self, result):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.button.setEnabled(False)
            self.status.setText(tr('batch.stopping'))
            return
        super().done(result)
