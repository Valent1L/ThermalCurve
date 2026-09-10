"""Exports Excel traçables / Traceable Excel exports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable

import pandas as pd

from .i18n import tr as _t
from . import APP_NAME
from .models import CorrectionResult, ExperimentData, is_celsius_unit, same_path as _same_path
from .labels import format_unit
from .projects import application_version
from .zone_quantification import ZoneQuantification


class ExportError(ValueError):
    """Erreur de destination ou de format d'export."""


@dataclass(frozen=True, slots=True)
class ExportedFiles:
    data_path: Path


def _validate_destinations(
    destinations: Iterable[str | Path],
    protected_paths: Iterable[str | Path] = (),
    *,
    overwrite: bool,
) -> tuple[Path, ...]:
    targets = tuple(Path(path) for path in destinations)
    protected_paths = tuple(protected_paths)
    for index, target in enumerate(targets):
        if any(_same_path(target, other) for other in targets[index + 1 :]):
            raise ExportError(f"Deux sorties visent le même fichier : {target}")
        for protected in protected_paths:
            if _same_path(target, protected):
                raise ExportError(f"La destination est une source protégée : {target}")
    if not overwrite:
        existing = next((target for target in targets if target.exists()), None)
        if existing is not None:
            raise FileExistsError(f"Le fichier existe déjà : {existing}")
    return targets


def _temporary_path(target: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}.", suffix=target.suffix, dir=target.parent, delete=False
    )
    handle.close()
    return Path(handle.name)


# Ces identifiants constituent le contrat stable des exports de zones.
ZONE_RESULT_COLUMNS = (
    "experiment_name", "experiment_key", "zone_id", "zone_name", "axis_type",
    "axis_unit", "zone_start", "zone_end", "valid_point_count",
    "tg_delta_mg", "tg_delta_pct_m0", "tg_delta_pct_reference",
    "tg_remaining_mass_end_mg", "tg_residual_mass_end_pct",
    "dtg_minimum", "dtg_minimum_position", "dtg_maximum",
    "dtg_maximum_position", "dtg_main_peak", "dtg_main_peak_position",
    "dtg_unit", "baseline_method", "heat_flow_minimum",
    "heat_flow_minimum_position", "heat_flow_maximum",
    "heat_flow_maximum_position", "heat_flow_main_peak",
    "heat_flow_main_peak_position", "heat_flow_unit", "heat_flow_area",
    "heat_flow_area_unit", "initial_mass_mg", "reference_mass_mg",
    "reference_name", "status", "warnings",
    "heat_flow_positive_area", "heat_flow_negative_area",
)

def _plain_unit(value: str, reference_name: str = "") -> str:
    """Convertit une unité interne/MathText en texte ASCII destiné aux fichiers."""

    unit = value.strip()
    if "/" in unit:
        unit = format_unit(unit, reference_name).plain_text
    return (
        unit.replace("·", ".").replace("⋅", ".")
        .replace("⁻¹", "^-1").replace("⁻²", "^-2")
        .replace("²", "2").replace("³", "3")
    )


def _axis_unit_for_export(axis_type: str, value: str) -> str:
    if axis_type in {"time_s", "time_min", "time_h"}:
        return {"time_s": "s", "time_min": "min", "time_h": "h"}[axis_type]
    return "degC" if is_celsius_unit(value) else _plain_unit(value)


def _zone_row(row: ZoneQuantification) -> dict[str, Any]:
    return {
        "experiment_name": row.experiment_name,
        "experiment_key": row.experiment_key,
        "zone_id": row.zone_id,
        "zone_name": row.zone_name,
        "axis_type": row.axis_type,
        "axis_unit": _axis_unit_for_export(row.axis_type, row.axis_unit),
        "zone_start": row.start,
        "zone_end": row.end,
        "valid_point_count": row.valid_point_count,
        "tg_delta_mg": row.delta_zone_mg,
        "tg_delta_pct_m0": row.delta_zone_pct_m0,
        "tg_delta_pct_reference": row.delta_zone_pct_reference,
        "tg_remaining_mass_end_mg": row.remaining_mass_end_mg,
        "tg_residual_mass_end_pct": row.residual_mass_end_pct,
        "dtg_minimum": row.dtg_minimum,
        "dtg_minimum_position": row.dtg_minimum_position,
        "dtg_maximum": row.dtg_maximum,
        "dtg_maximum_position": row.dtg_maximum_position,
        "dtg_main_peak": row.dtg_main_peak,
        "dtg_main_peak_position": row.dtg_main_peak_position,
        "dtg_unit": _plain_unit(row.dtg_unit, row.reference_name),
        "baseline_method": row.baseline_method,
        "heat_flow_minimum": row.heat_flow_minimum,
        "heat_flow_minimum_position": row.heat_flow_minimum_position,
        "heat_flow_maximum": row.heat_flow_maximum,
        "heat_flow_maximum_position": row.heat_flow_maximum_position,
        "heat_flow_main_peak": row.heat_flow_main_peak,
        "heat_flow_main_peak_position": row.heat_flow_main_peak_position,
        "heat_flow_unit": _plain_unit(row.heat_flow_unit, row.reference_name),
        "heat_flow_area": row.heat_flow_area,
        "heat_flow_positive_area": row.heat_flow_positive_area,
        "heat_flow_negative_area": row.heat_flow_negative_area,
        "heat_flow_area_unit": _plain_unit(row.heat_flow_area_unit, row.reference_name),
        "initial_mass_mg": row.initial_mass_mg,
        "reference_mass_mg": row.reference_mass_mg,
        "reference_name": row.reference_name,
        "status": row.status,
        "warnings": " | ".join(row.warnings),
    }


