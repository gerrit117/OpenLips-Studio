"""One-step DLC export: prepare project media and atomically package it."""
import copy
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QProgressBar, QLabel, QPushButton,
    QFileDialog, QLineEdit, QListWidget, QHBoxLayout)
import qtawesome as qta
from studio.exporters import internal_chart
from studio.i18n import tr


class PackageWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, project, output, parent, *, projects=None, pack_name=None):
        super().__init__(parent)
        self.project, self.output = copy.deepcopy(project), output
        self.projects = copy.deepcopy(projects) if projects is not None else [self.project]
        self.pack_name = pack_name

    def run(self):
        try:
            from studio.dlc_pack import build_projects_dlc
            result = build_projects_dlc(self.projects, self.output, self.progress.emit,
                                        pack_name=self.pack_name)
            self.completed.emit(result['output_path'])
        except Exception as error:
            self.failed.emit(str(error))


class DlcDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project, self.worker = project, None
        self.setWindowTitle(tr('DLC exportieren (experimentell)'))
        self.resize(520, 190)
        layout = QVBoxLayout(self)
        self.status = QLabel(tr('export.dlc_ready'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.preview_button = QPushButton(tr('preview.settings'))
        self.preview_button.clicked.connect(self.edit_preview)
        layout.addWidget(self.preview_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        layout.addWidget(self.progress)
        self.save_button = QPushButton(tr('export.dlc_save'))
        self.save_button.clicked.connect(self.build)
        layout.addWidget(self.save_button)
        self.usb_button = QPushButton(qta.icon('fa5b.usb', color='#cdd3d9'), tr('usb.title'))
        self.usb_button.setVisible(False)
        self.usb_button.clicked.connect(self.copy_to_usb)
        layout.addWidget(self.usb_button)
        self.output_path = None
        self.editable_controls = [self.preview_button]

    def edit_preview(self):
        parent = self.parent()
        if parent and hasattr(parent, 'edit_preview'):
            parent.edit_preview()
        else:
            from studio.preview_dialog import PreviewDialog
            dialog = PreviewDialog(self.project, self)
            if dialog.exec():
                self.project.preview_start, self.project.preview_length = dialog.values()

    def build(self):
        self.start_build([self.project])

    def start_build(self, projects, pack_name=None):
        if self.worker and self.worker.isRunning():
            return
        try:
            for project in projects:
                try:
                    internal_chart(project)
                except ValueError as error:
                    raise ValueError(f'{project.artist} - {project.title}: {error}') from error
                source = project.video_path or project.audio_path
                if not source or not Path(source).is_file():
                    raise ValueError(tr('export.need_media'))
        except Exception as error:
            self.status.setText(str(error))
            return
        path = QFileDialog.getExistingDirectory(self, tr('export.dlc_directory'))
        if not path:
            return
        self.worker = PackageWorker(self.project, path, self, projects=projects, pack_name=pack_name)
        self.worker.progress.connect(self.status.setText)
        self.worker.completed.connect(self.success)
        self.worker.failed.connect(self.failure)
        self.progress.setRange(0, 0)
        self.save_button.setEnabled(False)
        for widget in self.editable_controls:
            widget.setEnabled(False)
        self.usb_button.setVisible(False)
        self.worker.start()

    def success(self, path):
        self.output_path = path
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.status.setText(tr('export.saved', path=path))
        self.save_button.setEnabled(True)
        for widget in self.editable_controls:
            widget.setEnabled(True)
        self.usb_button.setVisible(True)

    def copy_to_usb(self):
        from studio.usb_dialog import UsbDialog
        UsbDialog(self, self.output_path).exec()

    def failure(self, message):
        self.progress.setRange(0, 1)
        self.status.setText(message)
        self.save_button.setEnabled(True)
        for widget in self.editable_controls:
            widget.setEnabled(True)

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)


class SongPackDialog(DlcDialog):
    def __init__(self, project, parent=None):
        super().__init__(project, parent)
        self.setWindowTitle(tr('pack.title'))
        self.resize(620, 470)
        self.projects = []
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr('pack.name'))
        self.layout().insertWidget(0, self.name)
        self.songs = QListWidget()
        self.layout().insertWidget(1, self.songs)
        buttons = QHBoxLayout()
        add = QPushButton(qta.icon('fa5s.plus', color='#cdd3d9'), tr('pack.add'))
        add.clicked.connect(self.add_projects)
        buttons.addWidget(add)
        remove = QPushButton(qta.icon('fa5s.trash-alt', color='#cdd3d9'), tr('pack.remove'))
        remove.clicked.connect(self.remove_project)
        buttons.addWidget(remove)
        self.layout().insertLayout(2, buttons)
        self.editable_controls += [self.name, self.songs, add, remove]
        if project.notes:
            self.append_project(copy.deepcopy(project))
        self.status.setText(tr('pack.ready'))

    def append_project(self, project):
        self.projects.append(project)
        self.songs.addItem(f'{project.artist} - {project.title}')
        if self.songs.currentRow() < 0:
            self.songs.setCurrentRow(0)

    def edit_preview(self):
        from studio.preview_dialog import PreviewDialog
        row = self.songs.currentRow()
        if row < 0:
            return
        project = self.projects[row]
        dialog = PreviewDialog(project, self)
        if dialog.exec():
            project.preview_start, project.preview_length = dialog.values()

    def add_projects(self):
        from studio.model import load_project
        paths, _ = QFileDialog.getOpenFileNames(self, tr('pack.add'), filter='OpenLips (*.olp)')
        for path in paths:
            try:
                self.append_project(load_project(path))
            except Exception as error:
                self.status.setText(str(error))

    def remove_project(self):
        row = self.songs.currentRow()
        if row >= 0:
            self.projects.pop(row)
            self.songs.takeItem(row)

    def build(self):
        if not self.name.text().strip():
            self.status.setText(tr('pack.need_name'))
        elif not 2 <= len(self.projects) <= 16:
            self.status.setText(tr('pack.count_limit'))
        else:
            self.start_build(self.projects, self.name.text().strip())
