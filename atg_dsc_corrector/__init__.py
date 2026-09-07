"""ThermalCurve."""

APP_NAME = "ThermalCurve"
__version__ = "1.0.0"
COPYRIGHT = "© 2026 Valentin Legrand"
CONTACT = "valentin.legrand@emse.fr"
LICENSE = "PolyForm Noncommercial 1.0.0"

from .analysis_zones import AnalysisZone, AnalysisZoneManager, points_in_zone
from .correction import (
    CorrectionError,
    CorrectionSettings,
    NoOverlapError,
    correct_experiment,
)
from .exporters import ExportError, ExportedFiles, export_batch, export_result
from .models import ColumnMapping, CorrectionResult, ExperimentData, FileInspection, FileProbe
from .projects import (
    ProjectDocument,
    ProjectError,
    ProjectValidationError,
    SourceFileRecord,
    load_project,
    save_project,
)
from .readers import (
    DataReadError,
    DetectedFileFormat,
    detect_file_format,
    inspect_file,
    load_experiment,
    probe_file,
)
from .zone_quantification import (
    HeatFlowZoneProfile,
    ZoneQuantification,
    heat_flow_zone_profile,
    quantify_zone,
)

__all__ = [
    "AnalysisZone",
    "AnalysisZoneManager",
    "ColumnMapping",
    "CorrectionError",
    "CorrectionResult",
    "CorrectionSettings",
    "DataReadError",
    "DetectedFileFormat",
    "ExperimentData",
    "ExportError",
    "ExportedFiles",
    "FileInspection",
    "FileProbe",
    "HeatFlowZoneProfile",
    "NoOverlapError",
    "ProjectDocument",
    "ProjectError",
    "ProjectValidationError",
    "SourceFileRecord",
    "ZoneQuantification",
    "correct_experiment",
    "detect_file_format",
    "export_batch",
    "export_result",
    "inspect_file",
    "heat_flow_zone_profile",
    "load_project",
    "load_experiment",
    "probe_file",
    "points_in_zone",
    "quantify_zone",
    "save_project",
]
