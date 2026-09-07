"""Contrôles QC non destructifs de l'intégrité des données chargées."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .models import ExperimentData, temperature_axis_error


@dataclass(frozen=True, slots=True)
class QCThresholds:
    """Critères opérationnels de QC; ils ne constituent pas des seuils scientifiques."""

    step_irregularity_relative: float = 0.20
    interruption_seconds: float = 60.0
    minimum_points: int = 10
    maximum_temperature_jump_c: float = 25.0

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.step_irregularity_relative)
            or self.step_irregularity_relative < 0
            or not math.isfinite(self.interruption_seconds)
            or self.interruption_seconds <= 0
            or self.minimum_points < 2
            or not math.isfinite(self.maximum_temperature_jump_c)
            or self.maximum_temperature_jump_c <= 0
        ):
            raise ValueError("Les critères QC doivent être finis et strictement positifs.")

    def to_dict(self) -> dict[str, float | int]:
        return {
            "step_irregularity_relative": self.step_irregularity_relative,
            "interruption_seconds": self.interruption_seconds,
            "minimum_points": self.minimum_points,
            "maximum_temperature_jump_c": self.maximum_temperature_jump_c,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "QCThresholds":
        if value is None:
            return cls()
        defaults = cls()
        try:
            def number(name: str, default: float) -> float:
                candidate = value.get(name, default)
                if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
                    raise ValueError
                return float(candidate)

            minimum_points = value.get("minimum_points", defaults.minimum_points)
            if isinstance(minimum_points, bool) or not isinstance(minimum_points, int):
                raise ValueError
            return cls(
                step_irregularity_relative=number(
                    "step_irregularity_relative", defaults.step_irregularity_relative),
                interruption_seconds=number("interruption_seconds", defaults.interruption_seconds),
                minimum_points=minimum_points,
                maximum_temperature_jump_c=number(
                    "maximum_temperature_jump_c", defaults.maximum_temperature_jump_c),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Les critères QC enregistrés sont invalides.") from exc


@dataclass(frozen=True, slots=True)
class QCProblem:
    code: str
    severity: str
    message: str
    indices: tuple[int, ...] = ()
    ranges: tuple[tuple[int, int], ...] = ()

    def detail(self) -> str:
        details = [self.message]
        if self.indices:
            shown = ", ".join(map(str, self.indices[:12]))
            suffix = "..." if len(self.indices) > 12 else ""
            details.append(f"Indices : {shown}{suffix}")
        if self.ranges:
            shown = ", ".join(f"{start}-{end}" for start, end in self.ranges[:12])
            suffix = "..." if len(self.ranges) > 12 else ""
            details.append(f"Plages : {shown}{suffix}")
        return "\n".join(details)


@dataclass(frozen=True, slots=True)
class QualityControlResult:
    experiment_name: str
    point_count: int
    duration_seconds: float | None
    temperature_ranges: dict[str, tuple[float, float]]
    median_step_seconds: float | None
    invalid_values: int
    duplicate_times: int
    interruptions: int
    signals: dict[str, bool]
    problems: tuple[QCProblem, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        if any(problem.severity == "error" for problem in self.problems):
            return "Erreur"
        if self.problems:
            return "Avertissement"
        return "OK"

    @property
    def concise_problems(self) -> str:
        return "; ".join(problem.message for problem in self.problems[:3]) or "Aucun problème détecté."


def _numeric(series: pd.Series) -> np.ndarray:
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)


def _problem(
    problems: list[QCProblem], code: str, severity: str, message: str,
    indices: list[int] | np.ndarray = (), ranges: list[tuple[int, int]] = (),
) -> None:
    problems.append(QCProblem(code, severity, message, tuple(map(int, indices)), tuple(ranges)))


def assess_experiment(experiment: ExperimentData, thresholds: QCThresholds | None = None) -> QualityControlResult:
    """Évalue une expérience sans modifier, supprimer ni interpoler ses valeurs."""

    thresholds = thresholds or QCThresholds()
    data = experiment.data
    problems: list[QCProblem] = []
    point_count = len(data.index)
    invalid_values = 0
    required = ("Temps_s",)
    for column in required:
        if column not in data.columns:
            _problem(problems, "missing_required_column", "error", f"Colonne obligatoire absente : {column}.")
    mapped = {
        role: column for role, column in experiment.mapping.as_dict().items() if column is not None
    }
    for role, column in mapped.items():
        if column not in data.columns:
            _problem(problems, "missing_mapped_column", "error", f"Colonne associée absente ({role}) : {column}.")

    inspected_columns = list(dict.fromkeys(["Temps_s", *mapped.values()]))
    numeric: dict[str, np.ndarray] = {}
    for column in inspected_columns:
        if column not in data.columns:
            continue
        values = _numeric(data[column])
        numeric[column] = values
        invalid = np.flatnonzero(~np.isfinite(values))
        invalid_values += len(invalid)
        if len(invalid):
            _problem(problems, "invalid_values", "error" if column == "Temps_s" else "warning",
                     f"{len(invalid)} valeur(s) NaN, infinie(s) ou non numérique(s) dans {column}.", invalid.tolist())
        if len(data[column]) != point_count:
            _problem(problems, "inconsistent_lengths", "error", f"Longueur incohérente pour {column}.")

    signals = {
        role: bool(column and column in data.columns)
        for role, column in ((role, getattr(experiment.mapping, role)) for role in ("tg", "dtg", "heat_flow"))
    }
    for role, available in signals.items():
        if not available:
            _problem(problems, "missing_signal", "warning", f"Signal absent : {role}.")

    time = numeric.get("Temps_s", np.array([], dtype=float))
    finite_time = np.isfinite(time)
    duration: float | None = None
    median_step: float | None = None
    duplicates = 0
    interruptions = 0
    if len(time) and finite_time.any():
        valid_time = time[finite_time]
        duration = float(np.max(valid_time) - np.min(valid_time))
        if valid_time.size < 2:
            _problem(problems, "time_coverage", "error", "Couverture temporelle insuffisante (moins de deux temps valides).")
        duplicate_mask = pd.Series(valid_time).duplicated(keep="first").to_numpy()
        duplicates = int(duplicate_mask.sum())
        if duplicates:
            _problem(problems, "duplicate_times", "warning", f"{duplicates} temps dupliqué(s).",
                     np.flatnonzero(finite_time)[duplicate_mask].tolist())
        adjacent = finite_time[:-1] & finite_time[1:]
        deltas = np.diff(time)
        positions = np.flatnonzero(adjacent) + 1
        non_positive = positions[deltas[adjacent] <= 0]
        if len(non_positive):
            _problem(problems, "non_monotonic_time", "error", "Axe temps non strictement croissant.", non_positive.tolist())
        positive = deltas[adjacent & (deltas > 0)]
        positive_positions = positions[deltas[adjacent] > 0]
        if positive.size:
            median_step = float(np.median(positive))
            irregular = np.abs(positive - median_step) > thresholds.step_irregularity_relative * median_step
            if irregular.any():
                _problem(problems, "irregular_step", "warning",
                         f"{int(irregular.sum())} pas fortement irrégulier(s) selon le critère QC.",
                         positive_positions[irregular].tolist())
            gaps = positive > thresholds.interruption_seconds
            interruptions = int(gaps.sum())
            if interruptions:
                _problem(problems, "interruption", "warning",
                         f"{interruptions} interruption(s) dépassant le critère QC.",
                         positive_positions[gaps].tolist())
        elif valid_time.size >= 2:
            _problem(problems, "time_step", "error", "Aucun pas de temps strictement positif exploitable.")
    elif "Temps_s" in data.columns:
        _problem(problems, "time_coverage", "error", "Aucun temps numérique fini exploitable.")

    if point_count < thresholds.minimum_points:
        _problem(problems, "minimum_points", "warning",
                 f"{point_count} point(s), inférieur au critère QC de {thresholds.minimum_points}.")

    temperature_ranges: dict[str, tuple[float, float]] = {}
    for role in ("furnace_temperature", "sample_temperature"):
        column = getattr(experiment.mapping, role)
        if not column or column not in numeric:
            continue
        if error := temperature_axis_error(experiment, role):
            _problem(
                problems,
                "unsupported_temperature_unit",
                "warning",
                error,
            )
            continue
        values = numeric[column]
        finite = np.isfinite(values)
        if not finite.any():
            continue
        temperature_ranges[role] = (float(np.min(values[finite])), float(np.max(values[finite])))
        below_absolute_zero = np.flatnonzero(values < -273.15)
        if len(below_absolute_zero):
            _problem(problems, "nonphysical_temperature", "error",
                     f"Température sous -273,15 °C dans {column}.", below_absolute_zero.tolist())
        adjacent = finite[:-1] & finite[1:]
        jumps = np.abs(np.diff(values))
        positions = np.flatnonzero(adjacent) + 1
        abrupt = positions[jumps[adjacent] > thresholds.maximum_temperature_jump_c]
        if len(abrupt):
            _problem(problems, "temperature_jump", "warning",
                     f"{len(abrupt)} saut(s) de température dépassant le critère QC dans {column}.", abrupt.tolist())
    if not temperature_ranges:
        _problem(problems, "temperature_coverage", "warning", "Aucune température exploitable pour la couverture thermique.")
    elif all(low == high for low, high in temperature_ranges.values()):
        _problem(problems, "temperature_coverage", "warning", "Couverture thermique nulle.")

    return QualityControlResult(
        experiment.name, point_count, duration, temperature_ranges, median_step,
        invalid_values, duplicates, interruptions, signals, tuple(problems),
    )
