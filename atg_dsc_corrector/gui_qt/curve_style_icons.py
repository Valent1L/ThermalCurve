"""Palette-aware previews of the same Matplotlib paths used in the graph."""
from matplotlib.markers import MarkerStyle
from matplotlib.path import Path
from matplotlib.lines import Line2D
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPalette, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

from atg_dsc_corrector.curve_styles import mpl_line_style
from .theme import LineIcon


class CurveStyleIcon(LineIcon):
    def __init__(self, kind, value):
        super().__init__(kind)
        self.value = value
        self.path = None
        if kind == 'marker' and value:
            marker = MarkerStyle(value)
            self.path = marker.get_path().transformed(marker.get_transform())
            self.filled = marker.is_filled()
        # Matplotlib expands the standard dash names using its active defaults.
        self.dashes = Line2D([], [], linestyle=mpl_line_style(value))._unscaled_dash_pattern if kind == 'line' else None

    def clone(self):
        return CurveStyleIcon(self.name, self.value)

    def paint(self, painter, rect, mode, state):
        palette = QApplication.palette()
        group = QPalette.ColorGroup.Disabled if mode == QIcon.Mode.Disabled else QPalette.ColorGroup.Active
        role = QPalette.ColorRole.HighlightedText if mode == QIcon.Mode.Selected else QPalette.ColorRole.ButtonText
        color = palette.color(group, role)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.translate(rect.center())
        if self.value in ('', 'none'):
            painter.drawEllipse(QRectF(-5, -5, 10, 10))
            painter.drawLine(-4, 4, 4, -4)
        elif self.name == 'line':
            pen = QPen(color, 1.4)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            offset, pattern = self.dashes
            if pattern:
                pen.setDashPattern(list(pattern))
                pen.setDashOffset(offset)
            painter.setPen(pen)
            painter.drawLine(-rect.width() // 2 + 2, 0, rect.width() // 2 - 2, 0)
        else:
            path = QPainterPath()
            size = 2 if self.value == ',' else 13
            for vertices, code in self.path.iter_segments(curves=False):
                if code == Path.MOVETO:
                    path.moveTo(float(vertices[0]) * size, -float(vertices[1]) * size)
                elif code == Path.LINETO:
                    path.lineTo(float(vertices[0]) * size, -float(vertices[1]) * size)
                elif code == Path.CLOSEPOLY:
                    path.closeSubpath()
            if self.filled:
                painter.setBrush(color)
            painter.drawPath(path)
        painter.restore()


def curve_style_icon(kind, value):
    return QIcon(CurveStyleIcon(kind, value))
