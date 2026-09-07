"""Panneaux natifs partagés par les espaces de comparaison et de calcul."""

from atg_dsc_corrector.i18n import tr as _t
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QSplitter, QToolButton, QVBoxLayout, QWidget,
)
from .theme import line_icon


def scroll_panel(content: QWidget, name: str = "") -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName(name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


class FoldPanel(QWidget):
    """Garde un chevron accessible quand le contenu d'un splitter est replié."""

    def __init__(self, title: str, content: QWidget, *, vertical: bool = False, expanded_size: int = 280):
        super().__init__()
        self.setObjectName("workspacePanel")
        self.content = content
        self.vertical = vertical
        self._expanded_size = expanded_size
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setObjectName("workspacePanelHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(8, 4, 4, 4)
        self.title = QLabel(title)
        self.title.setProperty("panelTitle", True)
        self.button = QToolButton()
        self.button.setCheckable(True)
        self.button.setChecked(True)
        self.button.setIcon(line_icon("up"))
        self.button.setAccessibleName(_t('Masquer ou afficher : {v1}', v1=title))
        self.button.setToolTip(_t('Masquer : {v1}', v1=title))
        row.addWidget(self.title, 1)
        row.addWidget(self.button)
        layout.addWidget(header)
        layout.addWidget(content, 1)
        self.button.toggled.connect(self.set_expanded)

    def set_expanded(self, expanded: bool) -> None:
        splitter = self.parentWidget()
        sizes = splitter.sizes() if isinstance(splitter, QSplitter) else []
        index = splitter.indexOf(self) if sizes else -1
        # Avant le premier affichage, le splitter n'a pas encore sa taille réelle.
        if not expanded and sizes and self.isVisible():
            self._expanded_size = sizes[index]
        self.content.setVisible(expanded)
        self.title.setVisible(expanded or self.vertical)
        self.button.setIcon(line_icon("up" if expanded else "down"))
        self.button.setToolTip(f"{_t('Masquer') if expanded else _t('Afficher')} : {self.title.text()}")
        if self.vertical:
            self.setMaximumHeight(16777215 if expanded else 36)
        else:
            self.setMaximumWidth(16777215 if expanded else 36)
        if sizes:
            previous = sizes[index]
            sizes[index] = max(80, self._expanded_size) if expanded else 36
            # Le centre est le premier élément vertical, le deuxième horizontal.
            center = 0 if self.vertical or index == 1 else 1
            sizes[center] = max(1, sizes[center] + previous - sizes[index])
            splitter.setSizes(sizes)
