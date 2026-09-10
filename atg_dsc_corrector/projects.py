"""Modèle persistant des projets reproductibles ATG-DSC."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Literal, Mapping

from . import __version__
from .analysis_zones import AnalysisZone
from .curve_styles import LINE_STYLES, MARKERS
from .models import (
    CANONICAL_FIELDS,
    ExperimentData,
    capture_source_fingerprint,
    sha256_file,
    same_path,
)
from .i18n import tr
from .quality_control import QCThresholds
from .normalization import (
    HEAT_FLOW_REPRESENTATIONS,
    REFERENCE_AXES,
    REFERENCE_MODES,
    TG_REPRESENTATIONS,
    validate_dtg_smoothing_points,
)
from .readers import load_experiment
from .input_safety import (
    DataReadError, MAX_PROJECT_BYTES, check_input_size, read_limited_bytes,
    require_automatic_local_path,
)
from .thermal_program import validate_thermal_program


SCHEMA_VERSION = 1
STOICHIOMETRY_VERSION = 1
SUPPORTED_CORRECTION_AXES = {
    "time_s",
    "furnace_temperature",
    "sample_temperature",
}
SUPPORTED_DISPLAY_AXES = {
    "time_s",
    "time_min", "time_h",
    "furnace_temperature",
    "sample_temperature",
}
SUPPORTED_SIGNALS = {"tg", "dtg", "heat_flow"}
GRAPH_AXES = ("x", "tg", "dtg", "heat_flow")
GRAPH_SCALES = {"linear", "log"}
GRAPH_TICK_FORMATS = {"auto", "fixed", "scientific"}
GRAPH_GRID_AXES = {"x", "y", "both"}
GRAPH_LEGEND_POSITIONS = {
    "best",
    "upper left",
    "upper right",
    "lower left",
    "lower right",
    "upper center", "lower center", "center left", "center right", "center",
    "outside left", "outside top", "outside bottom", "manual",
    "outside",
}
GRAPH_FONT_TARGETS = {"title", "axes", "ticks", "legend", "annotations"}
GRAPH_ANNOTATION_COORDINATES = {"data", "axes_fraction"}
GRAPH_ANNOTATION_ALIGNMENTS = {"left", "center", "right"}
GRAPH_ARROW_STYLES = {"", "->", "-|>"}
GRAPH_TEMPLATE_VERSION = 1


class ProjectError(ValueError):
    """Erreur lisible liée à un fichier projet."""


class ProjectValidationError(ProjectError):
    """Le JSON ne respecte pas le schéma attendu."""


class ProjectVersionError(ProjectValidationError):
    """La version de schéma ne peut pas être ouverte."""


class ProjectOpenCancelled(ProjectError):
    """L'utilisateur a annulé la résolution d'une source."""


class SourceMissingError(ProjectError):
    """Une source référencée par le projet est introuvable."""

    def __init__(self, source: SourceFileRecord) -> None:
        self.source = source
        super().__init__(
            f"Fichier source introuvable : {source.name} "
            f"(ancien chemin : {source.absolute_path})"
        )


class SourceHashMismatchError(ProjectError):
    """Une source existe mais ne correspond plus à son empreinte enregistrée."""

    def __init__(self, source: SourceFileRecord, path: Path) -> None:
        self.source = source
        self.path = path
        super().__init__(f"Le fichier source a été modifié : {source.name} ({path})")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def application_version() -> str:
    return __version__


def _relative_source_path(source: Path, project_path: Path) -> str | None:
    try:
        return str(source.resolve().relative_to(project_path.resolve().parent))
    except ValueError:
        return None


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ProjectValidationError(f"Le champ '{field_name}' doit être un objet JSON.")
    return value


def _require_string(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ProjectValidationError(f"Le champ '{field_name}' doit être une chaîne non vide.")
    return value


def _require_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProjectValidationError(f"Le champ '{field_name}' doit être une liste de chaînes.")
    return list(value)


def _validate_timestamp(value: Any, field_name: str) -> str:
    text = _require_string(value, field_name)
    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProjectValidationError(
            f"Le champ '{field_name}' doit contenir une date ISO 8601."
        ) from exc
    return text


@dataclass(slots=True)
class ProcessingEvent:
    timestamp: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {"timestamp": self.timestamp, "description": self.description}

    @classmethod
    def create(cls, description: str) -> ProcessingEvent:
        return cls(utc_now(), description)

    @classmethod
    def from_dict(cls, value: Any, field_name: str = "processing_history") -> ProcessingEvent:
        data = _require_mapping(value, field_name)
        return cls(
            _validate_timestamp(data.get("timestamp"), f"{field_name}.timestamp"),
            _require_string(data.get("description"), f"{field_name}.description"),
        )


@dataclass(slots=True)
class SourceFileRecord:
    name: str
    relative_path: str | None
    absolute_path: str
    size: int
    modified_at: str
    sha256: str
    detected_format: str
    header_line: int | None
    sheet_name: str | None
    column_mapping: dict[str, str | None]
    original_columns: list[str]
    original_units: dict[str, str]
    time_unit: str
    description: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_experiment(
        cls,
        experiment: ExperimentData,
        project_path: str | Path,
        *,
        source_path: str | Path | None = None,
    ) -> SourceFileRecord:
        source = Path(source_path or experiment.source_path).resolve()
        fingerprint = experiment.source_fingerprint
        if fingerprint is None:
            fingerprint = capture_source_fingerprint(source)
        return cls(
            name=source.name,
            relative_path=_relative_source_path(source, Path(project_path)),
            absolute_path=str(source),
            size=fingerprint.size,
            modified_at=fingerprint.modified_at,
            sha256=fingerprint.sha256,
            detected_format=experiment.file_format,
            header_line=experiment.metadata.get("header_line"),
            sheet_name=experiment.sheet_name,
            column_mapping=experiment.mapping.as_dict(),
            original_columns=list(experiment.original_columns),
            original_units=dict(experiment.units),
            time_unit=experiment.time_unit,
            description=experiment.description,
            warnings=list(experiment.warnings),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "paths": {
                "relative": self.relative_path,
                "absolute": self.absolute_path,
            },
            "fingerprint": {
                "size": self.size,
                "modified_at": self.modified_at,
                "sha256": self.sha256,
            },
            "detected_format": self.detected_format,
            "header_line": self.header_line,
            "sheet_name": self.sheet_name,
            "column_mapping": self.column_mapping,
            "original_columns": self.original_columns,
            "original_units": self.original_units,
            "time_unit": self.time_unit,
            "description": self.description,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, value: Any, field_name: str) -> SourceFileRecord:
        data = _require_mapping(value, field_name)
        paths = _require_mapping(data.get("paths"), f"{field_name}.paths")
        fingerprint = _require_mapping(
            data.get("fingerprint"), f"{field_name}.fingerprint"
        )

        relative = paths.get("relative")
        if relative is not None:
            relative = _require_string(relative, f"{field_name}.paths.relative")
            if Path(relative).is_absolute():
                raise ProjectValidationError(
                    f"Le chemin relatif de '{field_name}' ne doit pas être absolu."
                )
        absolute = _require_string(paths.get("absolute"), f"{field_name}.paths.absolute")
        if not Path(absolute).is_absolute():
            raise ProjectValidationError(
                f"Le chemin de secours de '{field_name}' doit être absolu."
            )

        size = fingerprint.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ProjectValidationError(
                f"Le champ '{field_name}.fingerprint.size' doit être un entier positif."
            )
        digest = _require_string(
            fingerprint.get("sha256"), f"{field_name}.fingerprint.sha256"
        ).lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ProjectValidationError(
                f"L'empreinte SHA-256 de '{field_name}' est invalide."
            )

        header_line = data.get("header_line")
        if header_line is not None and (
            not isinstance(header_line, int)
            or isinstance(header_line, bool)
            or header_line < 1
        ):
            raise ProjectValidationError(
                f"Le champ '{field_name}.header_line' doit être nul ou un entier positif."
            )
        sheet_name = data.get("sheet_name")
        if sheet_name is not None and not isinstance(sheet_name, str):
            raise ProjectValidationError(
                f"Le champ '{field_name}.sheet_name' doit être nul ou une chaîne."
            )

        mapping_data = _require_mapping(
            data.get("column_mapping"), f"{field_name}.column_mapping"
        )
        mapping: dict[str, str | None] = {}
        for role in CANONICAL_FIELDS:
            item = mapping_data.get(role)
            if item is not None and not isinstance(item, str):
                raise ProjectValidationError(
                    f"L'association '{field_name}.column_mapping.{role}' est invalide."
                )
            mapping[role] = item

        units_data = _require_mapping(
            data.get("original_units"), f"{field_name}.original_units"
        )
        if not all(isinstance(key, str) and isinstance(item, str) for key, item in units_data.items()):
            raise ProjectValidationError(
                f"Le champ '{field_name}.original_units' doit associer des chaînes."
            )
        time_unit = _require_string(data.get("time_unit"), f"{field_name}.time_unit")
        if time_unit not in {"s", "min"}:
            raise ProjectValidationError(
                f"L'unité de temps de '{field_name}' doit être 's' ou 'min'."
            )

        return cls(
            name=_require_string(data.get("name"), f"{field_name}.name"),
            relative_path=relative,
            absolute_path=absolute,
            size=size,
            modified_at=_validate_timestamp(
                fingerprint.get("modified_at"),
                f"{field_name}.fingerprint.modified_at",
            ),
            sha256=digest,
            detected_format=_require_string(
                data.get("detected_format"), f"{field_name}.detected_format"
            ),
            header_line=header_line,
            sheet_name=sheet_name,
            column_mapping=mapping,
            original_columns=_require_string_list(
                data.get("original_columns"), f"{field_name}.original_columns"
            ),
            original_units=dict(units_data),
            time_unit=time_unit,
            description=_require_string(
                data.get("description", ""),
                f"{field_name}.description",
                allow_empty=True,
            ),
            warnings=_require_string_list(
                data.get("warnings", []), f"{field_name}.warnings"
            ),
        )


def default_display_settings() -> dict[str, Any]:
    return {
        "x_axis": "time_s",
        "visible_signals": ["tg", "heat_flow"],
        "limits": {
            "x": [None, None],
            "tg": [None, None],
            "dtg": [None, None],
            "heat_flow": [None, None],
        },
        "align_zeros": False,
        "alignment_mode": "none",
        "analysis_zone_selected_id": None,
        "show_zone_surfaces": True,
        "show_zone_baselines": True,
        "show_subtraction": True,
        "graph": default_graph_settings(),
    }


def default_legend_style() -> dict[str, Any]:
    return {
        "frame": "rounded", "fill_color": "#FFFFFF", "fill_alpha": 0.8,
        "border_color": "#CCCCCC", "border_width": 0.8,
        "margins": {side: 40.0 for side in ("left", "right", "top", "bottom")},
        "wrap": False, "wrap_width": 40,
        "unit": "axes_percent", "anchor": "upper right", "anchor_frame": True,
        "x": 99.0, "y": 99.0, "lock_x": False, "lock_y": False,
        "text_color": "#000000", "rotation": 0.0, "line_spacing": None,
        "tab_width": 8, "white_out": False, "align_columns": True, "columns": 1,
        "alignment": "left", "verbatim": False, "underline": False, "entries": {},
    }


def _validate_legend_style(value: Any) -> dict[str, Any]:
    defaults = default_legend_style()
    data = _require_mapping(value, "legend_style")
    checked = dict(defaults)
    for key, choices in {
        "frame": {"none", "box", "rounded"}, "unit": {"axes_percent", "figure_percent"},
        "anchor": GRAPH_LEGEND_POSITIONS - {"best", "outside", "outside left", "outside top", "outside bottom", "manual"},
        "alignment": {"left", "center", "right"},
    }.items():
        item = _require_string(data.get(key, defaults[key]), f"legend_style.{key}")
        if item not in choices:
            raise ProjectValidationError("Un réglage de légende est invalide.")
        checked[key] = item
    for key in ("wrap", "anchor_frame", "lock_x", "lock_y", "white_out", "align_columns", "verbatim", "underline"):
        item = data.get(key, defaults[key])
        if not isinstance(item, bool):
            raise ProjectValidationError("Un réglage de légende est invalide.")
        checked[key] = item
    for key, low, high in (("fill_alpha", 0, 1), ("border_width", 0, 20), ("x", -1000, 1000),
                           ("y", -1000, 1000), ("rotation", -360, 360), ("line_spacing", 25, 500),
                           ("wrap_width", 5, 500), ("tab_width", 1, 32), ("columns", 1, 20)):
        item = data.get(key, defaults[key])
        if key == "line_spacing" and item is None:
            checked[key] = None
            continue
        if isinstance(item, bool) or not isinstance(item, (float, int)) or not math.isfinite(item) or not low <= item <= high:
            raise ProjectValidationError("Un réglage de légende est invalide.")
        if key in {"wrap_width", "tab_width", "columns"}:
            if int(item) != item:
                raise ProjectValidationError("Un réglage de légende est invalide.")
            item = int(item)
        checked[key] = item
    for key in ("fill_color", "border_color", "text_color"):
        item = data.get(key, defaults[key])
        checked[key] = "" if key == "fill_color" and item == "" else _validate_graph_color(item, f"legend_style.{key}")
    margins = _require_mapping(data.get("margins", defaults["margins"]), "legend_style.margins")
    checked["margins"] = {}
    for side in defaults["margins"]:
        item = _optional_finite_number(margins.get(side, 40.0), f"legend_style.margins.{side}")
        if item is None or not 0 <= item <= 500:
            raise ProjectValidationError("Un réglage de légende est invalide.")
        checked["margins"][side] = item
    entries = _require_mapping(data.get("entries", {}), "legend_style.entries")
    checked["entries"] = {_require_string(key, "legend_style.entry"): _require_string(text, "legend_style.text", allow_empty=True)
                          for key, text in entries.items()}
    return checked


def default_axis_appearance(role: str) -> dict[str, Any]:
    return {
        "visible": True, "line_visible": True, "color": None, "width": 0.8,
        "position": "auto", "arrow": "none", "labels_visible": role != "x_top",
        "major": {"visible": role != "x_top", "direction": "out", "length": None, "width": None, "color": None},
        "minor": {"visible": role != "x_top", "direction": "out", "length": None, "width": None, "color": None},
    }


def default_graph_settings(
    *, title: str = "", grid_major: bool = True
) -> dict[str, Any]:
    return {
        "title": title,
        "axis_labels": {axis: "" for axis in GRAPH_AXES},
        "axis_scales": {axis: "linear" for axis in GRAPH_AXES},
        "major_tick_steps": {axis: None for axis in GRAPH_AXES},
        "minor_tick_subdivisions": {axis: 0 for axis in GRAPH_AXES},
        "tick_formats": {axis: "auto" for axis in GRAPH_AXES},
        "tick_decimals": {axis: 2 for axis in GRAPH_AXES},
        "x_tick_rotation": 0,
        "grid_major": grid_major,
        "grid_minor": False,
        "grid_axis": "both",
        "grid_styles": {
            "major": {"color": None, "line_style": "-", "line_width": 0.7},
            "minor": {"color": None, "line_style": ":", "line_width": 0.5},
        },
        "axis_appearance": {role: default_axis_appearance(role) for role in (*GRAPH_AXES, "x_top", "thermal_program")},
        "layout_margins": None,
        "legend_visible": True,
        "legend_position": "best",
        "legend_style": default_legend_style(),
        "curve_styles": {},
        "reference_lines": [],
        "annotations": [],
        "axis_spacing": {
            "tg_right_position": 1.0,
            "dtg_right_position": 1.12,
            "label_pads": {axis: 4.0 for axis in GRAPH_AXES},
            "tick_pads": {axis: 3.5 for axis in GRAPH_AXES},
        },
        "fonts": {"general": {}, "overrides": {}},
    }


def default_comparison_settings() -> dict[str, Any]:
    return {
        "entries": {},
        "mean_styles": {},
        "stacking": {"signal": "tg", "spacing": None},
        "signal": "tg",
        "signals": ["tg"],
        "representations": {
            "tg": "delta_m_mg",
            "dtg": "raw",
            "heat_flow": "raw",
        },
        "dtg_unit_mode": "source",
        "x_axis": "time_s",
        "domain_mode": "union",
        "x_limits": [None, None],
        "y_limits": [None, None],
        "limits": {
            "x": [None, None],
            "tg": [None, None],
            "dtg": [None, None],
            "heat_flow": [None, None],
        },
        "title": "Comparaison des expériences",
        "grid": True,
        "align_zeros": False,
        "show_offsets_in_legend": False,
        "statistics": {
            "enabled": False,
            "groups": [],
            "display_mode": "mean_band",
            "grid_method": "auto",
            "manual_points": 200,
            "show_mean": True,
            "show_band": True,
            "show_individual": False,
        },
        "colors": {},
        "graph": default_graph_settings(title="Comparaison des expériences"),
    }


def default_normalization_settings() -> dict[str, Any]:
    return {
        "tg_reference_mode": "first_valid",
        "heat_flow_reference_mode": "first_valid",
        "reference_mode": "first_valid",
        "reference_axis": "time_s",
        "range_start": None,
        "range_end": None,
        "tg_representation": "delta_m_mg",
        "dtg_unit_mode": "source",
        "dtg_representation": "raw",
        "heat_flow_representation": "raw",
        "normalization_enabled": False,
        "reference_mass_mg": None,
        "reference_name": "",
        "use_initial_mass_as_reference": False,
        "calculate_dtg_if_missing": False,
        "dtg_smoothing_points": 1,
        "experiments": [],
    }


def default_quality_control_settings() -> dict[str, float | int]:
    return QCThresholds().to_dict()


def _optional_finite_number(
    value: Any,
    field_name: str,
    *,
    positive: bool = False,
) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProjectValidationError(f"Le champ '{field_name}' doit être numérique ou nul.")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        qualifier = " fini et strictement positif" if positive else " fini"
        raise ProjectValidationError(f"Le champ '{field_name}' doit être{qualifier}.")
    return number


def _validate_normalization(value: Any) -> dict[str, Any]:
    data = _require_mapping(value, "normalization")
    tg_mode = data.get("tg_reference_mode", "first_valid")
    tg_mode = _require_string(tg_mode, "normalization.tg_reference_mode")
    if tg_mode != "first_valid":
        raise ProjectValidationError(
            "La référence TG doit être le premier point valide."
        )
    mode = _require_string(
        data.get(
            "heat_flow_reference_mode",
            data.get("reference_mode", "first_valid"),
        ),
        "normalization.heat_flow_reference_mode",
    )
    axis = _require_string(
        data.get("reference_axis", "time_s"), "normalization.reference_axis"
    )
    tg_representation = _require_string(
        data.get("tg_representation", "delta_m_mg"),
        "normalization.tg_representation",
    )
    dtg_unit_mode = _require_string(
        data.get("dtg_unit_mode", "source"), "normalization.dtg_unit_mode"
    )
    dtg_representation = _require_string(
        data.get("dtg_representation", "raw"), "normalization.dtg_representation"
    )
    heat_representation = _require_string(
        data.get("heat_flow_representation", "raw"),
        "normalization.heat_flow_representation",
    )
    if mode not in REFERENCE_MODES:
        raise ProjectValidationError("Le mode de référence du projet est inconnu.")
    if axis not in REFERENCE_AXES:
        raise ProjectValidationError("L'axe de référence du projet est inconnu.")
    if tg_representation not in TG_REPRESENTATIONS:
        raise ProjectValidationError("La représentation TG du projet est inconnue.")
    if heat_representation not in HEAT_FLOW_REPRESENTATIONS:
        raise ProjectValidationError(
            "La représentation HeatFlow du projet est inconnue."
        )
    if dtg_unit_mode not in {"source", "per_second", "per_minute", "per_hour"}:
        raise ProjectValidationError("L'unité dTG du projet est inconnue.")
    if dtg_representation not in {"raw", "per_mass", "percent"}:
        raise ProjectValidationError("La représentation dTG du projet est inconnue.")
    mass_required = (
        tg_representation in {"normalized_mg_mg", "normalized_pct"}
        or dtg_representation != "raw"
        or heat_representation
        in {"mw_mg", "zero_mw_mg", "w_g", "zero_w_g", "w_mg", "zero_w_mg"}
    )
    normalization_enabled = data.get("normalization_enabled", mass_required)
    if not isinstance(normalization_enabled, bool):
        raise ProjectValidationError(
            "Le champ 'normalization.normalization_enabled' doit être booléen."
        )
    reference_mass = _optional_finite_number(
        data.get("reference_mass_mg"),
        "normalization.reference_mass_mg",
        positive=True,
    )
    reference_name = _require_string(
        data.get("reference_name", ""),
        "normalization.reference_name",
        allow_empty=True,
    )
    use_initial_mass = data.get(
        "use_initial_mass_as_reference",
        mass_required and reference_mass is None,
    )
    if not isinstance(use_initial_mass, bool):
        raise ProjectValidationError(
            "Le champ 'normalization.use_initial_mass_as_reference' doit être booléen."
        )
    calculate_dtg = data.get("calculate_dtg_if_missing", False)
    try:
        smoothing_points = validate_dtg_smoothing_points(data.get("dtg_smoothing_points", 1))
    except ValueError as exc:
        raise ProjectValidationError(str(exc)) from exc
    if not isinstance(calculate_dtg, bool):
        raise ProjectValidationError(
            "Le champ 'normalization.calculate_dtg_if_missing' doit être booléen."
        )
    start = _optional_finite_number(
        data.get("range_start"), "normalization.range_start"
    )
    end = _optional_finite_number(data.get("range_end"), "normalization.range_end")
    if mode == "range_mean" and (
        start is None or end is None or start >= end
    ):
        raise ProjectValidationError(
            "La plage de référence du projet doit avoir deux bornes croissantes."
        )
    experiment_data = data.get("experiments", [])
    if not isinstance(experiment_data, list):
        raise ProjectValidationError(
            "Le champ 'normalization.experiments' doit être une liste."
        )
    experiments: list[dict[str, Any]] = []
    for index, item in enumerate(experiment_data):
        field_name = f"normalization.experiments[{index}]"
        record = _require_mapping(item, field_name)
        legacy_mass = "m0_mg" not in record and record.get("m_ref_mg") is not None
        initial_mass = _optional_finite_number(
            record.get("m0_mg", record.get("m_ref_mg")),
            f"{field_name}.m0_mg",
            positive=True,
        )
        record_reference_mass = _optional_finite_number(
            record.get("m_ref_mg", initial_mass),
            f"{field_name}.m_ref_mg",
            positive=True,
        )
        mass_source = "legacy" if legacy_mass else record.get("mass_source")
        if mass_source is not None:
            mass_source = _require_string(mass_source, f"{field_name}.mass_source")
        normalization_mass_source = (
            "legacy" if legacy_mass else record.get("normalization_mass_source")
        )
        if normalization_mass_source is not None:
            normalization_mass_source = _require_string(
                normalization_mass_source,
                f"{field_name}.normalization_mass_source",
            )
        experiments.append(
            {
                "source_name": _require_string(
                    record.get("source_name"), f"{field_name}.source_name"
                ),
                "source_sha256": _require_string(
                    record.get("source_sha256"), f"{field_name}.source_sha256"
                ),
                "manual_mass_mg": _optional_finite_number(
                    record.get("manual_mass_mg"),
                    f"{field_name}.manual_mass_mg",
                    positive=True,
                ),
                "m0_mg": initial_mass,
                "m_ref_mg": record_reference_mass,
                "mass_source": mass_source,
                "normalization_mass_source": normalization_mass_source,
                "tg_reference": _optional_finite_number(
                    record.get("tg_reference"), f"{field_name}.tg_reference"
                ),
                "heat_flow_reference_mw": _optional_finite_number(
                    record.get("heat_flow_reference_mw"),
                    f"{field_name}.heat_flow_reference_mw",
                ),
            }
        )
    return {
        "tg_reference_mode": "first_valid",
        "heat_flow_reference_mode": mode,
        "reference_mode": mode,
        "reference_axis": axis,
        "range_start": start,
        "range_end": end,
        "tg_representation": tg_representation,
        "dtg_unit_mode": dtg_unit_mode,
        "dtg_representation": dtg_representation,
        "heat_flow_representation": heat_representation,
        "normalization_enabled": normalization_enabled,
        "reference_mass_mg": reference_mass,
        "reference_name": reference_name,
        "use_initial_mass_as_reference": use_initial_mass,
        "calculate_dtg_if_missing": calculate_dtg,
        "dtg_smoothing_points": smoothing_points,
        "experiments": experiments,
    }


def _validate_limit_pair(value: Any, field_name: str) -> list[float | None]:
    if not isinstance(value, list) or len(value) != 2:
        raise ProjectValidationError(
            f"Le champ '{field_name}' doit contenir exactement deux limites."
        )
    result: list[float | None] = []
    for item in value:
        if item is not None and (
            not isinstance(item, (int, float)) or isinstance(item, bool)
        ):
            raise ProjectValidationError(
                f"Les limites de '{field_name}' doivent être numériques ou nulles."
            )
        if item is not None and not math.isfinite(float(item)):
            raise ProjectValidationError(
                f"Les limites de '{field_name}' doivent être finies."
            )
        result.append(None if item is None else float(item))
    if result[0] is not None and result[1] is not None and result[0] >= result[1]:
        raise ProjectValidationError(
            f"La limite minimale de '{field_name}' doit être inférieure à la maximale."
        )
    return result


def _validate_graph_color(value: Any, field_name: str) -> str:
    color = _require_string(value, field_name)
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is None:
        raise ProjectValidationError(
            f"La couleur de '{field_name}' doit utiliser le format #RRGGBB."
        )
    return color.upper()


def _validate_graph_appearance(data: Mapping[str, Any]) -> dict[str, Any]:
    defaults = default_graph_settings()

    def number(value, low, high, optional=False):
        checked = _optional_finite_number(value, "graph.appearance")
        if checked is None and optional:
            return None
        if checked is None or not low <= checked <= high:
            raise ProjectValidationError("Un réglage des axes ou de la grille est invalide.")
        return checked

    def color(value):
        return None if value is None else _validate_graph_color(value, "graph.appearance.color")

    def flag(value):
        if not isinstance(value, bool):
            raise ProjectValidationError("Un réglage des axes ou de la grille est invalide.")
        return value

    grids = _require_mapping(data.get("grid_styles", {}), "graph.grid_styles")
    _reject_unknown_template_keys(grids, {"major", "minor"}, "graph.grid_styles")
    grid_styles = {}
    for kind, default in defaults["grid_styles"].items():
        style = _require_mapping(grids.get(kind, {}), "graph.grid_styles")
        _reject_unknown_template_keys(style, set(default), "graph.grid_styles")
        style = {**default, **style}
        if style["line_style"] not in ("-", "--", "-.", ":"):
            raise ProjectValidationError("Un réglage des axes ou de la grille est invalide.")
        grid_styles[kind] = {"color": color(style["color"]), "line_style": style["line_style"], "line_width": number(style["line_width"], 0.1, 10)}
    appearances = _require_mapping(data.get("axis_appearance", {}), "graph.axis_appearance")
    _reject_unknown_template_keys(appearances, set(defaults["axis_appearance"]), "graph.axis_appearance")
    axes = {}
    for role, default in defaults["axis_appearance"].items():
        raw = _require_mapping(appearances.get(role, {}), "graph.axis_appearance")
        _reject_unknown_template_keys(raw, set(default), "graph.axis_appearance")
        style = {**default, **raw}
        positions = {"auto", "bottom"} if role == "x" else {"auto", "top"} if role == "x_top" else {"auto", "left", "right"}
        if style["position"] not in tuple(positions) or style["arrow"] not in ("none", "end", "both"):
            raise ProjectValidationError("Un réglage des axes ou de la grille est invalide.")
        for key in ("visible", "line_visible", "labels_visible"):
            style[key] = flag(style[key])
        style["width"] = number(style["width"], 0.1, 10)
        style["color"] = color(style["color"])
        for kind in ("major", "minor"):
            raw_tick = _require_mapping(raw.get(kind, {}), "graph.axis_appearance.ticks")
            _reject_unknown_template_keys(raw_tick, set(default[kind]), "graph.axis_appearance.ticks")
            tick = {**default[kind], **raw_tick}
            if tick["direction"] not in ("in", "out", "inout"):
                raise ProjectValidationError("Un réglage des axes ou de la grille est invalide.")
            tick["visible"] = flag(tick["visible"])
            tick["color"] = color(tick["color"])
            tick["length"] = number(tick["length"], 0, 30, optional=True)
            tick["width"] = number(tick["width"], 0.1, 10, optional=True)
            style[kind] = tick
        axes[role] = style
    margins = data.get("layout_margins")
    if margins is not None:
        margins = _require_mapping(margins, "graph.layout_margins")
        _reject_unknown_template_keys(margins, {"left", "right", "top", "bottom"}, "graph.layout_margins")
        margins = {key: number(margins.get(key), 0, 1) for key in ("left", "right", "bottom", "top")}
        if margins["left"] >= margins["right"] or margins["bottom"] >= margins["top"]:
            raise ProjectValidationError("Les marges doivent laisser une surface de tracé positive.")
    return {"grid_styles": grid_styles, "axis_appearance": axes, "layout_margins": margins}


def _validate_graph_settings(
    value: Any,
    field_name: str,
    *,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    data = {} if value is None else _require_mapping(value, field_name)

    def axis_mapping(name: str) -> Mapping[str, Any]:
        return _require_mapping(
            data.get(name, defaults[name]), f"{field_name}.{name}"
        )

    labels_data = axis_mapping("axis_labels")
    labels = {
        axis: _require_string(
            labels_data.get(axis, defaults["axis_labels"][axis]),
            f"{field_name}.axis_labels.{axis}",
            allow_empty=True,
        )
        for axis in GRAPH_AXES
    }
    scales_data = axis_mapping("axis_scales")
    scales = {
        axis: _require_string(
            scales_data.get(axis, defaults["axis_scales"][axis]),
            f"{field_name}.axis_scales.{axis}",
        )
        for axis in GRAPH_AXES
    }
    if any(scale not in GRAPH_SCALES for scale in scales.values()):
        raise ProjectValidationError("Une échelle graphique est inconnue.")

    steps_data = axis_mapping("major_tick_steps")
    steps = {
        axis: _optional_finite_number(
            steps_data.get(axis, defaults["major_tick_steps"][axis]),
            f"{field_name}.major_tick_steps.{axis}",
            positive=True,
        )
        for axis in GRAPH_AXES
    }
    minor_data = axis_mapping("minor_tick_subdivisions")
    minor: dict[str, int] = {}
    for axis in GRAPH_AXES:
        count = minor_data.get(axis, defaults["minor_tick_subdivisions"][axis])
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 0 <= count <= 10
        ):
            raise ProjectValidationError(
                f"Les subdivisions de '{field_name}.{axis}' doivent être comprises entre 0 et 10."
            )
        minor[axis] = count

    formats_data = axis_mapping("tick_formats")
    formats = {
        axis: _require_string(
            formats_data.get(axis, defaults["tick_formats"][axis]),
            f"{field_name}.tick_formats.{axis}",
        )
        for axis in GRAPH_AXES
    }
    if any(value not in GRAPH_TICK_FORMATS for value in formats.values()):
        raise ProjectValidationError("Un format de graduations est inconnu.")
    decimals_data = axis_mapping("tick_decimals")
    decimals: dict[str, int] = {}
    for axis in GRAPH_AXES:
        count = decimals_data.get(axis, defaults["tick_decimals"][axis])
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 0 <= count <= 12
        ):
            raise ProjectValidationError(
                f"Le nombre de décimales de '{field_name}.{axis}' est invalide."
            )
        decimals[axis] = count

    rotation = data.get("x_tick_rotation", defaults["x_tick_rotation"])
    if rotation not in {0, 30, 45, 90}:
        raise ProjectValidationError("La rotation des graduations X est invalide.")
    grid_major = data.get("grid_major", defaults["grid_major"])
    grid_minor = data.get("grid_minor", defaults["grid_minor"])
    legend_visible = data.get("legend_visible", defaults["legend_visible"])
    if not all(
        isinstance(item, bool)
        for item in (grid_major, grid_minor, legend_visible)
    ):
        raise ProjectValidationError(
            "Les options de grille et de légende doivent être booléennes."
        )
    grid_axis = _require_string(
        data.get("grid_axis", defaults["grid_axis"]),
        f"{field_name}.grid_axis",
    )
    legend_position = _require_string(
        data.get("legend_position", defaults["legend_position"]),
        f"{field_name}.legend_position",
    )
    if grid_axis not in GRAPH_GRID_AXES:
        raise ProjectValidationError("L'orientation de grille est inconnue.")
    if legend_position not in GRAPH_LEGEND_POSITIONS:
        raise ProjectValidationError("La position de légende est inconnue.")

    styles_data = _require_mapping(
        data.get("curve_styles", defaults["curve_styles"]),
        f"{field_name}.curve_styles",
    )
    styles: dict[str, dict[str, Any]] = {}
    for signal, raw_style in styles_data.items():
        if signal not in SUPPORTED_SIGNALS:
            raise ProjectValidationError("Un rôle de courbe graphique est inconnu.")
        style = _require_mapping(raw_style, f"{field_name}.curve_styles.{signal}")
        line_style = style.get("line_style", "-")
        marker = style.get("marker", "")
        line_width = style.get("line_width", 1.4)
        markevery = style.get("markevery")
        if (
            not isinstance(line_style, str) or line_style not in LINE_STYLES
            or not isinstance(marker, str) or marker not in MARKERS
            or not isinstance(line_width, (int, float))
            or isinstance(line_width, bool)
            or not math.isfinite(float(line_width))
            or not 0.1 <= float(line_width) <= 10.0
            or (
                markevery is not None
                and (
                    not isinstance(markevery, int)
                    or isinstance(markevery, bool)
                    or markevery <= 0
                )
            )
        ):
            raise ProjectValidationError("Un style de courbe graphique est invalide.")
        styles[signal] = {
            "color": _validate_graph_color(
                style.get("color"), f"{field_name}.curve_styles.{signal}.color"
            ),
            "line_style": line_style,
            "line_width": float(line_width),
            "marker": marker,
            "markevery": markevery,
        }

    lines_data = data.get("reference_lines", defaults["reference_lines"])
    if not isinstance(lines_data, list):
        raise ProjectValidationError("Les lignes de référence doivent être une liste.")
    reference_lines: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, raw_line in enumerate(lines_data):
        name = f"{field_name}.reference_lines[{index}]"
        line = _require_mapping(raw_line, name)
        identifier = _require_string(line.get("id"), f"{name}.id")
        orientation = _require_string(
            line.get("orientation"), f"{name}.orientation"
        )
        axis = _require_string(line.get("axis"), f"{name}.axis")
        number = _optional_finite_number(line.get("value"), f"{name}.value")
        visible = line.get("visible", True)
        width = line.get("line_width", 1.0)
        line_style = line.get("line_style", "--")
        if identifier in identifiers:
            raise ProjectValidationError("Un identifiant de ligne est dupliqué.")
        if orientation not in {"vertical", "horizontal"} or (
            orientation == "vertical" and axis != "x"
        ) or (orientation == "horizontal" and axis not in SUPPORTED_SIGNALS):
            raise ProjectValidationError("La cible d'une ligne de référence est invalide.")
        if number is None:
            raise ProjectValidationError("La valeur d'une ligne de référence est obligatoire.")
        if not isinstance(visible, bool):
            raise ProjectValidationError("La visibilité d'une ligne doit être booléenne.")
        if (
            line_style not in {"-", "--", "-.", ":"}
            or not isinstance(width, (int, float))
            or isinstance(width, bool)
            or not math.isfinite(float(width))
            or not 0.1 <= float(width) <= 10.0
        ):
            raise ProjectValidationError("Le style d'une ligne de référence est invalide.")
        if scales[axis] == "log" and number <= 0:
            raise ProjectValidationError(
                "Une ligne de référence logarithmique doit être strictement positive."
            )
        reference_lines.append(
            {
                "id": identifier,
                "orientation": orientation,
                "axis": axis,
                "value": number,
                "label": _require_string(
                    line.get("label", ""), f"{name}.label", allow_empty=True
                ),
                "visible": visible,
                "color": _validate_graph_color(
                    line.get("color", "#666666"), f"{name}.color"
                ),
                "line_style": line_style,
                "line_width": float(width),
            }
        )
        identifiers.add(identifier)

    annotations_data = data.get("annotations", defaults["annotations"])
    if not isinstance(annotations_data, list):
        raise ProjectValidationError("Les annotations doivent être une liste.")
    annotations: list[dict[str, Any]] = []
    annotation_ids: set[str] = set()
    for index, raw_annotation in enumerate(annotations_data):
        name = f"{field_name}.annotations[{index}]"
        annotation = _require_mapping(raw_annotation, name)
        identifier = _require_string(annotation.get("id"), f"{name}.id")
        text = _require_string(annotation.get("text"), f"{name}.text")
        coordinate_system = _require_string(
            annotation.get("coordinate_system"), f"{name}.coordinate_system"
        )
        axis = _require_string(annotation.get("axis"), f"{name}.axis")
        position = annotation.get("position")
        arrow_position = annotation.get("arrow_position")
        if (
            identifier in annotation_ids
            or not text.strip()
            or "$" in text
            or coordinate_system not in GRAPH_ANNOTATION_COORDINATES
            or axis not in GRAPH_AXES
            or not isinstance(position, list)
            or len(position) != 2
        ):
            raise ProjectValidationError("Une annotation graphique est invalide.")
        checked_position = [
            _optional_finite_number(value, f"{name}.position[{item}]")
            for item, value in enumerate(position)
        ]
        if any(value is None for value in checked_position):
            raise ProjectValidationError("La position d'une annotation est obligatoire.")
        if arrow_position is not None:
            if not isinstance(arrow_position, list) or len(arrow_position) != 2:
                raise ProjectValidationError("La flèche d'une annotation est invalide.")
            checked_arrow = [
                _optional_finite_number(value, f"{name}.arrow_position[{item}]")
                for item, value in enumerate(arrow_position)
            ]
            if any(value is None for value in checked_arrow):
                raise ProjectValidationError("La flèche d'une annotation est invalide.")
        else:
            checked_arrow = None
        if coordinate_system == "data":
            checked_values = [checked_position, *([] if checked_arrow is None else [checked_arrow])]
            if axis == "x" and scales["x"] == "log" and any(values[0] <= 0 for values in checked_values):
                raise ProjectValidationError("Une annotation X logarithmique doit être strictement positive.")
            if axis != "x" and scales[axis] == "log" and any(values[1] <= 0 for values in checked_values):
                raise ProjectValidationError("Une annotation logarithmique doit être strictement positive.")
        alignment = _require_string(
            annotation.get("alignment", "left"), f"{name}.alignment"
        )
        arrow_style = _require_string(
            annotation.get("arrow_style", ""),
            f"{name}.arrow_style",
            allow_empty=True,
        )
        size = annotation.get("font_size", 10.0)
        if (
            alignment not in GRAPH_ANNOTATION_ALIGNMENTS
            or arrow_style not in GRAPH_ARROW_STYLES
            or not isinstance(size, (int, float))
            or isinstance(size, bool)
            or not math.isfinite(float(size))
            or not 6.0 <= float(size) <= 36.0
        ):
            raise ProjectValidationError("Le style d'une annotation est invalide.")
        weight = _require_string(annotation.get("font_weight", "normal"), f"{name}.font_weight")
        style = _require_string(annotation.get("font_style", "normal"), f"{name}.font_style")
        if weight not in {"normal", "bold"} or style not in {"normal", "italic"}:
            raise ProjectValidationError("La police d'une annotation est invalide.")
        if checked_arrow is not None and not arrow_style:
            raise ProjectValidationError("Une annotation avec flèche requiert un style de flèche.")
        annotations.append({
            "id": identifier, "text": text, "coordinate_system": coordinate_system,
            "axis": axis, "position": checked_position,
            "arrow_position": checked_arrow, "alignment": alignment,
            "color": _validate_graph_color(annotation.get("color", "#000000"), f"{name}.color"),
            "font_size": float(size), "font_weight": weight,
            "font_style": style, "arrow_style": arrow_style,
        })
        annotation_ids.add(identifier)

    spacing_data = _require_mapping(
        data.get("axis_spacing", defaults["axis_spacing"]), f"{field_name}.axis_spacing"
    )
    def spacing_value(key: str, minimum: float, maximum: float) -> float:
        value = spacing_data.get(key, defaults["axis_spacing"][key])
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or not minimum <= float(value) <= maximum:
            raise ProjectValidationError(f"L'espacement '{key}' est invalide.")
        return float(value)
    label_data = _require_mapping(spacing_data.get("label_pads", defaults["axis_spacing"]["label_pads"]), f"{field_name}.axis_spacing.label_pads")
    tick_data = _require_mapping(spacing_data.get("tick_pads", defaults["axis_spacing"]["tick_pads"]), f"{field_name}.axis_spacing.tick_pads")
    label_pads = {axis: _optional_finite_number(label_data.get(axis, 4.0), f"{field_name}.axis_spacing.label_pads.{axis}") for axis in GRAPH_AXES}
    tick_pads = {axis: _optional_finite_number(tick_data.get(axis, 3.5), f"{field_name}.axis_spacing.tick_pads.{axis}") for axis in GRAPH_AXES}
    if any(value is None or not 0.0 <= value <= 60.0 for value in [*label_pads.values(), *tick_pads.values()]):
        raise ProjectValidationError("Les espacements des labels sont invalides.")
    tg_right = spacing_value("tg_right_position", 1.0, 1.20)
    dtg_right = spacing_value("dtg_right_position", 1.04, 1.40)
    if dtg_right < tg_right + 0.04:
        raise ProjectValidationError("L'axe dTG doit rester à l'extérieur de TG.")

    fonts_data = _require_mapping(data.get("fonts", defaults["fonts"]), f"{field_name}.fonts")
    def font_value(value: Any, name: str) -> dict[str, Any]:
        source = _require_mapping(value, name)
        family = _require_string(source.get("family", ""), f"{name}.family", allow_empty=True)
        size = source.get("size")
        if size is not None and (not isinstance(size, (int, float)) or isinstance(size, bool) or not math.isfinite(float(size)) or not 6.0 <= float(size) <= 36.0):
            raise ProjectValidationError(f"La taille de police '{name}' est invalide.")
        weight = _require_string(source.get("weight", "normal"), f"{name}.weight")
        style = _require_string(source.get("style", "normal"), f"{name}.style")
        if weight not in {"normal", "bold"} or style not in {"normal", "italic"}:
            raise ProjectValidationError(f"Le style de police '{name}' est invalide.")
        return {"family": family, "size": None if size is None else float(size), "weight": weight, "style": style}
    general_font = font_value(fonts_data.get("general", {}), f"{field_name}.fonts.general")
    override_data = _require_mapping(fonts_data.get("overrides", {}), f"{field_name}.fonts.overrides")
    if set(override_data) - GRAPH_FONT_TARGETS:
        raise ProjectValidationError("Une cible de police est inconnue.")
    font_overrides = {target: font_value(value, f"{field_name}.fonts.overrides.{target}") for target, value in override_data.items()}

    return {
        "title": _require_string(
            data.get("title", defaults["title"]),
            f"{field_name}.title",
            allow_empty=True,
        ),
        "axis_labels": labels,
        "axis_scales": scales,
        "major_tick_steps": steps,
        "minor_tick_subdivisions": minor,
        "tick_formats": formats,
        "tick_decimals": decimals,
        "x_tick_rotation": rotation,
        "grid_major": grid_major,
        "grid_minor": grid_minor,
        "grid_axis": grid_axis,
        **_validate_graph_appearance(data),
        "legend_visible": legend_visible,
        "legend_position": legend_position,
        "legend_style": _validate_legend_style(data.get("legend_style", default_legend_style())),
        "curve_styles": styles,
        "reference_lines": reference_lines,
        "annotations": annotations,
        "axis_spacing": {"tg_right_position": tg_right, "dtg_right_position": dtg_right, "label_pads": label_pads, "tick_pads": tick_pads},
        "fonts": {"general": general_font, "overrides": font_overrides},
    }


def graph_template_payload(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Retourne le seul contenu déclaratif autorisé dans un modèle externe."""

    checked = _validate_graph_settings(graph, "template.graph", defaults=default_graph_settings())
    return {"version": GRAPH_TEMPLATE_VERSION, "graph": checked}


