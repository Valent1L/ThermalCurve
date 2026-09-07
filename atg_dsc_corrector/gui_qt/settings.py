"""Shared application preferences, independent of scientific projects."""

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


def application_settings() -> QSettings:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    path = Path(root) / "ATG-DSC" / "ATG-DSC-Tool.ini"
    return QSettings(str(path), QSettings.Format.IniFormat)
