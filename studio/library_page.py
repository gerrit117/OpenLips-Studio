"""Optional local library workspace; retaining files never implies publishing them."""
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QFileDialog, QTabWidget, QTreeWidget, QTreeWidgetItem, QLabel, QMenu)
import qtawesome as qta

from studio.i18n import tr
from studio.library import Library, default_library_root
from studio.model import load_project


def configured_library():
    settings = QSettings('OpenLips', 'OpenLips Studio')
    if not settings.value('library/enabled', False, type=bool):
        return None
    return Path(str(settings.value('library/root', str(default_library_root()))))


class LibraryTask(QThread):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, callback, parent):
        super().__init__(parent)
        self.callback = callback

    def run(self):
        try:
            self.completed.emit(self.callback(self.progress.emit))
        except Exception as error:
            self.failed.emit(str(error))


class LibraryPage(QWidget):
    project_opened = Signal(str)
    community_upload_requested = Signal(object)
    sync_requested = Signal()

    def __init__(self, project_getter, parent=None, *, root=None):
        super().__init__(parent)
        self.get_project = project_getter
        self.worker = None
        self.library = Library(root or configured_library() or default_library_root())
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('library.search'))
        self.search.textChanged.connect(self.filter)
        top.addWidget(self.search, 1)
        refresh = QPushButton(qta.icon('fa5s.sync-alt', color='#cdd3d9'), '')
        refresh.setToolTip(tr('library.refresh'))
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        usb = QPushButton(qta.icon('fa5b.usb', color='#cdd3d9'), tr('usb.manage'))
        usb.clicked.connect(self.manage_usb)
        top.addWidget(usb)
        layout.addLayout(top)
        self.tabs = QTabWidget()
        self.projects = QTreeWidget()
        self.projects.setHeaderLabels([tr('Artist'), tr('Titel'), tr('library.date'), tr('library.status'), tr('library.version'), tr('library.packages')])
        self.projects.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.packages = QTreeWidget()
        self.packages.setHeaderLabels([tr('library.package'), tr('library.songs'), tr('library.date'), tr('library.index_date'), 'MiB'])
        self.packages.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tabs.addTab(self.projects, tr('library.projects'))
        self.tabs.addTab(self.packages, tr('library.packages'))
        self.tabs.currentChanged.connect(self.update_export_label)
        layout.addWidget(self.tabs, 1)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.details)
        self.packages.itemSelectionChanged.connect(self.selection)
        self.projects.itemSelectionChanged.connect(self.update_commands)
        self.tabs.currentChanged.connect(self.update_commands)
        self.tabs.currentChanged.connect(self.selection)
        for tree in (self.projects, self.packages):
            tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda pos, view=tree: self.context_menu(view, pos))
        self.projects.itemDoubleClicked.connect(lambda *_: self.open_project())
        row = QHBoxLayout()
        self.buttons = []
        for label, icon, callback in [('library.add_current', 'fa5s.plus', self.add_current),
                                      ('library.import', 'fa5s.file-import', self.import_projects),
                                      ('library.import_package', 'fa5s.box', self.import_packages)]:
            button = QPushButton(qta.icon(icon, color='#cdd3d9'), tr(label))
            button.clicked.connect(callback)
            self.buttons.append(button)
            row.addWidget(button)
        layout.addLayout(row)
        commands = QHBoxLayout()
        self.command_buttons = {}
        for index, (label, icon, callback) in enumerate([('library.open', 'fa5s.folder-open', self.open_project),
                                      ('library.export', 'fa5s.file-export', self.export),
                                      ('xbox.title', 'fa5s.upload', self.copy),
                                      ('usb.title', 'fa5b.usb', self.copy_usb),
                                      ('library.community_upload', 'fa5s.users', self.upload_community),
                                      ('server.title', 'fa5s.server', self.server)]):
            if index == 3:
                layout.addLayout(commands)
                commands = QHBoxLayout()
            button = QPushButton(qta.icon(icon, color='#cdd3d9'), tr(label))
            button.clicked.connect(callback)
            self.buttons.append(button)
            commands.addWidget(button)
            self.command_buttons[label] = button
            if label == 'library.export':
                self.export_button = button
        layout.addLayout(commands)
        self.status = QLabel(str(self.library.root))
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.refresh()

    def update_commands(self):
        if not hasattr(self, 'command_buttons'):
            return
        busy = bool(self.worker and self.worker.isRunning())
        projects = len(self.projects.selectedItems()) if self.tabs.currentWidget() is self.projects else 0
        packages = len(self.packages.selectedItems()) if self.tabs.currentWidget() is self.packages else 0
        for key, enabled in {'library.open': projects == 1, 'library.export': bool(projects or packages),
                'xbox.title': packages == 1, 'usb.title': packages == 1,
                'library.community_upload': projects == 1, 'server.title': True}.items():
            self.command_buttons[key].setEnabled(enabled and not busy)

    def update_export_label(self):
        if hasattr(self, 'export_button'):
            self.export_button.setText(tr('library.export_packages' if self.tabs.currentWidget() is self.packages else 'library.export'))

    def context_menu(self, tree, pos):
        item = tree.itemAt(pos)
        if not item or self.worker and self.worker.isRunning():
            return
        if not item.isSelected():
            tree.clearSelection()
            item.setSelected(True)
        menu = QMenu(self)
        commands = ([('library.open', self.open_project), ('library.export', self.export),
                     ('library.community_upload', self.upload_community)] if tree is self.projects else
                    [('library.export_packages', self.export), ('xbox.title', self.copy), ('usb.title', self.copy_usb)])
        for label, callback in commands:
            menu.addAction(tr(label), callback)
        menu.addSeparator()
        menu.addAction(tr('remote.sync'), self.sync_requested.emit)
        menu.exec(tree.viewport().mapToGlobal(pos))

    def upload_community(self):
        selected = self.projects.selectedItems() if self.tabs.currentWidget() is self.projects else []
        if len(selected) == 1:
            try:
                self.community_upload_requested.emit(load_project(self.library.project_path(
                    selected[0].data(0, Qt.ItemDataRole.UserRole))))
            except Exception as error:
                self.status.setText(str(error))
        else:
            self.status.setText(tr('library.choose_project'))

    def refresh(self):
        from studio.usb_catalog import display_date, file_date
        self.projects.clear()
        records = self.library.projects()
        latest = {}
        for record in records:
            key = record['artist'].casefold(), record['title'].casefold()
            latest[key] = max(latest.get(key, ''), record['modified'])
        for record in records:
            key = record['artist'].casefold(), record['title'].casefold()
            version = 'library.latest' if record['modified'] == latest[key] else 'library.older'
            item = QTreeWidgetItem([record['artist'], record['title'], display_date(record['modified']),
                tr('library.' + record['status']), tr(version), str(record['packages'])])
            item.setData(0, Qt.ItemDataRole.UserRole, record['id'])
            item.setToolTip(1, str(self.library.project_path(record['id'])))
            self.projects.addTopLevelItem(item)
        self.packages.clear()
        for record in self.library.packages():
            item = QTreeWidgetItem([record['title'], str(len(record['songs'])), display_date(record['built']),
                file_date(record['created']), f"{record['bytes'] / 1024 ** 2:.1f}"])
            item.setData(0, Qt.ItemDataRole.UserRole, record)
            item.setToolTip(0, str(self.library.package_path(record['id'])))
            item.setToolTip(2, tr('usb.date_hint'))
            self.packages.addTopLevelItem(item)
        for tree in (self.projects, self.packages):
            for column in range(tree.columnCount()):
                tree.resizeColumnToContents(column)
        self.filter()
        self.update_commands()

    def filter(self):
        query = self.search.text().casefold()
        for tree in (self.projects, self.packages):
            for index in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(index)
                text = ' '.join(item.text(c) for c in range(tree.columnCount()))
                if tree is self.packages:
                    record = item.data(0, Qt.ItemDataRole.UserRole)
                    text += ' '.join(song['artist'] + ' ' + song['title'] for song in record['songs'])
                item.setHidden(query not in text.casefold())

    def selection(self):
        selected = self.packages.selectedItems() if self.tabs.currentWidget() is self.packages else []
        record = selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else None
        self.details.setText('\n'.join(song['artist'] + ' - ' + song['title']
                            for song in record['songs']) if record else '')
        self.update_commands()

    def task(self, callback):
        if self.worker and self.worker.isRunning():
            return
        self.worker = LibraryTask(callback, self)
        self.worker.progress.connect(self.status.setText)
        self.worker.completed.connect(lambda _: self.finish(tr('library.saved')))
        self.worker.failed.connect(self.finish)
        self.worker.finished.connect(self.update_commands)
        for button in self.buttons:
            button.setEnabled(False)
        self.worker.start()

    def finish(self, message):
        self.status.setText(message)
        for button in self.buttons:
            button.setEnabled(True)
        self.refresh()

    def add_current(self):
        import copy
        from datetime import datetime, timezone
        project = copy.deepcopy(self.get_project())
        project.modified_at = datetime.now(timezone.utc).isoformat(timespec='microseconds')
        self.task(lambda progress: self.library.add_project(project, progress))

    def import_projects(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('library.import'), filter='OpenLips (*.olp)')
        if paths:
            self.task(lambda progress: [self.library.add_project(load_project(path), progress) for path in paths])

    def import_packages(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('library.import_package'))
        if paths:
            self.task(lambda progress: [self.library.add_package(path, progress=progress) for path in paths])

    def open_project(self):
        selected = self.projects.selectedItems() if self.tabs.currentWidget() is self.projects else []
        if selected:
            self.project_opened.emit(str(self.library.project_path(selected[0].data(0, Qt.ItemDataRole.UserRole))))

    def export(self):
        if self.tabs.currentWidget() is self.packages:
            selected = self.packages.selectedItems()
            if not selected:
                return
            directory = QFileDialog.getExistingDirectory(self, tr('library.export_packages'))
            if directory:
                identifiers = [item.data(0, Qt.ItemDataRole.UserRole)['id'] for item in selected]
                from studio.library_sync import copy_packages
                self.task(lambda progress: copy_packages(self.library, identifiers, directory, progress))
            return
        selected = self.projects.selectedItems()
        projects = [load_project(self.library.project_path(item.data(0, Qt.ItemDataRole.UserRole))) for item in selected]
        if not projects:
            return
        from studio.dlc_dialog import DlcDialog, SongPackDialog
        if len(projects) == 1:
            DlcDialog(projects[0], self).exec()
        else:
            dialog = SongPackDialog(projects[0], self)
            for project in projects[1:]:
                dialog.append_project(project)
            dialog.exec()
        self.refresh()

    def copy(self):
        selected = self.packages.selectedItems() if self.tabs.currentWidget() is self.packages else []
        if selected:
            from studio.xbox_dialog import XboxDialog
            XboxDialog(self, self.library.package_path(selected[0].data(0, Qt.ItemDataRole.UserRole)['id'])).exec()

    def copy_usb(self):
        selected = self.packages.selectedItems() if self.tabs.currentWidget() is self.packages else []
        if selected:
            from studio.usb_dialog import UsbDialog
            UsbDialog(self, self.library.package_path(selected[0].data(0, Qt.ItemDataRole.UserRole)['id']), library=self.library).exec()

    def manage_usb(self):
        if not self.worker or not self.worker.isRunning():
            from studio.usb_dialog import UsbDialog
            UsbDialog(self, library=self.library, browse=True).exec()

    def server(self):
        from studio.server_dialog import ServerDialog
        ServerDialog(self, self.library.root).exec()
