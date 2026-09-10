"""Table de saisie locale du programme de consigne de l'expérience active."""

from __future__ import annotations

from atg_dsc_corrector.models import TIME_AXIS_SECONDS

import math

from PySide6.QtCore import QSignalBlocker, Qt
from .number_format import number_locale, parse_number
from atg_dsc_corrector.i18n import language
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QStyledItemDelegate,
)

from atg_dsc_corrector.i18n import tr as _t
from atg_dsc_corrector.thermal_program import (
    default_thermal_program, segment_duration, thermal_program_points,
    validate_thermal_program,
    parse_duration, format_duration,
)


class DurationEdit(QLineEdit):
    """Duration entry with optional automatic separators, without clock limits."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("hh:mm:ss")
        self.editingFinished.connect(self._normalize)

    def keyPressEvent(self, event):
        # Accept an explicitly typed separator after the automatically inserted one.
        position = self.cursorPosition()
        if event.text() == ":" and not self.hasSelectedText():
            if self.text()[position:position + 1] == ":":
                self.setCursorPosition(position + 1)
                return
            if position and self.text()[position - 1:position] == ":":
                return
        super().keyPressEvent(event)
        text = self.text()
        if (event.text().isascii() and event.text().isdigit()
                and self.cursorPosition() == len(text) and text.count(":") < 2
                and len(text.rsplit(":", 1)[-1].lstrip("-")) == 2):
            self.insert(":")

    def _normalize(self):
        try:
            self.setText(self.display_duration(parse_duration(self.text())))
        except ValueError:
            pass  # The existing program validation reports incomplete input.

    @staticmethod
    def display_duration(minutes):
        text = format_duration(minutes)
        return text.replace(".", ",") if language() == "fr" else text


class DurationDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return DurationEdit(parent)

    def setEditorData(self, editor, index):
        owner = self.parent()
        text = str(index.data())
        try:
            text = DurationEdit.display_duration(owner._number(text, _t('Temps')) / owner._time_factor)
        except ValueError:
            pass
        editor.setText(text)
        editor.setPlaceholderText("hh:mm:ss")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        text = editor.text()
        try:
            text = self.parent()._format(parse_duration(text) * self.parent()._time_factor)
        except ValueError:
            if ":" not in text:
                text += ":"
        model.setData(index, text, Qt.ItemDataRole.EditRole)


class ThermalProgramEditor(QWidget):
    def __init__(self, program: dict | None = None, parent=None, *, time_axis="time_min"):
        super().__init__(parent)
        self._locale = number_locale()
        self.setLocale(self._locale)
        self._unit = "°C"
        self._time_factor = 60 / TIME_AXIS_SECONDS.get(time_axis, 60)
        self._time_unit = time_axis.removeprefix("time_") if time_axis in TIME_AXIS_SECONDS else "min"
        layout = QVBoxLayout(self)
        self.enabled_check = QCheckBox(_t('Afficher le programme thermique'))
        layout.addWidget(self.enabled_check)
        form = QFormLayout()
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["°C", "K"])
        self.t0_entry = DurationEdit()
        self.t0_entry.setText("00:00:00")
        form.addRow(_t('Unité de température'), self.unit_combo)
        form.addRow(_t('Début t₀ (hh:mm:ss)'), self.t0_entry)
        self.unit_combo.setAccessibleName(_t('Unité de température'))
        self.t0_entry.setAccessibleName(_t('Début t₀ (hh:mm:ss)'))
        layout.addLayout(form)
        note = QLabel(_t('Programme de consigne, affiché uniquement sur un axe temporel. T_ini suit T_f de la ligne précédente.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 5)
        self.table.setAccessibleName(_t('Programme thermique'))
        self.table.setItemDelegateForColumn(4, DurationDelegate(self))
        self.table.setToolTip(_t('Saisir les durées en hh:mm:ss ; affichage dans l’unité de temps du graphique.'))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet("QTableWidget::item { padding: 0px 8px; border: 0px; }")
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.add_button = QPushButton(_t('Ajouter une ligne'))
        self.remove_button = QPushButton(_t('Supprimer la ligne'))
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.total_label = QLabel()
        self.error_label = QLabel()
        self.error_label.setProperty("error", True)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.total_label)
        layout.addWidget(self.error_label)
        self.load_program(program if program is not None else default_thermal_program())
        self.add_button.clicked.connect(self.add_row)
        self.remove_button.clicked.connect(self.remove_row)
        self.table.itemChanged.connect(self._refresh)
        self.t0_entry.textChanged.connect(self._refresh)
        self.enabled_check.toggled.connect(self._refresh)
        self.unit_combo.currentTextChanged.connect(self._change_unit)

    def _format(self, value):
        return self._locale.toString(float(value), "g", 15)

    def _number(self, text, name):
        value, valid = parse_number(text, self._locale)
        if not valid or not math.isfinite(value):
            raise ValueError(_t('{name} doit être un nombre fini.', name=name))
        return value

    def _cell_number(self, row, column):
        return self._number(self.table.item(row, column).text(),
                            self.table.horizontalHeaderItem(column).text())

    def _set_cell(self, row, column, text, editable):
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, column, item)
        item.setText(text)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        item.setFlags(flags | Qt.ItemFlag.ItemIsEditable if editable else flags)

    def _append(self, kind, start, end, rate, duration):
        row = self.table.rowCount()
        self.table.insertRow(row)
        combo = QComboBox()
        for label, value in [(_t('Palier'), "hold"), (_t('Montée'), "heating"), (_t('Descente'), "cooling")]:
            combo.addItem(label, value)
        combo.setCurrentIndex(combo.findData(kind))
        combo.setAccessibleName(_t('Type de segment'))
        cell = QWidget()
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(4, 4, 4, 4)
        cell_layout.addWidget(combo)
        self.table.setCellWidget(row, 0, cell)
        for column, value in enumerate((start, end, rate, duration), 1):
            if column == 4 and value is not None:
                value *= self._time_factor
            self._set_cell(row, column, "" if value is None else self._format(value), True)
        combo.currentIndexChanged.connect(lambda: self._type_changed(combo))

    def load_program(self, program):
        program = validate_thermal_program(program)
        with QSignalBlocker(self.table), QSignalBlocker(self.unit_combo), QSignalBlocker(self.t0_entry), QSignalBlocker(self.enabled_check):
            self._unit = program["temperature_unit"]
            self.unit_combo.setCurrentText(self._unit)
            self.enabled_check.setChecked(program["enabled"])
            self.t0_entry.setText(DurationEdit.display_duration(program["t0_min"]))
            self.table.setHorizontalHeaderLabels([
                _t('Type'), f"T_ini ({self._unit})", f"T_f ({self._unit})",
                f"β ({self._unit}/min)", f"{_t('Temps')} ({self._time_unit})",
            ])
            self.table.setRowCount(0)
            start = program["initial_temperature_c"] + (273.15 if self._unit == "K" else 0)
            for segment in program["segments"]:
                end = (segment["target_temperature_c"] + (273.15 if self._unit == "K" else 0)
                       if segment["type"] != "hold" else start)
                self._append(segment["type"], start, end, segment.get("rate_c_per_min"), segment.get("duration_min"))
                start = end
        self._refresh()

    def add_row(self):
        row = self.table.rowCount()
        with QSignalBlocker(self.table):
            self._append("hold", 20 + (273.15 if self._unit == "K" else 0), None, None, None)
        self._refresh()
        self.table.setCurrentCell(row, 4)
        self.table.editItem(self.table.item(row, 4))

    def remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            with QSignalBlocker(self.table):
                self.table.removeRow(row)
            self._refresh()

    def _type_changed(self, combo):
        with QSignalBlocker(self.table):
            for row in range(self.table.rowCount()):
                if self.table.cellWidget(row, 0).findChild(QComboBox) is combo:
                    if combo.currentData() == "hold":
                        self.table.item(row, 4).setText("")
                    elif not self.table.item(row, 3).text():
                        self.table.item(row, 3).setText("10")
                    break
        self._refresh()

    def _refresh(self, *_args):
        with QSignalBlocker(self.table):
            for row in range(self.table.rowCount()):
                kind = self.table.cellWidget(row, 0).findChild(QComboBox).currentData()
                initial = self.table.item(row - 1, 2).text() if row else self.table.item(row, 1).text()
                self._set_cell(row, 1, initial, row == 0)
                if kind == "hold":
                    self._set_cell(row, 2, initial, False)
                    self._set_cell(row, 3, "", False)
                    self._set_cell(row, 4, self.table.item(row, 4).text(), True)
                else:
                    self._set_cell(row, 2, self.table.item(row, 2).text(), True)
                    self._set_cell(row, 3, self.table.item(row, 3).text(), True)
                    try:
                        offset = 273.15 if self._unit == "K" else 0
                        duration = segment_duration(kind, self._cell_number(row, 1) - offset,
                                                    self._cell_number(row, 2) - offset,
                                                    self._cell_number(row, 3), None)
                        text = self._format(duration * self._time_factor)
                    except ValueError:
                        text = ""
                    self._set_cell(row, 4, text, False)
        try:
            program = self.program()
            times, _ = thermal_program_points(program)
            self.total_label.setText(_t('Durée totale : {duration} {unit}', duration=self._format((times[-1] - times[0]) * self._time_factor), unit=self._time_unit))
            self.error_label.clear()
        except ValueError as exc:
            self.total_label.clear()
            self.error_label.setText(str(exc))

    def program(self):
        offset = 273.15 if self._unit == "K" else 0
        program = default_thermal_program()
        program.update(enabled=self.enabled_check.isChecked(), temperature_unit=self._unit,
                       t0_min=parse_duration(self.t0_entry.text()))
        for row in range(self.table.rowCount()):
            try:
                if row == 0:
                    program["initial_temperature_c"] = self._cell_number(row, 1) - offset
                kind = self.table.cellWidget(row, 0).findChild(QComboBox).currentData()
                segment = {"type": kind}
                if kind == "hold":
                    if ":" in self.table.item(row, 4).text():
                        raise ValueError(_t('Saisir une durée au format hh:mm:ss.'))
                    segment["duration_min"] = self._cell_number(row, 4) / self._time_factor
                else:
                    segment.update(target_temperature_c=self._cell_number(row, 2) - offset,
                                   rate_c_per_min=self._cell_number(row, 3))
                program["segments"].append(segment)
            except ValueError as exc:
                raise ValueError(_t('Ligne {row} : {error}', row=row + 1, error=str(exc))) from exc
        return validate_thermal_program(program)

    def _change_unit(self, unit):
        try:
            program = self.program()
        except ValueError as exc:
            with QSignalBlocker(self.unit_combo):
                self.unit_combo.setCurrentText(self._unit)
            self.error_label.setText(str(exc))
            return
        program["temperature_unit"] = unit
        self.load_program(program)


class ThermalProgramDialog(QDialog):
    """Édition de la consigne sur une copie, indépendante des réglages du graphique."""

    def __init__(self, *, program: dict, apply_callback, parent=None, time_axis="time_min"):
        super().__init__(parent)
        self.setWindowTitle(_t('Programme thermique'))
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(560, 440)
        self.resize(720, 600)
        self._apply_callback = apply_callback
        layout = QVBoxLayout(self)
        self.editor = ThermalProgramEditor(program, self, time_axis=time_axis)
        layout.addWidget(self.editor)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText(_t('Appliquer'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_t('Annuler'))
        layout.addWidget(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)

    def _apply(self):
        try:
            self._apply_callback(self.editor.program())
        except ValueError as exc:
            self.editor.error_label.setText(str(exc))
            return False
        self.editor.error_label.clear()
        return True

    def _accept(self):
        if self._apply():
            self.accept()
