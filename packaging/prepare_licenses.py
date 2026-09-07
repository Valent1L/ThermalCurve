"""Collecte locale des notices vérifiées / Collect verified local notices.

Run after downloading the official source archives recorded in J40.
Does not install packages, fetch data, or change the virtual environment.
"""

from importlib.metadata import distribution
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import sys
import tarfile
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "licenses"
ARCHIVES = ROOT / ".tmp/third-party-sources"
PACKAGES = (
    "PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "matplotlib",
    "numpy", "pandas", "openpyxl", "xlrd", "contourpy", "cycler", "fonttools",
    "kiwisolver", "packaging", "pillow", "pyparsing", "python-dateutil", "tzdata",
    "et-xmlfile", "six", "PyInstaller", "typing_extensions",
)


def write_notice(relative, data):
    target = (DEST / relative).resolve()
    if not target.is_relative_to(DEST.resolve()):
        raise ValueError(f"Unsafe notice path: {relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def is_notice(name):
    path = PurePosixPath(name.lower())
    if path.suffix in {".py", ".pyc", ".pyd", ".dll"}:
        return False
    return (path.name.startswith(("license", "licence", "copying", "copyright", "notice", "authors"))
            or "licenses" in path.parts)


def main():
    required = {f"{name}-everywhere-src-6.11.1.zip" for name in
                ("qtbase", "qtsvg", "qtimageformats", "qttranslations", "pyside-setup")}
    required.update({"openpyxl-3.1.5.tar.gz", "et_xmlfile-2.0.0.tar.gz"})
    if not required.issubset({path.name for path in ARCHIVES.glob("*")}):
        raise ValueError("Archives officielles manquantes / Missing official archives in .tmp/third-party-sources")
    index = [
        "ThermalCurve - Licences tierces / Third-party licenses", "",
        "FR : Textes conservés depuis les paquets installés et archives officielles.",
        "Les notices Qt incluent un ensemble conservateur de contributions tierces.",
        "La présence d'une notice n'implique pas l'utilisation de tout le composant.",
        "Qt/PySide sont utilisés sous LGPL v3. Voir Qt/*/LICENSES/LGPL-3.0-only.txt",
        "et GPL-3.0-only.txt. Sources et remplacement : voir QT_SOURCES.txt.", "",
        "EN: Texts retained from installed packages and official source archives.",
        "Qt notices include a conservative set of third-party contributions.",
        "A notice does not imply that the entire component is used.",
        "Qt/PySide are used under LGPL v3. See Qt/*/LICENSES/LGPL-3.0-only.txt",
        "and GPL-3.0-only.txt. Sources and replacement: see QT_SOURCES.txt.", "",
    ]
    for name in PACKAGES:
        package = distribution(name)
        index.append(f"{name} {package.version}")
        for file in package.files or ():
            if is_notice(str(file)):
                write_notice(Path("Python-packages") / name / str(file), package.locate_file(file).read_bytes())
    write_notice(Path("Python") / "LICENSE.txt", (Path(sys.base_prefix) / "LICENSE.txt").read_bytes())
    for archive in sorted(ARCHIVES.glob("*.zip")):
        with ZipFile(archive) as source:
            if source.testzip() is not None:
                raise ValueError(f"Corrupt source archive: {archive.name}")
            names = set(source.namelist())
            selected = {name for name in names if not name.endswith("/") and is_notice(name)}
            for name in names:
                if name.endswith("qt_attribution.json") and "/src/" in name:
                    selected.add(name)
                    # Qt notices can contain literal newlines in JSON strings.
                    data = json.loads(source.read(name), strict=False)
                    for record in data if isinstance(data, list) else [data]:
                        if record.get("LicenseFile"):
                            notice = posixpath.normpath(posixpath.join(posixpath.dirname(name), record["LicenseFile"]))
                            if notice not in names:
                                raise ValueError(f"Missing Qt notice: {notice}")
                            selected.add(notice)
            for name in sorted(selected):
                write_notice(Path("Qt") / name, source.read(name))
    for archive in sorted(ARCHIVES.glob("*.tar.gz")):
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                if member.isfile() and is_notice(member.name):
                    write_notice(Path("Python-sources") / member.name, source.extractfile(member).read())
    write_notice(Path("Mendeleev") / "LICENSE", (ROOT / "atg_dsc_corrector/resources/mendeleev/v0.20.0/LICENSE").read_bytes())
    write_notice(Path("Mendeleev") / "PROVENANCE.md", (ROOT / "atg_dsc_corrector/resources/mendeleev/v0.20.0/PROVENANCE.md").read_bytes())
    write_notice("INDEX.txt", ("\n".join(index) + "\n").encode("utf-8"))
    checksums = []
    for path in sorted(ARCHIVES.iterdir()):
        if path.is_file():
            with path.open("rb") as stream:
                checksums.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.name}")
    write_notice("SOURCE_ARCHIVES_SHA256.txt", ("\n".join(checksums) + "\n").encode("ascii"))
    assert list(DEST.rglob("LGPL-3.0-only.txt")) and list(DEST.rglob("GPL-3.0-only.txt"))
    print(f"Collected {sum(p.is_file() for p in DEST.rglob('*'))} notices")


if __name__ == "__main__":
    main()
