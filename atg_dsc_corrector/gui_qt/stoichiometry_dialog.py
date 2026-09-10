"""Fenêtre Qt légère branchée sur les moteurs stœchiométriques existants."""

from __future__ import annotations

from atg_dsc_corrector.i18n import canonical_number, decimal_text, language, tr as _t

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QToolButton,
    QWidget,
)

from atg_dsc_corrector.atomic_data import SOURCE_ID
from atg_dsc_corrector.projects import default_stoichiometry_settings
from atg_dsc_corrector.stoichiometry import (
    BalanceError,
    ChemicalEquation,
    CondensedMassBalance,
    ExcessGas,
    GasByFraction,
    GasByFlow,
    GasByPartialPressure,
    IdealGasConditions,
    IndividualMasses,
    MassBalanceError,
    MassValue,
    MASS_UNIT_TO_GRAMS,
    StoichiometricTotalMass,
    StoichiometryError,
    balance_equation,
    calculate_condensed_mass_balance,
    format_equation,
    is_balanced,
    parse_equation,
)

from .adapters import ProjectWorkflow
from .workspace_widgets import FoldPanel, scroll_panel
from .theme import line_icon


class EquationDelegate(QStyledItemDelegate):
    """Affiche l'état sous l'équation, sans changer les données du tableau."""

    def paint(self, painter, option, index):
        view = QStyleOptionViewItem(option)
        self.initStyleOption(view, index)
        formula = view.text
        view.text = ""
        view.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, view, painter, view.widget)
        painter.save()
        painter.setFont(view.font)
        painter.setPen(view.palette.color(QPalette.ColorRole.Text))
        rect = view.rect.adjusted(6, 6, -6, -6)
        formula_rect = rect.adjusted(0, 0, 0, -view.fontMetrics.height() - 4)
        painter.drawText(formula_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                         | Qt.TextFlag.TextWordWrap, formula)
        rect.setTop(formula_rect.bottom() + 4)
        painter.setPen(view.palette.color(QPalette.ColorRole.PlaceholderText))
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                         str(index.siblingAtColumn(2).data() or ""))
        painter.restore()


MASS_UNITS = ("µg", "mg", "g")
AMOUNT_UNIT_TO_MOLES = {"µmol": Decimal("1e-6"), "mmol": Decimal("1e-3"), "mol": Decimal(1)}
PRESSURE_UNITS = ("mbar", "bar", "atm")
VOLUME_UNITS = ("mL", "L")
TEMPERATURE_UNITS = ("°C", "K")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return "" if value is None else decimal_text(value)


def _new_entry() -> dict[str, Any]:
    return {
        "text": "",
        "checked": True,
        "inputs": {
            "condensed_mode": "individual",
            "individual_masses": {},
            "total_mass": {"value": "", "unit": "mg"},
            "gases": {},
        },
        "atomic_data_source_id": SOURCE_ID,
    }


def _gas_input_from_data(value: object):
    data = _mapping(value)
    mode = data.get("mode", "mass")
    if mode == "mass":
        mass = _mapping(data.get("mass"))
        return MassValue(mass.get("value", ""), _text(mass.get("unit", "mg")))
    if mode == "partial_pressure":
        partial = _mapping(data.get("partial_pressure"))
        return GasByPartialPressure(
            IdealGasConditions(
                partial.get("pressure", ""),
                _text(partial.get("pressure_unit", "bar")),
                partial.get("volume", ""),
                _text(partial.get("volume_unit", "L")),
                partial.get("temperature", ""),
                _text(partial.get("temperature_unit", "°C")),
            )
        )
    if mode == "fraction":
        fraction = _mapping(data.get("fraction"))
        return GasByFraction(
            fraction.get("value", ""),
            _text(fraction.get("kind", "molar_ppm")),
            IdealGasConditions(
                fraction.get("pressure", ""),
                _text(fraction.get("pressure_unit", "bar")),
                fraction.get("volume", ""),
                _text(fraction.get("volume_unit", "L")),
                fraction.get("temperature", ""),
                _text(fraction.get("temperature_unit", "°C")),
            ),
        )
    if mode == "excess":
        return ExcessGas()
    if mode == "flow":
        flow = _mapping(data.get("flow"))
        return GasByFlow(flow.get("flow", ""), _text(flow.get("flow_unit", "mL/min")),
            flow.get("duration", ""), _text(flow.get("duration_unit", "min")),
            flow.get("pressure", ""), _text(flow.get("pressure_unit", "bar")),
            flow.get("temperature", ""), _text(flow.get("temperature_unit", "°C")),
            flow.get("value", ""), _text(flow.get("kind", "percent")))
    raise MassBalanceError(_t('Mode gazeux inconnu dans le projet.'))


def _inputs_for_equation(
    equation: ChemicalEquation, entry: Mapping[str, Any]
) -> IndividualMasses | StoichiometricTotalMass:
    data = _mapping(entry.get("inputs"))
    gases = _mapping(data.get("gases"))
    if data.get("condensed_mode", "individual") == "total":
        total = _mapping(data.get("total_mass"))
        return StoichiometricTotalMass(
            MassValue(total.get("value", ""), _text(total.get("unit", "mg"))),
            tuple(
                _gas_input_from_data(gases.get(str(index), {}))
                for index, species in enumerate(equation.reactants)
                if species.state == "g"
            ),
        )
    masses = _mapping(data.get("individual_masses"))
    return IndividualMasses(
        tuple(
            _gas_input_from_data(gases.get(str(index), {}))
            if species.state == "g"
            else MassValue(
                _mapping(masses.get(str(index), {})).get("value", ""),
                _text(_mapping(masses.get(str(index), {})).get("unit", "mg")),
            )
            for index, species in enumerate(equation.reactants)
        )
    )


