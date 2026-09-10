"""Dialogue Qt partagé pour les réglages déclaratifs des graphiques."""

from __future__ import annotations

from atg_dsc_corrector.i18n import tr as _t

from copy import deepcopy
import json
import math
from uuid import uuid4

from PySide6.QtCore import QSignalBlocker, Qt
from .number_format import number_locale, parse_number
from atg_dsc_corrector.i18n import decimal_text
from PySide6.QtGui import QColor, QDoubleValidator, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .color_button import ColorButton
from atg_dsc_corrector.projects import (
    default_graph_settings,
    graph_from_template_payload,
    graph_template_payload,
    ProjectValidationError,
)


AXIS_LABELS = {
    "x": 'Axe X',
    "tg": "TG",
    "dtg": "dTG",
    "heat_flow": 'Flux de chaleur',
}
LINE_STYLES = {
    "-": 'Continue',
    "--": 'Tirets',
    "-.": 'Mixte',
    ":": 'Points',
}


def _color_button(color: str) -> QPushButton:
    button = ColorButton(color.upper())
    button.setProperty("graphColor", color.upper())
    button.setAccessibleName(_t('Couleur {v1}', v1=color.upper()))

    def choose() -> None:
        selected = QColorDialog.getColor(QColor(button.property("graphColor")), button)
        if selected.isValid():
            value = selected.name().upper()
            button.setProperty("graphColor", value)
            button.setText(value)
            button.setAccessibleName(_t('Couleur {v1}', v1=value))

    button.clicked.connect(choose)
    return button


