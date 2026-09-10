"""Compact zone definitions and results, backed by the existing zone engine."""

import math
from PySide6.QtCore import QLocale, Qt, Signal, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStyledItemDelegate, QHeaderView,
    QTableWidget, QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)
from atg_dsc_corrector.i18n import tr as _t
from .color_button import ColorButton
from .theme import line_icon
from .zone_results_table import ZoneResultsTable, copy_table
from .number_format import number_locale
from atg_dsc_corrector.i18n import decimal_text

BASELINE_LABELS = {"none": _t("Aucune"), "constant": _t("Constante"), "linear": _t("Linéaire")}
FIELDS = (None, "name", "start", "end", "axis_type", "baseline_method", "baseline_value")


class ZoneCellDelegate(QStyledItemDelegate):
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def createEditor(self, parent, option, index):
        if index.column() == 5:
            editor = QComboBox(parent)
            for key, label in BASELINE_LABELS.items():
                if key != "linear" or index.data(Qt.ItemDataRole.UserRole + 1) == "linear":
                    editor.addItem(label, key)
            return editor
        return QLineEdit(parent)

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(max(0, editor.findData(value)))
        else:
            editor.setText("" if value is None else decimal_text(value) if index.column() in (2, 3, 6) else str(value))
            editor.selectAll()

    def setModelData(self, editor, model, index):
        value = editor.currentData() if isinstance(editor, QComboBox) else editor.text().strip()
        if index.column() in (2, 3, 6):
            number, ok = number_locale().toDouble(value)
            if not ok:
                number, ok = QLocale.c().toDouble(value.replace(",", "."))
            if not ok or not math.isfinite(number):
                self.parent().show_validation(_t("La valeur doit être un nombre fini."))
                return
            value = number
        self.parent().zone_edit_requested.emit(
            index.siblingAtColumn(1).data(Qt.ItemDataRole.UserRole), {FIELDS[index.column()]: value})


