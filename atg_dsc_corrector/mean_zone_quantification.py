"""Zone indicators on the displayed mean, without creating experimental sources."""

from .models import TIME_AXIS_SECONDS

from dataclasses import replace

import numpy as np

from .comparison_statistics import _zone_mean_data
from .models import unit_key
from .zone_quantification import (
    HeatFlowZoneProfile, _heat_flow_area_unit, _split_signed_area, _zone_baseline,
    unavailable_zone_quantification,
)


def mean_heat_flow_profile(statistics, zone, *, axis_type, representation="raw"):
    x, signal, _ = _zone_mean_data(statistics, zone, axis_type=axis_type)
    # scientific_unit identifies the numerical scale; the plotted unit may be MathText.
    unit = statistics.scientific_unit.split(":", 2)[1] if statistics.scientific_unit else statistics.unit
    unit = {"mw": "mW", "w": "W", "mw/mg": "mW/mg", "w/g": "W/g", "w/mg": "W/mg"}.get(unit, unit)
    if zone.baseline_method == "constant" and zone.baseline_value is not None:
        if zone.baseline_representation != representation or unit_key(zone.baseline_unit or "") != unit_key(unit):
            raise ValueError("Ligne de base incompatible avec l'unité ou la représentation de la moyenne.")
    baseline = _zone_baseline(zone, x, float(signal[0]), float(signal[-1]))
    corrected = signal - baseline
    time = x * TIME_AXIS_SECONDS[axis_type] if axis_type in TIME_AXIS_SECONDS else np.full(x.shape, np.nan)
    warnings = []
    area_unit = _heat_flow_area_unit(unit)
    above = below = signed = None
    if not np.isfinite(time).all():
        warnings.append("L'aire de la moyenne nécessite un axe temporel ; aucune durée n'est déduite de la température.")
    elif len(x) < 3:
        warnings.append("L'intégration HeatFlow exige au moins trois points valides, bornes comprises.")
    elif not area_unit:
        warnings.append("L'unité de la moyenne ne permet pas l'intégration du flux de chaleur.")
    else:
        above, below = _split_signed_area(time, corrected)
        signed = above + below
    return HeatFlowZoneProfile(x, time, signal, baseline, corrected, unit, area_unit, signed,
                               tuple(warnings), positive_area=above, negative_area=below)


def quantify_mean_zone_signal(statistics, zone, *, axis_type, axis_unit, representation="raw", references=()):
    """Read one mean on its own grid; never average individual peaks or areas."""
    result = unavailable_zone_quantification("mean:" + statistics.group.identifier, statistics.group.name,
                                             zone, "", axis_unit)
    try:
        x, values, _ = _zone_mean_data(statistics, zone, axis_type=axis_type)
        updates = dict(valid_point_count=len(x), warnings=(), status="OK")
        if statistics.signal == "tg":
            unit = statistics.scientific_unit.split(":", 2)[1] if statistics.scientific_unit else statistics.unit
            if unit_key(unit) == "mg":
                updates["delta_zone_mg"] = float(values[-1] - values[0])
            updates.update(_mean_tg_references(values, unit, representation, references, len(statistics.included)))
            updates["tg_state"] = "mean"
        else:
            prefix = statistics.signal
            if prefix == "heat_flow":
                profile = mean_heat_flow_profile(statistics, zone, axis_type=axis_type, representation=representation)
                x, values = profile.axis, profile.corrected
                updates.update(heat_flow_area=profile.signed_area, heat_flow_area_unit=profile.area_unit,
                               heat_flow_positive_area=profile.positive_area, heat_flow_negative_area=profile.negative_area,
                               warnings=profile.warnings)
            for field, index in (("minimum", np.argmin(values)), ("maximum", np.argmax(values)),
                                 ("main_peak", np.argmax(np.abs(values)))):
                updates[f"{prefix}_{field}"] = float(values[index])
                updates[f"{prefix}_{field}_position"] = float(x[index])
            updates[f"{prefix}_unit"] = statistics.unit
            updates[f"{prefix}_state"] = "mean"
        if updates["warnings"]:
            updates["status"] = "Avertissement"
        return replace(result, **updates)
    except ValueError as exc:
        return replace(result, warnings=(str(exc),))


def _mean_tg_references(values, unit, representation, references, count):
    """Ratios of the displayed mean, not averages of individual zone ratios."""
    delta = float(values[-1] - values[0])
    updates = {}
    if representation in {"delta_m_pct", "residual_mass_pct"}:
        updates['delta_zone_pct_m0'] = delta
        updates['residual_mass_end_pct'] = float(values[-1]) + (100 if representation == 'delta_m_pct' else 0)
    complete = len(references) == count and count > 0 and all(
        ref is not None and ref.mass_mg is not None and np.isfinite(ref.mass_mg) and ref.mass_mg > 0
        for ref in references)
    if not complete:
        if not updates:
            updates['warnings'] = ("Masse initiale m0 absente pour au moins une expérience incluse : renseignez-la dans Réglages > Préparation.",)
        return updates
    m0 = float(np.mean([ref.mass_mg for ref in references]))
    updates['initial_mass_mg'] = m0
    if unit_key(unit) == 'mg':
        updates['delta_zone_pct_m0'] = 100 * delta / m0
        tg0 = (0 if representation == 'delta_m_mg' else m0 if representation == 'remaining_mass_mg'
               else float(np.mean([ref.tg_reference for ref in references]))
               if all(ref.tg_reference is not None for ref in references) else None)
        if tg0 is not None:
            updates['remaining_mass_end_mg'] = m0 + float(values[-1]) - tg0
            updates['residual_mass_end_pct'] = 100 * updates['remaining_mass_end_mg'] / m0
    elif representation in {'normalized_pct', 'normalized_mg_mg'}:
        if all(ref.normalization_mass_mg == ref.mass_mg for ref in references):
            factor = 1 if representation == 'normalized_pct' else 100
            updates['delta_zone_pct_m0'] = factor * delta
            updates['residual_mass_end_pct'] = 100 + factor * float(values[-1])
        else:
            updates['warnings'] = ("Les références de normalisation de la moyenne diffèrent de m0 : afficher TG en mg ou Δm/m0 pour les résultats relatifs.",)
    return updates
