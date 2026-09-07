"""Statistiques de répétitions dérivées pour la comparaison graphique."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .comparison import ComparisonCurve, ComparisonOptions, ComparisonPlot
from .models import temperature_axis_error
from .analysis_zones import AnalysisZone


@dataclass(frozen=True, slots=True)
class GroupZoneSummary:
    start_mean: float
    end_mean: float
    minimum: float
    maximum: float
    start_std: float | None
    end_std: float | None

    @property
    def delta(self) -> float:
        return self.end_mean - self.start_mean

    @property
    def delta_bounds(self) -> tuple[float, float] | None:
        if self.start_std is None or self.end_std is None:
            return None
        width = self.start_std + self.end_std
        return self.delta - width, self.delta + width


def quantify_group_zone(statistics: GroupStatistics, zone: AnalysisZone, *, axis_type: str) -> GroupZoneSummary:
    """Lit la moyenne affichée aux bornes, sans extrapolation ni conversion d'unité.

    Les bornes de Δ sont l'enveloppe des bandes ponctuelles aux deux extrémités,
    pas un écart-type de Δ (qui nécessiterait leur covariance).
    """
    if zone.axis_type != axis_type:
        raise ValueError("La zone et la moyenne utilisent des axes différents.")
    x, mean, std = statistics.x, statistics.mean, statistics.std
    if x.size < 2 or mean.shape != x.shape or std.shape != x.shape or not np.isfinite(x).all():
        raise ValueError("Moyenne indisponible sur cette zone.")
    if np.all(np.diff(x) < 0):
        x, mean, std = x[::-1], mean[::-1], std[::-1]
    if not np.all(np.diff(x) > 0):
        raise ValueError("Plusieurs passages ou abscisses répétées : sélectionner une zone temporelle.")
    if zone.start < x[0] or zone.end > x[-1]:
        raise ValueError("La moyenne ne couvre pas toute la zone ; aucune extrapolation.")
    first = max(0, int(np.searchsorted(x, zone.start, side="right")) - 1)
    last = min(x.size - 1, int(np.searchsorted(x, zone.end, side="left")))
    if not np.isfinite(mean[first:last + 1]).all():
        raise ValueError("La moyenne comporte une lacune dans la zone.")
    start, end = np.interp([zone.start, zone.end], x, mean)
    values = np.r_[start, mean[(x > zone.start) & (x < zone.end)], end]
    start_std = end_std = None
    if np.isfinite(std[first:last + 1]).all():
        start_std, end_std = map(float, np.interp([zone.start, zone.end], x, std))
    return GroupZoneSummary(float(start), float(end), float(values.min()), float(values.max()), start_std, end_std)


@dataclass(frozen=True, slots=True)
class RepeatGroup:
    identifier: str
    name: str
    members: tuple[str, ...]


@dataclass(slots=True)
class GroupStatistics:
    group: RepeatGroup
    x: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    mean: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    std: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    count: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    unit: str = ""
    included: list[str] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)
    domain: tuple[float, float] | None = None
    signal: str = "tg"
    scientific_unit: str = ""


def _finite_xy(
    curve: ComparisonCurve,
    options: ComparisonOptions,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, str, str] | None:
    resolved = ComparisonPlot._curve_data_with_rows(curve, options)
    if resolved is None:
        return None
    x, y, rows, source_size = resolved
    if x.size < 2 or np.unique(x).size < 2:
        return None
    curve_options = curve.plot_options or options.plot_options
    unit = ComparisonPlot._unit_for_curve(curve, curve_options, options.signal)
    scientific_unit = ComparisonPlot._scientific_unit_for_curve(
        curve, curve_options, options.signal
    )
    return x, y, rows, source_size, unit, scientific_unit


def _automatic_grid(bounds: tuple[float, float], series: Iterable[tuple[np.ndarray, np.ndarray, str]]) -> np.ndarray:
    steps = []
    for x, _y, _unit in series:
        differences = np.diff(x)
        positive = differences[differences > 0.0]
        if positive.size:
            steps.append(float(np.median(positive)))
    if not steps:
        return np.array([], dtype=float)
    step = min(steps)
    start, end = bounds
    count = max(2, int(np.floor((end - start) / step)) + 1)
    if count > 1_000_000:
        count = 1_000_000
        step = (end - start) / (count - 1)
    grid = start + step * np.arange(count, dtype=float)
    if grid[-1] < end:
        grid = np.append(grid, end)
    else:
        grid[-1] = end
    return grid


def _row_mean_grid(
    series: Iterable[tuple[np.ndarray, np.ndarray, np.ndarray, int, str]],
) -> np.ndarray | None:
    """Moyenne les abscisses lorsque les lignes sources correspondent."""

    items = list(series)
    if not items:
        return None
    first_x, _first_y, first_rows, first_size, _first_unit = items[0]
    if all(
        source_size == first_size
        and x.shape == first_x.shape
        and np.array_equal(rows, first_rows)
        for x, _y, rows, source_size, _unit in items[1:]
    ):
        return np.mean(
            np.vstack([x for x, _y, _rows, _source_size, _unit in items]),
            axis=0,
        )
    return None


def _interpolation_xy(
    x: np.ndarray,
    y: np.ndarray,
    x_axis: str,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Prépare une passe monotone sans trier ni fusionner des passages."""

    differences = np.diff(x)
    if np.all(differences > 0.0):
        return x, y
    if (
        x_axis in {"furnace_temperature", "sample_temperature"}
        and np.all(differences < 0.0)
    ):
        return x[::-1], y[::-1]
    return None