def _reject_unknown_template_keys(
    value: Mapping[str, Any], allowed: set[str], field_name: str
) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ProjectValidationError(
            f"La clé de modèle '{sorted(unknown)[0]}' n'est pas autorisée dans {field_name}."
        )


def _validate_graph_template_whitelist(graph: Mapping[str, Any]) -> None:
    defaults = default_graph_settings()
    _reject_unknown_template_keys(graph, set(defaults), "template.graph")
    legend = graph.get("legend_style")
    if isinstance(legend, Mapping):
        _reject_unknown_template_keys(legend, set(default_legend_style()), "template.graph.legend_style")
        if isinstance(legend.get("margins"), Mapping):
            _reject_unknown_template_keys(legend["margins"], {"left", "right", "top", "bottom"}, "template.graph.legend_style.margins")
    for name in (
        "axis_labels", "axis_scales", "major_tick_steps", "minor_tick_subdivisions",
        "tick_formats", "tick_decimals",
    ):
        value = graph.get(name)
        if isinstance(value, Mapping):
            _reject_unknown_template_keys(
                value, set(GRAPH_AXES), f"template.graph.{name}"
            )
    styles = graph.get("curve_styles")
    if isinstance(styles, Mapping):
        _reject_unknown_template_keys(
            styles, SUPPORTED_SIGNALS, "template.graph.curve_styles"
        )
        for signal, style in styles.items():
            if isinstance(style, Mapping):
                _reject_unknown_template_keys(
                    style,
                    {"color", "line_style", "line_width", "marker", "markevery"},
                    f"template.graph.curve_styles.{signal}",
                )
    for name, allowed in (
        (
            "reference_lines",
            {"id", "orientation", "axis", "value", "label", "visible", "color", "line_style", "line_width"},
        ),
        (
            "annotations",
            {"id", "text", "coordinate_system", "axis", "position", "arrow_position", "alignment", "color", "font_size", "font_weight", "font_style", "arrow_style"},
        ),
    ):
        items = graph.get(name)
        if isinstance(items, list):
            for index, item in enumerate(items):
                if isinstance(item, Mapping):
                    _reject_unknown_template_keys(
                        item, allowed, f"template.graph.{name}[{index}]"
                    )
    spacing = graph.get("axis_spacing")
    if isinstance(spacing, Mapping):
        _reject_unknown_template_keys(
            spacing,
            {"tg_right_position", "dtg_right_position", "label_pads", "tick_pads"},
            "template.graph.axis_spacing",
        )
        for name in ("label_pads", "tick_pads"):
            value = spacing.get(name)
            if isinstance(value, Mapping):
                _reject_unknown_template_keys(
                    value, set(GRAPH_AXES), f"template.graph.axis_spacing.{name}"
                )
    fonts = graph.get("fonts")
    if isinstance(fonts, Mapping):
        _reject_unknown_template_keys(
            fonts, {"general", "overrides"}, "template.graph.fonts"
        )
        general = fonts.get("general")
        if isinstance(general, Mapping):
            _reject_unknown_template_keys(
                general,
                {"family", "size", "weight", "style"},
                "template.graph.fonts.general",
            )
        overrides = fonts.get("overrides")
        if isinstance(overrides, Mapping):
            _reject_unknown_template_keys(
                overrides, GRAPH_FONT_TARGETS, "template.graph.fonts.overrides"
            )
            for target, override in overrides.items():
                if isinstance(override, Mapping):
                    _reject_unknown_template_keys(
                        override,
                        {"family", "size", "weight", "style"},
                        f"template.graph.fonts.overrides.{target}",
                    )


