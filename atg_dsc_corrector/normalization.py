"""Normalisation et remise à zéro sans modification des données sources."""

from __future__ import annotations

from .models import TIME_AXIS_SECONDS, TIME_UNIT_SECONDS

from dataclasses import dataclass
import math
import re
import unicodedata
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .labels import format_unit, tg_normalized_labels
from .models import CorrectionResult, ExperimentData, temperature_axis_error


REFERENCE_MODES = {"first_valid", "range_mean"}
REFERENCE_AXES = {"time_s", "time_min", "time_h", "furnace_temperature", "sample_temperature"}
TG_REPRESENTATIONS = {
    "raw": ("TG_corrigee", "TG originale", None),
    "delta_m_mg": ("Delta_m_mg", "Variation de masse", "mg"),
    "delta_m_pct": ("Delta_m_pct", "Variation relative de masse", "%"),
    "remaining_mass_mg": ("Masse_restante_mg", "Masse restante", "mg"),
    "residual_mass_pct": ("Masse_residuelle_pct", "Masse résiduelle", "%"),
    "normalized_mg_mg": (
        "Delta_m_mg_mg_ref",
        "Variation normalisée",
        "mg/mg",
    ),
    "normalized_pct": (
        "Delta_m_pct_ref",
        "Variation normalisée",
        "%",
    ),
}
HEAT_FLOW_REPRESENTATIONS = {
    "raw": ("HeatFlow_corrige", "Flux de chaleur original", None),
    "zero_mw": ("HeatFlow_zero_mW", "Flux de chaleur relatif à la référence", "mW"),
    "w": ("HeatFlow_W", "Flux de chaleur", "W"),
    "zero_w": ("HeatFlow_zero_W", "Flux de chaleur relatif à la référence", "W"),
    "mw_mg": ("HeatFlow_mW_mg", "Flux de chaleur", "mW/mg"),
    "zero_mw_mg": (
        "HeatFlow_zero_mW_mg",
        "Flux de chaleur relatif à la référence",
        "mW/mg",
    ),
    "w_g": ("HeatFlow_W_g", "Flux de chaleur massique", "W/g"),
    "zero_w_g": ("HeatFlow_zero_W_g", "Flux de chaleur massique relatif à la référence", "W/g"),
    "w_mg": ("HeatFlow_W_mg", "Flux de chaleur", "W/mg"),
    "zero_w_mg": (
        "HeatFlow_zero_W_mg",
        "Flux de chaleur relatif à la référence",
        "W/mg",
    ),
}
DERIVED_COLUMNS = {
    "Delta_m_mg",
    "Delta_m_pct",
    "Masse_restante_mg",
    "Masse_residuelle_pct",
    "Delta_m_mg_mg_ref",
    "Delta_m_pct_ref",
    "dTG_mg_s",
    "dTG_mg_min",
    "dTG_pct_s",
    "dTG_pct_min",
    "dTG_mg_s_mg_ref",
    "dTG_mg_min_mg_ref",
    "dTG_pct_s_ref",
    "dTG_pct_min_ref",
    "HeatFlow_zero_mW",
    "HeatFlow_W",
    "HeatFlow_zero_W",
    "HeatFlow_mW_mg",
    "HeatFlow_zero_mW_mg",
    "HeatFlow_W_g",
    "HeatFlow_zero_W_g",
    "HeatFlow_W_mg",
    "HeatFlow_zero_W_mg",
}


class NormalizationError(ValueError):
    """Paramètre ou référence de normalisation inexploitable."""


