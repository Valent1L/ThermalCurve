"""Panneau Qt compact pour les zones d'analyse existantes."""

from __future__ import annotations

from atg_dsc_corrector.i18n import tr as _t

from collections.abc import Iterable

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from atg_dsc_corrector.analysis_zones import AnalysisZone


BASELINE_LABELS = {
    "none": _t('Aucune'),
    "constant": _t('Constante'),
}


class ZoneResultsDialog(QDialog):
    """Fenêtre native réutilisée pour le rapport complet des zones."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(False)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(620, 400)
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setObjectName("zoneResultsDialogTitle")
        self.heading.setProperty("pageTitle", True)
        layout.addWidget(self.heading)
        self.report = QPlainTextEdit()
        self.report.setObjectName("allZoneResults")
        self.report.setReadOnly(True)
        self.report.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.report, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.close)
        layout.addWidget(self.buttons)

    def set_report(self, title: str, text: str) -> None:
        self.setWindowTitle(title)
        self.heading.setText(title)
        self.report.setPlainText(text)


class ZonesPanel(QGroupBox):
    """Éditeur de zones sans calcul scientifique ni copie de données."""

    active_zone_changed = Signal(str)
    show_all_results_requested = Signal()

    def __init__(self, axis_labels: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(_t('Zones et quantification'), parent)
        self._axis_labels = axis_labels
        self._zones: dict[str, AnalysisZone] = {}
        self._locale = QLocale.system()
        self._heat_flow_visible = True

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.zone_table = QTableWidget(0, 4)
        self.zone_table.setObjectName("zonesTable")
        self.zone_table.setHorizontalHeaderLabels((_t('Nom'), _t('Début'), _t('Fin'), _t('Axe')))
        self.zone_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.zone_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.zone_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.zone_table.setAlternatingRowColors(True)
        self.zone_table.verticalHeader().setVisible(False)
        self.zone_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in (1, 2, 3):
            self.zone_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        row_height = max(24, self.fontMetrics().height() + 10)
        self.zone_table.verticalHeader().setDefaultSectionSize(row_height)
        self.zone_table.setMinimumHeight(row_height * 4 + row_height)
        self.zone_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.zone_table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.zone_table)

        self._form = QFormLayout()
        form = self._form
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(6)

        self.name_entry = QLineEdit()
        self.name_entry.setObjectName("zoneNameEntry")
        self.name_entry.setClearButtonEnabled(True)
        name_label = QLabel(_t('Nom'))
        name_label.setBuddy(self.name_entry)
        form.addRow(name_label, self.name_entry)

        validator = QDoubleValidator(-1.0e300, 1.0e300, 12, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        validator.setLocale(self._locale)
        self.start_entry = QLineEdit()
        self.start_entry.setObjectName("zoneStartEntry")
        self.start_entry.setValidator(validator)
        self.end_entry = QLineEdit()
        self.end_entry.setObjectName("zoneEndEntry")
        end_validator = QDoubleValidator(-1.0e300, 1.0e300, 12, self)
        end_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        end_validator.setLocale(self._locale)
        self.end_entry.setValidator(end_validator)
        start_label = QLabel(_t('Borne initiale'))
        start_label.setBuddy(self.start_entry)
        end_label = QLabel(_t('Borne finale'))
        end_label.setBuddy(self.end_entry)
        form.addRow(start_label, self.start_entry)
        form.addRow(end_label, self.end_entry)

        self.baseline_combo = QComboBox()
        self.baseline_combo.setObjectName("zoneBaselineCombo")
        for key, label in BASELINE_LABELS.items():
            self.baseline_combo.addItem(label, key)
        baseline_label = QLabel(_t('Ligne de base Flux de chaleur'))
        baseline_label.setBuddy(self.baseline_combo)
        form.addRow(baseline_label, self.baseline_combo)
        self.baseline_value_entry = QLineEdit()
        self.baseline_value_entry.setObjectName("zoneBaselineValueEntry")
        baseline_validator = QDoubleValidator(-1.0e300, 1.0e300, 12, self)
        baseline_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        baseline_validator.setLocale(self._locale)
        self.baseline_value_entry.setValidator(baseline_validator)
        self.baseline_value_entry.setPlaceholderText(_t('Valeur du signal'))
        baseline_value_label = QLabel(_t('Valeur constante'))
        baseline_value_label.setBuddy(self.baseline_value_entry)
        form.addRow(baseline_value_label, self.baseline_value_entry)
        self.baseline_combo.currentIndexChanged.connect(self._sync_baseline_value)
        layout.addLayout(form)
        self.heat_flow_notice = QLabel(
            _t('En température, les deux bornes peuvent être saisies dans les deux sens. Les aires Flux de chaleur au-dessus et au-dessous de la ligne de base sont séparées.')
        )
        self.heat_flow_notice.setWordWrap(True)
        layout.addWidget(self.heat_flow_notice)

        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(6)
        self.add_button = QPushButton(_t('Ajouter'))
        self.add_button.setObjectName("addZoneButton")
        self.update_button = QPushButton(_t('Modifier'))
        self.update_button.setObjectName("updateZoneButton")
        self.delete_button = QPushButton(_t('Supprimer'))
        self.delete_button.setObjectName("deleteZoneButton")
        self.graph_button = QPushButton(_t('Sélectionner sur le graphe'))
        self.graph_button.setObjectName("selectZoneOnGraphButton")
        self.graph_button.setCheckable(True)
        self.graph_button.setAccessibleName(
            _t('Créer une zone par sélection sur le graphe')
        )
        actions.addWidget(self.add_button, 0, 0)
        actions.addWidget(self.update_button, 0, 1)
        actions.addWidget(self.delete_button, 1, 0, 1, 2)
        actions.addWidget(self.graph_button, 2, 0, 1, 2)
        layout.addLayout(actions)

        self.validation_label = QLabel()
        self.validation_label.setObjectName("zoneValidationMessage")
        self.validation_label.setProperty("error", True)
        self.validation_label.setWordWrap(True)
        self.validation_label.setAccessibleName(_t('Erreur de validation de la zone'))
        self.validation_label.hide()
        layout.addWidget(self.validation_label)

        self.axis_notice = QLabel()
        self.axis_notice.setObjectName("zoneAxisNotice")
        self.axis_notice.setProperty("secondary", True)
        self.axis_notice.setWordWrap(True)
        self.axis_notice.hide()
        layout.addWidget(self.axis_notice)

        results_label = QLabel(_t('Résultats de la zone active'))
        results_label.setObjectName("zoneResultsLabel")
        self.results = QPlainTextEdit()
        self.results.setObjectName("zoneResults")
        self.results.setReadOnly(True)
        self.results.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.results.setMinimumHeight(max(150, self.fontMetrics().height() * 8))
        self.results.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.results.setPlaceholderText(
            _t('Sélectionner une zone pour afficher ses quantifications.')
        )
        layout.addWidget(results_label)
        layout.addWidget(self.results)
        self.all_results_button = QPushButton(_t('Afficher tous les résultats…'))
        self.all_results_button.setObjectName("showAllZoneResultsButton")
        self.all_results_button.setAccessibleName(
            _t('Afficher les résultats de toutes les zones')
        )
        self.all_results_button.clicked.connect(self.show_all_results_requested.emit)
        layout.addWidget(self.all_results_button)
        self.set_availability(False, False)
        self._sync_baseline_value()

    def set_zones(
        self,
        zones: Iterable[AnalysisZone],
        active_id: str | None,
        display_axis: str,
    ) -> None:
        zone_list = list(zones)
        self._zones = {zone.identifier: zone for zone in zone_list}
        self.zone_table.blockSignals(True)
        try:
            self.zone_table.setRowCount(len(zone_list))
            selected_row = -1
            for row, zone in enumerate(zone_list):
                name = QTableWidgetItem(zone.name)
                name.setData(Qt.ItemDataRole.UserRole, zone.identifier)
                self.zone_table.setItem(row, 0, name)
                self.zone_table.setItem(row, 1, QTableWidgetItem(self._number(zone.start)))
                self.zone_table.setItem(row, 2, QTableWidgetItem(self._number(zone.end)))
                self.zone_table.setItem(
                    row,
                    3,
                    QTableWidgetItem(self._axis_labels.get(zone.axis_type, zone.axis_type)),
                )
                if zone.identifier == active_id:
                    selected_row = row
            if selected_row >= 0:
                self.zone_table.selectRow(selected_row)
                self._load_editor(zone_list[selected_row])
            else:
                self.zone_table.clearSelection()
                self._clear_editor_if_empty(zone_list)
        finally:
            self.zone_table.blockSignals(False)

        hidden = sum(zone.axis_type != display_axis for zone in zone_list)
        if hidden:
            self.axis_notice.setText(
                _t('{v0} zone(s) conservée(s) mais masquée(s) sur le graphe : elles sont définies sur un autre axe.', v0=hidden)
            )
            self.axis_notice.show()
        else:
            self.axis_notice.clear()
            self.axis_notice.hide()
        self._update_selected_actions()

    def selected_zone_id(self) -> str | None:
        row = self.zone_table.currentRow()
        if row < 0:
            return None
        item = self.zone_table.item(row, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def editor_values(self, axis_type: str = "time_s") -> tuple[str, float, float, str, float | None]:
        name = self.name_entry.text().strip()
        if not name:
            raise ValueError(_t('Le nom de la zone est obligatoire.'))
        start = self._parse_number(self.start_entry.text(), _t('borne initiale'))
        end = self._parse_number(self.end_entry.text(), _t('borne finale'))
        if axis_type in {"furnace_temperature", "sample_temperature"}:
            start, end = sorted((start, end))
        if end <= start:
            raise ValueError(
                _t('La borne finale doit être strictement supérieure à la borne initiale.')
            )
        method, value = self.baseline_values()
        return name, start, end, method, value

    def baseline_values(self) -> tuple[str, float | None]:
        method = str(self.baseline_combo.currentData())
        value = (
            self._parse_number(self.baseline_value_entry.text(), _t('valeur constante'))
            if method == "constant"
            else None
        )
        return method, value

    def prepare_new_zone(self, suggested_name: str) -> None:
        self.zone_table.clearSelection()
        self.name_entry.setText(suggested_name)
        self.start_entry.clear()
        self.end_entry.clear()
        self.baseline_combo.setCurrentIndex(
            max(0, self.baseline_combo.findData("none"))
        )
        self.baseline_value_entry.clear()
        self.name_entry.setFocus()
        self.clear_validation()
        self._update_selected_actions()

    def set_results(self, text: str) -> None:
        self.results.setPlainText(text)

    def show_validation(self, message: str) -> None:
        self.validation_label.setText(message)
        self.validation_label.show()

    def clear_validation(self) -> None:
        self.validation_label.clear()
        self.validation_label.hide()

    def set_graph_selection_active(self, active: bool) -> None:
        self.graph_button.blockSignals(True)
        try:
            self.graph_button.setChecked(active)
            self.graph_button.setText(
                _t('Annuler la sélection') if active else _t('Sélectionner sur le graphe')
            )
        finally:
            self.graph_button.blockSignals(False)

    def set_availability(self, experiment_loaded: bool, result_available: bool) -> None:
        self.add_button.setEnabled(experiment_loaded)
        self.graph_button.setEnabled(result_available)
        self.results.setEnabled(result_available)
        self.all_results_button.setEnabled(experiment_loaded)
        self._update_selected_actions()

    def set_heat_flow_visible(self, visible: bool) -> None:
        """Masque les options DSC sans effacer la ligne de base choisie."""

        self._heat_flow_visible = visible
        self._form.setRowVisible(self.baseline_combo, visible)
        self._form.setRowVisible(self.baseline_value_entry, visible)
        self.heat_flow_notice.setVisible(visible)

    def tab_controls(self) -> list[QWidget]:
        return [
            self.zone_table,
            self.name_entry,
            self.start_entry,
            self.end_entry,
            self.baseline_combo,
            self.baseline_value_entry,
            self.add_button,
            self.update_button,
            self.delete_button,
            self.graph_button,
            self.results,
            self.all_results_button,
        ]

    def _selection_changed(self) -> None:
        identifier = self.selected_zone_id()
        if identifier is not None and identifier in self._zones:
            self._load_editor(self._zones[identifier])
            self.clear_validation()
            self.active_zone_changed.emit(identifier)
        self._update_selected_actions()

    def _load_editor(self, zone: AnalysisZone) -> None:
        self.name_entry.setText(zone.name)
        self.start_entry.setText(self._number(zone.start))
        self.end_entry.setText(self._number(zone.end))
        self.baseline_combo.setCurrentIndex(
            max(0, self.baseline_combo.findData(zone.baseline_method))
        )
        self.baseline_value_entry.setText(
            "" if zone.baseline_value is None else self._number(zone.baseline_value)
        )

    def _clear_editor_if_empty(self, zones: list[AnalysisZone]) -> None:
        if zones:
            return
        self.name_entry.clear()
        self.start_entry.clear()
        self.end_entry.clear()
        self.baseline_combo.setCurrentIndex(
            max(0, self.baseline_combo.findData("none"))
        )
        self.baseline_value_entry.clear()

    def _sync_baseline_value(self, _index: int = -1) -> None:
        constant = self.baseline_combo.currentData() == "constant"
        self.baseline_value_entry.setEnabled(constant)

    def _update_selected_actions(self) -> None:
        selected = self.selected_zone_id() is not None
        self.update_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def _parse_number(self, text: str, field_name: str) -> float:
        value = text.strip()
        if not value:
            raise ValueError(_t('La {v1} est obligatoire.', v1=field_name))
        number, ok = self._locale.toDouble(value)
        if not ok:
            number, ok = QLocale.c().toDouble(value)
        if not ok:
            raise ValueError(_t('La {v1} doit être numérique.', v1=field_name))
        return float(number)

    @staticmethod
    def _number(value: float) -> str:
        return f"{value:.8g}"
