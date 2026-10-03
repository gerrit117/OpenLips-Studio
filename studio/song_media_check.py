"""Offer a soundtrack early when a chosen video contains no audio."""
from pathlib import Path
from PySide6.QtWidgets import QMessageBox, QFileDialog
from studio.dlc_media import bundled_tool, resolve_audio_source, media_streams
from studio.i18n import tr


def ensure_song_audio(project, parent=None):
    if not project.video_path:
        return True
    probe = bundled_tool('ffprobe')
    if not probe:
        return True  # Non-Windows builds currently lack the native export tools.
    try:
        source = resolve_audio_source(project, probe)
    except ValueError:
        if QMessageBox.question(parent, tr('wizard.audio_missing'), tr('wizard.audio_missing_question'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes) == QMessageBox.StandardButton.No:
            return True
        path, _ = QFileDialog.getOpenFileName(parent, tr('wizard.select_audio'), '',
            'Audio (*.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus *.wma);;All files (*)')
        if not path:
            return False
        if 'audio' not in media_streams(Path(path), probe):
            QMessageBox.warning(parent, tr('wizard.audio_missing'), tr('export.no_audio'))
            return False
        project.audio_path = path
    else:
        if Path(source).resolve() != Path(project.video_path).resolve():
            project.audio_path = source
    return True
