"""Local and remote library modes share one optional Studio workspace."""
from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
    QStackedWidget, QPushButton, QFileDialog)
import qtawesome as qta
from pathlib import Path

from studio.library_page import LibraryPage
from studio.remote_library import RemoteLibraryPage
from studio.i18n import tr


class LibraryWorkspace(QWidget):
    project_opened = Signal(str)
    community_upload_requested = Signal(object)
    def __init__(self, project_getter, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems([tr('library.local'), tr('library.remote')])
        row.addWidget(self.mode)
        row.addStretch()
        self.location = QPushButton(qta.icon('fa5s.folder-open', color='#cdd3d9'), tr('library.directory'))
        self.location.clicked.connect(self.change_location)
        row.addWidget(self.location)
        layout.addLayout(row)
        self.stack = QStackedWidget()
        self.local = LibraryPage(project_getter, self)
        self.remote = RemoteLibraryPage(project_getter, self, library_getter=lambda: self.local.library)
        self.local.community_upload_requested.connect(self.community_upload_requested.emit)
        self.remote.community_upload_requested.connect(self.community_upload_requested.emit)
        self.local.sync_requested.connect(self.sync)
        for page in (self.local, self.remote):
            page.project_opened.connect(self.project_opened.emit)
            self.stack.addWidget(page)
        layout.addWidget(self.stack)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.mode.setCurrentIndex(QSettings('OpenLips', 'OpenLips Studio').value('library/mode', 0, type=int))

    def sync(self):
        self.mode.setCurrentIndex(1)
        if self.remote.client:
            self.remote.synchronize()
        else:
            self.remote.status.setText(tr('remote.ready'))

    @property
    def library(self):
        return self.local.library

    @property
    def worker(self):
        for page in (self.local, self.remote):
            if page.worker and page.worker.isRunning():
                return page.worker
        return None

    def change_mode(self, index):
        if self.worker:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.stack.currentIndex())
            self.mode.blockSignals(False)
            return
        self.stack.setCurrentIndex(index)
        self.location.setVisible(index == 0)
        QSettings('OpenLips', 'OpenLips Studio').setValue('library/mode', index)

    def change_location(self):
        if self.worker:
            return
        from studio.library_setup import LibrarySetupDialog
        if LibrarySetupDialog(self).exec():
            from studio.library import Library
            root = Path(str(QSettings('OpenLips', 'OpenLips Studio').value('library/root')))
            try:
                library = Library(root)
            except Exception as error:
                self.local.status.setText(str(error))
                return
            QSettings('OpenLips', 'OpenLips Studio').setValue('library/root', str(root))
            self.local.library = library
            self.local.refresh()
