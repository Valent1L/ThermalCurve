"""Compact command rows that wrap instead of overflowing their panel."""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item):
        self._items.append(item)
        self.invalidate()

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < self.count() else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < self.count() else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), measure=True)

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def sizeHint(self):
        sizes = [item.sizeHint() for item in self._items if not item.isEmpty()]
        left, top, right, bottom = self.getContentsMargins()
        return QSize(sum(size.width() for size in sizes) + max(0, len(sizes) - 1) * self.spacing()
                     + left + right, max((size.height() for size in sizes), default=0) + top + bottom)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect)

    def _arrange(self, rect, *, measure=False):
        left, top, right, bottom = self.getContentsMargins()
        area = rect.adjusted(left, top, -right, -bottom)
        x, y, row_height = area.x(), area.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            size.setWidth(min(size.width(), max(item.minimumSize().width(), area.width())))
            if item.hasHeightForWidth():
                size.setHeight(item.heightForWidth(size.width()))
            if x > area.x() and x + size.width() > area.x() + area.width():
                x = area.x()
                y += row_height + self.spacing()
                row_height = 0
            if not measure:
                item.setGeometry(QRect(x, y, size.width(), size.height()))
            x += size.width() + self.spacing()
            row_height = max(row_height, size.height())
        return y + row_height - rect.y() + bottom