def _zone_metadata_document(
    rows: list[ZoneQuantification],
    data_path: Path,
    representations: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "application": {
            "name": APP_NAME,
            "version": application_version(),
            "schema_version": 1,
        },
        "export": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "data_file": data_path.name,
            "row_definition": "Une ligne par couple experience-zone.",
        },
        "columns": list(ZONE_RESULT_COLUMNS),
        "representations": representations or {},
        "results": {
            "tg_delta_mg": {"definition": "m_fin - m_debut", "unit": "mg"},
            "tg_delta_pct_m0": {"definition": "100 * delta_m / m0", "unit": "%"},
            "tg_delta_pct_reference": {"definition": "100 * delta_m / m_ref", "unit": "%"},
            "tg_remaining_mass_end_mg": {"definition": "m0 + TG_fin - TG0", "unit": "mg"},
            "tg_residual_mass_end_pct": {"definition": "100 * m_fin / m0", "unit": "%"},
            "dtg_minimum": {"definition": "minimum dTG dans la zone", "unit_column": "dtg_unit"},
            "dtg_maximum": {"definition": "maximum dTG dans la zone", "unit_column": "dtg_unit"},
            "dtg_main_peak": {"definition": "extremum de valeur absolue de dTG", "unit_column": "dtg_unit"},
            "heat_flow_minimum": {"definition": "minimum HeatFlow apres ligne de base", "unit_column": "heat_flow_unit"},
            "heat_flow_maximum": {"definition": "maximum HeatFlow apres ligne de base", "unit_column": "heat_flow_unit"},
            "heat_flow_main_peak": {"definition": "extremum de valeur absolue apres ligne de base", "unit_column": "heat_flow_unit"},
            "heat_flow_area": {"definition": "integrale trapezoidale signee sur Temps_s apres ligne de base", "unit_column": "heat_flow_area_unit"},
            "heat_flow_positive_area": {"definition": "integrale au-dessus de la ligne de base sur Temps_s", "unit_column": "heat_flow_area_unit"},
            "heat_flow_negative_area": {"definition": "integrale signee au-dessous de la ligne de base sur Temps_s", "unit_column": "heat_flow_area_unit"},
        },
        "rows": [{
            "experiment_key": row.experiment_key,
            "zone_id": row.zone_id,
            "baseline_method": row.baseline_method,
            "baseline": {
                "method": row.baseline_method,
                "value": row.baseline_value,
                "value_rule": (
                    "explicit"
                    if row.baseline_method == "constant" and row.baseline_value is not None
                    else "signal_at_zone_start"
                    if row.baseline_method == "constant"
                    else "signal_at_zone_bounds"
                    if row.baseline_method == "linear"
                    else "zero"
                ),
                "representation": row.baseline_representation,
                "unit": (
                    None
                    if row.baseline_unit is None
                    else _plain_unit(row.baseline_unit, row.reference_name)
                ),
            },
            "initial_mass_mg": row.initial_mass_mg,
            "reference_mass_mg": row.reference_mass_mg,
            "reference_name": row.reference_name,
            "status": row.status,
            "warnings": list(row.warnings),
        } for row in rows],
    }


def _source_reference(source: ExperimentData) -> dict[str, Any]:
    fingerprint = source.source_fingerprint
    return {
        "source_path": str(source.source_path),
        "format": source.file_format,
        "sheet": source.sheet_name,
        "source_fingerprint": None if fingerprint is None else {
            "size": fingerprint.size,
            "modified_at": fingerprint.modified_at,
            "sha256": fingerprint.sha256,
        },
    }


def _metadata_document(result: CorrectionResult, data_path: Path) -> dict[str, Any]:
    experiment = result.experiment
    blank = result.blank
    formula = None if (
        blank is None or "TG_corrigee" not in result.corrected_columns
    ) else (
        "TG_experience[i] - TG_blanc[i]"
        if result.method == "direct"
        else "TG_experience[i] - (TG_blanc[i] - TG_blanc_initial)"
    )
    return {
        "application": {
            "name": APP_NAME,
            "version": application_version(),
            "schema_version": 1,
        },
        "export": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "data_file": data_path.name,
        },
        "experiment": {
            **_source_reference(experiment),
            "available_sheets": list(experiment.available_sheets),
            "description": experiment.description,
            "metadata": experiment.metadata,
            "raw_metadata_rows": experiment.raw_metadata_rows,
            "original_columns": list(experiment.original_columns),
            "column_mapping": experiment.mapping.as_dict(),
            "units": experiment.units,
            "original_time_unit": experiment.time_unit,
            "normalized_time_column": "Temps_s",
        },
        "blank": None if blank is None else {
            **_source_reference(blank),
            "description": blank.description,
            "column_mapping": blank.mapping.as_dict(),
            "units": blank.units,
        },
        "correction": {
            "method": result.method,
            "tg_formula": formula,
            "dtg_formula": (
                "dTG_experience[i] - dTG_blanc[i]"
                if blank is not None and "dTG_corrigee" in result.corrected_columns else None
            ),
            "heat_flow_formula": (
                "HeatFlow_experience[i] - HeatFlow_blanc[i]"
                if blank is not None and "HeatFlow_corrige" in result.corrected_columns else None
            ),
            "common_time_s": list(result.common_time_s),
            "corrected_columns": list(result.corrected_columns),
            "parameters": {
                name: value
                for name, value in result.parameters.items()
                if "interpol" not in name.lower()
            },
        },
        "normalization": result.parameters.get("normalization", {}),
        "warnings": result.warnings,
    }