def graph_from_template_payload(value: Any, *, defaults: dict[str, Any]) -> dict[str, Any]:
    data = _require_mapping(value, "template")
    _reject_unknown_template_keys(data, {"version", "graph"}, "template")
    if data.get("version") != GRAPH_TEMPLATE_VERSION:
        raise ProjectValidationError("Version de modèle graphique non prise en charge.")
    graph = _require_mapping(data.get("graph"), "template.graph")
    _validate_graph_template_whitelist(graph)
    return _validate_graph_settings(graph, "template.graph", defaults=defaults)


def _validate_log_limits(
    limits: Mapping[str, list[float | None]], graph: Mapping[str, Any]
) -> None:
    for axis, scale in graph["axis_scales"].items():
        if scale != "log":
            continue
        if any(value is not None and value <= 0 for value in limits[axis]):
            raise ProjectValidationError(
                f"Les limites logarithmiques de l'axe '{axis}' doivent être positives."
            )


def _validate_correction(value: Any) -> dict[str, str]:
    data = _require_mapping(value, "correction")
    method = _require_string(data.get("tg_method"), "correction.tg_method")
    if method not in {"direct", "drift"}:
        raise ProjectValidationError("La méthode TG du projet est inconnue.")
    axis = _require_string(
        data.get("interpolation_axis"), "correction.interpolation_axis"
    )
    if axis not in SUPPORTED_CORRECTION_AXES:
        raise ProjectValidationError("L'axe d'interpolation du projet est inconnu.")
    return {"tg_method": method, "interpolation_axis": axis}


