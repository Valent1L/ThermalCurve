"""Application text only: never translate source columns or project identifiers."""

from .translations_en import EN

_language = "fr"


def set_language(language: str) -> None:
    global _language
    _language = language if language in {"fr", "en"} else "fr"


def language() -> str:
    return _language


def tr(source: str, **values: object) -> str:
    text = EN.get(source, source) if _language == "en" else source
    return text.format(**values) if values else text
