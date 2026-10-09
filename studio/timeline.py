"""Horizontal karaoke editor: playback scrolls the notes to the left."""
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QLineEdit, QMenu

from studio.i18n import tr
from studio.model import EditorNote, pitch_name, snap_time, merge_selection
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
        self.timeline.selected_ids = {self.note_id}
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
    pitch_preview = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.selected_id = ''
        self.selected_ids = set()
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
            self.selected_ids.clear()
            for field in self.lyric_fields.values():
                field.hide()
                field.deleteLater()
            self.lyric_fields.clear()
        self.project = project
        self.selected_ids.intersection_update(n.id for n in project.notes)
        pitches = [n.pitch if n.pitch_assigned else 60 for n in project.notes]
        self.low = max(0, min(pitches, default=54) - 4)
        self.high = min(127, max(self.low + 23, max(pitches, default=72) + 4))
        self.update()

    def geometry_for(self, note):
        lane = (self.height() - 92) / (self.high - self.low + 1)
        return QRectF(62 + (note.time - self.origin) * self.scale,
                      38 + (self.high - (note.pitch if note.pitch_assigned else 60)) * lane + 2,
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
        from studio.keys import key_info, key_pitches
        key = key_info(self.project.key_signature)
        guide = key_pitches(self.project.key_signature)
        for pitch in range(self.low, self.high + 1):
            y = 38 + (self.high - pitch) * lane
            background = QColor('#22262b' if pitch % 12 in (1, 3, 6, 8, 10) else '#1c2024')
            if pitch % 12 in guide:
                background = QColor('#233832')
            if video:
                background.setAlpha(130)
            p.fillRect(QRectF(62, y, self.width() - 62, lane), background)
            p.setPen(QColor('#525b64'))
            p.drawLine(62, int(y), self.width(), int(y))
            if lane >= 13:
                p.setPen(QColor('#75ded1' if pitch % 12 in guide else '#a9b1b9'))
                p.drawText(QRectF(3, y, 53, lane), Qt.AlignmentFlag.AlignCenter, pitch_name(pitch))
            if key and pitch % 12 == key['root']:
                p.fillRect(QRectF(58, y + 2, 3, max(1, lane - 4)), QColor('#75ded1'))
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
        ordered = self.project.ordered()
        p.setPen(QPen(QColor('#91b5b3'), 1, Qt.PenStyle.DashLine))
        for left, right in zip(ordered, ordered[1:]):
            if right.text.strip() == '~' and not left.end_word and not left.line_break_after:
                a, b = self.geometry_for(left), self.geometry_for(right)
                middle = (a.right() + b.left()) / 2
                p.drawLine(int(a.right()), int(a.center().y()), int(middle), int(a.center().y()))
                p.drawLine(int(middle), int(a.center().y()), int(middle), int(b.center().y()))
                p.drawLine(int(middle), int(b.center().y()), int(b.left()), int(b.center().y()))
        for i, n in enumerate(visible):
            r = self.geometry_for(n)
            active = n.time <= self.cursor < n.time + n.length
            chosen = n.id == self.selected_id or n.id in self.selected_ids
            color = '#ef599c' if chosen else '#88929b' if not n.pitch_assigned else '#f4c95d' if active else '#49c6cd'
            p.setPen(QPen(QColor('#ffffff' if chosen else '#fa7c7c' if not n.text.strip() else color), 1,
                         Qt.PenStyle.SolidLine if n.pitch_assigned else Qt.PenStyle.DashLine))
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
            field.setToolTip(f'{n.text} / {pitch_name(n.pitch) if n.pitch_assigned else tr("timing.unassigned")} / {n.length:.3f}s')
            field.setGeometry(round(left), self.height() - 34, round(right - left), 25)
            field.show()
            seen.add(n.id)
        for ident in list(self.lyric_fields):
            if ident not in seen:
                self.lyric_fields[ident].hide()
                if not any(n.id == ident for n in self.project.notes):
                    self.lyric_fields.pop(ident).deleteLater()

    def hit(self, pos):
        if pos.x() < 62 or not 38 <= pos.y() < self.height()-54:
            return None
        return next((n for n in reversed(self.project.notes)
                     if self.geometry_for(n).adjusted(-3, -4, 3, 4).contains(pos)), None)

    def edge_at(self, note, pos):
        rect = self.geometry_for(note)
        margin = min(7, rect.width() / 4)
        if pos.x() <= rect.left() + margin:
            return 'left'
        if pos.x() >= rect.right() - margin:
            return 'right'
        return 'move'

    def resized_values(self, note, start, length, delta, edge):
        end = start + length
        if edge == 'left':
            previous = max((n.time+n.length for n in self.project.notes
                            if n.id != note.id and n.time < start), default=0)
            value = start + delta
            if self.snap:
                value = snap_time(value, self.project.bpm)
            value = max(0, min(start, previous), min(end-.001, value))
            return value, end-value
        following = min((n.time for n in self.project.notes if n.id != note.id and n.time > start),
                        default=float('inf'))
        value = end + delta
        if self.snap:
            value = snap_time(value, self.project.bpm)
        value = min(max(end, following), max(start+.001, value))
        return start, value-start

    def mousePressEvent(self, event):
        if not self.project or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        note = self.hit(pos)
        if note:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if self.selected_id and not self.selected_ids:
                    self.selected_ids.add(self.selected_id)
                if note.id in self.selected_ids:
                    self.selected_ids.remove(note.id)
                    self.selected_id = next(iter(self.selected_ids), '')
                else:
                    self.selected_ids.add(note.id)
                    self.selected_id = note.id
                self.selected.emit(self.selected_id)
                self.update()
                return
            self.selected_ids = {note.id}
            self.selected_id = note.id
            self.selected.emit(note.id)
            mode = self.edge_at(note, pos)
            self.setCursor(Qt.CursorShape.SizeHorCursor if mode != 'move' else Qt.CursorShape.ClosedHandCursor)
            self.drag = (note, pos, note.time, note.length, note.pitch, mode, False)
        else:
            self.selected_ids.clear()
            self.selected_id = ''
            self.selected.emit('')
            self.seek.emit(max(0, self.origin + (pos.x() - 62) / self.scale))
        self.update()

    def keyPressEvent(self, event):
        if self.project and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            event.accept()
            return
        if self.project and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            identifiers = self.selected_ids or {self.selected_id}
            notes = [n for n in self.project.notes if n.id in identifiers]
            if notes:
                delta = 1 if event.key() == Qt.Key.Key_Up else -1
                if all(0 <= note.pitch + delta <= 127 for note in notes):
                    self.before_edit.emit()
                    for note in notes:
                        note.pitch += delta
                        note.pitch_assigned = True
                    self.edited.emit()
                    self.pitch_preview.emit(notes[0].pitch)
                event.accept()
                return
        super().keyPressEvent(event)

    def merge_notes(self):
        merge_selection(self.project, self.selected_ids, validate_only=True)
        self.before_edit.emit()
        note = merge_selection(self.project, self.selected_ids)
        self.selected_id = note.id
        self.selected_ids = {note.id}
        self.edited.emit()
        self.selected.emit(note.id)
        if note.pitch_assigned:
            self.pitch_preview.emit(note.pitch)

    def delete_selected(self):
        from studio.lyric_timing import delete_notes
        identifiers = self.selected_ids or {self.selected_id}
        if self.project and any(n.id in identifiers for n in self.project.notes):
            self.before_edit.emit()
            delete_notes(self.project, identifiers)
            self.selected_id = ''
            self.selected_ids.clear()
            self.edited.emit()
            self.selected.emit('')

    def contextMenuEvent(self, event):
        if not self.project:
            return
        note = self.hit(event.pos())
        if not note:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if note.id not in self.selected_ids:
            self.selected_ids = {note.id}
        self.selected_id = note.id
        self.selected.emit(note.id)
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        action = menu.addAction(tr('note.merge_selected'))
        try:
            merge_selection(self.project, self.selected_ids, validate_only=True)
        except ValueError:
            action.setEnabled(False)
        action.setToolTip(tr('note.merge_hint'))
        action.triggered.connect(self.merge_notes)
        seconds = self.origin + (event.pos().x()-62)/self.scale
        split = menu.addAction(tr('timing.split'))
        split.setEnabled(note.time+.001 <= seconds <= note.time+note.length-.001)
        split.triggered.connect(lambda: self.split_selected(note.id, seconds))
        melisma = menu.addAction(tr('note.add_melisma'))
        melisma.setEnabled(note.length >= .002)
        melisma.triggered.connect(lambda: self.add_melisma(note.id, seconds))
        words = menu.addAction(tr('timing.split_words'))
        words.setEnabled(len(note.text.split()) > 1 and note.length/len(note.text.split()) >= .001)
        words.setToolTip(tr('timing.estimated'))
        words.triggered.connect(lambda: self.split_selected(note.id))
        menu.addSeparator()
        menu.addAction(tr('Note loeschen'), self.delete_selected)
        menu.exec(event.globalPos())

    def add_melisma(self, identifier, seconds=None):
        note = next(n for n in self.project.notes if n.id == identifier)
        if seconds is None or not note.time+.001 <= seconds <= note.time+note.length-.001:
            seconds = note.time + note.length/2
        self.split_selected(identifier, seconds)

    def split_selected(self, identifier, seconds=None):
        from studio.lyric_timing import split_note, split_words
        self.before_edit.emit()
        if seconds is None:
            result = split_words(self.project, identifier)[0]
        else:
            result = split_note(self.project, identifier, seconds)
        self.selected_id = result.id
        self.selected_ids = {result.id}
        self.edited.emit()
        self.selected.emit(result.id)

    def mouseMoveEvent(self, event):
        if self.drag:
            n, start, time, length, pitch, mode, begun = self.drag
            if not begun and (event.position() - start).manhattanLength() < 4:
                return
            delta = (event.position().x() - start.x()) / self.scale
            if mode != 'move':
                value, duration = self.resized_values(n, time, length, delta, mode)
                new_pitch = n.pitch
            else:
                value = max(0, time + delta)
                if self.snap:
                    value = snap_time(value, self.project.bpm)
                duration = length
                lane = (self.height() - 92) / (self.high - self.low + 1)
                new_pitch = max(0, min(127, pitch - round((event.position().y() - start.y()) / lane)))
            if (n.time, n.length, n.pitch) == (value, duration, new_pitch):
                return
            if not begun:
                self.before_edit.emit()
                self.drag = (n, start, time, length, pitch, mode, True)
            n.time, n.length, n.pitch = value, duration, new_pitch
            if new_pitch != pitch:
                n.pitch_assigned = True
            if mode == 'left':
                ordered = self.project.ordered()
                index = ordered.index(n)
                if index:
                    previous = ordered[index-1]
                    if previous.page_break_time is not None and previous.page_break_time > n.time:
                        previous.page_break_time = None
            self.update()
        elif self.project:
            n = self.hit(event.position())
            self.setToolTip(f'{pitch_name(n.pitch) if n.pitch_assigned else tr("timing.unassigned")} / {n.time:.3f}s / {n.length:.3f}s / {n.text}' if n else '')
            self.setCursor(Qt.CursorShape.SizeHorCursor if n and self.edge_at(n, event.position()) != 'move'
                           else Qt.CursorShape.OpenHandCursor if n else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.drag and self.drag[-1]:
            self.edited.emit()
            if self.drag[0].pitch != self.drag[4]:
                self.pitch_preview.emit(self.drag[0].pitch)
        self.drag = None
        self.unsetCursor()

    def leaveEvent(self, event):
        if not self.drag:
            self.unsetCursor()
        super().leaveEvent(event)

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
