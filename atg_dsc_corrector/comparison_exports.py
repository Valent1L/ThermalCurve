"""Exports reproductibles de la vue de comparaison."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .i18n import tr as _t
from .workbook_export import source_blocks, write_workbook

from . import APP_NAME
from .comparison import ComparisonCurve, ComparisonOptions, ComparisonPlot
from .comparison_statistics import GroupStatistics
from .exporters import (
    ExportError,
    _source_reference,
    _temporary_path,
    _validate_destinations,
)
from .labels import format_unit
from .normalization import HEAT_FLOW_REPRESENTATIONS, TG_REPRESENTATIONS
from .plotting import PlotOptions, X_LABELS, _normalization_parameters
from .projects import application_version


class ComparisonExportError(ValueError):
    """Erreur d'export de comparaison explicite et sans effet de bord."""


def _curve_provenance(curve: ComparisonCurve) -> dict[str, Any]:
    result = curve.result
    return {
        "identifier": curve.identifier,
        "original_name": result.experiment.name,
        "legend_name": curve.legend_name,
        "visible": curve.visible,
        "stage": curve.stage,
        "experiment": _source_reference(result.experiment),
        "blank": None if result.blank is None else _source_reference(result.blank),
        "correction": {
            "method": result.method,
            "corrected_columns": list(result.corrected_columns),
            "parameters": result.parameters,
        },
        "normalization": _normalization_parameters(result),
        "warnings": list(result.warnings),
    }