def calculate_group_statistics(
    curves: Iterable[ComparisonCurve],
    group: RepeatGroup,
    options: ComparisonOptions,
    *,
    grid_method: str = "auto",
    manual_points: int | None = None,
) -> GroupStatistics:
    """Calcule des statistiques sans extrapolation ni décalage visuel."""
    if grid_method not in {"auto", "manual"}:
        raise ValueError("Méthode de grille statistique inconnue.")
    if grid_method == "manual" and (manual_points is None or manual_points < 2):
        raise ValueError("Le nombre manuel de points doit être au moins égal à 2.")
    by_identifier = {curve.identifier: curve for curve in curves}
    statistics = GroupStatistics(group=group, signal=options.signal)
    series: list[
        tuple[str, np.ndarray, np.ndarray, np.ndarray, int, str, str]
    ] = []
    expected_unit = ""
    expected_scientific_unit: str | None = None
    for identifier in group.members:
        curve = by_identifier.get(identifier)
        if curve is None:
            statistics.excluded[identifier] = "Expérience absente."
            continue
        curve_options = curve.plot_options or options.plot_options
        if curve_options.x_axis in {"furnace_temperature", "sample_temperature"}:
            if error := temperature_axis_error(
                curve.result.experiment, curve_options.x_axis
            ):
                statistics.excluded[identifier] = error
                continue
        resolved = _finite_xy(curve, options)
        if resolved is None:
            statistics.excluded[identifier] = "Signal, axe ou données finies insuffisants."
            continue
        x, y, rows, source_size, unit, scientific_unit = resolved
        if (
            curve_options.x_axis in {"time_s", "time_min"}
            and not np.all(np.diff(x) > 0.0)
        ):
            statistics.excluded[identifier] = (
                "Axe temporel non strictement croissant ou valeurs X répétées."
            )
            continue
        if not scientific_unit:
            statistics.excluded[identifier] = "Unité scientifique absente."
            continue
        if expected_scientific_unit is None:
            expected_scientific_unit = scientific_unit
            expected_unit = unit
        elif scientific_unit != expected_scientific_unit:
            statistics.excluded[identifier] = "Unité incompatible."
            continue
        series.append(
            (
                identifier,
                x,
                y,
                rows,
                source_size,
                unit,
                curve_options.x_axis,
            )
        )
    if not series:
        return statistics
    raw_series = [
        (x, y, rows, source_size, unit)
        for _identifier, x, y, rows, source_size, unit, _x_axis in series
    ]
    row_mean_grid = _row_mean_grid(raw_series) if grid_method == "auto" else None
    if row_mean_grid is not None:
        grid = row_mean_grid
        calculation_series = series
        interpolation_series = [
            (x, y, unit)
            for x, y, _rows, _source_size, unit in raw_series
        ]
    else:
        calculation_series = []
        interpolation_series = []
        for identifier, x, y, rows, source_size, unit, x_axis in series:
            prepared = _interpolation_xy(x, y, x_axis)
            if prepared is None:
                detail = (
                    "plusieurs passages thermiques"
                    if (
                        x_axis in {"furnace_temperature", "sample_temperature"}
                        and np.any(np.diff(x) > 0.0)
                        and np.any(np.diff(x) < 0.0)
                    )
                    else "axe non strictement monotone ou valeurs X répétées"
                )
                statistics.excluded[identifier] = (
                    f"Interpolation indisponible : {detail}."
                )
                continue
            prepared_x, prepared_y = prepared
            calculation_series.append(
                (identifier, x, y, rows, source_size, unit, x_axis)
            )
            interpolation_series.append((prepared_x, prepared_y, unit))
        if not interpolation_series:
            return statistics
        start = max(float(np.min(x)) for x, _y, _unit in interpolation_series)
        end = min(float(np.max(x)) for x, _y, _unit in interpolation_series)
        if start >= end:
            for (
                identifier,
                _x,
                _y,
                _rows,
                _source_size,
                _unit,
                _x_axis,
            ) in calculation_series:
                statistics.excluded[identifier] = "Aucun domaine commun de recouvrement."
            return statistics
        grid = (
            _automatic_grid((start, end), interpolation_series)
            if grid_method == "auto"
            else np.linspace(start, end, int(manual_points), dtype=float)
        )
    if grid.size < 2:
        return statistics
    values = np.full((len(calculation_series), grid.size), np.nan, dtype=float)
    for row, (
        (
            identifier,
            _raw_x,
            raw_y,
            _rows,
            _source_size,
            _unit,
            _x_axis,
        ),
        (x, y, _),
    ) in enumerate(
        zip(calculation_series, interpolation_series)
    ):
        if row_mean_grid is not None:
            values[row] = raw_y
        else:
            within = (grid >= x[0]) & (grid <= x[-1])
            values[row, within] = np.interp(grid[within], x, y)
        statistics.included.append(identifier)
    count = np.sum(np.isfinite(values), axis=0).astype(int)
    mean = np.full(grid.size, np.nan, dtype=float)
    valid_mean = count > 0
    mean[valid_mean] = np.nansum(values[:, valid_mean], axis=0) / count[valid_mean]
    std = np.full(grid.size, np.nan, dtype=float)
    valid_std = count >= 2
    std[valid_std] = np.nanstd(values[:, valid_std], axis=0, ddof=1)
    statistics.x = grid
    statistics.mean = mean
    statistics.std = std
    statistics.count = count
    statistics.unit = expected_unit
    statistics.scientific_unit = expected_scientific_unit or ""
    statistics.domain = (float(np.min(grid)), float(np.max(grid)))
    return statistics
