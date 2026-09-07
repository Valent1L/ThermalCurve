"""Segmentation et appariement temporels des programmes thermiques.

Les températures ne sont jamais triées globalement. Un tri local est permis
uniquement pour interpoler à l'intérieur d'une rampe déjà identifiée.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd


class ThermalSegmentationError(ValueError):
    """Le programme thermique ne permet pas une segmentation fiable."""


@dataclass(frozen=True, slots=True)
class ThermalSegment:
    """Intervalle contigu, indexé par positions, du programme thermique."""

    kind: str
    start: int
    stop: int

    @property
    def size(self) -> int:
        return self.stop - self.start


@dataclass(frozen=True, slots=True)
class ThermalSegmentationRules:
    """Règles effectives, ajustées à la durée et à l'échantillonnage."""

    slope_window_s: float
    smoothing_window_s: float
    ramp_enter_slope_c_s: float
    ramp_exit_slope_c_s: float
    transition_hold_s: float
    minimum_segment_duration_s: float
    minimum_ramp_amplitude_c: float


@dataclass(frozen=True, slots=True)
class ThermalSegmentPair:
    """Association chronologique de deux phases thermiques compatibles."""

    experiment: ThermalSegment
    blank: ThermalSegment
    common_temperature_c: tuple[float, float] | None = None
    common_duration_s: float | None = None


@dataclass(frozen=True, slots=True)
class ThermalMatch:
    """Résultat d'un appariement conservant l'ordre des deux acquisitions."""

    pairs: tuple[ThermalSegmentPair, ...]
    unmatched_experiment: tuple[ThermalSegment, ...]
    unmatched_blank: tuple[ThermalSegment, ...]
    minimum_common_ramp_amplitude_c: float


def _median_step(values: np.ndarray) -> float:
    steps = np.diff(values)
    positive = steps[steps > 0]
    if not positive.size:
        raise ThermalSegmentationError(
            "L'axe temps doit être strictement croissant pour segmenter la température."
        )
    return float(np.median(positive))


