"""Quantification TG et dTG des zones d'analyse."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .analysis_zones import AnalysisZone, axis_unit, axis_values
from .models import CorrectionResult, unit_key
from .normalization import (
    HEAT_FLOW_REPRESENTATIONS,
    NormalizationReferences,
    _is_mg_unit,
    resolve_working_signal,
    signal_source_state,
)


@dataclass(frozen=True, slots=True)
class ZoneQuantification:
    experiment_key: str
    experiment_name: str
    zone_id: str
    zone_name: str
    axis_type: str
    start: float
    end: float
    valid_point_count: int
    status: str
    warnings: tuple[str, ...] = ()
    tg_state: str = "unavailable"
    dtg_state: str = "unavailable"
    heat_flow_state: str = "unavailable"
    delta_zone_mg: float | None = None
    delta_zone_pct_m0: float | None = None
    delta_zone_pct_reference: float | None = None
    remaining_mass_end_mg: float | None = None
    residual_mass_end_pct: float | None = None
    dtg_minimum: float | None = None
    dtg_minimum_position: float | None = None
    dtg_maximum: float | None = None
    dtg_maximum_position: float | None = None
    dtg_main_peak: float | None = None
    dtg_main_peak_position: float | None = None
    dtg_unit: str = ""
    baseline_method: str = "none"
    baseline_value: float | None = None
    baseline_representation: str | None = None
    baseline_unit: str | None = None
    heat_flow_minimum: float | None = None
    heat_flow_minimum_position: float | None = None
    heat_flow_maximum: float | None = None
    heat_flow_maximum_position: float | None = None
    heat_flow_main_peak: float | None = None
    heat_flow_main_peak_position: float | None = None
    heat_flow_unit: str = ""
    heat_flow_area: float | None = None
    heat_flow_area_unit: str = ""
    initial_mass_mg: float | None = None
    reference_mass_mg: float | None = None
    reference_name: str = ""
    heat_flow_positive_area: float | None = None
    heat_flow_negative_area: float | None = None
    axis_unit: str = ""


@dataclass(frozen=True, slots=True)
class HeatFlowZoneProfile:
    axis: np.ndarray
    time_s: np.ndarray
    signal: np.ndarray
    baseline: np.ndarray
    corrected: np.ndarray
    signal_unit: str
    area_unit: str
    signed_area: float | None
    warnings: tuple[str, ...] = ()
    ambiguous: bool = False
    positive_area: float | None = None
    negative_area: float | None = None


@dataclass(frozen=True, slots=True)
class _ReferenceValues:
    m0_mg: float | None
    tg0: float | None
    normalization_mass_mg: float | None
    normalization_mass_source: str | None
    reference_name: str


def _axis_values(result: CorrectionResult, axis_type: str) -> pd.Series:
    return axis_values(result.experiment, axis_type)


def _reference_values(
    result: CorrectionResult,
    references: NormalizationReferences | None,
) -> _ReferenceValues:
    if references is not None:
        return _ReferenceValues(
            m0_mg=float(references.mass_mg),
            tg0=references.tg_reference,
            normalization_mass_mg=references.normalization_mass_mg,
            normalization_mass_source=references.normalization_mass_source,
            reference_name=references.reference_name,
        )
    normalization = result.parameters.get("normalization", {})
    if not isinstance(normalization, dict):
        normalization = {}
    stored = normalization.get("references", {})
    if not isinstance(stored, dict):
        stored = {}
    return _ReferenceValues(
        m0_mg=_optional_float(stored.get("m0_mg")),
        tg0=_optional_float(stored.get("tg0", stored.get("tg_reference"))),
        normalization_mass_mg=_optional_float(
            stored.get(
                "normalization_mass_mg",
                stored.get("m_ref_mg"),
            )
        ),
        normalization_mass_source=_optional_text(
            stored.get("normalization_mass_source")
        ),
        reference_name=_optional_text(
            stored.get("reference_name", normalization.get("reference_name"))
        )
        or "",
    )


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _dtg_display(
    result: CorrectionResult,
    signal_stage: str = "working",
) -> tuple[str | None, str]:
    normalization = result.parameters.get("normalization", {})
    if signal_stage in {"working", "normalized"} and isinstance(
        normalization, dict
    ):
        display = normalization.get("dtg_display", {})
        if isinstance(display, dict):
            column = display.get("column")
            if isinstance(column, str) and column in result.data:
                unit = display.get("unit")
                return column, unit if isinstance(unit, str) else ""
    column = resolve_working_signal(
        result,
        "dtg",
        stage=signal_stage,
    )[0]
    return column, result.experiment.unit_for("dtg") if column else ""


def _finite_rows(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    finite = np.isfinite(frame.loc[:, list(columns)].to_numpy(dtype=float)).all(
        axis=1
    )
    return frame.loc[finite]


def _collapsed_signal(axis: pd.Series, signal: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "axis": pd.to_numeric(axis, errors="coerce"),
            "signal": pd.to_numeric(signal, errors="coerce"),
        }
    )
    frame = _finite_rows(frame, ("axis", "signal"))
    return frame.groupby("axis", as_index=False, sort=True).mean(numeric_only=True)


def _invalid_signal_at_boundary(
    axis: pd.Series,
    signal: pd.Series,
    boundary: float,
) -> bool:
    axis_values = pd.to_numeric(axis, errors="coerce").to_numpy(dtype=float)
    signal_values = pd.to_numeric(signal, errors="coerce").to_numpy(dtype=float)
    matching = np.isfinite(axis_values) & np.isclose(
        axis_values,
        boundary,
        rtol=0.0,
        atol=1e-10,
    )
    return bool(matching.any() and not np.isfinite(signal_values[matching]).any())


def _heat_flow_display(
    result: CorrectionResult,
    representation: str | None,
    signal_stage: str = "working",
) -> tuple[str | None, str, str, str]:
    normalization = result.parameters.get("normalization", {})
    if not isinstance(normalization, dict):
        normalization = {}
    mode = representation or normalization.get(
        "heat_flow_representation",
        "raw",
    )
    if not isinstance(mode, str) or mode not in HEAT_FLOW_REPRESENTATIONS:
        return None, "", "Représentation HeatFlow inconnue.", ""
    if signal_stage in {"original", "corrected"} and mode != "raw":
        return None, "", "Représentation HeatFlow incompatible avec l'étape choisie.", mode
    column, _, configured_unit = HEAT_FLOW_REPRESENTATIONS[mode]
    if mode == "raw":
        column = resolve_working_signal(
            result,
            "heat_flow",
            stage=signal_stage,
        )[0]
    unit = configured_unit or result.experiment.unit_for("heat_flow")
    return (
        column if column is not None and column in result.data else None,
        unit,
        "",
        mode,
    )


def _heat_flow_area_unit(signal_unit: str) -> str:
    compact = (
        signal_unit.strip()
        .replace(" ", "")
        .replace("·", "/")
        .replace("⋅", "/")
        .replace("mg⁻¹", "/mg")
        .replace("g⁻¹", "/g")
        .replace("mg^-1", "/mg")
        .replace("g^-1", "/g")
        .lower()
    )
    while "//" in compact:
        compact = compact.replace("//", "/")
    return {
        "mw": "mJ",
        "w": "J",
        "mw/mg": "mJ·mg⁻¹",
        "w/g": "J·g⁻¹",
        "w/mg": "J·mg⁻¹",
    }.get(compact, "")


def _empty_heat_flow_profile(
    signal_unit: str,
    warning: str,
    *,
    ambiguous: bool = False,
) -> HeatFlowZoneProfile:
    empty = np.array([], dtype=float)
    return HeatFlowZoneProfile(
        axis=empty,
        time_s=empty,
        signal=empty,
        baseline=empty,
        corrected=empty,
        signal_unit=signal_unit,
        area_unit=_heat_flow_area_unit(signal_unit),
        signed_area=None,
        warnings=(warning,),
        ambiguous=ambiguous,
    )


def _multiple_directions(axis: np.ndarray) -> bool:
    differences = np.diff(axis)
    return bool(np.any(differences > 0) and np.any(differences < 0))


def _clip_zone_path(
    frame: pd.DataFrame,
    zone: AnalysisZone,
) -> tuple[pd.DataFrame, bool]:
    """Découpe les intervalles adjacents sans traverser une lacune HeatFlow."""
    values = frame[["axis", "time_s", "signal"]].to_numpy(dtype=float)
    points: list[np.ndarray] = []
    break_pending = False
    gap_in_zone = False
    for first, last in zip(values[:-1], values[1:]):
        if not np.isfinite(first[2]) or not np.isfinite(last[2]):
            break_pending = True
            low_axis, high_axis = sorted((first[0], last[0]))
            gap_in_zone = gap_in_zone or (
                zone.start <= low_axis <= zone.end
                if np.isclose(low_axis, high_axis, rtol=0.0, atol=1e-10)
                else low_axis < zone.end and high_axis > zone.start
            )
            continue
        if last[1] <= first[1]:
            continue
        delta = last[0] - first[0]
        if delta == 0:
            if not zone.start <= first[0] <= zone.end:
                continue
            low, high = 0.0, 1.0
        else:
            low, high = sorted(((zone.start - first[0]) / delta, (zone.end - first[0]) / delta))
            low, high = max(0.0, low), min(1.0, high)
            if low >= high:
                continue
        begin = first + low * (last - first)
        finish = first + high * (last - first)
        if points and (
            break_pending
            or not np.isclose(points[-1][1], begin[1], rtol=0, atol=1e-10)
        ):
            points.append(np.full(3, np.nan))
        if not points or not np.isfinite(points[-1][1]):
            points.append(begin)
        points.append(finish)
        break_pending = False
    return (
        pd.DataFrame(points, columns=["axis", "time_s", "signal"]),
        gap_in_zone,
    )


def _split_signed_area(time_s: np.ndarray, signal: np.ndarray) -> tuple[float, float]:
    """Intègre séparément les côtés de zéro, avec intersection linéaire exacte."""
    first, last = signal[:-1], signal[1:]
    duration = np.diff(time_s)
    valid = np.isfinite(first) & np.isfinite(last) & np.isfinite(duration) & (duration > 0)
    first, last, duration = first[valid], last[valid], duration[valid]
    positive = duration * (np.maximum(first, 0) + np.maximum(last, 0)) / 2
    crossing = ((first < 0) & (last > 0)) | ((first > 0) & (last < 0))
    positive[crossing] -= (
        duration[crossing] * np.abs(first[crossing] * last[crossing])
        / (2 * (np.abs(first[crossing]) + np.abs(last[crossing])))
    )
    total = float(np.sum(duration * (first + last) / 2))
    above = float(np.sum(positive))
    return above, total - above


def heat_flow_zone_profile(
    result: CorrectionResult,
    zone: AnalysisZone,
    heat_flow_representation: str | None = None,
    *,
    heat_flow_error: str | None = None,
    signal_stage: str = "working",
) -> HeatFlowZoneProfile:
    """Construit le signal et sa ligne de base, ordonnés par Temps_s."""

    column, signal_unit, display_error, representation = _heat_flow_display(
        result,
        heat_flow_representation,
        signal_stage,
    )
    explicit_constant = (
        zone.baseline_method == "constant" and zone.baseline_value is not None
    )
    if explicit_constant and (
        zone.baseline_representation is None or zone.baseline_unit is None
    ):
        return _empty_heat_flow_profile(
            signal_unit,
            "Ligne de base constante ambiguë : son unité ou sa représentation "
            "historique est absente. Revalider la zone dans le contexte voulu.",
            ambiguous=True,
        )
    if column is None:
        detail = display_error or heat_flow_error
        warning = "Le signal HeatFlow sélectionné est absent."
        if detail:
            warning += f" {detail}"
        return _empty_heat_flow_profile(signal_unit, warning)
    if explicit_constant:
        if (
            zone.baseline_representation != representation
            or unit_key(zone.baseline_unit) != unit_key(signal_unit)
        ):
            return _empty_heat_flow_profile(
                signal_unit,
                "Ligne de base constante refusée : définie pour la représentation "
                f"{zone.baseline_representation} en {zone.baseline_unit}, incompatible "
                f"avec la représentation {representation} en {signal_unit or 'unité absente'}. "
                "Aucune conversion automatique n'est appliquée.",
            )
    try:
        axis = _axis_values(result, zone.axis_type)
    except (KeyError, ValueError) as exc:
        return _empty_heat_flow_profile(signal_unit, str(exc))
    if "Temps_s" not in result.data:
        return _empty_heat_flow_profile(
            signal_unit,
            "La colonne Temps_s requise pour l'intégration est absente.",
        )

    frame = pd.DataFrame(
        {
            "axis": pd.to_numeric(axis, errors="coerce"),
            "time_s": pd.to_numeric(
                result.data["Temps_s"],
                errors="coerce",
            ),
            "signal": pd.to_numeric(
                result.data[column],
                errors="coerce",
            ),
        }
    ).sort_values("time_s", kind="stable")
    axis_time = _finite_rows(frame, ("axis", "time_s")).reset_index(drop=True)
    if axis_time.empty:
        return _empty_heat_flow_profile(
            signal_unit,
            "Aucun point HeatFlow ne possède un axe et un temps valides.",
        )
    if zone.start < float(axis_time["axis"].min()) or zone.end > float(
        axis_time["axis"].max()
    ):
        return _empty_heat_flow_profile(
            signal_unit,
            "Le signal HeatFlow ne couvre pas toute la zone.",
        )

    profile, gap_in_zone = _clip_zone_path(axis_time, zone)
    gap_warning = (
        "Une lacune HeatFlow coupe la zone ; aucune aire n'est intégrée "
        "à travers cette rupture."
        if gap_in_zone
        else ""
    )
    finite_profile = _finite_rows(
        profile,
        ("axis", "time_s", "signal"),
    )
    if finite_profile.empty:
        warning = "Aucun point HeatFlow valide n'est compris dans la zone."
        if gap_warning:
            warning += f" {gap_warning}"
        return _empty_heat_flow_profile(
            signal_unit,
            warning,
        )
    if zone.start < float(finite_profile["axis"].min()) - 1e-10 or zone.end > float(
        finite_profile["axis"].max()
    ) + 1e-10:
        warning = "Le signal HeatFlow ne couvre pas les deux bornes de la zone."
        if gap_warning:
            warning += f" {gap_warning}"
        return _empty_heat_flow_profile(
            signal_unit,
            warning,
        )

    multiple = _multiple_directions(finite_profile["axis"].to_numpy(dtype=float))
    if multiple and (zone.baseline_method == "linear" or (
        zone.baseline_method == "constant" and zone.baseline_value is None
    )):
        return _empty_heat_flow_profile(
            signal_unit,
            "Plusieurs passages thermiques : choisir une ligne de base constante explicite ou aucune.",
            ambiguous=True,
        )
    signal_start = float(finite_profile.loc[finite_profile["axis"].idxmin(), "signal"])
    signal_end = float(finite_profile.loc[finite_profile["axis"].idxmax(), "signal"])
    if zone.baseline_method == "none":
        baseline = np.zeros(len(profile), dtype=float)
    elif zone.baseline_method == "constant":
        baseline = np.full(
            len(profile),
            signal_start if zone.baseline_value is None else zone.baseline_value,
            dtype=float,
        )
    else:
        baseline = signal_start + (
            (signal_end - signal_start)
            * (profile["axis"].to_numpy(dtype=float) - zone.start)
            / (zone.end - zone.start)
        )
    signal = profile["signal"].to_numpy(dtype=float)
    corrected = signal - baseline
    warnings: list[str] = []
    area_unit = _heat_flow_area_unit(signal_unit)
    signed_area: float | None = None
    positive_area: float | None = None
    negative_area: float | None = None
    if gap_warning:
        warnings.append(gap_warning)
    if multiple:
        warnings.append("Plusieurs passages thermiques intégrés séparément dans l'ordre temporel.")
    if len(finite_profile) < 3:
        warnings.append(
            "L'intégration HeatFlow exige au moins trois points valides, bornes comprises."
        )
    elif not area_unit:
        warnings.append(
            f"Unité HeatFlow non prise en charge pour l'intégration : {signal_unit or 'absente'}."
        )
    else:
        positive_area, negative_area = _split_signed_area(
            profile["time_s"].to_numpy(dtype=float), corrected,
        )
        signed_area = positive_area + negative_area
    return HeatFlowZoneProfile(
        axis=profile["axis"].to_numpy(dtype=float),
        time_s=profile["time_s"].to_numpy(dtype=float),
        signal=signal,
        baseline=baseline,
        corrected=corrected,
        signal_unit=signal_unit,
        area_unit=area_unit,
        signed_area=signed_area,
        positive_area=positive_area,
        negative_area=negative_area,
        warnings=tuple(warnings),
    )


def unavailable_zone_quantification(
    experiment_key: str,
    experiment_name: str,
    zone: AnalysisZone,
    warning: str,
    axis_unit_value: str = "",
) -> ZoneQuantification:
    if not axis_unit_value:
        axis_unit_value = {"time_s": "s", "time_min": "min"}.get(
            zone.axis_type, ""
        )
    return ZoneQuantification(
        experiment_key=experiment_key,
        experiment_name=experiment_name,
        zone_id=zone.identifier,
        zone_name=zone.name,
        axis_type=zone.axis_type,
        start=zone.start,
        end=zone.end,
        valid_point_count=0,
        status="Absent",
        axis_unit=axis_unit_value,
        warnings=(warning,),
        baseline_method=zone.baseline_method,
        baseline_value=zone.baseline_value,
        baseline_representation=zone.baseline_representation,
        baseline_unit=zone.baseline_unit,
    )


def quantify_zone(
    result: CorrectionResult,
    zone: AnalysisZone,
    references: NormalizationReferences | None = None,
    *,
    dtg_error: str | None = None,
    heat_flow_representation: str | None = None,
    heat_flow_error: str | None = None,
    signal_stage: str = "working",
) -> ZoneQuantification:
    """Calcule TG, dTG et HeatFlow sans extrapolation."""

    experiment_key = str(result.experiment.source_path)
    result_axis_unit = axis_unit(result.experiment, zone.axis_type)
    warnings: list[str] = []
    try:
        axis = _axis_values(result, zone.axis_type)
    except (KeyError, ValueError) as exc:
        return unavailable_zone_quantification(
            experiment_key,
            result.experiment.name,
            zone,
            str(exc),
            result_axis_unit,
        )

    finite_axis = np.isfinite(axis.to_numpy(dtype=float))
    if not finite_axis.any():
        return unavailable_zone_quantification(
            experiment_key,
            result.experiment.name,
            zone,
            "L'axe de la zone ne contient aucun point valide.",
            result_axis_unit,
        )
    axis_min = float(axis[finite_axis].min())
    axis_max = float(axis[finite_axis].max())
    if zone.start < axis_min or zone.end > axis_max:
        return unavailable_zone_quantification(
            experiment_key,
            result.experiment.name,
            zone,
            (
                "L'expérience ne couvre pas toute la zone "
                f"[{zone.start:g}, {zone.end:g}] sur cet axe."
            ),
            result_axis_unit,
        )

    inside = finite_axis & axis.between(zone.start, zone.end, inclusive="both")
    tg_column, tg_state = resolve_working_signal(
        result,
        "tg",
        stage=signal_stage,
    )
    dtg_column, dtg_unit = _dtg_display(result, signal_stage)
    dtg_state = (
        signal_source_state(result, "dtg", stage=signal_stage)
        if dtg_column is not None and dtg_error is None
        else "unavailable"
    )
    heat_flow_column, _, _, _ = _heat_flow_display(
        result,
        heat_flow_representation,
        signal_stage,
    )
    heat_flow_state = (
        signal_source_state(result, "heat_flow", stage=signal_stage)
        if heat_flow_column is not None
        else "unavailable"
    )
    tg_valid = (
        np.isfinite(pd.to_numeric(result.data[tg_column], errors="coerce"))
        if tg_column is not None
        else np.zeros(len(result.data), dtype=bool)
    )
    dtg_valid = (
        np.isfinite(pd.to_numeric(result.data[dtg_column], errors="coerce"))
        if dtg_column is not None and dtg_error is None
        else np.zeros(len(result.data), dtype=bool)
    )
    heat_flow_valid = (
        np.isfinite(
            pd.to_numeric(
                result.data[heat_flow_column],
                errors="coerce",
            )
        )
        if heat_flow_column is not None
        else np.zeros(len(result.data), dtype=bool)
    )
    valid_point_count = int(
        (inside & (tg_valid | dtg_valid | heat_flow_valid)).sum()
    )

    delta_zone_mg: float | None = None
    delta_zone_pct_m0: float | None = None
    delta_zone_pct_reference: float | None = None
    remaining_mass_end_mg: float | None = None
    residual_mass_end_pct: float | None = None
    reference_values = _reference_values(result, references)

    if tg_column is None:
        warnings.append("Le signal TG est absent.")
    elif not _is_mg_unit(result.experiment.unit_for("tg")):
        warnings.append("La quantification TG exige un signal exprimé en mg.")
    elif zone.axis_type in {"furnace_temperature", "sample_temperature"} and _multiple_directions(
        axis[finite_axis].to_numpy(dtype=float)
    ):
        warnings.append("Variation TG non univoque sur plusieurs passages thermiques : utiliser une zone temporelle.")
    elif _invalid_signal_at_boundary(
        axis,
        result.data[tg_column],
        zone.start,
    ) or _invalid_signal_at_boundary(
        axis,
        result.data[tg_column],
        zone.end,
    ):
        warnings.append("Le signal TG est non fini à une borne de la zone.")
    else:
        tg = _collapsed_signal(axis, result.data[tg_column])
        if len(tg) < 2:
            warnings.append(
                "La quantification TG exige au moins deux positions valides."
            )
        elif zone.start < float(tg["axis"].iloc[0]) or zone.end > float(
            tg["axis"].iloc[-1]
        ):
            warnings.append("Le signal TG ne couvre pas toute la zone.")
        else:
            tg_start = float(
                np.interp(zone.start, tg["axis"], tg["signal"])
            )
            tg_end = float(np.interp(zone.end, tg["axis"], tg["signal"]))
            delta_zone_mg = tg_end - tg_start
            if reference_values.m0_mg is None or reference_values.tg0 is None:
                warnings.append(
                    "m0 ou la référence TG0 est absent : résultats relatifs indisponibles."
                )
            else:
                delta_zone_pct_m0 = (
                    100.0 * delta_zone_mg / reference_values.m0_mg
                )
                remaining_mass_end_mg = (
                    reference_values.m0_mg
                    + tg_end
                    - reference_values.tg0
                )
                residual_mass_end_pct = (
                    100.0
                    * remaining_mass_end_mg
                    / reference_values.m0_mg
                )
            if (
                reference_values.normalization_mass_source == "manual"
                and reference_values.normalization_mass_mg is not None
            ):
                delta_zone_pct_reference = (
                    100.0
                    * delta_zone_mg
                    / reference_values.normalization_mass_mg
                )

    dtg_minimum: float | None = None
    dtg_minimum_position: float | None = None
    dtg_maximum: float | None = None
    dtg_maximum_position: float | None = None
    dtg_main_peak: float | None = None
    dtg_main_peak_position: float | None = None
    if dtg_error is not None:
        warnings.append(f"dTG indisponible : {dtg_error}")
    elif dtg_column is None:
        warnings.append("Le signal dTG est absent.")
    else:
        dtg = pd.DataFrame(
            {
                "axis": pd.to_numeric(axis, errors="coerce"),
                "signal": pd.to_numeric(
                    result.data[dtg_column],
                    errors="coerce",
                ),
            }
        )
        dtg = _finite_rows(dtg, ("axis", "signal"))
        dtg = dtg.loc[
            dtg["axis"].between(zone.start, zone.end, inclusive="both")
        ]
        if dtg.empty:
            warnings.append("Aucun point dTG valide n'est compris dans la zone.")
        else:
            minimum_index = dtg["signal"].idxmin()
            maximum_index = dtg["signal"].idxmax()
            peak_index = dtg["signal"].abs().idxmax()
            dtg_minimum = float(dtg.loc[minimum_index, "signal"])
            dtg_minimum_position = float(dtg.loc[minimum_index, "axis"])
            dtg_maximum = float(dtg.loc[maximum_index, "signal"])
            dtg_maximum_position = float(dtg.loc[maximum_index, "axis"])
            dtg_main_peak = float(dtg.loc[peak_index, "signal"])
            dtg_main_peak_position = float(dtg.loc[peak_index, "axis"])

    heat_flow_profile = heat_flow_zone_profile(
        result,
        zone,
        heat_flow_representation,
        heat_flow_error=heat_flow_error,
        signal_stage=signal_stage,
    )
    warnings.extend(heat_flow_profile.warnings)
    heat_flow_minimum: float | None = None
    heat_flow_minimum_position: float | None = None
    heat_flow_maximum: float | None = None
    heat_flow_maximum_position: float | None = None
    heat_flow_main_peak: float | None = None
    heat_flow_main_peak_position: float | None = None
    if heat_flow_profile.corrected.size:
        minimum_index = int(np.nanargmin(heat_flow_profile.corrected))
        maximum_index = int(np.nanargmax(heat_flow_profile.corrected))
        peak_index = int(np.nanargmax(np.abs(heat_flow_profile.corrected)))
        heat_flow_minimum = float(
            heat_flow_profile.corrected[minimum_index]
        )
        heat_flow_minimum_position = float(
            heat_flow_profile.axis[minimum_index]
        )
        heat_flow_maximum = float(
            heat_flow_profile.corrected[maximum_index]
        )
        heat_flow_maximum_position = float(
            heat_flow_profile.axis[maximum_index]
        )
        heat_flow_main_peak = float(
            heat_flow_profile.corrected[peak_index]
        )
        heat_flow_main_peak_position = float(
            heat_flow_profile.axis[peak_index]
        )

    has_result = (
        delta_zone_mg is not None
        or dtg_minimum is not None
        or heat_flow_minimum is not None
    )
    if heat_flow_profile.ambiguous:
        status = "Ambigu"
    else:
        status = (
            "OK"
            if not warnings
            else ("Avertissement" if has_result else "Absent")
        )
    return ZoneQuantification(
        experiment_key=experiment_key,
        experiment_name=result.experiment.name,
        zone_id=zone.identifier,
        zone_name=zone.name,
        axis_type=zone.axis_type,
        start=zone.start,
        end=zone.end,
        valid_point_count=valid_point_count,
        status=status,
        axis_unit=result_axis_unit,
        warnings=tuple(dict.fromkeys(warnings)),
        tg_state=tg_state,
        dtg_state=dtg_state,
        heat_flow_state=heat_flow_state,
        delta_zone_mg=delta_zone_mg,
        delta_zone_pct_m0=delta_zone_pct_m0,
        delta_zone_pct_reference=delta_zone_pct_reference,
        remaining_mass_end_mg=remaining_mass_end_mg,
        residual_mass_end_pct=residual_mass_end_pct,
        dtg_minimum=dtg_minimum,
        dtg_minimum_position=dtg_minimum_position,
        dtg_maximum=dtg_maximum,
        dtg_maximum_position=dtg_maximum_position,
        dtg_main_peak=dtg_main_peak,
        dtg_main_peak_position=dtg_main_peak_position,
        dtg_unit=dtg_unit,
        baseline_method=zone.baseline_method,
        baseline_value=zone.baseline_value,
        baseline_representation=zone.baseline_representation,
        baseline_unit=zone.baseline_unit,
        heat_flow_minimum=heat_flow_minimum,
        heat_flow_minimum_position=heat_flow_minimum_position,
        heat_flow_maximum=heat_flow_maximum,
        heat_flow_maximum_position=heat_flow_maximum_position,
        heat_flow_main_peak=heat_flow_main_peak,
        heat_flow_main_peak_position=heat_flow_main_peak_position,
        heat_flow_unit=heat_flow_profile.signal_unit,
        heat_flow_area=heat_flow_profile.signed_area,
        heat_flow_positive_area=heat_flow_profile.positive_area,
        heat_flow_negative_area=heat_flow_profile.negative_area,
        heat_flow_area_unit=heat_flow_profile.area_unit,
        initial_mass_mg=reference_values.m0_mg,
        reference_mass_mg=reference_values.normalization_mass_mg,
        reference_name=reference_values.reference_name,
    )