def _validate_quality_control(value: Any) -> dict[str, float | int]:
    if value is None:
        return default_quality_control_settings()
    data = _require_mapping(value, "quality_control")
    try:
        return QCThresholds.from_dict(data).to_dict()
    except ValueError as exc:
        raise ProjectValidationError(str(exc)) from exc


def _validate_display(value: Any) -> dict[str, Any]:
    data = _require_mapping(value, "display")
    defaults = default_display_settings()
    x_axis = _require_string(data.get("x_axis"), "display.x_axis")
    if x_axis not in SUPPORTED_DISPLAY_AXES:
        raise ProjectValidationError("L'axe X du projet est inconnu.")
    signals = _require_string_list(data.get("visible_signals"), "display.visible_signals")
    if not signals or len(signals) != len(set(signals)) or set(signals) - SUPPORTED_SIGNALS:
        raise ProjectValidationError("La liste des signaux visibles est invalide.")
    align_zeros = data.get("align_zeros", False)
    if not isinstance(align_zeros, bool):
        raise ProjectValidationError("Le champ 'display.align_zeros' doit être booléen.")
    alignment_mode = data.get(
        "alignment_mode",
        "zeros" if align_zeros else "none",
    )
    alignment_mode = _require_string(alignment_mode, "display.alignment_mode")
    if alignment_mode not in {"none", "zeros", "references"}:
        raise ProjectValidationError("Le mode d'alignement du projet est inconnu.")
    limits_data = _require_mapping(data.get("limits"), "display.limits")
    limits = {
        name: _validate_limit_pair(limits_data.get(name), f"display.limits.{name}")
        for name in ("x", "tg", "dtg", "heat_flow")
    }
    graph = _validate_graph_settings(
        data.get("graph"), "display.graph", defaults=defaults["graph"]
    )
    _validate_log_limits(limits, graph)
    selected_zone = data.get("analysis_zone_selected_id")
    if selected_zone is not None:
        selected_zone = _require_string(
            selected_zone,
            "display.analysis_zone_selected_id",
        )
    show_zone_surfaces = data.get("show_zone_surfaces", True)
    show_zone_baselines = data.get("show_zone_baselines", True)
    show_subtraction = data.get("show_subtraction", True)
    if not isinstance(show_zone_surfaces, bool) or not isinstance(
        show_zone_baselines, bool
    ):
        raise ProjectValidationError(
            "Les paramètres d'affichage des zones doivent être booléens."
        )
    if not isinstance(show_subtraction, bool):
        raise ProjectValidationError(
            "Le paramètre 'display.show_subtraction' doit être booléen."
        )
    return {
        "x_axis": x_axis,
        "visible_signals": signals,
        "limits": limits,
        "align_zeros": align_zeros,
        "alignment_mode": alignment_mode,
        "analysis_zone_selected_id": selected_zone,
        "show_zone_surfaces": show_zone_surfaces,
        "show_zone_baselines": show_zone_baselines,
        "show_subtraction": show_subtraction,
        "graph": graph,
    }


