"""Construction des aperçus Matplotlib, sans dépendance directe à Tkinter."""

from __future__ import annotations

from .models import TIME_AXIS_SECONDS

from atg_dsc_corrector.i18n import tr as _t, decimal_text, language

from dataclasses import dataclass, field
from copy import copy
from typing import Iterable

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.transforms import blended_transform_factory
from matplotlib.legend import Legend
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.ticker import (
    AutoMinorLocator,
    FormatStrFormatter,
    Formatter,
    LogLocator,
    MultipleLocator,
    NullLocator,
    ScalarFormatter,
)

from .analysis_zones import AnalysisZone
from .curve_styles import mpl_line_style
from .labels import (
    format_unit,
    tg_normalized_labels,
)
from .models import CorrectionResult, temperature_axis_error
from .normalization import (
    HEAT_FLOW_REPRESENTATIONS,
    TG_REPRESENTATIONS,
    resolve_working_signal,
    signal_source_state,
)
from .thermal_segments import ThermalSegmentationError, segment_temperature_series
from .thermal_program import thermal_program_points
from .zone_quantification import HeatFlowZoneProfile, heat_flow_zone_profile


SIGNALS = ("tg", "dtg", "heat_flow")
SIGNAL_LABELS = {
    "tg": _t('TG corrigée'),
    "dtg": _t('dTG corrigée'),
    "heat_flow": _t('Flux de chaleur corrigé'),
}
SIGNAL_NAMES = {
    "tg": "TG",
    "dtg": "dTG",
    "heat_flow": _t('Flux de chaleur'),
}
SIGNAL_COLUMNS = {
    "tg": "TG_corrigee",
    "dtg": "dTG_corrigee",
    "heat_flow": "HeatFlow_corrige",
}
SIGNAL_COLORS = {
    "tg": "#0072B2",
    "dtg": "#D55E00",
    "heat_flow": "#009E73",
}
AXIS_SIGNAL_ORDER = ("heat_flow", "tg", "dtg")
OUTER_RIGHT_SPINE_POSITION = 1.12
NEUTRAL_AXIS_COLOR = "black"
X_LABELS = {
    "time_s": _t('Temps (s)'),
    "time_min": _t('Temps (min)'),
    "time_h": _t('Temps (h)'),
    "furnace_temperature": _t('Température du four (°C)'),
    "sample_temperature": _t("Température de l'échantillon (°C)"),
}


def x_label(x_axis: str, *, available: bool = True) -> str:
    label = _t(X_LABELS[x_axis])
    if not available and x_axis in {"furnace_temperature", "sample_temperature"}:
        return label.rsplit(" (", 1)[0] + _t(' (unité indisponible)')
    return label


def create_signal_axes(
    figure: Figure,
    signals: Iterable[str],
    *,
    outer_right_position: float = OUTER_RIGHT_SPINE_POSITION,
) -> tuple[object, dict[str, object]]:
    """Crée les axes demandés selon leur priorité scientifique fixe."""

    requested = tuple(dict.fromkeys(signals))
    unknown = set(requested) - set(SIGNALS)
    if unknown:
        raise ValueError(f"Signaux inconnus: {sorted(unknown)}")
    ordered_signals = tuple(
        signal for signal in AXIS_SIGNAL_ORDER if signal in requested
    )
    if not ordered_signals:
        raise ValueError(_t('Sélectionner au moins un signal.'))

    primary = figure.add_subplot(111)
    axes: dict[str, object] = {}
    for index, signal in enumerate(ordered_signals):
        axis = primary if index == 0 else primary.twinx()
        if index == 2:
            axis.spines["right"].set_position(("axes", outer_right_position))
            axis.set_frame_on(True)
            axis.patch.set_visible(False)
        axes[signal] = axis
    return primary, axes


def apply_neutral_axis_style(primary, axes: Iterable[object]) -> None:
    """Applique le style structurel commun sans modifier les courbes."""

    primary.xaxis.label.set_color(NEUTRAL_AXIS_COLOR)
    primary.title.set_color(NEUTRAL_AXIS_COLOR)
    primary.tick_params(axis="x", colors=NEUTRAL_AXIS_COLOR)
    primary.xaxis.get_offset_text().set_color(NEUTRAL_AXIS_COLOR)
    primary.spines["bottom"].set_color(NEUTRAL_AXIS_COLOR)
    for axis in axes:
        axis.yaxis.label.set_color(NEUTRAL_AXIS_COLOR)
        axis.tick_params(axis="y", colors=NEUTRAL_AXIS_COLOR)
        axis.yaxis.get_offset_text().set_color(NEUTRAL_AXIS_COLOR)
        for spine in axis.spines.values():
            if spine.get_visible():
                spine.set_color(NEUTRAL_AXIS_COLOR)


def _line_values(axis, coordinate: str) -> np.ndarray:
    values = []
    for line in axis.lines:
        if line.get_label() == "_nolegend_":
            continue
        raw = line.get_xdata() if coordinate == "x" else line.get_ydata()
        numeric = np.asarray(raw, dtype=float)
        finite = numeric[np.isfinite(numeric)]
        if finite.size:
            values.append(finite)
    return np.concatenate(values) if values else np.array([], dtype=float)


def _localized_tick(text: str) -> str:
    return text.replace(".", "{,}" if "$" in text else ",") if language() == "fr" else text


class LocalizedScalarFormatter(ScalarFormatter):
    def __call__(self, value, pos=None):
        return _localized_tick(super().__call__(value, pos))

    def format_data_short(self, value):
        return _localized_tick(super().format_data_short(value))

    def format_data(self, value):
        return _localized_tick(super().format_data(value))


class LocalizedFixedFormatter(FormatStrFormatter):
    def __call__(self, value, pos=None):
        return _localized_tick(super().__call__(value, pos))


