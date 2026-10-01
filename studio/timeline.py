"""Horizontal karaoke editor: playback scrolls the notes to the left."""
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QLineEdit

from studio.i18n import tr
from studio.model import EditorNote, pitch_name, snap_time
from tools.build_owned_chart import phrase_page_starts


class LyricField(QLineEdit):
    def __init__(self, timeline, note_id):
        super().__init__(timeline)
        self.timeline, self.note_id = timeline, note_id
        self.session_started = False
        self.setStyleSheet('QLineEdit { background: #1b2025; color: #edf1f4; border: 1px solid #48545e; padding: 2px; } QLineEdit:focus { border: 1px solid #ef599c; }')
        self.textEdited.connect(self.commit)
        self.editingFinished.connect(lambda: setattr(self, 'session_started', False))

    def focusInEvent(self, event):
        self.timeline.selected_id = self.note_id
        self.timeline.selected.emit(self.note_id)
        super().focusInEvent(event)

    def commit(self, text):
        n = next((n for n in self.timeline.project.notes if n.id == self.note_id), None)
        if not n or n.text == text:
            return
        if not self.session_started:
            self.timeline.before_edit.emit()
            self.session_started = True
        n.text = text.replace('\x00', '')
        self.timeline.edited.emit()

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        parameters = menu.addAction(tr('Notenparameter'))
        parameters.triggered.connect(lambda: self.timeline.selected.emit(self.note_id))
        menu.exec(event.globalPos())