def _validate_signal_settings(value: Any) -> dict[str, dict[str, Any]]:
    data = _require_mapping(value, "comparison.entries.signal_settings")
    style_fields = {"color", "line_style", "line_width", "marker", "markevery"}
    styles = {}
    for signal, raw in data.items():
        item = _require_mapping(raw, f"signal_settings.{signal}")
        if signal not in SUPPORTED_SIGNALS or set(item) - (style_fields | {"visible", "y_offset", "legend_name"}):
            raise ProjectValidationError("Les réglages du signal sont invalides.")
        styles[signal] = {"color": "#000000", **{key: val for key, val in item.items() if key in style_fields}}
    validated = _validate_graph_settings({"curve_styles": styles}, "signal_settings", defaults=default_graph_settings())["curve_styles"]
    result = {}
    for signal, item in data.items():
        checked = {key: validated[signal][key] for key in item if key in style_fields}
        if "visible" in item:
            if not isinstance(item["visible"], bool):
                raise ProjectValidationError("La visibilité du signal doit être booléenne.")
            checked["visible"] = item["visible"]
        if "y_offset" in item:
            checked["y_offset"] = _optional_finite_number(item["y_offset"], "signal_settings.y_offset")
            if checked["y_offset"] is None:
                raise ProjectValidationError("Le décalage du signal doit être un nombre fini.")
        if "legend_name" in item:
            checked["legend_name"] = _require_string(item["legend_name"], "signal_settings.legend_name").strip()
            if not checked["legend_name"]:
                raise ProjectValidationError("La légende du signal ne peut pas être vide.")
        result[signal] = checked
    return result


