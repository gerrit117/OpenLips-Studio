"""Standalone optional inference runtime. No GUI dependencies."""
from pathlib import Path
import os
import sys
from tools.create_ai_chart import main

if __name__ == '__main__':
    if getattr(sys, 'frozen', False) and '--ffmpeg' not in sys.argv:
        folder = Path(sys._MEIPASS) / 'media'
        choices = list(folder.glob('*ffmpeg*'))
        if len(choices) == 1:
            sys.argv += ['--ffmpeg', str(choices[0])]
    raise SystemExit(main())
