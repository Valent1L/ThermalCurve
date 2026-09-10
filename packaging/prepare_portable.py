r"""Préparer Python portable hors ligne / Prepare portable Python offline.

Usage: .venv\Scripts\python.exe packaging/prepare_portable.py python-embed.zip output
The official ZIP must be downloaded separately. No installation or network access.
"""

import argparse
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = "3.14.6"
PYTHON_SHA256 = "df901e84a896ff1ee720ad03377e0c8d8c2244fda79808aeeaff6316df1cb75c"
QT_MODULES = {"Core", "Gui", "Widgets", "Network", "Svg"}
QT_PLUGINS = {"platforms", "imageformats", "iconengines", "styles", "generic", "networkinformation", "tls"}


def runtime_file(path):
    """Keep runtime packages and the same Qt module set as the existing application."""
    if {"..", "__pycache__", "tests", "test"}.intersection(path.parts):
        return False
    if path.suffix.lower() in {".pyc", ".pyo", ".exe"} or path.name == "direct_url.json":
        return False
    if path.parts[0] != "PySide6":
        return True
    if len(path.parts) == 2:
        return (path.suffix == ".py" or path.name == "pyside6.abi3.dll"
                or path.name == "opengl32sw.dll"
                or path.name.lower().startswith(("msvcp140", "vcruntime140"))
                or any(path.name in {f"Qt{module}.pyd", f"Qt6{module}.dll"} for module in QT_MODULES))
    return (path.parts[1] == "support" and path.suffix == ".py"
            or path.parts[1] == "translations" and path.name in {"qtbase_fr.qm", "qtbase_en.qm"}
            or path.parts[1] == "plugins" and path.parts[2] in QT_PLUGINS
            and path.suffix == ".dll" and "pdf" not in path.name.lower())


def prepare(embedded_zip, output):
    if sys.version_info[:3] != (3, 14, 6) or sys.platform != "win32":
        raise ValueError("Préparation requise sous Windows avec Python 3.14.6 / Build on Windows with Python 3.14.6")
    with embedded_zip.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != PYTHON_SHA256:
            raise ValueError("Empreinte Python incorrecte / Incorrect Python checksum")
    output.mkdir(parents=True, exist_ok=False)
    with ZipFile(embedded_zip) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive Python corrompue / Corrupt Python archive")
        archive.extractall(output)  # Exact official archive authenticated above.
    site = output / "Lib/site-packages"
    site.mkdir(parents=True)
    packages = {}
    pending = [Requirement(line) for line in (ROOT / "requirements.txt").read_text().splitlines()
               if line.strip() and not line.startswith("#")]
    while pending:
        requirement = pending.pop()
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        package = distribution(requirement.name)
        name = package.metadata["Name"]
        if package.version not in requirement.specifier:
            raise ValueError(f"Version incompatible / Incompatible version: {requirement}, {package.version}")
        if name in packages:
            continue
        packages[name] = package.version
        pending.extend(Requirement(value) for value in package.requires or ())
        for file in package.files or ():
            relative = Path(file)
            if relative.is_absolute() or not runtime_file(relative):
                continue
            source = Path(package.locate_file(file))
            target = site / relative
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"Fichier manquant ou lié / Missing or linked file: {source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    (output / "python314._pth").write_text(
        "python314.zip\n.\nLib/site-packages\n..\n", encoding="ascii")
    provenance = {"python": PYTHON_VERSION, "archive_sha256": PYTHON_SHA256,
                  "source": "https://www.python.org/downloads/release/python-3146/",
                  "packages": dict(sorted(packages.items())), "qt_modules": sorted(QT_MODULES)}
    (output / "PORTABLE_RUNTIME.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"Python {PYTHON_VERSION}: {output}; {len(packages)} packages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("embedded_zip", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.embedded_zip, args.output)
