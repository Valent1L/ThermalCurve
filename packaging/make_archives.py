"""Archives sources et Python portable / Source and portable Python archives."""

import hashlib
import argparse
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


def archive(path, files, base, prefix, extras=()):
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as output:
        for file in sorted(files):
            if file.is_file():
                output.write(file, str(Path(prefix) / file.relative_to(base)))
        for file, relative in extras:
            output.write(file, str(Path(prefix) / relative))
    with ZipFile(path) as output:
        assert output.testzip() is None, path.name


def main(portable_runtime=None):
    destination = DIST if portable_runtime is None else ROOT / "dist" / f"{PREFIX}-portable"
    source = destination / f"{PREFIX}-source.zip"
    manifest = destination / "SHA256SUMS.txt"
    archives = [source]
    if portable_runtime is not None:
        portable_runtime = Path(portable_runtime).resolve()
        for name in ("python.exe", "pythonw.exe", "python314._pth", "PORTABLE_RUNTIME.json"):
            if not (portable_runtime / name).is_file():
                raise FileNotFoundError(portable_runtime / name)
        archives.extend((destination / f"{PREFIX}-windows-x64-portable.zip",
                         destination / f"{PREFIX}-third-party-sources.zip"))
    destination.mkdir(parents=True, exist_ok=True)
    if any(path.name not in {manifest.name, *(p.name for p in archives)} for path in destination.iterdir()):
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
    if portable_runtime is not None:
        runtime_files = [file for file in portable_runtime.rglob("*") if file.is_file()]
        if any(file.is_symlink() or file.name.lower() == "thermalcurve.exe"
               or {".venv", "__pycache__"}.intersection(file.relative_to(portable_runtime).parts)
               for file in runtime_files):
            raise ValueError("Contenu portable inattendu / Unexpected portable content")
        extras = [(file, Path("python") / file.relative_to(portable_runtime)) for file in runtime_files]
        extras.append((ROOT / "packaging/Lancer_ThermalCurve.cmd", Path("Lancer_ThermalCurve.cmd")))
        archive(archives[1], sources, ROOT, PREFIX, extras)
        upstream = ROOT / ".tmp/third-party-sources"
        upstream_files = []
        for line in (ROOT / "licenses/SOURCE_ARCHIVES_SHA256.txt").read_text().splitlines():
            expected, name = line.split(maxsplit=1)
            if Path(name).name != name:
                raise ValueError(name)
            file = upstream / name
            with file.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError(f"Empreinte incorrecte / Incorrect checksum: {name}")
            upstream_files.append(file)
        archive(archives[2], upstream_files, upstream, f"{PREFIX}-third-party-sources")
    checksums = []
    for file in archives:
        with file.open("rb") as stream:
            checksums.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {file.name}")
        print(f"{file}: {file.stat().st_size} bytes")
    manifest.write_text("\n".join(checksums) + "\n", encoding="ascii")
    print(manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable-runtime", type=Path)
    main(parser.parse_args().portable_runtime)
