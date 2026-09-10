"""Bouton entièrement coloré / Full-color button."""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton

from atg_dsc_corrector.i18n import tr as _t


class ColorButton(QPushButton):
    def __init__(self, color="", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(72)
        self.setText(color)

    def setText(self, text):
        color = QColor(text)
        if color.isValid():
            value = color.name().upper()
            self.setProperty("graphColor", value)
            border = '#263746' if color.lightnessF() > .5 else '#B9C9D5'
            self.setStyleSheet(f'QPushButton {{ background-color: {value}; border: 1px solid {border}; }}'
                              f'QPushButton:hover, QPushButton:focus {{ border: 2px solid {border}; }}'
                              f'QPushButton:pressed {{ border: 2px inset {border}; }}')
            super().setText("")
            self.setToolTip(value)
            self.setAccessibleName(_t("Couleur {v1}", v1=value))
        else:
            self.setProperty("graphColor", "")
            self.setStyleSheet('')
            super().setText(text)
            self.setToolTip(text)
            self.setAccessibleName(text or _t("Couleur"))
