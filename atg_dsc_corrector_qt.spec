# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)


datas = collect_data_files("matplotlib") + [
    ("atg_dsc_corrector/resources/mendeleev/v0.20.0", "atg_dsc_corrector/resources/mendeleev/v0.20.0"),
]

a = Analysis(
    ["run_qt.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["xlrd", "openpyxl"],
    hookspath=["packaging/hooks"],
    hooksconfig={"matplotlib": {"backends": ["QtAgg", "Agg", "svg", "pdf"]}},
    runtime_hooks=[],
    excludes=["pytest", "xlwt", "tkinter", "IPython"],
    noarchive=False,
    optimize=1,
)
assert not any("virtualkeyboard" in entry[0].lower() or "qt6pdf" in entry[0].lower()
               for entry in a.binaries), "Unexpected Qt components in this release"
assert not any("codex-runtimes" in entry[1].lower() for entry in a.binaries), \
    "Build with a clean PATH; external runtime DLLs must not enter the release"
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ThermalCurve",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=VSVersionInfo(
        ffi=FixedFileInfo(filevers=(1, 0, 0, 0), prodvers=(1, 0, 0, 0), fileType=1),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("ProductName", "ThermalCurve"),
                StringStruct("FileDescription", "ThermalCurve - Analyse thermique / Thermal analysis"),
                StringStruct("FileVersion", "1.0.0"),
                StringStruct("ProductVersion", "1.0.0"),
                StringStruct("LegalCopyright", "© 2026 Valentin Legrand"),
                StringStruct("OriginalFilename", "ThermalCurve.exe"),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    ),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ThermalCurve")