def _validated_series(
    time_s: np.ndarray,
    temperature: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    time = np.asarray(time_s, dtype=float)
    values = np.asarray(temperature, dtype=float)
    if time.ndim != 1 or values.ndim != 1 or time.size != values.size:
        raise ThermalSegmentationError(
            "Temps et température doivent être deux séries unidimensionnelles alignées."
        )
    if time.size < 2:
        raise ThermalSegmentationError(
            "Au moins deux lignes sont nécessaires pour segmenter la température."
        )
    if not np.isfinite(time).all() or not np.isfinite(values).all():
        raise ThermalSegmentationError(
            "Temps ou température contient des valeurs non numériques ou manquantes."
        )
    if np.any(np.diff(time) <= 0):
        raise ThermalSegmentationError(
            "L'axe temps doit être strictement croissant pour segmenter la température."
        )
    return time, values


def segmentation_rules(
    time_s: np.ndarray,
    temperature: np.ndarray,
) -> ThermalSegmentationRules:
    """Calcule les fenêtres effectives sans dépendre du nombre de lignes seul."""

    time, values = _validated_series(time_s, temperature)
    step = _median_step(time)
    duration = float(time[-1] - time[0])
    temperature_range = float(np.ptp(values))
    slope_window_s = min(30.0, max(2.0 * step, duration / 20.0))
    smoothing_window_s = min(3.0, slope_window_s / 5.0)
    return ThermalSegmentationRules(
        slope_window_s=slope_window_s,
        smoothing_window_s=smoothing_window_s,
        ramp_enter_slope_c_s=0.10,
        ramp_exit_slope_c_s=0.03,
        transition_hold_s=min(6.0, max(step, slope_window_s / 5.0)),
        minimum_segment_duration_s=min(
            20.0,
            max(2.0 * step, 0.004 * duration),
        ),
        minimum_ramp_amplitude_c=min(
            5.0,
            max(0.5, 0.01 * temperature_range),
        ),
    )


def robust_temperature_slope(
    time_s: np.ndarray,
    temperature: np.ndarray,
    rules: ThermalSegmentationRules | None = None,
) -> np.ndarray:
    """Calcule une pente robuste en °C/s sur une fenêtre temporelle centrée."""

    time, values = _validated_series(time_s, temperature)
    rules = rules or segmentation_rules(time, values)
    step = _median_step(time)
    smoothing_size = max(1, int(round(rules.smoothing_window_s / step)))
    if smoothing_size % 2 == 0:
        smoothing_size += 1
    smoothed = (
        pd.Series(values)
        .rolling(smoothing_size, center=True, min_periods=1)
        .median()
        .to_numpy(dtype=float)
    )
    half_window = max(1, int(round(rules.slope_window_s / (2.0 * step))))
    positions = np.arange(time.size)
    left = np.maximum(positions - half_window, 0)
    right = np.minimum(positions + half_window, time.size - 1)
    return (smoothed[right] - smoothed[left]) / (time[right] - time[left])


def _segments_from_labels(labels: np.ndarray) -> list[ThermalSegment]:
    starts = np.r_[0, np.flatnonzero(labels[1:] != labels[:-1]) + 1]
    stops = np.r_[starts[1:], labels.size]
    return [
        ThermalSegment(str(labels[start]), int(start), int(stop))
        for start, stop in zip(starts, stops, strict=True)
    ]


def _hysteresis_labels(
    time: np.ndarray,
    slope: np.ndarray,
    rules: ThermalSegmentationRules,
) -> np.ndarray:
    enter = rules.ramp_enter_slope_c_s
    leave = rules.ramp_exit_slope_c_s

    def initial(value: float) -> str:
        if value >= enter:
            return "rising"
        if value <= -enter:
            return "cooling"
        return "plateau"

    def requested(state: str, value: float) -> str:
        if state == "plateau":
            if value >= enter:
                return "rising"
            if value <= -enter:
                return "cooling"
            return state
        if state == "rising":
            if value <= -enter:
                return "cooling"
            if value <= leave:
                return "plateau"
            return state
        if value >= enter:
            return "rising"
        if value >= -leave:
            return "plateau"
        return state

    labels = np.empty(time.size, dtype=object)
    state = initial(float(slope[0]))
    pending_state: str | None = None
    pending_start = 0
    for index, value in enumerate(slope):
        wanted = requested(state, float(value))
        if wanted == state:
            pending_state = None
        elif wanted != pending_state:
            pending_state = wanted
            pending_start = index
        elif time[index] - time[pending_start] >= rules.transition_hold_s:
            state = wanted
            labels[pending_start : index + 1] = state
            pending_state = None
        labels[index] = state
    return labels


def _segment_duration(time: np.ndarray, segment: ThermalSegment) -> float:
    if segment.size < 2:
        return 0.0
    return float(time[segment.stop - 1] - time[segment.start])


def _segment_amplitude(
    temperature: np.ndarray,
    segment: ThermalSegment,
) -> float:
    return abs(float(temperature[segment.stop - 1] - temperature[segment.start]))


def _merge_microsegments(
    time: np.ndarray,
    temperature: np.ndarray,
    labels: np.ndarray,
    rules: ThermalSegmentationRules,
) -> np.ndarray:
    """Absorbe les états trop courts/faibles dans une phase physique voisine."""

    output = labels.copy()
    while True:
        segments = _segments_from_labels(output)
        if len(segments) <= 1:
            return output
        invalid: list[tuple[float, int]] = []
        for index, segment in enumerate(segments):
            duration = _segment_duration(time, segment)
            if segment.kind == "plateau":
                is_invalid = duration < rules.minimum_segment_duration_s
            else:
                is_invalid = (
                    duration < rules.minimum_segment_duration_s
                    or _segment_amplitude(temperature, segment)
                    < rules.minimum_ramp_amplitude_c
                )
            if is_invalid:
                invalid.append((duration, index))
        if not invalid:
            return output

        _, index = min(invalid)
        segment = segments[index]
        if (
            0 < index < len(segments) - 1
            and segments[index - 1].kind == segments[index + 1].kind
        ):
            replacement = segments[index - 1].kind
        elif index == 0:
            replacement = segments[1].kind
        elif index == len(segments) - 1:
            replacement = segments[-2].kind
        else:
            left_duration = _segment_duration(time, segments[index - 1])
            right_duration = _segment_duration(time, segments[index + 1])
            replacement = (
                segments[index - 1].kind
                if left_duration >= right_duration
                else segments[index + 1].kind
            )
        output[segment.start : segment.stop] = replacement


def segment_temperature_series(
    time_s: np.ndarray,
    temperature: np.ndarray,
) -> tuple[ThermalSegment, ...]:
    """Retourne les segments montée, palier et refroidissement dans le temps."""

    time, values = _validated_series(time_s, temperature)
    rules = segmentation_rules(time, values)
    slope = robust_temperature_slope(time, values, rules)
    labels = _hysteresis_labels(time, slope, rules)
    labels = _merge_microsegments(time, values, labels, rules)
    return tuple(_segments_from_labels(labels))


def match_thermal_segments(
    experiment_time_s: np.ndarray,
    experiment_temperature: np.ndarray,
    experiment_segments: tuple[ThermalSegment, ...],
    blank_time_s: np.ndarray,
    blank_temperature: np.ndarray,
    blank_segments: tuple[ThermalSegment, ...],
    *,
    plateau_temperature_tolerance_c: float,
) -> ThermalMatch:
    """Apparie des phases compatibles sans exiger des listes identiques."""

    exp_time, exp_temperature = _validated_series(
        experiment_time_s, experiment_temperature
    )
    blank_time, blank_temperature = _validated_series(
        blank_time_s, blank_temperature
    )
    exp_rules = segmentation_rules(exp_time, exp_temperature)
    blank_rules = segmentation_rules(blank_time, blank_temperature)
    minimum_common = min(
        exp_rules.minimum_ramp_amplitude_c,
        blank_rules.minimum_ramp_amplitude_c,
    )

    def compatibility(
        exp_segment: ThermalSegment,
        blank_segment: ThermalSegment,
    ) -> tuple[float, ThermalSegmentPair] | None:
        if exp_segment.kind != blank_segment.kind:
            return None
        if exp_segment.kind == "plateau":
            exp_target = float(
                np.median(exp_temperature[exp_segment.start : exp_segment.stop])
            )
            blank_target = float(
                np.median(blank_temperature[blank_segment.start : blank_segment.stop])
            )
            difference = abs(exp_target - blank_target)
            if difference > plateau_temperature_tolerance_c:
                return None
            common_duration = min(
                _segment_duration(exp_time, exp_segment),
                _segment_duration(blank_time, blank_segment),
            )
            if common_duration <= 0:
                return None
            return (
                plateau_temperature_tolerance_c - difference,
                ThermalSegmentPair(
                    exp_segment,
                    blank_segment,
                    common_duration_s=common_duration,
                ),
            )

        exp_values = exp_temperature[exp_segment.start : exp_segment.stop]
        blank_values = blank_temperature[blank_segment.start : blank_segment.stop]
        lower = max(float(np.min(exp_values)), float(np.min(blank_values)))
        upper = min(float(np.max(exp_values)), float(np.max(blank_values)))
        overlap = upper - lower
        if overlap < minimum_common:
            return None
        return (
            overlap,
            ThermalSegmentPair(
                exp_segment,
                blank_segment,
                common_temperature_c=(lower, upper),
            ),
        )

    @lru_cache(maxsize=None)
    def solve(
        exp_index: int,
        blank_index: int,
    ) -> tuple[int, float, tuple[ThermalSegmentPair, ...]]:
        if exp_index >= len(experiment_segments) or blank_index >= len(blank_segments):
            return 0, 0.0, ()
        options = [
            solve(exp_index + 1, blank_index),
            solve(exp_index, blank_index + 1),
        ]
        compatible = compatibility(
            experiment_segments[exp_index],
            blank_segments[blank_index],
        )
        if compatible is not None:
            quality, pair = compatible
            count, score, pairs = solve(exp_index + 1, blank_index + 1)
            options.append((count + 1, score + quality, (pair, *pairs)))
        return max(options, key=lambda item: (item[0], item[1]))

    _, _, pairs = solve(0, 0)
    matched_experiment = {pair.experiment for pair in pairs}
    matched_blank = {pair.blank for pair in pairs}
    return ThermalMatch(
        pairs=pairs,
        unmatched_experiment=tuple(
            segment
            for segment in experiment_segments
            if segment not in matched_experiment
        ),
        unmatched_blank=tuple(
            segment for segment in blank_segments if segment not in matched_blank
        ),
        minimum_common_ramp_amplitude_c=minimum_common,
    )


def local_interpolation_source(
    coordinates: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Prépare une source limitée à un segment déjà compatible."""

    frame = pd.DataFrame(
        {
            "coordinate": np.asarray(coordinates, dtype=float),
            "value": np.asarray(values, dtype=float),
        }
    ).dropna()
    if frame.empty:
        return np.empty(0, dtype=float), np.empty(0, dtype=float)
    frame = frame.groupby("coordinate", as_index=False, sort=True).mean(numeric_only=True)
    return (
        frame["coordinate"].to_numpy(dtype=float),
        frame["value"].to_numpy(dtype=float),
    )
