"""Use the platform's UI font, never an icon font as an offscreen fallback."""
import os
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QFontInfo


def use_system_font(app):
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    if app.platformName() == 'offscreen':
        # Qt's Windows offscreen plugin does not enumerate installed fonts.
        # Read the host fonts only; they must never be copied into distributions.
        if os.name == 'nt':
            root = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
            for name in ('segoeui.ttf', 'segoeuib.ttf', 'segoeuii.ttf'):
                path = root / name
                if path.is_file():
                    QFontDatabase.addApplicationFont(str(path))
            if 'Segoe UI' in QFontDatabase.families():
                font = QFont('Segoe UI', 9)
        elif QFontInfo(font).family().lower() in ('', 'codicon', 'font awesome 5 free'):
            path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
                font = QFont('DejaVu Sans', 9)
    app.setFont(font)
    return font
