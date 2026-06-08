from pathlib import Path
import sys


def get_source_dir() -> Path:
    return Path(__file__).resolve().parent


def get_exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return get_source_dir()


def get_bundle_dir() -> Path:
    # PyInstaller onefile / onedir internal directory
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()

    return get_source_dir()


SOURCE_DIR = get_source_dir()
EXE_DIR = get_exe_dir()
BUNDLE_DIR = get_bundle_dir()


def resource_path(relative_path: str) -> str:
    candidates = [
        EXE_DIR / relative_path,
        BUNDLE_DIR / relative_path,
        SOURCE_DIR / relative_path,
    ]

    for path in candidates:
        if path.exists():
            return str(path)

    return str(candidates[0])


def icon_path(filename: str) -> str:
    return resource_path(str(Path("assets") / "icons" / filename))


def app_path(filename: str) -> str:
    return resource_path(filename)