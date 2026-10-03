"""Explicit selection and verified copy to Xbox Content USB storage."""
from pathlib import Path

from PySide6.QtCore import QStorageInfo, QThread, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QLabel, QPushButton, QProgressBar, QVBoxLayout

from studio.i18n import tr
from tools.install_dlc_usb import content_directory, install_package


def xbox_volumes():
    result = []
    for volume in QStorageInfo.mountedVolumes():
        if not volume.isValid() or not volume.isReady() or volume.isReadOnly():
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


class UsbDialog(QDialog):
    def __init__(self, parent=None, package=None):
        super().__init__(parent)
        self.worker = None
        self.package = Path(package) if package else None
        self.setWindowTitle(tr('usb.title'))
        self.resize(560, 240)
        layout = QVBoxLayout(self)
        self.package_label = QLabel(str(self.package or ''))
        self.package_label.setWordWrap(True)
        layout.addWidget(self.package_label)
        self.choose = QPushButton(tr('usb.choose_package'))
        self.choose.clicked.connect(self.select_package)
        layout.addWidget(self.choose)
        self.drives = QComboBox()
        layout.addWidget(self.drives)
        self.refresh_button = QPushButton(tr('usb.refresh'))
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.copy_button = QPushButton(tr('usb.copy'))
        self.copy_button.clicked.connect(self.copy)
        layout.addWidget(self.copy_button)
        self.refresh()

    def refresh(self):
        self.drives.clear()
        for volume in xbox_volumes():
            self.drives.addItem(f'{volume.rootPath()}  {volume.displayName()}  '
                f'{volume.bytesAvailable() / (1024 ** 3):.1f} GB', volume.rootPath())
        self.status.setText(tr('usb.ready') if self.drives.count() else tr('usb.no_drive'))
        self.copy_button.setEnabled(bool(self.package and self.drives.count()))

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
        for widget in (self.choose, self.copy_button, self.refresh_button, self.drives):
            widget.setEnabled(False)
        self.status.setText(tr('usb.copying'))
        self.worker.start()

    def finished_copy(self, message, success):
        self.progress.setValue(100 if success else 0)
        self.status.setText(message)
        for widget in (self.choose, self.copy_button, self.refresh_button, self.drives):
            widget.setEnabled(True)

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
