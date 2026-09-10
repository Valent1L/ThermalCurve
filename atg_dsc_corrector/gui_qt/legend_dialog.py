"""Compact editor for the existing plot legend, independent of scientific data."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMenu, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from atg_dsc_corrector.i18n import tr as _t
from atg_dsc_corrector.legend import LEGEND_POSITIONS
from atg_dsc_corrector.projects import default_legend_style, graph_template_payload
from .color_button import ColorButton
from .flow_layout import FlowLayout
from .number_format import number_locale


class LegendDialog(QDialog):
    def __init__(self, graph, entries, apply_callback, parent=None, *, axes_bounds=(0, 0, 1, 1)):
        super().__init__(parent)
        self.setLocale(number_locale())
        self.setWindowTitle(_t("Modifier la légende"))
        self.setSizeGripEnabled(True)
        self.resize(660, 590)
        self.setMinimumSize(480, 440)
        self._graph = deepcopy(graph)
        self._style = deepcopy(graph.get("legend_style", default_legend_style()))
        self._entries = list(entries)
        self._active_entry = None
        self._apply_callback = apply_callback
        self._axes_bounds = axes_bounds
        root = QVBoxLayout(self)
        self.visible_check = QCheckBox(_t("Afficher la légende"))
        self.visible_check.setChecked(graph.get("legend_visible", True))
        root.addWidget(self.visible_check)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_frame()
        self._build_position()
        self._build_text()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setProperty("error", True)
        root.addWidget(self.error_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Apply |
                                       QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText(_t("Appliquer"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_t("Annuler"))
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        self.buttons.accepted.connect(lambda: self.accept() if self.apply() else None)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _tab(self, title):
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, _t(title))
        return layout

    def _combo(self, choices, value, *, translate=True):
        combo = QComboBox()
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(12)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for label, data in choices:
            combo.addItem(_t(label) if translate else label, data)
        combo.setCurrentIndex(max(0, combo.findData(value)))
        return combo

    def _number(self, value, low, high, *, integer=False, suffix=""):
        widget = QSpinBox() if integer else QDoubleSpinBox()
        widget.setLocale(self.locale())
        widget.setRange(low, high)
        if not integer:
            widget.setDecimals(3)
        widget.setValue(value)
        widget.setSuffix(suffix)
        return widget

    def _color(self, value):
        button = ColorButton(value, self)
        def choose():
            color = QColorDialog.getColor(QColor(button.property("graphColor")), self, _t("Couleur"))
            if color.isValid():
                button.setText(color.name())
        button.clicked.connect(choose)
        return button

    def _check(self, label, value):
        check = QCheckBox(_t(label))
        check.setChecked(value)
        return check

    def _build_frame(self):
        style = self._style
        layout = self._tab("Cadre")
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        self.frame_combo = self._combo((("Aucun", "none"), ("Rectangulaire", "box"), ("Arrondi", "rounded")), style["frame"])
        form.addRow(_t("Cadre"), self.frame_combo)
        self.wrap_check = self._check("Retour à la ligne, hauteur adaptée", style["wrap"])
        form.addRow(self.wrap_check)
        self.wrap_width = self._number(style["wrap_width"], 5, 500, integer=True)
        form.addRow(_t("Largeur de texte (caractères)"), self.wrap_width)
        self.wrap_check.toggled.connect(self.wrap_width.setEnabled)
        self.wrap_width.setEnabled(style["wrap"])
        self.fill_button = self._color(style["fill_color"] or "#FFFFFF")
        self.no_fill_check = self._check("Sans remplissage", not style["fill_color"])
        fill = QHBoxLayout()
        fill.addWidget(self.fill_button)
        fill.addWidget(self.no_fill_check)
        form.addRow(_t("Couleur du fond"), fill)
        transparency = QHBoxLayout()
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.transparency_spin = self._number(round(100 * (1 - style["fill_alpha"])), 0, 100, integer=True, suffix=" %")
        self.alpha_slider.setValue(self.transparency_spin.value())
        self.alpha_slider.valueChanged.connect(self.transparency_spin.setValue)
        self.transparency_spin.valueChanged.connect(self.alpha_slider.setValue)
        transparency.addWidget(self.alpha_slider)
        transparency.addWidget(self.transparency_spin)
        form.addRow(_t("Transparence du fond"), transparency)
        self.border_button = self._color(style["border_color"])
        self.border_width = self._number(style["border_width"], 0, 20, suffix=" pt")
        form.addRow(_t("Couleur du contour"), self.border_button)
        form.addRow(_t("Épaisseur du contour"), self.border_width)
        margin_group = QGroupBox(_t("Marges (% de la hauteur de police)"))
        margins = QGridLayout(margin_group)
        self.margin_all = self._number(style["margins"]["left"], 0, 500)
        margins.addWidget(QLabel(_t("Toutes")), 0, 0)
        margins.addWidget(self.margin_all, 0, 1)
        self.margin_spins = {}
        for index, (side, label) in enumerate((("left", "Gauche"), ("right", "Droite"), ("top", "Haut"), ("bottom", "Bas"))):
            spin = self._number(style["margins"][side], 0, 500)
            self.margin_spins[side] = spin
            margins.addWidget(QLabel(_t(label)), index // 2 + 1, index % 2 * 2)
            margins.addWidget(spin, index // 2 + 1, index % 2 * 2 + 1)
            self.margin_all.valueChanged.connect(spin.setValue)
        layout.addWidget(margin_group)
        layout.addStretch()

    def _build_position(self):
        layout = self._tab("Position")
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        self.position_combo = self._combo(LEGEND_POSITIONS, self._graph.get("legend_position", "best"))
        form.addRow(_t("Position"), self.position_combo)
        self.unit_combo = self._combo((("% du graphique", "axes_percent"), ("% de la figure", "figure_percent")), self._style["unit"])
        self._previous_unit = self._style["unit"]
        form.addRow(_t("Unité"), self.unit_combo)
        self.anchor_combo = self._combo(LEGEND_POSITIONS[1:10], self._style["anchor"])
        form.addRow(_t("Ancre"), self.anchor_combo)
        self.anchor_frame = self._check("Ancrer sur le cadre du texte", self._style["anchor_frame"])
        form.addRow(self.anchor_frame)
        self.x_spin = self._number(self._style["x"], -1000, 1000, suffix=" %")
        self.y_spin = self._number(self._style["y"], -1000, 1000, suffix=" %")
        form.addRow(_t("Horizontal"), self.x_spin)
        form.addRow(_t("Vertical"), self.y_spin)
        self.lock_x = self._check("Bloquer le déplacement horizontal", self._style["lock_x"])
        self.lock_y = self._check("Bloquer le déplacement vertical", self._style["lock_y"])
        form.addRow(self.lock_x)
        form.addRow(self.lock_y)
        note = QLabel(_t("Les positions extérieures évitent les axes et leurs titres. En position personnalisée, l'origine est en bas à gauche. La légende peut être déplacée à la souris ; les blocages s'appliquent à ce déplacement."))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.unit_combo.currentIndexChanged.connect(self._convert_coordinates)
        self.position_combo.currentIndexChanged.connect(self._position_enabled)
        self._position_enabled()
        layout.addStretch()

    def _position_enabled(self):
        manual = self.position_combo.currentData() == "manual"
        self.x_spin.setEnabled(manual)
        self.y_spin.setEnabled(manual)

    def _convert_coordinates(self):
        unit = self.unit_combo.currentData()
        if unit == self._previous_unit:
            return
        left, bottom, width, height = self._axes_bounds
        x, y = self.x_spin.value() / 100, self.y_spin.value() / 100
        x, y = ((left + x * width, bottom + y * height) if unit == "figure_percent"
                else ((x - left) / width, (y - bottom) / height))
        self.x_spin.setValue(x * 100)
        self.y_spin.setValue(y * 100)
        self._previous_unit = unit

    def _build_text(self):
        layout = self._tab("Texte")
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addLayout(form)
        font = self._graph.get("fonts", {}).get("overrides", {}).get("legend", {})
        effective_font = dict(self._graph.get("fonts", {}).get("general", {}))
        effective_font.update(font)
        self.font_combo = self._combo([("Héritée du graphique", "")] + [(name, name) for name in QFontDatabase.families()], font.get("family", ""))
        self.font_size = self._number(font.get("size") or 5, 5, 36, suffix=" pt")
        self.font_size.setSpecialValueText(_t("Héritée du graphique"))
        form.addRow(_t("Police"), self.font_combo)
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_size)
        self.text_color = self._color(self._style["text_color"])
        font_row.addWidget(QLabel(_t("Couleur")))
        font_row.addWidget(self.text_color)
        form.addRow(_t("Taille"), font_row)
        self.rotation = self._number(self._style["rotation"], -360, 360, suffix=" °")
        self.line_spacing = self._number(self._style["line_spacing"] or 24, 24, 500, suffix=" %")
        self.line_spacing.setSpecialValueText(_t("Automatique"))
        self.tab_width = self._number(self._style["tab_width"], 1, 32, integer=True)
        self.alignment = self._combo((("Gauche", "left"), ("Centre", "center"), ("Droite", "right")), self._style["alignment"])
        for label, widget in (("Rotation", self.rotation), ("Interligne", self.line_spacing),
                              ("Tabulation (espaces)", self.tab_width), ("Alignement", self.alignment)):
            form.addRow(_t(label), widget)
        self.columns = self._number(self._style["columns"], 1, 20, integer=True)
        form.addRow(_t("Colonnes"), self.columns)
        options = FlowLayout()
        layout.addLayout(options)
        self.align_columns = self._check("Aligner les colonnes", self._style["align_columns"])
        self.verbatim = self._check("Texte littéral", self._style["verbatim"])
        for check in (self.align_columns, self.verbatim):
            options.addWidget(check)
        self.entry_combo = self._combo([(label, key) for key, label in self._entries], None, translate=False)
        form_entry = QFormLayout()
        form_entry.addRow(_t("Entrée de légende"), self.entry_combo)
        layout.addLayout(form_entry)
        tools = FlowLayout()
        layout.addLayout(tools)
        self.bold = self._check("Gras", effective_font.get("weight") == "bold")
        self.italic = self._check("Italique", effective_font.get("style") == "italic")
        self.underline = self._check("Souligné", self._style["underline"])
        self._initial_font = self._font_values()
        for widget in (self.bold, self.italic, self.underline):
            tools.addWidget(widget)
        normal = QPushButton(_t("Normal"))
        normal.clicked.connect(lambda: [widget.setChecked(False) for widget in (self.bold, self.italic, self.underline)])
        tools.addWidget(normal)
        for label, prefix, suffix in (("x²", "${}^{", "}$"), ("x₂", "${}_{", "}$"), ("x²₂", "${}^{", "}_{b}$")):
            button = QPushButton(label)
            button.setToolTip(_t("Insérer un exposant ou un indice sur la sélection"))
            button.clicked.connect(lambda _checked=False, p=prefix, s=suffix: self._insert_math(p, s))
            tools.addWidget(button)
        for title, symbols in (("αβ", "α β γ δ ε θ λ μ π σ φ ω Δ Σ Ω"), ("À", "à â ä é è ê ë î ï ô ö ù û ü ç À É Ç"),
                               ("±", "± × · ° Δ ∞ ≤ ≥ ≠ → ⇌")):
            button = QToolButton()
            button.setText(title)
            button.setMinimumSize(36, 26)
            button.setToolTip(_t("Insérer un symbole"))
            menu = QMenu(button)
            for symbol in symbols.split():
                menu.addAction(symbol, lambda _checked=False, s=symbol: self.text_edit.insertPlainText(s))
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            tools.addWidget(button)
        self.text_edit = QPlainTextEdit()
        self.text_edit.setAccessibleName(_t("Texte de la légende"))
        self.text_edit.setMinimumHeight(95)
        self.text_edit.setMaximumHeight(120)
        layout.addWidget(self.text_edit, 1)
        reset = QPushButton(_t("Rétablir le libellé automatique"))
        reset.clicked.connect(self._reset_entry)
        layout.addWidget(reset)
        note = QLabel(_t("Le style s'applique à toute la légende. Le texte se modifie entrée par entrée, avec des retours à la ligne. Indices et exposants utilisent la syntaxe mathématique Matplotlib ; Texte littéral la désactive."))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.entry_combo.currentIndexChanged.connect(self._select_entry)
        self._select_entry()

    def _store_text(self):
        if self._active_entry is not None:
            key, original = self._active_entry
            text = self.text_edit.toPlainText()
            if text == original:
                self._style["entries"].pop(key, None)
            else:
                self._style["entries"][key] = text

    def _select_entry(self):
        self._store_text()
        index = self.entry_combo.currentIndex()
        self._active_entry = self._entries[index] if index >= 0 else None
        self.text_edit.setEnabled(self._active_entry is not None)
        if self._active_entry:
            key, original = self._active_entry
            self.entry_combo.setToolTip(original)
            self.text_edit.setPlainText(self._style["entries"].get(key, original))

    def _reset_entry(self):
        if self._active_entry:
            self.text_edit.setPlainText(self._active_entry[1])

    def _insert_math(self, prefix, suffix):
        cursor = self.text_edit.textCursor()
        cursor.insertText(prefix + (cursor.selectedText() or "a") + suffix)
        self.verbatim.setChecked(False)

    def values(self):
        self._store_text()
        style = deepcopy(self._style)
        style.update(frame=self.frame_combo.currentData(), fill_color="" if self.no_fill_check.isChecked() else self.fill_button.property("graphColor"),
                     fill_alpha=1 - self.transparency_spin.value() / 100,
                     border_color=self.border_button.property("graphColor"), border_width=self.border_width.value(),
                     margins={side: spin.value() for side, spin in self.margin_spins.items()},
                     wrap=self.wrap_check.isChecked(), wrap_width=self.wrap_width.value(),
                     unit=self.unit_combo.currentData(), anchor=self.anchor_combo.currentData(), anchor_frame=self.anchor_frame.isChecked(),
                     x=self.x_spin.value(), y=self.y_spin.value(), lock_x=self.lock_x.isChecked(), lock_y=self.lock_y.isChecked(),
                     text_color=self.text_color.property("graphColor"), rotation=self.rotation.value(),
                     line_spacing=self.line_spacing.value() if self.line_spacing.value() >= 25 else None,
                     tab_width=self.tab_width.value(), align_columns=self.align_columns.isChecked(),
                     columns=self.columns.value(), alignment=self.alignment.currentData(), verbatim=self.verbatim.isChecked(), underline=self.underline.isChecked())
        graph = deepcopy(self._graph)
        graph.update(legend_style=style, legend_visible=self.visible_check.isChecked(), legend_position=self.position_combo.currentData())
        if self._font_values() != self._initial_font:
            graph["fonts"]["overrides"]["legend"] = self._font_values()
        return graph_template_payload(graph)["graph"]

    def _font_values(self):
        return dict(family=self.font_combo.currentData(), size=self.font_size.value() if self.font_size.value() >= 6 else None,
                    weight="bold" if self.bold.isChecked() else "normal", style="italic" if self.italic.isChecked() else "normal")

    def apply(self):
        try:
            graph = self.values()
            self._apply_callback(graph)
        except (ValueError, OSError) as exc:
            self.error_label.setText(_t(str(exc)))
            return False
        self.error_label.clear()
        self._graph = deepcopy(graph)
        self._style = deepcopy(graph["legend_style"])
        self._initial_font = self._font_values()
        return True
