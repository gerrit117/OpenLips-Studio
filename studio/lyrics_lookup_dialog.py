"""Timed-lyrics lookup usable before a Studio project exists."""
from pathlib import Path
import uuid

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLineEdit, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QPlainTextEdit)

from studio.i18n import tr
from studio.lrc import parse_lrc
from studio.lyrics_search import LyricsSearch


class LyricsLookupDialog(QDialog):
    def __init__(self, parent=None, title='', artist=''):
        super().__init__(parent)
        self.setWindowTitle(tr('Lyrics suchen'))
        self.resize(720, 560)
        self.worker = None
        self.closing = False
        self.lrc_path = None
        self.document = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = QLineEdit(title)
        self.artist_edit = QLineEdit(artist)
        form.addRow(tr('Titel'), self.title_edit)
        form.addRow(tr('Artist'), self.artist_edit)
        layout.addLayout(form)
        notice = QLabel(tr('lookup.notice'))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.search = QPushButton(tr('Lyrics suchen'))
        self.search.clicked.connect(self.start_search)
        layout.addWidget(self.search)
        self.results = QTreeWidget()
        self.results.setHeaderLabels([tr('Artist'), tr('Titel'), tr('lookup.duration')])
        self.results.currentItemChanged.connect(self.select_result)
        layout.addWidget(self.results, 1)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch()
        self.cancel = QPushButton(tr('Abbrechen'))
        self.cancel.clicked.connect(self.reject)
        self.use = QPushButton(tr('lookup.use'))
        self.use.setEnabled(False)
        self.use.clicked.connect(self.use_result)
        row.addWidget(self.cancel)
        row.addWidget(self.use)
        layout.addLayout(row)

    def start_search(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.title_edit.text().strip():
            self.title_edit.setFocus()
            return
        self.results.clear()
        self.preview.clear()
        self.use.setEnabled(False)
        self.search.setEnabled(False)
        self.status.setText(tr('Lyrics-Suche laeuft ...'))
        self.worker = LyricsSearch(self.title_edit.text().strip(), self.artist_edit.text().strip(), self)
        self.worker.results.connect(self.show_results)
        self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(self.search_finished)
        self.worker.start()

    def search_finished(self):
        self.search.setEnabled(True)
        if self.closing:
            super().reject()

    def show_results(self, records):
        for record in records:
            lyrics = record.get('syncedLyrics')
            if not isinstance(lyrics, str) or not lyrics.strip():
                continue
            item = QTreeWidgetItem([str(record.get('artistName', '')),
                str(record.get('trackName', '')), str(record.get('duration', ''))])
            item.setData(0, Qt.ItemDataRole.UserRole, record)
            self.results.addTopLevelItem(item)
        self.status.setText('' if self.results.topLevelItemCount() else tr('lookup.empty'))
        if self.results.topLevelItemCount():
            self.results.setCurrentItem(self.results.topLevelItem(0))

    def select_result(self, item, *_):
        self.use.setEnabled(bool(item))
        self.preview.setPlainText(item.data(0, Qt.ItemDataRole.UserRole)['syncedLyrics'] if item else '')

    def use_result(self):
        item = self.results.currentItem()
        if not item:
            return
        try:
            record = item.data(0, Qt.ItemDataRole.UserRole)
            def metadata(value):
                return str(value).replace('\n', ' ').replace('\r', ' ').replace('[', '').replace(']', '')
            text = (f"[ti:{metadata(record.get('trackName', ''))}]\n"
                    f"[ar:{metadata(record.get('artistName', ''))}]\n" + record['syncedLyrics'])
            document = parse_lrc(text)
            folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'lyrics'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (uuid.uuid4().hex + '.lrc')
            path.write_text(text, encoding='utf-8')
            self.lrc_path, self.document = path, document
            self.accept()
        except (ValueError, OSError) as error:
            self.status.setText(str(error))

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.worker.requestInterruption()
            self.status.setText(tr('lookup.cancelling'))
            self.cancel.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)