def validate_dtg_smoothing_points(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value % 2 == 0:
        raise NormalizationError("La fenêtre de lissage dTG doit être un nombre impair de points, au moins 1.")
    return value


@dataclass(frozen=True, slots=True)
class NormalizationSettings:
    reference_mode: str = "first_valid"
    reference_axis: str = "time_s"
    range_start: float | None = None
    range_end: float | None = None
    tg_representation: str = "delta_m_mg"
    dtg_unit_mode: str = "source"
    dtg_representation: str = "raw"
    heat_flow_representation: str = "raw"
    normalization_enabled: bool = False
    reference_mass_mg: float | None = None
    reference_name: str = ""
    use_initial_mass_as_reference: bool = False
    calculate_dtg_if_missing: bool = False
    dtg_smoothing_points: int = 1
    allow_missing_initial_mass: bool = False

    def __post_init__(self) -> None:
        validate_dtg_smoothing_points(self.dtg_smoothing_points)
        if self.reference_mode not in REFERENCE_MODES:
            raise NormalizationError("Mode de référence inconnu.")
        if self.reference_axis not in REFERENCE_AXES:
            raise NormalizationError("Axe de référence inconnu.")
        if self.tg_representation not in TG_REPRESENTATIONS:
            raise NormalizationError("Représentation TG inconnue.")
        if self.heat_flow_representation not in HEAT_FLOW_REPRESENTATIONS:
            raise NormalizationError("Représentation Flux de chaleur inconnue.")
        if self.dtg_unit_mode not in {"source", "per_second", "per_minute", "per_hour"}:
            raise NormalizationError("Unité dTG demandée inconnue.")
        if self.dtg_representation not in {"raw", "per_mass", "percent"}:
            raise NormalizationError("Représentation dTG inconnue.")
        if not isinstance(self.normalization_enabled, bool):
            raise NormalizationError("L'activation de la normalisation doit être booléenne.")
        if not isinstance(self.calculate_dtg_if_missing, bool):
            raise NormalizationError("Le calcul optionnel de dTG doit être booléen.")
        if not isinstance(self.allow_missing_initial_mass, bool):
            raise NormalizationError(
                "La tolérance de masse initiale absente doit être booléenne."
            )
        if not isinstance(self.reference_name, str):
            raise NormalizationError("Le nom de la référence doit être du texte.")
        if self.reference_mass_mg is not None:
            if (
                isinstance(self.reference_mass_mg, bool)
                or not isinstance(self.reference_mass_mg, (int, float, np.number))
                or not math.isfinite(float(self.reference_mass_mg))
                or float(self.reference_mass_mg) <= 0
            ):
                raise NormalizationError(
                    "La masse de référence doit être numérique et strictement positive."
                )
        if self.reference_mode == "range_mean":
            if self.range_start is None or self.range_end is None:
                raise NormalizationError(
                    "Renseignez le début et la fin de la plage de référence."
                )
            if not math.isfinite(self.range_start) or not math.isfinite(self.range_end):
                raise NormalizationError("Les bornes de la plage doivent être finies.")
            if self.range_start >= self.range_end:
                raise NormalizationError(
                    "Le début de la plage doit être inférieur à sa fin."
                )


@dataclass(frozen=True, slots=True)
class NormalizationReferences:
    mass_mg: float | None
    mass_source: str
    tg_reference: float | None
    heat_flow_reference_mw: float | None
    normalization_mass_mg: float | None = None
    normalization_mass_source: str | None = None
    reference_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "m0_mg": self.mass_mg,
            "m_ref_mg": self.normalization_mass_mg,
            "mass_source": self.mass_source,
            "tg0": self.tg_reference,
            "tg_reference": self.tg_reference,
            "heat_flow_reference_mw": self.heat_flow_reference_mw,
            "normalization_mass_mg": self.normalization_mass_mg,
            "normalization_mass_source": self.normalization_mass_source,
            "reference_name": self.reference_name,
        }


def _normalised_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return (
        "".join(char for char in text if not unicodedata.combining(char))
        .lower()
        .replace("_", " ")
    )


def _is_mg_unit(value: Any) -> bool:
    text = _normalised_text(value).replace(" ", "")
    return bool(re.search(r"(^|[^a-z])mg($|[^a-z])", text))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, np.number)):
        number = float(value)
        return number if math.isfinite(number) else None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", str(value))
    if not match:
        return None
    number = float(match.group(0).replace(",", "."))
    return number if math.isfinite(number) else None