def _validate_comparison(value: Any) -> dict[str, Any]:
    if value is None:
        return default_comparison_settings()
    data = _require_mapping(value, "comparison")
    defaults = default_comparison_settings()
    signal = _require_string(data.get("signal", defaults["signal"]), "comparison.signal")
    if signal not in SUPPORTED_SIGNALS:
        raise ProjectValidationError("Le signal de comparaison est inconnu.")
    signals = _require_string_list(
        data.get("signals", [signal]), "comparison.signals"
    )
    if (
        not signals
        or len(signals) != len(set(signals))
        or any(item not in SUPPORTED_SIGNALS for item in signals)
    ):
        raise ProjectValidationError("Les signaux de comparaison sont invalides.")
    signal = signals[0]
    representations = _require_mapping(data.get("representations", defaults["representations"]), "comparison.representations")
    tg = _require_string(representations.get("tg"), "comparison.representations.tg")
    heat = _require_string(representations.get("heat_flow"), "comparison.representations.heat_flow")
    dtg = _require_string(representations.get("dtg"), "comparison.representations.dtg")
    if tg not in TG_REPRESENTATIONS or heat not in HEAT_FLOW_REPRESENTATIONS or dtg not in {"raw", "per_mass", "percent"}:
        raise ProjectValidationError("Une représentation de comparaison est inconnue.")
    entries = _require_mapping(data.get("entries", {}), "comparison.entries")
    checked_entries: dict[str, dict[str, Any]] = {}
    for key, item in entries.items():
        if not isinstance(key, str):
            raise ProjectValidationError("L'identifiant de comparaison est invalide.")
        item_data = _require_mapping(item, f"comparison.entries.{key}")
        checked_entries[key] = {
            "selected": item_data.get("selected", False),
            "visible": item_data.get("visible", item_data.get("selected", False)),
            "legend_name": _require_string(item_data.get("legend_name", ""), f"comparison.entries.{key}.legend_name"),
            "order": item_data.get("order", 0),
            "line_style": item_data.get("line_style", "-"),
            "line_width": item_data.get("line_width", 1.4),
            "marker": item_data.get("marker", ""),
            "markevery": item_data.get("markevery"),
            "y_offset": item_data.get("y_offset", 0.0),
        }
        if "signal_settings" in item_data:
            checked_entries[key]["signal_settings"] = _validate_signal_settings(item_data["signal_settings"])
        if "stage" in item_data:
            stage = _require_string(
                item_data["stage"], f"comparison.entries.{key}.stage"
            )
            if stage not in {"original", "corrected", "normalized"}:
                raise ProjectValidationError(
                    "La représentation d'une courbe de comparaison est inconnue."
                )
            checked_entries[key]["stage"] = stage
        if "show_subtraction" in item_data:
            if not isinstance(item_data["show_subtraction"], bool):
                raise ProjectValidationError("comparison.entries.show_subtraction doit être booléen.")
            checked_entries[key]["show_subtraction"] = item_data["show_subtraction"]
        if "blank" in item_data:
            checked_entries[key]["blank"] = (
                None
                if item_data["blank"] is None
                else SourceFileRecord.from_dict(
                    item_data["blank"], f"comparison.entries.{key}.blank"
                ).to_dict()
            )
        if "correction" in item_data:
            checked_entries[key]["correction"] = _validate_correction(
                item_data["correction"]
            )
        if "normalization" in item_data:
            checked_entries[key]["normalization"] = _validate_normalization(
                item_data["normalization"]
            )
        if "thermal_program" in item_data:
            try:
                checked_entries[key]["thermal_program"] = validate_thermal_program(
                    item_data["thermal_program"]
                )
            except ValueError as exc:
                raise ProjectValidationError(str(exc)) from exc
        if (
            not isinstance(checked_entries[key]["selected"], bool)
            or not isinstance(checked_entries[key]["visible"], bool)
            or not isinstance(checked_entries[key]["order"], int)
            or not isinstance(checked_entries[key]["line_style"], str)
            or checked_entries[key]["line_style"] not in LINE_STYLES
            or not isinstance(checked_entries[key]["marker"], str)
            or checked_entries[key]["marker"] not in MARKERS
            or not isinstance(checked_entries[key]["line_width"], (int, float))
            or isinstance(checked_entries[key]["line_width"], bool)
            or not math.isfinite(float(checked_entries[key]["line_width"]))
            or not 0.1 <= float(checked_entries[key]["line_width"]) <= 10.0
            or (
                checked_entries[key]["markevery"] is not None
                and (
                    not isinstance(checked_entries[key]["markevery"], int)
                    or isinstance(checked_entries[key]["markevery"], bool)
                    or checked_entries[key]["markevery"] <= 0
                )
            )
            or not isinstance(checked_entries[key]["y_offset"], (int, float))
            or isinstance(checked_entries[key]["y_offset"], bool)
            or not math.isfinite(float(checked_entries[key]["y_offset"]))
        ):
            raise ProjectValidationError("Les paramètres d'une courbe de comparaison sont invalides.")
    colors = _require_mapping(data.get("colors", {}), "comparison.colors")
    if any(not isinstance(key, str) or not isinstance(color, str) for key, color in colors.items()):
        raise ProjectValidationError("Les couleurs de comparaison sont invalides.")
    domain_mode = _require_string(data.get("domain_mode", "union"), "comparison.domain_mode")
    if domain_mode not in {"union", "overlap"}:
        raise ProjectValidationError("Le domaine de comparaison est inconnu.")
    grid = data.get("grid", True)
    if not isinstance(grid, bool):
        raise ProjectValidationError("La grille de comparaison doit être booléenne.")
    legacy_title = _require_string(
        data.get("title", defaults["title"]),
        "comparison.title",
        allow_empty=True,
    )
    graph = _validate_graph_settings(
        data.get("graph"),
        "comparison.graph",
        defaults=default_graph_settings(title=legacy_title, grid_major=grid),
    )
    align_zeros = data.get("align_zeros", False)
    if not isinstance(align_zeros, bool):
        raise ProjectValidationError("L'alignement des zéros doit être booléen.")
    show_offsets_in_legend = data.get("show_offsets_in_legend", False)
    if not isinstance(show_offsets_in_legend, bool):
        raise ProjectValidationError("L'option de légende des décalages doit être booléenne.")
    statistics_data = _require_mapping(
        data.get("statistics", defaults["statistics"]), "comparison.statistics"
    )
    statistics_enabled = statistics_data.get("enabled", False)
    display_mode = statistics_data.get("display_mode", "mean_band")
    grid_method = statistics_data.get("grid_method", "auto")
    manual_points = statistics_data.get("manual_points", 200)
    visibility = {
        "show_mean": statistics_data.get("show_mean", True),
        "show_band": statistics_data.get("show_band", True),
        "show_individual": statistics_data.get("show_individual", False),
    }
    if (
        not isinstance(statistics_enabled, bool)
        or display_mode not in {"mean", "mean_band", "mean_individual", "individual"}
        or grid_method not in {"auto", "manual"}
        or not isinstance(manual_points, int)
        or isinstance(manual_points, bool)
        or manual_points < 2
        or not all(isinstance(value, bool) for value in visibility.values())
    ):
        raise ProjectValidationError("Les paramètres statistiques de comparaison sont invalides.")
    groups_data = statistics_data.get("groups", [])
    if not isinstance(groups_data, list):
        raise ProjectValidationError("Les groupes de répétitions doivent être une liste.")
    groups: list[dict[str, Any]] = []
    group_ids: set[str] = set()
    assigned_members: set[str] = set()
    for index, item in enumerate(groups_data):
        item_data = _require_mapping(item, f"comparison.statistics.groups[{index}]")
        identifier = _require_string(item_data.get("id"), f"comparison.statistics.groups[{index}].id")
        name = _require_string(item_data.get("name"), f"comparison.statistics.groups[{index}].name")
        members = _require_string_list(item_data.get("members", []), f"comparison.statistics.groups[{index}].members")
        if identifier in group_ids or len(members) != len(set(members)) or assigned_members.intersection(members):
            raise ProjectValidationError("Les affectations aux groupes de répétitions sont invalides.")
        group_ids.add(identifier)
        assigned_members.update(members)
        groups.append({"id": identifier, "name": name, "members": members})
    dtg_unit_mode = _require_string(
        data.get("dtg_unit_mode", "source"), "comparison.dtg_unit_mode"
    )
    x_axis = _require_string(data.get("x_axis", "time_s"), "comparison.x_axis")
    if (
        dtg_unit_mode not in {"source", "per_second", "per_minute", "per_hour"}
        or x_axis not in SUPPORTED_DISPLAY_AXES
    ):
        raise ProjectValidationError("Les axes ou unités de comparaison sont inconnus.")
    legacy_x_limits = _validate_limit_pair(
        data.get("x_limits", [None, None]), "comparison.x_limits"
    )
    legacy_y_limits = _validate_limit_pair(
        data.get("y_limits", [None, None]), "comparison.y_limits"
    )
    if "limits" in data:
        limits_data = _require_mapping(data["limits"], "comparison.limits")
        limits = {
            axis: _validate_limit_pair(
                limits_data.get(axis, defaults["limits"][axis]),
                f"comparison.limits.{axis}",
            )
            for axis in GRAPH_AXES
        }
    else:
        limits = {
            axis: list(defaults["limits"][axis]) for axis in GRAPH_AXES
        }
        limits["x"] = legacy_x_limits
        limits[signal] = legacy_y_limits
    _validate_log_limits(limits, graph)
    mean_styles = _validate_signal_settings(data.get("mean_styles", {}))
    stacking = _require_mapping(data.get("stacking", defaults["stacking"]), "comparison.stacking")
    stack_signal = _require_string(stacking.get("signal", "tg"), "comparison.stacking.signal")
    stack_spacing = _optional_finite_number(stacking.get("spacing"), "comparison.stacking.spacing")
    if stack_signal not in SUPPORTED_SIGNALS or (stack_spacing is not None and not 0 <= stack_spacing <= 1e12):
        raise ProjectValidationError("L'écart d'empilement doit être compris entre 0 et 10¹².")
    return {
        "entries": checked_entries,
        "mean_styles": mean_styles,
        "stacking": {"signal": stack_signal, "spacing": stack_spacing},
        "signal": signal,
        "signals": signals,
        "representations": {"tg": tg, "dtg": dtg, "heat_flow": heat},
        "dtg_unit_mode": dtg_unit_mode,
        "x_axis": x_axis,
        "domain_mode": domain_mode,
        "x_limits": list(limits["x"]),
        "y_limits": list(limits[signal]),
        "limits": limits,
        "title": graph["title"],
        "grid": graph["grid_major"],
        "align_zeros": align_zeros,
        "show_offsets_in_legend": show_offsets_in_legend,
        "statistics": {
            "enabled": statistics_enabled,
            "groups": groups,
            "display_mode": display_mode,
            "grid_method": grid_method,
            "manual_points": manual_points,
            **visibility,
        },
        "colors": dict(colors),
        "graph": graph,
    }


