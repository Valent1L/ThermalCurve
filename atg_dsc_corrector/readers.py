"""Lecteurs pour les exports ATG-DSC Excel et ATG texte."""

from __future__ import annotations

from .models import TIME_UNIT_SECONDS

import codecs
import csv
from dataclasses import dataclass
from io import StringIO
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import numpy as np
import pandas as pd

from .input_safety import (
    DataReadError, MAX_INPUT_BYTES, MAX_TEXT_LINE_CHARS, MAX_TABLE_ROWS,
    check_input_size, check_table_size, check_xlsx_archive, read_limited_bytes,
)
from .i18n import tr

from .models import (
    CANONICAL_FIELDS,
    ColumnMapping,
    ExperimentData,
    FileInspection,
    FileProbe,
    capture_source_fingerprint,
)


def _load_with_fingerprint(
    source: Path,
    loader: Callable[[], ExperimentData],
) -> ExperimentData:
    check_input_size(source)
    before = capture_source_fingerprint(source)
    experiment = loader()
    after = capture_source_fingerprint(source)
    if before.sha256 != after.sha256:
        raise DataReadError(
            f"Le fichier source a été modifié pendant son chargement : {source}."
        )
    experiment.source_fingerprint = before
    return experiment


@dataclass(frozen=True, slots=True)
class DetectedFileFormat:
    """Format déterminé par la signature binaire, indépendamment de l'extension."""

    kind: str
    encoding: str | None = None

    @property
    def is_spreadsheet(self) -> bool:
        return self.kind in {"xls", "xlsx"}

    @property
    def engine(self) -> str | None:
        return {"xls": "xlrd", "xlsx": "openpyxl"}.get(self.kind)

    def display_name(self, path: Path, delimiter: str | None = None) -> str:
        if self.kind == "xls":
            return "XLS binaire"
        if self.kind == "xlsx":
            return "XLSX (ZIP)"
        separator = {
            "\t": "tabulé",
            ";": "séparé par point-virgule",
            ",": "séparé par virgule",
        }.get(delimiter, "texte")
        encoding = {
            "text_utf16": "UTF-16",
            "text_utf8": "UTF-8",
            "text_cp1252": "Windows-1252",
        }[self.kind]
        suffix_note = (
            " avec extension .xls"
            if path.suffix.lower() == ".xls"
            else ""
        )
        return f"Texte {encoding} {separator}{suffix_note}"


@dataclass(frozen=True, slots=True)
class HeaderSchema:
    """En-tête source, identifiants internes uniques et unités associées."""

    raw_headers: tuple[str, ...]
    columns: tuple[str, ...]
    units: dict[str, str]


_XLS_MAGIC = bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1")


_ALIASES: dict[str, tuple[str, ...]] = {
    "time": ("time", "temps", "elapsedtime", "t"),
    "furnace_temperature": (
        "furnacetemperature",
        "furnacetemp",
        "furnace temperature",
        "furnace temp",
        "four temperature",
        "four temp",
        "temperaturefour",
        "temperature four",
        "temperature du four",
        "tempfour",
        "temp four",
        "temp du four",
        "tfour",
        "oven temperature",
    ),
    "sample_temperature": (
        "sampletemperature",
        "sampletemp",
        "sample temperature",
        "sample temp",
        "temperatureechantillon",
        "temperature echantillon",
        "temperature de l echantillon",
        "tempechantillon",
        "temp echantillon",
        "temp de l echantillon",
        "techantillon",
        "specimentemperature",
    ),
    "tg": ("tg", "tga", "mass", "masse", "weight", "weightchange", "dm"),
    "dtg": ("dtg", "derivativetg", "derivativeweight", "dm/dt", "dmasse/dt"),
    "heat_flow": (
        "heatflow",
        "heat flow",
        "fluxchaleur",
        "fluxthermique",
        "dsc",
        "hf",
    ),
}

_TIME_SECONDS = {"s","/s","sec", "secs", "second", "seconds", "seconde", "secondes"}
_TIME_MINUTES = {"min", "mins", "minute", "minutes"}
_TIME_HOURS = {"h", "hr", "hrs", "hour", "hours", "heure", "heures"}
_INDEX_KEYS = {"index", "indice", "point"}
_TIME_KEYS = {"temps", "time", "t"}
_TEMPERATURE_KEYS = {"temperature", "temp","/°C"}
_TG_KEYS = {"tg", "masse", "mass", "weight","/mg"}
_DTG_KEYS = {"dtg", "deriveetg", "derivativetg", "/mg/min", "/mg/s", "/mg/h"}
_HEAT_FLOW_KEYS = {"heatflow", "dsc", "fluxthermique", "fluxdechaleur"}


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return str(value).strip()