def export_result(
    result: CorrectionResult, destination: str | Path, file_format: str,
    *, protected_paths: Iterable[str | Path] = (), overwrite: bool = False,
) -> ExportedFiles:
    """Exporte les résultats, les mesures initiales et le blanc dans trois feuilles."""
    from .normalization import resolve_working_signal
    from .workbook_export import source_blocks, write_workbook

    columns = ["Temps_s"]
    units = {**result.experiment.units, "Temps_s": "s"}
    for role in ("furnace_temperature", "sample_temperature"):
        column = getattr(result.experiment.mapping, role)
        if column and column in result.data and column not in columns:
            columns.append(column)
    for signal in ("tg", "dtg", "heat_flow"):
        column, _state = resolve_working_signal(result, signal)
        if column and column not in columns:
            columns.append(column)
            units[column] = result.experiment.unit_for(signal)
    columns.extend(column for column in result.corrected_columns
                   if column != "Dans_zone_commune" and column not in columns)
    units.update(result.parameters.get("normalization", {}).get("derived_units_text", {}))
    frame = result.data.loc[:, columns].copy()
    sources = [source.source_path for source in (result.experiment, result.blank) if source is not None]
    path = write_workbook(destination, file_format, [
        ("Données corrigées", [(result.experiment.name, frame, {
            **_metadata_document(result, Path(destination).with_suffix(".xlsx")), "units": units,
        })]),
        ("Données initiales", source_blocks([result.experiment])),
        ("Données du blanc", source_blocks([result.blank])),
    ], protected_paths=(*sources, *protected_paths), overwrite=overwrite)
    return ExportedFiles(path)


def export_zone_results(
    rows: Iterable[ZoneQuantification], destination: str | Path, file_format: str,
    *, representations: dict[str, str] | None = None,
    protected_paths: Iterable[str | Path] = (), overwrite: bool = False,
) -> ExportedFiles:
    """Exporte les quantifications recalculées, une ligne par expérience-zone."""
    from .workbook_export import write_workbook

    rows = list(rows)
    frame = pd.DataFrame([_zone_row(row) for row in rows], columns=ZONE_RESULT_COLUMNS)
    path = write_workbook(destination, file_format, [
        ("Zones", [("Zones", frame, _zone_metadata_document(rows, Path(destination), representations))]),
    ], protected_paths=protected_paths, overwrite=overwrite)
    return ExportedFiles(path)


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ_-]+", "_", value).strip("._")
    return stem or "experience"


def export_batch(
    results: Iterable[CorrectionResult],
    directory: str | Path,
    file_format: str,
    *,
    protected_paths: Iterable[str | Path] = (),
    overwrite: bool = False,
) -> list[ExportedFiles]:
    """Exporte séparément chaque expérience dans un même dossier."""

    kind = file_format.lower().lstrip(".")
    if kind != "xlsx":
        raise ExportError(_t("Le format d'export doit être XLSX."))
    folder = Path(directory)
    results = list(results)
    protected_paths = tuple(protected_paths)
    destinations: list[Path] = []
    used: dict[str, int] = {}
    for result in results:
        base = _safe_stem(result.experiment.source_path.stem) + "_corrige"
        occurrence = used.get(base, 0)
        used[base] = occurrence + 1
        stem = base if occurrence == 0 else f"{base}_{occurrence + 1}"
        destinations.append(folder / f"{stem}.{kind}")
    sources = [
        source.source_path
        for result in results
        for source in (result.experiment, result.blank)
        if source is not None
    ]
    _validate_destinations(
        destinations,
        (*sources, *protected_paths),
        overwrite=overwrite,
    )
    outputs: list[ExportedFiles] = []
    for result, destination in zip(results, destinations, strict=True):
        try:
            outputs.append(
                export_result(
                    result,
                    destination,
                    kind,
                    protected_paths=(*sources, *protected_paths),
                    overwrite=overwrite,
                )
            )
        except Exception as exc:
            produced = ", ".join(
                str(output.data_path) for output in outputs
            ) or "aucune"
            raise ExportError(
                f"Export du lot interrompu. Sorties déjà produites : {produced}. "
                f"Cause : {exc}"
            ) from exc
    return outputs
