"""Zones d'analyse descriptives, sans calcul scientifique."""

from __future__ import annotations

from .models import TIME_AXIS_SECONDS

from dataclasses import dataclass, replace
import math
import re
from typing import Iterable
from uuid import uuid4

import pandas as pd

from .models import ExperimentData, temperature_axis_error
from .normalization import HEAT_FLOW_REPRESENTATIONS


SUPPORTED_ZONE_AXES = {
    "time_s",
    "time_min", "time_h",
    "furnace_temperature",
    "sample_temperature",
}
BASELINE_METHODS = {"none", "constant", "linear"}


@dataclass(frozen=True, slots=True)
class AnalysisZone:
    identifier: str
    name: str
    axis_type: str
    start: float
    end: float
    baseline_method: str = "none"
    baseline_value: float | None = None
    baseline_representation: str | None = None
    baseline_unit: str | None = None
    color: str | None = None
    line_width: float | None = None
    opacity: float | None = None
    show_baseline: bool = True
    positive_area_color: str | None = None
    negative_area_color: str | None = None
    baseline_color: str | None = None

    def __post_init__(self) -> None:
        for color in (self.color, self.positive_area_color, self.negative_area_color, self.baseline_color):
            if color is not None and (not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
                raise ValueError("Couleur de zone invalide.")
        for value, lower, upper in ((self.line_width, .1, 10), (self.opacity, 0, 1)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or not lower <= value <= upper):
                raise ValueError("Épaisseur ou opacité de zone invalide.")
        if not isinstance(self.show_baseline, bool):
            raise ValueError("La visibilité de la ligne de base doit être booléenne.")
        if not self.identifier.strip():
            raise ValueError("L'identifiant de la zone est obligatoire.")
        if not self.name.strip():
            raise ValueError("Le nom de la zone est obligatoire.")
        if self.axis_type not in SUPPORTED_ZONE_AXES:
            raise ValueError(f"Axe de zone inconnu : {self.axis_type}")
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValueError("Les bornes de la zone doivent être finies.")
        if self.end <= self.start:
            raise ValueError(
                "La borne finale doit être strictement supérieure à la borne initiale."
            )
        if self.baseline_method not in BASELINE_METHODS:
            raise ValueError(
                f"Méthode de ligne de base inconnue : {self.baseline_method}"
            )
        if self.baseline_value is not None and not math.isfinite(self.baseline_value):
            raise ValueError("La valeur de ligne de base doit être finie.")
        if (self.baseline_representation is None) != (self.baseline_unit is None):
            raise ValueError(
                "L'unité et la représentation de la ligne de base doivent être renseignées ensemble."
            )
        if (
            self.baseline_representation is not None
            and self.baseline_representation not in HEAT_FLOW_REPRESENTATIONS
        ):
            raise ValueError(
                "Représentation de ligne de base HeatFlow inconnue : "
                f"{self.baseline_representation}"
            )
        if self.baseline_unit is not None and not self.baseline_unit.strip():
            raise ValueError("L'unité de la ligne de base ne peut pas être vide.")
        if (
            self.baseline_representation is not None
            and (
                self.baseline_method != "constant"
                or self.baseline_value is None
            )
        ):
            raise ValueError(
                "Le contexte HeatFlow est réservé aux lignes de base constantes explicites."
            )

    def to_dict(self) -> dict[str, str | float | bool | None]:
        return {
            "id": self.identifier,
            "name": self.name,
            "axis_type": self.axis_type,
            "start": self.start,
            "end": self.end,
            "baseline_method": self.baseline_method,
            "baseline_value": self.baseline_value,
            "baseline_representation": self.baseline_representation,
            "baseline_unit": self.baseline_unit,
            "color": self.color,
            "line_width": self.line_width,
            "opacity": self.opacity,
            "show_baseline": self.show_baseline,
            "positive_area_color": self.positive_area_color,
            "negative_area_color": self.negative_area_color,
            "baseline_color": self.baseline_color,
        }


class AnalysisZoneManager:
    def __init__(self, zones: Iterable[AnalysisZone] = ()) -> None:
        self._zones: dict[str, AnalysisZone] = {}
        self.replace(zones)

    @property
    def zones(self) -> tuple[AnalysisZone, ...]:
        return tuple(self._zones.values())

    def replace(self, zones: Iterable[AnalysisZone]) -> None:
        replacement: dict[str, AnalysisZone] = {}
        for zone in zones:
            if zone.identifier in replacement:
                raise ValueError(f"Identifiant de zone dupliqué : {zone.identifier}")
            replacement[zone.identifier] = zone
        self._zones = replacement

    def create_manual(
        self,
        name: str,
        axis_type: str,
        start: float,
        end: float,
        displayed_domain: tuple[float, float],
        baseline_method: str = "none",
        baseline_value: float | None = None,
        baseline_representation: str | None = None,
        baseline_unit: str | None = None,
    ) -> AnalysisZone:
        if axis_type in {"furnace_temperature", "sample_temperature"}:
            start, end = sorted((start, end))
        self._validate_inside_display(start, end, displayed_domain)
        zone = AnalysisZone(
            identifier=str(uuid4()),
            name=name.strip() or self.next_name(),
            axis_type=axis_type,
            start=float(start),
            end=float(end),
            baseline_method=baseline_method,
            baseline_value=baseline_value,
            baseline_representation=baseline_representation,
            baseline_unit=baseline_unit,
        )
        self._zones[zone.identifier] = zone
        return zone

    def create_from_drag(
        self,
        axis_type: str,
        first: float,
        second: float,
        displayed_domain: tuple[float, float],
        name: str = "",
        baseline_method: str = "none",
        baseline_value: float | None = None,
        baseline_representation: str | None = None,
        baseline_unit: str | None = None,
    ) -> AnalysisZone:
        domain_start, domain_end = sorted(map(float, displayed_domain))
        start = max(domain_start, min(float(first), float(second)))
        end = min(domain_end, max(float(first), float(second)))
        return self.create_manual(
            name or self.next_name(),
            axis_type,
            start,
            end,
            (domain_start, domain_end),
            baseline_method,
            baseline_value,
            baseline_representation,
            baseline_unit,
        )

    def update(
        self,
        identifier: str,
        *,
        name: str,
        start: float,
        end: float,
        displayed_domain: tuple[float, float],
        baseline_method: str | None = None,
        baseline_value: float | None = None,
        baseline_representation: str | None = None,
        baseline_unit: str | None = None,
    ) -> AnalysisZone:
        current = self.get(identifier)
        if current.axis_type in {"furnace_temperature", "sample_temperature"}:
            start, end = sorted((start, end))
        self._validate_inside_display(start, end, displayed_domain)
        preserve_value = baseline_method is None or (
            baseline_value is None
            and baseline_method == current.baseline_method
        )
        preserve_context = preserve_value and (
            baseline_representation is None and baseline_unit is None
        )
        updated = replace(
            current,
            name=name.strip(),
            axis_type=current.axis_type,
            start=float(start),
            end=float(end),
            baseline_method=(
                current.baseline_method
                if baseline_method is None
                else baseline_method
            ),
            baseline_value=(
                current.baseline_value if preserve_value else baseline_value
            ),
            baseline_representation=(
                current.baseline_representation
                if preserve_context
                else baseline_representation
            ),
            baseline_unit=(
                current.baseline_unit
                if preserve_context
                else baseline_unit
            ),
        )
        self._zones[identifier] = updated
        return updated

    def delete(self, identifier: str) -> None:
        if identifier not in self._zones:
            raise KeyError(f"Zone inconnue : {identifier}")
        del self._zones[identifier]

    def get(self, identifier: str) -> AnalysisZone:
        try:
            return self._zones[identifier]
        except KeyError as exc:
            raise KeyError(f"Zone inconnue : {identifier}") from exc

    def visible_for_axis(self, axis_type: str) -> tuple[AnalysisZone, ...]:
        return tuple(zone for zone in self._zones.values() if zone.axis_type == axis_type)

    def next_name(self) -> str:
        existing = {zone.name for zone in self._zones.values()}
        index = 1
        while f"Zone {index}" in existing:
            index += 1
        return f"Zone {index}"

    @staticmethod
    def _validate_inside_display(
        start: float,
        end: float,
        displayed_domain: tuple[float, float],
    ) -> None:
        if not all(math.isfinite(float(value)) for value in (*displayed_domain, start, end)):
            raise ValueError("Les bornes et le domaine affiché doivent être finis.")
        domain_start, domain_end = sorted(map(float, displayed_domain))
        if float(end) <= float(start):
            raise ValueError(
                "La borne finale doit être strictement supérieure à la borne initiale."
            )
        if float(start) < domain_start or float(end) > domain_end:
            raise ValueError(
                "Les bornes doivent rester dans le domaine actuellement affiché."
            )


def axis_values(experiment: ExperimentData, axis_type: str) -> pd.Series:
    if axis_type == "time_s":
        return pd.to_numeric(experiment.data["Temps_s"], errors="coerce")
    if axis_type in TIME_AXIS_SECONDS:
        return pd.to_numeric(experiment.data["Temps_s"], errors="coerce") / TIME_AXIS_SECONDS[axis_type]
    if axis_type not in SUPPORTED_ZONE_AXES:
        raise ValueError(f"Axe de zone inconnu : {axis_type}")
    column = getattr(experiment.mapping, axis_type)
    if column is None or column not in experiment.data:
        raise ValueError(
            f"L'expérience ne contient pas l'axe requis : {axis_type}"
        )
    if error := temperature_axis_error(experiment, axis_type):
        raise ValueError(error)
    return pd.to_numeric(experiment.data[column], errors="coerce")


def axis_unit(experiment: ExperimentData, axis_type: str) -> str:
    if axis_type == "time_s":
        return "s"
    if axis_type in TIME_AXIS_SECONDS:
        return axis_type.removeprefix("time_")
    return experiment.unit_for(axis_type) if axis_type in SUPPORTED_ZONE_AXES else ""


def points_in_zone(
    experiment: ExperimentData,
    zone: AnalysisZone,
) -> pd.DataFrame:
    """Retourne une copie des points inclus, bornes comprises."""

    values = axis_values(experiment, zone.axis_type)
    mask = values.notna() & values.between(zone.start, zone.end, inclusive="both")
    return experiment.data.loc[mask].copy()
