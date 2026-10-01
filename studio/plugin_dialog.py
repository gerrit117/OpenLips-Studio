"""Opt-in plugin manager, cancellable process jobs and explicit draft acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile

from PySide6.QtCore import QProcess, QProcessEnvironment, QSettings, QThread, QStandardPaths, Signal, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget,
    QListWidget, QCheckBox, QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QDoubleSpinBox, QSpinBox, QComboBox, QPlainTextEdit, QProgressBar, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QSplitter)
import qtawesome as qta

from studio.model import StudioProject, pitch_name
from studio.plugins import available_plugins, discover_plugins


def plugin_process_environment():
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert('PYINSTALLER_RESET_ENVIRONMENT', '1')
    if getattr(sys, 'frozen', False):
        # The separately frozen worker must not load the GUI's Python/Qt libraries.
        for key in ('DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH', 'PYTHONHOME', 'PYTHONPATH'):
            environment.remove(key)
        if sys.platform.startswith('linux'):
            original = environment.value('LD_LIBRARY_PATH_ORIG')
            if original:
                environment.insert('LD_LIBRARY_PATH', original)
            else:
                environment.remove('LD_LIBRARY_PATH')
    return environment


class ImportWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, plugin, path, parent):
        super().__init__(parent)
        self.plugin, self.path = plugin, path

    def run(self):
        try:
            result = self.plugin.import_file(Path(self.path))
            if not isinstance(result, StudioProject):
                raise ValueError('Importer must return a StudioProject')
            result.validate()
            self.result.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class PackageInstallWorker(QThread):
    installed = Signal(str, str)
    failed = Signal(str)

    def __init__(self, path, root, parent):
        super().__init__(parent)
        self.path, self.root = path, root

    def run(self):
        try:
            from studio.plugin_package import install_package
            folder = install_package(self.path, self.root)
            manifest = json.loads((folder / 'openlips-plugin.json').read_text(encoding='utf-8'))
            self.installed.emit(str(folder), manifest['id'])
        except Exception as error:
            self.failed.emit(str(error))


class PluginDialog(QDialog):
    accepted_project = Signal(object)

    def __init__(self, project, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle('Plugins · OpenLips Studio')
        self.resize(920, 690)
        self.setMinimumSize(720, 520)
        self.settings = settings if settings is not None else QSettings('OpenLips', 'OpenLips Studio')
        self.plugin = None
        self.result = None
        self.worker = None
        self.process = None
        self.temp = None
        self.cancelled = False
        self.output_buffer = b''
        self.controls = {}
        self.updating = False
        self.project = project
        self.enabled_ids = self.settings.value('plugins/enabled', [], type=list)
        self.folders = self.settings.value('plugins/folders', [], type=list)
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        self.list = QListWidget()
        self.list.setMinimumWidth(160)
        left_layout.addWidget(self.list)
        self.add_button = QPushButton(qta.icon('fa5s.folder-plus', color='#cdd3d9'), 'Plugin hinzufügen')
        self.add_button.clicked.connect(self.add_folder)
        left_layout.addWidget(self.add_button)
        self.install_button = QPushButton(qta.icon('fa5s.file-import', color='#cdd3d9'), '.opl installieren')
        self.install_button.clicked.connect(self.install_opl)
        left_layout.addWidget(self.install_button)
        self.remove_button = QPushButton(qta.icon('fa5s.unlink', color='#cdd3d9'), 'Verknüpfung entfernen')
        self.remove_button.setToolTip('Lokalen Plugin-Ordner aus Studio entfernen; Dateien bleiben erhalten')
        self.remove_button.clicked.connect(self.remove_folder)
        left_layout.addWidget(self.remove_button)
        splitter.addWidget(left)
        right = QWidget()
        body = QVBoxLayout(right)
        body.setContentsMargins(0, 0, 0, 0)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(self.details)
        self.enable = QCheckBox('Plugin aktivieren (nur vertrauenswürdige Quellen)')
        self.enable.clicked.connect(self.enable_selected)
        body.addWidget(self.enable)
        form = QFormLayout()
        source = QWidget()
        row = QHBoxLayout(source)
        row.setContentsMargins(0, 0, 0, 0)
        self.input = QLineEdit(project.audio_path)
        row.addWidget(self.input)
        self.browse_button = QPushButton(qta.icon('fa5s.folder-open', color='#cdd3d9'), '')
        self.browse_button.setToolTip('Quelldatei auswählen')
        self.browse_button.clicked.connect(self.choose_input)
        row.addWidget(self.browse_button)
        form.addRow('Quelldatei', source)
        self.runtime = QLineEdit()
        self.runtime.setPlaceholderText('Gebündelte Runtime verwenden')
        self.runtime.setToolTip('Optional für Entwickler: Python aus einer Basic-Pitch-Umgebung. Nicht die Studio-EXE.')
        self.runtime.textChanged.connect(self.runtime_changed)
        form.addRow('Python (optional)', self.runtime)
        self.runtime_label = form.labelForField(self.runtime)
        body.addLayout(form)
        self.parameters = QWidget()
        self.parameter_form = QFormLayout(self.parameters)
        self.parameter_form.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self.parameters)
        scroll.setMinimumHeight(225)
        body.addWidget(scroll)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        body.addWidget(self.progress)
        self.status = QLabel('Plugin auswählen und aktivieren')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        body.addWidget(self.status)
        self.tabs = QTabWidget()
        self.preview = QTableWidget(0, 4)
        self.preview.setHorizontalHeaderLabels(['Start (s)', 'Länge (s)', 'Ton', 'Text'])
        self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.preview, 'Notenentwurf')
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.tabs.addTab(self.log, 'Protokoll')
        body.addWidget(self.tabs, 1)
        buttons = QHBoxLayout()
        self.run_button = QPushButton(qta.icon('fa5s.play', color='#cdd3d9'), 'Analysieren')
        self.cancel_button = QPushButton(qta.icon('fa5s.stop', color='#cdd3d9'), 'Abbrechen')
        self.apply_button = QPushButton(qta.icon('fa5s.check', color='#cdd3d9'), 'Noten übernehmen')
        self.export_button = QPushButton(qta.icon('fa5s.file-export', color='#cdd3d9'), 'MIDI speichern')
        self.run_button.clicked.connect(self.run_plugin)
        self.cancel_button.clicked.connect(self.cancel)
        self.apply_button.clicked.connect(self.apply_result)
        self.export_button.clicked.connect(self.export_midi)
        for button in (self.run_button, self.cancel_button, self.apply_button, self.export_button):
            buttons.addWidget(button)
        body.addLayout(buttons)
        splitter.addWidget(right)
        splitter.setSizes([200, 700])
        layout.addWidget(splitter)
        self.list.currentRowChanged.connect(self.select_plugin)
        self.refresh_offers()

    def refresh_offers(self):
        self.offers, errors = available_plugins(self.folders)
        self.list.clear()
        self.list.addItems([offer.label for offer in self.offers])
        for error in errors:
            self.log.appendPlainText(error)
        if self.offers:
            self.list.setCurrentRow(0)

    def busy(self):
        return ((self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning)
                or (self.worker is not None and self.worker.isRunning()))

    def select_plugin(self, index):
        self.result = None
        self.preview.setRowCount(0)
        self.plugin = None
        if not 0 <= index < len(self.offers):
            self.update_buttons()
            return
        offer = self.offers[index]
        self.details.setText(f'{offer.label}\n{offer.source}')
        self.enable.setChecked(offer.id in self.enabled_ids)
        while self.parameter_form.rowCount():
            self.parameter_form.removeRow(0)
        self.controls.clear()
        if self.enable.isChecked():
            plugins, errors = discover_plugins([offer.id], self.folders)
            for error in errors:
                self.log.appendPlainText(error)
            if plugins:
                self.plugin = plugins[0]
                plugin = self.plugin
                permissions = ', '.join(plugin.permissions) or 'Not declared'
                self.details.setText(f'{plugin.label} {plugin.version} · {plugin.author}\n{plugin.description}\n{plugin.homepage}\nPermissions (informational): {permissions}')
                for parameter in plugin.parameters:
                    value = self.settings.value(f'plugins/{plugin.id}/{parameter.key}', parameter.default)
                    if parameter.kind in ('int', 'float'):
                        control = QSpinBox() if parameter.kind == 'int' else QDoubleSpinBox()
                        if parameter.kind == 'int':
                            control.setRange(int(parameter.minimum), int(parameter.maximum))
                        else:
                            control.setRange(parameter.minimum, parameter.maximum)
                        if parameter.kind == 'float':
                            control.setDecimals(2)
                            control.setSingleStep(.05)
                        control.setValue(int(value) if parameter.kind == 'int' else float(value))
                    elif parameter.kind == 'bool':
                        control = QCheckBox()
                        control.setChecked(str(value).lower() in ('true', '1'))
                    elif parameter.kind == 'text':
                        control = QLineEdit(str(value))
                        control.setMaxLength(8192)
                    else:
                        control = QComboBox()
                        for label, data in parameter.choices:
                            control.addItem(label, data)
                        control.setCurrentIndex(max(0, control.findData(value)))
                    self.controls[parameter.key] = control
                    self.parameter_form.addRow(parameter.label, control)
        self.updating = True
        self.runtime.setText(self.settings.value(f'plugins/{offer.id}/python', '', type=str))
        self.updating = False
        self.runtime.setVisible(self.plugin is not None and not self.plugin.process_plugin and not getattr(sys, 'frozen', False))
        self.runtime_label.setVisible(self.runtime.isVisibleTo(self))
        self.status.setText('Bereit' if self.plugin else 'Zum Verwenden aktivieren')
        self.update_buttons()

    def enable_selected(self, checked):
        index = self.list.currentRow()
        if index < 0:
            return
        offer = self.offers[index]
        if checked:
            answer = QMessageBox.warning(self, 'Plugin vertrauen?',
                'Dieses Plugin führt Code mit deinen Benutzerrechten aus und ist nicht sandboxed. Es kann Dateien und Netzwerk verwenden. Nur vertrauenswürdige Quellen aktivieren.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.enable.setChecked(False)
                return
        if checked and offer.id not in self.enabled_ids:
            self.enabled_ids.append(offer.id)
        elif not checked and offer.id in self.enabled_ids:
            self.enabled_ids.remove(offer.id)
        self.settings.setValue('plugins/enabled', self.enabled_ids)
        self.select_plugin(index)

    def runtime_changed(self, value):
        if not self.updating and self.list.currentRow() >= 0:
            self.settings.setValue(f'plugins/{self.offers[self.list.currentRow()].id}/python', value.strip())

    def add_folder(self):
        if self.busy():
            return
        folder = QFileDialog.getExistingDirectory(self, 'Plugin-Ordner mit openlips-plugin.json')
        if folder and folder not in self.folders:
            self.folders.append(folder)
            self.settings.setValue('plugins/folders', self.folders)
            self.refresh_offers()

    def install_opl(self):
        if self.busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Plugin installieren', '', 'OpenLips Plugin (*.opl)')
        if not path:
            return
        try:
            from studio.plugin_package import inspect_package
            manifest = inspect_package(path)
            if manifest['id'] in [offer.id for offer in self.offers]:
                raise ValueError('A plugin with this ID is already available. Disable/remove its link first.')
            root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'plugins'
            self.process = None
            self.worker = PackageInstallWorker(path, root, self)
            self.worker.installed.connect(self.package_installed)
            self.worker.failed.connect(self.fail)
            self.worker.finished.connect(self.update_buttons)
            self.progress.setRange(0, 0)
            self.status.setText('Plugin wird installiert …')
            self.worker.start()
            self.update_buttons()
        except Exception as error:
            self.fail(str(error))

    def package_installed(self, folder, ident):
        self.folders.append(folder)
        self.settings.setValue('plugins/folders', self.folders)
        self.refresh_offers()
        index = next(i for i, offer in enumerate(self.offers) if offer.id == ident)
        self.list.setCurrentRow(index)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText('Installiert, noch nicht aktiviert. Nur vertrauenswürdige Plugins aktivieren.')

    def choose_input(self):
        extensions = ' '.join('*' + ext for ext in self.plugin.extensions) if self.plugin else '*'
        path, _ = QFileDialog.getOpenFileName(self, 'Quelldatei', '', f'Plugin-Dateien ({extensions})')
        if path:
            self.input.setText(path)

    def remove_folder(self):
        index = self.list.currentRow()
        if self.busy() or index < 0:
            return
        offer = self.offers[index]
        self.folders = [folder for folder in self.folders if str(Path(folder)) != offer.source]
        self.enabled_ids = [ident for ident in self.enabled_ids if ident != offer.id]
        self.settings.setValue('plugins/folders', self.folders)
        self.settings.setValue('plugins/enabled', self.enabled_ids)
        self.refresh_offers()

    def options(self):
        values = {}
        for key, control in self.controls.items():
            if isinstance(control, QComboBox):
                value = control.currentData()
            elif isinstance(control, QCheckBox):
                value = control.isChecked()
            elif isinstance(control, QLineEdit):
                value = control.text()
            else:
                value = control.value()
            values[key] = value
            self.settings.setValue(f'plugins/{self.plugin.id}/{key}', value)
        return values

    def update_buttons(self):
        running = self.busy()
        self.list.setEnabled(not running)
        self.add_button.setEnabled(not running)
        self.install_button.setEnabled(not running)
        index = self.list.currentRow()
        local = index >= 0 and any(str(Path(folder)) == self.offers[index].source for folder in self.folders)
        self.remove_button.setEnabled(not running and local)
        self.enable.setEnabled(not running)
        self.input.setEnabled(not running)
        self.runtime.setEnabled(not running)
        self.parameters.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.run_button.setEnabled(self.plugin is not None and not running)
        # Legacy in-process importers cannot be forcibly cancelled safely.
        self.cancel_button.setEnabled(running and self.process is not None)
        self.apply_button.setEnabled(self.result is not None and not running)
        midi = self.temp is not None and (Path(self.temp.name) / 'draft.mid').is_file()
        self.export_button.setEnabled(self.result is not None and not running and midi)

    def run_plugin(self):
        if self.busy() or not self.plugin:
            return
        self.result = None
        self.preview.setRowCount(0)
        self.log.clear()
        self.cancelled = False
        self.output_buffer = b''
        self.progress.setRange(0, 0)
        try:
            source = Path(self.input.text()).resolve(strict=True)
            if not source.is_file():
                raise ValueError('Please select a file')
            options = self.options()
            if self.temp:
                self.temp.cleanup()
            self.temp = tempfile.TemporaryDirectory(prefix='openlips-plugin-')
            output = Path(self.temp.name)
            if self.plugin.create_command:
                request = output / 'request.json'
                request.write_text(json.dumps({'protocol': 1, 'input': str(source), 'options': options,
                                              'project': self.project.to_payload()}, ensure_ascii=False, allow_nan=False), encoding='utf-8')
                python = '' if getattr(sys, 'frozen', False) else self.runtime.text().strip()
                command = self.plugin.create_command(request, output, python)
                if not command or not all(isinstance(part, str) for part in command):
                    raise ValueError('Plugin command must be an argument list')
                self.process = QProcess(self)
                self.process.setProcessEnvironment(plugin_process_environment())
                self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
                self.process.readyReadStandardOutput.connect(self.read_output)
                self.process.finished.connect(self.process_finished)
                self.process.errorOccurred.connect(self.process_error)
                self.process.start(command[0], command[1:])
            else:
                self.process = None
                self.worker = ImportWorker(self.plugin, source, self)
                self.worker.result.connect(self.show_result)
                self.worker.failed.connect(self.fail)
                self.worker.finished.connect(self.update_buttons)
                self.worker.start()
            self.status.setText('Analyse läuft lokal …')
        except Exception as error:
            self.fail(str(error))
        self.update_buttons()

    def read_output(self):
        self.output_buffer += bytes(self.process.readAllStandardOutput())
        while b'\n' in self.output_buffer:
            line, self.output_buffer = self.output_buffer.split(b'\n', 1)
            self.read_line(line.decode('utf-8', errors='replace')[:8192])
        if len(self.output_buffer) > 65536:
            self.read_line(self.output_buffer[:8192].decode('utf-8', errors='replace'))
            self.output_buffer = b''

    def read_line(self, line):
        self.log.appendPlainText(line)
        if line.startswith('OPENLIPS_PLUGIN:'):
            try:
                data = json.loads(line.split(':', 1)[1])
                self.status.setText(str(data['message']))
            except (ValueError, KeyError, TypeError):
                pass

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.fail(self.process.errorString())

    def process_finished(self, exit_code, exit_status):
        self.read_output()
        if self.output_buffer:
            self.read_line(self.output_buffer.decode('utf-8', errors='replace')[:8192])
            self.output_buffer = b''
        if self.cancelled:
            self.fail('Analyse abgebrochen. Das Projekt wurde nicht geändert.')
            return
        if exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            self.log.appendPlainText(f'Worker exit_code={exit_code}, exit_status={exit_status.name}, error={self.process.errorString()}')
            self.fail('Analyse fehlgeschlagen. Details stehen im Protokoll.')
            return
        try:
            path = Path(self.temp.name) / 'result.json'
            path.resolve(strict=True).relative_to(Path(self.temp.name).resolve())
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError('Plugin result exceeds 64 MiB')
            result = StudioProject.from_payload(json.loads(path.read_text(encoding='utf-8')))
            self.show_result(result)
        except Exception as error:
            self.fail(str(error))

    def show_result(self, result):
        if not result.notes:
            self.fail('Keine Noten gefunden.')
            return
        self.result = result
        notes = result.ordered()[:200]
        self.preview.setRowCount(len(notes))
        for row, note in enumerate(notes):
            for column, value in enumerate((f'{note.time:.3f}', f'{note.length:.3f}', pitch_name(note.pitch), note.text)):
                self.preview.setItem(row, column, QTableWidgetItem(value))
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText(f'{len(result.notes)} Noten · {result.duration:.2f} s · Vorschau: erste {len(notes)}')
        for warning in result.warnings:
            self.log.appendPlainText(warning)
        self.tabs.setCurrentIndex(0)
        self.update_buttons()

    def fail(self, message):
        self.result = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(str(message))
        self.log.appendPlainText(str(message))
        self.tabs.setCurrentIndex(1)
        self.update_buttons()

    def cancel(self):
        if self.process and self.busy():
            self.cancelled = True
            self.process.kill()

    def apply_result(self):
        if not self.result or self.busy():
            return
        if self.project.notes and QMessageBox.question(self, 'Noten ersetzen?',
            'Die vorhandenen Noten einschließlich Textzuordnung werden ersetzt. Metadaten und Textentwurf bleiben erhalten. Rückgängig ist möglich.') != QMessageBox.StandardButton.Yes:
            return
        self.accepted_project.emit(self.result)
        self.accept()

    def export_midi(self):
        if not self.result or not self.temp:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'MIDI-Entwurf speichern', self.result.title + '.mid', 'MIDI (*.mid)')
        if path:
            if not Path(path).suffix:
                path += '.mid'
            try:
                source = Path(self.temp.name) / 'draft.mid'
                source.resolve(strict=True).relative_to(Path(self.temp.name).resolve())
                shutil.copyfile(source, path)
            except OSError as error:
                self.status.setText(str(error))
                self.log.appendPlainText(str(error))

    def done(self, result):
        if self.busy():
            self.status.setText('Analyse zuerst abbrechen oder abwarten.')
            return
        if self.temp:
            self.temp.cleanup()
            self.temp = None
        super().done(result)

    def closeEvent(self, event):
        if self.busy():
            event.ignore()
        else:
            super().closeEvent(event)
