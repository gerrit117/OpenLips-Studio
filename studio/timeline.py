"""Horizontal karaoke editor: playback scrolls the notes to the left."""
from PySide6.QtCore import Qt, QRectF, Signal, QMimeData
from PySide6.QtGui import QColor, QPainter, QPen, QKeySequence
from PySide6.QtWidgets import QWidget, QLineEdit, QMenu, QApplication

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
    lyric_word_dropped = Signal(str, object)
    selected = Signal(str)
    edited = Signal()
    before_edit = Signal()
    edit_text = Signal(str)
    seek = Signal(float)
    scrub_started = Signal()
    scrub_moved = Signal(float)
    scrub_finished = Signal()
    pitch_preview = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.expert_view = False
        self.selected_id = ''
        self.selected_ids = set()
        self.selection_anchor = ''
        self.target = None
        self.conflicts = {}
        self.scale = 100.0
        self.origin = 0.0
        self.cursor = 0.0
        self.follow = True
        self.snap = True
        self.low, self.high = 48, 78
        self.drag = None
        self.cursor_drag = False
        self.video_frame = None
        self.show_video = True
        self.lyric_fields = {}
        self.setMinimumSize(400, 280)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_project(self, project):
        if self.project is not project:
            self.target = None
            self.selection_anchor = ''
            self.selected_ids.clear()
            for field in self.lyric_fields.values():
                field.hide()
                field.deleteLater()
            self.lyric_fields.clear()
        self.project = project
        from studio.note_editing import conflicts
        self.conflicts = conflicts(project)
        self.selected_ids.intersection_update(n.id for n in project.notes)
        pitches = [n.pitch if n.pitch_assigned else 60 for n in project.notes]
        padding, minimum = (4, 23) if self.expert_view else (2, 11)
        self.low = max(0, min(pitches, default=54) - padding)
        self.high = min(127, max(self.low + minimum, max(pitches, default=72) + padding))
        self.update()

    def dragEnterEvent(self, event):
        from studio.lyric_document import WORD_MIME
        if event.mimeData().hasFormat(WORD_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        import json
        from studio.lyric_document import WORD_MIME
        if not event.mimeData().hasFormat(WORD_MIME):
            return event.ignore()
        note = self.hit(event.position())
        if not note:
            return event.ignore()
        try:
            value = json.loads(bytes(event.mimeData().data(WORD_MIME)))
            if not isinstance(value, dict):
                return event.ignore()
            self.lyric_word_dropped.emit(note.id, value)
            event.acceptProposedAction()
        except (ValueError, TypeError):
            event.ignore()

    def geometry_for(self, note):
        lane = (self.height() - 92) / (self.high - self.low + 1)
        height = max(4, lane-4) if self.expert_view else min(16, max(6, lane-6))
        return QRectF(62 + (note.time - self.origin) * self.scale,
                      38 + (self.high - (note.pitch if note.pitch_assigned else 60)) * lane + (lane-height)/2,
                      max(5, note.length * self.scale), height)

    def set_cursor(self, seconds):
        self.cursor = seconds
        if self.follow and not self.cursor_drag:
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
                background = QColor('#253132')
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
        from studio.beat_grid import points
        try:
            grid = points(self.project, self.origin, self.origin + self.width() / self.scale)
        except ValueError:
            grid = []
        for i, seconds in grid:
            x = 62 + (seconds - self.origin) * self.scale
            p.setPen(QColor('#434a51' if i % self.project.beat_division == 0 else '#2c3238'))
            p.drawLine(int(x), 30, int(x), self.height() - 40)
            if i % (self.project.beat_division * 4) == 0:
                p.setPen(QColor('#b6bec6'))
                p.drawText(int(x) + 4, 20, f'{seconds:.1f}s')
        visible = [n for n in self.project.ordered()
                   if n.time + n.length >= self.origin and
                   n.time <= self.origin + self.width() / self.scale]
        p.save()
        p.setClipRect(QRectF(62, 30, self.width() - 62, self.height() - 30))
        ordered = self.project.ordered()
        if self.target is not None and not self.selected_ids:
            start,length,pitch = self.target
            rect = self.geometry_for(EditorNote(start,length,pitch))
            p.fillRect(rect,QColor(73,198,205,45))
            p.setPen(QPen(QColor('#75ded1'),1,Qt.PenStyle.DashLine))
            p.drawRect(rect)
        p.setPen(QPen(QColor('#91b5b3'), 1, Qt.PenStyle.DashLine))
        for left, right in zip(ordered, ordered[1:]):
            if right.text.strip() in ('', '~') and not left.end_word and not left.line_break_after:
                a, b = self.geometry_for(left), self.geometry_for(right)
                middle = (a.right() + b.left()) / 2
                p.drawLine(int(a.right()), int(a.center().y()), int(middle), int(a.center().y()))
                p.drawLine(int(middle), int(a.center().y()), int(middle), int(b.center().y()))
                p.drawLine(int(middle), int(b.center().y()), int(b.left()), int(b.center().y()))
        for i, n in enumerate(sorted(visible, key=lambda n: n.id == self.selected_id or n.id in self.selected_ids)):
            r = self.geometry_for(n)
            active = n.time <= self.cursor < n.time + n.length
            chosen = n.id == self.selected_id or n.id in self.selected_ids
            color = '#ed8093' if chosen else '#88929b' if not n.pitch_assigned else '#f4c95d' if active else '#49c6cd'
            p.setPen(QPen(QColor('#ffffff' if chosen else '#ff9b5a' if n.id in self.conflicts else '#fa7c7c' if not n.text.strip() else color), 2 if n.id in self.conflicts else 1,
                         Qt.PenStyle.SolidLine if n.pitch_assigned else Qt.PenStyle.DashLine))
            p.setBrush(QColor(color))
            p.drawRoundedRect(r, 3, 3)
            if n.id in self.conflicts:
                p.setPen(QColor('#ff9b5a'))
                p.drawText(int(r.right())+2,int(r.top())+10,'!')
            next_x = self.geometry_for(visible[i + 1]).x() if i + 1 < len(visible) else r.right() + 80
            width = max(0, min(max(r.width(), 35), next_x - r.x() - 5))
        if not self.expert_view:
            from studio.lyric_mapping import note_words
            p.setPen(QColor('#d4dade'))
            for unit in note_words(ordered):
                notes = unit['notes']
                label = ''.join(note.text.replace('~', '') for note in notes)
                if not label.strip() or not any(note in visible for note in notes):
                    continue
                rectangles = [self.geometry_for(note) for note in notes]
                left, right = rectangles[0].left(), max(r.right() for r in rectangles)
                bottom = max(r.bottom() for r in rectangles)
                if len(notes) > 1:
                    p.drawLine(int(left), int(bottom+4), int(right), int(bottom+4))
                    p.drawLine(int(left), int(bottom), int(left), int(bottom+4))
                    p.drawLine(int(right), int(bottom), int(right), int(bottom+4))
                text = p.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, max(20, int(right-left+12)))
                p.drawText(QRectF(left, bottom+5, max(20, right-left+12), 20), Qt.AlignmentFlag.AlignHCenter, text)
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
        if not self.expert_view:
            for field in self.lyric_fields.values():
                field.hide()
            return
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
                value = self.snap_value(value)
            value = max(0, min(start, previous), min(end-.001, value))
            return value, end-value
        following = min((n.time for n in self.project.notes if n.id != note.id and n.time > start),
                        default=float('inf'))
        value = end + delta
        if self.snap:
            value = self.snap_value(value)
        value = min(max(end, following), max(start+.001, value))
        return start, value-start

    def cursor_hit(self, pos):
        x = 62 + (self.cursor-self.origin)*self.scale
        return x >= 62 and abs(pos.x()-x) <= 6 and 25 <= pos.y() < self.height()-10

    def scrub_position(self, pos):
        return max(0,self.origin+(pos.x()-62)/self.scale)

    def mousePressEvent(self, event):
        if not self.project or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if self.cursor_hit(pos) and not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.cursor_drag = True
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            self.scrub_started.emit()
            self.scrub_moved.emit(self.scrub_position(pos))
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.target = None
            self.seek.emit(max(0,self.origin+(pos.x()-62)/self.scale))
            return
        note = self.hit(pos)
        if note:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                ordered = self.project.ordered()
                ids = [n.id for n in ordered]
                anchor = self.selection_anchor if self.selection_anchor in ids else self.selected_id
                if anchor not in ids:
                    anchor = note.id
                begin,end = sorted((ids.index(anchor),ids.index(note.id)))
                self.selected_ids = set(ids[begin:end+1])
                self.selection_anchor = anchor
                self.selected_id = note.id
                self.target = (ordered[begin].time,ordered[end].time+ordered[end].length-ordered[begin].time,note.pitch)
                self.selected.emit(self.selected_id)
                self.update()
                return
            self.selected_ids = {note.id}
            self.selection_anchor = note.id
            self.target = (note.time,note.length,note.pitch)
            self.selected_id = note.id
            self.selected.emit(note.id)
            mode = self.edge_at(note, pos)
            self.setCursor(Qt.CursorShape.SizeHorCursor if mode != 'move' else Qt.CursorShape.ClosedHandCursor)
            self.drag = (note, pos, note.time, note.length, note.pitch, mode, False)
        else:
            if pos.x() < 62 or not 38 <= pos.y() < self.height()-54:
                return
            self.selected_ids.clear()
            self.selected_id = ''
            self.selected.emit('')
            self.selection_anchor = ''
            self.target = self.cell_at(pos)
        self.update()

    def cell_at(self, pos):
        import math
        from studio.beat_grid import step
        seconds = max(0,self.origin+(pos.x()-62)/self.scale)
        length = step(self.project)
        if self.snap:
            seconds = max(0,self.project.beat_offset+math.floor((seconds-self.project.beat_offset)/length+1e-9)*length)
        lane = (self.height()-92)/(self.high-self.low+1)
        pitch = max(0,min(127,self.high-int((pos.y()-38)/lane)))
        return seconds,length,pitch

    def create_note(self):
        from studio.beat_grid import step
        start,_,pitch = self.target or (self.cursor,step(self.project),60)
        self.before_edit.emit()
        note = EditorNote(start,step(self.project),pitch)
        self.project.notes.append(note)
        self.selected_id = note.id
        self.selected_ids = {note.id}
        self.selection_anchor = note.id
        self.edited.emit()
        self.selected.emit(note.id)

    def shift_lyrics(self, direction, suffix=False):
        from studio.note_editing import lyric_shift_plan
        try:
            plan = lyric_shift_plan(self.project,self.selected_id,direction,suffix)
        except ValueError as error:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self,tr('lyrics.shift'),tr(str(error)))
            return
        self.before_edit.emit()
        for note,text,end_word in plan:
            note.text,note.end_word = text,end_word
        self.edited.emit()
        self.selected.emit(self.selected_id)

    def snap_value(self, seconds):
        from studio.beat_grid import snap
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier:
            return max(0, seconds)
        return snap(self.project, seconds)

    def cut_selected_grid(self):
        from studio.beat_grid import cut_notes
        identifiers = self.selected_ids or {self.selected_id}
        if not any(n.id in identifiers for n in self.project.notes):
            return
        self.before_edit.emit()
        try:
            cut_notes(self.project, identifiers)
        except ValueError as error:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, tr('beat.cut'), str(error))
            return
        self.edited.emit()

    def link_selected_melisma(self):
        from studio.beat_grid import melisma_selection
        from PySide6.QtWidgets import QInputDialog
        notes = melisma_selection(self.project, self.selected_ids, validate_only=True)
        text = ' '.join(dict.fromkeys(n.text.strip() for n in notes if n.text.strip() not in ('', '~')))
        text, accepted = QInputDialog.getText(self, tr('beat.melisma'), tr('Text'), text=text)
        if not accepted or not text.strip():
            return
        self.before_edit.emit()
        melisma_selection(self.project, self.selected_ids, text)
        self.edited.emit()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_notes()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            if not event.isAutoRepeat():
                self.paste_notes()
            event.accept()
            return
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

    def copy_notes(self):
        if not self.project:
            return
        from studio.note_clipboard import capture, MIME
        try:
            payload, identifiers = capture(self.project, self.selected_ids or {self.selected_id})
        except ValueError as error:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, tr('notes.copy'), str(error))
            return
        if payload is None:
            return
        data = QMimeData()
        data.setData(MIME, payload)
        QApplication.clipboard().setMimeData(data)
        self.selected_ids = identifiers
        self.update()

    def choose_paste_mode(self, notes):
        from PySide6.QtWidgets import QMessageBox, QCheckBox
        start,end = min(n.time for n in notes),max(n.time+n.length for n in notes)
        count = sum(n.time < end-1e-6 and n.time+n.length > start+1e-6 for n in self.project.notes)
        box = QMessageBox(self)
        box.setWindowTitle(tr('notes.paste'))
        box.setText(tr('notes.paste_choice',start=start,end=end,count=count))
        lyrics = QCheckBox(tr('notes.paste_text'))
        lyrics.setChecked(True)
        box.setCheckBox(lyrics)
        box.setInformativeText(tr('notes.paste_only'))
        replace = box.addButton(tr('notes.replace'),QMessageBox.ButtonRole.AcceptRole)
        add = box.addButton(tr('notes.add'),QMessageBox.ButtonRole.ActionRole)
        box.addButton(tr('Abbrechen'),QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(replace if count else add)
        box.exec()
        mode = 'replace' if box.clickedButton() is replace else 'add' if box.clickedButton() is add else None
        return (mode, lyrics.isChecked()) if mode else None

    def paste_notes(self, seconds=None, *, mode=None, include_text=True):
        if not self.project:
            return
        from studio.note_clipboard import materialize, MIME
        data = QApplication.clipboard().mimeData()
        if not data or not data.hasFormat(MIME):
            return
        try:
            position = self.target[0] if self.target is not None else self.cursor
            notes = materialize(data.data(MIME), position if seconds is None else seconds,
                                len(self.project.notes))
            if mode is None:
                choice = self.choose_paste_mode(notes)
                if choice is None:
                    return
                mode, include_text = choice
            if not include_text:
                for note in notes:
                    note.text = ''
            from studio.note_editing import passage_destination
            replacement = passage_destination(self.project,notes,mode)
        except ValueError as error:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, tr('notes.paste'), str(error))
            return
        self.before_edit.emit()
        self.project.notes = replacement
        self.selected_id = notes[0].id
        self.selected_ids = {n.id for n in notes}
        self.edited.emit()
        self.selected.emit(notes[0].id)
        self.update()

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
            from studio.note_clipboard import MIME
            menu = QMenu(self)
            action = menu.addAction(tr('notes.paste_here'))
            data = QApplication.clipboard().mimeData()
            action.setEnabled(bool(data and data.hasFormat(MIME)))
            seconds = max(0, self.origin + (event.pos().x() - 62) / self.scale)
            action.triggered.connect(lambda: self.paste_notes(seconds))
            menu.exec(event.globalPos())
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if note.id not in self.selected_ids:
            self.selected_ids = {note.id}
        self.selected_id = note.id
        self.selected.emit(note.id)
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        stack = [n for n in self.project.ordered() if self.geometry_for(n).adjusted(-3,-4,3,4).contains(event.pos())]
        if len(stack) > 1:
            choose = menu.addMenu(tr('notes.choose_layer'))
            for number,item in enumerate(stack,1):
                action = choose.addAction(f'{number}: {pitch_name(item.pitch)} · {item.time:.3f} s · {item.text}')
                action.triggered.connect(lambda checked=False,identifier=item.id:self.select_layer(identifier))
        menu.addAction(tr('lyrics.left'),lambda:self.shift_lyrics(-1))
        menu.addAction(tr('lyrics.right'),lambda:self.shift_lyrics(1))
        menu.addSeparator()
        menu.addAction(tr('notes.copy'), self.copy_notes)
        from studio.note_clipboard import MIME
        paste = menu.addAction(tr('notes.paste'), lambda: self.paste_notes())
        data = QApplication.clipboard().mimeData()
        paste.setEnabled(bool(data and data.hasFormat(MIME)))
        menu.addSeparator()
        grid_cut = menu.addAction(tr('beat.cut'))
        grid_cut.triggered.connect(self.cut_selected_grid)
        link = menu.addAction(tr('beat.melisma'))
        from studio.beat_grid import melisma_selection
        try:
            melisma_selection(self.project, self.selected_ids, validate_only=True)
        except ValueError:
            link.setEnabled(False)
        link.triggered.connect(self.link_selected_melisma)
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

    def select_layer(self, identifier):
        note = next(n for n in self.project.notes if n.id == identifier)
        self.target = (note.time, note.length, note.pitch)
        self.selected_id = identifier
        self.selected_ids = {identifier}
        self.selection_anchor = identifier
        self.selected.emit(identifier)
        self.update()

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
        if self.cursor_drag:
            self.scrub_moved.emit(self.scrub_position(event.position()))
            return
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
                    value = self.snap_value(value)
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
            if self.cursor_hit(event.position()):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                self.setToolTip(tr('transport.scrub'))
                return
            n = self.hit(event.position())
            self.setToolTip(f'{pitch_name(n.pitch) if n.pitch_assigned else tr("timing.unassigned")} / {n.time:.3f}s / {n.length:.3f}s / {n.text}' if n else '')
            self.setCursor(Qt.CursorShape.SizeHorCursor if n and self.edge_at(n, event.position()) != 'move'
                           else Qt.CursorShape.OpenHandCursor if n else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.cursor_drag and event.button() == Qt.MouseButton.LeftButton:
            self.scrub_moved.emit(self.scrub_position(event.position()))
            self.cursor_drag = False
            self.scrub_finished.emit()
            self.unsetCursor()
            return
        if self.drag and self.drag[-1]:
            self.edited.emit()
            if self.drag[0].pitch != self.drag[4]:
                self.pitch_preview.emit(self.drag[0].pitch)
        self.drag = None
        self.unsetCursor()

    def leaveEvent(self, event):
        if not self.drag and not self.cursor_drag:
            self.unsetCursor()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self.project:
            return
        if self.cursor_hit(event.position()):
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            return
        n = self.hit(event.position())
        if n:
            self.edit_text.emit(n.id)
            return
        if event.position().x() < 62 or not 38 <= event.position().y() < self.height() - 54:
            return
        self.target = self.cell_at(event.position())
        self.create_note()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.scale = max(20, min(500, self.scale * (1.15 if event.angleDelta().y() > 0 else 1 / 1.15)))
        else:
            delta = event.angleDelta().x() or event.angleDelta().y()
            self.origin = max(0, self.origin - delta / self.scale)
        self.update()
