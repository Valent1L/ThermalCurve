"""Adaptateurs minimes entre Qt et le moteur scientifique existant."""

from __future__ import annotations

from atg_dsc_corrector.i18n import tr as _t
from atg_dsc_corrector.curve_styles import LINE_STYLES, MARKERS, mean_curve_style

from copy import deepcopy
from dataclasses import dataclass, replace
import math
from pathlib import Path
from typing import Iterable

from atg_dsc_corrector.correction import (
    CorrectionSettings,
    correct_experiment,
    uncorrected_experiment,
)
from atg_dsc_corrector.comparison import (
    COMPARISON_COLORS,
    ComparisonCurve,
    ComparisonOptions,
)
from atg_dsc_corrector.comparison_statistics import (
    GroupStatistics,
    RepeatGroup,
    calculate_group_statistics,
)
from atg_dsc_corrector.analysis_zones import AnalysisZone
from atg_dsc_corrector.exporters import ExportedFiles, _same_path, export_result
from atg_dsc_corrector.models import CorrectionResult, ExperimentData
from atg_dsc_corrector.plotting import PlotOptions
from atg_dsc_corrector.thermal_program import default_thermal_program, validate_thermal_program
from atg_dsc_corrector.normalization import (
    NormalizationError,
    NormalizationReferences,
    NormalizationSettings,
    apply_normalization,
    compute_references,
)
from atg_dsc_corrector.projects import (
    ModifiedHandler,
    MissingHandler,
    ProjectDocument,
    ProjectValidationError,
    SourceFileRecord,
    _validate_comparison,
    _validate_display,
    _validate_limit_pair,
    _validate_stoichiometry,
    load_project,
    new_project_document,
    reload_source,
    resolve_source,
    save_project,
)
from atg_dsc_corrector.readers import load_experiment
from atg_dsc_corrector.zone_quantification import (
    ZoneQuantification,
    quantify_zone,
)


class ScientificWorkflow:
    """État de la tranche Qt et délégation vers les fonctions métier."""

    def __init__(self) -> None:
        self.experiment: ExperimentData | None = None
        self.blank: ExperimentData | None = None
        self.result: CorrectionResult | None = None
        self.display_axis = "time_s"
        self.interpolation_axis = "time_s"

    def set_axes(
        self,
        *,
        display_axis: str | None = None,
        interpolation_axis: str | None = None,
    ) -> None:
        """Conserve les deux paramètres historiques, indépendamment de Qt."""

        supported_display = {
            "time_s",
            "time_min", "time_h",
            "furnace_temperature",
            "sample_temperature",
        }
        supported_interpolation = supported_display - {"time_min", "time_h"}
        if display_axis is not None:
            if display_axis not in supported_display:
                raise ValueError("Axe d'affichage inconnu.")
            self.display_axis = display_axis
        if interpolation_axis is not None:
            if interpolation_axis not in supported_interpolation:
                raise ValueError("Axe d'interpolation inconnu.")
            self.interpolation_axis = interpolation_axis

    def open_experiment(self, path: str | Path) -> ExperimentData:
        self.experiment = load_experiment(path)
        self.result = None
        return self.experiment

    def open_blank(self, path: str | Path) -> ExperimentData:
        self.blank = load_experiment(path)
        self.result = None
        return self.blank

    def process(self, settings: CorrectionSettings) -> CorrectionResult:
        if self.experiment is None:
            raise ValueError("Aucune expérience n'est chargée.")
        if self.blank is None:
            raise ValueError("Aucun blanc n'est chargé.")
        self.result = correct_experiment(self.experiment, self.blank, settings)
        return self.result

    def export_current(
        self,
        destination: str | Path,
        file_format: str,
        *,
        overwrite: bool = False,
    ) -> ExportedFiles:
        if self.result is None:
            raise ValueError("Aucun résultat traité n'est disponible pour l'export.")
        return export_result(
            self.result,
            destination,
            file_format,
            protected_paths=self.protected_paths(),
            overwrite=overwrite,
        )

    def protected_paths(self) -> tuple[Path, ...]:
        return tuple(
            source.source_path
            for source in (self.experiment, self.blank)
            if source is not None
        )


@dataclass(frozen=True)
class ProjectOpenState:
    """Résultat de l'ouverture, destiné à la présentation Qt."""

    warnings: tuple[str, ...]
    sources_changed: bool
    legacy_interpolation_axis_ignored: bool


