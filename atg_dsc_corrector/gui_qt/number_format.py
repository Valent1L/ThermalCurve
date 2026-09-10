"""Qt number conventions follow the application language, not Windows settings."""
from PySide6.QtCore import QLocale
from atg_dsc_corrector.i18n import language, canonical_number


def number_locale() -> QLocale:
    locale = QLocale("fr_FR" if language() == "fr" else "en_US")
    locale.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator | QLocale.NumberOption.RejectGroupSeparator)
    return locale


def parse_number(text: str, locale: QLocale | None = None) -> tuple[float, bool]:
    value, valid = (locale or number_locale()).toDouble(text.strip())
    return (value, valid) if valid else QLocale.c().toDouble(canonical_number(text))
