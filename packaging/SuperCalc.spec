from pathlib import Path

import shiboken6
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).resolve().parent

datas = [
    (str(root / "assets"), "assets"),
    (str(root / "examples"), "examples"),
    (str(root / "docs"), "docs"),
    (str(root / "README.md"), "."),
]
datas += collect_data_files("tzdata")

a = Analysis(
    [str(root / "packaging" / "gui_entry.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "supercalc_core.plotting",
        "supercalc_core.plugins",
        "supercalc_cli.worker",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtQuick3D",
        "PySide6.QtRemoteObjects",
        "PySide6.QtSensors",
        "PySide6.QtSerialBus",
        "PySide6.QtTextToSpeech",
        "pytest",
        "_pytest",
        "hypothesis",
        "IPython",
        "pyglet",
        "scipy",
        "pandas",
    ],
    noarchive=False,
)
# Qt 6.11 uses the Windows ICU runtime. PyInstaller may incorrectly collect an
# older icuuc/icudt pair from the host; shipping those shadows the compatible
# system DLLs and prevents QtCore from loading.
a.binaries = [
    item
    for item in a.binaries
    if Path(item[0]).name.lower() not in {"icuuc.dll", "icudt78.dll"}
]
shiboken_dll = Path(shiboken6.__file__).resolve().parent / "shiboken6.abi3.dll"
a.binaries.append(("PySide6/shiboken6.abi3.dll", str(shiboken_dll), "BINARY"))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SuperCalc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "packaging" / "supercalc.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SuperCalc",
)

