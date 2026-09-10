"""Apparence Qt et couleurs du graphique réservées à l'écran."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from atg_dsc_corrector.i18n import tr as _t

from matplotlib import get_data_path
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from atg_dsc_corrector.legend import EditableLegend
from matplotlib.text import Text
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette, QIcon, QIconEngine, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QTableView, QProxyStyle, QStyle


class LineIcon(QIconEngine):
    """Traits vectoriels monochromes, recolorés à chaque rendu Qt."""

    paths = {
        "info": (((12, 11), (12, 17)), ((12, 7), (12, 8))),
        "edit": (((4, 16), (15, 5), (19, 9), (8, 20), (3, 21), (4, 16)), ((13, 7), (17, 11))),
        "legend": (((3, 4), (21, 4), (21, 20), (3, 20), (3, 4)), ((6, 9), (10, 9)), ((13, 9), (18, 9)), ((6, 15), (10, 15)), ((13, 15), (18, 15))),
        "delete": (((4, 6), (20, 6)), ((9, 6), (9, 3), (15, 3), (15, 6)), ((6, 6), (7, 21), (17, 21), (18, 6)), ((10, 10), (10, 17)), ((14, 10), (14, 17))),
        "gear": (((9, 3), (15, 3), (15, 6), (18, 8), (21, 8), (21, 15), (18, 15), (15, 18), (15, 21), (9, 21), (9, 18), (6, 15), (3, 15), (3, 8), (6, 8), (9, 6), (9, 3)),),
        "import": (((3, 9), (3, 20), (21, 20), (21, 9)), ((12, 3), (12, 15)), ((7, 10), (12, 15), (17, 10))),
        "export": (((3, 15), (3, 20), (21, 20), (21, 15)), ((12, 16), (12, 3)), ((7, 8), (12, 3), (17, 8))),
        "save": (((4, 3), (17, 3), (21, 7), (21, 21), (3, 21), (3, 3), (4, 3)), ((7, 3), (7, 9), (16, 9), (16, 3)), ((7, 21), (7, 14), (17, 14), (17, 21))),
        "compare": (((3, 20), (3, 4)), ((3, 20), (21, 20)), ((6, 16), (11, 9), (16, 12), (21, 5)), ((6, 10), (11, 5), (16, 8), (21, 3))),
        "home": (((3, 11), (12, 3), (21, 11)), ((5, 10), (5, 21), (10, 21), (10, 15), (14, 15), (14, 21), (19, 21), (19, 10))),
        "back": (((14, 5), (7, 12), (14, 19)), ((7, 12), (21, 12))),
        "forward": (((10, 5), (17, 12), (10, 19)), ((3, 12), (17, 12))),
        "pan": (((12, 3), (12, 21)), ((3, 12), (21, 12)), ((9, 6), (12, 3), (15, 6)), ((9, 18), (12, 21), (15, 18)), ((6, 9), (3, 12), (6, 15)), ((18, 9), (21, 12), (18, 15))),
        "zoom": (((15, 15), (21, 21)), ((7, 10), (13, 10)), ((10, 7), (10, 13))),
        "settings": (((4, 6), (20, 6)), ((4, 12), (20, 12)), ((4, 18), (20, 18)), ((8, 3), (8, 9)), ((16, 9), (16, 15)), ((10, 15), (10, 21))),
        "up": (((6, 14), (12, 8), (18, 14)),),
        "down": (((6, 10), (12, 16), (18, 10)),),
        "add": (((5, 12), (19, 12)), ((12, 5), (12, 19))),
        "copy": (((8, 7), (20, 7), (20, 21), (8, 21), (8, 7)), ((16, 7), (16, 3), (4, 3), (4, 17), (8, 17))),
        "check": (((4, 12), (9, 17), (20, 6)),),
    }

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def clone(self):
        return LineIcon(self.name)

    def paint(self, painter, rect, mode, state):
        palette = QApplication.palette()
        group = QPalette.ColorGroup.Disabled if mode == QIcon.Mode.Disabled else QPalette.ColorGroup.Active
        role = QPalette.ColorRole.HighlightedText if mode == QIcon.Mode.Selected else QPalette.ColorRole.ButtonText
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(rect.width(), rect.height())
        painter.translate(rect.center().x() - size / 2, rect.center().y() - size / 2)
        painter.scale(size / 24, size / 24)
        painter.setPen(QPen(palette.color(group, role), 1.6, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for path in self.paths[self.name]:
            for (x1, y1), (x2, y2) in zip(path, path[1:]):
                painter.drawLine(x1, y1, x2, y2)
        if self.name == "zoom":
            painter.drawEllipse(3, 3, 14, 14)
        if self.name == "gear":
            painter.drawEllipse(8, 8, 8, 8)
        if self.name == "info":
            painter.drawEllipse(3, 3, 18, 18)
        painter.restore()

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap


def line_icon(name: str) -> QIcon:
    return QIcon(LineIcon(name))


def style_plot_toolbar(toolbar) -> None:
    labels = {
        "home": _t("Vue initiale"), "back": _t("Vue précédente"),
        "forward": _t("Vue suivante"), "pan": _t("Déplacer le graphique"),
        "zoom": _t("Zoom rectangulaire"), "save_figure": _t("Enregistrer la figure"),
    }
    for callback, name in (("home", "home"), ("back", "back"), ("forward", "forward"),
                           ("pan", "pan"), ("zoom", "zoom"), ("save_figure", "save")):
        if callback in toolbar._actions:
            toolbar._actions[callback].setIcon(line_icon(name))
            toolbar._actions[callback].setText(labels[callback])
            toolbar._actions[callback].setToolTip(labels[callback])


class PlotToolbar(NavigationToolbar2QT):
    # All presentation edits use the application's translated, persistent dialog.
    toolitems = tuple(item for item in NavigationToolbar2QT.toolitems
                      if item[3] not in {"edit_parameters", "configure_subplots"})


@dataclass(frozen=True)
class LightTheme:
    background: str = "#F4F7F9"
    surface: str = "#FFFFFF"
    alternate_surface: str = "#EEF3F7"
    foreground: str = "#17212B"
    muted_foreground: str = "#4D5D6C"
    border: str = "#C9D3DC"
    checkbox_border: str = "#6F7F8D"
    interactive: str = "#205C8F"
    interactive_hover: str = "#17466D"
    on_interactive: str = "#FFFFFF"
    inactive_selection: str = "#D8E2EA"
    focus: str = "#9A5B00"
    error: str = "#B42318"
    success: str = "#24704A"


_FALLBACK_FONT_ID = -1


class CheckboxContrastStyle(QProxyStyle):
    """Keep native checkbox states and geometry, with a clearer light-theme outline."""

    def drawPrimitive(self, element, option, painter, widget=None):
        super().drawPrimitive(element, option, painter, widget)
        if element in (QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                       QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck):
            tokens = LightTheme()
            color = tokens.checkbox_border if option.state & QStyle.StateFlag.State_Enabled else tokens.border
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(color), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(option.rect).adjusted(.5, .5, -.5, -.5), 2, 2)
            painter.restore()


def appearance_palette(theme: str = "light") -> LightTheme:
    if theme not in {"light", "dark"}:
        raise ValueError("Apparence inconnue.")
    if theme == "dark":
        return LightTheme(
            background="#171C24", surface="#222A35", alternate_surface="#293441",
            foreground="#EDF3F8", muted_foreground="#B7C4D1", border="#607384",
            interactive="#58C9DF",
            interactive_hover="#8ADCF0", on_interactive="#11222B",
            inactive_selection="#344B5B", focus="#F1C16B",
            error="#FFB4AB", success="#85D9AE",
        )
    return replace(
        LightTheme(),
        interactive="#086675",
        interactive_hover="#104B5C",
    )


class ThemedFigureCanvas(FigureCanvasQTAgg):
    """Colore le rendu écran sans changer les artistes utilisés par les exports."""

    screen_theme: LightTheme | None = None

    def draw(self) -> None:
        legends = [axes.get_legend() for axes in self.figure.axes
                   if isinstance(axes.get_legend(), EditableLegend)]
        for legend in legends:
            legend._position_cache = {}
        try:
            self._draw_themed()
        finally:
            for legend in legends:
                legend._position_cache = None

    def _draw_themed(self) -> None:
        tokens = self.screen_theme
        if tokens is None or self.is_saving():
            super().draw()
            return
        restored = []
        legend_texts = set()

        def color(artist, name, value):
            if getattr(artist, "_thermalcurve_custom_color", False):
                return
            setter = getattr(artist, f"set_{name}")
            restored.append((setter, getattr(artist, f"get_{name}")()))
            setter(value)

        try:
            color(self.figure, "facecolor", tokens.background)
            # Matplotlib crée les graduations à la demande : les matérialiser
            # avant de recolorer tous les textes, y compris les axes secondaires.
            for axes in [*self.figure.axes, *(child for parent in self.figure.axes for child in parent.child_axes)]:
                color(axes, "facecolor", tokens.surface)
                for spine in axes.spines.values():
                    color(spine, "edgecolor", tokens.muted_foreground)
                for line in axes.lines:
                    if getattr(line, "_thermalcurve_axis_arrow", False):
                        color(line, "color", tokens.muted_foreground)
                for axis in (axes.xaxis, axes.yaxis):
                    for kind, ticks in (("major", axis.get_major_ticks()), ("minor", axis.get_minor_ticks())):
                        for tick in ticks:
                            if not getattr(axis, f"_thermalcurve_tick_{kind}_color", False):
                                color(tick.tick1line, "markeredgecolor", tokens.muted_foreground)
                                color(tick.tick2line, "markeredgecolor", tokens.muted_foreground)
                            if not getattr(axis, f"_thermalcurve_grid_{kind}_color", False):
                                color(tick.gridline, "color", tokens.border)
                legend = axes.get_legend()
                if isinstance(legend, EditableLegend):
                    # User-selected legend colors apply equally on screen and in exports.
                    legend_texts.update(legend.get_texts())
                elif legend is not None:
                    color(legend.get_frame(), "facecolor", tokens.surface)
                    color(legend.get_frame(), "edgecolor", tokens.border)
            for label in self.figure.findobj(Text):
                if label not in legend_texts:
                    color(label, "color", tokens.foreground)
            super().draw()
        finally:
            for setter, value in reversed(restored):
                setter(value)


def _application_font() -> QFont:
    """Utilise la police système, avec un repli local pour Qt hors écran."""

    global _FALLBACK_FONT_ID
    if QFontDatabase.families():
        return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)

    fallback_path = Path(get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    if _FALLBACK_FONT_ID < 0:
        _FALLBACK_FONT_ID = QFontDatabase.addApplicationFont(str(fallback_path))
    families = QFontDatabase.applicationFontFamilies(_FALLBACK_FONT_ID)
    return QFont(families[0] if families else "Sans Serif")


def apply_application_theme(
    app: QApplication, theme: str = "light", *, set_font: bool = True
) -> None:
    """Applique Fusion, la police système et des rôles de couleur accessibles."""

    tokens = appearance_palette(theme)
    radius = 6
    height = 22
    padding = 2
    app.setStyle(CheckboxContrastStyle("Fusion") if theme == "light" else "Fusion")
    if set_font:
        font = _application_font()
        if font.pointSizeF() < 10.5:
            font.setPointSizeF(10.5)
        app.setFont(font)
    palette = app.palette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        palette.setColor(group, QPalette.ColorRole.Window, QColor(tokens.background))
        palette.setColor(group, QPalette.ColorRole.WindowText, QColor(tokens.foreground))
        palette.setColor(group, QPalette.ColorRole.Base, QColor(tokens.surface))
        palette.setColor(
            group,
            QPalette.ColorRole.AlternateBase,
            QColor(tokens.alternate_surface),
        )
        palette.setColor(group, QPalette.ColorRole.Text, QColor(tokens.foreground))
        palette.setColor(group, QPalette.ColorRole.Button, QColor(tokens.surface))
        palette.setColor(group, QPalette.ColorRole.ButtonText, QColor(tokens.foreground))
        palette.setColor(group, QPalette.ColorRole.ToolTipBase, QColor(tokens.surface))
        palette.setColor(group, QPalette.ColorRole.ToolTipText, QColor(tokens.foreground))
        palette.setColor(group, QPalette.ColorRole.PlaceholderText, QColor(tokens.muted_foreground))
        palette.setColor(group, QPalette.ColorRole.Link, QColor(tokens.interactive))
    palette.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.Highlight,
        QColor(tokens.interactive),
    )
    palette.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.HighlightedText,
        QColor(tokens.on_interactive),
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.Highlight,
        QColor(tokens.inactive_selection),
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.HighlightedText,
        QColor(tokens.foreground),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Base,
        QColor(tokens.background),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.AlternateBase,
        QColor(tokens.alternate_surface),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(tokens.muted_foreground),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
        QColor(tokens.muted_foreground),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(tokens.muted_foreground),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Highlight,
        QColor(tokens.inactive_selection),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.HighlightedText,
        QColor(tokens.foreground),
    )
    app.setPalette(palette)
    app.setStyleSheet(
        f"""
        QMainWindow, QDialog {{
            background: {tokens.background};
        }}
        QWidget {{
            color: {tokens.foreground};
        }}
        QGroupBox {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {radius}px;
            margin-top: 1.2em;
            padding-top: 0.5em;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}
        QLabel#pageTitle, QLabel[pageTitle="true"] {{
            font-size: 16pt;
            font-weight: 600;
            color: {tokens.foreground};
        }}
        QLabel#pageSubtitle, QLabel[secondary="true"] {{
            color: {tokens.muted_foreground};
        }}
        QLabel#workspaceTitle {{
            font-size: 12pt;
            font-weight: 600;
            padding: 4px 12px;
        }}
        QWidget#workspacePanel {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {radius}px;
        }}
        QWidget#workspacePanelHeader {{
            background: {tokens.surface};
            border-bottom: 1px solid {tokens.border};
        }}
        QGroupBox#comparisonFiles {{ border: 0; margin: 0; padding: 0; }}
        QTreeView#comparisonTable, QTableWidget#equationsList {{ border: 0; }}
        QTreeView#comparisonTable::item, QTableWidget#equationsList::item {{
            padding: 4px;
            border-bottom: 2px solid {tokens.surface};
        }}
        QLineEdit#reactionEquation {{
            font-size: 14pt;
            padding: 10px;
            min-height: 38px;
        }}
        QWidget#massSummaryCard {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {radius}px;
        }}
        QWidget#massSummaryCard[console="true"] {{ border: 0; }}
        QWidget#massSummaryCard[massChange="true"] {{
            background: {'#294B38' if theme == 'dark' else '#C2F1C8'};
            border: 1px solid {'#73A184' if theme == 'dark' else '#A0CCA7'};
        }}
        QWidget#massSummaryCard[massChange="true"] QLabel {{
            color: {'#D8F3DE' if theme == 'dark' else '#21452B'};
        }}
        QLabel#massSummaryValue {{
            color: {tokens.interactive};
            font-size: 15pt;
            font-weight: 600;
        }}
        QLabel[panelTitle="true"] {{
            font-weight: 600;
            padding: 4px 8px;
        }}
        QLabel#displayStage {{
            background: {tokens.interactive};
            color: {tokens.on_interactive};
            padding: 6px 12px;
            border-radius: {radius}px;
        }}
        QLabel[error="true"] {{
            color: {tokens.error};
        }}
        QPushButton {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {radius}px;
            min-height: {height}px;
            padding: {padding}px 10px;
        }}
        QPushButton:hover {{
            border-color: {tokens.interactive};
        }}
        QPushButton[primary="true"] {{
            background: {tokens.interactive};
            border-color: {tokens.interactive};
            color: {tokens.on_interactive};
            font-weight: 600;
        }}
        QPushButton[primary="true"]:hover {{
            background: {tokens.interactive_hover};
        }}
        QPushButton:disabled, QPushButton[primary="true"]:disabled {{
            color: {tokens.muted_foreground};
            background: {tokens.background};
        }}
        QPushButton:focus, QToolButton:focus, QComboBox:focus, QCheckBox:focus, QLineEdit:focus,
        QAbstractItemView:focus {{
            border: 2px solid {tokens.focus};
        }}
        QComboBox, QLineEdit {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {radius}px;
            min-height: {height}px;
            padding: 2px 8px;
        }}
        QPlainTextEdit {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {radius}px;
        }}
        QAbstractItemView {{
            background: {tokens.surface};
            alternate-background-color: {tokens.alternate_surface};
            color: {tokens.foreground};
            border: 1px solid {tokens.border};
        }}
        QAbstractItemView:disabled {{
            background: {tokens.background};
            alternate-background-color: {tokens.alternate_surface};
            color: {tokens.muted_foreground};
        }}
        QScrollArea {{
            border: 0;
        }}
        QSplitter::handle {{
            background: {tokens.border};
            border: 0;
        }}
        QSplitter::handle:horizontal {{
            width: 3px;
        }}
        QSplitter::handle:vertical {{
            height: 3px;
        }}
        QHeaderView {{ background: {tokens.alternate_surface}; }}
        QHeaderView::section {{
            background: {tokens.alternate_surface};
            color: {tokens.muted_foreground};
            font-weight: 600;
            padding: 6px 10px;
            border: 0;
            border-bottom: 1px solid {tokens.border};
        }}
        QHeaderView::section:vertical {{
            padding: 4px 8px;
            border-right: 1px solid {tokens.border};
        }}
        QHeaderView::section:checked {{ color: {tokens.interactive}; }}
        QTableCornerButton::section {{ background: {tokens.alternate_surface}; border: 0; }}
        QTableView {{ gridline-color: {tokens.alternate_surface}; }}
        QTableWidget#zonesTable:focus, QTableWidget#zoneResultsTable:focus {{
            border: 1px solid {tokens.border};
            outline: none;
        }}
        QTableWidget#zonesTable QComboBox, QTableWidget#zonesTable QLineEdit {{
            min-height: 0;
            margin: 0;
            padding: 0 4px;
            border: 1px solid {tokens.border};
            border-radius: 3px;
        }}
        QTableWidget#zonesTable QComboBox:focus, QTableWidget#zonesTable QLineEdit:focus {{
            border: 1px solid {tokens.interactive};
        }}
        QTableView::item, QTreeView::item {{ padding: 4px 8px; border: 0; border-bottom: 1px solid {tokens.alternate_surface}; }}
        QTableView::item:selected, QTreeView::item:selected {{ background: {tokens.inactive_selection}; color: {tokens.foreground}; }}
        QGroupBox[quiet="true"] {{ border: 0; margin-top: 1.5em; padding-top: 8px; }}
        QTabBar::tab, QToolBar {{
            background: {tokens.surface};
            color: {tokens.foreground};
            padding: {padding}px;
            border: 1px solid {tokens.border};
        }}
        QTabBar::tab:selected {{
            border-bottom: 3px solid {tokens.interactive};
            font-weight: 600;
        }}
        QTabWidget::pane {{ border: 1px solid {tokens.border}; }}
        QToolButton {{ padding: {padding}px; border-radius: {radius}px; }}
        QToolButton:hover {{ background: {tokens.inactive_selection}; }}
        QMenu::item:selected {{
            background: {tokens.interactive};
            color: {tokens.on_interactive};
        }}
        QMenu::item:disabled {{ color: {tokens.muted_foreground}; }}
        QMenu {{ background: {tokens.surface}; }}
        QStatusBar {{
            background: {tokens.surface};
            border-top: 1px solid {tokens.border};
        }}
        """
    )
    for widget in app.allWidgets():
        if isinstance(widget, QTableView):
            # Les listes de cartes et le tableau périodique ont leur propre géométrie.
            if widget.objectName() in {"comparisonTable", "equationsList", "mainExperimentsTable"}:
                continue
            ancestor = widget.parentWidget()
            while ancestor is not None and ancestor.__class__.__name__ != "PeriodicTableDialog":
                ancestor = ancestor.parentWidget()
            if ancestor is None:
                widget.setShowGrid(False)
                widget.setAlternatingRowColors(True)
                widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if widget.objectName() in {"zonesTable", "zoneResultsTable"}:
                    if widget.objectName() == "zoneResultsTable":
                        QTimer.singleShot(0, widget, widget.resize_to_contents)
                    else:
                        widget.resizeRowsToContents()
                else:
                    widget.verticalHeader().setDefaultSectionSize(34)
