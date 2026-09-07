"""Correction positionnelle des signaux ATG-DSC par un blanc synchronisé."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

import numpy as np
import pandas as pd

from .models import CorrectionResult, ExperimentData, unit_key
from .i18n import tr


class CorrectionError(ValueError):
    """Erreur empêchant une correction scientifiquement définie."""


class NoOverlapError(CorrectionError):
    """Conservé pour compatibilité avec les erreurs de grille temporelle."""


@dataclass(frozen=True, slots=True)
class CorrectionSettings:
    """Paramètres de compatibilité de la grille maîtresse expérience.

    ``interpolation_axis`` est conservé pour les projets historiques mais n'a
    aucun effet sur le calcul : la correction est toujours positionnelle.
    """

    method: str = "direct"
    interpolation_axis: str = "time_s"
    time_relative_tolerance: float = 0.05
    time_absolute_tolerance_s: float = 0.01
    temperature_tolerance_c: float = 5.0

    def __post_init__(self) -> None:
        if self.method not in {"direct", "drift"}:
            raise ValueError("La méthode doit être 'direct' ou 'drift'.")
        if self.interpolation_axis not in {
            "time_s",
            "furnace_temperature",
            "sample_temperature",
        }:
            raise ValueError("Axe d'interpolation historique inconnu.")
        try:
            invalid = any(
                isinstance(value, bool) or not isinstance(value, Real)
                or not math.isfinite(value) or value < 0
                for value in (
                    self.time_relative_tolerance,
                    self.time_absolute_tolerance_s,
                    self.temperature_tolerance_c,
                )
            )
        except OverflowError:
            invalid = True
        if invalid:
            raise ValueError(tr("Les tolérances doivent être numériques, finies et positives ou nulles."))


def _finite_numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)


def _unit_key(unit: str) -> str:
    return unit_key(unit)


def _signal_units_compatible(
    signal: str,
    experiment_unit: str,
    blank_unit: str,
    *,
    allow_both_missing: bool = False,
) -> tuple[bool, str]:
    """Compare deux unités sans convertir les valeurs du signal."""

    left = _unit_key(experiment_unit)
    right = _unit_key(blank_unit)
    if not left and not right:
        return (
            allow_both_missing,
            f"Unités {signal} absentes dans les deux fichiers: compatibilité non vérifiée.",
        )
    if not left or not right:
        return False, f"Unité {signal} absente dans un seul des deux fichiers."
    if left != right:
        return False, f"Unités {signal} incompatibles: '{experiment_unit}' et '{blank_unit}'."
    return True, ""


def dtg_units_compatible(experiment_unit: str, blank_unit: str) -> tuple[bool, str]:
    """Compare les unités sans convertir les valeurs de dTG."""

    return _signal_units_compatible(
        "dTG", experiment_unit, blank_unit, allow_both_missing=True
    )


def _validate_experiment_master_grid(
    experiment: ExperimentData,
    corrected: pd.DataFrame,
) -> None:
    """Garantit la conservation exacte de la grille et des métadonnées source."""

    if not corrected.index.equals(experiment.data.index):
        raise CorrectionError(
            "Invariant interne violé : les index corrigés diffèrent de l'expérience."
        )
    columns = (
        "Temps_s",
        experiment.mapping.time,
        experiment.mapping.furnace_temperature,
        experiment.mapping.sample_temperature,
        *experiment.original_columns,
    )
    for column in dict.fromkeys(columns):
        if column is None:
            continue
        if column not in corrected or not corrected[column].equals(
            experiment.data[column]
        ):
            raise CorrectionError(
                "Invariant interne violé : la grille corrigée ne conserve pas "
                f"exactement la colonne expérimentale '{column}'."
            )


def _format_number(value: float) -> str:
    return f"{value:.6g}" if np.isfinite(value) else "indisponible"


def _time_compatibility_error(
    experiment: ExperimentData,
    blank: ExperimentData,
    exp_time: np.ndarray,
    blank_time: np.ndarray,
    *,
    maximum_difference: float,
    first_mismatch: str,
    exp_cadence: float,
    blank_cadence: float,
    reason: str,
) -> NoOverlapError:
    return NoOverlapError(
        "Correction positionnelle impossible : "
        f"expérience {len(experiment.data)} lignes, blanc {len(blank.data)} lignes ; "
        f"écart maximal entre temps = {_format_number(maximum_difference)} s ; "
        f"premier décalage détecté = {first_mismatch} ; "
        f"cadence médiane expérience = {_format_number(exp_cadence)} s, "
        f"blanc = {_format_number(blank_cadence)} s. "
        f"Motif : {reason}."
    )


def _validate_positionally_compatible_times(
    experiment: ExperimentData,
    blank: ExperimentData,
    settings: CorrectionSettings,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Vérifie que chaque ligne du blanc correspond à la même acquisition."""

    exp_time = _finite_numeric(experiment.data, "Temps_s")
    blank_time = _finite_numeric(blank.data, "Temps_s")
    common_length = min(exp_time.size, blank_time.size)
    paired_exp = exp_time[:common_length]
    paired_blank = blank_time[:common_length]
    differences = np.abs(paired_exp - paired_blank)
    max_difference = float(np.max(differences)) if differences.size else np.nan
    exp_steps = np.diff(exp_time)
    blank_steps = np.diff(blank_time)
    exp_cadence = float(np.median(exp_steps)) if exp_steps.size else np.nan
    blank_cadence = float(np.median(blank_steps)) if blank_steps.size else np.nan

    if exp_time.size != blank_time.size:
        first = f"ligne {common_length + 1} (nombre de lignes différent)"
        raise _time_compatibility_error(
            experiment, blank, exp_time, blank_time,
            maximum_difference=max_difference,
            first_mismatch=first,
            exp_cadence=exp_cadence,
            blank_cadence=blank_cadence,
            reason="grilles de longueurs différentes",
        )
    if exp_time.size < 2 or not np.isfinite(exp_time).all() or not np.isfinite(blank_time).all():
        raise _time_compatibility_error(
            experiment, blank, exp_time, blank_time,
            maximum_difference=max_difference,
            first_mismatch="ligne 1",
            exp_cadence=exp_cadence,
            blank_cadence=blank_cadence,
            reason="temps insuffisant, manquant ou non numérique",
        )

    for label, steps in (("expérience", exp_steps), ("blanc", blank_steps)):
        invalid = np.flatnonzero(steps <= 0)
        if invalid.size:
            position = int(invalid[0]) + 2
            raise _time_compatibility_error(
                experiment, blank, exp_time, blank_time,
                maximum_difference=max_difference,
                first_mismatch=f"ligne {position} ({label}, pas non positif)",
                exp_cadence=exp_cadence,
                blank_cadence=blank_cadence,
                reason="duplication, inversion ou ligne temporelle manquante détectable",
            )

    point_tolerance = settings.time_absolute_tolerance_s
    mismatches = np.flatnonzero(differences > point_tolerance)
    if mismatches.size:
        position = int(mismatches[0]) + 1
        raise _time_compatibility_error(
            experiment, blank, exp_time, blank_time,
            maximum_difference=max_difference,
            first_mismatch=(
                f"ligne {position} (expérience {_format_number(exp_time[position - 1])} s, "
                f"blanc {_format_number(blank_time[position - 1])} s)"
            ),
            exp_cadence=exp_cadence,
            blank_cadence=blank_cadence,
            reason=(
                f"écart ligne à ligne supérieur à {point_tolerance:g} s"
            ),
        )

    cadence_tolerance = max(
        point_tolerance,
        settings.time_relative_tolerance * max(exp_cadence, blank_cadence),
    )
    cadence_mismatches = np.flatnonzero(np.abs(exp_steps - blank_steps) > cadence_tolerance)
    if cadence_mismatches.size or abs(exp_cadence - blank_cadence) > cadence_tolerance:
        position = (
            int(cadence_mismatches[0]) + 2
            if cadence_mismatches.size
            else 2
        )
        raise _time_compatibility_error(
            experiment, blank, exp_time, blank_time,
            maximum_difference=max_difference,
            first_mismatch=f"ligne {position} (cadence différente)",
            exp_cadence=exp_cadence,
            blank_cadence=blank_cadence,
            reason=(
                f"écart de cadence supérieur à {cadence_tolerance:g} s"
            ),
        )
    return exp_time, blank_time, max_difference, cadence_tolerance


