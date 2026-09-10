"""Modèle de données central, indépendant de l'interface graphique."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
from typing import Any
import unicodedata

import pandas as pd


TIME_UNIT_SECONDS = {"s": 1, "min": 60, "h": 3600}
TIME_AXIS_SECONDS = {"time_" + unit: factor for unit, factor in TIME_UNIT_SECONDS.items()}


CANONICAL_FIELDS = (
    "time",
    "furnace_temperature",
    "sample_temperature",
    "tg",
    "dtg",
    "heat_flow",
)


def same_path(first: str | Path, second: str | Path) -> bool:
    """Compare les chemins et liens physiques / Compare paths and hard links."""
    first_path = Path(first)
    second_path = Path(second)
    if os.path.normcase(str(first_path.resolve())) == os.path.normcase(
        str(second_path.resolve())
    ):
        return True
    try:
        return first_path.exists() and second_path.exists() and os.path.samefile(
            first_path, second_path
        )
    except OSError:
        return False


@dataclass(frozen=True, slots=True)
class SourceFingerprint:
    """Empreinte des octets dont une expérience a été chargée."""

    size: int
    modified_at: str
    sha256: str


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_source_fingerprint(path: str | Path) -> SourceFingerprint:
    source = Path(path)
    stat = source.stat()
    return SourceFingerprint(
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        sha256=sha256_file(source),
    )


def unit_key(unit: str) -> str:
    """Normalise une unité pour une comparaison stricte, sans conversion."""

    text = unicodedata.normalize("NFKD", unit or "")
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    text = text.replace("−", "-").replace("·", "").replace("^", "")
    text = re.sub(r"\s+", "", text).strip("[]()")
    text = re.sub(r"(secondes?|seconds?|secs?)-?1", "/s", text)
    text = re.sub(r"s-1", "/s", text)
    text = re.sub(r"(minutes?|mins?)-?1", "/min", text)
    text = re.sub(r"min-1", "/min", text)
    text = re.sub(r"(?:hours?|heures?|hrs?|h)-1", "/h", text)
    return text.replace("//", "/")


def is_celsius_unit(unit: str) -> bool:
    return unit_key(unit) in {
        "c", "°c", "degc", "degrec", "degrecelsius", "celsius"
    }


@dataclass(slots=True)
class ColumnMapping:
    """Association entre les rôles canoniques et les colonnes source."""

    time: str | None = None
    furnace_temperature: str | None = None
    sample_temperature: str | None = None
    tg: str | None = None
    dtg: str | None = None
    heat_flow: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {name: getattr(self, name) for name in CANONICAL_FIELDS}

    def signal_columns(self) -> dict[str, str]:
        return {
            name: value
            for name in ("tg", "dtg", "heat_flow")
            if (value := getattr(self, name)) is not None
        }


@dataclass(slots=True)
class FileInspection:
    """Résumé volontairement borné pour inspecter un fichier sans l'exposer."""

    path: Path
    sheet_names: list[str]
    selected_sheet: str | None
    first_rows: list[list[Any]]
    detected_columns: dict[str, str | None]
    shape: tuple[int, int]
    units: dict[str, str]
    last_rows: list[list[Any]]


@dataclass(slots=True)
class FileProbe:
    """Structure minimale nécessaire au choix de feuille et à l'association."""

    path: Path
    sheet_names: list[str]
    selected_sheet: str | None
    columns: list[str]
    units: dict[str, str]
    detected_columns: dict[str, str | None]


@dataclass(slots=True)
class ExperimentData:
    """Une expérience chargée, avec provenance et données originales conservées."""

    source_path: Path
    file_format: str
    data: pd.DataFrame
    original_columns: tuple[str, ...]
    mapping: ColumnMapping
    units: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_metadata_rows: list[list[Any]] = field(default_factory=list)
    description: str = ""
    sheet_name: str | None = None
    available_sheets: tuple[str, ...] = ()
    warnings: list[str] = field(default_factory=list)
    time_unit: str = "s"
    source_fingerprint: SourceFingerprint | None = None

    def __post_init__(self) -> None:
        missing = [name for name in self.original_columns if name not in self.data.columns]
        if missing:
            raise ValueError(f"Colonnes originales absentes des données: {missing}")
        if "Temps_s" not in self.data.columns:
            raise ValueError("La colonne interne Temps_s est obligatoire.")

    @property
    def name(self) -> str:
        return self.source_path.name

    def original_data(self) -> pd.DataFrame:
        """Retourne une copie des seules colonnes présentes dans le fichier source."""

        return self.data.loc[:, list(self.original_columns)].copy()

    def unit_for(self, canonical_name: str) -> str:
        column = getattr(self.mapping, canonical_name, None)
        return self.units.get(column, "") if column else ""


def temperature_axis_error(
    experiment: ExperimentData,
    canonical_name: str,
) -> str:
    """Explique pourquoi un axe thermique ne peut pas être traité en Celsius."""

    column = getattr(experiment.mapping, canonical_name, None)
    if not column:
        return ""
    unit = experiment.unit_for(canonical_name)
    if is_celsius_unit(unit):
        return ""
    if not unit.strip():
        return f"Unité de température absente pour '{column}'; axe Celsius indisponible."
    return (
        f"Unité de température '{unit}' non prise en charge pour '{column}'; "
        "axe Celsius indisponible."
    )


@dataclass(slots=True)
class CorrectionResult:
    """Résultat traçable de la correction d'une expérience par un blanc."""

    experiment: ExperimentData
    blank: ExperimentData | None
    data: pd.DataFrame
    method: str
    common_time_s: tuple[float, float]
    corrected_columns: tuple[str, ...]
    warnings: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = [
            name for name in self.experiment.original_columns if name not in self.data.columns
        ]
        if missing:
            raise ValueError(f"Colonnes originales perdues pendant la correction: {missing}")