def _apply_tick_settings(axis, coordinate: str, role: str, settings: dict) -> None:
    axis_object = axis.xaxis if coordinate == "x" else axis.yaxis
    scale = settings["axis_scales"][role]
    step = settings["major_tick_steps"][role]
    subdivisions = settings["minor_tick_subdivisions"][role]
    tick_format = settings["tick_formats"][role]
    decimals = settings["tick_decimals"][role]
    if isinstance(axis_object.get_major_formatter(), ScalarFormatter):
        axis_object.set_major_formatter(LocalizedScalarFormatter(useMathText=True))

    if step is not None:
        axis_object.set_major_locator(
            MultipleLocator(step)
            if scale == "linear"
            else LogLocator(
                base=10.0,
                numticks=max(2, int(12 / max(min(float(step), 12.0), 0.1))),
            )
        )
    if subdivisions:
        axis_object.set_minor_locator(
            AutoMinorLocator(subdivisions + 1)
            if scale == "linear"
            else LogLocator(base=10.0, subs="auto", numticks=subdivisions * 10)
        )
    else:
        axis_object.set_minor_locator(NullLocator())
    if tick_format == "fixed":
        axis_object.set_major_formatter(LocalizedFixedFormatter(f"%.{decimals}f"))
    elif tick_format == "scientific":
        formatter = LocalizedScalarFormatter(useMathText=True)
        formatter.set_scientific(True)
        formatter.set_powerlimits((0, 0))
        axis_object.set_major_formatter(formatter)


def apply_graph_presentation(
    primary,
    axes: dict[str, object],
    settings: dict[str, object],
    warnings: list[str],
) -> None:
    """Applique une présentation déclarative sans toucher aux données."""

    if not settings:
        apply_neutral_axis_style(primary, axes.values())
        return
    axis_scales = settings["axis_scales"]
    x_chunks = [
        values
        for axis in axes.values()
        if (values := _line_values(axis, "x")).size
    ]
    x_values_ = np.concatenate(x_chunks) if x_chunks else np.array([], dtype=float)
    if axis_scales["x"] == "log" and x_values_.size and np.any(x_values_ <= 0):
        raise ValueError("L'axe X contient des valeurs nulles ou négatives incompatibles avec l'échelle logarithmique.")
    primary.set_xscale(axis_scales["x"])
    for signal, axis in axes.items():
        values = _line_values(axis, "y")
        if axis_scales[signal] == "log" and values.size and np.any(values <= 0):
            raise ValueError(
                f"L'axe {_t(SIGNAL_NAMES[signal])} contient des valeurs nulles ou négatives "
                "incompatibles avec l'échelle logarithmique."
            )
        axis.set_yscale(axis_scales[signal])

    primary.set_title(str(settings["title"]))
    labels = settings["axis_labels"]
    if labels["x"]:
        primary.set_xlabel(labels["x"])
    for signal, axis in axes.items():
        if labels[signal]:
            axis.set_ylabel(labels[signal])
    _apply_tick_settings(primary, "x", "x", settings)
    primary.tick_params(axis="x", labelrotation=settings["x_tick_rotation"])
    for signal, axis in axes.items():
        _apply_tick_settings(axis, "y", signal, settings)

    primary.grid(False, which="both", axis="both")
    for kind, fallback, width, alpha in (("major", "#d9d9d9", 0.7, 0.7), ("minor", "#e8e8e8", 0.5, 0.6)):
        style = settings.get("grid_styles", {}).get(kind, {})
        if settings[f"grid_{kind}"]:
            primary.grid(True, which=kind, axis=settings["grid_axis"],
                         color=style.get("color") or fallback,
                         linewidth=style.get("line_width", width),
                         linestyle=style.get("line_style", "-"),
                         alpha=1 if style.get("color") else alpha)
        for axis in (primary.xaxis, primary.yaxis):
            setattr(axis, f"_thermalcurve_grid_{kind}_color", bool(style.get("color")))
    primary.set_axisbelow(True)

    apply_neutral_axis_style(primary, axes.values())


