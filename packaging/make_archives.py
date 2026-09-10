"""ZIP des sources sans exécutable / Source-only release ZIP."""

import hashlib
from pathlib import Path
import tomllib
from zipfile import ZipFile, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
PREFIX = f"ThermalCurve-{VERSION}"
DIST = ROOT / "dist" / f"{PREFIX}-sources"
SOURCE_FILES = (
    "README.md", "README_EN.md", "changelog.md", "LICENSE.txt", "THIRD_PARTY_NOTICES.txt",
    "pyproject.toml", "requirements.txt", "run_qt.py", "atg_dsc_corrector_qt.spec", ".gitattributes",
)


def archive(path, files, base, prefix):
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as output:
        for file in sorted(files):
            if file.is_file():
                output.write(file, str(Path(prefix) / file.relative_to(base)))
    with ZipFile(path) as output:
        assert output.testzip() is None, path.name


def main():
    source = DIST / f"{PREFIX}-source.zip"
    manifest = DIST / "SHA256SUMS.txt"
    DIST.mkdir(parents=True, exist_ok=True)
    if any(path.name not in {source.name, manifest.name} for path in DIST.iterdir()):
        raise ValueError("Dossier de publication non vide : utiliser un dossier dédié aux sources. / Use a dedicated source-only release folder.")
    sources = [ROOT / name for name in SOURCE_FILES]
    for file in sources:
        if not file.is_file():
            raise FileNotFoundError(file)
    forbidden = {".git", ".venv", ".codex", ".agents", ".tmp", "__pycache__", ".pytest_cache", "build", "dist"}
    binaries = {".exe", ".dll", ".pyd", ".so", ".dylib", ".pyc", ".pyo"}
    for directory in ("atg_dsc_corrector", "licenses", "packaging", "Exemple"):
        sources.extend(file for file in (ROOT / directory).rglob("*")
                       if file.is_file() and not file.is_symlink()
                       and not forbidden.intersection(file.relative_to(ROOT).parts)
                       and file.suffix.lower() not in binaries
                       and (file.suffix.lower() != ".atgproj" or file.is_relative_to(ROOT / "Exemple")))
    archive(source, sources, ROOT, PREFIX)
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest.write_text(f"{digest}  {source.name}\n", encoding="ascii")
    print(f"{source}: {source.stat().st_size} bytes")
    print(manifest)


if __name__ == "__main__":
    main()
