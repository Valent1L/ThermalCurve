"""Table Qt compacte pour piloter le moteur de comparaison existant."""

from __future__ import annotations

from atg_dsc_corrector.i18n import tr as _t

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSignalBlocker,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QColorDialog,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .adapters import ProjectWorkflow
from .theme import line_icon
from atg_dsc_corrector.comparison import COMPARISON_COLORS


STAGE_LABELS = {
    "original": _t('Original'),
    "corrected": _t('Corrigé'),
    "normalized": _t('Normalisé'),
}

STAT_DISPLAY_LABELS = {
    "mean": _t('Moyenne seule'),
    "mean_band": _t('Moyenne avec bande ±1 écart-type'),
    "mean_individual": _t('Moyenne avec courbes individuelles'),
    "individual": _t('Courbes individuelles seules'),
}

STAT_GRID_LABELS = {
    "auto": _t('Pas automatique (tous les points si grille commune)'),
    "manual": _t('Nombre manuel de points'),
}


class ComparisonTableModel(QAbstractTableModel):
    COLUMNS = (
        _t('Visible'), _t('Nom'), _t('Signal'), _t('Blanc'), _t('Normalisation'), _t('Style'), _t('Décalage Y')
    )

    def __init__(self, workflow: ProjectWorkflow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workflow = workflow

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.workflow.experiments)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex):
        if not index.isValid() or index.row() >= self.rowCount():
            return Qt.ItemFlag.NoItemFlags
        flags = super().flags(index) | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            return flags | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        if index.column() in {1, 2}:
            return flags | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled
        return flags | Qt.ItemFlag.ItemIsEnabled

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= self.rowCount():
            return None
        record = self.workflow.comparison_record(index.row())
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 1:
            identifier = self.workflow.comparison_key(self.workflow.experiments[index.row()])
            color = self.workflow.project_document.comparison["colors"].get(
                identifier, COMPARISON_COLORS[index.row() % len(COMPARISON_COLORS)]
            )
            swatch = QPixmap(5, 28)
            swatch.fill(QColor(color))
            return QIcon(swatch)
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 1:
            return str(self.workflow.experiments[index.row()].source_path)
        if index.column() == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if record["visible"] else Qt.CheckState.Unchecked
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
        if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
            if index.column() == 1:
                return str(record["legend_name"])
            if index.column() == 2:
                stage = str(record.get("stage", "corrected"))
                return stage if role == Qt.ItemDataRole.EditRole else STAGE_LABELS[stage]
            if index.column() == 3:
                blank = self.workflow.comparison_blank(index.row())
                return _t('Associé') if blank is not None else _t('Absent')
            if index.column() == 4:
                return _t('Active') if record.get("stage") == "normalized" else _t('Disponible')
            if index.column() == 5:
                marker = str(record.get("marker", ""))
                value = (
                    f"{record.get('line_style', '-')} · "
                    f"{float(record.get('line_width', 1.4)):g}"
                )
                return f"{value} · {marker}" if marker else value
            if index.column() == 6:
                return f"{float(record.get('y_offset', 0.0)):g}"
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 3:
            blank = self.workflow.comparison_blank(index.row())
            return _t('Aucun blanc associé') if blank is None else str(blank.source_path)
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or index.row() >= self.rowCount():
            return False
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            self.workflow.set_comparison_value(
                index.row(),
                "visible",
                value in {Qt.CheckState.Checked, Qt.CheckState.Checked.value},
            )
        elif index.column() == 1 and role == Qt.ItemDataRole.EditRole:
            name = str(value).strip()
            if not name:
                return False
            self.workflow.set_comparison_value(index.row(), "legend_name", name)
        elif index.column() == 2 and role == Qt.ItemDataRole.EditRole:
            self.workflow.set_comparison_value(index.row(), "stage", str(value))
        else:
            return False
        self.dataChanged.emit(index, index, [role])
        return True

    def refresh(self) -> None:
        self.beginResetModel()
        self.endResetModel()


class StageDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        for value, label in STAGE_LABELS.items():
            combo.addItem(label, value)
        combo.activated.connect(lambda: self.commitData.emit(combo))
        return combo

    def setEditorData(self, editor, index):
        editor.setCurrentIndex(max(0, editor.findData(index.data(Qt.ItemDataRole.EditRole))))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        rect = option.rect.adjusted(2, 2, -2, -2)
        height = min(rect.height(), max(32, editor.sizeHint().height()))
        rect.setTop(rect.top() + (rect.height() - height) // 2)
        rect.setHeight(height)
        editor.setGeometry(rect)


class ComparisonPanel(QGroupBox):
    changed = Signal()
    active_row_changed = Signal(int)
    export_data_requested = Signal()
    export_figure_requested = Signal()
    export_statistics_requested = Signal()
    auto_stack_requested = Signal()
    zero_offsets_requested = Signal()

    def __init__(self, workflow: ProjectWorkflow, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self.setObjectName("comparisonFiles")
        self.model = ComparisonTableModel(workflow, self)
        self._heat_flow_visible = True
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.signal_bar = QWidget(self)
        signal_row = QHBoxLayout(self.signal_bar)
        signal_row.setContentsMargins(0, 0, 0, 0)
        self.signal_checks: dict[str, QCheckBox] = {}
        for signal, label in (("tg", "TG"), ("dtg", "dTG"), ("heat_flow", _t('Flux de chaleur'))):
            check = QCheckBox(label)
            check.setAccessibleName(_t('Afficher le signal {v1} dans la comparaison', v1=label))
            self.signal_checks[signal] = check
            signal_row.addWidget(check)
        signal_row.addStretch(1)
        display_group = self.display_group = QGroupBox(_t('Affichage'), self)
        display_layout = QFormLayout(display_group)
        display_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        display_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        display_layout.setVerticalSpacing(6)

        self.domain_combo = QComboBox()
        self.domain_combo.addItem(_t('Union des domaines'), "union")
        self.domain_combo.addItem(_t('Recouvrement commun'), "overlap")
        display_layout.addRow(_t('Domaine'), self.domain_combo)

        offset_actions = QHBoxLayout()
        self.auto_stack_button = QPushButton(_t('Empiler'))
        self.zero_offsets_button = QPushButton(_t('Remettre à zéro'))
        offset_actions.addWidget(self.auto_stack_button)
        offset_actions.addWidget(self.zero_offsets_button)
        offset_actions.addStretch(1)
        display_layout.addRow(_t('Décalages'), offset_actions)

        self.validation_label = QLabel()
        self.validation_label.setObjectName("comparisonValidation")
        self.validation_label.setProperty("error", True)
        self.validation_label.setWordWrap(True)
        self.validation_label.setAccessibleName(
            _t('Erreur de validation de la comparaison')
        )
        self.validation_label.hide()
        display_layout.addRow(self.validation_label)
        self.curve_group = self._build_curve_editor()
        display_layout.addRow(self.curve_group)

        self.table = QTableView()
        self.table.setObjectName("comparisonTable")
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(2, StageDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(150)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.hide()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 28)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 132)
        for column in (3, 4, 5, 6):
            self.table.hideColumn(column)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.add_button = QPushButton(_t('Ajouter'))
        self.add_button.setIcon(line_icon("add"))
        self.remove_button = QPushButton(_t('Retirer'))
        self.up_button = QPushButton()
        self.up_button.setIcon(line_icon("up"))
        self.down_button = QPushButton()
        self.down_button.setIcon(line_icon("down"))
        self.up_button.setAccessibleName(_t("Monter l'essai"))
        self.down_button.setAccessibleName(_t("Descendre l'essai"))
        for button in (self.add_button, self.remove_button, self.up_button, self.down_button):
            button.setMinimumWidth(
                max(
                    button.sizeHint().width(),
                    button.fontMetrics().horizontalAdvance(button.text()) + 28,
                )
            )
            if button in (self.add_button, self.remove_button):
                actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        reorder = QHBoxLayout()
        reorder.addStretch(1)
        for button in (self.up_button, self.down_button):
            button.setFixedWidth(38)
            reorder.addWidget(button)
        reorder.addStretch(1)
        layout.addLayout(reorder)

        self.blank_button = QPushButton(_t('Associer un blanc'))
        self.blank_button.setToolTip(_t('Associer un blanc aux lignes sélectionnées'))
        self.blank_button.setEnabled(False)
        layout.addWidget(self.blank_button)

        self.statistics_group = QGroupBox(_t('Statistiques de répétitions'))
        statistics_layout = QFormLayout(self.statistics_group)
        statistics_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        statistics_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        statistics_layout.setVerticalSpacing(6)

        self.statistics_enabled_check = QCheckBox(_t('Activer le mode statistique'))
        statistics_layout.addRow(self.statistics_enabled_check)

        self.statistics_display_combo = QComboBox()
        for value, label in STAT_DISPLAY_LABELS.items():
            self.statistics_display_combo.addItem(label, value)
        statistics_layout.addRow(_t('Affichage'), self.statistics_display_combo)

        self.statistics_grid_combo = QComboBox()
        for value, label in STAT_GRID_LABELS.items():
            self.statistics_grid_combo.addItem(label, value)
        statistics_layout.addRow(_t('Grille'), self.statistics_grid_combo)

        self.statistics_points_spin = QSpinBox()
        self.statistics_points_spin.setRange(2, 1_000_000)
        statistics_layout.addRow(_t('Points'), self.statistics_points_spin)

        self.statistics_group_combo = QComboBox()
        self.statistics_group_combo.addItem(_t('Nouveau groupe'), None)
        self.statistics_group_combo.view().setAlternatingRowColors(True)
        statistics_layout.addRow(_t('Groupe'), self.statistics_group_combo)

        self.statistics_name_entry = QLineEdit()
        self.statistics_name_entry.setPlaceholderText(_t('Nom du groupe'))
        self.statistics_name_entry.setAccessibleName(
            _t('Nom du groupe de répétitions')
        )
        statistics_layout.addRow(_t('Nom'), self.statistics_name_entry)

        self.statistics_members_hint = QLabel()
        self.statistics_members_hint.setProperty("secondary", True)
        self.statistics_members_hint.setWordWrap(True)
        statistics_layout.addRow(self.statistics_members_hint)

        group_actions = QHBoxLayout()
        self.upsert_group_button = QPushButton()
        self.upsert_group_button.setToolTip(
            _t('Au moins deux expériences visibles sont nécessaires.')
        )
        self.delete_group_button = QPushButton(_t('Supprimer'))
        self.export_statistics_button = QPushButton(_t('Exporter…'))
        group_actions.addWidget(self.upsert_group_button)
        group_actions.addWidget(self.delete_group_button)
        group_actions.addWidget(self.export_statistics_button)
        group_actions.addStretch(1)
        statistics_layout.addRow(group_actions)

        self.statistics_summary = QLabel()
        self.statistics_summary.setProperty("secondary", True)
        self.statistics_summary.setWordWrap(True)
        self.statistics_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.statistics_summary.hide()
        statistics_layout.addRow(self.statistics_summary)

        self.export_bar = QWidget(self)
        export_actions = QHBoxLayout(self.export_bar)
        export_actions.setContentsMargins(0, 0, 0, 0)
        self.export_data_button = QPushButton(_t('Exporter les données'))
        self.export_data_button.setToolTip(
            _t('Le tableau contient les séries admises au graphique ; le JSON associé conserve les exclusions et leurs motifs.')
        )
        self.export_figure_button = QPushButton(_t('Exporter la figure'))
        export_actions.addWidget(self.export_figure_button)
        export_actions.addWidget(self.export_data_button)

        for button in (
            self.upsert_group_button,
            self.delete_group_button,
            self.export_statistics_button,
            self.auto_stack_button,
            self.zero_offsets_button,
            self.export_data_button,
            self.export_figure_button,
        ):
            button.setMinimumWidth(
                max(
                    button.sizeHint().width(),
                    button.fontMetrics().horizontalAdvance(button.text()) + 28,
                )
            )

        self.restore(workflow.project_document.comparison)
        self.model.dataChanged.connect(self._model_changed)
        self.model.modelReset.connect(self._update_group_controls)
        self.model.modelReset.connect(self._refresh_curve_editor)
        self.model.dataChanged.connect(self._refresh_curve_editor)
        self.model.modelReset.connect(self._open_stage_editors)
        for check in self.signal_checks.values():
            check.toggled.connect(self._signals_changed)
        self.domain_combo.currentIndexChanged.connect(self._apply_display_settings)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.statistics_enabled_check.toggled.connect(self._statistics_changed)
        self.statistics_display_combo.currentIndexChanged.connect(self._statistics_changed)
        self.statistics_grid_combo.currentIndexChanged.connect(self._statistics_changed)
        self.statistics_points_spin.valueChanged.connect(self._statistics_changed)
        self.statistics_group_combo.currentIndexChanged.connect(self._group_selected)
        self.upsert_group_button.clicked.connect(self._upsert_group)
        self.delete_group_button.clicked.connect(self._delete_group)
        self.export_statistics_button.clicked.connect(self.export_statistics_requested.emit)
        self.auto_stack_button.clicked.connect(self.auto_stack_requested.emit)
        self.zero_offsets_button.clicked.connect(self.zero_offsets_requested.emit)
        self.export_data_button.clicked.connect(self.export_data_requested.emit)
        self.export_figure_button.clicked.connect(self.export_figure_requested.emit)
        self.export_data_button.setEnabled(False)
        self.export_figure_button.setEnabled(False)

    def _build_curve_editor(self) -> QGroupBox:
        group = QGroupBox(_t('Courbe sélectionnée'), self)
        form = QFormLayout(group)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.curve_name = QLabel(_t('Sélectionnez un essai'))
        self.curve_name.setWordWrap(True)
        self.legend_entry = QLineEdit()
        self.color_button = QPushButton()
        self.style_combo = QComboBox()
        for name, value in ((_t('Continue'), "-"), (_t('Tirets'), "--"), (_t('Mixte'), "-."), (_t('Pointillés'), ":")):
            self.style_combo.addItem(name, value)
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-1e12, 1e12)
        self.offset_spin.setDecimals(6)
        form.addRow(self.curve_name)
        form.addRow(_t('Légende'), self.legend_entry)
        form.addRow(_t('Couleur'), self.color_button)
        form.addRow(_t('Style'), self.style_combo)
        form.addRow(_t('Décalage Y'), self.offset_spin)
        self.legend_entry.editingFinished.connect(lambda: self._edit_curve({"legend_name": self.legend_entry.text()}))
        self.style_combo.currentIndexChanged.connect(lambda: self._edit_curve({"line_style": self.style_combo.currentData()}))
        self.offset_spin.editingFinished.connect(lambda: self._edit_curve({"y_offset": self.offset_spin.value()}))
        self.color_button.clicked.connect(self._choose_color)
        group.setEnabled(False)
        return group

    def _open_stage_editors(self) -> None:
        for row in range(self.model.rowCount()):
            self.table.openPersistentEditor(self.model.index(row, 2))

    def _refresh_curve_editor(self, *_args) -> None:
        rows = self.selected_rows()
        self.curve_group.setEnabled(bool(rows))
        if not rows:
            self.curve_name.setText(_t('Sélectionnez un essai'))
            return
        row = rows[0]
        workflow = self.model.workflow
        record = workflow.comparison_record(row)
        self.curve_name.setText(str(record["legend_name"]))
        self.legend_entry.setText(str(record["legend_name"]))
        identifier = workflow.comparison_key(workflow.experiments[row])
        color = workflow.project_document.comparison["colors"].get(identifier, COMPARISON_COLORS[row % len(COMPARISON_COLORS)])
        self.color_button.setText(color)
        swatch = QPixmap(48, 16)
        swatch.fill(QColor(color))
        self.color_button.setIcon(QIcon(swatch))
        blockers = [QSignalBlocker(self.style_combo), QSignalBlocker(self.offset_spin)]
        self.style_combo.setCurrentIndex(self.style_combo.findData(record["line_style"]))
        self.offset_spin.setValue(float(record["y_offset"]))
        del blockers

    def _edit_curve(self, changes: dict) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        workflow = self.model.workflow
        settings = workflow.project_document.comparison
        try:
            workflow.set_comparison_graph_settings(
                graph=settings["graph"], limits=settings["limits"],
                align_zeros=settings["align_zeros"],
                show_offsets_in_legend=settings["show_offsets_in_legend"],
                rows=[rows[0]], curve_changes=changes,
            )
        except ValueError as exc:
            self.show_validation(_t(str(exc)))
            return
        self.clear_validation()
        self.model.dataChanged.emit(self.model.index(rows[0], 0), self.model.index(rows[0], 6))

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.color_button.text()), self, _t('Couleur de la courbe'))
        if color.isValid():
            self._edit_curve({"color": color.name()})

    def set_appearance(self, style: str) -> None:
        self.table.verticalHeader().setDefaultSectionSize(68 if style == "atelier" else 44)
        self.layout().setSpacing(12 if style == "atelier" else 6)

    def restore(self, settings: dict[str, object]) -> None:
        """Restaure les réglages persistés sans signaler de modification."""

        controls = (
            *self.signal_checks.values(),
            self.domain_combo,
            self.statistics_enabled_check,
            self.statistics_display_combo,
            self.statistics_grid_combo,
            self.statistics_points_spin,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        selected_signals = settings.get("signals", [settings.get("signal", "tg")])
        for signal, check in self.signal_checks.items():
            check.setChecked(signal in selected_signals)
        self.domain_combo.setCurrentIndex(
            max(0, self.domain_combo.findData(settings.get("domain_mode", "union")))
        )
        statistics = settings.get("statistics", {})
        self.statistics_enabled_check.setChecked(bool(statistics.get("enabled", False)))
        self.statistics_display_combo.setCurrentIndex(
            max(0, self.statistics_display_combo.findData(statistics.get("display_mode", "mean_band")))
        )
        self.statistics_grid_combo.setCurrentIndex(
            max(0, self.statistics_grid_combo.findData(statistics.get("grid_method", "auto")))
        )
        self.statistics_points_spin.setValue(int(statistics.get("manual_points", 200)))
        self.statistics_points_spin.setEnabled(
            self.statistics_grid_combo.currentData() == "manual"
        )
        self.refresh_groups(statistics)
        del blockers
        self.clear_validation()

    def selected_signals(self) -> tuple[str, ...]:
        return tuple(
            signal
            for signal, check in self.signal_checks.items()
            if check.isChecked() and (signal != "heat_flow" or self._heat_flow_visible)
        )

    def checked_signals(self) -> tuple[str, ...]:
        return tuple(
            signal for signal, check in self.signal_checks.items() if check.isChecked()
        )

    def _signals_changed(self, checked: bool) -> None:
        signals = self.selected_signals()
        if not signals:
            check = self.sender()
            blocker = QSignalBlocker(check)
            check.setChecked(True)
            del blocker
            self.show_validation(_t('Sélectionnez au moins une courbe à afficher.'))
            return
        try:
            self.model.workflow.set_comparison_signals(self.checked_signals())
        except ValueError as exc:
            self.show_validation(_t(str(exc)))
            return
        self.clear_validation()
        self.changed.emit()

    def _apply_display_settings(self, *_args) -> None:
        try:
            self.model.workflow.set_comparison_domain(
                str(self.domain_combo.currentData())
            )
        except ValueError as exc:
            self.show_validation(_t(str(exc)))
            return
        self.clear_validation()
        self.changed.emit()

    def show_validation(self, message: str) -> None:
        self.validation_label.setText(message)
        self.validation_label.show()

    def clear_validation(self) -> None:
        self.validation_label.clear()
        self.validation_label.hide()



    def refresh_groups(
        self,
        statistics: dict[str, object] | None = None,
        selected: str | None = None,
    ) -> None:
        statistics = statistics or self.model.workflow.project_document.comparison[
            "statistics"
        ]
        selected = (
            selected
            if selected is not None
            else self.statistics_group_combo.currentData()
        )
        blocker = QSignalBlocker(self.statistics_group_combo)
        self.statistics_group_combo.clear()
        self.statistics_group_combo.addItem(_t('Nouveau groupe'), None)
        for group in statistics.get("groups", []):
            self.statistics_group_combo.addItem(
                f"{group['name']} ({len(group['members'])})", group["id"]
            )
        self.statistics_group_combo.setCurrentIndex(
            max(0, self.statistics_group_combo.findData(selected))
        )
        del blocker
        self._group_selected()

    def _group_selected(self, *_args) -> None:
        identifier = self.statistics_group_combo.currentData()
        self.delete_group_button.setEnabled(identifier is not None)
        if identifier is None:
            self.statistics_name_entry.clear()
        else:
            groups = self.model.workflow.project_document.comparison["statistics"][
                "groups"
            ]
            group = next(group for group in groups if group["id"] == identifier)
            self.statistics_name_entry.setText(str(group["name"]))
        self._update_group_controls()

    def visible_rows(self) -> list[int]:
        return [
            row
            for row in range(self.model.rowCount())
            if self.model.workflow.comparison_record(row)["visible"]
        ]

    def _update_group_controls(self, *_args) -> None:
        count = len(self.visible_rows())
        self.statistics_members_hint.setText(
            _t("{v0} expériences visibles seront incluses. Une expérience déjà membre d'un autre groupe lui sera réaffectée.", v0=count)
        )
        self.upsert_group_button.setText(
            _t('Mettre à jour le groupe')
            if self.statistics_group_combo.currentData() is not None
            else _t('Créer le groupe')
        )
        self.upsert_group_button.setEnabled(count >= 2)

    def _model_changed(self, *_args) -> None:
        self._update_group_controls()
        self.changed.emit()

    def _statistics_changed(self, *_args) -> None:
        grid_method = str(self.statistics_grid_combo.currentData())
        self.statistics_points_spin.setEnabled(grid_method == "manual")
        try:
            self.model.workflow.set_comparison_statistics(
                enabled=self.statistics_enabled_check.isChecked(),
                display_mode=str(self.statistics_display_combo.currentData()),
                grid_method=grid_method,
                manual_points=self.statistics_points_spin.value(),
            )
        except ValueError as exc:
            self.show_validation(_t(str(exc)))
            return
        self.clear_validation()
        self.changed.emit()

    def _upsert_group(self) -> None:
        rows = self.visible_rows()
        if len(rows) < 2:
            self.show_validation(
                _t('Cochez au moins deux expériences visibles pour former un groupe.')
            )
            return
        try:
            identifier = self.model.workflow.upsert_comparison_group(
                self.statistics_group_combo.currentData(),
                self.statistics_name_entry.text(),
                rows,
            )
        except ValueError as exc:
            self.show_validation(_t(str(exc)))
            return
        self.clear_validation()
        self.refresh_groups(selected=identifier)
        self.changed.emit()

    def _delete_group(self) -> None:
        identifier = self.statistics_group_combo.currentData()
        if identifier is None:
            self.show_validation(_t('Sélectionnez un groupe à supprimer.'))
            return
        try:
            self.model.workflow.delete_comparison_group(str(identifier))
        except ValueError as exc:
            self.show_validation(_t(str(exc)))
            return
        self.clear_validation()
        self.refresh_groups()
        self.changed.emit()

    def set_statistics_summary(self, statistics: list[object]) -> None:
        lines = []
        for item in statistics:
            domain = (
                _t('aucun domaine commun')
                if item.domain is None
                else f"[{item.domain[0]:.6g}, {item.domain[1]:.6g}]"
            )
            lines.append(
                _t(
                    '{v0} ({v2}) : {v4}/{v6} répétitions, domaine {v8}, grille {v10} points',
                    v0=item.group.name,
                    v2=item.signal.upper() if item.signal != 'heat_flow' else _t('Flux de chaleur'),
                    v4=len(item.included),
                    v6=len(item.group.members),
                    v8=domain,
                    v10=item.x.size,
                )
            )
        self.statistics_summary.setText("\n".join(lines))
        self.statistics_summary.setVisible(bool(lines))
    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectionModel().selectedRows()})

    def select_row(self, row: int) -> None:
        if 0 <= row < self.model.rowCount():
            self.table.selectRow(row)

    def _selection_changed(self, *_args) -> None:
        rows = self.selected_rows()
        self._refresh_curve_editor()
        self.blank_button.setEnabled(bool(rows))
        if rows:
            self.active_row_changed.emit(rows[0])

    def set_availability(self, available: bool) -> None:
        self.export_data_button.setEnabled(available)
        self.export_figure_button.setEnabled(available)
        self.export_statistics_button.setEnabled(available)
        self.statistics_group.setEnabled(available)
        self.auto_stack_button.setEnabled(available)
        self.zero_offsets_button.setEnabled(available)

    def set_heat_flow_visible(self, visible: bool) -> None:
        """Masque Flux de chaleur sans modifier la sélection persistée."""

        self._heat_flow_visible = visible
        self.signal_checks["heat_flow"].setVisible(visible)

    def tab_controls(self) -> list[QWidget]:
        return [
            *self.signal_checks.values(),
            self.domain_combo,
            self.statistics_enabled_check,
            self.statistics_display_combo,
            self.statistics_grid_combo,
            self.statistics_points_spin,
            self.statistics_group_combo,
            self.statistics_name_entry,
            self.upsert_group_button,
            self.delete_group_button,
            self.export_statistics_button,
            self.table,
            self.add_button,
            self.blank_button,
            self.remove_button,
            self.up_button,
            self.down_button,
            self.auto_stack_button,
            self.zero_offsets_button,
            self.export_data_button,
            self.export_figure_button,
        ]