def draw_graph_reference_lines(
    primary,
    axes: dict[str, object],
    settings: dict[str, object],
    warnings: list[str],
) -> None:
    """Trace les repères après les réglages de mise en page J14."""

    if not settings:
        return
    for line in settings["reference_lines"]:
        if not line["visible"]:
            continue
        target = line["axis"]
        if target != "x" and target not in axes:
            warnings.append(
                f"Ligne de référence '{line['label'] or line['id']}' non tracée : "
                f"axe {_t(SIGNAL_NAMES[target])} indisponible."
            )
            continue
        axis = primary if target == "x" else axes[target]
        kwargs = {
            "color": line["color"],
            "linestyle": line["line_style"],
            "linewidth": line["line_width"],
            "label": "_nolegend_",
        }
        if line["orientation"] == "vertical":
            axis.axvline(line["value"], **kwargs)
            if line["label"]:
                axis.annotate(
                    line["label"],
                    xy=(line["value"], 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(3, -3),
                    textcoords="offset points",
                    va="top",
                )
        else:
            axis.axhline(line["value"], **kwargs)
            if line["label"]:
                axis.annotate(
                    line["label"],
                    xy=(1.0, line["value"]),
                    xycoords=("axes fraction", "data"),
                    xytext=(-3, 3),
                    textcoords="offset points",
                    ha="right",
                )


def draw_graph_legend(
    primary,
    lines: list,
    labels: list[str],
    settings: dict,
    warnings: list[str] | None = None,
) -> Legend | None:
    from .legend import replace_legend
    warning_list = warnings if warnings is not None else []
    return replace_legend(primary, lines, labels, settings, _font_settings(settings, "legend", warning_list))


def _font_settings(settings: dict, target: str, warnings: list[str]) -> dict[str, object]:
    fonts = settings.get("fonts", {})
    general = dict(fonts.get("general", {}))
    override = fonts.get("overrides", {}).get(target, {})
    general.update({key: value for key, value in override.items() if target != "legend" or value not in (None, "")})
    family = general.get("family", "")
    if family:
        try:
            findfont(FontProperties(family=family), fallback_to_default=False)
        except ValueError:
            warning = f"Police '{family}' indisponible : police système utilisée."
            if warning not in warnings:
                warnings.append(warning)
            family = ""
    return {
        "fontfamily": family or None,
        "fontsize": general.get("size") or None,
        "fontweight": general.get("weight", "normal"),
        "fontstyle": general.get("style", "normal"),
    }


def _apply_font(texts, settings: dict[str, object]) -> None:
    for text in texts:
        if settings["fontfamily"]:
            text.set_fontfamily(settings["fontfamily"])
        if settings["fontsize"] is not None:
            text.set_fontsize(settings["fontsize"])
        text.set_fontweight(settings["fontweight"])
        text.set_fontstyle(settings["fontstyle"])


def apply_graph_advanced_presentation(primary, axes: dict[str, object], settings: dict[str, object], warnings: list[str]) -> None:
    """Applique les réglages avancés sans modifier les séries scientifiques."""

    if not settings:
        return
    spacing = settings["axis_spacing"]
    figure = primary.figure
    if not hasattr(figure, "_thermalcurve_auto_layout"):
        figure._thermalcurve_auto_layout = figure.get_layout_engine()
        figure._thermalcurve_auto_margins = {key: getattr(figure.subplotpars, key) for key in ("left", "right", "bottom", "top")}
    margins = settings.get("layout_margins")
    if margins is not None:
        figure.set_layout_engine("none")
        # Clear Matplotlib's compatibility placeholder before manual adjustment.
        figure.set_layout_engine(None)
        figure.subplots_adjust(**margins)
    else:
        figure.set_layout_engine(figure._thermalcurve_auto_layout)
        if figure.get_layout_engine() is None or figure.get_layout_engine().adjust_compatible:
            figure.subplots_adjust(**figure._thermalcurve_auto_margins)
    if len(axes) == 3 and "tg" in axes and "dtg" in axes:
        axes["tg"].spines["right"].set_position(("axes", spacing["tg_right_position"]))
        axes["dtg"].spines["right"].set_position(("axes", spacing["dtg_right_position"]))
        left = primary.figure.subplotpars.left
        outer_right = left + (0.88 - left) / spacing["dtg_right_position"]
        layout_engine = primary.figure.get_layout_engine()
        if margins is None and (layout_engine is None or layout_engine.adjust_compatible):
            primary.figure.subplots_adjust(
                right=min(primary.figure.subplotpars.right, outer_right)
            )
    primary.xaxis.labelpad = spacing["label_pads"]["x"]
    primary.tick_params(axis="x", pad=spacing["tick_pads"]["x"])
    for role, axis in axes.items():
        axis.yaxis.labelpad = spacing["label_pads"][role]
        axis.tick_params(axis="y", pad=spacing["tick_pads"][role])

    _apply_font([primary.title], _font_settings(settings, "title", warnings))
    for axis in axes.values():
        _apply_font([axis.xaxis.label, axis.yaxis.label], _font_settings(settings, "axes", warnings))
        _apply_font([*axis.get_xticklabels(), *axis.get_yticklabels()], _font_settings(settings, "ticks", warnings))

    annotation_font = _font_settings(settings, "annotations", warnings)
    for annotation in settings["annotations"]:
        target = annotation["axis"]
        if target != "x" and target not in axes:
            warnings.append(
                f"Annotation '{annotation['text']}' non tracée : axe {_t(SIGNAL_NAMES[target])} indisponible."
            )
            continue
        axis = primary if target == "x" else axes[target]
        coords = "data" if annotation["coordinate_system"] == "data" else "axes fraction"
        text_style = {
            key: value for key, value in annotation_font.items() if value is not None
        }
        text_style.update(
            color=annotation["color"], fontsize=annotation["font_size"],
            fontweight=annotation["font_weight"], fontstyle=annotation["font_style"],
            horizontalalignment=annotation["alignment"],
        )
        if annotation["arrow_position"] is None:
            axis.text(*annotation["position"], annotation["text"], transform=(axis.transData if coords == "data" else axis.transAxes), **text_style)
        else:
            axis.annotate(
                annotation["text"], xy=annotation["arrow_position"], xytext=annotation["position"],
                xycoords=coords, textcoords=coords,
                arrowprops={"arrowstyle": annotation["arrow_style"]}, **text_style,
            )


@dataclass(slots=True)
class PlotOptions:
    x_axis: str = "time_s"
    signals: tuple[str, ...] = ("tg",)
    x_limits: tuple[float | None, float | None] = (None, None)
    y_limits: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    align_zeros: bool = False
    alignment_mode: str = "none"
    alignment_margin: float = 0.05
    tg_representation: str = "raw"
    dtg_representation: str = "raw"
    heat_flow_representation: str = "raw"
    reference_name: str = ""
    analysis_zones: tuple[AnalysisZone, ...] = ()
    selected_analysis_zone_id: str | None = None
    show_zone_surfaces: bool = True
    show_zone_baselines: bool = True
    graph_settings: dict[str, object] = field(default_factory=dict)
    thermal_program: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.x_axis not in X_LABELS:
            raise ValueError(f"Axe horizontal inconnu: {self.x_axis}")
        unknown = set(self.signals) - set(SIGNALS)
        if unknown:
            raise ValueError(f"Signaux inconnus: {sorted(unknown)}")
        if not self.signals:
            raise ValueError(_t('Sélectionner au moins un signal.'))
        if self.tg_representation not in TG_REPRESENTATIONS:
            raise ValueError(_t('Représentation TG inconnue.'))
        if self.heat_flow_representation not in HEAT_FLOW_REPRESENTATIONS:
            raise ValueError(_t('Représentation Flux de chaleur inconnue.'))
        if self.dtg_representation not in {"raw", "per_mass", "percent"}:
            raise ValueError(_t('Représentation dTG inconnue.'))
        if self.alignment_mode not in {"none", "zeros", "references"}:
            raise ValueError(_t("Mode d'alignement inconnu."))
        if self.align_zeros and self.alignment_mode == "none":
            self.alignment_mode = "zeros"
        if not 0.0 <= self.alignment_margin <= 0.5:
            raise ValueError(_t("La marge d'alignement doit être comprise entre 0 et 0,5."))


def _numeric(series: pd.Series) -> np.ndarray:
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)


