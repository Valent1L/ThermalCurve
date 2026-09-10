"""Comparaison graphique de résultats corrigés, sans interpolation commune."""

from __future__ import annotations

from atg_dsc_corrector.i18n import tr as _t

from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np
from matplotlib.figure import Figure

from .models import CorrectionResult, temperature_axis_error, unit_key
from .normalization import (
    HEAT_FLOW_REPRESENTATIONS,
    TG_REPRESENTATIONS,
    resolve_working_signal,
)
from .plotting import (
    PlotOptions,
    SIGNAL_NAMES,
    _column_for_signal,
    _label_for_signal,
    _normalization_parameters,
    _reference_level,
    _unit_for_signal,
    apply_graph_advanced_presentation,
    apply_axis_appearance,
    apply_graph_presentation,
    apply_scientific_tick_format,
    align_axis_zeros,
    align_axis_references,
    create_signal_axes,
    draw_graph_legend,
    draw_graph_reference_lines,
    draw_heat_flow_zone,
    draw_thermal_program,
    x_label,
    x_values,
)
from .zone_quantification import heat_flow_zone_profile
from .curve_styles import mpl_line_style, mean_curve_style


COMPARISON_COLORS = (
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
)


@dataclass(slots=True)
class ComparisonCurve:
    identifier: str
    result: CorrectionResult
    legend_name: str
    visible: bool = True
    line_style: str = "-"
    line_width: float = 1.4
    marker: str = ""
    markevery: int | None = None
    y_offset: float = 0.0
    stage: str = "corrected"
    plot_options: PlotOptions | None = None
    signal_settings: dict[str, dict[str, object]] = field(default_factory=dict)

    def for_signal(self, signal: str) -> ComparisonCurve:
        settings = self.signal_settings.get(signal, {})
        fields = {key: settings[key] for key in ("legend_name", "line_style", "line_width", "marker", "markevery", "y_offset") if key in settings}
        return replace(self, **fields, visible=self.visible and settings.get("visible", True)) if fields or not settings.get("visible", True) else self

    def __post_init__(self) -> None:
        if self.stage not in {"original", "corrected", "normalized"}:
            raise ValueError("Représentation de comparaison inconnue.")


