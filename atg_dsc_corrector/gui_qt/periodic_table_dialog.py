"""Fenêtre Qt native de consultation du tableau périodique."""

from __future__ import annotations

from atg_dsc_corrector.i18n import language, tr as _t

import unicodedata
from html import escape

from PySide6.QtCore import QEvent, QLocale, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPalette, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from atg_dsc_corrector.atomic_data import format_atomic_weight
from atg_dsc_corrector.periodic_table_data import (
    MENDELEEV_DATA_SOURCE,
    PeriodicTableData,
    PeriodicTableEntry,
    load_periodic_table,
)


_ATOMIC_NUMBER_ROLE = Qt.ItemDataRole.UserRole
_SYMBOL_ROLE = Qt.ItemDataRole.UserRole + 1
_NAME_ROLE = Qt.ItemDataRole.UserRole + 2
_MASS_ROLE = Qt.ItemDataRole.UserRole + 3


def _element_name(entry: PeriodicTableEntry) -> str:
    if language() == "en" and entry.enrichment and entry.enrichment.name_en:
        return entry.enrichment.name_en
    return entry.element.name_fr

# Mendeleev-data 310fcad9, data/json/series.json; MIT license in resources/mendeleev.
# Bokeh v1.2.0 uses these series colors with fill_alpha=0.6 on white.
_SERIES_STYLES = {
    1: (_t('Non-métaux'), "#baa2a6"), 2: (_t('Gaz nobles'), "#bbbb88"),
    3: (_t('Métaux alcalins'), "#a6cee3"), 4: (_t('Métaux alcalino-terreux'), "#1f78b4"),
    5: (_t('Métalloïdes'), "#33a02c"), 6: (_t('Halogènes'), "#fdbf6f"),
    7: (_t('Métaux pauvres'), "#b2df8a"), 8: (_t('Métaux de transition'), "#e08e79"),
    9: (_t('Lanthanides'), "#cab2d6"), 10: (_t('Actinides'), "#6a3d9a"),
}


def _series_background(color: str) -> QColor:
    source = QColor(color)
    return QColor(*(round(channel * 0.6 + 255 * 0.4) for channel in source.getRgb()[:3]))


def _normalized(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(character) != "Mn"
    )


class _ElementCellDelegate(QStyledItemDelegate):
    """Peint les quatre informations sans créer 118 widgets enfants."""

    def paint(self, painter, option, index) -> None:  # type: ignore[override]
        atomic_number = index.data(_ATOMIC_NUMBER_ROLE)
        if atomic_number is None:
            painter.fillRect(option.rect, QColor("white"))
            return
        painter.save()
        margin = 3 if option.rect.height() >= 65 else 1
        tile = option.rect.adjusted(margin, margin, -margin, -margin)
        painter.fillRect(tile, index.data(Qt.ItemDataRole.BackgroundRole))
        painter.setPen(QPen(QColor("#a0a0a0"), 1))
        painter.drawRect(tile.adjusted(0, 0, -1, -1))
        if option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus):
            painter.setPen(QPen(QColor("#202020"), 2))
            painter.drawRect(tile.adjusted(1, 1, -2, -2))
            painter.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(tile.adjusted(3, 3, -4, -4))
        painter.setPen(QColor("#000000"))
        rect = tile.adjusted(2, 2, -2, -2)
        compact = option.rect.height() < 65 or option.rect.width() < 50
        scale = min(option.rect.width() / 74, option.rect.height() / 96)
        number_font = QFont(option.font)
        number_font.setPixelSize(max(6, round((15 if compact else 12) * scale)))
        painter.setFont(number_font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, str(atomic_number))
        symbol_font = QFont(option.font)
        symbol_font.setBold(True)
        symbol_font.setPixelSize(max(8, round((28 if compact else 22) * scale)))
        painter.setFont(symbol_font)
        detail_font = QFont(option.font)
        detail_font.setPixelSize(max(7, round((16 if compact else 11) * scale)))
        detail_height = QFontMetrics(detail_font).height()
        detail_rows = 1 if compact else 2
        painter.drawText(
            rect.adjusted(0, QFontMetrics(number_font).height(), 0, -detail_rows * detail_height),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            str(index.data(_SYMBOL_ROLE)),
        )
        painter.setFont(detail_font)
        painter.drawText(
            rect.adjusted(0, rect.height() - detail_rows * detail_height, 0, -(detail_rows - 1) * detail_height),
            Qt.AlignmentFlag.AlignCenter,
            str(index.data(_MASS_ROLE)),
        )
        if not compact:
            name = painter.fontMetrics().elidedText(str(index.data(_NAME_ROLE)), Qt.TextElideMode.ElideRight, rect.width())
            painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, name)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # type: ignore[override]
        return QSize(74, 96)

    def helpEvent(self, event, view, option, index) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.ToolTip and index.data(_ATOMIC_NUMBER_ROLE) is not None:
            QToolTip.showText(event.globalPos(), index.data(Qt.ItemDataRole.ToolTipRole), view.viewport(), option.rect)
            return True
        return super().helpEvent(event, view, option, index)