def x_values(result: CorrectionResult, x_axis: str) -> np.ndarray | None:
    if x_axis == "time_s":
        return _numeric(result.data["Temps_s"])
    if x_axis in TIME_AXIS_SECONDS:
        return _numeric(result.data["Temps_s"]) / TIME_AXIS_SECONDS[x_axis]
    role = x_axis
    column = getattr(result.experiment.mapping, role)
    if column is None or column not in result.data:
        return None
    if temperature_axis_error(result.experiment, role):
        return None
    return _numeric(result.data[column])


def draw_heat_flow_zone(
    axis, profile: HeatFlowZoneProfile, *, offset: float = 0.0,
    show_baseline: bool = True, show_surfaces: bool = True,
    positive_color: str = "#0072B2", negative_color: str = "#D55E00",
    baseline_color: str = "#7A3E9D",
) -> None:
    """Dessine les deux côtés de la ligne de base sans changer les mesures."""
    if not profile.corrected.size:
        return
    if show_baseline:
        axis.plot(profile.axis, profile.baseline + offset, color=baseline_color,
                  linestyle="--", linewidth=1.3, alpha=0.9, label="_nolegend_")
    if not show_surfaces:
        return
    # Séparer les branches pour que le remplissage ne relie pas chauffe et refroidissement.
    turns = []
    direction = 0.0
    for index, step in enumerate(np.diff(profile.axis)):
        if not np.isfinite(step):
            direction = 0.0
        elif step != 0:
            if direction and np.sign(step) != direction:
                turns.append(index)
            direction = np.sign(step)
    starts, ends = [0, *turns], [*turns, len(profile.axis) - 1]
    for start, end in zip(starts, ends):
        part = slice(start, end + 1)
        for above, color in ((True, positive_color), (False, negative_color)):
            selected = (profile.corrected[part] >= 0 if above else profile.corrected[part] < 0)
            if selected.any():
                axis.fill_between(
                    profile.axis[part], profile.signal[part] + offset,
                    profile.baseline[part] + offset, where=selected, interpolate=True,
                    color=color, alpha=0.18, linewidth=0, label="_nolegend_",
                )


def _normalization_parameters(result: CorrectionResult) -> dict:
    value = result.parameters.get("normalization", {})
    return value if isinstance(value, dict) else {}


def _column_for_signal(
    result: CorrectionResult,
    options: PlotOptions,
    signal: str,
) -> str | None:
    if signal == "tg":
        column = TG_REPRESENTATIONS[options.tg_representation][0]
        if options.tg_representation == "raw":
            return resolve_working_signal(result, signal)[0]
        return column
    if signal == "heat_flow":
        column = HEAT_FLOW_REPRESENTATIONS[options.heat_flow_representation][0]
        if options.heat_flow_representation == "raw":
            return resolve_working_signal(result, signal)[0]
        return column
    dtg = _normalization_parameters(result).get("dtg_display", {})
    if isinstance(dtg, dict) and dtg.get("column"):
        return str(dtg["column"])
    return resolve_working_signal(result, signal)[0]


def format_reference_unit(unit: str, name: str) -> str:
    return format_unit(unit, name).mathtext


def _label_for_signal(
    result: CorrectionResult,
    options: PlotOptions,
    signal: str,
) -> str:
    if signal == "tg":
        if options.tg_representation == "raw":
            return {
                "corrected": _t('TG corrigée'),
                "original": _t('TG originale'),
            }.get(signal_source_state(result, signal), _t(SIGNAL_NAMES[signal]))
        if options.tg_representation in {"normalized_mg_mg", "normalized_pct"}:
            return tg_normalized_labels(
                options.tg_representation,
                options.reference_name,
            ).mathtext
        return _t(TG_REPRESENTATIONS[options.tg_representation][1])
    if signal == "heat_flow":
        if options.heat_flow_representation == "raw":
            return {
                "corrected": _t('Flux de chaleur corrigé'),
                "original": _t('Flux de chaleur original'),
            }.get(signal_source_state(result, signal), _t(SIGNAL_NAMES[signal]))
        return _t(HEAT_FLOW_REPRESENTATIONS[options.heat_flow_representation][1])
    if options.dtg_representation == "per_mass":
        return _t('dTG normalisée')
    if options.dtg_representation == "percent":
        return _t("dTG relative")
    return {
        "corrected": _t('dTG corrigée'),
        "original": _t('dTG originale'),
        "calculated": _t('dTG calculée'),
        "derived": _t('dTG dérivée'),
    }.get(signal_source_state(result, signal), _t(SIGNAL_NAMES[signal]))


def _unit_for_signal(
    result: CorrectionResult,
    options: PlotOptions,
    signal: str,
) -> str:
    if signal == "tg":
        if options.tg_representation in {"normalized_mg_mg", "normalized_pct"}:
            return ""
        unit = TG_REPRESENTATIONS[options.tg_representation][2]
        return format_unit(unit or result.experiment.unit_for(signal)).mathtext
    if signal == "heat_flow":
        unit = HEAT_FLOW_REPRESENTATIONS[options.heat_flow_representation][2]
        value = unit or result.experiment.unit_for(signal)
        if options.heat_flow_representation in {
            "mw_mg",
            "zero_mw_mg",
            "w_g",
            "zero_w_g",
            "w_mg",
            "zero_w_mg",
        }:
            return format_unit(value, options.reference_name).mathtext
        return format_unit(value).mathtext
    dtg = _normalization_parameters(result).get("dtg_display", {})
    unit = dtg.get("unit") if isinstance(dtg, dict) else None
    if not unit:
        return format_unit(result.experiment.unit_for(signal)).mathtext
    if options.dtg_representation == "per_mass":
        return format_unit(str(unit), options.reference_name).mathtext
    return format_unit(str(unit)).mathtext


