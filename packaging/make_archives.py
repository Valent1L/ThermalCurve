"""Archives de distribution à liste explicite / Allowlisted release archives."""

import hashlib
from pathlib import Path
import tomllib
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED


ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
PREFIX = f"ThermalCurve-{VERSION}"
DIST = ROOT / "dist"


def archive(path, files, base, prefix, compression=ZIP_DEFLATED):
    with ZipFile(path, "w", compression=compression) as output:
        for file in sorted(files):
            if file.is_file():
                output.write(file, str(Path(prefix) / file.relative_to(base)))
    with ZipFile(path) as output:
        assert output.testzip() is None, path.name


def main():
    upstream = ROOT / ".tmp/third-party-sources"
    expected = (ROOT / "licenses/SOURCE_ARCHIVES_SHA256.txt").read_text(encoding="ascii").splitlines()
    assert expected, "Missing source archive checksums"
    for line in expected:
        checksum, name = line.split("  ", 1)
        with (upstream / name).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == checksum, name
    folder = DIST / f"{PREFIX}-windows-x64" / "ThermalCurve"
    assert (folder / "ThermalCurve.exe").is_file()
    for example in (ROOT / "Exemple").rglob("*"):
        if example.is_file():
            packaged = folder / example.relative_to(ROOT)
            assert packaged.is_file() and packaged.read_bytes() == example.read_bytes(), packaged
    assert (folder / "changelog.md").is_file()
    files = list(folder.rglob("*"))
    forbidden = {".git", ".venv", ".codex", ".agents", "__pycache__", ".pytest_cache"}
    assert not any(forbidden.intersection(file.parts) or (
        file.suffix == ".atgproj" and not file.is_relative_to(folder / "Exemple")
    ) for file in files)
    binary = DIST / f"{PREFIX}-windows-x64.zip"
    archive(binary, files, folder, "ThermalCurve")

    sources = [ROOT / name for name in (
        "README.md", "README_EN.md", "changelog.md", "LICENSE.txt", "THIRD_PARTY_NOTICES.txt",
        "pyproject.toml", "requirements.txt", "run_qt.py", "atg_dsc_corrector_qt.spec", ".gitattributes",
    )]
    for directory in ("atg_dsc_corrector", "licenses", "packaging", "Exemple"):
        sources.extend(file for file in (ROOT / directory).rglob("*")
                       if file.is_file() and "__pycache__" not in file.parts
                       and file.suffix not in {".pyc", ".pyo"})
    source = DIST / f"{PREFIX}-source.zip"
    archive(source, sources, ROOT, PREFIX)

    third_party = DIST / f"{PREFIX}-third-party-sources.zip"
    archive(third_party, (upstream / line.split("  ", 1)[1] for line in expected),
            upstream, "third-party-sources", ZIP_STORED)
    checksums = []
    for path in (binary, source, third_party):
        with path.open("rb") as stream:
            checksums.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.name}")
        print(f"{path.name}: {path.stat().st_size} bytes")
    (DIST / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
