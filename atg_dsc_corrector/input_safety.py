"""Bounds for imported data and local-only automatic project references."""
from pathlib import Path, PureWindowsPath
import ntpath
import os
import posixpath
import re
import stat
from zipfile import BadZipFile, ZipFile

from defusedxml.ElementTree import iterparse
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

from .i18n import tr

MAX_INPUT_BYTES = 100 * 1024 * 1024
MAX_PROJECT_BYTES = 10 * 1024 * 1024
MAX_XLSX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_XLSX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_XLSX_MEMBERS = 10000
MAX_TABLE_CELLS = 5_000_000
MAX_TABLE_ROWS = 1_000_000
MAX_TABLE_COLUMNS = 4096
MAX_TEXT_LINE_CHARS = 1_048_576


class DataReadError(ValueError):
    """An input cannot be read safely or interpreted reliably."""


def check_input_size(path, limit=None):
    if limit is None:
        limit = MAX_INPUT_BYTES
    info = Path(path).stat()
    if not stat.S_ISREG(info.st_mode):
        raise DataReadError(tr("Un fichier ordinaire est requis : {path}", path=str(path)))
    if info.st_size > limit:
        raise DataReadError(tr("Fichier trop volumineux (limite : {limit} Mio) : {path}",
                               limit=limit // (1024 * 1024), path=str(path)))


def read_limited_bytes(path, limit):
    check_input_size(path, limit)
    with Path(path).open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise DataReadError(tr("Le fichier a dépassé la limite de lecture : {path}", path=str(path)))
    return data


def check_table_size(rows, columns):
    if rows > MAX_TABLE_ROWS or columns > MAX_TABLE_COLUMNS or rows * columns > MAX_TABLE_CELLS:
        raise DataReadError(tr("Tableau trop volumineux : maximum {rows} lignes, {columns} colonnes et {cells} cellules. Aucune donnée n'a été tronquée.",
                               rows=MAX_TABLE_ROWS, columns=MAX_TABLE_COLUMNS, cells=MAX_TABLE_CELLS))


def require_automatic_local_path(path):
    """Reject network/device paths before filesystem calls, then indirect paths.

    Deliberately do not resolve links here: their targets may be remote.
    Explicit user-selected imports and relocated sources use the normal reader.
    """
    message = tr("Accès automatique refusé pour une source réseau ou un lien : {path}. Utiliser une copie locale du fichier.", path=str(path))
    windows = PureWindowsPath(path)
    if (windows.drive.startswith('\\') or str(path).startswith(('//', '\\'))
            or ntpath.isreserved(str(path)) or (os.name != 'nt' and windows.drive)):
        raise DataReadError(message)
    local = Path(os.path.abspath(path))  # Lexical only; never Path.resolve().
    if os.name == 'nt':
        import ctypes
        get_drive_type = ctypes.WinDLL('kernel32', use_last_error=True).GetDriveTypeW
        get_drive_type.argtypes = [ctypes.c_wchar_p]
        get_drive_type.restype = ctypes.c_uint
        if get_drive_type(local.anchor) not in (2, 3, 5, 6):
            raise DataReadError(message)
    for part in (*reversed(local.parents), local):
        try:
            info = part.lstat()
        except (FileNotFoundError, NotADirectoryError):
            break
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_reparse_tag', 0) in (
            getattr(stat, 'IO_REPARSE_TAG_SYMLINK', 0xA000000C),
            getattr(stat, 'IO_REPARSE_TAG_MOUNT_POINT', 0xA0000003),
        ):
            raise DataReadError(message)


def check_xlsx_archive(path):
    """Bound decompression and sparse sheet extents before pandas allocates rows."""
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if (len(entries) > MAX_XLSX_MEMBERS
                    or sum(item.file_size for item in entries) > MAX_XLSX_EXPANDED_BYTES
                    or any(item.file_size > MAX_XLSX_MEMBER_BYTES or item.flag_bits & 1 for item in entries)):
                raise DataReadError(tr("Classeur XLSX refusé : contenu décompressé trop volumineux ou chiffré."))
            # Relationships may point to worksheets with nonstandard names/extensions.
            worksheets = set()
            for item in sorted(entries, key=lambda item: not item.filename.endswith('.rels')):
                if not item.filename.lower().endswith(('.xml', '.rels')) and item.filename not in worksheets:
                    continue
                with archive.open(item) as stream:
                    stack = []
                    rows = columns = 0
                    current_row = current_column = 0
                    worksheet = False
                    for event, element in iterparse(stream, events=('start', 'end'), forbid_dtd=True):
                        if event == 'start':
                            stack.append(element)
                            if len(stack) > 64:
                                raise DataReadError(tr("Classeur XLSX refusé : structure XML trop profonde."))
                            tag = element.tag.rsplit('}', 1)[-1]
                            if len(stack) == 1:
                                worksheet = tag == 'worksheet'
                            if tag == 'Relationship' and element.get('Type', '').endswith('/worksheet'):
                                target = element.get('Target', '')
                                base = posixpath.dirname(posixpath.dirname(item.filename))
                                worksheets.add(posixpath.normpath(posixpath.join(base, target)).lstrip('/'))
                            if worksheet and tag == 'row':
                                value = element.get('r', str(current_row + 1))
                                if not re.fullmatch(r'[1-9][0-9]{0,6}', value):
                                    raise DataReadError(tr("Classeur XLSX refusé : coordonnées de cellule invalides."))
                                current_row, current_column = int(value), 0
                                rows = max(rows, current_row)
                            elif worksheet and tag == 'c':
                                current_column += 1
                                if 'r' in element.attrib:
                                    match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})', element.attrib['r'])
                                    if not match:
                                        raise DataReadError(tr("Classeur XLSX refusé : coordonnées de cellule invalides."))
                                    current_column = 0
                                    for char in match[1]:
                                        current_column = current_column * 26 + ord(char) - ord('A') + 1
                                    rows = max(rows, int(match[2]))
                                columns = max(columns, current_column)
                            check_table_size(rows, columns)
                        else:
                            stack.pop()
                            if stack:
                                stack[-1].remove(element)
                            element.clear()
    except (BadZipFile, DefusedXmlException, ParseError, RuntimeError, NotImplementedError) as exc:
        raise DataReadError(tr("Classeur XLSX invalide ou contenu XML interdit.")) from exc