class GasInputWidget(QGroupBox):
    """Éditeur contextuel d'un seul réactif gazeux, sans calcul local."""

    changed = Signal()

    def __init__(self, species_name: str, reactant_index: int, parent: QWidget | None = None):
        super().__init__(f"{species_name} (g)", parent)
        self.reactant_index = reactant_index
        layout = QVBoxLayout(self)
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem(_t('Masse finie'), "mass")
        self.mode_combo.addItem(_t('Pression partielle, volume et température'), "partial_pressure")
        self.mode_combo.addItem(_t('ppm molaire ou ppmv'), "fraction")
        self.mode_combo.addItem(_t('Gaz en excès'), "excess")
        self.mode_combo.addItem(_t('Débit × durée et composition'), "flow")
        layout.addWidget(self.mode_combo)
        self.stack = QStackedWidget(self)
        self.mass_value, self.mass_unit, mass_page = self._mass_page()
        self.partial_fields, partial_page = self._pvt_page(_t('Pression partielle'))
        self.fraction_fields, fraction_page = self._fraction_page()
        self.flow_fields, flow_page = self._flow_page()
        excess_page = QWidget(self)
        excess_layout = QVBoxLayout(excess_page)
        excess_layout.addWidget(QLabel(_t("Ce gaz ne limite pas l'avancement."), excess_page))
        excess_layout.addStretch(1)
        for page in (mass_page, partial_page, fraction_page, excess_page, flow_page):
            self.stack.addWidget(page)
        layout.addWidget(self.stack)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self._connect_changes()

    def _combo(self, values: tuple[str, ...], value: str) -> QComboBox:
        combo = QComboBox(self)
        combo.addItems(values)
        combo.setCurrentIndex(max(0, combo.findText(value)))
        return combo

    def _mass_page(self):
        page = QWidget(self)
        form = QFormLayout(page)
        value = QLineEdit(page)
        unit = self._combo(MASS_UNITS, "mg")
        form.addRow(_t('Masse'), value)
        form.addRow(_t('Unité'), unit)
        return value, unit, page

    def _pvt_page(self, pressure_label: str):
        page = QWidget(self)
        form = QFormLayout(page)
        fields = {
            "pressure": QLineEdit(page),
            "pressure_unit": self._combo(PRESSURE_UNITS, "bar"),
            "volume": QLineEdit(page),
            "volume_unit": self._combo(VOLUME_UNITS, "L"),
            "temperature": QLineEdit(page),
            "temperature_unit": self._combo(TEMPERATURE_UNITS, "°C"),
        }
        form.addRow(pressure_label, fields["pressure"])
        form.addRow(_t('Unité de pression'), fields["pressure_unit"])
        form.addRow(_t('Volume'), fields["volume"])
        form.addRow(_t('Unité de volume'), fields["volume_unit"])
        form.addRow(_t('Température'), fields["temperature"])
        form.addRow(_t('Unité de température'), fields["temperature_unit"])
        return fields, page

    def _fraction_page(self):
        fields, page = self._pvt_page(_t('Pression totale'))
        form = page.layout()
        value = QLineEdit(page)
        kind = self._combo(("molar_ppm", "ppmv"), "molar_ppm")
        form.insertRow(0, _t('Fraction'), value)
        form.insertRow(1, _t('Type'), kind)
        fields["value"] = value
        fields["kind"] = kind
        return fields, page

    def _connect_changes(self) -> None:
        widgets = [self.mass_value, self.mass_unit, *self.partial_fields.values(), *self.fraction_fields.values(), *self.flow_fields.values()]
        for widget in widgets:
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.changed)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self.changed)

    def _mode_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.changed.emit()

    @staticmethod
    def _field_data(fields: Mapping[str, QWidget]) -> dict[str, str]:
        return {
            name: canonical_number(widget.text()) if isinstance(widget, QLineEdit) else widget.currentData() or widget.currentText()
            for name, widget in fields.items()
        }

    def data(self) -> dict[str, Any]:
        return {
            "mode": self.mode_combo.currentData(),
            "mass": {"value": canonical_number(self.mass_value.text()), "unit": self.mass_unit.currentText()},
            "partial_pressure": self._field_data(self.partial_fields),
            "fraction": self._field_data(self.fraction_fields),
            "flow": self._field_data(self.flow_fields),
        }

    def set_data(self, value: object) -> None:
        data = _mapping(value)
        self.mode_combo.setCurrentIndex(
            max(0, self.mode_combo.findData(data.get("mode", "mass")))
        )
        mass = _mapping(data.get("mass"))
        self.mass_value.setText(_text(mass.get("value", "")))
        self.mass_unit.setCurrentIndex(max(0, self.mass_unit.findText(_text(mass.get("unit", "mg")))))
        for name, widget in self.partial_fields.items():
            item = _mapping(data.get("partial_pressure")).get(name, "")
            if isinstance(widget, QLineEdit):
                widget.setText(_text(item))
            else:
                widget.setCurrentIndex(max(0, widget.findText(_text(item))))
        for name, widget in self.fraction_fields.items():
            item = _mapping(data.get("fraction")).get(name, "")
            if isinstance(widget, QLineEdit):
                widget.setText(_text(item))
            else:
                widget.setCurrentIndex(max(0, widget.findText(_text(item))))
        for name, widget in self.flow_fields.items():
            item = _mapping(data.get("flow")).get(name, "")
            if isinstance(widget, QLineEdit):
                widget.setText(_text(item))
            else:
                index = widget.findData(item)
                widget.setCurrentIndex(max(0, index if index >= 0 else widget.findText(_text(item))))

    def _flow_page(self):
        fields, page = self._pvt_page(_t("Pression totale absolue de référence du débit"))
        form = page.layout()
        form.removeRow(fields.pop("volume"))
        form.removeRow(fields.pop("volume_unit"))
        form.labelForField(fields["temperature"]).setText(_t("Température de référence du débit"))
        fields.update(flow=QLineEdit(page), flow_unit=self._combo(("mL/min", "L/min", "mL/s", "L/s", "mL/h", "L/h"), "mL/min"),
                      duration=QLineEdit(page), duration_unit=self._combo(("min", "s", "h"), "min"),
                      value=QLineEdit(page), kind=QComboBox(page))
        for label, key in (("% (mol/mol)", "percent"), ("ppm (mol/mol)", "molar_ppm"), ("ppmv", "ppmv")):
            fields["kind"].addItem(label, key)
        for row, (label, key) in enumerate((("Débit total du mélange", "flow"), ("Unité de débit", "flow_unit"),
            ("Durée d'exposition", "duration"), ("Unité de durée", "duration_unit"), ("Teneur du gaz réactif", "value"), ("Unité de teneur", "kind"))):
            form.insertRow(row, _t(label), fields[key])
        notice = QLabel(_t("Débit et composition supposés constants. Utiliser les conditions de référence du débitmètre, pas celles du four. Quantité apportée, sans modèle de cinétique ni de diffusion."))
        notice.setWordWrap(True)
        form.addRow(notice)
        return fields, page