def _unit_from_units_row(value: Any) -> str:
    """Canonise le séparateur initial admis dans la ligne d'unités ATG."""

    unit = _text(value)
    return unit[1:].lstrip() if unit.startswith("/") else unit


def _ascii_lower(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _name_key(value: Any) -> str:
    text = _ascii_lower(value)
    text = re.sub(r"\[[^]]*]|\([^)]*\)", "", text)
    return re.sub(r"[^a-z0-9/]+", "", text)


def _unit_key(value: Any) -> str:
    text = _ascii_lower(value).replace("−", "-")
    return re.sub(r"\s+", "", text).strip("[]()")


def _unit_from_header(column: str) -> str:
    match = re.search(r"\[([^]]+)]|\(([^)]+)\)\s*$", column)
    if match:
        return _text(match.group(1) or match.group(2))
    full_key = _name_key(column)
    known_aliases = {_name_key(alias) for aliases in _ALIASES.values() for alias in aliases}
    if full_key in known_aliases:
        return ""
    slash = re.search(r"/\s*(.+)$", column)
    return _text(slash.group(1)) if slash else ""


def detect_columns(
    columns: Iterable[Any], manual_mapping: Mapping[str, str] | None = None
) -> ColumnMapping:
    """Reconnaît les variantes usuelles et applique ensuite l'association manuelle."""

    original = [str(column).strip() for column in columns]
    detected: dict[str, str | None] = {name: None for name in CANONICAL_FIELDS}
    claimed: set[str] = set()

    for canonical, aliases in _ALIASES.items():
        alias_keys = {_name_key(alias) for alias in aliases}
        for column in original:
            key = _name_key(column)
            base_key = _name_key(re.split(r"/", _ascii_lower(column), maxsplit=1)[0])
            if column not in claimed and (key in alias_keys or base_key in alias_keys):
                detected[canonical] = column
                claimed.add(column)
                break

    generic_temperatures = [
        column
        for column in original
        if column.startswith("temperature_") and column not in claimed
    ]
    if detected["furnace_temperature"] is None and generic_temperatures:
        detected["furnace_temperature"] = generic_temperatures[0]
        claimed.add(generic_temperatures[0])
    if detected["sample_temperature"] is None and len(generic_temperatures) >= 2:
        detected["sample_temperature"] = generic_temperatures[1]
        claimed.add(generic_temperatures[1])

    if manual_mapping:
        unknown_roles = set(manual_mapping) - set(CANONICAL_FIELDS)
        if unknown_roles:
            raise DataReadError(f"Rôles de colonnes inconnus: {sorted(unknown_roles)}")
        for canonical, column in manual_mapping.items():
            if column not in original:
                raise DataReadError(
                    f"La colonne manuelle '{column}' n'existe pas pour le rôle '{canonical}'."
                )
            detected[canonical] = column

    return ColumnMapping(**detected)


def detect_time_unit(unit: str, header: str = "", override: str | None = None) -> str:
    """Retourne ``s``, ``min`` ou ``h`` sans déduire l'unité d'après les valeurs."""

    candidates = [override or "", unit, _unit_from_header(header)]
    for candidate in candidates:
        key = _unit_key(candidate)
        if key in _TIME_SECONDS:
            return "s"
        if key in _TIME_MINUTES:
            return "min"
        if key in _TIME_HOURS:
            return "h"
    raise DataReadError(
        "Unité de temps non reconnue. Indiquer manuellement 's', 'min' ou 'h' "
        "(variantes acceptées: sec, seconde(s), minute(s), heure(s))."
    )


def _split_parenthesized_unit(value: Any) -> tuple[str, str]:
    text = _text(value)
    match = re.match(r"^(.*?)\s*\(\s*([^()]*)\s*\)\s*$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text, _unit_from_header(text)


def _header_role(value: Any) -> str | None:
    key = _name_key(value)
    if key in _INDEX_KEYS:
        return "index"
    if key in _TIME_KEYS:
        return "time"
    if key in _TG_KEYS:
        return "tg"
    if key in _DTG_KEYS:
        return "dtg"
    if key in _HEAT_FLOW_KEYS:
        return "heat_flow"
    if (
        key in _TEMPERATURE_KEYS
        or "temperature" in key
        or key.startswith("temp")
        or key in {"tfour", "techantillon"}
    ):
        return "temperature"
    return None


def _build_header_schema(raw_headers: Iterable[Any]) -> HeaderSchema:
    raw = tuple(_text(value) for value in raw_headers)
    columns: list[str] = []
    units: dict[str, str] = {}
    counts: dict[str, int] = {}
    temperature_count = 0
    for position, source_header in enumerate(raw, start=1):
        base, unit = _split_parenthesized_unit(source_header)
        if _name_key(base) in _TEMPERATURE_KEYS:
            temperature_count += 1
            identifier = f"temperature_{temperature_count}"
        else:
            identifier = base or f"Colonne_{position}"
            count = counts.get(identifier, 0)
            counts[identifier] = count + 1
            if count:
                identifier = f"{identifier}.{count}"
        columns.append(identifier)
        units[identifier] = unit
    return HeaderSchema(raw, tuple(columns), units)


def _is_numeric_cell(value: Any) -> bool:
    text = _text(value).replace(" ", "").replace(",", ".")
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def _row_is_majority_numeric(row: Iterable[Any]) -> bool:
    values = [_text(value) for value in row]
    nonempty = [value for value in values if value]
    if not nonempty:
        return False
    numeric = sum(_is_numeric_cell(value) for value in nonempty)
    return numeric >= 2 and numeric / len(nonempty) >= 0.5


def _following_rows_are_numeric(rows: list[list[Any]], header_index: int) -> bool:
    evaluated: list[bool] = []
    for row in rows[header_index + 1 :]:
        if not any(_text(value) for value in row):
            continue
        evaluated.append(_row_is_majority_numeric(row))
        if len(evaluated) >= 8:
            break
    return bool(evaluated) and sum(evaluated) > len(evaluated) / 2


def _find_header_index(rows: list[list[Any]]) -> int:
    """Détecte l'en-tête ATG-DSC parmi au plus 50 lignes."""

    limited = rows[:50]
    for index, row in enumerate(limited):
        nonempty = [_text(value) for value in row if _text(value)]
        if len(nonempty) < 4:
            continue
        roles = [_header_role(value) for value in nonempty]
        has_time = "time" in roles
        has_index_or_time = "index" in roles or has_time
        has_temperature = "temperature" in roles
        has_signal = any(role in {"tg", "dtg", "heat_flow"} for role in roles)
        if (
            has_index_or_time
            and has_time
            and has_temperature
            and has_signal
            and _following_rows_are_numeric(limited, index)
        ):
            return index
    raise DataReadError(
        "En-tête ATG-DSC non reconnu dans les 50 premières lignes: Temps, "
        "Température et au moins un signal TG, dTG ou HeatFlow sont requis."
    )


def _data_line_bounds(rows: list[list[Any]], header_index: int) -> tuple[int, int]:
    indices = [
        index
        for index, row in enumerate(rows[header_index + 1 :], start=header_index + 1)
        if any(_text(value) for value in row)
    ]
    if not indices:
        raise DataReadError("Aucune ligne de données trouvée après l'en-tête ATG-DSC.")
    return indices[0] + 1, indices[-1] + 1


def _data_line_bounds_from_start(
    rows: list[list[Any]], data_start_index: int
) -> tuple[int, int]:
    indices = [
        index
        for index, row in enumerate(rows[data_start_index:], start=data_start_index)
        if any(_text(value) for value in row)
    ]
    if not indices:
        raise DataReadError("Aucune ligne de données trouvée après l'en-tête.")
    return indices[0] + 1, indices[-1] + 1


def _trim_trailing_empty(row: Iterable[Any]) -> list[Any]:
    values = list(row)
    while values and not _text(values[-1]):
        values.pop()
    return values


def _non_numeric_row_warnings(
    rows: list[list[Any]], header_index: int
) -> list[str]:
    line_numbers = [
        index + 1
        for index, row in enumerate(rows[header_index + 1 :], start=header_index + 1)
        if any(_text(value) for value in row) and not _row_is_majority_numeric(row)
    ]
    if not line_numbers:
        return []
    shown = ", ".join(str(value) for value in line_numbers[:10])
    suffix = "…" if len(line_numbers) > 10 else ""
    return [
        f"{len(line_numbers)} ligne(s) de données majoritairement non numérique(s) "
        f"conservée(s): {shown}{suffix}."
    ]


def _parser_metadata(
    schema: HeaderSchema,
    mapping: ColumnMapping,
    header_index: int,
    data_bounds: tuple[int, int],
) -> dict[str, Any]:
    return {
        "header_line": header_index + 1,
        "data_line_start": data_bounds[0],
        "data_line_end": data_bounds[1],
        "source_column_headers": list(schema.raw_headers),
        "column_identifiers": list(schema.columns),
        "recognized_columns": mapping.as_dict(),
        "detected_units": schema.units.copy(),
        "temperature_association": {
            "furnace_temperature": mapping.furnace_temperature,
            "sample_temperature": mapping.sample_temperature,
        },
        "dtg_present": mapping.dtg is not None,
    }


def _normalise_loaded_data(
    frame: pd.DataFrame,
    path: Path,
    file_format: str,
    mapping: ColumnMapping,
    units: dict[str, str],
    time_unit_override: str | None,
    additional_warnings: Iterable[str] | None = None,
    **kwargs: Any,
) -> ExperimentData:
    warnings: list[str] = list(additional_warnings or [])
    automatic_mapping = detect_columns(frame.columns)
    if mapping.time != automatic_mapping.time and automatic_mapping.time is not None:
        warnings.append(
            f"Association temporelle '{mapping.time}' ignorée : "
            f"l'en-tête '{automatic_mapping.time}' a été reconnu comme temps."
        )
        mapping.time = automatic_mapping.time
        metadata = kwargs.get("metadata")
        if isinstance(metadata, dict):
            metadata["recognized_columns"] = mapping.as_dict()
    if mapping.time is None:
        raise DataReadError(
            "Colonne de temps non reconnue; une association manuelle est nécessaire."
        )
    if not mapping.signal_columns():
        raise DataReadError(
            "Aucun signal TG, dTG ou HeatFlow reconnu; une association manuelle est nécessaire."
        )

    time_unit = detect_time_unit(
        units.get(mapping.time, ""), mapping.time, override=time_unit_override
    )
    original_columns = tuple(str(column) for column in frame.columns)
    result = frame.copy()
    time_values = pd.to_numeric(
        result[mapping.time]
        .astype("string")
        .str.replace(",", ".", regex=False),
        errors="coerce",
    )
    result["Temps_s"] = time_values * TIME_UNIT_SECONDS[time_unit]

    invalid = int(result["Temps_s"].isna().sum())
    if invalid:
        warnings.append(f"{invalid} valeur(s) de temps non numérique(s) ou manquante(s).")
    for role, column in mapping.signal_columns().items():
        source_values = result[column]
        present = source_values.notna() & source_values.astype("string").str.strip().ne("")
        numeric = pd.to_numeric(
            source_values.astype("string").str.replace(",", ".", regex=False),
            errors="coerce",
        )
        invalid_signal = int((present & numeric.isna()).sum())
        if invalid_signal:
            warnings.append(
                f"{invalid_signal} valeur(s) non numérique(s) dans {column} ({role}); "
                "lignes conservées."
            )

    return ExperimentData(
        source_path=path,
        file_format=file_format,
        data=result,
        original_columns=original_columns,
        mapping=mapping,
        units=units,
        warnings=warnings,
        time_unit=time_unit,
        **kwargs,
    )


def _looks_textual(text: str) -> bool:
    if not text or not any(char in text for char in "\r\n"):
        return False
    controls = sum(
        ord(char) < 32 and char not in "\r\n\t\f" for char in text[:65536]
    )
    sample_size = max(1, min(len(text), 65536))
    return controls / sample_size < 0.01 and any(char.isalnum() for char in text)


def _decode_initial_sample(raw: bytes, encoding: str) -> str:
    """Décode un bloc initial sans traiter sa frontière comme une fin de fichier."""

    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    return decoder.decode(raw, final=False)


def detect_file_format(path: str | Path) -> DetectedFileFormat:
    """Détecte XLS, XLSX ou texte à partir des premiers octets du fichier."""

    source = Path(path)
    try:
        check_input_size(source)
        with source.open("rb") as stream:
            raw = stream.read(65536)
    except OSError as exc:
        raise DataReadError(f"Impossible de lire le fichier: {exc}") from exc
    if not raw:
        raise DataReadError("Format de fichier non reconnu: le fichier est vide.")
    if raw.startswith(_XLS_MAGIC):
        return DetectedFileFormat("xls")
    if raw.startswith(b"PK"):
        check_xlsx_archive(source)
        return DetectedFileFormat("xlsx")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            text = _decode_initial_sample(raw, "utf-16")
        except UnicodeError as exc:
            raise DataReadError("Signature UTF-16 détectée, mais texte invalide.") from exc
        if _looks_textual(text):
            return DetectedFileFormat("text_utf16", "utf-16")
        raise DataReadError(
            "Format de fichier non reconnu: signature UTF-16 sans contenu textuel valide."
        )
    for kind, encoding in (("text_utf8", "utf-8-sig"), ("text_cp1252", "cp1252")):
        try:
            text = _decode_initial_sample(raw, encoding)
        except UnicodeError:
            continue
        if _looks_textual(text):
            return DetectedFileFormat(kind, encoding)
    signature = raw[:8].hex(" ").upper()
    raise DataReadError(
        "Format de fichier non reconnu. Signatures acceptées: XLS binaire, XLSX/ZIP, "
        f"UTF-16, UTF-8 ou Windows-1252 textuel. Premiers octets: {signature}."
    )
def _first_non_empty_sheet(book: pd.ExcelFile) -> str:
    for sheet in book.sheet_names:
        preview = pd.read_excel(book, sheet_name=sheet, header=None, nrows=15)
        if not preview.dropna(how="all").empty:
            return sheet
    raise DataReadError("Le classeur ne contient aucune feuille non vide.")


def _open_excel(source, detected):
    check_input_size(source)
    if detected.kind == 'xlsx':
        from openpyxl.xml.functions import iterparse as xml_iterparse
        if xml_iterparse.__module__ != 'defusedxml.common':
            raise DataReadError(tr("La protection XML est désactivée. Réinstaller les dépendances officielles de ThermalCurve."))
    book = pd.ExcelFile(source, engine=detected.engine,
                        engine_kwargs={'on_demand': True} if detected.kind == 'xls' else {})
    try:
        if detected.kind == 'xls':
            for index in range(book.book.nsheets):
                sheet = book.book.sheet_by_index(index)
                check_table_size(sheet.nrows, sheet.ncols)
                book.book.unload_sheet(index)
    except Exception:
        book.close()
        raise
    return book


def _read_spreadsheet_experiment(
    path: str | Path,
    detected: DetectedFileFormat,
    sheet_name: str | None = None,
    manual_mapping: Mapping[str, str] | None = None,
    time_unit: str | None = None,
) -> ExperimentData:
    """Lit un vrai classeur XLS/XLSX après détection dynamique de l'en-tête."""

    source = Path(path)
    try:
        book = _open_excel(source, detected)
    except Exception as exc:
        label = "XLS" if detected.kind == "xls" else "XLSX"
        raise DataReadError(f"Impossible d'ouvrir le classeur {label}: {exc}") from exc

    with book:
        available_sheets = tuple(book.sheet_names)
        if sheet_name is not None and sheet_name not in book.sheet_names:
            raise DataReadError(f"Feuille inconnue '{sheet_name}'. Feuilles: {book.sheet_names}")
        selected = sheet_name or _first_non_empty_sheet(book)
        raw_sheet = pd.read_excel(book, sheet_name=selected, header=None)
    rows = raw_sheet.replace({np.nan: None}).values.tolist()
    header_index = _find_header_index(rows)
    raw_headers = _trim_trailing_empty(rows[header_index])
    schema = _build_header_schema(raw_headers)
    data_bounds = _data_line_bounds(rows, header_index)

    raw_data = raw_sheet.iloc[header_index + 1 :, : len(schema.columns)].copy()
    raw_data = raw_data.reindex(columns=range(len(schema.columns)))
    raw_data.columns = list(schema.columns)
    frame = _coerce_numeric_columns(raw_data.dropna(how="all").reset_index(drop=True))
    units = schema.units.copy()
    mapping = detect_columns(frame.columns, manual_mapping)
    raw_meta = raw_sheet.iloc[:header_index]
    metadata_rows = [
        [_text(value) for value in row]
        for row in raw_meta.replace({np.nan: None}).values.tolist()
    ]
    metadata = {f"ligne_{index}": row for index, row in enumerate(metadata_rows, start=1)}
    parser_metadata = _parser_metadata(schema, mapping, header_index, data_bounds)

    return _normalise_loaded_data(
        frame,
        source,
        detected.display_name(source),
        mapping,
        units,
        time_unit,
        raw_metadata_rows=metadata_rows,
        metadata={
            **metadata,
            "detected_kind": detected.kind,
            "excel_engine": detected.engine,
            **parser_metadata,
        },
        sheet_name=selected,
        available_sheets=available_sheets,
        additional_warnings=_non_numeric_row_warnings(rows, header_index),
    )


def read_excel_experiment(
    path: str | Path,
    sheet_name: str | None = None,
    manual_mapping: Mapping[str, str] | None = None,
    time_unit: str | None = None,
) -> ExperimentData:
    """Lit un fichier à extension Excel après contrôle de sa signature réelle."""

    source = Path(path)

    def load() -> ExperimentData:
        detected = detect_file_format(source)
        if detected.is_spreadsheet:
            return _read_spreadsheet_experiment(
                source, detected, sheet_name, manual_mapping, time_unit
            )
        return _read_text_experiment(source, detected, manual_mapping, time_unit)

    return _load_with_fingerprint(source, load)


def _read_text_lines(
    path: Path, detected: DetectedFileFormat | None = None
) -> tuple[list[str], str]:
    detected = detected or detect_file_format(path)
    if detected.is_spreadsheet or detected.encoding is None:
        raise DataReadError("Le fichier détecté n'est pas un fichier texte.")
    try:
        text = read_limited_bytes(path, MAX_INPUT_BYTES).decode(detected.encoding)
        lines = []
        for line in StringIO(text):
            if len(lines) >= MAX_TABLE_ROWS or len(line) > MAX_TEXT_LINE_CHARS:
                raise DataReadError(tr("Fichier texte refusé : trop de lignes ou ligne trop longue. Aucune donnée n'a été tronquée."))
            lines.extend(line.splitlines())
            if len(lines) > MAX_TABLE_ROWS:
                raise DataReadError(tr("Fichier texte refusé : trop de lignes ou ligne trop longue. Aucune donnée n'a été tronquée."))
        return lines, detected.encoding
    except UnicodeError as exc:
        raise DataReadError(
            f"Le fichier n'est pas décodable avec l'encodage détecté {detected.encoding}."
        ) from exc


def _detect_delimiter(lines: list[str], header_index: int) -> str:
    if header_index >= len(lines):
        raise DataReadError("Ligne d'en-tête absente du fichier texte.")
    header = lines[header_index]
    for delimiter in ("\t", ";", ","):
        if delimiter in header:
            return delimiter
    sample = "\n".join(lines[max(0, header_index - 2) : header_index + 5])
    try:
        detected = csv.Sniffer().sniff(sample, delimiters="\t;,").delimiter
    except csv.Error as exc:
        raise DataReadError(
            "Séparateur textuel non reconnu; tabulation, point-virgule ou virgule attendu."
        ) from exc
    return detected


def _coerce_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Accepte point et virgule décimaux sans altérer les colonnes textuelles."""

    result = frame.copy()
    for column in result.columns:
        def convert(value: Any) -> Any:
            if value is None or (isinstance(value, float) and np.isnan(value)):
                return value
            text = str(value).strip()
            if not text:
                return value
            try:
                return float(text.replace(",", "."))
            except ValueError:
                return value

        result[column] = result[column].map(convert)
    return result


def _rows_from_text(lines: list[str], delimiter: str) -> list[list[str]]:
    rows = []
    width = 0
    for line in lines:
        row = next(csv.reader([line], delimiter=delimiter))
        width = max(width, len(row))
        check_table_size(len(rows) + 1, width)
        rows.append(row)
    return rows


def _find_text_header(lines: list[str]) -> tuple[str, list[list[str]], int]:
    errors: list[str] = []
    for delimiter in ("\t", ";", ","):
        rows = _rows_from_text(lines, delimiter)
        try:
            return delimiter, rows, _find_header_index(rows)
        except DataReadError as exc:
            errors.append(str(exc))
    raise DataReadError(errors[0])


def _text_layout(lines: list[str]):
    """Recognize the separate ATG units row before trying the dynamic DSC layout."""
    if len(lines) < 3:
        raise DataReadError("Le fichier texte ne contient pas l'en-tête attendu.")
    try:
        delimiter = _detect_delimiter(lines, 1)
    except DataReadError:
        delimiter, rows, header = _find_text_header(lines)
        return delimiter, rows, header, header + 1, False
    rows = _rows_from_text(lines, delimiter)
    # The classic three-line export also supports manually mapped headers.
    units = [_unit_from_units_row(value) for value in rows[2] if _text(value)]
    if len(_trim_trailing_empty(rows[1])) >= 2 and units and any(
        _unit_key(unit) in {"s", "sec", "secondes", "min", "minutes", "h", "heures", "c", "°c", "k", "mg", "%", "mw", "w"}
        or _text(value).startswith("/") for value, unit in zip([value for value in rows[2] if _text(value)], units)
    ) and not _row_is_majority_numeric(rows[2]):
        return delimiter, rows, 1, 3, True
    try:
        delimiter, rows, header = _find_text_header(lines)
        return delimiter, rows, header, header + 1, False
    except DataReadError:
        # Preserve the existing manual-mapping path for unknown units/headers.
        return delimiter, rows, 1, 3, True


def _read_text_experiment(
    source: Path,
    detected: DetectedFileFormat,
    manual_mapping: Mapping[str, str] | None,
    time_unit: str | None,
) -> ExperimentData:
    lines, encoding = _read_text_lines(source, detected)
    delimiter, rows, header_index, data_start, has_units_row = _text_layout(lines)
    minimum = data_start + 1
    if len(lines) < minimum:
        raise DataReadError(
            f"Le fichier texte doit contenir au moins {minimum} lignes pour ce format."
        )
    raw_headers = _trim_trailing_empty(rows[header_index])
    schema = _build_header_schema(raw_headers)
    columns = list(schema.columns)
    if has_units_row:
        unit_values = [
            _text(value)
            for value in next(csv.reader([lines[2]], delimiter=delimiter))
        ]
    else:
        unit_values = []
    units = schema.units.copy()
    for index, column in enumerate(columns):
        if index < len(unit_values) and unit_values[index]:
            units[column] = _unit_from_units_row(unit_values[index])
    try:
        frame = pd.read_csv(
            StringIO("\n".join(lines)),
            sep=delimiter,
            skiprows=data_start,
            names=columns,
            usecols=range(len(columns)),
            dtype=str,
            engine="python",
        )
    except Exception as exc:
        raise DataReadError(f"Impossible de lire le fichier texte: {exc}") from exc
    frame = _coerce_numeric_columns(frame.dropna(how="all").reset_index(drop=True))
    mapping = detect_columns(frame.columns, manual_mapping)
    if has_units_row:
        raw_metadata = [[lines[0].strip()], columns, unit_values]
    else:
        raw_metadata = [
            [_text(value) for value in row]
            for row in rows[:header_index]
        ]
    description = lines[0].lstrip("\ufeff").strip()
    format_label = detected.display_name(source, delimiter)
    data_bounds = (
        _data_line_bounds(rows, header_index)
        if not has_units_row
        else _data_line_bounds_from_start(rows, data_start)
    )
    parser_metadata = _parser_metadata(schema, mapping, header_index, data_bounds)

    return _normalise_loaded_data(
        frame,
        source,
        format_label,
        mapping,
        units,
        time_unit,
        description=description,
        metadata={
            "description": description,
            "encoding": encoding,
            "delimiter": delimiter,
            "units_row": unit_values,
            "detected_kind": detected.kind,
            "text_layout": "dynamic_atg_dsc" if not has_units_row else "atg_3_header_rows",
            "raw_metadata_lines": lines[:header_index],
            **parser_metadata,
        },
        raw_metadata_rows=raw_metadata,
        additional_warnings=_non_numeric_row_warnings(
            rows, header_index if not has_units_row else data_start - 1
        ),
    )


def read_text_experiment(
    path: str | Path,
    manual_mapping: Mapping[str, str] | None = None,
    time_unit: str | None = None,
) -> ExperimentData:
    """Lit un export ATG texte: description, colonnes, unités, puis données."""

    source = Path(path)

    def load() -> ExperimentData:
        detected = detect_file_format(source)
        if detected.is_spreadsheet:
            raise DataReadError(
                "Le fichier est un classeur réel; utiliser le lecteur de classeurs."
            )
        return _read_text_experiment(source, detected, manual_mapping, time_unit)

    return _load_with_fingerprint(source, load)


def load_experiment(
    path: str | Path,
    sheet_name: str | None = None,
    manual_mapping: Mapping[str, str] | None = None,
    time_unit: str | None = None,
) -> ExperimentData:
    """Route selon la signature réelle, jamais selon la seule extension."""

    source = Path(path)

    def load() -> ExperimentData:
        detected = detect_file_format(source)
        if detected.is_spreadsheet:
            return _read_spreadsheet_experiment(
                source, detected, sheet_name, manual_mapping, time_unit
            )
        return _read_text_experiment(source, detected, manual_mapping, time_unit)

    return _load_with_fingerprint(source, load)


def probe_file(path: str | Path, sheet_name: str | None = None) -> FileProbe:
    """Lit seulement la structure nécessaire à une association manuelle."""

    source = Path(path)
    detected = detect_file_format(source)
    if detected.is_spreadsheet:
        try:
            with _open_excel(source, detected) as book:
                if sheet_name is not None and sheet_name not in book.sheet_names:
                    raise DataReadError(f"Feuille inconnue '{sheet_name}'.")
                selected = sheet_name or _first_non_empty_sheet(book)
                preview = pd.read_excel(book, sheet_name=selected, header=None, nrows=50)
                sheets = list(book.sheet_names)
        except DataReadError:
            raise
        except Exception as exc:
            raise DataReadError(f"Impossible de sonder le classeur: {exc}") from exc
        preview_rows = preview.replace({np.nan: None}).values.tolist()
        header_index = _find_header_index(preview_rows)
        schema = _build_header_schema(
            _trim_trailing_empty(preview_rows[header_index])
        )
        columns = list(schema.columns)
    else:
        lines, _ = _read_text_lines(source, detected)
        delimiter, rows, header_index, _data_start, has_units_row = _text_layout(lines)
        schema = _build_header_schema(_trim_trailing_empty(rows[header_index]))
        columns = list(schema.columns)
        values = (
            [_text(value) for value in next(csv.reader([lines[2]], delimiter=delimiter))]
            if has_units_row
            else []
        )
        units = schema.units.copy()
        for index, column in enumerate(columns):
            if index < len(values) and values[index]:
                units[column] = _unit_from_units_row(values[index])
        mapping = detect_columns(columns)
        return FileProbe(source, [], None, columns, units, mapping.as_dict())

    units = schema.units.copy()
    mapping = detect_columns(columns)
    return FileProbe(source, sheets, selected, columns, units, mapping.as_dict())


def inspect_file(
    path: str | Path,
    sheet_name: str | None = None,
    manual_mapping: Mapping[str, str] | None = None,
    time_unit: str | None = None,
) -> FileInspection:
    """Produit uniquement le résumé borné autorisé pour l'inspection."""

    experiment = load_experiment(path, sheet_name, manual_mapping, time_unit)
    original = experiment.original_data()
    detected = detect_file_format(experiment.source_path)
    if detected.is_spreadsheet:
        raw_first = pd.read_excel(
            experiment.source_path,
            sheet_name=experiment.sheet_name,
            engine=detected.engine,
            header=None,
            nrows=15,
        )
        first = raw_first.replace({np.nan: None}).values.tolist()
    else:
        lines, _ = _read_text_lines(experiment.source_path, detected)
        delimiter = experiment.metadata.get("delimiter")
        if delimiter not in {"\t", ";", ","}:
            raise DataReadError("Séparateur textuel absent des métadonnées de lecture.")
        first = list(csv.reader(lines[:15], delimiter=delimiter))
    last = original.tail(5).replace({np.nan: None}).values.tolist()
    return FileInspection(
        path=experiment.source_path,
        sheet_names=list(experiment.available_sheets),
        selected_sheet=experiment.sheet_name,
        first_rows=first,
        detected_columns=experiment.mapping.as_dict(),
        shape=original.shape,
        units=experiment.units.copy(),
        last_rows=last,
    )
