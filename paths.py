from pathlib import Path
import os
import sys


APP_NAME = "EVE Local Intel Scanner"


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


def get_user_data_dir() -> Path:
    """Writable per-user app data directory.

    Program files can be read-only for normal users, so all mutable files go here:
    - data/local_intel.sqlite
    - killmails/*.tar.bz2
    - user.json
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")

        if base:
            return Path(base) / APP_NAME

        return Path.home() / "AppData" / "Local" / APP_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME


SOURCE_DIR = get_source_dir()
EXE_DIR = get_exe_dir()
BUNDLE_DIR = get_bundle_dir()
USER_DATA_DIR = get_user_data_dir()


def ensure_user_data_dirs() -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (USER_DATA_DIR / "data").mkdir(parents=True, exist_ok=True)
    (USER_DATA_DIR / "killmails").mkdir(parents=True, exist_ok=True)


def user_data_path(relative_path: str | Path) -> Path:
    ensure_user_data_dirs()
    return USER_DATA_DIR / Path(relative_path)


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
