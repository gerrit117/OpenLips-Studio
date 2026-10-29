"""A lyric document with occurrence highlighting and native word dragging."""
import hashlib
import json
import re

from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QDrag
from PySide6.QtWidgets import QTextEdit, QApplication

WORD_MIME = 'application/x-openlips-lyric-word'


def python_position(text, position):
    return len(text.encode('utf-16-le')[:position*2].decode('utf-16-le', errors='ignore'))


def qt_position(text, position):
    return len(text[:position].encode('utf-16-le'))//2


def word_payload(text, start, end):
    return dict(start=start, end=end, text=text[start:end],
                document=hashlib.sha256(text.encode('utf-8')).hexdigest())


def valid_payload(payload, text):
    from studio.lyric_mapping import tokens
    return (isinstance(payload, dict) and type(payload.get('start')) is int and
        type(payload.get('end')) is int and
        (payload['start'], payload['end']) in {(a, b) for a, b, _ in tokens(text)} and
        payload == word_payload(text, payload['start'], payload['end']))


class LyricDocument(QTextEdit):
    word_activated = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setReadOnly(True)
        self.setAcceptDrops(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setStyleSheet('QTextEdit { padding: 14px; font-size: 17px; border: 0; background: #23282d; }')
        self.project = None
        self.links = {}
        self.press = None
        self.press_word = None
        self.dragged = False
        self.cached_project = None
        self.units = []
        self.last_highlight = None

    def span_at(self, point):
        text = self.toPlainText()
        position = python_position(text, self.cursorForPosition(point).position())
        return next(((m.start(), m.end()) for m in re.finditer(r'\S+', text)
                     if m.start() <= position < m.end()), None)

    def mousePressEvent(self, event):
        self.press = event.position().toPoint()
        self.press_word = self.span_at(self.press) if self.isReadOnly() else None
        self.dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.press_word and event.buttons() & Qt.MouseButton.LeftButton and not self.dragged:
            if (event.position().toPoint()-self.press).manhattanLength() >= QApplication.startDragDistance():
                self.dragged = True
                mime = QMimeData()
                mime.setData(WORD_MIME, json.dumps(word_payload(self.toPlainText(), *self.press_word)).encode('utf-8'))
                mime.setText(self.toPlainText()[slice(*self.press_word)])
                drag = QDrag(self)
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.CopyAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.press_word and not self.dragged and event.button() == Qt.MouseButton.LeftButton:
            self.word_activated.emit(*self.press_word)
        self.press_word = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(WORD_MIME):
            event.acceptProposedAction()
        elif not self.isReadOnly():
            super().dragEnterEvent(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(WORD_MIME):
            return super().dropEvent(event) if not self.isReadOnly() else event.ignore()
        try:
            payload = json.loads(bytes(event.mimeData().data(WORD_MIME)))
            text = self.toPlainText()
            if not valid_payload(payload, text):
                return event.ignore()
            start, end = payload['start'], payload['end']
            destination = python_position(text, self.cursorForPosition(event.position().toPoint()).position())
            for match in re.finditer(r'\S+', text):
                if match.start() < destination < match.end():
                    destination = match.start() if destination-match.start() <= match.end()-destination else match.end()
                    break
            if start <= destination <= end:
                return event.ignore()
            # Relocate one complete word, preserving stanza breaks and document undo.
            if end < len(text) and text[end] == ' ':
                end += 1
            elif start and text[start-1] == ' ':
                start -= 1
            cursor = QTextCursor(self.document())
            cursor.beginEditBlock()
            cursor.setPosition(qt_position(text, start))
            cursor.setPosition(qt_position(text, end), QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            if destination > end:
                destination -= end-start
            remaining = self.toPlainText()
            cursor.setPosition(qt_position(remaining, destination))
            before = ' ' if destination and not remaining[destination-1].isspace() else ''
            after = ' ' if destination < len(remaining) and not remaining[destination].isspace() else ''
            cursor.insertText(before + payload['text'] + after)
            cursor.endEditBlock()
            event.acceptProposedAction()
        except (ValueError, TypeError, KeyError):
            event.ignore()

    def highlight(self, project, selected_id='', position=None):
        from studio.lyric_mapping import lyric_links, note_words, tokens
        self.project = project
        if position is None or project is not self.cached_project:
            self.links = lyric_links(project)
            self.units = note_words(project.ordered())
            self.cached_project = project
        text = self.toPlainText()
        if text != (project.draft_lyrics or project.lyric_text()):
            self.setExtraSelections([])
            return
        selected = None
        for unit in self.units:
            active = (any(n.id == selected_id for n in unit['notes']) if position is None else
                      any(n.time <= position < n.time+n.length for n in unit['notes']))
            if active:
                selected = self.links.get(unit['notes'][0].id)
                break
        signature = (id(project), selected, text)
        if position is not None and signature == self.last_highlight:
            return
        self.last_highlight = signature
        assigned = set(self.links.values())
        selections = []
        for start, end, _ in tokens(text):
            selection = QTextEdit.ExtraSelection()
            cursor = QTextCursor(self.document())
            cursor.setPosition(qt_position(text, start))
            cursor.setPosition(qt_position(text, end), QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor
            fmt = QTextCharFormat()
            if (start, end) == selected:
                fmt.setBackground(QColor('#ed8093'))
                fmt.setForeground(QColor('#191c20'))
            elif (start, end) in assigned:
                fmt.setForeground(QColor('#d4dade'))
            else:
                fmt.setUnderlineColor(QColor('#e2b352'))
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DotLine)
            selection.format = fmt
            selections.append(selection)
        self.setExtraSelections(selections)
