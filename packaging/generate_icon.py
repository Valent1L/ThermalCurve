"""Regenerate the Windows icon from the editable SVG, with installed Qt/Pillow."""
from pathlib import Path
from io import BytesIO
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


def main():
    app = QApplication.instance() or QApplication([])
    directory = Path(__file__).resolve().parents[1] / 'atg_dsc_corrector/resources'
    renderer = QSvgRenderer(str(directory / 'thermalcurve.svg'))
    if not renderer.isValid():
        raise ValueError('Invalid ThermalCurve SVG')
    picture = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    picture.fill(0)
    painter = QPainter(picture)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    picture.save(buffer, 'PNG')
    image = Image.open(BytesIO(bytes(buffer.data())))
    image.save(directory / 'thermalcurve.ico', sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    print(directory / 'thermalcurve.ico')


if __name__ == '__main__':
    main()