class ZoneAppearanceDialog(QDialog):
    def __init__(self, zone, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("Apparence de la zone") + " - " + zone.name)
        form = QFormLayout(self)
        self.color_button = ColorButton(zone.color or "#6A5ACD")
        self.color_button.clicked.connect(lambda: self._choose_color(self.color_button))
        self.positive_area_button = ColorButton(zone.positive_area_color or "#0072B2")
        self.negative_area_button = ColorButton(zone.negative_area_color or "#D55E00")
        self.baseline_color_button = ColorButton(zone.baseline_color or "#7A3E9D")
        self.baseline_color_button.clicked.connect(lambda: self._choose_color(self.baseline_color_button))
        self.positive_area_button.clicked.connect(lambda: self._choose_color(self.positive_area_button))
        self.negative_area_button.clicked.connect(lambda: self._choose_color(self.negative_area_button))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(.1, 10)
        self.width_spin.setDecimals(1)
        self.width_spin.setValue(zone.line_width if zone.line_width is not None else 1)
        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0, 100)
        self.opacity_spin.setSuffix(" %")
        self.opacity_spin.setValue(100 * (zone.opacity if zone.opacity is not None else .20))
        self.baseline_check = QCheckBox(_t("Afficher la ligne de base"))
        self.baseline_check.setChecked(zone.show_baseline)
        form.addRow(_t("Couleur"), self.color_button)
        form.addRow(_t("Couleur de la ligne de base"), self.baseline_color_button)
        form.addRow(_t("Couleur de l'aire au-dessus de la ligne de base"), self.positive_area_button)
        form.addRow(_t("Couleur de l'aire au-dessous de la ligne de base"), self.negative_area_button)
        form.addRow(_t("Épaisseur des bornes"), self.width_spin)
        form.addRow(_t("Opacité de la zone"), self.opacity_spin)
        form.addRow(self.baseline_check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _choose_color(self, button):
        color = QColorDialog.getColor(QColor(button.property("graphColor")), self, _t("Couleur"))
        if color.isValid():
            button.setText(color.name())

    def values(self):
        return dict(color=self.color_button.property("graphColor"), line_width=self.width_spin.value(),
                    baseline_color=self.baseline_color_button.property("graphColor"),
                    positive_area_color=self.positive_area_button.property("graphColor"),
                    negative_area_color=self.negative_area_button.property("graphColor"),
                    opacity=self.opacity_spin.value() / 100, show_baseline=self.baseline_check.isChecked())


class ZonesPanel(QWidget):
    active_zone_changed = Signal(str)
    zone_edit_requested = Signal(str, dict)
    appearance_requested = Signal(str)

    def __init__(self, axis_labels, parent=None):
        super().__init__(parent)
        self._axis_labels = axis_labels
        self._zones = {}
        self._available = False
        self._widths = {}
        self._sizing = False
        self.results_dialog = None
        self.information_dialog = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.tabs = QTabWidget()
        self.zone_table = QTableWidget(0, len(FIELDS))
        self.zone_table.setObjectName("zonesTable")
        self.zone_table.setHorizontalHeaderLabels(("", _t("Nom"), _t("Début"), _t("Fin"),
                                                  _t("Axe"), _t("Ligne de base"), _t("Valeur")))
        self.zone_table.setItemDelegate(ZoneCellDelegate(self))
        self.zone_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.zone_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.zone_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)
        self.zone_table.verticalHeader().hide()
        self.zone_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.zone_table.setAlternatingRowColors(True)
        self.zone_table.setWordWrap(False)
        self.zone_table.horizontalHeader().sectionResized.connect(self._remember_width)
        self.result_table = ZoneResultsTable()
        self.tabs.addTab(self.zone_table, _t("Définition"))
        self.tabs.addTab(self.result_table, _t("Résultats"))
        self.all_results_button = QPushButton(_t("Afficher tous les résultats"))
        self.all_results_button.setObjectName("showAllZoneResultsButton")
        self.all_results_button.clicked.connect(self._show_all_results)
        self.mean_label = QLabel()
        self.mean_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.mean_label.setWordWrap(True)
        self.mean_label.hide()
        layout.addWidget(self.mean_label)
        layout.addWidget(self.tabs, 1)
        self.validation_label = QLabel()
        self.validation_label.setProperty("error", True)
        self.validation_label.setWordWrap(True)
        self.validation_label.hide()
        self.axis_notice = QLabel()
        self.axis_notice.setProperty("secondary", True)
        self.axis_notice.setWordWrap(True)
        self.axis_notice.hide()
        layout.addWidget(self.validation_label)
        layout.addWidget(self.axis_notice)
        self.add_button = self._button("Ajouter une zone sur le graphique", "add")
        self.add_button.setCheckable(True)
        self.update_button = self._button("Modifier la zone sélectionnée", "edit")
        self.delete_button = self._button("Supprimer la zone sélectionnée", "delete")
        self.copy_button = self._button("Copier le tableau", "copy")
        self.information_button = self._button("Informations des zones", "info")
        self.information_button.clicked.connect(lambda: self._show_table_dialog(context=True))
        self.update_button.clicked.connect(self.edit_selected_zone)
        self.copy_button.clicked.connect(self.copy_current_table)
        self.zone_table.itemSelectionChanged.connect(self._selection_changed)
        self.result_table.itemSelectionChanged.connect(self._result_selection_changed)
        self.set_availability(False, False)

    def _button(self, label, icon):
        button = QToolButton(self)
        button.setMinimumSize(26, 26)
        button.setIcon(line_icon(icon))
        button.setToolTip(_t(label))
        button.setAccessibleName(_t(label))
        return button

    def set_zones(self, zones, active_id, display_axis):
        self._zones = {zone.identifier: zone for zone in zones}
        with QSignalBlocker(self.zone_table):
            self.zone_table.setRowCount(len(self._zones))
            for row, zone in enumerate(self._zones.values()):
                gear = self._button("Apparence de la zone", "gear")
                gear.setAccessibleName(_t("Apparence de la zone") + " " + zone.name)
                gear.clicked.connect(lambda checked=False, identifier=zone.identifier: self.appearance_requested.emit(identifier))
                self.zone_table.setCellWidget(row, 0, gear)
                for col, value in enumerate((zone.name, zone.start, zone.end,
                    self._axis_labels.get(zone.axis_type, zone.axis_type), zone.baseline_method, zone.baseline_value), 1):
                    text = BASELINE_LABELS.get(value, value) if col == 5 else value
                    if isinstance(value, float):
                        text = number_locale().toString(value, "g", 4)
                    if value is None:
                        text = "-"
                    item = QTableWidgetItem(str(text))
                    item.setData(Qt.ItemDataRole.UserRole, zone.identifier)
                    item.setData(Qt.ItemDataRole.UserRole + 1, value)
                    item.setToolTip(decimal_text(value) if value is not None and col in (2, 3, 6) else str(value) if value is not None else "-")
                    if col == 4 or (col == 6 and zone.baseline_method != "constant"):
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if col in (2, 3, 6):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if col == 6:
                        item.setToolTip(zone.baseline_unit or _t("Vide : valeur du premier point de la zone"))
                    self.zone_table.setItem(row, col, item)
                if zone.identifier == active_id:
                    self.zone_table.setCurrentCell(row, 1)
            if active_id not in self._zones:
                self.zone_table.setCurrentCell(-1, -1)
        self._sizing = True
        self.zone_table.resizeColumnsToContents()
        self.zone_table.setColumnWidth(0, 34)
        for col, width in self._widths.items():
            self.zone_table.setColumnWidth(col, width)
        self.zone_table.resizeRowsToContents()
        self._sizing = False
        hidden = sum(zone.axis_type != display_axis for zone in self._zones.values())
        self.axis_notice.setText(_t("{v0} zone(s) sur un autre axe, conservée(s) mais masquée(s).", v0=hidden) if hidden else "")
        self.axis_notice.setVisible(bool(hidden))
        self._update_actions()

    def _remember_width(self, column, old, width):
        if not self._sizing and width > 0:
            self._widths[column] = width

    def selected_zone_id(self):
        item = self.zone_table.item(self.zone_table.currentRow(), 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self):
        identifier = self.selected_zone_id()
        if identifier:
            self.clear_validation()
            self.active_zone_changed.emit(identifier)
        self._update_actions()

    def _result_selection_changed(self):
        item = self.result_table.item(self.result_table.currentRow(), 0)
        if item and item.data(Qt.ItemDataRole.UserRole) in self._zones:
            self.active_zone_changed.emit(item.data(Qt.ItemDataRole.UserRole))

    def edit_selected_zone(self):
        self.tabs.setCurrentIndex(0)
        if self.selected_zone_id():
            item = self.zone_table.item(self.zone_table.currentRow(), 2)
            self.zone_table.setCurrentItem(item)
            self.zone_table.editItem(item)

    def set_records(self, records):
        with QSignalBlocker(self.result_table):
            self.result_table.set_records(records)
        self.all_results_button.setEnabled(bool(records))
        self.information_button.setEnabled(bool(records))
        mean_names = dict.fromkeys(row.get("experiment_name", "") for row in records if row.get("statistics"))
        self.mean_label.setText("\n".join(mean_names))
        self.mean_label.setVisible(bool(mean_names))
        for dialog in (self.results_dialog, self.information_dialog):
            if dialog is not None:
                dialog.table.set_records(records)
                dialog.mean_label.setText(self.mean_label.text())
                dialog.mean_label.setVisible(bool(mean_names))

    def _show_all_results(self):
        self._show_table_dialog()

    def _show_table_dialog(self, *, context=False):
        attribute = "information_dialog" if context else "results_dialog"
        dialog = getattr(self, attribute)
        if dialog is None:
            dialog = QDialog(self)
            setattr(self, attribute, dialog)
            dialog.setWindowTitle(_t("Informations des zones") if context else _t("Tous les résultats des zones"))
            dialog.resize(1200, 600)
            layout = QVBoxLayout(dialog)
            copy_button = self._button("Copier le tableau", "copy")
            actions = QHBoxLayout()
            actions.addStretch()
            actions.addWidget(copy_button)
            layout.addLayout(actions)
            dialog.mean_label = QLabel(self.mean_label.text())
            dialog.mean_label.setWordWrap(True)
            dialog.mean_label.setVisible(bool(self.mean_label.text()))
            layout.addWidget(dialog.mean_label)
            dialog.table = ZoneResultsTable(dialog, context_only=context)
            dialog.table.complete = True
            layout.addWidget(dialog.table)
            copy_button.clicked.connect(lambda: copy_table(dialog.table))
            dialog.copy_button = copy_button
            close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            close.button(QDialogButtonBox.StandardButton.Close).setText(_t("Fermer"))
            close.rejected.connect(dialog.close)
            layout.addWidget(close)
            dialog.table.set_records(self.result_table.records)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def copy_current_table(self):
        definitions = self.tabs.currentIndex() == 0
        copy_table(self.zone_table if definitions else self.result_table, first_column=1 if definitions else 0)

    def show_validation(self, message):
        self.validation_label.setText(message)
        self.validation_label.show()

    def clear_validation(self):
        self.validation_label.clear()
        self.validation_label.hide()

    def set_graph_selection_active(self, active):
        with QSignalBlocker(self.add_button):
            self.add_button.setChecked(active)
        self.add_button.setToolTip(_t("Annuler la sélection") if active else _t("Ajouter une zone sur le graphique"))

    def set_availability(self, experiment_loaded, result_available):
        self._available = result_available
        self.add_button.setEnabled(result_available)
        self._update_actions()

    def set_heat_flow_visible(self, visible):
        self.zone_table.setColumnHidden(5, not visible)
        self.zone_table.setColumnHidden(6, not visible)

    def _update_actions(self):
        selected = self.selected_zone_id() is not None
        self.update_button.setEnabled(selected and self._available)
        self.delete_button.setEnabled(selected)

    def tab_controls(self):
        return [self.add_button, self.update_button, self.delete_button, self.copy_button,
                self.tabs.tabBar(), self.zone_table, self.result_table, self.all_results_button, self.information_button]