class PeriodicTableDialog(QDialog):
    """Consultation seule du référentiel J18 et de son enrichissement local."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data: PeriodicTableData = load_periodic_table()
        self.entries_by_number = {
            entry.element.atomic_number: entry for entry in self.data.entries
        }
        self.current_entry: PeriodicTableEntry | None = None
        self._items_by_number: dict[int, tuple[QTableWidget, QTableWidgetItem]] = {}
        self._locale = QLocale(QLocale.Language.French, QLocale.Country.France)
        self.setObjectName("periodicTable")
        self.setStyleSheet("""
            QDialog#periodicTable, QWidget#periodicGrid, QWidget#periodicTiles,
            QWidget#periodicLegend, QLabel { background: white; color: #202020; }
            QTableWidget { background: white; alternate-background-color: white; border: none; }
            QHeaderView { background: white; border: none; }
            QSizeGrip { background: white; }
            QHeaderView::section {
                background: white; color: #505050; border: none;
                padding: 0; font-weight: normal;
            }
            QTableCornerButton::section { background: white; border: none; }
        """)
        self.setWindowTitle(_t('Tableau périodique'))
        self.setModal(False)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setMinimumSize(480, 360)
        available = self.screen().availableGeometry()
        self.resize(min(1440, available.width() - 40), min(1000, available.height() - 60))
        self._build_window()
        self._populate_tables()
        self._connect_signals()
        self.select_atomic_number(1)

    def _build_window(self) -> None:
        layout = QVBoxLayout(self)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(_t('Rechercher un élément'), self))
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText(_t('Symbole, nom français ou anglais, numéro atomique'))
        self.search_edit.setAccessibleName(_t('Rechercher un élément'))
        search_row.addWidget(self.search_edit, 1)
        layout.addLayout(search_row)
        self.search_status = QLabel("", self)
        self.search_status.setWordWrap(True)
        self.search_status.hide()
        layout.addWidget(self.search_status)

        self.grid_panel = QWidget(self)
        self.grid_panel.setObjectName("periodicGrid")
        grid_panel = self.grid_panel
        grid_layout = QVBoxLayout(grid_panel)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(QLabel(_t('Tableau périodique · Groupes 1 à 18 · Masses en g/mol'), grid_panel))
        self.table_panel = QWidget(grid_panel)
        self.table_panel.setObjectName("periodicTiles")
        self.table_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.main_table = self._table(7, [str(period) for period in range(1, 8)])
        self.series_table = self._table(2, ["6", "7"], headers=False)
        for table in (self.main_table, self.series_table):
            table.setParent(self.table_panel)
        self.table_panel.installEventFilter(self)
        grid_layout.addWidget(self.table_panel, 1)
        self.legend = QWidget(grid_panel)
        self.legend.setObjectName("periodicLegend")
        legend_layout = QGridLayout(self.legend)
        for index, (name, color) in enumerate(_SERIES_STYLES.values()):
            label = QLabel(name, self.legend)
            label.setWordWrap(True)
            label.setMargin(2)
            label.setMinimumWidth(0)
            label.setStyleSheet(f"background-color: {_series_background(color).name()}; color: black;")
            legend_layout.addWidget(label, index // 5, index % 5)
        grid_layout.addWidget(self.legend)
        grid_layout.addWidget(QLabel(_t('Couleurs : séries Mendeleev · Blanc : série indisponible'), grid_panel))
        layout.addWidget(grid_panel, 1)

        self.details_dialog = QDialog(self, Qt.WindowType.Tool)
        self.details_dialog.setWindowTitle(_t("Détail de l'élément"))
        self.details_dialog.setModal(False)
        available = self.screen().availableGeometry()
        self.details_dialog.resize(min(460, available.width() - 40), min(440, available.height() - 60))
        popup_layout = QVBoxLayout(self.details_dialog)
        details = QGroupBox(_t("Détail de l'élément"), self.details_dialog)
        detail_layout = QVBoxLayout(details)
        self.detail_title = QLabel(details)
        title_font = self.detail_title.font()
        title_font.setBold(True)
        title_font.setPointSizeF(title_font.pointSizeF() + 3.0)
        self.detail_title.setFont(title_font)
        detail_layout.addWidget(self.detail_title)
        detail_form = QFormLayout()
        self.detail_atomic_number = self._detail_label(details)
        self.detail_mass = self._detail_label(details)
        self.detail_position = self._detail_label(details)
        self.detail_configuration = self._detail_label(details)
        self.detail_radioactivity = self._detail_label(details)
        self.detail_source = self._detail_label(details)
        detail_form.addRow(_t('Numéro atomique'), self.detail_atomic_number)
        detail_form.addRow(_t('Masse de calcul'), self.detail_mass)
        detail_form.addRow(_t('Groupe, période, bloc'), self.detail_position)
        detail_form.addRow(_t('Configuration électronique'), self.detail_configuration)
        detail_form.addRow(_t('Radioactivité'), self.detail_radioactivity)
        detail_form.addRow(_t('Provenance'), self.detail_source)
        detail_layout.addLayout(detail_form)
        self.mass_convention = self._detail_label(details)
        self.mass_convention.setText(
            _t("Entre crochets : nombre de masse d'un isotope de référence, sans poids atomique standard.")
        )
        detail_layout.addWidget(self.mass_convention)
        self.enrichment_status = self._detail_label(details)
        detail_layout.addWidget(self.enrichment_status)
        detail_layout.addStretch(1)
        self.details_scroll = QScrollArea(self.details_dialog)
        self.details_scroll.setWidget(details)
        self.details_scroll.setWidgetResizable(True)

        popup_layout.addWidget(self.details_scroll)

        actions = QHBoxLayout()
        self.copy_symbol_button = QPushButton(_t('Copier le symbole'), self)
        self.copy_information_button = QPushButton(_t('Copier les informations'), self)
        actions.addWidget(self.copy_symbol_button)
        actions.addWidget(self.copy_information_button)
        actions.addStretch(1)
        self.close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.close_buttons.button(QDialogButtonBox.StandardButton.Close).setText(_t('Fermer'))
        actions.addWidget(self.close_buttons)
        layout.addLayout(actions)
        popup_close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self.details_dialog)
        popup_close.button(QDialogButtonBox.StandardButton.Close).setText(_t('Fermer'))
        popup_close.rejected.connect(self.details_dialog.close)
        popup_layout.addWidget(popup_close)

    @staticmethod
    def _detail_label(parent: QWidget) -> QLabel:
        label = QLabel(parent)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _table(self, rows: int, vertical_labels: list[str], *, headers: bool = True) -> QTableWidget:
        table = QTableWidget(rows, 18, self)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAccessibleName(_t('Grille du tableau périodique'))
        table.setItemDelegate(_ElementCellDelegate(table))
        table.setShowGrid(False)
        palette = table.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("white"))
        table.setPalette(palette)
        table.setVerticalHeaderLabels(vertical_labels)
        for header in (table.horizontalHeader(), table.verticalHeader()):
            header.setHighlightSections(False)
            header.setSectionsClickable(False)
            header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        table.verticalHeader().setFixedWidth(28)
        table.verticalHeader().setMinimumSectionSize(1)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setMinimumSectionSize(1)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        if headers:
            table.setHorizontalHeaderLabels([str(group) for group in range(1, 19)])
            table.horizontalHeader().setFixedHeight(table.horizontalHeader().sizeHint().height())
        else:
            table.horizontalHeader().hide()
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setMinimumSize(0, 0)
        table.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        return table

    def _populate_tables(self) -> None:
        for entry in self.data.entries:
            element = entry.element
            if entry.group is None:
                row = 0 if entry.period == 6 else 1
                column = element.atomic_number - (58 if row == 0 else 90) + 2
                table = self.series_table
            else:
                row = entry.period - 1
                column = entry.group - 1
                table = self.main_table
            item = QTableWidgetItem(element.symbol)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(_ATOMIC_NUMBER_ROLE, element.atomic_number)
            item.setData(_SYMBOL_ROLE, element.symbol)
            item.setData(_NAME_ROLE, _element_name(entry))
            item.setData(_MASS_ROLE, self._display_mass(entry).removesuffix(" g/mol"))
            series_id = entry.enrichment.series_id if entry.enrichment else None
            series_name, color = _SERIES_STYLES.get(series_id, (_t('Série indisponible'), "#ffffff"))
            item.setBackground(_series_background(color))
            configuration = entry.enrichment.electronic_configuration if entry.enrichment else None
            fields = (
                (_t('Élément'), f"{_element_name(entry)} ({element.symbol})"),
                (_t('Numéro atomique'), str(element.atomic_number)),
                (_t('Masse'), self._display_mass(entry)),
                (_t('Série'), series_name),
                (_t('Configuration électronique'), configuration or _t('Indisponible')),
            )
            item.setToolTip('<table cellspacing="4">' + ''.join(
                f"<tr><td><b>{escape(label)}</b></td><td>{escape(value)}</td></tr>"
                for label, value in fields
            ) + '</table>')
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{element.atomic_number} {element.symbol}, {_element_name(entry)}, "
                f"{self._display_mass(entry)}, {series_name}",
            )
            table.setItem(row, column, item)
            self._items_by_number[element.atomic_number] = (table, item)

    def _connect_signals(self) -> None:
        for table in (self.main_table, self.series_table):
            table.itemSelectionChanged.connect(lambda source=table: self._show_selected(source))
            table.itemClicked.connect(self._open_details)
            table.itemActivated.connect(self._open_details)
        self.search_edit.returnPressed.connect(self.search)
        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.activated.connect(self.search_edit.setFocus)
        self.copy_symbol_button.clicked.connect(self.copy_symbol)
        self.copy_information_button.clicked.connect(self.copy_information)
        self.close_buttons.rejected.connect(self.close)

    def _display_mass(self, entry: PeriodicTableEntry) -> str:
        formatted = format_atomic_weight(entry.element)
        if formatted.startswith("["):
            return formatted
        return formatted.replace(".", str(self._locale.decimalPoint())) + " g/mol"

    def hideEvent(self, event) -> None:  # type: ignore[override]
        self.details_dialog.hide()
        super().hideEvent(event)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if watched is self.table_panel and event.type() == QEvent.Type.Resize:
            frame = self.main_table.frameWidth() * 2
            header_width = self.main_table.verticalHeader().width()
            header_height = self.main_table.horizontalHeader().height()
            gap = 6
            side = max(1, min(
                (self.table_panel.width() - header_width - frame) // 18,
                (self.table_panel.height() - header_height - 2 * frame - gap) // 9,
            ))
            width = 18 * side + header_width + frame
            height = 9 * side + header_height + 2 * frame + gap
            x = (self.table_panel.width() - width) // 2
            y = (self.table_panel.height() - height) // 2
            for table in (self.main_table, self.series_table):
                table.horizontalHeader().setDefaultSectionSize(side)
                table.verticalHeader().setDefaultSectionSize(side)
            main_height = 7 * side + header_height + frame
            self.main_table.setGeometry(x, y, width, main_height)
            self.series_table.setGeometry(x, y + main_height + gap, width, 2 * side + frame)
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "legend"):
            self.legend.setVisible(self.width() >= 1000 and self.height() >= 600)

    def _open_details(self, item: QTableWidgetItem) -> None:
        if item.data(_ATOMIC_NUMBER_ROLE) is None:
            return
        self._show_item(item)
        self.details_dialog.show()
        self.details_dialog.raise_()

    def _show_selected(self, table: QTableWidget) -> None:
        item = table.currentItem()
        if item is not None:
            self._show_item(item)

    def _show_item(self, item: QTableWidgetItem) -> None:
        atomic_number = item.data(_ATOMIC_NUMBER_ROLE)
        if atomic_number is not None:
            for table in (self.main_table, self.series_table):
                if table is not item.tableWidget():
                    table.blockSignals(True)
                    table.clearSelection()
                    table.blockSignals(False)
            self._show_entry(self.entries_by_number[int(atomic_number)])

    def _show_entry(self, entry: PeriodicTableEntry) -> None:
        self.current_entry = entry
        element = entry.element
        enrichment = entry.enrichment
        self.detail_title.setText(f"{element.symbol} - {_element_name(entry)}")
        self.detail_atomic_number.setText(str(element.atomic_number))
        self.detail_mass.setText(self._display_mass(entry))
        group = "-" if entry.group is None else str(entry.group)
        block = "-" if enrichment is None or enrichment.block is None else enrichment.block
        self.detail_position.setText(f"{group}, {entry.period}, {block}")
        self.detail_configuration.setText(
            _t('Indisponible') if enrichment is None or enrichment.electronic_configuration is None else enrichment.electronic_configuration
        )
        if enrichment is None or enrichment.is_radioactive is None:
            radioactivity = _t('Indisponible')
        else:
            radioactivity = _t('Déclarée radioactive') if enrichment.is_radioactive else _t('Non déclarée radioactive')
        self.detail_radioactivity.setText(radioactivity)
        self.detail_source.setText(_t('Source de calcul : CIAAW/IUPAC via J18'))
        if enrichment is None:
            self.enrichment_status.setText(_t('Informations complémentaires : indisponibles'))
        else:
            self.enrichment_status.setText(
                _t(
                    'Informations complémentaires : {v1}. Nom anglais : {v3}.',
                    v1=MENDELEEV_DATA_SOURCE,
                    v3=enrichment.name_en or _t('Indisponible'),
                )
            )

    def select_atomic_number(self, atomic_number: int) -> None:
        table, item = self._items_by_number[atomic_number]
        table.setCurrentItem(item)
        self._show_item(item)

    def search(self) -> None:
        self.search_status.show()
        query = _normalized(self.search_edit.text().strip())
        if not query:
            self.search_status.setText(_t('Saisissez un symbole, un nom ou un numéro atomique.'))
            return
        entries = tuple(self.entries_by_number.values())
        if query.isdecimal():
            matches = [entry for entry in entries if str(entry.element.atomic_number) == query]
        else:
            exact = [
                entry
                for entry in entries
                if query
                in {
                    _normalized(entry.element.symbol),
                    _normalized(entry.element.name_fr),
                    _normalized(entry.enrichment.name_en) if entry.enrichment and entry.enrichment.name_en else "",
                }
            ]
            matches = exact or [
                entry
                for entry in entries
                if any(
                    value.startswith(query)
                    for value in (
                        _normalized(entry.element.symbol),
                        _normalized(entry.element.name_fr),
                        _normalized(entry.enrichment.name_en)
                        if entry.enrichment and entry.enrichment.name_en
                        else "",
                    )
                )
            ]
        if not matches:
            self.search_status.setText(_t('Aucun élément ne correspond à cette recherche.'))
            return
        entry = matches[0]
        self.select_atomic_number(entry.element.atomic_number)
        self.search_status.setText(_t('Élément sélectionné : {v1} ({v3}).', v1=_element_name(entry), v3=entry.element.symbol))

    def copy_symbol(self) -> None:
        if self.current_entry is not None:
            QApplication.clipboard().setText(self.current_entry.element.symbol)

    def copy_information(self) -> None:
        if self.current_entry is None:
            return
        element = self.current_entry.element
        enrichment = self.current_entry.enrichment
        details = [
            f"{element.symbol} - {_element_name(self.current_entry)}",
            _t('Numéro atomique : {v1}', v1=element.atomic_number),
            _t('Masse de calcul : {v1}', v1=self._display_mass(self.current_entry)),
            _t('Source de calcul : CIAAW/IUPAC via J18'),
        ]
        if enrichment is None:
            details.append(_t('Informations complémentaires : indisponibles'))
        else:
            details.extend(
                (
                    _t('Nom anglais : {v1}', v1=enrichment.name_en or _t('Indisponible')),
                    _t('Informations complémentaires : {v1}', v1=MENDELEEV_DATA_SOURCE),
                )
            )
        QApplication.clipboard().setText("\n".join(details))
