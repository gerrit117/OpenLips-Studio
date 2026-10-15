"""Explicit, undoable review; never silently removes intentional harmony."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QTreeWidget,QTreeWidgetItem,QDialogButtonBox,QPushButton,QHBoxLayout,QAbstractItemView
from studio.i18n import tr
from studio.model import pitch_name
from studio.note_editing import conflicts,duplicate_ids
from studio.lyric_timing import delete_notes


class NoteConflictsDialog(QDialog):
    def __init__(self,project,parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self.setWindowTitle(tr('notes.conflicts'))
        self.resize(720,420)
        layout = QVBoxLayout(self)
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setHeaderLabels([tr('chart.note'),tr('Start'),tr('Laenge'),tr('Tonname'),tr('Text'),tr('chart.problem')])
        layout.addWidget(self.table)
        row = QHBoxLayout()
        self.remove = QPushButton(tr('notes.remove_selected'))
        self.remove.clicked.connect(self.remove_selected)
        self.deduplicate = QPushButton(tr('notes.remove_duplicates'))
        self.deduplicate.clicked.connect(self.remove_duplicates)
        row.addWidget(self.remove)
        row.addWidget(self.deduplicate)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self):
        self.table.clear()
        issues = conflicts(self.project)
        for number,note in enumerate(self.project.ordered(),1):
            if note.id not in issues:
                continue
            item = QTreeWidgetItem([str(number),f'{note.time:.3f} s',f'{note.length:.3f} s',pitch_name(note.pitch),note.text,
                                   ', '.join(tr('notes.'+r) for r in sorted(issues[note.id]))])
            item.setData(0,Qt.ItemDataRole.UserRole,note.id)
            self.table.addTopLevelItem(item)
        for column in range(5):
            self.table.resizeColumnToContents(column)
        self.deduplicate.setEnabled(bool(duplicate_ids(self.project)))

    def remove_selected(self):
        ids = {item.data(0,Qt.ItemDataRole.UserRole) for item in self.table.selectedItems()}
        delete_notes(self.project,ids)
        self.refresh()

    def remove_duplicates(self):
        delete_notes(self.project,duplicate_ids(self.project))
        self.refresh()
