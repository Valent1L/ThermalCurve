"""Table presentation of existing zone results; no scientific calculations."""

import csv
from io import StringIO

from PySide6.QtCore import Qt, QRect, QSize, QTimer, QPoint
from .number_format import number_locale
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QHeaderView, QStyle, QStyleOptionHeader, QStyleOptionViewItem, QTableWidget, QTableWidgetItem

from atg_dsc_corrector.i18n import tr as _t
from atg_dsc_corrector.labels import plain_display_label


# key, label, family, unit (literal or result field), shown in summary
COLUMNS = (
    ("zone_name", "Zone", "", "", True),
    ("valid_point_count", "Points", "", "", False),
    ("delta_zone_mg", "Δm", "TG", "mg", True),
    ("delta_zone_pct_m0", "Δm/m0", "TG", "%", True),
    ("delta_zone_pct_reference", "Δm/réf.", "TG", "%", False),
    ("remaining_mass_end_mg", "Masse finale", "TG", "mg", False),
    ("residual_mass_end_pct", "Résiduel", "TG", "%", True),
    ("dtg_minimum", "Min", "dTG", "@dtg_unit", False),
    ("dtg_minimum_position", "Position min", "dTG", "@axis_unit", False),
    ("dtg_maximum", "Max", "dTG", "@dtg_unit", False),
    ("dtg_maximum_position", "Position max", "dTG", "@axis_unit", False),
    ("dtg_main_peak", "Pic", "dTG", "@dtg_unit", True),
    ("dtg_main_peak_position", "Position du pic", "dTG", "@axis_unit", True),
    ("heat_flow_minimum", "Min", "Flux de chaleur", "@heat_flow_unit", False),
    ("heat_flow_minimum_position", "Position min", "Flux de chaleur", "@axis_unit", False),
    ("heat_flow_maximum", "Max", "Flux de chaleur", "@heat_flow_unit", False),
    ("heat_flow_maximum_position", "Position max", "Flux de chaleur", "@axis_unit", False),
    ("heat_flow_main_peak", "Pic", "Flux de chaleur", "@heat_flow_unit", True),
    ("heat_flow_main_peak_position", "Position du pic", "Flux de chaleur", "@axis_unit", True),
    ("heat_flow_area", "Aire signée", "Flux de chaleur", "@heat_flow_area_unit", True),
    ("heat_flow_positive_area", "Aire +", "Flux de chaleur", "@heat_flow_area_unit", False),
    ("heat_flow_negative_area", "Aire -", "Flux de chaleur", "@heat_flow_area_unit", False),
    ("start", "Début", "Contexte", "@axis_unit", False),
    ("end", "Fin", "Contexte", "@axis_unit", False),
    ("axis_type", "Axe", "Contexte", "", False),
    ("initial_mass_mg", "m0", "Contexte", "mg", False),
    ("reference_mass_mg", "Masse de référence", "Contexte", "mg", False),
    ("reference_name", "Référence", "Contexte", "", False),
    ("baseline_method", "Ligne de base", "Contexte", "", False),
    ("baseline_value", "Valeur", "Contexte", "@baseline_unit", False),
    ("baseline_representation", "Représentation de la constante", "Contexte", "", False),
    ("tg_state", "État TG", "Contexte", "", False),
    ("dtg_state", "État dTG", "Contexte", "", False),
    ("heat_flow_state", "État Flux de chaleur", "Contexte", "", False),
    ("representations", "Représentations", "Contexte", "", False),
    ("status", "État", "Contexte", "", False),
    ("warnings", "Avertissements", "Contexte", "", False),
)


STAT_COLUMNS = (
    ("stat_start_mean", "Moyenne au début", "Statistiques", "@stat_unit", False),
    ("stat_end_mean", "Moyenne à la fin", "Statistiques", "@stat_unit", False),
    ("stat_delta", "Variation de la moyenne", "Statistiques", "@stat_delta_unit", True),
    ("stat_minimum", "Min", "Statistiques", "@stat_unit", False),
    ("stat_maximum", "Max", "Statistiques", "@stat_unit", False),
    ("stat_start_std", "Écart-type au début", "Statistiques", "@stat_unit", False),
    ("stat_end_std", "Écart-type à la fin", "Statistiques", "@stat_unit", False),
    ("stat_delta_low", "Enveloppe Δ basse", "Statistiques", "@stat_delta_unit", True),
    ("stat_delta_high", "Enveloppe Δ haute", "Statistiques", "@stat_delta_unit", True),
    ("stat_count", "Répétitions", "Statistiques", "", False),
)


