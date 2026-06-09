from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST_EXE = ROOT / "dist" / "EVE Local Intel Scanner" / "EVE Local Intel Scanner.exe"
SETUP_EXE = ROOT / "installer_output" / "EVE_Local_Intel_Scanner_Setup.exe"


def ok(message: str):
    print(f"[OK] {message}")


def warn(message: str):
    print(f"[WARN] {message}")


def fail(message: str):
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def check_required_files():
    required = [
        "main.py",
        "ui.py",
        "zkill_panel.py",
        "local_intel_updater.py",
        "EVE Local Intel Scanner.spec",
        "installer.iss",
        "zkillCharLoad.py",
        "zkillKillLoad.py",
    ]

    for name in required:
        path = ROOT / name
        if not path.exists():
            fail(f"Missing required file: {name}")

    icon_path = ROOT / "assets" / "icons" / "app.ico"
    if icon_path.exists():
        ok("assets/icons/app.ico found")
    else:
        warn("assets/icons/app.ico not found; exe/setup may use default icon")

    ok("required project files checked")


def compile_all_py():
    errors = []

    for path in sorted(ROOT.glob("*.py")):
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as e:
            errors.append(f"{path.name}: {e}")

    if errors:
        fail("Python compile errors:\n" + "\n".join(errors))

    ok("all Python files compile")


def check_pyinstaller_available():
    try:
        import PyInstaller  # noqa: F401
        ok("PyInstaller import ok")
    except Exception:
        fail("PyInstaller is not installed in the current venv")


def check_dist_after_pyinstaller():
    if not DIST_EXE.exists():
        fail(f"PyInstaller output not found: {DIST_EXE}")

    ok(f"PyInstaller output exists: {DIST_EXE}")


def check_setup_after_inno():
    if not SETUP_EXE.exists():
        fail(f"Setup.exe output not found: {SETUP_EXE}")

    ok(f"Setup.exe output exists: {SETUP_EXE}")


def main():
    mode = sys.argv[1].lower().strip() if len(sys.argv) > 1 else "pre"

    if mode == "pre":
        check_required_files()
        compile_all_py()
        check_pyinstaller_available()
        ok("preflight checks passed")
        return

    if mode == "post-pyinstaller":
        check_dist_after_pyinstaller()
        ok("post-pyinstaller checks passed")
        return

    if mode == "post-inno":
        check_setup_after_inno()
        ok("post-inno checks passed")
        return

    fail(f"Unknown mode: {mode}")


if __name__ == "__main__":
    main()