@dataclass(slots=True)
class ComparisonOptions:
    signal: str = "tg"
    plot_options: PlotOptions = field(default_factory=PlotOptions)
    domain_mode: str = "union"
    x_limits: tuple[float | None, float | None] = (None, None)
    y_limits: tuple[float | None, float | None] = (None, None)
    y_limits_by_signal: dict[
        str, tuple[float | None, float | None]
    ] = field(default_factory=dict)
    title: str = _t('Comparaison des expériences')
    grid: bool = True
    colors: dict[str, str] = field(default_factory=dict)
    show_offsets_in_legend: bool = False
    signals: tuple[str, ...] = ()
    align_zeros: bool = False
    graph_settings: dict[str, object] = field(default_factory=dict)
    mean_styles: dict[str, dict[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        supported = {"tg", "dtg", "heat_flow"}
        if not self.signals:
            self.signals = (self.signal,)
        if (
            self.signal not in supported
            or any(signal not in supported for signal in self.signals)
            or self.signal not in self.signals
            or len(self.signals) != len(set(self.signals))
        ):
            raise ValueError("Signal de comparaison inconnu.")
        if self.domain_mode not in {"union", "overlap"}:
            raise ValueError("Domaine de comparaison inconnu.")


class ComparisonPlot:
    """Figure Matplotlib de comparaison avec une échelle Y par signal."""

    def __init__(self, figure: Figure | None = None) -> None:
        self.figure = figure or Figure(figsize=(9, 6), dpi=100, constrained_layout=True)
        self.axis: object | None = None
        self.axes: dict[str, object] = {}
        self.warnings: list[str] = []
        self.colors: dict[str, str] = {}
        self.thermal_axis = None

    def _create_axes(self, signals: tuple[str, ...]) -> object:
        primary, self.axes = create_signal_axes(self.figure, signals)
        self.axis = primary
        return primary

    def _align_references(self, curves, options) -> None:
        if options.align_zeros or options.plot_options.alignment_mode != "references":
            return
        references = {}
        for signal, axis in self.axes.items():
            levels = [
                _reference_level(curve.result, curve.plot_options or options.plot_options, signal)
                for curve in curves if curve.for_signal(signal).visible
            ]
            levels = [level for level in levels if level is not None and np.isfinite(level)]
            if levels and np.allclose(levels, levels[0]):
                references[axis] = levels[0]
            elif levels:
                self.warnings.append(_t('Références différentes : cet axe ne peut pas être aligné sur une référence commune.'))
        align_axis_references(references, options.plot_options.alignment_margin, {
            axis: options.y_limits_by_signal.get(signal, (None, None))
            for signal, axis in self.axes.items() if axis in references
        })

    def draw(
        self,
        curves: Iterable[ComparisonCurve],
        options: ComparisonOptions,
    ) -> None:
        curves = list(curves)
        self.figure.clear()
        primary = self._create_axes(options.signals)
        self.warnings = []
        self.colors.update(options.colors)
        compatible: dict[
            str, list[tuple[ComparisonCurve, np.ndarray, np.ndarray, str, PlotOptions]]
        ] = {signal: [] for signal in self.axes}
        expected_units: dict[str, str] = {}
        expected_scientific_units: dict[str, str] = {}
        displayed_x: list[np.ndarray] = []
        lines = []
        labels = []
        temperature_axis_available = any(
            curve.visible
            and x_values(
                curve.result,
                (curve.plot_options or options.plot_options).x_axis,
            ) is not None
            for curve in curves
        )
        for signal in self.axes:
            for curve in curves:
                if not curve.for_signal(signal).visible:
                    continue
                curve_options = curve.plot_options or options.plot_options
                resolved, reason = self._admitted_signal(
                    curve,
                    curve_options,
                    signal,
                    expected_scientific_units.get(signal),
                )
                if resolved is None:
                    self.warnings.append(
                        f"{curve.legend_name} ({_t(SIGNAL_NAMES[signal])}) : {reason}"
                    )
                    continue
                x, y, unit, scientific_unit, _column = resolved
                finite = np.isfinite(x) & np.isfinite(y)
                expected_scientific_units.setdefault(signal, scientific_unit)
                expected_units.setdefault(signal, unit)
                compatible[signal].append(
                    (curve, x[finite], y[finite], unit, curve_options)
                )

        multiple_signals = len(options.signals) > 1
        for signal, signal_curves in compatible.items():
            axis = self.axes[signal]
            for curve, x, y, unit, _curve_options in signal_curves:
                curve = curve.for_signal(signal)
                color = curve.signal_settings.get(signal, {}).get("color") or self.colors.setdefault(
                    curve.identifier,
                    COMPARISON_COLORS[len(self.colors) % len(COMPARISON_COLORS)],
                )
                label_text = curve.legend_name
                if multiple_signals:
                    label_text += f" - {_t(SIGNAL_NAMES[signal])}"
                if options.show_offsets_in_legend and not np.isclose(curve.y_offset, 0.0):
                    label_text += _t(" (décalage {offset:+.3g} {unit})", offset=curve.y_offset, unit=unit)
                line = axis.plot(
                    x,
                    y + curve.y_offset,
                    color=color,
                    linewidth=curve.line_width,
                    linestyle=mpl_line_style(curve.line_style),
                    marker=curve.marker or None,
                    markevery=curve.markevery,
                    gid=f"curve:{curve.identifier}:{signal}",
                    label=label_text,
                )[0]
                lines.append(line)
                labels.append(label_text)
                displayed_x.append(x)
            curve_labels = {
                self._label_for_curve(curve, curve_options, signal)
                for curve, _x, _y, _unit, curve_options in signal_curves
            }
            label = (
                next(iter(curve_labels))
                if len(curve_labels) == 1
                else _t(SIGNAL_NAMES[signal])
            )
            unit = expected_units.get(signal, "")
            axis.set_ylabel(label + (f" ({unit})" if unit else ""))

        primary.set_xlabel(
            x_label(
                options.plot_options.x_axis,
                available=(
                    temperature_axis_available
                    or options.plot_options.x_axis not in {
                        "furnace_temperature", "sample_temperature"
                    }
                ),
            )
        )
        primary.set_title(options.title)
        self.set_grid(options.grid)
        if displayed_x:
            xmin = min(float(np.min(x)) for x in displayed_x)
            xmax = max(float(np.max(x)) for x in displayed_x)
            if options.domain_mode == "overlap":
                xmin = max(float(np.min(x)) for x in displayed_x)
                xmax = min(float(np.max(x)) for x in displayed_x)
                if xmin >= xmax:
                    self.warnings.append("Les courbes n'ont pas de domaine X commun.")
                    xmin = xmax = None
            if options.x_limits != (None, None):
                self._apply_limits(primary, options.x_limits, horizontal=True)
            elif xmin is not None and xmax is not None:
                primary.set_xlim(xmin, xmax)
            limits_by_signal = options.y_limits_by_signal or {
                options.signal: options.y_limits
            }
            for signal, limits in limits_by_signal.items():
                if signal in self.axes:
                    self._apply_limits(
                        self.axes[signal], limits, horizontal=False
                    )
            if options.align_zeros:
                align_axis_zeros(self.axes.values(), {
                    axis: limits_by_signal.get(signal, (None, None)) for signal, axis in self.axes.items()
                })
        else:
            primary.text(0.5, 0.5, _t('Aucune courbe compatible à afficher'), ha="center", va="center", transform=primary.transAxes)
        self._align_references(curves, options)
        apply_scientific_tick_format(primary, "x")
        for axis in self.axes.values():
            apply_scientific_tick_format(axis, "y")
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
            primary, self.axes, options.plot_options, self.warnings, lines, labels
        )
        apply_axis_appearance(primary, self.axes, self.thermal_axis, options.graph_settings, self.warnings)
        draw_graph_legend(
            primary, lines, labels, options.graph_settings, self.warnings
        )

    def set_grid(self, visible: bool) -> None:
        """Applique la grille principale sans modifier les courbes ni les limites."""
        if self.axis is None:
            return
        self.axis.grid(visible=visible, which="major", axis="both")
        self.axis.set_axisbelow(True)

    @staticmethod
    def _column_for_curve(
        curve: ComparisonCurve, options: PlotOptions, signal: str
    ) -> str | None:
        if not curve.visible or not curve.signal_settings.get(signal, {}).get("visible", True):
            return None
        if curve.stage in {"original", "corrected"}:
            return resolve_working_signal(
                curve.result,
                signal,
                stage=curve.stage,
            )[0]
        return _column_for_signal(curve.result, options, signal)

    @staticmethod
    def _unit_for_curve(
        curve: ComparisonCurve, options: PlotOptions, signal: str
    ) -> str:
        if curve.stage in {"original", "corrected"}:
            raw = PlotOptions(
                x_axis=options.x_axis,
                signals=(signal,),
                tg_representation="raw",
                dtg_representation="raw",
                heat_flow_representation="raw",
            )
            return _unit_for_signal(curve.result, raw, signal)
        return _unit_for_signal(curve.result, options, signal)

    @staticmethod
    def _scientific_unit_for_curve(
        curve: ComparisonCurve, options: PlotOptions, signal: str
    ) -> str:
        """Identité numérique d'une courbe, indépendante de sa légende."""

        normalization = _normalization_parameters(curve.result)
        stored_reference = normalization.get("reference_name", "")
        normalization_reference = options.reference_name.strip() or (
            str(stored_reference).strip() if stored_reference else ""
        )
        reference = ""
        if curve.stage in {"original", "corrected"}:
            unit = curve.result.experiment.unit_for(signal)
        elif signal == "tg":
            representation = options.tg_representation
            unit = (
                TG_REPRESENTATIONS[representation][2]
                or curve.result.experiment.unit_for(signal)
            )
            if representation in {"normalized_mg_mg", "normalized_pct"}:
                reference = normalization_reference
        elif signal == "heat_flow":
            representation = options.heat_flow_representation
            unit = (
                HEAT_FLOW_REPRESENTATIONS[representation][2]
                or curve.result.experiment.unit_for(signal)
            )
            if representation in {
                "mw_mg", "zero_mw_mg", "w_g", "zero_w_g",
                "w_mg", "zero_w_mg",
            }:
                reference = normalization_reference
        else:
            display = normalization.get("dtg_display", {})
            unit = display.get("unit") if isinstance(display, dict) else ""
            unit = str(unit or curve.result.experiment.unit_for(signal))
            if options.dtg_representation == "per_mass":
                reference = normalization_reference
        key = unit_key(unit)
        return f"{signal}:{key}:reference={reference}" if key else ""

    @staticmethod
    def _admitted_signal(
        curve: ComparisonCurve,
        options: PlotOptions,
        signal: str,
        expected_scientific_unit: str | None = None,
    ) -> tuple[tuple[np.ndarray, np.ndarray, str, str, str] | None, str]:
        """Résout une série admise au tracé ou son motif d'exclusion."""

        if not curve.for_signal(signal).visible:
            return None, "Courbe décochée."
        x = x_values(curve.result, options.x_axis)
        if x is None:
            detail = (
                temperature_axis_error(curve.result.experiment, options.x_axis)
                if options.x_axis in {"furnace_temperature", "sample_temperature"}
                else ""
            )
            return None, detail or "axe X indisponible."
        column = ComparisonPlot._column_for_curve(curve, options, signal)
        if column is None or column not in curve.result.data:
            return None, "signal ou représentation indisponible."
        y = np.asarray(curve.result.data[column], dtype=float)
        if x.size != y.size:
            return None, "abscisses et signal de tailles différentes."
        if not np.any(np.isfinite(x) & np.isfinite(y)):
            return None, "aucune donnée finie."
        unit = ComparisonPlot._unit_for_curve(curve, options, signal)
        scientific_unit = ComparisonPlot._scientific_unit_for_curve(
            curve, options, signal
        )
        if not scientific_unit:
            return None, "unité scientifique absente."
        if (
            expected_scientific_unit is not None
            and scientific_unit != expected_scientific_unit
        ):
            return None, "unité incompatible avec les autres courbes."
        return (x, y, unit, scientific_unit, column), ""

    @staticmethod
    def _statistics_exclusion_reason(
        statistics: object,
        expected_scientific_unit: str | None = None,
    ) -> str:
        if not statistics.included or not statistics.x.size:
            return "aucune répétition compatible."
        if not statistics.scientific_unit:
            return "unité scientifique absente."
        if (
            expected_scientific_unit is not None
            and statistics.scientific_unit != expected_scientific_unit
        ):
            return "unité incompatible avec les autres groupes."
        return ""

    @staticmethod
    def _label_for_curve(
        curve: ComparisonCurve, options: PlotOptions, signal: str
    ) -> str:
        if curve.stage == "original":
            return {"tg": _t('TG originale'), "dtg": _t('dTG originale'), "heat_flow": _t('Flux de chaleur original')}[signal]
        if curve.stage == "corrected":
            return {"tg": _t('TG corrigée'), "dtg": _t('dTG corrigée'), "heat_flow": _t('Flux de chaleur corrigé')}[signal]
        return _label_for_signal(curve.result, options, signal)

    def draw_statistics(
        self,
        curves: Iterable[ComparisonCurve],
        options: ComparisonOptions,
        statistics: Iterable[object],
        display_mode: str,
    ) -> None:
        """Trace les groupes recalculés, sans inclure les décalages dans les moyennes."""
        if display_mode not in {"mean", "mean_band", "mean_individual", "individual"}:
            raise ValueError("Mode d'affichage statistique inconnu.")
        curves = list(curves)
        self.figure.clear()
        primary = self._create_axes(options.signals)
        self.warnings = []
        self.colors.update(options.colors)
        curves_by_id = {curve.identifier: curve for curve in curves}
        expected_units: dict[str, str] = {}
        expected_scientific_units: dict[str, str] = {}
        displayed_x: list[np.ndarray] = []
        lines = []
        labels = []
        show_mean = display_mode in {"mean", "mean_band", "mean_individual"}
        show_band = display_mode == "mean_band"
        show_individual = display_mode in {"mean_individual", "individual"}
        temperature_axis_available = any(
            x_values(
                curve.result,
                (curve.plot_options or options.plot_options).x_axis,
            ) is not None
            for curve in curves
        )
        for item in statistics:
            group = item.group
            signal = item.signal
            if signal not in self.axes:
                continue
            axis = self.axes[signal]
            signal_options = replace(options, signal=signal)
            reason = self._statistics_exclusion_reason(
                item, expected_scientific_units.get(signal)
            )
            if reason:
                self.warnings.append(
                    f"{group.name} ({_t(SIGNAL_NAMES[signal])}) : {reason}"
                )
                continue
            expected_scientific_units.setdefault(signal, item.scientific_unit)
            expected_units.setdefault(signal, item.unit)
            mean_style = mean_curve_style(signal, options.mean_styles)
            color = mean_style['color']
            offset = mean_style['y_offset']
            if show_individual:
                for identifier in item.included:
                    curve = curves_by_id[identifier].for_signal(signal)
                    resolved = self._curve_data(curve, signal_options)
                    if resolved is None:
                        continue
                    x, y = resolved
                    label_text = curve.legend_name
                    if len(options.signals) > 1:
                        label_text += f" - {_t(SIGNAL_NAMES[signal])}"
                    line = axis.plot(
                        x, y + curve.y_offset, color=curve.signal_settings.get(signal, {}).get("color") or self.colors.setdefault(
                            curve.identifier,
                            COMPARISON_COLORS[len(self.colors) % len(COMPARISON_COLORS)],
                        ), linewidth=curve.line_width, linestyle=mpl_line_style(curve.line_style),
                        marker=curve.marker or None, markevery=curve.markevery,
                        alpha=0.75, label=label_text,
                        gid=f"curve:{curve.identifier}:{signal}",
                    )[0]
                    lines.append(line)
                    labels.append(label_text)
                    displayed_x.append(x)
            if show_mean:
                label_text = mean_style['legend_name'] or group.name
                if len(options.signals) > 1:
                    label_text += f" - {_t(SIGNAL_NAMES[signal])}"
                if options.show_offsets_in_legend and offset:
                    label_text += _t(' (décalage {value:+g})', value=offset)
                line = axis.plot(
                    item.x, item.mean + offset, color=color, linewidth=mean_style['line_width'], label=label_text,
                    linestyle=mpl_line_style(mean_style['line_style']), marker=mean_style['marker'] or None,
                    markevery=mean_style['markevery'],
                    gid=f"mean:{group.identifier}:{signal}",
                )[0]
                lines.append(line)
                labels.append(label_text)
                displayed_x.append(item.x)
            if show_band:
                finite = np.isfinite(item.mean) & np.isfinite(item.std)
                if finite.any():
                    axis.fill_between(
                        item.x, item.mean - item.std + offset, item.mean + item.std + offset,
                        where=finite, color=color, alpha=0.2, linewidth=0,
                        label="_nolegend_",
                    )
                    displayed_x.append(item.x[finite])
        for signal, axis in self.axes.items():
            label = _t(SIGNAL_NAMES[signal])
            unit = expected_units.get(signal, "")
            axis.set_ylabel(label + (f" ({unit})" if unit else ""))
        primary.set_xlabel(
            x_label(
                options.plot_options.x_axis,
                available=(
                    temperature_axis_available
                    or options.plot_options.x_axis not in {
                        "furnace_temperature", "sample_temperature"
                    }
                ),
            )
        )
        primary.set_title(options.title)
        self.set_grid(options.grid)
        if options.x_limits != (None, None):
            self._apply_limits(primary, options.x_limits, horizontal=True)
        elif displayed_x:
            primary.set_xlim(
                min(float(np.min(x)) for x in displayed_x),
                max(float(np.max(x)) for x in displayed_x),
            )
        limits_by_signal = options.y_limits_by_signal or {
            options.signal: options.y_limits
        }
        for signal, limits in limits_by_signal.items():
            if signal in self.axes:
                self._apply_limits(self.axes[signal], limits, horizontal=False)
        if options.align_zeros:
            align_axis_zeros(self.axes.values(), {
                axis: limits_by_signal.get(signal, (None, None)) for signal, axis in self.axes.items()
            })
        if not lines:
            primary.text(0.5, 0.5, "Aucune statistique compatible à afficher", ha="center", va="center", transform=primary.transAxes)
        self._align_references(curves, options)
        apply_scientific_tick_format(primary, "x")
        for axis in self.axes.values():
            apply_scientific_tick_format(axis, "y")
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
            primary, self.axes, options.plot_options, self.warnings, lines, labels
        )
        apply_axis_appearance(primary, self.axes, self.thermal_axis, options.graph_settings, self.warnings)
        draw_graph_legend(
            primary, lines, labels, options.graph_settings, self.warnings
        )

    def draw_zones(self, curves, options: ComparisonOptions, *, show_heat_surfaces: bool = True) -> None:
        """Superpose les zones partagées sur le graphique de comparaison."""
        if self.axis is None:
            return
        x_limits = self.axis.get_xlim()
        y_limits = {signal: axis.get_ylim() for signal, axis in self.axes.items()}
        for zone in options.plot_options.analysis_zones:
            if zone.axis_type != options.plot_options.x_axis:
                continue
            active = zone.identifier == options.plot_options.selected_analysis_zone_id
            color = zone.color or "#6A5ACD"
            self.axis.axvspan(zone.start, zone.end, color=color,
                             alpha=zone.opacity if zone.opacity is not None else 0.20 if active else 0.08)
            for boundary in (zone.start, zone.end):
                self.axis.axvline(boundary, color=color,
                                 linewidth=zone.line_width if zone.line_width is not None else 1,
                                 linestyle="-" if active else ":", label="_nolegend_")
            if not active or not show_heat_surfaces or "heat_flow" not in self.axes:
                continue
            for curve in curves:
                curve = curve.for_signal("heat_flow")
                if not curve.visible:
                    continue
                curve_options = curve.plot_options or options.plot_options
                profile = heat_flow_zone_profile(
                    curve.result,
                    zone,
                    curve_options.heat_flow_representation,
                    signal_stage=curve.stage,
                )
                draw_heat_flow_zone(self.axes["heat_flow"], profile, offset=curve.y_offset,
                                    show_baseline=zone.show_baseline and options.plot_options.show_zone_baselines,
                                    positive_color=zone.positive_area_color or "#0072B2",
                                    negative_color=zone.negative_area_color or "#D55E00",
                                    baseline_color=zone.baseline_color or "#7A3E9D",
                                    show_surfaces=options.plot_options.show_zone_surfaces)
        self.axis.set_xlim(x_limits)
        for signal, limits in y_limits.items():
            self.axes[signal].set_ylim(limits)

    @staticmethod
    def _curve_data(
        curve: ComparisonCurve, options: ComparisonOptions
    ) -> tuple[np.ndarray, np.ndarray] | None:
        resolved = ComparisonPlot._curve_data_with_rows(curve, options)
        return None if resolved is None else resolved[:2]

    @staticmethod
    def _curve_data_with_rows(
        curve: ComparisonCurve,
        options: ComparisonOptions,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int] | None:
        curve_options = curve.plot_options or options.plot_options
        x = x_values(curve.result, curve_options.x_axis)
        column = ComparisonPlot._column_for_curve(curve, curve_options, options.signal)
        if x is None or column not in curve.result.data:
            return None
        y = np.asarray(curve.result.data[column], dtype=float)
        finite = np.isfinite(x) & np.isfinite(y)
        if not finite.any():
            return None
        return x[finite], y[finite], np.flatnonzero(finite), int(x.size)

    @staticmethod
    def automatic_offsets(
        curves: Iterable[ComparisonCurve], options: ComparisonOptions, *, spacing: float | None = None
    ) -> dict[str, float]:
        """Retourne des décalages visuels dans l'ordre de tracé, sans modifier les données."""
        amplitudes: list[float] = []
        visible: list[ComparisonCurve] = []
        values: list[np.ndarray] = []
        if spacing is not None and (not np.isfinite(spacing) or not 0 <= spacing <= 1e12):
            raise ValueError(_t("L'écart d'empilement doit être compris entre 0 et 10¹²."))
        for curve in curves:
            curve = curve.for_signal(options.signal)
            if not curve.visible:
                continue
            data = ComparisonPlot._curve_data(curve, options)
            if data is None:
                continue
            _, finite = data
            visible.append(curve)
            values.append(finite)
            amplitudes.append(float(np.max(finite) - np.min(finite)))
        if not visible:
            return {}
        amplitude = max(amplitudes)
        if np.isclose(amplitude, 0.0):
            scale = max(
                (float(np.max(np.abs(y))) for y in values),
                default=0.0,
            )
            amplitude = scale * 0.1 if scale > 0.0 else 1.0
        spacing = amplitude * 1.1 if spacing is None else spacing
        return {curve.identifier: index * spacing for index, curve in enumerate(visible)}

    @staticmethod
    def _apply_limits(axis: object, limits: tuple[float | None, float | None], *, horizontal: bool) -> None:
        minimum, maximum = limits
        if minimum is not None and maximum is not None and minimum >= maximum:
            raise ValueError(_t('La limite minimale doit être inférieure à la limite maximale.'))
        if minimum is not None or maximum is not None:
            (axis.set_xlim if horizontal else axis.set_ylim)(minimum, maximum)
