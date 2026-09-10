"""Fast XLSX writing with the same data, layout and source protection."""
from pathlib import Path
from pprint import pformat
import math
import os
from datetime import datetime, date, time, timedelta
import numpy as np
import pandas as pd
import xlsxwriter
from xlsxwriter.exceptions import XlsxWriterException
from atg_dsc_corrector.i18n import tr as _t
from atg_dsc_corrector.workbook_export import _column_header

def write_fast_workbook(destination, file_format, sheets, *, protected_paths=(), overwrite=False):
    from atg_dsc_corrector.exporters import ExportError, _temporary_path, _validate_destinations
    if file_format.lower().lstrip('.') != 'xlsx':
        raise ExportError(_t("Le format d'export doit être XLSX."))
    target = Path(destination).with_suffix('.xlsx')
    _validate_destinations((target,), protected_paths, overwrite=overwrite)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(target)
    try:
        with xlsxwriter.Workbook(temporary, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False}) as book:
            body = book.add_format({'text_wrap': True, 'valign': 'vcenter'})
            heading = book.add_format({'text_wrap': True, 'valign': 'vcenter', 'bold': True, 'font_color': '#23394D'})
            header = book.add_format({'text_wrap': True, 'valign': 'vcenter', 'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#36566F'})
            dates = {}
            for title, blocks in sheets:
                sheet = book.add_worksheet(_t(title))
                sheet.freeze_panes(3, 0)
                widths, heights, wrapped = ({}, {}, [])
                start = 0
                maxrow = 0
                for name, frame, metadata in blocks:
                    width = len(frame.columns)
                    if not width:
                        continue
                    if start + width > 16384 or len(frame) + 3 > 1048576:
                        raise ExportError(_t("Les données dépassent les dimensions maximales d'une feuille Excel."))
                    for row, values in enumerate(([name], [str(metadata.get('source_path', ''))], [_column_header(col, metadata.get('units', {})) for col in frame.columns])):
                        for offset, value in enumerate(values):
                            value = str(value)
                            if len(value) > 32767:
                                raise ExportError(_t('Une cellule de texte dépasse la limite Excel de 32767 caractères.'))
                            col = start + offset
                            span = width if row < 2 else 1
                            if span > 1:
                                sheet.merge_range(row, col, row, col + span - 1, value, heading)
                            else:
                                sheet.write_string(row, col, value, header if row == 2 else heading)
                            heights[row] = 19
                            wrapped.append((row, col, span, value))
                            if span == 1:
                                widths[col] = max(widths.get(col, 0), max(map(len, value.splitlines()), default=0))
                    if sheet.write_comment(0, start, pformat(metadata, sort_dicts=False), {'author': 'ThermalCurve', 'width': 144, 'height': 79}) != 0:
                        raise ExportError(_t('Le commentaire de provenance dépasse la limite Excel.'))
                    for row, values in enumerate(frame.itertuples(index=False, name=None), start=3):
                        for offset, value in enumerate(values):
                            if value is None or pd.isna(value):
                                continue
                            if isinstance(value, np.generic):
                                value = value.item()
                            if isinstance(value, float) and (not math.isfinite(value)):
                                continue
                            col = start + offset
                            heights[row] = 19
                            if isinstance(value, str):
                                if sheet.write_string(row, col, value, body) != 0:
                                    raise ExportError(_t('Une cellule de texte dépasse la limite Excel de 32767 caractères.'))
                                wrapped.append((row, col, 1, value))
                                length = max(map(len, value.splitlines()), default=0)
                            elif isinstance(value, (datetime, date, time, timedelta)):
                                fmt = '[hh]:mm:ss' if isinstance(value, timedelta) else 'h:mm:ss' if isinstance(value, time) else 'yyyy-mm-dd h:mm:ss' if isinstance(value, datetime) else 'yyyy-mm-dd'
                                if fmt not in dates:
                                    dates[fmt] = book.add_format({'text_wrap': True, 'valign': 'vcenter', 'num_format': fmt})
                                sheet.write_datetime(row, col, value, dates[fmt])
                                length = len(str(value))
                            elif isinstance(value, bool):
                                sheet.write_boolean(row, col, value, body)
                                length = len(str(value))
                            else:
                                sheet.write_number(row, col, value, body)
                                length = len(str(value))
                            widths[col] = max(widths.get(col, 0), length)
                    maxrow = max(maxrow, max(heights, default=0))
                    sheet.set_column(start + width, start + width, 3 - 5 / 7)
                    start += width + 1
                    maxrow = max(maxrow, 2)
                if start == 0:
                    value = _t('Aucune donnée.')
                    sheet.write_string(0, 0, value, body)
                    widths[0], heights[0] = (len(value), 19)
                sizes = {col: min(80, max(8, length + 3)) for col, length in widths.items()}
                for col, width in sizes.items():
                    sheet.set_column(col, col, width - 5 / 7)
                    sheet.col_info[col][5] = True  # Preserve the existing bestFit flag.
                for row, col, span, value in wrapped:
                    capacity = max(1, sum((sizes.get(i, 13) for i in range(col, col + span))) - 3)
                    lines = sum((max(1, math.ceil(len(line) / capacity)) for line in value.split('\n')))
                    heights[row] = max(heights[row], 15 * lines + 4)
                for row in range(maxrow + 1):
                    sheet.set_row(row, heights.get(row, 15))
        os.replace(temporary, target)
    except XlsxWriterException as exc:
        raise ExportError(str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return target
