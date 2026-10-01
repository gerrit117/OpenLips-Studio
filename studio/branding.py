"""Shared branding paths for source, wheels and frozen desktop builds."""
from pathlib import Path

from PySide6.QtGui import QIcon


def asset(name):
    return Path(__file__).resolve().parent / 'assets' / name


def app_icon():
    return QIcon(str(asset('app-icon.png')))
