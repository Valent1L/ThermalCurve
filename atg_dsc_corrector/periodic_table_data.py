"""Table périodique de consultation, enrichie par un instantané Mendeleev."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from importlib.resources import files
from typing import Any, Iterable

from .atomic_data import AtomicElement, ELEMENTS


MENDELEEV_DATA_VERSION = "v0.20.0"
MENDELEEV_DATA_COMMIT = "310fcad9ddf3191781abe735e61f6cd19ce8a5ee"
MENDELEEV_DATA_SOURCE = "Mendeleev-data v0.20.0"


class MendeleevDataError(ValueError):
    """Les données d'enrichissement ne permettent pas une jointure sûre."""


@dataclass(frozen=True)
class MendeleevElement:
    atomic_number: int
    symbol: str
    name_en: str | None
    atomic_weight: Decimal | None
    group: int | None
    period: int | None
    block: str | None
    electronic_configuration: str | None
    is_radioactive: bool | None
    series_id: int | None


@dataclass(frozen=True)
class PeriodicTableEntry:
    element: AtomicElement
    enrichment: MendeleevElement | None

    @property
    def group(self) -> int | None:
        return self.enrichment.group if self.enrichment is not None else self.element.group

    @property
    def period(self) -> int:
        return self.enrichment.period if self.enrichment is not None and self.enrichment.period is not None else self.element.period


@dataclass(frozen=True)
class AtomicWeightDiscrepancy:
    atomic_number: int
    symbol: str
    j18_weight: Decimal
    mendeleev_weight: Decimal


@dataclass(frozen=True)
class PeriodicTableData:
    entries: tuple[PeriodicTableEntry, ...]
    enrichment_available: bool
    warning: str | None
    atomic_weight_discrepancies: tuple[AtomicWeightDiscrepancy, ...]


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MendeleevDataError(f"{field} doit être une chaîne ou null.")
    return value


def _optional_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MendeleevDataError(f"{field} doit être un entier ou null.")
    return value


def _mendeleev_element(record: Any) -> MendeleevElement:
    if not isinstance(record, dict):
        raise MendeleevDataError("Chaque élément Mendeleev doit être un objet JSON.")
    atomic_number = _optional_integer(record.get("atomic_number"), "atomic_number")
    symbol = _optional_string(record.get("symbol"), "symbol")
    if atomic_number is None or atomic_number < 1 or not symbol:
        raise MendeleevDataError("Numéro atomique ou symbole Mendeleev invalide.")
    atomic_weight = record.get("atomic_weight")
    if atomic_weight is not None and not isinstance(atomic_weight, (int, float)):
        raise MendeleevDataError("atomic_weight doit être un nombre ou null.")
    radioactive = record.get("is_radioactive")
    if radioactive not in (None, 0, 1, False, True):
        raise MendeleevDataError("is_radioactive doit être booléen, 0, 1 ou null.")
    return MendeleevElement(
        atomic_number=atomic_number,
        symbol=symbol,
        name_en=_optional_string(record.get("name"), "name"),
        atomic_weight=None if atomic_weight is None else Decimal(str(atomic_weight)),
        group=_optional_integer(record.get("group_id"), "group_id"),
        period=_optional_integer(record.get("period"), "period"),
        block=_optional_string(record.get("block"), "block"),
        electronic_configuration=_optional_string(
            record.get("electronic_configuration"), "electronic_configuration"
        ),
        is_radioactive=None if radioactive is None else bool(radioactive),
        series_id=_optional_integer(record.get("series_id"), "series_id"),
    )


def _as_python_literal(source: str) -> str:
    """Normalise seulement les littéraux JSON hors chaînes, en mémoire."""

    result: list[str] = []
    index = 0
    quote: str | None = None
    escaped = False
    replacements = {"null": "None", "true": "True", "false": "False"}
    while index < len(source):
        character = source[index]
        if quote is not None:
            result.append(character)
            if character == quote and not escaped:
                quote = None
            escaped = character == "\\" and not escaped
            index += 1
            continue
        if character in "\"'":
            quote = character
            escaped = False
            result.append(character)
            index += 1
            continue
        if character.isalpha():
            end = index + 1
            while end < len(source) and source[end].isalpha():
                end += 1
            word = source[index:end]
            result.append(replacements.get(word, word))
            index = end
            continue
        result.append(character)
        index += 1
    return "".join(result)


@lru_cache(maxsize=1)
def load_mendeleev_elements() -> tuple[MendeleevElement, ...]:
    """Charge l'instantané local sans dépendance ni accès réseau."""

    resource = files("atg_dsc_corrector").joinpath(
        "resources", "mendeleev", MENDELEEV_DATA_VERSION, "elements.json"
    )
    try:
        payload = ast.literal_eval(_as_python_literal(resource.read_text(encoding="utf-8")))
    except (OSError, SyntaxError, ValueError) as exc:
        raise MendeleevDataError("L'enrichissement Mendeleev est indisponible.") from exc
    if not isinstance(payload, list):
        raise MendeleevDataError("elements.json doit contenir une liste.")
    return tuple(_mendeleev_element(record) for record in payload)


def join_mendeleev_elements(
    mendeleev_elements: Iterable[MendeleevElement],
) -> tuple[PeriodicTableEntry, ...]:
    """Joint les données tierces à J18 par numéro et symbole exacts."""

    records = tuple(mendeleev_elements)
    by_number = {record.atomic_number: record for record in records}
    if len(records) != 118 or len(by_number) != 118 or set(by_number) != set(range(1, 119)):
        raise MendeleevDataError("Mendeleev doit contenir exactement les 118 numéros atomiques.")
    if len({record.symbol for record in records}) != 118:
        raise MendeleevDataError("Les symboles Mendeleev doivent être uniques.")
    entries = []
    for element in ELEMENTS:
        record = by_number[element.atomic_number]
        if record.symbol != element.symbol:
            raise MendeleevDataError(
                f"Symbole divergent pour Z={element.atomic_number} : "
                f"{record.symbol!r} au lieu de {element.symbol!r}."
            )
        entries.append(PeriodicTableEntry(element, record))
    return tuple(entries)


def _weight_discrepancies(
    entries: Iterable[PeriodicTableEntry],
) -> tuple[AtomicWeightDiscrepancy, ...]:
    return tuple(
        AtomicWeightDiscrepancy(
            atomic_number=entry.element.atomic_number,
            symbol=entry.element.symbol,
            j18_weight=entry.element.standard_atomic_weight,
            mendeleev_weight=entry.enrichment.atomic_weight,
        )
        for entry in entries
        if entry.enrichment is not None
        and entry.element.standard_atomic_weight is not None
        and entry.enrichment.atomic_weight is not None
        and entry.element.standard_atomic_weight != entry.enrichment.atomic_weight
    )


def load_periodic_table() -> PeriodicTableData:
    """Retourne toujours J18 et ajoute Mendeleev quand la ressource est valide."""

    try:
        entries = join_mendeleev_elements(load_mendeleev_elements())
    except MendeleevDataError:
        return PeriodicTableData(
            entries=tuple(PeriodicTableEntry(element, None) for element in ELEMENTS),
            enrichment_available=False,
            warning="Les informations complémentaires Mendeleev sont indisponibles.",
            atomic_weight_discrepancies=(),
        )
    return PeriodicTableData(
        entries=entries,
        enrichment_available=True,
        warning=None,
        atomic_weight_discrepancies=_weight_discrepancies(entries),
    )