class GroupedHeader(QHeaderView):
    def __init__(self, parent):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.groups, self.labels = [], []
        self.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setMinimumSectionSize(35)

    def sizeHint(self):
        return QSize(super().sizeHint().width(), self.fontMetrics().height() * 3 + 24)

    def group_boundaries(self):
        previous = None
        boundaries = []
        for column, group in enumerate(self.groups):
            if self.isSectionHidden(column):
                continue
            if previous is not None and group != previous:
                boundaries.append(self.sectionViewportPosition(column))
            previous = group
        return boundaries

    def separator_pen(self):
        color = self.palette().color(QPalette.ColorRole.ButtonText)
        color.setAlpha(110)
        return QPen(color, 2)

    def sectionSizeFromContents(self, index):
        if index >= len(self.labels):
            return super().sectionSizeFromContents(index)
        width = max(self.fontMetrics().horizontalAdvance(line) for line in self.labels[index].splitlines())
        return QSize(width + 24, self.sizeHint().height())

    def paintSection(self, painter, rect, index):
        if index >= len(self.labels):
            return
        option = QStyleOptionHeader()
        self.initStyleOption(option)
        option.rect = QRect(rect.x(), rect.y() + rect.height() // 3, rect.width(), rect.height() * 2 // 3)
        painter.save()
        self.style().drawControl(QStyle.ControlElement.CE_HeaderSection, option, painter, self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.ButtonText))
        painter.drawText(option.rect.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignCenter, self.labels[index])
        painter.restore()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        runs = []
        for index, group in enumerate(self.groups):
            if self.isSectionHidden(index):
                continue
            x, width = self.sectionViewportPosition(index), self.sectionSize(index)
            if runs and runs[-1][0] == group:
                runs[-1][2] += width
            else:
                runs.append([group, x, width])
        for group, x, width in runs:
            option = QStyleOptionHeader()
            self.initStyleOption(option)
            option.rect = QRect(x, 0, width, self.height() // 3)
            self.style().drawControl(QStyle.ControlElement.CE_HeaderSection, option, painter, self)
            # Keep one family label visible even when its columns extend far
            # outside the viewport. Native styles must not repeat model titles.
            painter.setFont(self.font())
            painter.setPen(self.palette().color(QPalette.ColorRole.ButtonText))
            visible = option.rect.intersected(self.viewport().rect())
            if visible.width() > 12 and not visible.isEmpty():
                painter.drawText(visible.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignCenter, group)
        painter.setPen(self.separator_pen())
        for x in self.group_boundaries():
            painter.drawLine(x, 0, x, self.height())
        painter.end()


def copy_table(table, *, first_column=0):
    """Copy the entire current view, including off-screen rows, as Excel-friendly TSV."""
    columns = [c for c in range(first_column, table.columnCount()) if not table.isColumnHidden(c)]
    output = StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    for name in dict.fromkeys(row.get("experiment_name", "") for row in getattr(table, "records", ()) if row.get("statistics")):
        writer.writerow([name])
    header = table.horizontalHeader()
    writer.writerow([(f"{header.groups[c]} - " if isinstance(header, GroupedHeader) and header.groups[c] else "")
                     + table.horizontalHeaderItem(c).text() for c in columns])
    for row in range(table.rowCount()):
        values = []
        for col in columns:
            item = table.item(row, col)
            raw = item.data(Qt.ItemDataRole.UserRole + 1) if item else None
            if first_column and isinstance(raw, float):
                raw = number_locale().toString(raw, "g", 17)
            elif first_column:
                raw = None  # Definitions copy their translated labels, not editor identifiers.
            values.append(raw if raw is not None else item.text() if item else "")
        writer.writerow(values)
    QApplication.clipboard().setText(output.getvalue())


class ZoneResultsTable(QTableWidget):
    def __init__(self, parent=None, *, context_only=False):
        super().__init__(parent)
        self.records = []
        self.complete = False
        self.context_only = context_only
        self.columns = []
        self._widths = {}
        self._sizing = False
        self.setObjectName("zoneResultsTable")
        self.setHorizontalHeader(GroupedHeader(self))
        self.horizontalHeader().sectionResized.connect(self._remember_width)
        self.verticalHeader().hide()
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)

    def _remember_width(self, column, old, width):
        if not self._sizing and width > 0 and column < len(self.columns):
            self._widths[self.columns[column][0]] = width

    def paintEvent(self, event):
        super().paintEvent(event)
        header = self.horizontalHeader()
        painter = QPainter(self.viewport())
        painter.setPen(header.separator_pen())
        header_offset = header.viewport().mapTo(self, QPoint()).x() - self.viewport().x()
        for row in range(self.rowCount()):
            top = self.rowViewportPosition(row)
            bottom = top + self.rowHeight(row)
            if bottom < 0 or top > self.viewport().height() or self.columnSpan(row, 0) > 1:
                continue
            for x in header.group_boundaries():
                # Native styles can offset the header viewport from the cells.
                cell_x = x + header_offset
                painter.drawLine(cell_x, top, cell_x, bottom)
        painter.end()

    def showEvent(self, event):
        super().showEvent(event)
        # Windows finalizes native fonts after showEvent.
        QTimer.singleShot(0, self, self.resize_to_contents)

    def set_records(self, records):
        self.records = records
        self._sizing = True
        self.clearSpans()
        families = {"TG": "tg", "dTG": "dtg", "Flux de chaleur": "heat_flow"}
        visible_signals = {signal for row in records for signal in row.get("signals", families.values())}
        self.columns = []
        for spec_index, spec in enumerate(COLUMNS):
            family = spec[2]
            if (self.context_only and family != "Contexte" and spec[0] != "zone_name") or (not self.context_only and family == "Contexte"):
                continue
            if records and family in families and families[family] not in visible_signals:
                continue
            self.columns.append(spec)
            # Complete details stay within the corresponding TG/dTG/heat-flow block.
            last = not any(item[2] == family for item in COLUMNS[spec_index + 1:])
            signal = families.get(family)
            if last and signal and any(signal in row.get("statistics", {}) for row in records):
                self.columns.extend((signal + ":" + key, label, family, signal + ":" + unit, False)
                                    for key, label, _group, unit, _summary in STAT_COLUMNS)
        self.setColumnCount(len(self.columns))
        groups = {}
        for record in records:
            identity = record.get("experiment_key") or record.get("experiment_name", "")
            groups.setdefault(identity, []).append(record)
        display_rows = []
        for rows in groups.values():
            if len(groups) > 1 and not rows[0].get("statistics"):
                display_rows.append((None, rows[0].get("experiment_name", "")))
            display_rows.extend((record, "") for record in rows)
        self.setRowCount(len(display_rows))
        header = self.horizontalHeader()
        header.groups, header.labels = [], []
        locale = number_locale()
        for col, (key, label, group, unit, summary) in enumerate(self.columns):
            stat_signal = key.split(":")[0] if ":" in key else None
            if stat_signal == "heat_flow":
                label = {"stat_minimum": "Min avant ligne de base", "stat_maximum": "Max avant ligne de base",
                         "stat_start_mean": "Début avant ligne de base", "stat_end_mean": "Fin avant ligne de base"}.get(key.split(":")[1], label)
            unit = unit.split(":", 1)[-1] if stat_signal else unit
            def row_unit(row):
                source = row.get("statistics", {}).get(stat_signal, {}) if stat_signal else row
                value = source.get(unit[1:], "") if unit.startswith("@") else unit
                if key == "delta_zone_mg" and "mean_tg_unit" in row:
                    value = row["mean_tg_unit"]
                return plain_display_label(str(value or ""))
            units = {row_unit(row) for row in records} - {""} if records else {unit} - {""} if not unit.startswith("@") else set()
            if key == "delta_zone_mg" and units != {"mg"}:
                label = "ΔTG"
            common = next(iter(units)) if len(units) == 1 else ""
            if key.endswith("_position"):
                is_time = units <= {"s", "min", "h"}
                label = ("Temps" if is_time else "Température") if summary and not self.complete else (
                    ("t " if is_time else "T ") + ("min" if "minimum" in key else "max" if "maximum" in key else "pic"))
            if key == "heat_flow_area" and not self.complete:
                label = "Aire"
            title = _t(label) + (f" ({common})" if common else "")
            header.groups.append(_t(group))
            header.labels.append(title.replace(" (", "\n("))
            self.setHorizontalHeaderItem(col, QTableWidgetItem(title))
            for index, (record, group_name) in enumerate(display_rows):
                if record is None:
                    self.setItem(index, col, QTableWidgetItem(group_name if col == 0 else ""))
                    continue
                value = record.get("statistics", {}).get(stat_signal, {}).get(key.split(":", 1)[1]) if stat_signal else record.get(key)
                if key == "delta_zone_mg" and "mean_tg_delta" in record:
                    value = record["mean_tg_delta"]
                if group in families and families[group] not in record.get("signals", families.values()):
                    value = None
                if isinstance(value, (tuple, list)):
                    value = "\n".join(map(str, value))
                if isinstance(value, float):
                    text, raw = locale.toString(value, "g", 4), locale.toString(value, "g", 17)
                else:
                    text = "-" if value is None or value == "" else str(value)
                    if key in {"status", "baseline_method", "tg_state", "dtg_state", "heat_flow_state"}:
                        text = {"none": "Aucune", "constant": "Constante", "linear": "Linéaire",
                                "corrected": "corrigé", "calculated": "calculé", "derived": "dérivé",
                                "unavailable": "Indisponible", "mean": "Moyenne"}.get(text, text)
                        text = _t(text)
                    raw = text
                if key == "axis_type":
                    text = _t({"time_s": "Temps (s)", "time_min": "Temps (min)", "time_h": "Temps (h)",
                               "furnace_temperature": "Température du four", "sample_temperature": "Température de l'échantillon"}.get(text, text))
                    raw = text
                if key == "warnings":
                    text = text.replace("\n", "; ")
                if len(units) > 1 and value is not None:
                    suffix = row_unit(record)
                    text, raw = f"{text} {suffix}", f"{raw} {suffix}"
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, record.get("zone_id"))
                item.setData(Qt.ItemDataRole.UserRole + 1, raw)
                item.setToolTip("\n".join(filter(None, [record.get("experiment_name"), raw, "\n".join(record.get("warnings", ())) ])))
                if isinstance(value, (int, float)):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(index, col, item)
        for row, (record, group_name) in enumerate(display_rows):
            if record is None:
                self.setSpan(row, 0, 1, len(self.columns))
                item = self.item(row, 0)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setToolTip(group_name)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.set_complete(self.complete)

    def set_complete(self, complete):
        self._sizing = True
        self.complete = complete
        for col, spec in enumerate(self.columns):
            self.setColumnHidden(col, not complete and not spec[4])
        self.resize_to_contents()

    def resize_to_contents(self):
        """Measure visible labels and all data rows, excluding spanned group names."""
        self._sizing = True
        header = self.horizontalHeader()
        option = QStyleOptionViewItem()
        self.initViewItemOption(option)
        for col, spec in enumerate(self.columns):
            if not self.isColumnHidden(col):
                width = header.sectionSizeFromContents(col).width()
                for row in range(self.rowCount()):
                    if self.columnSpan(row, 0) > 1:
                        continue
                    index = self.model().index(row, col)
                    width = max(width, self.itemDelegateForIndex(index).sizeHint(option, index).width() + 2)
                self.setColumnWidth(col, self._widths.get(spec[0], width))
        self.resizeRowsToContents()
        self._sizing = False
        self.horizontalHeader().viewport().update()