def _validate_analysis_zones(value: Any) -> list[AnalysisZone]:
    if not isinstance(value, list):
        raise ProjectValidationError(
            "Le champ 'analysis_zones' doit être une liste."
        )
    zones: list[AnalysisZone] = []
    identifiers: set[str] = set()
    for index, item in enumerate(value):
        field_name = f"analysis_zones[{index}]"
        data = _require_mapping(item, field_name)
        identifier = _require_string(data.get("id"), f"{field_name}.id")
        if identifier in identifiers:
            raise ProjectValidationError(
                f"Identifiant de zone dupliqué : {identifier}"
            )
        start = _optional_finite_number(data.get("start"), f"{field_name}.start")
        end = _optional_finite_number(data.get("end"), f"{field_name}.end")
        if start is None or end is None:
            raise ProjectValidationError(
                f"Les bornes de '{field_name}' sont obligatoires."
            )
        try:
            zone = AnalysisZone(
                identifier=identifier,
                color=data.get("color"),
                line_width=data.get("line_width"),
                opacity=data.get("opacity"),
                show_baseline=data.get("show_baseline", True),
                positive_area_color=data.get("positive_area_color"),
                negative_area_color=data.get("negative_area_color"),
                baseline_color=data.get("baseline_color"),
                name=_require_string(data.get("name"), f"{field_name}.name"),
                axis_type=_require_string(
                    data.get("axis_type"), f"{field_name}.axis_type"
                ),
                start=start,
                end=end,
                baseline_method=_require_string(
                    data.get("baseline_method", "none"),
                    f"{field_name}.baseline_method",
                ),
                baseline_value=_optional_finite_number(
                    data.get("baseline_value"),
                    f"{field_name}.baseline_value",
                ),
                baseline_representation=(
                    None
                    if data.get("baseline_representation") is None
                    else _require_string(
                        data.get("baseline_representation"),
                        f"{field_name}.baseline_representation",
                    )
                ),
                baseline_unit=(
                    None
                    if data.get("baseline_unit") is None
                    else _require_string(
                        data.get("baseline_unit"),
                        f"{field_name}.baseline_unit",
                    )
                ),
            )
        except ValueError as exc:
            raise ProjectValidationError(str(exc)) from exc
        zones.append(zone)
        identifiers.add(identifier)
    return zones


def default_stoichiometry_settings() -> dict[str, Any]:
    return {
        "version": STOICHIOMETRY_VERSION,
        "current_index": None,
        "equations": [],
        "display": {"mass_unit": "mg", "amount_unit": "mol", "notation": "scientific"},
    }


def _validate_stoichiometry(value: Any) -> dict[str, Any]:
    if value is None:
        return default_stoichiometry_settings()
    data = _require_mapping(value, "stoichiometry")
    version = data.get("version", STOICHIOMETRY_VERSION)
    if version != STOICHIOMETRY_VERSION:
        raise ProjectValidationError("La version des calculs stœchiométriques est inconnue.")
    display = default_stoichiometry_settings()["display"]
    raw_display = _require_mapping(data.get("display", {}), "stoichiometry.display")
    for key, choices in (
        ("mass_unit", ("µg", "mg", "g")),
        ("amount_unit", ("µmol", "mmol", "mol")),
        ("notation", ("decimal", "scientific")),
    ):
        selected = raw_display.get(key, display[key])
        if not isinstance(selected, str) or selected not in choices:
            raise ProjectValidationError(f"Réglage 'stoichiometry.display.{key}' invalide : {selected!r}.")
        display[key] = selected
    raw_equations = data.get("equations", [])
    if not isinstance(raw_equations, list):
        raise ProjectValidationError("Le champ 'stoichiometry.equations' doit être une liste.")
    equations = []
    for index, item in enumerate(raw_equations):
        entry = _require_mapping(item, f"stoichiometry.equations[{index}]")
        checked = entry.get("checked", False)
        if not isinstance(checked, bool):
            raise ProjectValidationError(
                f"Le champ 'stoichiometry.equations[{index}].checked' doit être booléen."
            )
        inputs = entry.get("inputs", {})
        if not isinstance(inputs, dict):
            raise ProjectValidationError(
                f"Le champ 'stoichiometry.equations[{index}].inputs' doit être un objet JSON."
            )
        source_id = entry.get("atomic_data_source_id", "")
        if not isinstance(source_id, str):
            raise ProjectValidationError(
                f"Le champ 'stoichiometry.equations[{index}].atomic_data_source_id' doit être une chaîne."
            )
        equations.append(
            {
                "text": _require_string(
                    entry.get("text", ""),
                    f"stoichiometry.equations[{index}].text",
                    allow_empty=True,
                ),
                "checked": checked,
                "inputs": dict(inputs),
                "atomic_data_source_id": source_id,
            }
        )
    current_index = data.get("current_index")
    if (
        not isinstance(current_index, int)
        or isinstance(current_index, bool)
        or not 0 <= current_index < len(equations)
    ):
        current_index = None
    return {
        "version": STOICHIOMETRY_VERSION,
        "current_index": current_index,
        "equations": equations,
        "display": display,
    }