def safe_filename(value: str, fallback: str = "comparaison") -> str:
    """Produit un nom de fichier portable sans modifier le répertoire choisi."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    return cleaned or fallback


def export_visible_curves(
    curves: Iterable[ComparisonCurve],
    options: ComparisonOptions,
    destination: str | Path,
    file_format: str,
    *,
    display: dict[str, Any] | None = None,
    statistics: Iterable[GroupStatistics] = (),
    statistics_settings: dict[str, Any] | None = None,
    protected_paths: Iterable[str | Path] = (),
    overwrite: bool = False,
) -> Path:
    """Exporte les signaux cochés, avec leurs grilles propres et sans décalage visuel."""
    curves = list(curves)
    statistics = [item for item in statistics if item.signal in options.signals]
    mode = statistics_settings["display_mode"] if statistics_settings else "individual"
    if mode not in {"individual", "mean", "mean_band", "mean_individual"}:
        raise ComparisonExportError("Mode d'affichage statistique inconnu.")
    stats_header, stats_columns, groups = _statistics_columns(
        statistics, options, curves, match_current_plot=True
    )
    included = None
    if statistics_settings:
        included = (
            {
                (identifier, group["signal"])
                for group in groups
                if group["plot_exclusion"] is None
                for identifier in group["included"]
            }
            if mode in {"individual", "mean_individual"}
            else set()
        )
    header, columns, metadata_curves = _visible_columns(curves, options, included)
    if mode != "individual":
        header.extend(stats_header)
        columns.extend(stats_columns)
    else:
        for group in groups:
            group["columns"] = []
    metadata = {
        "kind": "visible_comparison_curves",
        "selection_contract": "only_series_admitted_to_current_plot",
        "signals": list(options.signals),
        "x_axis": options.plot_options.x_axis,
        "display": display or _display_metadata(options),
        "curves": metadata_curves,
        "statistics": statistics_settings,
        "groups": groups,
    }
    return _write_comparison_workbook(
        destination, file_format, header, columns, metadata, curves,
        protected_paths=protected_paths, overwrite=overwrite,
    )


def _visible_columns(
    curves: Iterable[ComparisonCurve], options: ComparisonOptions,
    included: set[tuple[str, str]] | None = None,
) -> tuple[list[str], list[np.ndarray], list[dict[str, Any]]]:
    header: list[str] = []
    columns: list[np.ndarray] = []
    metadata_curves: list[dict[str, Any]] = []
    expected_scientific_units: dict[str, str] = {}
    for index, curve in enumerate(curves, start=1):
        if not curve.visible:
            continue
        curve_options = curve.plot_options or options.plot_options
        warnings = list(curve.result.warnings)
        prefix = f"{curve.legend_name} [{index}]"
        curve_header: list[str] = []
        signals: dict[str, Any] = {}
        excluded_signals: dict[str, str] = {}
        for signal in options.signals:
            if included is not None and (curve.identifier, signal) not in included:
                excluded_signals[signal] = (
                    "Série non retenue par le mode statistique courant."
                )
                continue
            resolved, reason = ComparisonPlot._admitted_signal(
                curve,
                curve_options,
                signal,
                expected_scientific_units.get(signal),
            )
            if resolved is None:
                excluded_signals[signal] = reason
                warnings.append(f"{signal} : {reason}")
                continue
            x, y, _plot_unit, scientific_unit, column = resolved
            expected_scientific_units.setdefault(signal, scientific_unit)
            if not curve_header:
                curve_header.append(f"{prefix} - {_x_header(curve_options.x_axis, curve)}")
                columns.append(x)
            unit = _y_unit(curve, curve_options, signal)
            curve_header.append(f"{prefix} - {_signal_header(signal, unit)}")
            columns.append(y)
            signals[signal] = {
                "column": column, "unit": unit,
                "representation": _representation(options, curve, signal=signal),
            }
        header.extend(curve_header)
        metadata_curves.append({
            **_curve_provenance(curve),
            "signals": signals,
            "excluded_signals": excluded_signals,
            "columns": curve_header,
            "normalization_reference": curve_options.reference_name,
            "status": (
                "Partiellement exportée"
                if signals and excluded_signals
                else "OK"
                if signals
                else "Exclue du tracé"
            ),
            "warnings": warnings,
            "signal_settings": curve.signal_settings,
            "visual_offset": curve.y_offset,
            "style": {
                "line_style": curve.line_style, "line_width": curve.line_width,
                "marker": curve.marker, "markevery": curve.markevery,
            },
        })
    return header, columns, metadata_curves


def export_group_statistics(
    statistics: Iterable[GroupStatistics],
    options: ComparisonOptions,
    destination: str | Path,
    file_format: str,
    *,
    grid_method: str,
    manual_points: int,
    curves: Iterable[ComparisonCurve] = (),
    protected_paths: Iterable[str | Path] = (),
    overwrite: bool = False,
) -> Path:
    """Exporte moyenne, écart-type et effectif des signaux cochés, sans recalcul."""
    curves = list(curves)
    header, columns, groups = _statistics_columns(statistics, options, curves)
    metadata = {
        "kind": "comparison_repeat_statistics",
        "signals": list(options.signals),
        "x_axis": options.plot_options.x_axis,
        "grid_method": grid_method,
        "manual_points": manual_points if grid_method == "manual" else None,
        "curves": [_curve_provenance(curve) for curve in curves],
        "groups": groups,
    }
    return _write_comparison_workbook(
        destination, file_format, header, columns, metadata, curves,
        protected_paths=protected_paths, overwrite=overwrite,
    )


def _statistics_columns(
    statistics: Iterable[GroupStatistics], options: ComparisonOptions,
    curves: Iterable[ComparisonCurve],
    *, match_current_plot: bool = False,
) -> tuple[list[str], list[np.ndarray], list[dict[str, Any]]]:
    header: list[str] = []
    columns: list[np.ndarray] = []
    groups: list[dict[str, Any]] = []
    group_numbers: dict[str, int] = {}
    curves_by_id = {curve.identifier: curve for curve in curves}
    expected_scientific_units: dict[str, str] = {}
    for item in statistics:
        if item.signal not in options.signals:
            continue
        curve = next(
            (curves_by_id[identifier] for identifier in item.included if identifier in curves_by_id),
            None,
        )
        plot_options = (curve.plot_options if curve else None) or options.plot_options
        unit = _y_unit(curve, plot_options, item.signal) if curve else item.unit
        signal_header = _signal_header(item.signal, unit)
        group_number = group_numbers.setdefault(item.group.identifier, len(group_numbers) + 1)
        prefix = f"{item.group.name} [{group_number}]"
        group_header = [
            f"{prefix} - {signal_header} - {_x_header(plot_options.x_axis, curve)}",
            f"{prefix} - {_t('Moyenne')} {signal_header}",
            f"{prefix} - {_t('Écart-type')} {signal_header}",
            f"{prefix} - n {_signal_header(item.signal, '')}",
        ]
        plot_exclusion = (
            ComparisonPlot._statistics_exclusion_reason(
                item, expected_scientific_units.get(item.signal)
            )
            if match_current_plot
            else ""
        )
        status = "OK"
        if plot_exclusion or not item.included or not item.x.size:
            status = (
                plot_exclusion[0].upper() + plot_exclusion[1:]
                if plot_exclusion
                else "Aucune répétition compatible"
            )
            group_header = []
        else:
            if match_current_plot:
                expected_scientific_units.setdefault(
                    item.signal, item.scientific_unit
                )
            if len({array.size for array in (item.x, item.mean, item.std, item.count)}) != 1:
                raise ComparisonExportError("Les tableaux statistiques ont des tailles différentes.")
            header.extend(group_header)
            columns.extend([item.x, item.mean, item.std, item.count])
            if int(np.max(item.count, initial=0)) < 2:
                status = "Dispersion indisponible : moins de deux répétitions"
        groups.append({
            "identifier": item.group.identifier, "name": item.group.name,
            "signal": item.signal, "columns": group_header,
            "representation": _representation(options, curve, signal=item.signal),
            "included": item.included, "excluded": item.excluded,
            "domain": item.domain, "grid_points": int(item.x.size), "unit": unit,
            "plot_exclusion": plot_exclusion or None,
            "status": status,
        })
    return header, columns, groups


def export_figure(
    figure: Any, destination: str | Path, file_format: str, *, dpi: int = 300,
    protected_paths: Iterable[str | Path] = (),
    overwrite: bool = False,
) -> Path:
    """Écrit une figure Matplotlib atomiquement, sans remplacer un fichier existant."""
    kind = _format(file_format)
    if kind not in {"png", "svg", "pdf"}:
        raise ComparisonExportError("Le format du graphique doit être PNG, SVG ou PDF.")
    target = _target(destination, kind, protected_paths, overwrite)
    temporary = _temporary_path(target)
    try:
        figure.savefig(temporary, format=kind, dpi=dpi if kind == "png" else None)
        os.replace(temporary, target)
    except OSError as exc:
        raise ComparisonExportError(f"Impossible d'exporter le graphique : {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _write_comparison_workbook(destination, file_format, header, columns, metadata, curves,
                               *, protected_paths, overwrite):
    if not header:
        raise ComparisonExportError("Aucune donnée compatible avec les signaux cochés à exporter.")
    blocks = []
    offset = 0
    for item in (*metadata.get("curves", ()), *metadata.get("groups", ())):
        names = item.get("columns", [])
        if not names:
            continue
        width = len(names)
        # The title identifies the experiment/group once, above its data block.
        title = item.get("legend_name", item.get("name", ""))
        labels = [re.sub(rf"^{re.escape(title)} \[\d+\] - ", "", name, count=1) for name in names]
        if "signal" in item:
            labels[0] = labels[0].removeprefix(f"{_signal_header(item['signal'], item['unit'])} - ")
        frame = pd.DataFrame({name: pd.Series(values) for name, values in
                              zip(labels, columns[offset:offset + width], strict=True)})
        block_metadata = {**item, "source_path": item.get("experiment", {}).get("source_path", "")}
        blocks.append((item.get("original_name", item.get("name", "")), frame, block_metadata))
        offset += width
    if blocks:
        name, frame, block_metadata = blocks[0]
        blocks[0] = (name, frame, {
            **block_metadata,
            "application": {"name": APP_NAME, "version": application_version()},
            "export": {"created_utc": datetime.now(timezone.utc).isoformat()},
            **metadata,
        })
    sources = [curve.result.experiment for curve in curves if curve.visible]
    blanks = [curve.result.blank for curve in curves if curve.visible]
    try:
        return write_workbook(destination, file_format, [
            ("Données corrigées", blocks),
            ("Données initiales", source_blocks(sources)),
            ("Données du blanc", source_blocks(blanks)),
        ], protected_paths=(*_curve_source_paths(curves), *protected_paths), overwrite=overwrite)
    except ExportError as exc:
        raise ComparisonExportError(str(exc)) from exc


def _target(
    destination: str | Path,
    kind: str,
    protected_paths: Iterable[str | Path],
    overwrite: bool,
) -> Path:
    target = Path(destination).with_suffix(f".{kind}")
    try:
        _validate_destinations((target,), protected_paths, overwrite=overwrite)
    except ExportError as exc:
        raise ComparisonExportError(str(exc)) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _curve_source_paths(curves: Iterable[ComparisonCurve]) -> tuple[Path, ...]:
    return tuple(
        source.source_path
        for curve in curves
        for source in (curve.result.experiment, curve.result.blank)
        if source is not None
    )


def _format(value: str) -> str:
    return value.lower().lstrip(".")


def _representation(
    options: ComparisonOptions, curve: ComparisonCurve | None = None,
    *, signal: str,
) -> str:
    if curve is not None and curve.stage in {"original", "corrected"}:
        return curve.stage
    plot_options = (
        curve.plot_options
        if curve is not None and curve.plot_options is not None
        else options.plot_options
    )
    return str(getattr(plot_options, f"{signal}_representation", ""))


def _x_header(
    axis: str, curve: ComparisonCurve | None = None,
) -> str:
    label = X_LABELS[axis]
    if curve is None or axis in {"time_s", "time_min", "time_h"}:
        return label
    name = label.rsplit(" (", 1)[0]
    unit = curve.result.experiment.unit_for(axis)
    return f"{name} ({unit})" if unit else name


def _signal_header(signal: str, unit: str) -> str:
    name = {"tg": "TG", "dtg": "dTG", "heat_flow": "HeatFlow"}[signal]
    return f"{name} ({unit})" if unit else name


def _y_unit(
    curve: ComparisonCurve,
    plot_options: PlotOptions,
    signal: str,
) -> str:
    result = curve.result
    if curve.stage in {"original", "corrected"}:
        return format_unit(result.experiment.unit_for(signal)).plain_text
    if signal == "tg":
        unit = TG_REPRESENTATIONS[plot_options.tg_representation][2]
        reference = plot_options.reference_name if plot_options.tg_representation == "normalized_mg_mg" else ""
        return format_unit(unit or result.experiment.unit_for("tg"), reference).plain_text
    if signal == "heat_flow":
        unit = HEAT_FLOW_REPRESENTATIONS[plot_options.heat_flow_representation][2]
        value = unit or result.experiment.unit_for("heat_flow")
        if plot_options.heat_flow_representation in {"mw_mg", "zero_mw_mg", "w_g", "zero_w_g", "w_mg", "zero_w_mg"}:
            return format_unit(value, plot_options.reference_name).plain_text
        return format_unit(value).plain_text
    display = _normalization_parameters(result).get("dtg_display", {})
    unit = display.get("unit") if isinstance(display, dict) else None
    value = str(unit or result.experiment.unit_for("dtg"))
    return format_unit(value, plot_options.reference_name if plot_options.dtg_representation == "per_mass" else "").plain_text


def _display_metadata(options: ComparisonOptions) -> dict[str, Any]:
    return {
        "title": options.title, "domain_mode": options.domain_mode,
        "x_limits": options.x_limits, "y_limits": options.y_limits, "grid": options.grid,
    }
