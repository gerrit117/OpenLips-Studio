"""Explicit selection and verified copy to Xbox Content USB storage."""
from pathlib import Path

from PySide6.QtCore import QStorageInfo, QThread, Signal, Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QLabel, QPushButton,
    QProgressBar, QVBoxLayout, QTabWidget, QWidget, QTreeWidget, QTreeWidgetItem, QMessageBox, QMenu)
import qtawesome as qta

from studio.i18n import tr
from tools.install_dlc_usb import content_directory, install_package


def xbox_volumes(*, include_read_only=False):
    result = []
    for volume in QStorageInfo.mountedVolumes():
        if not volume.isValid() or not volume.isReady() or volume.isReadOnly() and not include_read_only:
            continue
        if bytes(volume.fileSystemType()).lower() not in (b'fat32', b'vfat', b'msdos', b'fat'):
            continue
        try:
            content_directory(volume.rootPath())
        except (OSError, ValueError):
            continue
        result.append(volume)
    return result


class UsbWorker(QThread):
    progress = Signal(int)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, package, root, parent):
        super().__init__(parent)
        self.package, self.root = package, root

    def run(self):
        try:
            matches = [v for v in xbox_volumes() if v.rootPath() == self.root]
            if not matches:
                raise ValueError(tr('usb.no_drive'))
            target = install_package(self.package, self.root,
                lambda copied, total: self.progress.emit(min(99, copied * 100 // total)))
            self.completed.emit(str(target))
        except Exception as error:
            self.failed.emit(str(error))


class CatalogWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, root, library, parent):
        super().__init__(parent)
        self.root, self.library = root, library

    def run(self):
        try:
            from studio.usb_catalog import scan_usb
            self.completed.emit(scan_usb(self.root, self.library.packages() if self.library else ()))
        except Exception as error:
            self.failed.emit(str(error))


class UsbDialog(QDialog):
    def __init__(self, parent=None, package=None, *, library=None, browse=False):
        super().__init__(parent)
        self.worker = None
        self.package = Path(package) if package else None
        self.library = library
        self.entries = []
        self.setWindowTitle(tr('usb.manage'))
        self.resize(940, 550)
        layout = QVBoxLayout(self)
        self.drives = QComboBox()
        self.drives.currentIndexChanged.connect(self.scan)
        layout.addWidget(self.drives)
        self.refresh_button = QPushButton(tr('usb.refresh'))
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        contents = QWidget()
        inventory = QVBoxLayout(contents)
        self.contents = QTreeWidget()
        self.contents.setHeaderLabels([tr('library.package'), tr('library.date'), tr('usb.copied'), tr('usb.local'), tr('usb.version')])
        self.contents.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.contents.customContextMenuRequested.connect(self.context_menu)
        inventory.addWidget(self.contents)
        self.remove_button = QPushButton(qta.icon('fa5s.trash-alt', color='#cdd3d9'), tr('usb.remove'))
        self.remove_button.clicked.connect(self.remove_selected)
        self.contents.itemSelectionChanged.connect(self.update_controls)
        inventory.addWidget(self.remove_button)
        self.tabs.addTab(contents, tr('usb.contents'))
        copying = QWidget()
        copy_layout = QVBoxLayout(copying)
        self.package_label = QLabel(str(self.package or ''))
        self.package_label.setWordWrap(True)
        copy_layout.addWidget(self.package_label)
        self.choose = QPushButton(tr('usb.choose_package'))
        self.choose.clicked.connect(self.select_package)
        copy_layout.addWidget(self.choose)
        copy_layout.addStretch()
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.copy_button = QPushButton(tr('usb.copy'))
        self.copy_button.clicked.connect(self.copy)
        copy_layout.addWidget(self.copy_button)
        self.tabs.addTab(copying, tr('usb.title'))
        self.tabs.setCurrentIndex(0 if browse else 1)
        self.refresh()

    def refresh(self):
        previous = self.drives.currentData()
        self.drives.blockSignals(True)
        self.drives.clear()
        for volume in xbox_volumes(include_read_only=True):
            self.drives.addItem(f'{volume.rootPath()}  {volume.displayName()}  '
                f'{volume.bytesAvailable() / (1024 ** 3):.1f} GB', volume.rootPath())
        found = self.drives.findData(previous)
        if found >= 0:
            self.drives.setCurrentIndex(found)
        self.drives.blockSignals(False)
        self.status.setText(tr('usb.ready') if self.drives.count() else tr('usb.no_drive'))
        self.scan()

    def update_controls(self):
        busy = bool(self.worker and self.worker.isRunning())
        writable = any(v.rootPath() == self.drives.currentData() for v in xbox_volumes())
        self.copy_button.setEnabled(bool(self.package and writable and not busy))
        self.remove_button.setEnabled(bool(self.contents.selectedItems() and writable and not busy))

    def scan(self):
        if self.worker and self.worker.isRunning():
            return
        self.contents.clear()
        self.entries = []
        root = self.drives.currentData()
        if not root:
            self.update_controls()
            return
        self.status.setText(tr('usb.scanning'))
        self.worker = CatalogWorker(root, self.library, self)
        self.worker.completed.connect(self.show_contents)
        self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(self.enable_controls)
        self.set_controls(False)
        self.worker.start()

    def show_contents(self, entries):
        from studio.usb_catalog import display_date, file_date
        self.entries = entries
        for entry in entries:
            item = QTreeWidgetItem([entry.title, display_date(entry.built), file_date(entry.copied),
                                   tr('usb.local_' + entry.local), tr('usb.version_' + entry.revision)])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(0, str(entry.path) + ('\n' + entry.error if entry.error else ''))
            item.setToolTip(1, tr('usb.date_hint'))
            self.contents.addTopLevelItem(item)
            for song in entry.songs:
                item.addChild(QTreeWidgetItem([song['artist'] + ' - ' + song['title']]))
        self.contents.setColumnWidth(0, 340)
        for column in range(1, 5):
            self.contents.resizeColumnToContents(column)
        self.status.setText(tr('usb.inventory', count=len(entries)))

    def set_controls(self, enabled):
        for widget in (self.choose, self.copy_button, self.refresh_button, self.drives, self.remove_button):
            widget.setEnabled(enabled)

    def enable_controls(self):
        self.set_controls(True)
        self.update_controls()

    def context_menu(self, pos):
        item = self.contents.itemAt(pos)
        if not item or self.worker and self.worker.isRunning():
            return
        self.contents.setCurrentItem(item)
        menu = QMenu(self)
        action = menu.addAction(tr('usb.remove'), self.remove_selected)
        action.setEnabled(self.remove_button.isEnabled())
        menu.exec(self.contents.viewport().mapToGlobal(pos))

    def remove_selected(self):
        if self.worker and self.worker.isRunning():
            return
        item = self.contents.currentItem()
        if not item:
            return
        while item.parent():
            item = item.parent()
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        root = self.drives.currentData()
        if not any(v.rootPath() == root for v in xbox_volumes()):
            return
        if QMessageBox.question(self, tr('usb.remove'), tr('usb.confirm_remove',
            title=entry.title, count=len(entry.songs)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            from studio.usb_catalog import delete_package
            delete_package(root, entry)
            self.scan()
        except Exception as error:
            self.status.setText(str(error))

    def select_package(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('usb.choose_package'))
        if path:
            self.package = Path(path)
            self.package_label.setText(path)
            self.refresh()

    def copy(self):
        root = self.drives.currentData()
        if not root or not self.package:
            return
        self.worker = UsbWorker(self.package, root, self)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.failed.connect(lambda message: self.finished_copy(message, False))
        self.worker.completed.connect(lambda path: self.finished_copy(tr('usb.saved', path=path), True))
        self.worker.finished.connect(self.enable_controls)
        self.worker.finished.connect(self.scan)
        self.set_controls(False)
        self.status.setText(tr('usb.copying'))
        self.worker.start()

    def finished_copy(self, message, success):
        self.progress.setValue(100 if success else 0)
        self.status.setText(message)

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
