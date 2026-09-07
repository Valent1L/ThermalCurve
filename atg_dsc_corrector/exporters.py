"""Exports tabulaires et manifestes JSON traçables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable

import numpy as np
import pandas as pd

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
    json_path: Path


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


def _publish_pair(
    data_temp: Path,
    json_temp: Path,
    data_path: Path,
    json_path: Path,
) -> None:
    pairs = ((data_temp, data_path), (json_temp, json_path))
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        for _, target in pairs:
            if target.exists():
                backup = _temporary_path(target)
                backup.unlink()
                os.replace(target, backup)
                backups[target] = backup
        for temporary, target in pairs:
            os.replace(temporary, target)
            published.append(target)
    except OSError as exc:
        rollback_errors: list[str] = []
        for target in published:
            try:
                target.unlink(missing_ok=True)
            except OSError as rollback_exc:
                rollback_errors.append(f"suppression de {target}: {rollback_exc}")
        for target, backup in backups.items():
            try:
                target.unlink(missing_ok=True)
                os.replace(backup, target)
            except OSError as rollback_exc:
                rollback_errors.append(
                    f"restauration de {target} depuis {backup}: {rollback_exc}"
                )
        detail = (
            " Restauration incomplète : " + " ; ".join(rollback_errors)
            if rollback_errors
            else ""
        )
        raise ExportError(f"Publication incomplète annulée : {exc}.{detail}") from exc
    finally:
        data_temp.unlink(missing_ok=True)
        json_temp.unlink(missing_ok=True)
    for backup in backups.values():
        try:
            backup.unlink(missing_ok=True)
        except OSError as exc:
            # Les deux sorties sont publiées ; seul le nettoyage a échoué.
            logging.getLogger(__name__).warning(
                "Export terminé, sauvegarde temporaire non supprimée : %s (%s)",
                backup,
                exc,
            )


def _write_table_and_json(
    frame: pd.DataFrame,
    data_path: Path,
    json_path: Path,
    json_text: str,
    *,
    kind: str,
    na_rep: str = "",
) -> None:
    data_temp = _temporary_path(data_path)
    try:
        json_temp = _temporary_path(json_path)
    except OSError:
        data_temp.unlink(missing_ok=True)
        raise
    try:
        with data_temp.open(
            "w",
            encoding="utf-8-sig" if kind == "csv" else "utf-8",
            newline="",
        ) as stream:
            frame.to_csv(
                stream,
                index=False,
                sep=";" if kind == "csv" else "\t",
                decimal="," if kind == "csv" else ".",
                na_rep=na_rep,
                lineterminator="\n",
            )
            stream.flush()
            os.fsync(stream.fileno())
        with json_temp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json_text)
            stream.flush()
            os.fsync(stream.fileno())
        _publish_pair(data_temp, json_temp, data_path, json_path)
    except OSError as exc:
        raise ExportError(f"Impossible de préparer l'export : {exc}") from exc
    finally:
        data_temp.unlink(missing_ok=True)
        json_temp.unlink(missing_ok=True)


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
    if axis_type in {"time_s", "time_min"}:
        return {"time_s": "s", "time_min": "min"}[axis_type]
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


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    raise TypeError(f"Type non sérialisable: {type(value).__name__}")


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


def _ordered_export_data(result: CorrectionResult) -> pd.DataFrame:
    columns: list[str] = list(result.experiment.original_columns)
    for column in ("Temps_s", "Dans_zone_commune", *result.corrected_columns):
        if column in result.data and column not in columns:
            columns.append(column)
    return result.data.loc[:, columns].copy()


def export_result(
    result: CorrectionResult,
    destination: str | Path,
    file_format: str,
    *,
    protected_paths: Iterable[str | Path] = (),
    overwrite: bool = False,
) -> ExportedFiles:
    """Exporte un résultat en CSV français ou TSV international et un JSON associé."""

    kind = file_format.lower().lstrip(".")
    if kind not in {"csv", "tsv"}:
        raise ExportError("Le format d'export doit être 'csv' ou 'tsv'.")
    path = Path(destination)
    expected_suffix = f".{kind}"
    if path.suffix.lower() != expected_suffix:
        path = path.with_suffix(expected_suffix)
    json_path = path.with_suffix(".json")
    sources = [result.experiment.source_path]
    if result.blank is not None:
        sources.append(result.blank.source_path)
    _validate_destinations(
        (path, json_path), (*sources, *protected_paths), overwrite=overwrite
    )
    frame = _ordered_export_data(result)
    json_text = json.dumps(
        _metadata_document(result, path),
        ensure_ascii=False,
        indent=2,
        default=_json_value,
        allow_nan=False,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_table_and_json(
        frame, path, json_path, json_text, kind=kind
    )
    return ExportedFiles(path, json_path)


def export_zone_results(
    rows: Iterable[ZoneQuantification],
    destination: str | Path,
    file_format: str,
    *,
    representations: dict[str, str] | None = None,
    protected_paths: Iterable[str | Path] = (),
    overwrite: bool = False,
) -> ExportedFiles:
    """Exporte les quantifications recalculées, une ligne par expérience-zone."""

    kind = file_format.lower().lstrip(".")
    if kind not in {"csv", "tsv"}:
        raise ExportError("Le format d'export doit être 'csv' ou 'tsv'.")
    path = Path(destination)
    if path.suffix.lower() != f".{kind}":
        path = path.with_suffix(f".{kind}")
    json_path = path.with_suffix(".json")
    _validate_destinations(
        (path, json_path), protected_paths, overwrite=overwrite
    )
    zone_rows = list(rows)
    frame = pd.DataFrame(
        [_zone_row(row) for row in zone_rows],
        columns=ZONE_RESULT_COLUMNS,
    )
    json_text = json.dumps(
        _zone_metadata_document(zone_rows, path, representations),
        ensure_ascii=False,
        indent=2,
        default=_json_value,
        allow_nan=False,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_table_and_json(
        frame, path, json_path, json_text, kind=kind, na_rep=""
    )
    return ExportedFiles(path, json_path)


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
    if kind not in {"csv", "tsv"}:
        raise ExportError("Le format d'export doit être 'csv' ou 'tsv'.")
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
        [
            path
            for data_path in destinations
            for path in (data_path, data_path.with_suffix(".json"))
        ],
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
                str(path)
                for output in outputs
                for path in (output.data_path, output.json_path)
            ) or "aucune"
            raise ExportError(
                f"Export du lot interrompu. Sorties déjà produites : {produced}. "
                f"Cause : {exc}"
            ) from exc
    return outputs
