"""Contrôles Qt des représentations calculées par le moteur de normalisation."""

from __future__ import annotations

from atg_dsc_corrector.i18n import tr as _t

import math
from typing import Any

from PySide6.QtCore import QLocale, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QWidget,
)

from atg_dsc_corrector.normalization import NormalizationSettings


TG_CHOICES = (
    (_t('TG originale'), "raw"),
    ("Δm, t₀ = 0 (mg)", "delta_m_mg"),
    ("Δm / m₀ (%)", "delta_m_pct"),
    (_t('Masse restante (mg)'), "remaining_mass_mg"),
    (_t('Masse résiduelle (%)'), "residual_mass_pct"),
    ("Δm / mᵣₑf (mg·mg⁻¹)", "normalized_mg_mg"),
    ("Δm / mᵣₑf (%)", "normalized_pct"),
)

DTG_UNIT_OPTIONS = (
    (_t('Source'), "source"),
    ("min⁻¹", "per_minute"),
    ("s⁻¹", "per_second"),
)

DTG_REPRESENTATION_CHOICES = (
    (_t('dTG originale'), "raw"),
    (_t('dTG normalisée par masse'), "per_mass"),
    (_t('dTG relative (%)'), "percent"),
)

HEAT_FLOW_CHOICES = (
    (_t('Original (mW)'), "raw"),
    (_t('Remis à zéro (mW)'), "zero_mw"),
    ("W", "w"),
    (_t('Remis à zéro (W)'), "zero_w"),
    ("mW·mg⁻¹", "mw_mg"),
    (_t('Remis à zéro (mW·mg⁻¹)'), "zero_mw_mg"),
    ("W·g⁻¹", "w_g"),
    (_t('Remis à zéro (W·g⁻¹)'), "zero_w_g"),
    ("W·mg⁻¹", "w_mg"),
    (_t('Remis à zéro (W·mg⁻¹)'), "zero_w_mg"),
)

REFERENCE_MODE_CHOICES = (
    (_t('Premier point valide'), "first_valid"),
    (_t('Moyenne sur une plage'), "range_mean"),
)

REFERENCE_AXIS_CHOICES = (
    (_t('Temps (s)'), "time_s"),
    (_t('Température du four'), "furnace_temperature"),
    (_t("Température de l'échantillon"), "sample_temperature"),
)

MASS_NORMALIZED_TG = {"normalized_mg_mg", "normalized_pct"}
MASS_NORMALIZED_HEAT = {
    "mw_mg",
    "zero_mw_mg",
    "w_g",
    "zero_w_g",
    "w_mg",
    "zero_w_mg",
}
ZEROED_HEAT = {"zero_mw", "zero_w", "zero_mw_mg", "zero_w_g", "zero_w_mg"}


def _combo(choices: tuple[tuple[str, str], ...], accessible_name: str) -> QComboBox:
    combo = QComboBox()
    combo.setAccessibleName(accessible_name)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    for text, value in choices:
        combo.addItem(text, value)
    return combo


def _optional_number(
    text: str,
    field_name: str,
    *,
    positive: bool = False,
    number_locale: QLocale | None = None,
) -> float | None:
    stripped = text.strip()
    if not stripped:
        return None
    value, valid = (number_locale or QLocale()).toDouble(stripped)
    if not valid:
        try:
            value = float(stripped.replace(",", "."))
        except ValueError as exc:
            raise ValueError(_t('{v0} doit être une valeur numérique.', v0=field_name)) from exc
    if not math.isfinite(value):
        raise ValueError(_t('{v0} doit être une valeur finie.', v0=field_name))
    if positive and value <= 0.0:
        raise ValueError(_t('{v0} doit être strictement positive.', v0=field_name))
    return value