class SignificantScientificFormatter(Formatter):
    """Facteur commun MathText et mantisses à deux chiffres significatifs."""

    def __init__(self, exponent: int) -> None:
        self.exponent = exponent
        self._factor = 10.0**exponent

    def __call__(self, value: float, position: int | None = None) -> str:
        del position
        scaled = value / self._factor
        if abs(scaled) < 1e-14:
            return "0"
        return decimal_text(f"{scaled:.2g}")

    def get_offset(self) -> str:
        return rf"$\times10^{{{self.exponent}}}$"


def _visible_line_values(axis, coordinate: str) -> np.ndarray:
    values: list[np.ndarray] = []
    x_low, x_high = sorted(axis.get_xlim())
    y_low, y_high = sorted(axis.get_ylim())
    for line in axis.lines:
        x = np.asarray(line.get_xdata(), dtype=float)
        y = np.asarray(line.get_ydata(), dtype=float)
        if x.shape != y.shape:
            continue
        visible = (
            np.isfinite(x)
            & np.isfinite(y)
            & (x >= x_low)
            & (x <= x_high)
            & (y >= y_low)
            & (y <= y_high)
        )
        selected = (x if coordinate == "x" else y)[visible]
        if selected.size:
            values.append(selected)
    return np.concatenate(values) if values else np.array([], dtype=float)


def apply_scientific_tick_format(axis, coordinate: str) -> bool:
    """Active le facteur commun pour les valeurs visibles d'ordre au plus 10⁻²."""

    values = _visible_line_values(axis, coordinate)
    nonzero = np.abs(values[values != 0.0])
    axis_object = axis.xaxis if coordinate == "x" else axis.yaxis
    if nonzero.size:
        exponent = int(np.floor(np.log10(float(nonzero.max()))))
        if exponent <= -2:
            axis_object.set_major_formatter(SignificantScientificFormatter(exponent))
            return True
    if isinstance(axis_object.get_major_formatter(), SignificantScientificFormatter):
        axis_object.set_major_formatter(LocalizedScalarFormatter(useMathText=True))
    return False


def _apply_partial_limits(
    axis,
    limits: tuple[float | None, float | None],
    horizontal: bool = False,
) -> None:
    current = axis.get_xlim() if horizontal else axis.get_ylim()
    low = current[0] if limits[0] is None else limits[0]
    high = current[1] if limits[1] is None else limits[1]
    if low >= high:
        raise ValueError(_t('La limite minimale doit être inférieure à la limite maximale.'))
    (axis.set_xlim if horizontal else axis.set_ylim)(low, high)


def align_axis_zeros(axes: Iterable, limits: dict | None = None) -> None:
    """Compatibilité : aligne zéro sans imposer des limites symétriques."""

    align_axis_references({axis: 0.0 for axis in axes}, limits=limits)