class Timeline(QWidget):
    selected = Signal(str)
    edited = Signal()
    before_edit = Signal()
    edit_text = Signal(str)
    seek = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.selected_id = ''
        self.scale = 100.0
        self.origin = 0.0
        self.cursor = 0.0
        self.follow = True
        self.snap = True
        self.low, self.high = 48, 78
        self.drag = None
        self.video_frame = None
        self.show_video = True
        self.lyric_fields = {}
        self.setMinimumSize(400, 280)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_project(self, project):
        if self.project is not project:
            for field in self.lyric_fields.values():
                field.hide()
                field.deleteLater()
            self.lyric_fields.clear()
        self.project = project
        pitches = [n.pitch for n in project.notes]
        self.low = max(0, min(pitches, default=54) - 4)
        self.high = min(127, max(self.low + 23, max(pitches, default=72) + 4))
        self.update()

    def geometry_for(self, note):
        lane = (self.height() - 92) / (self.high - self.low + 1)
        return QRectF(62 + (note.time - self.origin) * self.scale,
                      38 + (self.high - note.pitch) * lane + 2,
                      max(5, note.length * self.scale), max(4, lane - 4))

    def set_cursor(self, seconds):
        self.cursor = seconds
        if self.follow:
            self.origin = max(0, seconds - max(0, self.width() - 62) * .25 / self.scale)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#191c20'))
        video = self.show_video and self.video_frame is not None and not self.video_frame.isNull()
        if video:
            frame = self.video_frame
            ratio = min((self.width() - 62) / frame.width(), (self.height() - 92) / frame.height())
            w, h = frame.width() * ratio, frame.height() * ratio
            p.drawImage(QRectF(62 + (self.width() - 62 - w) / 2, 38 + (self.height() - 92 - h) / 2, w, h), frame)
        if not self.project:
            return
        lane = (self.height() - 92) / (self.high - self.low + 1)
        for pitch in range(self.low, self.high + 1):
            y = 38 + (self.high - pitch) * lane
            background = QColor('#22262b' if pitch % 12 in (1, 3, 6, 8, 10) else '#1c2024')
            if video:
                background.setAlpha(130)
            p.fillRect(QRectF(62, y, self.width() - 62, lane), background)
            p.setPen(QColor('#525b64'))
            p.drawLine(62, int(y), self.width(), int(y))
            if lane >= 13:
                p.setPen(QColor('#a9b1b9'))
                p.drawText(QRectF(3, y, 53, lane), Qt.AlignmentFlag.AlignCenter, pitch_name(pitch))
        beat = 60 / self.project.bpm
        start = int(self.origin / beat)
        count = min(2000, int(self.width() / self.scale / beat) + 3)
        for i in range(start, start + count):
            x = 62 + (i * beat - self.origin) * self.scale
            p.setPen(QColor('#434a51' if i % 4 == 0 else '#2c3238'))
            p.drawLine(int(x), 30, int(x), self.height() - 40)
            if i % 4 == 0:
                p.setPen(QColor('#b6bec6'))
                p.drawText(int(x) + 4, 20, f'{i * beat:.1f}s')
        visible = [n for n in self.project.ordered()
                   if n.time + n.length >= self.origin and
                   n.time <= self.origin + self.width() / self.scale]
        p.save()
        p.setClipRect(QRectF(62, 30, self.width() - 62, self.height() - 30))
        for i, n in enumerate(visible):
            r = self.geometry_for(n)
            active = n.time <= self.cursor < n.time + n.length
            color = '#f4c95d' if active else '#ef599c' if n.id == self.selected_id else '#49c6cd'
            p.setPen(QPen(QColor('#ffffff' if n.id == self.selected_id else color), 1))
            p.setBrush(QColor(color))
            p.drawRoundedRect(r, 3, 3)
            next_x = self.geometry_for(visible[i + 1]).x() if i + 1 < len(visible) else r.right() + 80
            width = max(0, min(max(r.width(), 35), next_x - r.x() - 5))
        try:
            pages = phrase_page_starts(self.project.notes)
        except ValueError:
            pages = [(i, n.page_break_time) for i, n in enumerate(self.project.notes)
                     if n.line_break_after and n.page_break_time is not None]
        for i, (_, seconds) in enumerate(pages, 1):
            px = 62 + (seconds - self.origin) * self.scale
            p.setPen(QPen(QColor('#ef599c'), 1, Qt.PenStyle.DashLine))
            p.drawLine(int(px), 28, int(px), self.height() - 40)
            p.drawText(int(px) + 4, 34, f'S{i}')
        x = 62 + (self.cursor - self.origin) * self.scale
        p.setPen(QPen(QColor('#ffffff'), 2))
        p.drawLine(int(x), 25, int(x), self.height() - 10)
        p.restore()
        self.sync_lyric_fields(visible)

    def sync_lyric_fields(self, visible):
        seen = set()
        for i, n in enumerate(visible):
            r = self.geometry_for(n)
            next_x = self.geometry_for(visible[i + 1]).x() if i + 1 < len(visible) else r.right() + 80
            left = max(62, r.x())
            right = min(self.width() - 2, max(r.right(), r.x() + 45), next_x - 4)
            if right - left < 12:
                continue
            field = self.lyric_fields.get(n.id)
            if field is None:
                field = self.lyric_fields[n.id] = LyricField(self, n.id)
            if not field.hasFocus() and field.text() != n.text:
                field.setText(n.text)
            field.setToolTip(f'{n.text} / {pitch_name(n.pitch)} / {n.length:.3f}s')
            field.setGeometry(round(left), self.height() - 34, round(right - left), 25)
            field.show()
            seen.add(n.id)
        for ident in list(self.lyric_fields):
            if ident not in seen:
                self.lyric_fields[ident].hide()
                if not any(n.id == ident for n in self.project.notes):
                    self.lyric_fields.pop(ident).deleteLater()

    def hit(self, pos):
        return next((n for n in reversed(self.project.notes)
                     if self.geometry_for(n).adjusted(-3, -4, 3, 4).contains(pos)), None)

    def mousePressEvent(self, event):
        if not self.project or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        note = self.hit(pos)
        if note:
            self.selected_id = note.id
            self.selected.emit(note.id)
            resize = abs(pos.x() - self.geometry_for(note).right()) < 9
            self.drag = (note, pos, note.time, note.length, note.pitch, resize, False)
        else:
            self.seek.emit(max(0, self.origin + (pos.x() - 62) / self.scale))
        self.update()

    def mouseMoveEvent(self, event):
        if self.drag:
            n, start, time, length, pitch, resize, begun = self.drag
            if not begun and (event.position() - start).manhattanLength() < 4:
                return
            if not begun:
                self.before_edit.emit()
                self.drag = (n, start, time, length, pitch, resize, True)
            delta = (event.position().x() - start.x()) / self.scale
            value = max(.02 if resize else 0, (length if resize else time) + delta)
            if self.snap:
                value = snap_time(value, self.project.bpm)
            if resize:
                n.length = max(.02, value)
            else:
                n.time = value
                lane = (self.height() - 92) / (self.high - self.low + 1)
                n.pitch = max(0, min(127, pitch - round((event.position().y() - start.y()) / lane)))
            self.update()
        elif self.project:
            n = self.hit(event.position())
            self.setToolTip(f'{pitch_name(n.pitch)} / {n.time:.3f}s / {n.length:.3f}s / {n.text}' if n else '')

    def mouseReleaseEvent(self, event):
        if self.drag and self.drag[-1]:
            self.edited.emit()
        self.drag = None

    def mouseDoubleClickEvent(self, event):
        if not self.project:
            return
        n = self.hit(event.position())
        if n:
            self.edit_text.emit(n.id)
            return
        if event.position().x() < 62 or not 38 <= event.position().y() < self.height() - 54:
            return
        time = max(0, self.origin + (event.position().x() - 62) / self.scale)
        if self.snap:
            time = snap_time(time, self.project.bpm)
        lane = (self.height() - 92) / (self.high - self.low + 1)
        pitch = max(0, min(127, self.high - int((event.position().y() - 38) / lane)))
        self.before_edit.emit()
        n = EditorNote(time, 60 / self.project.bpm, pitch)
        self.project.notes.append(n)
        self.selected_id = n.id
        self.edited.emit()
        self.selected.emit(n.id)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.scale = max(20, min(500, self.scale * (1.15 if event.angleDelta().y() > 0 else 1 / 1.15)))
        else:
            delta = event.angleDelta().x() or event.angleDelta().y()
            self.origin = max(0, self.origin - delta / self.scale)
            self.follow = False
        self.update()