class NormalizationPanel(QGroupBox):
    """Groupe défilable qui traduit les choix Qt en modèle métier existant."""

    changed = Signal()
    pending_changed = Signal()

    def __init__(self) -> None:
        super().__init__(_t('Normalisation'))
        self.setObjectName("normalizationGroup")
        self._heat_flow_visible = True
        self._experiment_loaded = False
        self._initial_mass_mg: float | None = None
        self._initial_mass_source: str | None = None
        self.number_locale = QLocale()
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        layout.setVerticalSpacing(8)
        self._layout = layout

        self.tg_combo = _combo(TG_CHOICES, _t('Mode de représentation TG'))
        self.tg_combo.setObjectName("tgRepresentationCombo")
        layout.addRow("TG", self.tg_combo)

        dtg_units = QWidget()
        dtg_units_layout = QHBoxLayout(dtg_units)
        dtg_units_layout.setContentsMargins(0, 0, 0, 0)
        dtg_units_layout.setSpacing(8)
        dtg_units_layout.addWidget(QLabel(_t('Unité :')))
        self.dtg_unit_group = QButtonGroup(self)
        self.dtg_unit_group.setExclusive(True)
        self.dtg_unit_checks: dict[str, QCheckBox] = {}
        for text, value in DTG_UNIT_OPTIONS:
            checkbox = QCheckBox(text)
            checkbox.setAccessibleName(_t('Unité temporelle dTG : {v1}', v1=text))
            self.dtg_unit_group.addButton(checkbox)
            self.dtg_unit_checks[value] = checkbox
            dtg_units_layout.addWidget(checkbox)
        self.dtg_unit_checks["source"].setChecked(True)
        dtg_units_layout.addStretch(1)
        layout.addRow("dTG", dtg_units)

        self.dtg_combo = _combo(
            DTG_REPRESENTATION_CHOICES,
            _t('Mode de représentation dTG'),
        )
        self.dtg_combo.setObjectName("dtgRepresentationCombo")
        layout.addRow("", self.dtg_combo)

        self.calculate_dtg_checkbox = QCheckBox(_t('Calculer dTG si elle est absente'))
        self.calculate_dtg_checkbox.setObjectName("calculateDtgCheckBox")
        layout.addRow(self.calculate_dtg_checkbox)

        self.heat_flow_combo = _combo(
            HEAT_FLOW_CHOICES,
            _t('Mode de représentation Flux de chaleur'),
        )
        self.heat_flow_combo.setObjectName("heatFlowRepresentationCombo")
        layout.addRow(_t('Flux de chaleur'), self.heat_flow_combo)

        self.initial_mass_entry = QLineEdit()
        self.initial_mass_entry.setObjectName("initialMassEntry")
        self.initial_mass_entry.setAccessibleName(_t('Masse initiale m0 en mg'))
        self.initial_mass_entry.setPlaceholderText(_t('Facultative, remplace les métadonnées'))
        initial_mass_validator = QDoubleValidator(0.0, 1.0e300, 12, self)
        initial_mass_validator.setLocale(self.number_locale)
        initial_mass_validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        self.initial_mass_entry.setValidator(initial_mass_validator)
        layout.addRow(_t('Masse initiale m₀ (mg)'), self.initial_mass_entry)

        self.initial_mass_provenance_label = QLabel()
        self.initial_mass_provenance_label.setObjectName("initialMassProvenance")
        self.initial_mass_provenance_label.setAccessibleName(
            _t('Provenance de la masse initiale m0')
        )
        self.initial_mass_provenance_label.setProperty("secondary", True)
        self.initial_mass_provenance_label.setWordWrap(True)
        layout.addRow(self.initial_mass_provenance_label)

        self.use_initial_mass_checkbox = QCheckBox(
            _t('Utiliser m₀ comme masse de référence')
        )
        self.use_initial_mass_checkbox.setObjectName("useInitialMassAsReferenceCheckBox")
        self.use_initial_mass_checkbox.setAccessibleName(
            _t('Utiliser la masse initiale m0 comme masse de référence')
        )
        layout.addRow(self.use_initial_mass_checkbox)

        self.reference_mass_entry = QLineEdit()
        self.reference_mass_entry.setObjectName("referenceMassEntry")
        self.reference_mass_entry.setAccessibleName(_t('Masse de normalisation m ref en mg'))
        self.reference_mass_entry.setPlaceholderText(_t('Facultative, en mg'))
        reference_mass_validator = QDoubleValidator(0.0, 1.0e300, 12, self)
        reference_mass_validator.setLocale(self.number_locale)
        reference_mass_validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        self.reference_mass_entry.setValidator(reference_mass_validator)
        layout.addRow(_t('Masse de normalisation mᵣₑf (mg)'), self.reference_mass_entry)

        self.reference_name_entry = QLineEdit()
        self.reference_name_entry.setObjectName("referenceNameEntry")
        self.reference_name_entry.setAccessibleName(_t('Nom de la référence'))
        self.reference_name_entry.setPlaceholderText(
            _t('Obligatoire avec une m_ref personnalisée')
        )
        layout.addRow(_t('Nom de la référence'), self.reference_name_entry)

        self.reference_mode_combo = _combo(
            REFERENCE_MODE_CHOICES,
            _t('Référence zéro du Flux de chaleur'),
        )
        self.reference_mode_combo.setObjectName("heatFlowReferenceModeCombo")
        layout.addRow(_t('Zéro Flux de chaleur'), self.reference_mode_combo)

        self.reference_axis_combo = _combo(
            REFERENCE_AXIS_CHOICES,
            _t('Axe de la plage Flux de chaleur'),
        )
        self.reference_axis_combo.setObjectName("heatFlowReferenceAxisCombo")
        layout.addRow(_t('Axe de la plage'), self.reference_axis_combo)

        self.range_start_entry = QLineEdit()
        self.range_start_entry.setObjectName("heatFlowRangeStartEntry")
        self.range_start_entry.setAccessibleName(_t('Début de la plage Flux de chaleur'))
        self.range_end_entry = QLineEdit()
        self.range_end_entry.setObjectName("heatFlowRangeEndEntry")
        self.range_end_entry.setAccessibleName(_t('Fin de la plage Flux de chaleur'))
        layout.addRow(_t('Début de plage'), self.range_start_entry)
        layout.addRow(_t('Fin de plage'), self.range_end_entry)

        self.unit_hint = QLabel()
        self.unit_hint.setObjectName("normalizationUnitHint")
        self.unit_hint.setProperty("secondary", True)
        self.unit_hint.setWordWrap(True)
        layout.addRow(self.unit_hint)

        self.validation_label = QLabel()
        self.validation_label.setObjectName("normalizationValidation")
        self.validation_label.setProperty("error", True)
        self.validation_label.setWordWrap(True)
        self.validation_label.hide()
        layout.addRow(self.validation_label)

        for combo in (
            self.tg_combo,
            self.dtg_combo,
            self.heat_flow_combo,
            self.reference_mode_combo,
            self.reference_axis_combo,
        ):
            combo.currentIndexChanged.connect(self._controls_changed)
        self.dtg_unit_group.buttonToggled.connect(
            lambda _button, checked: checked and self._controls_changed()
        )
        self.calculate_dtg_checkbox.toggled.connect(self._controls_changed)
        self.use_initial_mass_checkbox.toggled.connect(self._controls_changed)
        for entry in (
            self.initial_mass_entry,
            self.reference_mass_entry,
            self.reference_name_entry,
            self.range_start_entry,
            self.range_end_entry,
        ):
            entry.textEdited.connect(self._text_edited)
            entry.editingFinished.connect(self._controls_changed)
        self._update_visibility()

    def _text_edited(self, _text: str) -> None:
        if self.sender() is self.initial_mass_entry:
            self._update_mass_provenance()
            self._update_visibility()
        self.pending_changed.emit()

    def _controls_changed(self, *_args: Any) -> None:
        self.clear_validation()
        self._update_mass_provenance()
        self._update_visibility()
        self.changed.emit()

    def _update_visibility(self) -> None:
        tg_mode = str(self.tg_combo.currentData())
        dtg_representation = str(self.dtg_combo.currentData())
        heat_mode = (
            str(self.heat_flow_combo.currentData())
            if self._heat_flow_visible
            else "raw"
        )
        reference_mass_visible = bool(
            tg_mode in MASS_NORMALIZED_TG
            or dtg_representation != "raw"
            or heat_mode in MASS_NORMALIZED_HEAT
        )
        initial_mass_required = bool(
            tg_mode in {"delta_m_pct", "remaining_mass_mg", "residual_mass_pct"}
            or reference_mass_visible
        )
        initial_mass_visible = bool(
            initial_mass_required
            or (
                self._experiment_loaded
                and (
                    self._initial_mass_source != "metadata"
                    or bool(self.initial_mass_entry.text().strip())
                )
            )
        )
        name_visible = reference_mass_visible
        zero_visible = heat_mode in ZEROED_HEAT
        range_visible = (
            zero_visible and self.reference_mode_combo.currentData() == "range_mean"
        )
        self._layout.setRowVisible(self.heat_flow_combo, self._heat_flow_visible)
        self._layout.setRowVisible(self.initial_mass_entry, initial_mass_visible)
        self._layout.setRowVisible(
            self.initial_mass_provenance_label, self._experiment_loaded
        )
        self._layout.setRowVisible(
            self.use_initial_mass_checkbox, reference_mass_visible
        )
        self._layout.setRowVisible(self.reference_mass_entry, reference_mass_visible)
        self.reference_mass_entry.setEnabled(
            not self.use_initial_mass_checkbox.isChecked()
        )
        self._layout.setRowVisible(self.reference_name_entry, name_visible)
        self._layout.setRowVisible(self.reference_mode_combo, zero_visible)
        self._layout.setRowVisible(self.reference_axis_combo, range_visible)
        self._layout.setRowVisible(self.range_start_entry, range_visible)
        self._layout.setRowVisible(self.range_end_entry, range_visible)
        self.unit_hint.setText(self._unit_hint_text(tg_mode, dtg_representation, heat_mode))

    def _update_mass_provenance(self) -> None:
        if not self._experiment_loaded:
            self.initial_mass_provenance_label.clear()
            return
        if self.initial_mass_entry.text().strip():
            text = _t('Provenance m₀ : saisie utilisateur.')
        elif self._initial_mass_source == "metadata":
            value = self._number_text(self._initial_mass_mg)
            suffix = f" ({value} mg)" if value else ""
            text = _t('Provenance m₀ : métadonnées{v1}.', v1=suffix)
        elif self._initial_mass_source == "legacy":
            value = self._number_text(self._initial_mass_mg)
            suffix = f" ({value} mg)" if value else ""
            text = _t('Provenance m₀ : projet antérieur (legacy){v1}.', v1=suffix)
        elif self._initial_mass_source == "invalid":
            text = _t('Provenance m₀ : métadonnées invalides.')
        elif self._initial_mass_source == "manual":
            text = _t('Provenance m₀ : saisie utilisateur enregistrée.')
        elif self._initial_mass_source == "absent":
            text = _t('Provenance m₀ : absente.')
        else:
            text = _t('Provenance m₀ : indéterminée.')
        self.initial_mass_provenance_label.setText(text)

    def set_heat_flow_visible(self, visible: bool) -> None:
        """Adapte le panneau sans modifier les réglages Flux de chaleur mémorisés."""

        self._heat_flow_visible = visible
        self._update_visibility()

    def _dtg_unit_mode(self) -> str:
        return next(
            (
                mode
                for mode, checkbox in self.dtg_unit_checks.items()
                if checkbox.isChecked()
            ),
            "source",
        )

    def _unit_hint_text(
        self,
        tg_mode: str,
        dtg_representation: str,
        heat_mode: str,
    ) -> str:
        units: list[str] = []
        if tg_mode == "normalized_mg_mg":
            units.append("TG : mg·mg⁻¹")
        elif tg_mode in {"delta_m_pct", "residual_mass_pct", "normalized_pct"}:
            units.append("TG : %")
        elif tg_mode != "raw":
            units.append("TG : mg")
        dtg_unit_mode = self._dtg_unit_mode()
        if dtg_representation == "per_mass":
            if dtg_unit_mode == "per_minute":
                units.append("dTG : mg·min⁻¹·mg⁻¹")
            elif dtg_unit_mode == "per_second":
                units.append("dTG : mg·s⁻¹·mg⁻¹")
            else:
                units.append(_t('dTG : unité source·mg⁻¹'))
        elif dtg_representation == "percent":
            if dtg_unit_mode == "per_minute":
                units.append("dTG : %·min⁻¹")
            elif dtg_unit_mode == "per_second":
                units.append("dTG : %·s⁻¹")
            else:
                units.append(_t('dTG : % par unité source'))
        elif dtg_unit_mode == "per_minute":
            units.append("dTG : mg·min⁻¹")
        elif dtg_unit_mode == "per_second":
            units.append("dTG : mg·s⁻¹")
        heat_units = {
            "mw_mg": "mW·mg⁻¹",
            "zero_mw_mg": "mW·mg⁻¹",
            "w_g": "W·g⁻¹",
            "zero_w_g": "W·g⁻¹",
            "w_mg": "W·mg⁻¹",
            "zero_w_mg": "W·mg⁻¹",
        }
        if heat_mode in heat_units:
            units.append(_t('Flux de chaleur : {v1}', v1=heat_units[heat_mode]))
        return _t('Unités actives : ') + (" ; ".join(units) if units else _t('unités sources'))

    def values(self) -> tuple[NormalizationSettings, float | None]:
        manual_mass = _optional_number(
            self.initial_mass_entry.text(),
            _t('La masse initiale m0'),
            positive=True,
            number_locale=self.number_locale,
        )
        range_start = None
        range_end = None
        reference_mode = str(self.reference_mode_combo.currentData())
        if reference_mode == "range_mean":
            range_start = _optional_number(
                self.range_start_entry.text(),
                _t('Le début de plage'),
                number_locale=self.number_locale,
            )
            range_end = _optional_number(
                self.range_end_entry.text(),
                _t('La fin de plage'),
                number_locale=self.number_locale,
            )
        dtg_unit_mode = self._dtg_unit_mode()
        dtg_representation = str(self.dtg_combo.currentData())
        tg_representation = str(self.tg_combo.currentData())
        heat_flow_representation = str(self.heat_flow_combo.currentData())
        normalization_enabled = bool(
            tg_representation in MASS_NORMALIZED_TG
            or dtg_representation != "raw"
            or heat_flow_representation in MASS_NORMALIZED_HEAT
        )
        use_initial_mass = bool(
            normalization_enabled and self.use_initial_mass_checkbox.isChecked()
        )
        reference_mass = None
        if not use_initial_mass:
            reference_mass = _optional_number(
                self.reference_mass_entry.text(),
                _t('La masse de normalisation m_ref'),
                positive=True,
                number_locale=self.number_locale,
            )
        reference_name = self.reference_name_entry.text().strip()
        if (
            normalization_enabled
            and not use_initial_mass
            and reference_mass is not None
            and not reference_name
        ):
            raise ValueError(
                _t('Le nom de la référence m_ref est obligatoire avec une masse de normalisation personnalisée.')
            )
        settings = NormalizationSettings(
            reference_mode=reference_mode,
            reference_axis=str(self.reference_axis_combo.currentData()),
            range_start=range_start,
            range_end=range_end,
            tg_representation=tg_representation,
            dtg_unit_mode=dtg_unit_mode,
            dtg_representation=dtg_representation,
            heat_flow_representation=heat_flow_representation,
            normalization_enabled=normalization_enabled,
            reference_mass_mg=reference_mass,
            reference_name=reference_name,
            use_initial_mass_as_reference=use_initial_mass,
            calculate_dtg_if_missing=self.calculate_dtg_checkbox.isChecked(),
            allow_missing_initial_mass=True,
        )
        return settings, manual_mass

    def restore(
        self,
        normalization: dict[str, Any],
        *,
        manual_mass_mg: float | None = None,
        initial_mass_mg: float | None = None,
        mass_source: str | None = None,
        experiment_loaded: bool = False,
    ) -> None:
        self.blockSignals(True)
        try:
            self._experiment_loaded = experiment_loaded
            self._initial_mass_mg = initial_mass_mg
            self._initial_mass_source = mass_source
            self._set_combo(self.tg_combo, normalization.get("tg_representation", "raw"))
            self.dtg_unit_checks.get(
                str(normalization.get("dtg_unit_mode", "source")),
                self.dtg_unit_checks["source"],
            ).setChecked(True)
            self._set_combo(
                self.dtg_combo,
                normalization.get("dtg_representation", "raw"),
            )
            self._set_combo(
                self.heat_flow_combo,
                normalization.get("heat_flow_representation", "raw"),
            )
            self._set_combo(
                self.reference_mode_combo,
                normalization.get("heat_flow_reference_mode", "first_valid"),
            )
            self._set_combo(
                self.reference_axis_combo,
                normalization.get("reference_axis", "time_s"),
            )
            self.initial_mass_entry.setText(self._number_text(manual_mass_mg))
            self.use_initial_mass_checkbox.setChecked(
                bool(normalization.get("use_initial_mass_as_reference", False))
            )
            self.reference_mass_entry.setText(
                self._number_text(normalization.get("reference_mass_mg"))
            )
            self.reference_name_entry.setText(
                str(normalization.get("reference_name", ""))
            )
            self.range_start_entry.setText(
                self._number_text(normalization.get("range_start"))
            )
            self.range_end_entry.setText(
                self._number_text(normalization.get("range_end"))
            )
            self.calculate_dtg_checkbox.setChecked(
                bool(normalization.get("calculate_dtg_if_missing", False))
            )
            self.clear_validation()
            self._update_mass_provenance()
            self._update_visibility()
        finally:
            self.blockSignals(False)

    @staticmethod
    def _set_combo(combo: QComboBox, value: Any) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def _number_text(self, value: Any) -> str:
        return (
            ""
            if value is None
            else self.number_locale.toString(float(value), "g", 12)
        )

    def show_validation(self, message: str) -> None:
        self.validation_label.setText(message)
        self.validation_label.show()

    def clear_validation(self) -> None:
        self.validation_label.clear()
        self.validation_label.hide()

    def tab_controls(self) -> tuple[Any, ...]:
        return (
            self.tg_combo,
            *self.dtg_unit_checks.values(),
            self.dtg_combo,
            self.calculate_dtg_checkbox,
            self.heat_flow_combo,
            self.initial_mass_entry,
            self.use_initial_mass_checkbox,
            self.reference_mass_entry,
            self.reference_name_entry,
            self.reference_mode_combo,
            self.reference_axis_combo,
            self.range_start_entry,
            self.range_end_entry,
        )
