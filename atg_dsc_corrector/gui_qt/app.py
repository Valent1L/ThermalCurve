"""Point d'entrée de l'application Qt Widgets."""

from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Sequence

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from atg_dsc_corrector import APP_NAME, __version__
from atg_dsc_corrector.i18n import language, set_language
from .settings import application_settings
from .theme import apply_application_theme
from .number_format import number_locale


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(arguments)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / 'resources/thermalcurve.ico')))
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ATG-DSC")
    settings = application_settings()
    settings.sync()
    set_language(str(settings.value("interface/language", "fr")))
    QLocale.setDefault(number_locale())
    translator = QTranslator(app)
    if language() == "fr" and translator.load(
        "qtbase_fr", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    ):
        app.installTranslator(translator)
    from .main_window import MainWindow

    apply_application_theme(app)
    window = MainWindow(settings=settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