class _ReferenceLineDialog(QDialog):
    def __init__(self, line: dict[str, object] | None, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t('Ligne de référence'))
        self.setModal(True)
        self._locale = number_locale()
        self.setLocale(self._locale)
        layout = QFormLayout(self)

        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem(_t('Verticale'), "vertical")
        self.orientation_combo.addItem(_t('Horizontale'), "horizontal")
        layout.addRow(_t('Orientation'), self.orientation_combo)
        self.axis_combo = QComboBox()
        layout.addRow(_t('Axe cible'), self.axis_combo)

        validator = QDoubleValidator(self)
        validator.setLocale(self._locale)
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        self.value_entry = QLineEdit()
        self.value_entry.setValidator(validator)
        self.value_entry.setAccessibleName(_t('Valeur de la ligne de référence'))
        layout.addRow(_t('Valeur'), self.value_entry)
        self.label_entry = QLineEdit()
        layout.addRow(_t('Libellé'), self.label_entry)
        self.visible_check = QCheckBox(_t('Afficher la ligne'))
        layout.addRow(self.visible_check)
        self.color_button = _color_button("#666666")
        layout.addRow(_t('Couleur'), self.color_button)
        self.style_combo = QComboBox()
        for value, label in LINE_STYLES.items():
            self.style_combo.addItem(_t(label), value)
        layout.addRow(_t('Style'), self.style_combo)
        self.width_entry = QLineEdit("1")
        self.width_entry.setValidator(validator)
        layout.addRow(_t('Épaisseur'), self.width_entry)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_t('Annuler'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.orientation_combo.currentIndexChanged.connect(self._restore_targets)

        line = line or {}
        self.orientation_combo.setCurrentIndex(
            max(0, self.orientation_combo.findData(line.get("orientation", "vertical")))
        )
        self._restore_targets()
        self.axis_combo.setCurrentIndex(
            max(0, self.axis_combo.findData(line.get("axis", "x")))
        )
        if line.get("value") is not None:
            self.value_entry.setText(
                self._locale.toString(float(line["value"]), "g", 12)
            )
        self.label_entry.setText(str(line.get("label", "")))
        self.visible_check.setChecked(bool(line.get("visible", True)))
        color = str(line.get("color", "#666666")).upper()
        self.color_button.setProperty("graphColor", color)
        self.color_button.setText(color)
        self.style_combo.setCurrentIndex(
            max(0, self.style_combo.findData(line.get("line_style", "--")))
        )
        self.width_entry.setText(
            self._locale.toString(float(line.get("line_width", 1.0)), "g", 12)
        )

    def _restore_targets(self) -> None:
        current = self.axis_combo.currentData()
        self.axis_combo.clear()
        if self.orientation_combo.currentData() == "vertical":
            self.axis_combo.addItem(_t(AXIS_LABELS["x"]), "x")
        else:
            for role in ("tg", "dtg", "heat_flow"):
                self.axis_combo.addItem(_t(AXIS_LABELS[role]), role)
        self.axis_combo.setCurrentIndex(max(0, self.axis_combo.findData(current)))

    def line_value(self, identifier: str) -> dict[str, object]:
        value, valid = parse_number(self.value_entry.text(), self._locale)
        width, width_valid = parse_number(self.width_entry.text(), self._locale)
        if not valid or not math.isfinite(value):
            raise ValueError(_t('La valeur de la ligne doit être un nombre fini.'))
        if not width_valid or not math.isfinite(width) or not 0.1 <= width <= 10.0:
            raise ValueError(_t("L'épaisseur doit être comprise entre 0,1 et 10."))
        return {
            "id": identifier,
            "orientation": str(self.orientation_combo.currentData()),
            "axis": str(self.axis_combo.currentData()),
            "value": float(value),
            "label": self.label_entry.text().strip(),
            "visible": self.visible_check.isChecked(),
            "color": str(self.color_button.property("graphColor")),
            "line_style": str(self.style_combo.currentData()),
            "line_width": float(width),
        }

    def accept(self) -> None:
        try:
            self.line_value("validation")
        except ValueError as exc:
            QMessageBox.warning(self, _t('Ligne de référence'), _t(str(exc)))
            return
        super().accept()


class _AnnotationDialog(QDialog):
    def __init__(self, annotation: dict[str, object] | None, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t('Annotation'))
        self._locale = number_locale()
        self.setLocale(self._locale)
        form = QFormLayout(self)
        annotation = annotation or {}
        self.text_entry = QLineEdit(str(annotation.get("text", "")))
        form.addRow(_t('Texte'), self.text_entry)
        self.axis_combo = QComboBox()
        for role, label in AXIS_LABELS.items():
            self.axis_combo.addItem(_t(label), role)
        self.axis_combo.setCurrentIndex(max(0, self.axis_combo.findData(annotation.get("axis", "x"))))
        form.addRow(_t('Axe cible'), self.axis_combo)
        self.coordinates_combo = QComboBox()
        self.coordinates_combo.addItem(_t('Données'), "data")
        self.coordinates_combo.addItem(_t("Fraction de l'axe"), "axes_fraction")
        self.coordinates_combo.setCurrentIndex(max(0, self.coordinates_combo.findData(annotation.get("coordinate_system", "data"))))
        form.addRow(_t('Repère'), self.coordinates_combo)
        position = annotation.get("position", [0.5, 0.5])
        arrow = annotation.get("arrow_position") or [None, None]
        self.position_entries = [self._entry(value, _t('Position')) for value in position]
        self.arrow_entries = [self._entry(value, _t('Pointe de flèche')) for value in arrow]
        form.addRow(_t('Position X / Y'), self._pair(self.position_entries))
        form.addRow(_t('Flèche X / Y'), self._pair(self.arrow_entries))
        self.alignment_combo = QComboBox()
        for label, value in ((_t('Gauche'), "left"), (_t('Centre'), "center"), (_t('Droite'), "right")):
            self.alignment_combo.addItem(label, value)
        self.alignment_combo.setCurrentIndex(max(0, self.alignment_combo.findData(annotation.get("alignment", "left"))))
        form.addRow(_t('Alignement'), self.alignment_combo)
        self.color_button = _color_button(str(annotation.get("color", "#000000")))
        form.addRow(_t('Couleur'), self.color_button)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(6.0, 36.0)
        self.size_spin.setValue(float(annotation.get("font_size", 10.0)))
        form.addRow(_t('Taille'), self.size_spin)
        self.bold_check = QCheckBox(_t('Gras'))
        self.bold_check.setChecked(annotation.get("font_weight", "normal") == "bold")
        self.italic_check = QCheckBox(_t('Italique'))
        self.italic_check.setChecked(annotation.get("font_style", "normal") == "italic")
        form.addRow(self.bold_check)
        form.addRow(self.italic_check)
        self.arrow_combo = QComboBox()
        for label, value in ((_t('Sans flèche'), ""), (_t('Flèche'), "->"), (_t('Flèche pleine'), "-|>")):
            self.arrow_combo.addItem(label, value)
        self.arrow_combo.setCurrentIndex(max(0, self.arrow_combo.findData(annotation.get("arrow_style", ""))))
        form.addRow(_t('Style de flèche'), self.arrow_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_t('Annuler'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _entry(self, value: object, name: str) -> QLineEdit:
        entry = QLineEdit("" if value is None else self._locale.toString(float(value), "g", 12))
        entry.setAccessibleName(name)
        return entry

    @staticmethod
    def _pair(entries: list[QLineEdit]) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        for entry in entries:
            layout.addWidget(entry)
        return row

    def _number(self, entry: QLineEdit, *, required: bool) -> float | None:
        text = entry.text().strip()
        if not text and not required:
            return None
        value, valid = parse_number(text, self._locale)
        if not valid or not math.isfinite(value):
            raise ValueError(_t("Les coordonnées d'annotation doivent être finies."))
        return float(value)

    def value(self, identifier: str) -> dict[str, object]:
        text = self.text_entry.text().strip()
        if not text:
            raise ValueError(_t("Le texte de l'annotation est obligatoire."))
        if "$" in text:
            raise ValueError(_t("Les annotations n'acceptent pas de syntaxe MathText."))
        position = [self._number(entry, required=True) for entry in self.position_entries]
        arrow = [self._number(entry, required=False) for entry in self.arrow_entries]
        if all(value is None for value in arrow):
            arrow = None
        elif any(value is None for value in arrow):
            raise ValueError(_t('Les deux coordonnées de flèche sont obligatoires.'))
        arrow_style = str(self.arrow_combo.currentData())
        if arrow is not None and not arrow_style:
            raise ValueError(_t('Choisissez un style pour la flèche.'))
        return {"id": identifier, "text": text, "coordinate_system": str(self.coordinates_combo.currentData()), "axis": str(self.axis_combo.currentData()), "position": position, "arrow_position": arrow, "alignment": str(self.alignment_combo.currentData()), "color": str(self.color_button.property("graphColor")), "font_size": self.size_spin.value(), "font_weight": "bold" if self.bold_check.isChecked() else "normal", "font_style": "italic" if self.italic_check.isChecked() else "normal", "arrow_style": arrow_style}

    def accept(self) -> None:
        try:
            self.value("validation")
        except ValueError as exc:
            QMessageBox.warning(self, _t('Annotation'), _t(str(exc)))
            return
        super().accept()


class GraphSettingsDialog(QDialog):
    """Édite une copie locale et n'applique que sur demande explicite."""

    def __init__(
        self,
        *,
        graph: dict[str, object],
        limits: dict[str, list[float | None]],
        signals: tuple[str, ...],
        alignment_mode: str,
        comparison: bool,
        show_offsets_in_legend: bool,
        apply_callback,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t('Paramètres du graphique'))
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(560, 440)
        self.resize(700, 560)
        self._graph = deepcopy(graph)
        self._limits = deepcopy(limits)
        self._signals = tuple(dict.fromkeys(signals))
        self._comparison = comparison
        self._show_offsets_in_legend = show_offsets_in_legend
        self._apply_callback = apply_callback
        self._locale = number_locale()
        self.setLocale(self._locale)
        self._axis_role = "x"
        self._initial_reference_ids = {
            str(line["id"]) for line in self._graph["reference_lines"]
        }

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_general_tab(alignment_mode)
        self._build_grid_tab()
        self._build_axes_tab()
        self._build_reference_lines_tab()
        self._build_spacing_tab()
        self._build_advanced_tab()
        self.validation_label = QLabel()
        self.validation_label.setProperty("error", True)
        self.validation_label.setWordWrap(True)
        self.validation_label.setAccessibleName(_t('Erreur de validation du graphique'))
        self.validation_label.hide()
        layout.addWidget(self.validation_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Reset
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Reset).setText(
            _t('Réinitialiser')
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText(_t('Appliquer'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_t('Annuler'))
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            self._reset
        )
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        self.title_entry.setFocus()

    @staticmethod
    def _page() -> tuple[QWidget, QFormLayout]:
        page = QWidget()
        form = QFormLayout(page)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        return page, form

    def _number_entry(self, accessible_name: str) -> QLineEdit:
        validator = QDoubleValidator(self)
        validator.setLocale(self._locale)
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        entry = QLineEdit()
        entry.setValidator(validator)
        entry.setAccessibleName(accessible_name)
        return entry

    def _build_general_tab(self, alignment_mode: str) -> None:
        page, form = self._page()
        self.title_entry = QLineEdit(str(self._graph["title"]))
        self.title_entry.setAccessibleName(_t('Titre du graphique'))
        form.addRow(_t('Titre'), self.title_entry)
        self.alignment_combo = QComboBox()
        self.alignment_combo.addItem(_t('Aucun'), "none")
        self.alignment_combo.addItem(_t('Aligner les zéros'), "zeros")
        self.alignment_combo.addItem(_t('Aligner les références'), "references")
        self.alignment_combo.setCurrentIndex(
            max(0, self.alignment_combo.findData(alignment_mode))
        )
        form.addRow(_t('Alignement'), self.alignment_combo)
        self.tabs.addTab(page, _t('Général'))

    def _scroll_tab(self, content: QWidget, title: str) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, _t(title))

    @staticmethod
    def _optional_color(form: QFormLayout, title: str, fallback: str):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        button = _color_button(fallback)
        auto = QCheckBox(_t('Automatique'))
        auto.toggled.connect(button.setDisabled)
        layout.addWidget(button)
        layout.addWidget(auto)
        layout.addStretch()
        form.addRow(_t(title), row)
        return button, auto

    @staticmethod
    def _set_color(controls, value):
        button, auto = controls
        auto.setChecked(value is None)
        button.setEnabled(value is not None)
        if value is not None:
            button.setProperty("graphColor", value)
            button.setText(value)

    @staticmethod
    def _color_value(controls):
        button, auto = controls
        return None if auto.isChecked() else button.property("graphColor")

    def _build_grid_tab(self) -> None:
        page, form = self._page()
        self.grid_axis_combo = QComboBox()
        for label, value in (("X et Y", "both"), ("X", "x"), ("Y", "y")):
            self.grid_axis_combo.addItem(_t(label), value)
        form.addRow(_t('Orientation de grille'), self.grid_axis_combo)
        self.grid_controls = {}
        for kind, title in (("major", 'Grille majeure'), ("minor", 'Grille mineure')):
            box = QGroupBox(_t(title))
            box.setCheckable(True)
            group = QFormLayout(box)
            color = self._optional_color(group, 'Couleur', '#D2D2D2')
            style = QComboBox()
            for value, label in LINE_STYLES.items():
                style.addItem(_t(label), value)
            group.addRow(_t('Style'), style)
            width = QDoubleSpinBox()
            width.setRange(0.1, 10)
            width.setSingleStep(0.1)
            group.addRow(_t('Épaisseur (pt)'), width)
            form.addRow(box)
            self.grid_controls[kind] = (box, color, style, width)
        self._load_grid()
        self._scroll_tab(page, 'Grille')

    def _load_grid(self) -> None:
        self.grid_axis_combo.setCurrentIndex(self.grid_axis_combo.findData(self._graph['grid_axis']))
        for kind, (box, color, style, width) in self.grid_controls.items():
            values = self._graph['grid_styles'][kind]
            box.setChecked(self._graph[f'grid_{kind}'])
            self._set_color(color, values['color'])
            style.setCurrentIndex(style.findData(values['line_style']))
            width.setValue(values['line_width'])

    def _save_grid(self) -> None:
        self._graph['grid_axis'] = self.grid_axis_combo.currentData()
        for kind, (box, color, style, width) in self.grid_controls.items():
            self._graph[f'grid_{kind}'] = box.isChecked()
            self._graph['grid_styles'][kind] = {'color': self._color_value(color), 'line_style': style.currentData(), 'line_width': width.value()}

    def _build_axes_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        selector, form = self._page()
        form.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(selector)
        self.axis_combo = QComboBox()
        for role, label in (("x", "Axe inférieur (X)"), ("x_top", "Axe supérieur (X)"),
                            *((role, AXIS_LABELS[role]) for role in self._signals),
                            ("thermal_program", "Température programmée")):
            self.axis_combo.addItem(_t(label), role)
        self.axis_combo.currentIndexChanged.connect(self._axis_changed)
        form.addRow(_t('Axe'), self.axis_combo)
        self.all_axes_button = QPushButton(_t('Tous les axes'))
        self.paired_axes_button = QPushButton(_t('Les deux axes X'))
        self.all_axes_button.setToolTip(_t("Appliquer l'apparence à tous les axes"))
        self.paired_axes_button.setToolTip(_t("Appliquer à l'autre axe X"))
        self.all_axes_button.clicked.connect(lambda: self._copy_axis_appearance(all_axes=True))
        self.paired_axes_button.clicked.connect(lambda: self._copy_axis_appearance(all_axes=False))
        copy_row = QWidget()
        copy_layout = QHBoxLayout(copy_row)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.addWidget(self.all_axes_button)
        copy_layout.addWidget(self.paired_axes_button)
        form.addRow(_t("Copier l'apparence vers"), copy_row)
        copy_row.setToolTip(_t("La copie concerne les traits et graduations. Les bornes et échelles restent propres à chaque grandeur ; l'axe supérieur partage l'abscisse inférieure."))
        self.axis_tabs = QTabWidget()
        layout.addWidget(self.axis_tabs, 1)
        appearance_page, form = self._page()
        appearance_scroll = QScrollArea()
        appearance_scroll.setWidgetResizable(True)
        appearance_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        appearance_scroll.setWidget(appearance_page)
        self.axis_tabs.addTab(appearance_scroll, _t('Traits et graduations'))
        self.axis_visible_check = QCheckBox(_t('Afficher les traits et graduations'))
        form.addRow(self.axis_visible_check)
        self.axis_labels_check = QCheckBox(_t('Afficher les libellés et valeurs'))
        form.addRow(self.axis_labels_check)

        line_box = QGroupBox(_t("Trait de l'axe"))
        line_form = QFormLayout(line_box)
        self.axis_line_check = QCheckBox(_t('Afficher'))
        line_form.addRow(self.axis_line_check)
        self.axis_color = self._optional_color(line_form, 'Couleur', '#000000')
        self.axis_width_spin = QDoubleSpinBox()
        self.axis_width_spin.setRange(0.1, 10)
        self.axis_width_spin.setSingleStep(0.1)
        line_form.addRow(_t('Épaisseur (pt)'), self.axis_width_spin)
        self.axis_position_combo = QComboBox()
        line_form.addRow(_t("Position de l'axe"), self.axis_position_combo)
        self.axis_arrow_combo = QComboBox()
        for value, label in (("none", "Aucune"), ("end", "Extrémité positive"), ("both", "Deux extrémités")):
            self.axis_arrow_combo.addItem(_t(label), value)
        line_form.addRow(_t('Flèche'), self.axis_arrow_combo)
        form.addRow(line_box)

        self.tick_controls = {}
        for kind, title in (("major", 'Graduations majeures'), ("minor", 'Graduations mineures')):
            box = QGroupBox(_t(title))
            box.setCheckable(True)
            group = QFormLayout(box)
            direction = QComboBox()
            for value, label in (("out", "Vers l'extérieur"), ("in", "Vers l'intérieur"), ("inout", "Intérieur et extérieur")):
                direction.addItem(_t(label), value)
            group.addRow(_t('Direction'), direction)
            length = self._number_entry(_t('Longueur des graduations (pt)'))
            length.setPlaceholderText(_t('Automatique'))
            group.addRow(_t('Longueur (pt)'), length)
            color = self._optional_color(group, 'Couleur', '#000000')
            width = self._number_entry(_t('Épaisseur des graduations (pt)'))
            width.setPlaceholderText(_t('Automatique'))
            group.addRow(_t('Épaisseur (pt)'), width)
            form.addRow(box)
            self.tick_controls[kind] = (box, direction, length, color, width)

        self.axis_range_box = QGroupBox(_t('Échelle et valeurs'))
        range_form = QFormLayout(self.axis_range_box)
        range_scroll = QScrollArea()
        range_scroll.setWidgetResizable(True)
        range_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        range_scroll.setWidget(self.axis_range_box)
        self.axis_tabs.addTab(range_scroll, _t('Échelle et valeurs'))
        form = range_form
        label_row = QWidget()
        label_layout = QHBoxLayout(label_row)
        label_layout.setContentsMargins(0, 0, 0, 0)
        self.axis_label_entry = QLineEdit()
        self.axis_label_entry.setPlaceholderText(_t('Automatique'))
        self.axis_label_entry.setAccessibleName(_t("Libellé personnalisé de l'axe"))
        reset_label = QPushButton(_t('Automatique'))
        reset_label.clicked.connect(self.axis_label_entry.clear)
        label_layout.addWidget(self.axis_label_entry, 1)
        label_layout.addWidget(reset_label)
        form.addRow(_t('Libellé'), label_row)
        self.scale_combo = QComboBox()
        self.scale_combo.addItem(_t('Linéaire'), "linear")
        self.scale_combo.addItem(_t('Logarithmique'), "log")
        form.addRow(_t('Échelle'), self.scale_combo)
        limits_row = QWidget()
        limits_layout = QHBoxLayout(limits_row)
        limits_layout.setContentsMargins(0, 0, 0, 0)
        self.minimum_entry = self._number_entry(_t("Limite minimale de l'axe"))
        self.maximum_entry = self._number_entry(_t("Limite maximale de l'axe"))
        self.minimum_entry.setPlaceholderText(_t('Auto'))
        self.maximum_entry.setPlaceholderText(_t('Auto'))
        limits_layout.addWidget(self.minimum_entry)
        limits_layout.addWidget(self.maximum_entry)
        form.addRow(_t('Limites min / max'), limits_row)
        self.major_mode_combo = QComboBox()
        self.major_mode_combo.addItem(_t('Automatique'), "auto")
        self.major_mode_combo.addItem(_t('Pas fixe'), "fixed")
        form.addRow(_t('Graduations majeures'), self.major_mode_combo)
        self.major_step_entry = self._number_entry(_t('Pas des graduations majeures'))
        self.major_step_entry.setPlaceholderText(_t('Pas strictement positif'))
        form.addRow(_t('Pas majeur'), self.major_step_entry)
        self.minor_spin = QSpinBox()
        self.minor_spin.setRange(0, 10)
        self.minor_spin.setSpecialValueText(_t('Aucune'))
        form.addRow(_t('Subdivisions mineures'), self.minor_spin)
        self.tick_format_combo = QComboBox()
        self.tick_format_combo.addItem(_t('Automatique'), "auto")
        self.tick_format_combo.addItem(_t('Décimal fixe'), "fixed")
        self.tick_format_combo.addItem(_t('Scientifique'), "scientific")
        form.addRow(_t('Format des labels'), self.tick_format_combo)
        self.decimals_spin = QSpinBox()
        self.decimals_spin.setRange(0, 12)
        form.addRow(_t('Décimales'), self.decimals_spin)
        self.rotation_combo = QComboBox()
        for value in (0, 30, 45, 90):
            self.rotation_combo.addItem(f"{value}°", value)
        form.addRow(_t('Rotation X'), self.rotation_combo)
        self.major_mode_combo.currentIndexChanged.connect(self._update_axis_controls)
        self.tick_format_combo.currentIndexChanged.connect(self._update_axis_controls)
        self._load_axis("x")
        self.tabs.addTab(page, _t('Axes et graduations'))

    def _number(self, entry: QLineEdit, name: str, *, positive: bool = False):
        text = entry.text().strip()
        if not text:
            return None
        value, valid = parse_number(text, self._locale)
        if not valid or not math.isfinite(value) or (positive and value <= 0):
            qualifier = _t(' fini et strictement positif') if positive else _t(' fini')
            raise ValueError(_t('{v0} doit être un nombre{v2}.', v0=name, v2=qualifier))
        return float(value)

    def _save_axis(self) -> None:
        role = self._axis_role
        self._save_axis_appearance()
        if role not in self._limits:
            return
        minimum = self._number(self.minimum_entry, _t('La limite minimale'))
        maximum = self._number(self.maximum_entry, _t('La limite maximale'))
        scale = str(self.scale_combo.currentData())
        if minimum is not None and maximum is not None and minimum >= maximum:
            raise ValueError(_t('La limite minimale doit être inférieure à la maximale.'))
        if scale == "log" and any(
            value is not None and value <= 0 for value in (minimum, maximum)
        ):
            raise ValueError(_t('Les limites logarithmiques doivent être positives.'))
        step = None
        if self.major_mode_combo.currentData() == "fixed":
            step = self._number(
                self.major_step_entry, _t('Le pas majeur'), positive=True
            )
            if step is None:
                raise ValueError(_t('Le pas majeur est obligatoire en mode fixe.'))
        self._graph["axis_labels"][role] = self.axis_label_entry.text().strip()
        self._graph["axis_scales"][role] = scale
        self._limits[role] = [minimum, maximum]
        self._graph["major_tick_steps"][role] = step
        self._graph["minor_tick_subdivisions"][role] = self.minor_spin.value()
        self._graph["tick_formats"][role] = str(self.tick_format_combo.currentData())
        self._graph["tick_decimals"][role] = self.decimals_spin.value()
        if role == "x":
            self._graph["x_tick_rotation"] = int(self.rotation_combo.currentData())

    def _load_axis(self, role: str) -> None:
        self._axis_role = role
        self._load_axis_appearance()
        self.axis_range_box.setEnabled(role in self._limits)
        self.paired_axes_button.setEnabled(role in {"x", "x_top"})
        self.axis_range_box.setToolTip(
            _t("L'axe supérieur partage les bornes et les valeurs de l'axe inférieur.") if role == 'x_top'
            else _t("L'échelle de température programmée est automatique.") if role == 'thermal_program' else ''
        )
        if role == 'x_top':
            role = 'x'
        if role not in self._limits:
            for entry in (self.axis_label_entry, self.minimum_entry, self.maximum_entry, self.major_step_entry):
                entry.clear()
            self.scale_combo.setCurrentIndex(0)
            self.major_mode_combo.setCurrentIndex(0)
            self.tick_format_combo.setCurrentIndex(0)
            self.minor_spin.setValue(0)
            return
        self.axis_label_entry.setText(str(self._graph["axis_labels"][role]))
        self.scale_combo.setCurrentIndex(
            max(0, self.scale_combo.findData(self._graph["axis_scales"][role]))
        )
        minimum, maximum = self._limits[role]
        self.minimum_entry.setText(
            "" if minimum is None else self._locale.toString(float(minimum), "g", 12)
        )
        self.maximum_entry.setText(
            "" if maximum is None else self._locale.toString(float(maximum), "g", 12)
        )
        step = self._graph["major_tick_steps"][role]
        self.major_mode_combo.setCurrentIndex(0 if step is None else 1)
        self.major_step_entry.setText(
            "" if step is None else self._locale.toString(float(step), "g", 12)
        )
        self.minor_spin.setValue(int(self._graph["minor_tick_subdivisions"][role]))
        self.tick_format_combo.setCurrentIndex(
            max(0, self.tick_format_combo.findData(self._graph["tick_formats"][role]))
        )
        self.decimals_spin.setValue(int(self._graph["tick_decimals"][role]))
        self.rotation_combo.setCurrentIndex(
            max(0, self.rotation_combo.findData(self._graph["x_tick_rotation"]))
        )
        self._update_axis_controls()

    def _axis_changed(self, *_args) -> None:
        try:
            self._save_axis()
        except ValueError as exc:
            self._show_error(_t(str(exc)))
            with QSignalBlocker(self.axis_combo):
                self.axis_combo.setCurrentIndex(
                    max(0, self.axis_combo.findData(self._axis_role))
                )
            return
        self._load_axis(str(self.axis_combo.currentData()))

    def _update_axis_controls(self) -> None:
        self.major_step_entry.setEnabled(
            self.major_mode_combo.currentData() == "fixed"
        )
        self.decimals_spin.setEnabled(
            self.tick_format_combo.currentData() in {"fixed", "scientific"}
        )
        self.rotation_combo.setEnabled(self._axis_role == "x")

    def _save_axis_appearance(self) -> None:
        style = deepcopy(self._graph['axis_appearance'][self._axis_role])
        style.update(visible=self.axis_visible_check.isChecked(), line_visible=self.axis_line_check.isChecked(),
                     labels_visible=self.axis_labels_check.isChecked(), color=self._color_value(self.axis_color),
                     width=self.axis_width_spin.value(), position=self.axis_position_combo.currentData(),
                     arrow=self.axis_arrow_combo.currentData())
        for kind, (box, direction, length, color, width) in self.tick_controls.items():
            tick_length = self._number(length, _t('La longueur des graduations'))
            tick_width = self._number(width, _t("L'épaisseur des graduations"), positive=True)
            if (tick_length is not None and not 0 <= tick_length <= 30) or (tick_width is not None and not 0.1 <= tick_width <= 10):
                raise ValueError(_t('Longueur attendue : 0 à 30 pt ; épaisseur : 0,1 à 10 pt.'))
            style[kind] = dict(visible=box.isChecked(), direction=direction.currentData(), length=tick_length,
                               color=self._color_value(color), width=tick_width)
        self._graph['axis_appearance'][self._axis_role] = style

    def _load_axis_appearance(self) -> None:
        role = self._axis_role
        style = self._graph['axis_appearance'][role]
        self.axis_visible_check.setChecked(style['visible'])
        self.axis_line_check.setChecked(style['line_visible'])
        self.axis_labels_check.setChecked(style['labels_visible'])
        self._set_color(self.axis_color, style['color'])
        self.axis_width_spin.setValue(style['width'])
        self.axis_position_combo.clear()
        sides = (("bottom", "Inférieur"),) if role == "x" else (("top", "Supérieur"),) if role == "x_top" else (("left", "Gauche"), ("right", "Droite"))
        for value, label in (("auto", "Automatique"), *sides):
            self.axis_position_combo.addItem(_t(label), value)
        self.axis_position_combo.setCurrentIndex(self.axis_position_combo.findData(style['position']))
        self.axis_arrow_combo.setCurrentIndex(self.axis_arrow_combo.findData(style['arrow']))
        for kind, (box, direction, length, color, width) in self.tick_controls.items():
            tick = style[kind]
            box.setChecked(tick['visible'])
            direction.setCurrentIndex(direction.findData(tick['direction']))
            self._set_color(color, tick['color'])
            for entry, key in ((length, 'length'), (width, 'width')):
                entry.setText('' if tick[key] is None else self._locale.toString(float(tick[key]), 'g', 12))

    def _copy_axis_appearance(self, *, all_axes: bool) -> None:
        try:
            self._save_axis_appearance()
        except ValueError as exc:
            self._show_error(str(exc))
            return
        appearances = self._graph['axis_appearance']
        for role in (appearances if all_axes else ('x', 'x_top')):
            position = appearances[role]['position']
            appearances[role] = deepcopy(appearances[self._axis_role])
            appearances[role]['position'] = position
        self.validation_label.hide()

    def _build_reference_lines_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.lines_table = QTableWidget(0, 5)
        self.lines_table.setHorizontalHeaderLabels(
            (_t('Visible'), _t('Orientation'), _t('Axe'), _t('Valeur'), _t('Libellé'))
        )
        self.lines_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.lines_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.verticalHeader().setVisible(False)
        self.lines_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.lines_table, 1)
        buttons = QHBoxLayout()
        self.add_line_button = QPushButton(_t('Ajouter…'))
        self.edit_line_button = QPushButton(_t('Modifier…'))
        self.remove_line_button = QPushButton(_t('Supprimer'))
        buttons.addWidget(self.add_line_button)
        buttons.addWidget(self.edit_line_button)
        buttons.addWidget(self.remove_line_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.add_line_button.clicked.connect(self._add_line)
        self.edit_line_button.clicked.connect(self._edit_line)
        self.remove_line_button.clicked.connect(self._remove_line)
        self._refresh_lines()
        self.tabs.addTab(page, _t('Lignes de référence'))

    def _build_spacing_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        margins_box = QGroupBox(_t('Marges du graphique'))
        form = QFormLayout(margins_box)
        self.auto_margins_check = QCheckBox(_t('Espacement automatique'))
        form.addRow(self.auto_margins_check)
        self.margin_spins = {}
        for side, label in (("left", "Gauche (%)"), ("right", "Droite (%)"), ("bottom", "Bas (%)"), ("top", "Haut (%)")):
            spin = QDoubleSpinBox()
            spin.setRange(0, 100)
            spin.setDecimals(1)
            self.auto_margins_check.toggled.connect(spin.setDisabled)
            self.margin_spins[side] = spin
            form.addRow(_t(label), spin)
        self._load_margins()
        layout.addWidget(margins_box)
        spacing_box = QGroupBox(_t('Espacement des axes'))
        spacing_group = QFormLayout(spacing_box)
        self.tg_position_spin = QDoubleSpinBox()
        self.tg_position_spin.setRange(1.0, 1.20)
        self.dtg_position_spin = QDoubleSpinBox()
        self.dtg_position_spin.setRange(1.04, 1.40)
        self.tg_position_spin.setValue(float(self._graph["axis_spacing"]["tg_right_position"]))
        self.dtg_position_spin.setValue(float(self._graph["axis_spacing"]["dtg_right_position"]))
        spacing_group.addRow(_t('Position externe TG'), self.tg_position_spin)
        spacing_group.addRow(_t('Position externe dTG'), self.dtg_position_spin)
        self.spacing_axis_combo = QComboBox()
        for role, label in AXIS_LABELS.items():
            self.spacing_axis_combo.addItem(_t(label), role)
        self.label_pad_spin = QDoubleSpinBox()
        self.label_pad_spin.setRange(0.0, 60.0)
        self.tick_pad_spin = QDoubleSpinBox()
        self.tick_pad_spin.setRange(0.0, 60.0)
        self.spacing_axis_combo.currentIndexChanged.connect(self._load_spacing_axis)
        spacing_group.addRow(_t('Axe espacé'), self.spacing_axis_combo)
        spacing_group.addRow(_t('Marge du nom'), self.label_pad_spin)
        spacing_group.addRow(_t('Marge des graduations'), self.tick_pad_spin)
        self._load_spacing_axis()
        layout.addWidget(spacing_box)

        layout.addStretch()
        self._scroll_tab(page, 'Espacement')

    def _load_margins(self) -> None:
        margins = self._graph['layout_margins']
        self.auto_margins_check.setChecked(margins is None)
        values = margins or dict(left=0.125, right=0.9, bottom=0.11, top=0.88)
        for side, spin in self.margin_spins.items():
            spin.setValue(100 * (1 - values[side] if side in {'right', 'top'} else values[side]))
            spin.setEnabled(margins is not None)

    def _build_advanced_tab(self) -> None:
        page = QScrollArea()
        page.setWidgetResizable(True)
        content = QWidget()
        page.setWidget(content)
        layout = QVBoxLayout(content)
        annotations_box = QGroupBox(_t('Annotations'))
        annotations_group = QVBoxLayout(annotations_box)
        self.annotations_table = QTableWidget(0, 3)
        self.annotations_table.setHorizontalHeaderLabels((_t('Texte'), _t('Axe'), _t('Repère')))
        self.annotations_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.annotations_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.annotations_table.setAlternatingRowColors(True)
        self.annotations_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        annotations_group.addWidget(self.annotations_table)
        annotation_buttons = QHBoxLayout()
        self.add_annotation_button = QPushButton(_t('Ajouter…'))
        self.duplicate_annotation_button = QPushButton(_t('Dupliquer'))
        self.remove_annotation_button = QPushButton(_t('Supprimer'))
        for button in (self.add_annotation_button, self.duplicate_annotation_button, self.remove_annotation_button):
            annotation_buttons.addWidget(button)
        annotation_buttons.addStretch(1)
        annotations_group.addLayout(annotation_buttons)
        layout.addWidget(annotations_box)
        self.add_annotation_button.clicked.connect(self._add_annotation)
        self.duplicate_annotation_button.clicked.connect(self._duplicate_annotation)
        self.remove_annotation_button.clicked.connect(self._remove_annotation)

        fonts_box = QGroupBox(_t('Polices'))
        fonts_group = QFormLayout(fonts_box)
        self.font_target_combo = QComboBox()
        for target, label in (("general", _t('Valeur générale')), ("title", _t('Titre')), ("axes", _t('Noms des axes')), ("ticks", _t('Graduations')), ("annotations", _t('Annotations'))):
            self.font_target_combo.addItem(label, target)
        self.font_family_combo = QComboBox()
        self.font_family_combo.addItem(_t('Police système'), "")
        for family in QFontDatabase.families():
            self.font_family_combo.addItem(family, family)
        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(6.0, 36.0)
        self.font_weight_combo = QComboBox()
        self.font_weight_combo.addItem(_t('Normale'), "normal")
        self.font_weight_combo.addItem(_t('Grasse'), "bold")
        self.font_style_combo = QComboBox()
        self.font_style_combo.addItem(_t('Normal'), "normal")
        self.font_style_combo.addItem(_t('Italique'), "italic")
        self.use_general_font_check = QCheckBox(_t('Utiliser la valeur générale'))
        self.font_target_combo.currentIndexChanged.connect(self._font_target_changed)
        self.use_general_font_check.toggled.connect(self._update_font_controls)
        fonts_group.addRow(_t('Cible'), self.font_target_combo)
        fonts_group.addRow(self.use_general_font_check)
        fonts_group.addRow(_t('Famille'), self.font_family_combo)
        fonts_group.addRow(_t('Taille'), self.font_size_spin)
        fonts_group.addRow(_t('Graisse'), self.font_weight_combo)
        fonts_group.addRow(_t('Style'), self.font_style_combo)
        self._load_font_target()
        layout.addWidget(fonts_box)

        templates_box = QGroupBox(_t('Modèles de présentation'))
        template_buttons = QHBoxLayout(templates_box)
        self.import_template_button = QPushButton(_t('Importer un modèle…'))
        self.export_template_button = QPushButton(_t('Exporter le modèle…'))
        template_buttons.addWidget(self.import_template_button)
        template_buttons.addWidget(self.export_template_button)
        template_buttons.addStretch(1)
        layout.addWidget(templates_box)
        layout.addStretch(1)
        self.import_template_button.clicked.connect(self._import_template)
        self.export_template_button.clicked.connect(self._export_template)
        self._refresh_annotations()
        self.tabs.addTab(page, _t('Avancé'))

    def _load_spacing_axis(self, *_args) -> None:
        role = str(self.spacing_axis_combo.currentData())
        spacing = self._graph["axis_spacing"]
        previous = getattr(self, "_spacing_role", None)
        if previous is not None:
            spacing["label_pads"][previous] = self.label_pad_spin.value()
            spacing["tick_pads"][previous] = self.tick_pad_spin.value()
        self._spacing_role = role
        self.label_pad_spin.setValue(float(spacing["label_pads"][role]))
        self.tick_pad_spin.setValue(float(spacing["tick_pads"][role]))

    def _save_spacing(self) -> None:
        margins = None
        if not self.auto_margins_check.isChecked():
            margins = {side: (1 - spin.value() / 100 if side in {'right', 'top'} else spin.value() / 100) for side, spin in self.margin_spins.items()}
            if margins['left'] >= margins['right'] or margins['bottom'] >= margins['top']:
                raise ValueError(_t('Les marges doivent laisser une surface de tracé positive.'))
        self._graph['layout_margins'] = margins
        role = str(self.spacing_axis_combo.currentData())
        spacing = self._graph["axis_spacing"]
        if self.dtg_position_spin.value() < self.tg_position_spin.value() + 0.04:
            raise ValueError(_t("L'axe dTG doit rester à l'extérieur de TG."))
        spacing["tg_right_position"] = self.tg_position_spin.value()
        spacing["dtg_right_position"] = self.dtg_position_spin.value()
        spacing["label_pads"][role] = self.label_pad_spin.value()
        spacing["tick_pads"][role] = self.tick_pad_spin.value()

    def _font_target_changed(self, *_args) -> None:
        self._save_font_target()
        self._load_font_target()

    def _current_font(self) -> dict[str, object]:
        target = str(self.font_target_combo.currentData())
        fonts = self._graph["fonts"]
        return dict(fonts["general"] if target == "general" else fonts["overrides"].get(target, fonts["general"]))

    def _load_font_target(self) -> None:
        target = str(self.font_target_combo.currentData())
        fonts = self._graph["fonts"]
        use_general = target != "general" and target not in fonts["overrides"]
        with QSignalBlocker(self.use_general_font_check):
            self.use_general_font_check.setChecked(use_general)
        font = self._current_font()
        self.font_family_combo.setCurrentIndex(
            max(0, self.font_family_combo.findData(font.get("family", "")))
        )
        self.font_size_spin.setValue(float(font.get("size") or 10.0))
        self.font_weight_combo.setCurrentIndex(
            max(0, self.font_weight_combo.findData(font.get("weight", "normal")))
        )
        self.font_style_combo.setCurrentIndex(
            max(0, self.font_style_combo.findData(font.get("style", "normal")))
        )
        self._update_font_controls()

    def _update_font_controls(self, *_args) -> None:
        target = str(self.font_target_combo.currentData())
        self.use_general_font_check.setEnabled(target != "general")
        enabled = target == "general" or not self.use_general_font_check.isChecked()
        for control in (self.font_family_combo, self.font_size_spin, self.font_weight_combo, self.font_style_combo):
            control.setEnabled(enabled)

    def _save_font_target(self) -> None:
        target = str(self.font_target_combo.currentData())
        fonts = self._graph["fonts"]
        if target != "general" and self.use_general_font_check.isChecked():
            fonts["overrides"].pop(target, None)
            return
        value = {"family": str(self.font_family_combo.currentData()), "size": self.font_size_spin.value(), "weight": str(self.font_weight_combo.currentData()), "style": str(self.font_style_combo.currentData())}
        if target == "general":
            fonts["general"] = value
        else:
            fonts["overrides"][target] = value

    def _refresh_annotations(self) -> None:
        annotations = self._graph["annotations"]
        self.annotations_table.setRowCount(len(annotations))
        for row, annotation in enumerate(annotations):
            self.annotations_table.setItem(row, 0, QTableWidgetItem(str(annotation["text"])))
            self.annotations_table.setItem(row, 1, QTableWidgetItem(_t(AXIS_LABELS[str(annotation["axis"])])))
            coordinates = _t('Données') if annotation["coordinate_system"] == "data" else _t("Fraction de l'axe")
            self.annotations_table.setItem(row, 2, QTableWidgetItem(coordinates))

    def _annotation_row(self) -> int | None:
        rows = self.annotations_table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _add_annotation(self) -> None:
        dialog = _AnnotationDialog(None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._graph["annotations"].append(dialog.value(f"annotation-{uuid4().hex}"))
            self._refresh_annotations()

    def _duplicate_annotation(self) -> None:
        row = self._annotation_row()
        if row is None:
            self._show_error(_t('Sélectionnez une annotation à dupliquer.'))
            return
        copy = deepcopy(self._graph["annotations"][row])
        copy["id"] = f"annotation-{uuid4().hex}"
        self._graph["annotations"].append(copy)
        self._refresh_annotations()

    def _remove_annotation(self) -> None:
        row = self._annotation_row()
        if row is None:
            self._show_error(_t('Sélectionnez une annotation à supprimer.'))
            return
        del self._graph["annotations"][row]
        self._refresh_annotations()

    def _import_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, _t('Importer un modèle graphique'), "", _t('Modèle graphique (*.atgstyle.json)'))
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as stream:
                self._graph = graph_from_template_payload(json.load(stream), defaults=default_graph_settings(title=str(self._graph["title"])))
        except (OSError, ValueError, ProjectValidationError, json.JSONDecodeError) as exc:
            self._show_error(_t('Import du modèle impossible : {v1}', v1=exc))
            return
        self._restore_template_controls()

    def _export_template(self) -> None:
        try:
            payload = graph_template_payload(self._collect()["graph"])
        except (ValueError, ProjectValidationError) as exc:
            self._show_error(_t(str(exc)))
            return
        path, _ = QFileDialog.getSaveFileName(self, _t('Exporter le modèle graphique'), "presentation.atgstyle.json", _t('Modèle graphique (*.atgstyle.json)'))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._show_error(_t('Export du modèle impossible : {v1}', v1=exc))

    def _restore_advanced_controls(self) -> None:
        self._load_margins()
        self.tg_position_spin.setValue(float(self._graph["axis_spacing"]["tg_right_position"]))
        self.dtg_position_spin.setValue(float(self._graph["axis_spacing"]["dtg_right_position"]))
        self._spacing_role = None
        self._load_spacing_axis()
        self._load_font_target()
        self._refresh_annotations()

    def _restore_template_controls(self) -> None:
        self.title_entry.setText(str(self._graph["title"]))
        self._load_grid()
        self._load_axis(self._axis_role)
        self._refresh_lines()
        self._restore_advanced_controls()

    def _save_advanced(self) -> None:
        self._save_spacing()
        self._save_font_target()

    def _refresh_lines(self) -> None:
        lines = self._graph["reference_lines"]
        self.lines_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            visible = QTableWidgetItem()
            visible.setFlags(visible.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            visible.setCheckState(
                Qt.CheckState.Checked if line["visible"] else Qt.CheckState.Unchecked
            )
            self.lines_table.setItem(row, 0, visible)
            self.lines_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    _t('Verticale') if line["orientation"] == "vertical" else _t('Horizontale')
                ),
            )
            self.lines_table.setItem(row, 2, QTableWidgetItem(_t(AXIS_LABELS[line["axis"]])))
            self.lines_table.setItem(row, 3, QTableWidgetItem(decimal_text(f"{line['value']:g}")))
            self.lines_table.setItem(row, 4, QTableWidgetItem(str(line["label"])))

    def _sync_line_visibility(self) -> None:
        for row, line in enumerate(self._graph["reference_lines"]):
            item = self.lines_table.item(row, 0)
            line["visible"] = item.checkState() == Qt.CheckState.Checked

    def _selected_line_row(self) -> int | None:
        rows = self.lines_table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _add_line(self) -> None:
        dialog = _ReferenceLineDialog(None, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._graph["reference_lines"].append(
                dialog.line_value(f"line-{uuid4().hex}")
            )
        except ValueError as exc:
            self._show_error(_t(str(exc)))
            return
        self._refresh_lines()

    def _edit_line(self) -> None:
        row = self._selected_line_row()
        if row is None:
            self._show_error(_t('Sélectionnez une ligne à modifier.'))
            return
        self._sync_line_visibility()
        current = self._graph["reference_lines"][row]
        dialog = _ReferenceLineDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._graph["reference_lines"][row] = dialog.line_value(str(current["id"]))
        except ValueError as exc:
            self._show_error(_t(str(exc)))
            return
        self._refresh_lines()

    def _remove_line(self) -> None:
        row = self._selected_line_row()
        if row is None:
            self._show_error(_t('Sélectionnez une ligne à supprimer.'))
            return
        self._sync_line_visibility()
        line = self._graph["reference_lines"][row]
        if str(line["id"]) in self._initial_reference_ids and QMessageBox.question(
            self,
            _t('Supprimer la ligne'),
            _t('Supprimer cette ligne de référence déjà appliquée au projet ?'),
        ) != QMessageBox.StandardButton.Yes:
            return
        del self._graph["reference_lines"][row]
        self._refresh_lines()

    def _collect(self) -> dict[str, object]:
        self._save_axis()
        self._save_grid()
        self._save_advanced()
        self._graph["title"] = self.title_entry.text()
        self._sync_line_visibility()
        return {
            "graph": deepcopy(self._graph),
            "limits": deepcopy(self._limits),
            "alignment_mode": str(self.alignment_combo.currentData()),
            "show_offsets_in_legend": self._show_offsets_in_legend,
            "curve_changes": {},
        }

    def _show_error(self, message: str) -> None:
        self.validation_label.setText(message)
        self.validation_label.show()

    def _apply(self) -> bool:
        try:
            self._apply_callback(self._collect())
        except ValueError as exc:
            self._show_error(_t(str(exc)))
            return False
        self.validation_label.hide()
        self._initial_reference_ids = {
            str(line["id"]) for line in self._graph["reference_lines"]
        }
        return True

    def _accept(self) -> None:
        if self._apply():
            self.accept()

    def _reset(self) -> None:
        previous = self._graph
        title = _t('Comparaison des expériences') if self._comparison else ""
        self._graph = default_graph_settings(title=title)
        # These settings have dedicated editors and are outside this dialog.
        for key in ("legend_visible", "legend_position", "legend_style", "curve_styles"):
            self._graph[key] = deepcopy(previous[key])
        if "legend" in previous["fonts"]["overrides"]:
            self._graph["fonts"]["overrides"]["legend"] = deepcopy(previous["fonts"]["overrides"]["legend"])
        self._limits = {axis: [None, None] for axis in ("x", "tg", "dtg", "heat_flow")}
        self.alignment_combo.setCurrentIndex(0)
        self._restore_template_controls()
