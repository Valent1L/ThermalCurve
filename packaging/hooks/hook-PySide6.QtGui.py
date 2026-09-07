"""Ne livrer ni clavier virtuel ni lecteur PDF / Omit unused virtual keyboard and PDF reader."""

from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
# Le PDF est exporté par Matplotlib / Matplotlib handles PDF export.
binaries = [entry for entry in binaries if Path(entry[0]).name.lower()
            not in {"qtvirtualkeyboardplugin.dll", "qpdf.dll"}]
