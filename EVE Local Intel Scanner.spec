# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_dir = Path.cwd()

datas = []

if (project_dir / "assets").exists():
    datas.append(("assets", "assets"))

if (project_dir / "ships.json").exists():
    datas.append(("ships.json", "."))

# zKill is rendered by the native/API viewer now.
# Do not package old browser loader scripts or QtWebEngine assets.

icon_candidate = project_dir / "assets" / "icons" / "app.ico"
app_icon = str(icon_candidate) if icon_candidate.exists() else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtNetwork",
        "sqlite3",
        "requests",
        "pyperclip",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngine",
        "pyppeteer",
        "selenium",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EVE Local Intel Scanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EVE Local Intel Scanner",
)