def _metadata_candidates(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            key_path = f"{path}.{key}" if path else str(key)
            yield key_path, item
            yield from _metadata_candidates(item, key_path)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _metadata_candidates(item, f"{path}[{index}]")


def extract_initial_mass_mg(experiment: ExperimentData) -> float | None:
    """Extrait prudemment une masse initiale explicitement exprimée en mg."""

    names = ("masse initiale", "initial mass")
    for key, value in _metadata_candidates(experiment.metadata):
        key_text = _normalised_text(key)
        if any(name in key_text for name in names):
            if not (_is_mg_unit(key) or _is_mg_unit(value)):
                continue
            number = _number(value)
            if number is None:
                raise NormalizationError(
                    "La masse initiale des métadonnées n'est pas numérique."
                )
            if number <= 0:
                raise NormalizationError(
                    "La masse initiale des métadonnées doit être strictement positive."
                )
            return number

    for row in experiment.raw_metadata_rows:
        text = " ".join(str(cell) for cell in row if cell is not None)
        normalised = _normalised_text(text)
        if not any(name in normalised for name in names) or not _is_mg_unit(text):
            continue
        phrase = re.search(
            r"(?:masse\s+initiale|initial\s+mass).*?"
            r"([-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)\s*mg\b",
            normalised,
        )
        number = _number(phrase.group(1)) if phrase else None
        if number is None:
            numeric_cells = [_number(cell) for cell in row]
            number = next((item for item in numeric_cells if item is not None), None)
        if number is None:
            raise NormalizationError(
                "La masse initiale des métadonnées n'est pas numérique."
            )
        if number <= 0:
            raise NormalizationError(
                "La masse initiale des métadonnées doit être strictement positive."
            )
        return number
    return None


def _axis_values(result: CorrectionResult, axis: str) -> np.ndarray:
    if axis in {"furnace_temperature", "sample_temperature"}:
        if error := temperature_axis_error(result.experiment, axis):
            raise NormalizationError(error)
    if axis in TIME_AXIS_SECONDS:
        return pd.to_numeric(result.data["Temps_s"], errors="coerce").to_numpy(dtype=float) / TIME_AXIS_SECONDS[axis]
    else:
        column = getattr(result.experiment.mapping, axis)
    if column is None or column not in result.data:
        raise NormalizationError(
            "L'axe choisi pour la plage n'est pas disponible dans cette expérience."
        )
    return pd.to_numeric(result.data[column], errors="coerce").to_numpy(dtype=float)


def resolve_working_signal(
    result: CorrectionResult,
    signal: str,
    *,
    stage: str = "working",
) -> tuple[str | None, str]:
    """Retourne la colonne réellement utilisable et son origine scientifique."""

    if stage not in {"working", "original", "corrected", "normalized"}:
        raise ValueError("État de signal inconnu.")
    corrected = {
        "tg": "TG_corrigee",
        "dtg": "dTG_corrigee",
        "heat_flow": "HeatFlow_corrige",
    }[signal]
    source = getattr(result.experiment.mapping, signal)
    source = source if source is not None and source in result.data else None
    corrected_available = (
        corrected in result.data and corrected in result.corrected_columns
    )
    if stage == "original":
        return source, "original" if source is not None else "unavailable"
    if stage == "corrected":
        return (
            (corrected, "corrected")
            if corrected_available
            else (None, "unavailable")
        )
    if corrected_available:
        return corrected, "corrected"
    return source, "original" if source is not None else "unavailable"


def signal_source_state(
    result: CorrectionResult,
    signal: str,
    *,
    stage: str = "working",
) -> str:
    """Qualifie l'origine effective, y compris une dTG calculée."""

    _column, state = resolve_working_signal(result, signal, stage=stage)
    if state != "unavailable" or signal != "dtg" or stage in {
        "original",
        "corrected",
    }:
        return state
    normalization = result.parameters.get("normalization", {})
    if not isinstance(normalization, dict):
        return state
    display = normalization.get("dtg_display", {})
    if not isinstance(display, dict) or display.get("column") not in result.data:
        return state
    return "calculated" if normalization.get("dtg_calculated") else "derived"


def _working_column(result: CorrectionResult, signal: str) -> str | None:
    return resolve_working_signal(result, signal)[0]


def _dtg_unit_parts(unit: str) -> tuple[str, str] | None:
    text = _normalised_text(unit)
    compact = re.sub(r"[\s·*]", "", text).replace("−", "-")
    numerator = "mg" if "mg" in compact else "%" if "%" in compact else None
    if numerator is None:
        return None
    if re.search(r"(?:/|per)(?:min|minute)|min(?:-1|\^-?1)", compact):
        return numerator, "min"
    if re.search(r"(?:/|per)(?:s|sec|seconde)|s(?:-1|\^-?1)", compact):
        return numerator, "s"
    if re.search(r"(?:/|per)(?:h|hr|hour|heure)|h(?:-1|\^-?1)", compact):
        return numerator, "h"
    return None


def _convert_dtg_time_basis(
    values: pd.Series,
    source_period: str,
    target_period: str,
) -> pd.Series:
    if source_period == target_period:
        return values.copy()
    source_seconds, target_seconds = TIME_UNIT_SECONDS[source_period], TIME_UNIT_SECONDS[target_period]
    if source_seconds > target_seconds:
        return values / (source_seconds / target_seconds)
    return values * (target_seconds / source_seconds)


def _initial_mass_required(settings: NormalizationSettings) -> bool:
    return bool(
        settings.use_initial_mass_as_reference
        or settings.tg_representation
        in {"delta_m_pct", "remaining_mass_mg", "residual_mass_pct"}
    )


def calculate_dtg_mg_per_minute(result: CorrectionResult, *, smoothing_points: int = 1) -> pd.Series:
    """Calcule une dTG sur ``Temps_s`` sans modifier le résultat fourni."""

    validate_dtg_smoothing_points(smoothing_points)
    tg_column = _working_column(result, "tg")
    if tg_column is None:
        raise NormalizationError(
            "Le calcul de dTG exige un signal TG corrigé disponible."
        )
    if not _is_mg_unit(result.experiment.unit_for("tg")):
        raise NormalizationError(
            "Le calcul de dTG exige un signal TG exprimé en mg."
        )
    if "Temps_s" not in result.data:
        raise NormalizationError(
            "Le calcul de dTG exige l'axe temps canonique Temps_s."
        )
    time_s = pd.to_numeric(result.data["Temps_s"], errors="coerce")
    tg = pd.to_numeric(result.data[tg_column], errors="coerce")
    if len(time_s) < 2:
        raise NormalizationError(
            "Le calcul de dTG exige au moins deux points alignés."
        )
    time_values = time_s.to_numpy(dtype=float)
    tg_values = tg.to_numpy(dtype=float)
    if not np.isfinite(time_values).all() or not np.isfinite(tg_values).all():
        raise NormalizationError(
            "Le calcul de dTG exige des temps et valeurs TG numériques et finis."
        )
    if np.any(np.diff(time_values) <= 0.0):
        raise NormalizationError(
            "Le calcul de dTG exige un temps strictement croissant."
        )
    derivative_per_second = np.gradient(tg_values, time_values)
    derivative = pd.Series(
        derivative_per_second * 60.0,
        index=result.data.index,
        dtype=float,
    )
    if smoothing_points > len(derivative):
        raise NormalizationError("La fenêtre de lissage dTG dépasse le nombre de points disponibles.")
    if smoothing_points > 1:
        derivative = derivative.rolling(smoothing_points, center=True, min_periods=1).mean()
    return derivative


def _signal_reference(
    result: CorrectionResult,
    signal: str,
    settings: NormalizationSettings,
) -> float | None:
    column = _working_column(result, signal)
    if column is None:
        return None
    values = pd.to_numeric(result.data[column], errors="coerce").to_numpy(dtype=float)
    if settings.reference_mode == "first_valid":
        valid = values[np.isfinite(values)]
        if valid.size == 0:
            raise NormalizationError(
                f"Aucun point valide pour la référence {signal.upper()}."
            )
        return float(valid[0])

    axis = _axis_values(result, settings.reference_axis)
    in_range = (
        np.isfinite(axis)
        & (axis >= float(settings.range_start))
        & (axis <= float(settings.range_end))
    )
    valid = values[in_range & np.isfinite(values)]
    if valid.size == 0:
        finite_axis = axis[np.isfinite(axis)]
        if finite_axis.size and (
            float(settings.range_end) < float(finite_axis.min())
            or float(settings.range_start) > float(finite_axis.max())
        ):
            raise NormalizationError(
                "La plage de référence est hors du domaine de l'expérience."
            )
        raise NormalizationError(
            f"La plage de référence ne contient aucun point valide pour {signal.upper()}."
        )
    return float(valid.mean())


def compute_references(
    result: CorrectionResult,
    settings: NormalizationSettings,
    manual_mass_mg: float | None = None,
) -> NormalizationReferences:
    """Calcule séparément les références d'une expérience."""

    tg_settings = NormalizationSettings(
        reference_mode="first_valid",
        reference_axis=settings.reference_axis,
        tg_representation=settings.tg_representation,
        heat_flow_representation=settings.heat_flow_representation,
    )
    tg_reference = _signal_reference(result, "tg", tg_settings)
    heat_reference = _signal_reference(result, "heat_flow", settings)
    if (
        tg_reference is None
        and heat_reference is None
        and _working_column(result, "dtg") is None
    ):
        raise NormalizationError("Aucun signal TG, dTG ou Flux de chaleur n'est disponible.")

    mass: float | None
    source: str
    if manual_mass_mg is not None:
        try:
            mass = float(manual_mass_mg)
        except (TypeError, ValueError) as exc:
            raise NormalizationError(
                "La masse manuelle doit être un nombre strictement positif."
            ) from exc
        source = "manual"
    else:
        metadata_mass = extract_initial_mass_mg(result.experiment)
        if metadata_mass is not None:
            mass = metadata_mass
            source = "metadata"
        elif (
            settings.allow_missing_initial_mass
            and not _initial_mass_required(settings)
        ):
            mass = None
            source = "absent"
        else:
            raise NormalizationError(
                "Masse initiale m0 absente : ajoutez-la en mg "
                "dans les métadonnées ou saisissez-la manuellement."
            )
    if mass is not None and (not math.isfinite(mass) or mass <= 0):
        raise NormalizationError(
            "La masse initiale m0 doit être un nombre strictement positif."
        )
    normalization_mass: float | None = None
    normalization_source: str | None = None
    if settings.normalization_enabled:
        if settings.reference_mass_mg is not None:
            normalization_mass = float(settings.reference_mass_mg)
            normalization_source = "manual"
        elif settings.use_initial_mass_as_reference:
            if mass is None:
                raise NormalizationError(
                    "Masse initiale absente : saisissez une masse de référence "
                    "strictement positive."
                )
            normalization_mass = mass
            normalization_source = "m0"
        else:
            raise NormalizationError(
                "Masse de normalisation absente : saisissez une masse de référence "
                "strictement positive ou reprenez m0."
            )
        if not math.isfinite(normalization_mass) or normalization_mass <= 0:
            raise NormalizationError(
                "La masse de normalisation doit être strictement positive."
            )
    return NormalizationReferences(
        mass,
        source,
        tg_reference,
        heat_reference,
        normalization_mass,
        normalization_source,
        settings.reference_name.strip(),
    )


def apply_normalization(
    result: CorrectionResult,
    settings: NormalizationSettings,
    manual_mass_mg: float | None = None,
) -> tuple[CorrectionResult, NormalizationReferences]:
    """Ajoute uniquement les colonnes dérivées sélectionnées à une copie du résultat."""

    references = compute_references(result, settings, manual_mass_mg)
    data = result.data.drop(
        columns=[column for column in DERIVED_COLUMNS if column in result.data],
        errors="ignore",
    ).copy()
    derived: list[str] = []
    formulas: dict[str, str] = {}

    tg_column = _working_column(result, "tg")
    if tg_column is not None and settings.tg_representation != "raw":
        if not _is_mg_unit(result.experiment.unit_for("tg")):
            raise NormalizationError(
                "Les représentations TG dérivées exigent un signal TG exprimé en mg."
            )
        tg = pd.to_numeric(data[tg_column], errors="coerce")
        if references.tg_reference is None:
            raise NormalizationError("Le premier point TG valide est absent.")
        delta_mass = tg - references.tg_reference
        if settings.tg_representation == "delta_m_mg":
            column = "Delta_m_mg"
            data[column] = delta_mass
            formulas[column] = "TG(t) - TG(t0)"
        elif settings.tg_representation == "delta_m_pct":
            if references.mass_mg is None:
                raise NormalizationError(
                    "La variation relative exige une masse initiale m0."
                )
            column = "Delta_m_pct"
            data[column] = 100.0 * delta_mass / references.mass_mg
            formulas[column] = "100 * (TG(t) - TG(t0)) / m0"
        elif settings.tg_representation == "remaining_mass_mg":
            if references.mass_mg is None:
                raise NormalizationError(
                    "La masse restante exige une masse initiale m0."
                )
            column = "Masse_restante_mg"
            data[column] = references.mass_mg + delta_mass
            formulas[column] = "m0 + TG(t) - TG(t0)"
        elif settings.tg_representation == "residual_mass_pct":
            if references.mass_mg is None:
                raise NormalizationError(
                    "La masse résiduelle exige une masse initiale m0."
                )
            column = "Masse_residuelle_pct"
            data[column] = (
                100.0 * (references.mass_mg + delta_mass) / references.mass_mg
            )
            formulas[column] = "100 * (m0 + TG(t) - TG(t0)) / m0"
        elif settings.tg_representation == "normalized_mg_mg":
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            column = "Delta_m_mg_mg_ref"
            data[column] = delta_mass / references.normalization_mass_mg
            formulas[column] = "(TG(t) - TG(t0)) / m_ref"
        else:
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            column = "Delta_m_pct_ref"
            data[column] = (
                100.0 * delta_mass / references.normalization_mass_mg
            )
            formulas[column] = "100 * (TG(t) - TG(t0)) / m_ref"
        if column is not None:
            derived.append(column)

    dtg_derived_column: str | None = None
    dtg_derived_unit: str | None = None
    dtg_column = _working_column(result, "dtg")
    dtg_calculated = dtg_column is None and settings.calculate_dtg_if_missing
    if dtg_column is not None or dtg_calculated:
        if dtg_calculated:
            dtg_source = calculate_dtg_mg_per_minute(result, smoothing_points=settings.dtg_smoothing_points)
            unit_parts = ("mg", "min")
        else:
            dtg_source = pd.to_numeric(data[dtg_column], errors="coerce")
            unit_parts = _dtg_unit_parts(result.experiment.unit_for("dtg"))
        if unit_parts is None:
            raise NormalizationError(
                "L'unité dTG source doit préciser mg/s, mg/min, mg/h, %/s, %/min ou %/h."
            )
        numerator, source_period = unit_parts
        target_period = {
            "source": source_period,
            "per_second": "s",
            "per_minute": "min",
            "per_hour": "h",
        }[settings.dtg_unit_mode]
        dtg = _convert_dtg_time_basis(
            dtg_source,
            source_period,
            target_period,
        )
        period_name = target_period
        if dtg_calculated:
            conversion_formula = "60 * gradient(TG_corrigee, Temps_s)"
            if target_period == "s":
                conversion_formula = (
                    "(60 * gradient(TG_corrigee, Temps_s)) / 60"
                )
        else:
            conversion_formula = (
                "dTG_source"
                if source_period == target_period
                else (
                    "dTG_source / 60"
                    if source_period == "min"
                    else "dTG_source * 60"
                )
            )
        if target_period == "h" or source_period == "h":
            source_seconds, target_seconds = TIME_UNIT_SECONDS[source_period], TIME_UNIT_SECONDS[target_period]
            factor = max(source_seconds, target_seconds) / min(source_seconds, target_seconds)
            operation = "*" if target_seconds > source_seconds else "/"
            base = "60 * gradient(TG_corrigee, Temps_s)" if dtg_calculated else "dTG_source"
            conversion_formula = base if factor == 1 else f"({base}) {operation} {factor:g}"
        if dtg_calculated and settings.dtg_smoothing_points > 1:
            conversion_formula = f"rolling_mean({conversion_formula}, window={settings.dtg_smoothing_points}, center=True, min_periods=1)"
        if settings.dtg_representation == "raw":
            column = f"dTG_{'mg' if numerator == 'mg' else 'pct'}_{period_name}"
            data[column] = dtg
            unit = f"{numerator}/{period_name}"
            formulas[column] = conversion_formula
        else:
            if numerator != "mg":
                raise NormalizationError(
                    "La normalisation dTG par masse exige une dTG source en mg."
                )
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            if settings.dtg_representation == "per_mass":
                column = f"dTG_mg_{period_name}_mg_ref"
                data[column] = dtg / references.normalization_mass_mg
                unit = f"mg/{period_name}/mg"
                formulas[column] = f"({conversion_formula}) / m_ref"
            else:
                column = f"dTG_pct_{period_name}_ref"
                data[column] = 100.0 * dtg / references.normalization_mass_mg
                unit = f"%/{period_name}"
                formulas[column] = f"100 * ({conversion_formula}) / m_ref"
        derived.append(column)
        dtg_derived_column = column
        dtg_derived_unit = unit

    heat_column = _working_column(result, "heat_flow")
    if settings.heat_flow_representation != "raw":
        if heat_column is None:
            raise NormalizationError(
                "Le signal Flux de chaleur est absent de cette expérience."
            )
        heat_unit = _normalised_text(result.experiment.unit_for("heat_flow")).replace(
            " ", ""
        )
        if heat_unit != "mw":
            raise NormalizationError(
                "Les représentations Flux de chaleur dérivées exigent un signal en mW."
            )
        if references.heat_flow_reference_mw is None:
            raise NormalizationError("La référence Flux de chaleur est absente.")
        heat = pd.to_numeric(data[heat_column], errors="coerce")
        zeroed_heat = heat - references.heat_flow_reference_mw
        if settings.heat_flow_representation == "zero_mw":
            column = "HeatFlow_zero_mW"
            data[column] = zeroed_heat
            formulas[column] = "HF_mW - HF_ref"
        elif settings.heat_flow_representation == "w":
            column = "HeatFlow_W"
            data[column] = heat / 1000.0
            formulas[column] = "HF_mW / 1000"
        elif settings.heat_flow_representation == "zero_w":
            column = "HeatFlow_zero_W"
            data[column] = zeroed_heat / 1000.0
            formulas[column] = "(HF_mW - HF_ref) / 1000"
        elif settings.heat_flow_representation == "mw_mg":
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            column = "HeatFlow_mW_mg"
            data[column] = heat / references.normalization_mass_mg
            formulas[column] = "HF_mW / m_ref"
        elif settings.heat_flow_representation == "zero_mw_mg":
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            column = "HeatFlow_zero_mW_mg"
            data[column] = zeroed_heat / references.normalization_mass_mg
            formulas[column] = "(HF_mW - HF_ref) / m_ref"
        elif settings.heat_flow_representation == "w_g":
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            column = "HeatFlow_W_g"
            data[column] = heat / references.normalization_mass_mg
            formulas[column] = "HF_mW / m_ref"
        elif settings.heat_flow_representation == "zero_w_g":
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            column = "HeatFlow_zero_W_g"
            data[column] = zeroed_heat / references.normalization_mass_mg
            formulas[column] = "(HF_mW - HF_ref) / m_ref"
        elif settings.heat_flow_representation == "w_mg":
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            column = "HeatFlow_W_mg"
            data[column] = heat / (1000.0 * references.normalization_mass_mg)
            formulas[column] = "HF_mW / (1000 * m_ref)"
        else:
            if references.normalization_mass_mg is None:
                raise NormalizationError(
                    "Activez la normalisation et définissez sa masse de référence."
                )
            column = "HeatFlow_zero_W_mg"
            data[column] = zeroed_heat / (
                1000.0 * references.normalization_mass_mg
            )
            formulas[column] = "(HF_mW - HF_ref) / (1000 * m_ref)"
        derived.append(column)

    corrected_columns = tuple(
        column
        for column in (*result.corrected_columns, *derived)
        if column not in DERIVED_COLUMNS or column in derived
    )
    parameters = dict(result.parameters)
    derived_units: dict[str, str | None] = {}
    for derived_column in derived:
        if derived_column == dtg_derived_column:
            derived_units[derived_column] = dtg_derived_unit
            continue
        derived_units[derived_column] = next(
            representation_unit
            for representation in (TG_REPRESENTATIONS, HEAT_FLOW_REPRESENTATIONS)
            for _, (candidate, _, representation_unit) in representation.items()
            if candidate == derived_column
        )
    derived_labels: dict[str, str] = {}
    if settings.tg_representation in {"normalized_mg_mg", "normalized_pct"}:
        tg_column_name = TG_REPRESENTATIONS[settings.tg_representation][0]
        if tg_column_name in derived:
            derived_labels[tg_column_name] = tg_normalized_labels(
                settings.tg_representation,
                settings.reference_name,
            ).plain_text
    derived_units_text = {
        column: (
            None
            if unit is None
            else format_unit(unit, settings.reference_name).plain_text
        )
        for column, unit in derived_units.items()
    }
    parameters["normalization"] = {
        "tg_reference_mode": "first_valid",
        "heat_flow_reference_mode": settings.reference_mode,
        "reference_mode": settings.reference_mode,
        "reference_axis": settings.reference_axis,
        "range_start": settings.range_start,
        "range_end": settings.range_end,
        "tg_representation": settings.tg_representation,
        "dtg_unit_mode": settings.dtg_unit_mode,
        "dtg_representation": settings.dtg_representation,
        "heat_flow_representation": settings.heat_flow_representation,
        "normalization_enabled": settings.normalization_enabled,
        "reference_mass_mg": settings.reference_mass_mg,
        "reference_name": settings.reference_name.strip(),
        "use_initial_mass_as_reference": settings.use_initial_mass_as_reference,
        "calculate_dtg_if_missing": settings.calculate_dtg_if_missing,
        "dtg_smoothing_points": settings.dtg_smoothing_points,
        "dtg_smoothing_applied": dtg_calculated and settings.dtg_smoothing_points > 1,
        "dtg_calculated": dtg_calculated,
        "manual_mass_mg": manual_mass_mg,
        "references": references.as_dict(),
        "derived_columns": derived,
        "derived_units": derived_units,
        "derived_units_text": derived_units_text,
        "derived_labels": derived_labels,
        "formulas": formulas,
        "dtg_display": {
            "column": dtg_derived_column,
            "unit": dtg_derived_unit,
        },
    }
    return (
        CorrectionResult(
            experiment=result.experiment,
            blank=result.blank,
            data=data,
            method=result.method,
            common_time_s=result.common_time_s,
            corrected_columns=corrected_columns,
            warnings=list(result.warnings),
            parameters=parameters,
        ),
        references,
    )
