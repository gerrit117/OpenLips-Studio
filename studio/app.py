"""Native, cross-platform OpenLips Studio shell."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QSplitter, QLineEdit, QDoubleSpinBox, QSpinBox,
    QCheckBox, QLabel, QTextEdit, QPushButton, QToolBar, QFileDialog, QMessageBox,
    QInputDialog, QSlider, QComboBox, QGroupBox, QScrollArea, QLayout, QSizePolicy, QStackedWidget)
import qtawesome as qta
from studio.i18n import tr, language as ui_language, set_language

from studio import DISPLAY_VERSION
from studio.model import (StudioProject, demo_project, load_project, save_project,
                          assign_lyrics, pitch_name, EditorNote)
from studio.model import suggest_syllables
from studio.importers import read_midi, project_from_midi, import_ultrastar
from studio.exporters import export_debug_json, export_owned_pair
from studio.timeline import Timeline
from studio.branding import app_icon, asset


class StudioWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(app_icon())
        self.project = StudioProject()
        self.path = None
        self.dirty = False
        self.history, self.future = [], []
        self.loading = False
        self.playing = False
        self.position = 0.0
        self.clock_start = 0.0
        self.rate = 1.0
        from studio.tone_preview import TonePreview
        self.tones = TonePreview(self)
        self.tones.failed.connect(lambda message: self.statusBar().showMessage(message))
        self.sounding_note = None
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.65)
        self.player.setAudioOutput(self.audio)
        self.video_player = QMediaPlayer(self)
        self.video_audio = QAudioOutput(self)
        self.video_player.setAudioOutput(self.video_audio)
        self.video_sink = QVideoSink(self)
        self.video_player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self.video_frame)
        self.video_player.errorOccurred.connect(lambda *_: self.statusBar().showMessage(self.video_player.errorString()))
        self.player.errorOccurred.connect(lambda *_: self.statusBar().showMessage(self.player.errorString()))
        self.resize(1260, 790)
        self.setMinimumSize(840, 600)
        self.build_ui()
        self.loading = True
        self.lyrics.setPlainText(self.project.lyric_text())
        self.loading = False
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        self.refresh()

    def action(self, label, icon, callback, shortcut=None):
        a = QAction(qta.icon(icon, color='#cdd3d9'), label, self)
        a.triggered.connect(callback)
        if shortcut:
            a.setShortcut(shortcut)
        return a

    def build_ui(self):
        file = self.menuBar().addMenu(tr('Datei'))
        toolbar = QToolBar(tr('Projekt'), self)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)
        for label, icon, callback, shortcut in [
            (tr('Neu'), 'fa5s.file', self.new, QKeySequence.StandardKey.New),
            (tr('Projekt oeffnen'), 'fa5s.folder-open', self.open, QKeySequence.StandardKey.Open),
            (tr('Speichern'), 'fa5s.save', self.save, QKeySequence.StandardKey.Save)]:
            a = self.action(label, icon, callback, shortcut)
            file.addAction(a)
            toolbar.addAction(a)
        file.addAction(tr('Speichern unter'), self.save_as, QKeySequence.StandardKey.SaveAs)
        file.addSeparator()
        file.addAction(tr('wizard.title'), self.create_song)
        file.addAction(tr('batch.title'), self.import_ultrastar_batch)
        file.addAction(tr('welcome.community'), self.open_community)
        exports = file.addMenu(tr('export.menu'))
        exports.addAction(tr('export.community'), self.export_community)
        exports.addAction(tr('DLC exportieren (experimentell)'), self.export_dlc)
        exports.addAction(tr('pack.title'), self.export_song_pack)
        advanced = exports.addMenu(tr('export.advanced'))
        advanced.addAction(tr('X360-Paar exportieren'), self.export_pair)
        advanced.addAction(tr('Debug-JSON exportieren'), self.export_json)
        tools = self.menuBar().addMenu(tr('Werkzeuge'))
        for label, callback in [(tr('MIDI importieren'), self.import_midi),
                               (tr('UltraStar importieren'), self.import_txt),
                               (tr('lrc.import'), self.import_lrc),
                               (tr('wizard.media'), self.load_song_media),
                               (tr('Cover laden'), self.load_cover),
                               (tr('OG-Medien konvertieren'), self.convert_media)]:
            tools.addAction(label, callback)
        tools.addSeparator()
        tools.addAction(tr('preview.settings'), self.edit_preview)
        tools.addAction(tr('pages.title'), self.optimize_lyric_pages)
        self.smart_pages_action = self.action(tr('pages.smart'), 'fa5s.stream', self.intelligent_lyric_pages)
        self.smart_pages_action.setToolTip(tr('pages.smart'))
        tools.addAction(self.smart_pages_action)
        tools.addAction(tr('usb.title'), self.install_dlc_usb)
        tools.addAction(tr('Lyrics suchen'), self.search_lyrics)
        tools.addAction(tr('lrc.review'), self.review_lrc)
        tools.addAction(tr('ai.title'), self.ai_chart_dialog)
        tools.addAction(tr('download.youtube'), self.download_youtube)
        self.plugin_menu = tools.addMenu(tr('plugin.actions'))
        self.plugin_menu.aboutToShow.connect(self.refresh_plugin_actions)
        self.refresh_plugin_actions()
        tools.addAction('Plugins', self.plugins_dialog)
        tools.addAction(tr('Alle Noten zeitlich verschieben'), self.shift_all_notes)
        languages = self.menuBar().addMenu(tr('ui.language'))
        for label, code in [('English', 'en'), ('Deutsch', 'de')]:
            action = languages.addAction(label)
            action.setCheckable(True)
            action.setChecked(ui_language() == code)
            action.triggered.connect(lambda checked=False, value=code: self.change_language(value))
        edit = self.menuBar().addMenu(tr('Bearbeiten'))
        self.undo_action = self.action(tr('Rueckgaengig'), 'fa5s.undo', self.undo, QKeySequence.StandardKey.Undo)
        self.redo_action = self.action(tr('Wiederholen'), 'fa5s.redo', self.redo, QKeySequence.StandardKey.Redo)
        self.delete_action = self.action(tr('Note loeschen'), 'fa5s.trash-alt', self.delete_note, QKeySequence.StandardKey.Delete)
        for a in (self.undo_action, self.redo_action, self.delete_action):
            edit.addAction(a)
            toolbar.addAction(a)
        toolbar.addSeparator()
        toolbar.addAction(self.action('Plugins', 'fa5s.plug', self.plugins_dialog))
        toolbar.addAction(self.action(tr('ai.title'), 'fa5s.wave-square', self.ai_chart_dialog))
        toolbar.addSeparator()
        toolbar.addAction(self.smart_pages_action)
        toolbar.widgetForAction(self.smart_pages_action).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(asset('studio-logo-dark.png'))).scaled(
            156, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setToolTip(f'OpenLips Studio {DISPLAY_VERSION}')
        logo.setContentsMargins(8, 0, 4, 0)
        toolbar.addWidget(logo)

        root = QWidget()
        self.screens = QStackedWidget()
        self.setCentralWidget(self.screens)
        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.addStretch()
        brand = QLabel()
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setPixmap(QPixmap(str(asset('studio-logo-dark.png'))).scaled(
            360, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        welcome_layout.addWidget(brand)
        for label, icon, callback in [('welcome.create', 'fa5s.plus', self.create_song),
                                       ('batch.title', 'fa5s.file-import', self.import_ultrastar_batch),
                                       ('Projekt oeffnen', 'fa5s.folder-open', self.open),
                                       ('welcome.community', 'fa5s.users', self.open_community)]:
            button = QPushButton(qta.icon(icon, color='#cdd3d9'), tr(label))
            button.setMinimumHeight(52)
            button.setFixedWidth(360)
            button.clicked.connect(callback)
            welcome_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
        welcome_layout.addStretch()
        self.screens.addWidget(welcome)
        self.screens.addWidget(root)
        layout = QVBoxLayout(root)
        meta = QHBoxLayout()
        self.cover_preview = QLabel()
        self.cover_preview.setFixedSize(48, 48)
        meta.addWidget(self.cover_preview)
        self.title_edit = QLineEdit()
        self.artist_edit = QLineEdit()
        self.bpm_edit = QDoubleSpinBox()
        self.bpm_edit.setRange(1, 1000)
        self.bpm_edit.setDecimals(2)
        self.key_label = QLabel()
        for label, widget in [(tr('Titel'), self.title_edit), (tr('Artist'), self.artist_edit), ('BPM', self.bpm_edit)]:
            meta.addWidget(QLabel(label))
            meta.addWidget(widget, 1 if isinstance(widget, QLineEdit) else 0)
        meta.addWidget(self.key_label)
        layout.addLayout(meta)
        for widget in (self.title_edit, self.artist_edit, self.bpm_edit):
            widget.editingFinished.connect(self.edit_metadata)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.timeline = Timeline()
        splitter.addWidget(self.timeline)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        side.setContentsMargins(8, 0, 0, 0)
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(320)
        box = QGroupBox(tr('Note / Silbe'))
        form = QFormLayout(box)
        self.time_edit = QDoubleSpinBox()
        self.length_edit = QDoubleSpinBox()
        for w in (self.time_edit, self.length_edit):
            w.setDecimals(3)
            w.setSingleStep(.025)
            w.setSuffix(' s')
            w.setRange(0, 86400)
        self.length_edit.setMinimum(.02)
        self.pitch_edit = QSpinBox()
        self.pitch_edit.setRange(0, 127)
        self.pitch_edit.valueChanged.connect(self.preview_pitch_change)
        self.pitch_label = QLabel()
        self.text_edit = QLineEdit()
        self.word_edit = QCheckBox()
        self.phrase_edit = QCheckBox()
        self.page_override = QCheckBox()
        self.page_edit = QDoubleSpinBox()
        self.page_edit.setRange(0, 86400)
        self.page_edit.setDecimals(3)
        self.page_edit.setSuffix(' s')
        self.page_edit.setSingleStep(.025)
        for label, widget in [('Start', self.time_edit), (tr('Laenge'), self.length_edit),
            (tr('MIDI-Ton'), self.pitch_edit), (tr('Tonname'), self.pitch_label),
            ('Text', self.text_edit), (tr('Wortende'), self.word_edit), (tr('Phrasenende'), self.phrase_edit),
            (tr('Seitenzeit festlegen'), self.page_override), (tr('Seitenwechsel'), self.page_edit)]:
            form.addRow(label, widget)
        for widget in (self.time_edit, self.length_edit, self.pitch_edit, self.text_edit):
            widget.editingFinished.connect(self.edit_note)
        self.word_edit.clicked.connect(self.edit_note)
        self.phrase_edit.clicked.connect(self.edit_note)
        self.page_override.clicked.connect(self.edit_note)
        self.page_edit.editingFinished.connect(self.edit_note)
        tone_row = QWidget()
        tone_layout = QHBoxLayout(tone_row)
        tone_layout.setContentsMargins(0, 0, 0, 0)
        self.tone_button = QPushButton(qta.icon('fa5s.volume-up', color='#cdd3d9'), '')
        self.tone_button.setToolTip(tr('tone.listen'))
        self.tone_button.setFixedSize(36, 30)
        self.tone_button.clicked.connect(self.audition_note)
        tone_layout.addWidget(self.tone_button)
        self.tone_volume = QSlider(Qt.Orientation.Horizontal)
        self.tone_volume.setRange(0, 100)
        self.tone_volume.setValue(round(self.tones.volume * 100))
        self.tone_volume.setToolTip(tr('tone.volume'))
        self.tone_volume.valueChanged.connect(lambda value: self.tones.set_volume(value / 100))
        tone_layout.addWidget(self.tone_volume)
        form.addRow(tr('tone.listen'), tone_row)
        self.tone_auto = QCheckBox(tr('tone.automatic'))
        self.tone_auto.setChecked(True)
        form.addRow(self.tone_auto)
        box.setMinimumHeight(form.sizeHint().height() + 20)
        side.addWidget(box)
        add = QPushButton(qta.icon('fa5s.plus', color='#cdd3d9'), tr('Note erstellen'))
        add.clicked.connect(self.add_note)
        side.addWidget(add)
        self.lyrics = QTextEdit()
        self.lyrics.setAcceptRichText(False)
        self.lyrics.setMinimumHeight(100)
        side.addWidget(QLabel(tr('Songtext')))
        side.addWidget(self.lyrics, 1)
        self.syllables = QCheckBox(tr('Silben mit | trennen'))
        side.addWidget(self.syllables)
        language = QHBoxLayout()
        self.language = QComboBox()
        self.language.addItem('English', 'en_US')
        self.language.addItem('Deutsch', 'de_DE')
        language.addWidget(self.language)
        suggest = QPushButton(qta.icon('fa5s.magic', color='#cdd3d9'), '')
        suggest.setToolTip(tr('Silbentrennung vorschlagen (experimentell)'))
        suggest.clicked.connect(self.suggest_text)
        language.addWidget(suggest)
        side.addLayout(language)
        assign = QPushButton(qta.icon('fa5s.link', color='#cdd3d9'), tr('Ab Auswahl zuordnen'))
        assign.clicked.connect(self.assign)
        side.addWidget(assign)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        side_scroll.setMinimumWidth(258)
        side_scroll.setMaximumWidth(340)
        side_scroll.setWidget(sidebar)
        splitter.addWidget(side_scroll)
        splitter.setSizes([900, 280])
        layout.addWidget(splitter, 1)

        self.scroll = QSlider(Qt.Orientation.Horizontal)
        self.scroll.setRange(0, 100000)
        self.scroll.sliderMoved.connect(self.scroll_to)
        layout.addWidget(self.scroll)
        transport = QHBoxLayout()
        self.play_button = QPushButton(qta.icon('fa5s.play', color='#cdd3d9'), '')
        self.play_button.setToolTip(tr('Wiedergabe / Pause'))
        self.play_button.setFixedWidth(44)
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button = QPushButton(qta.icon('fa5s.stop', color='#cdd3d9'), '')
        self.stop_button.setToolTip(tr('Stopp'))
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setFixedWidth(44)
        self.clock_label = QLabel('00:00.000')
        self.clock_label.setMinimumWidth(100)
        transport.addWidget(self.play_button)
        transport.addWidget(self.stop_button)
        transport.addWidget(self.clock_label)
        self.follow_box = QCheckBox(tr('Cursor folgen'))
        self.follow_box.setChecked(True)
        self.follow_box.toggled.connect(lambda v: setattr(self.timeline, 'follow', v))
        transport.addWidget(self.follow_box)
        snap = QCheckBox(tr('Raster'))
        snap.setChecked(True)
        snap.toggled.connect(lambda v: setattr(self.timeline, 'snap', v))
        transport.addWidget(snap)
        self.hear_notes = QCheckBox(tr('tone.playback'))
        self.hear_notes.toggled.connect(self.toggle_note_tones)
        transport.addWidget(self.hear_notes)
        transport.addStretch()
        speed = QComboBox()
        speed.addItems(['0.5x', '0.75x', '1x', '1.25x', '1.5x'])
        speed.setCurrentIndex(2)
        speed.currentTextChanged.connect(self.set_speed)
        transport.addWidget(QLabel(tr('Tempo')))
        transport.addWidget(speed)
        zoom = QSlider(Qt.Orientation.Horizontal)
        zoom.setRange(20, 300)
        zoom.setValue(100)
        zoom.setMaximumWidth(120)
        zoom.valueChanged.connect(self.set_zoom)
        transport.addWidget(QLabel('Zoom'))
        transport.addWidget(zoom)
        layout.addLayout(transport)
        reference = QHBoxLayout()
        self.video_box = QCheckBox(tr('Referenzvideo'))
        self.video_box.setChecked(True)
        self.video_box.toggled.connect(self.toggle_video)
        reference.addWidget(self.video_box)
        self.reference_label = QLabel(tr('Keine Referenz'))
        self.reference_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        reference.addWidget(self.reference_label, 1)
        self.reference_mute = QPushButton(qta.icon('fa5s.volume-mute', color='#cdd3d9'), '')
        self.reference_mute.setCheckable(True)
        self.reference_mute.setFixedWidth(32)
        self.reference_mute.setToolTip(tr('media.mute'))
        self.reference_mute.setChecked(self.audio.isMuted())
        self.reference_mute.toggled.connect(self.set_reference_muted)
        reference.addWidget(self.reference_mute)
        self.reference_volume = QSlider(Qt.Orientation.Horizontal)
        self.reference_volume.setRange(0, 100)
        self.reference_volume.setValue(round(self.audio.volume() * 100))
        self.reference_volume.setFixedWidth(100)
        self.reference_volume.setToolTip(tr('media.volume'))
        self.reference_volume.setAccessibleName(tr('media.volume'))
        self.reference_volume.valueChanged.connect(self.set_reference_volume)
        reference.addWidget(self.reference_volume)
        reference.addWidget(QLabel(tr('Referenz-Offset')))
        self.reference_edit = QDoubleSpinBox()
        self.reference_edit.setRange(-86400, 86400)
        self.reference_edit.setDecimals(3)
        self.reference_edit.setSuffix(' s')
        self.reference_edit.editingFinished.connect(self.edit_reference)
        reference.addWidget(self.reference_edit)
        export_button = QPushButton(qta.icon('fa5s.file-export', color='#cdd3d9'), tr('export.menu'))
        export_button.setMenu(exports)
        reference.addWidget(export_button)
        layout.addLayout(reference)
        self.timeline.selected.connect(self.select_note)
        self.timeline.selected.connect(self.audition_selection)
        self.timeline.pitch_preview.connect(self.preview_pitch_change)
        self.timeline.before_edit.connect(self.snapshot)
        self.timeline.edited.connect(self.changed)
        self.timeline.edit_text.connect(self.focus_text)
        self.timeline.seek.connect(self.seek)
        self.statusBar().showMessage(tr('Bereit'))
        self.lyrics.textChanged.connect(self.draft_changed)

    def set_reference_volume(self, value):
        self.audio.setVolume(value / 100)
        self.video_audio.setVolume(value / 100)

    def set_reference_muted(self, muted):
        self.audio.setMuted(muted)
        self.video_audio.setMuted(muted or bool(self.project.audio_path))

    def draft_changed(self):
        if not self.loading:
            self.dirty = True
            self.project.draft_lyrics = self.lyrics.toPlainText()
            self.setWindowTitle(f'{self.project.title} * - OpenLips Studio {DISPLAY_VERSION}')

    def change_language(self, value):
        if value == ui_language():
            return
        position, selected = self.position, self.timeline.selected_id
        draft = self.lyrics.toPlainText()
        origin, scale, follow, snap = self.timeline.origin, self.timeline.scale, self.timeline.follow, self.timeline.snap
        self.stop()
        set_language(value)
        self.menuBar().clear()
        for toolbar in self.findChildren(QToolBar):
            self.removeToolBar(toolbar)
            toolbar.deleteLater()
        self.loading = True
        self.build_ui()
        self.lyrics.setPlainText(draft)
        self.loading = False
        self.timeline.selected_id = selected
        self.timeline.scale, self.timeline.follow, self.timeline.snap = scale, follow, snap
        self.follow_box.setChecked(follow)
        self.refresh()
        self.seek(position)
        self.timeline.origin = origin
        self.timeline.update()

    def search_lyrics(self):
        from studio.lyrics_search import LyricsSearch
        if getattr(self, 'search_worker', None) and self.search_worker.isRunning():
            return
        if QMessageBox.question(self, tr('Lyrics suchen'),
            tr('Titel und Artist an LRCLIB senden? Gefundene Texte bleiben lokal. Bitte Nutzungsrechte beachten.')) != QMessageBox.StandardButton.Yes:
            return
        self.search_worker = LyricsSearch(self.title_edit.text(), self.artist_edit.text(), self)
        self.search_worker.results.connect(self.lyrics_results)
        self.search_worker.failed.connect(lambda message: self.error(message))
        self.search_worker.start()
        self.statusBar().showMessage(tr('Lyrics-Suche laeuft ...'))

    def lyrics_results(self, results):
        if not results:
            self.statusBar().showMessage(tr('Keine Texte gefunden'))
            return
        labels = [f'{i + 1}. {r.get("artistName", "")} - {r.get("trackName", "")} ({r.get("duration", "?")} s)' for i, r in enumerate(results)]
        label, ok = QInputDialog.getItem(self, tr('Suchergebnisse'), 'Version', labels, 0, False)
        if ok:
            result = results[labels.index(label)]
            synced = result.get('syncedLyrics')
            if isinstance(synced, str) and synced.strip():
                options = [tr('lrc.synchronized'), tr('lrc.plain')]
                choice, accepted = QInputDialog.getItem(self, tr('Suchergebnisse'), tr('Songtext'), options, 0, False)
                if not accepted:
                    return
                if choice == options[0]:
                    from studio.lrc import parse_lrc
                    self.attempt(lambda: self.accept_lrc(parse_lrc(synced), f'LRCLIB:{result.get("id", "")}'))
                    return
            self.snapshot()
            self.lyrics.setPlainText(result.get('plainLyrics') or '')

    def ai_chart_dialog(self):
        from studio.ai_dialog import AiChartDialog
        dialog = AiChartDialog(self.project, self)
        if dialog.exec() and dialog.result_project:
            result = dialog.result_project
            self.stop()
            self.snapshot()
            self.project.notes = result.notes
            self.project.source = result.source
            self.project.warnings = result.warnings
            if result.lyric_reference:
                self.project.lyric_reference = result.lyric_reference
            if result.draft_lyrics:
                self.project.draft_lyrics = result.draft_lyrics
            self.project.audio_path = result.audio_path
            self.lyrics.setPlainText(self.project.draft_lyrics)
            self.timeline.selected_id = ''
            self.timeline.origin = 0
            self.configure_media()
            self.changed()

    def plugins_dialog(self):
        from studio.plugin_dialog import PluginDialog
        dialog = PluginDialog(self.project, self)
        dialog.accepted_project.connect(self.apply_plugin_notes)
        dialog.accepted_song.connect(self.apply_plugin_song)
        dialog.exec()
        self.refresh_plugin_actions()

    def finish_usdb_batch(self, dialog):
        if not getattr(dialog, 'batch_result', None):
            return
        projects, name, export_pack = dialog.batch_result
        self.apply_plugin_song(projects[0])
        if export_pack:
            from studio.dlc_dialog import SongPackDialog, DlcDialog
            if len(projects) == 1:
                export = DlcDialog(projects[0], self)
            else:
                export = SongPackDialog(StudioProject(), self)
                for project in projects:
                    export.append_project(project)
                export.name.setText(name)
            QTimer.singleShot(0, export.build)
            export.exec()

    def import_ultrastar_batch(self):
        if not self.confirm_discard():
            return
        from studio.ultrastar_batch_dialog import UltraStarBatchDialog
        dialog = UltraStarBatchDialog(self)
        if dialog.exec():
            self.finish_usdb_batch(dialog)

    def refresh_plugin_actions(self):
        from PySide6.QtCore import QSettings
        from studio.plugins import discover_plugins
        settings = QSettings('OpenLips', 'OpenLips Studio')
        plugins, errors = discover_plugins(settings.value('plugins/enabled', [], type=list),
                                           settings.value('plugins/folders', [], type=list))
        self.plugin_menu.clear()
        for plugin in plugins:
            actions = plugin.ui_actions or ({'id': 'default', 'label': plugin.label, 'view': 'parameters'},)
            for contribution in actions:
                self.plugin_menu.addAction(tr(contribution['label']),
                    lambda checked=False, p=plugin, view=contribution['view']: self.run_plugin_action(p, view))
        if not plugins:
            self.plugin_menu.addAction(tr('plugin.install_action'), self.plugins_dialog)

    def run_plugin_action(self, plugin, view):
        if view in ('media-download', 'usdb-browser'):
            if view == 'usdb-browser' and not self.confirm_discard():
                return
            from studio.plugin_download_dialog import PluginDownloadDialog
            dialog = PluginDownloadDialog(plugin, view, self.project, self)
            dialog.accepted_song.connect(self.apply_plugin_song)
            dialog.accepted_media.connect(self.apply_downloaded_media)
        else:
            from studio.plugin_dialog import PluginDialog
            dialog = PluginDialog(self.project, self)
            index = next((i for i, offer in enumerate(dialog.offers) if offer.id == plugin.id), -1)
            dialog.list.setCurrentRow(index)
            dialog.list.parentWidget().hide()
            dialog.setWindowTitle(plugin.label + ' · OpenLips Studio')
            dialog.accepted_project.connect(self.apply_plugin_notes)
            dialog.accepted_song.connect(self.apply_plugin_song)
        dialog.exec()
        self.finish_usdb_batch(dialog)

    def download_youtube(self, automatic=False):
        from types import SimpleNamespace
        from studio.plugin_download_dialog import PluginDownloadDialog
        def command(request, output, python_override=''):
            root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
            executable = root / 'download/OpenLipsDownload' / ('OpenLipsDownload.exe' if sys.platform == 'win32' else 'OpenLipsDownload')
            args = ['--serve', '--output', str(output)]
            if executable.is_file():
                return [str(executable), *args]
            if getattr(sys, 'frozen', False):
                raise ValueError(tr('download.worker_missing'))
            return [sys.executable, '-m', 'tools.youtube_download', *args]
        plugin = SimpleNamespace(id='studio-youtube', create_command=command)
        try:
            dialog = PluginDownloadDialog(plugin, 'media-download', self.project, self, automatic=automatic)
            dialog.accepted_media.connect(self.apply_downloaded_media)
            dialog.exec()
        except Exception as error:
            self.error(error)

    def apply_downloaded_media(self, result):
        self.stop()
        self.snapshot()
        self.project.video_reference = result['reference']
        if result['video']:
            self.project.video_path = result['path']
            self.project.audio_path = ''
        else:
            self.project.audio_path = result['path']
            self.project.video_path = ''
        self.configure_media()
        self.changed()

    def offer_reference_download(self):
        if self.project.audio_path or self.project.video_path or not self.project.video_reference:
            return
        from tools.youtube_download import youtube_url
        try:
            youtube_url(self.project.video_reference)
        except ValueError:
            return
        if QMessageBox.question(self, tr('download.youtube'), tr('download.auto_confirm'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.download_youtube(automatic=True)

    def apply_plugin_song(self, result):
        result.validate()
        self.stop()
        self.snapshot()
        self.project = copy.deepcopy(result)
        self.path = None
        self.project.draft_lyrics = result.draft_lyrics or result.lyric_text()
        self.loading = True
        self.lyrics.setPlainText(self.project.draft_lyrics)
        self.loading = False
        self.configure_media()
        self.timeline.selected_id = ''
        self.timeline.origin = 0
        self.changed()

    def apply_plugin_notes(self, result):
        result.validate()
        self.stop()
        self.snapshot()
        self.project.notes = copy.deepcopy(result.notes)
        self.project.source = result.source
        self.project.warnings = list(result.warnings)
        if not self.project.audio_path and not self.project.video_path:
            self.project.audio_path = result.audio_path
            self.configure_media()
        self.timeline.selected_id = ''
        self.timeline.origin = 0
        self.changed()

    def snapshot(self):
        self.history.append(copy.deepcopy(self.project))
        self.history = self.history[-100:]
        self.future.clear()

    def changed(self):
        self.dirty = True
        self.screens.setCurrentIndex(1)
        self.refresh()

    def refresh(self):
        self.loading = True
        self.setWindowTitle(f'{self.project.title} {"*" if self.dirty else ""} - OpenLips Studio {DISPLAY_VERSION}')
        self.title_edit.setText(self.project.title)
        self.artist_edit.setText(self.project.artist)
        self.bpm_edit.setValue(self.project.bpm)
        self.key_label.setText(tr('key.label', key=self.project.key_signature or '-'))
        from studio.media import cover_image
        try:
            self.cover_preview.setPixmap(QPixmap.fromImage(cover_image(self.project)).scaled(
                48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except ValueError:
            self.cover_preview.clear()
        self.cover_preview.setToolTip(self.project.cover_path or tr('Generiertes Cover'))
        self.reference_edit.setValue(self.project.reference_offset)
        names = [Path(p).name for p in (self.project.audio_path, self.project.video_path) if p]
        self.reference_label.setText(' / '.join(names) or tr('Keine Referenz'))
        self.reference_label.setToolTip('\n'.join(p for p in (self.project.audio_path, self.project.video_path) if p))
        self.timeline.set_project(self.project)
        self.undo_action.setEnabled(bool(self.history))
        self.redo_action.setEnabled(bool(self.future))
        self.smart_pages_action.setEnabled(bool(self.project.notes))
        self.select_note(self.timeline.selected_id)
        self.statusBar().showMessage(tr('notes.summary', count=len(self.project.notes), duration=self.project.duration,
                                       warnings=len(self.project.warnings), source=self.project.source))
        self.loading = False

    def note(self):
        return next((n for n in self.project.notes if n.id == self.timeline.selected_id), None)

    def select_note(self, ident):
        previous = self.loading
        self.loading = True
        self.timeline.selected_id = ident
        n = self.note()
        for w in (self.time_edit, self.length_edit, self.pitch_edit, self.text_edit, self.word_edit, self.phrase_edit, self.page_override):
            w.setEnabled(n is not None)
        self.delete_action.setEnabled(n is not None)
        self.tone_button.setEnabled(n is not None)
        if n:
            self.time_edit.setValue(n.time)
            self.length_edit.setValue(n.length)
            self.pitch_edit.setValue(n.pitch)
            self.pitch_label.setText(pitch_name(n.pitch))
            self.text_edit.setText(n.text)
            self.word_edit.setChecked(n.end_word)
            self.phrase_edit.setChecked(n.line_break_after)
            self.page_override.setEnabled(n.line_break_after)
            self.page_override.setChecked(n.page_break_time is not None)
            self.page_edit.setEnabled(n.line_break_after and n.page_break_time is not None)
            self.page_edit.setValue(n.page_break_time if n.page_break_time is not None else n.time + n.length)
        else:
            self.page_edit.setEnabled(False)
        self.loading = previous
        self.timeline.update()

    def audition_note(self):
        if self.note():
            self.tones.play(self.pitch_edit.value(), .6)

    def audition_selection(self, ident):
        if self.tone_auto.isChecked() and not self.playing:
            self.audition_note()

    def preview_pitch_change(self, value):
        if not self.loading and self.note():
            self.pitch_label.setText(pitch_name(value))
            if self.tone_auto.isChecked() and not self.playing:
                self.tones.play(value, .6)

    def toggle_note_tones(self, enabled):
        self.tones.stop()
        self.sounding_note = None

    def update_note_tones(self):
        if not self.playing or not self.hear_notes.isChecked():
            return
        note = max((n for n in self.project.notes if n.time <= self.position < n.time + n.length),
                   key=lambda n: n.time, default=None)
        identity = (note.id, note.pitch) if note else None
        if identity != self.sounding_note:
            self.sounding_note = identity
            if note:
                self.tones.play(note.pitch, (note.time + note.length - self.position) / self.rate)
            else:
                self.tones.stop()

    def edit_note(self):
        n = self.note()
        if self.loading or not n:
            return
        values = (self.time_edit.value(), self.length_edit.value(), self.pitch_edit.value(),
                  self.text_edit.text(), self.word_edit.isChecked(), self.phrase_edit.isChecked(),
                  self.page_edit.value() if self.page_override.isChecked() and self.phrase_edit.isChecked() else None)
        if values == (n.time, n.length, n.pitch, n.text, n.end_word, n.line_break_after, n.page_break_time):
            return
        self.snapshot()
        n.time, n.length, n.pitch, n.text, n.end_word, n.line_break_after, n.page_break_time = values
        self.changed()

    def edit_metadata(self):
        values = self.title_edit.text(), self.artist_edit.text(), self.bpm_edit.value()
        if self.loading or values == (self.project.title, self.project.artist, self.project.bpm):
            return
        self.snapshot()
        self.project.title, self.project.artist, self.project.bpm = values
        self.changed()

    def focus_text(self, ident):
        self.select_note(ident)
        self.text_edit.setFocus()
        self.text_edit.selectAll()

    def add_note(self):
        self.snapshot()
        n = EditorNote(self.position, 60 / self.project.bpm, 60)
        self.project.notes.append(n)
        self.timeline.selected_id = n.id
        self.changed()

    def delete_note(self):
        n = self.note()
        if n:
            self.snapshot()
            self.project.notes.remove(n)
            self.timeline.selected_id = ''
            self.changed()

    def undo(self):
        if self.history:
            sources = self.project.audio_path, self.project.video_path
            draft = self.project.draft_lyrics
            self.future.append(copy.deepcopy(self.project))
            self.project = self.history.pop()
            if sources != (self.project.audio_path, self.project.video_path):
                self.configure_media()
            if draft != self.project.draft_lyrics:
                self.loading = True
                self.lyrics.setPlainText(self.project.draft_lyrics)
                self.loading = False
            self.changed()

    def redo(self):
        if self.future:
            sources = self.project.audio_path, self.project.video_path
            draft = self.project.draft_lyrics
            self.history.append(copy.deepcopy(self.project))
            self.project = self.future.pop()
            if sources != (self.project.audio_path, self.project.video_path):
                self.configure_media()
            if draft != self.project.draft_lyrics:
                self.loading = True
                self.lyrics.setPlainText(self.project.draft_lyrics)
                self.loading = False
            self.changed()

    def assign(self):
        if not self.project.notes:
            return
        self.snapshot()
        ordered = self.project.ordered()
        index = ordered.index(self.note()) if self.note() else 0
        self.project.draft_lyrics = self.lyrics.toPlainText()
        count, remaining = assign_lyrics(self.project, self.project.draft_lyrics, index, self.syllables.isChecked())
        self.changed()
        self.statusBar().showMessage(tr('notes.assigned', count=count, remaining=remaining))

    def suggest_text(self):
        def run():
            suggestion = suggest_syllables(self.lyrics.toPlainText(), self.language.currentData())
            self.snapshot()
            self.lyrics.setPlainText(suggestion)
            self.syllables.setChecked(True)
            self.changed()
        self.attempt(run)

    def confirm_discard(self):
        if not self.dirty:
            return True
        result = QMessageBox.question(self, tr('Ungespeicherte Aenderungen'), tr('Projekt speichern?'),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return self.save() if result == QMessageBox.StandardButton.Save else result == QMessageBox.StandardButton.Discard

    def replace_project(self, project, path=None):
        if not isinstance(project, StudioProject):
            raise ValueError('Importer must return a StudioProject')
        project.validate()
        self.stop()
        self.project, self.path = project, path
        self.history.clear()
        self.future.clear()
        self.dirty = path is None and project != StudioProject()
        self.timeline.origin = 0
        self.timeline.selected_id = ''
        self.loading = True
        self.lyrics.setPlainText(project.draft_lyrics or project.lyric_text())
        self.loading = False
        self.configure_media()
        self.screens.setCurrentIndex(1)
        self.refresh()

    def new(self):
        if self.confirm_discard():
            self.replace_project(StudioProject())
            self.screens.setCurrentIndex(0)

    def create_song(self):
        if not self.confirm_discard():
            return
        from studio.song_wizard import SongWizard
        wizard = SongWizard(self)
        if wizard.exec() and wizard.project:
            self.replace_project(wizard.project)
            self.offer_reference_download()
            if wizard.choice == 'scratch':
                if wizard.method.currentData() == 'plugin':
                    self.plugins_dialog()
                elif wizard.method.currentData() == 'ai':
                    self.ai_chart_dialog()

    def open_community(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('welcome.community'), '', 'OpenLips Song (*.ols)')
        if path:
            from studio.community_import import import_community
            self.attempt(lambda: self.replace_project(import_community(path)))

    def load_song_media(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('wizard.media'), '',
            'Media (*.mp4 *.mkv *.mov *.wmv *.webm *.mp3 *.wav *.flac *.m4a *.wma *.xWMA);;All files (*)')
        if path:
            is_video = Path(path).suffix.lower() in ('.mp4', '.mkv', '.mov', '.wmv', '.webm')
            candidate = copy.deepcopy(self.project)
            setattr(candidate, 'video_path' if is_video else 'audio_path', path)
            from studio.song_media_check import ensure_song_audio
            try:
                if not ensure_song_audio(candidate, self):
                    return
            except Exception as error:
                self.error(error)
                return
            self.snapshot()
            self.project = candidate
            self.configure_media()
            self.changed()

    def open(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('Projekt oeffnen'), '', 'OpenLips Studio (*.olp *.olips)')
        if path:
            self.attempt(lambda: self.replace_project(load_project(path), Path(path)))

    def save(self):
        path = str(self.path) if self.path else QFileDialog.getSaveFileName(self, tr('Projekt speichern'), self.project.title + '.olp', 'OpenLips Studio (*.olp)')[0]
        if not path:
            return False
        if not Path(path).suffix:
            path += '.olp'
        try:
            self.project.draft_lyrics = self.lyrics.toPlainText()
            save_project(self.project, path)
            self.path, self.dirty = Path(path), False
            self.refresh()
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def save_as(self):
        previous = self.path
        self.path = None
        if not self.save():
            self.path = previous

    def import_midi(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('MIDI importieren'), '', 'MIDI (*.mid *.midi)')
        if not path:
            return
        def run():
            imported = read_midi(path)
            labels = [tr('midi.track', track=l.track + 1, name=l.name, channel=l.channel + 1,
                         count=len(l.notes)) for l in imported.lanes]
            label, ok = QInputDialog.getItem(self, tr('Melodiespur'), tr('Spur / Kanal'), labels, 0, False)
            if ok:
                self.replace_project(project_from_midi(path, imported, labels.index(label)))
                if self.project.warnings:
                    QMessageBox.warning(self, tr('Importhinweise'), '\n'.join(self.project.warnings))
        self.attempt(run)

    def import_txt(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('UltraStar importieren'), '', 'UltraStar (*.txt)')
        if path:
            def run():
                project = import_ultrastar(path)
                from studio.song_media_check import ensure_song_audio
                if not ensure_song_audio(project, self):
                    return
                self.replace_project(project)
                self.offer_reference_download()
            self.attempt(run)

    def import_lrc(self):
        from studio.lrc import read_lrc
        path, _ = QFileDialog.getOpenFileName(self, tr('lrc.import'), '', 'LRC (*.lrc)')
        if path:
            self.attempt(lambda: self.accept_lrc(read_lrc(path), path))

    def accept_lrc(self, document, source=''):
        from studio.lrc import attach_lrc
        from studio.lrc_dialog import LrcDialog
        dialog = LrcDialog(document, self, project=self.project)
        if dialog.exec() != LrcDialog.DialogCode.Accepted:
            return
        self.snapshot()
        attach_lrc(self.project, document, source)
        if dialog.assign_notes.isChecked():
            from studio.lrc import assign_lrc_notes
            assign_lrc_notes(self.project, document)
        self.loading = True
        self.lyrics.setPlainText(self.project.draft_lyrics)
        self.loading = False
        self.changed()

    def review_lrc(self):
        from studio.lrc import parse_lrc
        from studio.lrc_dialog import LrcDialog
        reference = self.project.lyric_reference
        if not reference:
            self.statusBar().showMessage(tr('lrc.none'))
            return
        self.attempt(lambda: LrcDialog(parse_lrc(reference['raw']), self, importing=False).exec())

    def load_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Audio laden'), '', tr('Audio (*.mp3 *.wav *.flac *.ogg *.m4a);;Alle Dateien (*)'))
        if path:
            self.snapshot()
            self.project.audio_path = path
            self.configure_media()
            self.changed()

    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Referenzvideo laden'), '', tr('Video (*.mp4 *.mkv *.wmv *.mov *.webm);;Alle Dateien (*)'))
        if path:
            self.snapshot()
            self.project.video_path = path
            # A newly chosen music video is the master, including its soundtrack.
            self.project.audio_path = ''
            self.configure_media()
            self.changed()

    def load_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Cover laden'), '', tr('Bilder (*.jpg *.jpeg *.png *.webp *.bmp)'))
        if path:
            from studio.media import cover_image
            candidate = copy.deepcopy(self.project)
            candidate.cover_path = path
            try:
                cover_image(candidate)
            except ValueError as exc:
                self.error(exc)
                return
            self.snapshot()
            self.project.cover_path = path
            self.changed()

    def convert_media(self):
        from studio.media_dialog import MediaDialog
        MediaDialog(self.project, self).exec()

    def shift_all_notes(self):
        offset, ok = QInputDialog.getDouble(self, tr('Chart synchronisieren'),
            tr('Noten und Seiten verschieben (Sekunden; positiv = spaeter)'), 0, -900, 900, 3)
        if not ok or not offset or not self.project.notes:
            return
        shifted = copy.deepcopy(self.project)
        for note in shifted.notes:
            note.time += offset
            if note.page_break_time is not None:
                note.page_break_time += offset
        try:
            shifted.validate()
        except ValueError as exc:
            self.error(exc)
            return
        self.snapshot()
        self.project = shifted
        self.changed()
        self.statusBar().showMessage(tr('notes.shifted', count=len(shifted.notes), offset=offset))

    def configure_media(self):
        self.stop()
        self.timeline.video_frame = None
        self.player.setSource(QUrl.fromLocalFile(self.project.audio_path) if self.project.audio_path else QUrl())
        self.video_player.setSource(QUrl.fromLocalFile(self.project.video_path) if self.project.video_path else QUrl())
        self.video_audio.setVolume(self.audio.volume())
        self.video_audio.setMuted(self.audio.isMuted() or bool(self.project.audio_path))

    def video_frame(self, frame):
        self.timeline.video_frame = frame.toImage()
        self.timeline.update()

    def toggle_video(self, value):
        self.timeline.show_video = value
        self.timeline.update()

    def edit_reference(self):
        if self.loading or self.project.reference_offset == self.reference_edit.value():
            return
        self.snapshot()
        self.project.reference_offset = self.reference_edit.value()
        self.seek(self.position)
        self.changed()

    def media_duration(self):
        return max(self.player.duration(), self.video_player.duration()) / 1000 - self.project.reference_offset

    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Debug-JSON exportieren'), self.project.title + '.json', 'JSON (*.json)')
        if path:
            self.attempt(lambda: export_debug_json(self.project, path))

    def export_pair(self):
        directory = QFileDialog.getExistingDirectory(self, tr('Ausgabe uebergeordnetes Verzeichnis'))
        if not directory:
            return
        name, ok = QInputDialog.getText(self, tr('Dateiname'), tr('Asset-Basisname'), text='custom_song')
        if not ok or not name:
            return
        audio, ok = QInputDialog.getText(self, tr('Audio-Referenz'), tr('Name der bereits konvertierten xWMA-Datei'), text=name + '.xWMA')
        if ok:
            self.attempt(lambda: export_owned_pair(self.project, Path(directory) / name, name, audio))

    def export_dlc(self):
        from studio.dlc_dialog import DlcDialog
        DlcDialog(self.project, self).exec()

    def edit_preview(self):
        from studio.preview_dialog import PreviewDialog
        dialog = PreviewDialog(self.project, self)
        if dialog.exec():
            start, length = dialog.values()
            if (start, length) != (self.project.preview_start, self.project.preview_length):
                self.snapshot()
                self.project.preview_start, self.project.preview_length = start, length
                self.changed()

    def intelligent_lyric_pages(self):
        from studio.smart_pages import intelligent_pages
        candidate = copy.deepcopy(self.project)
        try:
            result = intelligent_pages(candidate)
            if result['changed']:
                self.stop()
                self.snapshot()
                self.project = candidate
                self.changed()
            self.statusBar().showMessage(tr('pages.smart_result', **result))
        except ValueError as error:
            self.error(str(error))

    def optimize_lyric_pages(self):
        from studio.page_dialog import PageDialog
        from studio.lyric_pages import optimize_pages
        dialog = PageDialog(self)
        if dialog.exec():
            candidate = copy.deepcopy(self.project)
            result = optimize_pages(candidate, dialog.chars.value(),
                                    dialog.notes.value(), dialog.seconds.value())
            if result['added_breaks']:
                self.snapshot()
                self.project = candidate
                self.changed()
            QMessageBox.information(self, tr('pages.title'), tr('pages.result', **result))

    def export_song_pack(self):
        from studio.dlc_dialog import SongPackDialog
        SongPackDialog(self.project, self).exec()

    def install_dlc_usb(self):
        from studio.usb_dialog import UsbDialog
        UsbDialog(self).exec()

    def export_community(self):
        from studio.community_dialog import CommunityExportDialog
        CommunityExportDialog(self.project, self).exec()

    def seek(self, seconds):
        self.tones.stop()
        self.sounding_note = None
        self.position = min(max(0, seconds), max(self.project.duration, self.media_duration()))
        self.clock_start = time.monotonic() - self.position / self.rate
        media_position = max(0, round((self.position + self.project.reference_offset) * 1000))
        self.player.setPosition(media_position)
        self.video_player.setPosition(media_position)
        self.update_cursor()

    def toggle_play(self):
        if self.playing:
            self.playing = False
            self.timer.stop()
            self.player.pause()
            self.video_player.pause()
            self.tones.stop()
            self.sounding_note = None
        else:
            if self.position >= max(self.project.duration, self.media_duration()):
                self.seek(0)
            self.playing = True
            self.clock_start = time.monotonic() - self.position / self.rate
            self.seek(self.position)
            if self.position + self.project.reference_offset >= 0:
                if self.project.audio_path:
                    self.player.play()
                if self.project.video_path:
                    self.video_player.play()
            self.timer.start()
        self.play_button.setIcon(qta.icon('fa5s.pause' if self.playing else 'fa5s.play', color='#cdd3d9'))

    def stop(self):
        self.tones.stop()
        self.sounding_note = None
        self.playing = False
        if hasattr(self, 'timer'):
            self.timer.stop()
        self.player.stop()
        self.video_player.stop()
        self.position = 0
        self.update_cursor()
        self.play_button.setIcon(qta.icon('fa5s.play', color='#cdd3d9'))

    def tick(self):
        master = self.player if self.project.audio_path else self.video_player
        if (self.project.audio_path or self.project.video_path) and master.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.position = max(0, master.position() / 1000 - self.project.reference_offset)
            self.clock_start = time.monotonic() - self.position / self.rate
        else:
            self.position = (time.monotonic() - self.clock_start) * self.rate
        media_position = self.position + self.project.reference_offset
        if media_position >= 0:
            for player, path in ((self.player, self.project.audio_path), (self.video_player, self.project.video_path)):
                if path and media_position * 1000 < player.duration() and player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                    player.setPosition(round(media_position * 1000))
                    player.play()
            if self.project.audio_path and self.project.video_path and abs(self.video_player.position() / 1000 - media_position) > .25:
                self.video_player.setPosition(round(media_position * 1000))
        if self.position > max(self.project.duration, self.media_duration()) + .1:
            self.toggle_play()
        self.update_note_tones()
        self.update_cursor()

    def update_cursor(self):
        self.timeline.set_cursor(self.position)
        self.clock_label.setText(f'{int(self.position // 60):02d}:{self.position % 60:06.3f}')
        self.scroll.setValue(round(self.timeline.origin / max(1, self.project.duration) * 100000))

    def scroll_to(self, value):
        self.follow_box.setChecked(False)
        self.timeline.origin = value / 100000 * max(1, self.project.duration)
        self.timeline.update()

    def set_speed(self, value):
        self.rate = float(value.rstrip('x'))
        self.player.setPlaybackRate(self.rate)
        self.video_player.setPlaybackRate(self.rate)
        self.tones.stop()
        self.sounding_note = None
        self.clock_start = time.monotonic() - self.position / self.rate

    def set_zoom(self, value):
        self.timeline.scale = value
        self.timeline.update()

    def attempt(self, callback):
        try:
            result = callback()
            self.statusBar().showMessage(f'Fertig: {result or "OK"}')
        except Exception as exc:
            self.error(exc)

    def error(self, exc):
        QMessageBox.critical(self, 'OpenLips Studio', str(exc))

    def closeEvent(self, event):
        if getattr(self, 'search_worker', None) and self.search_worker.isRunning():
            self.statusBar().showMessage(tr('Bitte Lyrics-Suche abwarten (maximal 15 Sekunden)'))
            event.ignore()
            return
        if self.confirm_discard():
            self.tones.stop()
            self.player.stop()
            self.video_player.stop()
            event.accept()
        else:
            event.ignore()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='OpenLips Studio')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--smoke-test', type=Path, help='Write a synthetic UI screenshot and exit')
    parser.add_argument('--smoke-plugin', type=Path, help='Test bundled Basic Pitch and GUI acceptance with generated tones')
    parser.add_argument('--smoke-dlc', type=Path, help='Test bundled Windows encoders and STFS with synthetic media')
    parser.add_argument('--smoke-width', type=int, default=1260)
    parser.add_argument('--smoke-height', type=int, default=790)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    from studio.fonts import use_system_font
    use_system_font(app)
    app.setApplicationName('OpenLips Studio')
    app.setOrganizationName('OpenLips')
    app.setWindowIcon(app_icon())
    app.setStyle('Fusion')
    app.setStyleSheet('''
        QWidget { background: #25292e; color: #e6e9ec; font-size: 13px; }
        QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #181c20; border: 1px solid #535c64; padding: 4px; }
        QPushButton { border: 1px solid #59636c; padding: 6px; border-radius: 4px; }
        QPushButton:hover { background: #384249; }
        QMenu { border: 1px solid #59636c; }
        QMenu::item { padding: 7px 24px; }
        QMenu::item:selected, QMenuBar::item:selected, QMenuBar::item:pressed { background: #3c5559; }
        QMenu::item:disabled { color: #8c949a; }
        QToolButton:hover { background: #384249; }
        QGroupBox { border: 1px solid #49535c; margin-top: 12px; padding-top: 12px; }
        QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        QToolBar { border: none; spacing: 5px; }
        QToolButton { padding: 6px; }
        QCheckBox { spacing: 6px; }
        QSplitter::handle { background: #49535c; }
    ''')
    window = StudioWindow()
    if args.project:
        window.attempt(lambda: window.replace_project(load_project(args.project), args.project))
    window.show()
    if args.smoke_dlc:
        from studio.dlc_smoke import run
        QTimer.singleShot(150, lambda: run(app, window, args.smoke_dlc))
    elif args.smoke_plugin:
        from studio.plugin_smoke import run
        QTimer.singleShot(150, lambda: run(app, window, args.smoke_plugin))
    elif args.smoke_test:
        window.resize(args.smoke_width, args.smoke_height)
        def capture():
            args.smoke_test.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.smoke_test)):
                app.exit(1)
                return
            app.exit(0)
        QTimer.singleShot(350, capture)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
