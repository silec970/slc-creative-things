from pathlib import Path

root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(root / "packaging" / "cli_entry.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[(str(root / "examples"), "examples")],
    hiddenimports=["supercalc_cli.worker"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6",
        "matplotlib",
        "supercalc_gui",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SuperCalcCLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(root / "packaging" / "supercalc.ico"),
)