class ProjectWorkflow(ScientificWorkflow):
    """Cycle de vie projet Qt délégué à l'API ``projects`` existante."""

    def __init__(self) -> None:
        super().__init__()
        self.project_path: Path | None = None
        self.project_document = new_project_document()
        self.project_document.comparison["title"] = self.project_document.comparison["graph"]["title"] = _t("Comparaison des expériences")
        self.project_document.normalization["tg_representation"] = "raw"
        self.project_dirty = False
        self.experiments: list[ExperimentData] = []
        self.base_result: CorrectionResult | None = None
        self._normalization_records: dict[int, dict[str, object]] = {}
        self._normalization_overrides: dict[int, dict[str, object]] = {}
        self._comparison_blanks: dict[int, ExperimentData | None] = {}
        self._comparison_base_results: dict[int, CorrectionResult] = {}
        self._comparison_results: dict[int, CorrectionResult] = {}

    def new_project(self) -> None:
        self.project_path = None
        self.project_document = new_project_document()
        self.project_document.comparison["title"] = self.project_document.comparison["graph"]["title"] = _t("Comparaison des expériences")
        self.project_document.normalization["tg_representation"] = "raw"
        self.project_dirty = False
        self.experiments = []
        self.experiment = None
        self.blank = None
        self.result = None
        self.base_result = None
        self.display_axis = "time_s"
        self.interpolation_axis = "time_s"
        self._normalization_records = {}
        self._normalization_overrides = {}
        self._comparison_blanks = {}
        self._comparison_base_results = {}
        self._comparison_results = {}

    def protected_paths(self) -> tuple[Path, ...]:
        paths = [experiment.source_path for experiment in self.experiments]
        paths.extend(
            blank.source_path
            for blank in self._comparison_blanks.values()
            if blank is not None
        )
        if self.blank is not None:
            paths.append(self.blank.source_path)
        if self.project_path is not None:
            paths.append(self.project_path)
        return tuple(dict.fromkeys(paths))

    def is_protected_path(self, path: str | Path) -> bool:
        return any(_same_path(path, protected) for protected in self.protected_paths())

    def mark_dirty(self) -> None:
        self.project_dirty = True

    def set_stoichiometry(self, value: dict[str, object]) -> None:
        checked = _validate_stoichiometry(value)
        if checked != self.project_document.stoichiometry:
            self.project_document.stoichiometry = checked
            self.mark_dirty()

    def set_axes(
        self,
        *,
        display_axis: str | None = None,
        interpolation_axis: str | None = None,
    ) -> None:
        previous_display = self.display_axis
        super().set_axes(
            display_axis=display_axis,
            interpolation_axis=interpolation_axis,
        )
        if display_axis is not None and display_axis != previous_display:
            self.project_document.display["x_axis"] = display_axis
            self.project_document.comparison["x_axis"] = display_axis
            self.mark_dirty()

    def set_visible_signals(self, signals: tuple[str, ...]) -> None:
        visible = list(signals)
        if visible != self.project_document.display["visible_signals"]:
            self.project_document.display["visible_signals"] = visible
            self.mark_dirty()

    def set_align_zeros(self, enabled: bool) -> None:
        values = {
            "align_zeros": bool(enabled),
            "alignment_mode": "zeros" if enabled else "none",
        }
        display = self.project_document.display
        if any(display.get(name) != value for name, value in values.items()):
            display.update(values)
            self.mark_dirty()

    def set_show_subtraction(self, visible: bool) -> None:
        if visible != self.project_document.display["show_subtraction"]:
            self.project_document.display["show_subtraction"] = visible
            self.mark_dirty()

    def set_main_graph_settings(
        self,
        *,
        graph: dict[str, object],
        limits: dict[str, list[float | None]],
        alignment_mode: str,
        thermal_program: dict | None = None,
    ) -> None:
        candidate = deepcopy(self.project_document.display)
        candidate["graph"] = deepcopy(graph)
        candidate["limits"] = deepcopy(limits)
        candidate["alignment_mode"] = alignment_mode
        candidate["align_zeros"] = alignment_mode == "zeros"
        checked = _validate_display(candidate)
        program = None if thermal_program is None else validate_thermal_program(thermal_program)
        if program is not None and self.experiment is None:
            raise ValueError(_t('Aucune expérience active.'))
        if checked != self.project_document.display:
            self.project_document.display = checked
            self.mark_dirty()
        if program is not None and program != self.active_thermal_program():
            index = next(i for i, experiment in enumerate(self.experiments) if experiment is self.experiment)
            self.comparison_record(index)["thermal_program"] = program
            self.mark_dirty()

    def active_thermal_program(self) -> dict:
        if self.experiment is None:
            return default_thermal_program()
        record = self.project_document.comparison["entries"].get(
            self.comparison_key(self.experiment), {}
        )
        return deepcopy(record.get("thermal_program", default_thermal_program()))

    def open_experiment(self, path: str | Path) -> ExperimentData:
        experiment = super().open_experiment(path)
        self.experiments = [experiment]
        self.base_result = None
        self._normalization_records = {}
        self._normalization_overrides = {
            id(experiment): deepcopy(self.project_document.normalization)
        }
        self._comparison_blanks = {id(experiment): self.blank}
        self._comparison_base_results = {}
        self._comparison_results = {}
        self._ensure_comparison_entry(experiment, 0)
        self.mark_dirty()
        return experiment

    def open_blank(self, path: str | Path) -> ExperimentData:
        blank = super().open_blank(path)
        if self.experiment is not None:
            self._comparison_blanks[id(self.experiment)] = blank
            self._invalidate_experiment(self.experiment)
        self.base_result = None
        self.mark_dirty()
        return blank

    def add_comparison_experiment(
        self, path: str | Path, *, inherit_blank: bool = True
    ) -> ExperimentData:
        """Ajoute une source sans remplacer les expériences déjà chargées."""

        source_path = Path(path)
        if any(
            _same_path(source_path, experiment.source_path)
            for experiment in self.experiments
        ):
            raise ProjectValidationError(
                f"L'expérience est déjà chargée : {source_path}."
            )
        self._ensure_unambiguous_comparison_names(
            [self.comparison_key(experiment) for experiment in self.experiments]
            + [source_path.name]
        )

        experiment = load_experiment(source_path)
        self.experiments.append(experiment)
        self._comparison_blanks[id(experiment)] = self.blank if inherit_blank else None
        self._normalization_overrides[id(experiment)] = deepcopy(
            self.project_document.normalization
        )
        self._ensure_comparison_entry(experiment, len(self.experiments) - 1)
        if self.experiment is None:
            self.activate_comparison_experiment(0)
        self.mark_dirty()
        return experiment

    def activate_comparison_experiment(self, index: int) -> ExperimentData:
        if not 0 <= index < len(self.experiments):
            raise IndexError("Expérience de comparaison inconnue.")
        experiment = self.experiments[index]
        self.experiment = experiment
        self.blank = self._comparison_blanks.get(id(experiment), self.blank)
        self.base_result = self._comparison_base_results.get(id(experiment))
        self.result = self._comparison_results.get(id(experiment), self.base_result)
        return experiment

    def remove_comparison_experiments(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            if not 0 <= row < len(self.experiments):
                continue
            experiment = self.experiments.pop(row)
            key = self.comparison_key(experiment)
            self.project_document.comparison["entries"].pop(key, None)
            identifier = id(experiment)
            self._normalization_records.pop(identifier, None)
            self._normalization_overrides.pop(identifier, None)
            self._comparison_blanks.pop(identifier, None)
            self._comparison_base_results.pop(identifier, None)
            self._comparison_results.pop(identifier, None)
        self._renumber_comparison_entries()
        if self.experiments:
            self.activate_comparison_experiment(min(rows or [0], default=0) % len(self.experiments))
        else:
            self.experiment = None
            self.base_result = self.result = None
        self.mark_dirty()

    def move_comparison_experiment(self, row: int, delta: int) -> int:
        target = row + delta
        if not (0 <= row < len(self.experiments) and 0 <= target < len(self.experiments)):
            return row
        self.experiments[row], self.experiments[target] = (
            self.experiments[target], self.experiments[row]
        )
        self._renumber_comparison_entries()
        self.mark_dirty()
        return target

    def open_project(
        self,
        path: str | Path,
        *,
        missing_handler: MissingHandler | None = None,
        modified_handler: ModifiedHandler | None = None,
    ) -> ProjectOpenState:
        """Charge complètement un projet sans muter l'état avant validation."""

        project_path = Path(path)
        document = load_project(project_path)
        self._ensure_unambiguous_comparison_names(
            source.name for source in document.experiments
        )
        experiments: list[ExperimentData] = []
        normalization_records: dict[int, dict[str, object]] = {}
        warnings = list(document.warnings)
        sources_changed = False
        normalization_by_source = {
            (
                record.get("source_name"),
                record.get("source_sha256"),
            ): record
            for record in document.normalization["experiments"]
        }

        for source in document.experiments:
            resolution = resolve_source(
                source,
                project_path,
                missing_handler=missing_handler,
                modified_handler=modified_handler,
            )
            if resolution.path is None:
                warnings.append(
                    f"Expérience ignorée à l'ouverture : {source.name} "
                    f"({source.absolute_path})."
                )
                sources_changed = True
                continue
            experiment = reload_source(source, resolution.path)
            experiments.append(experiment)
            record = normalization_by_source.get((source.name, source.sha256))
            if record is not None:
                normalization_records[id(experiment)] = deepcopy(record)
            if resolution.relocated:
                warnings.append(f"Source relocalisée : {source.name} → {resolution.path}.")
                sources_changed = True
            if resolution.modified:
                warnings.append(
                    f"Source modifiée acceptée : {source.name} ({resolution.path})."
                )
                sources_changed = True

        blank: ExperimentData | None = None
        if document.blank is not None:
            resolution = resolve_source(
                document.blank,
                project_path,
                missing_handler=missing_handler,
                modified_handler=modified_handler,
            )
            if resolution.path is None:
                warnings.append(
                    f"Blanc ignoré à l'ouverture : {document.blank.name} "
                    f"({document.blank.absolute_path})."
                )
                sources_changed = True
            else:
                blank = reload_source(document.blank, resolution.path)
                if resolution.relocated:
                    warnings.append(
                        f"Blanc relocalisé : {document.blank.name} → {resolution.path}."
                    )
                    sources_changed = True
                if resolution.modified:
                    warnings.append(
                        f"Blanc modifié accepté : {document.blank.name} "
                        f"({resolution.path})."
                    )
                    sources_changed = True

        legacy_axis = document.correction["interpolation_axis"] != "time_s"
        if legacy_axis:
            warnings.append(
                "L'axe d'interpolation historique a été ignoré ; "
                "la correction reste positionnelle, ligne par ligne."
            )
        legacy_method = document.correction["tg_method"] != "direct"
        if legacy_method:
            warnings.append(
                "La méthode de correction historique a été ignorée ; "
                "la soustraction du blanc reste positionnelle, ligne par ligne."
            )

        comparison_blanks: dict[int, ExperimentData | None] = {}
        normalization_overrides: dict[int, dict[str, object]] = {}
        comparison_entries = document.comparison["entries"]
        for index, experiment in enumerate(experiments):
            entry = comparison_entries.get(experiment.source_path.name, {})
            normalization_overrides[id(experiment)] = deepcopy(
                entry.get("normalization", document.normalization)
            )
            # Une absence explicite ne doit pas reprendre le blanc global historique.
            own_blank = None if "blank" in entry else blank
            blank_data = entry.get("blank")
            if blank_data is not None:
                blank_record = SourceFileRecord.from_dict(
                    blank_data,
                    f"comparison.entries.{experiment.source_path.name}.blank",
                )
                resolution = resolve_source(
                    blank_record,
                    project_path,
                    missing_handler=missing_handler,
                    modified_handler=modified_handler,
                )
                if resolution.path is None:
                    warnings.append(
                        f"Blanc de {experiment.source_path.name} ignoré : "
                        f"{blank_record.name}."
                    )
                    own_blank = None
                    sources_changed = True
                else:
                    own_blank = reload_source(blank_record, resolution.path)
                    if resolution.relocated or resolution.modified:
                        sources_changed = True
            comparison_blanks[id(experiment)] = own_blank
            self._ensure_comparison_entry_in(
                document.comparison, experiment, index
            )

        self.project_path = project_path
        self.project_document = document
        self.project_document.warnings = warnings
        self.experiments = experiments
        self.experiment = experiments[0] if experiments else None
        self.blank = (
            comparison_blanks.get(id(self.experiment), blank)
            if self.experiment is not None
            else blank
        )
        self.result = None
        self.base_result = None
        self.display_axis = document.display["x_axis"]
        self.interpolation_axis = "time_s"
        self.project_dirty = sources_changed or legacy_axis or legacy_method
        self._normalization_records = normalization_records
        self._normalization_overrides = normalization_overrides
        self._comparison_blanks = comparison_blanks
        self._comparison_base_results = {}
        self._comparison_results = {}
        return ProjectOpenState(tuple(warnings), sources_changed, legacy_axis)

    def process(
        self,
        settings: CorrectionSettings,
        *,
        show_subtraction: bool = True,
    ) -> CorrectionResult:
        positional_settings = CorrectionSettings(
            method="direct",
            interpolation_axis="time_s",
            time_relative_tolerance=settings.time_relative_tolerance,
            time_absolute_tolerance_s=settings.time_absolute_tolerance_s,
            temperature_tolerance_c=settings.temperature_tolerance_c,
        )
        if self.experiment is None:
            raise ValueError("Aucune expérience n'est chargée.")
        result = self._process_experiment(
            self.experiment,
            positional_settings,
            show_subtraction=show_subtraction,
        )
        self.base_result = result
        if self._normalization_is_active():
            record = self._normalization_records.get(id(result.experiment), {})
            manual_mass = record.get("manual_mass_mg")
            try:
                result = self.set_normalization(
                    self.normalization_settings(),
                    None if manual_mass is None else float(manual_mass),
                    mark_dirty=False,
                ) or result
            except NormalizationError as exc:
                raise ValueError(_t("Normalisation restaurée impossible : {error}", error=_t(str(exc)))) from exc
        self._comparison_results[id(self.experiment)] = result
        self.result = result
        return result

    def normalization_settings(self) -> NormalizationSettings:
        normalization = self.project_document.normalization
        if self.experiment is not None:
            normalization = self._normalization_overrides.get(
                id(self.experiment), normalization
            )
        return NormalizationSettings(
            reference_mode=normalization["heat_flow_reference_mode"],
            reference_axis=normalization["reference_axis"],
            range_start=normalization["range_start"],
            range_end=normalization["range_end"],
            tg_representation=normalization["tg_representation"],
            dtg_unit_mode=normalization["dtg_unit_mode"],
            dtg_representation=normalization["dtg_representation"],
            heat_flow_representation=normalization["heat_flow_representation"],
            normalization_enabled=normalization["normalization_enabled"],
            reference_mass_mg=normalization["reference_mass_mg"],
            reference_name=normalization["reference_name"],
            use_initial_mass_as_reference=normalization[
                "use_initial_mass_as_reference"
            ],
            calculate_dtg_if_missing=normalization.get(
                "calculate_dtg_if_missing",
                False,
            ),
            allow_missing_initial_mass=True,
            dtg_smoothing_points=normalization.get("dtg_smoothing_points", 1),
        )

    def _normalization_is_active(
        self,
        normalization: dict[str, object] | None = None,
    ) -> bool:
        if normalization is None:
            normalization = self.project_document.normalization
            if self.experiment is not None:
                normalization = self._normalization_overrides.get(
                    id(self.experiment), normalization
                )
        return bool(
            normalization["normalization_enabled"]
            or normalization["tg_representation"] != "raw"
            or normalization["dtg_unit_mode"] != "source"
            or normalization["dtg_representation"] != "raw"
            or normalization["heat_flow_representation"] != "raw"
            or normalization.get("calculate_dtg_if_missing", False)
        )

    def set_normalization(
        self,
        settings: NormalizationSettings,
        manual_mass_mg: float | None,
        *,
        mark_dirty: bool = True,
    ) -> CorrectionResult | None:
        """Persiste les choix et délègue tous les calculs à ``apply_normalization``."""

        normalization = self.project_document.normalization
        updated = {
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
        }
        active = self._normalization_is_active(updated)
        candidate_result = self.base_result
        references = None
        if candidate_result is not None and active:
            candidate_result, references = apply_normalization(
                candidate_result,
                settings,
                manual_mass_mg,
            )

        changed = any(normalization.get(key) != value for key, value in updated.items())
        if self.experiment is not None:
            changed = changed or self._normalization_records.get(id(self.experiment), {}).get('manual_mass_mg') != manual_mass_mg
        normalization.update(updated)
        if self.experiment is not None:
            override = self._normalization_overrides.setdefault(
                id(self.experiment), deepcopy(normalization)
            )
            override.update(updated)
            record = self._normalization_records.setdefault(id(self.experiment), {})
            record["manual_mass_mg"] = manual_mass_mg
            self._comparison_results.pop(id(self.experiment), None)
        if changed and mark_dirty:
            self.mark_dirty()
        if candidate_result is None:
            return None
        self.result = candidate_result
        if active and self.experiment is not None:
            self._comparison_results[id(self.experiment)] = candidate_result
        if references is not None and self.experiment is not None:
            self._store_references_for(
                self.experiment, references, manual_mass_mg
            )
        return candidate_result

    def _process_experiment(
        self,
        experiment: ExperimentData,
        settings: CorrectionSettings,
        *,
        show_subtraction: bool = True,
    ) -> CorrectionResult:
        identifier = id(experiment)
        blank = self._comparison_blanks.get(identifier, self.blank)
        if blank is None or not show_subtraction:
            return uncorrected_experiment(experiment)
        cached = self._comparison_base_results.get(identifier)
        if cached is not None:
            return cached
        result = correct_experiment(experiment, blank, settings)
        self._comparison_base_results[identifier] = result
        return result

    @staticmethod
    def comparison_key(experiment: ExperimentData) -> str:
        """Identifiant historique des entrées de comparaison."""

        return experiment.source_path.name

    @staticmethod
    def _ensure_unambiguous_comparison_names(names: Iterable[str]) -> None:
        seen: set[str] = set()
        for name in names:
            if name in seen:
                raise ProjectValidationError(
                    "Identité de comparaison ambiguë : plusieurs expériences "
                    f"portent le nom '{name}'. Renommez l'un des fichiers avant "
                    "de les charger ensemble."
                )
            seen.add(name)

    @staticmethod
    def _ensure_comparison_entry_in(
        comparison: dict[str, object], experiment: ExperimentData, order: int
    ) -> dict[str, object]:
        entries = comparison.setdefault("entries", {})
        key = ProjectWorkflow.comparison_key(experiment)
        record = entries.setdefault(key, {})
        defaults = {
            "selected": True,
            "visible": True,
            "legend_name": experiment.name or experiment.source_path.stem,
            "order": order,
            "line_style": ("-", "--", "-.", ":")[order % 4],
            "line_width": 1.4,
            "marker": "",
            "markevery": None,
            "y_offset": 0.0,
            "stage": "corrected",
        }
        for name, value in defaults.items():
            record.setdefault(name, value)
        return record

    def _ensure_comparison_entry(
        self, experiment: ExperimentData, order: int
    ) -> dict[str, object]:
        return self._ensure_comparison_entry_in(
            self.project_document.comparison, experiment, order
        )

    def _renumber_comparison_entries(self) -> None:
        for order, experiment in enumerate(self.experiments):
            self._ensure_comparison_entry(experiment, order)["order"] = order

    def comparison_record(self, row: int) -> dict[str, object]:
        experiment = self.experiments[row]
        return self._ensure_comparison_entry(experiment, row)

    def comparison_blank(self, row: int) -> ExperimentData | None:
        experiment = self.experiments[row]
        return self._comparison_blanks.get(id(experiment), self.blank)

    def comparison_available_signals(self, row: int) -> tuple[str, ...]:
        experiment = self.experiments[row]
        signals = {signal for signal in ("tg", "dtg", "heat_flow")
                   if getattr(experiment.mapping, signal) in experiment.data.columns}
        normalization = self._normalization_overrides.get(id(experiment), self.project_document.normalization)
        if normalization.get("calculate_dtg_if_missing", False) and "tg" in signals and "Temps_s" in experiment.data:
            signals.add("dtg")
        return tuple(signal for signal in ("tg", "dtg", "heat_flow") if signal in signals)

    def comparison_signal_settings(self, row: int, signal: str) -> dict[str, object]:
        record = self.comparison_record(row)
        key = self.comparison_key(self.experiments[row])
        return {
            **{name: record[name] for name in ("legend_name", "line_style", "line_width", "marker", "markevery", "y_offset")},
            "visible": True,
            "color": self.project_document.comparison["colors"].get(key, COMPARISON_COLORS[row % len(COMPARISON_COLORS)]),
            **record.get("signal_settings", {}).get(signal, {}),
        }

    def set_comparison_signal_settings(self, row: int, signal: str, changes: dict[str, object]) -> None:
        candidate = deepcopy(self.project_document.comparison)
        key = self.comparison_key(self.experiments[row])
        candidate["entries"][key].setdefault("signal_settings", {}).setdefault(signal, {}).update(changes)
        checked = _validate_comparison(candidate)
        if checked != self.project_document.comparison:
            self.project_document.comparison = checked
            self.mark_dirty()

    def mean_curve_settings(self, signal: str) -> dict[str, object]:
        return mean_curve_style(signal, self.project_document.comparison.get('mean_styles', {}))

    def set_mean_curve_settings(self, signals: Iterable[str], changes: dict[str, object]) -> None:
        candidate = deepcopy(self.project_document.comparison)
        for signal in signals:
            style = candidate.setdefault('mean_styles', {}).setdefault(signal, {})
            style.update(changes)
            if style.get('legend_name') == '':
                style.pop('legend_name')
        checked = _validate_comparison(candidate)
        if checked != self.project_document.comparison:
            self.project_document.comparison = checked
            self.mark_dirty()

    def set_comparison_value(self, row: int, name: str, value: object) -> None:
        if name not in {"visible", "legend_name", "stage"}:
            raise ValueError("Paramètre de comparaison inconnu.")
        if name == "stage" and value not in {"original", "corrected", "normalized"}:
            raise ValueError("Représentation de comparaison inconnue.")
        record = self.comparison_record(row)
        if name == "visible" and not record.get("selected", True):
            record["selected"] = True
            self.mark_dirty()
        if record.get(name) != value:
            record[name] = value
            self.mark_dirty()

    def set_comparison_style(
        self,
        rows: list[int],
        *,
        line_style: str,
        line_width: float,
        marker: str,
        markevery: int | None,
        y_offset: float,
    ) -> None:
        """Met à jour uniquement la présentation des expériences sélectionnées."""

        if line_style not in LINE_STYLES:
            raise ValueError("Style de ligne de comparaison inconnu.")
        if marker not in MARKERS:
            raise ValueError("Marqueur de comparaison inconnu.")
        if not math.isfinite(line_width) or not 0.1 <= line_width <= 10.0:
            raise ValueError(
                "L'épaisseur de ligne doit être comprise entre 0,1 et 10."
            )
        if markevery is not None and markevery <= 0:
            raise ValueError("L'espacement des marqueurs doit être strictement positif.")
        if not math.isfinite(y_offset):
            raise ValueError("Le décalage vertical doit être fini.")
        changed = False
        values = {
            "line_style": line_style,
            "line_width": float(line_width),
            "marker": marker,
            "markevery": markevery,
            "y_offset": float(y_offset),
        }
        for row in rows:
            record = self.comparison_record(row)
            for name, value in values.items():
                if record.get(name) != value:
                    record[name] = value
                    changed = True
        if changed:
            self.mark_dirty()

    def set_comparison_domain(self, domain_mode: str) -> None:
        if domain_mode not in {"union", "overlap"}:
            raise ValueError("Le domaine de comparaison est inconnu.")
        settings = self.project_document.comparison
        if settings.get("domain_mode") != domain_mode:
            settings["domain_mode"] = domain_mode
            self.mark_dirty()

    def set_comparison_signal(self, signal: str) -> None:
        self.set_comparison_signals((signal,))

    def set_comparison_signals(self, signals: Iterable[str]) -> None:
        selected = tuple(dict.fromkeys(signals))
        if not selected or any(
            signal not in {"tg", "dtg", "heat_flow"} for signal in selected
        ):
            raise ValueError("Sélectionnez au moins un signal de comparaison valide.")
        values = {"signal": selected[0], "signals": list(selected)}
        settings = self.project_document.comparison
        if any(settings.get(name) != value for name, value in values.items()):
            settings.update(values)
            settings["y_limits"] = list(settings["limits"][selected[0]])
            self.mark_dirty()

    def set_comparison_offsets(self, offsets: dict[str, float], *, signal: str | None = None, spacing: float | None = None) -> None:
        """Persiste des décalages calculés par le moteur de comparaison."""

        candidate = deepcopy(self.project_document.comparison)
        if signal is not None:
            candidate['stacking'] = {'signal': signal, 'spacing': spacing}
        else:
            candidate['stacking']['spacing'] = None
        for row, experiment in enumerate(self.experiments):
            identifier = self.comparison_key(experiment)
            if identifier not in offsets:
                continue
            value = float(offsets[identifier])
            if not math.isfinite(value):
                raise ValueError("Le décalage vertical doit être fini.")
            record = self._ensure_comparison_entry_in(candidate, experiment, row)
            if signal is not None:
                record.setdefault('signal_settings', {}).setdefault(signal, {})['y_offset'] = value
                continue
            for settings in record.get("signal_settings", {}).values():
                if "y_offset" in settings:
                    del settings["y_offset"]
            record["y_offset"] = value
        checked = _validate_comparison(candidate)
        if checked != self.project_document.comparison:
            self.project_document.comparison = checked
            self.mark_dirty()

    def set_comparison_display(
        self,
        *,
        domain_mode: str,
        title: str,
        grid: bool,
        show_offsets_in_legend: bool,
        x_limits: tuple[float | None, float | None],
        y_limits: tuple[float | None, float | None],
        align_zeros: bool = False,
    ) -> None:
        """Met à jour les réglages d'affichage déjà portés par le projet."""

        if domain_mode not in {"union", "overlap"}:
            raise ValueError("Le domaine de comparaison est inconnu.")
        try:
            checked_x = _validate_limit_pair(list(x_limits), "comparison.x_limits")
            checked_y = _validate_limit_pair(list(y_limits), "comparison.y_limits")
        except ProjectValidationError as exc:
            raise ValueError(str(exc)) from exc
        settings = self.project_document.comparison
        candidate = deepcopy(settings)
        candidate.update(
            {
                "domain_mode": domain_mode,
                "title": title.strip(),
                "grid": bool(grid),
                "align_zeros": bool(align_zeros),
                "show_offsets_in_legend": bool(show_offsets_in_legend),
                "x_limits": checked_x,
                "y_limits": checked_y,
            }
        )
        candidate["limits"]["x"] = checked_x
        candidate["limits"][str(candidate["signal"])] = checked_y
        candidate["graph"]["title"] = title.strip()
        candidate["graph"]["grid_major"] = bool(grid)
        checked = _validate_comparison(candidate)
        if checked != settings:
            self.project_document.comparison = checked
            self.mark_dirty()

    def set_comparison_graph_settings(
        self,
        *,
        graph: dict[str, object],
        limits: dict[str, list[float | None]],
        align_zeros: bool,
        show_offsets_in_legend: bool,
        rows: list[int],
        curve_changes: dict[str, object],
    ) -> None:
        candidate = deepcopy(self.project_document.comparison)
        candidate["graph"] = deepcopy(graph)
        candidate["limits"] = deepcopy(limits)
        candidate["title"] = str(graph["title"])
        candidate["grid"] = bool(graph["grid_major"])
        candidate["x_limits"] = list(limits["x"])
        candidate["y_limits"] = list(limits[str(candidate["signal"])])
        candidate["align_zeros"] = bool(align_zeros)
        candidate["show_offsets_in_legend"] = bool(show_offsets_in_legend)
        for row in rows:
            experiment = self.experiments[row]
            identifier = self.comparison_key(experiment)
            record = candidate["entries"][identifier]
            for name, value in curve_changes.items():
                if name == "color":
                    candidate["colors"][identifier] = value
                else:
                    record[name] = value
                for settings in record.get("signal_settings", {}).values():
                    settings.pop(name, None)
        checked = _validate_comparison(candidate)
        if checked != self.project_document.comparison:
            self.project_document.comparison = checked
            self.mark_dirty()


    def set_comparison_statistics(
        self,
        *,
        enabled: bool,
        display_mode: str,
        grid_method: str,
        manual_points: int,
    ) -> None:
        if display_mode not in {"mean", "mean_band", "mean_individual", "individual"}:
            raise ValueError("Mode d'affichage statistique inconnu.")
        if grid_method not in {"auto", "manual"}:
            raise ValueError("Méthode de grille statistique inconnue.")
        if manual_points < 2:
            raise ValueError("Le nombre de points doit être au moins égal à 2.")
        values = {
            "enabled": bool(enabled),
            "display_mode": display_mode,
            "grid_method": grid_method,
            "manual_points": int(manual_points),
            "show_mean": display_mode in {"mean", "mean_band", "mean_individual"},
            "show_band": display_mode == "mean_band",
            "show_individual": display_mode in {"mean_individual", "individual"},
        }
        settings = self.project_document.comparison["statistics"]
        if any(settings.get(name) != value for name, value in values.items()):
            settings.update(values)
            self.mark_dirty()

    def upsert_comparison_group(
        self, identifier: str | None, name: str, rows: list[int]
    ) -> str:
        name = name.strip()
        if not name or not rows:
            raise ValueError(
                "Renseignez le nom du groupe et sélectionnez ses expériences."
            )
        members = list(
            dict.fromkeys(self.comparison_key(self.experiments[row]) for row in rows)
        )
        groups = self.project_document.comparison["statistics"]["groups"]
        before = deepcopy(groups)
        if identifier is None:
            index = 1
            identifiers = {group["id"] for group in groups}
            while f"group-{index}" in identifiers:
                index += 1
            identifier = f"group-{index}"
            groups.append({"id": identifier, "name": name, "members": members})
        else:
            group = next(
                (group for group in groups if group["id"] == identifier), None
            )
            if group is None:
                raise ValueError("Le groupe de répétitions est introuvable.")
            group.update({"name": name, "members": members})
        for group in groups:
            if group["id"] != identifier:
                group["members"] = [
                    member for member in group["members"] if member not in members
                ]
        if groups != before:
            self.mark_dirty()
        return identifier

    def delete_comparison_group(self, identifier: str) -> None:
        settings = self.project_document.comparison["statistics"]
        groups = settings["groups"]
        remaining = [group for group in groups if group["id"] != identifier]
        if len(remaining) == len(groups):
            raise ValueError("Le groupe de répétitions est introuvable.")
        settings["groups"] = remaining
        self.mark_dirty()

    def comparison_statistics_data(
        self, curves: list[ComparisonCurve], options: ComparisonOptions
    ) -> list[GroupStatistics]:
        """Recalcule chaque signal coché pour l'affichage comme pour l'export."""
        settings = self.project_document.comparison["statistics"]
        return [
            calculate_group_statistics(
                curves,
                RepeatGroup("checked-experiments", _t("Moyenne des expériences cochées"),
                            tuple(curve.identifier for curve in curves if curve.for_signal(signal).visible)),
                replace(options, signal=signal),
                grid_method=settings["grid_method"],
                manual_points=settings["manual_points"],
            )
            for signal in options.signals
        ]

    def assign_blank_to_comparison(
        self, rows: list[int], blank: ExperimentData | None
    ) -> None:
        for row in rows:
            experiment = self.experiments[row]
            self._comparison_blanks[id(experiment)] = blank
            self._invalidate_experiment(experiment)
        if self.experiment is not None and self.experiment in self.experiments:
            active_row = self.experiments.index(self.experiment)
            if active_row in rows:
                self.blank = blank
        self.mark_dirty()

    def open_comparison_blank(
        self, path: str | Path, rows: list[int]
    ) -> ExperimentData:
        """Charge un blanc puis l'affecte uniquement aux lignes demandées."""

        blank = load_experiment(path)
        self.assign_blank_to_comparison(rows, blank)
        return blank

    def _invalidate_experiment(self, experiment: ExperimentData) -> None:
        identifier = id(experiment)
        self._comparison_base_results.pop(identifier, None)
        self._comparison_results.pop(identifier, None)
        if experiment is self.experiment:
            self.base_result = None
            self.result = None

    def comparison_plot_data(
        self,
        *,
        x_axis: str,
        signal: str | None = None,
        signals: Iterable[str] | None = None,
        persist_signals: bool = True,
    ) -> tuple[ComparisonOptions, list[ComparisonCurve], list[str]]:
        """Construit les courbes en déléguant correction et normalisation au moteur."""

        selected_signals = tuple(
            signals
            if signals is not None
            else (signal,)
            if signal is not None
            else self.project_document.comparison.get("signals", ("tg",))
        )
        if persist_signals:
            self.set_comparison_signals(selected_signals)
        settings = self.project_document.comparison
        curves: list[ComparisonCurve] = []
        warnings: list[str] = []
        positional = CorrectionSettings(method="direct", interpolation_axis="time_s")
        for row, experiment in enumerate(self.experiments):
            record = self.comparison_record(row)
            if not bool(record["selected"] and record["visible"]):
                continue
            try:
                stage = str(record.get("stage", "corrected"))
                blank = self.comparison_blank(row)
                base = self._process_experiment(
                    experiment,
                    positional,
                    show_subtraction=stage != "original" and (
                        stage != "normalized" or record.get("show_subtraction", True)
                    ),
                )
                effective_stage = stage
                if blank is None and stage == "corrected":
                    effective_stage = "original"
                    warnings.append(
                        f"{experiment.source_path.name} : aucun blanc associé, "
                        "courbe originale affichée."
                    )
                result = base
                normal = self._settings_for_experiment(experiment)
                if effective_stage == "normalized":
                    cached = self._comparison_results.get(id(experiment))
                    cached_base_parameters = (
                        None
                        if cached is None
                        else {
                            name: value
                            for name, value in cached.parameters.items()
                            if name != "normalization"
                        }
                    )
                    if (
                        cached is None
                        or "normalization" not in cached.parameters
                        or cached.experiment is not base.experiment
                        or cached.blank is not base.blank
                        or cached.method != base.method
                        or cached_base_parameters != base.parameters
                    ):
                        manual = self._normalization_records.get(id(experiment), {}).get(
                            "manual_mass_mg"
                        )
                        cached, references = apply_normalization(
                            base,
                            normal,
                            None if manual is None else float(manual),
                        )
                        self._comparison_results[id(experiment)] = cached
                        self._store_references_for(experiment, references, manual)
                    result = cached
                plot_options = PlotOptions(
                    x_axis=x_axis,
                    signals=selected_signals,
                    tg_representation=(
                        normal.tg_representation
                        if effective_stage == "normalized"
                        else "raw"
                    ),
                    dtg_representation=(
                        normal.dtg_representation
                        if effective_stage == "normalized"
                        else "raw"
                    ),
                    heat_flow_representation=(
                        normal.heat_flow_representation
                        if effective_stage == "normalized"
                        else "raw"
                    ),
                    reference_name=normal.reference_name if effective_stage == "normalized" else "",
                    graph_settings=settings["graph"],
                )
                stage_label = {
                    "original": "original",
                    "corrected": _t("corrigé"),
                    "normalized": _t("normalisé"),
                }[effective_stage]
                curves.append(
                    ComparisonCurve(
                        identifier=self.comparison_key(experiment),
                        result=result,
                        legend_name=f"{record['legend_name']} - {stage_label}",
                        visible=True,
                        line_style=str(record["line_style"]),
                        line_width=float(record["line_width"]),
                        marker=str(record["marker"]),
                        markevery=record["markevery"],
                        y_offset=float(record["y_offset"]),
                        signal_settings=deepcopy(record.get("signal_settings", {})),
                        stage=effective_stage,
                        plot_options=plot_options,
                    )
                )
            except (ValueError, NormalizationError) as exc:
                warnings.append(str(exc))
        curves.sort(
            key=lambda curve: int(
                settings["entries"][curve.identifier].get("order", 0)
            )
        )
        options = ComparisonOptions(
            signal=selected_signals[0],
            signals=selected_signals,
            plot_options=PlotOptions(x_axis=x_axis, signals=selected_signals),
            domain_mode="union",
            x_limits=tuple(settings["limits"]["x"]),
            y_limits=tuple(settings["y_limits"]),
            y_limits_by_signal={
                signal: tuple(settings["limits"][signal])
                for signal in ("tg", "dtg", "heat_flow")
            },
            title=str(settings["graph"]["title"]),
            grid=bool(settings["graph"]["grid_major"]),
            align_zeros=bool(settings.get("align_zeros", False)),
            colors=dict(settings["colors"]),
            show_offsets_in_legend=bool(settings["show_offsets_in_legend"]),
            graph_settings=settings["graph"],
            mean_styles=deepcopy(settings.get('mean_styles', {})),
        )
        return options, curves, warnings

    def _settings_for_experiment(
        self, experiment: ExperimentData
    ) -> NormalizationSettings:
        previous = self.experiment
        self.experiment = experiment
        try:
            return self.normalization_settings()
        finally:
            self.experiment = previous

    def _store_references_for(
        self,
        experiment: ExperimentData,
        references: NormalizationReferences,
        manual_mass: object,
    ) -> None:
        values = references.as_dict()
        self._normalization_records.setdefault(id(experiment), {}).update(
            {
                "manual_mass_mg": manual_mass,
                "m0_mg": values["m0_mg"],
                "m_ref_mg": values["m_ref_mg"],
                "mass_source": values["mass_source"],
                "normalization_mass_source": values["normalization_mass_source"],
                "tg_reference": values["tg_reference"],
                "heat_flow_reference_mw": values["heat_flow_reference_mw"],
            }
        )

    def quantify_analysis_zone(
        self,
        zone: AnalysisZone,
        *,
        curve: ComparisonCurve | None = None,
    ) -> tuple[ZoneQuantification, str | None]:
        """Adapte l'état Qt vers le moteur de quantification existant."""

        result = curve.result if curve is not None else self.result
        if result is None:
            raise ValueError("Aucun résultat traité n'est disponible.")
        reference_source = result if curve is not None else self.base_result or result
        references, reference_error = self.zone_references(reference_source)
        settings = self._settings_for_experiment(result.experiment)
        quantified = quantify_zone(
            result,
            zone,
            references,
            heat_flow_representation=(
                curve.plot_options.heat_flow_representation
                if curve is not None and curve.plot_options is not None
                else settings.heat_flow_representation
            ),
            signal_stage=curve.stage if curve is not None else "working",
        )
        return quantified, reference_error

    def zone_references(self, result):
        """Keep TG mass references available even if an unrelated normalization fails."""
        experiment = result.experiment
        settings = self._settings_for_experiment(experiment)
        manual_mass = self._normalization_records.get(id(experiment), {}).get("manual_mass_mg")
        try:
            return compute_references(result, settings, manual_mass), None
        except (NormalizationError, TypeError, ValueError) as exc:
            try:
                basic = replace(settings, reference_mode="first_valid", tg_representation="raw",
                                heat_flow_representation="raw", normalization_enabled=False,
                                use_initial_mass_as_reference=False, allow_missing_initial_mass=True)
                return compute_references(result, basic, manual_mass), str(exc)
            except (NormalizationError, TypeError, ValueError):
                return None, str(exc)

    def document_for_save(
        self,
        project_path: str | Path,
        *,
        visible_signals: tuple[str, ...],
        modified_handler: ModifiedHandler | None = None,
    ) -> ProjectDocument:
        """Reconstruit les seules références de sources via l'API projet."""

        target = Path(project_path)
        source_records: dict[int, SourceFileRecord] = {}

        def source_record(experiment: ExperimentData) -> SourceFileRecord:
            identifier = id(experiment)
            cached = source_records.get(identifier)
            if cached is not None:
                return cached
            record = SourceFileRecord.from_experiment(experiment, target)
            resolution = resolve_source(
                record,
                target,
                modified_handler=modified_handler,
            )
            if resolution.path is None:
                raise ProjectValidationError(
                    f"La source chargée ne peut pas être enregistrée : {record.name}."
                )
            if resolution.relocated:
                record = SourceFileRecord.from_experiment(
                    experiment,
                    target,
                    source_path=resolution.path,
                )
            source_records[identifier] = record
            return record

        experiments = [source_record(experiment) for experiment in self.experiments]
        blank = (
            None
            if self.blank is None
            else source_record(self.blank)
        )
        normalization = deepcopy(self.project_document.normalization)
        normalization_experiments = []
        for experiment, source in zip(self.experiments, experiments, strict=True):
            record = deepcopy(self._normalization_records.get(id(experiment), {}))
            record.update(
                {
                    "source_name": source.name,
                    "source_sha256": source.sha256,
                    "manual_mass_mg": record.get("manual_mass_mg"),
                    "m0_mg": record.get("m0_mg"),
                    "m_ref_mg": record.get("m_ref_mg"),
                    "mass_source": record.get("mass_source"),
                    "normalization_mass_source": record.get(
                        "normalization_mass_source"
                    ),
                    "tg_reference": record.get("tg_reference"),
                    "heat_flow_reference_mw": record.get(
                        "heat_flow_reference_mw"
                    ),
                }
            )
            normalization_experiments.append(record)
        normalization["experiments"] = normalization_experiments
        comparison = deepcopy(self.project_document.comparison)
        for order, experiment in enumerate(self.experiments):
            record = self._ensure_comparison_entry_in(
                comparison, experiment, order
            )
            own_blank = self._comparison_blanks.get(id(experiment), self.blank)
            record["blank"] = (
                None
                if own_blank is None
                else source_record(own_blank).to_dict()
            )
            own_normalization = deepcopy(
                self._normalization_overrides.get(
                    id(experiment), self.project_document.normalization
                )
            )
            own_normalization["experiments"] = []
            record["normalization"] = own_normalization
            record["correction"] = {
                "tg_method": "direct",
                "interpolation_axis": "time_s",
            }
        display = deepcopy(self.project_document.display)
        display["x_axis"] = self.display_axis
        display["visible_signals"] = list(visible_signals)
        return ProjectDocument(
            schema_version=self.project_document.schema_version,
            app_version=self.project_document.app_version,
            project_name=self.project_document.project_name,
            created_at=self.project_document.created_at,
            modified_at=self.project_document.modified_at,
            experiments=experiments,
            blank=blank,
            correction={
                "tg_method": "direct",
                "interpolation_axis": "time_s",
            },
            display=display,
            normalization=normalization,
            quality_control=deepcopy(self.project_document.quality_control),
            comparison=comparison,
            analysis_zones=list(self.project_document.analysis_zones),
            stoichiometry=deepcopy(self.project_document.stoichiometry),
            processing_history=list(self.project_document.processing_history),
            warnings=list(self.project_document.warnings),
        )

    def save_project(
        self,
        path: str | Path,
        *,
        visible_signals: tuple[str, ...],
        modified_handler: ModifiedHandler | None = None,
    ) -> ProjectDocument:
        target = Path(path)
        document = self.document_for_save(
            target,
            visible_signals=visible_signals,
            modified_handler=modified_handler,
        )
        document.project_name = target.stem
        self.project_document = save_project(document, target)
        self.project_path = target
        self.project_dirty = False
        return self.project_document