def _line_extent(axis) -> tuple[float, float] | None:
    finite_values: list[np.ndarray] = []
    for line in axis.lines:
        values = np.asarray(line.get_ydata(), dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size:
            finite_values.append(finite)
    if not finite_values:
        return None
    merged = np.concatenate(finite_values)
    return float(merged.min()), float(merged.max())


def align_axis_references(
    references: dict[object, float],
    margin: float = 0.05,
    limits: dict | None = None,
    follow_limits: bool = True,
) -> None:
    """Aligne des niveaux physiques en conservant l'étendue utile de chaque série."""

    usable: list[tuple[object, float, float, float, float]] = []
    fractions: list[float] = []
    for axis, reference in references.items():
        extent = _line_extent(axis)
        if extent is None or not np.isfinite(reference):
            continue
        low, high = extent
        span = high - low
        padding = max(span * margin, abs(reference) * 1e-9, 1e-12)
        low = min(low, reference) - padding
        high = max(high, reference) + padding
        fraction = (reference - low) / (high - low)
        usable.append((axis, reference, low, high, fraction))
        fractions.append(fraction)
    if len(usable) < 2:
        return
    # Minimise la pire dilatation d'axe, y compris pour des signaux de signes opposés.
    target = max(fractions) / (max(fractions) + 1.0 - min(fractions))
    limits = limits or {}
    anchors = []
    for axis, reference, *_ in usable:
        low, high = limits.get(axis, (None, None))
        if (low is not None and low >= reference) or (high is not None and high <= reference):
            raise ValueError(_t('Les bornes doivent encadrer strictement le niveau aligné.'))
        if low is not None and high is not None:
            anchors.append((reference - low) / (high - low))
    if anchors:
        if max(anchors) - min(anchors) > 1e-8:
            raise ValueError(_t('Ces bornes imposent des positions de zéro différentes. Régler un seul axe à la fois ou désactiver l’alignement.'))
        target = anchors[0]
    for axis, reference, low, high, _ in usable:
        below = max(reference - low, 0.0)
        above = max(high - reference, 0.0)
        span = max(
            below / target if below else 0.0,
            above / (1.0 - target) if above else 0.0,
            1e-12,
        )
        fixed_low, fixed_high = limits.get(axis, (None, None))
        if fixed_low is not None:
            span = (reference - fixed_low) / target
        elif fixed_high is not None:
            span = (fixed_high - reference) / (1.0 - target)
        axis.set_ylim(reference - target * span, reference + (1.0 - target) * span, emit=False)

    if follow_limits:
        def keep_references_aligned(changed):
            low, high = changed.get_ylim()
            if low < references[changed] < high and all(a.get_yscale() == "linear" for a in references):
                align_axis_references(references, margin, {changed: (low, high)}, follow_limits=False)

        for axis, *_ in usable:
            axis.callbacks.connect("ylim_changed", keep_references_aligned)


def _reference_level(
    result: CorrectionResult,
    options: PlotOptions,
    signal: str,
) -> float | None:
    normalization = _normalization_parameters(result)
    references = normalization.get("references", {})
    references = references if isinstance(references, dict) else {}
    if signal == "dtg":
        return 0.0
    if signal == "tg":
        if options.tg_representation == "remaining_mass_mg":
            return float(references["m0_mg"]) if references.get("m0_mg") is not None else None
        if options.tg_representation == "residual_mass_pct":
            return 100.0
        return 0.0
    if options.heat_flow_representation.startswith("zero_"):
        return 0.0
    heat_reference = references.get("heat_flow_reference_mw")
    if heat_reference is None:
        return None
    value = float(heat_reference)
    if options.heat_flow_representation == "w":
        return value / 1000.0
    mass = references.get("normalization_mass_mg")
    if options.heat_flow_representation in {"mw_mg", "w_g"}:
        return value / float(mass) if mass else None
    if options.heat_flow_representation == "w_mg":
        return value / (1000.0 * float(mass)) if mass else None
    return value


def apply_axis_appearance(primary, axes, thermal_axis, settings, warnings):
    """Decorate independent axes after all scientific curves and limits exist."""
    appearances = settings.get("axis_appearance")
    if not appearances:
        return
    top = primary.secondary_xaxis("top")
    # This is a second ruler for the same abscissa, never a transformed series.
    top.xaxis.set_major_locator(copy(primary.xaxis.get_major_locator()))
    top.xaxis.set_minor_locator(copy(primary.xaxis.get_minor_locator()))
    top.xaxis.set_major_formatter(copy(primary.xaxis.get_major_formatter()))
    top.set_xlabel(primary.get_xlabel())
    primary._thermalcurve_top_axis = top
    targets = {"x": (primary, "x", "bottom"), "x_top": (top, "x", "top")}
    targets.update({role: (axis, "y", "left" if axis is primary else "right") for role, axis in axes.items()})
    if thermal_axis is not None:
        targets["thermal_program"] = (thermal_axis, "y", "right")
    moved_side = any(appearances[role]['position'] not in ('auto', side)
                     for role, (_, coordinate, side) in targets.items() if coordinate == 'y')
    for axis in primary.figure.axes:
        # Each physical spine is drawn by its owner, with no twin overpainting it.
        for spine in axis.spines.values():
            spine.set_visible(False)
    side_count = {"left": 0, "right": 0}
    for role, (axis, coordinate, default_side) in targets.items():
        style = appearances[role]
        side = default_side if style["position"] == "auto" else style["position"]
        spine = axis.spines[side]
        if coordinate == "y":
            if moved_side:
                spine.set_position(("outward", 52 * side_count[side]))
            side_count[side] += 1
            axis.yaxis.set_label_position(side)
        spine.set_visible(style["visible"] and style["line_visible"])
        spine.set_linewidth(style["width"])
        spine.set_edgecolor(style["color"] or NEUTRAL_AXIS_COLOR)
        spine._thermalcurve_custom_color = style["color"] is not None
        if coordinate == "y" and len(axes) == 1 and thermal_axis is None:
            # Complete the frame without adding a second ruler or twin overpainting.
            frame = axis.spines["right" if side == "left" else "left"]
            frame.set_visible(spine.get_visible())
            frame.set_linewidth(spine.get_linewidth())
            frame.set_edgecolor(spine.get_edgecolor())
            frame._thermalcurve_custom_color = spine._thermalcurve_custom_color
        axis_object = axis.xaxis if coordinate == "x" else axis.yaxis
        axis_object.label.set_visible(style["visible"] and style["labels_visible"])
        axis_object.get_offset_text().set_visible(style["visible"] and style["labels_visible"])
        sides = ("bottom", "top") if coordinate == "x" else ("left", "right")
        for kind in ("major", "minor"):
            tick = style[kind]
            kwargs = {name: style["visible"] and tick["visible"] and name == side for name in sides}
            kwargs.update({f"label{name}": style["visible"] and style["labels_visible"] and name == side for name in sides})
            kwargs.update({key: tick[key] for key in ("length", "width") if tick[key] is not None})
            axis.tick_params(axis=coordinate, which=kind, direction=tick["direction"],
                             color=tick["color"] or style["color"] or NEUTRAL_AXIS_COLOR, **kwargs)
            setattr(axis_object, f"_thermalcurve_tick_{kind}_color", bool(tick["color"] or style["color"]))
        if style["arrow"] != "none" and spine.get_visible():
            transform = blended_transform_factory(axis.transAxes, spine.get_transform()) if coordinate == "x" else blended_transform_factory(spine.get_transform(), axis.transAxes)
            ends = (0, 1) if style["arrow"] == "both" else (1,)
            for end in ends:
                if coordinate == "x":
                    xy = (end, 0 if side == "bottom" else 1)
                    marker = ">" if end else "<"
                else:
                    xy = (0 if side == "left" else 1, end)
                    marker = "^" if end else "v"
                arrow, = axis.plot(*xy, marker=marker, color=style["color"] or NEUTRAL_AXIS_COLOR,
                                   markersize=5 + style["width"], transform=transform, clip_on=False,
                                   scalex=False, scaley=False, label="_nolegend_")
                arrow._thermalcurve_custom_color = bool(style["color"])
                arrow._thermalcurve_axis_arrow = True
    _apply_font([top.xaxis.label], _font_settings(settings, "axes", warnings))
    _apply_font(top.get_xticklabels(), _font_settings(settings, "ticks", warnings))
    top.tick_params(axis="x", labelrotation=settings["x_tick_rotation"])


def draw_thermal_program(primary, axes, options, warnings, lines, labels):
    """Trace la consigne sur un axe droit, commun aux vues simples et superposées."""
    thermal_axis = None
    program = options.thermal_program
    if program is not None and program.get("enabled"):
        if options.x_axis not in {"time_s", "time_min", "time_h"}:
            warnings.append(_t('Le programme thermique est masqué : sélectionner un axe temporel.'))
        else:
            times, temperatures = thermal_program_points(program)
            x = np.asarray(times) * 60 / TIME_AXIS_SECONDS[options.x_axis]
            y = np.asarray(temperatures) + (273.15 if program["temperature_unit"] == "K" else 0)
            thermal_axis = primary.twinx()
            thermal_axis.yaxis.set_major_formatter(LocalizedScalarFormatter(useMathText=True))
            right_positions = [
                axis.spines["right"].get_position()[1]
                if axis.spines["right"].get_position()[0] == "axes" else 1.0
                for axis in axes.values() if axis is not primary
            ]
            spacing = options.graph_settings.get("axis_spacing", {})
            if spacing.get("tg_right_position", 1.0) == 1.0 and spacing.get("dtg_right_position", 1.12) == 1.12:
                right_axes = [axis for axis in axes.values() if axis is not primary]
                for index, axis in enumerate([*right_axes, thermal_axis]):
                    axis.spines["right"].set_position(("outward", 52 * index))
            else:
                position = max(right_positions) + 0.08 if right_positions else 1.0
                thermal_axis.spines["right"].set_position(("axes", position))
            thermal_axis.patch.set_visible(False)
            label = _t('Température programmée')
            line, = thermal_axis.plot(x, y, color="#8C564B", linestyle="--", label=label)
            line.set_gid("thermal-program")
            thermal_axis.set_ylabel(f"{label} ({program['temperature_unit']})")
            apply_neutral_axis_style(primary, [thermal_axis])
            # Les limites manuelles restent prioritaires ; le domaine auto inclut la consigne.
            left, right = primary.get_xlim()
            primary.set_xlim(
                min(left, float(x.min())) if options.x_limits[0] is None else options.x_limits[0],
                max(right, float(x.max())) if options.x_limits[1] is None else options.x_limits[1],
            )
            lines.append(line)
            labels.append(label)
    return thermal_axis


class CorrectionPlot:
    """Figure réutilisable par l'interface Tk et les tests hors écran."""

    def __init__(self, figure: Figure | None = None) -> None:
        self.figure = figure or Figure(figsize=(9, 6), dpi=100, constrained_layout=True)
        self.axes: dict[str, object] = {}
        self.primary_axis: object | None = None
        self.hidden_zone_count = 0
        self.warnings: list[str] = []
        self.thermal_axis = None

    def draw(self, results: Iterable[CorrectionResult], options: PlotOptions) -> None:
        results = list(results)
        self.figure.clear()
        self.warnings = []
        self.thermal_axis = None
        primary, self.axes = create_signal_axes(self.figure, options.signals)
        self.primary_axis = primary
        self.hidden_zone_count = sum(
            zone.axis_type != options.x_axis for zone in options.analysis_zones
        )

        line_styles = ("-", "--", "-.", ":")
        lines = []
        labels = []
        temperature_axis_available = False
        for result_index, result in enumerate(results):
            x = x_values(result, options.x_axis)
            if x is None:
                detail = (
                    temperature_axis_error(result.experiment, options.x_axis)
                    or "Axe X indisponible."
                    if options.x_axis in {"furnace_temperature", "sample_temperature"}
                    else "Axe X indisponible."
                )
                self.warnings.append(f"{result.experiment.name}: {detail}")
                continue
            temperature_axis_available = True
            temperature_segments = None
            if options.x_axis in {"furnace_temperature", "sample_temperature"}:
                try:
                    temperature_segments = segment_temperature_series(
                        _numeric(result.data["Temps_s"]), x
                    )
                except ThermalSegmentationError as error:
                    self.warnings.append(
                        f"{result.experiment.name}: tracé température non segmentable "
                        f"({error}); points affichés sans relier les phases."
                    )
            for signal in self.axes:
                column = _column_for_signal(result, options, signal)
                if column not in result.data:
                    continue
                y = _numeric(result.data[column])
                configured_style = options.graph_settings.get(
                    "curve_styles", {}
                ).get(signal, {})
                color = configured_style.get("color", SIGNAL_COLORS[signal])
                line_style = configured_style.get(
                    "line_style", line_styles[result_index % len(line_styles)]
                )
                line_width = configured_style.get("line_width", 1.4)
                marker = configured_style.get("marker", "") or None
                markevery = configured_style.get("markevery")
                if temperature_segments is not None:
                    first_segment_line = True
                    for segment in temperature_segments:
                        segment_slice = slice(segment.start, segment.stop)
                        finite = np.isfinite(x[segment_slice]) & np.isfinite(y[segment_slice])
                        if not finite.any():
                            continue
                        line = self.axes[signal].plot(
                            x[segment_slice][finite],
                            y[segment_slice][finite],
                            color=color,
                            linestyle=mpl_line_style(line_style),
                            linewidth=line_width,
                            marker=marker,
                            markevery=markevery,
                            label=(
                                f"{result.experiment.name} - "
                                f"{_label_for_signal(result, options, signal)}"
                                if first_segment_line
                                else "_nolegend_"
                            ),
                        )[0]
                        if first_segment_line:
                            lines.append(line)
                            labels.append(line.get_label())
                            first_segment_line = False
                    continue
                finite = np.isfinite(x) & np.isfinite(y)
                if not finite.any():
                    continue
                line = self.axes[signal].plot(
                    x[finite],
                    y[finite],
                    color=color,
                    linestyle=(
                        "None"
                        if options.x_axis in {"furnace_temperature", "sample_temperature"}
                        else mpl_line_style(line_style)
                    ),
                    marker=(
                        marker or "."
                        if options.x_axis in {"furnace_temperature", "sample_temperature"}
                        else marker
                    ),
                    markevery=markevery,
                    markersize=2.5,
                    linewidth=line_width,
                    label=f"{result.experiment.name} - {_label_for_signal(result, options, signal)}",
                )[0]
                lines.append(line)
                labels.append(line.get_label())

        primary.set_xlabel(
            x_label(
                options.x_axis,
                available=(
                    temperature_axis_available
                    or options.x_axis not in {
                        "furnace_temperature", "sample_temperature"
                    }
                ),
            )
        )
        primary.grid(True, color="#d9d9d9", linewidth=0.7, alpha=0.7)
        for signal, axis in self.axes.items():
            units = {
                unit
                for result in results
                if (unit := _unit_for_signal(result, options, signal))
            }
            unit_label = next(iter(units)) if len(units) == 1 else ""
            labels_for_signal = {
                _label_for_signal(result, options, signal) for result in results
            }
            signal_label = (
                next(iter(labels_for_signal))
                if len(labels_for_signal) == 1
                else _t(SIGNAL_NAMES[signal])
            )
            label = signal_label + (
                f" ({unit_label})" if unit_label else ""
            )
            axis.set_ylabel(label)
            if signal in options.y_limits:
                _apply_partial_limits(axis, options.y_limits[signal])

        _apply_partial_limits(primary, options.x_limits, horizontal=True)
        if options.alignment_mode != "none":
            aligned: dict[object, float] = {}
            for signal, axis in self.axes.items():
                if (
                    options.alignment_mode == "zeros"
                    and signal == "tg"
                    and options.tg_representation
                    in {"remaining_mass_mg", "residual_mass_pct"}
                ):
                    self.warnings.append(
                        "La masse restante/résiduelle est exclue de l'alignement sur zéro ; "
                        "utilisez l'alignement des niveaux de référence."
                    )
                    continue
                levels = [
                    _reference_level(result, options, signal) for result in results
                ]
                finite_levels = [
                    float(level) for level in levels if level is not None and np.isfinite(level)
                ]
                if options.alignment_mode == "zeros":
                    level = 0.0
                elif finite_levels:
                    level = float(np.median(finite_levels))
                else:
                    continue
                aligned[axis] = level
            align_axis_references(aligned, options.alignment_margin, {
                axis: options.y_limits.get(signal, (None, None))
                for signal, axis in self.axes.items() if axis in aligned
            })

        apply_scientific_tick_format(primary, "x")
        for axis in self.axes.values():
            apply_scientific_tick_format(axis, "y")
        if not lines:
            primary.text(
                0.5,
                0.5,
                _t('Aucune courbe compatible à afficher'),
                ha="center",
                va="center",
                transform=primary.transAxes,
            )
        displayed_limits = primary.get_xlim()
        zone_colors = ("#6A5ACD", "#C44E52", "#4C956C", "#CC8B00")
        visible_zones = (
            zone
            for zone in options.analysis_zones
            if zone.axis_type == options.x_axis
        )
        for index, zone in enumerate(visible_zones):
            color = zone.color or zone_colors[index % len(zone_colors)]
            active = zone.identifier == options.selected_analysis_zone_id
            primary.axvspan(
                zone.start,
                zone.end,
                color=color,
                alpha=zone.opacity if zone.opacity is not None else 0.22 if active else 0.10,
                linewidth=0,
                label="_nolegend_",
            )
            primary.axvline(
                zone.start,
                color=color,
                linewidth=zone.line_width if zone.line_width is not None else 2.2 if active else 1.0,
                linestyle="-" if active else ":",
                alpha=1.0 if active else 0.75,
                label="_nolegend_",
            )
            primary.axvline(
                zone.end,
                color=color,
                linewidth=zone.line_width if zone.line_width is not None else 2.2 if active else 1.0,
                linestyle="-" if active else ":",
                alpha=1.0 if active else 0.75,
                label="_nolegend_",
            )
            if (
                zone.identifier == options.selected_analysis_zone_id
                and "heat_flow" in self.axes
            ):
                heat_axis = self.axes["heat_flow"]
                for result in results:
                    profile = heat_flow_zone_profile(
                        result,
                        zone,
                        options.heat_flow_representation,
                    )
                    draw_heat_flow_zone(
                        heat_axis, profile,
                        show_baseline=zone.show_baseline and options.show_zone_baselines,
                        positive_color=zone.positive_area_color or "#0072B2",
                        negative_color=zone.negative_area_color or "#D55E00",
                        baseline_color=zone.baseline_color or "#7A3E9D",
                        show_surfaces=options.show_zone_surfaces,
                    )
        primary.set_xlim(displayed_limits)
        apply_graph_presentation(
            primary, self.axes, options.graph_settings, self.warnings
        )
        apply_graph_advanced_presentation(
            primary, self.axes, options.graph_settings, self.warnings
        )
        draw_graph_reference_lines(
            primary, self.axes, options.graph_settings, self.warnings
        )
        self.thermal_axis = draw_thermal_program(
            primary, self.axes, options, self.warnings, lines, labels
        )
        apply_axis_appearance(primary, self.axes, self.thermal_axis, options.graph_settings, self.warnings)
        draw_graph_legend(
            primary, lines, labels, options.graph_settings, self.warnings
        )

    def autoscale(self) -> None:
        for axis in self.axes.values():
            axis.relim()
            axis.autoscale(enable=True, axis="both", tight=False)
        if self.primary_axis is not None:
            apply_scientific_tick_format(self.primary_axis, "x")
        for axis in self.axes.values():
            apply_scientific_tick_format(axis, "y")
        if self.primary_axis is not None:
            apply_neutral_axis_style(self.primary_axis, self.axes.values())