@dataclass(slots=True)
class ProjectDocument:
    project_name: str
    created_at: str
    modified_at: str
    experiments: list[SourceFileRecord] = field(default_factory=list)
    blank: SourceFileRecord | None = None
    correction: dict[str, str] = field(
        default_factory=lambda: {
            "tg_method": "direct",
            "interpolation_axis": "time_s",
        }
    )
    display: dict[str, Any] = field(default_factory=default_display_settings)
    normalization: dict[str, Any] = field(
        default_factory=default_normalization_settings
    )
    quality_control: dict[str, float | int] = field(
        default_factory=default_quality_control_settings
    )
    comparison: dict[str, Any] = field(default_factory=default_comparison_settings)
    analysis_zones: list[AnalysisZone] = field(default_factory=list)
    stoichiometry: dict[str, Any] = field(default_factory=default_stoichiometry_settings)
    processing_history: list[ProcessingEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    app_version: str = field(default_factory=application_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_version": self.app_version,
            "project_name": self.project_name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "sources": {
                "experiments": [source.to_dict() for source in self.experiments],
                "blank": None if self.blank is None else self.blank.to_dict(),
            },
            "correction": self.correction,
            "display": self.display,
            "normalization": self.normalization,
            "quality_control": self.quality_control,
            "comparison": self.comparison,
            "analysis_zones": [zone.to_dict() for zone in self.analysis_zones],
            "stoichiometry": self.stoichiometry,
            "processing_history": [event.to_dict() for event in self.processing_history],
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, value: Any) -> ProjectDocument:
        data = _require_mapping(value, "racine")
        schema_version = data.get("schema_version")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ProjectValidationError(
                "Le champ 'schema_version' doit être un entier."
            )
        if schema_version != SCHEMA_VERSION:
            raise ProjectVersionError(
                f"Version de projet incompatible : {schema_version}. "
                f"Cette application prend en charge la version {SCHEMA_VERSION}."
            )
        sources = _require_mapping(data.get("sources"), "sources")
        experiments_data = sources.get("experiments")
        if not isinstance(experiments_data, list):
            raise ProjectValidationError(
                "Le champ 'sources.experiments' doit être une liste."
            )
        blank_data = sources.get("blank")
        history_data = data.get("processing_history")
        if not isinstance(history_data, list):
            raise ProjectValidationError(
                "Le champ 'processing_history' doit être une liste."
            )
        return cls(
            schema_version=schema_version,
            app_version=_require_string(data.get("app_version"), "app_version"),
            project_name=_require_string(data.get("project_name"), "project_name"),
            created_at=_validate_timestamp(data.get("created_at"), "created_at"),
            modified_at=_validate_timestamp(data.get("modified_at"), "modified_at"),
            experiments=[
                SourceFileRecord.from_dict(item, f"sources.experiments[{index}]")
                for index, item in enumerate(experiments_data)
            ],
            blank=(
                None
                if blank_data is None
                else SourceFileRecord.from_dict(blank_data, "sources.blank")
            ),
            correction=_validate_correction(data.get("correction")),
            display=_validate_display(data.get("display")),
            normalization=_validate_normalization(
                data.get("normalization", default_normalization_settings())
            ),
            quality_control=_validate_quality_control(data.get("quality_control")),
            comparison=_validate_comparison(data.get("comparison")),
            analysis_zones=_validate_analysis_zones(
                data.get("analysis_zones", [])
            ),
            stoichiometry=_validate_stoichiometry(data.get("stoichiometry")),
            processing_history=[
                ProcessingEvent.from_dict(item, f"processing_history[{index}]")
                for index, item in enumerate(history_data)
            ],
            warnings=_require_string_list(data.get("warnings"), "warnings"),
        )


def new_project_document(name: str = "Sans titre") -> ProjectDocument:
    now = utc_now()
    return ProjectDocument(project_name=name, created_at=now, modified_at=now)


def load_project(path: str | Path) -> ProjectDocument:
    project_path = Path(path)
    try:
        value = json.loads(read_limited_bytes(project_path, MAX_PROJECT_BYTES).decode('utf-8'))
    except json.JSONDecodeError as exc:
        raise ProjectValidationError(
            f"JSON invalide à la ligne {exc.lineno}, colonne {exc.colno} : {exc.msg}"
        ) from exc
    except OSError as exc:
        raise ProjectError(f"Impossible de lire le projet : {exc}") from exc
    except (DataReadError, UnicodeError, RecursionError) as exc:
        raise ProjectValidationError(tr("Projet refusé : fichier trop volumineux, illisible ou trop complexe. {detail}", detail=str(exc))) from exc
    return ProjectDocument.from_dict(value)


def save_project(document: ProjectDocument, path: str | Path) -> ProjectDocument:
    """Valide puis écrit le projet par remplacement atomique."""

    target = Path(path)
    payload = document.to_dict()
    validated = ProjectDocument.from_dict(payload)
    sources = list(validated.experiments)
    if validated.blank is not None:
        sources.append(validated.blank)
    sources.extend(
        SourceFileRecord.from_dict(entry["blank"], f"comparison.entries.{key}.blank")
        for key, entry in validated.comparison["entries"].items()
        if entry.get("blank") is not None
    )
    for source in sources:
        if any(same_path(target, candidate) for candidate in _candidate_paths(source, target)):
            raise ProjectValidationError(tr(
                "Impossible d'enregistrer le projet sur une source expérimentale : {path}",
                path=str(target),
            ))
    payload["modified_at"] = utc_now()
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    except OSError as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ProjectError(f"Impossible d'enregistrer le projet : {exc}") from exc
    document.modified_at = payload["modified_at"]
    return document


MissingAction = Literal["locate", "ignore", "cancel"]
ModifiedAction = Literal["continue", "locate", "cancel"]
MissingHandler = Callable[
    [SourceFileRecord], tuple[MissingAction, Path | None]
]
ModifiedHandler = Callable[
    [SourceFileRecord, Path], tuple[ModifiedAction, Path | None]
]


@dataclass(frozen=True, slots=True)
class SourceResolution:
    path: Path | None
    relocated: bool = False
    modified: bool = False


def _candidate_paths(
    source: SourceFileRecord,
    project_path: Path,
) -> list[Path]:
    candidates: list[Path] = []
    if source.relative_path:
        candidates.append(Path(os.path.abspath(project_path)).parent / source.relative_path)
    absolute = Path(source.absolute_path)
    if not candidates or os.path.normcase(os.path.abspath(absolute)) != os.path.normcase(os.path.abspath(candidates[0])):
        candidates.append(absolute)
    return candidates


def resolve_source(
    source: SourceFileRecord,
    project_path: str | Path,
    *,
    missing_handler: MissingHandler | None = None,
    modified_handler: ModifiedHandler | None = None,
) -> SourceResolution:
    """Résout une source sans jamais ignorer silencieusement un écart."""

    project_file = Path(project_path)
    initial_candidates = _candidate_paths(source, project_file)
    candidate = None
    for path in initial_candidates:
        try:
            require_automatic_local_path(path)
        except DataReadError as exc:
            raise ProjectValidationError(str(exc)) from exc
        if path.is_file():
            candidate = path
            break
    relocated = False

    while candidate is None:
        if missing_handler is None:
            raise SourceMissingError(source)
        action, selected = missing_handler(source)
        if action == "cancel":
            raise ProjectOpenCancelled("Ouverture du projet annulée.")
        if action == "ignore":
            return SourceResolution(None)
        if action != "locate" or selected is None:
            raise ProjectError("Réponse invalide lors de la localisation d'une source.")
        candidate = Path(selected)
        relocated = True
        if not candidate.is_file():
            candidate = None

    while True:
        check_input_size(candidate)
        digest = sha256_file(candidate)
        if digest == source.sha256:
            return SourceResolution(candidate.resolve(), relocated=relocated)
        if modified_handler is None:
            raise SourceHashMismatchError(source, candidate)
        action, selected = modified_handler(source, candidate)
        if action == "cancel":
            raise ProjectOpenCancelled("Ouverture du projet annulée.")
        if action == "continue":
            return SourceResolution(
                candidate.resolve(),
                relocated=relocated,
                modified=True,
            )
        if action != "locate" or selected is None:
            raise ProjectError("Réponse invalide pour une source modifiée.")
        candidate = Path(selected)
        relocated = True
        if not candidate.is_file():
            candidate = None
            while candidate is None:
                if missing_handler is None:
                    raise SourceMissingError(source)
                missing_action, missing_selected = missing_handler(source)
                if missing_action == "cancel":
                    raise ProjectOpenCancelled("Ouverture du projet annulée.")
                if missing_action == "ignore":
                    return SourceResolution(None)
                if missing_action != "locate" or missing_selected is None:
                    raise ProjectError(
                        "Réponse invalide lors de la localisation d'une source."
                    )
                candidate = Path(missing_selected)
                if not candidate.is_file():
                    candidate = None


def reload_source(
    source: SourceFileRecord,
    path: str | Path,
) -> ExperimentData:
    mapping = {
        role: column
        for role, column in source.column_mapping.items()
        if column is not None
    }
    return load_experiment(
        path,
        source.sheet_name,
        mapping,
        source.time_unit,
    )
