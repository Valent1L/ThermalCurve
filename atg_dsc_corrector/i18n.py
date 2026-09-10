"""Application text only: never translate source columns or project identifiers."""

import re
from decimal import Decimal
from string import Formatter

from .translations_en import EN

_language = "fr"


def set_language(language: str) -> None:
    global _language
    _language = language if language in {"fr", "en"} else "fr"


def language() -> str:
    return _language


def canonical_number(value: object) -> str:
    """Normalize a numeric input only; chemical formula dots are not decimals."""
    text = str(value).strip()
    if re.fullmatch(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?", text):
        return text.replace(",", ".")
    return text


def decimal_text(value: object) -> str:
    text = canonical_number(value)
    return text.replace(".", ",") if language() == "fr" and re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text
    ) else text


class _NumberFormatter(Formatter):
    def format_field(self, value, format_spec):
        text = super().format_field(value, format_spec)
        return decimal_text(text) if isinstance(value, (int, float, Decimal)) else text


def tr(source: str, **values: object) -> str:
    text = EN.get(source, source) if _language == "en" else source
    return _NumberFormatter().vformat(text, (), values) if values else text