class StoichiometryDialog(QDialog):
    """Présentation et saisie, les calculs restant dans ``stoichiometry``."""

    project_changed = Signal()

    def __init__(self, workflow: ProjectWorkflow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workflow = workflow
        self._entries: list[dict[str, Any]] = []
        self._current_index: int | None = None
        self._current_equation: ChemicalEquation | None = None
        self._results: dict[int, CondensedMassBalance] = {}
        self._statuses: dict[int, str] = {}
        self._proposal_text: str | None = None
        self._loading = False
        self._gas_widgets: list[GasInputWidget] = []
        self.setWindowTitle(_t('Calculs stœchiométriques'))
        self.setModal(False)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setMinimumSize(900, 600)
        self.resize(1600, 1000)
        self._build_window()
        self._connect_signals()
        self.restore_project_state()

    def _build_window(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        editor = self._build_editor_scroll()
        top = QHBoxLayout()
        self.style_title = QLabel(_t("Console d'analyse"))
        self.style_title.setObjectName("workspaceTitle")
        top.addWidget(self.style_title)
        top.addStretch(1)
        self.calculate_button = QPushButton(_t('Calculer la sélection'), self)
        self.calculate_button.setProperty("primary", True)
        self.input_actions.addStretch(1)
        self.input_actions.addWidget(self.calculate_button)
        top.addWidget(self.copy_button)
        layout.addLayout(top)
        splitter = self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        left = FoldPanel(_t('Équations'), self._build_equation_list())
        splitter.addWidget(left)
        center = self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        center.setChildrenCollapsible(False)
        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(editor, 1)
        editor_layout.addLayout(self.input_actions)
        center.addWidget(editor_panel)
        bottom = FoldPanel(_t('3  Bilan théorique'), scroll_panel(self.result_group), vertical=True)
        center.addWidget(bottom)
        center.setStretchFactor(0, 1)
        center.setSizes([490, 380])
        splitter.addWidget(center)
        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.addWidget(self.species_group)
        inspector_layout.addWidget(self.units_group)
        inspector_layout.addStretch(1)
        right = FoldPanel(_t('Référence et unités'), scroll_panel(inspector), expanded_size=420)
        splitter.addWidget(right)
        self.panels = {"left": left, "right": right, "bottom": bottom}
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 900, 420])
        right.button.setChecked(False)
        layout.addWidget(splitter, 1)
        self.batch_summary = QLabel("", self)
        self.batch_summary.setWordWrap(True)
        layout.addWidget(self.batch_summary)

    def set_appearance(self) -> None:
        self.style_title.setText(_t("Console d'analyse"))
        self.equations_table.verticalHeader().setDefaultSectionSize(68)
        self.equation_edit.setProperty("console", True)
        self.equation_edit.style().unpolish(self.equation_edit)
        self.equation_edit.style().polish(self.equation_edit)
        for card in self.summary_cards:
            card.setProperty("console", True)
            card.style().unpolish(card)
            card.style().polish(card)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_table_widths_initialized", False):
            self._table_widths_initialized = True
            # Le panneau de référence est initialement caché : sa largeur Qt
            # provisoire ne doit pas réduire toutes ses colonnes à 50 pixels.
            for column, sample in enumerate((_t('Réactif'), "ν", _t('Formule'), _t('État'), "g/mol")):
                self.species_table.setColumnWidth(column, self.fontMetrics().horizontalAdvance(sample) + 28)
            width = min(700, self.mass_table.viewport().width())
            for column, ratio in enumerate((.4, .3, .3)):
                self.mass_table.setColumnWidth(column, max(60, int(width * ratio)))

    def _build_equation_list(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        self.equations_table = QTableWidget(0, 3, panel)
        self.equations_table.setHorizontalHeaderLabels((_t('Calcul'), _t('Équation'), _t('État')))
        self.equations_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.equations_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.equations_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.equations_table.setObjectName("equationsList")
        self.equations_table.setShowGrid(False)
        self.equations_table.verticalHeader().hide()
        self.equations_table.verticalHeader().setDefaultSectionSize(96)
        self.equations_table.horizontalHeader().hide()
        self.equations_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.equations_table.setColumnWidth(0, 28)
        self.equations_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.equations_table.hideColumn(2)
        self.equations_table.setItemDelegateForColumn(1, EquationDelegate(self.equations_table))
        layout.addWidget(self.equations_table, 1)
        buttons = QHBoxLayout()
        self.add_button = QPushButton(_t('Ajouter'), panel)
        self.add_button.setIcon(line_icon("add"))
        self.remove_button = QPushButton(_t('Supprimer'), panel)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        layout.addLayout(buttons)
        return panel

    def _build_editor_scroll(self) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        layout = QVBoxLayout(body)
        equation_group = QGroupBox(_t('1  Équation'), body)
        equation_group.setProperty("quiet", True)
        equation_layout = QVBoxLayout(equation_group)
        self.equation_edit = QLineEdit(equation_group)
        self.equation_edit.setObjectName("reactionEquation")
        self.equation_edit.setPlaceholderText(_t('Ex. CaCO3(s) = CaO(s) + CO2(g)'))
        self.equation_edit.setAccessibleName(_t('Équation courante'))
        self.equation_edit.setToolTip(_t("Hydrates et adduits : MgCl2.6H2O ou MgCl2·6H2O. Les états (s), (l) et (g) sont facultatifs ; (s) est utilisé par défaut."))
        equation_layout.addWidget(self.equation_edit)
        actions = QHBoxLayout()
        self.verify_button = QPushButton(_t('Vérifier'), equation_group)
        self.verify_button.setIcon(line_icon("check"))
        self.balance_button = QPushButton(_t('Équilibrer'), equation_group)
        self.apply_proposal_button = QPushButton(_t('Utiliser la proposition'), equation_group)
        self.apply_proposal_button.setEnabled(False)
        self.apply_proposal_button.hide()
        for button in (self.verify_button, self.balance_button, self.apply_proposal_button):
            actions.addWidget(button)
        equation_layout.addLayout(actions)
        self.balance_ratios_button = QPushButton(_t('Conserver les proportions saisies'), equation_group)
        self.balance_ratios_button.hide()
        self.advanced_button = QToolButton()
        self.advanced_button.setText(_t("Options d'équilibrage"))
        self.advanced_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_button.setIcon(line_icon("settings"))
        self.advanced_button.setCheckable(True)
        self.advanced_button.toggled.connect(self.balance_ratios_button.setVisible)
        actions.addWidget(self.advanced_button)
        actions.addStretch(1)
        equation_layout.addWidget(self.balance_ratios_button)
        self.validation_label = QLabel("", equation_group)
        self.validation_label.setWordWrap(True)
        self.proposal_label = QLabel("", equation_group)
        self.proposal_label.setWordWrap(True)
        equation_layout.addWidget(self.validation_label)
        equation_layout.addWidget(self.proposal_label)
        layout.addWidget(equation_group)
        species_group = self.species_group = QGroupBox(_t('Espèces et masses molaires'), body)
        species_group.setProperty("quiet", True)
        species_layout = QVBoxLayout(species_group)
        self.species_table = QTableWidget(0, 5, species_group)
        self.species_table.setHorizontalHeaderLabels((_t('Rôle'), "ν", _t('Formule'), _t('État'), "g/mol"))
        self.species_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.species_table.verticalHeader().hide()
        self.species_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        species_layout.addWidget(self.species_table)
        self.inputs_group = QGroupBox(_t('2  Données initiales'), body)
        self.inputs_group.setProperty("quiet", True)
        inputs_layout = QVBoxLayout(self.inputs_group)
        modes = QHBoxLayout()
        self.individual_radio = QRadioButton(_t('Masses individuelles'), self.inputs_group)
        self.total_radio = QRadioButton(_t('Masse totale'), self.inputs_group)
        self.individual_radio.setChecked(True)
        self.condensed_modes = QButtonGroup(self.inputs_group)
        self.condensed_modes.addButton(self.individual_radio)
        self.condensed_modes.addButton(self.total_radio)
        modes.addWidget(self.individual_radio)
        modes.addWidget(self.total_radio)
        modes.addStretch(1)
        inputs_layout.addLayout(modes)
        self.mass_table = QTableWidget(0, 3, self.inputs_group)
        self.mass_table.setHorizontalHeaderLabels((_t('Réactif'), _t('Masse'), _t('Unité')))
        self.mass_table.verticalHeader().hide()
        self.mass_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.mass_table.setMinimumHeight(80)
        self.mass_table.setMaximumHeight(200)
        self.mass_table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.mass_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        inputs_layout.addWidget(self.mass_table)
        total_form = QFormLayout()
        self.total_mass_value = QLineEdit(self.inputs_group)
        self.total_mass_unit = QComboBox(self.inputs_group)
        self.total_mass_unit.addItems(MASS_UNITS)
        total_form.addRow(_t('Masse totale'), self.total_mass_value)
        total_form.addRow(_t('Unité'), self.total_mass_unit)
        self.total_mass_hint = QLabel(_t('Mélange condensé supposé stœchiométrique'), self.inputs_group)
        self.total_mass_hint.setWordWrap(True)
        total_form.addRow(self.total_mass_hint)
        self.total_container = QWidget(self.inputs_group)
        self.total_container.setLayout(total_form)
        inputs_layout.addWidget(self.total_container)
        self.gases_container = QGroupBox(_t('Gaz réactifs'))
        self.gases_container.setProperty("quiet", True)
        self.gases_layout = QVBoxLayout(self.gases_container)
        result_group = self.result_group = QWidget()
        result_layout = QVBoxLayout(result_group)
        self.units_group = QGroupBox(_t('Affichage du résultat'))
        self.units_group.setProperty("quiet", True)
        display_form = QFormLayout()
        self.display_mass_unit = QComboBox(result_group)
        self.display_mass_unit.addItems(MASS_UNITS)
        self.display_amount_unit = QComboBox(result_group)
        self.display_amount_unit.addItems(tuple(AMOUNT_UNIT_TO_MOLES))
        self.display_notation = QComboBox(result_group)
        self.display_notation.addItem(_t('Décimale'), "decimal")
        self.display_notation.addItem(_t('Scientifique'), "scientific")
        display_form.addRow(_t('Masses'), self.display_mass_unit)
        display_form.addRow("Quantités", self.display_amount_unit)
        display_form.addRow(_t('Notation'), self.display_notation)
        display_form.addRow(QLabel(_t('3 chiffres significatifs')))
        self.units_group.setLayout(display_form)
        summary = QHBoxLayout()
        self.summary_cards = []
        self.summary_values = []
        self.delta_title = None
        for title in (_t('Masse initiale condensée'), _t('Masse finale condensée'), _t('Δm condensée'), _t('Variation relative')):
            card = QWidget()
            card.setObjectName("massSummaryCard")
            card_layout = QVBoxLayout(card)
            label = QLabel(title)
            if title == _t('Δm condensée'):
                self.delta_title = label
                card.setProperty("massChange", True)
            label.setWordWrap(True)
            value = QLabel("-")
            value.setObjectName("massSummaryValue")
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            summary.addWidget(card, 1)
            self.summary_cards.append(card)
            self.summary_values.append(value)
        result_layout.addLayout(summary)
        self.balance_summary = QLabel(_t("Vérifiez l'équation et renseignez les données initiales."))
        self.balance_summary.setWordWrap(True)
        result_layout.addWidget(self.balance_summary)
        self.balance_table = QTableWidget(0, 4)
        self.balance_table.setHorizontalHeaderLabels((_t('Espèce'), _t('Initial'), _t('Consommé / produit'), _t('Restant')))
        self.balance_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.balance_table.verticalHeader().hide()
        self.balance_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.balance_table.setMinimumHeight(110)
        result_layout.addWidget(self.balance_table)
        self.details_button = QToolButton()
        self.details_button.setText(_t('Hypothèses et détail du calcul'))
        self.details_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_button.setCheckable(True)
        self.details_button.setIcon(line_icon("down"))
        result_layout.addWidget(self.details_button)
        self.result_text = QPlainTextEdit(result_group)
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(180)
        self.result_text.hide()
        self.details_button.toggled.connect(self.result_text.setVisible)
        self.details_button.toggled.connect(lambda expanded: self.details_button.setIcon(
            line_icon("up" if expanded else "down")))
        self.copy_button = QPushButton(_t('Copier le résultat'), result_group)
        self.copy_button.setIcon(line_icon("copy"))
        self.copy_button.setEnabled(False)
        result_layout.addWidget(self.result_text)
        layout.addWidget(self.inputs_group)
        layout.addWidget(self.gases_container)
        self.input_actions = QHBoxLayout()
        layout.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def _connect_signals(self) -> None:
        self.add_button.clicked.connect(self.add_equation)
        self.remove_button.clicked.connect(self.remove_current_equation)
        self.equations_table.itemChanged.connect(self._checkbox_changed)
        self.equations_table.itemSelectionChanged.connect(self._selection_changed)
        self.equation_edit.textChanged.connect(self._equation_changed)
        self.verify_button.clicked.connect(self.verify_current)
        self.balance_button.clicked.connect(self.propose_balance)
        self.balance_ratios_button.clicked.connect(
            lambda: self.propose_balance(preserve_reactant_ratios=True)
        )
        self.apply_proposal_button.clicked.connect(self.apply_proposal)
        self.condensed_modes.buttonToggled.connect(
            lambda _button, checked: self._inputs_changed() if checked else None
        )
        self.mass_table.itemChanged.connect(self._inputs_changed)
        self.total_mass_value.textChanged.connect(self._inputs_changed)
        self.total_mass_unit.currentIndexChanged.connect(self._inputs_changed)
        self.calculate_button.clicked.connect(self.calculate_checked)
        self.copy_button.clicked.connect(self.copy_result)
        for combo in (self.display_mass_unit, self.display_amount_unit, self.display_notation):
            combo.currentIndexChanged.connect(self._display_changed)

    def restore_project_state(self) -> None:
        data = self.workflow.project_document.stoichiometry
        self._loading = True
        try:
            display = data.get("display", default_stoichiometry_settings()["display"])
            self.display_mass_unit.setCurrentText(display["mass_unit"])
            self.display_amount_unit.setCurrentText(display["amount_unit"])
            self.display_notation.setCurrentIndex(self.display_notation.findData(display["notation"]))
            self._entries = deepcopy(list(data.get("equations", [])))
            self._current_index = data.get("current_index")
            if self._current_index is None and self._entries:
                self._current_index = 0
            self._results.clear()
            self._statuses.clear()
            self._refresh_equation_table()
            if self._current_index is not None:
                self.equations_table.setCurrentCell(self._current_index, 1)
                self._load_current_entry()
            else:
                self._clear_editor()
        finally:
            self._loading = False

    def add_equation(self) -> None:
        self._store_current_entry()
        self._entries.append(_new_entry())
        self._current_index = len(self._entries) - 1
        self._statuses[self._current_index] = _t('À vérifier')
        self._refresh_equation_table()
        self.equations_table.setCurrentCell(self._current_index, 1)
        self._load_current_entry()
        self._persist()

    def remove_current_equation(self) -> None:
        if self._current_index is None:
            return
        removed = self._current_index
        self._entries.pop(removed)
        self._results = {
            index - (index > removed): result
            for index, result in self._results.items()
            if index != removed
        }
        self._statuses = {
            index - (index > removed): status
            for index, status in self._statuses.items()
            if index != removed
        }
        self._current_index = min(removed, len(self._entries) - 1) if self._entries else None
        self._refresh_equation_table()
        if self._current_index is None:
            self._clear_editor()
        else:
            self.equations_table.setCurrentCell(self._current_index, 1)
            self._load_current_entry()
        self._persist()

    def _refresh_equation_table(self) -> None:
        self.equations_table.blockSignals(True)
        self.equations_table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            checked = QTableWidgetItem()
            checked.setFlags(checked.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked.setCheckState(
                Qt.CheckState.Checked if entry.get("checked") else Qt.CheckState.Unchecked
            )
            text = _text(entry.get("text", ""))
            equation = QTableWidgetItem(text or _t('Nouvelle équation'))
            equation.setToolTip(text)
            status = QTableWidgetItem(self._statuses.get(row, _t('À vérifier')))
            self.equations_table.setItem(row, 0, checked)
            self.equations_table.setItem(row, 1, equation)
            self.equations_table.setItem(row, 2, status)
        self.equations_table.blockSignals(False)

    def _checkbox_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 0:
            return
        self._entries[item.row()]["checked"] = item.checkState() == Qt.CheckState.Checked
        self._persist()

    def _selection_changed(self) -> None:
        if self._loading:
            return
        row = self.equations_table.currentRow()
        if row < 0 or row == self._current_index:
            return
        self._store_current_entry()
        self._current_index = row
        self._load_current_entry()
        self._persist()

    def _clear_editor(self) -> None:
        self._current_equation = None
        self._proposal_text = None
        self.equation_edit.clear()
        self.validation_label.clear()
        self.proposal_label.clear()
        self.apply_proposal_button.setEnabled(False)
        self.species_table.setRowCount(0)
        self.apply_proposal_button.hide()
        self.mass_table.setRowCount(0)
        self._clear_gas_widgets()
        self.result_text.clear()
        self._show_current_result()
        self.copy_button.setEnabled(False)

    def _load_current_entry(self) -> None:
        if self._current_index is None:
            self._clear_editor()
            return
        entry = self._entries[self._current_index]
        self._loading = True
        try:
            self.equation_edit.setText(_text(entry.get("text", "")))
            self._proposal_text = None
            self.proposal_label.clear()
            self.apply_proposal_button.setEnabled(False)
            self.apply_proposal_button.hide()
            self.validation_label.setText("")
            self._current_equation = None
            try:
                equation = parse_equation(self.equation_edit.text())
            except StoichiometryError:
                self.species_table.setRowCount(0)
                self.mass_table.setRowCount(0)
                self._clear_gas_widgets()
            else:
                self._set_equation(equation, _mapping(entry.get("inputs")))
            self._show_current_result()
        finally:
            self._loading = False

    def _set_equation(self, equation: ChemicalEquation, inputs: Mapping[str, Any]) -> None:
        self.validation_label.setText(
            _t('Équation équilibrée') if is_balanced(equation) else _t('Équation non équilibrée')
        )
        self._current_equation = equation
        self.species_table.setRowCount(0)
        for role, specieses in ((_t('Réactif'), equation.reactants), (_t('Produit'), equation.products)):
            for species in specieses:
                row = self.species_table.rowCount()
                self.species_table.insertRow(row)
                values = (
                    role,
                    str(species.coefficient),
                    species.formula,
                    f"({species.state})",
                    self._number(species.molar_mass),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    self.species_table.setItem(row, column, item)
        mode = inputs.get("condensed_mode", "individual")
        self.individual_radio.setChecked(mode != "total")
        self.total_radio.setChecked(mode == "total")
        total = _mapping(inputs.get("total_mass"))
        self.total_mass_value.setText(_text(total.get("value", "")))
        self.total_mass_unit.setCurrentIndex(
            max(0, self.total_mass_unit.findText(_text(total.get("unit", "mg"))))
        )
        self._populate_mass_table(equation, _mapping(inputs.get("individual_masses")))
        self._populate_gases(equation, _mapping(inputs.get("gases")))
        self._update_input_mode()

    def _populate_mass_table(
        self, equation: ChemicalEquation, values: Mapping[str, Any]
    ) -> None:
        self.mass_table.blockSignals(True)
        self.mass_table.setRowCount(0)
        for index, species in enumerate(equation.reactants):
            if species.state == "g":
                continue
            row = self.mass_table.rowCount()
            self.mass_table.insertRow(row)
            name = QTableWidgetItem(f"{species.formula} ({species.state})")
            name.setData(Qt.ItemDataRole.UserRole, index)
            self.mass_table.setItem(row, 0, name)
            item = _mapping(values.get(str(index)))
            self.mass_table.setItem(row, 1, QTableWidgetItem(_text(item.get("value", ""))))
            unit = QComboBox(self.mass_table)
            unit.addItems(MASS_UNITS)
            unit.setCurrentIndex(max(0, unit.findText(_text(item.get("unit", "mg")))))
            unit.currentIndexChanged.connect(self._inputs_changed)
            self.mass_table.setCellWidget(row, 2, unit)
        self.mass_table.blockSignals(False)

    def _clear_gas_widgets(self) -> None:
        self.gases_container.hide()
        while self.gases_layout.count():
            item = self.gases_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._gas_widgets = []

    def _populate_gases(self, equation: ChemicalEquation, values: Mapping[str, Any]) -> None:
        self._clear_gas_widgets()
        for index, species in enumerate(equation.reactants):
            if species.state != "g":
                continue
            widget = GasInputWidget(species.formula, index, self.gases_container)
            widget.set_data(values.get(str(index), {}))
            widget.changed.connect(self._inputs_changed)
            self.gases_layout.addWidget(widget)
            self._gas_widgets.append(widget)
        self.gases_container.setVisible(bool(self._gas_widgets))

    def _equation_changed(self) -> None:
        if self._loading or self._current_index is None:
            return
        self._current_equation = None
        self._invalidate_current_result(_t('À vérifier'))
        self.validation_label.clear()
        self._proposal_text = None
        self.proposal_label.clear()
        self.apply_proposal_button.setEnabled(False)
        self.apply_proposal_button.hide()
        self._store_current_entry()
        self._refresh_equation_table()
        self._persist()

    def _inputs_changed(self, *_args) -> None:
        if self._loading:
            return
        self._update_input_mode()
        if self._current_index is None:
            return
        self._invalidate_current_result()
        self._store_current_entry()
        self._persist()

    def _invalidate_current_result(self, status: str = _t('À recalculer')) -> None:
        self._results.pop(self._current_index, None)
        self._set_status(status)
        self._show_current_result()
        self.batch_summary.clear()

    def _show_current_result(self, error: str = "") -> None:
        result = self._results.get(self._current_index)
        self.result_text.setPlainText(
            error if result is None else self._format_result(self._entries[self._current_index], result)
        )
        self.copy_button.setEnabled(result is not None)
        self.balance_table.setRowCount(0)
        if result is None:
            self.delta_title.setText(_t('Δm condensée'))
            for label in self.summary_values:
                label.setText("-")
            self.balance_summary.setText(error or _t('Renseignez les données puis calculez la sélection.'))
            return
        values = (
            self._mass(result.initial_condensed_mass_g),
            self._mass(result.final_condensed_mass_g),
            self._mass(result.delta_mass_g, signed=True),
            f"{self._number(result.variation_percent)} %",
        )
        change = _t('gain') if result.delta_mass_g > 0 else _t('perte') if result.delta_mass_g < 0 else _t('aucune variation')
        self.delta_title.setText(_t('Δm condensée ({v1})', v1=change))
        for label, value in zip(self.summary_values, values):
            label.setText(value)
        limiting = ", ".join(result.reactants[i].species.formula for i in result.limiting_reactant_indices)
        self.balance_summary.setText(
            _t('Réactif(s) limitant(s) : {v1}     Avancement maximal : {v3}', v1=limiting, v3=self._amount(result.extent_mol))
        )
        rows = [
            (f"{item.species.formula} ({item.species.state})",
             self._amount(item.initial_amount_mol),
             "−" + self._amount(item.consumed_amount_mol),
             self._amount(item.final_amount_mol))
            for item in result.reactants
        ]
        rows.extend(
            (f"{item.species.formula} ({item.species.state})", self._amount(Decimal(0)),
             "+" + self._amount(item.produced_amount_mol), self._amount(item.produced_amount_mol))
            for item in result.products
        )
        self.balance_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.balance_table.setItem(row, column, QTableWidgetItem(value))

    def _update_input_mode(self) -> None:
        individual = self.individual_radio.isChecked()
        self.mass_table.setVisible(individual)
        self.total_container.setVisible(not individual)

    def _display_changed(self, *_args) -> None:
        if self._loading:
            return
        if self._current_equation is not None:
            species = (*self._current_equation.reactants, *self._current_equation.products)
            for row, item in enumerate(species):
                self.species_table.item(row, 4).setText(self._number(item.molar_mass))
        self._show_current_result()
        self._persist()

    def _store_current_entry(self) -> None:
        if self._loading or self._current_index is None:
            return
        entry = self._entries[self._current_index]
        entry["text"] = self.equation_edit.text()
        entry["atomic_data_source_id"] = SOURCE_ID
        if self._current_equation is None:
            return
        masses = {}
        for row in range(self.mass_table.rowCount()):
            index = self.mass_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            unit = self.mass_table.cellWidget(row, 2)
            masses[str(index)] = {
                "value": canonical_number(self.mass_table.item(row, 1).text()),
                "unit": unit.currentText(),
            }
        entry["inputs"] = {
            "condensed_mode": "individual" if self.individual_radio.isChecked() else "total",
            "individual_masses": masses,
            "total_mass": {
                "value": canonical_number(self.total_mass_value.text()),
                "unit": self.total_mass_unit.currentText(),
            },
            "gases": {str(widget.reactant_index): widget.data() for widget in self._gas_widgets},
        }

    def _persist(self) -> None:
        self.workflow.set_stoichiometry(
            {
                "version": 1,
                "current_index": self._current_index,
                "equations": deepcopy(self._entries),
                "display": {
                    "mass_unit": self.display_mass_unit.currentText(),
                    "amount_unit": self.display_amount_unit.currentText(),
                    "notation": self.display_notation.currentData(),
                },
            }
        )
        self.project_changed.emit()

    def _set_status(self, status: str) -> None:
        if self._current_index is None:
            return
        self._statuses[self._current_index] = status
        item = self.equations_table.item(self._current_index, 2)
        if item is not None:
            item.setText(status)
            self.equations_table.viewport().update()

    def verify_current(self) -> ChemicalEquation | None:
        if self._current_index is None:
            self.validation_label.setText(_t('Ajoutez une équation avant de la vérifier.'))
            return None
        self._store_current_entry()
        try:
            equation = parse_equation(self.equation_edit.text())
        except StoichiometryError as exc:
            self._current_equation = None
            self.validation_label.setText(_t(str(exc)))
            self._set_status(_t('Erreur de saisie'))
            return None
        self._loading = True
        try:
            self._set_equation(
                equation, _mapping(self._entries[self._current_index].get("inputs"))
            )
        finally:
            self._loading = False
        if not is_balanced(equation):
            self.validation_label.setText(_t('Équation valide, mais non équilibrée.'))
            self._set_status(_t('Non équilibrée'))
            return None
        self.validation_label.setText(_t('Équation valide et équilibrée.'))
        self._set_status(_t('Valide'))
        self._store_current_entry()
        self._persist()
        return equation

    def propose_balance(
        self, _checked: bool = False, *, preserve_reactant_ratios: bool = False
    ) -> None:
        self._proposal_text = None
        self.apply_proposal_button.setEnabled(False)
        self.apply_proposal_button.hide()
        constraint_text = ""
        try:
            equation = parse_equation(self.equation_edit.text())
            if preserve_reactant_ratios:
                names = ":".join(item.formula for item in equation.reactants)
                ratios = ":".join(
                    str(item.coefficient / equation.reactants[0].coefficient)
                    for item in equation.reactants
                )
                constraint_text = _t('Proportions réactives conservées : {v1} = {v3}.\n', v1=names, v3=ratios)
            proposal = balance_equation(
                equation, preserve_reactant_ratios=preserve_reactant_ratios
            )
        except (StoichiometryError, BalanceError) as exc:
            self.proposal_label.setText(f"{constraint_text}{exc}")
            return
        self._proposal_text = format_equation(proposal)
        self.proposal_label.setText(_t('{v0}Proposition : {v2}', v0=constraint_text, v2=self._proposal_text))
        self.apply_proposal_button.setEnabled(True)
        self.apply_proposal_button.show()

    def apply_proposal(self) -> None:
        if self._proposal_text is None:
            return
        self.equation_edit.setText(self._proposal_text)
        self._proposal_text = None
        self.proposal_label.clear()
        self.apply_proposal_button.setEnabled(False)
        self.apply_proposal_button.hide()
        self.verify_current()

    def calculate_checked(self) -> None:
        self._store_current_entry()
        selected = [index for index, entry in enumerate(self._entries) if entry.get("checked")]
        if not selected:
            self.batch_summary.setText(_t('Aucune équation cochée.'))
            return
        completed = failed = 0
        current_error = ""
        for index in selected:
            entry = self._entries[index]
            try:
                equation = parse_equation(_text(entry.get("text", "")))
                if not is_balanced(equation):
                    raise MassBalanceError(_t("L'équation n'est pas équilibrée."))
                result = calculate_condensed_mass_balance(
                    equation, _inputs_for_equation(equation, entry)
                )
            except (StoichiometryError, BalanceError, MassBalanceError) as exc:
                self._results.pop(index, None)
                self._statuses[index] = _t('Erreur de calcul')
                failed += 1
                if index == self._current_index:
                    current_error = _t(str(exc))
            else:
                self._results[index] = result
                self._statuses[index] = _t('Calculée')
                completed += 1
        self._refresh_equation_table()
        self._show_current_result(current_error)
        self.batch_summary.setText(_t('Lot : {v1} calculée(s), {v3} en erreur.', v1=completed, v3=failed))

    def _number(
        self, value: Decimal | None, *, factor: Decimal = Decimal(1), signed: bool = False
    ) -> str:
        if value is None or not value.is_finite():
            return _t('non défini')
        if not value:
            return "0"
        with localcontext() as context:
            context.prec = max(28, len(value.as_tuple().digits) + 6)
            context.rounding = ROUND_HALF_EVEN
            scientific = f"{value / factor:.2E}"
        mantissa, exponent = scientific.split("E")
        if self.display_notation.currentData() == "scientific" and abs(int(exponent)) > 2:
            superscript = str(int(exponent)).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
            text = f"{mantissa} × 10{superscript}"
        else:
            text = f"{Decimal(scientific):f}"
        return ("+" if signed and value > 0 else "") + (text.replace(".", ",") if language() == "fr" else text)

    def _mass(self, value: Decimal | None, *, signed: bool = False) -> str:
        unit = self.display_mass_unit.currentText()
        return f"{self._number(value, factor=MASS_UNIT_TO_GRAMS[unit], signed=signed)} {unit}"

    def _amount(self, value: Decimal | None) -> str:
        unit = self.display_amount_unit.currentText()
        return f"{self._number(value, factor=AMOUNT_UNIT_TO_MOLES[unit])} {unit}"

    def _format_result(self, entry: Mapping[str, Any], result: CondensedMassBalance) -> str:
        inputs = _mapping(entry.get("inputs"))
        reactant_labels = [
            f"{detail.species.formula}({detail.species.state}) (n° {index + 1})"
            for index, detail in enumerate(result.reactants)
        ]
        limiting_label = (
            _t('Réactif limitant') if len(result.limiting_reactant_indices) == 1
            else _t('Réactifs limitants simultanés')
        )
        limiting_names = ", ".join(reactant_labels[index] for index in result.limiting_reactant_indices)
        mode = (
            _t('Masses individuelles')
            if inputs.get("condensed_mode", "individual") == "individual"
            else _t("Masse totale de l'échantillon")
        )
        lines = [
            _t('Équation : {v1}', v1=result.equation_text),
            _t('Entrées condensées : {v1}', v1=mode),
            _t('Référentiel atomique : {v1}', v1=result.atomic_data_source_id),
            *self._format_inputs(inputs, result.equation),
            f"{limiting_label} : {limiting_names}",
            _t('Avancement maximal théorique : {v1}', v1=self._amount(result.extent_mol)),
            _t("Limitants déterminés avant l'arrondi d'affichage."),
            _t('Bilan : {v1}', v1=_t(result.direction)),
            f"Δm : {self._mass(result.delta_mass_g, signed=True)}",
            _t('Masse initiale condensée : {v1}', v1=self._mass(result.initial_condensed_mass_g)),
            _t('Masse finale condensée : {v1}', v1=self._mass(result.final_condensed_mass_g)),
            _t('Variation : {v1} %', v1=self._number(result.variation_percent)),
            "",
            _t('Espèces :'),
        ]
        for label, detail in zip(reactant_labels, result.reactants):
            lines.append(
                _t(
                    '- Réactif {v1} : initial {v3} ({v5}), consommé {v7} ({v9}), reste {v11} ({v13}).',
                    v1=label,
                    v3=self._amount(detail.initial_amount_mol),
                    v5=self._mass(detail.initial_mass_g),
                    v7=self._amount(detail.consumed_amount_mol),
                    v9=self._mass(detail.consumed_mass_g),
                    v11=self._amount(detail.final_amount_mol),
                    v13=self._mass(detail.final_mass_g),
                )
            )
        for detail in result.products:
            lines.append(
                _t(
                    '- Produit {v1} : {v3} ({v5}).',
                    v1=detail.species.formula,
                    v3=self._amount(detail.produced_amount_mol),
                    v5=self._mass(detail.produced_mass_g),
                )
            )
        lines.extend(("", _t('Hypothèses :'), *(f"- {_t(item)}" for item in result.assumptions)))
        return "\n".join(lines)

    @staticmethod
    def _format_inputs(inputs: Mapping[str, Any], equation: ChemicalEquation) -> list[str]:
        lines = [_t('Saisies :')]
        masses = _mapping(inputs.get("individual_masses"))
        if inputs.get("condensed_mode", "individual") == "total":
            total = _mapping(inputs.get("total_mass"))
            lines.append(
                _t('- Masse totale : {v1} {v3}', v1=_text(total.get('value')), v3=_text(total.get('unit')))
            )
        else:
            for index, species in enumerate(equation.reactants):
                if species.state == "g":
                    continue
                mass = _mapping(masses.get(str(index)))
                lines.append(
                    f"- {species.formula} : {_text(mass.get('value'))} {_text(mass.get('unit'))}"
                )
        gases = _mapping(inputs.get("gases"))
        for index, species in enumerate(equation.reactants):
            if species.state != "g":
                continue
            gas = _mapping(gases.get(str(index)))
            mode = gas.get("mode", "mass")
            if mode == "mass":
                mass = _mapping(gas.get("mass"))
                lines.append(
                    f"- {species.formula} : {_text(mass.get('value'))} {_text(mass.get('unit'))}"
                )
            elif mode == "partial_pressure":
                values = _mapping(gas.get("partial_pressure"))
                lines.append(
                    f"- {species.formula} : p={_text(values.get('pressure'))} "
                    f"{_text(values.get('pressure_unit'))}, V={_text(values.get('volume'))} "
                    f"{_text(values.get('volume_unit'))}, T={_text(values.get('temperature'))} "
                    f"{_text(values.get('temperature_unit'))}"
                )
            elif mode == "fraction":
                values = _mapping(gas.get("fraction"))
                lines.append(
                    f"- {species.formula} : {_text(values.get('value'))} "
                    f"{_text(values.get('kind'))}, p={_text(values.get('pressure'))} "
                    f"{_text(values.get('pressure_unit'))}, V={_text(values.get('volume'))} "
                    f"{_text(values.get('volume_unit'))}, T={_text(values.get('temperature'))} "
                    f"{_text(values.get('temperature_unit'))}"
                )
            elif mode == "flow":
                values = _mapping(gas.get("flow"))
                lines.append(f"- {species.formula} : Q={_text(values.get('flow'))} {_text(values.get('flow_unit'))}, "
                    f"t={_text(values.get('duration'))} {_text(values.get('duration_unit'))}, "
                    f"x={_text(values.get('value'))} {_text(values.get('kind'))}, "
                    f"P_ref={_text(values.get('pressure'))} {_text(values.get('pressure_unit'))}, "
                    f"T_ref={_text(values.get('temperature'))} {_text(values.get('temperature_unit'))}")
            else:
                lines.append(_t('- {v1} : gaz en excès', v1=species.formula))
        return lines

    def copy_result(self) -> None:
        if self._current_index in self._results and self.copy_button.isEnabled():
            QApplication.clipboard().setText(self.result_text.toPlainText())
            self.batch_summary.setText(_t('Résultat copié dans le presse-papiers.'))
