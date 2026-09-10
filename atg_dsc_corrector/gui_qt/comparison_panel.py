"""Table Qt compacte pour piloter le moteur de comparaison existant."""

from __future__ import annotations

from atg_dsc_corrector.i18n import tr as _t, decimal_text

from .color_button import ColorButton
from .flow_layout import FlowLayout
from .curve_style_icons import curve_style_icon
from .number_format import number_locale
from atg_dsc_corrector.curve_styles import LINE_STYLES, MARKERS
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QItemSelectionModel,
    QSignalBlocker,
    QSize,
    QTimer,
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
    QSlider,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
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


class ComparisonTableModel(QAbstractItemModel):
    COLUMNS = (
        '', _t('Expérience'), _t('État'), _t('Blanc'), _t('Normalisation'), _t('Style'), _t('Décalage Y')
    )

    def __init__(self, workflow: ProjectWorkflow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workflow = workflow
        self.experiment_keys = [workflow.comparison_key(item) for item in workflow.experiments]
        self.signals = [workflow.comparison_available_signals(row) for row in range(len(workflow.experiments))]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self.signals)
        return len(self.signals[parent.row()]) if (parent.internalId() == 0 and parent.column() == 0
                                                   and 0 <= parent.row() < len(self.signals)) else 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column, parent.row() + 1 if parent.isValid() else 0)

    def parent(self, index):
        return self.createIndex(index.internalId() - 1, 0, 0) if index.isValid() and index.internalId() else QModelIndex()

    def experiment_row(self, index):
        return index.internalId() - 1 if index.internalId() else index.row()

    def signal_for(self, index):
        return self.signals[self.experiment_row(index)][index.row()] if index.isValid() and index.internalId() else None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex):
        if not index.isValid() or index.row() >= self.rowCount(index.parent()):
            return Qt.ItemFlag.NoItemFlags
        flags = super().flags(index) | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            return flags | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        if index.column() in {1, 2} and not index.parent().isValid():
            return flags | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled
        return flags | Qt.ItemFlag.ItemIsEnabled

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if (not index.isValid() or index.row() >= self.rowCount(index.parent())
                or self.experiment_row(index) >= len(self.workflow.experiments)):
            return None
        signal = self.signal_for(index)
        if signal is not None:
            settings = self.workflow.comparison_signal_settings(self.experiment_row(index), signal)
            if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if settings["visible"] else Qt.CheckState.Unchecked
            if index.column() in {0, 1}:
                if role == Qt.ItemDataRole.DisplayRole:
                    return {"tg": "TG", "dtg": "dTG", "heat_flow": _t('Flux de chaleur')}[signal]
                if role == Qt.ItemDataRole.DecorationRole:
                    swatch = QPixmap(5, 24)
                    swatch.fill(QColor(settings["color"]))
                    return QIcon(swatch)
                if role == Qt.ItemDataRole.ToolTipRole:
                    return _t('Cocher cette courbe pour cette expérience. Les filtres généraux restent prioritaires.')
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
                return Qt.CheckState.Checked if record["selected"] and record["visible"] else Qt.CheckState.Unchecked
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
                    + decimal_text(f"{float(record.get('line_width', 1.4)):g}")
                )
                return f"{value} · {marker}" if marker else value
            if index.column() == 6:
                return decimal_text(f"{float(record.get('y_offset', 0.0)):g}")
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 3:
            blank = self.workflow.comparison_blank(index.row())
            return _t('Aucun blanc associé') if blank is None else str(blank.source_path)
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or index.row() >= self.rowCount(index.parent()):
            return False
        signal = self.signal_for(index)
        if signal is not None:
            if index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
                return False
            self.workflow.set_comparison_signal_settings(self.experiment_row(index), signal,
                {"visible": value in {Qt.CheckState.Checked, Qt.CheckState.Checked.value}})
            self.dataChanged.emit(index, index, [role])
            return True
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
            if value == "corrected":
                self.workflow.comparison_record(index.row())["show_subtraction"] = True
        else:
            return False
        self.dataChanged.emit(index, index, [role])
        return True

    def refresh(self) -> None:
        self.beginResetModel()
        self.experiment_keys = [self.workflow.comparison_key(item) for item in self.workflow.experiments]
        self.signals = [self.workflow.comparison_available_signals(row) for row in range(len(self.workflow.experiments))]
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


class CurveDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.parent().isValid():
            # Spanned child rows need the same inset for paint and checkbox hit testing.
            option.rect.adjust(self.parent().indentation() * 2, 0, 0, 0)


class BlankDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if self.parent().indexWidget(index) is not None:
            option.text = ""  # The menu button already displays the assigned blank.


class ExperimentTable(QTreeView):
    def mousePressEvent(self, event):
        self._checkbox_pressed = False
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and index.column() == 0 and event.button() == Qt.MouseButton.LeftButton:
            option = QStyleOptionViewItem()
            option.rect = self.visualRect(index)
            self.itemDelegateForIndex(index).initStyleOption(option, index)
            indicator = self.style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, self)
            if not index.parent().isValid() or indicator.contains(event.position().toPoint()):
                self._checkbox_pressed = True
                state = index.data(Qt.ItemDataRole.CheckStateRole)
                self.model().setData(index, Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and getattr(self, "_checkbox_pressed", False):
            self._checkbox_pressed = False
            event.accept()  # The press already toggled the checkbox; do not let the delegate toggle it again.
            return
        super().mouseReleaseEvent(event)

class ComparisonPanel(QGroupBox):
    changed = Signal()
    active_row_changed = Signal(int)
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
        signal_row = FlowLayout(self.signal_bar)
        signal_row.setContentsMargins(0, 0, 0, 0)
        self.signal_checks: dict[str, QCheckBox] = {}
        for signal, label in (("tg", "TG"), ("dtg", "dTG"), ("heat_flow", _t('Flux de chaleur'))):
            check = QCheckBox(label)
            check.setAccessibleName(_t('Afficher le signal {v1} dans la comparaison', v1=label))
            self.signal_checks[signal] = check
            signal_row.addWidget(check)
        self._mean_available = False
        self._stack_active = False
        self._stack_signal = None
        display_group = self.display_group = QGroupBox(_t('Courbes'), self)
        display_group.setLocale(number_locale())
        display_layout = QFormLayout(display_group)
        display_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        display_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        display_layout.setVerticalSpacing(6)

        self.curve_group = self._build_curve_editor()
        display_layout.addRow(self.curve_group)
        self.stack_group = QGroupBox(_t('Empilement des expériences cochées'))
        stack_layout = QFormLayout(self.stack_group)
        stack_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.stack_signal_combo = QComboBox()
        self.stack_signal_combo.currentIndexChanged.connect(self._stack_target_changed)
        stack_layout.addRow(_t('Axe'), self.stack_signal_combo)
        self.auto_spacing_check = QCheckBox(_t('Écart automatique'))
        self.auto_spacing_check.setChecked(True)
        stack_layout.addRow(self.auto_spacing_check)
        self.stack_spacing_spin = QDoubleSpinBox()
        self.stack_spacing_spin.setRange(0, 1e12)
        self.stack_spacing_spin.setDecimals(8)
        self.stack_spacing_spin.setKeyboardTracking(False)
        self.stack_spacing_spin.setValue(1)
        self.stack_spacing_spin.setAccessibleName(_t("Écart entre courbes dans l'unité de l'axe"))
        self.stack_slider = QSlider(Qt.Orientation.Horizontal)
        self.stack_slider.setRange(0, 1000)
        self.stack_slider.setTracking(False)
        self.stack_slider.setAccessibleName(_t("Écart entre courbes dans l'unité de l'axe"))
        self._stack_slider_max = 3.0
        self.stack_slider.setValue(333)
        stack_layout.addRow(_t('Écart entre courbes'), self.stack_spacing_spin)
        stack_layout.addRow(self.stack_slider)
        self.stack_timer = QTimer(self)
        self.stack_timer.setSingleShot(True)
        self.stack_timer.setInterval(80)
        self.stack_timer.timeout.connect(self.auto_stack_requested.emit)
        self.stack_slider.valueChanged.connect(lambda value: self.stack_spacing_spin.setValue(value * self._stack_slider_max / 1000))
        self.stack_spacing_spin.valueChanged.connect(self._stack_spacing_changed)
        self.auto_spacing_check.toggled.connect(self._update_stack_enabled)
        offset_actions = FlowLayout()
        self.auto_stack_button = QPushButton(_t('Empiler'))
        self.zero_offsets_button = QPushButton(_t('Remettre à zéro'))
        offset_actions.addWidget(self.auto_stack_button)
        offset_actions.addWidget(self.zero_offsets_button)
        stack_layout.addRow(offset_actions)
        display_layout.addRow(self.stack_group)

        self.validation_label = QLabel()
        self.validation_label.setObjectName("comparisonValidation")
        self.validation_label.setProperty("error", True)
        self.validation_label.setWordWrap(True)
        self.validation_label.setAccessibleName(
            _t('Erreur de validation de la comparaison')
        )
        self.validation_label.hide()
        display_layout.addRow(self.validation_label)

        self.table = ExperimentTable()
        self.table.setObjectName("comparisonTable")
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(0, CurveDelegate(self.table))
        self.table.setItemDelegateForColumn(2, StageDelegate(self.table))
        self.table.setItemDelegateForColumn(3, BlankDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setRootIsDecorated(True)
        self.table.setTreePosition(1)
        self.table.setIndentation(16)
        self.table.setUniformRowHeights(True)
        self.table.setItemsExpandable(True)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(150)
        header = self.table.header()
        header.show()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 28)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 108)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 100)
        for column in (4, 5, 6):
            self.table.hideColumn(column)
        layout.addWidget(self.table, 1)

        actions = FlowLayout()
        self.add_button = QPushButton(_t('Ajouter'))
        self.add_button.setIcon(line_icon("add"))
        self.remove_button = QPushButton(_t('Retirer'))
        self.up_button = QPushButton()
        self.up_button.setIcon(line_icon("up"))
        self.down_button = QPushButton()
        self.down_button.setIcon(line_icon("down"))
        self.up_button.setAccessibleName(_t("Monter l'essai"))
        self.down_button.setAccessibleName(_t("Descendre l'essai"))
        self.up_button.setToolTip(self.up_button.accessibleName())
        self.down_button.setToolTip(self.down_button.accessibleName())
        for button in (self.add_button, self.remove_button, self.up_button, self.down_button):
            button.setMinimumWidth(
                max(
                    button.sizeHint().width(),
                    button.fontMetrics().horizontalAdvance(button.text()) + 28,
                )
            )
            if button in (self.add_button, self.remove_button):
                actions.addWidget(button)
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
        layout.addWidget(self.validation_label)

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

        self.statistics_members_hint = QLabel()
        self.statistics_members_hint.setProperty("secondary", True)
        self.statistics_members_hint.setWordWrap(True)
        statistics_layout.addRow(self.statistics_members_hint)

        self.statistics_summary = QLabel()
        self.statistics_summary.setProperty("secondary", True)
        self.statistics_summary.setWordWrap(True)
        self.statistics_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.statistics_summary.hide()
        statistics_layout.addRow(self.statistics_summary)

        self.restore(workflow.project_document.comparison)
        for combo in (self.statistics_display_combo, self.statistics_grid_combo, self.curve_signal_combo,
                      self.curve_target_combo, self.marker_combo, self.style_combo, self.stack_signal_combo):
            combo.view().setAlternatingRowColors(True)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
            combo.setToolTip(combo.currentText())
            combo.currentTextChanged.connect(combo.setToolTip)
        self.model.dataChanged.connect(self._model_changed)
        self.model.modelReset.connect(self._update_selection_hint)
        self.model.modelReset.connect(self._refresh_curve_editor)
        self.model.dataChanged.connect(self._refresh_curve_editor)
        self.model.modelReset.connect(self._open_stage_editors)
        self.model.modelAboutToBeReset.connect(self._remember_tree_state)
        self.model.modelReset.connect(self._restore_tree_state)
        self._tree_state = (set(), None, None)
        for check in self.signal_checks.values():
            check.toggled.connect(self._signals_changed)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.statistics_enabled_check.toggled.connect(self._statistics_changed)
        self.statistics_display_combo.currentIndexChanged.connect(self._statistics_changed)
        self.statistics_grid_combo.currentIndexChanged.connect(self._statistics_changed)
        self.statistics_points_spin.valueChanged.connect(self._statistics_changed)
        self.auto_stack_button.clicked.connect(self.auto_stack_requested.emit)
        self.zero_offsets_button.clicked.connect(self.zero_offsets_requested.emit)

    def _build_curve_editor(self) -> QGroupBox:
        group = QGroupBox(_t('Courbes à modifier'), self)
        form = QFormLayout(group)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.curve_name = QLabel(_t('Sélectionnez un essai'))
        self.curve_name.setWordWrap(True)
        self.curve_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.curve_target_combo = QComboBox()
        self.curve_target_combo.addItem(_t('Expérience sélectionnée'), 'experiment')
        self.curve_target_combo.currentIndexChanged.connect(self._refresh_curve_editor)
        self.curve_signal_combo = QComboBox()
        self.curve_signal_combo.addItem(_t('Toutes les courbes'), None)
        for signal, label in (("tg", "TG"), ("dtg", "dTG"), ("heat_flow", _t('Flux de chaleur'))):
            self.curve_signal_combo.addItem(label, signal)
        self.curve_signal_combo.currentIndexChanged.connect(self._curve_scope_changed)
        self.legend_entry = QLineEdit()
        self.color_button = ColorButton()
        self.style_combo = QComboBox()
        self.style_combo.setIconSize(QSize(64, 20))
        for value, (name, _) in LINE_STYLES.items():
            self.style_combo.addItem(curve_style_icon('line', value), _t(name), value)
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-1e12, 1e12)
        self.offset_spin.setDecimals(6)
        form.addRow(_t('Cible'), self.curve_target_combo)
        form.addRow(self.curve_name)
        form.addRow(_t('Courbe'), self.curve_signal_combo)
        form.addRow(_t('Légende'), self.legend_entry)
        form.addRow(_t('Couleur'), self.color_button)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 10)
        self.width_spin.setSingleStep(0.1)
        self.width_spin.setDecimals(1)
        self.marker_combo = QComboBox()
        self.marker_combo.setIconSize(QSize(32, 20))
        for marker, name in MARKERS.items():
            self.marker_combo.addItem(curve_style_icon('marker', marker), _t(name), marker)
        self.markevery_spin = QSpinBox()
        self.markevery_spin.setRange(0, 1000000)
        self.markevery_spin.setSpecialValueText(_t('Tous les points'))
        form.addRow(_t('Épaisseur'), self.width_spin)
        form.addRow(_t('Style'), self.style_combo)
        form.addRow(_t('Marqueur'), self.marker_combo)
        form.addRow(_t('Pas des marqueurs'), self.markevery_spin)
        self.width_spin.valueChanged.connect(lambda: self._edit_curve({"line_width": self.width_spin.value()}))
        self.marker_combo.currentIndexChanged.connect(lambda: self._edit_curve({"marker": self.marker_combo.currentData()}))
        self.markevery_spin.valueChanged.connect(lambda: self._edit_curve({"markevery": self.markevery_spin.value() or None}))
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
            for child_row in range(3):
                self.table.setFirstColumnSpanned(child_row, self.model.index(row, 0), True)

    def _refresh_curve_editor(self, *_args) -> None:
        workflow = self.model.workflow
        statistics = workflow.project_document.comparison['statistics']
        mean_available = statistics['enabled'] and statistics['display_mode'] != 'individual'
        target = self.curve_target_combo.currentData()
        if mean_available and not self._mean_available:
            target = 'mean'
        self._mean_available = mean_available
        with QSignalBlocker(self.curve_target_combo):
            self.curve_target_combo.clear()
            self.curve_target_combo.addItem(_t('Expérience sélectionnée'), 'experiment')
            if mean_available:
                self.curve_target_combo.addItem(_t('Moyenne des expériences cochées'), 'mean')
            self.curve_target_combo.setCurrentIndex(max(0, self.curve_target_combo.findData(target)))
        is_mean = self.curve_target_combo.currentData() == 'mean'
        rows = self.selected_rows()
        self._refresh_stack_controls()
        self.curve_group.setEnabled(bool(rows) or mean_available)
        for control in (self.curve_signal_combo, self.legend_entry, self.color_button,
                        self.style_combo, self.offset_spin, self.width_spin,
                        self.marker_combo, self.markevery_spin):
            control.setEnabled(bool(rows) or is_mean)
        if not rows and not is_mean:
            self.curve_name.setText(_t('Sélectionnez un essai'))
            self.curve_name.setToolTip("")
            return
        row = rows[0] if rows else None
        signal = self.curve_signal_combo.currentData() if is_mean else self.model.signal_for(self.table.currentIndex())
        controls = (self.curve_signal_combo, self.legend_entry, self.style_combo,
                    self.offset_spin, self.width_spin, self.marker_combo, self.markevery_spin)
        blockers = [QSignalBlocker(control) for control in controls]
        self.curve_signal_combo.clear()
        self.curve_signal_combo.addItem(_t('Toutes les courbes'), None)
        labels = {"tg": "TG", "dtg": "dTG", "heat_flow": _t('Flux de chaleur')}
        available_signals = self.selected_signals() if is_mean else self.model.signals[row]
        for available in available_signals:
            self.curve_signal_combo.addItem(labels[available], available)
        self.curve_signal_combo.setCurrentIndex(max(0, self.curve_signal_combo.findData(signal)))
        signal = self.curve_signal_combo.currentData()
        if is_mean:
            settings = workflow.mean_curve_settings(signal or (available_signals[0] if available_signals else 'tg'))
            self.curve_name.setText(_t('Moyenne des expériences cochées'))
            self.curve_name.setToolTip(_t("Les styles et décalages visuels ne modifient pas les statistiques calculées."))
            self.legend_entry.setPlaceholderText(_t('Automatique'))
        else:
            settings = workflow.comparison_signal_settings(row, signal or '')
            self.curve_name.setText(workflow.experiments[row].source_path.name)
            self.curve_name.setToolTip(str(workflow.experiments[row].source_path))
            self.legend_entry.setPlaceholderText('')
        self.legend_entry.setText(str(settings["legend_name"]))
        self.color_button.setText(settings["color"])
        self.style_combo.setCurrentIndex(self.style_combo.findData(settings["line_style"]))
        self.offset_spin.setValue(settings["y_offset"])
        self.width_spin.setValue(settings["line_width"])
        self.marker_combo.setCurrentIndex(self.marker_combo.findData(settings["marker"]))
        self.markevery_spin.setValue(settings["markevery"] or 0)
        del blockers

    def _curve_scope_changed(self):
        if self.curve_target_combo.currentData() == 'mean':
            self._refresh_curve_editor()
            return
        rows = self.selected_rows()
        if rows:
            self.select_row(rows[0], self.curve_signal_combo.currentData())

    def _edit_curve(self, changes: dict) -> None:
        if self.curve_target_combo.currentData() == 'mean':
            signal = self.curve_signal_combo.currentData()
            try:
                self.model.workflow.set_mean_curve_settings((signal,) if signal else self.selected_signals(), changes)
            except ValueError as exc:
                self.show_validation(_t(str(exc)))
                return
            self.clear_validation()
            self._refresh_curve_editor()
            self.changed.emit()
            return
        rows = self.selected_rows()
        if not rows:
            return
        workflow = self.model.workflow
        settings = workflow.project_document.comparison
        try:
            signal = self.curve_signal_combo.currentData()
            if signal is not None:
                workflow.set_comparison_signal_settings(rows[0], signal, changes)
            else:
                workflow.set_comparison_graph_settings(
                    graph=settings["graph"], limits=settings["limits"],
                    align_zeros=settings["align_zeros"], show_offsets_in_legend=settings["show_offsets_in_legend"],
                    rows=[rows[0]], curve_changes=changes,
                )
        except ValueError as exc:
            self.show_validation(_t(str(exc)))
            return
        self.clear_validation()
        with QSignalBlocker(self):
            self.model.dataChanged.emit(self.model.index(rows[0], 0), self.model.index(rows[0], 6))
        parent = self.model.index(rows[0], 0)
        self.model.dataChanged.emit(self.model.index(0, 0, parent), self.model.index(2, 6, parent))

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.color_button.property("graphColor")), self, _t('Couleur de la courbe'))
        if color.isValid():
            self._edit_curve({"color": color.name()})

    def set_appearance(self) -> None:
        self.table.setStyleSheet("QTreeView::item { height: 38px; }")
        self.layout().setSpacing(6)

    def restore(self, settings: dict[str, object]) -> None:
        """Restaure les réglages persistés sans signaler de modification."""

        controls = (
            *self.signal_checks.values(),
            self.statistics_enabled_check,
            self.statistics_display_combo,
            self.statistics_grid_combo,
            self.statistics_points_spin,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        selected_signals = settings.get("signals", [settings.get("signal", "tg")])
        for signal, check in self.signal_checks.items():
            check.setChecked(signal in selected_signals)
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
        self._update_selection_hint()
        del blockers
        self._stack_signal = None
        self._stack_active = False
        self._refresh_curve_editor()
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
        self._refresh_curve_editor()
        self.changed.emit()


    def show_validation(self, message: str) -> None:
        self.validation_label.setText(message)
        self.validation_label.show()

    def clear_validation(self) -> None:
        self.validation_label.clear()
        self.validation_label.hide()


    def visible_rows(self) -> list[int]:
        return [
            row
            for row in range(self.model.rowCount())
            if (self.model.workflow.comparison_record(row)["selected"]
                and self.model.workflow.comparison_record(row)["visible"])
        ]

    def _update_selection_hint(self, *_args) -> None:
        self.statistics_members_hint.setText(_t(
            'Statistiques sur les courbes cochées des {v0} expériences cochées. Une bande d’écart-type nécessite au moins deux courbes compatibles.',
            v0=len(self.visible_rows())))

    def _model_changed(self, *_args) -> None:
        self._update_selection_hint()
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
        self._refresh_curve_editor()
        self.changed.emit()


    def set_statistics_summary(self, statistics: list[object]) -> None:
        lines = []
        for item in statistics:
            domain = (
                _t('aucun domaine commun')
                if item.domain is None
                else f"[{decimal_text(f'{item.domain[0]:.6g}')} ; {decimal_text(f'{item.domain[1]:.6g}')}]"
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
        return sorted({self.model.experiment_row(index) for index in self.table.selectionModel().selectedRows()})

    def select_row(self, row: int, signal: str | None = None) -> None:
        if 0 <= row < self.model.rowCount():
            index = self.model.index(row, 1)
            if signal in self.model.signals[row]:
                parent = self.model.index(row, 0)
                self.table.setExpanded(parent, True)
                index = self.model.index(self.model.signals[row].index(signal), 0, parent)
            self.table.selectionModel().setCurrentIndex(index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)

    def _remember_tree_state(self):
        expanded = {key for row, key in enumerate(self.model.experiment_keys)
                    if self.table.isExpanded(self.model.createIndex(row, 0, 0))}
        index = self.table.currentIndex()
        row = self.model.experiment_row(index) if index.isValid() else -1
        key = self.model.experiment_keys[row] if 0 <= row < len(self.model.experiment_keys) else None
        self._tree_state = (expanded, key, self.model.signal_for(index))

    def _restore_tree_state(self):
        expanded, key, signal = self._tree_state
        workflow = self.model.workflow
        for row, experiment in enumerate(workflow.experiments):
            identifier = workflow.comparison_key(experiment)
            self.table.setExpanded(self.model.index(row, 0), identifier in expanded)
            if experiment is workflow.experiment:
                with QSignalBlocker(self):
                    self.select_row(row, signal if identifier == key else None)

    def _selection_changed(self, *_args) -> None:
        rows = self.selected_rows()
        self._refresh_curve_editor()
        self.blank_button.setEnabled(bool(rows))
        if rows:
            self.active_row_changed.emit(rows[0])

    def set_availability(self, available: bool) -> None:
        self.statistics_group.setEnabled(available)
        self.zero_offsets_button.setEnabled(available)
        self._update_stack_enabled()

    def _refresh_stack_controls(self):
        setting = self.model.workflow.project_document.comparison['stacking']
        selected = setting['signal'] if self._stack_signal is None else self.stack_signal_combo.currentData()
        with QSignalBlocker(self.stack_signal_combo):
            self.stack_signal_combo.clear()
            for signal in self.selected_signals():
                self.stack_signal_combo.addItem(_t({'tg': 'TG', 'dtg': 'dTG', 'heat_flow': 'Flux de chaleur'}[signal]), signal)
            self.stack_signal_combo.setCurrentIndex(max(0, self.stack_signal_combo.findData(selected)))
        if self._stack_signal != self.stack_signal_combo.currentData():
            self._stack_target_changed()
        self._update_stack_enabled()

    def _stack_target_changed(self, *_args):
        self.stack_timer.stop()
        self._stack_active = False
        self._stack_signal = self.stack_signal_combo.currentData()
        setting = self.model.workflow.project_document.comparison['stacking']
        spacing = setting['spacing'] if setting['signal'] == self._stack_signal else None
        self.set_stack_spacing(1 if spacing is None else spacing, active=False)
        self.auto_spacing_check.setChecked(spacing is None)
        self._update_stack_enabled()

    def set_stack_spacing(self, value, *, active=True):
        if not self._stack_active or value > self._stack_slider_max:
            self._stack_slider_max = min(1e12, max(float(value) * 3, 1e-8))
        with QSignalBlocker(self.stack_spacing_spin), QSignalBlocker(self.stack_slider):
            self.stack_spacing_spin.setValue(value)
            self.stack_spacing_spin.setSingleStep(max(value / 100, 1e-8))
            self.stack_slider.setValue(round(value / self._stack_slider_max * 1000))
        self._stack_active = active
        self.auto_spacing_check.setChecked(False)
        self._update_stack_enabled()

    def _stack_spacing_changed(self, value):
        if value > self._stack_slider_max:
            self._stack_slider_max = min(1e12, value * 3)
        with QSignalBlocker(self.stack_slider):
            self.stack_slider.setValue(round(value / self._stack_slider_max * 1000))
        if self._stack_active:
            self.stack_timer.start()

    def _update_stack_enabled(self, *_args):
        statistics = self.model.workflow.project_document.comparison['statistics']
        available = bool(self.stack_signal_combo.count()) and len(self.visible_rows()) > 1
        available = available and (not statistics['enabled'] or statistics['display_mode'] in {'individual', 'mean_individual'})
        self.auto_stack_button.setEnabled(available)
        self.auto_spacing_check.setEnabled(available)
        for widget in (self.stack_spacing_spin, self.stack_slider):
            widget.setEnabled(available and not self.auto_spacing_check.isChecked())
        self.stack_group.setToolTip(_t("L'empilement décale les courbes individuelles affichées sur l'axe choisi."))
        if not available:
            self.stack_timer.stop()
            self._stack_active = False

    def set_heat_flow_visible(self, visible: bool) -> None:
        """Masque Flux de chaleur sans modifier la sélection persistée."""

        self._heat_flow_visible = visible
        self.signal_checks["heat_flow"].setVisible(visible)

    def tab_controls(self) -> list[QWidget]:
        return [*self.signal_checks.values(), self.statistics_enabled_check,
                self.statistics_display_combo, self.statistics_grid_combo, self.statistics_points_spin,
                self.table, self.add_button, self.blank_button, self.remove_button,
                self.up_button, self.down_button, self.auto_stack_button, self.zero_offsets_button,
                self.curve_target_combo, self.curve_signal_combo, self.legend_entry, self.color_button, self.width_spin,
                self.stack_signal_combo, self.auto_spacing_check, self.stack_spacing_spin, self.stack_slider,
                self.style_combo, self.marker_combo, self.markevery_spin, self.offset_spin]