def correct_experiment(
    experiment: ExperimentData,
    blank: ExperimentData,
    settings: CorrectionSettings | None = None,
) -> CorrectionResult:
    """Soustrait le blanc ligne à ligne sur la grille inchangée de l'expérience."""

    settings = settings or CorrectionSettings()
    exp_time, blank_time, max_difference, cadence_tolerance = (
        _validate_positionally_compatible_times(experiment, blank, settings)
    )
    result = experiment.data.copy()
    result["Dans_zone_commune"] = np.ones(exp_time.shape, dtype=bool)
    corrected: list[str] = []
    warnings = [*experiment.warnings, *blank.warnings]
    if settings.method == "drift":
        warnings.append(
            "Méthode de dérive ignorée : la correction du blanc est strictement positionnelle."
        )

    exp_tg = experiment.mapping.tg
    blank_tg = blank.mapping.tg
    if exp_tg and blank_tg:
        compatible, message = _signal_units_compatible(
            "TG", experiment.unit_for("tg"), blank.unit_for("tg")
        )
        if compatible:
            result["TG_corrigee"] = _finite_numeric(
                experiment.data, exp_tg
            ) - _finite_numeric(blank.data, blank_tg)
            corrected.append("TG_corrigee")
        else:
            warnings.append(
                f"{message} Correction TG non calculée; aucune conversion appliquée."
            )
    elif exp_tg:
        warnings.append("TG absente du blanc: correction TG non calculée.")

    exp_heat = experiment.mapping.heat_flow
    blank_heat = blank.mapping.heat_flow
    if exp_heat and blank_heat:
        compatible, message = _signal_units_compatible(
            "HeatFlow",
            experiment.unit_for("heat_flow"),
            blank.unit_for("heat_flow"),
        )
        if compatible:
            result["HeatFlow_corrige"] = _finite_numeric(
                experiment.data, exp_heat
            ) - _finite_numeric(blank.data, blank_heat)
            corrected.append("HeatFlow_corrige")
        else:
            warnings.append(
                f"{message} Correction HeatFlow non calculée; aucune conversion appliquée."
            )
    elif exp_heat:
        warnings.append("HeatFlow absent du blanc: correction HeatFlow non calculée.")

    exp_dtg = experiment.mapping.dtg
    blank_dtg = blank.mapping.dtg
    if exp_dtg and blank_dtg:
        compatible, message = dtg_units_compatible(
            experiment.unit_for("dtg"), blank.unit_for("dtg")
        )
        if compatible:
            result["dTG_corrigee"] = _finite_numeric(
                experiment.data, exp_dtg
            ) - _finite_numeric(blank.data, blank_dtg)
            corrected.append("dTG_corrigee")
            if message:
                warnings.append(message)
        else:
            warnings.append(
                f"{message} Correction dTG non calculée; aucune conversion appliquée."
            )
    elif exp_dtg:
        warnings.append("dTG absente du blanc: correction dTG non calculée.")

    if not corrected:
        raise CorrectionError("Aucun couple de signaux compatible ne peut être corrigé.")

    _validate_experiment_master_grid(experiment, result)
    return CorrectionResult(
        experiment=experiment,
        blank=blank,
        data=result,
        method="direct",
        common_time_s=(float(exp_time[0]), float(exp_time[-1])),
        corrected_columns=tuple(corrected),
        warnings=warnings,
        parameters={
            "correction_mode": "positionnelle",
            "interpolation": "aucune",
            "interpolation_axis": settings.interpolation_axis,
            "interpolation_axis_ignored": True,
            "common_interpolation_domain": [
                float(exp_time[0]),
                float(exp_time[-1]),
            ],
            "time_absolute_tolerance_s": settings.time_absolute_tolerance_s,
            "cadence_relative_tolerance": settings.time_relative_tolerance,
            "cadence_tolerance_s": cadence_tolerance,
            "maximum_time_difference_s": max_difference,
            "duplicate_blank_policy": "aucune agrégation: ligne à ligne",
            "duplicate_experiment_policy": "grille expérience conservée",
        },
    )


def uncorrected_experiment(experiment: ExperimentData) -> CorrectionResult:
    """Expose les données source sans fabriquer de correction."""

    time = _finite_numeric(experiment.data, "Temps_s")
    finite = time[np.isfinite(time)]
    if finite.size < 2:
        raise CorrectionError("Au moins deux temps valides sont requis pour l'affichage.")
    return CorrectionResult(
        experiment=experiment,
        blank=None,
        data=experiment.data.copy(),
        method="none",
        common_time_s=(float(finite.min()), float(finite.max())),
        corrected_columns=(),
        warnings=list(experiment.warnings),
        parameters={"correction_mode": "aucune"},
    )
