"""End-to-end source/frozen GUI smoke test using only original generated tones."""
import json
from pathlib import Path
import time
import sys

from PySide6.QtCore import QSettings, QTimer

from studio.basic_pitch_worker import synthetic_audio
from studio.model import StudioProject
from studio.plugin_dialog import PluginDialog


def run(app, window, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'synthetic.wav'
    synthetic_audio(source)
    window.replace_project(StudioProject(title='Plugin Test', artist='OpenLips Studio'))
    settings = QSettings(str(output / 'settings.ini'), QSettings.Format.IniFormat)
    settings.setValue('plugins/enabled', ['spotify-basic-pitch'])
    dialog = PluginDialog(window.project, window, settings)
    dialog.input.setText(str(source))
    dialog.accepted_project.connect(window.apply_plugin_notes)
    window.smoke_dialog = dialog
    dialog.show()
    dialog.run_plugin()
    started = time.monotonic()
    timer = QTimer(window)
    timer.setInterval(100)
    window.smoke_timer = timer

    def check():
        if time.monotonic() - started > 180:
            dialog.cancel()
            (output / 'error.txt').write_text('Plugin smoke timed out', encoding='utf-8')
            # Wait for process shutdown rather than destroying an active worker.
            if not dialog.busy():
                app.exit(1)
            return
        if dialog.busy():
            return
        timer.stop()
        (output / 'analysis.log').write_text(dialog.log.toPlainText(), encoding='utf-8')
        try:
            assert dialog.result is not None, dialog.status.text()
            assert {60, 64, 67}.issubset({note.pitch for note in dialog.result.notes})
            assert dialog.apply_button.isEnabled()
            assert dialog.export_button.isEnabled()
            dialog.input.setText(source.name)
            assert dialog.grab().save(str(output / 'plugins.png'))
            dialog.apply_result()
            assert window.project.notes
            assert window.project.title == 'Plugin Test'
            assert window.project.audio_path == str(source)
            assert not window.windowIcon().isNull()
            window.undo()
            assert not window.project.notes
            window.redo()
            assert window.project.notes
            app.processEvents()
            assert window.grab().save(str(output / 'editor.png'))
            (output / 'result.json').write_text(json.dumps(window.project.to_payload()), encoding='utf-8')
            app.exit(0)
        except Exception as error:
            (output / 'error.txt').write_text(str(error), encoding='utf-8')
            print(str(error), file=sys.stderr, flush=True)
            print(dialog.log.toPlainText(), file=sys.stderr, flush=True)
            app.exit(1)

    timer.timeout.connect(check)
    timer.start()
